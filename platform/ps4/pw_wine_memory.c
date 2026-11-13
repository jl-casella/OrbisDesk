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

/* What the walk saw last, for the boot line: run-0055 (12.50) stopped after 17 ranges with
 * rc 0 on a record the first version rejected, and its values were not logged. */
struct pw_dmem_walk { int32_t last_rc; unsigned ranges; int inclusive; const char *stop;
                      long long offset, start, end; int32_t type; };

/* bytes of direct memory this title has allocated below `direct`, or -1 when the walk did not
 * finish cleanly. Two readings of a record are accepted: `end` one past the range (shadPS4) or
 * the range's last byte, which shows as the same record coming back for a query at its end;
 * the walk then counts `end` inclusively. A range reaching past `direct` is counted up to it. */
static long long pw_direct_allocated( size_t direct, struct pw_dmem_walk *w )
{
    struct pw_dmem_query query;
    off_t offset = 0, last_start = -1, last_end = -1;
    long long allocated = 0;
    unsigned n;

    w->ranges = 0; w->inclusive = 0; w->stop = "limit";
    for (n = 0; n < PW_DMQ_WALK_MAX && (size_t)offset < direct; n++)
    {
        int32_t rc = sceKernelDirectMemoryQuery( offset, PW_DMQ_FIND_NEXT, &query, sizeof(query) );
        off_t from, to;

        w->last_rc = rc; w->offset = offset;
        if (rc == PW_KERNEL_EACCES) { w->stop = "end"; return allocated; }
        if (rc) { w->stop = "rc"; return -1; }
        w->start = query.start; w->end = query.end; w->type = query.type;
        if (query.start == last_start && query.end == last_end && !w->inclusive && query.end == offset)
        {
            /* the query at a record's end returned that record: ends are its last byte */
            w->inclusive = 1;
            allocated += w->ranges;  /* one byte more for each range counted so far */
            offset = query.end + 1;
            continue;
        }
        to = w->inclusive ? query.end + 1 : query.end;
        if (to <= query.start) { w->stop = "empty"; return -1; }
        if (to <= offset) { w->stop = "backwards"; return -1; }
        from = query.start > offset ? query.start : offset;
        if ((size_t)from >= direct) { w->stop = "past_size"; return allocated; }
        if ((size_t)to > direct) to = (off_t)direct;
        allocated += to - from;
        last_start = query.start; last_end = query.end;
        offset = to;
        w->ranges++;
    }
    if ((size_t)offset >= direct) { w->stop = "size"; return allocated; }
    return -1;
}

int pw_wine_memory_info( unsigned long long *total, unsigned long long *available )
{
    static int logged, last_method = -1;
    static unsigned switches;
    size_t flexible = 0, direct = sceKernelGetDirectMemorySize(), direct_free = 0, largest = 0;
    off_t found = 0;
    int32_t flexible_result = sceKernelAvailableFlexibleMemorySize( &flexible );
    int32_t direct_result = sceKernelAvailableDirectMemorySize( 0, (off_t)direct, 0, &found, &largest );
    struct pw_dmem_walk walk = { 0, 0, 0, "none", -1, -1, -1, -1 };
    long long allocated = -1;
    int method;

    if (direct_result) largest = 0;
    if (direct) allocated = pw_direct_allocated( direct, &walk );
    /* summed when the walk finished and agrees with the largest free range */
    method = allocated >= 0 && (size_t)allocated <= direct && direct - (size_t)allocated >= largest;
    direct_free = method ? direct - (size_t)allocated : largest;

    if (!logged++)
        fprintf( stderr, "PWBOOT memory_info direct=%zu direct_free=%zu (rc=%#x) flexible_free=%zu (rc=%#x)"
                 " direct_largest_free=%zu direct_allocated=%lld ranges=%u query_rc=%#x free_source=%s"
                 " walk_stop=%s inclusive=%d last_offset=%#llx last_start=%#llx last_end=%#llx last_type=%d\n",
                 direct, direct_free, (unsigned)direct_result, flexible, (unsigned)flexible_result,
                 largest, allocated, walk.ranges, (unsigned)walk.last_rc, method ? "summed" : "largest_range",
                 walk.stop, walk.inclusive, walk.offset, walk.start, walk.end, walk.type );
    else if (method != last_method && switches++ < 16)
        fprintf( stderr, "PWMEM direct_free source=%s free=%zu largest=%zu allocated=%lld ranges=%u query_rc=%#x"
                 " walk_stop=%s inclusive=%d last_offset=%#llx last_start=%#llx last_end=%#llx\n",
                 method ? "summed" : "largest_range", direct_free, largest, allocated, walk.ranges,
                 (unsigned)walk.last_rc, walk.stop, walk.inclusive, walk.offset, walk.start, walk.end );
    last_method = method;
    if (flexible_result || !direct) return -1;
    *total = (unsigned long long)direct + flexible;
    *available = (unsigned long long)direct_free + flexible;
    return 0;
}
