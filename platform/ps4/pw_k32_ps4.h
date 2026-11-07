/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef PW_K32_PS4_H
#define PW_K32_PS4_H
#include "pw_pe32.h"
/* Minimal synthetic kernel32 and msvcrt for a single i386 EXE without Wine.
 * The images have no PE headers: each is a registered module whose function
 * exports are 16-byte thunk slots filled with HLT, plus an optional RW data
 * page for data exports. Guest calls stop at a slot and run a host handler
 * through pw_guest_call. Only flat relative file names, flat .dll names under
 * the module directory and in-process threads are served; any other argument
 * fails with a Win32 error and a trace line, never a fake success. Not a
 * Windows loader, scheduler, object manager or C runtime. */
enum { PW_K32_EXPORTS = 26, PW_MSVCRT_EXPORTS = 25, PW_K32_THREADS = 8, PW_K32_HANDLES = 32 };
typedef void (*PwK32Trace)(void *opaque, const char *line);
typedef struct PwK32Stats {
    unsigned calls[PW_K32_EXPORTS], crt_calls[PW_MSVCRT_EXPORTS], refused, threads, thread_failures, leaked_handles;
    unsigned exited, returned, exit_code, run_rc, link_rc;
    unsigned modules_loaded, modules_unloaded, dll_init_failures, notifications;
    unsigned heap_allocations, heap_live_blocks, heap_peak_bytes, initializers, exit_handlers, crt_output_bytes;
    uint64_t steps, bytes_written;
    PwPe32LinkReport link;
} PwK32Stats;
typedef struct PwK32Process PwK32Process;
const char *pw_k32_ps4_export_name(unsigned index);
const char *pw_k32_ps4_crt_export_name(unsigned index);
/* base is a 64 KiB aligned address for kernel32; msvcrt follows at
 * base + 0x10000 and its heap occupies [0x3c000000, 0x3c100000). directory
 * resolves relative file names and module_directory DLL names (both must
 * exist). */
int pw_k32_ps4_create(PwK32Process **, const PwVmBackend *, uint32_t base, const char *directory,
                      const char *module_directory, PwK32Trace, void *opaque);
PwPe32Image *pw_k32_ps4_image(PwK32Process *);
/* Links exe against the loaded list, attaches a main thread with a TEB (and
 * the EXE's static TLS, if any) and runs it until ExitProcess,
 * TerminateProcess, exit() or return from the entry point. Worker threads are
 * joined and loaded DLLs detached and unmapped before returning. One run per
 * process. */
int pw_k32_ps4_run(PwK32Process *, PwPe32Image *exe, const char *exe_name,
                   uint32_t stack, uint32_t teb, uint64_t max_steps);
int pw_k32_ps4_stats(PwK32Process *, PwK32Stats *);
int pw_k32_ps4_destroy(PwK32Process *);
#endif
