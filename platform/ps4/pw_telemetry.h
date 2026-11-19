/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef PW_PS4_TELEMETRY_H
#define PW_PS4_TELEMETRY_H
#include <stdint.h>
#define PW_PS4_TELEMETRY_CLASS 0x50573454u /* private Wine/Orbis query, never a Windows CPU class */
#define PW_TELEMETRY_VERSION 1u
#define PW_CPU_VALID 1u
#define PW_GPU_VALID 2u
struct pw_ps4_telemetry {
    uint32_t size, version, flags, cpu_cores;
    uint64_t sample_ns, cpu_time_ns, gpu_busy_ticks, gpu_span_ticks;
    uint64_t gpu_lost_events, affinity_mask;
    uint32_t cpu_millipercent, gpu_millipercent;
    int32_t cpu_status, gpu_status;
};
/* 04.20, frame generation (docs/FRAME_GENERATION.md): a caller whose buffer holds this larger struct gets the same
 * fields plus what the screen shows of the image frame generation follows. size and version say which one was
 * filled: a caller that passes 80 bytes still gets version 1, unchanged. Fixed-width fields only, no padding:
 * the same layout in 32 and 64 bits (wow64 passes the query through, tools/build-wow64native-ps4.py). */
#define PW_TELEMETRY_FG_VERSION 2u
#define PW_FG_SHOWN 1u   /* generated frames reached the screen in the last measured second */
struct pw_ps4_telemetry_fg {
    struct pw_ps4_telemetry base;
    uint32_t fg_flags, fg_width, fg_height;                         /* the followed image's size: the swapchain's */
    uint32_t fg_shown_tenths, fg_real_tenths, fg_generated_tenths;  /* its frames a second on screen: all, real, generated */
    uint64_t fg_sample_ns;                                          /* title process time at the end of that second */
};
#if defined(__cplusplus)
static_assert(sizeof(pw_ps4_telemetry)==80, "telemetry ABI");
static_assert(sizeof(pw_ps4_telemetry_fg)==112, "telemetry ABI, frame generation");
#else
_Static_assert(sizeof(struct pw_ps4_telemetry)==80, "telemetry ABI");
_Static_assert(sizeof(struct pw_ps4_telemetry_fg)==112, "telemetry ABI, frame generation");
#endif
#endif
