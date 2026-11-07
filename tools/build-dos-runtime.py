#!/usr/bin/env python3
"""Build a pinned DOSBox Pure PE64 core and the GPL Win32 host; no game bundled."""
import pathlib,json,subprocess,shutil,hashlib,tarfile,argparse
parser=argparse.ArgumentParser()
parser.add_argument('--reuse-core',action='store_true',help='Reuse only a core with matching recipe, commit and binary hash')
args=parser.parse_args()
ROOT=pathlib.Path(__file__).resolve().parents[1]
lock=json.loads((ROOT/'dos.lock.json').read_text());source=ROOT/'.deps/dosbox-pure'
commit=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
if commit!=lock['commit']:raise SystemExit('DOSBox Pure revision differs from lock')
if subprocess.check_output(['git','-C',str(source),'status','--porcelain'],text=True).strip():raise SystemExit('DOSBox Pure source dirty')
work=ROOT/'build/dos-runtime'/commit[:12];copy=work/'source';out=ROOT/'out/wine-dos'
work.mkdir(parents=True,exist_ok=True);out.mkdir(parents=True,exist_ok=True)
if not copy.exists():shutil.copytree(source,copy,ignore=shutil.ignore_patterns('.git','build'))
llvm=pathlib.Path.home()/'vk-h0/llvm-mingw/bin'
command=['make','-B','-j12','ISWIN=1','CXX='+str(llvm/'x86_64-w64-mingw32-clang++'),
         'STRIP='+str(llvm/'llvm-strip'),'MAKE_CPUFLAGS=-DDISABLE_DYNAREC=1 -include new',
         'LDFLAGS=-shared -Wl,--gc-sections -static','LDLIBS=-lwinpthread']
if args.reuse_core:
    proof=json.loads((out/'manifest.json').read_text())
    if (proof['commit']!=commit or proof['build_commands']['core']!=command or
        hashlib.sha256((out/'dosbox_pure_libretro.dll').read_bytes()).hexdigest()!=proof['files']['dosbox_pure_libretro.dll']['sha256']):
        raise SystemExit('Cached core differs from its proof; rebuild without --reuse-core')
else:
    with (work/'core-build.log').open('w') as log:subprocess.run(command,cwd=copy,stdout=log,stderr=subprocess.STDOUT,check=True)
    shutil.copy2(copy/'dosbox_pure_libretro.dll',out/'dosbox_pure_libretro.dll')
host_command=['x86_64-w64-mingw32-gcc','-std=c11','-O2','-Wall','-municode','-mwindows',
              '-I'+str(source/'libretro-common/include'),'-I'+str(ROOT/'platform/ps4'),
              str(ROOT/'native/doshost_win32.c'),'-o',str(out/'doshost.exe'),'-luser32','-lgdi32','-lshell32',
              '-Wl,--no-insert-timestamp']
with (work/'host-build.log').open('w') as log:subprocess.run(host_command,stdout=log,stderr=subprocess.STDOUT,check=True)
shutil.copy2(source/'LICENSE',out/'DOSBox-Pure-LICENSE.txt')
readme=f'''OrbisDesk DOS runtime (experimental)\nDOSBox Pure: {lock['repository']}\nRevision: {commit}\nLicense: GPL version 2 or later. Corresponding source and build recipe: DOS-runtime-source.tar.gz.\nDOSBox Pure runs as a PE64 Wine guest. GDI software video; interpreted DOS CPU.\nOnly one DOS host at a time. Keyboard, arrows, Enter/Escape, left click=Space, right click=Ctrl.\nAudio uses the Orbis AudioOut bridge; availability and errors are logged.\nGame modifications use the core's union-drive save overlay under AppData/Local/OrbisDesk/DOS.\nNo games are included.\n'''
(out/'DOS-runtime-README.txt').write_text(readme)
(work/'build-command.json').write_text(json.dumps({'core':command,'host':host_command},indent=2)+'\n')
with tarfile.open(out/'DOS-runtime-source.tar.gz','w:gz') as archive:
    tracked=subprocess.check_output(['git','-C',str(source),'ls-files'],text=True).splitlines()
    for name in tracked:
        if (source/name).is_file():archive.add(source/name,arcname='dosbox-pure/'+name,recursive=False)
    for name in ('native/doshost_win32.c','platform/ps4/pw_dos_audio.h','native/dos_audio.c','tools/build-dos-runtime.py','dos.lock.json'):
        archive.add(ROOT/name,arcname='orbisdesk/'+name,recursive=False)
    archive.add(work/'build-command.json',arcname='build-command.json')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
names=('doshost.exe','dosbox_pure_libretro.dll','DOSBox-Pure-LICENSE.txt','DOS-runtime-README.txt','DOS-runtime-source.tar.gz')
manifest={'repository':lock['repository'],'commit':commit,'license':lock['license'],'build_commands':{'core':command,'host':host_command},
          'files':{name:{'path':name,'sha256':sha(out/name),'bytes':(out/name).stat().st_size} for name in names},
          'host_source_sha256':sha(ROOT/'native/doshost_win32.c'),'audio_abi_sha256':sha(ROOT/'platform/ps4/pw_dos_audio.h'),
          'hardware_validation':'pending','game_included':False,'cpu':'normal interpreter','video':'XRGB8888 software GDI'}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps({n:e['sha256'] for n,e in manifest['files'].items()}))
