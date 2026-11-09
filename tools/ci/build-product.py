#!/usr/bin/env python3
"""Experimental clean product recipe. Stop at the first real build failure."""
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile
from common import ROOT, RESULTS, phase, run, revision, sha, write_json
from product_cache import ProductCache, normalize_wine_source, product_download as download
from runner_disk import record as record_disk, GIB


LLVM_RUNTIME_SUBTREES = (
    'runtimes', 'libcxx', 'libcxxabi', 'libunwind', 'libc', 'cmake',
    'third-party', 'llvm/cmake', 'llvm/utils/lit', 'llvm/utils/llvm-lit',
)


def llvm_runtime_member(name):
    """Select complete runtime dependencies by path components, not substrings."""
    relative = PurePosixPath(name).parts[1:]
    return any(relative[:len(parts)] == parts
               for parts in (PurePosixPath(tree).parts for tree in LLVM_RUNTIME_SUBTREES))


def step(name, command, env=None):
    record_disk('before-' + name, minimum_gib=3)
    print('Starting product-' + name, flush=True)
    with phase('product-' + name):
        log = RESULTS / ('product-' + name + '.log')
        try:
            run(command, log, timeout=14400, env=env, minimum_free_bytes=2 * GIB)
        except Exception:
            if log.exists():
                print('\n'.join(log.read_text(errors='replace').splitlines()[-60:]), flush=True)
            raise
        finally:
            record_disk('after-' + name)


def python(name, *args):
    step(name, [sys.executable, ROOT / 'tools' / (name + '.py'), *args])


def build(version, cache_mode='reuse'):
    # Only verified snapshots may populate fresh destinations after this guard.
    for directory in (ROOT / '.deps/sdk', ROOT / '.deps/wine', ROOT / 'out', Path.home() / 'vk-h0'):
        if directory.exists():
            raise ValueError('Clean product build requires an absent directory: ' + str(directory))
    if subprocess.check_output(['git', '-C', str(ROOT), 'status', '--porcelain']).strip():
        raise ValueError('Product source checkout is dirty')
    RESULTS.mkdir(parents=True, exist_ok=True)
    cache = ProductCache(cache_mode)
    deps = json.loads((ROOT / 'dependencies.lock.json').read_text())
    # Steam is a separate product and not a dependency of this release recipe.
    names = [n for n in deps['repositories'] if n not in ('mangojuice', 'playden-ps5')]
    command = [sys.executable, ROOT / 'tools/restore-dependencies.py', '--fetch']
    for name in names:
        command += ['--only', name]
    command += ['--only', 'shadps4-fork']
    step('sources', command)
    with phase('product-downloads'):
        archive = download(json.loads((ROOT / 'artifacts.lock.json').read_text())['openorbis'], 'openorbis.tar.gz')
        sdk = ROOT / '.deps/sdk'
        sdk.mkdir(parents=True)
        with tarfile.open(archive) as source:
            source.extractall(sdk, filter='data')
        for spec in deps['archives'].values():
            destination = ROOT / spec['path']
            archive = download(spec, destination.name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(archive, destination)
        assets = json.loads((ROOT / 'product-assets.lock.json').read_text())['downloads']
        for name, spec in assets.items():
            archive = download(spec, name + '-' + Path(spec['path']).name)
            destination = Path(spec['path']).expanduser() if spec['path'].startswith('~/') else ROOT / spec['path']
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(archive, destination)
        llvm = ROOT / assets['llvm-source']['path']
        home = Path.home() / 'vk-h0'
        (home / 'src').mkdir(parents=True, exist_ok=True)
        # All members are verified by tarfile's data filter; no workstation tree is copied.
        with tarfile.open(llvm) as source:
            members = [m for m in source.getmembers() if llvm_runtime_member(m.name)]
            source.extractall(home / 'src', members=members, filter='data')
        write_json(RESULTS / 'product-downloads.json', {
            'assets': assets, 'locks': {p.name: sha(p) for p in ROOT.glob('*.lock.json')}})
    graphics_reused = cache.use('graphics')
    # Recreate the venv rather than restoring host interpreter symlinks.
    step('graphics-environment', ['bash', ROOT / 'tools/vk-h0/fetch.sh'])
    # Pin the graphics Python tools after the historical fetch script creates the venv.
    step('graphics-python', [home / 'mesa-venv/bin/pip', 'install', 'meson==1.12.1', 'Mako==1.4.3',
                            'MarkupSafe==3.0.4', 'PyYAML==6.0.3', 'packaging==26.3'])
    env = dict(os.environ, PATH=str(ROOT / '.deps/linux-tools/cmake/data/bin') + ':' + os.environ['PATH'])
    if not graphics_reused:
        for name in ('fetch-llvm-mingw', 'setup-libcxx', 'build-glslang'):
            step(name, ['bash', ROOT / 'tools/vk-h0' / (name + '.sh')], env)
        step('mesa-wine', ['bash', ROOT / 'tools/vk-h0/build-mesa.sh'], dict(env, VARIANT='wine'))
        for name in ('build-vulkan-loader', 'build-vulkan-loader-i386', 'build-mesa-zink',
                     'build-mesa-zink-i386', 'build-mangohud', 'build-mangohud-i386', 'build-vkcube'):
            step(name, ['bash', ROOT / 'tools/vk-h0' / (name + '.sh')], env)
        cache.save('graphics')
    python('build', '--fixtures-only')
    normalize_wine_source()
    if not cache.use('wine'):
        python('build-wine', '--jobs', '2', '--release-build')
        python('build-host-wine-closure', '--jobs', '2', '--product-staging')
        python('build-host-wine-unix')
        cache.save('wine')
    python('prepare-host-prefix')
    producers = list((ROOT / 'reports/increment15/prefix-producer').glob('*/report.json'))
    if len(producers) != 1:
        raise ValueError('Expected one new native prefix producer')
    python('package-wine-prefix', producers[0].parent, ROOT / 'reports/increment15/prefix-package')
    python('probe-wine-unix', '--configure-only')
    python('build-wine-ps4', '--boot', '--all-unix')
    python('build-wine-ps4', '--boot', '--server')
    # These entries are ordered by their input manifests, not alphabetically.
    for name in ('stage-wine-pe64', 'stage-wine-gui', 'stage-wine-programs', 'stage-wine-i386',
                 'stage-wine-extras', 'build-bcrypt-x64', 'stage-mshtml-hw',
                 'build-dmsynth-i386', 'stage-dshow-i386', 'stage-wine-gecko', 'stage-vlc',
                 'stage-dxvk', 'build-wowprospero-ps4', 'build-wow64native-ps4', 'build-freetype-ps4',
                 'build-win32u-ps4', 'build-winevulkan-batch', 'build-winevulkan-ps4',
                 'build-unixlibs-ps4', 'build-audio-ps4', 'build-xinput-hw', 'build-hidstack-hw',
                 'build-dinput-hw', 'build-joycpl-hw', 'build-env-ps4', 'build-signal-ps4',
                 'build-telemetry-ps4', 'link-wine-boot', 'build-wine-delete-server',
                 'build-wine-directory-ps4', 'build-wow64-world-ps4', 'build-ddraw-hw',
                 'build-wined3d-hw', 'build-wmvcore-hw', 'build-msstyles-hw',
                 'build-nsi-hw', 'build-dxgi-hw', 'build-winmm-hw',
                 'build-taskmgr-hw', 'build-winecfg-hw', 'build-explorer-hw', 'build-guest-hw',
                 'build-wfm', 'build-dos-runtime', 'build-games', 'make-icons', 'make-start-menu', 'make-app-icon'):
        python(name, *(['--pinball'] if name == 'build-games' else []))
    step('product-assets', [sys.executable, ROOT / 'tools/ci/product-fixtures.py'])
    # W292: the extra desktop wallpapers build-wine-hardware stages (generated, no download)
    python('make-wallpaper-set')
    python('build-wine-hardware', '--app-version', version)
    # the builder's build ID (W288, W302, ...) names its output folder; exactly one in a clean workspace
    manifests = list((ROOT / 'out').glob('wine-hardware-w*/manifest.json'))
    if len(manifests) != 1:
        raise ValueError('Expected one product manifest, found: ' + ', '.join(str(m) for m in manifests))
    manifest = manifests[0]
    data = json.loads(manifest.read_text())
    step('web-closure', [sys.executable, '-I', ROOT / 'tools/check-web-closure.py', ROOT / data['runtime_root']])
    write_json(RESULTS / 'product-build.json', {
        'source_sha': revision(), 'manifest': str(manifest.relative_to(ROOT)), 'manifest_sha256': sha(manifest),
        'build_scope': 'fresh hosted workspace with verified dependency snapshots; packaging and import closure only',
        'dependency_cache': cache.status,
        'Wine_booted': False, 'hardware_status': 'pending', 'status': 'built'})
    write_json(RESULTS / 'product-environment.json', {
        'source_sha': revision(),
        'packages': subprocess.check_output(['dpkg-query', '-W'], text=True).splitlines(),
        'dotnet': subprocess.check_output(['dotnet', '--info'], text=True),
        'disk': subprocess.check_output(['df', '-h', str(ROOT)], text=True)})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', required=True)
    parser.add_argument('--cache-mode', choices=('cold', 'reuse'), default='reuse')
    args = parser.parse_args()
    import re
    if not re.fullmatch(r'[0-9]{2}\.[0-9]{2}', args.version):
        parser.error('Version must be NN.NN')
    try:
        build(args.version, args.cache_mode)
    except Exception as exc:
        write_json(RESULTS / 'product-failure.json', {'source_sha': revision(), 'error': str(exc), 'status': 'failed'})
        raise


if __name__ == '__main__':
    main()
