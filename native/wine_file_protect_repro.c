/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <orbis/libkernel.h>
#include <fcntl.h>
#include <stdio.h>
#include <unistd.h>
int main(void)
{
    int fd=open("/data/image.bin",O_RDONLY);if(fd<0) return 96;
    void *mapped=NULL;int rc=sceKernelMmap(NULL,0x4000,1,2,fd,0,&mapped);
    printf("PWPROTECT map rc=%08x address=%p\n",(unsigned)rc,mapped);fflush(stdout);
    if(rc || !mapped) {close(fd);return 98;}
    puts("PWPROTECT requesting read-write protection on a private read-only-file mapping");fflush(stdout);
    rc=sceKernelMprotect(mapped,0x4000,3);
    printf("PWPROTECT returned rc=%08x\n",(unsigned)rc);fflush(stdout);
    int ok=!rc;
    if(ok) {
        ((unsigned char *)mapped)[0]=0xa7;
        unsigned char original=0;
        ok=read(fd,&original,1)==1 && original==0x52;
    }
    printf("PWPROTECT private-write=%d\n",ok);fflush(stdout);
    sceKernelMunmap(mapped,0x4000);close(fd);return ok?0:98;
}
