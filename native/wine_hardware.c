/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <errno.h>
#include <signal.h>
#include <stdarg.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#include <sys/socket.h>
#include <sys/mman.h>
#include <sys/ioctl.h>
#ifndef FIONBIO
#define FIONBIO 0x8004667e /* FreeBSD _IOW('f',126,int); absent from the SDK headers */
#endif
#include <orbis/libkernel.h>
#include <orbis/Sysmodule.h>
#include <orbis/SystemService.h>
#include <orbis/Rtc.h>
#include <orbis/Pad.h>
#include <time.h>
#include "hw_text.h"
#include "pw_brand.h"
#include "pw_wine_fs.h"
#include "pw_wine_platform.h"
#include "pw_wine_context.h"
#include "pw_wine_net.h"
#include "pw_trace.h"
#include <limits.h>
#include <pthread.h>
/* W001 and W002 sources and evidence: reports/wine-hardware-w00N/release-w00N. */
#define HW_BUILD "W303"
#ifndef HW_VERSION
#define HW_VERSION "04.02"
#endif
#define HW_DIR "/data/orbisdesk/w303"
#define HW_EXE "C:\\windows\\explorer.exe"
#define HW_RESULT "text-result.txt"
#ifndef PW_MANGOHUD_LAYER_ENABLED
#define PW_MANGOHUD_LAYER_ENABLED 1
#endif

extern int pw_wine_boot_main(int,char **);
extern void pw_vk_probe(void);
/* W071-W072 (H2, H3): win32u's Vulkan entry and the headless swapchains' frames
 * (platform/ps4/pw_wine_unixlibs.c, native/wine_vk_runtime.c) */
extern void pw_vk_runtime_init(void);
extern void pw_native_heap_report(void);
extern void pw_telemetry_init(void);
int main(void);
extern int pw_wine_present(const void *,unsigned int,unsigned int,unsigned int);
extern void __real_exit(int) __attribute__((noreturn));
extern void __real__exit(int) __attribute__((noreturn));
extern ssize_t __real_write(int,const void *,size_t);
static int log_fd=-1,stderr_redirected;
static uint32_t *pixels;

/* Launcher markers go straight to the log file, so they survive a missing stderr redirect.
 * W027: no fsync per line. A write() already reaches the kernel, so the text survives the
 * process ending or being killed; only exit and crash records still sync. */
static void note(const char *format,...) __attribute__((format(printf,1,2)));
static void note(const char *format,...)
{
    char message[256];va_list ap;va_start(ap,format);int n=vsnprintf(message,sizeof(message),format,ap);va_end(ap);
    if(n<0)return;if(n>=(int)sizeof(message))n=sizeof(message)-1;
    if(log_fd>=0)write(log_fd,message,(size_t)n);
    /* The console copy bypasses the write wrap, which would log the line a second time. */
    if(!stderr_redirected)__real_write(STDERR_FILENO,message,(size_t)n);
}

/* A redirect must be proven by its effect: a probe written to fd 2 has to advance the log file. */
static int redirect_verified(void)
{
    off_t before=lseek(log_fd,0,SEEK_END);
    static const char probe[]=HW_BUILD " stderr_probe\n";
    ssize_t written=write(STDERR_FILENO,probe,sizeof(probe)-1);
    off_t after=lseek(log_fd,0,SEEK_END);
    return written==(ssize_t)sizeof(probe)-1&&after==before+written;
}
/* fcntl is the libkernel import, so it takes FreeBSD commands; the SDK header is musl's. */
enum {FREEBSD_F_DUP2FD=10};
/* W001 saw dup2 return -1 on hardware; record why and try fcntl(F_DUP2FD), which
 * replaces the target descriptor without closing anything first. */
static void redirect_stderr(void)
{
    errno=0;int out=dup2(log_fd,STDOUT_FILENO),out_errno=errno;
    errno=0;int err=dup2(log_fd,STDERR_FILENO),err_errno=errno;
    stderr_redirected=err==STDERR_FILENO&&redirect_verified();
    note(HW_BUILD " stderr_redirect method=dup2 out=%d errno=%d err=%d errno=%d verified=%d\n",out,out_errno,err,err_errno,stderr_redirected);
    if(stderr_redirected)goto done;
    errno=0;out=fcntl(log_fd,FREEBSD_F_DUP2FD,STDOUT_FILENO);out_errno=errno;
    errno=0;err=fcntl(log_fd,FREEBSD_F_DUP2FD,STDERR_FILENO);err_errno=errno;
    stderr_redirected=err==STDERR_FILENO&&redirect_verified();
    note(HW_BUILD " stderr_redirect method=f_dup2fd out=%d errno=%d err=%d errno=%d verified=%d\n",out,out_errno,err,err_errno,stderr_redirected);
    if(!stderr_redirected)return;
done:
    setvbuf(stdout,NULL,_IONBF,0);setvbuf(stderr,NULL,_IONBF,0);
}
enum {WIDTH=1280,HEIGHT=720};

static void record_exit(int status,const char *method)
{
    char message[160];int n=snprintf(message,sizeof(message),HW_BUILD " process_exit method=%s status=0x%08x t_ms=%llu\n",method,(unsigned)status,
                                     (unsigned long long)(sceKernelGetProcessTime()/1000));
    if(log_fd>=0){write(log_fd,message,(size_t)n);fsync(log_fd);}
}
/* Phase 10 (J001): a GoldHEN jailbreak when Root is chosen on the loading screen, so Wine can
 * reach the USB disks at /mnt/usbN, which the sandbox does not show. GoldHEN Plugins SDK (MIT,
 * github.com/GoldHEN/GoldHEN_Plugins_SDK): sys_sdk_cmd(cmd, data) is syscall(500, cmd, data)
 * through the indirect syscall 0; command 2 jailbreaks and fills the backup, command 3 restores it. */
struct hw_jailbreak_backup
{
    uint32_t cr_uid,cr_ruid,cr_rgid,cr_groups;
    uint64_t cr_paid,cr_caps[2];
    void *cr_prison,*fd_cdir,*fd_jdir,*fd_rdir;
};
static struct hw_jailbreak_backup jailbreak_backup;
static volatile int jailbroken;
static int boot_root;  /* Root chosen (boot_choose) */
/* the Steam client inside the title (native/steam/steam_client.cpp) logs whether GoldHEN's jailbreak is on */
int pw_hw_root_mode(void);
int pw_hw_root_mode(void) {return jailbroken;}
/* W292: the mode chosen at start, for explorer's Reset item (native/hw_pad.c "<root-mode>") */
int pw_hw_boot_root(void);
int pw_hw_boot_root(void) {return boot_root;}
extern int pw_wine_sigaction(int,const struct sigaction *,struct sigaction *);
static long goldhen_cmd(uint64_t cmd,void *data,int *error)
{
    long ret;unsigned char failed;
    __asm__ volatile("syscall\n\tsetc %1":"=a"(ret),"=q"(failed):"a"(0L),"D"(500L),"S"(cmd),"d"(data)
                     :"rcx","r8","r9","r10","r11","memory","cc");
    *error=failed?(int)ret:0;
    return failed?-1:ret;
}
static void jailbreak_line(const char *message,int n)
{
    if(log_fd>=0&&n>0){__real_write(log_fd,message,(size_t)n);fsync(log_fd);}
}
/* phase 10 hot plug: in ROOT, the USB drive letters follow the disks while Wine runs
 * (platform/ps4/pw_wine_fs.c); polled, every 2 s, until the jailbreak is undone. DVD (J002): the
 * same poll covers L:, the optical disc at /mnt/disc (its slot 8), on insert and eject. */
static void *usb_watch(void *unused)
{
    extern unsigned pw_wine_fs_usb_refresh(void);
    (void)unused;
    while(jailbroken) {
        sceKernelUsleep(2000000);
        if(jailbroken) pw_wine_fs_usb_refresh();
    }
    return NULL;
}
static void pw_hw_unjailbreak(const char *who);
static void pw_hw_jailbreak(void)
{
    struct stat st;struct sigaction ignore,previous;char message[200];int error=0;
    if(jailbroken) return;
    /* without GoldHEN, syscall 500 raises SIGSYS (the crash handler would end the title) */
    memset(&ignore,0,sizeof(ignore));ignore.sa_handler=SIG_IGN;sigemptyset(&ignore.sa_mask);
    int saved=pw_wine_sigaction(SIGSYS,&ignore,&previous);
    memset(&jailbreak_backup,0,sizeof(jailbreak_backup));
    long rc=goldhen_cmd(2,&jailbreak_backup,&error);
    if(!saved) pw_wine_sigaction(SIGSYS,&previous,NULL);
    jailbroken=!rc&&!error;
    errno=0;int usb=stat("/mnt/usb0",&st),usb_errno=usb?errno:0;
    int n=snprintf(message,sizeof(message),HW_BUILD " PWJB jailbreak rc=%ld errno=%d uid=%d mnt_usb0=%d errno=%d\n",
                   rc,error,getuid(),usb,usb_errno);
    jailbreak_line(message,n);
    if(!jailbroken) return;
    /* W228 (W227: "wineserver: lstat .../.wineserver/server-...: Permission denied"): GoldHEN's uid 0
     * does not override file permissions on the console, and Wine's own directories are 0700 of the
     * app's user. Back to that user (the backup's uid); the root directory and prison stay. */
    unsigned own=jailbreak_backup.cr_uid;
    saved=pw_wine_sigaction(SIGSYS,&ignore,&previous);
    errno=0;int id_rc=setuid((uid_t)own),id_errno=id_rc?errno:0;
    if(!saved) pw_wine_sigaction(SIGSYS,&previous,NULL);
    errno=0;int lookup=stat("/data/wine-prefix/.wineserver/pw-root-check",&st),lookup_errno=lookup?errno:0;
    n=snprintf(message,sizeof(message),HW_BUILD " PWJB identity setuid=%u rc=%d errno=%d uid=%d euid=%d wineserver_lookup=%d\n",
               own,id_rc,id_errno,getuid(),geteuid(),lookup_errno);
    jailbreak_line(message,n);
    if(id_rc) {pw_hw_unjailbreak("identity");return;}  /* Wine would stop at its server directory: start as Normal */
    pthread_t watcher;int watch_rc=pthread_create(&watcher,NULL,usb_watch,NULL);
    if(!watch_rc) pthread_detach(watcher);
    n=snprintf(message,sizeof(message),HW_BUILD " PWJB usb_watch rc=%d\n",watch_rc);
    jailbreak_line(message,n);
}
static void pw_hw_unjailbreak(const char *who)
{
    char message[160];int error=0;
    if(!__sync_bool_compare_and_swap(&jailbroken,1,0)) return;
    long rc=goldhen_cmd(3,&jailbreak_backup,&error);
    int n=snprintf(message,sizeof(message),HW_BUILD " PWJB unjailbreak who=%s rc=%ld errno=%d uid=%d\n",who,rc,error,getuid());
    jailbreak_line(message,n);
}
static void return_to_desktop(void);
void __wrap_exit(int status)
{
    record_exit(status,"exit");
    pw_hw_unjailbreak("exit");
    return_to_desktop();
    __real_exit(status);
}
/* W013: libkernel's _exit raised SIGSYS (err=2, at the syscall instruction) on hardware;
 * a retail application is closed by the system instead. The first caller asks for that
 * and waits; if the request fails or nothing happens, the original _exit still runs. */
static void wait_for_system_close(const char *who)
{
    for(int i=0;i<100;i++) sceKernelUsleep(100000);
    char message[96];int n=snprintf(message,sizeof(message),HW_BUILD " system_close_timeout who=%s\n",who);
    if(log_fd>=0&&n>0){__real_write(log_fd,message,(size_t)n);fsync(log_fd);}
}
/* W043: a program started from the desktop runs in a relaunch of this title (see
 * pw_hw_switch_program); when it ends, the title relaunches again into the desktop. */
static int switched;
#define HW_NEXT "/data/orbisdesk/next.txt"
#define HW_SELF "/app0/eboot.bin"
/* W262 (W261: Prince of Persia's launcher starts POP.exe, which needs the launcher's base): the starter's working
 * directory and the variables it set, for the program a switch starts (pw_hw_switch_context, called by ntdll's
 * NtCreateUserProcess hook right before pw_hw_switch_program), beside HW_NEXT */
#define HW_NEXT_CONTEXT "/data/orbisdesk/next-context.txt"
#define MAX_SWITCH_ENV 8
static char switch_dir[400],switch_env[2048];
void pw_hw_switch_context(const char *dir,const char *env);
void pw_hw_switch_context(const char *dir,const char *env)
{
    snprintf(switch_dir,sizeof(switch_dir),"%s",dir?dir:"");
    snprintf(switch_env,sizeof(switch_env),"%s",env?env:"");
}
/* W045: asked from exit(), before atexit handlers and stdio teardown, as the switch into
 * the program is asked from a running title. In W044 it was asked from _exit and, after
 * taskmgr, the title stayed half closed: no new run started and the system menu could
 * not close it. Asked once; the marker is written before the request. */
static void return_to_desktop(void)
{
    static volatile int asked;
    if(!switched || __sync_lock_test_and_set(&asked,1)) return;
    char message[96];int n=snprintf(message,sizeof(message),HW_BUILD " return_to_desktop t_ms=%llu\n",
                                    (unsigned long long)(sceKernelGetProcessTime()/1000));
    if(log_fd>=0&&n>0){__real_write(log_fd,message,(size_t)n);fsync(log_fd);}
    int back=sceSystemServiceLoadExec(HW_SELF,NULL);
    n=snprintf(message,sizeof(message),HW_BUILD " return_to_desktop load_exec rc=0x%08x\n",(unsigned)back);
    if(log_fd>=0&&n>0){__real_write(log_fd,message,(size_t)n);fsync(log_fd);}
    if(!back) wait_for_system_close("return_to_desktop");
}
/* W236: the overlay's Salir (native/hw_overlay.c) in a run that is not the desktop: a program the
 * desktop relaunched the title for (W043) goes back to the desktop, as its own exit would. 0 for the
 * desktop's run, where explorer's kernelbase closes the program in front itself. With ask 0 it only
 * says which run this is. Returns only if the system did not close the title. */
int pw_hw_overlay_exit_title(int ask);
int pw_hw_overlay_exit_title(int ask)
{
    if(!switched) return 0;
    if(!ask) return 1;
    note(HW_BUILD " overlay_exit return_to_desktop\n");
    pw_hw_unjailbreak("overlay");
    return_to_desktop();
    if(boot_root) pw_hw_jailbreak();
    return 1;
}
void __wrap__exit(int status)
{
    static volatile int closing;
    record_exit(status,"_exit");
    pw_hw_unjailbreak("_exit");
    if(__sync_lock_test_and_set(&closing,1)) {wait_for_system_close("_exit");__real__exit(status);}
    return_to_desktop();
    int rc=sceSystemServiceLoadExec("exit",NULL);
    char message[96];int n=snprintf(message,sizeof(message),HW_BUILD " system_close load_exec rc=0x%08x\n",(unsigned)rc);
    if(log_fd>=0&&n>0){__real_write(log_fd,message,(size_t)n);fsync(log_fd);}
    if(!rc) wait_for_system_close("load_exec");
    __real__exit(status);
}
/* W043: a title cannot start a second process. When a program is started from the
 * desktop (Start menu, Run), ntdll's NtCreateUserProcess hands its image and command line
 * here: they are written to HW_NEXT and the title relaunches itself, so the program
 * replaces the desktop until it exits. Returns only on failure, and the caller then
 * fails the process creation. */
/* W265 (W263: PoP's launcher gave POP.exe as the application name and "-007" alone as the command line; Worms 3D's
 * gave "E:\PC\Worms 3D\bin\Worms3D.exe /W 1280 ..." unquoted): whether name[0..length) names the image: its full
 * path, a tail of it after a '\\' or its file name, with or without ".exe", letters in any case */
static char switch_fold(char c){return c=='/'?'\\':(c>='A'&&c<='Z')?(char)(c-'A'+'a'):c;}
static int switch_names_image(const char *image,const char *name,size_t length)
{
    size_t image_length=strlen(image);
    for(int exe=0;length && exe<2;exe++) {
        size_t full=length+(exe?4:0),i;
        if(full>image_length) continue;
        const char *tail=image+image_length-full;
        if(tail!=image && tail[-1]!='\\' && tail[-1]!='/') continue;
        for(i=0;i<full;i++) if(switch_fold(i<length?name[i]:".exe"[i-length])!=switch_fold(tail[i])) break;
        if(i==full) return 1;
    }
    return 0;
}
/* a first token is the program when it names the image, by its path or its file name, or is some ".exe"/".com" */
static int switch_token_is_program(const char *image,const char *name,size_t length)
{
    size_t base=length;
    while(base && name[base-1]!='\\' && name[base-1]!='/' && name[base-1]!=':') --base;
    if(switch_names_image(image,name,length) || switch_names_image(image,name+base,length-base)) return 1;
    return length>4 && name[length-4]=='.' && (switch_names_image(".exe",name+length-4,4) ||
                                              switch_names_image(".com",name+length-4,4));
}
/* how much of the command line is the program's own name; 0 when it does not start with it (with an application
 * name, Windows passes the command line as it is: PoP's "-007" is all arguments) */
static size_t switch_program_name_length(const char *image,const char *command_line)
{
    const char *at=command_line;
    while(*at==' ' || *at=='\t') ++at;
    if(*at=='"') {
        const char *end=strchr(at+1,'"');
        if(end && switch_token_is_program(image,at+1,(size_t)(end-at-1))) return (size_t)(end+1-command_line);
        return 0;
    }
    size_t first=strcspn(at," \t");
    if(switch_token_is_program(image,at,first)) return (size_t)(at+first-command_line);
    /* unquoted with spaces: the shortest prefix ending at a space that is the image path (as CreateProcess resolves
     * an unquoted program path) */
    for(const char *end=at+first;*end;) {
        end+=strspn(end," \t");
        end+=strcspn(end," \t");
        if(switch_names_image(image,at,(size_t)(end-at))) return (size_t)(end-command_line);
    }
    return 0;
}
/* W292: "Reset as Root" / "Reset as Sandbox" (explorer's Start menu, native/hw_pad.c "<reset-root>",
 * "<reset-sandbox>"): the title relaunches itself, as for a program (W043), and the next start takes that
 * mode once without the NORMAL/ROOT screen (boot_choose reads and removes HW_FORCE_MODE). Returns only
 * when that failed. */
#define HW_FORCE_MODE "/data/orbisdesk/force-mode.txt"
static void wait_for_system_close(const char *who);
const char *pw_hw_reset_mode(int root);
const char *pw_hw_reset_mode(int root)
{
    static char reply[128];
    const char *mode=root?"root":"normal";
    if(switched) return "error: not the desktop's run";
    if(!root==!boot_root) {snprintf(reply,sizeof(reply),"error: already in %s mode",root?"ROOT":"NORMAL");return reply;}
    FILE *force=fopen(HW_FORCE_MODE,"w");
    if(!force) {
        snprintf(reply,sizeof(reply),"error: cannot write %s (errno %d)",HW_FORCE_MODE,errno);
        note(HW_BUILD " PWROOT reset to=%s open_failed errno=%d\n",mode,errno);
        return reply;
    }
    int written=fprintf(force,"%s\n",mode)>0;
    if(fclose(force) || !written) {
        snprintf(reply,sizeof(reply),"error: cannot write %s (errno %d)",HW_FORCE_MODE,errno);
        note(HW_BUILD " PWROOT reset to=%s write_failed errno=%d\n",mode,errno);
        unlink(HW_FORCE_MODE);
        return reply;
    }
    note(HW_BUILD " PWROOT reset to=%s relaunch t_ms=%llu\n",mode,(unsigned long long)(sceKernelGetProcessTime()/1000));
    pw_hw_unjailbreak("reset");
    int rc=sceSystemServiceLoadExec(HW_SELF,NULL);
    note(HW_BUILD " PWROOT reset to=%s load_exec rc=0x%08x\n",mode,(unsigned)rc);
    if(rc) {
        unlink(HW_FORCE_MODE);
        if(boot_root) pw_hw_jailbreak();
        snprintf(reply,sizeof(reply),"error: the relaunch was refused (0x%08x)",(unsigned)rc);
        return reply;
    }
    wait_for_system_close("reset");
    unlink(HW_FORCE_MODE);
    if(boot_root) pw_hw_jailbreak();
    note(HW_BUILD " PWROOT reset to=%s still_running\n",mode);
    snprintf(reply,sizeof(reply),"error: the system did not close the title; close OrbisDesk and choose %s on its start screen",
             root?"ROOT":"NORMAL");
    return reply;
}
int pw_hw_switch_program(const char *image,const char *command_line)
{
    enum {MAX_SWITCH_ARGS=16};  /* W265: was 6 (Worms 3D: /W 1280 /H 720 /FS /REFRESH 60) */
    FILE *next=fopen(HW_NEXT,"w");
    if(!next) {note(HW_BUILD " switch_program open_failed errno=%d\n",errno);return -1;}
    fprintf(next,"%s\n",image);
    /* W265: the program's own name, when the command line starts with it, then its arguments, split as the
     * Microsoft C runtime splits them (CommandLineToArgvW); Wine quotes them again when it rebuilds the command line */
    size_t name_length=switch_program_name_length(image,command_line);
    note(HW_BUILD " switch_program program_name=%.*s\n",(int)(name_length<200?name_length:200),command_line);
    const char *at=command_line+name_length;int args=0;
    while(args<MAX_SWITCH_ARGS) {
        while(*at==' ' || *at=='\t') ++at;
        if(!*at) break;
        char word[300];size_t n=0;int quoted=0;
        while(*at && (quoted || (*at!=' ' && *at!='\t'))) {
            size_t slashes=0;
            while(*at=='\\') {++slashes;++at;}
            if(*at=='"') {
                for(size_t i=0;i<slashes/2;i++) if(n<sizeof(word)-1) word[n++]='\\';
                if(slashes%2) {if(n<sizeof(word)-1) word[n++]='"';++at;}
                else if(quoted && at[1]=='"') {if(n<sizeof(word)-1) word[n++]='"';at+=2;}
                else {quoted=!quoted;++at;}
            } else {
                for(size_t i=0;i<slashes;i++) if(n<sizeof(word)-1) word[n++]='\\';
                if(*at && (quoted || (*at!=' ' && *at!='\t'))) {if(n<sizeof(word)-1) word[n++]=*at;++at;}
            }
        }
        word[n]=0;
        if(!n) continue;  /* an empty argument ("") has no line of its own in HW_NEXT */
        fprintf(next,"%s\n",word);++args;
        note(HW_BUILD " switch_program arg=%.200s\n",word);
    }
    fclose(next);
    /* W262: the starter's working directory and variables, when ntdll handed them */
    unlink(HW_NEXT_CONTEXT);
    if(switch_dir[0] || switch_env[0]) {
        FILE *context=fopen(HW_NEXT_CONTEXT,"w");int envs=0,written=context!=NULL;
        if(context) {
            if(switch_dir[0]) fprintf(context,"dir=%s\n",switch_dir);
            for(const char *at=switch_env;*at;) {
                const char *end=strchr(at,'\n');size_t n=end?(size_t)(end-at):strlen(at);
                if(n && envs<MAX_SWITCH_ENV) {
                    fprintf(context,"env=%.*s\n",(int)n,at);++envs;
                    note(HW_BUILD " switch_context env=%.*s\n",(int)(n<200?n:200),at);
                }
                at+=n+(end?1:0);
            }
            fclose(context);
        }
        note(HW_BUILD " switch_context dir=%s envs=%d written=%d\n",switch_dir,envs,written);
    }
    note(HW_BUILD " switch_program command=%.200s\n",command_line);
    note(HW_BUILD " switch_program image=%s args=%d t_ms=%llu\n",image,args,(unsigned long long)(sceKernelGetProcessTime()/1000));
    pw_hw_unjailbreak("switch_program");
    int rc=sceSystemServiceLoadExec(HW_SELF,NULL);
    note(HW_BUILD " switch_program load_exec rc=0x%08x\n",(unsigned)rc);
    if(rc) {if(boot_root) pw_hw_jailbreak();unlink(HW_NEXT);unlink(HW_NEXT_CONTEXT);return -1;}
    wait_for_system_close("switch_program");
    unlink(HW_NEXT);
    unlink(HW_NEXT_CONTEXT);
    return -1;
}
/* W170: the loading screen. Black, the app logo (the PS4-shaped window of
 * tools/make-app-icon.py, same 512-unit geometry) and a green bar at the real boot stage:
 * the launcher's own steps, then Wine's PWBOOT markers as they reach the run log
 * (boot_marker). ps5drv's "PWBOOT gpu_layers=" line comes before its first frame: the bar is
 * drawn full there and never again. Each stage is one frame (the sink dumps changed frames). */
static pthread_mutex_t screen_lock=PTHREAD_MUTEX_INITIALIZER;
static volatile int screen_handed;
static int boot_percent;
typedef struct {float x,y;} LogoPoint;
static int logo_inside(const LogoPoint *p,float x,float y)
{
    int c=0;
    for(int i=0,j=3;i<4;j=i++)
        if((p[i].y>y)!=(p[j].y>y)&&x<p[j].x+(y-p[j].y)*(p[i].x-p[j].x)/(p[i].y-p[j].y))c=!c;
    return c;
}
static float logo_groove(float x){return 196.0f+0.1376f*(x-180.0f);}
static uint32_t logo_mix(uint32_t a,uint32_t b,float t)
{
    if(t<0)t=0;
    if(t>1)t=1;
    uint32_t out=0xff000000;
    for(int s=0;s<24;s+=8){float ca=(float)((a>>s)&255),cb=(float)((b>>s)&255);out|=(uint32_t)(ca+(cb-ca)*t+0.5f)<<s;}
    return out;
}
/* the logo with its top-left design corner (122,64) at left,top; scale: pixels per unit */
static void draw_logo(int left,int top,float scale)
{
    enum {L0=122,L1=166,R0=180,R1=392,TOP=64,TOP_R=112,FOOT=456,BASE_L=438,BASE_R=428};
    const float half=7;
    const LogoPoint panes[5][4]={
        {{L0,logo_groove(L0)-2},{R1,logo_groove(R1)-2},{R1,logo_groove(R1)+2},{L0,logo_groove(L0)+2}},  /* light bar */
        {{L0,TOP+6},{L1,TOP},{L1,logo_groove(L1)-half},{L0,logo_groove(L0)-half}},                         /* side, upper */
        {{L0,logo_groove(L0)+half},{L1,logo_groove(L1)+half},{L1,BASE_L},{L0,FOOT}},                       /* side, lower */
        {{R0,TOP},{R1,TOP_R},{R1,logo_groove(R1)-half},{R0,logo_groove(R0)-half}},                         /* face, upper */
        {{R0,logo_groove(R0)+half},{R1,logo_groove(R1)+half},{R1,BASE_R},{R0,BASE_L}}};                    /* face, lower */
    const uint32_t from[5]={0xffc8f0ff,0xff3a9cf0,0xff155cb8,0xff62c4ff,0xff2380ea};
    const uint32_t to[5]={0xffc8f0ff,0xff1866c4,0xff0a3d8a,0xff2a8af0,0xff0d4fb0};
    const float y0[5]={0,TOP,logo_groove(L0),TOP,logo_groove(R0)},y1[5]={1,logo_groove(L0),FOOT,logo_groove(R1),BASE_L};
    int width=(int)((R1-L0)*scale)+2,height=(int)((FOOT-TOP)*scale)+2;
    for(int py=0;py<height;py++)for(int px=0;px<width;px++){
        float r=0,g=0,b=0;
        for(int sy=0;sy<4;sy++)for(int sx=0;sx<4;sx++){
            float x=L0+(px+(sx+0.5f)/4)/scale,y=TOP+(py+(sy+0.5f)/4)/scale;uint32_t c=0;
            for(int i=0;i<5;i++)if(logo_inside(panes[i],x,y))c=logo_mix(from[i],to[i],(y-y0[i])/(y1[i]-y0[i]));
            r+=(c>>16)&255;g+=(c>>8)&255;b+=c&255;
        }
        int sx=left+px,sy=top+py;
        if(sx>=0&&sx<WIDTH&&sy>=0&&sy<HEIGHT)
            pixels[sy*WIDTH+sx]=0xff000000|(uint32_t)(r/16+0.5f)<<16|(uint32_t)(g/16+0.5f)<<8|(uint32_t)(b/16+0.5f);
    }
}
static void centred_text(int y,const char *text,uint32_t color,int scale)
{
    hw_text(pixels,WIDTH,HEIGHT,(WIDTH-((int)strlen(text)*6-1)*scale)/2,y,text,color,scale);
}
/* screen_lock held; percent<0: no bar (a stop screen) */
static void draw_screen(int percent,const char *state,const char *detail)
{
    if(!pixels)pixels=malloc(WIDTH*HEIGHT*4);
    if(!pixels)return;
    for(int i=0;i<WIDTH*HEIGHT;i++)pixels[i]=0xff000000;
    draw_logo(WIDTH/2-81,110,0.6f);
    centred_text(370,"ORBISDESK",0xffffffff,4);
    if(percent>=0){
        enum {BAR_X=390,BAR_Y=450,BAR_W=500,BAR_H=12};
        int fill=BAR_W*percent/100;char label[16];
        for(int y=0;y<BAR_H;y++)for(int x=0;x<BAR_W;x++)
            pixels[(BAR_Y+y)*WIDTH+BAR_X+x]=x<fill?(y<BAR_H/2?0xff5be36a:0xff2ebd40):0xff1e1e1e;
        snprintf(label,sizeof(label),"%d%%",percent);
        hw_text(pixels,WIDTH,HEIGHT,BAR_X+BAR_W+16,BAR_Y-1,label,0xffb0b0b0,2);
        centred_text(484,state,0xff8a8a8a,2);
    } else {
        centred_text(450,state,0xffff6a6a,3);
        centred_text(500,detail,0xffffffff,2);
        centred_text(560,"IF THE APP CLOSES - REPORT BACK",0xff8a8a8a,2);
        centred_text(590,"LOGS: /DATA/ORBISDESK",0xff8a8a8a,2);
    }
    pw_wine_present(pixels,WIDTH,HEIGHT,WIDTH*4);
}
static void loading(int percent,const char *state)
{
    pthread_mutex_lock(&screen_lock);
    if(!screen_handed&&percent>boot_percent){boot_percent=percent;draw_screen(percent,state,NULL);}
    if(percent>=100)screen_handed=1;
    pthread_mutex_unlock(&screen_lock);
}
static void panel(const char *state,const char *detail)
{
    pthread_mutex_lock(&screen_lock);
    draw_screen(-1,state,detail);
    pthread_mutex_unlock(&screen_lock);
}
/* Phase 10: NORMAL (the sandbox, left, chosen) or ROOT (the GoldHEN jailbreak, USB disks as
 * D:..K:) under the logo, on the loading screen before Wine starts */
#define HW_BOOT_MODE "/data/orbisdesk/boot-mode.txt"
static void draw_choice(int root,int tenths)
{
    static const char *const names[2]={"NORMAL","ROOT"};
    enum {BOX_W=220,BOX_H=56,BOX_Y=440,GAP=40,SCALE=3};
    char hint[64];
    pthread_mutex_lock(&screen_lock);
    if(!pixels)pixels=malloc(WIDTH*HEIGHT*4);
    if(pixels){
        for(int i=0;i<WIDTH*HEIGHT;i++)pixels[i]=0xff000000;
        draw_logo(WIDTH/2-81,110,0.6f);
        centred_text(370,"ORBISDESK",0xffffffff,4);
        for(int i=0;i<2;i++){
            int x0=WIDTH/2-BOX_W-GAP/2+i*(BOX_W+GAP),selected=i==root;
            uint32_t edge=selected?0xff5be36a:0xff404040,fill=selected?0xff1e3a22:0xff141414;
            for(int y=0;y<BOX_H;y++)for(int x=0;x<BOX_W;x++)
                pixels[(BOX_Y+y)*WIDTH+x0+x]=(y<3||y>=BOX_H-3||x<3||x>=BOX_W-3)?edge:fill;
            int text_w=((int)strlen(names[i])*6-1)*SCALE;
            hw_text(pixels,WIDTH,HEIGHT,x0+(BOX_W-text_w)/2,BOX_Y+(BOX_H-7*SCALE)/2,names[i],selected?0xffffffff:0xff8a8a8a,SCALE);
        }
        snprintf(hint,sizeof(hint),"LEFT - RIGHT: CHOOSE    X: START    %d.%d",tenths/10,tenths%10);
        centred_text(520,hint,0xff8a8a8a,2);
        centred_text(550,root?"ROOT: GOLDHEN JAILBREAK - USB DISKS AS D: TO K:":"NORMAL: THE APP SANDBOX - NO USB DISKS",0xff8a8a8a,2);
        hw_text(pixels,WIDTH,HEIGHT,24,HEIGHT-30,"VERSION " HW_VERSION " (" HW_BUILD ")",0xff404040,2);
        pw_wine_present(pixels,WIDTH,HEIGHT,WIDTH*4);
    }
    pthread_mutex_unlock(&screen_lock);
}
static void boot_choose(void)
{
    extern int pw_hw_pad_handle(void);  /* native/hw_pad.c: opened once, shared with its input thread */
    struct stat st;
    /* W292: "Reset as Root" / "Reset as Sandbox" (pw_hw_reset_mode): that mode once, without the screen */
    if(!stat(HW_FORCE_MODE,&st)) {
        char mode[16]={0};FILE *file=fopen(HW_FORCE_MODE,"r");
        if(file){if(!fgets(mode,sizeof(mode),file))mode[0]=0;fclose(file);}
        int removed=unlink(HW_FORCE_MODE);
        int root=!strncmp(mode,"root",4),normal=!strncmp(mode,"normal",6);
        note(HW_BUILD " PWROOT force_mode=%.8s removed=%d\n",(root||normal)?mode:"(unknown)",removed);
        if(root||normal) {
            boot_root=root;
            file=fopen(HW_BOOT_MODE,"w");
            if(file){fputs(root?"root\n":"normal\n",file);fclose(file);}
            note(HW_BUILD " PWJB mode=%s source=reset\n",root?"root":"normal");
            return;
        }
    }
    /* a program started from the desktop relaunches the title (W043): it keeps the first start's mode */
    if(!stat(HW_NEXT,&st)) {
        char mode[16]={0};FILE *file=fopen(HW_BOOT_MODE,"r");
        if(file){if(!fgets(mode,sizeof(mode),file))mode[0]=0;fclose(file);}
        boot_root=!strncmp(mode,"root",4);
        note(HW_BUILD " PWJB mode=%s source=relaunch\n",boot_root?"root":"normal");
        return;
    }
    enum {WINDOW_US=2500000,POLL_US=16000};
    int handle=pw_hw_pad_handle(),root=0,confirmed=0,changes=0,first=1,shown=-1,shown_tenths=-1;
    uint64_t start=sceKernelGetProcessTime(),deadline=start+WINDOW_US,now=start;uint32_t held=0;
    while(handle>=0 && (now=sceKernelGetProcessTime())<deadline) {
        OrbisPadData data;memset(&data,0,sizeof(data));
        if(!scePadReadState(handle,&data) && data.connected) {
            /* the first read only records what is held: the X that opened the app does not count */
            uint32_t pressed=first?0:data.buttons&~held;held=data.buttons;first=0;
            int want=root;
            if((data.buttons&ORBIS_PAD_BUTTON_RIGHT) || data.leftStick.x>200) want=1;
            if((data.buttons&ORBIS_PAD_BUTTON_LEFT) || data.leftStick.x<56) want=0;
            if(want!=root) {root=want;++changes;deadline=now+WINDOW_US;}
            if(pressed&ORBIS_PAD_BUTTON_CROSS) {confirmed=1;break;}
        }
        int tenths=(int)((deadline-now+99999)/100000);
        if(root!=shown || tenths!=shown_tenths) {draw_choice(root,tenths);shown=root;shown_tenths=tenths;}
        sceKernelUsleep(POLL_US);
    }
    boot_root=root;
    FILE *file=fopen(HW_BOOT_MODE,"w");
    if(file){fputs(root?"root\n":"normal\n",file);fclose(file);}
    note(HW_BUILD " PWJB mode=%s source=screen pad=0x%08x confirmed=%d changes=%d waited_ms=%llu\n",root?"root":"normal",
         (unsigned)handle,confirmed,changes,(unsigned long long)((sceKernelGetProcessTime()-start)/1000));
    pthread_mutex_lock(&screen_lock);
    if(!screen_handed) draw_screen(boot_percent,"PREPARING WINE",NULL);
    pthread_mutex_unlock(&screen_lock);
}

/* a run-log line from Wine: the boot stages it marks. Never one the sink writes under its
 * own lock (PWSINK), since loading() presents. */
static void boot_marker(const void *buffer,size_t bytes)
{
    static const struct {const char *text;int percent;const char *state;} marks[]={
        {"PWBOOT server_ready",55,"WINE SERVER READY"},
        {"PWBOOT static_unixlib /data/wine/lib/wine/x86_64-unix/win32u.so",80,"LOADING THE DESKTOP"},
        {"PWBOOT gpu_layers=",100,"STARTING THE DESKTOP"}};
    if(screen_handed||bytes<7||memcmp(buffer,"PWBOOT ",7))return;
    for(unsigned i=0;i<sizeof(marks)/sizeof(marks[0]);i++){
        size_t length=strlen(marks[i].text);
        if(bytes>=length&&!memcmp(buffer,marks[i].text,length)){loading(marks[i].percent,marks[i].state);return;}
    }
}

/* PWBOOT progress markers use the kernel debug channel, invisible on retail hardware;
 * mirror them into the run log as well. */
extern int __real_sceKernelDebugOutText(int,const char *);
int __wrap_sceKernelDebugOutText(int channel,const char *text)
{
    if(log_fd>=0&&text){write(log_fd,text,strlen(text));boot_marker(text,strlen(text));}
    return __real_sceKernelDebugOutText(channel,text);
}

/* A retail PS4 application has no usable fd 1/2 and cannot dup2 onto them (EPERM,
 * W002). Wine reports its progress with fprintf(stderr) and write(2), so the link
 * wraps those entry points and sends console output to the run log instead. */
extern ssize_t __real_write(int,const void *,size_t);
static int console_fd(int fd){return (fd==STDOUT_FILENO||fd==STDERR_FILENO)&&log_fd>=0&&!stderr_redirected;}
ssize_t __wrap_write(int fd,const void *buffer,size_t bytes)
{
    if(!console_fd(fd))return __real_write(fd,buffer,bytes);
    ssize_t written=__real_write(log_fd,buffer,bytes);
    boot_marker(buffer,bytes);
    return written;
}
static int console_stream(FILE *stream){return (stream==stdout||stream==stderr)&&log_fd>=0&&!stderr_redirected;}
extern int __real_vfprintf(FILE *,const char *,va_list);
int __wrap_vfprintf(FILE *stream,const char *format,va_list ap)
{
    if(!console_stream(stream))return __real_vfprintf(stream,format,ap);
    char text[4096];int n=vsnprintf(text,sizeof(text),format,ap);
    if(n<0)return n;
    __wrap_write(STDERR_FILENO,text,(size_t)(n<(int)sizeof(text)?n:(int)sizeof(text)-1));return n;
}
int __wrap_fprintf(FILE *stream,const char *format,...)
{
    va_list ap;va_start(ap,format);int n=__wrap_vfprintf(stream,format,ap);va_end(ap);return n;
}
extern int __real_fputs(const char *,FILE *);
int __wrap_fputs(const char *text,FILE *stream)
{
    if(!console_stream(stream))return __real_fputs(text,stream);
    return __wrap_write(STDERR_FILENO,text,strlen(text))<0?EOF:0;
}
extern size_t __real_fwrite(const void *,size_t,size_t,FILE *);
size_t __wrap_fwrite(const void *data,size_t size,size_t count,FILE *stream)
{
    if(!console_stream(stream))return __real_fwrite(data,size,count,stream);
    if(!size||!count)return 0;
    return __wrap_write(STDERR_FILENO,data,size*count)<0?0:count;
}

/* Before Wine installs its own handlers a fault ends the app with only CE-34878-0
 * on screen. Record the signal and the faulting context, then exit. */
extern int pw_wine_sigaction(int,const struct sigaction *,struct sigaction *);
static void crash_handler(int signal,siginfo_t *info,void *raw)
{
    (void)info;const PwOrbisMcontext *mc=&((const PwOrbisUcontext *)raw)->uc_mcontext;
    char text[320];int n=snprintf(text,sizeof(text),HW_BUILD " crash signal=%d code=%d trapno=%u err=0x%llx addr=0x%llx rip=0x%llx rsp=0x%llx rax=0x%llx rdi=0x%llx ret=0x%llx main=%p\n",
        signal,info?info->si_code:-1,mc->mc_trapno,(unsigned long long)mc->mc_err,(unsigned long long)mc->mc_addr,
        (unsigned long long)mc->mc_rip,(unsigned long long)mc->mc_rsp,(unsigned long long)mc->mc_rax,
        (unsigned long long)mc->mc_rdi,(unsigned long long)*(const uint64_t *)(uintptr_t)mc->mc_rsp,(void *)&main);
    if(log_fd>=0&&n>0){__real_write(log_fd,text,(size_t)n);fsync(log_fd);}
    pw_hw_unjailbreak("crash");
    /* A refused syscall (SIGSYS) would be refused again by _exit; let the system close the app. */
    if(signal==SIGSYS) {wait_for_system_close("sigsys");}
    __real__exit(0x80+signal);
}
static void install_crash_handler(void)
{
    static const int signals[]={SIGSEGV,SIGBUS,SIGILL,SIGFPE,SIGSYS,SIGTRAP,SIGABRT};
    struct sigaction action;memset(&action,0,sizeof(action));
    action.sa_sigaction=crash_handler;action.sa_flags=SA_SIGINFO;sigemptyset(&action.sa_mask);
    for(unsigned i=0;i<sizeof(signals)/sizeof(signals[0]);i++){
        errno=0;int rc=pw_wine_sigaction(signals[i],&action,NULL);
        note(HW_BUILD " crash_handler signal=%d rc=%d errno=%d\n",signals[i],rc,rc?errno:0);
    }
}

/* Alpha-1 trace switch (platform/ps4/pw_trace.h): the build's default, then /data/orbisdesk/trace.txt.
 * Present and empty or "1": traces on; "0": off. The answer reaches Wine as PW_TRACE (main). */
static void trace_setup(void)
{
    const char *source="build";
    pw_trace_level=!ORBIS_RELEASE;
    int fd=open(PW_TRACE_FILE,O_RDONLY);
    if(fd>=0) {
        char text[8]={0};ssize_t n=read(fd,text,sizeof(text)-1);close(fd);
        pw_trace_level=n>0&&text[0]>='0'&&text[0]<='9'?text[0]-'0':1;
        source="trace.txt";
    }
    setenv("PW_TRACE",pw_trace_level?"1":"0",1);
    note(HW_BUILD " trace level=%d source=%s release=%d\n",pw_trace_level,source,ORBIS_RELEASE);
}
/* Platform facts the Wine path layer relies on, each with its own error code. */
static void platform_probes(void)
{
    struct stat st;char text[64],canonical[PATH_MAX];
    errno=0;int rc=lstat("/data/wine-prefix/drive_c",&st);
    note(HW_BUILD " probe libc_lstat rc=%d errno=%d dir=%d\n",rc,rc?errno:0,!rc&&S_ISDIR(st.st_mode));
    errno=0;rc=pw_wine_stat("/data/wine-prefix/drive_c",&st);
    note(HW_BUILD " probe kernel_stat rc=%d errno=%d dir=%d\n",rc,rc?errno:0,!rc&&S_ISDIR(st.st_mode));
    /* W002 died on hardware at a raw readlink probe: links are never queried directly. */
    errno=0;rc=pw_wine_lstat("/data/wine-prefix/drive_c",&st);
    note(HW_BUILD " probe wine_lstat rc=%d errno=%d dir=%d\n",rc,rc?errno:0,!rc&&S_ISDIR(st.st_mode));
    rc=pw_wine_fs_drive_mounts("/data/wine-prefix");
    errno=0;ssize_t n=pw_wine_readlink(0,"/data/wine-prefix/dosdevices/c:",text,sizeof(text));
    note(HW_BUILD " probe drive_c_mount mounts=%d readlink=%zd text=%.*s errno=%d\n",rc,n,n>0?(int)n:0,text,n<0?errno:0);
    errno=0;const char *real=pw_wine_realpath(0,"/data/wine-prefix/dosdevices/c:/orbis/console32.exe",canonical);
    note(HW_BUILD " probe drive_c_resolve ok=%d path=%s errno=%d\n",real!=NULL,real?canonical:"-",real?0:errno);
    /* W009: the wineserver's NLS mapping failed on hardware; it dups the file descriptor. */
    errno=0;int fd=open("/data/wine/share/wine/nls/locale.nls",O_RDONLY);int open_errno=errno;
    errno=0;int copy=fd>=0?dup(fd):-1;int dup_errno=errno;
    errno=0;int above=fd>=0?fcntl(fd,0 /* FreeBSD F_DUPFD */,64):-1;int dupfd_errno=errno;
    note(HW_BUILD " probe fd_dup open=%d errno=%d dup=%d errno=%d f_dupfd=%d errno=%d\n",fd,open_errno,copy,dup_errno,above,dupfd_errno);
    if(above>=0)close(above);if(copy>=0)close(copy);
    /* W011: the Wine client got EINVAL from recvmsg when the server passed a descriptor. */
    int pair[2]={-1,-1};errno=0;int pair_rc=socketpair(AF_UNIX,SOCK_STREAM,0,pair);int pair_errno=errno;
    char byte='x';struct iovec vec={&byte,1};
    union {struct cmsghdr header;char buffer[CMSG_SPACE(sizeof(int))];} control;memset(&control,0,sizeof(control));
    struct msghdr msg;memset(&msg,0,sizeof(msg));msg.msg_iov=&vec;msg.msg_iovlen=1;
    msg.msg_control=&control;msg.msg_controllen=CMSG_SPACE(sizeof(int));
    struct cmsghdr *header=CMSG_FIRSTHDR(&msg);header->cmsg_level=SOL_SOCKET;header->cmsg_type=SCM_RIGHTS;
    header->cmsg_len=CMSG_LEN(sizeof(int));memcpy(CMSG_DATA(header),&fd,sizeof(int));
    errno=0;ssize_t sent=pair_rc?-1:pw_wine_sendmsg(pair[0],&msg,0);int sent_errno=errno;
    char cbuf[256];memset(cbuf,0,sizeof(cbuf));msg.msg_control=cbuf;msg.msg_controllen=sizeof(cbuf);
    errno=0;ssize_t got=sent==1?pw_wine_recvmsg(pair[1],&msg,0):-1;int got_errno=errno;
    int received=-1;
    if(got>0) for(header=CMSG_FIRSTHDR(&msg);header;header=CMSG_NXTHDR(&msg,header))
        if(header->cmsg_level==SOL_SOCKET && header->cmsg_type==SCM_RIGHTS) memcpy(&received,CMSG_DATA(header),sizeof(int));
    errno=0;int getfd=received>=0?fcntl(received,F_GETFD):-1;int getfd_errno=errno;
    errno=0;int setfd=received>=0?fcntl(received,F_SETFD,FD_CLOEXEC):-1;int setfd_errno=errno;
    struct stat a,b;int same=received>=0 && !pw_wine_fstat(fd,&a) && !pw_wine_fstat(received,&b) && a.st_ino==b.st_ino && a.st_dev==b.st_dev;
    note(HW_BUILD " probe scm_rights pair=%d errno=%d send=%zd errno=%d recv=%zd errno=%d controllen=%u fd=%d same=%d getfd=%d errno=%d setfd=%d errno=%d\n",
         pair_rc,pair_errno,sent,sent_errno,got,got_errno,(unsigned)msg.msg_controllen,received,same,getfd,getfd_errno,setfd,setfd_errno);
    errno=0;ssize_t cloexec=-1;int cloexec_errno=0,second=-1;
    if(sent==1) {
        msg.msg_control=&control;msg.msg_controllen=CMSG_SPACE(sizeof(int));
        if(pw_wine_sendmsg(pair[0],&msg,0)==1) {
            msg.msg_control=cbuf;msg.msg_controllen=sizeof(cbuf);
            errno=0;cloexec=pw_wine_recvmsg(pair[1],&msg,MSG_CMSG_CLOEXEC);cloexec_errno=errno;
            if(cloexec>0) for(header=CMSG_FIRSTHDR(&msg);header;header=CMSG_NXTHDR(&msg,header))
                if(header->cmsg_level==SOL_SOCKET && header->cmsg_type==SCM_RIGHTS) memcpy(&second,CMSG_DATA(header),sizeof(int));
        }
    }
    note(HW_BUILD " probe scm_rights_cloexec recv=%zd errno=%d fd=%d\n",cloexec,cloexec_errno,second);
    /* W015: on hardware every caption was drawn with Marlett glyphs. win32u maps font
     * files read-only and private; check that for each staged font. W016 showed the
     * mappings work; W018 leaves the probe out because Wine then stopped in virtual_init. */
#ifdef HW_FONT_MAP_PROBE
    static const char *const fonts[]={"tahoma.ttf","tahomabd.ttf","marlett.ttf"};
    for(unsigned i=0;i<sizeof(fonts)/sizeof(fonts[0]);i++) {
        char font[96];snprintf(font,sizeof(font),"/data/wine-prefix/drive_c/windows/Fonts/%s",fonts[i]);
        errno=0;int ffd=open(font,O_RDONLY);int open_errno=errno;struct stat fst;
        int size=ffd>=0 && !pw_wine_fstat(ffd,&fst)?(int)fst.st_size:-1;
        errno=0;void *map=ffd>=0 && size>0?mmap(NULL,(size_t)size,PROT_READ,MAP_PRIVATE,ffd,0):MAP_FAILED;int map_errno=errno;
        unsigned magic=0;if(map!=MAP_FAILED){memcpy(&magic,map,sizeof(magic));munmap(map,(size_t)size);}
        note(HW_BUILD " probe font_map file=%s open=%d errno=%d size=%d map=%d errno=%d magic=%08x\n",
             fonts[i],ffd,open_errno,size,map!=MAP_FAILED,map==MAP_FAILED?map_errno:0,magic);
        if(ffd>=0)close(ffd);
    }
#endif
    /* W012: fcntl gave EINVAL even for F_GETFD. Wine also sets O_NONBLOCK through F_SETFL. */
    for(int i=0;i<2;++i) {
        int target=i?pair[0]:fd;
        errno=0;int getfl=fcntl(target,F_GETFL);int getfl_errno=errno;
        errno=0;int setfl=fcntl(target,F_SETFL,O_NONBLOCK);int setfl_errno=errno;
        int on=1;errno=0;int nbio=ioctl(target,FIONBIO,&on);int nbio_errno=errno;
        note(HW_BUILD " probe nonblock target=%s getfl=%d errno=%d setfl=%d errno=%d fionbio=%d errno=%d\n",
             i?"socket":"file",getfl,getfl_errno,setfl,setfl_errno,nbio,nbio_errno);
    }
    /* W019: Wine died in a MAP_FIXED of its own reservation at the top of the user
     * address space; record what the kernel has there and the flexible memory left. */
    size_t flexible=0;
    int flex_rc=((int (*)(size_t *))(uintptr_t)&sceKernelAvailableFlexibleMemorySize)(&flexible);
    note(HW_BUILD " probe flexible_memory rc=0x%08x available=%zu\n",(unsigned)flex_rc,flexible);
    const char *cursor=(const char *)0x7ff000000000;
    for(int i=0;i<8;i++) {
        OrbisKernelVirtualQueryInfo info;memset(&info,0,sizeof(info));
        int q=sceKernelVirtualQuery(cursor,1,&info,sizeof(info));
        if(q) {note(HW_BUILD " probe top_region rc=0x%08x\n",(unsigned)q);break;}
        note(HW_BUILD " probe top_region start=%p end=%p prot=%d type=%d flex=%u direct=%u stack=%u committed=%u name=%.32s\n",
             info.unk01,info.unk02,info.unk04,info.unk05,info.isFlexibleMemory,info.isDirectMemory,info.isStack,info.isCommitted,info.name);
        if((const char *)info.unk02<=cursor) break;
        cursor=(const char *)info.unk02;
    }
    if(second>=0)close(second);if(received>=0)close(received);
    if(pair[0]>=0)close(pair[0]);if(pair[1]>=0)close(pair[1]);if(fd>=0)close(fd);
}

/* W130: the folder of a program started on its own, passed to Wine as PW_PROGRAM_DIR: the title
 * may not chdir (W129: EPERM), and ntdll's initial directory (tools/build-env-ps4.py) takes it
 * before the Unix cwd, so the program starts in its folder as Explorer would. */
static char program_cwd[400],program_dir_env[430];

/* Phase 10: a Windows path as a Unix one: C: is the prefix's drive_c, D:..K: the USB disks at
 * /mnt/usb0..7 and L: the optical disc at /mnt/disc (platform/ps4/pw_wine_fs.c, seen after the
 * jailbreak); S5: Z: is the prefix's parent, /data, where the Steam title (ORBS00001) installs games
 * as Z:\orbisdesk\steam-games\<app>\. 0 for any other drive. */
static int windows_unix_path(const char *windows_path,char *out,size_t size)
{
    char drive=(char)(windows_path[0]|0x20);size_t n;
    if(windows_path[1]!=':') return 0;
    if(drive=='c') n=(size_t)snprintf(out,size,"/data/wine-prefix/drive_c");
    else if(drive>='d' && drive<='k') n=(size_t)snprintf(out,size,"/mnt/usb%d",drive-'d');
    else if(drive=='l') n=(size_t)snprintf(out,size,"/mnt/disc");
    else if(drive=='z') n=(size_t)snprintf(out,size,"/data");
    else return 0;
    for(const char *at=windows_path+2;*at && n<size-1;++at) out[n++]=*at=='\\'?'/':*at;
    out[n]=0;return 1;
}

/* W116: the PE machine of a program given by its Windows path on drive C: (phase 10: or D:..K:),
 * or 0 with the reason in the log (not found, not a PE). */
static int pe_machine(const char *windows_path)
{
    char path[400];
    if(!windows_unix_path(windows_path,path,sizeof(path))) {
        note(HW_BUILD " pe_machine unsupported_path=%s\n",windows_path);return 0;
    }
    int fd=open(path,O_RDONLY);
    if(fd<0) {note(HW_BUILD " pe_machine open_failed path=%s errno=%d\n",path,errno);return 0;}
    unsigned char header[64],signature[6];uint32_t offset=0;int machine=0;
    if(read(fd,header,sizeof(header))==(ssize_t)sizeof(header) && header[0]=='M' && header[1]=='Z') {
        memcpy(&offset,header+60,4);
        if(lseek(fd,offset,SEEK_SET)==(off_t)offset && read(fd,signature,sizeof(signature))==(ssize_t)sizeof(signature) &&
           !memcmp(signature,"PE\0\0",4)) machine=signature[4]|signature[5]<<8;
    }
    close(fd);
    note(HW_BUILD " pe_machine path=%s machine=0x%x\n",path,(unsigned)machine);
    return machine;
}

/* W226: the build's system.reg keys that the live one lacks (wine-prefix/system.reg.build, written
 * by tools/build-wine-hardware.py), appended before Wine starts. W225's upload replaced system.reg,
 * but a Wine started during the upload saved its old registry back over it and DirectShow's
 * classes never reached the prefix. Keys the console has are not touched. */
/* W230: to the end of the file, without a size from fstat: the SDK libc's struct stat does not
 * match the kernel's, and W229 read 3 KB of each registry and wrote a 5 KB system.reg */
static char *read_whole(const char *path,size_t *size)
{
    int fd=open(path,O_RDONLY);
    if(fd<0) return NULL;
    size_t got=0,capacity=1<<20;
    char *data=malloc(capacity+1);
    while(data) {
        if(got==capacity) {
            char *grown=realloc(data,capacity*2+1);
            if(!grown) {free(data);data=NULL;break;}
            data=grown;capacity*=2;
        }
        ssize_t n=read(fd,data+got,capacity-got);
        if(n<0) {free(data);data=NULL;break;}
        if(!n) break;
        got+=(size_t)n;
    }
    close(fd);
    if(!data) return NULL;
    data[got]=0;*size=got;return data;
}
struct reg_key { const char *name; size_t len; };
static uint64_t reg_key_hash(const char *name,size_t len)
{
    uint64_t h=1469598103934665603ull;
    for(size_t i=0;i<len;i++){unsigned char c=(unsigned char)name[i];if(c>='A'&&c<='Z')c+=32;h=(h^c)*1099511628211ull;}
    return h;
}
static int reg_key_equal(const struct reg_key *a,const char *name,size_t len)
{
    if(a->len!=len) return 0;
    for(size_t i=0;i<len;i++){
        unsigned char x=(unsigned char)a->name[i],y=(unsigned char)name[i];
        if(x>='A'&&x<='Z')x+=32;
        if(y>='A'&&y<='Z')y+=32;
        if(x!=y) return 0;
    }
    return 1;
}
/* the key of a "[key] stamp" line at p, or 0 */
static size_t reg_key_at(const char *p,const char **name)
{
    if(*p!='[') return 0;
    const char *end=strchr(p,']'),*nl=strchr(p,'\n');
    if(!end || (nl && nl<end)) return 0;
    *name=p+1;return (size_t)(end-p-1);
}
static void merge_system_reg(void)
{
    static const char live_path[]="/data/wine-prefix/system.reg",build_path[]="/data/wine-prefix/system.reg.build",
                      temp_path[]="/data/wine-prefix/system.reg.merge",marker_path[]=HW_DIR "/system-reg-merged.txt";
    /* once per build: Wine does not save every key back (value-less parents, device keys it
     * enumerates again), and merging those at each start would rewrite system.reg each time */
    int marker=open(marker_path,O_RDONLY);
    if(marker>=0) {close(marker);note(HW_BUILD " system_reg_merge already_done\n");return;}
    size_t live_size=0,build_size=0;
    char *build=read_whole(build_path,&build_size),*live=build?read_whole(live_path,&live_size):NULL;
    if(!build || !live || strncmp(live,"WINE REGISTRY Version 2",23) || strncmp(build,"WINE REGISTRY Version 2",23)) {
        note(HW_BUILD " system_reg_merge skipped build=%s live=%s\n",build?"read":"absent",live?"read":"absent");
        free(build);free(live);return;
    }
    /* the live keys, in an open-addressed table */
    unsigned live_keys=0,build_keys=0,added=0;
    size_t slots=1;
    unsigned build_lines=0;
    for(const char *p=live;p;p=strchr(p,'\n')) {if(*p=='\n')p++;if(*p=='[')live_keys++;}
    for(const char *p=build;p;p=strchr(p,'\n')) {if(*p=='\n')p++;if(*p=='[')build_lines++;}
    /* W230: room for the live keys and every build key it may add; sized for the live ones
     * only, a small live file and a large build one filled the table and the probe never ended */
    while(slots<((size_t)live_keys+build_lines)*2+16) slots<<=1;
    struct reg_key *table=calloc(slots,sizeof(*table));
    char *out=table?malloc(live_size+build_size+2):NULL;
    if(!out) {note(HW_BUILD " system_reg_merge no_memory\n");free(table);free(build);free(live);return;}
    for(const char *p=live;p && *p;) {
        const char *name;size_t len=reg_key_at(p,&name);
        if(len) {
            size_t i=(size_t)reg_key_hash(name,len)&(slots-1);
            while(table[i].name && !reg_key_equal(&table[i],name,len)) i=(i+1)&(slots-1);
            table[i].name=name;table[i].len=len;
        }
        p=strchr(p,'\n');if(p)p++;
    }
    memcpy(out,live,live_size);size_t used=live_size;
    if(used && out[used-1]!='\n') out[used++]='\n';
    /* each build block runs from its key line to the next key line */
    for(const char *p=build;p && *p;) {
        const char *name;size_t len=reg_key_at(p,&name);
        const char *next=strchr(p,'\n');next=next?next+1:p+strlen(p);
        if(!len) {p=next;continue;}
        build_keys++;
        const char *end=next;int values=0;
        while(*end && *end!='[') {
            if(*end=='"' || *end=='@') values=1;
            const char *nl=strchr(end,'\n');end=nl?nl+1:end+strlen(end);
        }
        size_t i=(size_t)reg_key_hash(name,len)&(slots-1);
        while(table[i].name && !reg_key_equal(&table[i],name,len)) i=(i+1)&(slots-1);
        /* a key without values comes back with its subkeys; Wine does not save it on its own */
        if(!table[i].name && values) {
            out[used++]='\n';
            memcpy(out+used,p,(size_t)(end-p));used+=(size_t)(end-p);
            if(out[used-1]!='\n') out[used++]='\n';
            table[i].name=name;table[i].len=len;added++;
        }
        p=end;
    }
    int rc=0;
    /* W230: never write unless both files look whole (the prefix's registry is about 1.4 MB and
     * 7000 keys); a cut read would replace system.reg with a fragment (W229) */
    if(live_size<(256u<<10) || build_size<(256u<<10) || live[live_size-1]!='\n' || build[build_size-1]!='\n' ||
       live_keys<1000 || build_keys<1000) {
        note(HW_BUILD " system_reg_merge implausible live_bytes=%zu build_bytes=%zu live_keys=%u build_keys=%u\n",
             live_size,build_size,live_keys,build_keys);
        free(out);free(table);free(build);free(live);return;
    }
    if(added) {
        int fd=open(temp_path,O_CREAT|O_TRUNC|O_WRONLY,0666);
        size_t done=0;
        while(fd>=0 && done<used) {ssize_t n=write(fd,out+done,used-done);if(n<=0)break;done+=(size_t)n;}
        if(fd<0 || done!=used || fsync(fd)) rc=-1;
        if(fd>=0) close(fd);
        if(!rc) rc=sceKernelRename(temp_path,live_path);
        if(rc) unlink(temp_path);
    }
    note(HW_BUILD " system_reg_merge live_keys=%u build_keys=%u added=%u bytes=%zu rc=0x%08x\n",
         live_keys,build_keys,added,added?used:live_size,(unsigned)rc);
    if(!rc) {
        marker=open(marker_path,O_CREAT|O_WRONLY|O_TRUNC,0644);
        if(marker>=0) {
            char line[96];int n=snprintf(line,sizeof(line),"%s added=%u\n",HW_BUILD,added);
            if(n>0 && write(marker,line,(size_t)n)!=n) note(HW_BUILD " system_reg_merge marker_short_write\n");
            close(marker);
        }
    }
    free(out);free(table);free(build);free(live);
}

#include "hw_install.h"  /* alpha-1: the first-run installer (uses note, read_whole and the loading screen) */
int main(void)
{
    pw_brand_prepare_state();
    mkdir("/data/orbisdesk",0755);mkdir(HW_DIR,0777);
    char path[160];
    for(unsigned n=1;n<10000;n++){
        snprintf(path,sizeof(path),HW_DIR "/run-%04u.log",n);
        log_fd=open(path,O_CREAT|O_EXCL|O_WRONLY,0644);
        if(log_fd>=0||errno!=EEXIST)break;
    }
    if(log_fd<0){panel("LOG OPEN FAILED","CLOSE THE APP AND REPORT THIS SCREEN");for(;;)sceKernelUsleep(1000000);}
    fchmod(log_fd,0644);
    {extern int pw_native_log_fd;pw_native_log_fd=log_fd;}  /* W253: platform/ps4/pw_wine_signals.c's lost-signal line */
    note(HW_BUILD " entered_launcher log=%s\n",path);
    redirect_stderr();
    install_crash_handler();
    trace_setup();
    loading(5,"PREPARING WINE");
    boot_choose();  /* phase 10: Normal or Root */
    int net=(int)sceSysmoduleLoadModuleInternal(ORBIS_SYSMODULE_INTERNAL_NET);
    note(HW_BUILD " sysmodule_net rc=0x%08x\n",(unsigned)net);
    if(pw_trace_on()) platform_probes();  /* diagnostics of W001-W030; the paths they checked are in use since */
    /* W135: phase 5, whether 32-bit code can run natively (compatibility mode) on this
     * console; once per build (native/compat32_probe.c) */
    {
        extern int pw_compat32_probe(const char *marker,char *detail,size_t size);
        char detail[200];
        int native32=pw_compat32_probe(HW_DIR "/compat32-probe.txt",detail,sizeof(detail));
        note(HW_BUILD " compat32_probe native32=%d %s\n",native32,detail);
    }
    /* W070 (H1): Vulkan (Mesa RADV on GNM) in this ELF: the G001 probe, off screen, before
     * Wine starts; its device stays open while Wine runs. Lines start with PWVK. */
    note(HW_BUILD " vk_probe_start t_ms=%llu\n",(unsigned long long)(sceKernelGetProcessTime()/1000));
    pw_vk_probe();
    note(HW_BUILD " vk_probe_end t_ms=%llu\n",(unsigned long long)(sceKernelGetProcessTime()/1000));
    pw_vk_runtime_init();
    pw_native_heap_report();
    pw_telemetry_init();
    note(HW_BUILD " experiment mangohud_layer=%s\n",PW_MANGOHUD_LAYER_ENABLED?"enabled":"disabled");
    /* Keep result evidence from earlier attempts, never accept it as this run. */
    const char *result="/data/wine-prefix/drive_c/orbis/" HW_RESULT;
    OrbisKernelStat previous;
    if(sceKernelStat(result,&previous)==0){
        char archived[192];snprintf(archived,sizeof(archived),"%s." HW_RESULT,path);
        int moved=sceKernelRename(result,archived);
        note(HW_BUILD " result_archived rc=0x%08x to=%s\n",(unsigned)moved,archived);
        if(moved){panel("RESULT ARCHIVE FAILED","READ THE FTP LOG");for(;;)sceKernelUsleep(1000000);}
    }
    /* alpha-1: the runtime the package carries, into /data on the first start of a build (native/hw_install.h).
     * Before the jailbreak: GoldHEN's escape from the sandbox takes /app0 away (W303's Root start found no
     * /app0/runtime, errno 2); the sandbox writes /data as Wine does there. */
    {
        char detail[96]={0};
        if(hw_install_runtime(detail,sizeof(detail))) {panel("INSTALL FAILED",detail);for(;;)sceKernelUsleep(1000000);}
    }
    if(boot_root) pw_hw_jailbreak();  /* phase 10: Root on the loading screen */
    merge_system_reg();
    /* W015: first GUI program on hardware, the PE64 window fixture of increment 24. */
    /* W038: the program comes from /data/orbisdesk/launch.txt when present: the first line
     * is the Windows path of the EXE, each further non-empty line one argument. A title
     * cannot start a second process, so this is how another program is chosen without
     * rebuilding. Without the file it is the explorer desktop at the 1280x720 output size,
     * with controller input (native/hw_pad.c); explorer runs until the app closes. */
    enum {MAX_LAUNCH_ARGS=16};  /* W265 (W263: PoP, Worms 3D): was 6, as the switch's */
    static char exe_arg[300],wine_args[MAX_LAUNCH_ARGS][300];
    char *args[24+MAX_LAUNCH_ARGS+MAX_SWITCH_ENV]={"wine-" HW_BUILD,"--prepared-prefix",exe_arg,"--env=WINE_PS5_DESKTOP=1280x720"};
    int argc=4;
    snprintf(exe_arg,sizeof(exe_arg),"--wine-exe=" HW_EXE);
    /* W043: a program started from the desktop (HW_NEXT) comes first, once */
    FILE *launch=fopen(HW_NEXT,"r");
    if(launch) {switched=1;unlink(HW_NEXT);note(HW_BUILD " switched_program\n");}
    /* W262: the starter's working directory and variables for that program (pw_hw_switch_context) */
    static char context_dir[400],context_env[MAX_SWITCH_ENV][300];
    int context_envs=0;
    if(switched) {
        FILE *context=fopen(HW_NEXT_CONTEXT,"r");
        if(context) {
            char line[600];
            while(fgets(line,sizeof(line),context)) {
                line[strcspn(line,"\r\n")]=0;
                if(!strncmp(line,"dir=",4)) snprintf(context_dir,sizeof(context_dir),"%s",line+4);
                else if(!strncmp(line,"env=",4) && context_envs<MAX_SWITCH_ENV)
                    snprintf(context_env[context_envs++],sizeof(context_env[0]),"--env=%s",line+4);
            }
            fclose(context);
            unlink(HW_NEXT_CONTEXT);
            note(HW_BUILD " switch_context read dir=%s envs=%d\n",context_dir,context_envs);
        }
    }
    else launch=fopen("/data/orbisdesk/launch.txt","r");
    if(launch) {
        char line[320];int lines=0;  /* W265: arguments up to 299 characters, as the switch writes them */
        while(fgets(line,sizeof(line),launch)) {
            line[strcspn(line,"\r\n")]=0;
            if(!line[0]) continue;
            if(!lines++) snprintf(exe_arg,sizeof(exe_arg),"--wine-exe=%s",line);
            else if(argc<4+MAX_LAUNCH_ARGS) {
                snprintf(wine_args[argc-4],sizeof(wine_args[0]),"--wine-arg=%s",line);args[argc]=wine_args[argc-4];++argc;
            }
        }
        fclose(launch);
        note(HW_BUILD " launch_file lines=%d\n",lines);
        for(int i=0;i<context_envs;i++) args[argc++]=context_env[i];  /* W262 */
    } else {
        static char desktop[]="--wine-arg=/desktop=shell,1280x720";
        args[argc++]=desktop;
    }
    /* W044: the console's local time for Wine's clock, as a POSIX TZ (west of UTC is
     * positive). W047: on hardware the C library's clock, which Wine reads, is not the
     * time the console shows (W045: 9:11 PM in the taskbar at 2:30 AM local), so the zone
     * alone is not enough. The offset is the console's local time (sceRtc) minus the
     * C library's time, to the second; local times in Wine then match the console, UTC
     * ones keep the C library's error. The zone parameter remains the fallback. */
    static char tz_arg[48];int32_t zone=0,summer=0;
    TimeTable now_local;memset(&now_local,0,sizeof(now_local));
    time_t libc_now=time(NULL);
    long long east=LLONG_MIN;
    int rtc=sceRtcGetCurrentClockLocalTime(&now_local);
    if(!rtc) {
        /* days from 1970-01-01 to the console's local date (proleptic Gregorian) */
        long long y=now_local.year-(now_local.month<=2),era=(y>=0?y:y-399)/400,yoe=y-era*400;
        long long doy=(153*(now_local.month+(now_local.month>2?-3:9))+2)/5+now_local.day-1;
        long long days=era*146097+yoe*365+yoe/4-yoe/100+doy-719468;
        long long local=days*86400+now_local.hour*3600+now_local.minute*60+now_local.second;
        east=local-(long long)libc_now;
    } else if(!sceSystemServiceParamGetInt(ORBIS_SYSTEM_SERVICE_PARAM_ID_TIME_ZONE,&zone)) {
        if(sceSystemServiceParamGetInt(ORBIS_SYSTEM_SERVICE_PARAM_ID_SUMMERTIME,&summer)) summer=0;
        east=(long long)(zone+(summer?60:0))*60;
    }
    note(HW_BUILD " time_source rtc=0x%08x local=%04u-%02u-%02u %02u:%02u:%02u libc=%lld\n",(unsigned)rtc,now_local.year,now_local.month,
         now_local.day,now_local.hour,now_local.minute,now_local.second,(long long)libc_now);
    if(east!=LLONG_MIN) {
        long long west=-east,magnitude=west<0?-west:west;
        snprintf(tz_arg,sizeof(tz_arg),"TZ=LCL%c%lld:%02lld:%02lld",west<0?'-':'+',magnitude/3600,magnitude/60%60,magnitude%60);
        /* the C library here must honour it: check with its own localtime */
        setenv("TZ",tz_arg+3,1);tzset();
        struct tm shown;localtime_r(&libc_now,&shown);
        note(HW_BUILD " time_zone east_s=%lld tz=%s localtime=%02d:%02d:%02d\n",east,tz_arg+3,shown.tm_hour,shown.tm_min,shown.tm_sec);
        memmove(tz_arg+6,tz_arg,strlen(tz_arg)+1);memcpy(tz_arg,"--env=",6);
        args[argc++]=tz_arg;
    } else note(HW_BUILD " time_zone unavailable\n");
    /* W045: the user driver draws the wallpaper under every window (the desktop window
     * itself has no surface); the same file the registry names. */
    static char wallpaper[]="--env=WINE_PS5_WALLPAPER=/data/wine-prefix/drive_c/windows/orbis-hills.bmp";
    args[argc++]=wallpaper;
    /* W052: 64-bit GUI programs started from the desktop run as guests of this process
     * (kernelbase/ntdll of tools/build-guest-hw.py) instead of relaunching the title */
    static char guests[]="--env=WINE_PS4_GUESTS=1";
    args[argc++]=guests;
    /* W078: Mesa's WGL/Zink (opengl32.dll) reports on Windows through stderr and
     * OutputDebugString (util/log ignores MESA_LOG_FILE there, W077); Wine logs the latter
     * as a warning of its seh channel, which goes to the run log. */
    /* W092: and which DLL fails to initialise (warn+module): loading MangoHud's layer gave
     * ERROR_DLL_INIT_FAILED (1114) in W091. W151: warn+module, not trace+module, which logged
     * every resource lookup (the Start menu's icons on each opening). */
    static char mesa_log[]="--env=WINEDEBUG=warn+module,trace+seh,trace+loaddll,warn+debugstr";
    /* alpha-1 (pw_trace.h): without traces, Wine's errors and warn+module (a DLL that fails to load or
     * initialise) only. Off: fixme (dozens of lines per program start), trace+seh (lines per exception,
     * on the faulting thread), trace+loaddll and debugstr (each OutputDebugString). */
    static char release_log[]="--env=WINEDEBUG=fixme-all,warn+module";
    int debug_arg=argc;
    args[argc++]=pw_trace_on()?mesa_log:release_log;
    static char trace_env[]="--env=PW_TRACE=0";
    trace_env[sizeof(trace_env)-2]=pw_trace_on()?'1':'0';
    args[argc++]=trace_env;
    /* alpha-1: DXVK (64-bit programs, and 32-bit ones relaunched alone) unset logs at info into <exe>_d3d9.log and
     * friends in the program's folder. Never files; warnings with traces, errors without, to the run log (stderr).
     * The 32-bit world sets its own per program (fixtures/win32/orbis32host.c, C:\orbis\dxvkdebug.txt). */
    static char dxvk_path[]="--env=DXVK_LOG_PATH=none";
    static char dxvk_warn[]="--env=DXVK_LOG_LEVEL=warn",dxvk_error[]="--env=DXVK_LOG_LEVEL=error";
    args[argc++]=dxvk_path;
    args[argc++]=pw_trace_on()?dxvk_warn:dxvk_error;
    /* W086: the MangoHud Vulkan layer (implicit, registered in the prefix) is on for every
     * Vulkan and OpenGL (Zink) program */
    static char mangohud[]="--env=MANGOHUD=1";
    args[argc++]=mangohud;
    /* W087: wined3d without 3D, so dxgi only enumerates (the Khronos loader verifies registry
     * drivers with a DXGI factory, and MangoHud asks it for the GPU); its OpenGL init failed
     * and left no adapter (W086: VK_ERROR_INCOMPATIBLE_DRIVER).
     * W092: the loader's VK_* variables are gone: it reports running elevated under Wine and
     * ignores them (W091); it finds the driver and the layer through the registry. */
    static char d3d_config[]="--env=WINE_D3D_CONFIG=renderer=no3d";
    int d3d_arg=argc;
    args[argc++]=d3d_config;
    /* W116: a 32-bit program (PE32) runs under WoW64 with prospero-win's IA-32 translator.
     * Without the option wow64 falls back to wow64cpu.dll, which the prefix does not ship
     * (W015 dropped it with the PE64 fixture; W013/W014 passed it). */
    /* W137: phase 5A, 32-bit code runs natively in compatibility mode (wow64native, W135 probe);
     * wow64.dll falls back to wowprospero.dll when wow64native does not start */
    static char wow64_cpu[]="--wow64-cpu=wow64native.dll";
    int machine=pe_machine(exe_arg+11);
    /* W129: a program started on its own (relaunch or launch.txt) starts in its own folder, as
     * Explorer would open it; Wine takes the process's current directory from the Unix one.
     * W128: SuperMarioKart.exe (Blitz3D) loads SMK\*.x and its images by relative path and read
     * through a NULL pointer when they were not found. Only drive C: maps to the prefix. */
    if(switched || machine==0x14c) {
        const char *win=exe_arg+11;
        /* W181: the pad's key profile for this program, if C:\orbis\padmaps has one (native/hw_pad.c) */
        {extern void pw_hw_pad_profile(const char *exe);pw_hw_pad_profile(win);}
        /* W261: and the overlay's cursor mode for it (native/hw_overlay.c) */
        {extern void pw_hw_overlay_program(const char *exe,int load);pw_hw_overlay_program(win,1);}
        /* W262: the starter's working directory (next-context.txt), else the program's own folder */
        char starter_dir[420];
        if(context_dir[0]) snprintf(starter_dir,sizeof(starter_dir),"%s\\.",context_dir);
        if(windows_unix_path(context_dir[0]?starter_dir:win,program_cwd,sizeof(program_cwd))) {  /* phase 10: C: or D:..K: */
            char *dir=program_cwd;
            char *slash=strrchr(dir,'/');
            if(slash) *slash=0;
            /* W130: chdir is refused to the title (W129: EPERM); Wine gets the folder instead */
            struct stat st;
            if(stat(dir,&st) || !S_ISDIR(st.st_mode)) note(HW_BUILD " program_cwd missing dir=%s errno=%d\n",dir,errno);
            else {
                snprintf(program_dir_env,sizeof(program_dir_env),"--env=PW_PROGRAM_DIR=%s",dir);
                args[argc++]=program_dir_env;
                note(HW_BUILD " program_cwd dir=%s via=PW_PROGRAM_DIR\n",dir);
            }
        }
    }
    const char *cpu="native";
    /* W117: the first PE32 GUI run (W116) ended in a win32u system call that jumped to
     * address 0 right after Vulkan initialised; trace win32u OpenGL/Vulkan and the WoW64
     * system calls of 32-bit runs to name it. */
    /* W131: ddraw calls and file opens of 32-bit programs (SuperMarioKart.exe: an image Blitz loads comes
     * back NULL, W130); the Vulkan trace of W117 is no longer needed.
     * W155: those traces are gone too (warn for ddraw, file, virtual, section): with them SuperMarioKart
     * wrote 429,000 lines in 80 s (W153), one per draw call, texture change and file read. */
    static char pe32_log[]="--env=WINEDEBUG=warn+module,trace+seh,trace+loaddll,warn+debugstr,warn+ddraw,warn+file,warn+virtual,warn+section,warn+d3d,warn+vulkan,warn+dmloader,warn+dmsynth,warn+dmime,warn+dmusic";
    /* W127: a 32-bit program runs alone (no explorer, Khronos loader or MangoHud in its
     * process), so wined3d can render through its Vulkan renderer: DirectDraw and Direct3D 7
     * and older (SuperMarioKart.exe, Blitz3D), with fixed-function emulated in HLSL. */
    static char d3d_vulkan[]="--env=WINE_D3D_CONFIG=renderer=vulkan";
    /* W136: phase 5A, native 32-bit code needs signals the kernel delivers to Wine's own entry
     * (ntdll signal_x86_64.c, platform/ps4/pw_wine_signals.c); first on its own, with the
     * translator still running the program */
    static char native_signals[]="--env=PW_NATIVE_SIGNALS=1";
    /* W155: a 32-bit program runs as a title: the screen shows the area its windows cover
     * (ps5drv.c present_screen), so a game in an 800x600 window fills the screen */
    static char fit[]="--env=WINE_PS5_FIT=1";
    /* W167: prospero-win's 32-bit Vulkan call batching (W166, tools/build-winevulkan-batch.py) is
     * opt-in: without PW_VK_BATCH=1 its winevulkan sends every call as before (W166 was tested so).
     * W178: without its counters (PW_VK_BATCH_STATS, PW_VK_BATCH_FALLBACK_PROFILE) and without
     * wow64native's profiler (PW_NATIVE_PROFILE, PW_QPC_TSC_HZ), which measured the W159-W167 work. */
    static char vk_batch[]="--env=PW_VK_BATCH=1";
    if(machine==0x14c) {args[argc++]=wow64_cpu;cpu="wow64native";if(pw_trace_on()) args[debug_arg]=pe32_log;args[d3d_arg]=d3d_vulkan;
                        args[argc++]=native_signals;args[argc++]=fit;args[argc++]=vk_batch;}
    /* B0 of the plan for 32-bit guests of explorer (pe32-en-explorer-plan.md): explorer with the raw
     * signal entry 32-bit code needs, while C:\orbis\wow64probe.txt exists; C:\orbis\wow64probe64.exe
     * then measures the low address space and initializes wow64native in this process */
    /* W235 (P8): explorer always has them now, for its 32-bit world (opening a PE32 runs it there,
     * tools/build-guest-hw.py); C:\orbis\pe32relaunch.txt brings back the relaunch for every PE32 and
     * explorer without them, as before B0 */
    else {
        OrbisKernelStat relaunch_marker;
        if(sceKernelStat("/data/wine-prefix/drive_c/orbis/pe32relaunch.txt",&relaunch_marker)!=0) {
            args[argc++]=native_signals;
            args[argc++]=wow64_cpu;
            note(HW_BUILD " wow64world native_signals=1 cpu=wow64native.dll\n");
        } else note(HW_BUILD " wow64world off: pe32relaunch.txt\n");
    }
    /* W256: C:\orbis\winedebug.txt adds Wine debug channels to this run (W254: Vice City's second filter
     * graph, "trace+quartz,trace+devenum"); its first line, letters, digits and "+-,_" only */
    {
        static char user_debug[512];
        char extra[200];
        int fd=open("/data/wine-prefix/drive_c/orbis/winedebug.txt",O_RDONLY),kernel_fd=-1,open_errno=errno;
        /* W271 (W270: the file was there, rwx, and no line said so): the kernel's own open when libc's fails */
        if(fd<0) kernel_fd=sceKernelOpen("/data/wine-prefix/drive_c/orbis/winedebug.txt",0,0);
        if(fd>=0 || kernel_fd>=0) {
            ssize_t n=fd>=0?read(fd,extra,sizeof(extra)-1):sceKernelRead(kernel_fd,extra,sizeof(extra)-1);
            size_t len=0;
            if(fd>=0) close(fd); else {
                sceKernelClose(kernel_fd);
                note(HW_BUILD " PWBOOT winedebug libc open errno=%d, read with sceKernelOpen\n",open_errno);
            }
            if(n<0) n=0;
            extra[n]=0;
            while(len<(size_t)n && ((extra[len]>='a'&&extra[len]<='z')||(extra[len]>='A'&&extra[len]<='Z')||
                  (extra[len]>='0'&&extra[len]<='9')||strchr("+-,_",extra[len]))) len++;
            extra[len]=0;
            if(len && snprintf(user_debug,sizeof(user_debug),"%s,%s",args[debug_arg],extra)<(int)sizeof(user_debug)) {
                args[debug_arg]=user_debug;
                note(HW_BUILD " PWBOOT winedebug extra=%s\n",extra);
            } else note(HW_BUILD " PWBOOT winedebug ignored (empty or too long)\n");
        }
        /* W271 (W270: the file was there, rwx, and no line said so) */
        else {
            OrbisKernelStat debug_marker;
            if(sceKernelStat("/data/wine-prefix/drive_c/orbis/winedebug.txt",&debug_marker)==0)
                note(HW_BUILD " PWBOOT winedebug open_failed errno=%d kernel=%#x (the kernel sees the file)\n",
                     open_errno,(unsigned)kernel_fd);
        }
    }
    /* W264 (W262: every 32-bit program that loaded Mesa's i386 opengl32 ended the app; W263 went back to Wine's builtin):
     * C:\\orbis\\opengl32native.txt gives 32-bit programs Mesa's opengl32 (Zink) from syswow64; the 64-bit view has no
     * builtin opengl32 and keeps Mesa's either way */
    {
        /* W267 (W266: Call of Duty alone stopped in zink's screen: the Khronos loader loaded DXVK's dxgi, which started
         * DXVK inside it): Wine's builtin dxgi, as explorer's world (AppDefaults\\explorer.exe, W190) */
        static char gl32_native[]="--env=WINEDLLOVERRIDES=opengl32=n,b;dxgi=b";
        OrbisKernelStat gl32_marker;
        if(sceKernelStat("/data/wine-prefix/drive_c/orbis/opengl32native.txt",&gl32_marker)==0) {
            args[argc++]=gl32_native;
            note(HW_BUILD " PWGL opengl32 native (opengl32native.txt)\n");
        }
    }
    args[argc]=NULL;
    for(int i=2;i<argc;i++) note(HW_BUILD " launch_arg %s\n",args[i]);
    note(HW_BUILD " calling_wine_boot_main cpu=%s machine=0x%x t_ms=%llu\n",cpu,(unsigned)machine,(unsigned long long)(sceKernelGetProcessTime()/1000));
    loading(30,"STARTING WINE");
    sceKernelUsleep(1000000);
    int rc=pw_wine_boot_main(argc,args);
    note(HW_BUILD " boot_main_return rc=%d\n",rc);
    char detail[96];snprintf(detail,sizeof(detail),"BOOT RETURNED CODE 0X%08X - READ THE FTP LOG",(unsigned)rc);
    panel("WINE BOOT STOPPED",detail);
    for(;;)sceKernelUsleep(1000000);
}
