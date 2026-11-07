/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef PW_K32_INTERNAL_H
#define PW_K32_INTERNAL_H
#include "pw_k32_ps4.h"
#include "pw_guest_call.h"
/* Shared between the synthetic modules of pw_k32_ps4; not a public API. */
enum { PW_K32_EXITED = 1, PW_K32_DATA_BYTES = 0x4000 };
typedef struct PwK32Thread PwK32Thread;
/* A synthetic export: a thunk (stdcall or cdecl, fixed argument bytes,
 * optionally variadic) or, with data != 0, the address data - 1 bytes into
 * the module's RW data page. */
typedef struct PwK32Export { const char *name; uint16_t bytes; uint8_t cdecl, variadic; uint32_t data; } PwK32Export;
typedef struct PwK32Call {
    PwK32Process *process;
    PwK32Thread *thread;
    PwX86State *state;
    PwGuestCall *frame;
    unsigned index;
    uint32_t a[8];
    int error;            /* Win32 last error to set, or -1 to keep it */
    const char *refusal;  /* set when the arguments are outside the served subset */
    unsigned bits;        /* 0 for void, else 32 */
    unsigned exit;        /* request process exit with exit_code after this call */
    uint32_t exit_code;
    int rc;               /* nonzero ends the guest thread (PW_K32_EXITED or a fault) */
} PwK32Call;
typedef uint32_t (*PwK32Handler)(void *state, PwK32Call *);
typedef struct PwK32Module {
    const char *name;
    const PwK32Export *exports;
    unsigned count;
    PwK32Handler handler;
} PwK32Module;

void pw_k32_trace(PwK32Process *, const char *format, ...) __attribute__((format(printf, 2, 3)));
int pw_k32_guest_span(const PwX86State *, uint32_t address, uint32_t bytes, unsigned permission);
/* 0, or the Win32 error for an unreadable or unterminated string. */
int pw_k32_guest_string(const PwX86State *, uint32_t address, char *out, unsigned capacity);
/* Runs guest code at target on the calling guest thread, nested inside the
 * current call. Returns PW_OK, PW_K32_EXITED or a fault. */
int pw_k32_call_guest(PwK32Call *, uint32_t target, const uint32_t *arguments, unsigned count,
                      PwGuestConvention, uint32_t *result);
/* A process-wide guest range added to every thread's region table. */
int pw_k32_add_region(PwK32Process *, uint32_t base, uint32_t bytes, unsigned permission);
unsigned pw_k32_thread_slot(const PwK32Thread *);

/* msvcrt.dll subset over a guest heap; see pw_msvcrt_ps4.c. */
typedef struct PwMsvcrt PwMsvcrt;
extern const PwK32Module pw_msvcrt_ps4_module;
int pw_msvcrt_ps4_create(PwMsvcrt **, PwK32Process *, const PwVmBackend *, uint32_t heap, uint32_t data, uint8_t *data_host);
int pw_msvcrt_ps4_set_program(PwMsvcrt *, const char *name);
void pw_msvcrt_ps4_stats(PwMsvcrt *, PwK32Stats *);
int pw_msvcrt_ps4_destroy(PwMsvcrt *);
#endif
