/* OrbisDesk H0 (G001). DolphinPS4's port/ps4_runtime.cpp refers to the kernel's JIT shared
 * memory functions for Dolphin's own JIT; the probe never calls them (ps4_exec_probe is not
 * run). The OpenOrbis SDK's libkernel stub does not export them, so they are defined here as
 * failures with a trace. */
#include <stdio.h>
#include <stddef.h>

#define ORBIS_KERNEL_ERROR_ENOSYS 0x8002004e

int sceKernelJitCreateSharedMemory( const char *name, size_t len, int prot, int *fd )
{
    fprintf( stderr, "G001 sceKernelJitCreateSharedMemory unavailable (len=%zu)\n", len );
    return (int)ORBIS_KERNEL_ERROR_ENOSYS;
}

int sceKernelJitCreateAliasOfSharedMemory( int fd, int prot, int *alias )
{
    fprintf( stderr, "G001 sceKernelJitCreateAliasOfSharedMemory unavailable (fd=%d)\n", fd );
    return (int)ORBIS_KERNEL_ERROR_ENOSYS;
}
