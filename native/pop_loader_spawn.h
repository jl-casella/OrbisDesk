/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Title-side (eboot) spawn of the Phase B / P014 separate process. kernelbase's PW_EXEC_SEPARATE hook writes
 * the target app path to POP_SEP_REQUEST; this watcher thread, running in the native eboot (which has the
 * network libraries), sends the bundled child ELF to the GoldHEN resident loader on 127.0.0.1:9021 (the same
 * ELF path Phase A used, with the SCHED_RR MAX loader fix). The loader spawns it as a genuine second native
 * process; the child joins the title's real wineserver (native/process_p014_child.c). sceNet is declared
 * with a void* sockaddr so no SDK net header is required; the eboot link gains -lSceNet
 * (tools/build-wine-hardware.py). Loader-dependent research substrate, not a shippable feature. */
#ifndef POP_LOADER_SPAWN_H
#define POP_LOADER_SPAWN_H
#include <errno.h>
#include <stdint.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <pthread.h>
#include <sys/stat.h>
#include <sys/socket.h>
#include <sys/un.h>
#include "pop_separate.h"

typedef struct {uint32_t events,pad;uint64_t ident,data;} PopNetEvent;
extern int sceNetInit(void);
extern int sceNetSocket(const char *,int,int,int);
extern int sceNetSetsockopt(int,int,int,const void *,unsigned);
extern int sceNetGetsockopt(int,int,int,void *,unsigned *);
extern int sceNetConnect(int,const void *,unsigned);
extern int sceNetSend(int,const void *,size_t,int);
extern int sceNetRecv(int,void *,size_t,int);
extern int sceNetShutdown(int,int);
extern int sceNetSocketClose(int);
extern int sceNetEpollCreate(const char *,int);
extern int sceNetEpollControl(int,int,int,PopNetEvent *);
extern int sceNetEpollWait(int,PopNetEvent *,int,int);
extern int sceNetEpollDestroy(int);
extern int *sceNetErrnoLoc(void);

/* 04.15: unused since the loader connection uses the kernel's sockets (pop_loader_socket) */
__attribute__((unused)) static int pop_net_error(void){int e=*sceNetErrnoLoc();return e?-e:-5;}
__attribute__((unused)) static int pop_wait_socket(int fd,int events,int milliseconds){
    int epoll=sceNetEpollCreate("p014-wait",0);if(epoll<0)return pop_net_error();
    PopNetEvent item={events==4?2u:1u,0,(uint64_t)fd,0};
    int result=sceNetEpollControl(epoll,1,fd,&item);
    if(!result)result=sceNetEpollWait(epoll,&item,1,milliseconds*1000);
    int error=result<0?pop_net_error():result?0:-60;sceNetEpollDestroy(epoll);return error;
}
static void pop_sep_log(FILE *log,const char *event,long value){
    if(log){fprintf(log,"{\"build\":\"P014\",\"side\":\"title\",\"event\":\"%s\",\"value\":%ld}\n",event,value);fflush(log);fsync(fileno(log));}
}

/* pick the first child-ELF path that exists: post-jailbreak /app0 is gone, but the sandbox mount and /data
 * are reachable from the escaped root. Logs which one was used (or -1 if none). */
static const char *pop_pick_child_elf(FILE *log){
    /* logged index: 0 = /data (FTP-uploaded iteration), 1 = sandbox (installed), 2 = /app0 */
    static const char *const candidates[]={POP_SEP_CHILD_ELF_DATA,POP_SEP_CHILD_ELF_SANDBOX,POP_SEP_CHILD_ELF};
    for(unsigned i=0;i<sizeof(candidates)/sizeof(candidates[0]);i++){
        struct stat st;if(stat(candidates[i],&st)==0){pop_sep_log(log,"child_elf_path",(long)i);return candidates[i];}
    }
    pop_sep_log(log,"child_elf_not_found",-1);return NULL;
}

/* 04.15 (W303 run-0198, run-0199: Prince of Persia's launcher, moved to a separate process from a 32-bit guest that held
 * a Vulkan device and MangoHud, ended the whole title twice with no crash line, no coredump; title.jsonl stops at
 * child_elf_path both times, so inside the loader connect below, which then used libSceNet: sceNetSocket,
 * sceNetSetsockopt, sceNetConnect and a sceNetEpoll per wait). libSceNet's epoll already aborted the title once (PoP
 * D.7, platform/ps4/pw_wine_net.c), and Wine's own sockets and waits in this process use the kernel's socket() and
 * poll(). The loader connection now does the same: a loopback TCP socket of the kernel, a blocking connect (loopback
 * answers at once, or refuses), send and receive timeouts, and poll() for the stream. Each step is logged, so a
 * death that remains names its call. The address is BSD's (len, family), as pop_bsd_unix_addr's. */
#include <poll.h>
#include <sys/time.h>
static int pop_loader_socket(int port,FILE *log,const char *who){
    pop_sep_log(log,who,0);   /* step 0: about to create the socket */
    int fd=socket(AF_INET,SOCK_STREAM,0);
    if(fd<0){pop_sep_log(log,"loader_socket_errno",errno);return -1;}
    const struct timeval timeout={.tv_sec=2};
    int one=1;setsockopt(fd,SOL_SOCKET,0x1022 /* SO_NOSIGPIPE */,&one,sizeof(one));
    if(setsockopt(fd,SOL_SOCKET,SO_SNDTIMEO,&timeout,sizeof(timeout)))pop_sep_log(log,"loader_sndtimeo_errno",errno);
    if(setsockopt(fd,SOL_SOCKET,SO_RCVTIMEO,&timeout,sizeof(timeout)))pop_sep_log(log,"loader_rcvtimeo_errno",errno);
    struct {uint8_t len,family;uint16_t port;uint8_t ip[4],zero[8];} address={16,AF_INET,0,{127,0,0,1},{0}};
    address.port=(uint16_t)((port>>8)|((port&255)<<8));
    pop_sep_log(log,"loader_connecting",port);
    if(connect(fd,(struct sockaddr *)&address,sizeof(address))){
        int e=errno;close(fd);errno=e;return -1;
    }
    return fd;
}
static int pop_loader_send_all(int fd,const unsigned char *buf,size_t n){
    for(size_t off=0;off<n;){
        ssize_t sent=send(fd,buf+off,n-off,0);
        if(sent<0&&errno==EINTR)continue;
        if(sent<=0)return sent<0?-errno:-EPIPE;
        off+=(size_t)sent;
    }
    return 0;
}

/* send the bundled child ELF to the loader's socksrv (raw ELF bytes -> elfldr_spawn). Returns bytes sent, or <0 */
static long pop_loader_spawn_elf(const char *elf_path,FILE *log){
    int sock=pop_loader_socket(9021,log,"loader_socket_begin");
    if(sock<0){long e=-(long)errno;pop_sep_log(log,"loader_unavailable",e);return e?e:-1;}
    long result=-1;FILE *elf=NULL;long rc;
    pop_sep_log(log,"loader_connected",9021);
    elf=fopen(elf_path,"rb");if(!elf){pop_sep_log(log,"child_elf_open_failed",errno);goto done;}
    unsigned char buf[4096];size_t n;unsigned total=0;
    while((n=fread(buf,1,sizeof(buf),elf))){
        if(total+n>1048576){pop_sep_log(log,"child_elf_too_large",total+n);goto done;}
        if((rc=pop_loader_send_all(sock,buf,n))){pop_sep_log(log,"loader_send_failed",rc);goto done;}
        total+=(unsigned)n;
    }
    pop_sep_log(log,"child_elf_bytes_sent",total);shutdown(sock,SHUT_WR);
    result=(long)total;
    /* drain the child's stdout stream for a short while (evidence of the loader actually running it) */
    char path[224];snprintf(path,sizeof(path),POP_SEP_DIR "/loader-stream.log");FILE *stream=fopen(path,"wb");
    for(unsigned k=0;k<40;k++){
        struct pollfd pfd={sock,POLLIN,0};
        rc=poll(&pfd,1,200);if(rc==0||(rc<0&&errno==EINTR))continue;
        if(rc<0){pop_sep_log(log,"loader_stream_poll_errno",errno);break;}
        rc=recv(sock,buf,sizeof(buf),0);
        if(!rc){pop_sep_log(log,"loader_stream_eof",0);break;}
        if(rc<0){if(errno==EINTR||errno==EAGAIN)continue;pop_sep_log(log,"loader_stream_error",-(long)errno);break;}
        if(stream){fwrite(buf,1,(size_t)rc,stream);fflush(stream);}
    }
    if(stream){fsync(fileno(stream));fclose(stream);}
done:
    if(elf)fclose(elf);close(sock);
    return result;
}

/* PoP D.7 (hardware 2026-11-13: after each console reboot separate programs did not start until the loader was
 * sent again from a PC): the resident loader is GoldHEN BinLoader's to start. When it does not answer, the title
 * sends the bundled elfldr (POP_SEP_LOADER_ELF, built and pinned by tools/process-loader, GPL-3.0-or-later, its
 * source next to it) to BinLoader on 127.0.0.1:9090, as tools/start-process-loader.py --start does from a PC.
 * Returns the bytes sent, or <0. */
static long pop_loader_bootstrap(FILE *log){
    static const char *const candidates[]={POP_SEP_LOADER_ELF_DATA,POP_SEP_LOADER_ELF_SANDBOX,POP_SEP_LOADER_ELF};
    FILE *elf=NULL;long result=-1;
    for(unsigned i=0;i<sizeof(candidates)/sizeof(candidates[0])&&!elf;i++)
        if((elf=fopen(candidates[i],"rb")))pop_sep_log(log,"loader_bootstrap_path",(long)i);
    if(!elf){pop_sep_log(log,"loader_bootstrap_missing",-1);return -1;}
    /* 04.15: the kernel's socket, as pop_loader_spawn_elf */
    int sock=pop_loader_socket(9090,log,"loader_bootstrap_begin");
    if(sock<0){pop_sep_log(log,"loader_bootstrap_connect",-(long)errno);fclose(elf);return -1;}
    unsigned char buf[4096];size_t n;unsigned total=0;long rc;
    while((n=fread(buf,1,sizeof(buf),elf))){
        if((rc=pop_loader_send_all(sock,buf,n))){pop_sep_log(log,"loader_bootstrap_send",rc);goto done;}
        total+=(unsigned)n;
    }
    pop_sep_log(log,"loader_bootstrap_sent",total);result=(long)total;
done:
    fclose(elf);close(sock);
    return result;
}

/* OpenOrbis' musl sockaddr_un has no sun_len (sun_family is byte 0), but the PS4 kernel is BSD: it reads
 * byte 0 as the length and byte 1 as the family, so a musl-layout bind fails with EINVAL (hardware,
 * 2026-11-12). Build the BSD layout by hand: len, AF_UNIX, path, NUL. */
static int pop_bsd_unix_addr(unsigned char *addr,size_t cap,const char *path){
    size_t n=strlen(path);if(n+3>cap||n+3>255)return -1;
    memset(addr,0,cap);addr[1]=AF_UNIX;memcpy(addr+2,path,n+1);addr[0]=(unsigned char)(n+3);
    return (int)(n+3);
}
/* exported by the in-process wineserver (tools/prepare-wine-boot.py, server/request.c) */
extern int pw_wine_server_adopt_client(int fd);
/* Bridge: WINE_INPROCESS_SERVER has no socket file, so listen at <server dir>/socket -- where a separate
 * process looks for the master socket -- and hand every accepted connection to the server thread. The dir
 * is 0700 and owned by the app uid; the child adopts that uid before connecting. */
static void *pop_sep_bridge(void *arg){
    FILE *log=arg;char dir[400],sock[420];struct stat st;int ready=0;
    for(int t=0;t<600&&!ready;t++){  /* up to 5 minutes for the server to create its directory */
        if(stat(POP_SEP_PREFIX,&st)==0){
            snprintf(dir,sizeof(dir),"%s/.wineserver/server-%llx-%llx",POP_SEP_PREFIX,
                     (unsigned long long)st.st_dev,(unsigned long long)st.st_ino);
            ready=stat(dir,&st)==0;
        }
        if(!ready)usleep(500000);
    }
    if(!ready){pop_sep_log(log,"bridge_no_server_dir",errno);return NULL;}
    snprintf(sock,sizeof(sock),"%s/socket",dir);unlink(sock);
    unsigned char addr[128];int len=pop_bsd_unix_addr(addr,sizeof(addr),sock);
    int fd=len<0?-1:socket(AF_UNIX,SOCK_STREAM,0),err=len<0?ENAMETOOLONG:fd<0?errno:0;
    if(!err&&bind(fd,(struct sockaddr*)addr,(socklen_t)len))err=errno;
    if(!err&&chmod(sock,0600))err=errno;
    if(!err&&listen(fd,16))err=errno;
    pop_sep_log(log,"bridge_listen_errno",err);
    if(err){if(fd>=0)close(fd);return NULL;}
    for(;;){
        int client=accept(fd,NULL,NULL);
        if(client<0){if(errno!=EINTR){pop_sep_log(log,"bridge_accept_errno",errno);usleep(100000);}continue;}
        int rc=pw_wine_server_adopt_client(client);
        pop_sep_log(log,"bridge_adopt",rc?-(long)errno:(long)client);
        close(client);
    }
    return NULL;
}
static void pop_sep_log_stat(FILE *log,const char *what,const char *path){
    char event[64];struct stat st;
    if(stat(path,&st)){snprintf(event,sizeof(event),"%s_stat_errno",what);pop_sep_log(log,event,errno);return;}
    /* mode logged in octal digits as a decimal number (e.g. 140600 = socket, 0600) */
    char octal[16];snprintf(octal,sizeof(octal),"%o",(unsigned)st.st_mode);
    snprintf(event,sizeof(event),"%s_mode_octal",what);pop_sep_log(log,event,atol(octal));
    snprintf(event,sizeof(event),"%s_uid",what);pop_sep_log(log,event,(long)st.st_uid);
    snprintf(event,sizeof(event),"%s_gid",what);pop_sep_log(log,event,(long)st.st_gid);
}
/* Phase C / P015 (title side): the separate process streams its window's pixels here (POP_SEP_SURFACE); the
 * sink composites the latest frame at the window's desktop rectangle on every output frame
 * (pw_hw_separate_draw, called from platform/ps4/pw_wine_sink_ps4.c), and a new frame requests a re-show,
 * like a pointer move. The window itself lives in the wineserver (the child created it there), so hit testing
 * and input routing are the server's; only the pixels travel this way. Shown only while the child is
 * connected: a closed connection removes the picture. */
static pthread_mutex_t pop_sep_surface_lock=PTHREAD_MUTEX_INITIALIZER;
static struct pop_sep_frame pop_sep_shown;      /* header of the frame on screen */
static uint32_t *pop_sep_pixels;               /* its pixels, pop_sep_shown.w * .h */
static size_t pop_sep_pixels_cap;
static int pop_sep_visible;
extern void pw_hw_cursor_moved(void);           /* platform/ps4/pw_wine_sink_ps4.c: re-show the output */

static int pop_sep_read_all(int fd,void *buf,size_t len){
    char *p=buf;
    while(len){ssize_t r=recv(fd,p,len,0);if(r==0)return -1;if(r<0){if(errno==EINTR)continue;return -1;}p+=r;len-=(size_t)r;}
    return 0;
}
static void *pop_sep_surface_thread(void *arg){
    FILE *log=arg;
    unlink(POP_SEP_SURFACE);
    unsigned char addr[128];int len=pop_bsd_unix_addr(addr,sizeof(addr),POP_SEP_SURFACE);
    int fd=len<0?-1:socket(AF_UNIX,SOCK_STREAM,0),err=len<0?ENAMETOOLONG:fd<0?errno:0;
    if(!err&&bind(fd,(struct sockaddr*)addr,(socklen_t)len))err=errno;
    if(!err&&chmod(POP_SEP_SURFACE,0666))err=errno;
    if(!err&&listen(fd,4))err=errno;
    pop_sep_log(log,"surface_listen_errno",err);
    if(err){if(fd>=0)close(fd);return NULL;}
    uint32_t *incoming=NULL;size_t incoming_cap=0;
    for(;;){
        int client=accept(fd,NULL,NULL);
        if(client<0){if(errno!=EINTR){pop_sep_log(log,"surface_accept_errno",errno);usleep(100000);}continue;}
        pop_sep_log(log,"surface_connected",client);
        unsigned long frames=0;
        for(;;){
            struct pop_sep_frame hdr;
            if(pop_sep_read_all(client,&hdr,sizeof(hdr)))break;
            if(hdr.magic!=POP_SEP_FRAME_MAGIC||hdr.w<=0||hdr.h<=0||hdr.w>1920||hdr.h>1080){
                pop_sep_log(log,"surface_bad_header",(long)hdr.magic);break;
            }
            size_t bytes=(size_t)hdr.w*(size_t)hdr.h*4;
            if(bytes>incoming_cap){free(incoming);incoming=malloc(bytes);incoming_cap=incoming?bytes:0;if(!incoming)break;}
            if(pop_sep_read_all(client,incoming,bytes))break;
            pthread_mutex_lock(&pop_sep_surface_lock);
            uint32_t *old=pop_sep_pixels;size_t old_cap=pop_sep_pixels_cap;
            pop_sep_pixels=incoming;pop_sep_pixels_cap=incoming_cap;
            incoming=old;incoming_cap=old_cap;
            pop_sep_shown=hdr;pop_sep_visible=1;
            pthread_mutex_unlock(&pop_sep_surface_lock);
            if(!frames++)pop_sep_log(log,"surface_first_frame",(long)hdr.window);
            pw_hw_cursor_moved();
        }
        pthread_mutex_lock(&pop_sep_surface_lock);pop_sep_visible=0;pthread_mutex_unlock(&pop_sep_surface_lock);
        pw_hw_cursor_moved();
        pop_sep_log(log,"surface_closed_frames",(long)frames);
        close(client);
    }
    return NULL;
}
/* Called by win32u's driver for each pointer event (ps5drv.c window_at): the separate process's window (its
 * handle, sent with each frame) when desktop point x,y is over it as last composited, else 0. trylock: input
 * must never wait on the presenter. */
unsigned long long pw_hw_separate_window(int x, int y);
unsigned long long pw_hw_separate_window(int x, int y){
    if(pthread_mutex_trylock(&pop_sep_surface_lock)) return 0;
    const struct pop_sep_frame *f = &pop_sep_shown;
    unsigned long long hwnd = pop_sep_visible && x >= f->x && x < f->x + f->w && y >= f->y && y < f->y + f->h ? f->window : 0;
    pthread_mutex_unlock(&pop_sep_surface_lock);
    return hwnd;
}
/* Called by the sink on each output frame: the desktop (desk_w x desk_h) is shown scaled at
 * (left,top,scale_w,scale_h) of the output; draw the separate window's pixels at its desktop rectangle with
 * the same mapping. Returns 1 when something was drawn (the sink then redraws the pointer over it). */
int pw_hw_separate_draw(uint32_t *target,unsigned pitch,unsigned out_w,unsigned out_h,unsigned left,unsigned top,
                        unsigned scale_w,unsigned scale_h,unsigned desk_w,unsigned desk_h);
int pw_hw_separate_draw(uint32_t *target,unsigned pitch,unsigned out_w,unsigned out_h,unsigned left,unsigned top,
                        unsigned scale_w,unsigned scale_h,unsigned desk_w,unsigned desk_h){
    if(!desk_w||!desk_h||!scale_w||!scale_h)return 0;
    if(pthread_mutex_trylock(&pop_sep_surface_lock))return 0;   /* never stall the presenter */
    int drawn=0;
    if(pop_sep_visible&&pop_sep_pixels){
        const struct pop_sep_frame *f=&pop_sep_shown;
        long x0=(long)left+(long)f->x*scale_w/desk_w,y0=(long)top+(long)f->y*scale_h/desk_h;
        long x1=(long)left+(long)(f->x+f->w)*scale_w/desk_w,y1=(long)top+(long)(f->y+f->h)*scale_h/desk_h;
        if(x0<0)x0=0;if(y0<0)y0=0;if(x1>(long)out_w)x1=out_w;if(y1>(long)out_h)y1=out_h;
        long ow=(long)(f->w)*scale_w/desk_w,oh=(long)(f->h)*scale_h/desk_h;
        long ox=(long)left+(long)f->x*scale_w/desk_w,oy=(long)top+(long)f->y*scale_h/desk_h;
        if(ow>0&&oh>0)for(long y=y0;y<y1;y++){
            long sy=(y-oy)*f->h/oh;if(sy<0||sy>=f->h)continue;
            const uint32_t *row=pop_sep_pixels+(size_t)sy*f->w;uint32_t *out=target+(size_t)y*pitch;
            for(long x=x0;x<x1;x++){long sx=(x-ox)*f->w/ow;if(sx>=0&&sx<f->w)out[x]=row[sx]|0xff000000u;}
        }
        drawn=1;
    }
    pthread_mutex_unlock(&pop_sep_surface_lock);
    return drawn;
}
/* watcher thread: when kernelbase drops POP_SEP_REQUEST, spawn the child once and log the outcome */
static void *pop_separate_watch(void *arg){
    (void)arg;
    int init=sceNetInit();  /* harmless if the title already initialised the network */
    mkdir("/data/orbisdesk",0755);mkdir(POP_SEP_DIR,0777);
    FILE *log=fopen(POP_SEP_DIR "/title.jsonl","a");
    /* the eboot has already dropped to the title's app uid (W228); publish it so the root child can adopt it */
    FILE *uf=fopen(POP_SEP_APP_UID,"w");if(uf){fprintf(uf,"%d\n",(int)getuid());fclose(uf);}
    pop_sep_log(log,"watch_started",init);pop_sep_log(log,"app_uid",(long)getuid());
    pop_sep_log(log,"app_euid",(long)geteuid());pop_sep_log(log,"app_gid",(long)getgid());
    {pthread_t bridge;pop_sep_log(log,"bridge_thread",pthread_create(&bridge,NULL,pop_sep_bridge,log));}
    {pthread_t surface;pop_sep_log(log,"surface_thread",pthread_create(&surface,NULL,pop_sep_surface_thread,log));}
    /* one-time boot self-test: prove the separate-process JOIN on hardware without needing a guest to launch
     * a Separados-flagged EXE. Delay so the in-process wineserver is up (the child also retries its connect).
     * Disable by creating POP_SEP_DIR/no-selftest. The kernelbase PW_EXEC_SEPARATE path still works too. */
    {
        struct stat st;int disabled=stat(POP_SEP_SELFTEST,&st)!=0;   /* D.3: opt-in */
        pop_sep_log(log,"selftest_disabled",disabled);
        if(!disabled){
            for(int s=0;s<20;s++)sleep(1);
            {   /* the wineserver is up by now: its directory and socket as the title sees them */
                struct stat pst;char dir[400],sock[420];
                if(stat(POP_SEP_PREFIX,&pst)==0){
                    snprintf(dir,sizeof(dir),"%s/.wineserver/server-%llx-%llx",POP_SEP_PREFIX,
                             (unsigned long long)pst.st_dev,(unsigned long long)pst.st_ino);
                    snprintf(sock,sizeof(sock),"%s/socket",dir);
                    pop_sep_log_stat(log,"server_dir",dir);pop_sep_log_stat(log,"server_socket",sock);
                }else pop_sep_log(log,"prefix_stat_errno",errno);
            }
            pop_sep_log(log,"selftest_spawn",0);
            const char *elf=pop_pick_child_elf(log);
            long sent=elf?pop_loader_spawn_elf(elf,log):-1;
            pop_sep_log(log,"selftest_spawn_done",sent);
        }
    }
    for(;;){
        FILE *req=fopen(POP_SEP_REQUEST,"rb");
        if(req){
            char app[8192];size_t got=fread(app,1,sizeof(app)-1,req);app[got]=0;fclose(req);
            unlink(POP_SEP_REQUEST);
            pop_sep_log(log,"spawn_requested",(long)got);
            /* D.3: the request is the child's job (it reads and removes it before running Wine) */
            FILE *job=fopen(POP_SEP_JOB ".tmp","wb");
            int job_ok=job&&fwrite(app,1,got,job)==got;if(job)fclose(job);
            if(job_ok){chmod(POP_SEP_JOB ".tmp",0666);job_ok=!rename(POP_SEP_JOB ".tmp",POP_SEP_JOB);}
            pop_sep_log(log,"job_written",job_ok?(long)got:-(long)errno);
            const char *elf=pop_pick_child_elf(log);
            long sent=elf?pop_loader_spawn_elf(elf,log):-1;
            /* PoP D.7: no resident loader (a console reboot): send it, then try again while it starts */
            if(sent<0&&elf&&pop_loader_bootstrap(log)>0)
                for(int attempt=0;attempt<10&&sent<0;attempt++){sleep(1);sent=pop_loader_spawn_elf(elf,log);}
            pop_sep_log(log,"spawn_done",sent);
            if(sent<0){
                /* PoP D.7: kernelbase stops waiting for started-<token> (30 s with the desktop thread held) */
                char failed[256];unsigned long token=strtoul(app,NULL,10);
                snprintf(failed,sizeof(failed),POP_SEP_DIR "/failed-%lu",token);
                FILE *ff=fopen(failed,"w");if(ff){fprintf(ff,"%ld\n",sent);fclose(ff);chmod(failed,0666);}
                unlink(POP_SEP_JOB);   /* no stale job for the next start */
                pop_sep_log(log,"spawn_failed_reported",(long)token);
            }
        }
        usleep(200000);
    }
    return NULL;
}

#endif
