#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Initialize a prefix with real native Wine and verify the PE32 console fixture."""
import argparse,datetime,hashlib,json,os,pathlib,resource,signal,subprocess,tarfile,tempfile,time
ROOT=pathlib.Path(__file__).resolve().parents[1];BUILD=ROOT/'.deps/wine/runtime/build'
parser=argparse.ArgumentParser()
parser.add_argument('--wine-debug',default='-all,err+all,+wineboot,+setupapi')
parser.add_argument('--boot-timeout',type=int,default=120)
args=parser.parse_args()
programs=[BUILD/name for name in ('loader/wine','loader/wine-preloader','server/wineserver')]
inputs=[BUILD/'loader/wine.inf',BUILD/'programs/wineboot/x86_64-windows/wineboot.exe',ROOT/'out/console32-bare.exe']
missing=[str(path.relative_to(ROOT)) for path in [*programs,*inputs] if not path.is_file()]
not_executable=[str(path.relative_to(ROOT)) for path in programs if path.is_file() and not os.access(path,os.X_OK)]
if missing or not_executable:
    raise SystemExit('Host prefix inputs missing or not executable; build the host PE/Unix closure first: '+
                     repr({'missing':missing,'not_executable':not_executable}))
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
out=ROOT/'reports/increment15/prefix-producer'/stamp;out.mkdir(parents=True)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def execute(command,name,env,cwd,timeout):
    with (out/(name+'.log')).open('w') as log:
        process=subprocess.Popen(command,env=env,cwd=cwd,stdout=log,stderr=subprocess.STDOUT,
            start_new_session=True,preexec_fn=lambda:resource.setrlimit(resource.RLIMIT_CORE,(0,0)))
        try:return {'command':list(map(str,command)),'exit_code':process.wait(timeout=timeout),'timed_out':False}
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGKILL)
            return {'command':list(map(str,command)),'exit_code':process.wait(),'timed_out':True}
def stop(env):
    codes=[]
    for argument in ('-k','-w'):
        try:codes.append(subprocess.run([BUILD/'server/wineserver',argument],env=env,capture_output=True,timeout=10).returncode)
        except subprocess.TimeoutExpired:codes.append(None)
    return codes
start=time.monotonic()
with tempfile.TemporaryDirectory(prefix='orbis-prefix-') as temporary:
    root=pathlib.Path(temporary);prefix=root/'prefix';run=root/'run';run.mkdir()
    env=dict(os.environ,WINEPREFIX=str(prefix),WINEDEBUG=args.wine_debug,
        WINEDLLOVERRIDES='winemenubuilder.exe=d',DISPLAY='',WAYLAND_DISPLAY='')
    boot=execute([BUILD/'loader/wine',BUILD/'programs/wineboot/x86_64-windows/wineboot.exe','--init'],
                 'wineboot',env,run,args.boot_timeout)
    first_stop=stop(env)
    fixture={'exit_code':None,'timed_out':False};second_stop=[]
    if boot['exit_code']==0 and not boot['timed_out'] and first_stop==[0,0]:
        fixture=execute([BUILD/'loader/wine',ROOT/'out/console32-bare.exe'],'console32',env,run,60)
        second_stop=stop(env)
    result=run/'result.txt';expected=b'sum=500500;thread=ok;dll=ok\r\n'
    matches=result.is_file() and result.read_bytes()==expected
    if result.is_file():(out/'result.txt').write_bytes(result.read_bytes())
    registry={name:sha(prefix/name) for name in ('system.reg','user.reg','userdef.reg') if (prefix/name).is_file()}
    logs='\n'.join(p.read_text(errors='replace') for p in out.glob('*.log'))
    setup_errors='SetupDefaultQueueCallbackW copy error' in logs
    initialized=boot['exit_code']==0 and not boot['timed_out'] and first_stop==[0,0]
    verified=initialized and fixture['exit_code']==0 and not fixture['timed_out'] and matches and second_stop==[0,0] and len(registry)==3 and not setup_errors
    with tarfile.open(out/'prefix.tar.gz','w:gz',dereference=False) as archive:
        if prefix.exists():archive.add(prefix,arcname='prefix')
    report={'schema_version':1,'status':'passed' if verified else 'blocked',
        'scope':'Native Linux prefix for the console fixture; not PS4 validation',
        'initialized_by_wineboot':initialized,'console32_verified':matches and fixture['exit_code']==0,
        'prefix_ready_for_packaging':verified,'prefix_ready_for_ps4':False,
        'wineboot':boot,'console32':fixture,'server_cleanup':[first_stop,second_stop],
        'registry_hashes':registry,'setup_copy_errors':setup_errors,
        'wine_commit':subprocess.check_output(['git','-C',str(ROOT/'.deps/wine/source'),'rev-parse','HEAD'],text=True).strip(),
        'exe_sha256':sha(ROOT/'out/console32-bare.exe'),'prefix_archive_sha256':sha(out/'prefix.tar.gz'),
        'native_loader_sha256':sha(BUILD/'loader/wine'),'native_server_sha256':sha(BUILD/'server/wineserver'),
        'disabled_components':['winemenubuilder.exe (desktop integration)'],
        'wine_debug':args.wine_debug,'boot_timeout_seconds':args.boot_timeout,
        'duration_seconds':round(time.monotonic()-start,3),'hardware_status':'pending'}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report));print('Report:',out/'report.json')
    if not verified:raise SystemExit(1)
