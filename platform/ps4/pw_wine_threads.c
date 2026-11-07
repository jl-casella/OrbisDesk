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

enum {PW_WINE_THREADS_MAX=1024};
typedef struct Entry {long tid;pthread_t thread;} Entry;
static pthread_mutex_t lock=PTHREAD_MUTEX_INITIALIZER;
static Entry entries[PW_WINE_THREADS_MAX];
static unsigned count;
static pthread_key_t leave_key;
static pthread_once_t key_once=PTHREAD_ONCE_INIT;
static unsigned full_reported,kill_reported,fail_reported;

extern int pthread_getthreadid_np(void);       /* libkernel; the SDK has no pthread_np.h */
extern int pw_wine_orbis_signal(int signal);  /* pw_wine_signals.c: SDK (musl) number to the kernel's */

static Entry *find_locked(long tid)
{
    for(unsigned i=0;i<count;i++) if(entries[i].tid==tid) return &entries[i];
    return NULL;
}
static void leave(void *value)
{
    long tid=(long)(intptr_t)value;
    pthread_mutex_lock(&lock);
    Entry *entry=find_locked(tid);
    if(entry) *entry=entries[--count];
    pthread_mutex_unlock(&lock);
}
static void make_key(void)
{
    if(pthread_key_create(&leave_key,leave)) fprintf(stderr,"PWTHREAD key_create failed\n");
}
static void enter(void)
{
    long tid=pthread_getthreadid_np();
    int full=0;
    pthread_once(&key_once,make_key);
    pthread_mutex_lock(&lock);
    Entry *entry=find_locked(tid);
    if(entry) entry->thread=pthread_self();
    else if(count<PW_WINE_THREADS_MAX) entries[count++]=(Entry){tid,pthread_self()};
    else full=1;
    pthread_mutex_unlock(&lock);
    if(full) {
        if(full_reported++<8) fprintf(stderr,"PWTHREAD table_full tid=%ld count=%u\n",tid,count);
        return;
    }
    pthread_setspecific(leave_key,(void *)(intptr_t)tid);
}
__attribute__((constructor)) static void enter_main(void) {enter();}

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
    pthread_mutex_lock(&lock);
    Entry *entry=find_locked(tid);
    status=entry?pthread_kill(entry->thread,orbis):ESRCH;
    pthread_mutex_unlock(&lock);
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
    pthread_mutex_lock(&lock);
    Entry *entry=find_locked(tid);
    rc=entry?scePthreadSetaffinity(entry->thread,cores):-1;
    pthread_mutex_unlock(&lock);
    if(rc?set_failed++<32:(cores!=title_cores&&set_reported++<64))
        fprintf(stderr,"PWTHREAD affinity tid=%ld mask=%llx cores=%llx of %llx rc=%#x found=%d\n",tid,mask,
                (unsigned long long)cores,(unsigned long long)title_cores,(unsigned)rc,entry!=NULL);
    if(!entry) {errno=ESRCH;return -1;}
    if(rc) {errno=EPERM;return -1;}
    return 0;
}
