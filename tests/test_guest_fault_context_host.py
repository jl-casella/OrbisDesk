#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compile actual bounded context diagnostics for both PE context layouts."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
code=r'''
#include <assert.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef long LONG;typedef unsigned UINT;typedef uint32_t DWORD;
typedef uint64_t ULONGLONG;typedef uintptr_t ULONG_PTR;typedef unsigned char BYTE;
typedef struct {DWORD Eax,Ebx,Ecx,Edx,Esi,Edi,Ebp,Esp,Eip,EFlags;
 ULONGLONG Rax,Rbx,Rcx,Rdx,Rsi,Rdi,Rbp,Rsp,Rip,R8,R9,R10,R11,R12,R13,R14,R15;} CONTEXT;
#define ARRAY_SIZE(x) (sizeof(x)/sizeof((x)[0]))
static char log_text[32768];static int fail_reads,reads;
static void record(const char *format,...){va_list args;va_start(args,format);size_t n=strlen(log_text);vsnprintf(log_text+n,sizeof(log_text)-n,format,args);va_end(args);}
#define ERR(...) record(__VA_ARGS__)
static int ps4_guest_read(ULONG_PTR address,void *out,UINT size){
 reads++;assert(reads<=2);if(fail_reads)return 0;
 if(address==0x1000){assert(size==16);memset(out,0xcc,size);memcpy(out,"\x8b\x34\x81",3);return 1;}
 assert(address==0x2000);
#ifdef __i386__
 assert(size==8*sizeof(DWORD));DWORD *p=out;
#else
 assert(size==8*sizeof(ULONGLONG));ULONGLONG *p=out;
#endif
 for(unsigned i=0;i<8;i++)p[i]=i+0x9000;return 1;
}
'''+(root/'platform/ps4/pw_guest_fault_context.inc.c').read_text()+r'''
int main(void){
 CONTEXT c={0};c.Eip=c.Rip=0x1000;c.Esp=c.Rsp=0x2000;c.Eax=c.Rax=0x84;c.Ecx=c.Rcx=0;c.EFlags=0x202;c.R15=0xfedcba9876543210ULL;
 CONTEXT original=c;ps4_guest_fault_context(1,&c);assert(!memcmp(&c,&original,sizeof(c))&&reads==2);
 assert(strstr(log_text,"instruction_bytes=8b 34 81 cc")&&strstr(log_text,"stack_slot=7 value=0x9007"));
#ifdef __i386__
 assert(strstr(log_text,"regs32 eax=0x84")&&strstr(log_text,"ecx=0"));
#else
 assert(strstr(log_text,"regs64 rax=0x84")&&strstr(log_text,"r15=0xfedcba9876543210"));
#endif
 fail_reads=1;reads=0;log_text[0]=0;ps4_guest_fault_context(2,&c);
 assert(reads==2&&strstr(log_text,"instruction_bytes=unreadable")&&strstr(log_text,"stack=unreadable"));
 assert(!strstr(log_text,"stack_slot=")&&!memcmp(&c,&original,sizeof(c)));
 puts("PASS: actual fault diagnostics, unchanged context, bounded safe reads and unreadable-memory handling");
}
'''
with tempfile.TemporaryDirectory() as tmp:
    p=Path(tmp);(p/'check.c').write_text(code)
    for arch in (32,64):
        exe=p/f'check-{arch}'
        subprocess.run(['cc','-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-fsanitize=address,undefined','-no-pie',*(['-D__i386__'] if arch==32 else []),str(p/'check.c'),'-o',str(exe)],check=True)
        subprocess.run([str(exe)],check=True,timeout=10)
builder=(root/'tools/build-guest-hw.py').read_text()
assert 'if ((n = InterlockedIncrement( &traced )) > 8) return EXCEPTION_CONTINUE_SEARCH;' in builder
assert 'context = *ptrs->ContextRecord;\n    ps4_guest_fault_context( n, &context );' in builder
