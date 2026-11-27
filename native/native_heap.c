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
#include <string.h>

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

/* Alice 04.87: std::bad_alloc precedes an abort, but says neither how much was
 * requested nor who requested it. Record failed allocations after releasing the
 * allocator lock, using only the raw logger (no allocation/stdio/TLS unwinding).
 * A caller address can be symbolized against this build's exact ELF. */
extern int pw_native_log_fd;
extern uintptr_t pw_native_raw_syscall;
extern long pw_native_syscall_at(uintptr_t,long,long,long,long);
static unsigned allocation_failures;
static void heap_line(const char *prefix,const char *const *names,const uint64_t *values,unsigned count)
{
    static const char digits[]="0123456789abcdef";
    char line[256];unsigned n=0;
    for(unsigned i=0;prefix[i];i++)line[n++]=prefix[i];
    for(unsigned i=0;i<count;i++) {
        line[n++]=' ';
        for(unsigned j=0;names[i][j];j++)line[n++]=names[i][j];
        line[n++]='=';line[n++]='0';line[n++]='x';
        for(unsigned j=0;j<16;j++)line[n++]=digits[(values[i]>>(60-4*j))&15];
    }
    line[n++]='\n';
    pw_native_syscall_at(pw_native_raw_syscall,4,pw_native_log_fd,(long)line,(long)n);
}
static void heap_failure(uint64_t kind,size_t size,size_t count,int error,uintptr_t caller)
{
    static const char *const names[]={"n","kind","size","count","errno","caller"};
    if(pw_native_log_fd<0 || !pw_native_raw_syscall ||
       __atomic_load_n(&allocation_failures,__ATOMIC_RELAXED)>=16) return;
    unsigned sequence=__atomic_add_fetch(&allocation_failures,1,__ATOMIC_RELAXED);
    if(sequence>16)return;
    const uint64_t values[]={sequence,kind,size,count,(unsigned)error,caller};
    heap_line("PWHEAP allocation_failed v=1",names,values,sizeof(values)/sizeof(values[0]));
}

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

#define HEAP_RETURN(type, expression, failure, kind, size, count, block) do { \
    int heap_errno = errno; \
    heap_enter(); \
    errno = heap_errno; \
    type result = (expression); \
    heap_errno = errno; \
    heap_leave(); \
    if (failure) heap_failure(kind,size,count,heap_errno,(uintptr_t)__builtin_return_address(0)); \
    (void)(block); \
    errno = heap_errno; \
    return result; \
} while (0)

/* kind: 1 malloc, 2 calloc, 3 realloc, 4 memalign, 5 __memalign,
 *       6 aligned_alloc, 7 posix_memalign. count is never multiplied here. */
void *__wrap_malloc(size_t size) { HEAP_RETURN(void *, __real_malloc(size),!result&&size,1,size,1,result); }
void *__wrap_calloc(size_t count, size_t size) { HEAP_RETURN(void *, __real_calloc(count, size),!result&&size&&count,2,size,count,result); }
void *__wrap_realloc(void *ptr, size_t size) { HEAP_RETURN(void *, __real_realloc(ptr, size),!result&&size,3,size,1,result); }
void *__wrap_memalign(size_t alignment, size_t size) { HEAP_RETURN(void *, __real_memalign(alignment, size),!result&&size,4,size,alignment,result); }
void *__wrap___memalign(size_t alignment, size_t size) { HEAP_RETURN(void *, __real___memalign(alignment, size),!result&&size,5,size,alignment,result); }
void *__wrap_aligned_alloc(size_t alignment, size_t size) { HEAP_RETURN(void *, __real_aligned_alloc(alignment, size),!result&&size,6,size,alignment,result); }
int __wrap_posix_memalign(void **ptr, size_t alignment, size_t size)
{
    HEAP_RETURN(int, __real_posix_memalign(ptr, alignment, size),result==ENOMEM,7,size,alignment,result?NULL:*ptr);
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

/* Alice 04.91 (W303 run-0243 of 20261126T160943Z): Mesa's shader compiler asked for 140 and 160 KiB
 * (rzalloc_array_size, operator new), malloc failed with errno EINVAL, libc++ threw bad_alloc and the
 * title ended. musl serves those sizes with an anonymous mmap (and grows its heap with one); the title
 * has ~390 MB of flexible memory, and when that pool is empty the kernel refuses the map with EINVAL,
 * not ENOMEM (docs/SEAMONKEY_FLEXIBLE_MEMORY.md). Wine's views stop using the pool below 64 MiB (flexible
 * reserve), but the native heap had nothing else. musl's own mmap and munmap (malloc.lo and
 * expand_heap.lo reference __mmap and __munmap) are wrapped in the title's link
 * (tools/build-wine-hardware.py): an anonymous map that the flexible pool refuses takes direct memory
 * (~4.6 GB) instead, zeroed as anonymous memory is, and its munmap gives the direct memory back. musl's
 * chunk headers are its own as before; its mremap never succeeds here, so realloc copies. If direct
 * memory fails too, the map fails as before and PWHEAP allocation_failed still says so. */
extern void *__real___mmap(void *, size_t, int, int, int, long);
extern int __real___munmap(void *, size_t);
extern int sceKernelAllocateDirectMemory(long, long, size_t, size_t, int, long *);
extern int sceKernelMapDirectMemory(void **, size_t, int, int, long, size_t);
extern int sceKernelReleaseDirectMemory(long, size_t);
extern size_t sceKernelGetDirectMemorySize(void);
#define HEAP_DIRECT_PAGE 0x4000u   /* the kernel's page */
#define HEAP_DIRECT_MAX 4096u
#define HEAP_MAP_ANONYMOUS 0x1000  /* FreeBSD MAP_ANON, as the SDK passes it */
static struct heap_direct { uintptr_t base; size_t size; long offset; } heap_directs[HEAP_DIRECT_MAX];
static unsigned heap_direct_count, heap_direct_lines;
static int heap_direct_lock;
static uint64_t heap_direct_bytes;
static void heap_direct_enter(void)
{
    while (__atomic_exchange_n(&heap_direct_lock, 1, __ATOMIC_ACQUIRE)) sceKernelUsleep(1);
}
static void heap_direct_leave(void)
{
    __atomic_store_n(&heap_direct_lock, 0, __ATOMIC_RELEASE);
}
static void heap_direct_line(size_t size, int error, int rc, uintptr_t ptr, uint64_t total, unsigned count)
{
    static const char *const names[]={"n","size","errno","rc","ptr","total","blocks"};
    if (pw_native_log_fd < 0 || !pw_native_raw_syscall ||
        __atomic_load_n(&heap_direct_lines, __ATOMIC_RELAXED) >= 16) return;
    unsigned sequence = __atomic_add_fetch(&heap_direct_lines, 1, __ATOMIC_RELAXED);
    if (sequence > 16) return;
    const uint64_t values[]={sequence,size,(unsigned)error,(uint32_t)rc,ptr,total,count};
    heap_line("PWHEAP direct v=1", names, values, sizeof(values)/sizeof(values[0]));
}
void *__wrap___mmap(void *addr, size_t len, int prot, int flags, int fd, long off)
{
    void *result = __real___mmap(addr, len, prot, flags, fd, off);
    int error = errno;
    size_t size = (len + HEAP_DIRECT_PAGE - 1) & ~(size_t)(HEAP_DIRECT_PAGE - 1);
    long offset = 0;
    void *at = NULL;
    int rc;

    if (result != (void *)-1 || addr || fd != -1 || !(flags & HEAP_MAP_ANONYMOUS) ||
        (error != EINVAL && error != ENOMEM) || !len || size < len) return result;
    heap_direct_enter();
    if (heap_direct_count == HEAP_DIRECT_MAX) rc = -1;
    else if (!(rc = sceKernelAllocateDirectMemory(0, (long)sceKernelGetDirectMemorySize(), size, HEAP_DIRECT_PAGE,
                                                  0 /* WB_ONION */, &offset)))
    {
        rc = sceKernelMapDirectMemory(&at, size, prot, 0, offset, HEAP_DIRECT_PAGE);
        if (rc) sceKernelReleaseDirectMemory(offset, size);
    }
    if (!rc)
    {
        heap_directs[heap_direct_count++] = (struct heap_direct){(uintptr_t)at, size, offset};
        heap_direct_bytes += size;
    }
    uint64_t total = heap_direct_bytes;
    unsigned count = heap_direct_count;
    heap_direct_leave();
    heap_direct_line(size, error, rc, rc ? 0 : (uintptr_t)at, total, count);
    if (rc)
    {
        errno = error;
        return result;
    }
    memset(at, 0, size);  /* an anonymous map is zeroed; musl's calloc relies on it */
    errno = error;
    return at;
}
int __wrap___munmap(void *addr, size_t len)
{
    struct heap_direct found = {0, 0, 0};

    if (__atomic_load_n(&heap_direct_count, __ATOMIC_RELAXED))
    {
        heap_direct_enter();
        for (unsigned i = 0; i < heap_direct_count; i++)
            if (heap_directs[i].base == (uintptr_t)addr)
            {
                found = heap_directs[i];
                heap_directs[i] = heap_directs[--heap_direct_count];
                heap_direct_bytes -= found.size;
                break;
            }
        heap_direct_leave();
    }
    if (!found.base) return __real___munmap(addr, len);
    int result = __real___munmap(addr, found.size);
    sceKernelReleaseDirectMemory(found.offset, found.size);
    return result;
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
