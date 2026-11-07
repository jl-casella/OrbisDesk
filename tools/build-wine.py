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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--jobs', type=int, default=8)
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
                            'CONFIGURE_ARGS="--enable-archs=i386,x86_64 --disable-tests --without-x --without-freetype"')
    # Incremental bring-up: upstream -B also reruns configure and makedep for
    # every DLL. Reproducibility rebuilds are a separate, explicit validation.
    script = script.replace('make -B -j', 'make -j')
    runtime = ROOT / '.deps/wine/runtime'
    runtime.mkdir(parents=True, exist_ok=True)
    driver = runtime / 'driver.sh'
    driver.write_text(script)
    command = ['sh', str(driver), '--build-root', str(runtime), '--source', str(source),
               '--out', str(ROOT / 'out/wine'), '--jobs', str(args.jobs)]
    with (runtime / 'driver.log').open('w') as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                                env=dict(os.environ, LC_ALL='C', TZ='UTC'))
    report = {'schema_version': 1, 'wine_commit': head, 'status': 'built' if not result.returncode else 'blocked',
              'environment': 'WSL cross-built PE modules; PS4 execution unvalidated',
              'builder_sha256': hashlib.sha256(builder.read_bytes()).hexdigest(),
              'driver_sha256': hashlib.sha256(driver.read_bytes()).hexdigest(),
              'exit_code': result.returncode, 'logs': '.deps/wine/runtime/',
              'hardware_status': 'pending'}
    (ROOT / 'out/wine-build.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report), flush=True)
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
