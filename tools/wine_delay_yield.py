# SPDX-License-Identifier: LGPL-2.1-or-later
"""Keep zero-delay yield status; avoid unused rusage queries for timed sleeps."""
OLD='''        status = NtYieldExecution();
        if (!when) return status;'''
NEW='''        if (!when) return NtYieldExecution();
#ifdef HAVE_SCHED_YIELD
        /* OrbisDesk: nonzero sleeps ignore NtYieldExecution's status. Keep
         * its sched_yield, without the two unused per-thread rusage queries. */
        sched_yield();
#endif'''
def patch(text):
    if text.count(OLD)!=1:raise ValueError('NtDelayExecution yield context changed')
    return text.replace(OLD,NEW)
