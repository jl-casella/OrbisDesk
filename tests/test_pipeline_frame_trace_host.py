#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise actual pipeline/frame correlation and per-window log bounds."""
import pathlib,subprocess,tempfile
r=pathlib.Path(__file__).resolve().parents[1];source=(r/'platform/ps4/pw_wine_sink_ps4.c').read_text()
start=source.index('#include <sys/resource.h>');end=source.index('static void fg_read_config(void)',start)
code=r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <pthread.h>
#include <limits.h>
static uint64_t clock_us=1000;static int enabled=1;
static int pw_perf_on(void){return enabled;}
uint64_t sceKernelGetProcessTime(void){return clock_us;}
int pthread_getthreadid_np(void){return 42;}
'''+source[start:end]+r'''
int main(void){
 for(int i=0;i<12;i++)pw_vk_pipeline_note(0,60000000,0);
 assert(pf_kind_count[0]==12&&pf_slow_lines==8); /* accounting includes suppressed events */
 clock_us+=5000000;pw_vk_pipeline_note(1,70000000,3);assert(pf_slow_lines==1&&pf_disk==1&&pf_hits==1);
 memset(pf_kind_count,0,sizeof(pf_kind_count));memset(pf_kind_ns,0,sizeof(pf_kind_ns));pf_since_ns=0;
 pf_present();
 for(int i=0;i<10;i++){clock_us+=200000;pw_vk_pipeline_note(0,1000000,1);pf_present();}
 assert(pf_frames==10&&pf_over_100ms==10&&pf_frame_lines==10);
 clock_us+=5000000;pf_present();assert(pf_frame_lines==1&&pf_frames==0);
 enabled=0;unsigned before=pf_kind_count[0];pw_vk_pipeline_note(0,100000000,0);pf_present();assert(pf_kind_count[0]==before);
 puts("PASS: real pipeline/frame timestamps, bounded logs renew after five seconds, all events still counted and diagnostics-off path");
}
'''
with tempfile.TemporaryDirectory() as t:
 p=pathlib.Path(t);(p/'check.c').write_text(code)
 subprocess.run(['cc','-D_GNU_SOURCE','-std=gnu11','-O1','-g','-fsanitize=address,undefined','-no-pie',str(p/'check.c'),'-lpthread','-o',str(p/'check')],check=True)
 run=subprocess.run([str(p/'check')],capture_output=True,text=True,check=True)
 assert run.stderr.count('PWPERF slow_compile ')==9,run.stderr
 assert run.stderr.count('PWFRAME start_us=')==9,run.stderr
 assert 'end_us=' in run.stderr and 'native_tid=42' in run.stderr and 'compile_overlap_us=1000' in run.stderr
 print(run.stdout.strip())
