/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef PW_WINE_CONTEXT_H
#define PW_WINE_CONTEXT_H
#include <stddef.h>
#include <stdint.h>
#include <errno.h>
#undef sa_sigaction
#define sa_sigaction __sa_handler.__sa_sigaction
#undef sa_handler
#define sa_handler __sa_handler.sa_handler
/* Orbis wire layout, independently declared from SDK's Linux ucontext.
 * Reference: shadPS4 exception.h; RIP prefix already measured in the probes.
 * FP offsets are structural hypotheses until the runtime FP probe passes. */
typedef struct PwOrbisMcontext {
    uint64_t mc_onstack,mc_rdi,mc_rsi,mc_rdx,mc_rcx,mc_r8,mc_r9,mc_rax,mc_rbx,mc_rbp;
    uint64_t mc_r10,mc_r11,mc_r12,mc_r13,mc_r14,mc_r15;
    uint32_t mc_trapno;uint16_t mc_fs,mc_gs;uint64_t mc_addr;
    uint32_t mc_flags;uint16_t mc_es,mc_ds;
    uint64_t mc_err,mc_rip,mc_cs,mc_rflags,mc_rsp,mc_ss;
    uint64_t mc_len,mc_fpformat,mc_ownedfp,mc_lbrfrom,mc_lbrto,mc_aux1,mc_aux2;
    uint64_t mc_fpstate[104],mc_fsbase,mc_gsbase,mc_spare[6];
} PwOrbisMcontext;
typedef struct PwOrbisUcontext {
    uint32_t mask[4],reserved[12];PwOrbisMcontext uc_mcontext;
    struct PwOrbisUcontext *link;
    struct {void *ptr;uint64_t size;int flags,padding;} stack;
    int flags,spare[4],tail[3];
} PwOrbisUcontext;
_Static_assert(sizeof(PwOrbisUcontext)==0x500,"Orbis ucontext size");
_Static_assert(offsetof(PwOrbisUcontext,uc_mcontext.mc_rip)==224,"Orbis RIP offset");
_Static_assert(offsetof(PwOrbisUcontext,uc_mcontext.mc_fpstate)==320,"Orbis FP offset");
/* FreeBSD amd64 trap ABI numbers, checked against releng/9.0 machine/trap.h.
 * These describe the target ABI, not a promise that an emulator populates it. */
enum {T_PRIVINFLT=1,T_BPTFLT=3,T_ARITHTRAP=6,T_PROTFLT=9,T_TRCTRAP=10,T_PAGEFLT=12,
      T_ALIGNFLT=14,T_DIVIDE=18,T_NMI=19,T_OFLOW=20,T_BOUND=21,T_DNA=22,T_DOUBLEFLT=23,
      T_FPOPFLT=24,T_TSSFLT=25,T_SEGNPFLT=26,T_STKFLT=27,T_MCHK=28,T_XMMFLT=29};
extern int sysarch(int,void *);
static inline int pw_wine_get_gsbase(void **out) {return sysarch(130,out);}
static inline int pw_wine_set_gsbase(void *base)
{
    void *observed=NULL;
    if(sysarch(131,&base) || pw_wine_get_gsbase(&observed)) return -1;
    if(observed!=base) {errno=ENOTSUP;return -1;}
    return 0;
}
#endif
