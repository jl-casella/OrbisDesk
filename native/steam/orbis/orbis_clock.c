/* SPDX-License-Identifier: GPL-3.0-or-later */
/* clock_gettime and clock_getres with Linux's clock numbers, as every caller in the Steam client
 * title passes them (the OpenOrbis SDK's <time.h>, compiled into libc++.a and curl too), turned
 * into the PS4 kernel's FreeBSD numbers. Without it CLOCK_MONOTONIC (1) is FreeBSD's
 * CLOCK_VIRTUAL, the process's user CPU time: std::chrono::steady_clock and curl's timers would
 * barely move while a thread waits on the network, and no deadline or heartbeat would come.
 * docs HARDWARE_W003_W011 (W047/W048) found the same for Wine's clocks.
 * Linked with ld --wrap=clock_gettime --wrap=clock_getres (tools/build-steam-s2.py). */
#include <time.h>

#ifndef STEAM_UI_HOSTED
int __real_clock_gettime(clockid_t id, struct timespec *ts);
int __real_clock_getres(clockid_t id, struct timespec *ts);
#endif

/* FreeBSD's <sys/time.h> */
enum {FREEBSD_REALTIME=0,FREEBSD_MONOTONIC=4,FREEBSD_UPTIME=5,FREEBSD_THREAD_CPUTIME=14,FREEBSD_PROCESS_CPUTIME=15};

static clockid_t kernel_clock(clockid_t id)
{
    switch(id) {
    case 0: return FREEBSD_REALTIME;            /* CLOCK_REALTIME */
    case 1: return FREEBSD_MONOTONIC;           /* CLOCK_MONOTONIC */
    case 2: return FREEBSD_PROCESS_CPUTIME;     /* CLOCK_PROCESS_CPUTIME_ID */
    case 3: return FREEBSD_THREAD_CPUTIME;      /* CLOCK_THREAD_CPUTIME_ID */
    case 4: return FREEBSD_MONOTONIC;           /* CLOCK_MONOTONIC_RAW */
    case 5: return FREEBSD_REALTIME;            /* CLOCK_REALTIME_COARSE */
    case 6: return FREEBSD_MONOTONIC;           /* CLOCK_MONOTONIC_COARSE */
    case 7: return FREEBSD_UPTIME;              /* CLOCK_BOOTTIME */
    default: return id;                         /* no Linux name: passed as it came */
    }
}

#ifdef STEAM_UI_HOSTED
/* Inside OrbisDesk's title a global --wrap would also turn Wine's and Mesa's calls, which already
 * pass FreeBSD's numbers (W048). There the Steam objects' calls are renamed to these instead
 * (objcopy --redefine-sym in tools/build-steam-hosted.py), and they call the real functions. */
int pw_steam_clock_gettime(clockid_t id, struct timespec *ts) {return clock_gettime(kernel_clock(id),ts);}
int pw_steam_clock_getres(clockid_t id, struct timespec *ts) {return clock_getres(kernel_clock(id),ts);}
#else
int __wrap_clock_gettime(clockid_t id, struct timespec *ts) {return __real_clock_gettime(kernel_clock(id),ts);}
int __wrap_clock_getres(clockid_t id, struct timespec *ts) {return __real_clock_getres(kernel_clock(id),ts);}
#endif
