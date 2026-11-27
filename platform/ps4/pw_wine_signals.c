/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include <signal.h>
#include <pthread.h>
#include <string.h>
#include <stdio.h>
#include <unistd.h>
#include <errno.h>
#include <time.h>
#include <sys/stat.h>
#include <sys/time.h>
#include "pw_wine_context.h"
#include "pw_native_fault_record.h"
int pw_wine_fstat(int,struct stat *);  /* pw_wine_platform.c: the console's stat layout, decoded */
typedef struct PwWireAction {void (*handler)(int,void *,void *);int flags;uint32_t mask[4];} PwWireAction;
_Static_assert(offsetof(PwWireAction,mask)==12,"Orbis sigaction mask");
/* The SDK takes signal numbers, SA_* flags and SIG_* operations from musl's
 * Linux bits/signal.h, while libkernel implements the FreeBSD ABI. Every value
 * crosses this boundary translated; an untranslatable one fails with EINVAL. */
enum {PW_ORBIS_SIGRTMIN=65,PW_ORBIS_SIGRTMAX=126,PW_MUSL_SIGRTMIN=34,PW_MUSL_SIGNALS=65};
static const unsigned char musl_to_orbis[32]={0,1,2,3,4,5,6,10,8,9,30,11,31,13,14,15,
                                              0,20,19,17,18,21,22,16,24,25,26,27,28,23,0,12};
static int to_orbis_signal(int signal)
{
    if(signal>0 && signal<32) return musl_to_orbis[signal];
    if(signal>=PW_MUSL_SIGRTMIN && signal<PW_MUSL_SIGNALS) return signal-PW_MUSL_SIGRTMIN+PW_ORBIS_SIGRTMIN;
    return 0;
}
static int to_musl_signal(int signal)
{
    for(int n=1;n<32;++n) if(musl_to_orbis[n]==signal) return n;
    if(signal>=PW_ORBIS_SIGRTMIN && signal<=PW_ORBIS_SIGRTMAX) {
        int musl=signal-PW_ORBIS_SIGRTMIN+PW_MUSL_SIGRTMIN;
        if(musl<PW_MUSL_SIGNALS) return musl;
    }
    return 0;
}
static const struct {int musl,orbis;} flag_map[]={{SA_NOCLDSTOP,0x8},{SA_NOCLDWAIT,0x20},{SA_SIGINFO,0x40},
    {SA_ONSTACK,0x1},{SA_RESTART,0x2},{SA_NODEFER,0x10},{(int)SA_RESETHAND,0x4}};
enum {PW_MUSL_SA_RESTORER=0x04000000};
static int to_orbis_flags(int flags,int *out)
{
    int result=0;flags&=~PW_MUSL_SA_RESTORER;
    for(size_t n=0;n<sizeof(flag_map)/sizeof(flag_map[0]);++n)
        if(flags&flag_map[n].musl) {result|=flag_map[n].orbis;flags&=~flag_map[n].musl;}
    if(flags) return -1;
    *out=result;return 0;
}
static int to_musl_flags(int flags)
{
    int result=0;
    for(size_t n=0;n<sizeof(flag_map)/sizeof(flag_map[0]);++n)
        if(flags&flag_map[n].orbis) result|=flag_map[n].musl;
    return result;
}
static void to_orbis_mask(const sigset_t *set,uint32_t wire[4])
{
    const unsigned char *bits=(const unsigned char *)set;memset(wire,0,16);
    for(int signal=1;signal<PW_MUSL_SIGNALS;++signal) {
        if(!(bits[(signal-1)/8]&(1u<<((signal-1)%8)))) continue;
        int orbis=to_orbis_signal(signal);
        if(orbis) wire[(orbis-1)/32]|=1u<<((orbis-1)%32);
    }
}
static void to_musl_mask(const uint32_t wire[4],sigset_t *set)
{
    unsigned char *bits=(unsigned char *)set;memset(set,0,sizeof(*set));
    for(int orbis=1;orbis<=128;++orbis) {
        if(!(wire[(orbis-1)/32]&(1u<<((orbis-1)%32)))) continue;
        int signal=to_musl_signal(orbis);
        if(signal) bits[(signal-1)/8]|=1u<<((signal-1)%8);
    }
}
static int to_orbis_how(int how)
{
    switch(how) {case SIG_BLOCK:return 1;case SIG_UNBLOCK:return 2;case SIG_SETMASK:return 3;default:return 0;}
}
typedef void (*PwHandler)(int,void *,void *);
static PwHandler handlers[129];
static void trampoline(int signal,void *info,void *context)
{
    PwHandler handler=signal>0 && signal<129?handlers[signal]:NULL;
    if(handler) handler(to_musl_signal(signal),info,context);
}
static int special(PwHandler handler) {return (uintptr_t)handler<=1;}

/* OrbisDesk W136, adapted from prospero-win patch 0883: native 32-bit code runs with
 * the guest TEB as FS base, while libkernel's signal wrapper finds its thread through
 * %fs. In raw mode the kernel calls pw_native_signal_entry directly (sigaction is the
 * system call itself, issued through the syscall instruction of libkernel's getppid
 * stub, as prospero-win does), and the entry puts the host FS base back before any C. */
enum {PW_SYS_GETPID=20,PW_SYS_GETPPID=39,PW_SYS_SIGACTION=416,PW_STUB_SYSCALL=10};
_Static_assert(offsetof(PwOrbisUcontext,uc_mcontext.mc_cs)==232,"Orbis CS offset");
_Static_assert(offsetof(PwOrbisUcontext,uc_mcontext.mc_fsbase)==1152,"Orbis FS base offset");
_Static_assert(offsetof(PwOrbisUcontext,stack.ptr)==1224 && offsetof(PwOrbisUcontext,stack.size)==1232 &&
               offsetof(PwOrbisUcontext,stack.flags)==1240,"Orbis uc_stack");
extern long pw_native_syscall_at(uintptr_t entry,long number,long a1,long a2,long a3);
__asm__(".text\n.globl pw_native_syscall_at\n.hidden pw_native_syscall_at\n.type pw_native_syscall_at,@function\n"
        "pw_native_syscall_at:\n\t"
        "movq %rsi,%rax\n\tmovq %rdi,%r11\n\tmovq %rdx,%rdi\n\tmovq %rcx,%rsi\n\tmovq %r8,%rdx\n\t"
        "subq $8,%rsp\n\tcallq *%r11\n\taddq $8,%rsp\n\tret\n"
        ".size pw_native_syscall_at,.-pw_native_syscall_at\n");
__attribute__((visibility("hidden"))) uintptr_t pw_native_raw_syscall;
/* W253: a 32-bit thread's signal that the entry below cannot hand to Wine ends the title (label 9); it leaves a
 * line in the run log first (native/wine_hardware.c sets the descriptor). This runs on the guest's FS base:
 * no libc, no TLS, only the raw write system call. */
__attribute__((visibility("hidden"))) int pw_native_log_fd=-1;
__attribute__((visibility("hidden"))) void pw_native_signal_lost(long signal,const PwOrbisUcontext *context);
__attribute__((visibility("hidden"),no_stack_protector)) void pw_native_signal_lost(long signal,const PwOrbisUcontext *context)
{
    static char text[320];
    static const char head[]="PWNATIVE lost signal=",digits[]="0123456789abcdef",
                      tail[]=": a signal in 32-bit code with no host FS base; the title exits (127)\n";
    static const char *const names[6]={"",", cs=",", rip=",", rsp=",", addr=",", fsbase="};
    const PwOrbisMcontext *mc=&context->uc_mcontext;
    uint64_t values[6];
    unsigned n=0,i,j;

    if(pw_native_log_fd<0) return;
    values[0]=(uint64_t)signal;values[1]=mc->mc_cs;values[2]=mc->mc_rip;values[3]=mc->mc_rsp;
    values[4]=mc->mc_addr;values[5]=mc->mc_fsbase;
    for(j=0;head[j];j++) text[n++]=head[j];
    for(i=0;i<6;i++) {
        for(j=0;names[i][j];j++) text[n++]=names[i][j];
        text[n++]='0';text[n++]='x';
        for(j=0;j<16;j++) text[n++]=digits[(values[i]>>(60-4*j))&15];
    }
    for(j=0;tail[j];j++) text[n++]=tail[j];
    pw_native_syscall_at(pw_native_raw_syscall,4 /* SYS_write */,pw_native_log_fd,(long)text,(long)n);
}
static int raw_mode;
/* 04.81 (W303 run-0125/0127/0128, 04.78: the title ended with no line soon after Half-Life ended): a fault that
 * Wine's handler cannot take ends the title silently (the kernel ends it when the handler faults again). Two cases
 * leave a line in the run log first, through the raw write as above, each once per thread and before Wine's handler
 * runs: a fault on a thread that is not on its signal stack (a native thread of RADV, the audio mixer or the
 * compositor; Wine's handler finds its thread data through that stack), and a fault while this thread is still in
 * the handler of an earlier one. Nothing else changes: Wine's handler gets every signal as before. Faults of Wine
 * threads on their signal stack (every PE exception) are not logged. */
int pw_native_fault_diag;  /* 04.83: set by the title's main (native/wine_hardware.c) only */
/* 04.84 (run-0180 of 20261125T232346Z: with 04.83's gate the separate-process child still stopped right after its
 * drive mapping): no thread-local storage at all in this object, which pop-wine-child.prx shares; process-wide
 * state instead, so "in a fault handler" means any thread's, and each line is logged once per process */
static volatile int pw_fault_depth,pw_fault_reported;
static volatile uint64_t pw_fault_first_rip,pw_fault_first_addr;
static unsigned pw_native_fault_snapshots,pw_native_fault_off_stack,pw_native_fault_sequence;
static void pw_native_fault_line(const char *head,long signal,const PwOrbisUcontext *context,uint64_t extra_rip,
                                 uint64_t extra_addr)
{
    static const char digits[]="0123456789abcdef";
    static const char *const names[7]={" signal="," rip="," rsp="," addr="," fsbase="," first_rip="," first_addr="};
    char text[320];
    const PwOrbisMcontext *mc=&context->uc_mcontext;
    uint64_t values[7];
    unsigned n=0,i,j,count=extra_rip||extra_addr?7u:5u;

    if(pw_native_log_fd<0) return;
    values[0]=(uint64_t)signal;values[1]=mc->mc_rip;values[2]=mc->mc_rsp;values[3]=mc->mc_addr;
    values[4]=mc->mc_fsbase;values[5]=extra_rip;values[6]=extra_addr;
    for(j=0;head[j]&&n<80;j++) text[n++]=head[j];
    for(i=0;i<count;i++) {
        for(j=0;names[i][j];j++) text[n++]=names[i][j];
        text[n++]='0';text[n++]='x';
        for(j=0;j<16;j++) text[n++]=digits[(values[i]>>(60-4*j))&15];
    }
    text[n++]='\n';
    pw_native_syscall_at(pw_native_raw_syscall,4 /* SYS_write */,pw_native_log_fd,(long)text,(long)n);
}
static int pw_fault_signal(int signal) {return signal==4||signal==8||signal==10||signal==11;}  /* Orbis ILL FPE BUS SEGV */
static int pw_on_signal_stack(const PwOrbisUcontext *context)
{
    uintptr_t sp=(uintptr_t)__builtin_frame_address(0),base=(uintptr_t)context->stack.ptr;
    return !(context->stack.flags&4 /* SS_DISABLE */)&&base&&sp>=base&&sp-base<context->stack.size;
}
/* The TEB of a Wine thread on its signal stack: the first word of the 64 KiB block, as pw_native_signal_entry and
 * Wine's get_current_thread_data read it. Only called on that stack. */
__attribute__((noinline)) static const uint64_t *pw_native_signal_teb(void)
{
    uintptr_t block=(uintptr_t)__builtin_frame_address(0)&~(uintptr_t)0xffff;
    uintptr_t teb=*(const uintptr_t *)block;
    return teb>=0x10000 && teb<0x800000000000ull && !(teb&7)?(const uint64_t *)teb:NULL;
}
/* THAW 04.90: the 1 KiB record has its own frame. Inline, the dispatcher reserved it (sub $0x4c8,%rsp) for every
 * signal, Wine's included, where 04.87 took it only for a snapshot. */
__attribute__((noinline)) static void pw_native_fault_snapshot(int signal,const PwOrbisUcontext *uc)
{
    char record[PW_NATIVE_FAULT_RECORD_BYTES];
    unsigned sequence=__atomic_add_fetch(&pw_native_fault_sequence,1,__ATOMIC_RELAXED);
    unsigned bytes=pw_native_fault_record(record,sizeof(record),sequence,signal,&uc->uc_mcontext);
    pw_native_syscall_at(pw_native_raw_syscall,4 /* SYS_write */,pw_native_log_fd,(long)record,(long)bytes);
}
__attribute__((visibility("hidden"))) void pw_native_signal_dispatch(int signal,void *info,void *context);
void pw_native_signal_dispatch(int signal,void *info,void *context)
{
    const PwOrbisUcontext *uc=context;

    /* 04.83 (run-0169 of 20261125T220642Z: 04.81's lines below made every separate-process child die right after
     * its drive mapping, with no line: the child is a PRX, whose thread-local variables the handler cannot reach):
     * the title's main sets this; the child never touches the thread-local state */
    if(!pw_native_fault_diag || !pw_fault_signal(signal)) {trampoline(signal,info,context);return;}
    /* Alice 04.87: Wine returns native pipeline faults as c0000005, bypassing
     * PWFAULT. Preserve the first native register contexts even on Wine's signal
     * stack. The PRX leaves diagnostics disabled; no new thread-local state. */
    /* W303 run-0207/0208 (04.87, symbolized: wineserver get_next_timeout and malloc): the fatal faults were on the
     * server thread, off Wine's signal stack, where Wine's handler faults again and the title ends. Those get
     * their own budget of snapshots, so handled faults earlier in the session cannot use it up, and need not be
     * in the title's code. The sequence number counts every snapshot. */
    int off_stack=!pw_on_signal_stack(uc);
    /* THAW 04.90: a stack overflow (stack pointer below the TEB's limit) in any code is fatal too: same budget */
    int fatal=off_stack||pw_native_fault_below_stack(uc->uc_mcontext.mc_rsp,pw_native_signal_teb());
    unsigned *budget=fatal?&pw_native_fault_off_stack:&pw_native_fault_snapshots;
    unsigned limit=fatal?PW_NATIVE_FAULT_OFF_STACK_LIMIT:PW_NATIVE_FAULT_RECORD_LIMIT;
    if(pw_native_log_fd>=0 &&
       (fatal || pw_native_fault_in_title(uc->uc_mcontext.mc_rip,(uintptr_t)&pw_native_signal_dispatch)) &&
       __atomic_load_n(budget,__ATOMIC_RELAXED)<limit && __atomic_add_fetch(budget,1,__ATOMIC_RELAXED)<=limit)
        pw_native_fault_snapshot(signal,uc);
    if(pw_fault_depth&&!(pw_fault_reported&2)) {
        pw_fault_reported|=2;
        pw_native_fault_line("PWNATIVE fault in a fault handler:",signal,uc,pw_fault_first_rip,pw_fault_first_addr);
    }
    if(!(pw_fault_reported&1)&&off_stack) {
        pw_fault_reported|=1;
        pw_native_fault_line("PWNATIVE fault off Wine's signal stack (a native thread?):",signal,uc,0,0);
    }
    pw_fault_first_rip=uc->uc_mcontext.mc_rip;pw_fault_first_addr=uc->uc_mcontext.mc_addr;
    __atomic_add_fetch(&pw_fault_depth,1,__ATOMIC_RELAXED);
    trampoline(signal,info,context);
    __atomic_sub_fetch(&pw_fault_depth,1,__ATOMIC_RELAXED);
}
/* rdi=signal, rsi=siginfo, rdx=ucontext, on the stack the kernel chose. Frame:
 * -8 signal, -16 info, -24 context, -32 FS base at entry, -40 host FS base (0: none),
 * -48 CS at entry. The host FS base of a Wine thread is in its TEB at 0x348
 * (amd64_thread_data, signal_x86_64.c). The FS base is put back on the way out, except
 * when the handler sent a thread interrupted in 32-bit code (CS 0x33) to 64-bit code
 * (Wine's exception dispatch): that one continues on the host FS, in the live register
 * and in the frame the kernel restores. */
extern void pw_native_signal_entry(int,void *,void *);
__asm__(".text\n.globl pw_native_signal_entry\n.hidden pw_native_signal_entry\n.type pw_native_signal_entry,@function\n"
        "pw_native_signal_entry:\n\t"
        "pushq %rbp\n\tmovq %rsp,%rbp\n\tsubq $48,%rsp\n\t"
        "movq %rdi,-8(%rbp)\n\tmovq %rsi,-16(%rbp)\n\tmovq %rdx,-24(%rbp)\n\t"
        "movq $0,-40(%rbp)\n\tmovzwq 232(%rdx),%rax\n\tmovq %rax,-48(%rbp)\n\tcld\n\t"
        /* on Wine's signal stack (the kernel's uc_stack, not disabled) the 64 KiB block
         * starts with the thread's TEB pointer, as Wine's get_current_thread_data reads it */
        "testl $4,1240(%rdx)\n\tjnz 2f\n\t"
        "movq %rsp,%rax\n\tsubq 1224(%rdx),%rax\n\tjb 2f\n\tcmpq 1232(%rdx),%rax\n\tjae 2f\n\t"
        "movq %rsp,%rax\n\tandq $-65536,%rax\n\tmovq (%rax),%rax\n\ttestq %rax,%rax\n\tjz 2f\n\t"
        "movq 0x348(%rax),%rax\n\ttestq %rax,%rax\n\tjz 2f\n\tmovq %rax,-40(%rbp)\n\t"
        "movl $128,%edi\n\tleaq -32(%rbp),%rsi\n\tcall sysarch@PLT\n\ttestl %eax,%eax\n\tjnz 9f\n\t"
        "movq -32(%rbp),%rax\n\tcmpq -40(%rbp),%rax\n\tje 3f\n\t"
        "movl $129,%edi\n\tleaq -40(%rbp),%rsi\n\tcall sysarch@PLT\n\ttestl %eax,%eax\n\tjnz 9f\n\tjmp 3f\n"
        /* no host FS known: only 64-bit code on its own FS may get here */
        "2:\n\tcmpq $0x33,-48(%rbp)\n\tje 9f\n"
        "3:\n\tmovq -8(%rbp),%rdi\n\tmovq -16(%rbp),%rsi\n\tmovq -24(%rbp),%rdx\n\t"
        "call pw_native_signal_dispatch\n\t"
        "cmpq $0,-40(%rbp)\n\tje 5f\n\t"
        "movq -32(%rbp),%rax\n\tcmpq -40(%rbp),%rax\n\tje 5f\n\t"
        "movq -24(%rbp),%rdx\n\tcmpq $0x33,-48(%rbp)\n\tjne 4f\n\tcmpw $0x33,232(%rdx)\n\tje 4f\n\t"
        "movq -40(%rbp),%rax\n\tmovq %rax,1152(%rdx)\n\tjmp 5f\n"
        "4:\n\tmovq -32(%rbp),%rax\n\tmovq %rax,1152(%rdx)\n\t"
        "movl $129,%edi\n\tleaq -32(%rbp),%rsi\n\tcall sysarch@PLT\n"
        "5:\n\tleave\n\tret\n"
        /* never run C, or fault again, with an FS base that is not the host's: exit(127) */
        /* W253: the line first (pw_native_signal_lost), then exit(127) */
        "9:\n\tmovq -8(%rbp),%rdi\n\tmovq -24(%rbp),%rsi\n\tcall pw_native_signal_lost\n"
        "8:\n\tmovq pw_native_raw_syscall(%rip),%rdi\n\tmovl $1,%esi\n\tmovl $127,%edx\n\t"
        "call pw_native_syscall_at\n\tjmp 8b\n"
        ".size pw_native_signal_entry,.-pw_native_signal_entry\n");
static int kernel_sigaction(int orbis,const PwWireAction *action,PwWireAction *old)
{
    typedef int (*Call)(int,const void *,void *);
    if(raw_mode) return (int)pw_native_syscall_at(pw_native_raw_syscall,PW_SYS_SIGACTION,orbis,(long)action,(long)old);
    return ((Call)(uintptr_t)&sigaction)(orbis,action,old);
}
/* 04.73 (run-0081 of 20261125T104317Z: vc_redist.x86's MSI extracted all eleven files from cab1.cab, then
 * failed InstallFiles with 1603, "compressed file wasn't installed"): the SDK's futimens and utimensat are stubs
 * that fail with ENOSYS, so every SetFileTime failed, and msi's cabinet_close_file_info returns before marking
 * the file installed. The console kernel has FreeBSD's futimes (system call 206); this issues it through the
 * same libkernel syscall instruction as sigaction above. Without that entry the call still fails with ENOSYS.
 * It is named futimens so that ntdll's file.o (and musl's futimes) bind here, ahead of libc.a's stub. */
int futimens(int fd,const struct timespec times[2])
{
    enum {PW_SYS_FUTIMES=206};
    struct timeval tv[2];
    struct stat st;
    int have_stat=0;
    if(!pw_native_raw_syscall) {fprintf(stderr,"PWFUTIMES fd=%d no_raw_syscall\n",fd);errno=ENOSYS;return -1;}
    for(int i=0;i<2;i++) {
        long nsec=times?times[i].tv_nsec:UTIME_NOW;
        if(nsec==UTIME_NOW) {
            struct timespec now;
            if(clock_gettime(CLOCK_REALTIME,&now)) return -1;
            tv[i].tv_sec=now.tv_sec;tv[i].tv_usec=now.tv_nsec/1000;
        } else if(nsec==UTIME_OMIT) {
            /* 04.75 (run-0100 of 20261125T134217Z: every omitted access time read 0 with garbage nanoseconds,
             * EINVAL): libc's fstat does not decode the console's stat layout; pw_wine_fstat does */
            if(!have_stat) {if(pw_wine_fstat(fd,&st)) return -1;have_stat=1;}
            const struct timespec *kept=i?&st.st_mtim:&st.st_atim;
            tv[i].tv_sec=kept->tv_sec;tv[i].tv_usec=kept->tv_nsec/1000;
        } else {
            if(nsec<0 || nsec>=1000000000L) {errno=EINVAL;return -1;}
            tv[i].tv_sec=times[i].tv_sec;tv[i].tv_usec=nsec/1000;
        }
    }
    int rc=(int)pw_native_syscall_at(pw_native_raw_syscall,PW_SYS_FUTIMES,fd,(long)tv,0);
    /* 04.74 (run-0091 of 20261125T125644Z): a line per call showed the kernel call works with both times given;
     * 04.75 keeps a line for the first 16 failures only */
    static int logged;
    if(rc && __atomic_fetch_add(&logged,1,__ATOMIC_RELAXED)<16) {
        int saved=errno;
        fprintf(stderr,"PWFUTIMES fd=%d rc=%d errno=%d atime=%lld mtime=%lld omit=%d/%d\n",fd,rc,rc?saved:0,
                (long long)tv[0].tv_sec,(long long)tv[1].tv_sec,times && times[0].tv_nsec==UTIME_OMIT,times && times[1].tv_nsec==UTIME_OMIT);
        errno=saved;
    }
    return rc;
}
static PwHandler registered_entry(void) {return raw_mode?(PwHandler)pw_native_signal_entry:trampoline;}
static int is_entry(PwHandler handler) {return handler==trampoline || handler==(PwHandler)pw_native_signal_entry;}
int pw_wine_sigaction(int signal,const struct sigaction *action,struct sigaction *old)
{
    int orbis=to_orbis_signal(signal);
    PwWireAction wire={0},previous={0};
    if(!orbis) {errno=EINVAL;return -1;}
    if(action) {
        PwHandler handler;memcpy(&handler,&action->__sa_handler,sizeof(handler));
        if(to_orbis_flags(action->sa_flags,&wire.flags)) {errno=EINVAL;return -1;}
        wire.handler=special(handler)?handler:registered_entry();to_orbis_mask(&action->sa_mask,wire.mask);
        PwHandler replaced=handlers[orbis];
        if(!special(handler)) handlers[orbis]=handler;
        int rc=kernel_sigaction(orbis,&wire,old?&previous:NULL);
        if(rc) {handlers[orbis]=replaced;return rc;}
        if(old && is_entry(previous.handler)) previous.handler=replaced;
    } else {
        int rc=kernel_sigaction(orbis,NULL,old?&previous:NULL);
        if(rc) return rc;
        if(old && is_entry(previous.handler)) previous.handler=handlers[orbis];
    }
    if(old) {
        memset(old,0,sizeof(*old));memcpy(&old->__sa_handler,&previous.handler,sizeof(previous.handler));
        old->sa_flags=to_musl_flags(previous.flags);to_musl_mask(previous.mask,&old->sa_mask);
    }
    return 0;
}
static int mask_call(void *function,int how,const sigset_t *set,sigset_t *old)
{
    typedef int (*Call)(int,const void *,void *);
    uint32_t wire[4]={0},previous[4]={0};
    int orbis_how=set?to_orbis_how(how):1;
    if(!orbis_how) {errno=EINVAL;return -1;}
    if(set) to_orbis_mask(set,wire);
    int rc=((Call)(uintptr_t)function)(orbis_how,set?wire:NULL,old?previous:NULL);
    if(!rc && old) to_musl_mask(previous,old);
    return rc;
}
/* stack_t is (sp, flags, size) in the SDK and (sp, size, flags) in libkernel;
 * SS_ONSTACK is 1 in both, SS_DISABLE is 2 in musl and 4 in FreeBSD. */
typedef struct PwWireStack {void *sp;size_t size;int flags;} PwWireStack;
int pw_wine_sigaltstack(const stack_t *stack,stack_t *old)
{
    typedef int (*Call)(const void *,void *);
    PwWireStack wire={0},previous={0};
    if(stack) {
        if(stack->ss_flags&~(SS_ONSTACK|SS_DISABLE)) {errno=EINVAL;return -1;}
        wire.sp=stack->ss_sp;wire.size=stack->ss_size;
        wire.flags=(stack->ss_flags&SS_ONSTACK?0x1:0)|(stack->ss_flags&SS_DISABLE?0x4:0);
    }
    int rc=((Call)(uintptr_t)&sigaltstack)(stack?&wire:NULL,old?&previous:NULL);
    if(!rc && old) {
        memset(old,0,sizeof(*old));old->ss_sp=previous.sp;old->ss_size=previous.size;
        old->ss_flags=(previous.flags&0x1?SS_ONSTACK:0)|(previous.flags&0x4?SS_DISABLE:0);
    }
    return rc;
}
int pw_wine_sigprocmask(int how,const sigset_t *set,sigset_t *old)
{return mask_call((void *)&sigprocmask,how,set,old);}
int pw_wine_pthread_sigmask(int how,const sigset_t *set,sigset_t *old)
{return mask_call((void *)&pthread_sigmask,how,set,old);}
/* Internal musl callers use the SDK layout. Keep their real conversion path
 * when the public sigaction entry is supplied by libkernel. */
__attribute__((visibility("hidden")))
int __sigaction(int signal,const struct sigaction *action,struct sigaction *old)
{return pw_wine_sigaction(signal,action,old);}
__attribute__((visibility("hidden")))
int __libc_sigaction(int signal,const struct sigaction *action,struct sigaction *old)
{return pw_wine_sigaction(signal,action,old);}

/* W136: find libkernel's syscall instruction (getppid's stub: "mov $39,%rax; mov %rcx,%r10;
 * syscall; jb error; ret") and prove it runs other calls: getpid and getppid swapped, which
 * only a real syscall instruction answers. Then check, with one raw registration, that the
 * kernel's frame holds this thread's MXCSR and FS base where Wine and the entry read them
 * (FXSAVE at uc+320, FS base at uc+1152). Only then are later registrations raw.
 * Returns 0 when raw mode is on; *detail says what was found either way. */
static volatile int frame_hits;
static volatile uint32_t frame_mxcsr;
static volatile uint64_t frame_fsbase;
static void frame_probe(int signal,void *info,void *context)
{
    (void)signal;(void)info;
    const unsigned char *uc=context;uint32_t mxcsr;uint64_t fsbase;
    memcpy(&mxcsr,uc+320+24,4);memcpy(&fsbase,uc+1152,8);
    frame_mxcsr=mxcsr;frame_fsbase=fsbase;frame_hits++;
}
int pw_wine_native_signals_enable(char *detail,size_t size)
{
    uintptr_t entry=(uintptr_t)&getppid+PW_STUB_SYSCALL;
    long pid=getpid(),ppid=getppid();
    if(pid<=0 || ppid<0 || pid==ppid) {snprintf(detail,size,"pid=%ld ppid=%ld unusable",pid,ppid);return -1;}
    long swapped_pid=pw_native_syscall_at(entry,PW_SYS_GETPID,0,0,0);
    long swapped_ppid=pw_native_syscall_at(entry,PW_SYS_GETPPID,0,0,0);
    if(swapped_pid!=pid || swapped_ppid!=ppid) {
        snprintf(detail,size,"syscall=%p not_proven pid=%ld/%ld ppid=%ld/%ld",(void *)entry,swapped_pid,pid,swapped_ppid,ppid);
        return -1;
    }
    pw_native_raw_syscall=entry;
    uint64_t fsbase=0;
    if(sysarch(128,&fsbase) || !fsbase) {snprintf(detail,size,"syscall=%p no_fsbase",(void *)entry);return -1;}
    PwWireAction probe={0},previous={0};
    probe.handler=frame_probe;probe.flags=0x40; /* SA_SIGINFO */
    const int orbis_sigusr2=31;
    if(pw_native_syscall_at(entry,PW_SYS_SIGACTION,orbis_sigusr2,(long)&probe,(long)&previous)) {
        snprintf(detail,size,"syscall=%p raw_sigaction errno=%d",(void *)entry,errno);return -1;
    }
    sigset_t unblock,mask;sigemptyset(&unblock);sigaddset(&unblock,SIGUSR2);
    pw_wine_pthread_sigmask(SIG_UNBLOCK,&unblock,&mask);
    uint32_t mxcsr,marked;__asm__ volatile("stmxcsr %0":"=m"(mxcsr));
    marked=(mxcsr&~0x6000u)|0x2000u; /* round down: visible and harmless */
    __asm__ volatile("ldmxcsr %0"::"m"(marked));
    pthread_kill(pthread_self(),orbis_sigusr2); /* libkernel: FreeBSD numbering */
    __asm__ volatile("ldmxcsr %0"::"m"(mxcsr));
    pw_wine_pthread_sigmask(SIG_SETMASK,&mask,NULL);
    pw_native_syscall_at(entry,PW_SYS_SIGACTION,orbis_sigusr2,(long)&previous,0);
    int ok=frame_hits==1 && frame_mxcsr==marked && frame_fsbase==fsbase;
    snprintf(detail,size,"syscall=%p hits=%d mxcsr=%#x/%#x fsbase=%#llx/%#llx",(void *)entry,frame_hits,
             (unsigned)frame_mxcsr,(unsigned)marked,(unsigned long long)frame_fsbase,(unsigned long long)fsbase);
    if(!ok) return -1;
    raw_mode=1;
    return 0;
}
int pw_wine_native_signals_active(void) {return raw_mode;}
/* 04.52: never send a thread quit until Wine's actual raw SIGQUIT handler is
 * installed. Reading the current action also excludes a later SIG_DFL/IGN. */
int pw_wine_thread_quit_ready(void)
{
    struct sigaction action;PwHandler handler;
    if(!raw_mode||pw_wine_sigaction(SIGQUIT,NULL,&action))return 0;
    memcpy(&handler,&action.__sa_handler,sizeof(handler));
    return !special(handler)&&handler==handlers[to_orbis_signal(SIGQUIT)];
}
/* W195: pw_wine_thread_kill (pw_wine_threads.c) sends the server's SDK-numbered signal */
int pw_wine_orbis_signal(int signal) {return to_orbis_signal(signal);}
/* W137: the proven ntdll object has no native WoW64 signal protocol: it reports none (0).
 * ntdll's signal_x86_64.c built by tools/build-signal-ps4.py defines the real one. */
__attribute__((weak)) unsigned int __wine_prospero_native_wow64_caps(unsigned int version);
__attribute__((weak)) unsigned int __wine_prospero_native_wow64_caps(unsigned int version) {(void)version;return 0;}
