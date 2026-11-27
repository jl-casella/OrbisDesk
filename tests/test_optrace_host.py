#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actual optrace recorder: nested calls, errno, pending, bounded logs and TLS."""
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
static void call(unsigned op,uint64_t us,int status,uint64_t bytes){struct pw_opstamp s=pw_optrace_begin();fake_tsc+=us*1000;pw_optrace_end(s,op,status,bytes);}
static void *other(void *arg){(void)arg;assert(!pw_ops.op[PW_OP_READ].calls);call(PW_OP_READ,7,0,8);assert(pw_ops.op[PW_OP_READ].calls==1);return NULL;}
int main(void){
 pw_optrace_configure(1000000000,0);assert(!pw_optrace_begin().active);
 pw_optrace_configure(1,1);assert(!pw_optrace_begin().active);
 pw_optrace_configure(1000000000,1);output[0]=0;
 errno=73;call(PW_OP_READ,200,0x103,4096);assert(errno==73&&pw_ops.op[PW_OP_READ].pending==1&&pw_ops.op[PW_OP_READ].requested==4096);
 struct pw_opstamp a=pw_optrace_begin(),b=pw_optrace_begin();assert(a.active&&!b.active);
 fake_tsc+=1000000;pw_optrace_end(b,PW_OP_WAIT_ONE,0,0);assert(pw_ops.busy);pw_optrace_end(a,PW_OP_READ,0,1);
 assert(pw_ops.op[PW_OP_READ].calls==2&&!pw_ops.op[PW_OP_WAIT_ONE].calls&&!pw_ops.busy);
 call(PW_OP_DELAY,60000,0xc0000008u,0);assert(pw_ops.op[PW_OP_DELAY].failed==1&&strstr(output,"PWOP slow"));
 for(int i=0;i<20;i++)call(PW_OP_DELAY,60000,0,0);
 int n=0;for(char *p=output;(p=strstr(p,"PWOP slow"));p++)n++;assert(n==8);
 pthread_t thread;assert(!pthread_create(&thread,NULL,other,NULL));pthread_join(thread,NULL);assert(pw_ops.op[PW_OP_READ].calls==2);
 fake_tsc+=5000000000ull;pw_optrace_report(0x123);assert(strstr(output,"wine_tid=0123")&&strstr(output,"op=NtReadFile")&&strstr(output,"requested_bytes=4097")&&strstr(output,"pending=1"));
 assert(!pw_ops.op[PW_OP_READ].calls&&!pw_ops.busy&&errno==73);
 output[0]=0;call(PW_OP_DELAY,60000,0,0);assert(strstr(output,"PWOP slow"));
 pw_optrace_configure(1000000000,0);output[0]=0;call(PW_OP_READ,60000,0,8);assert(!output[0]);
 puts("PASS: real operation recorder, no nested double counting, errno preserved, pending/failed distinction, exact budgets, isolated TLS and disabled fast path");
}
'''
with tempfile.TemporaryDirectory() as t:
 p=pathlib.Path(t);(p/'check.c').write_text(code)
 subprocess.run(['cc','-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-no-pie','-I'+str(r/'platform/ps4'),str(p/'check.c'),'-lpthread','-o',str(p/'check')],check=True)
 subprocess.run([str(p/'check')],check=True)
