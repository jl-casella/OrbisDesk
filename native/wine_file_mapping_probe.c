/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <orbis/libkernel.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <unistd.h>
#define PAGE 0x4000
static int record(const char *name,int ok)
{
    printf("PWFILEMAP {\"case\":\"%s\",\"status\":\"%s\"}\n",name,ok?"passed":"blocked");fflush(stdout);return ok;
}
static int byte(void)
{
    unsigned char value=0;int fd=open("/data/image.bin",O_RDONLY);if(fd<0) return -1;
    int ok=read(fd,&value,1)==1;close(fd);return ok?value:-1;
}
static int protection(void *address)
{
    void *start=NULL,*end=NULL;int prot=-1;
    return sceKernelQueryMemoryProtection(address,&start,&end,&prot)?-1:prot;
}
static void *map(int fd,int flags,void *address)
{
    void *result=NULL;int rc=sceKernelMmap(address,PAGE,1,flags,fd,0,&result);
    return rc?NULL:result;
}
int main(void)
{
    int all=1,ro=open("/data/image.bin",O_RDONLY),rw=open("/data/image.bin",O_RDWR);
    if(ro<0 || rw<0) return 96;
    puts("PWFILEMAP requesting private and shared file protection contract");fflush(stdout);
    unsigned char *private_ro=map(ro,2,NULL),*private_rw=map(rw,2,NULL);
    int ok=private_ro && !sceKernelMprotect(private_ro,PAGE,3) && protection(private_ro)==3;
    all&=record("private-readonly-upgrade",ok);
    if(ok) private_ro[0]=0xa7;
    all&=record("private-readonly-copy",ok && private_ro[0]==0xa7 && byte()==0x52);
    ok=private_rw && !sceKernelMprotect(private_rw,PAGE,3);
    if(ok) private_rw[0]=0xc8;
    all&=record("private-readwrite-copy",ok && byte()==0x52 && private_ro && private_ro[0]==0xa7);
    unsigned char *independent=map(ro,2,NULL);
    all&=record("private-independent-view",independent && independent[0]==0x52);
    if(independent) sceKernelMunmap(independent,PAGE);
    int old=ro;close(ro);ro=-1;int reused=open("/data/image.bin",O_RDWR);
    ok=private_ro && reused==old && !sceKernelMprotect(private_ro,PAGE,1) && !sceKernelMprotect(private_ro,PAGE,3);
    if(ok) private_ro[0]=0xa7;
    all&=record("private-close-reuse",ok && byte()==0x52);
    if(reused>=0) close(reused);
    ro=open("/data/image.bin",O_RDONLY);
    unsigned char *shared_ro=map(ro,1,NULL);
    old=ro;close(ro);ro=-1;reused=open("/data/image.bin",O_RDWR);
    ok=shared_ro && reused==old && sceKernelMprotect(shared_ro,PAGE,3)==(int32_t)0x8002000d && protection(shared_ro)==1;
    all&=record("shared-readonly-denied-after-reuse",ok && shared_ro[0]==0x52);
    if(reused>=0) close(reused);
    ro=open("/data/image.bin",O_RDONLY);
    void *range=NULL;int rc=sceKernelMapFlexibleMemory(&range,2*PAGE,3,0);
    unsigned char *first=NULL,*second=NULL;
    if(!rc && range) {first=map(ro,0x12,range);second=map(ro,0x11,(unsigned char *)range+PAGE);}
    ok=first && second && !sceKernelMprotect(first,PAGE,1) &&
        sceKernelMprotect(first,2*PAGE,3)==(int32_t)0x8002000d && protection(first)==1 && protection(second)==1;
    all&=record("mixed-range-denied-atomically",ok);
    if(range) sceKernelMunmap(range,2*PAGE);
    unsigned char *shared_rw=map(rw,1,NULL);
    ok=shared_rw && !sceKernelMprotect(shared_rw,PAGE,3);
    if(ok) shared_rw[0]=0xb6;
    all&=record("shared-readwrite-persist",ok && byte()==0xb6 && shared_ro && shared_ro[0]==0xb6);
    all&=record("dirty-private-isolation",private_ro && private_rw && private_ro[0]==0xa7 && private_rw[0]==0xc8);
    old=rw;close(rw);rw=-1;reused=open("/data/image.bin",O_RDONLY);
    ok=shared_rw && reused==old && !sceKernelMprotect(shared_rw,PAGE,1) && !sceKernelMprotect(shared_rw,PAGE,3);
    all&=record("shared-readwrite-close-reuse",ok);
    if(reused>=0) close(reused);
    if(ro>=0) close(ro);
    if(private_ro) sceKernelMunmap(private_ro,PAGE);
    if(private_rw) sceKernelMunmap(private_rw,PAGE);
    if(shared_ro) sceKernelMunmap(shared_ro,PAGE);
    if(shared_rw) sceKernelMunmap(shared_rw,PAGE);
    return all?0:98;
}
