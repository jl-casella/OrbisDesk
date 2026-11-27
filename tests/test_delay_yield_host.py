#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compare actual original/patched Wine timed sleeps with a deterministic clock."""
import pathlib,subprocess,tempfile,sys
r=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(r/'tools'))
from wine_delay_yield import patch
source=(r/'.deps/wine/source/dlls/ntdll/unix/sync.c').read_text()
def function(name):
 start=source.index('NTSTATUS WINAPI '+name);brace=source.index('{',start);end=brace+1;depth=1
 while depth:depth+=(source[end]=='{')-(source[end]=='}');end+=1
 return source[start:end]
orig=function('NtDelayExecution');new=patch(orig)
code=r'''
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <sys/resource.h>
#include <sys/time.h>
#include <setjmp.h>
typedef int32_t NTSTATUS;typedef int BOOLEAN;typedef long long timeout_t;
typedef struct {long long QuadPart;} LARGE_INTEGER;
#define WINAPI
#define HAVE_SCHED_YIELD 1
#ifndef RUSAGE_THREAD
#define RUSAGE_THREAD 1
#endif
#define STATUS_SUCCESS 0
#define STATUS_TIMEOUT 0x102
#define STATUS_NO_YIELD_PERFORMED 0x40000024
#define TIMEOUT_INFINITE 0x7fffffffffffffffLL
#define SELECT_INTERRUPTIBLE 1
#define SELECT_ALERTABLE 2
static long long clock_now;static int yields,usage_calls,selects,server_calls,server_result,force_switch,infinite,interrupt_once;
static jmp_buf escape;
static int fake_usage(int who,struct rusage *out){(void)who;usage_calls++;*out=(struct rusage){0};out->ru_nvcsw=force_switch?yields:0;return 0;}
static int fake_yield(void){yields++;return 0;}
static int fake_select(int n,void *a,void *b,void *c,struct timeval *tv){
 assert(!n&&!a&&!b&&!c);selects++;
 if(!tv){assert(infinite);longjmp(escape,1);}
 if(interrupt_once){interrupt_once=0;return -1;}
 clock_now+=(tv->tv_sec*1000000LL+tv->tv_usec)*10;return 0;
}
static int NtQuerySystemTime(LARGE_INTEGER *out){out->QuadPart=clock_now;return 0;}
static int server_wait(void *s,int n,int flags,const LARGE_INTEGER *t){(void)s;(void)n;(void)t;assert(flags==3);server_calls++;return server_result;}
#define getrusage fake_usage
#define sched_yield fake_yield
#define select fake_select
'''+function('NtYieldExecution')+'\n'+orig.replace('NtDelayExecution','original_delay',1)+'\n'+new.replace('NtDelayExecution','patched_delay',1)+r'''
static void reset(void){clock_now=1000000;yields=usage_calls=selects=server_calls=0;infinite=interrupt_once=0;}
int main(void){
 for(int switched=0;switched<2;switched++)for(int type=0;type<4;type++) {
  force_switch=switched;LARGE_INTEGER timeout={type==0?0:type==1?-100000:type==2?1200000:900000};
  reset();int a=original_delay(0,&timeout);long long elapsed=clock_now;int old_yields=yields,old_selects=selects,old_usage=usage_calls;
  reset();int b=patched_delay(0,&timeout);
  assert(a==b&&clock_now==elapsed&&yields==old_yields&&selects==old_selects);
  assert(type==0?(usage_calls==old_usage&&usage_calls==2):(usage_calls==0&&old_usage==2));
 }
 for(int i=0;i<2;i++) {
  LARGE_INTEGER timeout={-10000};reset();server_result=i?0xc0000008:STATUS_TIMEOUT;
  assert(original_delay(1,&timeout)==(i?server_result:0));assert(!yields&&!usage_calls&&server_calls==1);
  reset();assert(patched_delay(1,&timeout)==(i?server_result:0));assert(!yields&&!usage_calls&&server_calls==1);
 }
 LARGE_INTEGER timeout={-10000};reset();interrupt_once=1;patched_delay(0,&timeout);assert(selects==2&&clock_now==1010000&&!usage_calls);
 reset();infinite=1;if(!setjmp(escape))patched_delay(0,NULL);assert(selects==1&&!yields&&!usage_calls);
 puts("PASS: actual Wine delay, preserved zero-yield status, relative/absolute/past waits, alertable result, interruption and infinite wait; unused queries removed only for nonzero sleeps");
}
'''
with tempfile.TemporaryDirectory() as t:
 p=pathlib.Path(t);(p/'check.c').write_text(code)
 subprocess.run(['cc','-std=gnu11','-O1','-g','-fsanitize=address,undefined','-no-pie',str(p/'check.c'),'-o',str(p/'check')],check=True)
 subprocess.run([str(p/'check')],check=True)
try:patch(new)
except ValueError:pass
else:raise AssertionError('patch must reject changed context')
