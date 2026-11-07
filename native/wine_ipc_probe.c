/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "pw_wine_net.h"
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/uio.h>
#include <unistd.h>
#include <pthread.h>
#include <stdint.h>
static void record(const char *name,int passed,long observed,int error)
{
    printf("PWSERVICE {\"case\":\"%s\",\"status\":\"%s\",\"observed\":%ld,\"errno\":%d}\n",
           name,passed?"passed":"blocked",observed,error);fflush(stdout);
}
static ssize_t send_rights(int socket,char marker,const int *fds,size_t count)
{
    union {struct cmsghdr aligned;char bytes[CMSG_SPACE(4*sizeof(int))];} control;
    memset(&control,0,sizeof(control));struct iovec payload={&marker,1};
    struct msghdr message={0};message.msg_iov=&payload;message.msg_iovlen=1;
    message.msg_control=&control;message.msg_controllen=CMSG_SPACE(count*sizeof(int));
    struct cmsghdr *header=CMSG_FIRSTHDR(&message);
    header->cmsg_level=SOL_SOCKET;header->cmsg_type=SCM_RIGHTS;
    header->cmsg_len=CMSG_LEN(count*sizeof(int));memcpy(CMSG_DATA(header),fds,count*sizeof(int));
    return pw_wine_sendmsg(socket,&message,0);
}
static ssize_t receive_rights(int socket,char *marker,int *fds,size_t capacity,int flags,int *truncated)
{
    union {struct cmsghdr aligned;char bytes[CMSG_SPACE(4*sizeof(int))];} control;
    memset(&control,0,sizeof(control));char bytes[32]={0};struct iovec payload={bytes,sizeof(bytes)};
    struct msghdr message={0};message.msg_iov=&payload;message.msg_iovlen=1;
    message.msg_control=&control;
    message.msg_controllen=capacity?CMSG_LEN(capacity*sizeof(int)):0;
    ssize_t got=pw_wine_recvmsg(socket,&message,flags);
    if(got!=1) return -1;
    *marker=bytes[0];*truncated=(message.msg_flags&MSG_CTRUNC)!=0;
    size_t count=0;
    for(struct cmsghdr *header=CMSG_FIRSTHDR(&message);header;header=CMSG_NXTHDR(&message,header)) {
        if(header->cmsg_level!=SOL_SOCKET || header->cmsg_type!=SCM_RIGHTS ||
           header->cmsg_len<CMSG_LEN(0)) return -1;
        size_t incoming=(header->cmsg_len-CMSG_LEN(0))/sizeof(int);
        if(incoming>capacity-count) return -1;
        memcpy(fds+count,CMSG_DATA(header),incoming*sizeof(int));count+=incoming;
    }
    return (ssize_t)count;
}
struct sender_state {int socket,fd;char marker;};
static void *concurrent_sender(void *argument)
{
    struct sender_state *state=argument;
    for(int n=0;n<10;n++) if(send_rights(state->socket,state->marker,&state->fd,1)!=1) return (void *)1;
    return NULL;
}
static int transfer_services(int transport[2])
{
    int passed=1,fd=open("/data/ipc-transfer.tmp",O_CREAT|O_TRUNC|O_RDWR,0600);
    if(fd<0) {record("scm-queued-owner",0,-1,errno);return 0;}
    int original=fd,received[4]={-1,-1,-1,-1},truncated=0;char marker=0,byte=0;
    int setup=write(fd,"abcd",4)==4 && lseek(fd,0,SEEK_SET)==0;
    int pair_fds[2]={fd,fd};
    int sent=setup && send_rights(transport[0],'m',pair_fds,2)==1;
    close(fd);fd=-1;
    ssize_t count=sent?receive_rights(transport[1],&marker,received,4,0,&truncated):-1;
    int ok=count==2 && marker=='m' && !truncated && received[0]!=received[1] &&
           read(received[0],&byte,1)==1 && byte=='a' && read(received[1],&byte,1)==1 && byte=='b' &&
           fcntl(received[0],F_GETFD)==0;
    record("scm-queued-owner",ok,count,errno);passed&=ok;
    if(count>0) for(int i=0;i<count;i++) close(received[i]);
    fd=open("/data/ipc-transfer.tmp",O_RDWR);
    if(fd<0) return 0;
    pair_fds[0]=pair_fds[1]=fd;
    sent=send_rights(transport[0],'t',pair_fds,2)==1;
    count=sent?receive_rights(transport[1],&marker,received,1,0,&truncated):-1;
    ok=count==1 && truncated && marker=='t';record("scm-truncation",ok,count,errno);passed&=ok;
    if(count>0) for(int i=0;i<count;i++) close(received[i]);
    sent=send_rights(transport[0],'n',&fd,1)==1;
    count=sent?receive_rights(transport[1],&marker,received,0,0,&truncated):-1;
    ok=count==0 && truncated && marker=='n';record("scm-zero-control",ok,count,errno);passed&=ok;
    char plain='b';
    sent=write(transport[0],&plain,1)==1 && send_rights(transport[0],'r',&fd,1)==1;
    count=sent?receive_rights(transport[1],&marker,received,1,0,&truncated):-1;
    ok=count==0 && marker=='b';
    count=sent?receive_rights(transport[1],&marker,received,1,0,&truncated):-1;
    ok=ok && count==1 && marker=='r';record("scm-stream-boundary",ok,count,errno);passed&=ok;
    if(count>0) for(int i=0;i<count;i++) close(received[i]);
    sent=send_rights(transport[0],'d',&fd,1)==1;
    char discard=0;
    ok=sent && read(transport[1],&discard,1)==1 && discard=='d';
    sent=send_rights(transport[0],'p',&fd,1)==1;
    count=sent?receive_rights(transport[1],&marker,received,1,MSG_PEEK,&truncated):-1;
    ok=ok && count==1 && marker=='p';int peek_fd=count==1?received[0]:-1;
    count=count==1?receive_rights(transport[1],&marker,received,1,0,&truncated):-1;
    ok=ok && count==1 && received[0]!=peek_fd && marker=='p';
    record("scm-discard-and-peek",ok,count,errno);passed&=ok;
    if(peek_fd>=0) close(peek_fd);
    if(count>0) for(int i=0;i<count;i++) close(received[i]);
    int sockets[2];ok=socketpair(AF_UNIX,SOCK_STREAM,0,sockets)==0;
    if(ok) {
        sent=send_rights(transport[0],'s',sockets,1)==1;close(sockets[0]);
        count=sent?receive_rights(transport[1],&marker,received,1,MSG_CMSG_CLOEXEC,&truncated):-1;
        ok=count==1 && write(sockets[1],"z",1)==1 && read(received[0],&byte,1)==1 && byte=='z' &&
           (fcntl(received[0],F_GETFD)&FD_CLOEXEC);
        if(count>0) for(int i=0;i<count;i++) close(received[i]);
        close(sockets[1]);
    }
    record("scm-socket-close-survival",ok,count,errno);passed&=ok;
    ok=socketpair(AF_UNIX,SOCK_STREAM,0,sockets)==0;
    if(ok) {
        int duplicate=dup(sockets[0]);
        ok=duplicate>=3 && duplicate!=sockets[0] && !fcntl(sockets[0],F_SETFL,O_NONBLOCK) &&
           (fcntl(duplicate,F_GETFL)&O_NONBLOCK) && !fcntl(sockets[0],F_SETFD,FD_CLOEXEC) &&
           fcntl(duplicate,F_GETFD)==0;
        close(sockets[0]);
        ok=ok && write(sockets[1],"q",1)==1 && read(duplicate,&byte,1)==1 && byte=='q';
        if(duplicate>=3) close(duplicate);close(sockets[1]);
    }
    record("socket-dup-shared-status",ok,ok,errno);passed&=ok;
    int invalid=-123;
    errno=0;ssize_t bad=send_rights(transport[0],'x',&invalid,1);int error=errno;
    struct pollfd waiting={transport[1],POLLIN,0};
    ok=bad==-1 && error==EBADF && pw_wine_poll(&waiting,1,0)==0;
    record("scm-invalid-no-data",ok,bad,error);passed&=ok;
    errno=0;bad=send_rights(transport[0],'x',transport,1);error=errno;
    ok=bad==-1 && error==EOPNOTSUPP && pw_wine_poll(&waiting,1,0)==0;
    record("scm-cycle-rejected",ok,bad,error);passed&=ok;
    int cycle[2];ok=socketpair(AF_UNIX,SOCK_STREAM,0,cycle)==0;
    if(ok) {
        sent=send_rights(transport[0],'c',cycle,1)==1;
        errno=0;bad=sent?send_rights(cycle[0],'x',transport,1):0;error=errno;
        ok=sent && bad==-1 && error==EOPNOTSUPP;
        count=sent?receive_rights(transport[1],&marker,received,1,0,&truncated):-1;
        ok=ok && count==1;
        if(count>0) for(int i=0;i<count;i++) close(received[i]);
        close(cycle[0]);close(cycle[1]);
    }
    record("scm-indirect-cycle-rejected",ok,bad,error);passed&=ok;
    int second=open("/data/ipc-transfer-other.tmp",O_CREAT|O_TRUNC|O_RDWR,0600);
    pthread_t workers[2];struct sender_state states[2]={{transport[0],fd,'A'},{transport[0],second,'B'}};
    ok=second>=0 && lseek(fd,0,SEEK_SET)==0 && write(fd,"A",1)==1 && write(second,"B",1)==1;
    int started=0;
    if(ok) for(int i=0;i<2;i++) {if(pthread_create(&workers[i],NULL,concurrent_sender,&states[i])) break;started++;}
    ok=ok && started==2;
    if(ok) for(int n=0;n<20;n++) {
        count=receive_rights(transport[1],&marker,received,1,0,&truncated);
        int matches=count==1 && !truncated && lseek(received[0],0,SEEK_SET)==0 &&
                    read(received[0],&byte,1)==1 && byte==marker;
        if(count>0) for(int i=0;i<count;i++) close(received[i]);
        ok=ok && matches;
    }
    for(int i=0;i<started;i++) {void *result=NULL;ok=(pthread_join(workers[i],&result)==0 && !result) && ok;}
    record("scm-concurrent-order",ok,started,errno);passed&=ok;
    if(second>=0) close(second);close(fd);
    fd=open("/data/ipc-transfer.tmp",O_RDONLY);
    ok=fd==original;record("scm-descriptor-reclamation",ok,fd,errno);passed&=ok;
    if(fd>=0) close(fd);
    unlink("/data/ipc-transfer.tmp");unlink("/data/ipc-transfer-other.tmp");return passed;
}
int pw_wine_boot_ipc_services(void)
{
    int pair[2];if(socketpair(AF_UNIX,SOCK_STREAM,0,pair)) {record("msg-vectors",0,-1,errno);return 92;}
    char a[]="hello ",b[]="world",received[12]={0};
    struct iovec sending[2]={{a,6},{b,5}},receiving[2]={{received,6},{received+6,5}};
    struct msghdr msg={0};msg.msg_iov=sending;msg.msg_iovlen=2;
    ssize_t sent=pw_wine_sendmsg(pair[0],&msg,0),got=-1;
    if(sent==11) {
        msg.msg_iov=receiving;
        got=pw_wine_recvmsg(pair[1],&msg,0);
    }
    int vectors=got==11 && !strcmp(received,"hello world") && msg.msg_flags==0 && msg.msg_controllen==0;
    record("msg-vectors",vectors,got,got<0?errno:0);
    if(!vectors) {close(pair[0]);close(pair[1]);return 92;}
    int set=fcntl(pair[1],F_SETFL,O_NONBLOCK),flags=fcntl(pair[1],F_GETFL);
    ssize_t empty=-1;int empty_error=0;
    if(set==0 && flags>=0 && (flags&O_NONBLOCK)) {
        errno=0;empty=pw_wine_recvmsg(pair[1],&msg,0);empty_error=errno;
    }
    int nonblocking=empty==-1 && (empty_error==EAGAIN || empty_error==EWOULDBLOCK);
    record("msg-nonblocking",nonblocking,empty,empty_error);
    if(fcntl(pair[1],F_SETFL,0)) nonblocking=0;
    int fd=open("/data/ipc-services.tmp",O_CREAT|O_TRUNC|O_RDWR,0600);
    if(fd<0 || write(fd,"abc",3)!=3 || lseek(fd,0,SEEK_SET)) {
        record("scm-rights",0,-1,errno);if(fd>=0) close(fd);close(pair[0]);close(pair[1]);return 92;
    }
    union {struct cmsghdr aligned;char bytes[CMSG_SPACE(sizeof(int))];} control;
    memset(&control,0,sizeof(control));char marker='r';struct iovec payload={&marker,1};
    memset(&msg,0,sizeof(msg));msg.msg_iov=&payload;msg.msg_iovlen=1;
    msg.msg_control=&control;msg.msg_controllen=sizeof(control);
    struct cmsghdr *header=CMSG_FIRSTHDR(&msg);header->cmsg_level=SOL_SOCKET;header->cmsg_type=SCM_RIGHTS;
    header->cmsg_len=CMSG_LEN(sizeof(fd));memcpy(CMSG_DATA(header),&fd,sizeof(fd));
    errno=0;sent=pw_wine_sendmsg(pair[0],&msg,0);int error=errno,rights=0,copy=-1;
    if(sent==1) {
        memset(&control,0,sizeof(control));marker=0;
        got=pw_wine_recvmsg(pair[1],&msg,MSG_CMSG_CLOEXEC);header=CMSG_FIRSTHDR(&msg);
        if(got==1 && marker=='r' && header && header->cmsg_level==SOL_SOCKET &&
           header->cmsg_type==SCM_RIGHTS && header->cmsg_len>=CMSG_LEN(sizeof(copy))) {
            memcpy(&copy,CMSG_DATA(header),sizeof(copy));char first=0,second=0,last=0;
            int flags=fcntl(copy,F_GETFD);
            rights=copy>=3 && copy!=fd && read(fd,&first,1)==1 && read(copy,&second,1)==1 &&
                   first=='a' && second=='b' && flags>=0 && (flags&FD_CLOEXEC);
            close(fd);fd=-1;
            rights=rights && read(copy,&last,1)==1 && last=='c';
        }
        if(copy>=3 && copy!=fd) close(copy);
    } else if(sent==-1 && error==EOPNOTSUPP) {
        struct pollfd pollfd={pair[1],POLLIN,0};int ready=pw_wine_poll(&pollfd,1,0);
        record("scm-rejects-without-data",ready==0,ready,ready<0?errno:0);
    }
    record("scm-rights",rights,sent,error);
    if(fd>=0) close(fd);
    int extra=rights?transfer_services(pair):0;
    unlink("/data/ipc-services.tmp");close(pair[0]);close(pair[1]);return rights && nonblocking && extra?0:92;
}
