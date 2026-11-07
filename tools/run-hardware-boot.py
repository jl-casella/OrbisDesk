#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""One short emulator smoke check of the hardware bootstrap, not the Wine suite."""
import argparse,datetime,hashlib,json,os,pathlib,re,shutil,signal,struct,subprocess,tempfile,zlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--build',choices=['H001','H001B'],default='H001B');args=parser.parse_args()
slug='hardware-'+args.build.lower()
out=ROOT/'reports'/slug/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
out.mkdir(parents=True)
app=ROOT/'build'/slug/'app'
with tempfile.TemporaryDirectory(prefix='orbis-hw01-') as tmp:
    work=pathlib.Path(tmp);data=work/'data';data.mkdir()
    command=['python3',str(ROOT/'tools/run-linux-shad.py'),'--fork','--config-clean','--fullscreen','false',
             '--mount',str(data),'/data','-g',str(app/'eboot.bin')]
    with (out/'stdout.log').open('w') as stdout,(out/'stderr.log').open('w') as stderr:
        proc=subprocess.Popen(command,cwd=work,stdout=stdout,stderr=stderr,start_new_session=True)
        try:proc.wait(timeout=15)
        except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
    if (data/'orbisdesk/hw01').exists():shutil.copytree(data/'orbisdesk/hw01',out/'data')
records=[]
for log in sorted((out/'data').glob('report-*.jsonl')):
    records += [json.loads(line) for line in log.read_text().splitlines()]
frames=sorted((out/'data/frames').glob('*.bmp'))
if frames:
    bmp=frames[-1].read_bytes();w,h=struct.unpack_from('<ii',bmp,18);h=abs(h);pixels=bmp[54:]
    rows=b''.join(b'\0'+bytes(v for x in range(w) for v in
        (pixels[(y*w+x)*4+2],pixels[(y*w+x)*4+1],pixels[(y*w+x)*4])) for y in range(h))
    def chunk(kind,body):return struct.pack('>I',len(body))+kind+body+struct.pack('>I',zlib.crc32(kind+body)&0xffffffff)
    (out/'screen.png').write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,2,0,0,0))+
        chunk(b'IDAT',zlib.compress(rows,9))+chunk(b'IEND',b''))
text=(out/'stdout.log').read_text(errors='replace')
expected={'videoout','LOG FILE','APP0 READ','DATA ROUNDTRIP','MEMORY PROTECT','LOW MEMORY','THREADS TLS'}
passed={r['case'] for r in records if r['status']=='passed'}
result={'build':args.build,'status':'passed' if expected<=passed and any(r['case']=='complete' for r in records) else 'failed',
    'classification':'emulator smoke check only','hardware_status':'pending','records':records,
    'invoked_stubs':sorted(set(re.findall(r'\bStub: ([^\r\n(]+) \(nid:',text))),
    'eboot_sha256':hashlib.sha256((app/'eboot.bin').read_bytes()).hexdigest()}
(out/'report.json').write_text(json.dumps(result,indent=2)+'\n')
print(out/'report.json')
if result['status']!='passed':raise SystemExit('Bootstrap smoke check failed')
