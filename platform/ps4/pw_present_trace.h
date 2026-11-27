/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef PW_PRESENT_TRACE_H
#define PW_PRESENT_TRACE_H
#include <stdint.h>
enum {PW_PRESENT_LOCK,PW_PRESENT_METADATA,PW_PRESENT_PREPARE,PW_PRESENT_LIMIT,PW_PRESENT_TAIL,PW_PRESENT_STAGES};
void pw_present_trace_begin(const void *chain,uint64_t now,int enabled);
void pw_present_trace_mark(unsigned stage);
void pw_present_trace_end(uint64_t blit_wait_ns);
#endif
