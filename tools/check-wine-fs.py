#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Sanitized native Linux check of path algorithms, separate from Orbis ABI tests."""
import hashlib,json,os,pathlib,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
out=ROOT/'reports/increment14/host-fs';out.mkdir(parents=True,exist_ok=True)
binary=ROOT/'build/host/wine-fs-increment14'
sources=[ROOT/'tests/wine_fs.c',ROOT/'platform/ps4/pw_wine_fs.c',ROOT/'platform/ps4/pw_wine_fs.h']
hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
command=['clang','-D_GNU_SOURCE','-std=gnu11','-g','-O1','-fsanitize=address,undefined',
         '-fno-omit-frame-pointer','-fno-pie','-no-pie','-pthread','-I'+str(ROOT/'platform/ps4'),
         str(sources[0]),str(sources[1]),'-o',str(binary)]
with (out/'build.log').open('w') as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
with (out/'run.log').open('w') as log:
    result=subprocess.run([str(binary)],stdout=log,stderr=subprocess.STDOUT,
                          env=dict(os.environ,ASAN_OPTIONS='detect_leaks=1:abort_on_error=1'),timeout=30)
if hashes!={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}:
    raise SystemExit('Source changed during check')
report={'status':'passed' if result.returncode==0 else 'failed','exit_code':result.returncode,
        'scope':'Linux path and ownership algorithms; not Orbis directory ABI',
        'command':command,'source_hashes':hashes,'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),
        'compiler':subprocess.check_output(['clang','--version'],text=True).splitlines()[0],
        'sanitizers':['ASan','UBSan','leak detection'],'pie':False,'hardware_status':'pending'}
(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if result.returncode:raise SystemExit(1)
