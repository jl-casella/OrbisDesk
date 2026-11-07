/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "pw_wine_platform.h"
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <unistd.h>
void *pw_wine_test_tryfixed(void *,size_t,int,int);
int pw_wine_test_paths(void);
uint32_t cdrom_DeviceIoControl(void *,void *,void *,void *,void *,unsigned,void *,unsigned,void *,unsigned);
uint32_t get_device_info(int,void *);

int probe_wine_platform(int kind,char *detail,size_t capacity)
{
    int rc=0;unsigned checks=0;uint32_t result=0;
    if(kind==0) {
        void *address=(void *)(uintptr_t)0x28000000;
        void *p=pw_wine_test_tryfixed(address,0x4000,3,0);
        if(p==MAP_FAILED) rc=1;
        if(!rc) {
            *(uint32_t *)p=0x12345678;
            errno=0;void *collision=pw_wine_test_tryfixed(address,0x4000,3,0);
            if(collision!=MAP_FAILED || errno!=EEXIST || *(uint32_t *)p!=0x12345678) rc=1;
            else checks++;
            const unsigned char code[]={0xb8,42,0,0,0,0xc3};
            memcpy(p,code,sizeof(code));
            if(pw_wine_memory_protect(p,0x4000,5)) rc=1;
            if(!rc) {result=((unsigned (*)(void))p)();if(result!=42) rc=1;else checks++;}
            if(pw_wine_memory_protect(p,0x4000,3)) rc=1;
            /* libc's free advises MADV_DONTNEED: FreeBSD keeps the contents. */
            *(uint32_t *)p=0x600dcafe;
            if(!rc && !madvise(p,0x4000,4) && *(uint32_t *)p==0x600dcafe) checks++;else rc=1;
            errno=0;if(!rc && madvise(p,0x4000,99)==-1 && errno==EINVAL) checks++;else rc=1;
            /* Wine's process times come from getrusage. */
            struct rusage usage;memset(&usage,0xff,sizeof(usage));
            if(!rc && !getrusage(RUSAGE_SELF,&usage) && usage.ru_utime.tv_usec>=0 && usage.ru_utime.tv_usec<1000000) checks++;else rc=1;
            errno=0;if(!rc && getrusage(99,&usage)==-1 && errno==EINVAL) checks++;else rc=1;
            if(pw_wine_memory_release(p,0x4000)) rc=1;
        }
        if(!rc) {
            p=pw_wine_test_tryfixed(address,0x4000,0,0);
            if(p==MAP_FAILED) rc=1;
            else {
                if(pw_wine_test_tryfixed(address,0x4000,3,0)!=MAP_FAILED || errno!=EEXIST) rc=1;
                /* Wine commits a reservation by protecting it: the pages must then be usable. */
                const unsigned char code[]={0xb8,42,0,0,0,0xc3};
                if(!rc && !pw_wine_memory_protect(p,0x4000,7)) {
                    memcpy(p,code,sizeof(code));
                    if(((unsigned (*)(void))p)()==42) checks++;else rc=1;
                } else rc=1;
                if(pw_wine_memory_release(p,0x4000)) rc=1;else checks++;
            }
        }
        if(!rc && (pw_wine_test_tryfixed((char *)address+1,0x4000,3,0)!=MAP_FAILED || errno!=EINVAL)) rc=1;
        else if(!rc) checks++;
        if(!rc && (pw_wine_test_tryfixed(address,0x4000,3,MAP_SHARED)!=MAP_FAILED || errno!=ENOTSUP)) rc=1;
        else if(!rc) checks++;
        if(!rc && (pw_wine_test_tryfixed(address,0x4000,8,0)!=MAP_FAILED || errno!=EINVAL)) rc=1;
        else if(!rc) checks++;
        if(!rc) {
            p=pw_wine_test_tryfixed((char *)address+0x4000,0x4000,3,0);
            if(p==MAP_FAILED) rc=1;
            else {
                *(uint32_t *)p=0xabcdef;
                if(pw_wine_test_tryfixed(address,0x8000,3,0)!=MAP_FAILED || errno!=EEXIST || *(uint32_t *)p!=0xabcdef) rc=1;
                else checks++;
                if(pw_wine_memory_release(p,0x4000)) rc=1;
            }
        }
    } else if(kind==1) {
        if(mkdir("/data/wine-prefix",0700) || mkdir("/data/wine-home",0700)) rc=1;
        if(!rc && (pw_wine_init_paths("relative","/data/wine-home","orbis")!=-1 || errno!=EINVAL)) rc=1;
        else if(!rc) checks++;
        if(!rc && (pw_wine_init_paths("/data/absent-prefix","/data/wine-home","orbis")!=-1 || errno!=ENOENT)) rc=1;
        else if(!rc) checks++;
        if(!rc && (pw_wine_init_paths("/data/wine-prefix","/data/wine-home","bad/user")!=-1 || errno!=EINVAL)) rc=1;
        else if(!rc) checks++;
        if(!rc) rc=pw_wine_init_paths("/data/wine-prefix","/data/wine-home","orbis");
        if(!rc) rc=pw_wine_test_paths();
        if(!rc) checks++;
        int fd=!rc?open("/data/wine-prefix/result.tmp",O_CREAT|O_EXCL|O_RDWR,0600):-1;
        if(!rc && fd<0) rc=1;
        const char text[]="Wine PS4 prefix file roundtrip\n";char readback[sizeof(text)]={0};
        if(!rc && (write(fd,text,sizeof(text))!=(ssize_t)sizeof(text) || lseek(fd,0,SEEK_SET)!=0 ||
                    read(fd,readback,sizeof(readback))!=(ssize_t)sizeof(readback) || memcmp(text,readback,sizeof(text)))) rc=1;
        struct stat descriptor_stat;
        if(!rc && (pw_wine_fstat(fd,&descriptor_stat) || descriptor_stat.st_size!=(off_t)sizeof(text))) rc=1;
        if(!rc) checks++;
        if(fd>=0 && close(fd)) rc=1;
        if(!rc && rename("/data/wine-prefix/result.tmp","/data/wine-prefix/result.txt")) rc=1;
        struct stat st={0};if(!rc && (pw_wine_stat("/data/wine-prefix/result.txt",&st) || st.st_size!=(off_t)sizeof(text))) rc=1;
        if(!rc) checks++;
        if(!rc && (pw_wine_lstat("/data/wine-prefix/result.txt",&st) || st.st_size!=(off_t)sizeof(text))) rc=1;
        if(!rc) checks++;
        struct stat unchanged=st;
        if(!rc && (pw_wine_stat("/data/absent-stat",&st)!=-1 || errno!=ENOENT || memcmp(&unchanged,&st,sizeof(st)))) rc=1;
        if(!rc) checks++;
        if(!rc && (pw_wine_fstat(-1,&st)!=-1 || errno!=EBADF || memcmp(&unchanged,&st,sizeof(st)))) rc=1;
        if(!rc) checks++;
        if(!rc && (pw_wine_init_paths("/data/wine-prefix","/data/wine-prefix/result.txt","orbis")!=-1 || errno!=ENOTDIR)) rc=1;
        if(!rc) checks++;
    } else if(kind==2) {
        unsigned char output[64],saved[64];memset(output,0xa5,sizeof(output));memcpy(saved,output,sizeof(output));
        result=cdrom_DeviceIoControl(NULL,NULL,NULL,NULL,output,0,NULL,0,output,sizeof(output));
        if(result!=0xc00000bbu || memcmp(output,saved,sizeof(output))) rc=1;else checks++;
        result=get_device_info(-1,output);
        if(result!=0xc00000bbu || memcmp(output,saved,sizeof(output))) rc=1;else checks++;
    } else rc=1;
    snprintf(detail,capacity,"kind=%d rc=%d checks=%u result=0x%x actual_Wine_units=1 Wine_booted=0",kind,rc,checks,result);
    return rc;
}
