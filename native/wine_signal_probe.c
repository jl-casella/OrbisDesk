/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include "pw_wine_context.h"
extern int pw_wine_sigaction(int,const struct sigaction *,struct sigaction *);
extern int pw_wine_pthread_sigmask(int,const sigset_t *,sigset_t *);
extern int pw_wine_sigaltstack(const stack_t *,stack_t *);
/* Wine's segv_handler classifies faults by FreeBSD trap number and error code,
 * reads the FPU state from mc_fpstate and resumes through the edited context. */
struct Observed {
    int count;uint32_t trapno;uint64_t err,addr,rflags,fpformat,fsbase,gsbase;uint32_t mxcsr;
    unsigned char *page;uint32_t write_mxcsr;uintptr_t handler_sp;uint64_t cs,ss;uint16_t ds;
};
static volatile struct Observed seen;
static void handler(int signal,void *info,void *raw)
{
    (void)signal;(void)info;
    PwOrbisUcontext *context=raw;PwOrbisMcontext *mc=&context->uc_mcontext;
    {volatile int marker=0;seen.handler_sp=(uintptr_t)&marker;}
    seen.count++;seen.trapno=mc->mc_trapno;seen.err=mc->mc_err;seen.addr=mc->mc_addr;
    seen.rflags=mc->mc_rflags;seen.fpformat=mc->mc_fpformat;seen.fsbase=mc->mc_fsbase;seen.gsbase=mc->mc_gsbase;
    seen.cs=mc->mc_cs;seen.ss=mc->mc_ss;seen.ds=mc->mc_ds;
    memcpy((void *)&seen.mxcsr,(unsigned char *)mc->mc_fpstate+24,4);
    if(seen.write_mxcsr) memcpy((unsigned char *)mc->mc_fpstate+24,(const void *)&seen.write_mxcsr,4);
    mprotect(seen.page,16384,PROT_READ|PROT_WRITE);
}
static uint32_t read_mxcsr(void) {uint32_t value;__asm__ volatile("stmxcsr %0":"=m"(value));return value;}
static void write_mxcsr(uint32_t value) {__asm__ volatile("ldmxcsr %0"::"m"(value));}
static void report(const char *name,int passed)
{
    printf("PWSERVICE {\"case\":\"%s\",\"status\":\"%s\",\"trapno\":%u,\"err\":%llu,\"fpformat\":\"0x%llx\",\"mxcsr\":\"0x%x\"}\n",
           name,passed?"passed":"blocked",seen.trapno,(unsigned long long)seen.err,
           (unsigned long long)seen.fpformat,seen.mxcsr);
    fflush(stdout);
}
static int fault(unsigned char *page,int write,uint32_t new_mxcsr)
{
    memset((void *)&seen,0,sizeof(seen));seen.page=page;seen.write_mxcsr=new_mxcsr;
    if(mprotect(page,16384,PROT_NONE)) return 0;
    if(write) *(volatile unsigned char *)(page+8)=0x5a;
    else (void)*(volatile unsigned char *)(page+8);
    return seen.count==1;
}
int pw_wine_boot_signal_services(void)
{
    struct sigaction action;memset(&action,0,sizeof(action));
    action.sa_sigaction=(void (*)(int,siginfo_t *,void *))handler;action.sa_flags=SA_SIGINFO;
    unsigned char *page=mmap(NULL,16384,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANON,-1,0);
    if(page==MAP_FAILED || pw_wine_sigaction(SIGSEGV,&action,NULL)) {report("signal-setup",0);return 94;}
    uintptr_t tcb=0,gs=0;__asm__ volatile("movq %%fs:0,%0":"=r"(tcb));
    if(sysarch(130,&gs)) gs=UINTPTR_MAX;
    uint32_t mxcsr=read_mxcsr();
    /* Wine compares the saved SS with its 64-bit data selector to tell 16-bit code apart. */
    uint16_t cs,ss,ds;__asm__ volatile("movw %%cs,%0; movw %%ss,%1; movw %%ds,%2":"=r"(cs),"=r"(ss),"=r"(ds));
    int read_ok=fault(page,0,0) && seen.trapno==T_PAGEFLT && !(seen.err&2) && seen.addr==(uintptr_t)(page+8) &&
                (seen.rflags&2) && seen.fsbase==tcb && seen.gsbase==gs &&
                seen.cs==cs && seen.ss==ss && seen.ds==ds;
    report("signal-read-page-fault",read_ok);
    int write_ok=fault(page,1,0) && seen.trapno==T_PAGEFLT && (seen.err&2) && page[8]==0x5a;
    report("signal-write-page-fault",write_ok);
    /* Status flags (bits 0-5) are sticky and may change between reads; control bits must match. */
    int fp_read=fault(page,0,0) && seen.fpformat==0x10002 && (seen.mxcsr&~0x3fu)==(mxcsr&~0x3fu);
    report("signal-fpu-state-read",fp_read);
    uint32_t rounded=(mxcsr&~0x6000u)|0x6000u;
    int fp_write=fault(page,0,rounded) && read_mxcsr()==rounded;
    write_mxcsr(mxcsr);
    report("signal-fpu-state-write",fp_write);
    sigset_t blocked,current,restored;sigemptyset(&blocked);sigaddset(&blocked,SIGUSR1);sigaddset(&blocked,SIGBUS);
    int mask_ok=!pw_wine_pthread_sigmask(SIG_BLOCK,&blocked,NULL) && !pw_wine_pthread_sigmask(SIG_BLOCK,NULL,&current) &&
                sigismember(&current,SIGUSR1)==1 && sigismember(&current,SIGBUS)==1 && sigismember(&current,SIGUSR2)==0 &&
                !pw_wine_pthread_sigmask(SIG_UNBLOCK,&blocked,NULL) && !pw_wine_pthread_sigmask(SIG_BLOCK,NULL,&restored) &&
                sigismember(&restored,SIGUSR1)==0 && sigismember(&restored,SIGBUS)==0;
    memset((void *)&seen,0,sizeof(seen));
    report("signal-mask-translation",mask_ok);
    /* Wine asks for SA_ONSTACK without installing an alternate stack: a thread
     * starts with SS_DISABLE and the handler runs on the current stack. */
    /* libkernel takes the FreeBSD stack_t (sp, size, flags; SS_DISABLE=4), not the SDK's. */
    struct {void *sp;size_t size;int flags;} current_stack={0,0,0};
    typedef int (*StackCall)(const void *,void *);
    int disabled=!((StackCall)(uintptr_t)&sigaltstack)(NULL,&current_stack) && (current_stack.flags&0x4);
    action.sa_flags=SA_SIGINFO|SA_ONSTACK;
    int onstack_ok=disabled && !pw_wine_sigaction(SIGSEGV,&action,NULL) && fault(page,0,0) && seen.trapno==T_PAGEFLT;
    report("signal-onstack-without-altstack",onstack_ok);
    /* Wine installs its per-thread signal stack with the SDK's stack_t. */
    static unsigned char alternate[65536] __attribute__((aligned(16)));
    stack_t installed={0},previous={0};installed.ss_sp=alternate;installed.ss_size=sizeof(alternate);
    int altstack_ok=!pw_wine_sigaltstack(&installed,NULL) && fault(page,0,0) &&
                    seen.handler_sp>(uintptr_t)alternate && seen.handler_sp<=(uintptr_t)alternate+sizeof(alternate) &&
                    !pw_wine_sigaltstack(NULL,&previous) && previous.ss_sp==alternate && previous.ss_size==sizeof(alternate) &&
                    !(previous.ss_flags&SS_DISABLE);
    installed.ss_flags=SS_DISABLE;pw_wine_sigaltstack(&installed,NULL);
    report("signal-installed-altstack",altstack_ok);
    return read_ok && write_ok && fp_read && fp_write && mask_ok && onstack_ok && altstack_ok?0:94;
}
