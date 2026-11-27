/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef PW_THREAD_QUIESCE_H
#define PW_THREAD_QUIESCE_H
#include <stdint.h>
/* Private opt-in extension of ThreadTimes, forwarded unchanged by WoW64.
 * Ordinary callers still receive exactly KERNEL_USER_TIMES. Older native code
 * returns 32 bytes, which a new guest treats as unsupported, never as quiet. */
#define PW_THREAD_QUIET_MAGIC 0x50575152u
struct pw_thread_quiet {int64_t times[4];uint32_t magic,active;uint64_t token;};
#endif
