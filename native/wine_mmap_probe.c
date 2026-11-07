/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <orbis/libkernel.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <unistd.h>
static int record(const char *name,int ok)
{
    printf("PWMMAP {\"case\":\"%s\",\"status\":\"%s\"}\n",name,ok?"passed":"blocked");fflush(stdout);return ok;
}
static int invalid(int fd,int64_t offset,void *address,int flags,const char *name)
{
    void *output=(void *)(uintptr_t)0x12345678;
    int32_t rc=sceKernelMmap(address,0x4000,1,flags,fd,offset,&output);
    return record(name,rc==(int32_t)0x80020016 && output==(void *)(uintptr_t)0x12345678);
}
int main(void)
{
    int fd=open("/data/image.bin",O_RDONLY);if(fd<0) return 96;
    puts("PWMMAP requesting file offset contract");fflush(stdout);
    int all=invalid(fd,0xc00,NULL,2,"offset-0xc00");
    all&=invalid(fd,-0x4000,NULL,2,"negative-offset");
    all&=invalid(fd,0x1000,NULL,2,"offset-4k");
    void *mapped=NULL;int32_t rc=sceKernelMmap(NULL,0x4000,1,2,fd,0x4000,&mapped);
    all&=record("aligned-offset",!rc && mapped && ((const unsigned char *)mapped)[0]==0x52);
    if(!rc) sceKernelMunmap(mapped,0x4000);
    void *memory=NULL;rc=sceKernelMapFlexibleMemory(&memory,0x4000,3,0);
    int ok=!rc && memory;
    if(ok) {
        ((unsigned char *)memory)[0]=0xa7;
        ok=invalid(fd,0xc00,memory,0x12,"fixed-offset-rejected") && ((unsigned char *)memory)[0]==0xa7;
        sceKernelMunmap(memory,0x4000);
    }
    all&=record("failed-fixed-preserves-memory",ok);
    close(fd);return all?0:97;
}
