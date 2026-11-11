/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef PROCESS_LOADER_PROTOCOL_H
#define PROCESS_LOADER_PROTOCOL_H
#include <stdint.h>
#include <stddef.h>
#define P005_MAGIC UINT64_C(0x50303035434f4558)
#define P005_PAGE 16384
#ifndef P005_REQUEST_PATH
#define P005_REQUEST_PATH "/data/orbisdesk/process-p005/request.bin"
#endif
struct p005_request { uint64_t magic,token[2];uint32_t observer_pid,reserved;char directory[160]; };
struct p005_state {
    uint64_t magic,token[2];
    uint32_t observer_pid,observer_tick,helper_pid,helper_ppid,helper_tick;
    uint32_t observer_seen_child,helper_done,helper_parent_progress,helper_low_ok,helper_low_value;
};
_Static_assert(sizeof(struct p005_request)==192,"request ABI");
_Static_assert(sizeof(struct p005_state)==64,"state ABI");
/* FreeBSD/Orbis userland syscall ABI. Never used for process creation or kexec. */
static inline long p005_sys(long n,long a,long b,long c,long d,long e,long f)
{
#ifdef P005_HOST_REFERENCE
    switch(n){case 1:n=60;break;case 3:n=0;break;case 4:n=1;break;case 5:n=2;break;
    case 6:n=3;break;case 20:n=39;break;case 39:n=110;break;case 73:n=11;break;
    case 95:n=74;break;case 240:n=35;break;case 477:n=9;if(d&0x1000)d=(d&~0x1000)|0x20;break;default:return -38;}
#endif
    register long r10 __asm__("r10")=d,r8 __asm__("r8")=e,r9 __asm__("r9")=f;
    long value;unsigned char failed;
    __asm__ volatile("syscall\n\tsetc %1":"=a"(value),"=qm"(failed),"+r"(r10),"+r"(r8),"+r"(r9)
        :"a"(n),"D"(a),"S"(b),"d"(c):"rcx","r11","memory","cc");
#ifdef P005_HOST_REFERENCE
    return value;
#else
    return failed?-value:value;
#endif
}
static inline void p005_delay(void){int64_t t[2]={0,20000000};p005_sys(240,(long)t,0,0,0,0,0);}
#endif
