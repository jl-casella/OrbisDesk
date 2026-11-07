#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Fresh Linux-host boot attempt; keep runtime files on ext4, archive as tar.
An entry marker is progress, never proof of Windows execution.
"""
import argparse,datetime,hashlib,json,os,pathlib,re,resource,shutil,signal,struct,subprocess,tarfile,tempfile,time
from wine_prefix import stage_package
from wine_fonts import stage_fonts
ROOT=pathlib.Path(__file__).resolve().parents[1]
# Windows reference folder, EXE, reference copy in /data, file the EXE writes.
CONSOLE_CASES={'console-bare':('increment11-windows-reference','console32-bare.exe','console-bare-reference.txt','orbisdesk/console-bare/result.txt'),
               'console32':('increment18-windows-reference','console32.exe','console32-reference.txt','orbisdesk/console32/result.txt')}
parser=argparse.ArgumentParser();parser.add_argument('--timeout',type=int,default=25)
parser.add_argument('--fork',action='store_true')
parser.add_argument('--exe',type=pathlib.Path)
parser.add_argument('--prepared-prefix',type=pathlib.Path)
parser.add_argument('--prefix-preflight',action='store_true')
parser.add_argument('--case',default='files',help='Diagnostic case, only with --baseline')
mode=parser.add_mutually_exclusive_group();mode.add_argument('--baseline',action='store_true');mode.add_argument('--services',action='store_true')
mode.add_argument('--ipc-services',action='store_true');mode.add_argument('--gs-services',action='store_true');mode.add_argument('--signal-services',action='store_true')
parser.add_argument('--wow64-cpu',choices=['wowprospero'],help='Stage the translator WoW64 CPU backend and select it for the prepared-prefix attempt')
parser.add_argument('--wineenv',action='append',default=[],help='Diagnostic KEY=VALUE for the prepared-prefix attempt')
parser.add_argument('--wine-gui',action='store_true',help='Stage the PE64 GUI closure (out/wine-gui) and the GUI fixture')
parser.add_argument('--wine-exe',help='Windows path of the program Wine runs in the prepared prefix')
parser.add_argument('--wine-arg',action='append',default=[],help='Argument for that program')
parser.add_argument('--winedebug',help='Diagnostic WINEDEBUG channels for the prepared-prefix attempt')
mode.add_argument('--pipe-services',action='store_true');mode.add_argument('--fs-services',action='store_true')
mode.add_argument('--metadata-services',action='store_true');args=parser.parse_args()
if args.prefix_preflight and not args.prepared_prefix:
    parser.error('--prefix-preflight requires --prepared-prefix')
if args.wow64_cpu and not args.prepared_prefix:parser.error('--wow64-cpu requires --prepared-prefix')
if (args.wine_gui or args.wine_exe or args.wine_arg) and not args.prepared_prefix:parser.error('--wine-gui/--wine-exe require --prepared-prefix')
if args.prepared_prefix and any((args.baseline,args.services,args.ipc_services,args.gs_services,args.signal_services,args.pipe_services,args.fs_services,args.metadata_services)):
    parser.error('--prepared-prefix cannot be combined with diagnostic modes')
if args.prepared_prefix and args.exe and args.exe.resolve()!=(ROOT/'out/console32-bare.exe').resolve():
    parser.error('Prepared prefix currently requires the packaged console32-bare.exe')
args.exe=args.exe or ROOT/('out/console32-bare.exe' if args.prepared_prefix else 'out/console32.exe')
if not re.fullmatch('[a-z][a-z0-9-]*',args.case) or (args.case!='files' and not args.baseline):
    parser.error('--case requires a valid diagnostic name and --baseline')
name=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
out=ROOT/'reports/linux-wine-runs'/name;out.mkdir(parents=True)
emulator_manifest=None
if args.fork:
    emulator_manifest=json.loads((ROOT/'build/shadPS4-linux/build-manifest.json').read_text())
    binary=ROOT/'build/shadPS4-linux/shadps4'
    if hashlib.sha256(binary.read_bytes()).hexdigest()!=emulator_manifest['executable_sha256']:
        raise SystemExit('Fork binary differs from build manifest')
    shutil.copyfile(ROOT/'build/shadPS4-linux/build-manifest.json',out/'emulator-build.json')
with tempfile.TemporaryDirectory(prefix='orbisdesk-') as temporary:
    run=pathlib.Path(temporary);data=run/'data'
    for path in ['wine-prefix','wine-home','wine/lib/wine/x86_64-unix','wine/lib/wine/i386-windows','wine/lib/wine/x86_64-windows','wine/share/wine/nls']:(data/path).mkdir(parents=True,exist_ok=True)
    for user in range(1000,1004):
        for path in ['savedata','trophy','inputs']:(run/f'user/home/{user}/{path}').mkdir(parents=True,exist_ok=True)
    shutil.copyfile(args.exe,data/'console32.exe')
    prefix_package=None
    if args.prepared_prefix:
        wine_commit=json.loads((ROOT/'build/wine-boot/report.json').read_text())['wine_commit']
        prefix_package=stage_package(args.prepared_prefix,data/'wine-prefix',wine_commit)
        if prefix_package['exe_sha256']!=hashlib.sha256(args.exe.read_bytes()).hexdigest():
            raise SystemExit('Packaged EXE differs from console32-bare.exe')
        shutil.copyfile(args.prepared_prefix/'manifest.json',out/'prefix-manifest.json')
    if args.metadata_services:
        directory=data/'metadata';directory.mkdir();(directory/'dir').mkdir()
        (directory/'sample.bin').write_bytes(b'payload');(directory/'other.bin').write_bytes(b'payload')
        os.link(directory/'sample.bin',directory/'hard.bin')
        for name,target in [('file-link','sample.bin'),('dir-link','dir'),('dangling','missing')]:
            (directory/name).symlink_to(target)
    if args.baseline:
        fixtures=json.loads((ROOT/'out/build.json').read_text())['artifacts']
        for filename,entry in fixtures.items():
            if pathlib.Path(filename).suffix not in ('.exe','.dll') or filename=='console32.exe':continue
            source=ROOT/'out'/filename
            if hashlib.sha256(source.read_bytes()).hexdigest()!=entry['sha256']:
                raise SystemExit('Baseline fixture mismatch: '+filename)
            shutil.copyfile(source,data/filename)
        if args.case in CONSOLE_CASES:
            folder,exe_name,reference_name,_=CONSOLE_CASES[args.case]
            reference=json.loads((ROOT/'reports'/folder/'report.json').read_text())
            if hashlib.sha256((data/exe_name).read_bytes()).hexdigest()!=reference['exe_sha256']:
                raise SystemExit(exe_name+' differs from the Windows reference build')
            shutil.copyfile(ROOT/'reports'/folder/'result.txt',data/reference_name)
    manifest=json.loads((ROOT/'out/wine/wine-runtime-manifest.json').read_text())
    for module in manifest['modules']:
        source=ROOT/'out/wine'/module['path']
        assert hashlib.sha256(source.read_bytes()).hexdigest()==module['sha256']
        shutil.copyfile(source,data/'wine/lib/wine/i386-windows'/module['name'])
    for entry in manifest['data']:
        source=ROOT/'out/wine'/entry['path']
        assert hashlib.sha256(source.read_bytes()).hexdigest()==entry['sha256']
        shutil.copyfile(source,data/'wine/share/wine/nls'/source.name)
    pe64=json.loads((ROOT/'out/wine-pe64/manifest.json').read_text())
    for entry in pe64['modules'].values():
        source=ROOT/'out/wine-pe64'/entry['path']
        assert hashlib.sha256(source.read_bytes()).hexdigest()==entry['sha256']
        shutil.copyfile(source,data/'wine/lib/wine/x86_64-windows'/source.name)
    wow64_cpu=None
    if args.wow64_cpu:
        wow64_cpu=json.loads((ROOT/'out/wowprospero-ps4/manifest.json').read_text())
        for entry in wow64_cpu['modules'].values():
            source=ROOT/'out/wowprospero-ps4'/entry['path']
            assert hashlib.sha256(source.read_bytes()).hexdigest()==entry['sha256']
            shutil.copyfile(source,data/'wine/lib/wine/x86_64-windows'/source.name)
        shutil.copyfile(ROOT/'out/wowprospero-ps4/manifest.json',out/'wowprospero-manifest.json')
        # Installed into the extracted prefix after its verification, as prospero-win installs
        # it on the PS5: Wine loads a builtin outside bootstrap only through a system32 file.
        shutil.copyfile(ROOT/'out/wowprospero-ps4/x86_64-windows/wowprospero.dll',
                        data/'wine-prefix/drive_c/windows/system32/wowprospero.dll')
    if args.wine_gui:
        gui=json.loads((ROOT/'out/wine-gui/manifest.json').read_text())
        for entry in gui['modules'].values():
            source=ROOT/'out/wine-gui'/entry['path']
            assert hashlib.sha256(source.read_bytes()).hexdigest()==entry['sha256']
            shutil.copyfile(source,data/'wine/lib/wine/x86_64-windows'/source.name)
        for name in ('gui-window64.exe','gui-text64.exe'):
            fixture=ROOT/gui['targets'][name]['path']
            if hashlib.sha256(fixture.read_bytes()).hexdigest()!=gui['targets'][name]['sha256']:
                raise ValueError('GUI fixture hash mismatch: '+name)
            shutil.copyfile(fixture,data/'wine-prefix/drive_c/orbis'/name)
        stage_fonts(ROOT,ROOT/'out/wine-gui',gui['fonts'],data/'wine-prefix')
        shutil.copyfile(data/'wine-prefix/drive_c/windows/Fonts/tahoma.ttf',data/'wine-prefix/drive_c/orbis/tahoma.ttf')
        shutil.copyfile(ROOT/'out/wine-gui/manifest.json',out/'wine-gui-manifest.json')
    original_elf=ROOT/'out/eboot.bin' if args.baseline else ROOT/'build/wine-boot/eboot.bin'
    elf=run/'guest/eboot.bin';elf.parent.mkdir();shutil.copyfile(original_elf,elf)
    elf_hash=hashlib.sha256(elf.read_bytes()).hexdigest()
    if not args.baseline:
        shutil.copyfile(ROOT/'build/wine-boot/link-report.json',out/'link-report.json')
        shutil.copyfile(ROOT/'build/wine-boot/report.json',out/'ntdll-build.json')
        shutil.copyfile(ROOT/'build/wine-server/report.json',out/'server-build.json')
    guest_args=['--case',args.case] if args.baseline else ['--services'] if args.services else ['--ipc-services'] if args.ipc_services else ['--gs-services'] if args.gs_services else ['--signal-services'] if args.signal_services else ['--pipe-services'] if args.pipe_services else ['--fs-services'] if args.fs_services else ['--metadata-services'] if args.metadata_services else ['/data/console32.exe','/data/wine-prefix']
    if args.prepared_prefix:guest_args=['--prefix-preflight' if args.prefix_preflight else '--prepared-prefix']+(['--winedebug='+args.winedebug] if args.winedebug else [])+(['--wow64-cpu=wowprospero.dll'] if args.wow64_cpu else [])+['--env='+item for item in args.wineenv]+(['--wine-exe='+args.wine_exe] if args.wine_exe else [])+['--wine-arg='+item for item in args.wine_arg]
    command=['python3',str(ROOT/'tools/run-linux-shad.py'),*(['--fork'] if args.fork else []),'--config-clean','--fullscreen','false','--mount',str(data),'/data','-g',str(elf),'--','/app0/eboot.bin',*guest_args]
    start=time.monotonic();timeout=False
    with (out/'stdout.log').open('w') as stdout,(out/'stderr.log').open('w') as stderr:
        process=subprocess.Popen(command,cwd=run,stdout=stdout,stderr=stderr,start_new_session=True,
                                 preexec_fn=lambda:resource.setrlimit(resource.RLIMIT_CORE,(0,0)))
        try:code=process.wait(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            timeout=True;os.killpg(process.pid,signal.SIGKILL);code=process.wait()
    text=(out/'stdout.log').read_text(errors='replace')+(out/'stderr.log').read_text(errors='replace')
    produced=data/CONSOLE_CASES[args.case][3] if args.case in CONSOLE_CASES else None
    console_result=produced.read_bytes() if args.baseline and produced and produced.is_file() else None
    with tarfile.open(out/'runtime.tar.gz','w:gz') as archive:
        archive.add(run,arcname='runtime',filter=lambda item:None if pathlib.PurePosixPath(item.name).name=='core' or pathlib.PurePosixPath(item.name).name.startswith('core.') else item)
    result={'schema_version':1,'status':'blocked','Wine_booted':False,'baseline':args.baseline,
            'unix_entry_reached':'PWBOOT entered___wine_main' in text,'timed_out':timeout,'exit_code':code,
            'duration_seconds':round(time.monotonic()-start,3),'command':command,
            'elf_sha256':elf_hash,'hardware_status':'pending',
            'prefix_state':'empty-development-prefix',
            'host':'WSL Ubuntu 22.04 + private glibc + lavapipe','emulator_kind':'official Linux release',
            'source_commit_declared':json.loads((ROOT/'linux-emulator.lock.json').read_text())['declared_source_commit']}
    result['stages']=list(dict.fromkeys(re.findall(r'PWBOOT ([A-Za-z0-9_]+)',text)))
    main_load=re.findall(r'PWBOOT main_image_load status=([0-9a-f]+) machine=([0-9a-f]+) base=(\S+)',text)
    result['wine_main_image_load']={'status_hex':'0x'+main_load[-1][0],'machine_hex':'0x'+main_load[-1][1],'base':re.sub(r'\x1b\[[0-9;]*m','',main_load[-1][2])} if main_load else None
    result['image_read_fallbacks']=[{'offset_hex':'0x'+offset,'requested':int(requested),'copied':int(copied),'errno':int(error)}
        for offset,requested,copied,error in re.findall(r'PWBOOT image_read_fallback offset=([0-9a-f]+) requested=(\d+) copied=(-?\d+) errno=(\d+)',text)]
    alignment=re.findall(r'PWBOOT anon_alignment_blocked address=(0x[0-9a-f]+) size=(\d+) host_page=(\d+) prot=([0-9a-f]+) flags=([0-9a-f]+)',text)
    result['anon_alignment_blocker']={'address':alignment[-1][0],'size':int(alignment[-1][1]),'host_page':int(alignment[-1][2]),'prot':int(alignment[-1][3],16),'flags':int(alignment[-1][4],16)} if alignment else None
    dispatcher=re.findall(r'PWBOOT dispatcher_slot_ready address=(0x[0-9a-f]+) host_page=(\d+)',text)
    result['dispatcher_slot']={'address':dispatcher[-1][0],'host_page':int(dispatcher[-1][1])} if dispatcher else None
    result['prefix_package']=prefix_package
    result['prefix_state']='externally-initialized-copy' if prefix_package else 'empty-development-prefix'
    result['prefix_preflight_only']=args.prefix_preflight
    result['prefix_preflight_passed']='prefix_preflight_passed' in result['stages']
    result['external_prefix_policy_used']='external_prefix_ready' in result['stages']
    exits=re.findall(r'(?:Exiting with status code |Guest requested process exit, status = )(-?\d+)',text);result['guest_exit_code']=int(exits[-1]) if exits else None
    result['guest_exit_status_hex']=f"0x{result['guest_exit_code']&0xffffffff:08x}" if result['guest_exit_code'] is not None else None
    result['baseline_case']=args.case if args.baseline else None
    result['baseline_guest_passed']=bool(args.baseline and re.search(r'"case":"'+re.escape(args.case)+r'","status":"passed"',text))
    result['services_only']=args.services
    result['ipc_services_only']=args.ipc_services
    result['winedebug']=args.winedebug;result['wine_gui']=args.wine_gui;result['wine_exe']=args.wine_exe;result['wine_args']=args.wine_arg;result['wineenv']=args.wineenv;result['wow64_cpu']=args.wow64_cpu;result['gs_services_only']=args.gs_services;result['signal_services_only']=args.signal_services
    result['pipe_services_only']=args.pipe_services
    result['fs_services_only']=args.fs_services
    result['metadata_services_only']=args.metadata_services
    result['service_results']=[json.loads(line) for line in re.findall(r'PWSERVICE (\{[^\r\n]+\})',text)]
    result['invoked_stubs']=sorted(set(re.findall(r'\bStub: ([^\r\n(]+) \(nid:',text)))
    result['unhandled_access_violation']='Unhandled access violation' in text
    result['windows_execution_verified']=False
    result['validation_scope']='i386 EXE through own PE32 loader and minimal kernel32, without Wine' if args.baseline and args.case in ('console-bare','console32','lifecycle-host') else 'native platform diagnostic' if args.baseline else 'Wine services diagnostic' if args.services or args.ipc_services or args.gs_services or args.signal_services or args.pipe_services or args.fs_services or args.metadata_services else 'Wine startup attempt'
    result['host_ld_preload']=os.environ.get('LD_PRELOAD')
    if args.services or args.ipc_services or args.gs_services or args.signal_services or args.pipe_services or args.fs_services or args.metadata_services or args.prefix_preflight:
        if (result['service_results'] and all(entry['status']=='passed' for entry in result['service_results'])
            and result['guest_exit_code']==0 and code==0 and not timeout
            and not result['invoked_stubs'] and not result['unhandled_access_violation']):
            result['status']='passed'
    if args.prefix_preflight:
        result['validation_scope']='Prepared Wine prefix I/O and PE preflight; no Wine execution'
        if not result['prefix_preflight_passed']:result['status']='blocked'
    result['frames_presented']=len(re.findall(r'PWBOOT frame_presented ',text))
    result['frame_log']=[dict(zip(('n','size','hash'),item)) for item in
                         re.findall(r'PWBOOT frame_presented n=(\d+) size=(\S+) hash=([0-9a-f]+)',text)]
    result['video_out_ready']='PWBOOT video_out_ready' in text
    result['frame_dumps']={}
    for frame in sorted((data/'frames').glob('frame-*.bmp')) if (data/'frames').is_dir() else []:
        bitmap=frame.read_bytes();width,height=struct.unpack_from('<ii',bitmap,18);pixels=bitmap[54:]
        fill=sum(1 for at in range(0,len(pixels),4) if pixels[at:at+3]==bytes((140,60,20)))
        result['frame_dumps'][frame.name]={'sha256':hashlib.sha256(bitmap).hexdigest(),'width':width,
                                           'height':abs(height),'fixture_fill_pixels':fill}
    if args.prepared_prefix and not args.prefix_preflight and args.wine_exe:
        result['validation_scope']='Wine GUI program '+args.wine_exe+' through the in-process user driver'
        reference=ROOT/'reports/increment24-windows-reference/result.txt'
        produced=data/'wine-prefix/drive_c/orbis/result.txt'
        result['gui_result']=produced.read_bytes().decode(errors='replace') if produced.is_file() else None
        text_result=data/'wine-prefix/drive_c/orbis/text-result.txt'
        result['text_result']=text_result.read_text() if text_result.is_file() else None
        if args.wine_exe.lower().endswith('gui-text64.exe'):
            result['text_exe_sha256']=gui['targets']['gui-text64.exe']['sha256']
            if (result['text_result'] and result['text_result'].startswith('passed=1;family_tahoma=1;') and
                result['guest_exit_code']==0 and code==0 and not timeout and not result['invoked_stubs'] and
                not result['unhandled_access_violation'] and result['video_out_ready'] and result['frames_presented']):
                result['status']='passed';result['Wine_booted']=True;result['windows_execution_verified']=True
        result['gui_result_matches_windows_reference']=(reference.is_file() and produced.is_file() and
                                                       produced.read_bytes()==reference.read_bytes())
        reference_report=ROOT/'reports/increment24-windows-reference/report.json'
        staged_exe=data/'wine-prefix/drive_c/orbis/gui-window64.exe'
        result['gui_exe_matches_windows_reference']=(reference_report.is_file() and staged_exe.is_file() and
            hashlib.sha256(staged_exe.read_bytes()).hexdigest()==json.loads(reference_report.read_text())['exe_sha256'])
        if (args.wine_exe.lower().endswith('gui-window64.exe') and result['gui_result_matches_windows_reference'] and
                result['gui_exe_matches_windows_reference'] and
                result['guest_exit_code']==0 and code==0 and not timeout and not result['invoked_stubs'] and
                not result['unhandled_access_violation'] and result['video_out_ready'] and
                any(item['fixture_fill_pixels'] for item in result['frame_dumps'].values())):
            result['status']='passed';result['Wine_booted']=True;result['windows_execution_verified']=True
    elif args.prepared_prefix and not args.prefix_preflight:
        # The prefix package carries no result.txt: only this run's EXE under Wine can write it.
        windows=json.loads((ROOT/'reports/increment11-windows-reference/report.json').read_text())
        expected=(ROOT/'reports/increment11-windows-reference/result.txt').read_bytes()
        produced=data/'wine-prefix/drive_c/orbis/result.txt'
        wine_result=produced.read_bytes() if produced.is_file() else None
        exe=data/'wine-prefix/drive_c/orbis/console32.exe'
        result['wine_result_sha256']=hashlib.sha256(wine_result).hexdigest() if wine_result is not None else None
        result['wine_result_matches_windows_reference']=wine_result==expected
        result['wine_exe_matches_windows_reference']=exe.is_file() and hashlib.sha256(exe.read_bytes()).hexdigest()==windows['exe_sha256']
        result['windows_reference_exit_code']=windows['exit_code']
        if (result['wine_result_matches_windows_reference'] and result['wine_exe_matches_windows_reference'] and
                result['guest_exit_code']==windows['exit_code'] and code==windows['exit_code'] and not timeout and
                not result['invoked_stubs'] and not result['unhandled_access_violation']):
            result['status']='passed';result['Wine_booted']=True;result['windows_execution_verified']=True
            result['validation_scope']='i386 EXE through Wine (prepared prefix) with the WoW64 CPU backend '+str(args.wow64_cpu)
    if args.baseline and args.case in CONSOLE_CASES:
        folder=CONSOLE_CASES[args.case][0]
        expected=(ROOT/'reports'/folder/'result.txt').read_bytes()
        windows=json.loads((ROOT/'reports'/folder/'report.json').read_text())
        result['k32_trace']=[json.loads(line) for line in re.findall(r'PWK32 (\{[^\r\n]+\})',text)]
        result['crt_output']=[json.loads(line) for line in re.findall(r'PWCRT (\{[^\r\n]+\})',text)]
        result['console_result_sha256']=hashlib.sha256(console_result).hexdigest() if console_result is not None else None
        result['console_result_matches_windows_reference']=console_result==expected
        result['windows_reference_exit_code']=windows['exit_code']
        result['console_exe_sha256']=windows['exe_sha256']
    if args.baseline and args.case=='lifecycle-host':
        windows=json.loads((ROOT/'reports/increment17-windows-reference/report.json').read_text())
        result['k32_trace']=[json.loads(line) for line in re.findall(r'PWK32 (\{[^\r\n]+\})',text)]
        result['windows_reference_exit_code']=windows['exit_code']
        result['windows_reference_inputs_match']=all(
            hashlib.sha256((data/name).read_bytes()).hexdigest()==digest for name,digest in windows['inputs'].items())
        if not result['windows_reference_inputs_match']:result['baseline_guest_passed']=False
    if args.baseline:
        expected_exit=42 if args.case in ('pe-preferred','pe-relocated','pe-fourk-preferred','pe-fourk-relocated','pe-dll-preferred','pe-dll-relocated','lifecycle-host') else 7 if args.case=='process-exit-seven' else 0
        result['expected_guest_exit']=expected_exit
        if args.case in CONSOLE_CASES and not result['console_result_matches_windows_reference']:
            result['baseline_guest_passed']=False
        if result['baseline_guest_passed'] and result['guest_exit_code']==expected_exit and code==expected_exit and not timeout and not result['invoked_stubs'] and not result['unhandled_access_violation']:
            result['status']='passed'
    result['exe_source']=str(args.exe.resolve())
    result['exe_sha256']=hashlib.sha256((data/'console32.exe').read_bytes()).hexdigest()
    if args.fork:
        result['emulator_kind']='local Linux fork'
        result['host']='WSL Ubuntu 22.04 + native glibc + lavapipe'
        result['source_commit_declared']=emulator_manifest['commit']
        result['source_patch_sha256']=emulator_manifest.get('source_patch_sha256')
        result['emulator_sha256']=emulator_manifest['executable_sha256']
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));print('Report:',out/'report.json')
