#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actual recorder: stage totals, errno, partial/unknown bytes and independent budgets."""
import pathlib,subprocess,tempfile
r=pathlib.Path(__file__).resolve().parents[1]
code=r'''
#include <assert.h>
#include <stdarg.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <pthread.h>
static __thread uint64_t fake_tsc=1000000000;
static char output[65536];
static int record(FILE *stream,const char *format,...){(void)stream;va_list a;va_start(a,format);size_t n=strlen(output);int ret=vsnprintf(output+n,sizeof(output)-n,format,a);va_end(a);errno=EIO;return ret;}
uint64_t sceKernelGetProcessTime(void){return fake_tsc/1000;}
int pthread_getthreadid_np(void){return 42;}
#define fprintf record
#define PW_OPTRACE_READ_TSC() fake_tsc
'''+(r/'platform/ps4/pw_optrace.inc.c').read_text()+r'''
static void *other(void *p){(void)p;assert(!pw_reads.start&&!pw_reads.kind[1].calls);return NULL;}
int main(void){
 pw_optrace_configure(1000000000,0);assert(!pw_readtrace_begin().active);
 pw_optrace_configure(1000000000,1);output[0]=0;errno=73;
 struct pw_readstamp s=pw_readtrace_begin();s.kind=1;s.async_read=1;
 fake_tsc+=10000;pw_readtrace_stage(&s,PW_READ_BUFFER);
 fake_tsc+=20000;pw_readtrace_stage(&s,PW_READ_IO);
 fake_tsc+=30000;s.actual=7;s.known=1;pw_readtrace_stage(&s,PW_READ_COMPLETION);
 fake_tsc+=40000;s.event=1;s.completion=1;
 assert(pw_readtrace_end(&s,0x103,100)==0x103&&errno==73);
 assert(pw_reads.kind[1].calls==1&&pw_reads.kind[1].ticks[0]==10000&&pw_reads.kind[1].ticks[3]==40000);
 assert(pw_reads.kind[1].max==100000&&pw_reads.kind[1].actual==7&&pw_reads.kind[1].pending==1);
 assert(!pw_readtrace_end(&s,0,0)&&pw_reads.kind[1].calls==1); /* one end only */
 s=pw_readtrace_begin();s.kind=2;fake_tsc+=1000;
 assert(pw_readtrace_end(&s,(int32_t)0xc0000008,33)==(int32_t)0xc0000008);
 assert(pw_reads.kind[2].failed==1&&!pw_reads.kind[2].known&&!pw_reads.kind[2].actual);
 pthread_t t;assert(!pthread_create(&t,NULL,other,NULL));pthread_join(t,NULL);
 for(int i=0;i<12;i++){struct pw_opstamp a=pw_optrace_begin();fake_tsc+=60000000;pw_optrace_end(a,PW_OP_DELAY,0,0);}
 struct pw_opstamp a=pw_optrace_begin();fake_tsc+=60000000;pw_optrace_end(a,PW_OP_READ,0,1);
 assert(strstr(output,"op=NtReadFile")); /* sleepers cannot exhaust reads' slow budget */
 fake_tsc+=5000000000ull;pw_optrace_report(0x123);
 assert(strstr(output,"PWREAD")&&strstr(output,"kind=file calls=1 lookup_us=10 buffer_us=20 io_us=30 completion_us=40 max_us=100 requested_bytes=100 inline_bytes=7 inline_known=1 pending=1 failed=0 async=1 event=1 apc=0 fd_completion=1"));
 assert(strstr(output,"kind=socket calls=1")&&!pw_reads.kind[1].calls&&errno==73);
 puts("PASS: read stage accounting, exact status and errno, unknown delegated bytes, TLS and independent read slow budget");
}
'''
with tempfile.TemporaryDirectory() as t:
 p=pathlib.Path(t);(p/'check.c').write_text(code)
 subprocess.run(['cc','-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-no-pie','-I'+str(r/'platform/ps4'),str(p/'check.c'),'-lpthread','-o',str(p/'check')],check=True)
 subprocess.run([str(p/'check')],check=True)
