#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Build the hardware variant of Wine's taskmgr.exe (PE64).

W112. Same method as build-explorer-hw.py: the pinned sources are copied to an overlay and
revised there; each object is compiled with the exact command the pinned Wine build uses
(taken from `make -n`), only with the overlay source and a separate output.
"""
import hashlib,json,pathlib,shutil,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
SOURCE=ROOT/'.deps/wine/source';BUILD=ROOT/'.deps/wine/runtime/build'
overlay=ROOT/'.deps/wine/taskmgr-hw-overlay';work=ROOT/'build/taskmgr-hw';out=ROOT/'out/taskmgr-hw'
UNITS=('applpage','perfdata')
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
commit=subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip()
if commit!=json.loads((ROOT/'sources.lock.json').read_text())['sources']['wine']['commit']:
    raise SystemExit('Wine source is not the pinned revision')
if overlay.exists():shutil.rmtree(overlay)
shutil.copytree(SOURCE/'programs/taskmgr',overlay)
for folder in (work,out):folder.mkdir(parents=True,exist_ok=True)
revisions=[]
def revise(path,old,new,why):
    target=overlay/path;text=target.read_text()
    if text.count(old)!=1:raise SystemExit('Unexpected context in '+path+': '+old[:60])
    target.write_text(text.replace(old,new));revisions.append({'path':path,'why':why})

# Applications: dead rows were only removed while another qualifying window was enumerated.
# After End task on the only application nothing called AddOrUpdateHwnd and the row stayed.
revise('applpage.c','''    BOOL                            bAlreadyInList = FALSE;
    BOOL                            bItemRemoved = FALSE;
''','''    BOOL                            bAlreadyInList = FALSE;
''','Removal moves to ApplicationPageRemoveDead.')
revise('applpage.c','''        SendMessageW(hApplicationPageListCtrl, LVM_INSERTITEMW, 0, (LPARAM) &item);
    }


    /* Check to see if we need to remove any items from the list */''','''        SendMessageW(hApplicationPageListCtrl, LVM_INSERTITEMW, 0, (LPARAM) &item);
    }

    ApplicationPageUpdate();
}

/* OrbisDesk: run after every enumeration, also when no window was enumerated. */
static void ApplicationPageRemoveDead(void)
{
    LPAPPLICATION_PAGE_LIST_ITEM    pAPLI;
    HIMAGELIST                      hImageListLarge;
    HIMAGELIST                      hImageListSmall;
    LV_ITEMW                        item;
    int                             i, count;
    BOOL                            bItemRemoved = FALSE;

    hImageListLarge = (HIMAGELIST)SendMessageW(hApplicationPageListCtrl, LVM_GETIMAGELIST, LVSIL_NORMAL, 0);
    hImageListSmall = (HIMAGELIST)SendMessageW(hApplicationPageListCtrl, LVM_GETIMAGELIST, LVSIL_SMALL, 0);

    /* Check to see if we need to remove any items from the list */''','Dead-row pass as its own function.')
revise('applpage.c','''            (GetWindowLongW(hWnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW))
        {
            ImageList_Remove''','''            (GetWindowLongW(pAPLI->hWnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW))
        {
            ImageList_Remove''','Test the listed window, not the enumerated one.')
revise('applpage.c','''            EnumWindows(EnumWindowsProc, 0);
''','''            EnumWindows(EnumWindowsProc, 0);
            ApplicationPageRemoveDead();
''','Remove closed windows after each refresh.')

# Performance/Processes: trace each failing query; never walk a buffer a failed query left.
revise('perfdata.c','''#include "taskmgr.h"
#include "perfdata.h"
''','''#include "taskmgr.h"
#include "perfdata.h"
#include "wine/debug.h"

WINE_DEFAULT_DEBUG_CHANNEL(taskmgr);
''','Debug channel for PWTASK traces.')
for name,old in (('SystemTimeOfDayInformation','''    status = NtQuerySystemInformation(SystemTimeOfDayInformation, &SysTimeInfo, sizeof(SysTimeInfo), 0);
    if (status != NO_ERROR)
        return;'''),('SystemPerformanceInformation','''    status = NtQuerySystemInformation(SystemPerformanceInformation, &SysPerfInfo, sizeof(SysPerfInfo), NULL);
    if (status != NO_ERROR)
        return;'''),('SystemFileCacheInformation','''    status = NtQuerySystemInformation(SystemFileCacheInformation, &SysCacheInfo, sizeof(SysCacheInfo), NULL);
    if (status != NO_ERROR)
        return;''')):
    revise('perfdata.c',old,old.replace('        return;','''    {
        ERR("PWTASK %s status %08lx\\n", "'''+name+'''", status);
        return;
    }'''),'Trace '+name+' failure.')
revise('perfdata.c','''    if (status != NO_ERROR) {
        HeapFree(GetProcessHeap(), 0, SysProcessorTimeInfo);
        return;
    }''','''    if (status != NO_ERROR) {
        ERR("PWTASK SystemProcessorPerformanceInformation status %08lx\\n", status);
        HeapFree(GetProcessHeap(), 0, SysProcessorTimeInfo);
        return;
    }''','Trace processor time failure.')
revise('perfdata.c','''    } while (status == 0xC0000004 /*STATUS_INFO_LENGTH_MISMATCH*/);

    /* Get process information''','''    } while (status == 0xC0000004 /*STATUS_INFO_LENGTH_MISMATCH*/);
    if (status != NO_ERROR) {
        ERR("PWTASK SystemHandleInformation status %08lx\\n", status);
        HeapFree(GetProcessHeap(), 0, SysHandleInfoData);
        HeapFree(GetProcessHeap(), 0, SysProcessorTimeInfo);
        return;
    }

    /* Get process information''','Do not use a handle buffer from a failed query.')
revise('perfdata.c','''    } while (status == 0xC0000004 /*STATUS_INFO_LENGTH_MISMATCH*/);

    EnterCriticalSection(&PerfDataCriticalSection);''','''    } while (status == 0xC0000004 /*STATUS_INFO_LENGTH_MISMATCH*/);
    if (status != NO_ERROR) {
        ERR("PWTASK SystemProcessInformation status %08lx\\n", status);
        HeapFree(GetProcessHeap(), 0, pBuffer);
        HeapFree(GetProcessHeap(), 0, SysHandleInfoData);
        HeapFree(GetProcessHeap(), 0, SysProcessorTimeInfo);
        return;
    }

    EnterCriticalSection(&PerfDataCriticalSection);''','Do not walk a process buffer from a failed query.')

# The pinned build's own commands for the taskmgr objects and link, from make -n.
dry=subprocess.run(['make','-n']+[f'-W../../source/programs/taskmgr/{u}.c' for u in UNITS]+
                   ['programs/taskmgr/x86_64-windows/taskmgr.exe'],cwd=BUILD,capture_output=True,text=True,check=True).stdout
dry=dry.replace('\\\n',' ')
commands=[]
for line in dry.splitlines():
    if 'programs/taskmgr/' not in line:continue
    for u in UNITS:line=line.replace(f'../../source/programs/taskmgr/{u}.c',str(overlay/(u+'.c')))
    # Only the revised units and the link go to work/; the other objects are the pinned build's.
    for name in [u+'.o' for u in UNITS]+['taskmgr.exe']:
        line=line.replace('programs/taskmgr/x86_64-windows/'+name,str(work/name))
    commands.append(line)
if not all(any(str(overlay/(u+'.c')) in c for c in commands) for u in UNITS) or not any(str(work/'taskmgr.exe') in c for c in commands):
    raise SystemExit('make -n did not give the taskmgr commands:\n'+dry[-2000:])
for command in commands:
    run=subprocess.run(command,shell=True,cwd=BUILD,capture_output=True,text=True)
    if run.returncode:raise SystemExit(command[:300]+'\n'+run.stdout+run.stderr)
    if 'warning' in run.stderr:print(run.stderr)
target=out/'taskmgr.exe';shutil.copyfile(work/'taskmgr.exe',target)
manifest={'schema_version':1,'wine_commit':commit,'taskmgr':{'path':'taskmgr.exe','sha256':sha(target)},
          'revisions':revisions,'commands':commands,
          'overlay_sha256':{u+'.c':sha(overlay/(u+'.c')) for u in UNITS},
          'builder_sha256':sha(pathlib.Path(__file__))}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'taskmgr':str(target.relative_to(ROOT)),'sha256':manifest['taskmgr']['sha256'],'revisions':len(revisions)}))
