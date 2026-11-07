/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef PW_VM_PS4_H
#define PW_VM_PS4_H
#include "prospero_win_vm.h"
typedef struct PwPs4VmStats {
    size_t reservations, reserved_bytes, committed_bytes;
} PwPs4VmStats;
int pw_vm_ps4_backend(PwVmBackend *out);
int pw_vm_ps4_stats(PwPs4VmStats *out);
#endif
