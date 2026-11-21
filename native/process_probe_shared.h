/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef PROCESS_PROBE_SHARED_H
#define PROCESS_PROBE_SHARED_H
#include <stdint.h>
enum {P002_MAGIC=0x50303032,P002_PAGE=0x4000};
struct p002_shared {
    uint32_t magic,parent_pid,parent_low_ok,parent_value;
    uint32_t heartbeat,child_pid,child_seen,child_low_ok,child_value;
};
#endif
