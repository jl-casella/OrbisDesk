#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Focused Win32 registry-policy reference in a disposable Wine prefix, not PS4 acceptance."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
def main():
    work=Path(tempfile.mkdtemp(prefix='orbisdesk-execution-modes-',dir='/var/tmp'))
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    report=ROOT/'reports/execution-modes'/stamp;report.mkdir(parents=True)
    fixture=work/'execution-modes.exe'
    command=['x86_64-w64-mingw32-gcc','-O2','-Wall','-Wextra','-Werror','-I',str(ROOT/'platform/ps4'),
             str(ROOT/'tests/execution_modes.c'),'-o',str(fixture),'-ladvapi32']
    subprocess.run(command,check=True)
    wine=ROOT/'.deps/wine/runtime/build'
    env=dict(os.environ,WINEPREFIX=str(work/'prefix'),WINEDEBUG='-all',WINEDLLOVERRIDES='winemenubuilder.exe=d')
    try:
        result=subprocess.run([wine/'loader/wine',fixture],env=env,cwd=work,capture_output=True,text=True,timeout=130)
    finally:
        subprocess.run([wine/'server/wineserver','-k'],env=env,capture_output=True,timeout=10)
    (report/'stdout.jsonl').write_text(result.stdout);(report/'stderr.log').write_text(result.stderr)
    cases=[json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
    data={'classification':'host_wine_registry_policy','ps4_validated':False,'work':str(work),'exit_code':result.returncode,
          'cases':cases,'passed':result.returncode==0 and len(cases)==14 and all(c['passed'] for c in cases),
          'sources':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                     [ROOT/'tests/execution_modes.c',ROOT/'platform/ps4/pw_execution_mode.h',ROOT/'platform/ps4/pw_execution_policy.h']}}
    (report/'report.json').write_text(json.dumps(data,indent=2)+'\n')
    print(json.dumps({'passed':data['passed'],'cases':len(cases),'exit_code':result.returncode,'report':str(report)}))
    return 0 if data['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
