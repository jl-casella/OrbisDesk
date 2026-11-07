/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "pw_pe32_lifecycle.h"
#include "pw_guest_call.h"
#include <string.h>

static int invoke(PwPe32Thread *thread, unsigned module, uint32_t target, unsigned reason, unsigned tls, uint32_t *result)
{
    PwPe32Lifecycle *life = thread->life;
    if (life->events == 1024) return PW_ERR_LIMIT;
    PwX86State *state = pw_cpu_ps4_state(thread->cpu);
    if (!state) return PW_ERR_STATE;
    uint32_t arguments[] = {life->images[module]->base, reason, 0};
    PwGuestCallback frame = {0};
    int rc = pw_guest_callback_enter(&frame, state, target, 0x0badf00d, arguments, 3, PW_GUEST_STDCALL);
    if (!rc) rc = life->runner ? life->runner(life->runner_opaque, thread->cpu, 0x0badf00d)
                               : pw_cpu_ps4_run(thread->cpu, 0x0badf00d, 256);
    uint64_t value = 0;
    if (!rc) rc = pw_guest_callback_leave(&frame, tls ? 0 : 32, &value);
    if (!rc) {
        *result = (uint32_t)value;
        life->trace[life->events++] = (PwPe32InitEvent){module, reason, tls, *result};
    }
    return rc;
}
static int notify(PwPe32Thread *thread, unsigned module, unsigned reason)
{
    PwPe32Image *image = thread->life->images[module];
    if (!image) return PW_OK;
    uint32_t result = 1;
    for (unsigned i = 0; i < image->info.tls_callback_count; ++i) {
        int rc = invoke(thread, module, image->base + image->info.tls_callbacks[i], reason, 1, &result);
        if (rc) return rc;
    }
    /* An EXE takes part only through its TLS; its entry point is the process start. */
    if (image->entry && image->info.is_dll) {
        int rc = invoke(thread, module, image->entry, reason, 0, &result);
        if (rc) return rc;
        if (reason == 1 && !result) return PW_PE32_INIT_FAILED;
    }
    return PW_OK;
}
/* Fresh TLS block for one slot of one thread; lifecycle mutex held. */
static void install_block(PwPe32Thread *thread, size_t slot)
{
    PwPe32Image *image = thread->life->images[slot];
    uint32_t *slots = (uint32_t *)((uint8_t *)thread->region.write_base + PW_PE32_PAGE);
    uint8_t *block = (uint8_t *)(uintptr_t)thread->blocks[slot];
    memset(block, 0, PW_PE32_PAGE);
    if (image->info.tls_template_bytes)
        memcpy(block, (uint8_t *)image->region.write_base + image->info.tls_template_rva, image->info.tls_template_bytes);
    slots[slot] = thread->blocks[slot];
}
static void remove_slot(PwPe32Lifecycle *life, size_t slot)
{
    life->images[slot]->lifecycle_owner = NULL;
    life->images[slot] = NULL;
    for (unsigned i = 0; i < PW_PE32_MAX_THREADS; ++i)
        if (life->live[i]) ((uint32_t *)((uint8_t *)life->live[i]->region.write_base + PW_PE32_PAGE))[slot] = 0;
    while (life->count && !life->images[life->count - 1]) life->count--;
}
int pw_pe32_lifecycle_create(PwPe32Lifecycle *life, const PwVmBackend *vm, PwPe32Image *const *images, size_t count)
{
    if (!life || !pw_vm_backend_valid(vm) || vm->page_bytes != PW_PE32_PAGE ||
        !(vm->capabilities & PW_VM_CAP_EXACT_ADDRESS) || !vm->reserve_at ||
        !images || !count || count > PW_PE32_MAX_MODULES) return PW_ERR_PRECONDITION;
    for (size_t i = 0; i < count; ++i) {
        /* DLLs must be flat; one linked EXE may join first, for its static TLS. */
        int exe = images[i] && !images[i]->info.is_dll;
        if (!images[i] || !images[i]->region.handle || !images[i]->linked || (exe && i) ||
            (!exe && images[i]->info.import_count) || images[i]->lifecycle_owner || images[i]->init_state == 3) return PW_ERR_STATE;
        for (size_t j = 0; j < i; ++j) if (images[i] == images[j]) return PW_ERR_PRECONDITION;
    }
    memset(life, 0, sizeof(*life));
    if (pthread_mutex_init(&life->mutex, NULL)) return PW_ERR_STATE;
    life->backend = *vm; life->count = count; life->initialized = 1;
    for (size_t i = 0; i < count; ++i) {
        life->images[i] = images[i]; images[i]->lifecycle_owner = life;
        if (images[i]->info.tls_bytes) {
            uint32_t index = (uint32_t)i;
            memcpy((uint8_t *)images[i]->region.write_base + images[i]->info.tls_index_rva, &index, 4);
        }
    }
    return PW_OK;
}
int pw_pe32_lifecycle_set_runner(PwPe32Lifecycle *life, PwPe32Runner runner, void *opaque)
{
    if (!life || !life->initialized) return PW_ERR_PRECONDITION;
    pthread_mutex_lock(&life->mutex);
    int rc = life->threads ? PW_ERR_STATE : PW_OK;
    if (!rc) { life->runner = runner; life->runner_opaque = opaque; }
    pthread_mutex_unlock(&life->mutex);
    return rc;
}
int pw_pe32_thread_create(PwPe32Lifecycle *life, PwPs4Cpu *cpu, uint32_t address, int main_thread, PwPe32Thread *out)
{
    PwX86State *state = pw_cpu_ps4_state(cpu);
    if (!life || !life->initialized || !out || !state || !address || state->memory_count >= PW_X86_MEMORY_REGIONS) return PW_ERR_PRECONDITION;
    pthread_mutex_lock(&life->mutex);
    int rc = PW_OK;
    if (main_thread ? life->status != PW_PE32_LIFE_NEW || life->threads : life->status != PW_PE32_LIFE_ATTACHED) rc = PW_ERR_STATE;
    unsigned registry = PW_PE32_MAX_THREADS;
    for (unsigned i = 0; i < PW_PE32_MAX_THREADS && registry == PW_PE32_MAX_THREADS; ++i) if (!life->live[i]) registry = i;
    if (!rc && registry == PW_PE32_MAX_THREADS) rc = PW_ERR_LIMIT;
    PwPe32Thread thread = {0};
    thread.life = life; thread.cpu = cpu; thread.main_thread = !!main_thread;
    size_t bytes = (2 + PW_PE32_MAX_MODULES) * PW_PE32_PAGE;
    if ((uint64_t)address + bytes > 0x100000000ull) rc = PW_ERR_PRECONDITION;
    if (!rc) rc = life->backend.reserve_at(life->backend.context, address, bytes, PW_PE32_PAGE, &thread.region);
    if (!rc) rc = life->backend.commit(life->backend.context, &thread.region, 0, thread.region.bytes, 3);
    if (!rc) {
        memset(thread.region.write_base, 0, thread.region.bytes);
        uint32_t *teb = thread.region.write_base;
        teb[0] = UINT32_MAX;
        teb[4 / 4] = state->stack_high; teb[8 / 4] = state->stack_low;
        teb[0x18 / 4] = address; teb[0x2c / 4] = address + PW_PE32_PAGE;
        for (size_t i = 0; i < PW_PE32_MAX_MODULES; ++i) thread.blocks[i] = address + (uint32_t)(2 + i) * PW_PE32_PAGE;
        for (size_t i = 0; i < life->count; ++i) if (life->images[i]) install_block(&thread, i);
        thread.old_fs = state->fs_base; thread.old_fs_bytes = state->fs_bytes;
        state->fs_base = address; state->fs_bytes = PW_PE32_PAGE;
        state->memory[state->memory_count++] = (PwX86Memory){address, (uint64_t)address + bytes, 3};
        life->threads++; *out = thread;
        life->live[registry] = out;
    } else if (thread.region.handle) life->backend.release(life->backend.context, &thread.region);
    pthread_mutex_unlock(&life->mutex);
    return rc;
}
int pw_pe32_process_attach(PwPe32Thread *thread)
{
    if (!thread || !thread->region.handle || !thread->main_thread || !pw_cpu_ps4_state(thread->cpu)) return PW_ERR_STATE;
    PwPe32Lifecycle *life = thread->life;
    pthread_mutex_lock(&life->mutex);
    int rc = life->status == PW_PE32_LIFE_NEW && !thread->attached ? PW_OK : PW_ERR_STATE;
    if (rc) { pthread_mutex_unlock(&life->mutex); return rc; }
    size_t initialized = 0;
    for (; initialized < life->count; ++initialized) {
        life->images[initialized]->init_state = 1;
        rc = notify(thread, (unsigned)initialized, 1);
        if (rc) break;
        life->images[initialized]->init_state = 2;
    }
    if (rc == PW_PE32_INIT_FAILED) {
        int cleanup = notify(thread, (unsigned)initialized, 0);
        while (initialized) {
            --initialized;
            life->images[initialized]->init_state = 1;
            int failed = notify(thread, (unsigned)initialized, 0);
            if (failed) cleanup = failed;
        }
        if (cleanup) rc = cleanup;
    }
    if (rc) {
        life->status = PW_PE32_LIFE_FAILED;
        for (size_t i = 0; i < life->count; ++i) life->images[i]->init_state = 3;
    } else { life->status = PW_PE32_LIFE_ATTACHED; thread->attached = 1; }
    pthread_mutex_unlock(&life->mutex);
    return rc;
}
static int thread_notify(PwPe32Thread *thread, unsigned reason)
{
    if (!thread || !thread->region.handle || thread->main_thread || !pw_cpu_ps4_state(thread->cpu)) return PW_ERR_STATE;
    PwPe32Lifecycle *life = thread->life;
    pthread_mutex_lock(&life->mutex);
    int rc = life->status == PW_PE32_LIFE_ATTACHED && thread->attached == (reason == 3) ? PW_OK : PW_ERR_STATE;
    if (!rc) {
        for (size_t i = 0; i < life->count; ++i) {
            size_t module = reason == 3 ? life->count - 1 - i : i;
            rc = notify(thread, (unsigned)module, reason);
            if (rc) break;
        }
        if (!rc) thread->attached = reason == 2;
        else {
            life->status = PW_PE32_LIFE_FAILED;
            for (size_t i = 0; i < life->count; ++i) if (life->images[i]) life->images[i]->init_state = 3;
        }
    }
    pthread_mutex_unlock(&life->mutex);
    return rc;
}
int pw_pe32_thread_attach(PwPe32Thread *thread) { return thread_notify(thread, 2); }
int pw_pe32_thread_detach(PwPe32Thread *thread) { return thread_notify(thread, 3); }
int pw_pe32_process_detach(PwPe32Thread *thread)
{
    if (!thread || !thread->region.handle || !thread->main_thread || !pw_cpu_ps4_state(thread->cpu)) return PW_ERR_STATE;
    PwPe32Lifecycle *life = thread->life;
    pthread_mutex_lock(&life->mutex);
    int rc = life->status == PW_PE32_LIFE_ATTACHED && life->threads == 1 && thread->attached ? PW_OK : PW_ERR_STATE;
    if (!rc) {
        for (size_t i = life->count; i > 0; --i) {
            rc = notify(thread, (unsigned)(i - 1), 0);
            if (rc) break;
        }
        thread->attached = 0;
        life->status = rc ? PW_PE32_LIFE_FAILED : PW_PE32_LIFE_DETACHED;
        for (size_t i = 0; i < life->count; ++i) if (life->images[i]) life->images[i]->init_state = 3;
    }
    pthread_mutex_unlock(&life->mutex);
    return rc;
}
static int caller_valid(PwPe32Lifecycle *life, PwPe32Thread *caller)
{
    return life && life->initialized && caller && caller->life == life && caller->region.handle &&
           caller->attached && pw_cpu_ps4_state(caller->cpu);
}
int pw_pe32_lifecycle_load(PwPe32Lifecycle *life, PwPe32Image *image, PwPe32Thread *caller)
{
    if (!caller_valid(life, caller) || !image || !image->region.handle || !image->info.is_dll || !image->linked ||
        image->lifecycle_owner || image->init_state == 3) return PW_ERR_STATE;
    pthread_mutex_lock(&life->mutex);
    size_t slot = 0;
    while (slot < PW_PE32_MAX_MODULES && life->images[slot]) ++slot;
    int rc = life->status != PW_PE32_LIFE_ATTACHED ? PW_ERR_STATE : slot == PW_PE32_MAX_MODULES ? PW_ERR_LIMIT : PW_OK;
    if (!rc) {
        life->images[slot] = image; image->lifecycle_owner = life;
        if (slot >= life->count) life->count = slot + 1;
        if (image->info.tls_bytes) {
            uint32_t index = (uint32_t)slot;
            memcpy((uint8_t *)image->region.write_base + image->info.tls_index_rva, &index, 4);
        }
        for (unsigned i = 0; i < PW_PE32_MAX_THREADS; ++i) if (life->live[i]) install_block(life->live[i], slot);
        image->init_state = 1;
        rc = notify(caller, (unsigned)slot, 1);
        if (rc == PW_PE32_INIT_FAILED) {
            int cleanup = notify(caller, (unsigned)slot, 0);
            if (cleanup) rc = cleanup;
        }
        if (!rc) image->init_state = 2;
        else { remove_slot(life, slot); image->init_state = 3; }
    }
    pthread_mutex_unlock(&life->mutex);
    return rc;
}
int pw_pe32_lifecycle_unload(PwPe32Lifecycle *life, PwPe32Image *image, PwPe32Thread *caller)
{
    if (!caller_valid(life, caller) || !image) return PW_ERR_STATE;
    pthread_mutex_lock(&life->mutex);
    size_t slot = 0;
    while (slot < life->count && life->images[slot] != image) ++slot;
    int rc = slot == life->count || life->status != PW_PE32_LIFE_ATTACHED || image->init_state != 2 ? PW_ERR_STATE : PW_OK;
    if (!rc) {
        image->init_state = 1;
        rc = notify(caller, (unsigned)slot, 0);
        remove_slot(life, slot);
        image->init_state = 3;
    }
    pthread_mutex_unlock(&life->mutex);
    return rc;
}
int pw_pe32_thread_destroy(PwPe32Thread *thread)
{
    if (!thread || !thread->region.handle) return PW_ERR_STATE;
    PwX86State *state = pw_cpu_ps4_state(thread->cpu);
    if (!state) return PW_ERR_STATE;
    PwPe32Lifecycle *life = thread->life;
    pthread_mutex_lock(&life->mutex);
    if (thread->attached && life->status == PW_PE32_LIFE_ATTACHED) { pthread_mutex_unlock(&life->mutex); return PW_ERR_STATE; }
    unsigned slot = state->memory_count;
    uint32_t base = (uint32_t)(uintptr_t)thread->region.write_base;
    for (unsigned i = 0; i < state->memory_count; ++i) if (state->memory[i].low == base) { slot = i; break; }
    int rc = slot == state->memory_count ? PW_ERR_STATE : life->backend.release(life->backend.context, &thread->region);
    if (!rc) {
        memmove(state->memory + slot, state->memory + slot + 1, (state->memory_count - slot - 1) * sizeof(state->memory[0]));
        state->memory_count--;
        state->fs_base = thread->old_fs; state->fs_bytes = thread->old_fs_bytes;
        for (unsigned i = 0; i < PW_PE32_MAX_THREADS; ++i) if (life->live[i] == thread) life->live[i] = NULL;
        life->threads--; memset(thread, 0, sizeof(*thread));
    }
    pthread_mutex_unlock(&life->mutex);
    return rc;
}
int pw_pe32_lifecycle_destroy(PwPe32Lifecycle *life)
{
    if (!life || !life->initialized || life->threads || life->status == PW_PE32_LIFE_ATTACHED) return PW_ERR_STATE;
    if (pthread_mutex_destroy(&life->mutex)) return PW_ERR_STATE;
    for (size_t i = 0; i < life->count; ++i) if (life->images[i]) life->images[i]->lifecycle_owner = NULL;
    memset(life, 0, sizeof(*life));
    return PW_OK;
}
