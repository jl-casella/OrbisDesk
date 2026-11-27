#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise native queue summaries with verbose traces disabled; no console required."""
import pathlib
import subprocess
import tempfile
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
CHECK = r'''
#include <assert.h>
#include <stdint.h>
#include <sys/resource.h>
int pw_trace_level=0;
extern int pw_perf_level;
extern int pw_vk_perf_enabled(void);
extern void pw_vk_empty_submit_event(int,unsigned,uint64_t,int);
extern void pw_vk_perf_flush(const char *);
extern void pw_perf_thread_report(unsigned);
static uint64_t now;
static int usage_error;
uint64_t sceKernelGetProcessTime(void) {return now;}
int pthread_getthreadid_np(void) {return 42;}
/* The independent sync adapter has its own behavioral host test. */
void pw_wine_thread_alert_report(unsigned tid) {(void)tid;}
int __wrap_getrusage(int who,struct rusage *usage) {
 assert(who==RUSAGE_THREAD);
 if(usage_error)return -1;
 *usage=(struct rusage){0};usage->ru_utime.tv_sec=1;usage->ru_utime.tv_usec=123;
 usage->ru_stime.tv_usec=456;usage->ru_inblock=3;usage->ru_oublock=4;
 usage->ru_nvcsw=5;usage->ru_nivcsw=6;usage->ru_minflt=7;usage->ru_majflt=8;
 return 0;
}
int main(void) {
 assert(!pw_vk_perf_enabled());
 now=1;pw_vk_empty_submit_event(0,99,999999,0); /* off: not counted */
 pw_perf_level=1;assert(pw_vk_perf_enabled());
 now=100;pw_vk_empty_submit_event(0,2,2000,0);
 now=5000100;pw_vk_empty_submit_event(1,1,9000,-4);
 now=6000100;pw_vk_perf_flush("quiet"); /* zero window still preserves totals */
 now=6000200;pw_vk_empty_submit_event(0,1,3000,0);
 now=6000300;pw_vk_perf_flush("program-change"); /* partial window */
 pw_perf_thread_report(0x74);
 usage_error=1;pw_perf_thread_report(0x84);
 pw_perf_level=0;assert(!pw_vk_perf_enabled());
 pw_trace_level=1;assert(pw_vk_perf_enabled());
 return 0;
}
'''
with tempfile.TemporaryDirectory() as temp:
    base = pathlib.Path(temp)
    (base/'check.c').write_text(CHECK)
    subprocess.run(['cc','-D_GNU_SOURCE','-O2','-Wall','-Wextra','-Werror','-ffunction-sections','-fdata-sections',
                    '-I'+str(ROOT/'platform/ps4'),str(ROOT/'native/wine_vk_runtime.c'),str(base/'check.c'),
                    '-Wl,--gc-sections','-Wl,--wrap=getrusage','-pthread','-o',str(base/'check')],check=True)
    result = subprocess.run([str(base/'check')],text=True,capture_output=True,check=True)
    rows=result.stderr.strip().splitlines()
    assert len(rows)==6,result.stderr
    assert 'reason=first-use' in rows[0] and 'async=1 cpu=0 waits=2' in rows[0]
    assert 'cpu_us=9' in rows[1] and 'failed=1' in rows[1] and 'total_async=1 total_cpu=1' in rows[1]
    assert 'async=0 cpu=0 waits=0' in rows[2] and 'total_async=1 total_cpu=1 reason=quiet' in rows[2]
    assert 'async=1 cpu=0 waits=1' in rows[3] and 'total_async=2 total_cpu=1 reason=program-change' in rows[3]
    assert rows[4]==('PWTHREADPERF wine_tid=0074 native_tid=42 wall_us=6000300 user_us=1000123 kernel_us=456 '
                     'io_in_blocks=3 io_out_blocks=4 voluntary=5 involuntary=6 minor_faults=7 major_faults=8')
    assert rows[5]=='PWTHREADPERF wine_tid=0084 cpu_available=0'
print('PASS: trace-off summaries, first/quiet/partial queue reports, cumulative totals and thread CPU/I/O/error counters')
