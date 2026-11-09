#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""W282: winmm.dll (i386 and x86_64) whose timer thread outlives a program that left timers behind.

Programs run as guests of one process (tools/build-guest-hw.py), so winmm and its one timer thread
(TIME_MMSysTimeThread, W281: no guest's thread) stay after a program ends. Need for Speed
Underground 2 ends without timeKillEvent; its periodic timer kept calling into speed2.exe after the
image was unloaded, the timer thread died on the access violation (W281 run-0001.log, thread 007c,
c0000005), and winmm kept TIME_hMMTimer, so no timer of the second start ever fired: no music and no
movie sound. On Windows the process ends with the program and takes its timers along.
Here, before a TIME_CALLBACK_FUNCTION timer is called, its function must lie in committed executable
memory; when it does not, the timer is removed with ERR "PWMMTIMER". A callback that faults is caught,
traced the same way and removed, and the thread goes on. Timers of live programs are untouched.
The overlay comes from the pinned time.c (sha256); the other objects, resources and the link come from
the host tree with the recipes of its Makefile (make -n dlls/winmm/all).
Output: out/winmm-hw/{i386-windows,x86_64-windows}/winmm.dll and manifest.json.
"""
import hashlib,json,pathlib,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
# Keep the checkout and $HOME out of __FILE__ strings and debug info.
PREFIX_MAP=['-ffile-prefix-map=%s=.'%ROOT,'-ffile-prefix-map=%s=vk-h0'%(pathlib.Path.home()/'vk-h0')]
SOURCE=ROOT/'.deps/wine/source';BUILD=ROOT/'.deps/wine/runtime/build'
work=ROOT/'build/winmm-hw';out=ROOT/'out/winmm-hw'
ARCHES={'i386-windows':'i686-w64-mingw32','x86_64-windows':'x86_64-w64-mingw32'}
for path in (work,*[work/a for a in ARCHES],*[out/a for a in ARCHES]):path.mkdir(parents=True,exist_ok=True)
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def run(command):
    with (work/'build.log').open('a') as log:
        log.write('$ '+' '.join(map(str,command))+'\n');log.flush()
        subprocess.run(list(map(str,command)),cwd=BUILD,check=True,stdout=log,stderr=subprocess.STDOUT)
(work/'build.log').write_text('')
commit=subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip()
if commit!=json.loads((ROOT/'sources.lock.json').read_text())['sources']['wine']['commit']:
    raise SystemExit('winmm requires the pinned Wine revision')
PINNED={'dlls/winmm/time.c':'01b5b4fcee2f5ff3ee98acf9042ab68153b76ab8b3a8f9341bb166a1dd5fccd9',
        'dlls/winmm/winmm.spec':'8139149e997e90aad0a0bdab62eb7b38da46c029f840d395e253128c996def4f'}
for name,digest in PINNED.items():
    if sha(SOURCE/name)!=digest:raise SystemExit('unexpected source: '+name)

text=(SOURCE/'dlls/winmm/time.c').read_text()
def change(old,new):
    global text
    if text.count(old)!=1:raise SystemExit('time.c: context found %d times: %s'%(text.count(old),old[:60]))
    text=text.replace(old,new)
change('''#include "wine/debug.h"
''','''#include "wine/debug.h"
#include "wine/exception.h"
''')
change('''/**************************************************************************
 *           TIME_MMSysTimeCallback
 */''','''/* W282: a timer function that is no longer in committed executable memory (its program ended
 * and its image went away while winmm stayed) */
static BOOL pw_timer_func_gone(LPTIMECALLBACK func)
{
    MEMORY_BASIC_INFORMATION info;

    if (!VirtualQuery(func, &info, sizeof(info))) return TRUE;
    return info.State != MEM_COMMIT ||
           !(info.Protect & (PAGE_EXECUTE | PAGE_EXECUTE_READ | PAGE_EXECUTE_READWRITE | PAGE_EXECUTE_WRITECOPY));
}

/* W282: a callback that faults is caught; the caller removes its timer */
static BOOL pw_timer_call(LPTIMECALLBACK func, UINT16 id, DWORD_PTR user)
{
    BOOL ok = TRUE;

    __TRY
    {
        func(id, 0, user, 0, 0);
    }
    __EXCEPT_ALL
    {
        ERR("PWMMTIMER timer %u function %p faulted (code %#lx); the timer is removed\\n", id, func, GetExceptionCode());
        ok = FALSE;
    }
    __ENDTRY
    return ok;
}

/**************************************************************************
 *           TIME_MMSysTimeCallback
 */''')
change('''                LPTIMECALLBACK func = timer->lpFunc;

                if (flags & TIME_KILL_SYNCHRONOUS) EnterCriticalSection(&TIME_cbcrst);
                LeaveCriticalSection(&WINMM_cs);

                func(id, 0, user, 0, 0);

                EnterCriticalSection(&WINMM_cs);
                if (flags & TIME_KILL_SYNCHRONOUS) LeaveCriticalSection(&TIME_cbcrst);
                if (id != timer->wTimerID) timer = NULL;''','''                LPTIMECALLBACK func = timer->lpFunc;
                BOOL ok;

                if (pw_timer_func_gone(func))
                {
                    ERR("PWMMTIMER timer %u function %p is no longer mapped executable; the timer is removed\\n", id, func);
                    timer->wTimerID = 0;
                    continue;
                }
                if (flags & TIME_KILL_SYNCHRONOUS) EnterCriticalSection(&TIME_cbcrst);
                LeaveCriticalSection(&WINMM_cs);

                ok = pw_timer_call(func, id, user);

                EnterCriticalSection(&WINMM_cs);
                if (flags & TIME_KILL_SYNCHRONOUS) LeaveCriticalSection(&TIME_cbcrst);
                if (!ok && id == timer->wTimerID) timer->wTimerID = 0;
                if (id != timer->wTimerID) timer = NULL;''')
time_c=work/'time.c';time_c.write_text(text)

src='../../source'
common=['-Idlls/winmm','-I'+src+'/dlls/winmm','-Iinclude','-I'+src+'/include','-I'+src+'/include/msvcrt','-D_UCRT',
        '-D__WINESRC__','-D_WINMM_','-D__WINE_PE_BUILD','-Wall','-fno-strict-aliasing','-Wempty-body','-Wignored-qualifiers',
        '-Winit-self','-Wno-packed-not-aligned','-Wshift-overflow=2','-Wtype-limits','-Wunused-but-set-parameter',
        '-Wvla','-Wwrite-strings','-Wpointer-arith','-Wlogical-op','-ffunction-sections']
arch_flags={'i386-windows':['-fno-omit-frame-pointer','-mpreferred-stack-boundary=2','-mlong-double-64','-msse2'],
            'x86_64-windows':['-Wformat-overflow','-Wnonnull','-mlong-double-64','-mcx16','-mcmodel=small']}
link_tail={'i386-windows':['-Wl,--disable-stdcall-fixup','-Wl,--build-id'],'x86_64-windows':['-Wl,--build-id']}
tail=['-gdwarf-4','-Wdeclaration-after-statement','-Wstrict-prototypes','-Wabsolute-value','-g','-O2',*PREFIX_MAP]
resources=[BUILD/'dlls/winmm/winmm.res',BUILD/'dlls/winmm/winmm_res.res']
modules={}
for arch,triple in ARCHES.items():
    obj=work/arch/'time.o'
    run([triple+'-gcc','-c','-o',obj,time_c,*common,*arch_flags[arch],*tail])
    host=[BUILD/'dlls/winmm'/arch/(n+'.o') for n in ('driver','joystick','lolvldrv','mci','mmio','playsound')]
    host_after=[BUILD/'dlls/winmm'/arch/(n+'.o') for n in ('waveform','winmm')]
    libs=[BUILD/p.format(arch) for p in ('libs/uuid/{}/libuuid.a','dlls/user32/{}/libuser32.a','dlls/advapi32/{}/libadvapi32.a',
          'dlls/ole32/{}/libole32.a','dlls/msacm32/{}/libmsacm32.a','dlls/dinput8/{}/libdinput8.delay.a',
          'libs/winecrt0/{}/libwinecrt0.a','libs/compiler-rt/{}/libcompiler-rt.a','dlls/ucrtbase/{}/libucrtbase.a',
          'dlls/kernel32/{}/libkernel32.a','dlls/ntdll/{}/libntdll.a')]
    for path in (*host,*host_after,*resources,*libs):
        if not path.is_file():raise SystemExit('missing input: '+str(path))
    dll=out/arch/'winmm.dll'
    run(['tools/winegcc/winegcc','-o',dll,'--wine-objdir','.','--cc-cmd='+triple+'-gcc','-b',triple,
         '-Wl,--wine-builtin','-shared',src+'/dlls/winmm/winmm.spec',*host,obj,*host_after,*resources,*libs,*link_tail[arch]])
    modules[arch]={'path':arch+'/winmm.dll','sha256':sha(dll),'host_original_sha256':sha(BUILD/'dlls/winmm'/arch/'winmm.dll')}
manifest={'schema_version':1,'wine_commit':commit,'builder_sha256':sha(pathlib.Path(__file__)),
          'sources':PINNED,'overlays':{'time.c':sha(time_c)},
          'source_change':'a TIME_CALLBACK_FUNCTION timer whose function is not committed executable memory, or '
                          'whose call faults, is removed with ERR "PWMMTIMER"; the timer thread goes on',
          'modules':modules}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(modules,indent=2))
