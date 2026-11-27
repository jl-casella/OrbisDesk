/* SPDX-License-Identifier: LGPL-2.1-or-later
 * Included by the canonical Wine sync.c overlay, after Wine's headers.
 * A single kernel event bit has the same coalescing/consume semantics as the
 * existing process-local auto-reset server event. No Windows object handles
 * or cross-process waits are redirected here. */
#include <orbis/libkernel.h>
#include <orbis/_types/errors.h>

static int pw_alert_enabled, pw_alert_diagnostics;
static unsigned pw_alert_create_failures;
static __thread struct
{
    unsigned long long sets, waits, fallback_sets, fallback_waits;
    unsigned long long timeouts, errors, wait_ticks, max_ticks;
} pw_alert_stats;

void pw_wine_thread_alert_configure( int enabled, int diagnostics )
{
    /* Called before Wine starts; never switch the backend of a live entry. */
    pw_alert_enabled = enabled;
    pw_alert_diagnostics = diagnostics;
}

void pw_wine_thread_alert_report( unsigned tid )
{
    if (!pw_alert_diagnostics) return;
    fprintf( stderr, "PWALERTPERF tid=%04x sets=%llu waits=%llu fallback_sets=%llu fallback_waits=%llu "
             "timeouts=%llu errors=%llu wait_ticks=%llu max_ticks=%llu\n", tid,
             pw_alert_stats.sets, pw_alert_stats.waits,
             pw_alert_stats.fallback_sets, pw_alert_stats.fallback_waits,
             pw_alert_stats.timeouts, pw_alert_stats.errors,
             pw_alert_stats.wait_ticks, pw_alert_stats.max_ticks );
}

static unsigned long long pw_alert_tsc(void)
{
    unsigned lo, hi;
    __asm__ volatile( "lfence; rdtsc" : "=a"(lo), "=d"(hi) : : "memory" );
    return ((unsigned long long)hi << 32) | lo;
}

/* NULL means uninitialized, -1 permanently selects Wine's original fallback.
 * Each racing initializer publishes exactly one immutable backend choice. */
#define PW_ALERT_SERVER ((OrbisKernelEventFlag)(LONG_PTR)-1)
static OrbisKernelEventFlag pw_alert_create(void)
{
    OrbisKernelEventFlag event = NULL;
    int ret;
    if (!pw_alert_enabled) return PW_ALERT_SERVER;
    /* FIFO, multiple waiters; wait atomically consumes bit 1 (OR|CLEAR_PAT).
     * Multiple mode also tolerates Wine TID reuse, as the old server event did. */
    ret = sceKernelCreateEventFlag( &event, "wine-tid-alert", 0x21, 0, NULL );
    if (!ret) return event;
    if (__sync_fetch_and_add( &pw_alert_create_failures, 1 ) < 4)
        fprintf( stderr, "PWALERT create_failed=%#x backend=server\n", ret );
    return PW_ALERT_SERVER;
}

static NTSTATUS pw_alert_set( OrbisKernelEventFlag event )
{
    int ret = sceKernelSetEventFlag( event, 1 );
    if (pw_alert_diagnostics)
    {
        pw_alert_stats.sets++;
        pw_alert_stats.errors += ret != 0;
    }
    return ret ? STATUS_INVALID_HANDLE : STATUS_SUCCESS;
}

static NTSTATUS pw_alert_wait( OrbisKernelEventFlag event, const LARGE_INTEGER *timeout )
{
    BOOL finite = timeout && timeout->QuadPart != TIMEOUT_INFINITE;
    ULONGLONG end = 0, start = pw_alert_diagnostics ? pw_alert_tsc() : 0;
    NTSTATUS status;
    if (finite)
    {
        if (timeout->QuadPart < 0)
        {
            LARGE_INTEGER now;
            NtQuerySystemTime( &now );
            /* Avoid signed overflow for INT64_MIN and very long delays. */
            end = (ULONGLONG)now.QuadPart + (ULONGLONG)(-(timeout->QuadPart + 1)) + 1;
        }
        else end = timeout->QuadPart;
    }
    for (;;)
    {
        OrbisKernelUseconds micros = 0;
        ULONGLONG left = 0;
        int ret;
        if (finite)
        {
            LARGE_INTEGER now;
            NtQuerySystemTime( &now );
            if (end > (ULONGLONG)now.QuadPart) left = end - now.QuadPart;
            ULONGLONG us = left / 10 + !!(left % 10);
            micros = us > 0xffffffffu ? 0xffffffffu : us;
        }
        /* A zero timeout still checks and consumes a pending alert. No separate
         * poll/clear sequence that could lose a concurrent signal. */
        ret = sceKernelWaitEventFlag( event, 1, 0x22, NULL, finite ? &micros : NULL );
        if (!ret) { status = STATUS_ALERTED; break; }
        if ((unsigned)ret == ORBIS_KERNEL_ERROR_EINTR) continue;
        if ((unsigned)ret == ORBIS_KERNEL_ERROR_ETIMEDOUT && finite)
        {
            LARGE_INTEGER now;
            NtQuerySystemTime( &now );
            if (end > (ULONGLONG)now.QuadPart) continue; /* long wait or early wake */
            status = STATUS_TIMEOUT;
            break;
        }
        status = STATUS_INVALID_HANDLE;
        break;
    }
    if (pw_alert_diagnostics)
    {
        unsigned long long ticks = pw_alert_tsc() - start;
        pw_alert_stats.waits++;
        pw_alert_stats.timeouts += status == STATUS_TIMEOUT;
        pw_alert_stats.errors += status != STATUS_TIMEOUT && status != STATUS_ALERTED;
        pw_alert_stats.wait_ticks += ticks;
        if (ticks > pw_alert_stats.max_ticks) pw_alert_stats.max_ticks = ticks;
    }
    return status;
}
