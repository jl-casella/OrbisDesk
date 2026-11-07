/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "pw_pthread_ps4.h"
#include <orbis/libkernel.h>

int pw_ps4_pthread_key_delete(pthread_key_t key)
{
    int rc = scePthreadKeyDelete((OrbisPthreadKey)key);
    return rc < 0 ? (int)((unsigned)rc & 0xffffu) : rc;
}
