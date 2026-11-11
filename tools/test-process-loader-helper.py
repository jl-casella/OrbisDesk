#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Exercise the actual freestanding helper on Linux; never PS4 acceptance."""
import ctypes
import hashlib
import json
import mmap
import os
from pathlib import Path
import secrets
import struct
import subprocess
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
def main():
    work=Path(tempfile.mkdtemp(prefix='orbisdesk-p005-reference-',dir='/var/tmp'))
    request_path=work/'request.bin'
    binary=work/'helper'
    command=['clang','-O2','-Wall','-Wextra','-Werror','-ffreestanding','-fno-builtin',
             '-fno-stack-protector','-fPIC','-mno-red-zone','-nostdlib','-static',
             '-DP005_HOST_REFERENCE=1','-DP005_REQUEST_PATH="'+str(request_path)+'"',
             '-Wl,-e,_start',str(ROOT/'native/process_loader_helper.c'),'-o',str(binary)]
    subprocess.run(command,check=True)
    cases=[]
    for stale in (False,True):
        run=work/('stale' if stale else 'valid');run.mkdir()
        token=struct.unpack('<QQ',secrets.token_bytes(16))
        with (run/'state.bin').open('w+b') as f:
            f.truncate(16384)
            state=mmap.mmap(f.fileno(),16384)
        state[:64]=struct.pack('<QQQ10I',0x50303035434f4558,*token,os.getpid(),0,0,0,0,0,0,0,0,0)
        request_path.write_bytes(struct.pack('<QQQII160s',0x50303035434f4558,
            token[0]^(1 if stale else 0),token[1],os.getpid(),0,str(run).encode()))
        with (run/'stdout.jsonl').open('w') as out:
            proc=subprocess.Popen([binary],stdout=out)
            start=time.monotonic();ticks=0
            try:
                while proc.poll() is None and time.monotonic()-start<6:
                    ticks+=1;struct.pack_into('<I',state,28,ticks)
                    helper_pid=struct.unpack_from('<I',state,32)[0]
                    if helper_pid==proc.pid:struct.pack_into('<I',state,44,1)
                    time.sleep(.02)
                exit_code=proc.wait(timeout=1)
            finally:
                if proc.poll() is None:proc.kill();proc.wait()
        values=struct.unpack('<QQQ10I',state[:64]);state.close()
        passed=exit_code==83 if stale else exit_code==42 and values[5]==proc.pid and values[8:11]==(1,42,1) and values[7]>=10
        cases.append({'case':'stale_token' if stale else 'coexistence','passed':passed,
                      'native_exit_code':exit_code,'helper_pid':proc.pid,'state':values,
                      'duration_seconds':round(time.monotonic()-start,3)})
    result={'classification':'linux_host_reference','ps4_validated':False,'work_directory':str(work),
            'helper_source_sha256':hashlib.sha256((ROOT/'native/process_loader_helper.c').read_bytes()).hexdigest(),
            'command':command,'cases':cases,'passed':all(c['passed'] for c in cases)}
    report=ROOT/'build/process-loader-helper-reference';report.mkdir(parents=True,exist_ok=True)
    (report/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    return 0 if result['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
