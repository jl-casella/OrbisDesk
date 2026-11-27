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
#include "pw_trace.h"

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
#include <sys/resource.h>
#include "pw_present_trace.inc.c"
/* the kernel clock in microseconds: clock_gettime here is the kernel's, with FreeBSD clock
 * ids that the SDK headers do not use */
extern uint64_t sceKernelGetProcessTime( void );

int pw_perf_level;
int pw_vk_perf_enabled(void) {return pw_perf_on();}
void pw_perf_thread_report(unsigned wine_tid);

static pthread_mutex_t queue_perf_lock = PTHREAD_MUTEX_INITIALIZER;
static uint64_t queue_start, queue_sum[2], queue_maximum[2], queue_total[2];
static unsigned queue_count[2], queue_failed, queue_waits, queue_first;

/* Caller holds queue_perf_lock. Totals never reset, including across quiet periods. */
static void queue_perf_report(uint64_t now, const char *reason)
{
    fprintf(stderr, "PWQUEUE window_us=%llu async=%u cpu=%u waits=%u async_us=%llu cpu_us=%llu "
            "async_max_us=%llu cpu_max_us=%llu failed=%u total_async=%llu total_cpu=%llu reason=%s\n",
            (unsigned long long)(now-queue_start),queue_count[0],queue_count[1],queue_waits,
            (unsigned long long)(queue_sum[0]/1000),(unsigned long long)(queue_sum[1]/1000),
            (unsigned long long)(queue_maximum[0]/1000),(unsigned long long)(queue_maximum[1]/1000),queue_failed,
            (unsigned long long)queue_total[0],(unsigned long long)queue_total[1],reason);
    queue_start=now;queue_sum[0]=queue_sum[1]=queue_maximum[0]=queue_maximum[1]=0;
    queue_count[0]=queue_count[1]=queue_failed=queue_waits=0;
}

void pw_vk_perf_flush(const char *reason)
{
    uint64_t now;
    if (!pw_perf_on()) return;
    now=sceKernelGetProcessTime();
    pthread_mutex_lock(&queue_perf_lock);
    if (!queue_start) queue_start=now;
    queue_perf_report(now,reason);
    pthread_mutex_unlock(&queue_perf_lock);
}

static void *perf_monitor(void *unused)
{
    extern int sceKernelUsleep(unsigned);
    (void)unused;
    for (;;) {
        for (unsigned i=0;i<5;i++) {
            int result=sceKernelUsleep(1000000);
            if(result) {fprintf(stderr,"PWQUEUE monitor sleep_failed=%d\n",result);return NULL;}
        }
        pw_vk_perf_flush("timer");
    }
    return NULL;
}

int pw_vk_perf_monitor_start(void)
{
    extern void (*pw_perf_thread_hook)(unsigned);
    static int started;
    pthread_t thread;
    int result;
    if (!pw_perf_level || __sync_lock_test_and_set(&started,1)) return 0;
    pw_perf_thread_hook=pw_perf_thread_report;
    result=pthread_create(&thread,NULL,perf_monitor,NULL);
    if (result) started=0;
    else pthread_detach(thread);
    return result;
}

/* First use is observable even if the title ends before a periodic report. */
void pw_vk_empty_submit_event(int cpu, unsigned waits, uint64_t ns, int result)
{
    uint64_t now;
    if (!pw_perf_on()) return;
    now = sceKernelGetProcessTime();
    cpu = !!cpu;
    pthread_mutex_lock(&queue_perf_lock);
    if (!queue_start) queue_start = now;
    ++queue_count[cpu];++queue_total[cpu];queue_sum[cpu] += ns;
    if (ns > queue_maximum[cpu]) queue_maximum[cpu] = ns;
    queue_waits += waits;queue_failed += result != 0;
    if (!queue_first++) queue_perf_report(now,"first-use");
    else if (now - queue_start >= 5000000) queue_perf_report(now,"submit");
    pthread_mutex_unlock(&queue_perf_lock);
}

/* WoW64 calls this on the profiled thread, with host FS active. Cumulative CPU/I/O
 * counters accompany its TSC buckets; differences between two lines form a sample. */
void pw_perf_thread_report(unsigned wine_tid)
{
    extern void pw_wine_thread_alert_report(unsigned);
    extern void pw_optrace_report(unsigned) __attribute__((weak));
    struct rusage usage;
    extern int pthread_getthreadid_np(void);
#ifndef RUSAGE_THREAD
#define RUSAGE_THREAD 1
#endif
    if (!pw_perf_on()) return;
    pw_wine_thread_alert_report(wine_tid);
    if(pw_optrace_report)pw_optrace_report(wine_tid);
    if (getrusage(RUSAGE_THREAD,&usage)) {
        fprintf(stderr,"PWTHREADPERF wine_tid=%04x cpu_available=0\n",wine_tid);
        return;
    }
    fprintf(stderr,"PWTHREADPERF wine_tid=%04x native_tid=%d wall_us=%llu user_us=%llu kernel_us=%llu "
            "io_in_blocks=%ld io_out_blocks=%ld voluntary=%ld involuntary=%ld minor_faults=%ld major_faults=%ld\n",
            wine_tid,pthread_getthreadid_np(),(unsigned long long)sceKernelGetProcessTime(),
            (unsigned long long)usage.ru_utime.tv_sec*1000000+usage.ru_utime.tv_usec,
            (unsigned long long)usage.ru_stime.tv_sec*1000000+usage.ru_stime.tv_usec,
            usage.ru_inblock,usage.ru_oublock,usage.ru_nvcsw,usage.ru_nivcsw,usage.ru_minflt,usage.ru_majflt);
}

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

/* Frame generation, stage 1 (docs/FRAME_GENERATION.md): every present, with its process time in
 * microseconds, for whoever set the hook (the hardware sink, pw_wine_sink_ps4.c). A pointer, not a
 * call: the ELFs that link this file without that sink (the PoP child) leave it NULL. It runs on the
 * presenting thread before the present returns, so the pixels are still the ones just presented. */
void (*pw_vk_present_hook)( const void *swapchain, const void *pixels, unsigned int pitch, unsigned int width,
                            unsigned int height, int format, uint64_t present_us );

/* 04.26: every Vulkan present so far, all swapchains; the overlay (native/hw_overlay.c) holds MangoHud's key until
 * one comes after it, since MangoHud reads its key in its present hook, before this one */
static volatile unsigned int present_count;
unsigned int pw_wine_vk_presents( void );
unsigned int pw_wine_vk_presents( void )
{
    return present_count;
}

static void presented( const void *swapchain, const void *pixels, uint32_t pitch, uint32_t width, uint32_t height,
                       int format, uint64_t blit_wait_ns )
{
    unsigned int fps_tenths = 0;
    static unsigned int count, second_count;
    static uint64_t second_wait_ns;
    static uint64_t second_start;
    uint64_t now = sceKernelGetProcessTime();
    unsigned int i;

    pw_present_trace_begin(swapchain,now,pw_perf_on());
    pthread_mutex_lock( &frames_lock );
    pw_present_trace_mark(PW_PRESENT_METADATA);
    present_count++;  /* 04.26 */
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
        /* W074: and how long each present waited for the blit into the CPU buffer. alpha-1: a line a second for
         * the whole game, traces only (pw_trace.h); the overlay's counter below keeps the value */
        if (pw_perf_on()) fprintf( stderr, "PWVK present fps %.1f (%u presents, %ux%u format %d) blit_wait_us=%llu\n",
                 second_count / seconds, count, width, height, format,
                 (unsigned long long)(second_wait_ns / second_count / 1000) );
        fps_tenths = (unsigned int)(second_count * 10 / seconds + 0.5);
        second_start = now;
        second_count = 0;
        second_wait_ns = 0;
    }
    pthread_mutex_unlock( &frames_lock );
    if (fps_tenths) pw_wine_vk_fps( fps_tenths );
    pw_present_trace_mark(PW_PRESENT_PREPARE);
    if (pw_vk_present_hook) pw_vk_present_hook( swapchain, pixels, pitch, width, height, format, now );
    pw_present_trace_end(blit_wait_ns);
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
