/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "translator_runtime.h"
#include "pw_x86_hostexec.h"
#include "pw_vm_ps4.h"
#include "pw_pthread_ps4.h"
#include <orbis/libkernel.h>
#include <errno.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { PAGE = 0x4000, TEB_BYTES = 0x1000, ITERATIONS = 64 };

static uintptr_t native_tcb(void)
{
    uintptr_t value;
    __asm__ volatile("movq %%fs:0, %0" : "=r"(value));
    return value;
}

static int translated(PwX86State *state, void *code, const uint8_t *source, size_t bytes)
{
    PwX86Block block;
    int rc = sceKernelMprotect(code, PAGE * 4, 3);
    if (!rc) rc = pw_x86_translate(source, bytes, state->eip, code, PAGE * 4, &block);
    if (!rc && block.source_bytes != bytes) rc = PW_ERR_UNSUPPORTED;
    if (!rc) rc = sceKernelMprotect(code, PAGE * 4, 5);
    return rc ? rc : pw_x86_run_block(state, code);
}

typedef struct TebRendezvous {
    pthread_mutex_t mutex;
    pthread_cond_t condition;
    unsigned arrived, generation;
    int aborted;
} TebRendezvous;

static void abort_rendezvous(TebRendezvous *gate)
{
    if (!gate) return;
    pthread_mutex_lock(&gate->mutex);
    gate->aborted = 1;
    pthread_cond_broadcast(&gate->condition);
    pthread_mutex_unlock(&gate->mutex);
}

static int rendezvous(TebRendezvous *gate)
{
    if (!gate) return 0;
    int rc = pthread_mutex_lock(&gate->mutex);
    if (rc) return rc;
    unsigned generation = gate->generation;
    if (++gate->arrived == 2) {
        gate->arrived = 0;
        gate->generation++;
        rc = pthread_cond_broadcast(&gate->condition);
    } else {
        while (!rc && !gate->aborted && gate->generation == generation)
            rc = pthread_cond_wait(&gate->condition, &gate->mutex);
    }
    if (gate->aborted) rc = 1;
    int unlocked = pthread_mutex_unlock(&gate->mutex);
    return rc ? rc : unlocked;
}

typedef struct TebWorker {
    uintptr_t tcb;
    uint32_t base, marker;
    pthread_key_t key;
    TebRendezvous *gate;
    unsigned completed;
    int rc;
} TebWorker;

static void *teb_worker(void *opaque)
{
    TebWorker *worker = opaque;
    PwVmBackend vm;
    PwVmRegion teb = {0};
    PwX86State *state = calloc(1, sizeof(*state));
    void *code = NULL;
    int rc = state ? pw_vm_ps4_backend(&vm) : PW_ERR_VM;
    worker->tcb = native_tcb();
    if (!worker->tcb) rc = 1;
    if (!rc) rc = pthread_setspecific(worker->key, worker);
    if (!rc) rc = vm.reserve_at(NULL, worker->base, PAGE, PAGE, &teb);
    if (!rc) rc = vm.commit(NULL, &teb, 0, teb.bytes, 3);
    if (!rc) rc = sceKernelMapFlexibleMemory(&code, PAGE * 4, 3, 0);
    if (!rc) {
        uint32_t *words = teb.write_base;
        words[0x18 / 4] = worker->base;
        words[0x30 / 4] = worker->marker;
        pw_guest_fp_init(&state->fp);
        state->fs_base = worker->base;
        state->fs_bytes = TEB_BYTES;
        state->memory_count = 1;
        state->memory[0] = (PwX86Memory){worker->base, worker->base + PAGE, 3};
        const uint8_t access[] = {
            0x64,0x8b,0x3d,0x18,0,0,0,  /* mov edi, fs:[18h] */
            0x64,0xa1,0x30,0,0,0,        /* mov eax, fs:[30h] */
            0x64,0x89,0x0d,0x34,0,0,0    /* mov fs:[34h], ecx */
        };
        for (unsigned i = 0; !rc && i < ITERATIONS; ++i) {
            state->eip = 0x1000;
            state->eflags = 0xad7;
            state->gpr[1] = worker->marker + i;
            errno = 100 + (int)worker->marker;
            rc = rendezvous(worker->gate);
            if (!rc) rc = translated(state, code, access, sizeof(access));
            if (!rc && (state->gpr[7] != worker->base || state->gpr[0] != worker->marker ||
                        words[0x34 / 4] != worker->marker + i || state->eip != 0x1014 ||
                        state->eflags != 0xad7 || native_tcb() != worker->tcb ||
                        pthread_getspecific(worker->key) != worker || errno != 100 + (int)worker->marker)) rc = 1;
            if (!rc) worker->completed++;
            sceKernelUsleep(100);
        }
        /* The mapping is larger than the declared TEB: bounds must be enforced
         * by the translator rather than relying on a host access violation. */
        const uint8_t outside[] = {0x64,0xa3,0,0x10,0,0};
        words[TEB_BYTES / 4] = 0xdecafbad;
        state->eip = 0x2000;
        int refused = rc ? 0 : translated(state, code, outside, sizeof(outside));
        if (!rc && (refused != PW_ERR_PRECONDITION || state->eip != 0x2000 ||
                    words[TEB_BYTES / 4] != 0xdecafbad)) rc = 1;
        const uint8_t overflow[] = {0x64,0xa1,4,0,0,0};
        state->fs_base = 0xfffffffd;
        refused = rc ? 0 : translated(state, code, overflow, sizeof(overflow));
        if (!rc && (refused != PW_ERR_PRECONDITION || state->eip != 0x2000)) rc = 1;
    }
    if (rc) abort_rendezvous(worker->gate);
    if (code && sceKernelMunmap(code, PAGE * 4)) rc = 1;
    if (teb.handle && vm.release(NULL, &teb)) rc = 1;
    if (pthread_setspecific(worker->key, NULL)) rc = 1;
    free(state);
    worker->rc = rc;
    return NULL;
}

int probe_translator_teb(int threaded, char *detail, size_t capacity)
{
    TebWorker workers[2] = {{.base = 0x2a000000, .marker = 17}, {.base = 0x2a004000, .marker = 29}};
    TebRendezvous gate = {.mutex = PTHREAD_MUTEX_INITIALIZER, .condition = PTHREAD_COND_INITIALIZER};
    pthread_key_t key;
    pthread_t threads[2];
    uintptr_t parent_tcb = native_tcb();
    int rc = pthread_key_create(&key, NULL);
    if (rc) return rc;
    workers[0].key = workers[1].key = key;
    unsigned created = 0;
    if (threaded) {
        workers[0].gate = workers[1].gate = &gate;
        for (; created < 2; ++created) {
            rc = pthread_create(&threads[created], NULL, teb_worker, &workers[created]);
            if (rc) break;
        }
        if (created != 2) abort_rendezvous(&gate);
        for (unsigned i = 0; i < created; ++i) if (pthread_join(threads[i], NULL)) rc = 1;
        if (created != 2 || !workers[0].tcb || !workers[1].tcb ||
            workers[0].tcb == workers[1].tcb || workers[0].tcb == parent_tcb ||
            workers[1].tcb == parent_tcb) rc = 1;
    } else {
        teb_worker(&workers[0]);
    }
    unsigned count = threaded ? 2 : 1;
    for (unsigned i = 0; i < count; ++i)
        if (workers[i].rc || workers[i].completed != ITERATIONS) rc = 1;
    if (native_tcb() != parent_tcb || pthread_getspecific(key)) rc = 1;
    if (pw_ps4_pthread_key_delete(key)) rc = 1;
    if (pthread_cond_destroy(&gate.condition) || pthread_mutex_destroy(&gate.mutex)) rc = 1;
    PwPs4VmStats stats = {0};
    if (pw_vm_ps4_stats(&stats) || stats.reservations || stats.committed_bytes) rc = 1;
    snprintf(detail, capacity, "workers=%u iterations=%u,%u native_tls_preserved=%d bounds_and_wrap_refused=%d live=%zu",
             count, workers[0].completed, workers[1].completed, !rc, !rc, stats.reservations);
    return rc;
}

int probe_hostexec(int cache, char *detail, size_t capacity)
{
    PwVmBackend vm;
    PwVmRegion data = {0};
    PwX86HostExec *hostexec = calloc(1, sizeof(*hostexec));
    PwX86State *state = calloc(1, sizeof(*state));
    int rc = hostexec && state ? pw_vm_ps4_backend(&vm) : PW_ERR_VM;
    if (!rc) rc = vm.reserve_at(NULL, 0x2b000000, PAGE, PAGE, &data);
    if (!rc) rc = vm.commit(NULL, &data, 0, data.bytes, 3);
    if (!rc) rc = pw_x86_hostexec_init(hostexec, &vm, PAGE * 4);
    uint32_t mxcsr_before, mxcsr_after;
    uint16_t cw_before, cw_after;
    uintptr_t tcb = native_tcb();
    __asm__ volatile("stmxcsr %0; fnstcw %1" : "=m"(mxcsr_before), "=m"(cw_before));
    if (!rc) {
        pw_guest_fp_init(&state->fp);
        state->eip = 0x1000;
        state->eflags = 0xad7;
        if (!cache) {
            uint32_t *words = data.write_base;
            words[0] = 0x3f80;
            state->gpr[0] = 0x2b000000;
            const uint8_t load_control[] = {0x0f,0xae,0x10};
            rc = pw_x86_hostexec_step(hostexec, state, load_control, sizeof(load_control));
            if (!rc && (state->fp.mxcsr != 0x3f80 || state->eip != 0x1003)) rc = 1;
            const float input[4] = {1.0f, 2.0f, -4.0f, 0.5f};
            const float expected[4] = {2.0f, 4.0f, -8.0f, 1.0f};
            memcpy((uint8_t *)data.write_base + 16, input, sizeof(input));
            memcpy(state->fp.xmm[0], input, sizeof(input));
            state->gpr[0] += 16;
            const uint8_t add_float[] = {0x0f,0x58,0x00};
            if (!rc) rc = pw_x86_hostexec_step(hostexec, state, add_float, sizeof(add_float));
            if (!rc && (memcmp(state->fp.xmm[0], expected, sizeof(expected)) || state->eip != 0x1006 ||
                        state->fp.mxcsr != 0x3f80 || state->eflags != 0xad7)) rc = 1;
            snprintf(detail, capacity, "ldmxcsr_addps=%d mxcsr=0x%x eip=0x%x executed=%llu compiled=%llu",
                     rc, state->fp.mxcsr, state->eip, (unsigned long long)hostexec->executed,
                     (unsigned long long)hostexec->compiled);
        } else {
            uint8_t instruction[] = {0xb8,1,0,0,0};
            for (unsigned i = 0; !rc && i < 3; ++i) {
                instruction[1] = i == 2 ? 2 : 1;
                state->eip = 0x1000;
                rc = pw_x86_hostexec_step(hostexec, state, instruction, sizeof(instruction));
                if (!rc && (state->gpr[0] != instruction[1] || state->eip != 0x1005 ||
                            hostexec->compiled != (i == 2 ? 2u : 1u))) rc = 1;
            }
            snprintf(detail, capacity, "source_change=%d eax=%u executed=%llu compiled=%llu",
                     rc, state->gpr[0], (unsigned long long)hostexec->executed,
                     (unsigned long long)hostexec->compiled);
        }
    }
    __asm__ volatile("stmxcsr %0; fnstcw %1" : "=m"(mxcsr_after), "=m"(cw_after));
    if (mxcsr_before != mxcsr_after || cw_before != cw_after || native_tcb() != tcb) rc = 1;
    size_t used = strlen(detail);
    if (used < capacity) snprintf(detail + used, capacity - used, " host_fp_tls_preserved=%d", !rc);
    if (hostexec && hostexec->initialized && pw_x86_hostexec_destroy(hostexec)) rc = 1;
    if (data.handle && vm.release(NULL, &data)) rc = 1;
    free(hostexec);
    free(state);
    PwPs4VmStats stats = {0};
    if (pw_vm_ps4_stats(&stats) || stats.reservations || stats.committed_bytes) rc = 1;
    return rc;
}
