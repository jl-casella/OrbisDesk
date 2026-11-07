/* SPDX-License-Identifier: LGPL-2.1-or-later */
#define _GNU_SOURCE
#include <fcntl.h>
#include <setjmp.h>
#include <stdint.h>
#include <stdio.h>
#include <unistd.h>

typedef struct { uint32_t bits[4]; } WireMask;
typedef struct { void (*handler)(int,void*,void*); int flags; WireMask mask; } WireAction;
extern int sigaction(int,const WireAction*,WireAction*);
extern int sigprocmask(int,const WireMask*,WireMask*);
static sigjmp_buf jump;
static volatile int data = 42;
static volatile int *volatile pointer = &data;
static int answer(void) { return 42; }
static int (*volatile function_pointer)(void) = answer;
static volatile int received, code_selector;
extern long platform_raw_call(uintptr_t,long,long,long,long);
__asm__(".text\n.globl platform_raw_call\nplatform_raw_call:\n"
        "movq %rsi,%rax\nmovq %rdi,%r11\nmovq %rdx,%rdi\nmovq %rcx,%rsi\nmovq %r8,%rdx\n"
        "subq $8,%rsp\ncallq *%r11\naddq $8,%rsp\nret\n");
static void handler(int signal,void *info,void *context) {
    (void)info; code_selector=*(uint16_t*)((unsigned char*)context+232); received=signal; siglongjmp(jump,9);
}
int main(void) {
    int fixed = *pointer==42 && function_pointer()==42;
    volatile int value = sigsetjmp(jump,1);
    if (!value) siglongjmp(jump,0);
    int zero = value==1;
    WireMask old={0},first={{1u<<29,0,0,0}},second={{1u<<30,0,0,0}},got={0};
    int masks = sigprocmask(3,&first,&old)==0;
    value=sigsetjmp(jump,1);
    if (!value) { sigprocmask(3,&second,0); siglongjmp(jump,7); }
    masks = masks && value==7 && !sigprocmask(1,0,&got) && got.bits[0]==first.bits[0];
    sigprocmask(3,&old,0);
    WireAction action={handler,0x40,{{0}}},previous={0};
    int signal_test = sigaction(4,&action,&previous)==0;
    value=sigsetjmp(jump,1);
    if (!value) __asm__ volatile("ud2");
    signal_test = signal_test && value==9 && received==4;
    sigaction(4,&previous,0);
    uintptr_t entry=(uintptr_t)&getppid+10;
    int raw=platform_raw_call(entry,20,0,0,0)==getpid() && platform_raw_call(entry,39,0,0,0)==getppid()
        && platform_raw_call(entry,999999,0,0,0)!=0;
    int selector=code_selector==0x43;
    char report[256];
    int n=snprintf(report,sizeof(report),"{\"fixed_pointers\":%d,\"longjmp_zero\":%d,\"saved_mask\":%d,\"signal_recovery\":%d,\"raw_syscalls\":%d,\"signal_cs\":%d}\n",fixed,zero,masks,signal_test,raw,selector);
    int fd=open("/data/orbisdesk-platform-check.json",O_CREAT|O_TRUNC|O_WRONLY,0644);
    if (fd>=0) { write(fd,report,(size_t)n); fsync(fd); close(fd); }
    return fixed && zero && masks && signal_test && raw && selector ? 0 : 1;
}
