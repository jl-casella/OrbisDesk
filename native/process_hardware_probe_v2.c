/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <sys/wait.h>
#include <unistd.h>
#include <orbis/libkernel.h>
#include "hw_text.h"
#include "pw_wine_net.h"
#include "process_probe_shared.h"

#ifndef PROBE_BUILD
#define PROBE_BUILD "P002"
#define PROBE_TAG "p002"
#endif
#ifndef PROBE_INSPECT_ONLY
#define PROBE_INSPECT_ONLY 0
#endif

enum {W=1280,H=720};
int pw_trace_level=0;
static uint32_t *pixels;
static FILE *log_file;
static pthread_mutex_t log_lock=PTHREAD_MUTEX_INITIALIZER;
static char run_dir[160];
static unsigned row=155;
static int active_case=-1,worker_done,spawn_result=-1;
static int ipc_done,ipc_results[5];
static struct p002_shared *state;
static void *parent_low;
typedef int (*SpawnFn)(pid_t *,const char *,const void *,const void *,char *const *,char *const *);
typedef pid_t (*WaitFn)(pid_t,int *,int);
static SpawnFn spawn_fn;
static WaitFn wait_fn;
int pw_wine_present(const void *,unsigned int,unsigned int,unsigned int);

static void note(const char *event,int rc,int error,long detail)
{
    pthread_mutex_lock(&log_lock);
    if(log_file){fprintf(log_file,"{\"build\":\"" PROBE_BUILD "\",\"event\":\"%s\",\"case\":%d,\"rc\":%d,\"errno\":%d,\"detail\":%ld}\n",event,active_case,rc,error,detail);fflush(log_file);fsync(fileno(log_file));}
    pthread_mutex_unlock(&log_lock);
}
void p002_net_trace(const char *call,const char *stage,int error,int flags,unsigned control_bytes)
{
    pthread_mutex_lock(&log_lock);
    if(log_file){fprintf(log_file,"{\"event\":\"net_failure\",\"case\":%d,\"call\":\"%s\",\"stage\":\"%s\",\"errno\":%d,\"wire_flags\":%d,\"wire_control_bytes\":%u}\n",active_case,call,stage,error,flags,control_bytes);fflush(log_file);fsync(fileno(log_file));}
    pthread_mutex_unlock(&log_lock);
}
static void screen(const char *name,const char *status,uint32_t color)
{
    char text[128];snprintf(text,sizeof(text),"%s: %s",name,status);
    hw_text(pixels,W,H,40,(int)row,text,color,3);row+=40;pw_wine_present(pixels,W,H,W*4);
}
static void *lookup(const char *name)
{
    OrbisKernelModule modules[128];size_t count=0;
    if(sceKernelGetModuleList(modules,128,&count) || count>128)return NULL;
    for(size_t i=0;i<count;i++){
        void *address=NULL;
        if(!sceKernelDlsym(modules[i],name,&address) && address){note(name,0,0,modules[i]);return address;}
    }
    note(name,-1,0,0);return NULL;
}
static int open_run(void)
{
    mkdir("/data/orbisdesk",0755);mkdir("/data/orbisdesk/process-" PROBE_TAG,0755);
    for(unsigned n=1;n<10000;n++){
        snprintf(run_dir,sizeof(run_dir),"/data/orbisdesk/process-" PROBE_TAG "/run-%04u",n);
        if(!mkdir(run_dir,0755)){
            char path[200];snprintf(path,sizeof(path),"%s/report.jsonl",run_dir);
            log_file=fopen(path,"w");return log_file?0:errno;
        }
        if(errno!=EEXIST)return errno;
    }
    return EEXIST;
}
#ifdef PROBE_INSPECT_CALLEES
#include "process_probe_inspect.h"
#endif
static int inspect_spawn(void)
{
    OrbisKernelModule modules[128];size_t count=0;int snapshots=0;
    if(sceKernelGetModuleList(modules,128,&count) || count>128){note("code_inventory_failed",-1,0,0);return 0;}
    for(size_t i=0;i<count;i++){
        void *address=NULL;
        if(sceKernelDlsym(modules[i],"posix_spawn",&address) || !address)continue;
        OrbisKernelModuleInfo info;memset(&info,0,sizeof(info));info.size=sizeof(info);
        if(sceKernelGetModuleInfo(modules[i],&info)){note("code_module_info_failed",-1,0,modules[i]);continue;}
        int saved=0;
        for(unsigned s=0;s<info.segmentCount && s<4;s++){
            uintptr_t begin=(uintptr_t)info.segmentInfo[s].address,at=(uintptr_t)address;
            size_t size=info.segmentInfo[s].size;
            if(!(info.segmentInfo[s].prot&PROT_READ) || at<begin || at-begin>=size)continue;
            size_t bytes=size-(at-begin);if(bytes>512)bytes=512;
            char path[240];snprintf(path,sizeof(path),"%s/posix-spawn-%u.bin",run_dir,modules[i]);
            FILE *file=fopen(path,"wb");if(!file){note("code_file_failed",-1,errno,modules[i]);break;}
            saved=fwrite(address,1,bytes,file)==bytes;fflush(file);fsync(fileno(file));fclose(file);
            pthread_mutex_lock(&log_lock);
            if(log_file){fprintf(log_file,"{\"event\":\"spawn_code_snapshot\",\"module\":%u,\"address\":\"%llx\",\"segment_address\":\"%llx\",\"segment_offset\":%llu,\"bytes\":%zu,\"saved\":%s}\n",modules[i],(unsigned long long)at,(unsigned long long)begin,(unsigned long long)(at-begin),bytes,saved?"true":"false");fflush(log_file);fsync(fileno(log_file));}
            pthread_mutex_unlock(&log_lock);break;
        }
        if(!saved)note("code_snapshot_unavailable",-1,0,modules[i]);else snapshots++;
#ifdef PROBE_INSPECT_CALLEES
        if(saved)p004_inspect(address,&info,modules,count);
#endif
    }
    return snapshots;
}
static int ipc_case(int fd,int flags,unsigned capacity,int send_flags)
{
    int pair[2],received=-1,result=0;
    if(socketpair(AF_UNIX,SOCK_STREAM,0,pair)){note("socketpair",-1,errno,0);return -1;}
    char byte='P';struct iovec vec={&byte,1};
    union {struct cmsghdr aligned;char bytes[256];} buffer;
    memset(&buffer,0,sizeof(buffer));
    struct msghdr msg;memset(&msg,0,sizeof(msg));msg.msg_iov=&vec;msg.msg_iovlen=1;
    msg.msg_control=buffer.bytes;msg.msg_controllen=CMSG_SPACE(sizeof(int));
    struct cmsghdr *header=CMSG_FIRSTHDR(&msg);header->cmsg_level=SOL_SOCKET;header->cmsg_type=SCM_RIGHTS;
    header->cmsg_len=CMSG_LEN(sizeof(int));memcpy(CMSG_DATA(header),&fd,sizeof(fd));
    note("send_flags",send_flags,0,0);
    errno=0;ssize_t sent=pw_wine_sendmsg(pair[0],&msg,send_flags);note("send",sent==1?0:-1,sent<0?errno:0,sent);
    if(sent!=1){result=-1;goto done;}
    memset(&buffer,0,sizeof(buffer));byte=0;msg.msg_controllen=capacity;msg.msg_flags=0;
    errno=0;ssize_t got=pw_wine_recvmsg(pair[1],&msg,flags);
    note("receive",got==1?0:-1,got<0?errno:0,(long)msg.msg_controllen);
    if(got!=1 || byte!='P'){result=-1;goto done;}
    header=CMSG_FIRSTHDR(&msg);
    if(header && header->cmsg_level==SOL_SOCKET && header->cmsg_type==SCM_RIGHTS && header->cmsg_len>=CMSG_LEN(sizeof(int)))
        memcpy(&received,CMSG_DATA(header),sizeof(received));
    char marker=0;
    if(received<0 || lseek(fd,0,SEEK_SET)<0 || write(fd,"D",1)!=1 || lseek(received,0,SEEK_SET)<0 ||
       read(received,&marker,1)!=1 || marker!='D')result=-1;
    note("receiver_io",result,result?errno:0,received);
done:
    if(received>=0)close(received);
    close(pair[0]);close(pair[1]);return result;
}
static void *ipc_worker(void *unused)
{
    (void)unused;
    char path[220];snprintf(path,sizeof(path),"%s/ipc.tmp",run_dir);
    int fd=open(path,O_RDWR|O_CREAT|O_EXCL,0600);
    for(int i=0;i<5;i++){
        active_case=i;unsigned capacity=(i&1)||i==4?256:CMSG_SPACE(sizeof(int));int flags=i&2?MSG_DONTWAIT:0;
        note("ipc_configuration",flags,0,capacity);
        ipc_results[i]=fd<0?-1:ipc_case(fd,flags,capacity,i==4?0:MSG_DONTWAIT|MSG_NOSIGNAL);
    }
    if(fd>=0){close(fd);unlink(path);}else note("ipc_file_failed",-1,errno,0);
    active_case=-1;__atomic_store_n(&ipc_done,1,__ATOMIC_RELEASE);return NULL;
}
static void *spawn_worker(void *unused)
{
    (void)unused;
    char *empty_env[]={NULL};
    char *missing_args[]={"/app0/p002-missing.bin",NULL};
    pid_t missing_pid=-1;
    note("negative_spawn_enter",0,0,0);
    errno=0;int rc=spawn_fn(&missing_pid,missing_args[0],NULL,NULL,missing_args,empty_env);
    note("negative_spawn_return",rc,errno,missing_pid);
    if(!rc && missing_pid>0 && missing_pid!=getpid() && wait_fn){int status=0;wait_fn(missing_pid,&status,WNOHANG);}
    char *args[]={"/app0/process-child.bin",run_dir,NULL};pid_t child=-1;
    note("spawn_enter",0,0,0);
    errno=0;rc=spawn_fn(&child,args[0],NULL,NULL,args,empty_env);
    note("spawn_return",rc,errno,child);
    spawn_result=rc?rc:-1;
    if(!rc && child>0 && child!=getpid()){
        note("spawn_distinct_pid",0,0,child);
        int status=0,reaped=0;
        for(unsigned n=0;n<250;n++){
            if(wait_fn){errno=0;pid_t result=wait_fn(child,&status,WNOHANG);if(result==child){reaped=1;break;}if(result<0){note("wait_failed",-1,errno,child);break;}}
            sceKernelUsleep(20000);
        }
        int identity=__atomic_load_n(&state->child_pid,__ATOMIC_ACQUIRE)==(uint32_t)child;
        int progress=__atomic_load_n(&state->child_seen,__ATOMIC_ACQUIRE)!=0;
        int exited=reaped && WIFEXITED(status) && WEXITSTATUS(status)==42;
        note("child_exit",reaped?0:-1,0,status);
        note("shared_child_identity",identity?0:-1,0,state->child_pid);
        note("parent_progress_observed",progress?0:-1,0,state->heartbeat);
        if(state->parent_low_ok && state->child_low_ok)
            note("low_address_isolation",parent_low && *(volatile uint32_t *)parent_low==0x11223344 && state->child_value==0x55667788?0:-1,0,0x400000);
        else note("low_address_test_inconclusive",-1,0,0x400000);
        spawn_result=identity && progress && exited?0:-1;
    }
    __atomic_store_n(&worker_done,1,__ATOMIC_RELEASE);
    return NULL;
}
int main(void)
{
    pixels=calloc(W*H,4);if(!pixels)return 1;
    for(unsigned i=0;i<W*H;i++)pixels[i]=0xff102030;
    hw_text(pixels,W,H,40,30,"ORBISDESK PROCESS CHECK " PROBE_BUILD,0xffffffff,4);
    hw_text(pixels,W,H,40,80,PROBE_INSPECT_ONLY?"IPC FIX AND SPAWN INSPECTION - NO SPAWN":"IPC VARIANTS AND NATIVE CHILD - NO WINE",0xffb0ccff,3);
    pw_wine_present(pixels,W,H,W*4);
    if(open_run()){screen("LOG","FAILED",0xffff7777);goto idle;}
    note("started",0,0,getpid());
    pthread_t ipc_thread;int ipc_rc=pthread_create(&ipc_thread,NULL,ipc_worker,NULL);
    if(ipc_rc){note("ipc_worker_failed",ipc_rc,0,0);screen("IPC","WORKER FAILED",0xffff7777);goto finish;}
    for(unsigned n=0;n<750 && !__atomic_load_n(&ipc_done,__ATOMIC_ACQUIRE);n++){
        if(!(n%25))pw_wine_present(pixels,W,H,W*4);sceKernelUsleep(20000);
    }
    if(!__atomic_load_n(&ipc_done,__ATOMIC_ACQUIRE)){screen("IPC","CALL STILL PENDING",0xffffcc77);goto idle;}
    pthread_join(ipc_thread,NULL);
    for(int i=0;i<5;i++){
        char label[64];
        if(i==4)snprintf(label,sizeof(label),"IPC 4 PRODUCTION FLAGS0");
        else snprintf(label,sizeof(label),"IPC %d %s %s",i,i&2?"NONBLOCK":"FLAGS0",i&1?"LARGE":"SMALL");
        screen(label,ipc_results[i]?"FAIL":"PASS",ipc_results[i]?0xffff7777:0xff88ee99);
    }
    if(PROBE_INSPECT_ONLY){int snapshots=inspect_spawn();screen("SPAWN","NOT CALLED",0xffffcc77);screen("CODE SNAPSHOT",snapshots?"SAVED":"NOT AVAILABLE",snapshots?0xff88ee99:0xffffcc77);note("spawn_not_called",0,0,snapshots);goto finish;}
    spawn_fn=(SpawnFn)lookup("posix_spawn");wait_fn=(WaitFn)lookup("waitpid");
    if(!spawn_fn || !wait_fn){screen("NATIVE SPAWN","API UNAVAILABLE",0xffffcc77);note("spawn_skipped",-1,0,0);goto finish;}
    char path[220];snprintf(path,sizeof(path),"%s/state.bin",run_dir);int fd=open(path,O_RDWR|O_CREAT|O_EXCL,0600);
    void *view=NULL;int rc=fd<0?-1:sceKernelFtruncate(fd,P002_PAGE);
    if(!rc)rc=sceKernelMmap(NULL,P002_PAGE,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0,&view);
    if(fd>=0)close(fd);
    if(rc){note("state_map_failed",rc,errno,0);screen("NATIVE SPAWN","STATE FAILED",0xffff7777);goto finish;}
    state=view;state->magic=P002_MAGIC;state->parent_pid=getpid();
    int low_rc=sceKernelMmap((void *)0x400000,P002_PAGE,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANON,-1,0,&parent_low);
    state->parent_low_ok=!low_rc && parent_low==(void *)0x400000;
    if(!low_rc){*(volatile uint32_t *)parent_low=0x11223344;state->parent_value=0x11223344;}
    note("parent_low_mapping",low_rc,0,state->parent_low_ok);
    pthread_t thread;rc=pthread_create(&thread,NULL,spawn_worker,NULL);
    note("spawn_worker_start",rc,0,0);
    if(rc){screen("NATIVE SPAWN","WORKER FAILED",0xffff7777);goto finish;}
    for(unsigned n=0;n<750 && !__atomic_load_n(&worker_done,__ATOMIC_ACQUIRE);n++){
        __atomic_add_fetch(&state->heartbeat,1,__ATOMIC_RELEASE);
        if(!(n%25))pw_wine_present(pixels,W,H,W*4);
        sceKernelUsleep(20000);
    }
    if(__atomic_load_n(&worker_done,__ATOMIC_ACQUIRE)){
        pthread_join(thread,NULL);screen("NATIVE CHILD",spawn_result?"FAIL - SEE LOG":"PASS",spawn_result?0xffff7777:0xff88ee99);
    }else {note("spawn_worker_timeout",-1,0,15);screen("NATIVE CHILD","CALL STILL PENDING",0xffffcc77);}
finish:
    note("panel_ready",0,0,0);
idle:
    hw_text(pixels,W,H,40,530,"SEND PHOTO THEN CLOSE FROM PS4 MENU",0xffffffff,3);
    hw_text(pixels,W,H,40,580,run_dir,0xffb0ccff,2);
    for(;;){pw_wine_present(pixels,W,H,W*4);sceKernelUsleep(1000000);}
}
