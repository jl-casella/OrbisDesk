/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* OrbisDesk's one switch for diagnostic traces (docs/RELEASE_TRACES.md).
 *
 * The hardware launcher (native/wine_hardware.c) decides, once, before Wine starts:
 *   build:  ORBIS_RELEASE=1 (its default) starts with traces off; -DORBIS_RELEASE=0 with them on;
 *   run:    /data/orbisdesk/trace.txt overrides the build without recompiling. Present and empty, or
 *           "1", turns traces on; "0" turns them off.
 * It sets pw_trace_level for the native side and passes PW_TRACE=0|1 to Wine, so Windows and Unix
 * code in Wine use the same answer (getenv / GetEnvironmentVariable "PW_TRACE").
 *
 * Anything else that links these objects (fork and host diagnostics, wine_boot.c alone) never calls
 * the launcher: pw_trace_level stays 1 and an unset PW_TRACE counts as on, as before the switch.
 *
 * Never behind this switch: build and run markers (HW_BUILD lines, PWBOOT milestones), real errors,
 * crashes, exits. Traces off must never turn a failure into a silent success. */
#ifndef PW_TRACE_H
#define PW_TRACE_H

#ifndef ORBIS_RELEASE
#define ORBIS_RELEASE 1
#endif

#define PW_TRACE_FILE "/data/orbisdesk/trace.txt"

/* 0 off, >=1 traces; defined in platform/ps4/pw_wine_platform.c. Weak: a program linked without it (the host
 * check tools/check-wine-fs.py, tools/build-hardware-boot.py) keeps every trace, as before the switch. */
extern int pw_trace_level __attribute__((weak));
static inline int pw_trace_on(void) {return &pw_trace_level?pw_trace_level>0:1;}

#ifdef PW_TRACE_DEFINE_LEVEL
/* A standalone title that never links pw_wine_platform.c (the S4 Steam title, tools/build-steam-s4.py): the
 * console's loader refuses an import no eboot provides, weak or not, so the one source given this macro
 * defines the level itself. Traces stay on there, as before the switch. */
int pw_trace_level = 1;
#endif

#endif
