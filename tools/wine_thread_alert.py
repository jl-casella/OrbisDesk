#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Context-checked process-local PS4 thread-alert overlay; safe to import."""


def patch_thread_alerts(source):
    def replace(old, new):
        nonlocal source
        if source.count(old) != 1:
            raise ValueError('Unexpected thread-alert patch context: ' + old[:90])
        source = source.replace(old, new)

    replace('union tid_alert_entry\n{\n#ifdef USE_FUTEX',
            '#ifdef __ORBIS__\n#include "pw_wine_thread_alert.inc.c"\n#endif\n\n'
            'union tid_alert_entry\n{\n#ifdef __ORBIS__\n'
            '    struct { OrbisKernelEventFlag native; HANDLE event; } ps4;\n'
            '#elif defined(USE_FUTEX)')
    replace('    entry = &tid_alert_blocks[block_idx][idx % TID_ALERT_BLOCK_SIZE];\n\n#ifdef USE_FUTEX',
            '''    entry = &tid_alert_blocks[block_idx][idx % TID_ALERT_BLOCK_SIZE];

#ifdef __ORBIS__
    if (!entry->ps4.native)
    {
        OrbisKernelEventFlag event = pw_alert_create();
        if (InterlockedCompareExchangePointer( (void **)&entry->ps4.native, event, NULL ) &&
            event != PW_ALERT_SERVER) sceKernelDeleteEventFlag( event );
    }
    if (entry->ps4.native == PW_ALERT_SERVER && !entry->ps4.event)
    {
        HANDLE event;
        if (NtCreateEvent( &event, EVENT_ALL_ACCESS, NULL, SynchronizationEvent, FALSE )) return NULL;
        if (InterlockedCompareExchangePointer( &entry->ps4.event, event, NULL )) NtClose( event );
    }
#elif defined(USE_FUTEX)''')
    # Only these two functions change. Other Windows synchronization primitives
    # retain the server path, including all cross-process handles.
    for name, code in (
        ('NtAlertThreadByThreadId( HANDLE tid )', '''    if (entry->ps4.native != PW_ALERT_SERVER) return pw_alert_set( entry->ps4.native );
    if (pw_alert_diagnostics) pw_alert_stats.fallback_sets++;
    return NtSetEvent( entry->ps4.event, NULL );'''),
        ('NtWaitForAlertByThreadId( const void *address, const LARGE_INTEGER *timeout )', '''    if (entry->ps4.native != PW_ALERT_SERVER) return pw_alert_wait( entry->ps4.native, timeout );
    if (pw_alert_diagnostics) pw_alert_stats.fallback_waits++;
    {
        NTSTATUS status = NtWaitForSingleObject( entry->ps4.event, FALSE, timeout );
        return !status ? STATUS_ALERTED : status;
    }'''),
    ):
        start = source.index('NTSTATUS WINAPI ' + name)
        pos = source.index('#ifdef USE_FUTEX', start)
        source = source[:pos] + '#ifdef __ORBIS__\n' + code + '\n#elif defined(USE_FUTEX)' + source[pos + len('#ifdef USE_FUTEX'):]
    # The table has ARRAY_SIZE entries; equality was out of bounds in the base.
    replace('return block_idx <= ARRAY_SIZE(tid_alert_blocks);',
            'return block_idx < ARRAY_SIZE(tid_alert_blocks);')
    replace('if (block_idx > ARRAY_SIZE(tid_alert_blocks))',
            'if (block_idx >= ARRAY_SIZE(tid_alert_blocks))')
    return source
