/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "pw_cpu_ps4.h"
#include "pw_x86_hostexec.h"
#include <pthread.h>
#include <string.h>

enum { CACHE_ENTRIES = 256, ENGINE_BYTES = 0x100000, HOST_BYTES = 0x10000 };
struct PwPs4Cpu {
    pthread_t owner;
    PwVmBackend backend;
    PwVmRegion storage;
    PwX86SourceView source_view;
    void *opaque;
    PwX86State state;
    PwX86Engine engine;
    PwX86HostExec host;
    PwX86CacheEntry entries[CACHE_ENTRIES];
    PwPs4CpuStats stats;
};

static int owned(const PwPs4Cpu *cpu)
{
    return cpu && pthread_equal(cpu->owner, pthread_self());
}

int pw_cpu_ps4_create(PwPs4Cpu **out, const PwVmBackend *backend,
                      PwX86SourceView source_view, void *opaque)
{
    if (!out || !backend || !source_view || !pw_vm_backend_valid(backend)) return PW_ERR_PRECONDITION;
    PwVmRegion storage = {0};
    int rc = backend->reserve(backend->context, sizeof(PwPs4Cpu), backend->page_bytes, &storage);
    if (rc) return rc;
    rc = backend->commit(backend->context, &storage, 0, storage.bytes, PW_PROT_READ | PW_PROT_WRITE);
    if (rc) { backend->release(backend->context, &storage); return rc; }
    PwPs4Cpu *cpu = storage.write_base;
    memset(cpu, 0, sizeof(*cpu));
    cpu->owner = pthread_self();
    cpu->backend = *backend;
    cpu->storage = storage;
    cpu->source_view = source_view;
    cpu->opaque = opaque;
    rc = pw_x86_engine_init(&cpu->engine, &cpu->backend, cpu->entries,
                               CACHE_ENTRIES, ENGINE_BYTES, 1, source_view, opaque);
    if (!rc) rc = pw_x86_hostexec_init(&cpu->host, &cpu->backend, HOST_BYTES);
    if (rc) {
        if (cpu->engine.initialized) pw_x86_engine_destroy(&cpu->engine);
        backend->release(backend->context, &storage);
        return rc;
    }
    pw_guest_fp_init(&cpu->state.fp);
    cpu->state.eflags = 2;
    *out = cpu;
    return PW_OK;
}

PwX86State *pw_cpu_ps4_state(PwPs4Cpu *cpu)
{
    return owned(cpu) ? &cpu->state : NULL;
}

static int check_host_operand(PwX86State *state, const uint8_t *source, size_t bytes)
{
    PwX86HostExecPlan plan;
    int rc = pw_x86_hostexec_plan(state, source, bytes, &plan);
    if (rc) return rc;
    unsigned width = 0, permission = PW_X86_READ;
    /* Deliberately bounded fallback until more operand forms are audited.
     * Prefixes and implicit memory/stack operands are refused. */
    if (bytes < 3 || source[0] != 0x0f) return PW_ERR_UNSUPPORTED;
    if (source[1] == 0x58) {
        if (plan.mem_form) width = 16;
    } else if (source[1] == 0xae && plan.mem_form) {
        unsigned group = (source[2] >> 3) & 7;
        if (group != 2 && group != 3) return PW_ERR_UNSUPPORTED;
        width = 4;
        if (group == 3) permission = PW_X86_WRITE;
    } else return PW_ERR_UNSUPPORTED;
    uint64_t cursor = plan.address, end = cursor + width;
    if (end > 0x100000000ull || state->memory_count > PW_X86_MEMORY_REGIONS) goto fault;
    while (cursor < end) {
        uint64_t covered = cursor;
        for (unsigned i = 0; i < state->memory_count; ++i) {
            const PwX86Memory *m = &state->memory[i];
            if (m->low <= cursor && m->high > cursor && (m->permissions & permission) == permission && m->high > covered)
                covered = m->high;
        }
        if (covered == cursor) goto fault;
        cursor = covered < end ? covered : end;
    }
    if (width && source[1] == 0xae && permission == PW_X86_READ) {
        uint32_t mxcsr;
        memcpy(&mxcsr, (const void *)(uintptr_t)plan.address, 4);
        if (mxcsr & 0xffff0000u) return PW_ERR_UNSUPPORTED;
    }
    return PW_OK;
fault:
    state->fault_address = plan.address;
    state->fault_width = width;
    state->fault_write = permission == PW_X86_WRITE;
    return PW_ERR_VM;
}

int pw_cpu_ps4_step(PwPs4Cpu *cpu)
{
    if (!cpu) return PW_ERR_PRECONDITION;
    if (!owned(cpu)) return PW_ERR_STATE;
    PwX86StepReport report;
    cpu->stats.steps++;
    const uint8_t *current = NULL;
    size_t available = 0;
    int rc = cpu->source_view(cpu->opaque, cpu->state.eip, &current, &available);
    if (rc) return rc;
    if (!current || !available) return PW_ERR_NOT_FOUND;
    rc = pw_x86_engine_step(&cpu->engine, &cpu->state, &report);
    cpu->stats.translated_instructions += report.retired;
    if (report.retired) cpu->stats.translated_blocks++;
    if (rc == PW_ERR_UNSUPPORTED) {
        const uint8_t *source = NULL;
        size_t bytes = 0;
        pw_x86_commit_canonical_flags(&cpu->state);
        pw_x86_engine_fp_sync(&cpu->engine, &cpu->state);
        rc = cpu->source_view(cpu->opaque, cpu->state.eip, &source, &bytes);
        if (!rc && (!source || !bytes)) rc = PW_ERR_NOT_FOUND;
        if (!rc && bytes >= 2 && source[0] == 0xdb && source[1] == 0xe3) {
            /* FNINIT on the synced guest state: default control word, clear
             * status, pointers and pending exceptions, all registers empty.
             * The data registers keep their bytes, as on hardware. */
            PwGuestFp *fp = &cpu->state.fp;
            fp->x87_control = 0x037f; fp->x87_status = 0; fp->x87_tag = 0xffff;
            fp->x87_opcode = 0; fp->x87_pending = 0; fp->x87_ip = 0; fp->x87_dp = 0;
            cpu->state.eip += 2;
            cpu->stats.x87_resets++;
            return PW_OK;
        }
        if (!rc) {
            cpu->stats.host_attempts++;
            rc = check_host_operand(&cpu->state, source, bytes);
            if (!rc) rc = pw_x86_hostexec_step(&cpu->host, &cpu->state, source, bytes);
            if (!rc) cpu->stats.host_steps++;
        }
    }
    return rc;
}

int pw_cpu_ps4_run(PwPs4Cpu *cpu, uint32_t stop_pc, uint32_t max_steps)
{
    if (!cpu || !max_steps) return PW_ERR_PRECONDITION;
    if (!owned(cpu)) return PW_ERR_STATE;
    for (uint32_t i = 0; i < max_steps; ++i) {
        if (cpu->state.eip == stop_pc) return PW_OK;
        int rc = pw_cpu_ps4_step(cpu);
        if (rc) return rc;
    }
    return cpu->state.eip == stop_pc ? PW_OK : PW_ERR_LIMIT;
}

int pw_cpu_ps4_stats(PwPs4Cpu *cpu, PwPs4CpuStats *out)
{
    if (!cpu || !out) return PW_ERR_PRECONDITION;
    if (!owned(cpu)) return PW_ERR_STATE;
    *out = cpu->stats;
    out->compiles = cpu->engine.compiles;
    out->cache_hits = cpu->engine.cache.hits;
    out->host_compiles = cpu->host.compiled;
    return PW_OK;
}

int pw_cpu_ps4_destroy(PwPs4Cpu *cpu)
{
    if (!cpu) return PW_ERR_PRECONDITION;
    if (!owned(cpu)) return PW_ERR_STATE;
    int a = pw_x86_hostexec_destroy(&cpu->host);
    int b = pw_x86_engine_destroy(&cpu->engine);
    PwVmBackend backend = cpu->backend;
    PwVmRegion storage = cpu->storage;
    int c = backend.release(backend.context, &storage);
    return a ? a : b ? b : c;
}
