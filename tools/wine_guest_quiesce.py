# SPDX-License-Identifier: LGPL-2.1-or-later
"""Context-checked native exit acknowledgement; no standard ThreadTimes change."""
def patch_thread(text):
    if 'pw_wine_thread_quiescent' in text:raise ValueError('Native quiescence already patched')
    edits=[('    pthread_exit( UIntToPtr(status) );','''#ifdef __ORBIS__
    extern void pw_wine_thread_quiescent(void);
    pw_wine_thread_quiescent(); /* OrbisDesk 04.52: no guest code after this point */
#endif
    pthread_exit( UIntToPtr(status) );'''),
    ('''            if (data) memcpy( data, &kusrt, min( length, sizeof(kusrt) ));
            if (ret_len) *ret_len = min( length, sizeof(kusrt) );''','''#ifdef __ORBIS__
            /* Private, explicitly tagged 48-byte request; ordinary callers
             * retain Wine's original output and length. WoW64 passes it intact. */
            if (data && length == sizeof(struct pw_thread_quiet)) {
                struct pw_thread_quiet *q=data;
                if(q->magic==PW_THREAD_QUIET_MAGIC) {
                    extern unsigned pw_wine_thread_query(int,long,uint64_t *);
                    memcpy(q->times,&kusrt,sizeof(kusrt));
                    q->active=pw_wine_thread_query(unix_pid,unix_tid,&q->token);
                    if(ret_len)*ret_len=sizeof(*q);
                    return STATUS_SUCCESS;
                }
            }
#endif
            if (data) memcpy( data, &kusrt, min( length, sizeof(kusrt) ));
            if (ret_len) *ret_len = min( length, sizeof(kusrt) );''')]
    for old,new in edits:
        if text.count(old)!=1:raise ValueError('Unexpected native quiescence context: '+old[:80])
        text=text.replace(old,new)
    if text.count('#include "config.h"')!=1:raise ValueError('Missing Wine configuration header')
    return text.replace('#include "config.h"','#include "config.h"\n#include "pw_thread_quiesce.h"')
