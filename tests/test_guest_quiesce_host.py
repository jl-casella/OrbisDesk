#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Real native registry and guest unload guard with modeled Wine ThreadTimes.

Exercises generation reuse and native exit acknowledgement independently of
server handle completion. Does not claim PS4 raw-signal/runtime acceptance.
"""
import pathlib,subprocess,sys,tempfile
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from wine_guest_quiesce import patch_thread
source=(ROOT/'.deps/wine/source/dlls/ntdll/unix/thread.c').read_text()
patched=patch_thread(source)
try:patch_thread(patched)
except ValueError:pass
else:raise AssertionError('duplicate patch accepted')
start=patched.index('#ifdef __ORBIS__\n            /* Private, explicitly tagged')
end=patched.index('#endif',start)+len('#endif')
private=patched[start:end]
N=r'''
#define _GNU_SOURCE
#include <assert.h>
#include <string.h>
#include <sys/syscall.h>
#include <sched.h>
#define __ORBIS__ 1
'''+(ROOT/'platform/ps4/pw_wine_threads.c').read_text()+r'''
int pthread_getthreadid_np(void){return syscall(SYS_gettid);}
int pw_wine_orbis_signal(int sig){return sig;}
int pw_wine_pthread_sigmask(int how,const sigset_t *set,sigset_t *old){return pthread_sigmask(how,set,old);}
int __real_pthread_create(pthread_t *t,const pthread_attr_t *a,void *(*r)(void *),void *p){return pthread_create(t,a,r,p);}
int scePthreadSetaffinity(pthread_t t,uint64_t m){(void)t;(void)m;return 0;}
void scePthreadGetaffinity(pthread_t t,uint64_t *m){(void)t;*m=63;}
typedef struct {int64_t words[4];} KERNEL_USER_TIMES;
#define STATUS_SUCCESS 0
#define min(a,b) ((a)<(b)?(a):(b))
static int query_times(void *data,unsigned length,unsigned *ret_len,int unix_pid,int unix_tid){
 KERNEL_USER_TIMES kusrt={{1,2,3,4}};
'''+private+r'''
 if(data)memcpy(data,&kusrt,min(length,sizeof(kusrt)));
 if(ret_len)*ret_len=min(length,sizeof(kusrt));return 0;
}
static _Atomic int ready,finish;
static _Atomic int quit_hits,usr_hits;
static long worker_tid;
static void quit_model(int sig){(void)sig;atomic_fetch_add(&quit_hits,1);pw_wine_thread_quiescent();pthread_exit(NULL);}
static void usr_model(int sig){(void)sig;atomic_fetch_add(&usr_hits,1);}
static void *holding_registry(void *unused){
 (void)unused;sigset_t previous;assert(!thread_lock(&previous));worker_tid=pthread_getthreadid_np();atomic_store(&ready,1);
 while(!atomic_load(&finish))sched_yield();thread_unlock(&previous);
 for(;;)sched_yield();return NULL;
}
static void *worker(void *unused){
 (void)unused;worker_tid=pthread_getthreadid_np();atomic_store(&ready,1);
 while(!atomic_load(&finish))sched_yield();
 pw_wine_thread_quiescent();
 assert(atomic_load(&this_quiet)==1);return NULL;
}
int main(void){
 assert(sizeof(struct pw_thread_quiet)==48);
 uint64_t token=0;assert(pw_wine_thread_query(getpid(),pthread_getthreadid_np(),&token)==1&&token);
 struct pw_thread_quiet q={0};unsigned received;q.magic=PW_THREAD_QUIET_MAGIC;
 assert(!query_times(&q,sizeof(q),&received,getpid(),pthread_getthreadid_np())&&received==48&&q.active==1&&q.token);
 KERNEL_USER_TIMES times;assert(!query_times(&times,sizeof(times),&received,getpid(),0)&&received==32&&times.words[0]==1);
 q.magic=0;q.active=77;query_times(&q,sizeof(q),&received,getpid(),0);assert(received==32&&q.active==77);
 pthread_t t;assert(!__wrap_pthread_create(&t,NULL,worker,NULL));while(!atomic_load(&ready))sched_yield();
 uint64_t worker_token=0;assert(pw_wine_thread_query(getpid(),worker_tid,&worker_token)==1&&worker_token!=token);
 /* A server-side signalled handle has no effect on this native predicate. */
 assert(pw_wine_thread_query(getpid(),worker_tid,&worker_token)==1);
 atomic_store(&finish,1);pthread_join(t,NULL);assert(!pw_wine_thread_query(getpid(),worker_tid,&worker_token));
 pthread_mutex_lock(&lock);entries[count++]=(Entry){worker_tid,pthread_self(),worker_token+100,&this_quiet};pthread_mutex_unlock(&lock);
 assert(!pw_wine_thread_query(getpid(),worker_tid,&worker_token)); /* tid reused: old token is gone */
 uint64_t new_token=0;assert(pw_wine_thread_query(getpid(),worker_tid,&new_token)==1&&new_token!=worker_token);
 registry_reliable=0;assert(pw_wine_thread_query(getpid(),worker_tid,&new_token)==2);registry_reliable=1;
 assert(pw_wine_thread_query(getpid()+1,worker_tid,&new_token)==2);
 assert(pw_wine_thread_kill(getpid()+1,worker_tid,SIGQUIT)==-1&&errno==ESRCH);
 pthread_mutex_lock(&lock);entries[1]=entries[--count];pthread_mutex_unlock(&lock);
 signal(SIGQUIT,quit_model);signal(SIGUSR1,usr_model);
 /* Deliver a real host pthread signal while the target owns the registry:
  * it stays pending until unlock, then exits through the modeled Wine boundary. */
 for(int i=0;i<16;i++){
  atomic_store(&ready,0);atomic_store(&finish,0);assert(!__wrap_pthread_create(&t,NULL,holding_registry,NULL));
  while(!atomic_load(&ready))sched_yield();assert(!pthread_kill(t,SIGQUIT));usleep(1000);
  assert(atomic_load(&quit_hits)==i);atomic_store(&finish,1);pthread_join(t,NULL);assert(atomic_load(&quit_hits)==i+1);
 }
 atomic_store(&ready,0);atomic_store(&finish,0);assert(!__wrap_pthread_create(&t,NULL,worker,NULL));
 while(!atomic_load(&ready))sched_yield();assert(!pw_wine_thread_kill(getpid(),worker_tid,SIGUSR1));
 for(int i=0;i<10000&&!atomic_load(&usr_hits);i++)sched_yield();assert(atomic_load(&usr_hits)==1);
 atomic_store(&finish,1);pthread_join(t,NULL);
 puts("PASS: actual native registry, exit boundary, ThreadTimes opt-in, server/native distinction, id reuse and unknown refusal");
}
'''
P=r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "pw_thread_quiesce.h"
typedef unsigned DWORD,UINT,ULONG;typedef int BOOL,NTSTATUS;typedef uintptr_t HANDLE;
#define ARRAY_SIZE(a) (sizeof(a)/sizeof(*(a)))
#define TRUE 1
#define FALSE 0
#define ThreadTimes 17
#define ERR(...) ((void)0)
static int ps4_pw_traced(void) {return 1;}
struct ps4_guest {int lock;HANDLE threads[4];UINT thread_count;void *module;};
static unsigned ticks,calls;static int old_native,unknown,error,active_loops;
static DWORD GetTickCount(void){return ticks;}
static DWORD GetCurrentThreadId(void){return 99;}
static DWORD GetThreadId(HANDLE h){return h;}
static void RtlEnterCriticalSection(int *p){(void)p;}
static void RtlLeaveCriticalSection(int *p){(void)p;}
static void Sleep(unsigned ms){ticks+=ms;}
static int NtQueryInformationThread(HANDLE h,int cls,void *data,unsigned length,ULONG *received){
 struct pw_thread_quiet *q=data;calls++;assert(cls==ThreadTimes&&length==48&&q->magic==PW_THREAD_QUIET_MAGIC);
 if(error)return -1;
 if(old_native){*received=32;return 0;}
 *received=48;q->token=100+h;q->active=unknown?2:active_loops-- > 0;return 0;
}
'''+(ROOT/'platform/ps4/pw_guest_quiesce.inc.c').read_text()+r'''
int main(void){
 struct ps4_guest g={0,{1,2,99},3,(void *)1};
 active_loops=4;assert(ps4_guest_native_quiet(&g,2000)&&ticks>0);
 old_native=1;assert(!ps4_guest_native_quiet(&g,2000));old_native=0;
 unknown=1;assert(!ps4_guest_native_quiet(&g,2000));unknown=0;
 error=1;assert(!ps4_guest_native_quiet(&g,2000));error=0;
 active_loops=100000;unsigned before=ticks;assert(!ps4_guest_native_quiet(&g,50)&&ticks-before>=50);
 active_loops=0;assert(ps4_guest_native_quiet(&g,0));
 puts("PASS: actual guest guard waits for native acknowledgement; old/unknown/failing backend and timeout retain mappings");
}
'''
signal_source=(ROOT/'platform/ps4/pw_wine_signals.c').read_text()
begin=signal_source.index('int pw_wine_thread_quit_ready(void)')
brace=signal_source.index('{',begin);end=brace+1;depth=1
while depth:
    depth+=(signal_source[end]=='{')-(signal_source[end]=='}');end+=1
ready_function=signal_source[begin:end].replace('struct sigaction','struct mock_sigaction')
readiness=r'''
typedef void (*PwHandler)(int,void *,void *);
static PwHandler handlers[129],current_handler;
static int raw_mode,read_fail;
struct mock_sigaction {PwHandler __sa_handler;};
static int to_orbis_signal(int sig){return sig;}
static int special(PwHandler p){return (uintptr_t)p<=1;}
static int pw_wine_sigaction(int sig,const void *unused,struct mock_sigaction *old){
 (void)unused;assert(sig==SIGQUIT);old->__sa_handler=current_handler;return read_fail;
}
static void wine_quit(int a,void *b,void *c){(void)a;(void)b;(void)c;}
static void foreign_quit(int a,void *b,void *c){(void)a;(void)b;(void)c;}
'''+ready_function
N=N.replace('int main(void){',readiness+r'''
int main(void){
 handlers[SIGQUIT]=wine_quit;current_handler=wine_quit;assert(!pw_wine_thread_quit_ready());
 raw_mode=1;assert(pw_wine_thread_quit_ready());
 current_handler=NULL;assert(!pw_wine_thread_quit_ready());
 current_handler=(PwHandler)1;assert(!pw_wine_thread_quit_ready());
 current_handler=foreign_quit;assert(!pw_wine_thread_quit_ready());
 current_handler=wine_quit;read_fail=1;assert(!pw_wine_thread_quit_ready());read_fail=0;
''')
with tempfile.TemporaryDirectory() as tmp:
    base=pathlib.Path(tmp)
    for name,code in [('native',N),('guest',P)]:
        path=base/(name+'.c');path.write_text(code)
        subprocess.run(['cc','-std=gnu11','-O1','-g','-Wall','-Wextra','-Wno-unused-parameter','-Wno-misleading-indentation',
                        '-fsanitize=address,undefined','-no-pie','-pthread','-I'+str(ROOT/'platform/ps4'),str(path),'-o',str(base/name)],check=True)
        subprocess.run([str(base/name)],check=True,timeout=15)
