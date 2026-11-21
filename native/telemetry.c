/* SPDX-License-Identifier: LGPL-2.1-or-later
 * CPU: title process CPU clock / wall time / initial libkernel affinity capacity.
 * GPU: Crema's GPU timestamps, merged in the single GFX submission queue order.
 * Unsupported clocks, counter loss and warmup remain invalid, never fake zero.
 */
#include <errno.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <sys/resource.h>
#include "pw_telemetry.h"
#include "pw_trace.h"
extern void *scePthreadSelf(void);
extern void scePthreadGetaffinity(void *, uint64_t *);
extern uint64_t sceKernelGetProcessTime(void);
extern void ac_ps4_get_gpu_app_busy(uint64_t *,uint64_t *,uint64_t *);
/* 04.20: platform/ps4/pw_wine_sink_ps4.c, what the screen showed of the image frame generation follows, in its last
 * measured second; 1 while that second is recent. Weak: a link without the hardware sink reports nothing. */
extern int pw_hw_sink_fg_rate(unsigned *width,unsigned *height,unsigned *shown_tenths,unsigned *real_tenths,
                              unsigned *generated_tenths,uint64_t *sample_us) __attribute__((weak));

static pthread_mutex_t lock=PTHREAD_MUTEX_INITIALIZER;
static struct pw_ps4_telemetry cached;
static uint64_t previous_wall,previous_cpu,previous_busy,previous_span,previous_lost;
static uint64_t affinity;
static unsigned cores, initialized;

void pw_telemetry_init(void)
{
    /* Capture the title's initial CPU capacity before individual workers change affinity.
     * The SDK declares this output API void: validate the written mask, not an invented rc. */
    scePthreadGetaffinity(scePthreadSelf(),&affinity);
    if (affinity && !(affinity & ~UINT64_C(255))) cores=(unsigned)__builtin_popcountll(affinity);
    initialized=1;
    fprintf(stderr,"PWTELEM init affinity=%llx cores=%u cpu_source=getrusage_self gpu=crema_gfx_union\n",
            (unsigned long long)affinity,cores);
}

/* W112: process CPU times for NtQuerySystemInformation (Task Manager), in 100 ns units.
 * Same sources as the HUD: title wall clock, getrusage(RUSAGE_SELF) and the initial
 * affinity capacity. Returns 0 or a negative errno; nothing is filled on failure. */
int pw_ps4_cpu_times(uint64_t *wall,uint64_t *busy,uint64_t *sys,unsigned *capacity)
{
    struct rusage usage;
    if (!initialized || !cores) return -ENOTSUP;
    memset(&usage,0,sizeof(usage));
    if (getrusage(RUSAGE_SELF,&usage)) return -errno;
    if (usage.ru_utime.tv_sec<0 || usage.ru_stime.tv_sec<0 ||
        usage.ru_utime.tv_usec<0 || usage.ru_utime.tv_usec>=1000000 ||
        usage.ru_stime.tv_usec<0 || usage.ru_stime.tv_usec>=1000000) return -ERANGE;
    *wall=sceKernelGetProcessTime()*10;
    *sys=(uint64_t)usage.ru_stime.tv_sec*10000000+(uint64_t)usage.ru_stime.tv_usec*10;
    *busy=(uint64_t)usage.ru_utime.tv_sec*10000000+(uint64_t)usage.ru_utime.tv_usec*10+*sys;
    *capacity=cores;
    return 0;
}

uint32_t pw_ps4_telemetry_query(void *info,uint32_t bytes,uint32_t *returned)
{
    uint64_t now=sceKernelGetProcessTime()*1000, cpu=0,busy=0,span=0,lost=0;
    struct rusage usage;
    int rc;
    /* 04.20: a buffer for struct pw_ps4_telemetry_fg (MangoHud's FPS row) gets version 2; 80 bytes, version 1 as before */
    int extended=bytes>=sizeof(struct pw_ps4_telemetry_fg);
    if (returned) *returned=extended?sizeof(struct pw_ps4_telemetry_fg):sizeof(cached);
    if (bytes<sizeof(cached)) return 0xc0000004u;
    if (!info) return 0xc0000005u;
    pthread_mutex_lock(&lock);
    if (!cached.sample_ns || now-cached.sample_ns>=UINT64_C(500000000))
    {
        memset(&cached,0,sizeof(cached));
        cached.size=sizeof(cached);cached.version=PW_TELEMETRY_VERSION;
        cached.sample_ns=now;cached.affinity_mask=affinity;cached.cpu_cores=cores;
        /* W103's imported clock 15 advanced as wall time on hardware. Use the
         * process's accumulated user + kernel CPU time instead. No per-core
         * idle times are inferred from this process accounting. */
        memset(&usage,0,sizeof(usage));
        rc=getrusage(RUSAGE_SELF,&usage);
        cached.cpu_status=rc ? (rc==-1?-errno:rc) : (cores && initialized ? 1 : -ENOTSUP);
        if (!rc && usage.ru_utime.tv_sec>=0 && usage.ru_stime.tv_sec>=0 &&
            usage.ru_utime.tv_usec>=0 && usage.ru_utime.tv_usec<1000000 &&
            usage.ru_stime.tv_usec>=0 && usage.ru_stime.tv_usec<1000000)
        {
            cpu=((uint64_t)usage.ru_utime.tv_sec+(uint64_t)usage.ru_stime.tv_sec)*UINT64_C(1000000000)+
                ((uint64_t)usage.ru_utime.tv_usec+(uint64_t)usage.ru_stime.tv_usec)*1000;
            cached.cpu_time_ns=cpu;
            if (previous_wall && cpu>=previous_cpu && cores && initialized && now>previous_wall)
            {
                double value=(double)(cpu-previous_cpu)*100000.0/((double)(now-previous_wall)*cores);
                if (value>=0 && value<=100500.0)
                {
                    cached.cpu_millipercent=(uint32_t)(value>100000.0?100000.0:value);
                    cached.flags|=PW_CPU_VALID;cached.cpu_status=0;
                }
                else cached.cpu_status=-ERANGE;
            }
        }
        else if (!rc) cached.cpu_status=-ERANGE;
        ac_ps4_get_gpu_app_busy(&busy,&span,&lost);
        cached.gpu_busy_ticks=busy;cached.gpu_span_ticks=span;cached.gpu_lost_events=lost;
        cached.gpu_status=1; /* warmup or no completed timestamp span */
        if (previous_wall && span>previous_span && busy>=previous_busy && lost==previous_lost)
        {
            uint64_t db=busy-previous_busy,ds=span-previous_span;
            if (db<=ds)
            {
                cached.gpu_millipercent=(uint32_t)((double)db*100000.0/(double)ds);
                cached.flags|=PW_GPU_VALID;cached.gpu_status=0;
            }
            else cached.gpu_status=3; /* counter window inconsistency, don't clamp it to 100 */
        }
        if (lost!=previous_lost) cached.gpu_status=2;
        /* alpha-1: up to two lines a second while MangoHud or Task Manager asks; traces only (pw_trace.h) */
        if (pw_trace_on()) fprintf(stderr,"PWTELEM sample wall_ns=%llu cpu_ns=%llu cores=%u cpu_mp=%u cpu_rc=%d gpu_busy=%llu gpu_span=%llu gpu_mp=%u gpu_rc=%d lost=%llu flags=%x\n",
                (unsigned long long)now,(unsigned long long)cpu,cores,cached.cpu_millipercent,cached.cpu_status,
                (unsigned long long)busy,(unsigned long long)span,cached.gpu_millipercent,cached.gpu_status,
                (unsigned long long)lost,cached.flags);
        previous_wall=now;previous_cpu=cpu;previous_busy=busy;previous_span=span;previous_lost=lost;
    }
    if (!extended) {
        memcpy(info,&cached,sizeof(cached));
        pthread_mutex_unlock(&lock);
        return 0;
    }
    struct pw_ps4_telemetry_fg fg;
    memset(&fg,0,sizeof(fg));
    fg.base=cached;
    pthread_mutex_unlock(&lock);
    fg.base.size=sizeof(fg);fg.base.version=PW_TELEMETRY_FG_VERSION;
    /* read every call, not on the 500 ms sample: the sink publishes once a second and the HUD asks often */
    {
        unsigned width=0,height=0,shown=0,real=0,generated=0;uint64_t sample_us=0;
        if (pw_hw_sink_fg_rate && pw_hw_sink_fg_rate(&width,&height,&shown,&real,&generated,&sample_us))
        {
            fg.fg_flags=PW_FG_SHOWN;fg.fg_width=width;fg.fg_height=height;
            fg.fg_shown_tenths=shown;fg.fg_real_tenths=real;fg.fg_generated_tenths=generated;fg.fg_sample_ns=sample_us*1000;
        }
    }
    {
        static int logged;  /* once: the first caller that asked for version 2 (MangoHud 04.20) */
        if (!__atomic_exchange_n(&logged,1,__ATOMIC_RELAXED))
            fprintf(stderr,"PWTELEM framegen query bytes=%u version=%u fg_flags=%x\n",bytes,fg.base.version,fg.fg_flags);
    }
    memcpy(info,&fg,sizeof(fg));
    return 0;
}
