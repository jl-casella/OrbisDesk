/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* P007: prove BinLoader entry with file I/O only; no mmap, kernel access or child. */
#include "process_loader_protocol.h"
static inline long indirect(long number,long a,long b,long c)
{
    register long r10 __asm__("r10")=c;long value;unsigned char failed;
    __asm__ volatile("syscall\n\tsetc %1":"=a"(value),"=qm"(failed),"+r"(r10)
        :"a"(0L),"D"(number),"S"(a),"d"(b):"rcx","r8","r9","r11","memory","cc");
    return failed?-value:value;
}
__attribute__((force_align_arg_pointer)) int _start(void)
{
    const char *path="/data/orbisdesk/process-binloader-p007.txt";
    long direct=p005_sys(5,(long)path,0x209,0666,0,0,0);
    long other=indirect(5,(long)path,0x209,0666);
    const char marker[]="P007 BIN ENTRY REACHED\n";
    if(direct>=0){p005_sys(4,direct,(long)marker,sizeof(marker)-1,0,0,0);p005_sys(95,direct,0,0,0,0,0);p005_sys(6,direct,0,0,0,0,0);}
    if(other>=0){indirect(4,other,(long)marker,sizeof(marker)-1);indirect(95,other,0,0);indirect(6,other,0,0);}
    return 0;
}
