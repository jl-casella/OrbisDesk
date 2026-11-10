#!/usr/bin/env python3
"""Experimental clean product recipe. Stop at the first real build failure."""
import argparse
import json
import subprocess
import sys
from common import ROOT, RESULTS, revision, sha, write_json
from product_cache import ProductCache
# llvm_runtime_member stays importable from here for its existing tests
from product_blocks import (build_graphics, build_wine, graphics_environment, llvm_runtime_member,  # noqa: F401
                            prepare_sources, python, require_clean_workspace, step, wine_prerequisites)


def build(version, cache_mode='reuse'):
    require_clean_workspace()
    cache = ProductCache(cache_mode)
    prepare_sources()
    # The dependency blocks come from actions/cache, else from the prebuilt release assets of
    # prebuilt-blocks.lock.json when their key equals the computed one, else they are built here.
    graphics_reused = cache.use('graphics')
    # Recreate the venv rather than restoring host interpreter symlinks.
    env = graphics_environment()
    if not graphics_reused:
        build_graphics(env)
        cache.save('graphics')
    wine_prerequisites()
    # The Wine block includes the sealed prefix made from the complete host tree (W303).
    if not cache.use('wine'):
        build_wine()
        cache.save('wine')
    python('probe-wine-unix', '--configure-only')
    python('build-wine-ps4', '--boot', '--all-unix')
    python('build-wine-ps4', '--boot', '--server')
    # These entries are ordered by their input manifests, not alphabetically.
    for name in ('stage-wine-pe64', 'stage-wine-gui', 'stage-wine-programs', 'stage-wine-i386',
                 'stage-wine-extras', 'build-bcrypt-x64', 'build-dmsynth-i386', 'stage-mshtml-hw',
                 'stage-dshow-i386', 'stage-wine-gecko', 'stage-vlc',
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
        python(name)
    step('product-assets', [sys.executable, ROOT / 'tools/ci/product-fixtures.py'])
    # The Steam client inside the title: its TLS/HTTP libraries, then the hosted object, checked against
    # the bootstrap ELF link-wine-boot made (pinned downloads: product-assets.lock.json, steam-*)
    python('build-steam-deps', '--target', 'ps4')
    python('build-steam-hosted')
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
