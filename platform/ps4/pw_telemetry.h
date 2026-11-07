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
#if defined(__cplusplus)
static_assert(sizeof(pw_ps4_telemetry)==80, "telemetry ABI");
#else
_Static_assert(sizeof(struct pw_ps4_telemetry)==80, "telemetry ABI");
#endif
#endif
