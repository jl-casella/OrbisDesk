/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef PW_WINE_PLATFORM_H
#define PW_WINE_PLATFORM_H
#include <stddef.h>
/* Raw mappings belong to Wine, not the managed PE/JIT allocation registry.
 * Same kernel primitives as pw_vm_ps4; 16 KiB granularity. Never replace an
 * occupied range. Unsupported mapping flags are rejected (Wine's fallback
 * MAP_NORESERVE is zero with the OpenOrbis headers). */
void *pw_wine_anon_tryfixed(void *, size_t, int, int);
int pw_wine_memory_protect(void *, size_t, int);
int pw_wine_memory_release(void *, size_t);
/* Before Wine startup/threads. Validate explicit existing roots and install
 * HOME/USER/WINEPREFIX. Does not create or initialize a Wine prefix. */
int pw_wine_init_paths(const char *, const char *, const char *);
struct stat;
int pw_wine_stat(const char *,struct stat *);
int pw_wine_fstat(int,struct stat *);
int pw_wine_lstat(const char *,struct stat *);
long pw_wine_sysconf(int);
#endif
