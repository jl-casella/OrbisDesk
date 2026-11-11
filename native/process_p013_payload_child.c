/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* P013 payload-SDK child: a dynamically-linked ELF built with the PS4 payload SDK toolchain (like elfldr's
 * own samples, which it loads successfully), to prove a libc/libkernel second process runs through the
 * loader's ELF path. The earlier P013 child, built with the OpenOrbis toolchain (crt1.o), stalled the loader
 * at kevent; the payload SDK's CRT self-resolves imports (__rtld_init) and places main at the offset elfldr
 * expects. POSIX/standard APIs only (no OpenOrbis sceKernel*), so it compiles with this toolchain. The
 * descriptor exchange (already proven in P007) is intentionally left out of this first payload-SDK child. */
#include <fcntl.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <time.h>
#include <unistd.h>
#include "process_p007_protocol.h"

static FILE *logfile;
static void note(const char *event, long value)
{
    if(logfile){fprintf(logfile,"{\"build\":\"P013\",\"side\":\"child\",\"event\":\"%s\",\"value\":%ld}\n",event,value);fflush(logfile);}
}
static void *worker(void *argument){*(volatile long *)argument=(long)getpid();return NULL;}

int main(void)
{
    /* the loader rdup's its socket onto the child's stdio, so the first line reaches the title's stream log */
    printf("P013 payload child pid=%ld\n",(long)getpid());fflush(stdout);
    int rfd=open("/data/orbisdesk/process-p013/request.bin",O_RDONLY);
    struct p007_request request;
    if(rfd<0 || read(rfd,&request,sizeof(request))!=(ssize_t)sizeof(request) || request.magic!=P007_MAGIC){
        printf("P013 payload child: request read failed\n");return 80;
    }
    close(rfd);
    const char *directory=request.directory;
    char path[256];snprintf(path,sizeof(path),"%s/child.jsonl",directory);
    logfile=fopen(path,"w");if(!logfile)return 82;
    note("child_entered",(long)getpid());note("child_ppid",(long)getppid());note("payload_sdk",1);
    snprintf(path,sizeof(path),"%s/state.bin",directory);
    int fd=open(path,O_RDWR);if(fd<0){note("state_open_failed",0);return 84;}
    void *view=mmap(NULL,P005_PAGE,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);close(fd);
    if(view==MAP_FAILED){note("state_map_failed",0);return 84;}
    struct p007_state *state=view;
    if(state->magic!=P007_MAGIC || memcmp(state->token,request.token,sizeof(request.token)) ||
       state->observer_pid==(uint32_t)getpid()){note("identity_failed",0);return 85;}
    state->helper_ppid=(uint32_t)getppid();__atomic_store_n(&state->helper_pid,(uint32_t)getpid(),__ATOMIC_RELEASE);
    /* the libc/pthread/heap/time pieces a Wine child would need, all through the payload SDK's runtime */
    volatile long seen=0;pthread_t thread;
    int rc=pthread_create(&thread,NULL,worker,(void *)&seen);if(!rc)pthread_join(thread,NULL);
    note("thread_ok",!rc && seen==getpid());
    void *heap=malloc(16<<20);if(heap)memset(heap,0x5a,16<<20);note("heap_ok",heap!=NULL);free(heap);
    struct timespec now;note("clock_ok",clock_gettime(CLOCK_MONOTONIC,&now)==0);
    note("own_code_address",(long)(uintptr_t)&main);
    /* the fixed PE32 base */
    void *fixed=mmap((void *)P007_BASE,P007_SPAN,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANON|MAP_FIXED,-1,0);
    if(fixed==(void *)P007_BASE){
        uint32_t marker=0xc0de0000u|((uint32_t)getpid()&0xffff);((volatile uint32_t *)fixed)[0]=marker;
        state->helper_marker=((volatile uint32_t *)fixed)[0];state->helper_fixed_address=P007_BASE;
        state->helper_fixed_ok=state->helper_marker==marker;
    }
    note("fixed_ok",state->helper_fixed_ok);note("fixed_addr",(long)(uintptr_t)fixed);
    /* cross-process descriptor exchange over the title's AF_UNIX socket, through Sony's native socket ABI
     * (the payload SDK's msghdr/cmsghdr match the kernel, so no adapter: it interoperates with the title's
     * pw_wine_sendmsg). Proven in P007 with the freestanding helper; here with a libc child. */
    state->helper_ipc_stage=1;int sock=socket(AF_UNIX,SOCK_STREAM,0);
    struct sockaddr_un address;memset(&address,0,sizeof(address));address.sun_family=AF_UNIX;
    snprintf(address.sun_path,sizeof(address.sun_path),"%s/ipc.sock",directory);
    address.sun_len=(uint8_t)(2+strlen(address.sun_path)+1);
    state->helper_ipc_stage=2;int crc=-1;
    for(unsigned n=0;sock>=0 && n<100;n++){crc=connect(sock,(struct sockaddr *)&address,address.sun_len);if(!crc)break;struct timespec d={0,20000000};nanosleep(&d,NULL);}
    if(sock>=0 && !crc){
        state->helper_connected=1;state->helper_ipc_stage=3;
        char byte=0;struct iovec iov={&byte,1};
        union {struct cmsghdr header;char space[CMSG_SPACE(sizeof(int))*2];} control;memset(&control,0,sizeof(control));
        struct msghdr message;memset(&message,0,sizeof(message));message.msg_iov=&iov;message.msg_iovlen=1;
        message.msg_control=control.space;message.msg_controllen=sizeof(control.space);
        ssize_t got=recvmsg(sock,&message,0);struct cmsghdr *header=CMSG_FIRSTHDR(&message);
        if(got==1 && byte=='T' && header && header->cmsg_level==SOL_SOCKET && header->cmsg_type==SCM_RIGHTS){
            int theirs;memcpy(&theirs,CMSG_DATA(header),sizeof(int));
            uint64_t content[2]={0,0};lseek(theirs,0,SEEK_SET);
            state->helper_got_fd=read(theirs,content,sizeof(content))==(ssize_t)sizeof(content) &&
                                 content[0]==request.token[0] && content[1]==UINT64_C(0x214446454c544954);
            close(theirs);note("received_fd_content_ok",state->helper_got_fd);
            state->helper_ipc_stage=4;snprintf(path,sizeof(path),"%s/helper-file.bin",directory);
            int own=open(path,O_RDWR|O_CREAT|O_TRUNC,0666);
            content[0]=request.token[1];content[1]=UINT64_C(0x44465245504c4548);
            if(own>=0 && write(own,content,sizeof(content))==(ssize_t)sizeof(content)){
                fsync(own);lseek(own,0,SEEK_SET);
                byte='H';memset(&control,0,sizeof(control));memset(&message,0,sizeof(message));
                message.msg_iov=&iov;message.msg_iovlen=1;message.msg_control=control.space;message.msg_controllen=CMSG_SPACE(sizeof(int));
                header=CMSG_FIRSTHDR(&message);header->cmsg_level=SOL_SOCKET;header->cmsg_type=SCM_RIGHTS;header->cmsg_len=CMSG_LEN(sizeof(int));
                memcpy(CMSG_DATA(header),&own,sizeof(int));
                state->helper_sent_fd=sendmsg(sock,&message,0)==1;note("sent_fd",state->helper_sent_fd);
            }else note("helper_file_failed",own<0?-1:0);
        }else note("receive_failed",got<0?-1:(long)got);
        state->helper_ipc_stage=5;
    }else note("connect_failed",crc);
    /* run alongside the title and show mutual progress */
    int result=84;uint32_t start=__atomic_load_n(&state->observer_tick,__ATOMIC_ACQUIRE);
    for(unsigned n=0;n<250;n++){
        __atomic_add_fetch(&state->helper_tick,1,__ATOMIC_RELEASE);
        if(__atomic_load_n(&state->observer_tick,__ATOMIC_ACQUIRE)>=start+5 &&
           __atomic_load_n(&state->observer_seen_child,__ATOMIC_ACQUIRE) && n>=10 &&
           (!state->helper_sent_fd || __atomic_load_n(&state->observer_got_fd,__ATOMIC_ACQUIRE))){
            state->helper_parent_progress=1;result=42;break;
        }
        struct timespec delay={0,20000000};nanosleep(&delay,NULL);
    }
    __atomic_store_n(&state->helper_done,(uint32_t)result,__ATOMIC_RELEASE);
    note("child_exit",result);fclose(logfile);
    return result;
}
