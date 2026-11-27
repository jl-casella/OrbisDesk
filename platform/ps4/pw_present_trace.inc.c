/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include "pw_present_trace.h"
extern uint64_t sceKernelGetProcessTime(void);
extern int pthread_getthreadid_np(void);
#ifndef PW_PRESENT_CLOCK
#define PW_PRESENT_CLOCK() sceKernelGetProcessTime()
#endif
static __thread struct {
    const void *chain;
    uint64_t previous_return,previous_start,previous_callback,previous_trace,arrival_interval;
    uint64_t window,start,last,outside,stage_us[PW_PRESENT_STAGES];
    unsigned active,stage,known,slow_used;
    struct {uint64_t calls,known,outside,callback,blit,max_outside,max_callback,stage[PW_PRESENT_STAGES];} sum;
} pw_pt;
void pw_present_trace_begin(const void *chain,uint64_t now,int enabled)
{
    if(!enabled){pw_pt.active=0;pw_pt.previous_return=0;pw_pt.window=0;return;}
    if(!pw_pt.window||now<pw_pt.window) {
        pw_pt.window=now;pw_pt.slow_used=0;memset(&pw_pt.sum,0,sizeof(pw_pt.sum));
    }
    pw_pt.known=pw_pt.chain==chain&&pw_pt.previous_return&&now>=pw_pt.previous_return;
    pw_pt.outside=pw_pt.known?now-pw_pt.previous_return:0;
    pw_pt.arrival_interval=pw_pt.known&&now>=pw_pt.previous_start?now-pw_pt.previous_start:0;
    pw_pt.previous_trace=pw_pt.known&&pw_pt.previous_return>=pw_pt.previous_start+pw_pt.previous_callback?
        pw_pt.previous_return-pw_pt.previous_start-pw_pt.previous_callback:0;
    pw_pt.chain=chain;pw_pt.start=pw_pt.last=now;
    pw_pt.stage=PW_PRESENT_LOCK;pw_pt.active=1;memset(pw_pt.stage_us,0,sizeof(pw_pt.stage_us));
}
void pw_present_trace_mark(unsigned stage)
{
    int saved=errno;uint64_t now;
    if(!pw_pt.active||stage>=PW_PRESENT_STAGES)return;
    now=PW_PRESENT_CLOCK();
    if(now<pw_pt.last){pw_pt.active=0;pw_pt.previous_return=0;errno=saved;return;}
    pw_pt.stage_us[pw_pt.stage]+=now-pw_pt.last;pw_pt.last=now;pw_pt.stage=stage;errno=saved;
}
void pw_present_trace_end(uint64_t blit_wait_ns)
{
    int saved=errno,logged=0;uint64_t end,callback;
    if(!pw_pt.active)return;
    pw_present_trace_mark(pw_pt.stage);
    if(!pw_pt.active){errno=saved;return;}
    end=pw_pt.last;callback=end-pw_pt.start;pw_pt.active=0;
    pw_pt.sum.calls++;pw_pt.sum.known+=pw_pt.known;pw_pt.sum.outside+=pw_pt.outside;
    pw_pt.sum.callback+=callback;pw_pt.sum.blit+=blit_wait_ns/1000;
    if(callback>pw_pt.sum.max_callback)pw_pt.sum.max_callback=callback;
    if(pw_pt.outside>pw_pt.sum.max_outside)pw_pt.sum.max_outside=pw_pt.outside;
    for(unsigned i=0;i<PW_PRESENT_STAGES;i++)pw_pt.sum.stage[i]+=pw_pt.stage_us[i];
    if((pw_pt.arrival_interval>=100000||callback>=100000)&&pw_pt.slow_used<8) {
        pw_pt.slow_used++;logged=1;
        fprintf(stderr,"PWPRESENT slow end_us=%llu native_tid=%d outside_known=%u outside_us=%llu callback_us=%llu lock_us=%llu metadata_us=%llu prepare_us=%llu limiter_us=%llu tail_us=%llu blit_us=%llu arrival_interval_us=%llu previous_callback_us=%llu previous_trace_us=%llu\n",
            (unsigned long long)end,pthread_getthreadid_np(),pw_pt.known,(unsigned long long)pw_pt.outside,(unsigned long long)callback,
            (unsigned long long)pw_pt.stage_us[0],(unsigned long long)pw_pt.stage_us[1],(unsigned long long)pw_pt.stage_us[2],
            (unsigned long long)pw_pt.stage_us[3],(unsigned long long)pw_pt.stage_us[4],(unsigned long long)(blit_wait_ns/1000),
            (unsigned long long)pw_pt.arrival_interval,(unsigned long long)(pw_pt.known?pw_pt.previous_callback:0),(unsigned long long)pw_pt.previous_trace);
    }
    if(end>=pw_pt.window&&end-pw_pt.window>=5000000) {
        logged=1;
        fprintf(stderr,"PWPRESENT window_us=%llu end_us=%llu native_tid=%d calls=%llu outside_known=%llu outside_us=%llu callback_us=%llu lock_us=%llu metadata_us=%llu prepare_us=%llu limiter_us=%llu tail_us=%llu blit_us=%llu outside_max_us=%llu callback_max_us=%llu\n",
            (unsigned long long)(end-pw_pt.window),(unsigned long long)end,pthread_getthreadid_np(),
            (unsigned long long)pw_pt.sum.calls,(unsigned long long)pw_pt.sum.known,(unsigned long long)pw_pt.sum.outside,(unsigned long long)pw_pt.sum.callback,
            (unsigned long long)pw_pt.sum.stage[0],(unsigned long long)pw_pt.sum.stage[1],(unsigned long long)pw_pt.sum.stage[2],
            (unsigned long long)pw_pt.sum.stage[3],(unsigned long long)pw_pt.sum.stage[4],(unsigned long long)pw_pt.sum.blit,
            (unsigned long long)pw_pt.sum.max_outside,(unsigned long long)pw_pt.sum.max_callback);
        pw_pt.window=end;pw_pt.slow_used=0;memset(&pw_pt.sum,0,sizeof(pw_pt.sum));
    }
    /* Reporting time is excluded from the next interval outside the callback. */
    pw_pt.previous_return=logged?PW_PRESENT_CLOCK():end;
    pw_pt.previous_start=pw_pt.start;pw_pt.previous_callback=callback;errno=saved;
}
