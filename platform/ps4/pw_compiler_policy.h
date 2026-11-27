/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef PW_COMPILER_POLICY_H
#define PW_COMPILER_POLICY_H
#include <stddef.h>
#include <string.h>
#define PW_COMPILER_ENV_BYTES 32768
/* Migration only: never generate per-game compiler settings. DXVK can retain
 * its configuration in a shared instance after forced guest termination. */
#define PW_COMPILER_MARK ";[__orbisdesk_compiler_policy_v1__]"
#define PW_COMPILER_WMARK L";[__orbisdesk_compiler_policy_v1__]"
static inline int pw_compiler_clean(const char *base,char *out,size_t capacity)
{
    const char *mark=base?strstr(base,PW_COMPILER_MARK):NULL;
    size_t n=base?(mark?(size_t)(mark-base):strlen(base)):0;
    if(n>=capacity)return 0;
    if(n)memcpy(out,base,n);
    out[n]=0;return 1;
}
#endif
