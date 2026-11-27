#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise transformed batch housekeeping with the real SPSC framing core."""
import pathlib
import subprocess
import sys
import tempfile

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from wine_vk_batch_hotpath import patch_batch_hotpath
src=ROOT/'upstream/prospero-win/wine/ps5/vulkan'
core=src.parent
text=patch_batch_hotpath((src/'pw_vk_batch_pe.c').read_text())
try:
    patch_batch_hotpath(text)
    raise AssertionError('duplicate patch accepted')
except ValueError:
    pass

def function(name):
    pos=text.index(name+'(')
    start=text.rfind('\n',0,pos)+1
    brace=text.index('{',pos);depth=1;end=brace+1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[start:end]+'\n'

PRELUDE=r'''
#include <assert.h>
#include <pthread.h>
#include <sched.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include "pw_vk_spsc.h"
typedef int32_t LONG;
typedef uint32_t DWORD;
typedef uint64_t UINT64;
typedef int BOOL;
#define FALSE 0
#define TRUE 1
#define TLS_OUT_OF_INDEXES 0xffffffffu
#define PW_VK_BATCH_ARENA 1024u
#define PW_VK_BATCH_SCRATCH 16384u
#define InterlockedCompareExchange(p,v,old) __sync_val_compare_and_swap(p,old,v)
#define InterlockedIncrement(p) __sync_add_and_fetch(p,1)
#define InterlockedDecrement(p) __sync_sub_and_fetch(p,1)
#define InterlockedExchange(p,v) __sync_lock_test_and_set(p,v)
struct producer {struct producer *next;struct pw_vk_spsc stream;LONG retired;unsigned char arena[PW_VK_BATCH_ARENA];};
static struct {struct producer *streams;} registry;
static struct pw_vk_spsc_sequence stream_sequence;
static uint64_t next_replay=1,enqueued_total;
static unsigned char scratch[PW_VK_BATCH_SCRATCH];
static LONG retired_pending;
static UINT64 empty_collect_skips,reclaim_skips,template_skips;
static unsigned locks,frees,created_calls,yields;
static pthread_mutex_t registry_gate=PTHREAD_MUTEX_INITIALIZER,metadata_gate=PTHREAD_MUTEX_INITIALIZER;
static void EnterCriticalSection(pthread_mutex_t *m){locks++;pthread_mutex_lock(m);}
static void LeaveCriticalSection(pthread_mutex_t *m){pthread_mutex_unlock(m);}
static void heap_free(void *p){frees++;free(p);}
static void fatal(void){assert(!"bad stream ordering");abort();}
static void wait_tick(const char *s,struct producer **p,size_t n,uint64_t marker,unsigned *spins,DWORD *start,BOOL *reported){(void)s;(void)p;(void)n;(void)marker;(void)spins;(void)start;(void)reported;}
static DWORD tls=1;
static _Thread_local struct producer *tls_value;
static void *TlsGetValue(DWORD slot){assert(slot==tls);return tls_value;}
static void TlsSetValue(DWORD slot,void *v){assert(slot==tls);tls_value=v;}
static struct producer *unpublished;
static void SwitchToThread(void){
 yields++;assert(unpublished);
 /* Reservation exists but its record is not yet visible. Publish the real
  * framed bytes only after the collector yielded for the missing ticket. */
 atomic_store(&unpublished->stream.write,80);unpublished=NULL;
}
enum {unix_vkCreateDescriptorUpdateTemplate=1,unix_vkCreateDescriptorUpdateTemplateKHR=2,ordinary_command=3};
static void template_created_locked(unsigned code,void *args){assert(args&&code<=2);created_calls++;}
'''
CHECK=r'''
static struct producer *add_producer(void){
 struct producer *p=calloc(1,sizeof(*p));assert(p);
 assert(!pw_vk_spsc_init(&p->stream,p->arena,sizeof(p->arena)));
 p->next=registry.streams;registry.streams=p;return p;
}
static uint64_t ticket(size_t offset){uint64_t v=0;for(unsigned i=0;i<8;i++)v|=(uint64_t)scratch[offset+24+i]<<(i*8);return v;}
static void *retire_concurrently(void *p){tls_value=p;pw_vk_batch_thread_detach();return NULL;}
int main(void){
 size_t bytes=99,records=99;unsigned before;
 pw_vk_spsc_sequence_init(&stream_sequence);
 collect(&bytes,&records);assert(!bytes&&!records&&!locks&&empty_collect_skips==1);
 reclaim();assert(!locks&&reclaim_skips==1);
 int args=1;template_created(ordinary_command,&args);assert(!locks&&!created_calls&&template_skips==1);
 template_created(unix_vkCreateDescriptorUpdateTemplate,&args);
 template_created(unix_vkCreateDescriptorUpdateTemplateKHR,&args);assert(locks==2&&created_calls==2);
 struct producer *a=add_producer(),*b=add_producer();uint32_t payload=7;
 assert(!pw_vk_spsc_append(&stream_sequence,&a->stream,1,&payload,4));
 assert(!pw_vk_spsc_append(&stream_sequence,&b->stream,2,&payload,4));
 assert(!pw_vk_spsc_append(&stream_sequence,&a->stream,3,&payload,4));
 collect(&bytes,&records);assert(records==3&&bytes==120&&next_replay==4&&enqueued_total==3);
 assert(ticket(0)==1&&ticket(40)==2&&ticket(80)==3);
 before=locks;collect(&bytes,&records);assert(!bytes&&!records&&locks==before);
 /* A reserved-but-unpublished ticket must never take the empty shortcut. */
 assert(!pw_vk_spsc_append(&stream_sequence,&b->stream,4,&payload,4));
 uint64_t write=atomic_load(&b->stream.write);assert(write==80);
 atomic_store(&b->stream.write,40);unpublished=b;
 collect(&bytes,&records);assert(records==1&&ticket(0)==4&&yields==1&&next_replay==5);
 /* Counter publication can precede the retire flag; it must not free early. */
 InterlockedIncrement(&retired_pending);before=frees;reclaim();assert(frees==before&&retired_pending==1);
 assert(!pw_vk_spsc_append(&stream_sequence,&a->stream,5,&payload,4));
 InterlockedExchange(&a->retired,1);reclaim();assert(frees==before&&retired_pending==1);
 collect(&bytes,&records);assert(records==1&&ticket(0)==5);
 reclaim();assert(frees==before+1&&!retired_pending&&registry.streams==b&&!b->next);
 tls_value=b;pw_vk_batch_thread_detach();assert(!tls_value&&retired_pending==1&&b->retired);
 pw_vk_batch_thread_detach();assert(retired_pending==1);
 reclaim();assert(!registry.streams&&!retired_pending&&frees==2);
 before=locks;reclaim();assert(locks==before);
 pthread_t threads[8];
 for(unsigned i=0;i<8;i++){struct producer *p=add_producer();assert(!pthread_create(&threads[i],NULL,retire_concurrently,p));}
 while(registry.streams){reclaim();sched_yield();}
 for(unsigned i=0;i<8;i++)pthread_join(threads[i],NULL);
 assert(!retired_pending&&frees==10);
 puts("PASS: empty housekeeping avoids locks; real SPSC order, unpublished gaps, pending retirements and detach publication preserved");
 return 0;
}
'''
with tempfile.TemporaryDirectory() as tmp:
    base=pathlib.Path(tmp)
    code=PRELUDE+''.join(function(n) for n in ('reclaim','producers','collect','pw_vk_batch_thread_detach','template_created'))+CHECK
    (base/'check.c').write_text(code)
    subprocess.run(['cc','-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-pthread',
                    '-I'+str(core),str(base/'check.c'),str(core/'pw_vk_spsc.c'),str(core/'pw_vk_command_stream.c'),'-o',str(base/'check')],check=True)
    subprocess.run([str(base/'check')],check=True,timeout=10)
