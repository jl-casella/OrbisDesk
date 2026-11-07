/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef PW_CPU_PS4_H
#define PW_CPU_PS4_H
#include "pw_x86_engine.h"

typedef struct PwPs4Cpu PwPs4Cpu;
typedef struct PwPs4CpuStats {
    uint64_t steps, translated_blocks, translated_instructions, host_attempts, host_steps;
    uint64_t compiles, cache_hits, host_compiles, x87_resets;
} PwPs4CpuStats;

/* Single owner thread. Source spans must remain mapped and immutable until
 * destroy. Fallback currently admits FNINIT (on guest state, no host FP) and
 * only unprefixed ADDPS, LDMXCSR and STMXCSR through hostexec;
 * their memory spans are checked against the logical region table. General
 * native fault conversion and FP exception delivery are not implemented. */
int pw_cpu_ps4_create(PwPs4Cpu **out, const PwVmBackend *backend,
                      PwX86SourceView source_view, void *opaque);
PwX86State *pw_cpu_ps4_state(PwPs4Cpu *cpu);
int pw_cpu_ps4_step(PwPs4Cpu *cpu);
/* stop_pc is a caller-specified boundary, not a simulated Windows exit call.
 * Exhaustion returns PW_ERR_LIMIT; it does not reset caches or retry faults. */
int pw_cpu_ps4_run(PwPs4Cpu *cpu, uint32_t stop_pc, uint32_t max_steps);
int pw_cpu_ps4_stats(PwPs4Cpu *cpu, PwPs4CpuStats *out);
int pw_cpu_ps4_destroy(PwPs4Cpu *cpu);
#endif
