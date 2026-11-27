#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise the shared real FG preparation state machine with init/probe models."""
from pathlib import Path
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
text=(root/'native/hw_sink_gpu/framegen.inc.c').read_text()
start=text.index('static int fg_prepare_locked(void)')
end=text.index('\nint pw_sink_gpu_fg_prepare',start)
code=r'''
#include <assert.h>
#include <stddef.h>
#include <stdio.h>
static struct {int state;unsigned frames;} fg;
static int images=1,pool_fail,init_fail,probe_fail,inits,probes,shutdowns;
static int pool_init(void){return pool_fail;}
static int fg_init(void){inits++;return init_fail;}
static int fg_probe(void){probes++;return probe_fail;}
static void fg_shutdown(const char *why){assert(why);shutdowns++;fg.state=-1;}
'''+text[start:end]+r'''
int main(void){
 assert(fg_prepare_locked()==1&&fg.state==1&&inits==1&&probes==1&&!fg.frames);
 assert(fg_prepare_locked()==1&&inits==1&&probes==1); /* first present reuses prepared shaders */
 fg.state=0;init_fail=1;assert(fg_prepare_locked()==-1&&fg.state==-1&&shutdowns==1);
 assert(fg_prepare_locked()==-1&&inits==2); /* no retry after a real failure */
 fg.state=0;init_fail=0;probe_fail=1;assert(fg_prepare_locked()==-1&&shutdowns==2&&probes==2);
 fg.state=0;probe_fail=0;images=0;assert(fg_prepare_locked()==-1&&shutdowns==3&&inits==3);
 fg.state=0;images=1;pool_fail=1;assert(fg_prepare_locked()==-1&&shutdowns==4&&inits==3);
 puts("PASS: FG prewarm and lazy use share initialization, probes, failure shutdown and empty history");
 return 0;
}
'''
with tempfile.TemporaryDirectory() as tmp:
    base=Path(tmp);(base/'check.c').write_text(code)
    subprocess.run(['cc','-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=undefined',str(base/'check.c'),'-o',str(base/'check')],check=True)
    subprocess.run([str(base/'check')],check=True,timeout=10)

# Exercise the real sink-side admission/override and accounting wrapper too.
sink=(root/'platform/ps4/pw_wine_sink_ps4.c').read_text()
start=sink.index('int pw_hw_framegen_prewarm(void)')
end=sink.index('\n}\n',start)+3
wrapper=r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <pthread.h>
enum {FG_OFF,FG_TIMING,FG_SHADOW,FG_DISPLAY};
static int fg_file_mode=-1,gpu=1,saved,prepared,perf,started,reports,result=1;
static uint64_t pf_window_us,pf_last_us,pf_since_ns;
static pthread_mutex_t lock=PTHREAD_MUTEX_INITIALIZER,pf_lock=PTHREAD_MUTEX_INITIALIZER;
int pw_hw_overlay_framegen_saved(void){return saved;}
int pw_sink_gpu_fg_prepare(void){prepared++;return result;}
static void ft_start(void){started++;}
static int pw_perf_on(void){return perf;}
static uint64_t sceKernelGetProcessTime(void){return 100;}
static void pf_start(uint64_t now){pf_window_us=now;}
static void pf_report(uint64_t now,char *line,unsigned long capacity){assert(now==100&&capacity);reports++;line[0]=0;}
'''+sink[start:end]+r'''
int main(void){
 assert(pw_hw_framegen_prewarm()==0&&!prepared);
 saved=1;assert(pw_hw_framegen_prewarm()==1&&prepared==1);
 fg_file_mode=FG_OFF;assert(pw_hw_framegen_prewarm()==0&&prepared==1);
 fg_file_mode=FG_TIMING;assert(pw_hw_framegen_prewarm()==0&&prepared==1);
 saved=0;fg_file_mode=FG_SHADOW;assert(pw_hw_framegen_prewarm()==1&&prepared==2);
 gpu=0;assert(pw_hw_framegen_prewarm()==0&&prepared==2);gpu=1;
 fg_file_mode=FG_DISPLAY;perf=1;pf_last_us=4;pf_since_ns=5;
 assert(pw_hw_framegen_prewarm()==1&&prepared==3&&reports==1);
 assert(!pf_window_us&&!pf_last_us&&!pf_since_ns);
 result=-1;assert(pw_hw_framegen_prewarm()==-1&&reports==2);
 assert(started==8);
 puts("PASS: saved FG choice, explicit overrides, GPU eligibility and separate startup accounting");
 return 0;
}
'''
with tempfile.TemporaryDirectory() as tmp:
    base=Path(tmp);(base/'wrapper.c').write_text(wrapper)
    subprocess.run(['cc','-DPW_SINK_GPU','-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror',
                    '-fsanitize=undefined','-pthread',str(base/'wrapper.c'),'-o',str(base/'check')],check=True)
    subprocess.run([str(base/'check')],check=True,timeout=10)
