# SPDX-License-Identifier: LGPL-2.1-or-later
"""Add a userspace pending bit to the existing, proven PS4 kernel-alert overlay.

Used by the hardware sync replacement producer, leaving the baseline object intact.
No Windows handle or cross-process synchronization API is changed.
"""
def patch(source):
    changes=[
        ('#include "pw_wine_thread_alert.inc.c"',
         '#define pw_wine_thread_alert_report pw_wine_thread_alert_kernel_report\n'
         '#include "pw_wine_thread_alert.inc.c"\n#undef pw_wine_thread_alert_report\n'
         '#include "pw_thread_alert_pending.inc.c"'),
        ('OrbisKernelEventFlag event = pw_alert_create();','OrbisKernelEventFlag event = pw_pending_alert_create();'),
        ('event != PW_ALERT_SERVER) sceKernelDeleteEventFlag( event );','event != PW_ALERT_SERVER) pw_pending_alert_delete( event );'),
        ('return pw_alert_set( entry->ps4.native );','return pw_pending_alert_set( entry->ps4.native );'),
        ('return pw_alert_wait( entry->ps4.native, timeout );','return pw_pending_alert_wait( entry->ps4.native, timeout );')]
    for old,new in changes:
        if source.count(old)!=1:raise ValueError('Pending-alert context changed: '+old)
        source=source.replace(old,new,1)
    return source
