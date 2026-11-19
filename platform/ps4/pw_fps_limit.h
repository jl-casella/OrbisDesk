/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* The overlay's FPS LIMIT (native/hw_overlay.c, docs/FPS_LIMIT.md): the decisions, without the console. The sink
 * (platform/ps4/pw_wine_sink_ps4.c) calls these from the thread that presents a Vulkan swapchain, before that present
 * returns, and holds the thread until the vblank they name; tests/fps_limit_host_check.c runs them on the host.
 *
 * Pacing is in vblanks: a cap of 2 lets a present go on the second vblank after the one the previous present of
 * the same swapchain was let go on (30 FPS at 60 Hz), a cap of 1 on the next one (60 FPS). A present that comes
 * later than that is let go at once and starts the count again: nothing is held for a frame that is late, nothing
 * is dropped, nothing is made up.
 *
 * Auto starts at a cap of 1 and measures, over windows of about a second, how fast the game could present without
 * the hold: frames divided by the time the game itself spent on them (from the release of one present to the
 * arrival of the next). Two windows in a row below 52 FPS set a cap of 2; while at 2, enough windows in a row at or
 * above 57 FPS set 1 again. A game that hands frames to a presenting thread (DXVK) has its next frame ready when the
 * hold ends, so its time looks short and Auto goes back to 1; if it then cannot keep 57, the windows below 52 bring
 * the cap back to 2. Each such failed return doubles the windows asked for the next one (3, 6, 12, ... up to 96);
 * a return that holds for FPSL_SETTLE windows sets it back to 3. */
#ifndef PW_FPS_LIMIT_H
#define PW_FPS_LIMIT_H
#include <stdint.h>
#include <string.h>

enum {FPSL_OFF=0,FPSL_30=30,FPSL_60=60,FPSL_AUTO=-1};
enum {FPSL_WINDOW_US=1000000,FPSL_LOW_X10=520,FPSL_HIGH_X10=570,FPSL_LOW_WINDOWS=2,FPSL_HIGH_WINDOWS=3,
      FPSL_HIGH_WINDOWS_MAX=96,FPSL_SETTLE=10,FPSL_WORK_MAX_US=250000};

/* Auto's state, one per run of a setting (all swapchains together) */
struct pw_fpsl_auto {
    int setting;                  /* the overlay's value it was made for */
    int cap;                      /* vblanks per frame now: 1 or 2 (0 for Off) */
    uint64_t window_us;           /* start of the current window, 0 none yet */
    unsigned frames;              /* presents in the window */
    uint64_t work_us;             /* their time without the hold */
    int low,high;                 /* windows in a row below FPSL_LOW_X10 / at or above FPSL_HIGH_X10 */
    int high_needed;              /* windows in a row at or above FPSL_HIGH_X10 to set a cap of 1 */
    int since_switch;             /* windows since the cap last changed */
    int returned;                 /* the cap of 1 in force came from a return (2 to 1), not from the start */
    unsigned last_potential_x10;  /* the last window's figure, for the log */
};
/* one swapchain's pacing */
struct pw_fpsl_chain {
    const void *swapchain;
    uint64_t release_us;          /* when its last present was let go, 0 none yet */
    uint64_t release_vblank;      /* the vblank count then, 0 unknown */
};

/* the cap a fixed setting asks for */
static inline int pw_fpsl_fixed_cap(int setting)
{
    return setting==FPSL_30?2:setting==FPSL_60?1:0;
}
/* the setting may have changed: Auto starts again at a cap of 1; returns 1 when it was reset */
static inline int pw_fpsl_setting(struct pw_fpsl_auto *a,int setting)
{
    if(a->setting==setting && (a->cap || setting==FPSL_OFF)) return 0;
    memset(a,0,sizeof(*a));
    a->setting=setting;
    a->cap=setting==FPSL_AUTO?1:pw_fpsl_fixed_cap(setting);
    a->high_needed=FPSL_HIGH_WINDOWS;
    return 1;
}
/* a present arrived at now_us, work_us after its swapchain's last release (the caller skips a swapchain's first
 * present, which has none). Auto only. Returns 1 when the cap changed (old cap in *was). */
static inline int pw_fpsl_auto_frame(struct pw_fpsl_auto *a,uint64_t now_us,uint64_t work_us,int *was)
{
    int changed=0;
    if(a->setting!=FPSL_AUTO) return 0;
    if(!a->window_us) {a->window_us=now_us;a->frames=0;a->work_us=0;}
    ++a->frames;
    a->work_us+=work_us<FPSL_WORK_MAX_US?work_us:FPSL_WORK_MAX_US;
    if(now_us-a->window_us<FPSL_WINDOW_US) return 0;
    /* frames per second the game reached on its own time; with no time at all (every frame waiting), as fast as
     * the counter goes */
    uint64_t potential_x10=a->frames?(a->work_us?(uint64_t)a->frames*10000000ull/a->work_us:9990):0;
    if(potential_x10>9990) potential_x10=9990;
    a->last_potential_x10=(unsigned)potential_x10;
    a->low=potential_x10<FPSL_LOW_X10?a->low+1:0;
    a->high=potential_x10>=FPSL_HIGH_X10?a->high+1:0;
    ++a->since_switch;
    *was=a->cap;
    if(a->cap==1 && a->low>=FPSL_LOW_WINDOWS) {
        /* a return to 1 that did not hold: the next one asks for twice the windows */
        if(a->returned && a->since_switch<FPSL_SETTLE)
            a->high_needed=a->high_needed*2<FPSL_HIGH_WINDOWS_MAX?a->high_needed*2:FPSL_HIGH_WINDOWS_MAX;
        a->cap=2;a->returned=0;changed=1;
    } else if(a->cap==2 && a->high>=a->high_needed) {
        a->cap=1;a->returned=1;changed=1;
    } else if(a->cap==1 && a->since_switch>=FPSL_SETTLE) a->high_needed=FPSL_HIGH_WINDOWS;
    if(changed) {a->low=a->high=0;a->since_switch=0;}
    a->window_us=now_us;a->frames=0;a->work_us=0;
    return changed;
}
/* the vblank count a present of this swapchain waits for, given the count now; 0 when it goes at once */
static inline uint64_t pw_fpsl_target_vblank(const struct pw_fpsl_chain *c,int cap,uint64_t vblank_now)
{
    if(!cap || !c->release_vblank) return 0;
    uint64_t target=c->release_vblank+(uint64_t)cap;
    return vblank_now<target?target:0;
}
/* without a vblank count: the time a present waits for (a little early: the flip still waits for its vblank) */
static inline uint64_t pw_fpsl_target_time(const struct pw_fpsl_chain *c,int cap,uint64_t period_us,uint64_t now_us)
{
    if(!cap || !c->release_us) return 0;
    uint64_t target=c->release_us+(uint64_t)cap*period_us-period_us/8;
    return now_us<target?target:0;
}
#endif
