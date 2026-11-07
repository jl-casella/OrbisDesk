/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* W080: how much memory this title has, for ntdll's SystemBasicInformation and
 * SystemPerformanceInformation (GlobalMemoryStatusEx). Until W079 the performance query was
 * STATUS_NOT_SUPPORTED on the PS4, so GlobalMemoryStatusEx failed and Mesa's Zink refused
 * to start ("failed to get total physical memory").
 *
 * A title has two pools: direct memory (the GPU's, and RADV's buffers) and flexible memory
 * (mmap, which Wine uses). The total is the direct memory size plus the flexible memory still
 * available; the available amount is the largest free direct memory range plus the flexible
 * memory available. Both are the kernel's figures at the time of the call. The kernel does
 * not report the flexible pool's configured size or the direct memory free in total, so
 * these are not Windows' exact physical memory figures; each call's numbers are logged once.
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

int pw_wine_memory_info( unsigned long long *total, unsigned long long *available );

int pw_wine_memory_info( unsigned long long *total, unsigned long long *available )
{
    static int logged;
    size_t flexible = 0, direct = sceKernelGetDirectMemorySize(), direct_free = 0;
    off_t found = 0;
    int32_t flexible_result = sceKernelAvailableFlexibleMemorySize( &flexible );
    int32_t direct_result = sceKernelAvailableDirectMemorySize( 0, (off_t)direct, 0, &found, &direct_free );

    if (!logged++)
        fprintf( stderr, "PWBOOT memory_info direct=%zu direct_free=%zu (rc=%#x) flexible_free=%zu (rc=%#x)\n",
                 direct, direct_free, (unsigned)direct_result, flexible, (unsigned)flexible_result );
    if (flexible_result || !direct) return -1;
    if (direct_result) direct_free = 0;
    *total = (unsigned long long)direct + flexible;
    *available = (unsigned long long)direct_free + flexible;
    return 0;
}
