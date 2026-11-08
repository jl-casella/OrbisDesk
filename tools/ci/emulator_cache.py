#!/usr/bin/env python3
"""Bind an emulator-only cache to restored fork sources, toolchain and build recipes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
from common import ROOT, RESULTS, phase, revision, run, sha, write_json

BUNDLE = ROOT / '.deps/emulator-cache'
INPUTS = RESULTS / 'emulator-inputs.json'
FILES = {'shadps4', 'build-manifest.json', 'source.patch', 'cache-proof.json'}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def output(name, value):
    if os.environ.get('GITHUB_OUTPUT'):
        with Path(os.environ['GITHUB_OUTPUT']).open('a') as stream:
            stream.write(name + '=' + str(value) + '\n')


def submodules(lines):
    result = []
    for line in lines:
        if not line or line[0] != ' ':
            raise ValueError('Uninitialized or changed fork submodule: ' + line)
        commit, path, *_ = line[1:].split()
        result.append({'path': path, 'commit': commit})
    return sorted(result, key=lambda entry: entry['path'])


def source_identity():
    source = ROOT / '.deps/shadPS4-fork'
    def git(*args):
        return subprocess.check_output(['git', '-c', 'core.autocrlf=true', '-c', 'diff.ignoreSubmodules=all',
                                        '-C', str(source), *args])
    patch = git('diff', 'HEAD', '--binary')
    modules = submodules(git('submodule', 'status', '--recursive').decode().splitlines())
    for module in modules:
        command = ['git', '-c', 'core.autocrlf=true', '-C', str(source / module['path'])]
        changed = subprocess.run([*command, 'diff', '--quiet', '--ignore-submodules=all', 'HEAD', '--'])
        extra = subprocess.check_output([*command, 'ls-files', '--others', '--exclude-standard'])
        if changed.returncode or extra.strip():
            raise ValueError('Fork submodule has unrecorded source edits: ' + module['path'])
    return {'commit': git('rev-parse', 'HEAD').decode().strip(),
            'tree': git('rev-parse', 'HEAD^{tree}').decode().strip(),
            'patch_sha256': hashlib.sha256(patch).hexdigest(),
            'submodules': modules}


def make_inputs():
    fork_restore = json.loads((ROOT / 'dependencies.lock.json').read_text())['shadps4_fork']
    source = source_identity()
    if source['tree'] != fork_restore['expected_head_tree'] or source['patch_sha256'] != fork_restore['overlay']['sha256']:
        raise ValueError('Fork tree/overlay differs from the locked restoration inputs')
    tools = {}
    paths = {'cmake': ROOT / '.deps/linux-tools/cmake/data/bin/cmake',
             'ninja': ROOT / '.deps/linux-tools/bin/ninja', 'python': Path(sys.executable)}
    for name in ('clang-19', 'clang++-19', 'ld.lld-19', 'clang-scan-deps-19', 'ccache', 'git', 'pkg-config'):
        path = shutil.which(name)
        if not path:
            raise ValueError('Missing cache toolchain input: ' + name)
        paths[name] = Path(path)
    for name, path in paths.items():
        tools[name] = {'path': str(path), 'sha256': sha(path),
                       'version': subprocess.check_output([str(path), '--version'], text=True).strip()}
    toolchain = {'tools': tools, 'architecture': platform.machine(),
                 'packages': subprocess.check_output(['dpkg-query', '-W', '-f=${binary:Package}=${Version}\n'], text=True).splitlines(),
                 'os_release': Path('/etc/os-release').read_text()}
    inputs = {'schema_version': 1, 'source': source, 'toolchain': toolchain,
              'checkout_path': str(ROOT), 'jobs': 2, 'ccache_enabled': True,
              'environment': {k: os.environ.get(k, '') for k in ('CFLAGS', 'CXXFLAGS', 'CPPFLAGS', 'LDFLAGS',
                  'CMAKE_PREFIX_PATH', 'PKG_CONFIG_PATH', 'PKG_CONFIG_LIBDIR', 'LIBRARY_PATH',
                  'CPATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH', 'LD_LIBRARY_PATH')},
              'recipes': {name: sha(ROOT / name) for name in ('tools/build-shad-linux.py',
                  'tools/shad-linux-toolchain.cmake', 'tools/logged_process.py', 'tools/restore-dependencies.py',
                  'tools/ci/emulator_cache.py')},
              'fork_lock': json.loads((ROOT / 'fork.lock.json').read_text()),
              'fork_restore': fork_restore}
    return inputs, fingerprint(toolchain)


def key():
    inputs, toolchain_key = make_inputs()
    record = {'inputs': inputs, 'key': fingerprint(inputs), 'toolchain_key': toolchain_key,
              'requested_by_source_sha': revision()}
    write_json(INPUTS, record)
    output('key', record['key'])
    output('toolchain_key', toolchain_key)
    print(json.dumps({'emulator_cache_key': record['key'], 'toolchain_key': toolchain_key}), flush=True)


def validate_bundle(bundle, record):
    if {p.name for p in bundle.iterdir()} != FILES or any(p.is_symlink() or not p.is_file() for p in bundle.iterdir()):
        raise ValueError('Unexpected emulator cache files')
    proof = json.loads((bundle / 'cache-proof.json').read_text())
    if proof['key'] != record['key'] or proof['inputs'] != record['inputs']:
        raise ValueError('Emulator cache input identity differs')
    manifest_path = bundle / 'build-manifest.json'
    if sha(manifest_path) != proof['manifest_sha256']:
        raise ValueError('Cached build manifest was altered')
    manifest = json.loads(manifest_path.read_text())
    source = record['inputs']['source']
    if (manifest['commit'] != source['commit'] or manifest['source_patch_sha256'] != source['patch_sha256'] or
            submodules(manifest['submodules']) != source['submodules'] or
            sha(bundle / 'source.patch') != source['patch_sha256']):
        raise ValueError('Cached build does not match the restored fork/patches/submodules')
    binary = bundle / 'shadps4'
    with binary.open('rb') as stream:
        if stream.read(5) != b'\x7fELF\x02':
            raise ValueError('Cached emulator is not ELF64')
    if binary.stat().st_size < 64 or sha(binary) != manifest['executable_sha256']:
        raise ValueError('Cached emulator binary was altered')
    return manifest


def build():
    start = time.monotonic()
    record = json.loads(INPUTS.read_text())
    current, _ = make_inputs()
    if fingerprint(current) != record['key'] or current != record['inputs']:
        raise ValueError('Emulator inputs changed after cache key generation')
    destination = ROOT / 'build/shadPS4-linux'
    destination.mkdir(parents=True, exist_ok=True)
    reused = BUNDLE.exists() and os.environ.get('CI_CACHE_MODE') == 'reuse'
    if reused:
        with phase('emulator-cache-restore'):
            validate_bundle(BUNDLE, record)
            for name in ('shadps4', 'build-manifest.json', 'source.patch'):
                shutil.copyfile(BUNDLE / name, destination / name)
            (destination / 'shadps4').chmod(0o755)
    else:
        env = dict(os.environ, CCACHE_DIR=str(ROOT / '.deps/ccache'), CCACHE_BASEDIR=str(ROOT),
                   CCACHE_COMPILERCHECK='content')
        # Do not inherit relaxed hashing policies from a developer environment.
        env.pop('CCACHE_SLOPPINESS', None)
        output('attempted_build', 'true')
        run(['ccache', '--max-size', '2G'], RESULTS / 'ccache-config.log', env=env)
        run(['ccache', '--zero-stats'], RESULTS / 'ccache-reset.log', env=env)
        try:
            with phase('emulator-build'):
                run([sys.executable, ROOT / 'tools/build-shad-linux.py', '--jobs', '2', '--ccache'],
                    RESULTS / 'emulator-build-driver.log', timeout=3600, env=env)
        finally:
            run(['ccache', '--show-stats'], RESULTS / 'ccache-stats.log', env=env)
        if source_identity() != record['inputs']['source']:
            raise ValueError('Fork sources changed during cached build')
        BUNDLE.mkdir(parents=True, exist_ok=True)
        for name in ('shadps4', 'build-manifest.json', 'source.patch'):
            shutil.copyfile(destination / name, BUNDLE / name)
        write_json(BUNDLE / 'cache-proof.json', {'key': record['key'], 'inputs': record['inputs'],
                   'manifest_sha256': sha(BUNDLE / 'build-manifest.json'), 'producer_source_sha': revision()})
        validate_bundle(BUNDLE, record)
        output('built', 'true')
    write_json(RESULTS / 'emulator-cache.json', {'key': record['key'], 'reused': reused,
               'requested_by_source_sha': revision(), 'binary_sha256': sha(destination / 'shadps4'),
               'duration_seconds': round(time.monotonic() - start, 3),
               'scope': 'Emulator build reuse only; diagnostic tests always execute'})
    output('reused', str(reused).lower())


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('key', 'build'))
    args = parser.parse_args()
    key() if args.action == 'key' else build()
