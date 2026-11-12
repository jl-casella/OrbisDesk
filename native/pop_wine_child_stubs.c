/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* PoP Phase D.1b: the separate Wine process has no GPU of its own (the title owns RADV/GNM and the display).
 * The title's telemetry reads the GPU busy counters from Mesa; here there are none, so they stay zero and
 * telemetry reports its existing "warmup / no completed span" status, never a fabricated measurement. */
#include <stdint.h>
void ac_ps4_get_gpu_app_busy(uint64_t *busy, uint64_t *span, uint64_t *lost);
void ac_ps4_get_gpu_app_busy(uint64_t *busy, uint64_t *span, uint64_t *lost)
{
    if (busy) *busy = 0;
    if (span) *span = 0;
    if (lost) *lost = 0;
}

/* ntdll's NtCreateUserProcess hook records the starter's directory and variables for the title's program
 * switch (native/wine_hardware.c) before asking for it. This process cannot switch the title; the switch
 * request itself is the platform's weak ENOSYS (platform/ps4/pw_wine_platform.c), so nothing is recorded. */
void pw_hw_switch_context(const char *dir, const char *env);
void pw_hw_switch_context(const char *dir, const char *env)
{
    (void)dir; (void)env;
}

/* PoP D.3: win32u asks for a separate process's window under a point, which only the title composites;
 * this process has none of those. */
unsigned long long pw_hw_separate_window(int x, int y);
unsigned long long pw_hw_separate_window(int x, int y)
{
    (void)x; (void)y;
    return 0;
}
