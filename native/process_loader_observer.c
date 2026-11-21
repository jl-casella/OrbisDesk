/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#include <orbis/libkernel.h>
#include <orbis/_types/net.h>
#include "hw_text.h"
#include "process_loader_protocol.h"
enum {W=1280,H=720};
int pw_trace_level=0;
int pw_wine_present(const void *,unsigned,unsigned,unsigned);
static uint32_t *pixels;static FILE *logfile;static char directory[160];
static struct p005_state *state;static void *low;
static int worker_done,transport_result=-1;static pthread_mutex_t lock=PTHREAD_MUTEX_INITIALIZER;
typedef struct {uint32_t events,pad;uint64_t ident,data;} P005NetEvent;
/* Net.h in this SDK has void placeholders for errno/epoll; use the established adapter ABI. */
extern int sceNetInit(void);
extern int sceNetSocket(const char *,int,int,int);
extern int sceNetSetsockopt(int,int,int,const void *,unsigned);
extern int sceNetGetsockopt(int,int,int,void *,unsigned *);
extern int sceNetConnect(int,const OrbisNetSockaddr *,unsigned);
extern int sceNetSend(int,const void *,size_t,int);
extern int sceNetRecv(int,void *,size_t,int);
extern int sceNetShutdown(int,int);
extern int sceNetSocketClose(int);
extern int sceNetEpollCreate(const char *,int);
extern int sceNetEpollControl(int,int,int,P005NetEvent *);
extern int sceNetEpollWait(int,P005NetEvent *,int,int);
extern int sceNetEpollDestroy(int);
extern int *sceNetErrnoLoc(void);
static int net_error(void){int e=*sceNetErrnoLoc();return e?-e:-5;}
static void note(const char *event,long value)
{
    pthread_mutex_lock(&lock);
    if(logfile){fprintf(logfile,"{\"build\":\"P005\",\"event\":\"%s\",\"value\":%ld}\n",event,value);fflush(logfile);fsync(fileno(logfile));}
    pthread_mutex_unlock(&lock);
}
static void line(int y,const char *text,uint32_t color){hw_text(pixels,W,H,40,y,text,color,3);}
static int wait_socket(int fd,int events,int milliseconds)
{
    int epoll=sceNetEpollCreate("p005-wait",0);if(epoll<0)return net_error();
    P005NetEvent item={events==4?2u:1u,0,(uint64_t)fd,0};
    int result=sceNetEpollControl(epoll,1,fd,&item);
    if(!result)result=sceNetEpollWait(epoll,&item,1,milliseconds*1000);
    int error=result<0?net_error():result?0:-60;sceNetEpollDestroy(epoll);return error;
}
static void *send_helper(void *unused)
{
    (void)unused;
    int initialized=sceNetInit();if(initialized<0){note("net_init_failed",initialized);goto no_socket;}
    long sock=sceNetSocket("p005-loader",2,1,0);FILE *elf=NULL,*stream=NULL;
    if(sock<0){note("loader_socket_failed",sock);goto done;}
    int one=1;if(sceNetSetsockopt((int)sock,0xffff,0x1200,&one,sizeof(one))<0){note("loader_nonblock_failed",net_error());goto done;}
    struct {uint8_t len,family;uint16_t port;uint8_t ip[4],zero[8];} address={16,2,0,{127,0,0,1},{0}};
    address.port=(uint16_t)((9021>>8)|((9021&255)<<8));
    long rc=sceNetConnect((int)sock,(const OrbisNetSockaddr *)&address,sizeof(address));if(rc<0)rc=net_error();
    if(rc<0 && rc!=-36){note("loader_connect_failed",rc);goto done;}
    if(rc<0){
        rc=wait_socket((int)sock,4,2000);int error=0;unsigned bytes=sizeof(error);
        if(!rc)rc=sceNetGetsockopt((int)sock,0xffff,0x1007,&error,&bytes);
        if(rc || error){note("loader_unavailable",rc?rc:-error);goto done;}
    }
    note("loader_connected",9021);
    elf=fopen("/app0/process-helper.elf","rb");if(!elf){note("helper_open_failed",errno);goto done;}
    unsigned char buf[4096];size_t bytes;unsigned total=0;
    /* Limit both payload size and total send attempts; no privileged API is called by this title. */
    while((bytes=fread(buf,1,sizeof(buf),elf))){
        if(total+bytes>262144){note("helper_too_large",total+bytes);goto done;}
        for(size_t offset=0;offset<bytes;){
            rc=wait_socket((int)sock,4,1000);if(rc){note("loader_send_wait_failed",rc);goto done;}
            long sent=sceNetSend((int)sock,buf+offset,bytes-offset,0x20000);
            if(sent<=0){note("loader_send_failed",sent);goto done;}offset+=(size_t)sent;
        }
        total+=(unsigned)bytes;
    }
    if(ferror(elf)){note("helper_read_failed",errno);goto done;}
    note("helper_bytes_sent",total);sceNetShutdown((int)sock,1);
    char path[224];snprintf(path,sizeof(path),"%s/loader-stream.log",directory);stream=fopen(path,"wb");
    transport_result=0;
    for(unsigned n=0;n<25;n++){
        rc=wait_socket((int)sock,1,200);if(rc)continue;
        rc=sceNetRecv((int)sock,buf,sizeof(buf),0);if(rc<0)rc=net_error();
        if(!rc){note("loader_stream_eof",0);break;}
        if(rc<0){if(rc==-35)continue;note("loader_stream_error",rc);break;}
        if(stream){fwrite(buf,1,(size_t)rc,stream);fflush(stream);}
    }
done:
    if(stream){fsync(fileno(stream));fclose(stream);}if(elf)fclose(elf);
    if(sock>=0)sceNetSocketClose((int)sock);
no_socket:
    __atomic_store_n(&worker_done,1,__ATOMIC_RELEASE);return NULL;
}
static int prepare(void)
{
    mkdir("/data/orbisdesk",0755);mkdir("/data/orbisdesk/process-p005",0755);
    for(unsigned n=1;n<10000;n++){
        snprintf(directory,sizeof(directory),"/data/orbisdesk/process-p005/run-%04u",n);
        if(!mkdir(directory,0777))break;if(errno!=EEXIST)return -1;
        if(n==9999)return -1;
    }
    chmod(directory,0777);
    char path[224];snprintf(path,sizeof(path),"%s/report.jsonl",directory);logfile=fopen(path,"w");if(!logfile)return -1;
    snprintf(path,sizeof(path),"%s/state.bin",directory);int fd=open(path,O_RDWR|O_CREAT|O_EXCL,0666);if(fd<0)return -1;
    fchmod(fd,0666);int rc=sceKernelFtruncate(fd,P005_PAGE);void *view=NULL;
    if(!rc)rc=sceKernelMmap(NULL,P005_PAGE,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0,&view);close(fd);if(rc)return -1;
    state=view;memset(state,0,P005_PAGE);state->magic=P005_MAGIC;state->observer_pid=(uint32_t)getpid();
    /* The token rejects stale helpers; it is not an authentication boundary for privileged local code. */
    int random=open("/dev/urandom",O_RDONLY);if(random<0)return -1;
    ssize_t got=read(random,state->token,sizeof(state->token));close(random);if(got!=sizeof(state->token))return -1;
    struct p005_request request;memset(&request,0,sizeof(request));request.magic=P005_MAGIC;
    memcpy(request.token,state->token,sizeof(request.token));request.observer_pid=state->observer_pid;
    snprintf(request.directory,sizeof(request.directory),"%s",directory);
    const char *temp="/data/orbisdesk/process-p005/request.tmp";fd=open(temp,O_WRONLY|O_CREAT|O_TRUNC,0644);if(fd<0)return -1;
    ssize_t written=write(fd,&request,sizeof(request));fsync(fd);close(fd);
    if(written!=sizeof(request) || rename(temp,P005_REQUEST_PATH))return -1;
    note("observer_started",getpid());note("native_spawn_not_called",1);note("bootstrap_not_executed",1);
    void *mapping=NULL;rc=sceKernelMmap((void *)0x400000,P005_PAGE,3,MAP_PRIVATE|MAP_ANON,-1,0,&mapping);
    if(!rc){low=mapping;*(volatile uint32_t *)low=0x11223344;}note("observer_low_address",(long)low);
    return 0;
}
int main(void)
{
    pixels=calloc(W*H,4);if(!pixels)return 1;
    for(unsigned i=0;i<W*H;i++)pixels[i]=0xff102030;
    hw_text(pixels,W,H,40,30,"ORBISDESK PROCESS CHECK P005",0xffffffff,4);
    line(90,"EXTERNAL LOADER COEXISTENCE - NO WINE",0xffb0ccff);
    line(140,"CONNECTING TO LOCAL ELF LOADER 9021",0xffffcc77);pw_wine_present(pixels,W,H,W*4);
    if(prepare()){line(210,"SETUP FAILED - SEE LOG",0xffff7777);goto idle;}
    pthread_t worker;int rc=pthread_create(&worker,NULL,send_helper,NULL);
    if(rc){note("worker_start_failed",rc);goto finish;}
    for(unsigned n=0;n<600;n++){
        __atomic_add_fetch(&state->observer_tick,1,__ATOMIC_RELEASE);
        uint32_t pid=__atomic_load_n(&state->helper_pid,__ATOMIC_ACQUIRE);
        if(pid && pid!=state->observer_pid && __atomic_load_n(&state->helper_tick,__ATOMIC_ACQUIRE))
            __atomic_store_n(&state->observer_seen_child,1,__ATOMIC_RELEASE);
        if(__atomic_load_n(&worker_done,__ATOMIC_ACQUIRE) && (transport_result || __atomic_load_n(&state->helper_done,__ATOMIC_ACQUIRE)))break;
        if(!(n%25))pw_wine_present(pixels,W,H,W*4);sceKernelUsleep(20000);
    }
    if(__atomic_load_n(&worker_done,__ATOMIC_ACQUIRE))pthread_join(worker,NULL);
    uint32_t done=__atomic_load_n(&state->helper_done,__ATOMIC_ACQUIRE);
    int identity=state->helper_pid && state->helper_pid!=state->observer_pid;
    int progress=state->helper_parent_progress && state->observer_seen_child && state->helper_tick>=10;
    int coexistence=identity && progress && done==42;
    note("helper_pid",state->helper_pid);note("helper_native_ppid",state->helper_ppid);
    note("helper_tick",state->helper_tick);note("helper_exit_self_report",done);
    note("coexistence_handshake_passed",coexistence);note("native_exit_reaped",0);
    line(210,transport_result?"LOADER UNAVAILABLE OR TRANSFER FAILED":"HELPER SENT - CHECKING HANDSHAKE",transport_result?0xffffcc77:0xffb0ccff);
    line(260,identity?"DISTINCT NATIVE PID: PASS":"DISTINCT NATIVE PID: NOT VERIFIED",identity?0xff88ee99:0xffffcc77);
    line(310,progress?"BOTH PROCESSES ACTIVE: PASS":"BOTH PROCESSES ACTIVE: NOT VERIFIED",progress?0xff88ee99:0xffffcc77);
    line(360,coexistence?"COEXISTENCE HANDSHAKE: PASS":"COEXISTENCE HANDSHAKE: NOT VERIFIED",coexistence?0xff88ee99:0xffffcc77);
    int low_ok=low==(void *)0x400000 && state->helper_low_ok && state->helper_low_value==0x55667788 && *(volatile uint32_t *)low==0x11223344;
    note("low_address_isolation",low_ok);
    line(410,low_ok?"LOW ADDRESS ISOLATION: PASS":"LOW ADDRESS ISOLATION: INCONCLUSIVE",low_ok?0xff88ee99:0xffffcc77);
    line(460,"NATIVE EXIT STATUS: NOT REAPED BY TITLE",0xffffcc77);
finish:
    note("panel_ready",1);
idle:
    line(530,"SEND PHOTO THEN CLOSE FROM PS4 MENU",0xffffffff);
    hw_text(pixels,W,H,40,580,directory,0xffb0ccff,2);
    for(;;){pw_wine_present(pixels,W,H,W*4);sceKernelUsleep(1000000);}
}
