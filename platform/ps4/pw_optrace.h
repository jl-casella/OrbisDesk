/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef PW_OPTRACE_H
#define PW_OPTRACE_H
#include <stdint.h>
enum {PW_OP_READ,PW_OP_WAIT_ONE,PW_OP_WAIT_MANY,PW_OP_DELAY,PW_OP_YIELD,PW_OP_QPC,
      PW_OP_WAIT_ALERT,PW_OP_ALERT,PW_OP_SET_EVENT,PW_OP_RESET_EVENT,PW_OP_PEEK,PW_OP_MSG_WAIT,PW_OP_COUNT};
struct pw_opstamp {uint64_t tsc;unsigned active;};
void pw_optrace_configure(uint64_t hz,int enabled);
struct pw_opstamp pw_optrace_begin(void);
void pw_optrace_end(struct pw_opstamp stamp,unsigned op,int32_t status,uint64_t requested);
void pw_optrace_report(unsigned wine_tid);
enum {PW_READ_LOOKUP,PW_READ_BUFFER,PW_READ_IO,PW_READ_COMPLETION,PW_READ_STAGES};
struct pw_readstamp {
    uint64_t last,ticks[PW_READ_STAGES],actual;
    unsigned active,stage,kind,async_read,event,apc,completion,known;
};
struct pw_readstamp pw_readtrace_begin(void);
void pw_readtrace_stage(struct pw_readstamp *stamp,unsigned stage);
int32_t pw_readtrace_end(struct pw_readstamp *stamp,int32_t status,uint64_t requested);
#endif
