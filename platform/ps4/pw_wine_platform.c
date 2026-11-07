/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "pw_wine_platform.h"
#include "pw_vm_ps4_kernel.h"
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <string.h>
#include <orbis/libkernel.h>
#include <unistd.h>

long pw_wine_sysconf(int name)
{
    if(name==_SC_NPROCESSORS_ONLN || name==_SC_NPROCESSORS_CONF) {errno=ENOTSUP;return -1;}
    return sysconf(name);
}

static int result(int rc)
{
    if(!rc) return 0;
    /* OpenOrbis errno constants use the Orbis/FreeBSD numbering. */
    errno=((uint32_t)rc&0xffff0000u)==0x80020000u ? ((uint32_t)rc&0xffffu) : EIO;
    return -1;
}
static int shape(void *address,size_t bytes,int protection)
{
    uintptr_t start=(uintptr_t)address;
    if(!start || start%0x4000 || !bytes || bytes%0x4000 || bytes>UINTPTR_MAX-start ||
       (protection&~7)) {errno=EINVAL;return -1;}
    return 0;
}
/* W204: the fixed reservation or mapping below was refused with EINVAL for a range that libc
 * mmap (the non-fixed path of virtual.c) had just handed out and released (W203: Pale Moon's
 * allocator retried VirtualAlloc of the same 1 MB at 0x219400000 100 791 times). The same range
 * through libc mmap, as a hint without MAP_FIXED: kept only if the kernel places it exactly
 * there, so nothing is mapped over; elsewhere it is released and the range reported occupied. */
static void *tryfixed_hint(void *address,size_t bytes,int protection,const char *step,int rc)
{
    static unsigned count;
    void *mapped=mmap(address,bytes,protection,MAP_PRIVATE|MAP_ANON,-1,0);
    int saved=errno;
    if(count++<8 || !(count%1000)) {
        OrbisKernelVirtualQueryInfo info;memset(&info,0,sizeof(info));
        int query=sceKernelVirtualQuery(address,0,&info,sizeof(info));
        char text[256];
        snprintf(text,sizeof(text),"PWVM tryfixed_hint n=%u address=%p bytes=%zx step=%s rc=%x mapped=%p errno=%d "
                 "query=%x region=%p-%p flexible=%u direct=%u committed=%u\n",count,address,bytes,step,(unsigned)rc,
                 mapped,mapped==MAP_FAILED?saved:0,(unsigned)query,info.unk01,info.unk02,
                 info.isFlexibleMemory,info.isDirectMemory,info.isCommitted);
        sceKernelDebugOutText(0,text);
    }
    if(mapped==MAP_FAILED) {errno=saved;return MAP_FAILED;}
    if(mapped!=address) {munmap(mapped,bytes);errno=EEXIST;return MAP_FAILED;}
    return address;
}
void *pw_wine_anon_tryfixed(void *address,size_t bytes,int protection,int flags)
{
    if(shape(address,bytes,protection)) return MAP_FAILED;
    if(flags) {errno=ENOTSUP;return MAP_FAILED;}
    void *reserved=address;
    int reserve_rc=pw_ps4_kernel_reserve(&reserved,bytes,0x10|0x80,0x4000);
    if(reserve_rc) {
        result(reserve_rc);
        /* Orbis reserve may report ENOMEM for an occupied address. Wine needs
         * EEXIST to continue its address search. Only translate after a real
         * query proves overlap; do not disguise allocation exhaustion. */
        if(errno==ENOMEM) {
            int original_errno=errno;
            OrbisKernelVirtualQueryInfo info={0};
            if(!sceKernelVirtualQuery(address,1,&info,sizeof(info)) &&
               (uintptr_t)info.unk01<(uintptr_t)address+bytes &&
               (uintptr_t)info.unk02>(uintptr_t)address) errno=EEXIST;
            else errno=original_errno;
        }
        if(errno==EINVAL && protection) return tryfixed_hint(address,bytes,protection,"reserve",reserve_rc);
        return MAP_FAILED;
    }
    if(reserved!=address) {
        if(reserved) pw_ps4_kernel_unmap(reserved,bytes);
        if(protection) return tryfixed_hint(address,bytes,protection,"reserve_moved",0);
        errno=EINVAL;return MAP_FAILED;
    }
    /* PROT_NONE stays a virtual reservation. Wine's existing fixed anonymous
     * mapping path must commit it later; do not allocate physical memory here. */
    if(protection) {
        void *mapped=address;
        int rc=pw_ps4_kernel_map(&mapped,bytes,protection,0x10);
        if(rc || mapped!=address) {
            if(!rc && mapped && mapped!=address) pw_ps4_kernel_unmap(mapped,bytes);
            pw_ps4_kernel_unmap(reserved,bytes);
            if(rc) result(rc);else errno=EINVAL;
            if(errno==EINVAL) return tryfixed_hint(address,bytes,protection,rc?"map":"map_moved",rc);
            return MAP_FAILED;
        }
    }
    return address;
}
/* Wine commits reserved pages by changing their protection. A PROT_NONE
 * reservation has no memory on Orbis and the kernel ignores protection
 * changes on it, so the first accessible protection maps flexible memory over
 * each still-uncommitted part, as pw_wine_anon_tryfixed does for new views. */
static int commit_reserved(uintptr_t start,uintptr_t end,int protection)
{
    while(start<end) {
        OrbisKernelVirtualQueryInfo info;memset(&info,0,sizeof(info));
        if(sceKernelVirtualQuery((void *)start,0,&info,sizeof(info))) return 0;
        uintptr_t region_end=(uintptr_t)info.unk02;
        if(region_end<=start) return 0;
        uintptr_t stop=region_end<end?region_end:end;
        /* W175: ntdll maps direct memory under large commits (tools/build-audio-ps4.py); never
         * map flexible memory over it, whatever the committed bit says. */
        if(!info.isCommitted && !info.isDirectMemory) {
            void *mapped=(void *)start;
            int rc=pw_ps4_kernel_map(&mapped,stop-start,protection,0x10);
            if(rc) return result(rc);
            if(mapped!=(void *)start) {pw_ps4_kernel_unmap(mapped,stop-start);errno=EINVAL;return -1;}
        }
        start=stop;
    }
    return 0;
}
int pw_wine_memory_protect(void *address,size_t bytes,int protection)
{
    if(shape(address,bytes,protection)) return -1;
    if(protection && commit_reserved((uintptr_t)address,(uintptr_t)address+bytes,protection)) return -1;
    return result(pw_ps4_kernel_protect(address,bytes,protection));
}
int pw_wine_memory_release(void *address,size_t bytes)
{
    if(shape(address,bytes,0)) return -1;
    return result(pw_ps4_kernel_unmap(address,bytes));
}
static int directory(const char *path)
{
    if(!path || path[0]!='/') {errno=EINVAL;return -1;}
    struct stat st;
    if(pw_wine_stat(path,&st)) return -1;
    if(!S_ISDIR(st.st_mode)) {errno=ENOTDIR;return -1;}
    return 0;
}

/* OpenOrbis's public struct stat uses a 32-bit mode_t; the kernel wire ABI
 * uses 16-bit mode/nlink. Never let the kernel write directly into the public
 * structure: the timestamp/size offsets differ. */
typedef struct PwOrbisTimespec {int64_t sec,nsec;} PwOrbisTimespec;
typedef struct PwOrbisStat {
    uint32_t dev,ino;uint16_t mode,nlink;uint32_t uid,gid,rdev;
    PwOrbisTimespec atime,mtime,ctime;
    int64_t size,blocks;uint32_t blksize,flags,gen;int32_t spare;
    PwOrbisTimespec birthtime;
} PwOrbisStat;
_Static_assert(sizeof(PwOrbisStat)==120,"Orbis stat wire size");
_Static_assert(offsetof(PwOrbisStat,size)==72,"Orbis stat size offset");
_Static_assert(offsetof(PwOrbisStat,birthtime)==104,"Orbis stat birthtime offset");
static void convert_stat(struct stat *out,const PwOrbisStat *in)
{
    memset(out,0,sizeof(*out));
    out->st_dev=in->dev;out->st_ino=in->ino;out->st_mode=in->mode;out->st_nlink=in->nlink;
    out->st_uid=in->uid;out->st_gid=in->gid;out->st_rdev=in->rdev;
    out->st_atim.tv_sec=in->atime.sec;out->st_atim.tv_nsec=in->atime.nsec;
    out->st_mtim.tv_sec=in->mtime.sec;out->st_mtim.tv_nsec=in->mtime.nsec;
    out->st_ctim.tv_sec=in->ctime.sec;out->st_ctim.tv_nsec=in->ctime.nsec;
    out->st_size=in->size;out->st_blocks=in->blocks;out->st_blksize=in->blksize;
    out->st_flags=in->flags;out->st_gen=in->gen;
    out->st_birthtim.tv_sec=in->birthtime.sec;out->st_birthtim.tv_nsec=in->birthtime.nsec;
}
int pw_wine_stat(const char *path,struct stat *out)
{
    if(!path || !out) {errno=EINVAL;return -1;}
    PwOrbisStat wire={0};
    if(result(sceKernelStat(path,(OrbisKernelStat *)&wire))) return -1;
    if(!wire.ino && !wire.dev) {
        /* Retail PS4 path stat reports st_ino=0 and st_dev=0 (W005); fstat on the opened
         * file reports both. Wine compares them to find drive roots, so take the
         * identity from the descriptor. If the path cannot be opened, keep the zeros. */
        int fd=sceKernelOpen(path,0,0);
        if(fd>=0) {
            PwOrbisStat opened={0};
            if(!sceKernelFstat(fd,(OrbisKernelStat *)&opened)) {wire.ino=opened.ino;wire.dev=opened.dev;}
            sceKernelClose(fd);
        }
    }
    convert_stat(out,&wire);return 0;
}
int pw_wine_fstat(int fd,struct stat *out)
{
    if(!out) {errno=EINVAL;return -1;}
    PwOrbisStat wire={0};
    if(result(sceKernelFstat(fd,(OrbisKernelStat *)&wire))) return -1;
    convert_stat(out,&wire);return 0;
}
int pw_wine_lstat(const char *path,struct stat *out)
{
    if(!path || !out) {errno=EINVAL;return -1;}
    PwOrbisStat wire={0};
    if(!lstat(path,(struct stat *)&wire)) {convert_stat(out,&wire);return 0;}
    /* PS4 applications get EPERM from lstat (W002 on hardware) and cannot read
     * links either, so no link is observable to Wine there: serve it as stat. */
    if(errno!=EPERM) return -1;
    static int reported;
    if(!reported) {reported=1;sceKernelDebugOutText(0,"PWBOOT lstat_eperm_served_by_stat\n");}
    return pw_wine_stat(path,out);
}
int pw_wine_init_paths(const char *prefix,const char *home,const char *user)
{
    if(!user || !*user) {errno=EINVAL;return -1;}
    for(const unsigned char *p=(const unsigned char *)user;*p;++p)
        if(*p<33 || *p>126 || *p=='/' || *p=='\\' || *p=='=') {errno=EINVAL;return -1;}
    if(directory(prefix) || directory(home)) return -1;
    if(setenv("HOME",home,1) || setenv("USER",user,1) || setenv("WINEPREFIX",prefix,1)) return -1;
    return 0;
}
/* W043: ntdll's NtCreateUserProcess offers each new program to the title, which cannot
 * start a second process. Without a title-specific handler (the hardware launcher
 * defines one) nothing is switched: report it and fail. */
#include <stdio.h>
__attribute__((weak)) int pw_hw_switch_program(const char *image,const char *command_line)
{
    (void)command_line;
    fprintf(stderr,"PWBOOT switch_program unavailable image=%s\n",image);
    errno=ENOSYS;
    return -1;
}
