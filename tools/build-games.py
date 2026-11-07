#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Build the Start menu games (PE64 GUI) for C:\\windows\\system32.

W114. Pinned checkouts in games.lock.json, compiled unchanged with llvm-mingw in WSL:
- ReactOS Solitaire (sol.exe) and Spider Solitaire (spider.exe) with cardlib, and ReactOS
  cards.dll, which cardlib loads at run time. Solitaire and cardlib are public domain,
  Spider is GPL-2.0, cards.dll LGPL-2.1-or-later: source and build commands go in
  games-source.tar.gz. Only ReactOS's version/manifest resource includes are empty stubs.
- SpaceCadetPinball (MIT) with SDL2 and SDL2_mixer (Zlib; WAVE and native MIDI only). The
  game data (PINBALL.DAT, WAV, MID) belongs to Microsoft and is not included: the program
  looks for it next to the exe and in %APPDATA%\\SpaceCadetPinball.
  Built only with --pinball; without it the manifest has no pinball entries.
Output: out/games/ and manifest.json with sha256.
"""
import argparse,hashlib,json,pathlib,shutil,subprocess,tarfile
parser=argparse.ArgumentParser()
parser.add_argument('--pinball',action='store_true',help='Also build SDL2, SDL2_mixer and SpaceCadetPinball')
args=parser.parse_args()
ROOT=pathlib.Path(__file__).resolve().parents[1]
locks=json.loads((ROOT/'games.lock.json').read_text())
def checkout(key):
    lock=locks[key];path=ROOT/lock['checkout']
    commit=subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD'],text=True).strip()
    if commit!=lock['commit']:raise SystemExit(key+' revision differs from games.lock.json')
    if subprocess.check_output(['git','-C',str(path),'status','--porcelain'],text=True).strip():raise SystemExit(key+' checkout dirty')
    return path
source=checkout('reactos');commit=locks['reactos']['commit']
work=ROOT/'build/games'/commit[:12];out=ROOT/'out/games'
(work/'include/reactos').mkdir(parents=True,exist_ok=True);out.mkdir(parents=True,exist_ok=True)
# ReactOS-only resource includes: version block and common-controls manifest. Left empty.
for name in ('version.rc','manifest_exe.rc'):(work/'include/reactos'/name).write_text('/* OrbisDesk: empty stub */\n')
llvm=pathlib.Path.home()/'vk-h0/llvm-mingw/bin'
CXX=str(llvm/'x86_64-w64-mingw32-clang++');CC=str(llvm/'x86_64-w64-mingw32-clang');RC=str(llvm/'x86_64-w64-mingw32-windres')
CARDLIB=source/'sdk/lib/3rdparty/cardlib'
FLAGS=['-O2','-municode','-DUNICODE','-D_UNICODE','-D_WIN32_WINNT=0x0600','-D__REACTOS__','-include','windows.h','-Dmin(a,b)=(((a)<(b))?(a):(b))','-Dmax(a,b)=(((a)>(b))?(a):(b))','-w']
# windows.h first: ReactOS headers include windef/winbase directly, which mingw-w64 does not support;
# min/max as the ReactOS SDK headers define them for C++.
commands=[]
def run(command,cwd=None,log=None):
    commands.append(command)
    result=subprocess.run(command,cwd=cwd,capture_output=True,text=True)
    if log:log.write_text(result.stdout+result.stderr)
    if result.returncode:raise SystemExit(' '.join(command)[:400]+'\n'+(result.stdout+result.stderr)[-4000:])
def objects(sources,includes,name,compiler=CXX,extra=()):
    built=[]
    for src in sources:
        obj=work/name/(src.stem+'.o');obj.parent.mkdir(parents=True,exist_ok=True)
        run([compiler,*FLAGS,*extra,*['-I'+str(i) for i in includes],'-c',str(src),'-o',str(obj)]);built.append(obj)
    return built
def resource(rc,name,defines=()):
    obj=work/name/'rsrc.o'
    run([RC,'--codepage=65001','-I'+str(work/'include'),'-I'+str(rc.parent),*defines,'-DLANGUAGE_EN_US','-DLANGUAGE_ES_ES',
         '-i',str(rc),'-o',str(obj),'-O','coff'],cwd=rc.parent)
    return obj
cardlib=objects(sorted(CARDLIB.glob('*.cpp')),[CARDLIB],'cardlib')
LIBS=['-ladvapi32','-lcomctl32','-lshell32','-luser32','-lgdi32','-lkernel32']
GAMES={'sol.exe':source/'base/applications/games/solitaire','spider.exe':source/'base/applications/games/spider'}
for exe,folder in GAMES.items():
    name=exe[:-4]
    built=objects(sorted(folder.glob('*.cpp')),[CARDLIB,folder],name)+[resource(folder/'rsrc.rc',name)]
    run([CXX,'-municode','-mwindows','-static','-s','-Wl,--no-insert-timestamp',*map(str,built),*map(str,cardlib),*LIBS,'-o',str(out/exe)])
# cards.dll: cdt* entry points that cardlib loads at run time (LoadLibrary("cards.dll")).
cards=source/'dll/win32/cards'
(work/'cards.def').write_text('LIBRARY cards.dll\nEXPORTS\n  WEP\n  cdtAnimate\n  cdtDraw\n  cdtDrawExt\n  cdtInit\n  cdtTerm\n')
built=objects([cards/'cards.c'],[cards],'cards',CC,['-DCARDSTYLE_DEFAULT'])+[resource(cards/'cards.rc','cards',['-DCARDSTYLE_DEFAULT'])]
run([CC,'-shared','-static','-s','-Wl,--no-insert-timestamp',*map(str,built),str(work/'cards.def'),'-luser32','-lgdi32','-o',str(out/'cards.dll')])

# SDL2, SDL2_mixer and SpaceCadetPinball with CMake; one prefix, shared SDL DLLs.
PINBALL=('SpaceCadetPinball.exe','SDL2.dll','SDL2_mixer.dll')
PINBALL_NOTICES=('SpaceCadetPinball-LICENSE.txt','SDL2-LICENSE.txt','SDL2_mixer-LICENSE.txt')
def build_pinball():
    sdl,mixer,pinball=checkout('sdl2'),checkout('sdl2_mixer'),checkout('spacecadetpinball')
    prefix=work/'sdl-prefix';toolchain=work/'llvm-mingw.cmake'
    toolchain.write_text(f'''set(CMAKE_SYSTEM_NAME Windows)\nset(CMAKE_SYSTEM_PROCESSOR x86_64)
set(CMAKE_C_COMPILER {CC})\nset(CMAKE_CXX_COMPILER {CXX})\nset(CMAKE_RC_COMPILER {RC})
set(CMAKE_FIND_ROOT_PATH {prefix})\nset(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)\nset(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)\nset(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)\n''')
    base=['cmake','-G','Ninja','-DCMAKE_TOOLCHAIN_FILE='+str(toolchain),'-DCMAKE_BUILD_TYPE=Release','-DCMAKE_INSTALL_PREFIX='+str(prefix)]
    def cmake(name,src,options):
        build=work/name
        run(base+['-S',str(src),'-B',str(build)]+options,log=work/(name+'-configure.log'))
        run(['cmake','--build',str(build),'-j12'],log=work/(name+'-build.log'))
        return build
    run(['cmake','--install',str(cmake('sdl2',sdl,['-DSDL_SHARED=ON','-DSDL_STATIC=OFF','-DSDL_TEST=OFF']))])
    run(['cmake','--install',str(cmake('sdl2-mixer',mixer,['-DSDL2_DIR='+str(prefix/'lib/cmake/SDL2'),'-DSDL2MIXER_VENDORED=OFF',
        '-DSDL2MIXER_SAMPLES=OFF','-DSDL2MIXER_CMD=OFF','-DSDL2MIXER_FLAC=OFF','-DSDL2MIXER_GME=OFF','-DSDL2MIXER_MOD=OFF',
        '-DSDL2MIXER_MP3=OFF','-DSDL2MIXER_OPUS=OFF','-DSDL2MIXER_VORBIS=','-DSDL2MIXER_WAVPACK=OFF','-DSDL2MIXER_WAVE=ON',
        '-DSDL2MIXER_MIDI=ON','-DSDL2MIXER_MIDI_NATIVE=ON','-DSDL2MIXER_MIDI_TIMIDITY=OFF','-DSDL2MIXER_MIDI_FLUIDSYNTH=OFF']))])
    # The pinball CMakeLists writes bin/ inside its source tree, so it builds from a copy.
    copy=work/'pinball-source'
    shutil.copytree(pinball,copy,ignore=shutil.ignore_patterns('.git'),dirs_exist_ok=True)
    cmake('pinball',copy,['-DSDL2_INCLUDE_DIR='+str(prefix/'include/SDL2'),'-DSDL2_LIBRARY_TEMP='+str(prefix/'lib/libSDL2.dll.a'),
          '-DSDL2_MIXER_INCLUDE_DIR='+str(prefix/'include/SDL2'),'-DSDL2_MIXER_LIBRARY='+str(prefix/'lib/libSDL2_mixer.dll.a'),
          '-DCMAKE_EXE_LINKER_FLAGS=-mwindows -s -Wl,--no-insert-timestamp'])
    shutil.copyfile(copy/'bin/SpaceCadetPinball.exe',out/'SpaceCadetPinball.exe')
    for name in ('SDL2.dll','SDL2_mixer.dll'):
        shutil.copyfile(prefix/'bin'/name,out/name);run([str(llvm/'llvm-strip'),str(out/name)])
    shutil.copyfile(pinball/'LICENSE',out/'SpaceCadetPinball-LICENSE.txt')
    shutil.copyfile(sdl/'LICENSE.txt',out/'SDL2-LICENSE.txt');shutil.copyfile(mixer/'LICENSE.txt',out/'SDL2_mixer-LICENSE.txt')
if args.pinball:build_pinball()

# Licenses, notices and corresponding source.
shutil.copyfile(source/'COPYING',out/'ReactOS-COPYING.txt');shutil.copyfile(source/'COPYING.LIB',out/'ReactOS-COPYING.LIB.txt')
shutil.copyfile(cards/'COPYING',out/'cards-images-COPYING.txt')
(work/'build-commands.json').write_text(json.dumps(commands,indent=2)+'\n')
with tarfile.open(out/'games-source.tar.gz','w:gz') as archive:
    tracked=subprocess.check_output(['git','-C',str(source),'ls-files'],text=True).splitlines()
    for name in tracked:
        if (source/name).is_file():archive.add(source/name,arcname='reactos/'+name,recursive=False)
    for name in ('tools/build-games.py','games.lock.json'):archive.add(ROOT/name,arcname='orbisdesk/'+name,recursive=False)
    archive.add(work/'include',arcname='orbisdesk/stub-include')
    archive.add(work/'build-commands.json',arcname='build-commands.json')
readme=f'''OrbisDesk games
ReactOS {locks['reactos']['repository']} revision {commit}
sol.exe: ReactOS Solitaire (Klondike), public domain (J Brown cardlib example).
spider.exe: ReactOS Spider Solitaire, GPL-2.0 (ReactOS-COPYING.txt).
cards.dll: ReactOS cards, LGPL-2.1-or-later (ReactOS-COPYING.LIB.txt); images: cards-images-COPYING.txt.
Corresponding source and build commands for the ReactOS files: games-source.tar.gz.
'''
if args.pinball:readme+=f'''SpaceCadetPinball.exe: {locks['spacecadetpinball']['repository']} {locks['spacecadetpinball']['commit']}, MIT.
SDL2.dll ({locks['sdl2']['tag']}) and SDL2_mixer.dll ({locks['sdl2_mixer']['tag']}): Zlib.
The 3D Pinball data files (PINBALL.DAT, *.WAV, PINBALL.MID) are not included. Copy them from a
licensed Windows installation to %APPDATA%\SpaceCadetPinball or next to the exe.
'''
(out/'games-README.txt').write_text(readme)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
PROGRAMS=('sol.exe','spider.exe','cards.dll')+(PINBALL if args.pinball else ())
NOTICES=('ReactOS-COPYING.txt','ReactOS-COPYING.LIB.txt','cards-images-COPYING.txt','games-README.txt',
         'games-source.tar.gz')+(PINBALL_NOTICES if args.pinball else ())
used=('reactos','sdl2','sdl2_mixer','spacecadetpinball') if args.pinball else ('reactos',)
licenses=dict(locks['reactos']['licenses'])
if args.pinball:licenses.update({'SpaceCadetPinball.exe':locks['spacecadetpinball']['license'],
                                 'SDL2.dll':locks['sdl2']['license'],'SDL2_mixer.dll':locks['sdl2_mixer']['license']})
manifest={'schema_version':1,'sources':{k:{'repository':locks[k]['repository'],'commit':locks[k]['commit']} for k in used},
          'licenses':licenses,'system32':list(PROGRAMS),'notices':list(NOTICES),'pinball':args.pinball,'game_data_included':False,
          'files':{n:{'path':n,'sha256':sha(out/n),'bytes':(out/n).stat().st_size} for n in PROGRAMS+NOTICES},
          'build_commands':commands,'builder_sha256':sha(pathlib.Path(__file__)),
          'hardware_validation':'pending'}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({n:e['sha256'][:16] for n,e in manifest['files'].items()}))
