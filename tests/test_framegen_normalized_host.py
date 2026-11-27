#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Execute the sink's actual normalized-frame bridge with modeled GPU boundaries."""
import ast, pathlib, subprocess, tempfile
r=pathlib.Path(__file__).resolve().parents[1]
s=(r/'platform/ps4/pw_wine_sink_ps4.c').read_text()
def function(name):
 start=s.index('static void '+name+'(') if 'static void '+name+'(' in s else s.index('void '+name+'(',s.index('void '+name+'(')+1)
 begin=s.index('{',start);depth=0
 for i in range(begin,len(s)):
  if s[i]=='{':depth+=1
  elif s[i]=='}':
   depth-=1
   if not depth:return s[start:i+1]
 raise AssertionError(name)
code=r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <pthread.h>
#include <limits.h>
#include "pw_present_pixels.h"
#define PW_SINK_GPU 1
static int pw_trace_on(void){return 1;}
enum {FG_OFF,FG_TIMING,FG_SHADOW,FG_DISPLAY,FT_SOURCES=2,FT_BUCKETS=6,FT_NOMINAL_PERIOD_US=16667};
static int fg_mode=FG_DISPLAY,fg_generator_off,fg_restart_wanted=1,ft_logging;
static struct {int cap;} fl_auto={2};static struct {int gave_up;} fgd;
static unsigned ft_generated,ft_generated_failed,ft_present_seq,ft_period_us;
static pthread_mutex_t fgd_lock=PTHREAD_MUTEX_INITIALIZER,ft_lock=PTHREAD_MUTEX_INITIALIZER;
static struct {const void *swapchain,*pixels;unsigned width,height;int span;uint64_t seq;} fgd_note;
struct ft_source {const void *swapchain;unsigned width,height;int format;uint64_t last_us,sum_us,sumsq_us,min_us,max_us;unsigned n,bucket[FT_BUCKETS],presents;};
static struct ft_source ft_sources[FT_SOURCES];
static unsigned captures;static const void *captured;static unsigned captured_pitch,captured_rgba;static int restarted,gpu_result=1;
static int pw_hw_overlay_hud_rect(unsigned w,unsigned h,int *rect){return 0;}
static int pw_sink_gpu_fg_frame(const void *sc,const void *pixels,unsigned pitch,unsigned w,unsigned h,int rgba,const int *keep,int restart){
 assert(sc && pixels && pitch>=w*4);captures++;captured=pixels;captured_pitch=pitch;captured_rgba=rgba;restarted=restart;return gpu_result;
}
''' + function('fg_capture_frame')+'\n'+function('pw_wine_framegen_normalized')+'\n'+function('ft_present')+r'''
int main(void){
 uint16_t source[]={0xff00,0xf0f0,0xf00f,0xffff};uint32_t bgra[4];
 assert(pw_present_to_bgra(bgra,source,4,2,2,1000340000));
 const void *sc=(void*)10;
 // Hook sees one packed frame. It must not submit a 16-bit row to a 32-bit generator.
 ft_present(sc,source,4,2,2,1000340000,100);
 assert(!captures && ft_present_seq==1 && ft_sources[0].presents==1);
 // The limiter's note is published by the hook; the driver now supplies its real BGRA layer.
 fgd_note.swapchain=sc;fgd_note.pixels=source;fgd_note.width=2;fgd_note.height=2;fgd_note.seq=1;
 pw_wine_framegen_normalized(sc,source,bgra,2,2);
 assert(captures==1 && captured==bgra && captured_pitch==8 && !captured_rgba && restarted);
 assert(bgra[0]==0xffff0000 && bgra[1]==0xff00ff00 && bgra[2]==0xff0000ff);
 assert(fgd_note.pixels==captured && fgd_note.seq==1 && ft_present_seq==1 && ft_generated==1);
 // An obsolete callback cannot replace the current image or submit old content.
 pw_wine_framegen_normalized(sc,source,bgra,2,2);assert(captures==1);
 fgd_note.pixels=source;pw_wine_framegen_normalized(sc,source,bgra,3,2);assert(captures==1);
 pw_wine_framegen_normalized((void*)12,source,bgra,2,2);assert(captures==1);
 // Disabled generation and a non-30-fps cap must not produce invented generated counts.
 fg_mode=FG_OFF;pw_wine_framegen_normalized(sc,source,bgra,2,2);assert(captures==1);
 fg_mode=FG_DISPLAY;fl_auto.cap=1;fgd_note.pixels=source;
 pw_wine_framegen_normalized(sc,source,bgra,2,2);assert(captures==1 && fg_restart_wanted);
 fl_auto.cap=2;fgd_note.pixels=source;gpu_result=0;
 pw_wine_framegen_normalized(sc,source,bgra,2,2);assert(captures==2 && restarted && ft_generated==1);
 // Timing/shadow mode can capture normalized images without a display scheduler note.
 fg_mode=FG_SHADOW;fgd_note.pixels=NULL;
 pw_wine_framegen_normalized(sc,source,bgra,2,2);assert(captures==3 && !fgd_note.pixels);
 // Ordinary 32-bit frames still use the existing direct path and colour order.
 fg_mode=FG_DISPLAY;ft_present((void*)11,bgra,8,2,2,37,200);
 assert(captures==4 && captured==bgra && captured_rgba==1 && ft_present_seq==2);
 ft_present((void*)11,bgra,8,2,2,44,300);assert(captures==5 && !captured_rgba);
 gpu_result=-1;ft_present((void*)11,bgra,8,2,2,44,400);
 assert(fg_generator_off && ft_generated_failed==1 && ft_generated==1);
 fg_restart_wanted=0;ft_present((void*)11,bgra,8,2,2,999,500);assert(fg_restart_wanted && captures==6);
 puts("PASS: packed input deferred, converted BGRA captured once, scheduler pointer matches layer, stale callbacks rejected, real counters and 32-bit path preserved");
}
'''
with tempfile.TemporaryDirectory() as tmp:
 p=pathlib.Path(tmp);(p/'check.c').write_text(code)
 subprocess.run(['cc','-std=gnu11','-O1','-g','-fsanitize=address,undefined','-no-pie','-pthread','-I'+str(r/'platform/ps4'),str(p/'check.c'),'-o',str(p/'check')],check=True)
 subprocess.run([str(p/'check')],check=True)
# Displayed-rate publication must still depend on actually shown generated flips.
assert 'fgr_published.generated_tenths>0' in s and 'fgr_published.shown_tenths=real+generated' in s
print('PASS: shown-FPS publication still requires generated frames on screen; no counter override introduced')

# Wine native units use hidden visibility and the producer localizes hidden
# symbols. Exercise the canonical fallback through that exact kind of link:
# the product's strong callback must win, not a localized/inlined empty body.
tree=ast.parse((r/'tools/wine_present_pixels.py').read_text())
replacement=next(n.value for n in ast.walk(tree) if isinstance(n,ast.Constant) and isinstance(n.value,str) and 'void __attribute__((weak,noinline' in n.value)
at=replacement.index('void __attribute__');end=replacement.index('\n}',at)+2 if '\n}' in replacement[at:] else replacement.index('; }',at)+3
fallback=replacement[at:end]
assert 'visibility("default")' in fallback
with tempfile.TemporaryDirectory() as tmp:
 p=pathlib.Path(tmp)
 (p/'weak.c').write_text(fallback+'\nvoid __attribute__((visibility("default"))) call_bridge(void){pw_wine_framegen_normalized((void*)1,(void*)2,(void*)3,16,16);}\n')
 (p/'strong.c').write_text('#include <assert.h>\nstatic int n;void call_bridge(void);void pw_wine_framegen_normalized(const void*a,const void*b,const void*c,unsigned w,unsigned h){assert(a&&b&&c&&w==16&&h==16);n++;}int main(void){call_bridge();assert(n==1);}\n')
 subprocess.run(['clang','-O2','-fvisibility=hidden','-c',str(p/'weak.c'),'-o',str(p/'weak.o')],check=True)
 subprocess.run(['objcopy','--localize-hidden',str(p/'weak.o')],check=True)
 symbols=subprocess.check_output(['nm',str(p/'weak.o')],text=True)
 assert ' W pw_wine_framegen_normalized' in symbols,symbols
 subprocess.run(['cc',str(p/'strong.c'),str(p/'weak.o'),'-o',str(p/'binding')],check=True)
 subprocess.run([str(p/'binding')],check=True)
print('PASS: canonical weak fallback remains replaceable after hidden-symbol localization; product callback executes')
