#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Build real pinned Wine PE modules; no claim of a PS4 Unix runtime.

Run in WSL. Source is private under .deps/wine; upstream stays unchanged.
Logs survive failures. Uses the pinned prospero-win builder, normalizing only
its shell line endings and locating its own validator in the original tree.
"""
import argparse
import hashlib
import json
import os
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
HOST_CONFIGURE_ARGS = ('--enable-archs=i386,x86_64 --disable-tests --without-x '
                       '--without-freetype --enable-wineusb-sys')


# Keep the checkout and $HOME out of __FILE__ strings and debug info. Configure records
# these in the Makefile, so the replayed PE recipes (build-*-hw.py) inherit them too.
PREFIX_MAP = ('-ffile-prefix-map=%s=. -ffile-prefix-map=%s=vk-h0'
              % (ROOT, pathlib.Path.home() / 'vk-h0'))
FLAG_KEYS = ('CFLAGS', 'CXXFLAGS', 'CROSSCFLAGS', 'i386_CFLAGS',
             'i386_CXXFLAGS', 'x86_64_CFLAGS', 'x86_64_CXXFLAGS')


def build_environment(release_build=False):
    env = dict(os.environ, LC_ALL='C', TZ='UTC')
    # Wine's PE flags use CROSSCFLAGS, independently of the native CFLAGS.
    # '-g -O2' is configure's own default when these are unset.
    for key in FLAG_KEYS:
        env[key] = ('-O2 -g0' if release_build else os.environ.get(key, '-g -O2')) + ' ' + PREFIX_MAP
    return env


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--jobs', type=int, default=8)
    parser.add_argument('--release-build', action='store_true',
                        help='Omit host/PE debug symbols to limit hosted runner disk use')
    args = parser.parse_args()
    lock = json.loads((ROOT / 'sources.lock.json').read_text())['sources']['wine']
    source = ROOT / '.deps/wine/source'
    head = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if head != lock['commit']:
        raise SystemExit('Wine source revision mismatch')
    dirty = subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain'], text=True).strip()
    if dirty:
        raise SystemExit('Wine source must be clean')
    upstream = ROOT / 'upstream/prospero-win'
    builder = upstream / 'tools/build_wine_runtime.sh'
    script = builder.read_text().replace('root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)',
                                        'root=' + __import__('shlex').quote(str(upstream)))
    script = script.replace('CONFIGURE_ARGS="--enable-archs=i386,x86_64 --disable-tests"',
                            'CONFIGURE_ARGS="' + HOST_CONFIGURE_ARGS + '"')
    # Prefix initialization needs wineusb.sys PE resources even when configure
    # cannot detect libusb and would otherwise disable the whole module. The
    # host Unix closure separately omits the unused USB backend, not this PE.
    # Incremental bring-up: upstream -B also reruns configure and makedep for
    # every DLL. Reproducibility rebuilds are a separate, explicit validation.
    script = script.replace('make -B -j', 'make -j')
    runtime = ROOT / '.deps/wine/runtime'
    runtime.mkdir(parents=True, exist_ok=True)
    # The driver configures only without a Makefile. A tree configured before the
    # prefix map (or for another checkout/$HOME) is reconfigured; objects compiled
    # earlier keep their old paths until rebuilt.
    makefile = runtime / 'build/Makefile'
    if makefile.is_file() and PREFIX_MAP not in makefile.read_text(errors='replace'):
        makefile.unlink()
    driver = runtime / 'driver.sh'
    driver.write_text(script)
    command = ['sh', str(driver), '--build-root', str(runtime), '--source', str(source),
               '--out', str(ROOT / 'out/wine'), '--jobs', str(args.jobs)]
    with (runtime / 'driver.log').open('w') as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                                env=build_environment(args.release_build))
    report = {'schema_version': 1, 'wine_commit': head, 'status': 'built' if not result.returncode else 'blocked',
              'environment': 'WSL cross-built PE modules; PS4 execution unvalidated',
              'builder_sha256': hashlib.sha256(builder.read_bytes()).hexdigest(),
              'driver_sha256': hashlib.sha256(driver.read_bytes()).hexdigest(),
              'exit_code': result.returncode, 'logs': '.deps/wine/runtime/',
              'hardware_status': 'pending', 'debug_symbols': not args.release_build}
    (ROOT / 'out/wine-build.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report), flush=True)
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
