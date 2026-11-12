/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* W080: how much memory this title has, for ntdll's SystemBasicInformation and
 * SystemPerformanceInformation (GlobalMemoryStatusEx). Until W079 the performance query was
 * STATUS_NOT_SUPPORTED on the PS4, so GlobalMemoryStatusEx failed and Mesa's Zink refused
 * to start ("failed to get total physical memory").
 *
 * A title has two pools: direct memory (the GPU's, RADV's buffers and, since W175, Wine's
 * commits of 1 MiB or more) and flexible memory (mmap). The total is the direct memory size plus
 * the flexible memory still available. The kernel does not report the flexible pool's
 * configured size, so the total leaves out flexible memory already in use and is not Windows'
 * exact physical memory figure. Each call's numbers come from the kernel at the time of the call.
 *
 * Free direct memory: sceKernelAvailableDirectMemorySize answers with the largest free range
 * only. Since W175 Wine allocates and partly releases direct memory per commit, so the free
 * space splits into many ranges, and the largest one alone understates what is free. The
 * allocated ranges are walked instead (sceKernelDirectMemoryQuery, find-next) and free = size -
 * allocated. The largest range stays the figure when the walk fails or disagrees with it (free
 * in total below the largest free range). The first answer is logged, and so is every switch
 * between the two methods.
 *
 * The SDK's orbis/libkernel.h declares the two Available functions with their output
 * pointers as plain values, so they are declared here as the kernel takes them. */
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <sys/types.h>

extern size_t sceKernelGetDirectMemorySize( void );
extern int32_t sceKernelAvailableFlexibleMemorySize( size_t *size );
extern int32_t sceKernelAvailableDirectMemorySize( off_t start, off_t end, size_t alignment, off_t *found,
                                                   size_t *size );
extern int32_t sceKernelDirectMemoryQuery( off_t offset, int32_t flags, void *info, size_t info_size );

int pw_wine_memory_info( unsigned long long *total, unsigned long long *available );

/* SceKernelDirectMemoryQueryInfo */
struct pw_dmem_query { off_t start, end; int32_t type; };
enum { PW_DMQ_FIND_NEXT = 1, PW_DMQ_WALK_MAX = 65536 };
#define PW_KERNEL_EACCES ((int32_t)0x8002000d)  /* no allocated range at or after the offset */

/* bytes of direct memory this title has allocated, or -1 when the walk did not finish cleanly */
static long long pw_direct_allocated( size_t direct, int32_t *last_rc, unsigned *ranges )
{
    struct pw_dmem_query query;
    off_t offset = 0;
    long long allocated = 0;
    unsigned n;

    *ranges = 0;
    for (n = 0; n < PW_DMQ_WALK_MAX && (size_t)offset < direct; n++)
    {
        int32_t rc = sceKernelDirectMemoryQuery( offset, PW_DMQ_FIND_NEXT, &query, sizeof(query) );
        *last_rc = rc;
        if (rc == PW_KERNEL_EACCES) return allocated;
        if (rc) return -1;
        if (query.end <= query.start || query.end <= offset || (size_t)query.end > direct) return -1;
        allocated += query.end - (query.start > offset ? query.start : offset);
        offset = query.end;
        (*ranges)++;
    }
    return (size_t)offset >= direct ? allocated : -1;
}

int pw_wine_memory_info( unsigned long long *total, unsigned long long *available )
{
    static int logged, last_method = -1;
    static unsigned switches;
    size_t flexible = 0, direct = sceKernelGetDirectMemorySize(), direct_free = 0, largest = 0;
    off_t found = 0;
    int32_t flexible_result = sceKernelAvailableFlexibleMemorySize( &flexible );
    int32_t direct_result = sceKernelAvailableDirectMemorySize( 0, (off_t)direct, 0, &found, &largest );
    int32_t query_rc = 0;
    unsigned ranges = 0;
    long long allocated = -1;
    int method;

    if (direct_result) largest = 0;
    if (direct) allocated = pw_direct_allocated( direct, &query_rc, &ranges );
    /* summed when the walk finished and agrees with the largest free range */
    method = allocated >= 0 && (size_t)allocated <= direct && direct - (size_t)allocated >= largest;
    direct_free = method ? direct - (size_t)allocated : largest;

    if (!logged++)
        fprintf( stderr, "PWBOOT memory_info direct=%zu direct_free=%zu (rc=%#x) flexible_free=%zu (rc=%#x)"
                 " direct_largest_free=%zu direct_allocated=%lld ranges=%u query_rc=%#x free_source=%s\n",
                 direct, direct_free, (unsigned)direct_result, flexible, (unsigned)flexible_result,
                 largest, allocated, ranges, (unsigned)query_rc, method ? "summed" : "largest_range" );
    else if (method != last_method && switches++ < 16)
        fprintf( stderr, "PWMEM direct_free source=%s free=%zu largest=%zu allocated=%lld ranges=%u query_rc=%#x\n",
                 method ? "summed" : "largest_range", direct_free, largest, allocated, ranges, (unsigned)query_rc );
    last_method = method;
    if (flexible_result || !direct) return -1;
    *total = (unsigned long long)direct + flexible;
    *available = (unsigned long long)direct_free + flexible;
    return 0;
}
