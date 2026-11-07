#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Preserve the native Wine diagnostic objects and toolchain adaptation."""
import argparse
import hashlib
import json
import pathlib
import shutil

ROOT=pathlib.Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('snapshot',type=pathlib.Path)
args=parser.parse_args()
snapshot=args.snapshot.resolve()
if not snapshot.is_relative_to(ROOT/'reports') or not (snapshot/'report.json').is_file():
    raise SystemExit('Expected a probe snapshot within workspace reports')
build=json.loads((snapshot/'build.json').read_text())
for relative,digest in build['local_inputs'].items():
    if hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()!=digest:
        raise SystemExit('Build input changed: '+relative)
guest=json.loads((snapshot/'report.json').read_text())
if hashlib.sha256((ROOT/'out/eboot.bin').read_bytes()).hexdigest()!=guest['elf']['sha256']:
    raise SystemExit('ELF no longer matches the snapshot')
destination=snapshot/'wine-platform';destination.mkdir(exist_ok=False)
files=[ROOT/'tools/archive-wine-platform.py',ROOT/'tools/run-probes.ps1',
       ROOT/'out/probe.elf',ROOT/'out/probe.oelf',ROOT/'out/eboot.bin',
       ROOT/'build/increment9-build.log',ROOT/'build/increment9-remaining.log',
       ROOT/'build/wine-source-status.txt',ROOT/'build/lstat.o',ROOT/'build/fstatat.o',
       ROOT/'build/lstat-disassembly.txt',ROOT/'build/fstatat-disassembly.txt',
       ROOT/'build/shadPS4-win/build-manifest.json',ROOT/'fork.lock.json']
files.extend(p for p in (ROOT/'build/wine-ps4').rglob('*') if p.is_file())
sdk=ROOT/'.deps/sdk/OpenOrbis/PS4Toolchain'
files.extend(sdk/p for p in ('LICENSE','include/bits/stat.h','include/bits/alltypes.h',
                            'include/bits/mman.h','include/orbis/_types/kernel.h'))
identities={}
for path in files:
    relative=path.relative_to(ROOT);target=destination/relative
    target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
    identities[str(relative)]={'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'bytes':target.stat().st_size}
report={'schema_version':1,'files':identities,'wine_commit':build['wine_unix']['wine_commit'],
        'source_pristine':not (ROOT/'build/wine-source-status.txt').read_text().strip(),
        'Wine_booted':False,'hardware_status':'pending',
        'runtime_scope':'Reduced diagnostic functions from patched Wine units, not a linked ntdll.so',
        'pe_distribution_reference':'reports/increment8-fork-final/wine/out/wine/wine-runtime-manifest.json'}
(destination/'evidence.json').write_text(json.dumps(report,indent=2)+'\n')
print('Native Wine evidence:',destination/'evidence.json')
