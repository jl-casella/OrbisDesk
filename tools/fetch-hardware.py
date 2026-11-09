#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Collect the evidence a hardware build left on the console by FTP and classify the latest run."""
import argparse,datetime,ftplib,hashlib,json,pathlib,re,struct,zlib
from project_brand import state_root
ROOT=pathlib.Path(__file__).resolve().parents[1]
BUILDS={b:('out/wine-hardware-'+b.lower(),'reports/wine-hardware-'+b.lower(),state_root(b)+'/'+b.lower()) for b in ('W001','W002','W003','W004','W005','W006','W007','W008','W009','W010','W011','W012','W013','W014','W015','W016','W017','W018','W019','W020','W021','W022','W023','W024','W025','W026','W027','W028','W029','W030','W031','W032','W033','W034','W035','W036','W037','W038','W039','W040','W041','W042','W043','W044','W045','W046','W047','W048','W049','W050','W051','W052','W053','W054','W055','W056','W057','W058','W059','W060','W061','W062','W063','W064','W065','W066','W067','W068','W069','W070','W071','W072','W073','W074','W075','W076','W077','W078','W079','W080','W081','W082','W083','W084','W085','W086','W087','W088','W089','W090','W091','W092','W093','W094','W095','W096','W097','W098','W099','W100','W101','W102','W103','W104','W105','W106','W107','W108','W109','W110','W111','W112','W113','W114','W115','W116','W117','W118','W119','W120','W121','W122','W123','W124','W125','W126','W127','W128','W129','W130','W131','W132','W133','W134','W135','W136','W137','W138','W139','W140','W141','W142','W143','W144','W145','W146','W147','W148','W149','W150','W151','W152','W153','W154','W155','W156','W157','W158','W159','W160','W161','W162','W163','W164','W165','W166','W167','W168','W169','W170','W171','W172','W173','W174','W175','W176','W177','W178','W179','W180','W181','W182','W183','W184','W185','W186','W187','W188','W189','W190','W191','W192','W193','W194','W195','W196','W197','W198','W199','W200','W201','W202','W203','W204','W205','W206','W207','W208','W209','W210','W211','W212','W213','W214','W215','W216','W217','W218','W219','W220','W221','W222','W223','W224','W225','W226','W227','W228','W229','W230','W231','W232','W233','W234','W235','W236','W237','W238','W239','W240','W241','W242','W243','W244','W245','W246','W247','W248','W249','W250','W251','W252','W253','W254','W255','W256','W257','W258','W259','W260','W261','W262','W263','W264','W265','W266','W267','W268','W269','W270','W271','W272','W273','W274','W275','W276','W277','W278','W279','W280','W281','W282','W283','W284','W285','W286','W287','W288','W289','W290','W291','W292','W293','W294','W295','W296','W297','W298','W299','W300','W301','W302')}
parser=argparse.ArgumentParser()
parser.add_argument('--build',choices=sorted(BUILDS),required=True)
parser.add_argument('--host',default='192.168.68.107');parser.add_argument('--port',type=int,default=2121)
args=parser.parse_args()
out_dir,report_dir,remote_dir=BUILDS[args.build]
manifest=json.loads((ROOT/out_dir/'manifest.json').read_text())
target=ROOT/report_dir/'physical'/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
target.mkdir(parents=True)
ftp=ftplib.FTP();ftp.connect(args.host,args.port,timeout=60);ftp.login();ftp.set_pasv(True)
def listing(path):
    try:return sorted(ftp.nlst(path))
    except ftplib.error_perm:return []
chmodded=[]
def fetch(remote,local):
    local.parent.mkdir(parents=True,exist_ok=True)
    for attempt in range(2):
        try:
            with local.open('wb') as stream:ftp.retrbinary('RETR '+remote,stream.write)
            return True
        except ftplib.error_perm:
            local.unlink(missing_ok=True)
            # Our own diagnostic files may be created 0600; widen only those for read access.
            if attempt or not remote.startswith(remote_dir):return False
            try:ftp.sendcmd('SITE CHMOD 644 '+remote);chmodded.append(remote)
            except ftplib.all_errors:return False
    return False
names=[n if n.startswith('/') else remote_dir+'/'+n for n in listing(remote_dir)]
(target/'ftp-list.txt').write_text('\n'.join(names)+'\n')
fetched={}
for remote in names:
    base=remote.rsplit('/',1)[-1]
    if base in ('.','..'):continue
    if base=='frames':
        for frame in listing(remote):
            frame=frame if frame.startswith('/') else remote+'/'+frame
            if frame.endswith('.bmp') and fetch(frame,target/'frames'/frame.rsplit('/',1)[-1]):fetched[frame]=True
    elif fetch(remote,target/base):fetched[remote]=True
result_name=manifest.get('result_name','result.txt')
result_remote='/data/wine-prefix/drive_c/orbis/'+result_name
has_result=fetch(result_remote,target/result_name)
ftp.quit()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
logs=sorted(target.glob('run-*.log'),key=lambda p:int(re.search(r'(\d+)',p.name).group(1)))
log=logs[-1].read_text(errors='replace') if logs else ''
markers=re.findall(r'^(?:'+args.build+r'|PWBOOT) [^\r\n]*',log,re.M)
exit_match=re.search(args.build+r' process_exit method=\S+ status=0x([0-9a-f]{8})',log)
boot_return=re.search(args.build+r' boot_main_return rc=(-?\d+)',log)
exit_code=int(exit_match.group(1),16) if exit_match else int(boot_return.group(1)) if boot_return else None
reference=(ROOT/manifest['expected_result']).read_bytes()
# Text rendering (W026) is judged as in increment 25: FreeType antialiasing is not
# expected to equal Windows ink, only the pass flags the fixture computes itself.
prefix=manifest.get('expected_prefix')
produced=(target/result_name).read_bytes() if has_result else b''
matches=has_result and (produced.startswith(prefix.encode()) if prefix else produced==reference)
# explorer (W027) has no result file and runs until the app is closed: it is judged by
# presenting desktop frames without a crash record, never as passed.
if manifest.get('runs_until_closed'):
    # any frame Wine presents after the launcher hands over (W028 uses a 1280x720 desktop)
    handed=log.find(args.build+' calling_wine_boot_main')
    desktop=handed>=0 and re.search(r'^PWBOOT frame_presented ',log[handed:],re.M)
    status='presented' if desktop and not re.search(args.build+r' crash ',log) else 'crashed' if markers else 'no-log'
elif matches and exit_code==0:status='passed'
# The launcher stops on a failed stage and logs its code; only a log without that is a crash.
elif exit_code is None and markers and re.search(r' rc=(?!0)-?\w+$',markers[-1]):status='blocked'
elif exit_code is None and not boot_return:status='crashed' if markers else 'no-log'
else:status='blocked'
frames=sorted((target/'frames').glob('*.bmp')) if (target/'frames').exists() else []
if frames:
    bmp=frames[-1].read_bytes();w,h=struct.unpack_from('<ii',bmp,18);top=h<0;h=abs(h);pixels=bmp[54:]
    order=range(h) if top else range(h-1,-1,-1)
    rows=b''.join(b'\0'+bytes(v for x in range(w) for v in
        (pixels[(y*w+x)*4+2],pixels[(y*w+x)*4+1],pixels[(y*w+x)*4])) for y in order)
    def chunk(kind,body):return struct.pack('>I',len(body))+kind+body+struct.pack('>I',zlib.crc32(kind+body)&0xffffffff)
    (target/'screen.png').write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,2,0,0,0))+
        chunk(b'IDAT',zlib.compress(rows,9))+chunk(b'IEND',b''))
report={'build':args.build,'status':status,'classification':'physical PS4 run','host':args.host,
    'log':logs[-1].name if logs else None,'exit_code':exit_code,'result_present':has_result,
    'result_matches_windows_reference':matches,'last_marker':markers[-1] if markers else None,
    'markers':markers[-40:],'chmod_applied':chmodded,'eboot_sha256':manifest['eboot_sha256'],
    'artifacts':{p.relative_to(target).as_posix():sha(p) for p in sorted(target.rglob('*')) if p.is_file()}}
(target/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(target/'report.json');print(json.dumps({k:report[k] for k in ('status','log','exit_code','last_marker')}))
