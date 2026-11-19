/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* FPS LIMIT's decisions (platform/ps4/pw_fps_limit.h) against simulated games on a 60 Hz output, on the host:
 * the sink's hold is modelled as "let go just after the target vblank". Two kinds of game:
 * - synchronous: the next frame takes `work` after the present returns;
 * - queued (as DXVK): a render thread works up to two frames ahead of a presenting thread, so a held present
 *   finds the next frame ready.
 * Prints one line per case and exits 1 if any check fails. tests/test_fps_limit_host.py builds and runs it. */
#include <stdint.h>
#include <stdio.h>
#include "pw_fps_limit.h"

enum {PERIOD=16683,EPS=50};
struct run {unsigned frames,switches;uint64_t at_cap2_us,total_us;unsigned interval_hist[6];int final_cap;
            uint64_t max_interval,min_interval;};

/* setting, a work time that may change at change_us to work2, queued or not, for seconds */
static struct run simulate(int setting,uint64_t work,uint64_t change_us,uint64_t work2,int queued,unsigned seconds)
{
    struct pw_fpsl_auto a={0};struct pw_fpsl_chain c={0};struct run r={0};
    uint64_t end=(uint64_t)seconds*1000000,finish_prev=0,release_prev=0,release_prev2=0,now=0,last_release=0;
    r.min_interval=UINT64_MAX;
    pw_fpsl_setting(&a,setting);
    c.swapchain=&c;
    while(now<end) {
        uint64_t w=now<change_us?work:work2,arrival;
        if(queued) {
            uint64_t start=finish_prev>release_prev2?finish_prev:release_prev2;
            uint64_t finish=start+w;
            arrival=finish>release_prev+EPS?finish:release_prev+EPS;
            finish_prev=finish;
        } else arrival=release_prev+w;
        int was;
        int cap_before=a.cap;
        if(c.release_us && pw_fpsl_auto_frame(&a,arrival,arrival-c.release_us,&was)) ++r.switches;
        int cap=a.cap;
        uint64_t count=arrival/PERIOD,target=pw_fpsl_target_vblank(&c,cap,count),release,release_count;
        if(target) {release=target*PERIOD+EPS;release_count=target;}
        else {release=arrival;release_count=count;}
        if(last_release) {
            uint64_t interval=release-last_release,b=(interval+PERIOD/2)/PERIOD;
            ++r.interval_hist[b<6?b:5];
            if(interval>r.max_interval) r.max_interval=interval;
            if(interval<r.min_interval) r.min_interval=interval;
            if(cap_before==2) r.at_cap2_us+=interval;
            r.total_us+=interval;
        }
        c.release_us=release;c.release_vblank=release_count?release_count:1;
        last_release=release;release_prev2=release_prev;release_prev=release;now=release;++r.frames;
    }
    r.final_cap=a.cap;
    return r;
}
static int failures;
static void check(const char *name,int ok,const struct run *r)
{
    printf("%-44s %s frames=%u switches=%u cap2_share=%.2f final_cap=%d spans=%u,%u,%u,%u,%u,%u min=%llu max=%llu\n",name,
           ok?"PASS":"FAIL",r->frames,r->switches,r->total_us?(double)r->at_cap2_us/r->total_us:0.0,r->final_cap,
           r->interval_hist[0],r->interval_hist[1],r->interval_hist[2],r->interval_hist[3],r->interval_hist[4],
           r->interval_hist[5],(unsigned long long)r->min_interval,(unsigned long long)r->max_interval);
    if(!ok) ++failures;
}
int main(void)
{
    struct run r;
    r=simulate(FPSL_30,5000,UINT64_MAX,0,0,20);
    check("30, fast synchronous game: every 2 vblanks",r.interval_hist[2]>=r.frames-2,&r);
    r=simulate(FPSL_30,5000,UINT64_MAX,0,1,20);
    check("30, fast queued game: every 2 vblanks",r.interval_hist[2]>=r.frames-2,&r);
    r=simulate(FPSL_60,5000,UINT64_MAX,0,0,20);
    check("60, fast synchronous game: every vblank",r.interval_hist[1]>=r.frames-2,&r);
    r=simulate(FPSL_30,40000,UINT64_MAX,0,0,20);
    check("30, slow game (25 FPS): never held",r.min_interval==40000 && r.max_interval==40000,&r);
    r=simulate(FPSL_OFF,7000,UINT64_MAX,0,0,20);
    check("off: never held",r.min_interval==7000 && r.max_interval==7000,&r);
    r=simulate(FPSL_AUTO,10000,UINT64_MAX,0,0,60);
    check("auto, synchronous 100 FPS: stays at 60",r.switches==0 && r.final_cap==1,&r);
    r=simulate(FPSL_AUTO,22000,UINT64_MAX,0,0,60);
    check("auto, synchronous 45 FPS: 30 within 3 s, stays",r.switches==1 && r.final_cap==2 && r.at_cap2_us>=57000000,&r);
    r=simulate(FPSL_AUTO,22000,20000000,10000,0,60);
    check("auto, synchronous 45 then 100 FPS: back to 60",r.switches==2 && r.final_cap==1,&r);
    r=simulate(FPSL_AUTO,22000,UINT64_MAX,0,1,600);
    /* returns after 3, 6, 12, 24, 48, then every 96 windows, each back to 30 after 2: about 10 in 600 s */
    check("auto, queued 45 FPS: mostly 30, returns back off",r.switches<=22 && r.total_us &&
          (double)r.at_cap2_us/r.total_us>=0.95 && r.final_cap==2,&r);
    r=simulate(FPSL_AUTO,12000,UINT64_MAX,0,1,60);
    check("auto, queued 83 FPS: stays at 60",r.switches==0 && r.final_cap==1,&r);
    r=simulate(FPSL_AUTO,17500,UINT64_MAX,0,0,60);
    check("auto, synchronous 57 FPS: stays at 60",r.switches==0 && r.final_cap==1,&r);
    printf("%s\n",failures?"FAIL":"PASS");
    return failures?1:0;
}
