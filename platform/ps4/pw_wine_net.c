/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "pw_wine_net.h"
#include "pw_wine_platform.h"
#include <errno.h>
#include <limits.h>
#include <pthread.h>
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/stat.h>
#include <orbis/libkernel.h>
/* SDK Net.h omits these prototypes. Target ABI: Orbis epoll events are 24
 * bytes; IN=1, OUT=2, ERR=8, HUP=16. Reference: shadPS4 net_types.h/net.cpp. */
typedef struct PwNetEvent {uint32_t events,pad;uint64_t ident,data;} PwNetEvent;
_Static_assert(sizeof(PwNetEvent)==24,"Orbis epoll event ABI");
extern int sceNetInit(void);
extern int sceNetEpollCreate(const char *,int);
extern int sceNetEpollControl(int,int,int,PwNetEvent *);
extern int sceNetEpollWait(int,PwNetEvent *,int,int);
extern int sceNetEpollDestroy(int);
extern int *sceNetErrnoLoc(void);
static pthread_once_t once=PTHREAD_ONCE_INIT;
static int initialization;
static void initialize(void) {initialization=sceNetInit();}
static int failure(void) {errno=*sceNetErrnoLoc();if(!errno) errno=EIO;return -1;}
/* W202: the in-process wineserver polls its whole descriptor table here (server/fd.c main_loop),
 * one slot per Windows thread plus its sockets, pipes and files. Up to W201 more than 256 failed
 * with EINVAL, and with Pale Moon as a guest of explorer every server poll failed: no request was
 * read any more and the desktop stopped. Past 256 the events buffer is on the heap. */
#define PW_POLL_MAX 4096
int pw_wine_poll(struct pollfd *fds,nfds_t count,int timeout)
{
    if(count>PW_POLL_MAX) {
        static int reported;
        if(!reported) {
            char text[96];
            reported=1;
            snprintf(text,sizeof(text),"PWNET poll_count_unsupported n=%u max=%d\n",(unsigned)count,PW_POLL_MAX);
            sceKernelDebugOutText(0,text);
        }
        errno=EINVAL;return -1;
    }
    if((count && !fds) || timeout>INT_MAX/1000) {errno=EINVAL;return -1;}
    if(count>256) {
        static nfds_t reported=256;
        if(count>=reported+64 || reported==256) {
            char text[96];
            reported=count;
            snprintf(text,sizeof(text),"PWNET poll_count n=%u\n",(unsigned)count);
            sceKernelDebugOutText(0,text);
        }
    }
    if(!count) {
        if(timeout<0) {errno=ENOTSUP;return -1;}
        if(timeout && sceKernelUsleep((unsigned)timeout*1000)) {errno=EINTR;return -1;}
        return 0;
    }
    pthread_once(&once,initialize);if(initialization<0) return failure();
    PwNetEvent stack_events[256],*events=stack_events;
    if(count>256 && !(events=malloc(count*sizeof(*events)))) {errno=ENOMEM;return -1;}
    int epoll=sceNetEpollCreate("wine-poll",0);
    if(epoll<0) {int saved=failure();if(events!=stack_events) free(events);return saved;}
    int ready=0,rc=0;
    for(nfds_t i=0;i<count;++i) {
        fds[i].revents=0;if(fds[i].fd<0) continue;
        /* W176: wineserver asks for POLLIN|POLLPRI on a socket with a waiting receive
         * (sock_get_poll_events). sceNetEpoll has no out-of-band event, so POLLPRI is left
         * out of the wait and never reported; POLLERR and POLLHUP are always reported, as by
         * poll(). Rejecting them failed every server poll while a receive waited (W174:
         * recv and recvfrom on network sockets never completed, 997 after the timeout). */
        if(fds[i].events&POLLPRI) {
            static int reported;
            if(!reported) {reported=1;sceKernelDebugOutText(0,"PWNET poll_pri_not_waited\n");}
        }
        if(fds[i].events&~(POLLIN|POLLRDNORM|POLLOUT|POLLWRNORM|POLLPRI|POLLERR|POLLHUP)) {
            static unsigned reported;
            if(reported++<8) {
                char text[96];
                snprintf(text,sizeof(text),"PWNET poll_events_unsupported fd=%d events=%x\n",fds[i].fd,fds[i].events);
                sceKernelDebugOutText(0,text);
            }
            errno=ENOTSUP;rc=-1;break;
        }
        for(nfds_t j=0;j<i;++j) if(fds[j].fd==fds[i].fd) {errno=ENOTSUP;rc=-1;break;}
        if(rc) break;
        PwNetEvent event={0};event.data=i;
        if(fds[i].events&(POLLIN|POLLRDNORM)) event.events|=1;
        if(fds[i].events&(POLLOUT|POLLWRNORM)) event.events|=2;
        if(!event.events) {
            /* W034: wineserver parks a descriptor with no events (the message queue's
             * input socket after it fired) and sceNetEpoll rejects an empty mask with
             * EINVAL, which failed the whole server loop. poll() reports only errors
             * and hang-ups for such an entry, so ask for exactly those; if even that is
             * refused, leave the entry out instead of failing every other descriptor. */
            event.events=8|16;
            if(sceNetEpollControl(epoll,1,fds[i].fd,&event)<0) {
                static int reported;
                if(!reported) {reported=1;sceKernelDebugOutText(0,"PWBOOT poll_idle_fd_skipped\n");}
            }
            continue;
        }
        if(sceNetEpollControl(epoll,1,fds[i].fd,&event)<0) {
            int net_errno=*sceNetErrnoLoc();
            struct stat st;int stat_rc=pw_wine_fstat(fds[i].fd,&st);
            if(!stat_rc && S_ISREG(st.st_mode)) {
                fds[i].revents=fds[i].events;++ready;
            } else if(errno==EBADF) {fds[i].revents=POLLNVAL;++ready;}
            else {
                /* W033: report descriptors the server loop cannot wait on */
                static unsigned reported;
                if(reported++<16) {
                    char text[160];
                    snprintf(text,sizeof(text),"PWBOOT poll_unsupported fd=%d events=%x net_errno=%d stat=%d mode=%o\n",
                             fds[i].fd,fds[i].events,net_errno,stat_rc,stat_rc?0:(unsigned)st.st_mode);
                    sceKernelDebugOutText(0,text);
                }
                errno=ENOTSUP;rc=-1;break;
            }
        }
    }
    if(!rc) {
        int found=sceNetEpollWait(epoll,events,(int)count,ready?0:timeout<0?-1:timeout*1000);
        if(found<0) rc=failure();
        else for(int n=0;n<found;++n) {
            uint64_t i=events[n].data;if(i>=count) {errno=EIO;rc=-1;break;}
            short value=0;
            if(events[n].events&1) value|=fds[i].events&(POLLIN|POLLRDNORM);
            if(events[n].events&2) value|=fds[i].events&(POLLOUT|POLLWRNORM);
            if(events[n].events&8) value|=POLLERR;
            if(events[n].events&16) value|=POLLHUP;
            if(value && !fds[i].revents) ++ready;
            fds[i].revents|=value;
        }
    }
    int saved=errno;
    if(events!=stack_events) free(events);
    if(sceNetEpollDestroy(epoll)<0 && !rc) return failure();
    errno=saved;return rc?rc:ready;
}

/* The SDK msghdr is 56 bytes (flags at 48), Orbis uses 48 (flags at 44).
 * Its cmsghdr also pads after len; the kernel pads after type instead. */
typedef struct PwMessage {
    void *name;uint32_t namelen,pad0;struct iovec *iov;int32_t iovlen,pad1;
    void *control;uint32_t controllen;int32_t flags;
} PwMessage;
typedef struct PwControl {uint32_t length;int32_t level,type;uint32_t pad;} PwControl;
_Static_assert(sizeof(PwMessage)==48 && offsetof(PwMessage,flags)==44,"Orbis msghdr ABI");
_Static_assert(sizeof(PwControl)==16,"Aligned Orbis control header");
_Static_assert(sizeof(struct cmsghdr)==16,"OpenOrbis control header");
extern ssize_t kernel_sendmsg(int,const PwMessage *,int) __asm__("sendmsg");
extern ssize_t kernel_recvmsg(int,PwMessage *,int) __asm__("recvmsg");
/* Records which layer refused a message (W011: recvmsg EINVAL on hardware). */
static void trace(const char *call,const char *stage,int error,const PwMessage *wire)
{
    static int traced;if(traced>=8) return;++traced;
    char text[160];snprintf(text,sizeof(text),"PWBOOT %s_failed stage=%s errno=%d iovlen=%d controllen=%u flags=0x%x\n",
                           call,stage,error,wire?wire->iovlen:-1,wire?wire->controllen:0,wire?(unsigned)wire->flags:0);
    sceKernelDebugOutText(0,text);
}
static int controls(void *destination,const void *source,size_t bytes,int to_kernel)
{
    size_t offset=0;
    if(bytes) memcpy(destination,source,bytes);
    while(bytes-offset>=16) {
        uint32_t length;
        memcpy(&length,(const char *)source+offset,sizeof(length));
        if(length<16 || length>bytes-offset) {errno=EINVAL;return -1;}
        if(to_kernel) {
            const struct cmsghdr *header=(const void *)((const char *)source+offset);
            PwControl *wire=(void *)((char *)destination+offset);
            wire->length=header->cmsg_len;wire->level=header->cmsg_level;wire->type=header->cmsg_type;wire->pad=0;
        } else {
            const PwControl *wire=(const void *)((const char *)source+offset);
            struct cmsghdr *header=(void *)((char *)destination+offset);
            memset(header,0,sizeof(*header));header->cmsg_len=wire->length;
            header->cmsg_level=wire->level;header->cmsg_type=wire->type;
        }
        size_t aligned=((size_t)length+7)&~(size_t)7;
        if(aligned>bytes-offset) break;
        offset+=aligned;
    }
    return 0;
}
/* Phase 8: the address of a datagram (sendto/recvfrom of a UDP socket, through ntdll's
 * try_send/try_recv) goes to the kernel as it is: the SDK's sockaddr has FreeBSD's layout
 * (sa_len, sa_family) and the kernel sets sa_len from the length given. */
static int message(const struct msghdr *source,PwMessage *wire,void **buffer)
{
    if(!source) {errno=EFAULT;return -1;}
    if(source->msg_iovlen<0 || source->msg_iovlen>1024 ||
       (source->msg_iovlen && !source->msg_iov) ||
       (source->msg_controllen && !source->msg_control)) {errno=EINVAL;return -1;}
    if(!source->msg_name && source->msg_namelen) {errno=EINVAL;return -1;}
    if(source->msg_namelen>sizeof(struct sockaddr_storage)) {errno=EINVAL;return -1;}
    if(source->msg_controllen>1024*1024) {errno=EMSGSIZE;return -1;}
    *buffer=source->msg_controllen?calloc(1,source->msg_controllen):NULL;
    if(source->msg_controllen && !*buffer) return -1;
    memset(wire,0,sizeof(*wire));wire->name=source->msg_name;wire->namelen=source->msg_namelen;
    wire->iov=source->msg_iov;wire->iovlen=source->msg_iovlen;
    wire->control=*buffer;wire->controllen=source->msg_controllen;return 0;
}
/* Phase 8: the SDK's MSG_* numbers are Linux's; the kernel reads FreeBSD's. Its MSG_DONTWAIT
 * (0x40) is FreeBSD's MSG_WAITALL, its MSG_WAITALL (0x100) FreeBSD's MSG_EOF, and the flags a
 * receive reports come back as FreeBSD's (MSG_TRUNC 0x10, MSG_CTRUNC 0x20, MSG_EOR 0x8). */
enum {KERNEL_MSG_OOB=0x1,KERNEL_MSG_PEEK=0x2,KERNEL_MSG_DONTROUTE=0x4,KERNEL_MSG_EOR=0x8,KERNEL_MSG_TRUNC=0x10,
      KERNEL_MSG_CTRUNC=0x20,KERNEL_MSG_WAITALL=0x40,KERNEL_MSG_DONTWAIT=0x80,KERNEL_MSG_NOSIGNAL=0x20000};
static const struct {int sdk,kernel;} message_flags[]={
    {MSG_OOB,KERNEL_MSG_OOB},{MSG_PEEK,KERNEL_MSG_PEEK},{MSG_DONTROUTE,KERNEL_MSG_DONTROUTE},
    {MSG_WAITALL,KERNEL_MSG_WAITALL},{MSG_DONTWAIT,KERNEL_MSG_DONTWAIT},{MSG_NOSIGNAL,KERNEL_MSG_NOSIGNAL}};
static const struct {int kernel,sdk;} received_flags[]={
    {KERNEL_MSG_OOB,MSG_OOB},{KERNEL_MSG_EOR,MSG_EOR},{KERNEL_MSG_TRUNC,MSG_TRUNC},{KERNEL_MSG_CTRUNC,MSG_CTRUNC}};
/* The kernel's flags for the SDK's FLAGS, or -1 when one of them has no translation. */
static int kernel_flags(int flags)
{
    int kernel=0;
    for(unsigned i=0;i<sizeof(message_flags)/sizeof(message_flags[0]);++i)
        if(flags&message_flags[i].sdk) {kernel|=message_flags[i].kernel;flags&=~message_flags[i].sdk;}
    return flags?-1:kernel;
}
int pw_wine_kernel_msg_flags(int flags) {return kernel_flags(flags);}
ssize_t pw_wine_sendmsg(int fd,const struct msghdr *source,int flags)
{
    int kernel=kernel_flags(flags);
    if(kernel<0) {errno=ENOTSUP;trace("sendmsg","flag",ENOTSUP,NULL);return -1;}
    PwMessage wire;void *buffer=NULL;if(message(source,&wire,&buffer)) {trace("sendmsg","header",errno,NULL);return -1;}
    if(controls(buffer,source->msg_control,wire.controllen,1)) {trace("sendmsg","control",errno,&wire);free(buffer);return -1;}
    ssize_t result=kernel_sendmsg(fd,&wire,kernel);int saved=errno;
    if(result<0 && saved!=EAGAIN) trace("sendmsg","kernel",saved,&wire);
    free(buffer);errno=saved;return result;
}
ssize_t pw_wine_recvmsg(int fd,struct msghdr *destination,int flags)
{
    int kernel=kernel_flags(flags&~MSG_CMSG_CLOEXEC);
    if(kernel<0) {errno=ENOTSUP;trace("recvmsg","flag",ENOTSUP,NULL);return -1;}
    PwMessage wire;void *buffer=NULL;if(message(destination,&wire,&buffer)) {trace("recvmsg","header",errno,NULL);return -1;}
    ssize_t result=kernel_recvmsg(fd,&wire,kernel);int saved=errno;
    if(result<0 && saved!=EAGAIN) trace("recvmsg","kernel",saved,&wire);
    if(result>=0) {
        int reported=0,unknown=wire.flags;
        for(unsigned i=0;i<sizeof(received_flags)/sizeof(received_flags[0]);++i)
            if(unknown&received_flags[i].kernel) {reported|=received_flags[i].sdk;unknown&=~received_flags[i].kernel;}
        if(unknown || wire.controllen>destination->msg_controllen) {saved=ENOTSUP;result=-1;trace("recvmsg","flags",saved,&wire);}
        else if(controls(destination->msg_control,buffer,wire.controllen,0)) {saved=errno;result=-1;trace("recvmsg","control",saved,&wire);}
        else {
            destination->msg_controllen=wire.controllen;destination->msg_flags=reported;destination->msg_namelen=wire.namelen;
            if(flags&MSG_CMSG_CLOEXEC) {
                for(struct cmsghdr *header=CMSG_FIRSTHDR(destination);header;header=CMSG_NXTHDR(destination,header)) {
                    if(header->cmsg_level!=SOL_SOCKET || header->cmsg_type!=SCM_RIGHTS) continue;
                    for(size_t n=0;n+sizeof(int)<=header->cmsg_len-16;n+=sizeof(int)) {
                        int received;memcpy(&received,CMSG_DATA(header)+n,sizeof(received));
                        if(!fcntl(received,F_SETFD,FD_CLOEXEC)) continue;
                        /* PS4 applications get EINVAL from every fcntl command (W012) and
                         * cannot exec, so close-on-exec has nothing to act on. */
                        if(errno==EINVAL) {
                            static int noted;
                            if(!noted++) sceKernelDebugOutText(0,"PWBOOT cloexec_einval_no_exec\n");
                            continue;
                        }
                        saved=errno;result=-1;trace("recvmsg","cloexec",saved,&wire);
                    }
                }
                if(result<0) {
                    for(struct cmsghdr *header=CMSG_FIRSTHDR(destination);header;header=CMSG_NXTHDR(destination,header)) {
                        if(header->cmsg_level!=SOL_SOCKET || header->cmsg_type!=SCM_RIGHTS) continue;
                        for(size_t n=0;n+sizeof(int)<=header->cmsg_len-16;n+=sizeof(int)) {
                            int received;memcpy(&received,CMSG_DATA(header)+n,sizeof(received));close(received);
                        }
                    }
                    destination->msg_controllen=0;
                }
            }
        }
    }
    free(buffer);errno=saved;return result;
}

/* Phase 8: wineserver makes every Winsock socket non-blocking with fcntl(F_SETFL, O_NONBLOCK)
 * (server/sock.c, revised by tools/build-wine-delete-server.py to call this). W013 measured
 * F_SETFL and FIONBIO refused on a console socket; libSceNet's own option, SO_NBIO, is the
 * second try. A socket left blocking would block the in-process server in connect and accept,
 * so a failure of both is traced and returned. */
extern int sceNetSetsockopt(int,int,int,const void *,unsigned int);
enum {SCE_NET_SOL_SOCKET=0xffff,SCE_NET_SO_NBIO=0x1200};
int pw_wine_socket_nonblock(int fd)
{
    errno=0;
    if(!fcntl(fd,F_SETFL,O_NONBLOCK)) return 0;
    int fcntl_errno=errno,on=1;
    pthread_once(&once,initialize);
    int rc=sceNetSetsockopt(fd,SCE_NET_SOL_SOCKET,SCE_NET_SO_NBIO,&on,sizeof(on));
    static int reported;
    if(rc<0 || !reported) {
        char text[160];
        reported=1;
        snprintf(text,sizeof(text),"PWNET nonblock fd=%d fcntl_errno=%d so_nbio=0x%08x net_errno=%d\n",
                 fd,fcntl_errno,(unsigned)rc,rc<0?*sceNetErrnoLoc():0);
        sceKernelDebugOutText(0,text);
    }
    if(rc<0) {errno=*sceNetErrnoLoc();if(!errno) errno=fcntl_errno?fcntl_errno:EIO;return -1;}
    return 0;
}

