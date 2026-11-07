/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef PW_PROCESS_PS4_H
#define PW_PROCESS_PS4_H
#include "pw_pe32.h"
/* Bounded initial process data. ASCII input is widened to UTF-16; unsupported
 * text is rejected. No heap, handles, loader lock or syscall service is implied.
 * Initialize to zero, keep its address stable, and serialize all operations. */
typedef struct PwPs4Process {
    PwVmBackend backend;
    PwVmRegion region;
    uint32_t peb, parameters, ldr;
    unsigned bindings;
} PwPs4Process;
int pw_process_ps4_create(PwPs4Process *, const PwVmBackend *, uint32_t,
                         const PwPe32Module *, size_t, const char *, const char *, const char *);
/* Attach only after a private TEB has been created. Restore with unbind before
 * destroying that TEB or this process. Caller serializes process lifetime. */
int pw_process_ps4_bind(PwPs4Process *, PwX86State *, uint32_t *previous);
int pw_process_ps4_unbind(PwPs4Process *, PwX86State *, uint32_t previous);
int pw_process_ps4_destroy(PwPs4Process *);
#endif
