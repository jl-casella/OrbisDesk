/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* W093: pthread_once for Wine's Unix libraries in the title. The kernel's pthread_once, the one
 * this ELF links, treats pthread_once_t as a 16-byte structure while the SDK headers declare a
 * 4-byte int, so it writes past the variable (DolphinPS4 port/ps4_runtime.cpp, and
 * native/wine_vk_runtime.c for Mesa). Libraries built by tools/build-unixlibs-ps4.py call this
 * one, which uses only the 4 bytes: 0 = not run (PTHREAD_ONCE_INIT), 1 = running, 2 = done. */
#include <pthread.h>
#include <sched.h>

int pw_wine_pthread_once(pthread_once_t *once,void (*init)(void));

int pw_wine_pthread_once(pthread_once_t *once,void (*init)(void))
{
    int *state=(int *)once,expected=0;

    if(__atomic_load_n(state,__ATOMIC_ACQUIRE)==2) return 0;
    if(__atomic_compare_exchange_n(state,&expected,1,0,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE)) {
        init();
        __atomic_store_n(state,2,__ATOMIC_RELEASE);
        return 0;
    }
    while(__atomic_load_n(state,__ATOMIC_ACQUIRE)!=2) sched_yield();
    return 0;
}
