/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* First hardware check: ordinary app APIs only, no Wine or kernel payload. */
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/stat.h>
#include <orbis/libkernel.h>

int pw_wine_present(const void *,unsigned int,unsigned int,unsigned int);
#define HW_BUILD_TAG "H001B"
#define HW_MARKER_TEXT "orbisdesk app0 " HW_BUILD_TAG "\n"
enum {W=1280,H=720,PAGE=0x4000};
static uint32_t *pixels;
static int log_fd=-1,run_number;
static unsigned row=140;
static __thread int tls_value=11;
static pthread_mutex_t mutex=PTHREAD_MUTEX_INITIALIZER;
static int shared_value;
static const unsigned char glyphs[][7]={
 {14,17,17,31,17,17,17},{30,17,17,30,17,17,30},{14,17,16,16,16,17,14},
 {30,17,17,17,17,17,30},{31,16,16,30,16,16,31},{31,16,16,30,16,16,16},
 {14,17,16,23,17,17,15},{17,17,17,31,17,17,17},{14,4,4,4,4,4,14},
 {7,2,2,2,18,18,12},{17,18,20,24,20,18,17},{16,16,16,16,16,16,31},
 {17,27,21,21,17,17,17},{17,25,21,19,17,17,17},{14,17,17,17,17,17,14},
 {30,17,17,30,16,16,16},{14,17,17,17,21,18,13},{30,17,17,30,20,18,17},
 {15,16,16,14,1,1,30},{31,4,4,4,4,4,4},{17,17,17,17,17,17,14},
 {17,17,17,17,17,10,4},{17,17,17,21,21,21,10},{17,17,10,4,10,17,17},
 {17,17,10,4,4,4,4},{31,1,2,4,8,16,31},
 {14,17,19,21,25,17,14},{4,12,4,4,4,4,14},{14,17,1,2,4,8,31},
 {30,1,1,14,1,1,30},{2,6,10,18,31,2,2},{31,16,16,30,1,1,30},
 {14,16,16,30,17,17,14},{31,1,2,4,8,8,8},{14,17,17,14,17,17,14},
 {14,17,17,15,1,1,14},{0,4,4,0,4,4,0},{0,0,0,31,0,0,0},
 {0,0,0,0,0,4,4},{1,2,2,4,8,8,16}
};

static void text(int x,int y,const char *s,uint32_t color,int scale)
{
    for(;*s;s++,x+=6*scale){
        unsigned char c=(unsigned char)*s;int g=-1;
        if(c>='a'&&c<='z')c-=32;
        if(c>='A'&&c<='Z')g=c-'A';else if(c>='0'&&c<='9')g=26+c-'0';
        else if(c==':')g=36;else if(c=='-')g=37;else if(c=='.')g=38;else if(c=='/')g=39;
        if(g<0)continue;
        for(int yy=0;yy<7;yy++)for(int xx=0;xx<5;xx++)if(glyphs[g][yy]&(1<<(4-xx)))
            for(int dy=0;dy<scale;dy++)for(int dx=0;dx<scale;dx++){
                int px=x+xx*scale+dx,py=y+yy*scale+dy;
                if(px>=0&&px<W&&py>=0&&py<H)pixels[py*W+px]=color;
            }
    }
}

static void event(const char *name,const char *status,int code)
{
    char line[256];int n=snprintf(line,sizeof(line),
        "{\"build\":\"" HW_BUILD_TAG "\",\"case\":\"%s\",\"status\":\"%s\",\"code\":%d}\n",name,status,code);
    sceKernelDebugOutText(0,line);
    if(log_fd>=0){write(log_fd,line,(size_t)n);fsync(log_fd);}
}

static void result(const char *name,int code)
{
    char line[160];snprintf(line,sizeof(line),"%s: %s  CODE 0X%08X",name,code?"FAIL":"PASS",(unsigned)code);
    text(48,(int)row,line,code?0xffff6666:0xff77ee99,3);row+=48;
    event(name,code?"failed":"passed",code);
    pw_wine_present(pixels,W,H,W*4);
}

static int sfo_metadata(void)
{
    unsigned char magic[4];int fd=open("/app0/sce_sys/param.sfo",O_RDONLY);
    if(fd<0)return errno?errno:1;
    int ok=read(fd,magic,4)==4&&!memcmp(magic,"\0PSF",4);close(fd);return ok?0:1;
}

static int app_files(void)
{
    const char expected[]=HW_MARKER_TEXT;char data[sizeof(expected)]={0};
    int fd=open("/app0/hardware-marker.txt",O_RDONLY);
    if(fd<0)return errno?errno:1;
    ssize_t count=read(fd,data,sizeof(data));close(fd);
    return count==(ssize_t)(sizeof(expected)-1)&&!memcmp(data,expected,sizeof(expected)-1)?0:1;
}

static int data_files(void)
{
    char path[160],data[32]={0};const char payload[]="orbisdesk hardware " HW_BUILD_TAG "\n";
    snprintf(path,sizeof(path),"/data/orbisdesk/hw01/roundtrip-%04d.bin",run_number);
    int fd=open(path,O_CREAT|O_EXCL|O_RDWR,0644);
    if(fd<0)return errno?errno:1;
    if(fchmod(fd,0644)){int error=errno;close(fd);return error?error:1;}
    int ok=write(fd,payload,sizeof(payload))==(ssize_t)sizeof(payload)&&lseek(fd,0,SEEK_SET)==0&&
        read(fd,data,sizeof(payload))==(ssize_t)sizeof(payload)&&!memcmp(payload,data,sizeof(payload));
    int rc=close(fd);return ok&&!rc?0:1;
}

static int memory(void)
{
    void *p=NULL;int rc=sceKernelMapFlexibleMemory(&p,PAGE,3,0);
    if(rc)return rc;
    *(volatile uint32_t *)p=0x12345678;
    rc=sceKernelMprotect(p,PAGE,1);
    if(!rc&&*(volatile uint32_t *)p!=0x12345678)rc=1;
    if(!rc)rc=sceKernelMprotect(p,PAGE,3);
    int released=sceKernelMunmap(p,PAGE);return rc?rc:released;
}

static int low_memory(void)
{
    void *p=(void *)(uintptr_t)0x20000000;
    int rc=sceKernelReserveVirtualRange(&p,PAGE,0,PAGE);if(rc)return rc;
    int ok=(uintptr_t)p>=0x10000&&(uintptr_t)p+PAGE<=0x100000000ULL;
    rc=sceKernelMunmap(p,PAGE);return ok?rc:1;
}

static void *worker(void *unused)
{
    (void)unused;if(tls_value!=11)return (void *)(uintptr_t)1;
    tls_value=77;
    int rc=pthread_mutex_lock(&mutex);if(rc)return (void *)(uintptr_t)rc;
    shared_value=42;pthread_mutex_unlock(&mutex);return (void *)(uintptr_t)42;
}

static int threads(void)
{
    pthread_t thread;void *value=NULL;int rc=pthread_create(&thread,NULL,worker,NULL);
    if(rc)return rc;rc=pthread_join(thread,&value);if(rc)return rc;
    return (uintptr_t)value==42&&shared_value==42&&tls_value==11?0:1;
}

int main(void)
{
    mkdir("/data/orbisdesk",0755);mkdir("/data/orbisdesk/hw01",0755);
    char path[160];
    for(run_number=1;run_number<10000;run_number++){
        snprintf(path,sizeof(path),"/data/orbisdesk/hw01/report-%04d.jsonl",run_number);
        log_fd=open(path,O_CREAT|O_EXCL|O_WRONLY,0644);
        if(log_fd>=0||errno!=EEXIST)break;
    }
    int log_mode=log_fd>=0?fchmod(log_fd,0644):-1;
    event("boot","entered",0);
    pixels=malloc(W*H*4);if(!pixels){event("framebuffer","failed",ENOMEM);return 1;}
    for(int i=0;i<W*H;i++)pixels[i]=0xff102030;
    text(48,40,"ORBISDESK HARDWARE CHECK " HW_BUILD_TAG,0xffffffff,4);
    text(48,92,"BOOTSTRAP ONLY - NOT WINE",0xffb0ccff,3);
    int video=pw_wine_present(pixels,W,H,W*4);event("videoout",video?"failed":"passed",video);
    if(video)return 2;
    result("LOG FILE",log_fd>=0&&!log_mode?0:1);
    event("app0-read","running",0);result("APP0 READ",app_files());
    event("data-roundtrip","running",0);result("DATA ROUNDTRIP",data_files());
    event("memory-protect","running",0);result("MEMORY PROTECT",memory());
    event("low-memory","running",0);result("LOW MEMORY",low_memory());
    event("threads-tls","running",0);result("THREADS TLS",threads());
    int metadata=sfo_metadata();event("sfo-metadata",metadata?"unavailable":"readable",metadata);
    char info[96];snprintf(info,sizeof(info),"OPTIONAL SFO METADATA CODE 0X%08X",(unsigned)metadata);
    text(48,430,info,0xffb0ccff,2);
    text(48,470,"READY - SEND A PHOTO OF THIS SCREEN",0xffffffff,3);
    text(48,520,"CLOSE THE APP FROM THE PS4 MENU",0xffb0ccff,3);
    text(48,570,path,0xffb0ccff,2);
    event("complete","finished",0);
    for(;;){pw_wine_present(pixels,W,H,W*4);sceKernelUsleep(1000000);}
}
