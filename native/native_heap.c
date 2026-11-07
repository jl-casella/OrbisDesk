/* SPDX-License-Identifier: LGPL-2.1-or-later
 * W100: serialize the SDK allocator when threads come from libkernel.
 *
 * The linked musl malloc checks an internal libc thread counter before taking
 * its bin locks. Libkernel pthread_create does not maintain musl's thread list.
 * Do not enable arbitrary musl pthread paths by writing its private state.
 * Keep its allocator and pointer ABI; guard all of its public allocation entries.
 * No allocation, stdio or musl pthread primitive is used while acquiring this lock.
 */
#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

extern void *scePthreadSelf(void);
extern int sceKernelUsleep(unsigned int usec);
extern void *__real_malloc(size_t);
extern void *__real_calloc(size_t, size_t);
extern void *__real_realloc(void *, size_t);
extern void __real_free(void *);
extern void *__real_memalign(size_t, size_t);
extern void *__real___memalign(size_t, size_t);
extern void *__real_aligned_alloc(size_t, size_t);
extern int __real_posix_memalign(void **, size_t, size_t);

static uintptr_t owner;
static unsigned int depth;
static unsigned long long operations, nested, waits;

static void heap_enter(void)
{
    uintptr_t self = (uintptr_t)scePthreadSelf();
    uintptr_t expected;

    /* Allocation-family functions may call each other through wrapped symbols.
     * Owner identity comes from libkernel, independently of Wine's GS/TEB.
     * scePthreadSelf returns the current kernel thread's non-null handle. */
    if (__atomic_load_n(&owner, __ATOMIC_ACQUIRE) == self)
    {
        ++depth;
        ++nested;
        ++operations;
        return;
    }
    for (;;)
    {
        expected = 0;
        if (__atomic_compare_exchange_n(&owner, &expected, self, 0,
                                        __ATOMIC_ACQUIRE, __ATOMIC_RELAXED)) break;
        __atomic_add_fetch(&waits, 1, __ATOMIC_RELAXED);
        sceKernelUsleep(1);
    }
    depth = 1;
    ++operations;
}

static void heap_leave(void)
{
    if (--depth) return;
    __atomic_store_n(&owner, 0, __ATOMIC_RELEASE);
}

#define HEAP_RETURN(type, expression) do { \
    int heap_errno = errno; \
    heap_enter(); \
    errno = heap_errno; \
    type result = (expression); \
    heap_errno = errno; \
    heap_leave(); \
    errno = heap_errno; \
    return result; \
} while (0)

void *__wrap_malloc(size_t size) { HEAP_RETURN(void *, __real_malloc(size)); }
void *__wrap_calloc(size_t count, size_t size) { HEAP_RETURN(void *, __real_calloc(count, size)); }
void *__wrap_realloc(void *ptr, size_t size) { HEAP_RETURN(void *, __real_realloc(ptr, size)); }
void *__wrap_memalign(size_t alignment, size_t size) { HEAP_RETURN(void *, __real_memalign(alignment, size)); }
void *__wrap___memalign(size_t alignment, size_t size) { HEAP_RETURN(void *, __real___memalign(alignment, size)); }
void *__wrap_aligned_alloc(size_t alignment, size_t size) { HEAP_RETURN(void *, __real_aligned_alloc(alignment, size)); }
int __wrap_posix_memalign(void **ptr, size_t alignment, size_t size)
{
    HEAP_RETURN(int, __real_posix_memalign(ptr, alignment, size));
}

void __wrap_free(void *ptr)
{
    int heap_errno = errno;
    heap_enter();
    errno = heap_errno;
    __real_free(ptr);
    heap_errno = errno;
    heap_leave();
    errno = heap_errno;
}

void pw_native_heap_report(void)
{
    unsigned long long calls, recursion, contention;
    int heap_errno = errno;
    heap_enter();
    calls = operations;
    recursion = nested;
    contention = __atomic_load_n(&waits, __ATOMIC_RELAXED);
    heap_leave();
    fprintf(stderr, "PWHEAP serialized_sdk_allocator entries=8 operations=%llu nested=%llu waits=%llu\n",
            calls, recursion, contention);
    errno = heap_errno;
}
