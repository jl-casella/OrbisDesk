#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise the actual signal dispatch with captured register contexts, under ASan/UBSan."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / 'platform/ps4/pw_wine_signals.c').read_text()
start = source.index('/* THAW 04.90: the 1 KiB record has its own frame.')
end = source.index('\n/* rdi=signal,', start)
code = r'''
#include <assert.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include "pw_native_fault_record.h"
static int pw_native_fault_diag=1,pw_native_log_fd=7,pw_fault_depth,pw_fault_reported;
static unsigned pw_native_fault_snapshots,pw_native_fault_off_stack,pw_native_fault_sequence,forwarded,records,lines;
static int on_stack=1;
static uint64_t pw_fault_first_rip,pw_fault_first_addr;
static long pw_native_raw_syscall;
static char captured[PW_NATIVE_FAULT_RECORD_BYTES+1];
static void *wanted_context,*wanted_info;
static int wanted_signal;
static long pw_native_syscall_at(long entry,long call,long fd,long buffer,long bytes) {
    (void)entry;assert(call==4&&fd==7&&bytes>0&&bytes<PW_NATIVE_FAULT_RECORD_BYTES);
    memcpy(captured,(void *)buffer,(size_t)bytes);captured[bytes]=0;++records;return bytes;
}
static void trampoline(int signal,void *info,void *context) {
    assert(signal==wanted_signal&&context==wanted_context&&info==wanted_info);++forwarded;
}
static int pw_fault_signal(int signal) {return signal==4||signal==8||signal==10||signal==11;}
static int pw_on_signal_stack(const PwOrbisUcontext *context) {(void)context;return on_stack;}
static uint64_t fake_teb[3];
static const uint64_t *pw_native_signal_teb(void) {return fake_teb;}
static void pw_native_fault_line(const char *head,long signal,const PwOrbisUcontext *context,
                                uint64_t rip,uint64_t addr) {
    (void)signal;(void)context;(void)rip;(void)addr;
    assert(!on_stack&&strstr(head,"off Wine's signal stack"));++lines;
}
''' + source[start:end] + r'''
int main(void) {
    PwOrbisUcontext context={0};
    context.uc_mcontext.mc_rip=(uintptr_t)&pw_native_signal_dispatch;
    context.uc_mcontext.mc_rsp=1; /* deliberately unreadable: never dereference */
    context.uc_mcontext.mc_addr=UINT64_MAX-239;
    context.uc_mcontext.mc_rax=0xfeedfacecafebeefULL;
    context.uc_mcontext.mc_r15=0x123456789abcdef0ULL;
    PwOrbisUcontext original=context;
    wanted_context=&context;wanted_info=(void *)0x1234;wanted_signal=11;
    pw_native_signal_dispatch(wanted_signal,wanted_info,&context);
    assert(records==1&&forwarded==1&&!memcmp(&original,&context,sizeof(context)));
    assert(strstr(captured,"PWNATIVE snapshot v=1 n=0x0000000000000001"));
    assert(strstr(captured,"rax=0xfeedfacecafebeef")&&strstr(captured,"r15=0x123456789abcdef0"));
    assert(strstr(captured,"addr=0xffffffffffffff10")&&strstr(captured,"rsp=0x0000000000000001"));
    for(unsigned i=0;i<80;i++)pw_native_signal_dispatch(wanted_signal,wanted_info,&context);
    assert(records==PW_NATIVE_FAULT_RECORD_LIMIT&&forwarded==81);
    pw_native_fault_snapshots=0;pw_native_fault_diag=0;
    pw_native_signal_dispatch(wanted_signal,wanted_info,&context);
    assert(records==PW_NATIVE_FAULT_RECORD_LIMIT&&forwarded==82);
    pw_native_fault_diag=1;wanted_signal=30;
    pw_native_signal_dispatch(wanted_signal,wanted_info,&context);
    assert(records==PW_NATIVE_FAULT_RECORD_LIMIT&&forwarded==83);
    wanted_signal=11;context.uc_mcontext.mc_rip^=1ULL<<32;
    pw_native_signal_dispatch(wanted_signal,wanted_info,&context);
    assert(records==PW_NATIVE_FAULT_RECORD_LIMIT&&forwarded==84);
    assert(!pw_native_fault_in_title(0,(uintptr_t)&pw_native_signal_dispatch));
    /* off Wine's signal stack (W303 run-0207/0208): own budget of 8, even with the other spent and foreign code */
    pw_native_fault_snapshots=PW_NATIVE_FAULT_RECORD_LIMIT;on_stack=0;
    for(unsigned i=0;i<20;i++)pw_native_signal_dispatch(wanted_signal,wanted_info,&context);
    assert(records==PW_NATIVE_FAULT_RECORD_LIMIT+PW_NATIVE_FAULT_OFF_STACK_LIMIT&&forwarded==104&&lines==1);
    assert(strstr(captured,"PWNATIVE snapshot v=1 n=0x0000000000000028")&&strstr(captured,"rax=0xfeedfacecafebeef"));
    /* a stack overflow on Wine's signal stack (THAW 04.90 run-0240): rsp 0x8a30 below the TEB's limit, foreign code */
    on_stack=1;pw_native_fault_off_stack=0;
    fake_teb[1]=0x10374fd20ULL;fake_teb[2]=0x103658000ULL;
    context.uc_mcontext.mc_rsp=0x10364f5d0ULL;context.uc_mcontext.mc_addr=0x10364f5c8ULL;
    pw_native_signal_dispatch(wanted_signal,wanted_info,&context);
    assert(records==PW_NATIVE_FAULT_RECORD_LIMIT+PW_NATIVE_FAULT_OFF_STACK_LIMIT+1&&forwarded==105&&lines==1);
    assert(strstr(captured,"n=0x0000000000000029")&&strstr(captured,"rsp=0x000000010364f5d0"));
    /* guard-page growth (rsp above the limit) and a thread with no TEB: no snapshot */
    context.uc_mcontext.mc_rsp=0x103658100ULL;context.uc_mcontext.mc_addr=0x103657ff8ULL;
    pw_native_signal_dispatch(wanted_signal,wanted_info,&context);
    fake_teb[2]=0;context.uc_mcontext.mc_rsp=0x10364f5d0ULL;
    pw_native_signal_dispatch(wanted_signal,wanted_info,&context);
    assert(records==PW_NATIVE_FAULT_RECORD_LIMIT+PW_NATIVE_FAULT_OFF_STACK_LIMIT+1&&forwarded==107);
    assert(!pw_native_fault_below_stack(1,NULL));
    struct {char guard[16];char data[PW_NATIVE_FAULT_RECORD_BYTES];char tail[16];} buffer;
    memset(&buffer,0xa5,sizeof(buffer));
    assert(!pw_native_fault_record(buffer.data,16,1,11,&context.uc_mcontext));
    for(unsigned i=0;i<sizeof(buffer);i++)assert(((unsigned char *)&buffer)[i]==0xa5);
    unsigned n=pw_native_fault_record(buffer.data,sizeof(buffer.data),1,11,&context.uc_mcontext);
    assert(n>0&&n<sizeof(buffer.data)&&buffer.data[n-1]=='\n');
    for(unsigned i=0;i<16;i++)assert((unsigned char)buffer.guard[i]==0xa5&&(unsigned char)buffer.tail[i]==0xa5);
    puts("PASS native fault capture: registers, unchanged context, forwarding, budget, disabled PRX, foreign code, off-stack budget, stack overflow, bounds");
}
'''
with tempfile.TemporaryDirectory() as temporary:
    path = Path(temporary)
    (path / 'check.c').write_text(code)
    subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror', '-O1', '-g',
                    '-fsanitize=address,undefined', '-no-pie', '-I'+str(root/'platform/ps4'),
                    str(path/'check.c'), '-o', str(path/'check')], check=True)
    subprocess.run([str(path/'check')], check=True, timeout=15)
