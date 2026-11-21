/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Core of the Phase B / P014 slim Wine client, shared by the host tool (pop_wine_join.c) and the PS4
 * payload-SDK child (process_p014_child.c). It joins an EXISTING wineserver by connecting to its master
 * socket by path -- the same path every standalone `wine foo.exe` takes (server/request.c
 * master_socket_poll_event does create_process(client, NULL, ...) on each accept) -- performs the minimal
 * init_first_thread handshake (no PE loader, no win32u), then creates or opens a NAMED kernel object to
 * prove cross-process shared named objects through the real wineserver. That is the mechanism a
 * dual-fixed-base launcher game needs: Prince of Persia's launcher and POP.exe rendezvous on a named
 * "PrinceSM" shared object. Wire logic mirrors dlls/ntdll/unix/server.c; layouts come from
 * pop_wine_proto.h (pinned to SERVER_PROTOCOL_VERSION). Each includer is its own standalone process, so
 * fatal paths exit(). */
#ifndef POP_WINE_JOIN_CORE_H
#define POP_WINE_JOIN_CORE_H
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/un.h>
#include <unistd.h>
#include "pop_wine_proto.h"

#ifndef MSG_CMSG_CLOEXEC
#define MSG_CMSG_CLOEXEC 0
#endif
#define POP_OBJ_OPENIF 0x80u
#define POP_STATUS_OBJECT_NAME_EXISTS ((unsigned int)0x40000000)
#define POP_MUTANT_ALL_ACCESS 0x1f0001u

struct pop_join {
    int fd_socket;   /* master connection */
    int request_fd;  /* per-process request socket from the server */
    int reply_fd;    /* our end of the reply pipe */
    FILE *log;       /* optional structured log; NULL -> stderr */
    unsigned int session_id,wine_pid,wine_tid;  /* from init_first_thread (Phase C uses the session) */
};

static void pop_logf(struct pop_join *j,const char *fmt,...){
    FILE *f=j->log?j->log:stderr;va_list ap;va_start(ap,fmt);vfprintf(f,fmt,ap);va_end(ap);fputc('\n',f);fflush(f);
}
static void pop_fail(struct pop_join *j,const char *what){pop_logf(j,"pop_wine_join FATAL %s: %s",what,strerror(errno));exit(2);}

static int pop_gettid(void){
#ifdef SYS_gettid
    return (int)syscall(SYS_gettid);
#else
    return (int)getpid();
#endif
}

/* wine_server_send_fd(): hand an fd to the server as an inflight fd keyed by (tid, fd-number) */
static void pop_send_fd(struct pop_join *j,int tid,int fd){
    struct send_fd data={.tid=(unsigned)tid,.fd=fd};
    struct iovec vec={&data,sizeof(data)};
    union{struct cmsghdr h;char space[CMSG_SPACE(sizeof(int))];}control;
    struct msghdr msg;memset(&msg,0,sizeof(msg));memset(&control,0,sizeof(control));
    msg.msg_iov=&vec;msg.msg_iovlen=1;msg.msg_control=control.space;msg.msg_controllen=CMSG_LEN(sizeof(int));
    struct cmsghdr *c=CMSG_FIRSTHDR(&msg);c->cmsg_level=SOL_SOCKET;c->cmsg_type=SCM_RIGHTS;c->cmsg_len=CMSG_LEN(sizeof(int));
    memcpy(CMSG_DATA(c),&fd,sizeof(int));
    for(;;){ssize_t r=sendmsg(j->fd_socket,&msg,0);if(r==(ssize_t)sizeof(data))return;if(r>=0){pop_logf(j,"send_fd partial");exit(2);}if(errno==EINTR)continue;pop_fail(j,"sendmsg send_fd");}
}

/* wine_server_receive_fd(): receive an SCM_RIGHTS fd plus an obj_handle_t tag in the data */
static int pop_receive_fd(struct pop_join *j,unsigned int *handle){
    struct iovec vec={handle,sizeof(*handle)};
    char cmsg_buffer[256];struct msghdr msg;memset(&msg,0,sizeof(msg));
    msg.msg_iov=&vec;msg.msg_iovlen=1;msg.msg_control=cmsg_buffer;msg.msg_controllen=sizeof(cmsg_buffer);
    for(;;){
        ssize_t r=recvmsg(j->fd_socket,&msg,MSG_CMSG_CLOEXEC);
        if(r>0){
            int fd=-1;
            for(struct cmsghdr *c=CMSG_FIRSTHDR(&msg);c;c=CMSG_NXTHDR(&msg,c))
                if(c->cmsg_level==SOL_SOCKET&&c->cmsg_type==SCM_RIGHTS)memcpy(&fd,CMSG_DATA(c),sizeof(int));
            return fd;
        }
        if(r==0)return -1;
        if(errno==EINTR)continue;
        pop_fail(j,"recvmsg receive_fd");
    }
}

/* server dir: PS4 port uses <config>/.wineserver/server-<dev>-<ino>; host uses /tmp/.wine-<uid>/server-... */
static void pop_server_dir(struct pop_join *j,const char *prefix,char *out,size_t n){
    const char *override=getenv("WINESERVERDIR");
    if(override&&*override){snprintf(out,n,"%s",override);return;}
    if(!prefix||!*prefix){prefix=getenv("WINEPREFIX");if(!prefix||!*prefix)prefix="/data/wine-prefix";}
    struct stat st;if(stat(prefix,&st)==-1)pop_fail(j,"stat WINEPREFIX");
#if defined(__FreeBSD__)||defined(__ORBIS__)
    snprintf(out,n,"%s/.wineserver/server-%llx-%llx",prefix,(unsigned long long)st.st_dev,(unsigned long long)st.st_ino);
#else
    snprintf(out,n,"/tmp/.wine-%u/server-%llx-%llx",(unsigned)getuid(),(unsigned long long)st.st_dev,(unsigned long long)st.st_ino);
#endif
}

static void pop_connect(struct pop_join *j,const char *prefix){
    char dir[400];pop_server_dir(j,prefix,dir,sizeof(dir));
    struct sockaddr_un addr;memset(&addr,0,sizeof(addr));addr.sun_family=AF_UNIX;
    snprintf(addr.sun_path,sizeof(addr.sun_path),"%s/socket",dir);
#if defined(__FreeBSD__)||defined(__ORBIS__)
    addr.sun_len=(uint8_t)(sizeof(addr)-sizeof(addr.sun_path)+strlen(addr.sun_path)+1);
#endif
    pop_logf(j,"pop_wine_join connecting %s",addr.sun_path);
    /* the in-process wineserver may still be coming up at boot; retry the connect for a while */
    int attempts=0;
    for(;;){
        j->fd_socket=socket(AF_UNIX,SOCK_STREAM,0);if(j->fd_socket==-1)pop_fail(j,"socket");
        if(connect(j->fd_socket,(struct sockaddr*)&addr,sizeof(addr))==0)break;
        close(j->fd_socket);j->fd_socket=-1;
        if(++attempts>=150){errno=errno?errno:ETIMEDOUT;pop_fail(j,"connect master socket");}
        if(attempts==1||attempts%25==0)pop_logf(j,"connect retry %d (errno %d)",attempts,errno);
        usleep(100000);
    }
    pop_logf(j,"connected after %d attempt(s)",attempts+1);
}

/* write a request union (+ optional vararg), read the reply union (+ extra); returns reply error */
static unsigned int pop_call(struct pop_join *j,union pop_request *req,size_t req_extra_len,const void *req_extra,
                             union pop_reply *rep,size_t rep_max,void *rep_extra){
    req->header.request_size=(data_size_t)req_extra_len;
    req->header.reply_size=(data_size_t)rep_max;
    if(write(j->request_fd,req,sizeof(*req))!=(ssize_t)sizeof(*req))pop_fail(j,"write req");
    if(req_extra_len&&write(j->request_fd,req_extra,req_extra_len)!=(ssize_t)req_extra_len)pop_fail(j,"write req data");
    size_t got=0;char *p=(char*)rep;
    while(got<sizeof(*rep)){ssize_t r=read(j->reply_fd,p+got,sizeof(*rep)-got);if(r<=0)pop_fail(j,"read reply");got+=(size_t)r;}
    data_size_t extra=rep->header.reply_size;
    for(size_t off=0;off<extra;){ssize_t r=read(j->reply_fd,(char*)rep_extra+off,extra-off);if(r<=0)pop_fail(j,"read reply data");off+=(size_t)r;}
    return rep->header.error;
}

static size_t pop_pack_objattr(char *buf,unsigned int attributes,const char *ascii){
    size_t nchars=strlen(ascii);
    struct object_attributes oa;memset(&oa,0,sizeof(oa));
    oa.attributes=attributes;oa.name_len=(data_size_t)(nchars*sizeof(uint16_t));
    memcpy(buf,&oa,sizeof(oa));
    uint16_t *name=(uint16_t*)(buf+sizeof(oa));
    for(size_t i=0;i<nchars;i++)name[i]=(uint16_t)(unsigned char)ascii[i];
    return sizeof(oa)+nchars*sizeof(uint16_t);
}

/* Join the wineserver at `prefix`, then create (opening=0) or open-if-exists (opening=1) the named mutex
 * `fullname` (an absolute object path like "\\BaseNamedObjects\\PrinceSM"). On a creator, hold the object
 * for hold_seconds so another process can observe it. Returns 1 on the expected outcome, 0 otherwise. */
static int pop_wine_join_run(struct pop_join *j,const char *prefix,int opening,const char *fullname,int hold_seconds){
    pop_connect(j,prefix);
    unsigned int version=0;j->request_fd=pop_receive_fd(j,&version);
    if(j->request_fd<0){pop_logf(j,"no request_fd");return 0;}
    if(version!=POP_SERVER_PROTOCOL_VERSION){pop_logf(j,"version mismatch %u/%u",version,POP_SERVER_PROTOCOL_VERSION);return 0;}
    pop_logf(j,"request_fd=%d version=%u OK",j->request_fd,version);

    int reply_pipe[2],wait_pipe[2];
    if(socketpair(AF_UNIX,SOCK_STREAM,0,reply_pipe)==-1||socketpair(AF_UNIX,SOCK_STREAM,0,wait_pipe)==-1)pop_fail(j,"socketpair");
    pop_send_fd(j,0,reply_pipe[1]);
    pop_send_fd(j,0,wait_pipe[1]);
    j->reply_fd=reply_pipe[0];

    union pop_request req;union pop_reply rep;unsigned short machines[32];
    memset(&req,0,sizeof(req));
    req.ift.__header.req=POP_REQ_init_first_thread;
    req.ift.unix_pid=getpid();req.ift.unix_tid=pop_gettid();
    req.ift.reply_fd=reply_pipe[1];req.ift.wait_fd=wait_pipe[1];
    req.ift.page_size=(unsigned)sysconf(_SC_PAGESIZE);
    unsigned int err=pop_call(j,&req,0,NULL,&rep,sizeof(machines),machines);
    if(err){pop_logf(j,"init_first_thread error 0x%08x",err);return 0;}
    pop_logf(j,"REGISTERED pid=%u tid=%u session=%u machines=%d",rep.ift.pid,rep.ift.tid,rep.ift.session_id,
             (int)(rep.ift.__header.reply_size/sizeof(unsigned short)));
    j->session_id=rep.ift.session_id;j->wine_pid=rep.ift.pid;j->wine_tid=rep.ift.tid;
    if(rep.ift.inproc_device){unsigned int h;pop_receive_fd(j,&h);}

    char attrbuf[512];size_t attrlen=pop_pack_objattr(attrbuf,opening?POP_OBJ_OPENIF:0,fullname);
    memset(&req,0,sizeof(req));
    req.cm.__header.req=POP_REQ_create_mutex;req.cm.access=POP_MUTANT_ALL_ACCESS;req.cm.owned=0;
    unsigned int merr=pop_call(j,&req,attrlen,attrbuf,&rep,0,NULL);
    unsigned int handle=rep.cm.handle;
    pop_logf(j,"create_mutex(%s) name=%s status=0x%08x handle=0x%x",opening?"OPENIF":"CREATE",fullname,merr,handle);

    int ok = opening ? (merr==POP_STATUS_OBJECT_NAME_EXISTS&&handle) : (merr==0&&handle);
    if(!opening&&ok&&hold_seconds>0){
        pop_logf(j,"holding object for %ds",hold_seconds);
        for(int i=0;i<hold_seconds;i++)sleep(1);
    }
    return ok;
}

#endif
