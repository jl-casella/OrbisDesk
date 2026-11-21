/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* P009 child: an OpenOrbis fake SELF linked as the Wine eboot is (static libc, ET_SCE_EXEC at a high base,
 * the same system libraries as DT_NEEDED), started by the resident loader's SELF path (file:// request,
 * execve in a loader child). It proves that such an image runs in its own process: it writes in the run
 * directory, uses threads and the heap, takes 0x400000 (free, since its own image is high) and exchanges a
 * descriptor with the title over its AF_UNIX socket. Argument 1: the run directory. */
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <unistd.h>
#include <orbis/libkernel.h>
#ifdef P013
/* P013: the same child, but a dynamically-linked ELF loaded by elfldr's ELF path (not an app SELF): it runs
 * at the real root (no sandbox) with libc/libkernel resolved by Sony's linker, which is the substrate Wine
 * would use. No /app0 needed. The run directory comes from the request file (the ELF path passes no argv). */
#define CHILD_BUILD "P013"
#define P005_REQUEST_PATH "/data/orbisdesk/process-p013/request.bin"
#define P007_RUN_PREFIX "/data/orbisdesk/process-p013/run-"
#elif defined(P012)
#define CHILD_BUILD "P012"
#define P005_REQUEST_PATH "/data/orbisdesk/process-p012/request.bin"
#define P007_RUN_PREFIX "/data/orbisdesk/process-p012/run-"
#else
#define CHILD_BUILD "P009"
#define P005_REQUEST_PATH "/data/orbisdesk/process-p009/request.bin"
#define P007_RUN_PREFIX "/data/orbisdesk/process-p009/run-"
#endif
#include "process_p007_protocol.h"
ssize_t pw_wine_sendmsg(int,const struct msghdr *,int);
ssize_t pw_wine_recvmsg(int,struct msghdr *,int);
int pw_trace_level=0;
static FILE *logfile;
static void note(const char *event,long value)
{
    if(logfile){fprintf(logfile,"{\"build\":\"" CHILD_BUILD "\",\"side\":\"child\",\"event\":\"%s\",\"value\":%ld}\n",event,value);fflush(logfile);fsync(fileno(logfile));}
}
static void *worker(void *argument){*(volatile long *)argument=(long)getpid();return NULL;}
int main(int argc,char **argv)
{
    /* stdout/stderr are the loader's socket to the title (selfldr's rdup): the first line shows the start */
    printf(CHILD_BUILD " child pid=%ld argc=%d\n",(long)getpid(),argc);fflush(stdout);
#ifdef P013
    /* the ELF path passes no args; the run directory comes from the request file written by the title */
    struct p007_request preq;int preqfd=open(P005_REQUEST_PATH,O_RDONLY);
    if(preqfd<0 || read(preqfd,&preq,sizeof(preq))!=(ssize_t)sizeof(preq) || preq.magic!=P007_MAGIC){
        printf(CHILD_BUILD " request read failed errno=%d\n",errno);return 80;}
    close(preqfd);
    const char *directory=preq.directory;(void)argv;
#else
    if(argc<2)return 80;
    const char *directory=argv[1];
#endif
    size_t prefix=strlen(P007_RUN_PREFIX);
    if(strncmp(directory,P007_RUN_PREFIX,prefix) || strchr(directory+prefix,'.') || strlen(directory)>=160)return 81;
    char path[224];snprintf(path,sizeof(path),"%s/child.jsonl",directory);
    logfile=fopen(path,"w");if(!logfile){printf(CHILD_BUILD " child log open failed errno=%d\n",errno);return 82;}
    note("child_entered",(long)getpid());note("child_ppid",(long)getppid());
#ifdef P012
    note("candidate_revision_01_12",112);note("variant_sandbox",1);
#else
    if(argc>2)note(argv[2][0]=='s'?"variant_system":"variant_npdrm",1);
#endif
    struct p007_request request;int fd=open(P005_REQUEST_PATH,O_RDONLY);
    if(fd<0 || read(fd,&request,sizeof(request))!=(ssize_t)sizeof(request) || request.magic!=P007_MAGIC){note("request_failed",errno);return 83;}
    close(fd);
    snprintf(path,sizeof(path),"%s/state.bin",directory);fd=open(path,O_RDWR);
    void *view=NULL;int rc=fd<0?-1:sceKernelMmap(NULL,P005_PAGE,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0,&view);
    if(fd>=0)close(fd);
    if(rc){note("state_map_failed",rc);return 84;}
    struct p007_state *state=view;
    if(state->magic!=P007_MAGIC || memcmp(state->token,request.token,sizeof(request.token)) ||
       state->observer_pid==(uint32_t)getpid()){note("state_identity_failed",1);return 85;}
    state->helper_ppid=(uint32_t)getppid();__atomic_store_n(&state->helper_pid,(uint32_t)getpid(),__ATOMIC_RELEASE);
    /* the runtime pieces Wine uses at start: threads, a large heap, the process clock */
    volatile long seen=0;pthread_t thread;
    rc=pthread_create(&thread,NULL,worker,(void *)&seen);if(!rc)pthread_join(thread,NULL);
    note("thread_ok",!rc && seen==getpid());
    void *heap=malloc(64<<20);if(heap)memset(heap,0x5a,64<<20);note("heap_64mib_ok",heap!=NULL);free(heap);
    note("process_time_us",(long)sceKernelGetProcessTime());
    /* where this image is, and whether 0x400000 is free for a PE32 */
    note("own_code_address",(long)(uintptr_t)&main);
    OrbisKernelVirtualQueryInfo info;memset(&info,0,sizeof(info));
    int occupied=!sceKernelVirtualQuery((const void *)P007_BASE,1,&info,sizeof(info)) && (uint64_t)info.unk01<P007_BASE+P007_SPAN;
    state->helper_span_free_before=!occupied;note("span_occupied",occupied);
    if(occupied)note("occupant_start",(long)(uintptr_t)info.unk01);
    else{
        void *fixed=NULL;
        rc=sceKernelMmap((void *)P007_BASE,P007_SPAN,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANON|MAP_FIXED,-1,0,&fixed);
        if(!rc && fixed==(void *)P007_BASE){
            uint32_t marker=0xc0de0000u|((uint32_t)getpid()&0xffff);((volatile uint32_t *)fixed)[0]=marker;
            state->helper_marker=((volatile uint32_t *)fixed)[0];state->helper_fixed_address=P007_BASE;
            state->helper_fixed_ok=state->helper_marker==marker;
        }
        note("fixed_map_rc",rc);
    }
    note("fixed_ok",state->helper_fixed_ok);
    /* the title's socket, through the same adapter Wine uses */
    state->helper_ipc_stage=1;int sock=socket(AF_UNIX,SOCK_STREAM,0);
    struct {uint8_t length,family;char path[104];} address;memset(&address,0,sizeof(address));
    snprintf(path,sizeof(path),"%s/ipc.sock",directory);size_t length=strlen(path);
    memcpy(address.path,path,length);address.family=AF_UNIX;address.length=(uint8_t)(2+length+1);
    state->helper_ipc_stage=2;rc=-1;
    for(unsigned n=0;sock>=0 && n<100;n++){rc=connect(sock,(struct sockaddr *)&address,address.length);if(!rc)break;sceKernelUsleep(20000);}
    if(rc){state->helper_ipc_error=-errno;note("connect_failed",errno);goto heartbeat;}
    state->helper_connected=1;state->helper_ipc_stage=3;
    char byte=0;struct iovec iov={&byte,1};
    union {struct cmsghdr header;char space[CMSG_SPACE(sizeof(int))*2];} control;memset(&control,0,sizeof(control));
    struct msghdr message;memset(&message,0,sizeof(message));message.msg_iov=&iov;message.msg_iovlen=1;
    message.msg_control=control.space;message.msg_controllen=sizeof(control.space);
    ssize_t got=pw_wine_recvmsg(sock,&message,0);struct cmsghdr *header=CMSG_FIRSTHDR(&message);
    if(got!=1 || byte!='T' || !header || header->cmsg_type!=SCM_RIGHTS){state->helper_ipc_error=-1;note("receive_failed",got<0?errno:got);goto heartbeat;}
    int theirs;memcpy(&theirs,CMSG_DATA(header),sizeof(int));
    uint64_t content[2]={0,0};lseek(theirs,0,SEEK_SET);
    state->helper_got_fd=read(theirs,content,sizeof(content))==(ssize_t)sizeof(content) && content[0]==request.token[0] &&
                         content[1]==UINT64_C(0x214446454c544954);
    close(theirs);note("received_fd_content_ok",state->helper_got_fd);
    state->helper_ipc_stage=4;snprintf(path,sizeof(path),"%s/helper-file.bin",directory);
    int own=open(path,O_RDWR|O_CREAT|O_TRUNC,0666);
    content[0]=request.token[1];content[1]=UINT64_C(0x44465245504c4548);
    if(own<0 || write(own,content,sizeof(content))!=(ssize_t)sizeof(content)){state->helper_ipc_error=-errno;goto heartbeat;}
    fsync(own);lseek(own,0,SEEK_SET);
    byte='H';memset(&control,0,sizeof(control));memset(&message,0,sizeof(message));
    message.msg_iov=&iov;message.msg_iovlen=1;message.msg_control=control.space;message.msg_controllen=CMSG_SPACE(sizeof(int));
    header=CMSG_FIRSTHDR(&message);header->cmsg_level=SOL_SOCKET;header->cmsg_type=SCM_RIGHTS;header->cmsg_len=CMSG_LEN(sizeof(int));
    memcpy(CMSG_DATA(header),&own,sizeof(int));
    state->helper_sent_fd=pw_wine_sendmsg(sock,&message,0)==1;note("sent_fd",state->helper_sent_fd);
    state->helper_ipc_stage=5;
heartbeat:;
    int result=84;uint32_t start=__atomic_load_n(&state->observer_tick,__ATOMIC_ACQUIRE);
    for(unsigned n=0;n<250;n++){
        __atomic_add_fetch(&state->helper_tick,1,__ATOMIC_RELEASE);
        if(__atomic_load_n(&state->observer_tick,__ATOMIC_ACQUIRE)>=start+5 && __atomic_load_n(&state->observer_seen_child,__ATOMIC_ACQUIRE) &&
           n>=10 && (!state->helper_sent_fd || __atomic_load_n(&state->observer_got_fd,__ATOMIC_ACQUIRE))){
            state->helper_parent_progress=1;result=42;break;
        }
        sceKernelUsleep(20000);
    }
    __atomic_store_n(&state->helper_done,(uint32_t)result,__ATOMIC_RELEASE);
    note("child_exit",result);fclose(logfile);
    return result;
}
