/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Frame generation, stage 4 (docs/FRAME_GENERATION.md): whether the sink shows a new game frame as a pair, the
 * generated frame on the next vblank and the real one on the vblank after, or as the real frame alone. Pure logic,
 * no console calls: pw_wine_sink_ps4.c feeds it, tests/framegen_sched_host_check.c simulates it.
 *
 * A pair needs, for that frame:
 * - FPS LIMIT holding the program at 30 (cap 2) on a trusted vblank count, and the frame released exactly two
 *   vblanks after the previous one: then the generated frame takes the vblank between two real frames and the
 *   shown cadence is one frame per vblank;
 * - the generator's copy of this frame, with a generated frame from the previous copy, finished in time;
 * - the generation's GPU time measured over FGD_WARMUP generations, and its average within FGD_BUDGET_US.
 * Anything else shows the real frame alone and names the reason. An average over budget for FGD_SLOW_FRAMES frames
 * in a row gives up: generation stops until the setting or the program changes (pw_fgd_reset), so a GPU that cannot
 * afford it is not charged for frames nobody sees. */
#ifndef PW_FRAMEGEN_SCHED_H
#define PW_FRAMEGEN_SCHED_H

enum {FGD_WARMUP=30,FGD_BUDGET_US=8000,FGD_SLOW_FRAMES=60};
/* the reason a frame shows alone (FGD_PAIR: it does not) */
enum {FGD_PAIR,FGD_NOT_30,FGD_NO_VBLANK,FGD_IRREGULAR,FGD_FIRST,FGD_LATE,FGD_WARMING,FGD_SLOW,FGD_GAVE_UP,FGD_GEN_OFF,
      FGD_NOT_FOLLOWED,FGD_REASONS};
static const char *const pw_fgd_reason_words[FGD_REASONS]={"pair","cap_not_30","vblank_not_trusted","irregular","first",
    "late","warming_up","gpu_over_budget","gave_up","generator_off","not_followed"};
/* pick: what native/hw_sink_gpu/framegen.inc.c pw_sink_gpu_fg_pick answered */
enum {FGD_PICK_OFF=-1,FGD_PICK_NONE=0,FGD_PICK_READY=1,FGD_PICK_LATE=2,FGD_PICK_FIRST=3};
struct pw_fgd_in {int cap,vblank_trusted,span,pick;unsigned gpu_us,timed;};
struct pw_fgd {int showing,gave_up,last_reason;unsigned slow_run,counts[FGD_REASONS];};

static inline void pw_fgd_reset(struct pw_fgd *d)
{
    d->showing=0;d->gave_up=0;d->last_reason=FGD_NOT_30;d->slow_run=0;
    for(int i=0;i<FGD_REASONS;i++) d->counts[i]=0;
}
/* one new game frame: FGD_PAIR or the reason it shows alone; counted */
static inline int pw_fgd_decide(struct pw_fgd *d,const struct pw_fgd_in *in)
{
    int r;
    if(d->gave_up) r=FGD_GAVE_UP;
    else if(in->pick==FGD_PICK_OFF) r=FGD_GEN_OFF;
    else if(in->cap!=2) r=FGD_NOT_30;
    else if(!in->vblank_trusted) r=FGD_NO_VBLANK;
    else if(in->pick==FGD_PICK_NONE) r=FGD_NOT_FOLLOWED;
    else if(in->pick==FGD_PICK_FIRST) r=FGD_FIRST;
    else if(in->timed<FGD_WARMUP) r=FGD_WARMING;
    else if(in->gpu_us>FGD_BUDGET_US) r=FGD_SLOW;
    else if(in->pick==FGD_PICK_LATE) r=FGD_LATE;
    else if(in->span!=2) r=FGD_IRREGULAR;
    else r=FGD_PAIR;
    /* only frames the generator measured count towards giving up */
    if(r==FGD_SLOW) {if(++d->slow_run>=FGD_SLOW_FRAMES) d->gave_up=1;}
    else if(in->timed>=FGD_WARMUP && in->gpu_us<=FGD_BUDGET_US) d->slow_run=0;
    ++d->counts[r];
    d->showing=r==FGD_PAIR;d->last_reason=r;
    return r;
}
#endif
