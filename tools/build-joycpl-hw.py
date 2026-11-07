#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Build the hardware joy.cpl (Game Controllers) without the Windows.Gaming.Input tab (W229).

The pinned joy.cpl has four pages: devices, DirectInput test, XInput test and Windows.Gaming.Input.
OrbisDesk does not ship windows.gaming.input.dll, so the last page only showed two lists with
nothing to choose, and since W178 its update read a NULL activation factory (an access violation
in a window callback, then a c0000258 loop). The pad works through XInput, DirectInput and HID.
Method of build-taskmgr-hw.py: the pinned sources are copied to an overlay and revised there; each
object is compiled with the exact command the pinned Wine build uses (make -n), only with the
overlay source and a separate output. wginput.c stays compiled, unused.
Output: out/joycpl-hw/joy.cpl and manifest.json.
"""
import hashlib,json,pathlib,shutil,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
SOURCE=ROOT/'.deps/wine/source';BUILD=ROOT/'.deps/wine/runtime/build'
overlay=ROOT/'.deps/wine/joycpl-hw-overlay';work=ROOT/'build/joycpl-hw';out=ROOT/'out/joycpl-hw'
UNITS=('main',)
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
commit=subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip()
if commit!=json.loads((ROOT/'sources.lock.json').read_text())['sources']['wine']['commit']:
    raise SystemExit('Wine source is not the pinned revision')
if overlay.exists():shutil.rmtree(overlay)
shutil.copytree(SOURCE/'dlls/joy.cpl',overlay)
for folder in (work,out):folder.mkdir(parents=True,exist_ok=True)
revisions=[]
def revise(path,old,new,why):
    target=overlay/path;text=target.read_text()
    if text.count(old)!=1:raise SystemExit('Unexpected context in '+path+': '+old[:60])
    target.write_text(text.replace(old,new));revisions.append({'path':path,'why':why})

revise('main.c','''        {
            .dwSize = sizeof(PROPSHEETPAGEW),
            .hInstance = hcpl,
            .pszTemplate = MAKEINTRESOURCEW( IDD_TEST_WGI ),
            .pfnDlgProc = test_wgi_dialog_proc,
        },
    };''','''        /* OrbisDesk (W229): no Windows.Gaming.Input page; windows.gaming.input.dll is not shipped */
    };''','No Windows.Gaming.Input page.')

# The pinned build's own commands for the joy.cpl objects and link, from make -n.
dry=subprocess.run(['make','-n']+[f'-W../../source/dlls/joy.cpl/{u}.c' for u in UNITS]+
                   ['dlls/joy.cpl/x86_64-windows/joy.cpl'],cwd=BUILD,capture_output=True,text=True,check=True).stdout
dry=dry.replace('\\\n',' ')
commands=[]
for line in dry.splitlines():
    if 'dlls/joy.cpl/' not in line:continue
    for u in UNITS:line=line.replace(f'../../source/dlls/joy.cpl/{u}.c',str(overlay/(u+'.c')))
    # Only the revised unit and the link go to work/; the other objects are the pinned build's.
    for name in [u+'.o' for u in UNITS]+['joy.cpl']:
        line=line.replace('dlls/joy.cpl/x86_64-windows/'+name,str(work/name))
    commands.append(line)
if not all(any(str(overlay/(u+'.c')) in c for c in commands) for u in UNITS) or not any(str(work/'joy.cpl') in c for c in commands):
    raise SystemExit('make -n did not give the joy.cpl commands:\n'+dry[-2000:])
for command in commands:
    run=subprocess.run(command,shell=True,cwd=BUILD,capture_output=True,text=True)
    if run.returncode:raise SystemExit(command[:300]+'\n'+run.stdout+run.stderr)
    if 'warning' in run.stderr:print(run.stderr)
target=out/'joy.cpl';shutil.copyfile(work/'joy.cpl',target)
manifest={'schema_version':1,'wine_commit':commit,'joy.cpl':{'path':'joy.cpl','sha256':sha(target)},
          'revisions':revisions,'commands':commands,'overlay_sha256':{u+'.c':sha(overlay/(u+'.c')) for u in UNITS},
          'builder_sha256':sha(pathlib.Path(__file__))}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'joy.cpl':str(target.relative_to(ROOT)),'sha256':manifest['joy.cpl']['sha256'],'revisions':len(revisions)}))
