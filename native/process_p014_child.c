/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* P014 child (built with the PS4 payload SDK, like elfldr's own samples, so its CRT self-resolves imports
 * and the loader's ELF path runs it -- Phase A substrate, with the SCHED_RR MAX loader fix). It is a genuine
 * SECOND native process that joins the TITLE's real in-process wineserver by connecting to its filesystem
 * master socket (OrbisDesk's server still calls open_master_socket(); patches/wine/0003), performs the slim
 * init_first_thread handshake, and creates the named object the title then opens. This is the exact
 * cross-process shared-named-object rendezvous a dual-fixed-base launcher game (Prince of Persia:
 * launcher + POP.exe on "PrinceSM") needs. Loader-dependent research substrate; not a shippable feature. */
#include <sys/stat.h>
#include <dlfcn.h>
#include "pop_separate.h"
#include "pop_wine_join_core.h"
#include "pop_separate_window.h"

/* connect a fresh AF_UNIX stream socket to `path`; 0 on success, else errno */
static int pop_try_connect(const char *path){
    struct sockaddr_un addr;memset(&addr,0,sizeof(addr));addr.sun_family=AF_UNIX;
    snprintf(addr.sun_path,sizeof(addr.sun_path),"%s",path);
    addr.sun_len=(uint8_t)(sizeof(addr)-sizeof(addr.sun_path)+strlen(addr.sun_path)+1);
    int fd=socket(AF_UNIX,SOCK_STREAM,0);if(fd<0)return errno?errno:-1;
    int rc=connect(fd,(struct sockaddr*)&addr,sizeof(addr));int err=rc?errno:0;close(fd);return err;
}

/* EACCES diagnosis (first hardware run, 2026-11-12): who the child really is, what each component of the
 * server socket path looks like from here, and whether AF_UNIX connects work at all from this process --
 * to itself, and to a 0777 socket the title publishes in a 0777 directory. If those work and the server
 * socket does not, it is file permissions/credentials; if the title probe fails too, it is the sandbox. */
static void pop_child_diagnose(struct pop_join *j){
    gid_t groups[16];int ngroups=getgroups(16,groups);
    pop_logf(j,"{\"build\":\"P014\",\"event\":\"creds\",\"uid\":%d,\"euid\":%d,\"gid\":%d,\"egid\":%d,\"ngroups\":%d,\"group0\":%d}",
             (int)getuid(),(int)geteuid(),(int)getgid(),(int)getegid(),ngroups,ngroups>0?(int)groups[0]:-1);
    char dir[400];pop_server_dir(j,POP_SEP_PREFIX,dir,sizeof(dir));
    char path[420];snprintf(path,sizeof(path),"%s/socket",dir);
    for(char *p=path+1;;p++){
        char saved=*p;if(saved!='/'&&saved!=0)continue;
        *p=0;struct stat st;
        if(stat(path,&st)==0)pop_logf(j,"{\"build\":\"P014\",\"event\":\"path_stat\",\"path\":\"%s\",\"mode\":\"%o\",\"uid\":%d,\"gid\":%d}",
                                      path,(unsigned)st.st_mode,(int)st.st_uid,(int)st.st_gid);
        else pop_logf(j,"{\"build\":\"P014\",\"event\":\"path_stat\",\"path\":\"%s\",\"errno\":%d}",path,errno);
        *p=saved;if(!saved)break;
    }
    pop_logf(j,"{\"build\":\"P014\",\"event\":\"socket_access_rw\",\"errno\":%d}",access(path,R_OK|W_OK)?errno:0);
    /* AF_UNIX inside this process */
    const char *self=POP_SEP_DIR "/child-self.sock";unlink(self);
    struct sockaddr_un addr;memset(&addr,0,sizeof(addr));addr.sun_family=AF_UNIX;
    snprintf(addr.sun_path,sizeof(addr.sun_path),"%s",self);
    addr.sun_len=(uint8_t)(sizeof(addr)-sizeof(addr.sun_path)+strlen(addr.sun_path)+1);
    int listener=socket(AF_UNIX,SOCK_STREAM,0),bind_err=-1,self_err=-1;
    if(listener>=0){
        bind_err=(bind(listener,(struct sockaddr*)&addr,sizeof(addr))||listen(listener,4))?errno:0;
        if(!bind_err)self_err=pop_try_connect(self);
        close(listener);unlink(self);
    }
    pop_logf(j,"{\"build\":\"P014\",\"event\":\"self_socket\",\"bind_errno\":%d,\"connect_errno\":%d}",bind_err,self_err);
    /* AF_UNIX to the title, through its world-open probe socket */
    struct stat st;int present=stat(POP_SEP_TITLE_PROBE,&st)==0;
    pop_logf(j,"{\"build\":\"P014\",\"event\":\"title_probe\",\"present\":%d,\"mode\":\"%o\",\"uid\":%d,\"connect_errno\":%d}",
             present,present?(unsigned)st.st_mode:0u,present?(int)st.st_uid:-1,present?pop_try_connect(POP_SEP_TITLE_PROBE):-1);
}

int main(void){
    /* the loader rdup's its socket onto stdio, so this first line reaches the title's stream log */
    printf("P014 child pid=%ld joining wineserver\n",(long)getpid());fflush(stdout);
    mkdir("/data/orbisdesk",0755);mkdir(POP_SEP_DIR,0777);
    FILE *logf=fopen(POP_SEP_CHILD_LOG,"w");
    struct pop_join j={.fd_socket=-1,.request_fd=-1,.reply_fd=-1,.log=logf};
    pop_logf(&j,"{\"build\":\"P014\",\"event\":\"child_entered\",\"pid\":%ld,\"ppid\":%ld,\"uid\":%d}",(long)getpid(),(long)getppid(),(int)getuid());
    /* W228: GoldHEN's root does NOT override file permissions, and the title dropped to its app uid, so the
     * wineserver's 0600 master socket is unreachable by root. Adopt the title's uid (written by the eboot
     * watcher) before connecting, so the socket's owner check and the server's session match. */
    FILE *uf=fopen(POP_SEP_APP_UID,"r");
    /* The loader hands us uid=1 but euid=0 (hardware, 2026-11-12): permission checks use the euid, so compare
     * both; setuid() from euid 0 sets real, effective and saved uid together. */
    if(uf){int want=-1;if(fscanf(uf,"%d",&want)==1 && want>=0 && ((int)getuid()!=want || (int)geteuid()!=want)){
        errno=0;int rc=setuid((uid_t)want),err=rc?errno:0;
        if(rc && (int)geteuid()!=want){errno=0;rc=seteuid((uid_t)want);err=rc?errno:0;}
        pop_logf(&j,"{\"build\":\"P014\",\"event\":\"adopt_uid\",\"want\":%d,\"rc\":%d,\"errno\":%d,\"uid\":%d,\"euid\":%d}",
                 want,rc,err,(int)getuid(),(int)geteuid());}fclose(uf);}
    else pop_logf(&j,"{\"build\":\"P014\",\"event\":\"app_uid_missing\",\"uid\":%d}",(int)getuid());
    /* Phase D.1a / P016: host OpenOrbis code (the toolchain and libc of the title's Wine) in this process
     * through the system linker, the way GoldHEN plugins load: imports, TLS and initialisers resolved there. */
    {void *prx=dlopen(POP_SEP_PRX_PROBE,RTLD_NOW);
     int (*probe)(int)=prx?(int(*)(int))dlsym(prx,"pop_prx_probe"):NULL;
     const char *dlerr=prx&&probe?"":dlerror();
     pop_logf(&j,"{\"build\":\"P016\",\"event\":\"prx_load\",\"handle\":%d,\"entry\":%d,\"error\":\"%s\"}",
              prx!=NULL,probe!=NULL,dlerr?dlerr:"?");
     if(probe){if(logf)fflush(logf);int r=probe(logf?fileno(logf):-1);
        pop_logf(&j,"{\"build\":\"P016\",\"event\":\"prx_returned\",\"ok\":%d}",r);}}
    /* Phase D.1b / P017: when the Wine PRX is installed, this process becomes a Wine process of the title's
     * server: connect to the bridge, hand the socket to Wine (WINESERVERSOCKET) and run a Windows program.
     * pop_wine_child_run does not return on success (Wine exits the process with the program's exit code). */
    {struct stat wst;
     if(stat(POP_SEP_WINE_PRX,&wst)==0){
        void *w=dlopen(POP_SEP_WINE_PRX,RTLD_NOW);
        int (*run)(int,const char*,const char*)=w?(int(*)(int,const char*,const char*))dlsym(w,"pop_wine_child_run"):NULL;
        int (*run_job)(int,const char*,const char*,const char*,const char*,const char*)=
            w?(int(*)(int,const char*,const char*,const char*,const char*,const char*))dlsym(w,"pop_wine_child_run_job"):NULL;
        const char *werr=w&&run?"":dlerror();
        pop_logf(&j,"{\"build\":\"P017\",\"event\":\"wine_prx_load\",\"bytes\":%lld,\"handle\":%d,\"entry\":%d,\"error\":\"%s\"}",
                 (long long)wst.st_size,w!=NULL,run!=NULL,werr?werr:"?");
        if(run){
            pop_connect(&j,POP_SEP_PREFIX);
            pop_logf(&j,"{\"build\":\"P017\",\"event\":\"wine_handoff\",\"server_fd\":%d,\"exe\":\"%s\"}",j.fd_socket,"separate_d1.exe");
            if(logf)fflush(logf);
            /* D.3: kernelbase's request, handed over by the title as POP_SEP_JOB: token, image, command line,
             * current directory, one per line */
            static char job[8192];char *field[4]={0};
            FILE *jf=fopen(POP_SEP_JOB,"rb");
            if(jf){size_t got=fread(job,1,sizeof(job)-1,jf);job[got]=0;fclose(jf);unlink(POP_SEP_JOB);
                char *p=job;for(int k=0;k<4&&p&&*p;k++){field[k]=p;p=strchr(p,'\n');if(p)*p++=0;}}
            int rc;
            if(field[3]&&run_job){
                pop_logf(&j,"{\"build\":\"P019\",\"event\":\"job\",\"token\":\"%s\",\"image_bytes\":%zu}",field[0],strlen(field[1]));
                if(logf)fflush(logf);
                rc=run_job(j.fd_socket,field[0],field[1],field[2],field[3],POP_SEP_WINE_LOG);
            }else{
                struct stat d2;const char *exe=stat(POP_SEP_D2_FILE,&d2)==0?POP_SEP_D2_EXE:POP_SEP_D1_EXE;  /* D.2: the GUI program when installed */
                rc=run(j.fd_socket,exe,POP_SEP_WINE_LOG);
            }
            pop_logf(&j,"{\"build\":\"P017\",\"event\":\"wine_child_returned\",\"rc\":%d}",rc);
            if(logf)fclose(logf);
            return rc;
        }
     }}
    pop_child_diagnose(&j);
    /* Phase B: join + named object (held for the whole run: the handle stays open while this process lives) */
    int ok=pop_wine_join_run(&j,POP_SEP_PREFIX,0/*create*/,POP_SEP_OBJECT_A,0);
    pop_logf(&j,"{\"build\":\"P014\",\"event\":\"joined\",\"shared_namespace_ok\":%d}",ok);
    /* Phase C: a window of this process in the title's desktop, its input, its pixels */
    int window_ok=ok?pop_separate_window_run(&j,POP_SEP_WINDOW_SECONDS):0;
    pop_logf(&j,"{\"build\":\"P015\",\"event\":\"child_exit\",\"shared_namespace_ok\":%d,\"window_ok\":%d}",ok,window_ok);
    if(logf)fclose(logf);
    return ok?42:5;
}
