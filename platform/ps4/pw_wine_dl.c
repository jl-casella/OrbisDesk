/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* W158: dlopen, dlsym, dlerror and dlclose for the static boot ELF.
 *
 * The SDK's libc is musl, whose static build has stubs that always fail (there is no dynamic
 * loading here) and record the error per thread: __dl_vseterr reads musl's thread structure at
 * %fs:0, frees the pointer at offset 0xa8, stores a new malloc'd message there and sets a flag at
 * offset 0x46; dlerror reads and clears them. On the PS4 %fs:0 is the system's thread block, not
 * musl's, so every failed lookup freed whatever word was at that offset and wrote into the block.
 * Wine does one for each builtin DLL with a Unix side outside the static table
 * (pw_wine_unixlibs.c), e.g. dnsapi. In W155 glxgears faulted there (a jump into read-only data,
 * registers holding 0xafafafaf) after DOS programs had run, and the app closed silently once
 * after glxgears.
 *
 * These fail the same way and keep no per-thread state: dlerror always returns the reason. */
#include <stddef.h>

static const char reason[] = "Dynamic loading not supported";

void *dlopen(const char *file, int mode)
{
    (void)file; (void)mode;
    return NULL;
}

void *dlsym(void *handle, const char *name)
{
    (void)handle; (void)name;
    return NULL;
}

char *dlerror(void)
{
    return (char *)reason;
}

int dlclose(void *handle)
{
    (void)handle;
    return 0;
}
