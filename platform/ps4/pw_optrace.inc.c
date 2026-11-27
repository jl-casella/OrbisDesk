/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include <errno.h>
#include <pthread.h>
#include <stdio.h>
#include <string.h>
#include "pw_optrace.h"
extern uint64_t sceKernelGetProcessTime(void);
extern int pthread_getthreadid_np(void);
static uint64_t pw_op_hz;
static unsigned pw_op_enabled;
static const char *const pw_op_names[PW_OP_COUNT]={"NtReadFile","NtWaitForSingleObject","NtWaitForMultipleObjects","NtDelayExecution","NtYieldExecution","NtQueryPerformanceCounter",
    "NtWaitForAlertByThreadId","NtAlertThreadByThreadId","NtSetEvent","NtResetEvent","NtUserPeekMessage","NtUserMsgWaitForMultipleObjectsEx"};
static __thread struct {
    unsigned busy,wine_tid;
    uint64_t start;
    struct {uint64_t calls,ticks,max,requested,pending,failed,buckets[5];} op[PW_OP_COUNT];
} pw_ops;
static pthread_mutex_t pw_op_budget_lock=PTHREAD_MUTEX_INITIALIZER;
static uint64_t pw_op_budget_start;
static unsigned pw_op_budget_used[PW_OP_COUNT];
static __thread struct {
    uint64_t start;
    struct {uint64_t calls,ticks[PW_READ_STAGES],max,requested,actual,known,pending,failed,async_read,event,apc,completion;} kind[4];
} pw_reads;
#ifndef PW_OPTRACE_READ_TSC
static uint64_t pw_op_read_tsc(void)
{
    unsigned lo,hi;__asm__ volatile("lfence; rdtsc":"=a"(lo),"=d"(hi));return (uint64_t)hi<<32|lo;
}
#define PW_OPTRACE_READ_TSC() pw_op_read_tsc()
#endif
void pw_optrace_configure(uint64_t hz,int enabled)
{
    pw_op_hz=hz;
    __atomic_store_n(&pw_op_enabled,enabled&&hz>=100000000&&hz<=10000000000ull,__ATOMIC_RELEASE);
    if(pw_op_enabled) fprintf(stderr,"PWOP config enabled=%u tsc_hz=%llu clock=kernel-frequency nested=outer-only\n",pw_op_enabled,(unsigned long long)hz);
}
static uint64_t pw_op_us(uint64_t ticks)
{
    return ticks/pw_op_hz*1000000+(ticks%pw_op_hz)*1000000/pw_op_hz;
}
struct pw_opstamp pw_optrace_begin(void)
{
    struct pw_opstamp stamp={0,0};
    if(!__atomic_load_n(&pw_op_enabled,__ATOMIC_ACQUIRE)||pw_ops.busy)return stamp;
    pw_ops.busy=1;stamp.tsc=PW_OPTRACE_READ_TSC();stamp.active=1;
    if(!pw_ops.start)pw_ops.start=stamp.tsc;
    return stamp;
}
struct pw_readstamp pw_readtrace_begin(void)
{
    struct pw_readstamp s={0};
    if(!__atomic_load_n(&pw_op_enabled,__ATOMIC_ACQUIRE))return s;
    s.active=1;s.last=PW_OPTRACE_READ_TSC();
    if(!pw_reads.start)pw_reads.start=s.last;
    return s;
}
void pw_readtrace_stage(struct pw_readstamp *s,unsigned stage)
{
    uint64_t now;
    if(!s->active||stage>=PW_READ_STAGES)return;
    now=PW_OPTRACE_READ_TSC();
    if(now>=s->last)s->ticks[s->stage]+=now-s->last;
    s->last=now;s->stage=stage;
}
static void pw_read_emit(uint64_t now)
{
    static const char *const names[]={"unknown","file","socket","other"};
    if(!pw_reads.start||now<pw_reads.start||now-pw_reads.start<5*pw_op_hz)return;
    for(unsigned i=0;i<4;i++)if(pw_reads.kind[i].calls) {
        fprintf(stderr,"PWREAD window_us=%llu end_us=%llu wine_tid=%04x native_tid=%d kind=%s calls=%llu lookup_us=%llu buffer_us=%llu io_us=%llu completion_us=%llu max_us=%llu requested_bytes=%llu inline_bytes=%llu inline_known=%llu pending=%llu failed=%llu async=%llu event=%llu apc=%llu fd_completion=%llu\n",
            (unsigned long long)pw_op_us(now-pw_reads.start),(unsigned long long)sceKernelGetProcessTime(),pw_ops.wine_tid,pthread_getthreadid_np(),names[i],
            (unsigned long long)pw_reads.kind[i].calls,
            (unsigned long long)pw_op_us(pw_reads.kind[i].ticks[0]),(unsigned long long)pw_op_us(pw_reads.kind[i].ticks[1]),
            (unsigned long long)pw_op_us(pw_reads.kind[i].ticks[2]),(unsigned long long)pw_op_us(pw_reads.kind[i].ticks[3]),
            (unsigned long long)pw_op_us(pw_reads.kind[i].max),(unsigned long long)pw_reads.kind[i].requested,
            (unsigned long long)pw_reads.kind[i].actual,(unsigned long long)pw_reads.kind[i].known,
            (unsigned long long)pw_reads.kind[i].pending,(unsigned long long)pw_reads.kind[i].failed,
            (unsigned long long)pw_reads.kind[i].async_read,(unsigned long long)pw_reads.kind[i].event,
            (unsigned long long)pw_reads.kind[i].apc,(unsigned long long)pw_reads.kind[i].completion);
    }
    memset(pw_reads.kind,0,sizeof(pw_reads.kind));pw_reads.start=now;
}
int32_t pw_readtrace_end(struct pw_readstamp *s,int32_t status,uint64_t requested)
{
    int saved=errno;uint64_t ticks=0;
    if(!s->active)return status;
    pw_readtrace_stage(s,s->stage);
    unsigned k=s->kind<4?s->kind:0;
    pw_reads.kind[k].calls++;pw_reads.kind[k].requested+=requested;
    for(unsigned i=0;i<PW_READ_STAGES;i++){pw_reads.kind[k].ticks[i]+=s->ticks[i];ticks+=s->ticks[i];}
    if(ticks>pw_reads.kind[k].max)pw_reads.kind[k].max=ticks;
    pw_reads.kind[k].actual+=s->actual;pw_reads.kind[k].known+=s->known;
    pw_reads.kind[k].pending+=status==0x103;pw_reads.kind[k].failed+=status<0;
    pw_reads.kind[k].async_read+=s->async_read;pw_reads.kind[k].event+=s->event;
    pw_reads.kind[k].apc+=s->apc;pw_reads.kind[k].completion+=s->completion;
    s->active=0;pw_read_emit(s->last);errno=saved;return status;
}
static int pw_op_slow_token(unsigned op,uint64_t now)
{
    int allow=0;
    /* Diagnostic events never wait on another reporting thread. */
    if(pthread_mutex_trylock(&pw_op_budget_lock))return 0;
    if(!pw_op_budget_start||now<pw_op_budget_start||now-pw_op_budget_start>=5*pw_op_hz) {
        pw_op_budget_start=now;memset(pw_op_budget_used,0,sizeof(pw_op_budget_used));
    }
    if(pw_op_budget_used[op]<8){pw_op_budget_used[op]++;allow=1;}
    pthread_mutex_unlock(&pw_op_budget_lock);return allow;
}
static void pw_op_emit(uint64_t now)
{
    unsigned chosen[PW_OP_COUNT]={0};
    if(!pw_ops.start||now<pw_ops.start||now-pw_ops.start<5*pw_op_hz)return;
    /* At most three operation summaries per thread per five seconds. */
    for(unsigned rank=0;rank<3;rank++) {
        unsigned best=PW_OP_COUNT;
        for(unsigned i=0;i<PW_OP_COUNT;i++)if(!chosen[i]&&pw_ops.op[i].calls&&
            (best==PW_OP_COUNT||pw_ops.op[i].ticks>pw_ops.op[best].ticks))best=i;
        if(best==PW_OP_COUNT)break;
        chosen[best]=1;
        fprintf(stderr,"PWOP window_us=%llu end_us=%llu wine_tid=%04x native_tid=%d op=%s calls=%llu total_us=%llu max_us=%llu requested_bytes=%llu pending=%llu failed=%llu lt50us=%llu lt1ms=%llu lt10ms=%llu lt50ms=%llu ge50ms=%llu\n",
            (unsigned long long)pw_op_us(now-pw_ops.start),(unsigned long long)sceKernelGetProcessTime(),pw_ops.wine_tid,pthread_getthreadid_np(),pw_op_names[best],
            (unsigned long long)pw_ops.op[best].calls,(unsigned long long)pw_op_us(pw_ops.op[best].ticks),(unsigned long long)pw_op_us(pw_ops.op[best].max),
            (unsigned long long)pw_ops.op[best].requested,(unsigned long long)pw_ops.op[best].pending,(unsigned long long)pw_ops.op[best].failed,
            (unsigned long long)pw_ops.op[best].buckets[0],(unsigned long long)pw_ops.op[best].buckets[1],(unsigned long long)pw_ops.op[best].buckets[2],
            (unsigned long long)pw_ops.op[best].buckets[3],(unsigned long long)pw_ops.op[best].buckets[4]);
    }
    memset(pw_ops.op,0,sizeof(pw_ops.op));pw_ops.start=now;
}
void pw_optrace_end(struct pw_opstamp stamp,unsigned op,int32_t status,uint64_t requested)
{
    int saved=errno;uint64_t now,ticks,us;
    if(!stamp.active)return;
    now=PW_OPTRACE_READ_TSC();
    if(op<PW_OP_COUNT&&now>=stamp.tsc) {
        ticks=now-stamp.tsc;us=pw_op_us(ticks);
        pw_ops.op[op].calls++;pw_ops.op[op].ticks+=ticks;
        if(ticks>pw_ops.op[op].max)pw_ops.op[op].max=ticks;
        pw_ops.op[op].requested+=requested;
        pw_ops.op[op].pending+=status==0x103;pw_ops.op[op].failed+=status<0;
        pw_ops.op[op].buckets[us<50?0:us<1000?1:us<10000?2:us<50000?3:4]++;
        if(us>=50000&&pw_op_slow_token(op,now))
            fprintf(stderr,"PWOP slow end_us=%llu wine_tid=%04x native_tid=%d op=%s us=%llu status=%#x requested_bytes=%llu\n",
                (unsigned long long)sceKernelGetProcessTime(),pw_ops.wine_tid,pthread_getthreadid_np(),pw_op_names[op],(unsigned long long)us,(unsigned)status,(unsigned long long)requested);
        pw_op_emit(now);
    }
    pw_ops.busy=0;errno=saved;
}
void pw_optrace_report(unsigned wine_tid)
{
    int saved=errno;
    if(!__atomic_load_n(&pw_op_enabled,__ATOMIC_ACQUIRE)||pw_ops.busy)return;
    pw_ops.busy=1;pw_ops.wine_tid=wine_tid;pw_op_emit(PW_OPTRACE_READ_TSC());pw_read_emit(PW_OPTRACE_READ_TSC());pw_ops.busy=0;errno=saved;
}
