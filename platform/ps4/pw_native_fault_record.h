/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef PW_NATIVE_FAULT_RECORD_H
#define PW_NATIVE_FAULT_RECORD_H
#include "pw_wine_context.h"

/* A Unix-call fault can be returned as an NTSTATUS without entering the PE
 * exception dispatcher. Capture its original registers before Wine handles it.
 * No allocation, locks, TLS, stdio, stack walking or fault-address dereference.
 * This is a register snapshot, not a full core dump. */
#define PW_NATIVE_FAULT_RECORD_LIMIT 32u
/* Faults off Wine's signal stack (fatal: Wine's handler faults again) have their own budget. */
#define PW_NATIVE_FAULT_OFF_STACK_LIMIT 8u
#define PW_NATIVE_FAULT_RECORD_BYTES 1024u
static inline unsigned pw_native_fault_record(char *out, unsigned capacity,
        unsigned sequence, int signal, const PwOrbisMcontext *mc)
{
    static const char hex[] = "0123456789abcdef";
    static const char prefix[] = "PWNATIVE snapshot v=1";
    static const char *const names[] = {
        "n", "signal", "rip", "rsp", "rbp", "addr", "err", "cs", "rflags",
        "fsbase", "gsbase", "rax", "rbx", "rcx", "rdx", "rsi", "rdi",
        "r8", "r9", "r10", "r11", "r12", "r13", "r14", "r15"
    };
    const uint64_t values[] = {
        sequence, (unsigned)signal, mc->mc_rip, mc->mc_rsp, mc->mc_rbp,
        mc->mc_addr, mc->mc_err, mc->mc_cs, mc->mc_rflags, mc->mc_fsbase,
        mc->mc_gsbase, mc->mc_rax, mc->mc_rbx, mc->mc_rcx, mc->mc_rdx,
        mc->mc_rsi, mc->mc_rdi, mc->mc_r8, mc->mc_r9, mc->mc_r10,
        mc->mc_r11, mc->mc_r12, mc->mc_r13, mc->mc_r14, mc->mc_r15
    };
    unsigned n = 0;
    if (capacity < PW_NATIVE_FAULT_RECORD_BYTES) return 0;
    for (unsigned i = 0; prefix[i]; ++i) out[n++] = prefix[i];
    for (unsigned i = 0; i < sizeof(values)/sizeof(values[0]); ++i) {
        out[n++] = ' ';
        for (unsigned j = 0; names[i][j]; ++j) out[n++] = names[i][j];
        out[n++] = '='; out[n++] = '0'; out[n++] = 'x';
        for (unsigned j = 0; j < 16; ++j)
            out[n++] = hex[(values[i] >> (60 - 4*j)) & 15];
    }
    out[n++] = '\n';
    return n;
}

/* The linked title's native code occupies its own 4 GiB address window. Use
 * the dispatcher's actual relocated address, never a hardcoded build base.
 * PE faults in other windows still follow Wine's existing diagnostics. */
static inline int pw_native_fault_in_title(uint64_t ip, uintptr_t dispatcher)
{
    return ip && (ip >> 32) == ((uint64_t)dispatcher >> 32);
}

/* THAW 04.90 (W303 run-0239/0240/0241): the title ended with "invalid frame ... Exception frame is not in stack
 * limits", 0x8a30 below the thread's stack limit each time, and no snapshot (the code was not the title's). A fault
 * whose stack pointer is already below the thread's StackLimit (NT_TIB at 0x10 of its TEB) has overflowed the stack:
 * Wine cannot dispatch it. Growth through a guard page keeps the stack pointer above the limit. */
static inline int pw_native_fault_below_stack(uint64_t sp, const uint64_t *teb)
{
    uint64_t limit = teb ? teb[2] : 0;
    return limit && sp < limit && limit - sp <= 0x100000u;
}
#endif
