/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* P007 observer (the title): asks the resident loader for the helper (as P005 did), listens on an AF_UNIX
 * socket in the run directory, exchanges a descriptor with the helper in each direction through the
 * production adapter (pw_wine_sendmsg/pw_wine_recvmsg), and times how long the helper's end takes to show
 * as the socket's end. It also inventories its own span at 0x400000. No spawn, privilege or Wine call. */
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <unistd.h>
#include <orbis/libkernel.h>
#include <orbis/_types/net.h>
#include "hw_text.h"
/* P009 (-DP009): the same observer asking the loader for an OpenOrbis SELF child through file:// */
#ifdef P009
#ifdef P012
#define PROBE_NAME "P012"
#define PROBE_DIR "/data/orbisdesk/process-p012"
#else
#define PROBE_NAME "P009"
#define PROBE_DIR "/data/orbisdesk/process-p009"
#endif
#define P005_REQUEST_PATH PROBE_DIR "/request.bin"
#define P007_RUN_PREFIX PROBE_DIR "/run-"
#elif defined(P013)
/* P013: a dynamically-linked ELF child via elfldr's ELF path (not a SELF); it runs at the real root with
 * libc/libkernel resolved by Sony's linker. Same ELF send as P007, its own run directory. */
#define PROBE_NAME "P013"
#define PROBE_DIR "/data/orbisdesk/process-p013"
#define P005_REQUEST_PATH PROBE_DIR "/request.bin"
#define P007_RUN_PREFIX PROBE_DIR "/run-"
#else
#define PROBE_NAME "P007"
#define PROBE_DIR "/data/orbisdesk/process-p007"
#endif
#include "process_p007_protocol.h"
enum {W=1280,H=720};
int pw_trace_level=0;
int pw_wine_present(const void *,unsigned,unsigned,unsigned);
ssize_t pw_wine_sendmsg(int,const struct msghdr *,int);
ssize_t pw_wine_recvmsg(int,struct msghdr *,int);
static uint32_t *pixels;static FILE *logfile;static char directory[160];
static struct p007_state *state;static int worker_done,transport_result=-1,ipc_done;
static int title_occupied=-1;static long eof_ms=-1;
static pthread_mutex_t lock=PTHREAD_MUTEX_INITIALIZER;
typedef struct {uint32_t events,pad;uint64_t ident,data;} NetEvent;
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
extern int sceNetEpollControl(int,int,int,NetEvent *);
extern int sceNetEpollWait(int,NetEvent *,int,int);
extern int sceNetEpollDestroy(int);
extern int *sceNetErrnoLoc(void);
static int net_error(void){int e=*sceNetErrnoLoc();return e?-e:-5;}
static void note(const char *event,long value)
{
    pthread_mutex_lock(&lock);
    if(logfile){fprintf(logfile,"{\"build\":\"" PROBE_NAME "\",\"side\":\"title\",\"event\":\"%s\",\"value\":%ld}\n",event,value);fflush(logfile);fsync(fileno(logfile));}
    pthread_mutex_unlock(&lock);
}
static void note_region(const OrbisKernelVirtualQueryInfo *info)
{
    char name[33];for(unsigned i=0;i<32;i++){char c=info->name[i];name[i]=(c>=32 && c<127 && c!='"' && c!='\\')?c:(c?'?':0);}name[32]=0;
    pthread_mutex_lock(&lock);
    if(logfile){fprintf(logfile,"{\"build\":\"" PROBE_NAME "\",\"side\":\"title\",\"event\":\"region\",\"start\":\"%p\",\"end\":\"%p\",\"name\":\"%s\"}\n",
                        info->unk01,info->unk02,name);fflush(logfile);}
    pthread_mutex_unlock(&lock);
}
static void line(int y,const char *text,uint32_t color){hw_text(pixels,W,H,40,y,text,color,3);}
static long now_ms(void){return (long)(sceKernelGetProcessTime()/1000);}
static int wait_socket(int fd,int events,int milliseconds)
{
    int epoll=sceNetEpollCreate("p007-wait",0);if(epoll<0)return net_error();
    NetEvent item={events==4?2u:1u,0,(uint64_t)fd,0};
    int result=sceNetEpollControl(epoll,1,fd,&item);
    if(!result)result=sceNetEpollWait(epoll,&item,1,milliseconds*1000);
    int error=result<0?net_error():result?0:-60;sceNetEpollDestroy(epoll);return error;
}
#ifdef P012
#include "process_loader_identity.h"
#endif
#ifdef P009
/* P009's SELF: an app ("fake" program type) run by the P010 loader inside this title's sandbox root, where
 * /app0 is this package (with sce_module) and /data is the same. On the console an app SELF at the loader's
 * real root stopped in Sysmodule (no /app0/sce_module/libSceFios2.prx); system_exec and npdrm_exec SELFs
 * got ENOEXEC. */
#define PROBE_SANDBOX "/mnt/sandbox/ORBP00001_000"
static const char *const variants[]={"sandbox"};
static int copy_child(const char *variant)
{
    char from[96],to[128];snprintf(from,sizeof(from),"/app0/process-child.self");
    snprintf(to,sizeof(to),PROBE_DIR "/child-%s.self",variant);
    /* static: this runs on the transfer thread, whose stack is small (P009 v01.08 stopped here) */
    static char copy[65536];FILE *in=fopen(from,"rb"),*out=fopen(to,"wb");size_t got;long copied=0;
    if(!in || !out){if(in)fclose(in);if(out)fclose(out);return -1;}
    while((got=fread(copy,1,sizeof(copy),in))>0){if(fwrite(copy,1,got,out)!=got){fclose(in);fclose(out);return -1;}copied+=(long)got;}
    fclose(in);fflush(out);fsync(fileno(out));fclose(out);chmod(to,0755);return copied>0?0:-1;
}
#endif
/* P005's transfer of the packaged helper (P009: a file:// request for one SELF variant) to the resident
 * loader on 127.0.0.1:9021; the stream it keeps is the child's stdout */
static void transfer(const char *variant)
{
    (void)variant;
#ifdef P012
    if(!p012_verify_loader())return;
#endif
    long sock=sceNetSocket("p007-loader",2,1,0);FILE *elf=NULL,*stream=NULL;
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
    unsigned char buf[4096];size_t bytes;unsigned total=0;
#ifdef P009
    {
        /* the loader reads the SELF from /data and execve()s it in a child it first moves into THIS title's
         * sandbox (P010: it copies our rootdir/jaildir/prison by our pid, so the child's /app0 is our package
         * with sce_module); argv after the two --orbisdesk- options is the child's own (run directory, variant) */
        char request[600];int length=snprintf(request,sizeof(request),"file://" PROBE_DIR "/child-%s.self?args="
                                              "--orbisdesk-pid=%d --orbisdesk-self=" PROBE_DIR "/child-%s.self %s %s\n",
                                              variant,(int)getpid(),variant,directory,variant);
        for(int offset=0;offset<length;){
            rc=wait_socket((int)sock,4,1000);if(rc){note("loader_send_wait_failed",rc);goto done;}
            long sent=sceNetSend((int)sock,request+offset,(size_t)(length-offset),0x20000);
            if(sent<=0){note("loader_send_failed",sent);goto done;}offset+=(int)sent;
        }
        total=(unsigned)length;(void)bytes;
    }
#else
    elf=fopen("/app0/process-helper.elf","rb");if(!elf){note("helper_open_failed",errno);goto done;}
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
#endif
    note("helper_bytes_sent",total);sceNetShutdown((int)sock,1);
    char path[224];snprintf(path,sizeof(path),"%s/loader-stream%s%s.log",directory,variant?"-":"",variant?variant:"");stream=fopen(path,"wb");
    transport_result=0;
    for(unsigned n=0;n<40;n++){
        rc=wait_socket((int)sock,1,200);if(rc)continue;
        rc=sceNetRecv((int)sock,buf,sizeof(buf),0);if(rc<0)rc=net_error();
        if(!rc){note("loader_stream_eof",0);break;}
        if(rc<0){if(rc==-35)continue;note("loader_stream_error",rc);break;}
        if(stream){fwrite(buf,1,(size_t)rc,stream);fflush(stream);}
    }
done:
    if(stream){fsync(fileno(stream));fclose(stream);}if(elf)fclose(elf);
    if(sock>=0)sceNetSocketClose((int)sock);
}
static void *send_helper(void *unused)
{
    (void)unused;
    int initialized=sceNetInit();if(initialized<0)note("net_init_failed",initialized);
    else{
#ifdef P009
        for(unsigned i=0;i<sizeof(variants)/sizeof(*variants);i++){
            if(copy_child(variants[i])){note("child_copy_failed",(long)i);continue;}
            note("variant_attempt",(long)i);transfer(variants[i]);
            if(__atomic_load_n(&state->helper_pid,__ATOMIC_ACQUIRE)){note("variant_started",(long)i);break;}
            note("variant_not_started",(long)i);
        }
#else
        transfer(NULL);
#endif
    }
    __atomic_store_n(&worker_done,1,__ATOMIC_RELEASE);return NULL;
}
/* the AF_UNIX side: accept, send a descriptor, receive one, then wait for the helper's end */
static int listener=-1;
static void *serve_ipc(void *unused)
{
    (void)unused;
    int peer=accept(listener,NULL,NULL);
    if(peer<0){note("accept_failed",errno);goto out;}
    note("accepted",peer);
    char path[224];snprintf(path,sizeof(path),"%s/title-file.bin",directory);
    int file=open(path,O_RDWR|O_CREAT|O_TRUNC,0666);
    uint64_t content[2]={state->token[0],UINT64_C(0x214446454c544954)};  /* "TITLEFD!" */
    if(file<0 || write(file,content,sizeof(content))!=(ssize_t)sizeof(content)){note("title_file_failed",errno);goto close_peer;}
    fsync(file);lseek(file,0,SEEK_SET);
    char byte='T';struct iovec iov={&byte,1};
    union {struct cmsghdr header;char space[CMSG_SPACE(sizeof(int))*2];} control;memset(&control,0,sizeof(control));
    struct msghdr message;memset(&message,0,sizeof(message));message.msg_iov=&iov;message.msg_iovlen=1;
    message.msg_control=control.space;message.msg_controllen=CMSG_SPACE(sizeof(int));
    struct cmsghdr *header=CMSG_FIRSTHDR(&message);header->cmsg_level=SOL_SOCKET;header->cmsg_type=SCM_RIGHTS;
    header->cmsg_len=CMSG_LEN(sizeof(int));memcpy(CMSG_DATA(header),&file,sizeof(int));
    ssize_t sent=pw_wine_sendmsg(peer,&message,0);note("title_sent_fd",sent==1);
    if(sent!=1){note("title_send_errno",errno);goto close_file;}
    memset(&control,0,sizeof(control));memset(&message,0,sizeof(message));byte=0;
    message.msg_iov=&iov;message.msg_iovlen=1;message.msg_control=control.space;message.msg_controllen=sizeof(control.space);
    ssize_t got=pw_wine_recvmsg(peer,&message,0);
    header=CMSG_FIRSTHDR(&message);
    if(got!=1 || byte!='H' || !header || header->cmsg_level!=SOL_SOCKET || header->cmsg_type!=SCM_RIGHTS){
        note("title_receive_failed",got<0?errno:got);goto close_file;
    }
    int theirs;memcpy(&theirs,CMSG_DATA(header),sizeof(int));note("title_received_fd",theirs);
    uint64_t back[2]={0,0};lseek(theirs,0,SEEK_SET);ssize_t read_bytes=read(theirs,back,sizeof(back));close(theirs);
    int ok=read_bytes==(ssize_t)sizeof(back) && back[0]==state->token[1] && back[1]==UINT64_C(0x44465245504c4548);
    note("title_received_fd_content_ok",ok);
    __atomic_store_n(&state->observer_got_fd,(uint32_t)ok,__ATOMIC_RELEASE);
    /* the helper's end: read returns 0 when its process (and so its socket) is gone */
    for(;;){
        char sink;ssize_t r=read(peer,&sink,1);
        if(r==0){
            long helper_end=now_ms();
            uint32_t done=__atomic_load_n(&state->helper_done,__ATOMIC_ACQUIRE);
            note("peer_eof_after_helper_done",(long)done);eof_ms=helper_end;break;
        }
        if(r<0){note("peer_read_error",errno);break;}
    }
close_file:
    close(file);
close_peer:
    close(peer);
out:
    __atomic_store_n(&ipc_done,1,__ATOMIC_RELEASE);return NULL;
}
static int prepare(void)
{
    mkdir("/data/orbisdesk",0755);mkdir(PROBE_DIR,0777);chmod(PROBE_DIR,0777);

    for(unsigned n=1;n<10000;n++){
        snprintf(directory,sizeof(directory),P007_RUN_PREFIX "%04u",n);
        if(!mkdir(directory,0777))break;if(errno!=EEXIST)return -1;
        if(n==9999)return -1;
    }
    chmod(directory,0777);
    char path[224];snprintf(path,sizeof(path),"%s/report.jsonl",directory);logfile=fopen(path,"w");if(!logfile)return -1;
    snprintf(path,sizeof(path),"%s/state.bin",directory);int fd=open(path,O_RDWR|O_CREAT|O_EXCL,0666);if(fd<0)return -1;
    fchmod(fd,0666);int rc=sceKernelFtruncate(fd,P005_PAGE);void *view=NULL;
    if(!rc)rc=sceKernelMmap(NULL,P005_PAGE,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0,&view);close(fd);if(rc)return -1;
    state=view;memset(state,0,P005_PAGE);state->magic=P007_MAGIC;state->observer_pid=(uint32_t)getpid();
    int random=open("/dev/urandom",O_RDONLY);if(random<0)return -1;
    ssize_t got=read(random,state->token,sizeof(state->token));close(random);if(got!=sizeof(state->token))return -1;
    /* the socket first, so a helper that connects early finds it */
    snprintf(path,sizeof(path),"%s/ipc.sock",directory);
    /* a listener that cannot be made is a result (the channel is not verified), not a setup failure:
     * the fixed base is still tested (the fork emulator answers bind with EAFNOSUPPORT) */
    listener=socket(AF_UNIX,SOCK_STREAM,0);
    if(listener<0)note("unix_socket_failed",errno);
    else{
        /* the kernel's (FreeBSD) sockaddr_un: sun_len, sun_family, 104 path bytes. The SDK's sys/un.h has
         * musl's layout (no sun_len, 108 bytes), which P007's first console run got EINVAL for. */
        struct {uint8_t length,family;char path[104];} address;memset(&address,0,sizeof(address));
        size_t length=strlen(path);if(length>=sizeof(address.path)){note("unix_path_too_long",(long)length);return -1;}
        memcpy(address.path,path,length);address.family=AF_UNIX;address.length=(uint8_t)(2+length+1);
        if(bind(listener,(struct sockaddr *)&address,address.length)){note("unix_bind_failed",errno);close(listener);listener=-1;}
        else{
            chmod(path,0777);
            if(listen(listener,2)){note("unix_listen_failed",errno);close(listener);listener=-1;}
            else note("unix_listening",1);
        }
    }
    struct p007_request request;memset(&request,0,sizeof(request));request.magic=P007_MAGIC;request.flags=P007_FLAG_UNMAP_HOST;
    memcpy(request.token,state->token,sizeof(request.token));request.observer_pid=state->observer_pid;
    snprintf(request.directory,sizeof(request.directory),"%s",directory);
    const char *temp=PROBE_DIR "/request.tmp";fd=open(temp,O_WRONLY|O_CREAT|O_TRUNC,0644);if(fd<0)return -1;
    ssize_t written=write(fd,&request,sizeof(request));fsync(fd);close(fd);
    if(written!=sizeof(request) || rename(temp,P005_REQUEST_PATH))return -1;
#ifdef P012
    note("candidate_revision_01_12",112);
#endif
    note("observer_started",getpid());note("native_spawn_not_called",1);
    /* the title's own span at 0x400000 (its eboot, where Wine's PE32 world cannot use it) */
    OrbisKernelVirtualQueryInfo info;memset(&info,0,sizeof(info));
    if(!sceKernelVirtualQuery((const void *)P007_BASE,1,&info,sizeof(info))){
        note_region(&info);title_occupied=(uint64_t)info.unk01<P007_BASE+P007_SPAN;
    }else title_occupied=0;
    note("title_span_occupied",title_occupied);
    return 0;
}
int main(void)
{
    pixels=calloc(W*H,4);if(!pixels)return 1;
    for(unsigned i=0;i<W*H;i++)pixels[i]=0xff102030;
    hw_text(pixels,W,H,40,30,"ORBISDESK PROCESS CHECK " PROBE_NAME,0xffffffff,4);
#ifdef P009
    line(90,"OPENORBIS SELF CHILD THROUGH THE LOADER - NO WINE",0xffb0ccff);
#else
    line(90,"CHILD FIXED BASE AND CROSS-PROCESS CHANNEL - NO WINE",0xffb0ccff);
#endif
    line(140,"CONNECTING TO LOCAL ELF LOADER 9021",0xffffcc77);pw_wine_present(pixels,W,H,W*4);
    if(prepare()){line(190,"SETUP FAILED - SEE LOG",0xffff7777);goto idle;}
    pthread_t ipc,worker;
    if(listener>=0 && pthread_create(&ipc,NULL,serve_ipc,NULL)){note("ipc_thread_failed",errno);goto finish;}
    if(listener<0)__atomic_store_n(&ipc_done,1,__ATOMIC_RELEASE);
    if(pthread_create(&worker,NULL,send_helper,NULL)){note("worker_start_failed",errno);goto finish;}
    long done_ms=-1;
    for(unsigned n=0;n<1500;n++){
        __atomic_add_fetch(&state->observer_tick,1,__ATOMIC_RELEASE);
        uint32_t pid=__atomic_load_n(&state->helper_pid,__ATOMIC_ACQUIRE);
        if(pid && pid!=state->observer_pid && __atomic_load_n(&state->helper_tick,__ATOMIC_ACQUIRE))
            __atomic_store_n(&state->observer_seen_child,1,__ATOMIC_RELEASE);
        if(done_ms<0 && __atomic_load_n(&state->helper_done,__ATOMIC_ACQUIRE))done_ms=now_ms();
        if(__atomic_load_n(&worker_done,__ATOMIC_ACQUIRE) && transport_result)break;
        if(done_ms>=0 && __atomic_load_n(&ipc_done,__ATOMIC_ACQUIRE))break;
        if(done_ms>=0 && now_ms()-done_ms>5000)break;
        if(!(n%25))pw_wine_present(pixels,W,H,W*4);sceKernelUsleep(20000);
    }
    uint32_t done=__atomic_load_n(&state->helper_done,__ATOMIC_ACQUIRE);
    int identity=state->helper_pid && state->helper_pid!=state->observer_pid;
    int coexistence=identity && state->helper_parent_progress && done==42;
    int child_fixed=state->helper_fixed_ok && state->helper_fixed_address==P007_BASE;
    int fd_in=state->helper_got_fd,fd_out=__atomic_load_n(&state->observer_got_fd,__ATOMIC_ACQUIRE);
    int end_seen=eof_ms>=0 && done_ms>=0;
    note("helper_pid",state->helper_pid);note("helper_native_ppid",state->helper_ppid);
    note("helper_regions",state->helper_region_count);note("helper_vq_status",state->helper_vq_status);
    note("helper_span_free_before",state->helper_span_free_before);note("helper_unmapped",state->helper_unmapped);
    note("helper_occupant_start",(long)state->helper_occupant_start);
    note("child_fixed_base_passed",child_fixed);note("helper_ipc_stage",state->helper_ipc_stage);
    note("helper_ipc_error",state->helper_ipc_error);note("fd_title_to_helper",fd_in);note("fd_helper_to_title",fd_out);
    note("helper_end_seen_ms",end_seen?eof_ms-done_ms:-1);note("coexistence_handshake_passed",coexistence);
    char text[96];
    line(190,transport_result?"LOADER UNAVAILABLE OR TRANSFER FAILED":"HELPER SENT",transport_result?0xffffcc77:0xffb0ccff);
    line(240,coexistence?"BOTH PROCESSES ACTIVE: PASS":"BOTH PROCESSES ACTIVE: NOT VERIFIED",coexistence?0xff88ee99:0xffffcc77);
    snprintf(text,sizeof(text),"TITLE 0x400000: %s",title_occupied>0?"OCCUPIED (EXPECTED)":title_occupied==0?"FREE":"UNKNOWN");
    line(290,text,0xffb0ccff);
    snprintf(text,sizeof(text),"CHILD FIXED BASE 0x400000: %s (FREED %u)",child_fixed?"PASS":"NOT VERIFIED",state->helper_unmapped);
    line(340,text,child_fixed?0xff88ee99:0xffffcc77);
    line(390,fd_in?"DESCRIPTOR TITLE TO CHILD: PASS":"DESCRIPTOR TITLE TO CHILD: NOT VERIFIED",fd_in?0xff88ee99:0xffffcc77);
    line(440,fd_out?"DESCRIPTOR CHILD TO TITLE: PASS":"DESCRIPTOR CHILD TO TITLE: NOT VERIFIED",fd_out?0xff88ee99:0xffffcc77);
    line(490,end_seen?"CHILD END SEEN BY TITLE: PASS":"CHILD END SEEN BY TITLE: NOT VERIFIED",end_seen?0xff88ee99:0xffffcc77);
finish:
    note("panel_ready",1);
idle:
    line(560,"SEND PHOTO THEN CLOSE FROM PS4 MENU",0xffffffff);
    hw_text(pixels,W,H,40,610,directory,0xffb0ccff,2);
    for(;;){pw_wine_present(pixels,W,H,W*4);sceKernelUsleep(1000000);}
}
