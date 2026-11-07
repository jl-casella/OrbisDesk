/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Compile the patched real Wine translation unit. Dead section elimination
 * excludes unrelated Wine startup code, without providing fake services. */
#include "virtual.c"
void *pw_wine_test_tryfixed(void *address,size_t bytes,int prot,int flags)
{
    return anon_mmap_tryfixed(address,bytes,prot,flags);
}
