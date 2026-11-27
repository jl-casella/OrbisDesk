#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actual presentation recorder: elapsed phases, own logging exclusion and disabled path."""
import pathlib,subprocess,tempfile
r=pathlib.Path(__file__).resolve().parents[1]
code=r'''
#include <assert.h>
#include <errno.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
static uint64_t now=1000000;static unsigned clocks;static char output[65536];
static uint64_t clock_us(void){clocks++;return now;}
int pthread_getthreadid_np(void){return 42;}
static int record(FILE *f,const char *format,...){(void)f;va_list a;va_start(a,format);size_t n=strlen(output);int ret=vsnprintf(output+n,sizeof(output)-n,format,a);va_end(a);errno=EIO;now+=5000;return ret;}
#define fprintf record
#define PW_PRESENT_CLOCK() clock_us()
'''+(r/'platform/ps4/pw_present_trace.inc.c').read_text()+r'''
static void frame(const void *chain){
 pw_present_trace_begin(chain,now,1);
 now+=10;pw_present_trace_mark(PW_PRESENT_METADATA);
 now+=20;pw_present_trace_mark(PW_PRESENT_PREPARE);
 now+=30;pw_present_trace_mark(PW_PRESENT_LIMIT);
 now+=40;pw_present_trace_mark(PW_PRESENT_TAIL);
 now+=50;pw_present_trace_end(6000);
}
int main(void){
 errno=73;pw_present_trace_begin((void *)1,now,0);pw_present_trace_mark(PW_PRESENT_LIMIT);pw_present_trace_end(0);assert(!clocks&&!output[0]&&errno==73);
 frame((void *)1);assert(pw_pt.sum.calls==1&&!pw_pt.sum.known&&pw_pt.sum.callback==150&&pw_pt.sum.stage[3]==40);
 now+=1000;frame((void *)1);assert(pw_pt.sum.outside==1000&&pw_pt.sum.known==1&&pw_pt.sum.blit==12);
 now+=2000;frame((void *)2);assert(pw_pt.sum.outside==1000&&pw_pt.sum.known==1); /* another chain is not producer delay */
 now+=150000;frame((void *)2);assert(strstr(output,"outside_known=1 outside_us=150000 callback_us=150 lock_us=10 metadata_us=20 prepare_us=30 limiter_us=40 tail_us=50 blit_us=6"));
 assert(pw_pt.previous_return==now&&errno==73); /* fake printf's 5ms excluded from next outside interval */
 now+=1000;frame((void *)2);assert(pw_pt.outside==1000&&pw_pt.arrival_interval==6150&&pw_pt.previous_trace==5000);
 for(int i=0;i<20;i++){now+=100000;frame((void *)2);}
 int n=0;for(char *p=output;(p=strstr(p,"PWPRESENT slow"));p++)n++;assert(n==8);
 now+=5000000;frame((void *)2);assert(strstr(output,"PWPRESENT window_us=")&&strstr(output,"native_tid=42")&&!pw_pt.sum.calls);
 pw_present_trace_begin((void *)2,now,1);now--;pw_present_trace_mark(PW_PRESENT_LIMIT);pw_present_trace_end(0);assert(!pw_pt.previous_return&&!pw_pt.active&&errno==73);
 memset(&pw_pt,0,sizeof(pw_pt));output[0]=0;now=10000000;
 pw_present_trace_begin((void *)1,now,1);pw_present_trace_mark(PW_PRESENT_LIMIT);now+=120000;pw_present_trace_end(0);
 now+=1000;frame((void *)1);
 assert(pw_pt.arrival_interval==126000&&strstr(output,"previous_callback_us=120000 previous_trace_us=5000"));
 puts("PASS: real present phases, outside-callback gaps, independent chains, bounded events, errno, logging exclusion, clock regression and zero-clock disabled path");
}
'''
with tempfile.TemporaryDirectory() as t:
 p=pathlib.Path(t);(p/'check.c').write_text(code)
 subprocess.run(['cc','-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-no-pie','-I'+str(r/'platform/ps4'),str(p/'check.c'),'-o',str(p/'check')],check=True)
 subprocess.run([str(p/'check')],check=True)
