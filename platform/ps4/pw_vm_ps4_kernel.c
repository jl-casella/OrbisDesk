/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "pw_vm_ps4_kernel.h"
#include <orbis/libkernel.h>

int pw_ps4_kernel_reserve(void **address, size_t bytes, int flags, size_t alignment)
{
    return sceKernelReserveVirtualRange(address, bytes, flags, alignment);
}
int pw_ps4_kernel_map(void **address, size_t bytes, int protection, int flags)
{
    return sceKernelMapFlexibleMemory(address, bytes, protection, flags);
}
int pw_ps4_kernel_protect(const void *address, size_t bytes, int protection)
{
    return sceKernelMprotect(address, bytes, protection);
}
int pw_ps4_kernel_unmap(void *address, size_t bytes)
{
    return sceKernelMunmap(address, bytes);
}
