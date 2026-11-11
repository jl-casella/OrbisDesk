#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Archive process diagnostic evidence via FTP without overwriting previous runs."""
import argparse
import datetime
import ftplib
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build',choices=['P001','P002','P003','P004','P005','P007','P009','P012','P013'],required=True)
    parser.add_argument('--host',required=True)
    parser.add_argument('--firmware',required=True,help='Current operator-reported version, not automatically detected')
    args=parser.parse_args();stem='process-hardware-'+args.build.lower()
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    dest=ROOT/'reports'/stem/'physical'/stamp;dest.mkdir(parents=True)
    result={'build':args.build,'classification':'physical_ps4','host':args.host,
            'reported_firmware':args.firmware,'firmware_source':'operator_cli','runs':[]}
    ftp=ftplib.FTP();ftp.connect(args.host,2121,timeout=20);ftp.login()
    base='/data/orbisdesk/process-'+args.build.lower()
    try:
        ftp.cwd(base)
        runs=sorted({Path(n.rstrip('/')).name for n in ftp.nlst() if re.fullmatch(r'run-\d{4}',Path(n.rstrip('/')).name)})
        for run in runs:
            ftp.cwd(base+'/'+run);local=dest/run;local.mkdir();files={}
            for entry in ftp.nlst():
                name=Path(entry).name
                if name not in ('report.jsonl','helper.jsonl','child.jsonl','state.bin','loader-stream.log','loader-identity.json') and not re.fullmatch(r'(?:posix-spawn-\d+|call-\d+-(?:stub|target))\.bin',name):continue
                try:
                    with (local/name).open('wb') as target:ftp.retrbinary('RETR '+name,target.write)
                except ftplib.error_perm as error:
                    files[name]={'retrieval_error':str(error)};continue
                raw=(local/name).read_bytes();files[name]={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
                if name.endswith('.jsonl'):files[name]['records']=[json.loads(line) for line in raw.splitlines() if line.strip()]
            result['runs'].append({'run':run,'files':files})
    finally:
        ftp.close();(dest/'fetch.json').write_text(json.dumps(result,indent=2)+'\n')
    summaries=[]
    for run in result['runs']:
        rows=run['files'].get('report.jsonl',{}).get('records',[])
        summaries.append({'run':run['run'],'events':rows,'files':list(run['files'])})
    print(dest/'fetch.json');print(json.dumps(summaries,indent=2))
if __name__=='__main__':main()
