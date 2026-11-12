#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Build MangoHud Settings (C:\\orbis\\mangohudcfg.exe), the HUD options editor (PE64).

fixtures/win32/mangohudcfg.c is a form for the MangoHud.conf keys that both MangoHud's layer and
the title overlay's Estadisticas HUD (native/hw_overlay.c) read; docs/MANGOHUD_SETTINGS.md says why
it is a small Win32 program and not MangoJuice. Run in WSL Ubuntu-22.04, where the MinGW-w64
compiler build-wine-hardware.py uses for the other C:\\orbis programs is installed. The compiler
package must be the version build-environment.lock.json records. The program is linked twice
into separate directories and must come out identical (no timestamp, no build path in it).
Output: out/mangohudcfg-hw/mangohudcfg.exe and manifest.json, read by build-wine-hardware.py.
It does not write into any directory another builder uses.
"""
import hashlib,json,pathlib,shutil,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
SOURCE=ROOT/'fixtures/win32/mangohudcfg.c'
work=ROOT/'build/mangohudcfg-hw';out=ROOT/'out/mangohudcfg-hw'
COMPILER='x86_64-w64-mingw32-gcc'
# the packages whose files go into the program: the compiler (its libgcc), binutils and the CRT/import libraries
PACKAGES=('gcc-mingw-w64-x86-64','gcc-mingw-w64-x86-64-win32','binutils-mingw-w64-x86-64','mingw-w64-x86-64-dev')
FLAGS=['-O2','-municode','-mwindows','-std=gnu11','-Wall','-Wextra','-Werror','-s','-static-libgcc',
       '-ffile-prefix-map=%s=.'%ROOT,'-Wl,--no-insert-timestamp','-Wl,--build-id=none']
LIBS=['-lcomctl32','-lshell32','-luser32','-lgdi32','-lkernel32']
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()

lock=json.loads((ROOT/'build-environment.lock.json').read_text())['packages']
installed={}
for package in PACKAGES:
    run=subprocess.run(['dpkg-query','-W','-f=${Version}',package],capture_output=True,text=True)
    if run.returncode:raise SystemExit('package not installed: '+package+' (run in WSL Ubuntu-22.04)')
    installed[package]=run.stdout.strip()
if installed['gcc-mingw-w64-x86-64']!=lock['gcc-mingw-w64-x86-64']:
    raise SystemExit('gcc-mingw-w64-x86-64 %s, build-environment.lock.json has %s'%(installed['gcc-mingw-w64-x86-64'],
                                                                                   lock['gcc-mingw-w64-x86-64']))
version=subprocess.check_output([COMPILER,'--version'],text=True).splitlines()[0]
if work.exists():shutil.rmtree(work)
out.mkdir(parents=True,exist_ok=True)
builds=[];commands=[]
for run_name in ('a','b'):
    folder=work/run_name;folder.mkdir(parents=True)
    command=[COMPILER]+FLAGS+['fixtures/win32/mangohudcfg.c','-o',str((folder/'mangohudcfg.exe').relative_to(ROOT))]+LIBS
    result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
    if result.returncode:raise SystemExit(' '.join(command)+'\n'+result.stdout+result.stderr)
    builds.append(folder/'mangohudcfg.exe');commands.append(command)
if sha(builds[0])!=sha(builds[1]):raise SystemExit('the two links differ: the build is not reproducible')
# the DLLs it imports, from objdump: each must be in the PE64 runtime (Wine's own builtins)
dump=subprocess.check_output(['x86_64-w64-mingw32-objdump','-p',str(builds[0])],text=True)
imports=sorted({line.split(':',1)[1].strip().lower() for line in dump.splitlines() if 'DLL Name:' in line})
if not set(imports)<={'comctl32.dll','shell32.dll','user32.dll','gdi32.dll','kernel32.dll','msvcrt.dll'}:
    raise SystemExit('unexpected imports: %r'%imports)
target=out/'mangohudcfg.exe';shutil.copyfile(builds[0],target)
manifest={'schema_version':1,'program':{'path':'mangohudcfg.exe','sha256':sha(target),'bytes':target.stat().st_size,
                                        'target':'C:\\orbis\\mangohudcfg.exe'},
          'source':{'path':'fixtures/win32/mangohudcfg.c','sha256':sha(SOURCE)},
          'compiler':{'version':version,'packages':installed},'commands':commands,'imports':imports,
          'reproducible':'two links identical','builder_sha256':sha(pathlib.Path(__file__))}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'program':str(target.relative_to(ROOT)),'sha256':manifest['program']['sha256'],
                  'bytes':manifest['program']['bytes'],'imports':imports}))
