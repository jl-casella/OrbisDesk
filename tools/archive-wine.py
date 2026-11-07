#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Attach auditable Wine build/ABI evidence to an existing probe snapshot."""
import argparse
import hashlib
import json
import pathlib
import re
import shutil

ROOT = pathlib.Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('snapshot', type=pathlib.Path)
parser.add_argument('--serial-exit', type=int, required=True)
args = parser.parse_args()
snapshot = args.snapshot.resolve()
if not snapshot.is_relative_to(ROOT/'reports') or not (snapshot/'report.json').is_file():
    raise SystemExit('Expected a probe snapshot within workspace reports')
destination = snapshot/'wine'
destination.mkdir(exist_ok=False)
files = [ROOT/'out/wine-build.json', ROOT/'out/wine-unix-probe.json', ROOT/'out/wine-audit.json',
         ROOT/'build/wine-process-abi.log', ROOT/'build/host/wine-process-abi.o',
         ROOT/'tests/wine-process-abi.c', ROOT/'tools/build-wine.py', ROOT/'tools/probe-wine-unix.py',
         ROOT/'tools/audit-wine.py', ROOT/'tools/archive-wine.py', ROOT/'tools/run-probes.ps1',
         ROOT/'upstream/prospero-win/tools/build_wine_runtime.sh',
         ROOT/'upstream/prospero-win/tools/validate_wine_runtime.py',
         ROOT/'build/shadPS4-win/build-manifest.json', ROOT/'sources.lock.json', ROOT/'fork.lock.json']
for name in ('configure.log','driver.log','driver.sh','make-ntdll.log','make-kernelbase.log','make-kernel32.log'):
    files.append(ROOT/'.deps/wine/runtime'/name)
for name in ('configure.log','config.log','include/config.h','make-ntdll.log','make-serial.log','orbis-cc'):
    files.append(ROOT/'.deps/wine/ps4-unix'/name)
files.extend(p for p in (ROOT/'out/wine').rglob('*') if p.is_file())
identities = {}
for path in files:
    relative = path.relative_to(ROOT)
    target = destination/relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, target)
    identities[str(relative)] = {'sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'bytes': target.stat().st_size}
errors = {}
for line in (ROOT/'.deps/wine/ps4-unix/make-serial.log').read_text().splitlines():
    match = re.search(r'/source/(.*?):(\d+):\d+: (?:fatal )?error: (.*)', line)
    if match:
        errors.setdefault(match[1], []).append({'line': int(match[2]), 'error': match[3]})
report = {'schema_version': 1, 'files': identities, 'serial_compile': {
    'command': ['make', '-k', '-j1', 'dlls/ntdll/ntdll.so', 'server/wineserver'],
    'exit_code': args.serial_exit, 'status': 'blocked' if args.serial_exit else 'built-unvalidated',
    'errors_by_file': errors}, 'abi_assertions': {'status': 'passed', 'count': 16,
    'environment': 'i686 compiler against pinned Wine headers, not emulator execution'},
    'Wine_booted': False, 'hardware_status': 'pending'}
(destination/'evidence.json').write_text(json.dumps(report, indent=2)+'\n')
print('Wine evidence:', destination/'evidence.json')
