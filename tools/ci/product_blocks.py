#!/usr/bin/env python3
"""The recipes of the two dependency blocks (graphics, host Wine) and the inputs they read.

build-product.py and build-block.py (the prebuilt-blocks workflow) both run these functions, so a
block published as a release asset is made exactly as the product build would make it. This file is
a key input of both blocks (product_cache.make_keys); build-product.py is not, so editing the later
PS4 steps does not invalidate the blocks.
"""
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile
from common import ROOT, RESULTS, phase, run, sha, write_json
from product_cache import normalize_wine_source, product_download as download
from runner_disk import record as record_disk, GIB

LLVM_RUNTIME_SUBTREES = (
    'runtimes', 'libcxx', 'libcxxabi', 'libunwind', 'libc', 'cmake',
    'third-party', 'llvm/cmake', 'llvm/utils/lit', 'llvm/utils/llvm-lit',
)
# Directories a clean product or block build must start without.
CLEAN_DIRECTORIES = (ROOT / '.deps/sdk', ROOT / '.deps/wine', ROOT / 'out', Path.home() / 'vk-h0')


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


def require_clean_workspace():
    # Only verified snapshots may populate fresh destinations after this guard.
    for directory in CLEAN_DIRECTORIES:
        if directory.exists():
            raise ValueError('Clean product build requires an absent directory: ' + str(directory))
    if subprocess.check_output(['git', '-C', str(ROOT), 'status', '--porcelain']).strip():
        raise ValueError('Product source checkout is dirty')
    RESULTS.mkdir(parents=True, exist_ok=True)


def prepare_sources():
    """Pinned sources, SDK, archives and assets; the LLVM runtime sources under ~/vk-h0/src."""
    deps = json.loads((ROOT / 'dependencies.lock.json').read_text())
    # The Steam client lives inside the title since alpha-1 (tools/build-steam-hosted.py), so Playden's
    # sources and curl patch are inputs; MangoJuice stays a reference only.
    names = [n for n in deps['repositories'] if n != 'mangojuice']
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


def graphics_environment():
    """The Mesa venv and pinned Python tools; recreated every run, never restored from a block."""
    home = Path.home() / 'vk-h0'
    step('graphics-environment', ['bash', ROOT / 'tools/vk-h0/fetch.sh'])
    # Pin the graphics Python tools after the historical fetch script creates the venv.
    step('graphics-python', [home / 'mesa-venv/bin/pip', 'install', 'meson==1.12.1', 'Mako==1.4.3',
                            'MarkupSafe==3.0.4', 'PyYAML==6.0.3', 'packaging==26.3'])
    return dict(os.environ, PATH=str(ROOT / '.deps/linux-tools/cmake/data/bin') + ':' + os.environ['PATH'])


def build_graphics(env):
    for name in ('fetch-llvm-mingw', 'setup-libcxx', 'build-glslang'):
        step(name, ['bash', ROOT / 'tools/vk-h0' / (name + '.sh')], env)
    step('mesa-wine', ['bash', ROOT / 'tools/vk-h0/build-mesa.sh'], dict(env, VARIANT='wine'))
    for name in ('build-vulkan-loader', 'build-vulkan-loader-i386', 'build-mesa-zink',
                 'build-mesa-zink-i386', 'build-mangohud', 'build-mangohud-i386', 'build-vkcube'):
        step(name, ['bash', ROOT / 'tools/vk-h0' / (name + '.sh')], env)


def wine_prerequisites():
    """The PE32 console fixture the prefix embeds, then the pinned Wine source timestamps."""
    python('build', '--fixtures-only')
    normalize_wine_source()


def build_wine():
    """Complete host Wine tree, its PE/Unix closures and the sealed prefix produced from it."""
    python('build-wine', '--jobs', '2', '--release-build')
    python('build-host-wine-closure', '--jobs', '2', '--product-staging')
    python('build-host-wine-unix')
    python('build-host-wine-tree', '--jobs', str(max(2, os.cpu_count() or 2)))
    python('prepare-host-prefix')
    producers = list((ROOT / 'reports/increment15/prefix-producer').glob('*/report.json'))
    if len(producers) != 1:
        raise ValueError('Expected one new native prefix producer')
    python('package-wine-prefix', producers[0].parent, ROOT / 'reports/increment15/prefix-package')
