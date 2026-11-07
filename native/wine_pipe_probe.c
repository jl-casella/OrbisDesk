/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "pw_wine_net.h"
#include "pw_wine_fs.h"
#include "pw_wine_platform.h"
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <signal.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/uio.h>
#include <unistd.h>
#include <orbis/libkernel.h>
extern int pw_wine_sigaction(int,const struct sigaction *,struct sigaction *);

static void record(const char *name,int ok,long observed)
{
    printf("PWSERVICE {\"case\":\"%s\",\"status\":\"%s\",\"observed\":%ld,\"errno\":%d}\n",
           name,ok?"passed":"blocked",observed,ok?0:errno);fflush(stdout);
}
static int create_pipe(int fds[2])
{
    fds[0]=-123;fds[1]=-456;
    int result=pipe(fds);
    if(!result && (fds[0]<3 || fds[1]<3 || fds[0]==fds[1])) {errno=ENOSYS;return -1;}
    return result;
}
static int ready(int fd,int timeout)
{
    struct pollfd pollfd={fd,POLLIN,0};
    int result=pw_wine_poll(&pollfd,1,timeout);
    return result==1 && (pollfd.revents&(POLLIN|POLLHUP));
}
static int basic(void)
{
    int fds[2];if(create_pipe(fds)) return 0;
    struct stat first,second;char text[3]={0};
    int ok=!pw_wine_fstat(fds[0],&first) && !pw_wine_fstat(fds[1],&second) &&
           S_ISFIFO(first.st_mode) && S_ISFIFO(second.st_mode) && first.st_ino &&
           first.st_ino==second.st_ino && first.st_dev==second.st_dev &&
           (fcntl(fds[0],F_GETFL)&O_ACCMODE)==O_RDONLY &&
           (fcntl(fds[1],F_GETFL)&O_ACCMODE)==O_WRONLY &&
           write(fds[1],"ok",2)==2 && ready(fds[0],10) && read(fds[0],text,2)==2 && !strcmp(text,"ok");
    close(fds[1]);ok=ok && ready(fds[0],10) && read(fds[0],text,1)==0;
    close(fds[0]);return ok;
}
static int access_errors(void)
{
    int fds[2];if(create_pipe(fds)) return 0;
    char byte=0;errno=0;int ok=read(fds[1],&byte,1)==-1 && errno==EBADF;
    errno=0;ok=ok && write(fds[0],"x",1)==-1 && errno==EBADF;
    errno=0;ok=ok && lseek(fds[0],0,SEEK_CUR)==-1 && errno==ESPIPE;
    errno=0;ok=ok && pread(fds[0],&byte,1,0)==-1 && errno==ESPIPE;
    errno=0;ok=ok && pwrite(fds[1],&byte,1,0)==-1 && errno==ESPIPE;
    ok=ok && read(fds[0],&byte,0)==0 && write(fds[1],&byte,0)==0;
    errno=0;ok=ok && pipe(NULL)==-1 && errno==EFAULT;
    int value=0;socklen_t length=sizeof(value);errno=0;
    ok=ok && getsockopt(fds[0],SOL_SOCKET,SO_TYPE,&value,&length)==-1 && errno==ENOTSOCK;
    close(fds[0]);close(fds[1]);return ok;
}
static int vectors(void)
{
    int fds[2];if(create_pipe(fds)) return 0;
    char first=0,rest[4]={0};
    struct iovec sending[2]={{"ab",2},{"cd",2}},receiving[2]={{&first,1},{rest,3}};
    int ok=writev(fds[1],sending,2)==4;
    struct iovec invalid[2]={{&first,1},{NULL,1}};errno=0;
    if(ok) ok=readv(fds[0],invalid,2)==-1 && errno==EFAULT &&
              readv(fds[0],receiving,2)==4 && first=='a' && !strcmp(rest,"bcd");
    close(fds[0]);close(fds[1]);return ok;
}
static int nonblocking(void)
{
    int fds[2];if(create_pipe(fds)) return 0;
    int ok=!fcntl(fds[0],F_SETFL,O_NONBLOCK) && !fcntl(fds[1],F_SETFL,O_NONBLOCK);
    char buffer[4096];memset(buffer,'f',sizeof(buffer));errno=0;
    ok=ok && read(fds[0],buffer,1)==-1 && errno==EAGAIN;
    size_t written=0,read_count=0;ssize_t amount=0;
    if(ok) for(int n=0;n<512;n++) {
        amount=write(fds[1],buffer,sizeof(buffer));
        if(amount<0) break;
        if(amount!=sizeof(buffer)) {ok=0;break;}
        written+=amount;
    }
    ok=ok && written>0 && amount==-1 && errno==EAGAIN;
    if(ok) {
        ok=read(fds[0],buffer,1)==1;read_count=1;errno=0;
        ok=ok && write(fds[1],"xy",2)==-1 && errno==EAGAIN;
        while((amount=read(fds[0],buffer,sizeof(buffer)))>0) read_count+=amount;
        ok=ok && amount==-1 && errno==EAGAIN && read_count==written;
    }
    close(fds[0]);close(fds[1]);return ok;
}
static int duplicates(void)
{
    int fds[2];if(create_pipe(fds)) return 0;
    int reader=dup(fds[0]),writer=dup(fds[1]);char byte=0;
    int ok=reader>=3 && writer>=3 && !fcntl(fds[0],F_SETFL,O_NONBLOCK) &&
           (fcntl(reader,F_GETFL)&O_NONBLOCK) && !fcntl(fds[0],F_SETFD,FD_CLOEXEC) &&
           fcntl(reader,F_GETFD)==0;
    close(fds[0]);close(fds[1]);
    ok=ok && !ready(reader,0) && write(writer,"d",1)==1 && read(reader,&byte,1)==1 && byte=='d';
    if(writer>=3) close(writer);
    ok=ok && ready(reader,10) && read(reader,&byte,1)==0;
    if(reader>=3) close(reader);return ok;
}
static int transfer(void)
{
    int fds[2],channel[2];if(create_pipe(fds)) return 0;
    if(socketpair(AF_UNIX,SOCK_STREAM,0,channel)) {close(fds[0]);close(fds[1]);return 0;}
    union {struct cmsghdr aligned;char bytes[CMSG_SPACE(2*sizeof(int))];} control;
    memset(&control,0,sizeof(control));char marker='p';struct iovec payload={&marker,1};
    struct msghdr message={0};message.msg_iov=&payload;message.msg_iovlen=1;
    message.msg_control=&control;message.msg_controllen=sizeof(control);
    struct cmsghdr *header=CMSG_FIRSTHDR(&message);
    header->cmsg_level=SOL_SOCKET;header->cmsg_type=SCM_RIGHTS;header->cmsg_len=CMSG_LEN(sizeof(fds));
    memcpy(CMSG_DATA(header),fds,sizeof(fds));
    int sent=pw_wine_sendmsg(channel[0],&message,0)==1;
    close(fds[0]);close(fds[1]);fds[0]=fds[1]=-1;
    int ok=0;
    if(sent) {
        memset(&control,0,sizeof(control));marker=0;
        ssize_t received=pw_wine_recvmsg(channel[1],&message,MSG_CMSG_CLOEXEC);
        header=CMSG_FIRSTHDR(&message);
        if(received==1 && marker=='p' && header && header->cmsg_level==SOL_SOCKET &&
           header->cmsg_type==SCM_RIGHTS && header->cmsg_len==CMSG_LEN(sizeof(fds))) {
            memcpy(fds,CMSG_DATA(header),sizeof(fds));char byte=0;struct stat st;
            ok=fds[0]>=3 && fds[1]>=3 && fds[0]!=fds[1] &&
               (fcntl(fds[0],F_GETFD)&FD_CLOEXEC) && (fcntl(fds[1],F_GETFD)&FD_CLOEXEC) &&
               !pw_wine_fstat(fds[0],&st) && S_ISFIFO(st.st_mode) &&
               write(fds[1],"t",1)==1 && read(fds[0],&byte,1)==1 && byte=='t';
            close(fds[1]);fds[1]=-1;ok=ok && ready(fds[0],10) && read(fds[0],&byte,1)==0;
        }
    }
    if(fds[0]>=3) close(fds[0]);if(fds[1]>=3) close(fds[1]);
    close(channel[0]);close(channel[1]);return ok;
}
struct reader_state {int fd;atomic_int started,done;int ok;};
static void *blocking_reader(void *argument)
{
    struct reader_state *state=argument;char byte=0;atomic_store(&state->started,1);
    state->ok=read(state->fd,&byte,1)==1 && byte=='w';atomic_store(&state->done,1);return NULL;
}
static int blocking(void)
{
    int fds[2];if(create_pipe(fds)) return 0;
    struct reader_state state={.fd=fds[0]};pthread_t thread;
    if(pthread_create(&thread,NULL,blocking_reader,&state)) {close(fds[0]);close(fds[1]);return 0;}
    for(int n=0;n<100 && !atomic_load(&state.started);n++) sceKernelUsleep(1000);
    sceKernelUsleep(10000);int ok=atomic_load(&state.started) && !atomic_load(&state.done);
    ok=(write(fds[1],"w",1)==1) && ok;close(fds[1]);
    ok=(pthread_join(thread,NULL)==0) && ok && state.ok;
    close(fds[0]);return ok;
}
struct writer_state {int fd;char marker;};
static void *atomic_writer(void *argument)
{
    struct writer_state *state=argument;char record[64];memset(record,state->marker,sizeof(record));
    int ok=1;for(int n=0;n<100;n++) if(write(state->fd,record,sizeof(record))!=sizeof(record)) {ok=0;break;}
    close(state->fd);return (void *)(intptr_t)!ok;
}
static int atomic_writes(void)
{
    int fds[2];if(create_pipe(fds)) return 0;
    struct writer_state states[2]={{dup(fds[1]),'A'},{dup(fds[1]),'B'}};
    pthread_t threads[2];int started=0,ok=states[0].fd>=3 && states[1].fd>=3;
    if(ok) for(int i=0;i<2;i++) {if(pthread_create(&threads[i],NULL,atomic_writer,&states[i])) break;started++;}
    close(fds[1]);ok=ok && started==2;
    for(int i=started;i<2;i++) if(states[i].fd>=3) close(states[i].fd);
    int counts[2]={0,0};char bytes[64];
    for(int n=0;n<started*100;n++) {
        size_t got=0;while(got<sizeof(bytes)) {ssize_t part=read(fds[0],bytes+got,sizeof(bytes)-got);if(part<=0) break;got+=part;}
        if(got!=sizeof(bytes)) {ok=0;break;}
        char marker=bytes[0];ok=ok && (marker=='A' || marker=='B');
        for(int i=1;i<sizeof(bytes);i++) if(bytes[i]!=marker) ok=0;
        if(marker=='A') counts[0]++;if(marker=='B') counts[1]++;
    }
    for(int i=0;i<started;i++) {void *result=NULL;ok=(pthread_join(threads[i],&result)==0 && !result) && ok;}
    ok=ok && counts[0]==100 && counts[1]==100 && read(fds[0],bytes,1)==0;
    close(fds[0]);return ok;
}
static int broken(void)
{
    int fds[2];if(create_pipe(fds)) return 0;
    struct sigaction action={0},previous;action.sa_handler=SIG_IGN;sigemptyset(&action.sa_mask);
    if(pw_wine_sigaction(SIGPIPE,&action,&previous)) {close(fds[0]);close(fds[1]);return 0;}
    close(fds[0]);errno=0;
    ssize_t result=write(fds[1],"x",1);int error=errno;close(fds[1]);
    int restored=pw_wine_sigaction(SIGPIPE,&previous,NULL);
    return result==-1 && error==EPIPE && restored==0;
}
static int allocation_rollback(void)
{
    int anchor=socket(AF_UNIX,SOCK_STREAM,0);if(anchor<0) return 0;
    int held[130][2],count=0,failed[2]={-123,-456},error=0;
    for(;count<130;count++) {
        int outputs[2]={-123,-456};errno=0;
        if(create_pipe(outputs)) {failed[0]=outputs[0];failed[1]=outputs[1];error=errno;break;}
        held[count][0]=outputs[0];held[count][1]=outputs[1];
    }
    int ok=count>0 && count<130 && failed[0]==-123 && failed[1]==-456 &&
           (error==EMFILE || error==ENFILE);
    for(int n=0;n<count;n++) {close(held[n][0]);close(held[n][1]);}
    close(anchor);int fresh[2];
    if(create_pipe(fresh)) return 0;
    char byte=0;ok=ok && write(fresh[1],"r",1)==1 && read(fresh[0],&byte,1)==1 && byte=='r';
    close(fresh[0]);close(fresh[1]);return ok;
}
int pw_wine_boot_pipe_services(void)
{
    struct {const char *name;int (*run)(void);} cases[]={
        {"pipe-basic-fifo-eof",basic},{"pipe-access-errors",access_errors},
        {"pipe-vectors",vectors},
        {"pipe-nonblocking-backpressure",nonblocking},{"pipe-dup-last-writer",duplicates},
        {"pipe-scm-rights",transfer},{"pipe-blocking-wakeup",blocking},
        {"pipe-atomic-writers",atomic_writes},{"pipe-broken-reader",broken},
        {"pipe-allocation-rollback",allocation_rollback}};
    int all=1;for(unsigned i=0;i<sizeof(cases)/sizeof(cases[0]);i++) {
        int ok=cases[i].run();record(cases[i].name,ok,ok);all=all && ok;
    }
    return all?0:92;
}
