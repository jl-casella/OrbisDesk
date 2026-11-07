/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef PW_VM_PS4_KERNEL_H
#define PW_VM_PS4_KERNEL_H
#include <stddef.h>
int pw_ps4_kernel_reserve(void **address, size_t bytes, int flags, size_t alignment);
int pw_ps4_kernel_map(void **address, size_t bytes, int protection, int flags);
int pw_ps4_kernel_protect(const void *address, size_t bytes, int protection);
int pw_ps4_kernel_unmap(void *address, size_t bytes);
#endif
