#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compile the real transformed Wine alert functions against a kernel model.

Exercises synchronization semantics, not PS4 kernel compatibility/performance.
"""
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from wine_thread_alert import patch_thread_alerts

source = (ROOT / '.deps/wine/source/dlls/ntdll/unix/sync.c').read_text()
patched = patch_thread_alerts(source)
try:
    patch_thread_alerts(patched)
    raise AssertionError('patch must reject duplicate application')
except ValueError:
    pass
fragment = patched[patched.index('#ifdef __ORBIS__\n#include "pw_wine_thread_alert.inc.c"'):]
fragment = fragment[:fragment.index('/***********************************************************************\n *           NtCreateTransaction')]

PRELUDE = r'''
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>
typedef void *HANDLE;
typedef int32_t LONG, NTSTATUS;
typedef intptr_t LONG_PTR;
typedef uint32_t ULONG;
typedef uint64_t ULONGLONG;
typedef int BOOL;
typedef union { int64_t QuadPart; } LARGE_INTEGER;
#define WINAPI
#define FALSE 0
#define TIMEOUT_INFINITE INT64_MAX
#define STATUS_SUCCESS 0
#define STATUS_ALERTED 0x101
#define STATUS_TIMEOUT 0x102
#define STATUS_INVALID_HANDLE ((NTSTATUS)0xc0000008)
#define STATUS_INVALID_CID ((NTSTATUS)0xc000000b)
#define EVENT_ALL_ACCESS 0
#define SynchronizationEvent 0
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define TRACE(...) ((void)0)
#define FIXME(...) ((void)0)
#define ULongToHandle(v) ((HANDLE)(uintptr_t)(v))
#define InterlockedCompareExchangePointer(p,v,old) __sync_val_compare_and_swap((p),(old),(v))
static unsigned wine_server_obj_handle(HANDLE v) {return (uintptr_t)v;}
static void *anon_mmap_alloc(size_t size,int prot) {return mmap(NULL,size,prot,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);}
static __thread struct {unsigned tid;} mock_thread;
#define get_thread_data() (&mock_thread)
static uint64_t fake_now;
static int scripted, interrupted, creation_failure, set_failure, wait_failure, script_alert;
static unsigned calls, created, destroyed;
static int race_create;
static pthread_barrier_t creation_barrier;
static uint32_t first_timeout;
static void NtQuerySystemTime(LARGE_INTEGER *now) {
 struct timespec ts;clock_gettime(CLOCK_REALTIME,&ts);
 now->QuadPart=scripted ? fake_now : (uint64_t)ts.tv_sec*10000000+ts.tv_nsec/100;
}
struct _OrbisKernelEventFlag {pthread_mutex_t lock;pthread_cond_t cv;int bit;};
#include <orbis/libkernel.h>
#include <orbis/_types/errors.h>
int sceKernelCreateEventFlag(OrbisKernelEventFlag *out,const char *name,uint32_t attr,uint64_t bits,const void *opt) {
 (void)name;(void)opt;assert(attr==0x21 && bits==0);
 if(creation_failure)return -1;
 *out=calloc(1,sizeof(**out));assert(*out);
 pthread_mutex_init(&(*out)->lock,NULL);pthread_cond_init(&(*out)->cv,NULL);
 __sync_fetch_and_add(&created,1);
 if(race_create)pthread_barrier_wait(&creation_barrier);
 return 0;
}
int sceKernelDeleteEventFlag(OrbisKernelEventFlag event) {
 pthread_cond_destroy(&event->cv);pthread_mutex_destroy(&event->lock);free(event);
 __sync_fetch_and_add(&destroyed,1);return 0;
}
int sceKernelSetEventFlag(OrbisKernelEventFlag event,uint64_t bits) {
 assert(bits==1);if(set_failure)return -1;
 pthread_mutex_lock(&event->lock);event->bit=1;pthread_cond_signal(&event->cv);pthread_mutex_unlock(&event->lock);return 0;
}
int sceKernelWaitEventFlag(OrbisKernelEventFlag event,uint64_t bits,uint32_t mode,uint64_t *result,uint32_t *us) {
 assert(bits==1 && mode==0x22 && !result);
 __sync_fetch_and_add(&calls,1);if(wait_failure)return -1;
 if(interrupted){interrupted=0;return ORBIS_KERNEL_ERROR_EINTR;}
 if(scripted){assert(us);if(calls==1)first_timeout=*us;
  if(script_alert && calls==2)return 0;
  fake_now+=(uint64_t)*us*10;return ORBIS_KERNEL_ERROR_ETIMEDOUT;}
 pthread_mutex_lock(&event->lock);
 struct timespec end;clock_gettime(CLOCK_REALTIME,&end);
 if(us){end.tv_sec+=*us/1000000;end.tv_nsec+=(*us%1000000)*1000ull;if(end.tv_nsec>=1000000000){end.tv_nsec-=1000000000;end.tv_sec++;}}
 while(!event->bit){
  int ret=us ? pthread_cond_timedwait(&event->cv,&event->lock,&end) : pthread_cond_wait(&event->cv,&event->lock);
  if(ret==ETIMEDOUT){pthread_mutex_unlock(&event->lock);return ORBIS_KERNEL_ERROR_ETIMEDOUT;}
  assert(!ret);
 }
 event->bit=0;pthread_mutex_unlock(&event->lock);return 0;
}
static unsigned fallback_created, fallback_sets, fallback_waits;
static NTSTATUS NtCreateEvent(HANDLE *out,unsigned access,void *attr,int type,int initial) {
 (void)access;(void)attr;(void)type;assert(!initial);
 fallback_created++;int saved=creation_failure;creation_failure=0;
 int ret=sceKernelCreateEventFlag((OrbisKernelEventFlag*)out,"fallback",0x21,0,NULL);
 creation_failure=saved;return ret;
}
static void NtClose(HANDLE event) {sceKernelDeleteEventFlag(event);}
static NTSTATUS NtSetEvent(HANDLE event,void *unused) {(void)unused;fallback_sets++;return sceKernelSetEventFlag(event,1);}
static NTSTATUS NtWaitForSingleObject(HANDLE event,BOOL alertable,const LARGE_INTEGER *timeout) {
 assert(!alertable);fallback_waits++;
 uint32_t us=0;assert(timeout && !timeout->QuadPart);
 int ret=sceKernelWaitEventFlag(event,1,0x22,NULL,&us);
 return ret ? STATUS_TIMEOUT : STATUS_SUCCESS;
}
NTSTATUS NtAlertThreadByThreadId(HANDLE tid);
'''

CHECK = r'''
static void *waiter(void *unused) {
 (void)unused;mock_thread.tid=0x80;
 assert(NtWaitForAlertByThreadId(NULL,NULL)==STATUS_ALERTED);return NULL;
}
static void *initialize_race(void *unused) {
 (void)unused;assert(get_tid_alert_entry(ULongToHandle(0x100)));return NULL;
}
static void *ping_peer(void *unused) {
 (void)unused;mock_thread.tid=0x204;
 for(unsigned i=0;i<4096;i++){
  assert(NtWaitForAlertByThreadId(NULL,NULL)==STATUS_ALERTED);
  assert(!NtAlertThreadByThreadId(ULongToHandle(0x200)));
 }
 return NULL;
}
int main(void) {
 LARGE_INTEGER zero={.QuadPart=0},finite={.QuadPart=-10000},infinite={.QuadPart=TIMEOUT_INFINITE};
 pw_wine_thread_alert_configure(1,1);mock_thread.tid=0x74;
 assert(!NtAlertThreadByThreadId(ULongToHandle(0x74)));
 assert(!NtAlertThreadByThreadId(ULongToHandle(0x74)));
 assert(NtWaitForAlertByThreadId(NULL,&zero)==STATUS_ALERTED);
 assert(NtWaitForAlertByThreadId(NULL,&zero)==STATUS_TIMEOUT); /* coalesced */
 assert(NtWaitForAlertByThreadId(NULL,&finite)==STATUS_TIMEOUT);
 assert(!NtAlertThreadByThreadId(ULongToHandle(0x74)));
 interrupted=1;assert(NtWaitForAlertByThreadId(NULL,&infinite)==STATUS_ALERTED);
 pthread_t thread;pthread_create(&thread,NULL,waiter,NULL);usleep(10000);
 assert(!NtAlertThreadByThreadId(ULongToHandle(0x80)));pthread_join(thread,NULL);
 /* Long waits are split without truncation or signed overflow. */
 scripted=1;fake_now=100000000;calls=0;
 LARGE_INTEGER long_wait={.QuadPart=-((int64_t)UINT32_MAX+10)*10};
 assert(pw_alert_wait(get_tid_alert_entry(ULongToHandle(0x74))->ps4.native,&long_wait)==STATUS_TIMEOUT);
 assert(calls==2 && first_timeout==UINT32_MAX);
 calls=0;LARGE_INTEGER absolute={.QuadPart=fake_now+101};
 assert(pw_alert_wait(get_tid_alert_entry(ULongToHandle(0x74))->ps4.native,&absolute)==STATUS_TIMEOUT);
 assert(calls==1 && first_timeout==11);
 calls=0;script_alert=1;LARGE_INTEGER largest_relative={.QuadPart=INT64_MIN};
 assert(pw_alert_wait(get_tid_alert_entry(ULongToHandle(0x74))->ps4.native,&largest_relative)==STATUS_ALERTED);
 assert(calls==2 && first_timeout==UINT32_MAX);script_alert=0;
 calls=0;interrupted=1;finite.QuadPart=-100;
 assert(pw_alert_wait(get_tid_alert_entry(ULongToHandle(0x74))->ps4.native,&finite)==STATUS_TIMEOUT);
 assert(calls==2); /* interrupted wait retains its original deadline */
 scripted=0;
 /* Kernel errors remain errors, never successful signals. */
 set_failure=1;assert(NtAlertThreadByThreadId(ULongToHandle(0x74))==STATUS_INVALID_HANDLE);set_failure=0;
 wait_failure=1;assert(NtWaitForAlertByThreadId(NULL,&zero)==STATUS_INVALID_HANDLE);wait_failure=0;
 /* Creation failure pins this entry to the original Wine backend. */
 creation_failure=1;mock_thread.tid=0x90;
 assert(!NtAlertThreadByThreadId(ULongToHandle(0x90)));
 creation_failure=0;
 pw_wine_thread_alert_configure(1,1);
 assert(NtWaitForAlertByThreadId(NULL,&zero)==STATUS_ALERTED);
 assert(fallback_created==1 && fallback_sets==1 && fallback_waits==1);
 assert(!fallback_waits || get_tid_alert_entry(ULongToHandle(0x90))->ps4.native==PW_ALERT_SERVER);
 pw_wine_thread_alert_configure(0,1);
 assert(get_tid_alert_entry(ULongToHandle(0x94))->ps4.native==PW_ALERT_SERVER);
 pw_wine_thread_alert_configure(1,1);
 /* Concurrent publication keeps one event and deletes every losing candidate. */
 unsigned before=created-destroyed, all_created=created;
 pthread_barrier_init(&creation_barrier,NULL,16);race_create=1;
 pthread_t racers[16];for(unsigned i=0;i<16;i++)pthread_create(&racers[i],NULL,initialize_race,NULL);
 for(unsigned i=0;i<16;i++)pthread_join(racers[i],NULL);
 race_create=0;pthread_barrier_destroy(&creation_barrier);
 assert(created-destroyed==before+1 && created-all_created==16);
 mock_thread.tid=0x200;pthread_create(&thread,NULL,ping_peer,NULL);
 for(unsigned i=0;i<4096;i++){
  assert(!NtAlertThreadByThreadId(ULongToHandle(0x204)));
  assert(NtWaitForAlertByThreadId(NULL,NULL)==STATUS_ALERTED);
 }
 pthread_join(thread,NULL);
 HANDLE invalid=ULongToHandle((ARRAY_SIZE(tid_alert_blocks)*TID_ALERT_BLOCK_SIZE+1)*4);
 assert(!is_alert_tid_valid(invalid));assert(!get_tid_alert_entry(invalid));
 pw_wine_thread_alert_report(0x90);
 puts("thread alerts: coalescing, pending/blocked wake, timeout, EINTR, chunks, errors, fallback, initialization race: PASS");
 return 0;
}
'''

with tempfile.TemporaryDirectory() as tmp:
    base = pathlib.Path(tmp)
    (base / 'orbis/_types').mkdir(parents=True)
    (base / 'orbis/libkernel.h').write_text('''#pragma once
typedef struct _OrbisKernelEventFlag *OrbisKernelEventFlag;
typedef uint32_t OrbisKernelUseconds;
int sceKernelCreateEventFlag(OrbisKernelEventFlag*,const char*,uint32_t,uint64_t,const void*);
int sceKernelDeleteEventFlag(OrbisKernelEventFlag);
int sceKernelSetEventFlag(OrbisKernelEventFlag,uint64_t);
int sceKernelWaitEventFlag(OrbisKernelEventFlag,uint64_t,uint32_t,uint64_t*,uint32_t*);
''')
    (base / 'orbis/_types/errors.h').write_text('''#pragma once
#define ORBIS_KERNEL_ERROR_EINTR 0x80020004u
#define ORBIS_KERNEL_ERROR_ETIMEDOUT 0x8002003cu
''')
    (base / 'check.c').write_text(PRELUDE + fragment + CHECK)
    subprocess.run(['cc', '-D__ORBIS__', '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra',
                    '-Werror', '-Wno-unused-parameter', '-fsanitize=undefined', '-pthread',
                    '-I'+str(base), '-I'+str(ROOT / 'platform/ps4'), str(base / 'check.c'),
                    '-o', str(base / 'check')], check=True)
    subprocess.run([str(base / 'check')], check=True, timeout=15)
