/* W070 (H1): runtime pieces Mesa's RADV needs inside Wine's ELF.
 *
 * pthread_once: the kernel's version (the one this ELF links) treats pthread_once_t as a
 * 16-byte structure, while the OpenOrbis headers declare a 4-byte int, so it writes past the
 * variable (DolphinPS4 port/ps4_runtime.cpp, __wrap_pthread_once). Mesa and libc++abi are
 * built or rewritten to call this one, which uses only those 4 bytes:
 * 0 = not run (PTHREAD_ONCE_INIT), 1 = running, 2 = done. */
#include <pthread.h>
#include <sched.h>
#include <string.h>

typedef void (*pw_vk_function)(void);
extern pw_vk_function vk_icdGetInstanceProcAddr( void *instance, const char *name );
extern pw_vk_function vk_common_GetDeviceProcAddr( void *device, const char *name );

/* W071 (H2): win32u's vkGetInstanceProcAddr. RADV's ICD lookup (the loader interface, there
 * is no Vulkan loader here) does not return vkGetDeviceProcAddr, which win32u asks it for;
 * that one is the Vulkan runtime's (prospero-win wine/ps5/pw_vulkan_radv.c does the same). */
pw_vk_function pw_vk_get_instance_proc_addr( void *instance, const char *name );

pw_vk_function pw_vk_get_instance_proc_addr( void *instance, const char *name )
{
    if (name && !strcmp( name, "vkGetDeviceProcAddr" )) return (pw_vk_function)vk_common_GetDeviceProcAddr;
    return vk_icdGetInstanceProcAddr( instance, name );
}

/* W072 (H3): the last image each headless swapchain presented. Mesa calls presented() from
 * the presenting thread once the image is in its CPU buffer (tools/vk-h0/patch-mesa-wsi.py);
 * win32u, on the same thread right after, takes it with last_frame() and draws it into the
 * window. The pixels stay valid until the application acquires and presents that image
 * again, which it cannot do before this present returns. */
#include <stdint.h>
#include <stdio.h>
/* the kernel clock in microseconds: clock_gettime here is the kernel's, with FreeBSD clock
 * ids that the SDK headers do not use */
extern uint64_t sceKernelGetProcessTime( void );

enum { PW_VK_SWAPCHAINS = 8 };
static struct
{
    const void *swapchain, *pixels;
    unsigned int pitch, width, height;
    int format;
} frames[PW_VK_SWAPCHAINS];
static unsigned int next_slot;
static pthread_mutex_t frames_lock = PTHREAD_MUTEX_INITIALIZER;

/* platform/ps4/pw_wine_sink_ps4.c (W165): the presents per second for its F12 frame counter */
extern void pw_wine_vk_fps( unsigned int tenths );

static void presented( const void *swapchain, const void *pixels, uint32_t pitch, uint32_t width, uint32_t height,
                       int format, uint64_t blit_wait_ns )
{
    unsigned int fps_tenths = 0;
    static unsigned int count, second_count;
    static uint64_t second_wait_ns;
    static uint64_t second_start;
    uint64_t now = sceKernelGetProcessTime();
    unsigned int i;

    pthread_mutex_lock( &frames_lock );
    for (i = 0; i < PW_VK_SWAPCHAINS && frames[i].swapchain != swapchain; i++) {}
    if (i == PW_VK_SWAPCHAINS) i = next_slot++ % PW_VK_SWAPCHAINS;
    frames[i].swapchain = swapchain;
    frames[i].pixels = pixels;
    frames[i].pitch = pitch;
    frames[i].width = width;
    frames[i].height = height;
    frames[i].format = format;
    /* presents per second, all swapchains together */
    if (!count++) second_start = now;
    second_count++;
    second_wait_ns += blit_wait_ns;
    if (now - second_start >= 1000000)
    {
        double seconds = (now - second_start) / 1e6;
        /* W074: and how long each present waited for the blit into the CPU buffer */
        fprintf( stderr, "PWVK present fps %.1f (%u presents, %ux%u format %d) blit_wait_us=%llu\n",
                 second_count / seconds, count, width, height, format,
                 (unsigned long long)(second_wait_ns / second_count / 1000) );
        fps_tenths = (unsigned int)(second_count * 10 / seconds + 0.5);
        second_start = now;
        second_count = 0;
        second_wait_ns = 0;
    }
    pthread_mutex_unlock( &frames_lock );
    if (fps_tenths) pw_wine_vk_fps( fps_tenths );
}

static int last_frame( const void *swapchain, const void **pixels, unsigned int *pitch, unsigned int *width,
                       unsigned int *height, int *format )
{
    unsigned int i;
    int found = 0;

    pthread_mutex_lock( &frames_lock );
    for (i = 0; i < PW_VK_SWAPCHAINS; i++)
    {
        if (frames[i].swapchain != swapchain) continue;
        *pixels = frames[i].pixels;
        *pitch = frames[i].pitch;
        *width = frames[i].width;
        *height = frames[i].height;
        *format = frames[i].format;
        found = 1;
        break;
    }
    pthread_mutex_unlock( &frames_lock );
    return found;
}

/* platform/ps4/pw_wine_unixlibs.c and Mesa's headless WSI */
extern void *(*pw_vk_instance_proc_addr)( void *instance, const char *name );
extern int (*pw_vk_last_frame)( const void *swapchain, const void **pixels, unsigned int *pitch, unsigned int *width,
                                unsigned int *height, int *format );
extern void (*pw_wsi_headless_presented)( const void *swapchain, const void *pixels, uint32_t pitch, uint32_t width,
                                          uint32_t height, int format, uint64_t blit_wait_ns );

/* called by the hardware launcher before Wine starts */
void pw_vk_runtime_init( void );

void pw_vk_runtime_init( void )
{
    pw_vk_instance_proc_addr = (void *(*)( void *, const char * ))pw_vk_get_instance_proc_addr;
    pw_vk_last_frame = last_frame;
    pw_wsi_headless_presented = presented;
}

int pw_vk_pthread_once( pthread_once_t *once, void (*init)(void) );

int pw_vk_pthread_once( pthread_once_t *once, void (*init)(void) )
{
    int *state = (int *)once, expected = 0;

    if (__atomic_load_n( state, __ATOMIC_ACQUIRE ) == 2) return 0;
    if (__atomic_compare_exchange_n( state, &expected, 1, 0, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE ))
    {
        init();
        __atomic_store_n( state, 2, __ATOMIC_RELEASE );
        return 0;
    }
    while (__atomic_load_n( state, __ATOMIC_ACQUIRE ) != 2) sched_yield();
    return 0;
}

/* W081: Crema's winsys (upstream/Crema/port/mesa/ac_ps4_drm.c) calls two helpers of Crema's
 * runtime: ps4_boot_trace, its startup trace (port/ps4_crashlog.cpp; here the run log), and
 * ps4_boost_thread, which raises its submission thread above the default priority
 * (port/ps4_runtime.cpp: scePthreadSetprio 650). */
extern void *scePthreadSelf( void );
extern int scePthreadSetprio( void *thread, int priority );

void ps4_boot_trace( const char *stage );
void ps4_boost_thread( void );

void ps4_boot_trace( const char *stage )
{
    size_t length = strlen( stage );
    fprintf( stderr, "PWVK boot %s%s", stage, length && stage[length - 1] == '\n' ? "" : "\n" );
}

void ps4_boost_thread( void )
{
    int result = scePthreadSetprio( scePthreadSelf(), 650 );
    if (result) fprintf( stderr, "PWVK boost_thread scePthreadSetprio failed %#x\n", (unsigned)result );
}
