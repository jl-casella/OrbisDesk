/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* OrbisDesk W195: the in-process server reaches one thread with a signal (SIGUSR1: suspend,
 * thread context). The console has no tkill or thr_kill2 (W064), but libkernel's pthread_kill
 * signals one thread of this process. The server knows a thread by its kernel id
 * (pthread_getthreadid_np, ntdll's get_unix_tid), so this table maps that id to its pthread_t,
 * as prospero-win's wine/ps5/pw_wine_threads.c (LGPL-2.1+) does. Threads enter the table from
 * pthread_create (linked with --wrap=pthread_create, tools/build-wine-hardware.py) and the main
 * thread from a constructor; a thread leaves it from its key destructor, before it exits. */
#include <errno.h>
#include <pthread.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <stdatomic.h>
#include "pw_thread_quiesce.h"

enum {PW_WINE_THREADS_MAX=1024};
typedef struct Entry {long tid;pthread_t thread;uint64_t token;_Atomic int *quiet;} Entry;
static pthread_mutex_t lock=PTHREAD_MUTEX_INITIALIZER;
static Entry entries[PW_WINE_THREADS_MAX];
static unsigned count;
static pthread_key_t leave_key;
static pthread_once_t key_once=PTHREAD_ONCE_INIT;
static unsigned full_reported,kill_reported,fail_reported;
static uint64_t next_token;
static _Atomic int registry_reliable=1;
static int key_ready;
static _Thread_local _Atomic int this_quiet;

extern int pthread_getthreadid_np(void);       /* libkernel; the SDK has no pthread_np.h */
extern int pw_wine_orbis_signal(int signal);  /* pw_wine_signals.c: SDK (musl) number to the kernel's */
extern int pw_wine_pthread_sigmask(int,const sigset_t *,sigset_t *);

/* A quit handler exits the target pthread. It must not interrupt that thread
 * while it owns the registry mutex, or its leave destructor would deadlock. */
static int thread_lock(sigset_t *previous)
{
    sigset_t set;sigemptyset(&set);sigaddset(&set,SIGQUIT);
    if(pw_wine_pthread_sigmask(SIG_BLOCK,&set,previous)) {registry_reliable=0;return -1;}
    if(pthread_mutex_lock(&lock)) {
        registry_reliable=0;pw_wine_pthread_sigmask(SIG_SETMASK,previous,NULL);return -1;
    }
    return 0;
}
static void thread_unlock(const sigset_t *previous)
{
    pthread_mutex_unlock(&lock);
    if(pw_wine_pthread_sigmask(SIG_SETMASK,previous,NULL))registry_reliable=0;
}

static Entry *find_locked(long tid)
{
    for(unsigned i=0;i<count;i++) if(entries[i].tid==tid) return &entries[i];
    return NULL;
}
static void leave(void *value)
{
    long tid=(long)(intptr_t)value;
    sigset_t previous;if(thread_lock(&previous))return;
    Entry *entry=find_locked(tid);
    if(entry) *entry=entries[--count];
    thread_unlock(&previous);
}
static void make_key(void)
{
    if(pthread_key_create(&leave_key,leave)) {registry_reliable=0;fprintf(stderr,"PWTHREAD key_create failed\n");}
    else key_ready=1;
}
static void enter(void)
{
    long tid=pthread_getthreadid_np();
    int full=0;
    pthread_once(&key_once,make_key);
    if(!key_ready)return;
    sigset_t previous;if(thread_lock(&previous))return;
    Entry *entry=find_locked(tid);
    if(entry) entry->thread=pthread_self();
    else if(count<PW_WINE_THREADS_MAX) {
        if(!++next_token) registry_reliable=0;
        atomic_store(&this_quiet,0);
        entries[count++]=(Entry){tid,pthread_self(),next_token,&this_quiet};
    }
    else {full=1;registry_reliable=0;}
    thread_unlock(&previous);
    if(full) {
        if(full_reported++<8) fprintf(stderr,"PWTHREAD table_full tid=%ld count=%u\n",tid,count);
        return;
    }
    if(pthread_setspecific(leave_key,(void *)(intptr_t)tid)) {
        registry_reliable=0;
        if(!thread_lock(&previous)) {
            Entry *entry=find_locked(tid);if(entry)*entry=entries[--count];
            thread_unlock(&previous);
        }
    }
}
__attribute__((constructor)) static void enter_main(void) {enter();}

/* Called only after Wine has closed its thread channels, immediately before
 * pthread_exit. No PE/guest code or DLL detach runs after this boundary.
 * Lock-free: SIGQUIT may have interrupted code using the registry mutex. */
void pw_wine_thread_quiescent(void) {atomic_store_explicit(&this_quiet,1,memory_order_release);}

/* 0: past the native Wine exit boundary, 1: still active, 2: unknown.
 * Tokens distinguish native thread-id reuse. Never infer quiet from a Wine
 * server handle becoming signalled; the pthread may still be running. */
unsigned pw_wine_thread_query(int pid,long tid,uint64_t *token)
{
    unsigned active=2;
    if(pid!=getpid()||tid<=0)return active;
    sigset_t previous;if(thread_lock(&previous))return active;
    Entry *entry=find_locked(tid);
    if(registry_reliable) {
        if(*token && (!entry||entry->token!=*token))active=0;
        else if(entry) {
            *token=entry->token;
            active=atomic_load_explicit(entry->quiet,memory_order_acquire)?0:1;
        }else active=0;
    }
    thread_unlock(&previous);
    return active;
}

typedef struct Start {void *(*routine)(void *);void *arg;} Start;
static void *start(void *value)
{
    Start start=*(Start *)value;free(value);
    enter();
    return start.routine(start.arg);
}
int __real_pthread_create(pthread_t *thread,const pthread_attr_t *attr,void *(*routine)(void *),void *arg);
int __wrap_pthread_create(pthread_t *thread,const pthread_attr_t *attr,void *(*routine)(void *),void *arg)
{
    Start *value=malloc(sizeof(*value));
    if(!value) return EAGAIN;
    value->routine=routine;value->arg=arg;
    int status=__real_pthread_create(thread,attr,start,value);
    if(status) free(value);
    return status;
}

/* send_thread_signal (server/ptrace.c, tools/build-wine-delete-server.py). The call is made
 * with the table locked: a thread leaves the table before it exits, so a pthread_t found here
 * is a live thread's. Fails with ESRCH for a thread that is not (or no longer) in the table. */
int pw_wine_thread_kill(int pid,long tid,int signal)
{
    int orbis=pw_wine_orbis_signal(signal),status;
    if(pid!=getpid()) {errno=ESRCH;return -1;}
    if(!orbis) {errno=EINVAL;return -1;}
    sigset_t previous;if(thread_lock(&previous)) {errno=ENOSYS;return -1;}
    Entry *entry=find_locked(tid);
    status=!registry_reliable?ENOSYS:entry?pthread_kill(entry->thread,orbis):ESRCH;
    thread_unlock(&previous);
    if(status?fail_reported++<64:kill_reported++<16)
        fprintf(stderr,"PWTHREAD kill tid=%ld sig=%d/%d status=%d\n",tid,signal,orbis,status);
    if(status) {errno=status;return -1;}
    return 0;
}

/* OrbisDesk W278 (W276: NFS Underground 2's threads were to stay on one core, and every request failed with
 * ENOSYS: the SDK's sched_setaffinity is Linux's): set_thread_affinity (server/thread.c,
 * tools/build-wine-delete-server.py) sets one thread's cores through libkernel. A Windows mask's bit i is core i,
 * within the cores this title may use (captured from the first caller, before any thread is narrowed); a mask
 * with none of them fails with EINVAL. */
extern int scePthreadSetaffinity(pthread_t thread,uint64_t mask);
extern void scePthreadGetaffinity(pthread_t thread,uint64_t *mask);  /* the SDK declares it void */

int pw_wine_thread_setaffinity(long tid,unsigned long long mask)
{
    static uint64_t title_cores;
    static unsigned set_reported,set_failed;
    uint64_t cores;
    int rc;
    if(!title_cores) {
        uint64_t current=0;
        scePthreadGetaffinity(pthread_self(),&current);
        title_cores=current&0xff?current&0xff:0x3f;
    }
    cores=mask&title_cores;
    if(!cores) {errno=EINVAL;return -1;}
    sigset_t previous;if(thread_lock(&previous)) {errno=ENOSYS;return -1;}
    Entry *entry=find_locked(tid);
    rc=entry?scePthreadSetaffinity(entry->thread,cores):-1;
    thread_unlock(&previous);
    if(rc?set_failed++<32:(cores!=title_cores&&set_reported++<64))
        fprintf(stderr,"PWTHREAD affinity tid=%ld mask=%llx cores=%llx of %llx rc=%#x found=%d\n",tid,mask,
                (unsigned long long)cores,(unsigned long long)title_cores,(unsigned)rc,entry!=NULL);
    if(!entry) {errno=ESRCH;return -1;}
    if(rc) {errno=EPERM;return -1;}
    return 0;
}
