#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Build the Start menu games (PE64 GUI) for C:\\windows\\system32.

W114. Pinned checkouts in games.lock.json, compiled unchanged with llvm-mingw in WSL:
- ReactOS Solitaire (sol.exe) and Spider Solitaire (spider.exe) with cardlib, and ReactOS
  cards.dll, which cardlib loads at run time. Solitaire and cardlib are public domain,
  Spider is GPL-2.0, cards.dll LGPL-2.1-or-later: source and build commands go in
  games-source.tar.gz. Only ReactOS's version/manifest resource includes are empty stubs.
Output: out/games/ and manifest.json with sha256.
"""
import argparse,hashlib,json,pathlib,shutil,subprocess,tarfile
parser=argparse.ArgumentParser()
args=parser.parse_args()
ROOT=pathlib.Path(__file__).resolve().parents[1]
# Keep the checkout and $HOME out of __FILE__ strings and debug info.
PREFIX_MAP=['-ffile-prefix-map=%s=.'%ROOT,'-ffile-prefix-map=%s=vk-h0'%(pathlib.Path.home()/'vk-h0')]
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
FLAGS=['-O2','-municode','-DUNICODE','-D_UNICODE','-D_WIN32_WINNT=0x0600','-D__REACTOS__','-include','windows.h','-Dmin(a,b)=(((a)<(b))?(a):(b))','-Dmax(a,b)=(((a)>(b))?(a):(b))','-w',*PREFIX_MAP]
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
(out/'games-README.txt').write_text(readme)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
PROGRAMS=('sol.exe','spider.exe','cards.dll')
NOTICES=('ReactOS-COPYING.txt','ReactOS-COPYING.LIB.txt','cards-images-COPYING.txt','games-README.txt',
         'games-source.tar.gz')
used=('reactos',)
licenses=dict(locks['reactos']['licenses'])
manifest={'schema_version':1,'sources':{k:{'repository':locks[k]['repository'],'commit':locks[k]['commit']} for k in used},
          'licenses':licenses,'system32':list(PROGRAMS),'notices':list(NOTICES),'game_data_included':False,
          'files':{n:{'path':n,'sha256':sha(out/n),'bytes':(out/n).stat().st_size} for n in PROGRAMS+NOTICES},
          'build_commands':commands,'builder_sha256':sha(pathlib.Path(__file__)),
          'hardware_validation':'pending'}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({n:e['sha256'][:16] for n,e in manifest['files'].items()}))
