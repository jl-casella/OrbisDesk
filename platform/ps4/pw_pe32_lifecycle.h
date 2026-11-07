/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef PW_PE32_LIFECYCLE_H
#define PW_PE32_LIFECYCLE_H
#include "pw_pe32.h"
#include "pw_cpu_ps4.h"
#include <pthread.h>
enum { PW_PE32_INIT_FAILED = -100, PW_PE32_LIFE_NEW = 0, PW_PE32_LIFE_ATTACHED = 1,
       PW_PE32_LIFE_FAILED = 2, PW_PE32_LIFE_DETACHED = 3, PW_PE32_MAX_THREADS = 64 };
typedef struct PwPe32InitEvent { unsigned module, reason, tls, result; } PwPe32InitEvent;
typedef struct PwPe32Thread PwPe32Thread;
/* Runs the thread's CPU until stop; replaces the default bounded run so guest
 * notifications can reach host services. Called with the lifecycle mutex held. */
typedef int (*PwPe32Runner)(void *opaque, PwPs4Cpu *cpu, uint32_t stop);
typedef struct PwPe32Lifecycle {
    PwVmBackend backend;
    PwPe32Image *images[PW_PE32_MAX_MODULES]; /* TLS index = slot; NULL after unload */
    size_t count;                             /* highest used slot + 1 */
    pthread_mutex_t mutex;
    unsigned initialized, status, threads, events;
    PwPe32Thread *live[PW_PE32_MAX_THREADS];
    PwPe32Runner runner;
    void *runner_opaque;
    PwPe32InitEvent trace[1024];
} PwPe32Lifecycle;
struct PwPe32Thread {
    PwPe32Lifecycle *life;
    PwPs4Cpu *cpu;
    PwVmRegion region;
    uint32_t blocks[PW_PE32_MAX_MODULES], old_fs, old_fs_bytes;
    unsigned main_thread, attached;
};
/* Caller supplies dependency order; only flat, linked DLLs are admitted, plus
 * optionally a linked EXE in slot 0 that receives TLS callbacks but never
 * entry-point notifications.
 * Notifications are serialized. This is not a Windows loader-lock API.
 * Each thread region holds a TLS block for every possible slot, so a module
 * loaded later gets a block in every live thread. A PwPe32Thread must keep
 * its address from create to destroy. */
int pw_pe32_lifecycle_create(PwPe32Lifecycle *, const PwVmBackend *, PwPe32Image *const *, size_t);
int pw_pe32_lifecycle_set_runner(PwPe32Lifecycle *, PwPe32Runner, void *opaque);
int pw_pe32_thread_create(PwPe32Lifecycle *, PwPs4Cpu *, uint32_t address, int main_thread, PwPe32Thread *);
int pw_pe32_process_attach(PwPe32Thread *);
int pw_pe32_thread_attach(PwPe32Thread *);
int pw_pe32_thread_detach(PwPe32Thread *);
int pw_pe32_process_detach(PwPe32Thread *);
/* Runtime load: a linked DLL gets a free TLS slot and a fresh block in every
 * live thread, then PROCESS_ATTACH on the caller. Rejected attach runs
 * PROCESS_DETACH and removes it (PW_PE32_INIT_FAILED). Unload runs
 * PROCESS_DETACH on the caller and removes the slot. Neither unmaps. */
int pw_pe32_lifecycle_load(PwPe32Lifecycle *, PwPe32Image *, PwPe32Thread *caller);
int pw_pe32_lifecycle_unload(PwPe32Lifecycle *, PwPe32Image *, PwPe32Thread *caller);
int pw_pe32_thread_destroy(PwPe32Thread *);
int pw_pe32_lifecycle_destroy(PwPe32Lifecycle *);
#endif
