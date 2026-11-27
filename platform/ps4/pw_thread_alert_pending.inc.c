/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* A process-local binary pending bit; kernel flags park blocked waiters only.
 * seq_cst store/load ordering closes the signal versus waiter-registration race.
 * Kernel bits can be stale; they never themselves count as an NT alert. */
struct pw_pending_alert {OrbisKernelEventFlag kernel;unsigned pending,waiters,broken;};
static __thread struct {unsigned long long sets,waits,fast_waits,armed_ready,skipped_sets,stale_wakes;} pw_pending_stats;
static struct pw_pending_alert *pw_pending_state(OrbisKernelEventFlag opaque)
{
    return (struct pw_pending_alert *)(void *)opaque;
}
static OrbisKernelEventFlag pw_pending_alert_create(void)
{
    OrbisKernelEventFlag kernel=pw_alert_create();struct pw_pending_alert *state;
    if(kernel==PW_ALERT_SERVER) return kernel;
    state=calloc(1,sizeof(*state));
    if(!state) {sceKernelDeleteEventFlag(kernel);return PW_ALERT_SERVER;}
    state->kernel=kernel;return (OrbisKernelEventFlag)(void *)state;
}
static void pw_pending_alert_delete(OrbisKernelEventFlag opaque)
{
    struct pw_pending_alert *state=pw_pending_state(opaque);
    sceKernelDeleteEventFlag(state->kernel);free(state);
}
static NTSTATUS pw_pending_alert_set(OrbisKernelEventFlag opaque)
{
    struct pw_pending_alert *state=pw_pending_state(opaque);NTSTATUS status=STATUS_SUCCESS;
    if(pw_alert_diagnostics) pw_pending_stats.sets++;
    if(__atomic_load_n(&state->broken,__ATOMIC_SEQ_CST)) return STATUS_INVALID_HANDLE;
    __atomic_store_n(&state->pending,1,__ATOMIC_SEQ_CST);
    if(__atomic_load_n(&state->waiters,__ATOMIC_SEQ_CST)) {
        status=pw_alert_set(state->kernel);
        if(status) __atomic_store_n(&state->broken,1,__ATOMIC_SEQ_CST);
    } else if(pw_alert_diagnostics) pw_pending_stats.skipped_sets++;
    return status;
}
static NTSTATUS pw_pending_alert_wait(OrbisKernelEventFlag opaque,const LARGE_INTEGER *timeout)
{
    struct pw_pending_alert *state=pw_pending_state(opaque);
    BOOL finite=timeout && timeout->QuadPart!=TIMEOUT_INFINITE;
    ULONGLONG end=0;NTSTATUS status;LARGE_INTEGER adjusted,now;
    if(pw_alert_diagnostics) pw_pending_stats.waits++;
    if(__atomic_load_n(&state->broken,__ATOMIC_SEQ_CST)) return STATUS_INVALID_HANDLE;
    if(__atomic_exchange_n(&state->pending,0,__ATOMIC_SEQ_CST)) {
        if(pw_alert_diagnostics) pw_pending_stats.fast_waits++;
        return STATUS_ALERTED;
    }
    __atomic_fetch_add(&state->waiters,1,__ATOMIC_SEQ_CST);
    if(finite) {
        if(timeout->QuadPart<0) {
            NtQuerySystemTime(&now);
            end=(ULONGLONG)now.QuadPart+(ULONGLONG)(-(timeout->QuadPart+1))+1;
        } else end=timeout->QuadPart;
    }
    for(;;) {
        if(__atomic_load_n(&state->broken,__ATOMIC_SEQ_CST)) {status=STATUS_INVALID_HANDLE;break;}
        if(__atomic_exchange_n(&state->pending,0,__ATOMIC_SEQ_CST)) {
            if(pw_alert_diagnostics) pw_pending_stats.armed_ready++;
            status=STATUS_ALERTED;break;
        }
        if(finite) {
            /* Preserve one deadline across stale wakes, including INT64_MIN.
             * INT64_MAX is Wine's infinite sentinel, not a usable absolute end. */
            if(end<(ULONGLONG)TIMEOUT_INFINITE) adjusted.QuadPart=end;
            else {
                ULONGLONG left;NtQuerySystemTime(&now);
                left=end>(ULONGLONG)now.QuadPart?end-(ULONGLONG)now.QuadPart:0;
                adjusted.QuadPart=left>(ULONGLONG)TIMEOUT_INFINITE?(-TIMEOUT_INFINITE-1):-(LONGLONG)left;
            }
        }
        status=pw_alert_wait(state->kernel,finite?&adjusted:NULL);
        if(status==STATUS_ALERTED) {
            if(__atomic_exchange_n(&state->pending,0,__ATOMIC_SEQ_CST)) break;
            if(pw_alert_diagnostics) pw_pending_stats.stale_wakes++;
            continue;
        }
        if(status==STATUS_TIMEOUT && __atomic_exchange_n(&state->pending,0,__ATOMIC_SEQ_CST)) status=STATUS_ALERTED;
        if(status!=STATUS_TIMEOUT && status!=STATUS_ALERTED) __atomic_store_n(&state->broken,1,__ATOMIC_SEQ_CST);
        break;
    }
    __atomic_fetch_sub(&state->waiters,1,__ATOMIC_SEQ_CST);return status;
}
void pw_wine_thread_alert_report(unsigned tid)
{
    pw_wine_thread_alert_kernel_report(tid);
    if(pw_alert_diagnostics)
        fprintf(stderr,"PWPENDINGALERT tid=%04x version=1 sets=%llu waits=%llu fast_waits=%llu armed_ready=%llu skipped_sets=%llu stale_wakes=%llu\n",
            tid,pw_pending_stats.sets,pw_pending_stats.waits,pw_pending_stats.fast_waits,pw_pending_stats.armed_ready,
            pw_pending_stats.skipped_sets,pw_pending_stats.stale_wakes);
}
