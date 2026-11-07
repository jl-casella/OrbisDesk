/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* W135, phase 5 of the PE32 plan: can this console run 32-bit code natively?
 *
 * prospero-win's wow64native runs i386 code in the CPU's compatibility mode instead of
 * translating it (wowprospero): code selector 0x33, 64-bit selector 0x43, FreeBSD's amd64
 * GDT layout. Before porting it, this probe asks the PS4 kernel the one question it depends
 * on: a far return to 0x33 runs one 32-bit instruction (it stores a marker), a far return
 * to 0x43 comes back. Code, data and stack are in one page below 4 GiB, as 32-bit code
 * needs. A fault ends the attempt through siglongjmp and is reported, not hidden.
 *
 * It runs once per build: a marker file is written before the attempt, so a probe that
 * takes the title down cannot do so on every start. */
#include <errno.h>
#include <fcntl.h>
#include <setjmp.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

extern int pw_wine_sigaction(int,const struct sigaction *,struct sigaction *);
static sigjmp_buf probe_jump;
static volatile int probe_signal;

static void probe_handler(int signal,siginfo_t *info,void *context)
{
    (void)info;(void)context;
    probe_signal=signal;
    siglongjmp(probe_jump,1);
}

/* Returns 1 when 32-bit code ran and came back, 0 when it could not; *detail says why. */
int pw_compat32_probe(const char *marker,char *detail,size_t size)
{
    int fd=open(marker,O_CREAT|O_EXCL|O_WRONLY,0644);
    if(fd<0) {snprintf(detail,size,"skipped marker=%s errno=%d",marker,errno);return 0;}
    write(fd,"attempt\n",8);fsync(fd);close(fd);

    /* one RWX page below 4 GiB: 32-bit code at +0, 64-bit return stub at +0x40,
     * result/saved state at +0x80, stack top at +0xff0 */
    uint8_t *page=MAP_FAILED;
    for(uintptr_t hint=0x30000000;hint<0x70000000 && page==MAP_FAILED;hint+=0x1000000)
        page=mmap((void *)hint,0x1000,PROT_READ|PROT_WRITE|PROT_EXEC,MAP_PRIVATE|MAP_ANON|MAP_FIXED,-1,0);
    if(page==MAP_FAILED) {snprintf(detail,size,"no_low_rwx_page errno=%d",errno);return 0;}
    uint32_t base=(uint32_t)(uintptr_t)page;
    volatile uint32_t *result=(volatile uint32_t *)(page+0x80);
    volatile uint64_t *saved_rsp=(volatile uint64_t *)(page+0x88);
    volatile uint64_t *continuation=(volatile uint64_t *)(page+0x90);
    uint8_t *code=page;
    /* 32-bit: mov dword [base+0x80], 0x32BEEF32 ; retf (pops EIP, CS: the 64-bit stub, 0x43) */
    code[0]=0xc7;code[1]=0x05;memcpy(code+2,&(uint32_t){base+0x80},4);memcpy(code+6,&(uint32_t){0x32beef32},4);
    code[10]=0xcb;
    /* 64-bit at +0x40: mov rsp, [abs32 saved_rsp] ; jmp [abs32 continuation] */
    uint8_t *stub=page+0x40;
    stub[0]=0x48;stub[1]=0x8b;stub[2]=0x24;stub[3]=0x25;memcpy(stub+4,&(uint32_t){base+0x88},4);
    stub[8]=0xff;stub[9]=0x24;stub[10]=0x25;memcpy(stub+11,&(uint32_t){base+0x90},4);
    /* 32-bit stack: [top] = EIP of the 64-bit stub, [top+4] = 0x43 */
    uint32_t top=base+0xfe0;
    memcpy(page+0xfe0,&(uint32_t){base+0x40},4);memcpy(page+0xfe4,&(uint32_t){0x43},4);
    *result=0;

    struct sigaction action,old[3];memset(&action,0,sizeof(action));
    /* the SDK's sa_sigaction macro names a member its union does not have */
    action.__sa_handler.__sa_sigaction=probe_handler;action.sa_flags=SA_SIGINFO;sigemptyset(&action.sa_mask);
    static const int signals[3]={SIGSEGV,SIGBUS,SIGILL};
    for(int i=0;i<3;i++) pw_wine_sigaction(signals[i],&action,&old[i]);
    probe_signal=0;
    uint16_t cs=0;__asm__ volatile("mov %%cs,%0":"=r"(cs));
    if(!sigsetjmp(probe_jump,1)) {
        __asm__ volatile(
            "lea 1f(%%rip),%%rax\n\t"
            "mov %%rax,(%[cont])\n\t"
            "mov %%rsp,(%[saved])\n\t"
            "mov %[top],%%rsp\n\t"
            "sub $16,%%rsp\n\t"
            "movq %[code32],(%%rsp)\n\t"
            "movq $0x33,8(%%rsp)\n\t"
            "lretq\n"
            "1:\n\t"
            :
            :[cont]"r"(continuation),[saved]"r"(saved_rsp),[top]"r"((uint64_t)top),[code32]"r"((uint64_t)base)
            /* the 32-bit code runs one mov and a retf: callee-saved registers are untouched */
            :"rax","rcx","rdx","rsi","rdi","r8","r9","r10","r11","memory","cc");
    }
    uint16_t cs_after=0;__asm__ volatile("mov %%cs,%0":"=r"(cs_after));
    for(int i=0;i<3;i++) pw_wine_sigaction(signals[i],&old[i],NULL);
    int ok=*result==0x32beef32 && !probe_signal && cs_after==cs;
    snprintf(detail,size,"page=%p cs=%#x cs_after=%#x result=%#x signal=%d",(void *)page,cs,cs_after,*result,probe_signal);
    munmap(page,0x1000);
    fd=open(marker,O_WRONLY|O_TRUNC);
    if(fd>=0){char text[200];int n=snprintf(text,sizeof(text),"%s %s\n",ok?"native32=1":"native32=0",detail);write(fd,text,(size_t)n);close(fd);}
    return ok;
}
