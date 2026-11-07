/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "pw_cpu_ps4.h"
#include "pw_vm_ps4.h"
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

enum { PAGE = 0x4000, DATA = 0x2c000000, PC = 0x1000 };
typedef struct Source {
    const uint8_t *bytes;
    size_t count;
} Source;

static int view(void *opaque, uint32_t pc, const uint8_t **bytes, size_t *count)
{
    Source *source = opaque;
    if (pc < PC || (uint64_t)pc - PC >= source->count) return PW_ERR_NOT_FOUND;
    *bytes = source->bytes + (pc - PC);
    *count = source->count - (pc - PC);
    return PW_OK;
}

typedef struct ForeignUse {
    PwPs4Cpu *cpu;
    int refused;
} ForeignUse;

static void *foreign_use(void *opaque)
{
    ForeignUse *use = opaque;
    PwPs4CpuStats stats;
    use->refused = pw_cpu_ps4_step(use->cpu) == PW_ERR_STATE &&
                   pw_cpu_ps4_run(use->cpu, PC + 1, 2) == PW_ERR_STATE &&
                   !pw_cpu_ps4_state(use->cpu) &&
                   pw_cpu_ps4_stats(use->cpu, &stats) == PW_ERR_STATE &&
                   pw_cpu_ps4_destroy(use->cpu) == PW_ERR_STATE;
    return NULL;
}

int probe_dispatcher(int kind, char *detail, size_t capacity)
{
    static const uint8_t mixed[] = {
        0xb8,0,0,0,0x2c,             /* mov eax, DATA */
        0xb9,0xff,0xff,0xff,0xff,    /* mov ecx, -1 */
        0x83,0xc1,1,                 /* add ecx, 1: CF=ZF=1 */
        0x0f,0xae,0x10,              /* ldmxcsr [eax]: hostexec */
        0xf3,0x0f,0x6f,0x40,0x10,    /* movdqu xmm0, [eax+16] */
        0x0f,0x58,0x40,0x20,         /* addps xmm0, [eax+32]: hostexec */
        0x83,0xd1,41,                /* adc ecx, 41: must consume CF */
        0xf3,0x0f,0x7f,0x40,0x30,    /* movdqu [eax+48], xmm0 */
        0x64,0x89,0x0d,0x34,0,0,0,   /* mov fs:[34h], ecx */
        0x64,0x8b,0x3d,0x18,0,0,0    /* mov edi, fs:[18h] */
    };
    static const uint8_t fault[] = {0x89,0x08};
    static const uint8_t loop[] = {0xeb,0xfe};
    static const uint8_t refused[] = {0xf4};
    static const uint8_t nop[] = {0x90};
    Source source = {kind == 0 ? mixed : kind == 1 ? fault : kind == 2 ? loop : nop,
                     kind == 0 ? sizeof(mixed) : kind == 1 ? sizeof(fault) : kind == 2 ? sizeof(loop) : sizeof(nop)};
    PwVmBackend vm;
    PwVmRegion data = {0};
    PwPs4Cpu *cpu = NULL;
    PwPs4CpuStats stats = {0};
    int rc = pw_vm_ps4_backend(&vm);
    if (!rc) rc = vm.reserve_at(NULL, DATA, PAGE, PAGE, &data);
    if (!rc) rc = vm.commit(NULL, &data, 0, PAGE, 3);
    if (!rc) rc = pw_cpu_ps4_create(&cpu, &vm, view, &source);
    uint32_t mxcsr_before, mxcsr_after;
    uint16_t cw_before, cw_after;
    __asm__ volatile("stmxcsr %0; fnstcw %1" : "=m"(mxcsr_before), "=m"(cw_before));
    if (!rc) {
        PwX86State *state = pw_cpu_ps4_state(cpu);
        state->eip = PC;
        state->fs_base = DATA + 0x1000;
        state->fs_bytes = 0x1000;
        state->gpr[0] = DATA;
        state->gpr[1] = 0xbad;
        state->memory_count = 1;
        state->memory[0] = (PwX86Memory){DATA, DATA + PAGE, kind == 1 ? PW_X86_READ : 3};
        uint32_t *words = data.write_base;
        words[0] = 0x3f80;
        words[(0x1000 + 0x18) / 4] = DATA + 0x1000;
        if (kind == 0) {
            const float input[4] = {1,2,-4,0.5f}, expected[4] = {2,4,-8,1};
            memcpy(words + 4, input, sizeof(input));
            memcpy(words + 8, input, sizeof(input));
            for (unsigned round = 0; !rc && round < 2; ++round) {
                state->eip = PC;
                state->eflags = 2;
                /* Inspect the exact route boundaries before running to the end. */
                rc = pw_cpu_ps4_step(cpu);
                if (!rc && (state->eip != PC + 13 || state->gpr[1] || (state->eflags & 0x41) != 0x41)) rc = 1;
                if (!rc) rc = pw_cpu_ps4_step(cpu);
                if (!rc && (state->eip != PC + 16 || state->fp.mxcsr != 0x3f80 ||
                            (state->eflags & 0x41) != 0x41)) rc = 1;
                if (!rc) rc = pw_cpu_ps4_step(cpu);
                if (!rc && (state->eip != PC + 21 || memcmp(state->fp.xmm[0], input, sizeof(input)))) rc = 1;
                if (!rc) rc = pw_cpu_ps4_step(cpu);
                if (!rc && (state->eip != PC + 25 || memcmp(state->fp.xmm[0], expected, sizeof(expected)) ||
                            (state->eflags & 0x41) != 0x41)) rc = 1;
                if (!rc) rc = pw_cpu_ps4_run(cpu, PC + sizeof(mixed), 4);
                if (!rc && (state->gpr[1] != 42 || state->gpr[7] != DATA + 0x1000 ||
                            words[(0x1000 + 0x34) / 4] != 42 || memcmp(words + 12, expected, sizeof(expected)))) rc = 1;
            }
        } else if (kind == 1) {
            int stopped = pw_cpu_ps4_run(cpu, PC + sizeof(fault), 4);
            if (stopped != PW_ERR_VM || state->eip != PC || words[0] != 0x3f80) rc = 1;
        } else if (kind == 2) {
            int stopped = pw_cpu_ps4_run(cpu, PC + sizeof(loop), 3);
            if (stopped != PW_ERR_LIMIT || state->eip != PC) rc = 1;
            if (pw_cpu_ps4_stats(cpu, &stats) || stats.steps != 3 || stats.host_attempts) rc = 1;
            if (!rc) rc = pw_cpu_ps4_destroy(cpu);
            cpu = NULL;
            source = (Source){refused, sizeof(refused)};
            if (!rc) rc = pw_cpu_ps4_create(&cpu, &vm, view, &source);
            if (!rc) {
                state = pw_cpu_ps4_state(cpu);
                state->eip = PC;
                stopped = pw_cpu_ps4_run(cpu, PC + 1, 3);
                if (stopped != PW_ERR_UNSUPPORTED || state->eip != PC) rc = 1;
                state->eip = PC - 1;
                stopped = pw_cpu_ps4_step(cpu);
                if (stopped != PW_ERR_NOT_FOUND || state->eip != PC - 1) rc = 1;
            }
        } else {
            ForeignUse use = {cpu, 0};
            pthread_t thread;
            rc = pthread_create(&thread, NULL, foreign_use, &use);
            if (!rc && pthread_join(thread, NULL)) rc = 1;
            if (!rc && !use.refused) rc = 1;
            if (!rc) rc = pw_cpu_ps4_run(cpu, PC + sizeof(nop), 1);
        }
        if (cpu && pw_cpu_ps4_stats(cpu, &stats)) rc = 1;
        if (!rc && kind == 0 && (stats.translated_blocks != 6 || stats.host_steps != 4 ||
                                stats.host_compiles != 2 || !stats.cache_hits)) rc = 1;
        if (!rc && kind == 1 && stats.host_attempts) rc = 1;
    }
    __asm__ volatile("stmxcsr %0; fnstcw %1" : "=m"(mxcsr_after), "=m"(cw_after));
    if (mxcsr_before != mxcsr_after || cw_before != cw_after) rc = 1;
    if (cpu && pw_cpu_ps4_destroy(cpu)) rc = 1;
    if (data.handle && vm.release(NULL, &data)) rc = 1;
    PwPs4VmStats memory = {0};
    if (pw_vm_ps4_stats(&memory) || memory.reservations || memory.committed_bytes) rc = 1;
    snprintf(detail, capacity, "kind=%d rc=%d steps=%llu blocks=%llu host=%llu attempts=%llu compiles=%llu hits=%llu host_compiles=%llu live=%zu",
             kind, rc, (unsigned long long)stats.steps, (unsigned long long)stats.translated_blocks,
             (unsigned long long)stats.host_steps, (unsigned long long)stats.host_attempts, (unsigned long long)stats.compiles,
             (unsigned long long)stats.cache_hits, (unsigned long long)stats.host_compiles, memory.reservations);
    return rc;
}
