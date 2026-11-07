/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "pw_vm_ps4.h"
#include "pw_vm_ps4_kernel.h"
#include <assert.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

enum { PAGE = 0x4000, SLOTS = 16, MAX_PAGES = 4 };
static unsigned char arena[SLOTS][PAGE * MAX_PAGES] __attribute__((aligned(PAGE)));
static struct { size_t bytes; int live; unsigned prot[MAX_PAGES]; } slots[SLOTS];
static unsigned reserve_calls, map_calls, protect_calls, unmap_calls;
static int fail_reserve, fail_map, fail_protect, fail_unmap;
static PwVmBackend vm;

int pw_ps4_kernel_reserve(void **p, size_t bytes, int flags, size_t alignment)
{
    (void)alignment;
    ++reserve_calls;
    if (fail_reserve) { fail_reserve = 0; return -1; }
    for (unsigned i = 0; i < SLOTS; ++i) {
        if ((flags & 0x10) && *p != arena[i]) continue;
        if (slots[i].live) { if (flags & 0x10) return -1; else continue; }
        assert(bytes <= sizeof(arena[i]));
        memset(&slots[i], 0, sizeof(slots[i]));
        slots[i].live = 1;
        slots[i].bytes = bytes;
        *p = arena[i];
        return 0;
    }
    return -1;
}

int pw_ps4_kernel_map(void **p, size_t bytes, int prot, int flags)
{
    assert(flags == 0x10);
    ++map_calls;
    if (fail_map) { fail_map = 0; return -1; }
    for (unsigned i = 0; i < SLOTS; ++i) {
        uintptr_t offset = (uintptr_t)*p - (uintptr_t)arena[i];
        if (!slots[i].live || offset > slots[i].bytes || bytes > slots[i].bytes - offset) continue;
        memset(*p, 0, bytes);
        for (size_t page = offset / PAGE; page < (offset + bytes) / PAGE; ++page) slots[i].prot[page] = prot;
        return 0;
    }
    return -1;
}

int pw_ps4_kernel_protect(const void *p, size_t bytes, int prot)
{
    ++protect_calls;
    if (fail_protect) { fail_protect = 0; return -1; }
    for (unsigned i = 0; i < SLOTS; ++i) {
        uintptr_t offset = (uintptr_t)p - (uintptr_t)arena[i];
        if (!slots[i].live || offset > slots[i].bytes || bytes > slots[i].bytes - offset) continue;
        for (size_t page = offset / PAGE; page < (offset + bytes) / PAGE; ++page) slots[i].prot[page] = prot;
        return 0;
    }
    return -1;
}

int pw_ps4_kernel_unmap(void *p, size_t bytes)
{
    ++unmap_calls;
    if (fail_unmap) { fail_unmap = 0; return -1; }
    for (unsigned i = 0; i < SLOTS; ++i) {
        if (slots[i].live && p == arena[i] && bytes == slots[i].bytes) {
            slots[i].live = 0;
            return 0;
        }
    }
    return -1;
}

static void stats(size_t count, size_t reserved, size_t committed)
{
    PwPs4VmStats state;
    assert(pw_vm_ps4_stats(&state) == PW_OK);
    assert(state.reservations == count && state.reserved_bytes == reserved && state.committed_bytes == committed);
}

static void negative_and_failure_paths(void)
{
    PwVmRegion region = {0}, saved, forged;
    unsigned calls = reserve_calls;
    assert(vm.reserve(NULL, SIZE_MAX, PAGE, &region) == PW_ERR_OVERFLOW);
    assert(vm.reserve(NULL, PAGE, 3, &region) == PW_ERR_PRECONDITION);
    assert(vm.reserve_at(NULL, UINT64_MAX - PAGE + 1, PAGE * 2, PAGE, &region) == PW_ERR_OVERFLOW);
    assert(reserve_calls == calls);
    fail_reserve = 1;
    saved = region;
    assert(vm.reserve(NULL, PAGE, PAGE, &region) == PW_ERR_VM);
    assert(!memcmp(&saved, &region, sizeof(region)));
    stats(0, 0, 0);

    assert(vm.reserve(NULL, PAGE * 3, PAGE, &region) == PW_OK);
    saved = region;
    assert(vm.reserve(NULL, PAGE * 3, PAGE, &region) == PW_OK);
    assert(region.handle != saved.handle);
    assert(vm.release(NULL, &saved) == PW_OK);
    saved = region;
    calls = protect_calls;
    assert(vm.protect(NULL, &region, 0, PAGE, 1) == PW_ERR_STATE);
    assert(protect_calls == calls);
    fail_map = 1;
    assert(vm.commit(NULL, &region, 0, PAGE, 3) == PW_ERR_VM);
    stats(1, PAGE * 3, 0);
    assert(vm.commit(NULL, &region, 0, PAGE, 3) == PW_OK);
    *(uint32_t *)region.write_base = 0x12345678;
    calls = map_calls;
    assert(vm.commit(NULL, &region, 0, PAGE * 2, 3) == PW_ERR_STATE);
    assert(map_calls == calls && *(uint32_t *)region.write_base == 0x12345678);
    assert(vm.commit(NULL, &region, 1, PAGE, 3) == PW_ERR_PRECONDITION);
    assert(vm.commit(NULL, &region, PAGE * 3, PAGE, 3) == PW_ERR_PRECONDITION);
    assert(vm.commit(NULL, &region, 0, PAGE, 0x80) == PW_ERR_PRECONDITION);
    assert(vm.commit(NULL, &region, PAGE, PAGE, 0) == PW_OK);
    stats(1, PAGE * 3, PAGE * 2);

    forged = region;
    forged.bytes += PAGE;
    calls = unmap_calls;
    assert(vm.release(NULL, &forged) == PW_ERR_PRECONDITION);
    assert(unmap_calls == calls);
    forged = region;
    forged.handle = (void *)(uintptr_t)UINTPTR_MAX;
    assert(vm.commit(NULL, &forged, PAGE * 2, PAGE, 3) == PW_ERR_PRECONDITION);

    fail_protect = 1;
    assert(vm.protect(NULL, &region, 0, PAGE * 2, 1) == PW_ERR_VM);
    stats(1, PAGE * 3, PAGE * 2);
    assert(vm.protect(NULL, &region, 0, PAGE * 2, 1) == PW_OK);
    calls = protect_calls;
    assert(vm.protect(NULL, &region, 0, PAGE * 3, 1) == PW_ERR_STATE);
    assert(protect_calls == calls);
    fail_unmap = 1;
    assert(vm.release(NULL, &region) == PW_ERR_VM);
    assert(!memcmp(&saved, &region, sizeof(region)));
    stats(1, PAGE * 3, PAGE * 2);
    assert(vm.release(NULL, &region) == PW_OK);
    assert(region.handle == NULL);
    stats(0, 0, 0);

    PwVmRegion replacement = {0};
    assert(vm.reserve_at(NULL, (uintptr_t)saved.exec_base, PAGE, PAGE, &replacement) == PW_OK);
    assert(replacement.write_base == saved.write_base && replacement.handle != saved.handle);
    calls = map_calls + protect_calls + unmap_calls;
    assert(vm.commit(NULL, &saved, 0, PAGE, 3) == PW_ERR_PRECONDITION);
    assert(vm.protect(NULL, &saved, 0, PAGE, 1) == PW_ERR_PRECONDITION);
    assert(vm.release(NULL, &saved) == PW_ERR_PRECONDITION);
    assert(calls == map_calls + protect_calls + unmap_calls);
    assert(vm.release(NULL, &replacement) == PW_OK);
    stats(0, 0, 0);
}

static void *parallel_worker(void *unused)
{
    (void)unused;
    for (unsigned i = 0; i < 100; ++i) {
        PwVmRegion region = {0};
        assert(vm.reserve(NULL, PAGE, PAGE, &region) == PW_OK);
        assert(vm.commit(NULL, &region, 0, PAGE, 3) == PW_OK);
        assert(vm.release(NULL, &region) == PW_OK);
    }
    return NULL;
}

int main(void)
{
    assert(pw_vm_ps4_backend(&vm) == PW_OK);
    negative_and_failure_paths();
    pthread_t threads[4];
    for (unsigned i = 0; i < 4; ++i) assert(!pthread_create(&threads[i], NULL, parallel_worker, NULL));
    for (unsigned i = 0; i < 4; ++i) assert(!pthread_join(threads[i], NULL));
    stats(0, 0, 0);
    puts("VM failure injection, stale handles, overlap and 400 concurrent reservation cycles passed");
    return 0;
}
