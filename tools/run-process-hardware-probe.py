#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Bounded emulator smoke run of a packaged process diagnostic, not hardware acceptance."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build',choices=['P001','P002','P003','P004','P005','P007','P009','P012','P013'],required=True)
    parser.add_argument('--timeout',type=int,default=20)
    args=parser.parse_args()
    if os.name!='posix':parser.error('Run with WSL/Linux Python')
    if not 5<=args.timeout<=60:parser.error('timeout must be 5..60')
    build=args.build;stem='process-hardware-'+build.lower()
    manifest=json.loads((ROOT/'out'/stem/'manifest.json').read_text())
    emulator=json.loads((ROOT/'build/shadPS4-linux/build-manifest.json').read_text())
    game=ROOT/'build'/stem/'app/eboot.bin'
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    if sha(game)!=manifest['eboot_sha256'] or sha(ROOT/'build/shadPS4-linux/shadps4')!=emulator['executable_sha256']:
        raise RuntimeError('Executable differs from its manifest')
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    report=ROOT/'reports'/stem/stamp;report.mkdir(parents=True)
    work=Path(tempfile.mkdtemp(prefix='orbisdesk-'+build.lower()+'-',dir='/var/tmp'));data=work/'data';data.mkdir()
    command=['python3',str(ROOT/'tools/run-linux-shad.py'),'--fork','--config-clean',
             '--fullscreen','false','--mount',str(data),'/data','-g',str(game)]
    def setup():
        import resource
        resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    start=time.monotonic();completed=False;logs=[]
    with (report/'stdout.log').open('w') as out,(report/'stderr.log').open('w') as err:
        proc=subprocess.Popen(command,cwd=work,stdout=out,stderr=err,start_new_session=True,preexec_fn=setup)
        try:
            while time.monotonic()-start<args.timeout:
                logs=list((data/'orbisdesk'/('process-'+build.lower())).glob('run-*/report.jsonl'))
                if logs:
                    records=[json.loads(line) for line in logs[0].read_text().splitlines() if line.strip()]
                    if any(r['event']==('scope' if build=='P001' else 'panel_ready') for r in records):
                        completed=True;break
                if proc.poll() is not None:break
                time.sleep(.2)
        finally:
            if proc.poll() is None:os.killpg(proc.pid,signal.SIGKILL)
            exit_code=proc.wait()
    records=[]
    if logs:
        raw=logs[0].read_bytes();(report/'report.jsonl').write_bytes(raw)
        records=[json.loads(line) for line in raw.splitlines() if line.strip()]
    result={'build':build,'classification':'fork_emulator','probe_completed':completed,'records':records,
            'exit_code':exit_code,'stopped_after_completion':completed,'working_directory':str(work),
            'duration_seconds':round(time.monotonic()-start,3),'command':command,'product_manifest':manifest,
            'emulator_manifest':emulator,'hardware_status':'pending','native_process_spawn_verified':False}
    (report/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('build','probe_completed','duration_seconds','exit_code')}))
    print(report/'report.json')
    return 0 if completed else 1


if __name__=='__main__':raise SystemExit(main())
