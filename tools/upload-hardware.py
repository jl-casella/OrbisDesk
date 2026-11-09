#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Upload a hardware build (PKG plus its /data runtime) by FTP, verifying every file by read-back."""
import argparse,datetime,ftplib,hashlib,io,json,pathlib,posixpath,re
from project_brand import LEGACY_STATE_ROOT, package_build
ROOT=pathlib.Path(__file__).resolve().parents[1]
BUILDS={b:('out/wine-hardware-'+b.lower(),'reports/wine-hardware-'+b.lower()) for b in ('W001','W002','W003','W004','W005','W006','W007','W008','W009','W010','W011','W012','W013','W014','W015','W016','W017','W018','W019','W020','W021','W022','W023','W024','W025','W026','W027','W028','W029','W030','W031','W032','W033','W034','W035','W036','W037','W038','W039','W040','W041','W042','W043','W044','W045','W046','W047','W048','W049','W050','W051','W052','W053','W054','W055','W056','W057','W058','W059','W060','W061','W062','W063','W064','W065','W066','W067','W068','W069','W070','W071','W072','W073','W074','W075','W076','W077','W078','W079','W080','W081','W082','W083','W084','W085','W086','W087','W088','W089','W090','W091','W092','W093','W094','W095','W096','W097','W098','W099','W100','W101','W102','W103','W104','W105','W106','W107','W108','W109','W110','W111','W112','W113','W114','W115','W116','W117','W118','W119','W120','W121','W122','W123','W124','W125','W126','W127','W128','W129','W130','W131','W132','W133','W134','W135','W136','W137','W138','W139','W140','W141','W142','W143','W144','W145','W146','W147','W148','W149','W150','W151','W152','W153','W154','W155','W156','W157','W158','W159','W160','W161','W162','W163','W164','W165','W166','W167','W168','W169','W170','W171','W172','W173','W174','W175','W176','W177','W178','W179','W180','W181','W182','W183','W184','W185','W186','W187','W188','W189','W190','W191','W192','W193','W194','W195','W196','W197','W198','W199','W200','W201','W202','W203','W204','W205','W206','W207','W208','W209','W210','W211','W212','W213','W214','W215','W216','W217','W218','W219','W220','W221','W222','W223','W224','W225','W226','W227','W228','W229','W230','W231','W232','W233','W234','W235','W236','W237','W238','W239','W240','W241','W242','W243','W244','W245','W246','W247','W248','W249','W250','W251','W252','W253','W254','W255','W256','W257','W258','W259','W260','W261','W262','W263','W264','W265','W266','W267','W268','W269','W270','W271','W272','W273','W274','W275','W276','W277','W278','W279','W280','W281','W282','W283','W284','W285','W286','W287','W288','W289','W290','W291','W292','W293','W294','W295','W296','W297','W298','W299','W300','W301','W302')}
parser=argparse.ArgumentParser()
parser.add_argument('--build',choices=sorted(BUILDS),required=True)
parser.add_argument('--host',default='192.168.68.107');parser.add_argument('--port',type=int,default=2121)
parser.add_argument('--timeout',type=int,default=60,help='FTP timeout in seconds, per connection/read')
parser.add_argument('--skip-runtime',action='store_true',help='upload only the PKG')
parser.add_argument('--pkg-only',action='store_true',
    help='alpha-1: upload only a PKG that carries the runtime; the app installs it into /data on its first start '
         '(native/hw_install.h). Old packages are removed after the PKG is verified.')
parser.add_argument('--keep-old-packages',action='store_true',help='retain previous OrbisDesk Wine PKGs (default: remove after verified full upload)')
args=parser.parse_args()
if args.timeout<=0:parser.error('--timeout must be positive')
out_dir,report_dir=(ROOT/p for p in BUILDS[args.build])
manifest=json.loads((out_dir/'manifest.json').read_text())
pkg=ROOT/manifest['package'];runtime=ROOT/manifest['runtime_root']
if args.pkg_only:
    if not manifest.get('runtime_embedded',{}).get('embedded'):
        raise SystemExit('--pkg-only needs a package with the runtime inside (built without --runtime-outside-package)')
    args.skip_runtime=True
sha=lambda data:hashlib.sha256(data).hexdigest()
# Writable state for Wine: the prefix registry and the home directory.
WRITABLE=('wine-prefix','wine-home')

def connect():
    session=ftplib.FTP();session.connect(args.host,args.port,timeout=args.timeout);session.login();session.set_pasv(True)
    return session
ftp=connect();welcome=ftp.getwelcome()
def retrying(action,*values):
    # A stalled GoldHEN transfer drops the control connection; reconnect and repeat the step.
    global ftp
    for attempt in range(4):
        try:return action(*values)
        except (TimeoutError,EOFError,ConnectionError,ftplib.error_temp) as error:
            print('retry',attempt+1,action.__name__,values[:1],repr(error),flush=True)
            try:ftp.close()
            except Exception:pass
            ftp=connect()
    raise SystemExit('FTP step failed repeatedly: %r'%(values[:1],))
def remote_hash(path):
    digest=hashlib.sha256()
    try:ftp.retrbinary('RETR '+path,digest.update)
    except ftplib.error_perm:return None
    return digest.hexdigest()
def ensure_dir(path):
    try:ftp.mkd(path)
    except ftplib.error_perm:
        try:ftp.cwd(path);ftp.cwd('/')
        except ftplib.error_perm:raise SystemExit('cannot create remote directory '+path)
def chmod(path,mode):
    try:ftp.sendcmd('SITE CHMOD %o %s'%(mode,path));return True
    except ftplib.all_errors:return False
def put(local,remote,expected):
    if remote_hash(remote)==expected:return 'present'
    with local.open('rb') as stream:ftp.storbinary('STOR '+remote,stream,blocksize=1<<20)
    if remote_hash(remote)!=expected:raise SystemExit('read-back mismatch: '+remote)
    return 'uploaded'
# W172/W175/W292: the user.reg keys the console keeps (tools/console_state.py, shared with the
# first-run installer's install.json)
USER_REG='wine-prefix/user.reg';REG_HEADER=b'WINE REGISTRY Version 2'
from console_state import CONSOLE_OWNED
reset=[key.lower() for key in manifest.get('user_reg_reset',[])]
if not set(reset)<=set(CONSOLE_OWNED):raise SystemExit('user_reg_reset names keys the console does not own: %r'%reset)
def reg_blocks(text):
    """the lines before the first key, then (key, lines) per key; a key block runs to the next one"""
    head,blocks=[],[]
    for line in text.split('\n'):
        match=re.match(r'^\[(.*)\](?: [0-9]+)?$',line)
        if match:blocks.append((match.group(1),[line]))
        elif blocks:blocks[-1][1].append(line)
        else:head.append(line)
    return head,blocks
def owner(key,roots):
    """the root of roots that key is or lies under (.reg keys double their backslashes), else None"""
    key=key.lower()
    for root in roots:
        stored=root.replace('\\','\\\\')
        if key==stored or key.startswith(stored+'\\\\'):return root
    return None
def merge_user_reg(build,console,roots,delivered):
    """the build's user.reg with the console's blocks under roots in place of its own, each group
    where the build has that root (else at the end). A build-only block under roots is added when
    it is new (its key, lower case, not in delivered); one an earlier upload delivered was deleted
    on the console and stays deleted (W207). Latin-1 keeps every byte as it is. Returns the file,
    the blocks kept per root, and the build-only blocks added and left out."""
    head,build_blocks=reg_blocks(build.decode('latin-1'))
    kept={root:[] for root in roots}
    for key,lines in reg_blocks(console.decode('latin-1'))[1]:
        root=owner(key,roots)
        if root:kept[root].append((key,lines))
    replaced={key.lower() for blocks in kept.values() for key,_ in blocks}
    merged=[];inserted=set();added=[];deleted=[]
    for key,lines in build_blocks:
        root=owner(key,roots)
        if root and root not in inserted:merged+=kept[root];inserted.add(root)
        if not root:merged.append((key,lines))
        elif key.lower() in replaced:continue
        elif key.lower() in delivered:deleted.append(key)
        else:merged.append((key,lines));added.append(key)
    for root in roots:
        if root not in inserted:merged+=kept[root]
    return ('\n'.join(head+[line for _,lines in merged for line in lines]).encode('latin-1'),
            {r:len(b) for r,b in kept.items()},added,deleted)
def fetch(path):
    data=io.BytesIO()
    try:ftp.retrbinary('RETR '+path,data.write)
    except ftplib.error_perm:return None
    return data.getvalue()
def put_bytes(data,remote):
    expected=sha(data)
    if remote_hash(remote)==expected:return 'present'
    ftp.storbinary('STOR '+remote,io.BytesIO(data),blocksize=1<<20)
    if remote_hash(remote)!=expected:raise SystemExit('read-back mismatch: '+remote)
    return 'uploaded'
# W207: the build's user.reg blocks under CONSOLE_OWNED that uploads delivered, on the console
# beside its logs (not in wine-prefix, which only the build fills). Written after user.reg is
# verified, with this build's blocks: a block a build drops and a later build brings back is new
# again. A ledger that is there but unreadable stops the upload.
LEDGER_DIR='/data/orbisdesk';LEDGER=LEDGER_DIR+'/user-reg-delivered.json'
def read_ledger():
    data=fetch(LEDGER)
    if data is None:data=fetch(LEGACY_STATE_ROOT+'/user-reg-delivered.json')
    if data is None:return None
    try:ledger=json.loads(data)
    except ValueError:raise SystemExit('ledger is not JSON: '+LEDGER)
    if ledger.get('schema_version')!=1 or not isinstance(ledger.get('keys'),list):raise SystemExit('unexpected ledger: '+LEDGER)
    return ledger

record={'host':args.host,'port':args.port,'build':args.build,'title_id':manifest['title_id'],'server':welcome,
    'started':datetime.datetime.now(datetime.timezone.utc).isoformat()}
pkg_sha=sha(pkg.read_bytes())
if pkg_sha!=manifest['package_sha256']:raise SystemExit('PKG differs from manifest')
remote_pkg=('/data/pkg/OrbisDesk.pkg' if pkg.name=='OrbisDesk.pkg'
            else '/data/pkg/orbisdesk-%s-%s.pkg'%(args.build,pkg_sha[:12]))
record.update(remote_path=remote_pkg,bytes=pkg.stat().st_size,sha256=pkg_sha,pkg_transfer=retrying(put,pkg,remote_pkg,pkg_sha))
if not args.skip_runtime:
    for d in manifest['directories']:
        remote='/data/'+d;retrying(ensure_dir,remote)
        if d.split('/')[0] in WRITABLE:retrying(chmod,remote,0o777)
    counts={'present':0,'uploaded':0};chmod_failed=[]
    for index,(name,entry) in enumerate(manifest['runtime_files'].items(),1):
        remote='/data/'+name
        if name==USER_REG:
            # W172: merged with the console's copy (merge_user_reg); never uploaded as the build's alone
            build_reg=(runtime/name).read_bytes()
            if sha(build_reg)!=entry['sha256']:raise SystemExit('runtime file differs from manifest: '+name)
            console_reg=retrying(fetch,remote)
            ledger=retrying(read_ledger)
            delivered=set(ledger['keys']) if ledger else set()
            roots=[root for root in CONSOLE_OWNED if root not in reset]
            if console_reg is None or not console_reg.startswith(REG_HEADER):
                data,kept,added,deleted=build_reg,{},[],[]
                source='build (console copy %s)'%('absent' if console_reg is None else 'not a registry file')
            else:
                data,kept,added,deleted=merge_user_reg(build_reg,console_reg,roots,delivered);source='merged'
            state=retrying(put_bytes,data,remote);counts[state]+=1
            owned=sorted({key.lower() for key,_ in reg_blocks(build_reg.decode('latin-1'))[1] if owner(key,CONSOLE_OWNED)})
            retrying(ensure_dir,LEDGER_DIR)
            ledger_state=retrying(put_bytes,(json.dumps({'schema_version':1,'build':args.build,'keys':owned},indent=1)+'\n').encode(),LEDGER)
            record['user_reg']={'source':source,'console_blocks_kept':kept,'reset':reset,'build_sha256':entry['sha256'],
                                'console_sha256':sha(console_reg) if console_reg is not None else None,'uploaded_sha256':sha(data),
                                'build_blocks_added':added,'build_blocks_deleted_on_console':deleted,
                                'ledger':{'path':LEDGER,'found':ledger is not None,'build':ledger.get('build') if ledger else None,
                                          'keys':len(owned),'state':ledger_state}}
            print(index,state,name,source,'console_blocks_kept=%d'%sum(kept.values()),'reset=%s'%','.join(reset),
                  'added=%d'%len(added),'left_deleted=%d'%len(deleted),'ledger=%s'%('found' if ledger else 'absent'),flush=True)
            if not retrying(chmod,remote,0o666):chmod_failed.append(name)
            continue
        state=retrying(put,runtime/name,remote,entry['sha256']);counts[state]+=1
        print(index,state,name,flush=True)
        if not retrying(chmod,remote,0o666 if name.split('/')[0] in WRITABLE else 0o644):chmod_failed.append(name)
    record['runtime']={'files':len(manifest['runtime_files']),
        'bytes':sum(e['bytes'] for e in manifest['runtime_files'].values()),**counts,'chmod_failed':chmod_failed}
    # W170: files earlier builds put in the persistent prefix and this one no longer ships.
    # Only paths under wine-prefix/ that this build does not upload; an absent file is fine.
    obsolete={'deleted':[],'absent':[]}
    def delete_file(path):return ftp.delete(path)
    for name in manifest.get('obsolete_files',[]):
        if not name.startswith('wine-prefix/') or '..' in name.split('/') or name in manifest['runtime_files']:
            raise SystemExit('refusing obsolete path '+name)
        try:obsolete['deleted'].append({'path':name,'reply':retrying(delete_file,'/data/'+name)})
        except ftplib.error_perm as error:obsolete['absent'].append({'path':name,'reply':str(error)})
    print('obsolete_deleted',len(obsolete['deleted']),'absent',len(obsolete['absent']),flush=True)
    record['obsolete_files']=obsolete
# User preference: keep only the new Wine PKG on the console, after a fully
# verified upload. Never delete logs, runtime files, local releases, other PKGs,
# a newer build, or a path outside exactly /data/pkg. NLST is untrusted input.
cleanup={'deleted':[],'failed':[],'kept':remote_pkg}
if not args.keep_old_packages and (args.pkg_only or not args.skip_runtime):
    def list_packages():return ftp.nlst('/data/pkg')
    def delete_package(path):return ftp.delete(path)
    for entry in retrying(list_packages):
        if posixpath.dirname(entry) not in ('','/data/pkg'):continue
        filename=posixpath.basename(entry)
        old_build=package_build(filename)
        if old_build is None or old_build>=int(args.build[1:]):continue
        remote='/data/pkg/'+filename
        if remote==remote_pkg:continue
        try:
            reply=retrying(delete_package,remote)
            cleanup['deleted'].append({'path':remote,'reply':reply})
        except ftplib.all_errors as error:
            cleanup['failed'].append({'path':remote,'error':str(error)})
    print('old_packages_deleted',len(cleanup['deleted']),'failed',len(cleanup['failed']),flush=True)
else:cleanup['skipped']='keep-old-packages' if args.keep_old_packages else 'runtime not verified (--skip-runtime)'
record['previous_packages_cleanup']=cleanup
ftp.quit()
record.update(readback_verified=True,installation='pending manual install',hardware_execution='pending',
    finished=datetime.datetime.now(datetime.timezone.utc).isoformat())
target=report_dir/'transfers';target.mkdir(parents=True,exist_ok=True)
path=target/(datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.json')
path.write_text(json.dumps(record,indent=2)+'\n');print(path);print(json.dumps({k:record.get(k) for k in ('remote_path','pkg_transfer','runtime')}))
