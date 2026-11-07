/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "pw_wine_platform.h"
#include "pw_wine_fs.h"
#include <orbis/libkernel.h>
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
static int report(const char *name,int ok)
{
    int saved=errno;
    printf("PWSERVICE {\"case\":\"prefix-%s\",\"status\":\"%s\"}\n",name,ok?"passed":"blocked");
    fflush(stdout);
    /* Retail PS4 applications cannot redirect stdout (dup2: EPERM); the debug channel
     * is what a hardware launcher can capture. */
    char line[128];snprintf(line,sizeof(line),"PWBOOT preflight case=%s status=%s errno=%d\n",name,ok?"passed":"blocked",ok?0:saved);
    sceKernelDebugOutText(0,line);errno=saved;return ok;
}
static int registry(const char *name)
{
    char path[256],header[23];snprintf(path,sizeof(path),"/data/wine-prefix/%s",name);
    int fd=open(path,O_RDONLY);if(fd<0) return 0;
    int ok=read(fd,header,sizeof(header))==sizeof(header) && !memcmp(header,"WINE REGISTRY Version 2",sizeof(header));
    close(fd);return ok;
}
static int machine(const char *relative,uint16_t expected)
{
    char path[256];unsigned char header[64]={0},pe[26]={0};
    snprintf(path,sizeof(path),"/data/wine-prefix/%s",relative);
    int fd=open(path,O_RDONLY);if(fd<0) return 0;
    int ok=read(fd,header,64)==64 && header[0]=='M' && header[1]=='Z';
    uint32_t offset=(uint32_t)header[60]|((uint32_t)header[61]<<8)|((uint32_t)header[62]<<16)|((uint32_t)header[63]<<24);
    ok=ok && offset<=0x100000 && lseek(fd,offset,SEEK_SET)==offset && read(fd,pe,26)==26;
    if(ok) ok=!memcmp(pe,"PE\0\0",4) && (pe[4]|(pe[5]<<8))==expected &&
        (pe[24]|(pe[25]<<8))==(expected==0x14c?0x10b:0x20b);
    close(fd);return ok;
}
int pw_wine_prefix_preflight(void)
{
    int all=1;char link[32],canonical[4096];struct stat a={0},b={0};
    all&=report("system-registry",registry("system.reg"));
    all&=report("user-registry",registry("user.reg"));
    all&=report("userdef-registry",registry("userdef.reg"));
    all&=report("drive-c",pw_wine_readlink(0,"/data/wine-prefix/dosdevices/c:",link,sizeof(link))==10 && !memcmp(link,"../drive_c",10));
    all&=report("drive-z",pw_wine_readlink(0,"/data/wine-prefix/dosdevices/z:",link,sizeof(link))==5 && !memcmp(link,"../..",5));
    all&=report("drive-resolution",pw_wine_realpath(0,"/data/wine-prefix/dosdevices/c:/orbis/console32.exe",canonical) &&
        !strcmp(canonical,"/data/wine-prefix/drive_c/orbis/console32.exe"));
    all&=report("drive-z-resolution",pw_wine_realpath(0,"/data/wine-prefix/dosdevices/z:/wine-prefix/drive_c/orbis/console32.exe",canonical) &&
        !strcmp(canonical,"/data/wine-prefix/drive_c/orbis/console32.exe"));
    int fd=open("/data/wine-prefix/drive_c/orbis/console32.exe",O_RDONLY);
    /* fd>=0, not >=3: a retail PS4 application may start without descriptors 0-2. */
    int via_path=fd>=0?pw_wine_path_stat(0,"/data/wine-prefix/dosdevices/c:/orbis/console32.exe",&a,1):-1;
    int via_fd=fd>=0?pw_wine_fstat(fd,&b):-1;
    int ok=fd>=0 && !via_path && !via_fd && a.st_ino && a.st_ino==b.st_ino && a.st_dev==b.st_dev && a.st_size==b.st_size;
    char detail[192];snprintf(detail,sizeof(detail),"PWBOOT preflight identity fd=%d path_rc=%d fd_rc=%d ino=%llu/%llu dev=%llu/%llu size=%lld/%lld\n",
        fd,via_path,via_fd,(unsigned long long)a.st_ino,(unsigned long long)b.st_ino,(unsigned long long)a.st_dev,
        (unsigned long long)b.st_dev,(long long)a.st_size,(long long)b.st_size);
    sceKernelDebugOutText(0,detail);
    if(fd>=0) close(fd);all&=report("file-identity",ok);
    all&=report("exe-pe32",machine("drive_c/orbis/console32.exe",0x14c));
    const char *names[]={"ntdll","kernel32","kernelbase","wow64","wow64win","apisetschema"};
    char path[160];ok=1;
    for(unsigned i=0;i<6;++i) {snprintf(path,sizeof(path),"drive_c/windows/system32/%s.dll",names[i]);ok&=machine(path,0x8664);}
    all&=report("dll-pe64",ok);ok=1;
    for(unsigned i=0;i<3;++i) {snprintf(path,sizeof(path),"drive_c/windows/syswow64/%s.dll",names[i]);ok&=machine(path,0x14c);}
    all&=report("dll-pe32",ok);
    errno=0;all&=report("host-cpu-absent",pw_wine_lstat("/data/wine-prefix/drive_c/windows/system32/wow64cpu.dll",&a)==-1 && errno==ENOENT);
    if(all) {puts("PWBOOT prefix_preflight_passed");fflush(stdout);}
    return all?0:95;
}
