/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <unistd.h>
#include <orbis/libkernel.h>
#include "hw_text.h"
#include "pw_wine_net.h"

enum {WIDTH=1280,HEIGHT=720,PAGE=0x4000};
int pw_trace_level=0;
static uint32_t *pixels;
static FILE *log_file;
static unsigned row=185,run_number;
static char run_dir[160];
int pw_wine_present(const void *,unsigned int,unsigned int,unsigned int);

static void note(const char *name,int rc,int error,long detail)
{
    if(log_file) {
        fprintf(log_file,"{\"build\":\"P001\",\"event\":\"%s\",\"rc\":%d,\"errno\":%d,\"detail\":%ld}\n",name,rc,error,detail);
        fflush(log_file);fsync(fileno(log_file));
    }
}
static void line(const char *name,int rc)
{
    char text[120];snprintf(text,sizeof(text),"%s: %s  CODE %08X",name,rc?"FAIL":"PASS",(unsigned)rc);
    hw_text(pixels,WIDTH,HEIGHT,45,(int)row,text,rc?0xffff7777:0xff88ee99,3);
    row+=45;pw_wine_present(pixels,WIDTH,HEIGHT,WIDTH*4);
}
static int open_run(void)
{
    mkdir("/data/orbisdesk",0755);mkdir("/data/orbisdesk/process-p001",0755);
    for(unsigned n=1;n<10000;n++) {
        snprintf(run_dir,sizeof(run_dir),"/data/orbisdesk/process-p001/run-%04u",n);
        errno=0;
        if(!mkdir(run_dir,0755)) {run_number=n;break;}
        if(errno!=EEXIST) return errno?errno:EIO;
    }
    if(!run_number)return EEXIST;
    char path[200];snprintf(path,sizeof(path),"%s/report.jsonl",run_dir);
    int fd=open(path,O_WRONLY|O_CREAT|O_EXCL,0644);
    if(fd<0)return errno?errno:EIO;
    log_file=fdopen(fd,"w");
    if(!log_file){int saved=errno;close(fd);return saved?saved:EIO;}
    note("started",0,0,(long)getpid());
    return 0;
}
static int mapping_probe(int fd)
{
    int rc=sceKernelFtruncate(fd,PAGE);
    note("mapping_truncate",rc,0,PAGE);
    if(rc)return rc;
    void *a=NULL,*b=NULL;
    rc=sceKernelMmap(NULL,PAGE,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0,&a);
    note("mapping_first",rc,0,0);
    if(rc)return rc;
    rc=sceKernelMmap(NULL,PAGE,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0,&b);
    note("mapping_second",rc,0,a!=b);
    if(!rc) {
        volatile uint32_t *one=a,*two=b;
        for(unsigned i=0;i<64;i++)one[i]=0x504f5000u+i;
        for(unsigned i=0;i<64;i++)if(two[i]!=0x504f5000u+i)rc=EIO;
        two[63]=0x1234abcd;
        if(one[63]!=0x1234abcd || a==b)rc=EIO;
        note("mapping_coherence",rc,0,64);
        int unmap=sceKernelMunmap(b,PAGE);note("mapping_unmap_second",unmap,0,0);
        if(!rc)rc=unmap;
    }
    int unmap=sceKernelMunmap(a,PAGE);note("mapping_unmap_first",unmap,0,0);
    return rc?rc:unmap;
}
static int channel_probe(int fd)
{
    int pair[2]={-1,-1},received=-1,error=0;
    errno=0;int rc=socketpair(AF_UNIX,SOCK_STREAM,0,pair);
    note("socketpair",rc,rc?errno:0,0);
    if(rc)return errno?errno:EIO;
    char byte='P';struct iovec vec={&byte,1};
    union {struct cmsghdr align;char bytes[CMSG_SPACE(sizeof(int))];} control;
    memset(&control,0,sizeof(control));
    struct msghdr msg;memset(&msg,0,sizeof(msg));
    msg.msg_iov=&vec;msg.msg_iovlen=1;msg.msg_control=control.bytes;msg.msg_controllen=sizeof(control.bytes);
    struct cmsghdr *header=CMSG_FIRSTHDR(&msg);
    header->cmsg_level=SOL_SOCKET;header->cmsg_type=SCM_RIGHTS;header->cmsg_len=CMSG_LEN(sizeof(int));
    memcpy(CMSG_DATA(header),&fd,sizeof(fd));
    errno=0;ssize_t sent=pw_wine_sendmsg(pair[0],&msg,MSG_DONTWAIT|MSG_NOSIGNAL);
    note("descriptor_send",sent==1?0:-1,sent<0?errno:0,(long)sent);
    if(sent!=1) {error=errno?errno:EIO;goto done;}
    memset(&control,0,sizeof(control));byte=0;msg.msg_controllen=sizeof(control.bytes);msg.msg_flags=0;
    errno=0;ssize_t got=pw_wine_recvmsg(pair[1],&msg,MSG_DONTWAIT);
    note("descriptor_receive",got==1?0:-1,got<0?errno:0,(long)got);
    if(got!=1 || byte!='P') {error=errno?errno:EIO;goto done;}
    header=CMSG_FIRSTHDR(&msg);
    if(header && header->cmsg_level==SOL_SOCKET && header->cmsg_type==SCM_RIGHTS && header->cmsg_len>=CMSG_LEN(sizeof(int)))
        memcpy(&received,CMSG_DATA(header),sizeof(received));
    if(received<0) {error=EBADF;goto done;}
    const char marker[]="P001-DESCRIPTOR";char output[sizeof(marker)]={0};
    if(lseek(fd,0,SEEK_SET)<0 || write(fd,marker,sizeof(marker))!=(ssize_t)sizeof(marker) ||
       lseek(received,0,SEEK_SET)<0 || read(received,output,sizeof(output))!=(ssize_t)sizeof(output) ||
       memcmp(output,marker,sizeof(marker)))error=errno?errno:EIO;
    note("received_descriptor_io",error,0,received);
done:
    if(received>=0)close(received);
    close(pair[0]);close(pair[1]);
    return error;
}
static int inventory(unsigned *matches)
{
    OrbisKernelModule modules[128];size_t count=0;
    const char *symbols[]={"posix_spawn","fork","rfork","execve","sceKernelSpawn","sceKernelCreateProcess"};
    int rc=sceKernelGetModuleList(modules,128,&count);
    note("loaded_modules",rc,0,(long)count);
    if(rc || count>128)return rc?rc:EOVERFLOW;
    for(size_t i=0;i<count;i++) {
        OrbisKernelModuleInfo info;memset(&info,0,sizeof(info));info.size=sizeof(info);
        int result=sceKernelGetModuleInfo(modules[i],&info);
        if(log_file) {
            /* Module names are diagnostic strings, not paths to execute. */
            for(unsigned c=0;c<sizeof(info.name) && info.name[c];c++)
                if(info.name[c]=='"'||info.name[c]=='\\'||(unsigned char)info.name[c]<32)info.name[c]=' ';
            info.name[sizeof(info.name)-1]=0;
            fprintf(log_file,"{\"event\":\"module\",\"handle\":%u,\"info_rc\":%d,\"name\":\"%s\"}\n",modules[i],result,info.name);
        }
        for(unsigned s=0;s<sizeof(symbols)/sizeof(symbols[0]);s++) {
            void *address=NULL;result=sceKernelDlsym(modules[i],symbols[s],&address);
            if(!result && address)++*matches;
            if(log_file)fprintf(log_file,"{\"event\":\"export\",\"handle\":%u,\"name\":\"%s\",\"rc\":%d,\"found\":%s}\n",modules[i],symbols[s],result,(!result&&address)?"true":"false");
        }
    }
    note("export_inventory_finished",0,0,*matches);
    return 0;
}
int main(void)
{
    pixels=calloc(WIDTH*HEIGHT,sizeof(*pixels));
    if(!pixels)return 1;
    for(unsigned i=0;i<WIDTH*HEIGHT;i++)pixels[i]=0xff102030;
    hw_text(pixels,WIDTH,HEIGHT,45,35,"ORBISDESK PROCESS CHECK P001",0xffffffff,4);
    hw_text(pixels,WIDTH,HEIGHT,45,85,"IPC PREREQUISITES - NO WINE",0xffb0ccff,3);
    hw_text(pixels,WIDTH,HEIGHT,45,130,"SECOND PROCESS: NOT TESTED",0xffffcc77,3);
    if(pw_wine_present(pixels,WIDTH,HEIGHT,WIDTH*4))return 2;
    int logging=open_run();line("LOG",logging);
    if(!logging) {
        char file[200];snprintf(file,sizeof(file),"%s/shared.tmp",run_dir);
        int fd=open(file,O_RDWR|O_CREAT|O_EXCL,0600);
        int mapped=fd<0?(errno?errno:EIO):mapping_probe(fd);line("SHARED MAP LOCAL",mapped);
        int channel=fd<0?(errno?errno:EIO):channel_probe(fd);line("FD TRANSFER LOCAL",channel);
        if(fd>=0) {close(fd);if(unlink(file))note("scratch_cleanup",-1,errno,0);}
        unsigned matches=0;int scanned=inventory(&matches);line("EXPORT INVENTORY",scanned);
        char result[100];snprintf(result,sizeof(result),"SPAWN EXPORT MATCHES: %u - NOT CALLED",matches);
        hw_text(pixels,WIDTH,HEIGHT,45,(int)row,result,0xffffcc77,3);row+=45;
        note("complete",mapped||channel||scanned,0,0);
        fputs("{\"event\":\"scope\",\"local_ipc_only\":true,\"cross_process_ipc_verified\":false,\"native_child_started\":false}\n",log_file);
        fflush(log_file);fsync(fileno(log_file));fclose(log_file);log_file=NULL;
    }
    hw_text(pixels,WIDTH,HEIGHT,45,510,"SEND A PHOTO THEN CLOSE FROM PS4 MENU",0xffffffff,3);
    hw_text(pixels,WIDTH,HEIGHT,45,565,run_dir,0xffb0ccff,2);
    for(;;){pw_wine_present(pixels,WIDTH,HEIGHT,WIDTH*4);sceKernelUsleep(1000000);}
}
