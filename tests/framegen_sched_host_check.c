/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Frame generation's display decisions (platform/ps4/pw_framegen_sched.h) on the host: which game frames show as a
 * generated/real pair and why the others show alone, including warming up, the GPU budget and giving up.
 * Prints one line per case and exits 1 if any check fails. tests/test_framegen_sched_host.py builds and runs it. */
#include <stdio.h>
#include "pw_framegen_sched.h"

static int failures;
static void check(const char *name,int ok,const struct pw_fgd *d)
{
    printf("%-58s %s pairs=%u last=%s gave_up=%d\n",name,ok?"PASS":"FAIL",d->counts[FGD_PAIR],
           pw_fgd_reason_words[d->last_reason],d->gave_up);
    if(!ok) ++failures;
}
/* frames of a game at 30 on a trusted vblank count, steady, ready in time, timed from frame 1 */
static struct pw_fgd_in steady(unsigned frame,unsigned gpu_us)
{
    struct pw_fgd_in in={.cap=2,.vblank_trusted=1,.span=2,.pick=frame?FGD_PICK_READY:FGD_PICK_FIRST,.gpu_us=gpu_us,
                         .timed=frame};
    return in;
}
int main(void)
{
    struct pw_fgd d;struct pw_fgd_in in;int r=0;
    pw_fgd_reset(&d);
    for(unsigned f=0;f<300;f++) {in=steady(f,5000);r=pw_fgd_decide(&d,&in);}
    check("steady 30, 5 ms: pairs after the warm-up",r==FGD_PAIR && d.counts[FGD_PAIR]==300-FGD_WARMUP &&
          d.counts[FGD_WARMING]==FGD_WARMUP-1 && d.counts[FGD_FIRST]==1,&d);

    pw_fgd_reset(&d);
    for(unsigned f=0;f<100;f++) {in=steady(f,5000);in.cap=1;r=pw_fgd_decide(&d,&in);}
    check("cap 60: never a pair",r==FGD_NOT_30 && !d.counts[FGD_PAIR],&d);

    pw_fgd_reset(&d);
    for(unsigned f=0;f<100;f++) {in=steady(f,5000);in.vblank_trusted=0;r=pw_fgd_decide(&d,&in);}
    check("vblank count not trusted: never a pair",r==FGD_NO_VBLANK && !d.counts[FGD_PAIR],&d);

    pw_fgd_reset(&d);
    for(unsigned f=0;f<101;f++) {in=steady(f,5000);if(f%10==9) in.span=3;r=pw_fgd_decide(&d,&in);}
    check("a late frame (span 3) shows alone, the next pairs again",d.counts[FGD_IRREGULAR]==7 && r==FGD_PAIR,&d);

    pw_fgd_reset(&d);
    for(unsigned f=0;f<100;f++) {in=steady(f,5000);if(f==50) in.pick=FGD_PICK_LATE;r=pw_fgd_decide(&d,&in);}
    check("a generation not done in time shows alone",d.counts[FGD_LATE]==1 && r==FGD_PAIR,&d);

    pw_fgd_reset(&d);
    for(unsigned f=0;f<300;f++) {in=steady(f,9500);r=pw_fgd_decide(&d,&in);}
    check("9.5 ms over budget: gives up after 60 frames, stays",d.gave_up && r==FGD_GAVE_UP &&
          d.counts[FGD_SLOW]==FGD_SLOW_FRAMES && !d.counts[FGD_PAIR],&d);

    pw_fgd_reset(&d);
    for(unsigned f=0;f<300;f++) {in=steady(f,(f/40)%2?9500:5000);r=pw_fgd_decide(&d,&in);}
    check("over budget in bursts of 40: no give-up, pairs return",!d.gave_up && d.counts[FGD_PAIR]>100,&d);

    pw_fgd_reset(&d);
    for(unsigned f=0;f<100;f++) {in=steady(f,5000);if(f>=60) in.pick=FGD_PICK_OFF;r=pw_fgd_decide(&d,&in);}
    check("generator off: real frames only",r==FGD_GEN_OFF && d.counts[FGD_GEN_OFF]==40,&d);

    pw_fgd_reset(&d);
    for(unsigned f=0;f<200;f++) {in=steady(f,9500);pw_fgd_decide(&d,&in);}
    pw_fgd_reset(&d);
    for(unsigned f=0;f<100;f++) {in=steady(f,5000);r=pw_fgd_decide(&d,&in);}
    check("reset (another program, the setting changed): tries again",!d.gave_up && r==FGD_PAIR,&d);

    pw_fgd_reset(&d);
    for(unsigned f=0;f<100;f++) {in=steady(f,5000);if(f>=50) in.pick=FGD_PICK_NONE;r=pw_fgd_decide(&d,&in);}
    check("another swapchain followed: alone",r==FGD_NOT_FOLLOWED && d.counts[FGD_NOT_FOLLOWED]==50,&d);

    printf("%s\n",failures?"FAIL":"PASS");
    return failures?1:0;
}
