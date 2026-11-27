#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Pending-alert protocol: production transformed functions, real host contention."""
import ast,pathlib,subprocess,sys,tempfile
r=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(r/'tools'))
from wine_thread_alert import patch_thread_alerts
from wine_thread_alert_pending import patch
tree=ast.parse((r/'tests/test_thread_alert_host.py').read_text());values={}
for node in tree.body:
    if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name) and node.targets[0].id in ('PRELUDE','CHECK'):
        values[node.targets[0].id]=ast.literal_eval(node.value)
source=patch(patch_thread_alerts((r/'.deps/wine/source/dlls/ntdll/unix/sync.c').read_text()))
try:patch(source);raise AssertionError('duplicate patch accepted')
except ValueError:pass
fragment=source[source.index('#ifdef __ORBIS__\n#define pw_wine_thread_alert_report'):]
fragment=fragment[:fragment.index('/***********************************************************************\n *           NtCreateTransaction')]
pre=values['PRELUDE'].replace('typedef uint64_t ULONGLONG;','typedef uint64_t ULONGLONG;\ntypedef int64_t LONGLONG;\nstatic unsigned *script_pending;')
pre=pre.replace('static uint32_t first_timeout;','static uint32_t first_timeout;\nstatic int script_stale;')
pre=pre.replace('if(scripted){assert(us);','if(scripted){assert(us);if(script_stale && calls==1){fake_now+=50;return 0;}')
pre=pre.replace('if(script_alert && calls==2)return 0;','if(script_alert && calls==2){assert(script_pending);__atomic_store_n(script_pending,1,__ATOMIC_SEQ_CST);return 0;}')
check=values['CHECK'].replace('i<4096','i<65536')
check=check.replace('pw_alert_wait(get_tid_alert_entry(ULongToHandle(0x74))->ps4.native,','pw_pending_alert_wait(get_tid_alert_entry(ULongToHandle(0x74))->ps4.native,')
check=check.replace('scripted=1;fake_now=100000000;calls=0;','script_pending=&pw_pending_state(get_tid_alert_entry(ULongToHandle(0x74))->ps4.native)->pending;\n scripted=1;fake_now=100000000;calls=0;')
check=check.replace('set_failure=1;assert(NtAlertThreadByThreadId(ULongToHandle(0x74))==STATUS_INVALID_HANDLE);set_failure=0;',
 '''struct pw_pending_alert *broken=pw_pending_state(get_tid_alert_entry(ULongToHandle(0x78))->ps4.native);
 __atomic_store_n(&broken->waiters,1,__ATOMIC_SEQ_CST);set_failure=1;
 assert(NtAlertThreadByThreadId(ULongToHandle(0x78))==STATUS_INVALID_HANDLE);set_failure=0;
 mock_thread.tid=0x78;assert(NtWaitForAlertByThreadId(NULL,&zero)==STATUS_INVALID_HANDLE);
 mock_thread.tid=0x74;''')
# The wait error is terminal for that entry; use a separate one from later test traffic.
check=check.replace('wait_failure=1;assert(NtWaitForAlertByThreadId(NULL,&zero)==STATUS_INVALID_HANDLE);wait_failure=0;',
 'mock_thread.tid=0x7c;wait_failure=1;assert(NtWaitForAlertByThreadId(NULL,&zero)==STATUS_INVALID_HANDLE);wait_failure=0;mock_thread.tid=0x74;')
check=check.replace('pw_wine_thread_alert_report(0x90);',r'''
 /* A queued alert returns without any kernel wait or set. */
 mock_thread.tid=0x300;unsigned kernel_calls=calls;
 assert(!NtAlertThreadByThreadId(ULongToHandle(0x300)));
 assert(NtWaitForAlertByThreadId(NULL,&zero)==STATUS_ALERTED);assert(calls==kernel_calls);
 /* A stale kernel bit is drained, never fabricated into an NT alert. */
 struct pw_pending_alert *stale=pw_pending_state(get_tid_alert_entry(ULongToHandle(0x300))->ps4.native);
 assert(!sceKernelSetEventFlag(stale->kernel,1));
 assert(NtWaitForAlertByThreadId(NULL,&finite)==STATUS_TIMEOUT);
 /* A stale wake consumes elapsed time, never restarts the relative deadline. */
 scripted=1;script_stale=1;fake_now=100000000;calls=0;finite.QuadPart=-100;
 assert(NtWaitForAlertByThreadId(NULL,&finite)==STATUS_TIMEOUT);
 assert(fake_now==100000100 && calls==2);script_stale=scripted=0;
 assert(pw_pending_stats.fast_waits && pw_pending_stats.skipped_sets && pw_pending_stats.stale_wakes);
 pw_wine_thread_alert_report(0x300);
''')
with tempfile.TemporaryDirectory() as tmp:
    d=pathlib.Path(tmp);(d/'orbis/_types').mkdir(parents=True)
    (d/'orbis/libkernel.h').write_text('''#pragma once
typedef struct _OrbisKernelEventFlag *OrbisKernelEventFlag;
typedef uint32_t OrbisKernelUseconds;
int sceKernelCreateEventFlag(OrbisKernelEventFlag*,const char*,uint32_t,uint64_t,const void*);
int sceKernelDeleteEventFlag(OrbisKernelEventFlag);
int sceKernelSetEventFlag(OrbisKernelEventFlag,uint64_t);
int sceKernelWaitEventFlag(OrbisKernelEventFlag,uint64_t,uint32_t,uint64_t*,uint32_t*);
''')
    (d/'orbis/_types/errors.h').write_text('#pragma once\n#define ORBIS_KERNEL_ERROR_EINTR 0x80020004u\n#define ORBIS_KERNEL_ERROR_ETIMEDOUT 0x8002003cu\n')
    (d/'check.c').write_text(pre+fragment+check)
    subprocess.run(['cc','-D__ORBIS__','-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-fsanitize=undefined','-pthread','-I'+str(d),'-I'+str(r/'platform/ps4'),str(d/'check.c'),'-o',str(d/'check')],check=True)
    subprocess.run([str(d/'check')],check=True,timeout=20)
