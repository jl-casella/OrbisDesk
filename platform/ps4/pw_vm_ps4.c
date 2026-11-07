/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "pw_vm_ps4.h"
#include "pw_vm_ps4_kernel.h"
#include <pthread.h>
#include <stdlib.h>
#include <string.h>

enum { PAGE_BYTES = 0x4000, MAP_FIXED = 0x10, MAP_NO_OVERWRITE = 0x80, COMMITTED = 8 };

typedef struct Reservation {
    struct Reservation *next;
    uintptr_t token;
    void *base;
    size_t bytes, alignment;
    unsigned char pages[];
} Reservation;

static pthread_mutex_t registry_lock = PTHREAD_MUTEX_INITIALIZER;
static Reservation *reservations;
static uintptr_t next_token = 1;

static int shape(size_t bytes, size_t alignment, size_t *rounded, size_t *effective)
{
    if (!bytes || !alignment || (alignment & (alignment - 1))) return PW_ERR_PRECONDITION;
    if (bytes > SIZE_MAX - (PAGE_BYTES - 1)) return PW_ERR_OVERFLOW;
    *rounded = (bytes + PAGE_BYTES - 1) & ~(size_t)(PAGE_BYTES - 1);
    *effective = alignment < PAGE_BYTES ? PAGE_BYTES : alignment;
    if (*effective > 0x80000000ULL) return PW_ERR_PRECONDITION;
    return PW_OK;
}

static Reservation *find(const PwVmRegion *region)
{
    if (!region || !region->handle) return NULL;
    for (Reservation *entry = reservations; entry; entry = entry->next) {
        if (entry->token == (uintptr_t)region->handle && region->write_base == entry->base &&
            region->exec_base == entry->base && region->bytes == entry->bytes &&
            region->alignment == entry->alignment) return entry;
    }
    return NULL;
}

static int take_reservation(uint64_t address, int exact, size_t bytes, size_t alignment, PwVmRegion *out)
{
    size_t rounded, effective;
    int rc = shape(bytes, alignment, &rounded, &effective);
    if (rc) return rc;
    if (!out || (exact && (!address || address > UINTPTR_MAX || address % effective)))
        return PW_ERR_PRECONDITION;
    if (exact && rounded > UINTPTR_MAX - (uintptr_t)address) return PW_ERR_OVERFLOW;
    size_t pages = rounded / PAGE_BYTES;
    if (pages > SIZE_MAX - sizeof(Reservation)) return PW_ERR_OVERFLOW;
    Reservation *entry = calloc(1, sizeof(*entry) + pages);
    if (!entry) return PW_ERR_VM;

    pthread_mutex_lock(&registry_lock);
    if (!next_token) {
        pthread_mutex_unlock(&registry_lock);
        free(entry);
        return PW_ERR_LIMIT;
    }
    void *p = exact ? (void *)(uintptr_t)address : NULL;
    rc = pw_ps4_kernel_reserve(&p, rounded, exact ? MAP_FIXED | MAP_NO_OVERWRITE : 0, effective);
    if (rc) {
        pthread_mutex_unlock(&registry_lock);
        free(entry);
        return PW_ERR_VM;
    }
    if (!p || (exact && (uintptr_t)p != address)) {
        if (p) pw_ps4_kernel_unmap(p, rounded);
        pthread_mutex_unlock(&registry_lock);
        free(entry);
        return PW_ERR_VM;
    }
    entry->base = p;
    entry->bytes = rounded;
    entry->alignment = effective;
    entry->token = next_token++;
    entry->next = reservations;
    reservations = entry;
    *out = (PwVmRegion){p, p, rounded, effective, (void *)entry->token};
    pthread_mutex_unlock(&registry_lock);
    return PW_OK;
}

static int reserve_at(void *context, uint64_t address, size_t bytes, size_t alignment, PwVmRegion *out)
{
    (void)context;
    return take_reservation(address, 1, bytes, alignment, out);
}

static int reserve(void *context, size_t bytes, size_t alignment, PwVmRegion *out)
{
    (void)context;
    return take_reservation(0, 0, bytes, alignment, out);
}

static int range_valid(const Reservation *entry, size_t offset, size_t bytes, unsigned protection)
{
    return bytes && !(offset % PAGE_BYTES) && !(bytes % PAGE_BYTES) && !(protection & ~7u) &&
           offset <= entry->bytes && bytes <= entry->bytes - offset;
}

static int commit(void *context, const PwVmRegion *region, size_t offset, size_t bytes, unsigned protection)
{
    (void)context;
    pthread_mutex_lock(&registry_lock);
    Reservation *entry = find(region);
    int rc = PW_ERR_PRECONDITION;
    if (!entry || !range_valid(entry, offset, bytes, protection)) goto done;
    for (size_t page = offset / PAGE_BYTES; page < (offset + bytes) / PAGE_BYTES; ++page) {
        if (entry->pages[page] & COMMITTED) { rc = PW_ERR_STATE; goto done; }
    }
    void *wanted = (uint8_t *)entry->base + offset;
    void *p = wanted;
    rc = pw_ps4_kernel_map(&p, bytes, (int)protection, MAP_FIXED) ? PW_ERR_VM : PW_OK;
    if (!rc && p != wanted) {
        pw_ps4_kernel_unmap(p, bytes);
        rc = PW_ERR_VM;
    }
    if (!rc) memset(entry->pages + offset / PAGE_BYTES, COMMITTED | protection, bytes / PAGE_BYTES);
done:
    pthread_mutex_unlock(&registry_lock);
    return rc;
}

static int protect(void *context, const PwVmRegion *region, size_t offset, size_t bytes, unsigned protection)
{
    (void)context;
    pthread_mutex_lock(&registry_lock);
    Reservation *entry = find(region);
    int rc = PW_ERR_PRECONDITION;
    if (!entry || !range_valid(entry, offset, bytes, protection)) goto done;
    for (size_t page = offset / PAGE_BYTES; page < (offset + bytes) / PAGE_BYTES; ++page) {
        if (!(entry->pages[page] & COMMITTED)) { rc = PW_ERR_STATE; goto done; }
    }
    rc = pw_ps4_kernel_protect((uint8_t *)entry->base + offset, bytes, (int)protection) ? PW_ERR_VM : PW_OK;
    if (!rc) memset(entry->pages + offset / PAGE_BYTES, COMMITTED | protection, bytes / PAGE_BYTES);
done:
    pthread_mutex_unlock(&registry_lock);
    return rc;
}

static int release(void *context, PwVmRegion *region)
{
    (void)context;
    pthread_mutex_lock(&registry_lock);
    Reservation *entry = find(region);
    int rc = PW_ERR_PRECONDITION;
    if (!entry) goto done;
    rc = pw_ps4_kernel_unmap(entry->base, entry->bytes) ? PW_ERR_VM : PW_OK;
    if (rc) goto done;
    Reservation **link = &reservations;
    while (*link != entry) link = &(*link)->next;
    *link = entry->next;
    free(entry);
    memset(region, 0, sizeof(*region));
done:
    pthread_mutex_unlock(&registry_lock);
    return rc;
}

int pw_vm_ps4_stats(PwPs4VmStats *out)
{
    if (!out) return PW_ERR_PRECONDITION;
    PwPs4VmStats value = {0};
    pthread_mutex_lock(&registry_lock);
    for (Reservation *entry = reservations; entry; entry = entry->next) {
        ++value.reservations;
        value.reserved_bytes += entry->bytes;
        for (size_t page = 0; page < entry->bytes / PAGE_BYTES; ++page)
            if (entry->pages[page] & COMMITTED) value.committed_bytes += PAGE_BYTES;
    }
    pthread_mutex_unlock(&registry_lock);
    *out = value;
    return PW_OK;
}

int pw_vm_ps4_backend(PwVmBackend *out)
{
    if (!out) return PW_ERR_PRECONDITION;
    *out = (PwVmBackend){NULL, PW_VM_CAP_PROTECT | PW_VM_CAP_EXACT_ADDRESS,
                        PAGE_BYTES, reserve, commit, protect, release, reserve_at};
    return PW_OK;
}
