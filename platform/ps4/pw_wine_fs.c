/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "pw_wine_fs.h"
#include "pw_wine_platform.h"
#include "pw_dirent_record.h"
#include "pw_trace.h"
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <limits.h>
#include <stdint.h>
#include <stddef.h>
#ifdef __ORBIS__
#include <orbis/libkernel.h>
#include <sys/socket.h>
#include "pw_wine_net.h"
#endif
enum {PATH_BYTES=PATH_MAX,FD_RECORDS=1024};
static pthread_mutex_t lock=PTHREAD_MUTEX_INITIALIZER;
static char current[2][PATH_BYTES]={"/","/"};
/* Directories keep their canonical path for openat/fchdir. Files keep the path and
 * open flags they were opened with, so a descriptor can be reopened when dup is
 * refused (PS4 applications get EPERM from dup, W010 on hardware). */
static struct {int used,fd,directory,flags;char path[PATH_BYTES];} records[FD_RECORDS];
static int directory_path(int fd,const struct stat *st,char *out);
/* PS4 applications cannot read or create symbolic links (readlink: ENOSYS on
 * hardware). The prefix's DOS drive links are a fixed mount table instead: every
 * path through <prefix>/dosdevices/c: or z: is rewritten to its target directory,
 * and pw_wine_readlink reports the link text Wine's own prefix would hold. A
 * missing target fails with the real error of the target path. */
/* phase 10: plus D:..K:, the USB disks at /mnt/usb0..7; DVD (J002): L:, the disc at /mnt/disc */
enum {DRIVE_MOUNTS=11,USB_SLOTS=9};
static struct {size_t length;char link[PATH_BYTES],target[PATH_BYTES];const char *text;} mounts[DRIVE_MOUNTS];
static unsigned mount_count;
/* Separate from `lock`: pw_wine_open resolves paths while holding it. */
static pthread_mutex_t mount_lock=PTHREAD_MUTEX_INITIALIZER;
/* phase 10: the USB slots, slot 0 = D: up to slot 7 = K:; slot 8 = L: is the optical disc, a
 * slot like the others: present while a disc's file system is mounted there (ROOT only) */
static const char *const usb_text[USB_SLOTS]={"/mnt/usb0","/mnt/usb1","/mnt/usb2","/mnt/usb3",
                                              "/mnt/usb4","/mnt/usb5","/mnt/usb6","/mnt/usb7",
                                              "/mnt/disc"};
enum {DISC_SLOT=8};
/* DVD (J002): the kind of disc at /mnt/disc, from the folders at its root (for the log) */
static const char *disc_kind(void)
{
    struct stat st;
    if(!pw_wine_stat("/mnt/disc/VIDEO_TS",&st)) return "dvd-video";
    if(!pw_wine_stat("/mnt/disc/BDMV",&st)) return "bd-video";
    if(!pw_wine_stat("/mnt/disc/sce_sys",&st)) return "ps4-game";
    return "data";
}
static char mount_prefix[PATH_BYTES];  /* the prefix of the table, for the hot-plug refresh */
static unsigned usb_mask;              /* the slots in the table */
/* The slots with a disk (J001: /mnt/usbN is seen only after GoldHEN's jailbreak,
 * native/wine_hardware.c; an empty slot is a directory on /mnt's own device). No lock held. */
static unsigned usb_scan(unsigned long long dev[USB_SLOTS])
{
    unsigned mask=0;struct stat mnt;
    if(pw_wine_stat("/mnt",&mnt)) return 0;
    for(unsigned slot=0;slot<USB_SLOTS;++slot) {
        struct stat st;
        if(!pw_wine_stat(usb_text[slot],&st) && S_ISDIR(st.st_mode) && st.st_dev!=mnt.st_dev) {
            mask|=1u<<slot;dev[slot]=(unsigned long long)st.st_dev;
        }
    }
    return mask;
}
/* mount_lock held: the entries after C: and Z: become the slots of mask */
static void usb_apply_locked(unsigned mask)
{
    unsigned count=2;
    for(unsigned slot=0;slot<USB_SLOTS;++slot) if(mask&1u<<slot) {
        snprintf(mounts[count].link,PATH_BYTES,"%s/dosdevices/%c:",mount_prefix,'d'+slot);
        snprintf(mounts[count].target,PATH_BYTES,"%s",usb_text[slot]);mounts[count].text=usb_text[slot];
        mounts[count].length=strlen(mounts[count].link);
        ++count;
    }
    mount_count=count;usb_mask=mask;
}
int pw_wine_fs_drive_mounts(const char *prefix)
{
    size_t n=prefix?strnlen(prefix,PATH_BYTES):0;
    if(!n || prefix[0]!='/' || prefix[n-1]=='/' || n+32>PATH_BYTES) {errno=EINVAL;return -1;}
    const char *slash=strrchr(prefix,'/');size_t parent=slash==prefix?1:(size_t)(slash-prefix);
    unsigned long long dev[USB_SLOTS]={0};unsigned mask=usb_scan(dev);
    for(unsigned slot=0;slot<USB_SLOTS;++slot)
        if(mask&1u<<slot) fprintf(stderr,"PWDRIVE %c: -> %s dev=%llx\n",'d'+slot,usb_text[slot],dev[slot]);
    if(mask&1u<<DISC_SLOT) fprintf(stderr,"PWDISC present l: kind=%s dev=%llx\n",disc_kind(),dev[DISC_SLOT]);
    pthread_mutex_lock(&mount_lock);
    snprintf(mounts[0].link,PATH_BYTES,"%s/dosdevices/c:",prefix);
    snprintf(mounts[0].target,PATH_BYTES,"%s/drive_c",prefix);mounts[0].text="../drive_c";
    snprintf(mounts[1].link,PATH_BYTES,"%s/dosdevices/z:",prefix);
    memcpy(mounts[1].target,prefix,parent);mounts[1].target[parent]=0;mounts[1].text="../..";
    for(unsigned i=0;i<2;++i) mounts[i].length=strlen(mounts[i].link);
    memcpy(mount_prefix,prefix,n+1);
    usb_apply_locked(mask);
    pthread_mutex_unlock(&mount_lock);
    return 0;
}
/* Phase 10 hot plug: the slots again, while Wine runs (the launcher's watcher, every 2 s in ROOT).
 * Returns the slot mask; before the table is built it changes nothing. */
unsigned pw_wine_fs_usb_refresh(void)
{
    unsigned long long dev[USB_SLOTS]={0};unsigned mask=usb_scan(dev),old;
    pthread_mutex_lock(&mount_lock);
    if(!mount_prefix[0]) {pthread_mutex_unlock(&mount_lock);return mask;}
    old=usb_mask;
    if(mask!=old) usb_apply_locked(mask);
    pthread_mutex_unlock(&mount_lock);
    for(unsigned slot=0;slot<USB_SLOTS;++slot) {
        unsigned bit=1u<<slot;
        if((mask&bit) && !(old&bit)) fprintf(stderr,"PWDRIVE added %c: -> %s dev=%llx\n",'d'+slot,usb_text[slot],dev[slot]);
        if((mask&bit) && !(old&bit) && slot==DISC_SLOT) fprintf(stderr,"PWDISC insert l: kind=%s dev=%llx\n",disc_kind(),dev[slot]);
        if(!(mask&bit) && (old&bit)) {
            /* descriptors still open on the disk: their reads and writes fail from now on */
            size_t length=strlen(usb_text[slot]);unsigned open_files=0;char first[PATH_BYTES]="-";
            pthread_mutex_lock(&lock);
            for(unsigned i=0;i<FD_RECORDS;++i)
                if(records[i].used && !strncmp(records[i].path,usb_text[slot],length) &&
                   (!records[i].path[length] || records[i].path[length]=='/')) {
                    if(!open_files++) strcpy(first,records[i].path);
                }
            pthread_mutex_unlock(&lock);
            fprintf(stderr,"PWDRIVE removed %c: (%s) open_files=%u first=%s\n",'d'+slot,usb_text[slot],open_files,first);
            if(slot==DISC_SLOT) fprintf(stderr,"PWDISC eject l: open_files=%u first=%s\n",open_files,first);
        }
    }
    return mask;
}
static int resolve_unmounted(int side,const char *path,char out[PATH_BYTES]);
static int resolve(int side,const char *path,char out[PATH_BYTES])
{
    char raw[PATH_BYTES];if(resolve_unmounted(side,path,raw)) return -1;
    pthread_mutex_lock(&mount_lock);
    for(unsigned i=0;i<mount_count;++i) {
        size_t length=mounts[i].length;
        if(strncmp(raw,mounts[i].link,length) || (raw[length] && raw[length]!='/')) continue;
        size_t target=strlen(mounts[i].target),rest=strlen(raw+length);
        if(target+rest+1>PATH_BYTES) {pthread_mutex_unlock(&mount_lock);errno=ENAMETOOLONG;return -1;}
        memcpy(out,mounts[i].target,target);memcpy(out+target,raw+length,rest+1);
        pthread_mutex_unlock(&mount_lock);return 0;
    }
    pthread_mutex_unlock(&mount_lock);strcpy(out,raw);return 0;
}
ssize_t pw_wine_readlink(int side,const char *path,char *buffer,size_t bytes)
{
    char full[PATH_BYTES];if(!buffer || !bytes) {errno=EINVAL;return -1;}
    if(resolve_unmounted(side,path,full)) return -1;
    pthread_mutex_lock(&mount_lock);
    for(unsigned i=0;i<mount_count;++i) if(!strcmp(full,mounts[i].link)) {
        size_t n=strlen(mounts[i].text);if(n>bytes) n=bytes;
        memcpy(buffer,mounts[i].text,n);pthread_mutex_unlock(&mount_lock);return (ssize_t)n;
    }
    pthread_mutex_unlock(&mount_lock);
    char target[PATH_BYTES];if(resolve(side,path,target)) return -1;
    return readlink(target,buffer,bytes);
}
/* Two module namespaces mirror the original separate Unix libraries.
 * Relative paths are resolved before entering kernel APIs. No host chdir. */
static int resolve_unmounted(int side,const char *path,char out[PATH_BYTES])
{
    if(side<0 || side>1 || !path || !*path) {errno=EINVAL;return -1;}
    size_t n=strnlen(path,PATH_BYTES);if(n==PATH_BYTES) {errno=ENAMETOOLONG;return -1;}
    if(path[0]=='/') {memcpy(out,path,n+1);return 0;}
    pthread_mutex_lock(&lock);size_t prefix=strlen(current[side]);
    if(prefix+n+2>PATH_BYTES) {pthread_mutex_unlock(&lock);errno=ENAMETOOLONG;return -1;}
    memcpy(out,current[side],prefix);out[prefix]='/';memcpy(out+prefix+1,path,n+1);
    pthread_mutex_unlock(&lock);return 0;
}
int pw_wine_chdir(int side,const char *path)
{
    char full[PATH_BYTES];struct stat st;
    if(resolve(side,path,full) || pw_wine_stat(full,&st)) return -1;
    if(!S_ISDIR(st.st_mode)) {errno=ENOTDIR;return -1;}
    /* Canonicalize only existing directories using the actual filesystem.
     * realpath receives an absolute path, so it cannot fall back to host cwd. */
    char canonical[PATH_BYTES];if(!pw_wine_realpath(side,full,canonical)) return -1;
    pthread_mutex_lock(&lock);strcpy(current[side],canonical);pthread_mutex_unlock(&lock);return 0;
}
char *pw_wine_getcwd(int side,char *buffer,size_t bytes)
{
    if(side<0 || side>1) {errno=EINVAL;return NULL;}
    pthread_mutex_lock(&lock);size_t need=strlen(current[side])+1;
    if(bytes && bytes<need) {pthread_mutex_unlock(&lock);errno=ERANGE;return NULL;}
    if(!buffer) {if(!bytes) bytes=need;buffer=malloc(bytes);if(!buffer) {pthread_mutex_unlock(&lock);return NULL;}}
    if(bytes<need) {pthread_mutex_unlock(&lock);errno=ERANGE;return NULL;}
    memcpy(buffer,current[side],need);pthread_mutex_unlock(&lock);return buffer;
}
/* DVD (W243): the first 64 opens under /mnt/disc (W241 had no sign of VLC reading the disc), and
 * the first 16 EMFILE/ENFILE (W241/W242: c000011f, STATUS_TOO_MANY_OPENED_FILES, after about 195
 * DLLs a VLC run loaded, the same in each of its runs: a ceiling, not a leak). At the first one,
 * the descriptors open (F_GETFD on 0..8191), the highest, and the kernel's limits; and a line
 * each time a descriptor goes 64 past the highest seen, to see the use grow. errno is kept. */
#ifdef __ORBIS__
extern int sysctl(const int *,unsigned int,void *,size_t *,const void *,size_t);
#endif
/* SeaMonkey descriptors (docs/SEAMONKEY_DESCRIPTORS.md; W303 04.11: YouTube stopped when the title ran out
 * at open=958, its disk cache and explorer's folder listing failing with it): what the descriptors are, so
 * a run tells a thread's pipes (six per live thread with the in-process server: request, reply, wait,
 * both ends) from sockets and from files (two per open handle: the server's and the client's cached
 * copy); and the kernel's descriptor limit. libkernel's getrlimit takes FreeBSD's numbers: RLIMIT_NOFILE
 * is 8 there (the SDK header's 7 is Linux's, FreeBSD's RLIMIT_NPROC). */
#ifdef __ORBIS__
struct pw_rlimit {int64_t current,maximum;};
extern int pw_getrlimit(int,struct pw_rlimit *) __asm__("getrlimit");  /* not the SDK header's prototype */
#endif
/* 04.24 (run-0224: SeaMonkey with GPU compositing hit EMFILE 10 s in at open=798, after 958 in run-0180 and 1035 in
 * run-0212, with RLIMIT_NOFILE at 13952): the limit is not the table's. The kernel's own counters, by name (the
 * numeric MIBs gave ENOENT): kern.openfiles is every process's open files, so it tells a console-wide limit from
 * the title's own. Each value as the kernel returns it (int or long); -1 and the errno when it refuses. */
#ifdef __ORBIS__
extern int sysctlbyname(const char *,void *,size_t *,const void *,size_t);
#endif
static int kernel_counters(char *line,size_t bytes)
{
    static const char *const names[]={"kern.openfiles","kern.maxfiles","kern.maxfilesperproc","kern.maxusers",
                                      "kern.ipc.numopensockets","kern.ipc.maxsockets","kern.ipc.pipekva",
                                      "kern.ipc.maxpipekva"};
    int len=0;
    for(unsigned i=0;i<sizeof(names)/sizeof(names[0]) && len<(int)bytes;++i) {
        long long value=-1;int rc=ENOSYS;
#ifdef __ORBIS__
        union {int i;long long l;} raw={.l=0};size_t size=sizeof(raw);
        rc=sysctlbyname(names[i],&raw,&size,NULL,0)?errno:0;
        if(!rc) value=size==sizeof(int)?raw.i:raw.l;
#endif
        if(rc) len+=snprintf(line+len,bytes-len," %s=-1/%d",names[i],rc);
        else len+=snprintf(line+len,bytes-len," %s=%lld",names[i],value);
    }
    return len;
}
/* The kinds of the open descriptors, as descriptor_report counts them; -1 in each on no scan */
struct descriptor_kinds {int open,highest,files,folders,pipes,sockets,others,unknown;};
static void descriptor_count(struct descriptor_kinds *kinds)
{
    memset(kinds,0,sizeof(*kinds));kinds->highest=-1;
    for(int i=0;i<8192;++i) if(fcntl(i,F_GETFD)!=-1) {
        struct stat st;
        kinds->open++;kinds->highest=i;
        if(pw_wine_fstat(i,&st)) kinds->unknown++;
        else if(S_ISREG(st.st_mode)) kinds->files++;
        else if(S_ISDIR(st.st_mode)) kinds->folders++;
        else if(S_ISFIFO(st.st_mode)) kinds->pipes++;
        else if(S_ISSOCK(st.st_mode)) kinds->sockets++;
        else kinds->others++;
    }
}
/* 04.24: at each fd_high, what the descriptors are, to see which kind grows to the limit. 04.26 (run-0234): a thread
 * made by NtCreateThreadEx holds three pipe ends since 04.25 (its wait pipe, the thread's two and the server's one) and
 * two socket ends (tools/prepare-wine-boot.py), so threads~ is pipes/3; a process's first thread still holds seven.
 * Every kern.* name answered ENOENT in run-0229 and run-0234, so they are read only once, at the first EMFILE. */
static void descriptor_growth(int fd)
{
    struct descriptor_kinds k;
    descriptor_count(&k);
    fprintf(stderr,"PWFS descriptor_growth fd=%d open=%d files=%d folders=%d pipes=%d sockets=%d other=%d unknown=%d"
            " threads~%d\n",fd,k.open,k.files,k.folders,k.pipes,k.sockets,k.others,k.unknown,k.pipes/3);
}
static void descriptor_report(void)
{
    int open_count=0,highest=-1,per_process=-1,system=-1,rc_process=-1,rc_system=-1;
    int files=0,folders=0,pipes=0,sockets=0,others=0,unknown=0;
    for(int i=0;i<8192;++i) if(fcntl(i,F_GETFD)!=-1) {
        struct stat st;
        open_count++;highest=i;
        if(pw_wine_fstat(i,&st)) unknown++;
        else if(S_ISREG(st.st_mode)) files++;
        else if(S_ISDIR(st.st_mode)) folders++;
        else if(S_ISFIFO(st.st_mode)) pipes++;
        else if(S_ISSOCK(st.st_mode)) sockets++;
        else others++;
    }
    long long limit_current=-1,limit_maximum=-1;int rc_limit=-1;
#ifdef __ORBIS__
    int mib[2]={1 /* CTL_KERN */,27 /* KERN_MAXFILESPERPROC */};size_t size=sizeof(per_process);
    rc_process=sysctl(mib,2,&per_process,&size,NULL,0)?errno:0;
    mib[1]=7 /* KERN_MAXFILES */;size=sizeof(system);
    rc_system=sysctl(mib,2,&system,&size,NULL,0)?errno:0;
    struct pw_rlimit limit={-1,-1};
    rc_limit=pw_getrlimit(8 /* FreeBSD RLIMIT_NOFILE */,&limit)?errno:0;
    limit_current=limit.current;limit_maximum=limit.maximum;
#endif
    fprintf(stderr,"PWFS descriptors open=%d highest=%d maxfilesperproc=%d errno=%d maxfiles=%d errno=%d\n",
            open_count,highest,per_process,rc_process,system,rc_system);
    fprintf(stderr,"PWFS descriptor_kinds files=%d folders=%d pipes=%d sockets=%d other=%d unknown=%d "
            "nofile=%lld/%lld errno=%d\n",files,folders,pipes,sockets,others,unknown,limit_current,limit_maximum,rc_limit);
    char counters[512];kernel_counters(counters,sizeof(counters));
    fprintf(stderr,"PWFS kernel_files%s\n",counters);  /* 04.24 */
}
static void open_trace(const char *path,int fd)
{
    static unsigned disc_opens,descriptor_failures;
    static int high_mark=128;
    int saved=errno;
    if(!strncmp(path,"/mnt/disc",9) && (!path[9] || path[9]=='/')) {
        unsigned n=__atomic_add_fetch(&disc_opens,1,__ATOMIC_RELAXED);
        if(n<=64) fprintf(stderr,"PWDISC open n=%u fd=%d errno=%d path=%s\n",n,fd,fd<0?saved:0,path);
    }
    if(fd>=high_mark) {
        high_mark=fd+64;
        fprintf(stderr,"PWFS fd_high fd=%d path=%s\n",fd,path);
        descriptor_growth(fd);  /* 04.24 */
    }
    if(fd<0 && (saved==EMFILE || saved==ENFILE)) {
        unsigned n=__atomic_add_fetch(&descriptor_failures,1,__ATOMIC_RELAXED);
        if(n<=16) fprintf(stderr,"PWFS open_failed errno=%d n=%u path=%s\n",saved,n,path);
        if(n==1) descriptor_report();
    }
    errno=saved;
}
int pw_wine_open(int side,const char *path,int flags,...)
{
    char full[PATH_BYTES];mode_t mode=0;
    if(flags&O_CREAT) {va_list args;va_start(args,flags);mode=va_arg(args,int);va_end(args);}
    if(resolve(side,path,full)) return -1;
    pthread_mutex_lock(&lock);
    int fd=open(full,flags,mode);open_trace(full,fd);if(fd<0) {pthread_mutex_unlock(&lock);return -1;}
    struct stat st;
    if(!pw_wine_fstat(fd,&st) && S_ISDIR(st.st_mode)) {
        char canonical[PATH_BYTES];
        if(!pw_wine_realpath(side,full,canonical)) {int saved=errno;close(fd);pthread_mutex_unlock(&lock);errno=saved;return -1;}
        int stored=0;
        for(unsigned i=0;i<FD_RECORDS;++i) if(!records[i].used) {
            records[i].used=1;records[i].fd=fd;records[i].directory=1;records[i].flags=O_RDONLY|O_DIRECTORY;
            strcpy(records[i].path,canonical);stored=1;break;
        }
        if(!stored) {close(fd);pthread_mutex_unlock(&lock);errno=EMFILE;return -1;}
    } else {
        /* Best effort: without a free record the descriptor simply cannot be reopened. */
        for(unsigned i=0;i<FD_RECORDS;++i) if(!records[i].used) {
            records[i].used=1;records[i].fd=fd;records[i].directory=0;
            records[i].flags=flags&~(O_CREAT|O_EXCL|O_TRUNC);strcpy(records[i].path,full);break;
        }
    }
    pthread_mutex_unlock(&lock);return fd;
}
static void forget_locked(int fd)
{
    for(unsigned i=0;i<FD_RECORDS;++i) if(records[i].used && records[i].fd==fd) records[i].used=0;
}
int pw_wine_close(int fd)
{
    pthread_mutex_lock(&lock);int rc=close(fd);if(!rc) forget_locked(fd);
    pthread_mutex_unlock(&lock);return rc;
}
/* fcntl byte-range locks (F_GETLK, F_SETLK, F_SETLKW) for wineserver's LockFile/LockFileEx
 * (docs/SEAMONKEY_FILE_LOCKS.md). The SDK's F_GETLK/F_SETLK/F_SETLKW are the kernel's (FreeBSD)
 * numbers, but its struct flock and F_RDLCK/F_WRLCK are Linux's, and its fcntl hands the pointer
 * to the kernel unchanged. The kernel then read the lock type from the wrong bytes (0, not a lock
 * type) and refused every lock with EINVAL: LockFileEx failed with ERROR_INVALID_PARAMETER and
 * SQLite reported SQLITE_BUSY (SeaMonkey: NS_ERROR_STORAGE_BUSY). Here the lock goes to the
 * kernel in its own layout and comes back translated; the first failures are traced. */
#ifdef __ORBIS__
struct pw_kernel_flock {int64_t l_start,l_len;int32_t l_pid;int16_t l_type,l_whence;int32_t l_sysid;};
_Static_assert(sizeof(struct pw_kernel_flock)==32,"FreeBSD struct flock");
enum {PW_KERNEL_RDLCK=1,PW_KERNEL_UNLCK=2,PW_KERNEL_WRLCK=3};
#endif
int pw_wine_fcntl_lock(int fd,int cmd,struct flock *lock)
{
#ifdef __ORBIS__
    struct pw_kernel_flock kernel;memset(&kernel,0,sizeof(kernel));
    kernel.l_start=lock->l_start;kernel.l_len=lock->l_len;kernel.l_pid=lock->l_pid;kernel.l_whence=lock->l_whence;
    switch(lock->l_type) {
    case F_RDLCK:kernel.l_type=PW_KERNEL_RDLCK;break;
    case F_WRLCK:kernel.l_type=PW_KERNEL_WRLCK;break;
    case F_UNLCK:kernel.l_type=PW_KERNEL_UNLCK;break;
    default:errno=EINVAL;return -1;
    }
    int rc=fcntl(fd,cmd,&kernel);  /* the SDK's fcntl passes the pointer through for these commands */
    if(rc==-1) {
        static int failures;int saved=errno;
        /* EBADF for a write lock: the handle is read-only (wineserver opened its file O_RDONLY) and
         * set_unix_lock asks again for a read lock, as on any Wine (04.14: SQLite's read-only
         * connections, PENDING byte). Not a failure; only a refused read lock or another error is. */
        if(!(saved==EBADF && lock->l_type==F_WRLCK) && __atomic_fetch_add(&failures,1,__ATOMIC_RELAXED)<8)
            fprintf(stderr,"PWFS lock_failed fd=%d cmd=%d type=%s start=%lld len=%lld errno=%d\n",fd,cmd,
                    lock->l_type==F_RDLCK?"read":lock->l_type==F_WRLCK?"write":"unlock",
                    (long long)lock->l_start,(long long)lock->l_len,saved);
        errno=saved;return -1;
    }
    if(cmd==F_GETLK) {
        lock->l_type=kernel.l_type==PW_KERNEL_RDLCK?F_RDLCK:kernel.l_type==PW_KERNEL_WRLCK?F_WRLCK:F_UNLCK;
        lock->l_whence=kernel.l_whence;lock->l_start=kernel.l_start;lock->l_len=kernel.l_len;lock->l_pid=kernel.l_pid;
    }
    return rc;
#else
    return fcntl(fd,cmd,lock);
#endif
}
#ifdef __ORBIS__
/* A real duplicate without dup(): pass the descriptor through a private socket pair with
 * SCM_RIGHTS (proven on hardware in W012) and take the received one. It shares the open
 * file description, so offset and status flags are shared as with dup, and it works for
 * sockets, which have no path to reopen (W032: set_queue_fd's dup of the input socket). */
static int scm_duplicate(int fd)
{
    static pthread_mutex_t channel_lock=PTHREAD_MUTEX_INITIALIZER;
    static int channel[2]={-1,-1};
    pthread_mutex_lock(&channel_lock);
    if(channel[0]<0 && socketpair(AF_UNIX,SOCK_STREAM,0,channel)) {
        int saved=errno;channel[0]=channel[1]=-1;pthread_mutex_unlock(&channel_lock);errno=saved;return -1;
    }
    char byte=0;struct iovec vec={&byte,1};
    union {struct cmsghdr header;char buffer[CMSG_SPACE(sizeof(int))];} control;memset(&control,0,sizeof(control));
    struct msghdr message;memset(&message,0,sizeof(message));
    message.msg_iov=&vec;message.msg_iovlen=1;message.msg_control=&control;message.msg_controllen=CMSG_SPACE(sizeof(int));
    struct cmsghdr *header=CMSG_FIRSTHDR(&message);
    header->cmsg_level=SOL_SOCKET;header->cmsg_type=SCM_RIGHTS;header->cmsg_len=CMSG_LEN(sizeof(int));
    memcpy(CMSG_DATA(header),&fd,sizeof(int));
    int copy=-1;
    if(pw_wine_sendmsg(channel[0],&message,0)==1) {
        char received[CMSG_SPACE(sizeof(int))*2];memset(received,0,sizeof(received));
        message.msg_control=received;message.msg_controllen=sizeof(received);
        if(pw_wine_recvmsg(channel[1],&message,0)==1)
            for(header=CMSG_FIRSTHDR(&message);header;header=CMSG_NXTHDR(&message,header))
                if(header->cmsg_level==SOL_SOCKET && header->cmsg_type==SCM_RIGHTS) memcpy(&copy,CMSG_DATA(header),sizeof(int));
    }
    int saved=errno;pthread_mutex_unlock(&channel_lock);
    if(copy<0) errno=saved?saved:EPERM;
    return copy;
}
#endif
int pw_wine_dup(int fd)
{
    pthread_mutex_lock(&lock);
    int found=-1;
    for(unsigned i=0;i<FD_RECORDS;i++) if(records[i].used && records[i].fd==fd) {found=(int)i;break;}
    int copy=dup(fd);
#ifdef __ORBIS__
    if(copy<0 && errno==EPERM) {
        static int reported;
        copy=scm_duplicate(fd);
        if(copy>=0 && !reported) {reported=1;sceKernelDebugOutText(0,"PWBOOT dup_eperm_scm_rights\n");}
        if(copy<0) errno=EPERM;
    }
#endif
    if(copy<0 && errno==EPERM && found>=0) {
        /* Reopen the same path instead. Unlike dup, the new descriptor has its own
         * file offset and status flags; the current offset is copied once. */
        static int reported;
#ifdef __ORBIS__
        if(!reported) {reported=1;sceKernelDebugOutText(0,"PWBOOT dup_eperm_reopen_by_path\n");}
#else
        (void)reported;
#endif
        copy=open(records[found].path,records[found].flags);
        if(copy>=0 && !records[found].directory) {
            off_t offset=lseek(fd,0,SEEK_CUR);
            if(offset>0 && lseek(copy,offset,SEEK_SET)!=offset) {int saved=errno;close(copy);copy=-1;errno=saved;}
        }
    }
    if(copy>=0 && found>=0) {
        int stored=0;
        for(unsigned i=0;i<FD_RECORDS;i++) if(!records[i].used) {
            records[i]=records[found];records[i].fd=copy;stored=1;break;
        }
        if(!stored && records[found].directory) {close(copy);copy=-1;errno=EMFILE;}
    }
    pthread_mutex_unlock(&lock);return copy;
}
int pw_wine_openat(int side,int directory,const char *path,int flags,...)
{
    mode_t mode=0;
    if(flags&O_CREAT) {va_list args;va_start(args,flags);mode=va_arg(args,int);va_end(args);}
    if(side<0 || side>1) {errno=EINVAL;return -1;}
    if(!path) {errno=EFAULT;return -1;}
    if(!*path) {errno=ENOENT;return -1;}
    if(path[0]=='/' || directory==AT_FDCWD) return pw_wine_open(side,path,flags,mode);
    struct stat st;if(pw_wine_fstat(directory,&st)) return -1;
    if(!S_ISDIR(st.st_mode)) {errno=ENOTDIR;return -1;}
    char full[PATH_BYTES]={0};
    if(directory_path(directory,&st,full)) {errno=ENOTSUP;return -1;}
    size_t prefix=strlen(full),tail=strnlen(path,PATH_BYTES);
    if(prefix+tail+2>PATH_BYTES) {errno=ENAMETOOLONG;return -1;}
    full[prefix++]='/';memcpy(full+prefix,path,tail+1);
    return pw_wine_open(side,full,flags,mode);
}
/* PoP D.7 (hardware 2026-11-13: Tony Hawk's American Wasteland's launcher, run in a separate process, said
 * "Please install DirectX 9.0c": its FindFirstFileA on C:\windows\system32\d3d9.dll failed with
 * ERROR_NOT_SUPPORTED, as every folder listing there did except the current folder's). In a separate process
 * (native/pop_wine_child.c) every directory descriptor comes from the title's wineserver over the bridge, so no
 * record of this process has its device and inode. Wine's client looks a path up before the server opens it
 * (lookup_unix_name's fstatat), so the folders looked up are remembered here by device and inode, and a
 * descriptor without a record takes the path of the folder with its identity, checked again before use. */
enum {SEEN_DIRECTORIES=256};
static struct {dev_t dev;ino_t ino;char path[PATH_BYTES];} seen[SEEN_DIRECTORIES];
static unsigned seen_count,seen_next;
static pthread_mutex_t seen_lock=PTHREAD_MUTEX_INITIALIZER;
static void seen_directory(const struct stat *st,const char *path)
{
    if(!st->st_ino || strnlen(path,PATH_BYTES)>=PATH_BYTES) return;  /* no identity, no record (W110) */
    pthread_mutex_lock(&seen_lock);
    unsigned i=0;
    while(i<seen_count && (seen[i].dev!=st->st_dev || seen[i].ino!=st->st_ino)) ++i;
    if(i==seen_count) {
        if(seen_count<SEEN_DIRECTORIES) i=seen_count++;
        else {i=seen_next;seen_next=(seen_next+1)%SEEN_DIRECTORIES;}
    }
    seen[i].dev=st->st_dev;seen[i].ino=st->st_ino;strcpy(seen[i].path,path);
    pthread_mutex_unlock(&seen_lock);
}
static int seen_path(const struct stat *st,char *out)
{
    int found=0;
    if(!st->st_ino) return -1;
    pthread_mutex_lock(&seen_lock);
    for(unsigned i=0;i<seen_count && !found;++i)
        if(seen[i].dev==st->st_dev && seen[i].ino==st->st_ino) {strcpy(out,seen[i].path);found=1;}
    pthread_mutex_unlock(&seen_lock);
    struct stat again;
    if(found && (pw_wine_stat(out,&again) || again.st_dev!=st->st_dev || again.st_ino!=st->st_ino)) found=0;
    return found?0:-1;
}

/* The canonical path of an open directory. W048: a descriptor that arrived by SCM_RIGHTS
 * (every handle the in-process server passes to a thread, and pw_wine_dup since W033)
 * has no record of its own, so NtQueryDirectoryFile's fchdir failed with ENOTSUP and
 * FindFirstFile with ERROR_NOT_SUPPORTED on hardware (the Start menu's folders). A
 * recorded directory with the same device and inode gives the path. A record found by
 * descriptor number must also match the inode: the number may have been reused. */
static int directory_path(int fd,const struct stat *st,char *out)
{
    int found=0;pthread_mutex_lock(&lock);
    for(unsigned pass=0;pass<2 && !found;++pass)
        for(unsigned i=0;i<FD_RECORDS && !found;++i) {
            if(!records[i].used || !records[i].directory || (!pass && records[i].fd!=fd)) continue;
            struct stat other;
            if(pw_wine_fstat(records[i].fd,&other) || other.st_dev!=st->st_dev || other.st_ino!=st->st_ino) continue;
            strcpy(out,records[i].path);found=1;
        }
    pthread_mutex_unlock(&lock);
    if(!found && !seen_path(st,out)) found=1;   /* PoP D.7: a descriptor from the title's server */
    return found?0:-1;
}
/* W050: Wine's lookup_unix_name tries one fstatat(root_fd, "<prefix>/dosdevices/c:/")
 * and, for a drive root (empty remaining name), returns STATUS_OBJECT_PATH_NOT_FOUND
 * when it fails; the console's C library does not know the mount table, so C:\ and Z:\
 * could not be opened (W049). Absolute or AT_FDCWD paths go through the mount table;
 * relative ones are joined to the directory's recorded path. Flags other than
 * AT_SYMLINK_NOFOLLOW (AT_NO_AUTOMOUNT) change nothing here. */
int pw_wine_fstatat(int side,int directory,const char *path,struct stat *out,int flags)
{
    if(!path || !out) {errno=EFAULT;return -1;}
    int follow=!(flags&AT_SYMLINK_NOFOLLOW);
    if(!*path) {errno=ENOENT;return -1;}
    if(path[0]=='/' || directory==AT_FDCWD) return pw_wine_path_stat(side,path,out,follow);
    struct stat st;if(pw_wine_fstat(directory,&st)) return -1;
    if(!S_ISDIR(st.st_mode)) {errno=ENOTDIR;return -1;}
    char full[PATH_BYTES]={0};
    if(directory_path(directory,&st,full)) {errno=ENOTSUP;return -1;}
    size_t prefix=strlen(full),tail=strnlen(path,PATH_BYTES);
    if(prefix+tail+2>PATH_BYTES) {errno=ENAMETOOLONG;return -1;}
    full[prefix++]='/';memcpy(full+prefix,path,tail+1);
    return pw_wine_path_stat(side,full,out,follow);
}
int pw_wine_fchdir(int side,int fd)
{
    struct stat st;if(pw_wine_fstat(fd,&st)) return -1;
    if(!S_ISDIR(st.st_mode)) {errno=ENOTDIR;return -1;}
    char path[PATH_BYTES]={0};
    if(directory_path(fd,&st,path)) {errno=ENOTSUP;return -1;}
    return pw_wine_chdir(side,path);
}
int pw_wine_path_stat(int side,const char *path,struct stat *out,int follow)
{
    char full[PATH_BYTES];if(resolve(side,path,full)) return -1;
    int rc=follow?pw_wine_stat(full,out):pw_wine_lstat(full,out);
    if(!rc && S_ISDIR(out->st_mode)) {int saved=errno;seen_directory(out,full);errno=saved;}   /* PoP D.7 */
    return rc;
}
int pw_wine_mkdir(int side,const char *path,mode_t mode)
{char full[PATH_BYTES];return resolve(side,path,full)?-1:mkdir(full,mode);}
int pw_wine_unlink(int side,const char *path)
{
    char full[PATH_BYTES];if(resolve(side,path,full)) return -1;
    int rc=unlink(full),saved=errno;
    /* alpha-1: every delete of an installer or a temp folder; failures always, the rest with traces (pw_trace.h) */
    if(rc || pw_trace_on()) fprintf(stderr,"PWDELETE unlink path=%s rc=%d errno=%d\n",full,rc,rc?saved:0);
    errno=saved;return rc;
}
int pw_wine_rmdir(int side,const char *path)
{
    char full[PATH_BYTES];if(resolve(side,path,full)) return -1;
    int rc=rmdir(full),saved=errno;
    if(rc || pw_trace_on()) fprintf(stderr,"PWDELETE rmdir path=%s rc=%d errno=%d\n",full,rc,rc?saved:0);
    errno=saved;return rc;
}
int pw_wine_rename(int side,const char *old,const char *new)
{
    char from[PATH_BYTES],to[PATH_BYTES],source[PATH_BYTES],target[PATH_BYTES],parent[PATH_BYTES];struct stat st;
    if(resolve(side,old,from)||resolve(side,new,to)) return -1;
    if(pw_wine_lstat(from,&st)) return -1;
    if(!S_ISDIR(st.st_mode)) return rename(from,to);
    if(!pw_wine_realpath(side,from,source)) return -1;
    char *base=strrchr(to,'/');
    if(!base || !base[1] || !strcmp(base+1,".") || !strcmp(base+1,"..")) {errno=EINVAL;return -1;}
    size_t parent_bytes=base-to;
    if(!parent_bytes) parent_bytes=1;
    memcpy(parent,to,parent_bytes);parent[parent_bytes]=0;
    if(!pw_wine_realpath(side,parent,target)) return -1;
    size_t length=strlen(target),tail=strlen(base+1);
    if(length+tail+2>sizeof(target)) {errno=ENAMETOOLONG;return -1;}
    if(length>1) target[length++]='/';
    strcpy(target+length,base+1);
    size_t before=strlen(source),after=strlen(target);
    if(!strcmp(source,"/")) {errno=EBUSY;return -1;}
    /* Keep mount roots stable; normal directory moves below them are real renames. */
    pthread_mutex_lock(&mount_lock);
    int mount_root=0;
    for(unsigned i=0;i<mount_count;++i) if(!strcmp(source,mounts[i].target)) mount_root=1;
    pthread_mutex_unlock(&mount_lock);
    if(mount_root) {errno=EBUSY;return -1;}
    pthread_mutex_lock(&lock);
    /* Check every replacement before the syscall: a successful rename must not
     * leave truncated paths for fchdir, openat or descriptor reopen. */
    for(unsigned i=0;i<FD_RECORDS+2;++i) {
        const char *path=i<FD_RECORDS?(records[i].used?records[i].path:NULL):current[i-FD_RECORDS];
        if(path && !strncmp(path,source,before) && (!path[before] || path[before]=='/') &&
           after+strlen(path+before)>=PATH_BYTES) {
            pthread_mutex_unlock(&lock);errno=ENAMETOOLONG;return -1;
        }
    }
    int result=rename(source,target),saved=errno;
    if(!result) for(unsigned i=0;i<FD_RECORDS+2;++i) {
        char *path=i<FD_RECORDS?(records[i].used?records[i].path:NULL):current[i-FD_RECORDS];
        if(path && !strncmp(path,source,before) && (!path[before] || path[before]=='/')) {
            memmove(path+after,path+before,strlen(path+before)+1);memcpy(path,target,after);
        }
    }
    pthread_mutex_unlock(&lock);
    if(result || pw_trace_on()) fprintf(stderr,"PWFS directory_rename from=%s to=%s rc=%d errno=%d\n",source,target,result,result?saved:0);
    errno=saved;return result;
}
int pw_wine_access(int side,const char *path,int mode)
{char full[PATH_BYTES];return resolve(side,path,full)?-1:access(full,mode);}
FILE *pw_wine_fopen(int side,const char *path,const char *mode)
{char full[PATH_BYTES];return resolve(side,path,full)?NULL:fopen(full,mode);}

char *pw_wine_realpath(int side,const char *path,char *output)
{
    char pending[PATH_BYTES],built[PATH_BYTES]="/";unsigned links=0;
    if(resolve(side,path,pending)) return NULL;
    size_t position=0,length=1;
    while(pending[position]) {
        while(pending[position]=='/') ++position;
        if(!pending[position]) break;
        size_t first=position;while(pending[position] && pending[position]!='/') ++position;
        size_t bytes=position-first;
        if(bytes==1 && pending[first]=='.') continue;
        if(bytes==2 && pending[first]=='.' && pending[first+1]=='.') {
            while(length>1 && built[length-1]!='/') --length;
            if(length>1) --length;
            built[length]=0;continue;
        }
        size_t parent=length;
        if(length>1) built[length++]='/';
        if(length+bytes+1>PATH_BYTES) {errno=ENAMETOOLONG;return NULL;}
        memcpy(built+length,pending+first,bytes);length+=bytes;built[length]=0;
        struct stat st;if(pw_wine_lstat(built,&st)) return NULL;
        if(S_ISLNK(st.st_mode)) {
            if(++links>40) {errno=ELOOP;return NULL;}
            char target[PATH_BYTES],rest[PATH_BYTES];
            ssize_t n=pw_wine_readlink(side,built,target,sizeof(target));
            if(n<=0) {if(!n) errno=ENOENT;return NULL;}
            if((size_t)n>=sizeof(target)) {errno=ENAMETOOLONG;return NULL;}target[n]=0;
            size_t remaining=strlen(pending+position);
            size_t lead=target[0]=='/'?0:parent;
            if(lead+1+(size_t)n+remaining+1>PATH_BYTES) {errno=ENAMETOOLONG;return NULL;}
            strcpy(rest,pending+position);
            if(lead) {memcpy(pending,built,lead);pending[lead++]='/';}
            memcpy(pending+lead,target,(size_t)n);strcpy(pending+lead+n,rest);
            position=0;length=1;built[1]=0;continue;
        }
        size_t next=position;while(pending[next]=='/') ++next;
        if(pending[next] && !S_ISDIR(st.st_mode)) {errno=ENOTDIR;return NULL;}
    }
    if(!output) {output=malloc(length+1);if(!output) return NULL;}
    memcpy(output,built,length+1);return output;
}

#ifdef __ORBIS__
typedef struct PwDirectory {
    int fd;
    pthread_mutex_t mutex;
    size_t position,available;
    unsigned char buffer[4096];
    struct dirent entry;
} PwDirectory;
_Static_assert(sizeof(PwDirHeader)==8,"Orbis directory header");
_Static_assert(offsetof(struct dirent,d_name)==8 && sizeof(struct dirent)==264,"SDK directory entry");
#endif
DIR *pw_wine_fdopendir(int fd)
{
    struct stat st;if(pw_wine_fstat(fd,&st)) return NULL;
    if(!S_ISDIR(st.st_mode)) {errno=ENOTDIR;return NULL;}
#ifdef __ORBIS__
    PwDirectory *directory=calloc(1,sizeof(*directory));if(!directory) return NULL;
    int error=pthread_mutex_init(&directory->mutex,NULL);
    if(error) {free(directory);errno=error;return NULL;}
    directory->fd=fd;return (DIR *)directory;
#else
    return fdopendir(fd);
#endif
}
DIR *pw_wine_opendir(int side,const char *path)
{
    int fd=pw_wine_open(side,path,O_RDONLY|O_DIRECTORY|O_CLOEXEC);if(fd<0) return NULL;
    DIR *directory=pw_wine_fdopendir(fd);
    if(!directory) {int saved=errno;pw_wine_close(fd);errno=saved;}
    return directory;
}
struct dirent *pw_wine_readdir(DIR *value)
{
    if(!value) {errno=EINVAL;return NULL;}
#ifdef __ORBIS__
    PwDirectory *directory=(PwDirectory *)value;pthread_mutex_lock(&directory->mutex);
next_record:
    if(directory->position==directory->available) {
        int result=sceKernelGetdents(directory->fd,(char *)directory->buffer,sizeof(directory->buffer));
        if(result<=0) {
            if(result<0) errno=((uint32_t)result&0xffff0000u)==0x80020000u?((uint32_t)result&0xffffu):EIO;
            if(result<0) {int saved=errno;fprintf(stderr,"PWDIRENUM getdents_failed fd=%d result=%d errno=%d\n",directory->fd,result,saved);errno=saved;}
            pthread_mutex_unlock(&directory->mutex);return NULL;
        }
        if((unsigned)result>sizeof(directory->buffer)) {errno=EIO;pthread_mutex_unlock(&directory->mutex);return NULL;}
        directory->position=0;directory->available=result;
    }
    size_t remaining=directory->available-directory->position;PwDirHeader header={0};
    const unsigned char *record=directory->buffer+directory->position;
    int state=pw_dirent_record(record,remaining,&header);
    if(state<0) {
        fprintf(stderr,"PWDIRENUM invalid_dirent fd=%d position=%zu available=%zu ino=%u length=%u type=%u namelen=%u remaining=%zu\n",
                directory->fd,directory->position,directory->available,header.inode,header.length,header.type,header.namelen,remaining);
        errno=EIO;pthread_mutex_unlock(&directory->mutex);return NULL;
    }
    if(!state) {
        int saved=errno;
        if(pw_trace_on()) fprintf(stderr,"PWDIRENUM skipped_unused fd=%d position=%zu length=%u inode=%u type=%u\n",directory->fd,directory->position,header.length,header.inode,header.type);
        errno=saved;
        directory->position+=header.length;
        goto next_record;
    }
    memset(&directory->entry,0,sizeof(directory->entry));
    memcpy(&directory->entry,record,sizeof(header)+header.namelen+1);
    directory->entry.d_reclen=sizeof(directory->entry);
    directory->position+=header.length;
    pthread_mutex_unlock(&directory->mutex);return &directory->entry;
#else
    return readdir(value);
#endif
}
int pw_wine_dirfd(DIR *directory)
{
    if(!directory) {errno=EINVAL;return -1;}
#ifdef __ORBIS__
    return ((PwDirectory *)directory)->fd;
#else
    return dirfd(directory);
#endif
}
void pw_wine_rewinddir(DIR *value)
{
    if(!value) {errno=EINVAL;return;}
#ifdef __ORBIS__
    PwDirectory *directory=(PwDirectory *)value;pthread_mutex_lock(&directory->mutex);
    if(lseek(directory->fd,0,SEEK_SET)==0) directory->position=directory->available=0;
    pthread_mutex_unlock(&directory->mutex);
#else
    rewinddir(value);
#endif
}
int pw_wine_closedir(DIR *value)
{
    if(!value) {errno=EINVAL;return -1;}
#ifdef __ORBIS__
    PwDirectory *directory=(PwDirectory *)value;
    int result=pw_wine_close(directory->fd),saved=errno;
    pthread_mutex_destroy(&directory->mutex);free(directory);errno=saved;return result;
#else
    pthread_mutex_lock(&lock);int fd=dirfd(value);int result=closedir(value);if(!result) forget_locked(fd);
    pthread_mutex_unlock(&lock);return result;
#endif
}
