/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* PWBASE probe: where the kernel loads a title ELF linked away from 0, and whether
 * 0x400000-0xa14000 (a fixed-base PE32 such as gta-vc.exe) can then be mapped. No Wine.
 * Built by tools/build-pwbase-probe.py as one driver and several stages:
 *   driver (eboot.bin): linked at 0. The first time it opens it is only the control: it
 *     writes PWBASE_LOG and the screen, waits 5 s and closes. From the second time on it
 *     records the baseline and starts each stage in turn.
 *   stage (/app0/pwbase_<name>.bin): the same code linked elsewhere; it records itself and
 *     starts the driver again.
 * B001-B003 closed at open before main; B004 put H001B's eboot under the same title and it
 * ran. Every ELF here is now built like H001B (tools/build-hardware-boot.py): the same
 * flags, H001B's own sink (build/hardware-h001b/sink.c) and only libkernel and
 * libSceVideoOut as needed libraries. The B00x probes needed libSceSystemService instead;
 * sceSystemServiceLoadExec is now looked up at run time, as native/hw_pad.c loads libScePad.
 * A stage that never reaches main is still visible: the driver marks it pending before
 * starting it, and finds the mark still pending on its next open.
 * Each line goes to PWBASE_LOG, to sceKernelDebugOutText and to the screen. */
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#include <orbis/libkernel.h>

#ifndef PWBASE_VARIANT
#error PWBASE_VARIANT must be "driver" or a stage name
#endif
#ifndef PWBASE_LINKED
#error PWBASE_LINKED must be the linked address of the first segment
#endif
#ifndef PWBASE_INDEX
#define PWBASE_INDEX -1        /* the driver */
#endif
/* the stages in order; tools/build-pwbase-probe.py builds one /app0/pwbase_<name>.bin each */
#ifndef PWBASE_STAGES
#error PWBASE_STAGES must list the stage names
#endif
/* B006 bisects from H001B, which runs under this title while B001-B005 closed before main:
 *   PWBASE_CONTROL_ONLY  only the log file and the screen: no stages, no LoadExec;
 *   PWBASE_NO_SELF_UNMAP without own_page, the 32 KiB page-aligned array in .bss. */
#ifndef PWBASE_CONTROL_ONLY
static const char *const stages[]={PWBASE_STAGES};
enum {STAGE_COUNT=sizeof(stages)/sizeof(stages[0])};
#endif

#define PWBASE_DIR "/data/orbisdesk"
#define PWBASE_LOG PWBASE_DIR "/probe-base.txt"
#define PWBASE_STATE PWBASE_DIR "/probe-base.state"
#define PWBASE_CONTROL PWBASE_DIR "/probe-base.control"
#define PWBASE_DRIVER_SELF "/app0/eboot.bin"
#define LOW_START 0x400000ull
#define LOW_SIZE 0x614000ull

int pw_wine_present(const void *,unsigned int,unsigned int,unsigned int);
extern char __text_start[];
static int log_fd=-1;

/* the screen: H001B's 5x7 font (native/hardware_boot.c), one line per note */
enum {W=1280,H=720,ROW=22,FIRST_ROW=96};
static uint32_t *pixels;
static int row=FIRST_ROW;
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
 {0,0,0,0,0,4,4},{1,2,2,4,8,8,16},{0,0,0,0,0,0,0}
};

static void text(int x,int y,const char *s,uint32_t color,int scale)
{
    if(!pixels) return;
    for(;*s && x<W;s++,x+=6*scale){
        unsigned char c=(unsigned char)*s;int g=-1;
        if(c>='a'&&c<='z')c-=32;
        if(c>='A'&&c<='Z')g=c-'A';else if(c>='0'&&c<='9')g=26+c-'0';
        else if(c==':'||c=='=')g=36;else if(c=='-'||c=='_')g=37;else if(c=='.')g=38;else if(c=='/')g=39;
        else if(c==' ')g=40;
        if(g<0)continue;
        for(int yy=0;yy<7;yy++)for(int xx=0;xx<5;xx++)if(glyphs[g][yy]&(1<<(4-xx)))
            for(int dy=0;dy<scale;dy++)for(int dx=0;dx<scale;dx++){
                int px=x+xx*scale+dx,py=y+yy*scale+dy;
                if(px>=0&&px<W&&py>=0&&py<H)pixels[py*W+px]=color;
            }
    }
}

static void screen_line(const char *line)
{
    if(!pixels) return;
    if(row+ROW>H-8) {   /* full: keep the title, clear the rest */
        for(int i=FIRST_ROW*W;i<W*H;i++)pixels[i]=0xff102030;
        row=FIRST_ROW;
    }
    text(24,row,line,0xffffffff,2);row+=ROW;
    pw_wine_present(pixels,W,H,W*4);
}

static void screen_open(void)
{
    pixels=malloc(W*H*4);
    if(!pixels) return;
    for(int i=0;i<W*H;i++)pixels[i]=0xff102030;
    text(24,24,"PWBASE PROBE " PWBASE_VARIANT,0xff77ee99,4);
    pw_wine_present(pixels,W,H,W*4);
}

/* note(): the log, the debug output and, unless the line is long detail, the screen */
static void emit(int on_screen,const char *format,va_list ap)
{
    char line[320];
    int n=vsnprintf(line,sizeof(line),format,ap);
    if(n<=0) return;
    if((size_t)n>=sizeof(line)) n=sizeof(line)-1;
    sceKernelDebugOutText(0,line);
    if(log_fd>=0) {write(log_fd,line,(size_t)n);fsync(log_fd);}
    if(on_screen) {
        if(n && line[n-1]=='\n') line[n-1]=0;
        screen_line(line+7);   /* without the "PWBASE " prefix */
    }
}
static void note(const char *format,...) {va_list ap;va_start(ap,format);emit(1,format,ap);va_end(ap);}

#ifndef PWBASE_CONTROL_ONLY
static int data_word=1;
static void detail(const char *format,...) {va_list ap;va_start(ap,format);emit(0,format,ap);va_end(ap);}

/* sceSystemServiceLoadExec without libSceSystemService as a needed library: the module is
 * loaded and the function looked up, as native/hw_pad.c loads libScePad (W030: system
 * libraries are under the sandbox's random word) */
typedef int32_t (*LoadExecFn)(const char *,const char *[]);
static LoadExecFn load_exec_fn(void)
{
    static LoadExecFn fn;static int tried;
    if(tried) return fn;
    tried=1;
    const char *word=sceKernelGetFsSandboxRandomWord();
    char dirs[3][64];
    snprintf(dirs[0],sizeof(dirs[0]),"/%s/common/lib/",word?word:"system");
    snprintf(dirs[1],sizeof(dirs[1]),"/%s/priv/lib/",word?word:"system");
    snprintf(dirs[2],sizeof(dirs[2]),"/system/common/lib/");
    int module=-1;char path[128]={0};
    for(unsigned i=0;i<3 && module<0;i++) {
        snprintf(path,sizeof(path),"%slibSceSystemService.sprx",dirs[i]);
        module=(int)sceKernelLoadStartModule(path,0,NULL,0,NULL,NULL);
    }
    void *address=NULL;
    int rc=module<0?-1:sceKernelDlsym(module,"sceSystemServiceLoadExec",&address);
    detail("PWBASE %s load_exec_lookup module=0x%08x path=%s dlsym=0x%08x address=%p\n",
           PWBASE_VARIANT,(unsigned)module,path,(unsigned)rc,address);
    if(!rc) fn=(LoadExecFn)address;
    return fn;
}
static int load_exec(const char *path)
{
    LoadExecFn fn=load_exec_fn();
    return fn?fn(path,NULL):-1;
}

/* the state: the next stage to start, and whether it was started without reporting back */
static void read_state(int *next,int *pending)
{
    *next=0;*pending=0;
    FILE *file=fopen(PWBASE_STATE,"r");
    if(!file) return;
    if(fscanf(file,"next=%d pending=%d",next,pending)!=2) {*next=0;*pending=0;}
    fclose(file);
}

static void write_state(int next,int pending)
{
    FILE *file=fopen(PWBASE_STATE,"w");
    if(!file) {note("PWBASE %s state_write_failed errno=%d\n",PWBASE_VARIANT,errno);return;}
    fprintf(file,"next=%d pending=%d\n",next,pending);fclose(file);
}

/* every region the kernel reports, in order (flag 1: the next one at or after). The names
 * show where this ELF, libkernel and /app0/sce_module/libc.prx are: a Wine boot loaded as a
 * module would land where those do. */
static void memory_map(void)
{
    const char *cursor=(const char *)0;
    for(int i=0;i<128;i++) {
        OrbisKernelVirtualQueryInfo info;memset(&info,0,sizeof(info));
        int q=sceKernelVirtualQuery(cursor,1,&info,sizeof(info));
        if(q) {detail("PWBASE %s map end rc=0x%08x\n",PWBASE_VARIANT,(unsigned)q);return;}
        detail("PWBASE %s map start=%p end=%p prot=%d type=%d flex=%u direct=%u stack=%u committed=%u name=%.32s\n",
               PWBASE_VARIANT,info.unk01,info.unk02,info.unk04,info.unk05,info.isFlexibleMemory,info.isDirectMemory,
               info.isStack,info.isCommitted,info.name);
        if((const char *)info.unk02<=cursor) return;
        cursor=(const char *)info.unk02;
    }
    detail("PWBASE %s map truncated at=%p\n",PWBASE_VARIANT,cursor);
}

/* the first region at or after LOW_START, or 0 if there is none below LOW_START+LOW_SIZE */
static uintptr_t low_occupant(void)
{
    OrbisKernelVirtualQueryInfo info;memset(&info,0,sizeof(info));
    if(sceKernelVirtualQuery((const void *)LOW_START,1,&info,sizeof(info))) return 0;
    return (uintptr_t)info.unk01<LOW_START+LOW_SIZE?(uintptr_t)info.unk01:0;
}

static void map_low(void)
{
    uintptr_t text_at=(uintptr_t)__text_start;
    if(text_at<LOW_START+LOW_SIZE && text_at+0x1000>LOW_START) {
        note("PWBASE %s low_map skipped reason=text_in_range\n",PWBASE_VARIANT);
        return;
    }
    /* a hint first: it never replaces anything, so it is safe even if the range is in use */
    errno=0;void *hint=mmap((void *)LOW_START,LOW_SIZE,PROT_READ|PROT_WRITE,MAP_ANON|MAP_PRIVATE,-1,0);
    note("PWBASE %s low_hint addr=%p errno=%d\n",PWBASE_VARIANT,hint,hint==MAP_FAILED?errno:0);
    if(hint!=MAP_FAILED) munmap(hint,LOW_SIZE);
    /* MAP_FIXED replaces what is there: only when the kernel reports nothing in the range */
    uintptr_t occupant=low_occupant();
    if(occupant) {
        note("PWBASE %s low_map skipped reason=occupied first=0x%lx\n",PWBASE_VARIANT,(unsigned long)occupant);
        return;
    }
    errno=0;void *fixed=mmap((void *)LOW_START,LOW_SIZE,PROT_READ|PROT_WRITE,MAP_FIXED|MAP_ANON|MAP_PRIVATE,-1,0);
    int fixed_errno=fixed==MAP_FAILED?errno:0;
    int wrote=0;
    if(fixed==(void *)LOW_START) {
        volatile uint32_t *word=(volatile uint32_t *)(LOW_START+0x2df9e0);   /* gta-vc.exe's TLS index slot */
        *word=0x32beef32;wrote=*word==0x32beef32;
        munmap(fixed,LOW_SIZE);
    }
    note("PWBASE %s low_map addr=%p errno=%d write_ok=%d\n",PWBASE_VARIANT,fixed,fixed_errno,wrote);
}

#ifndef PWBASE_NO_SELF_UNMAP
/* whether a page of this ELF's own image can be unmapped and mapped again in place: a stub
 * eboot that hands over to a module would have to release its own range this way. The page
 * belongs only to this array (aligned, twice the page size), and nothing else uses it. */
static char own_page[0x8000] __attribute__((aligned(0x4000)));
static void self_unmap(void)
{
    void *page=own_page;
    errno=0;int unmapped=munmap(page,0x4000);int unmap_errno=unmapped?errno:0;
    void *again=MAP_FAILED;int map_errno=0,wrote=0;
    if(!unmapped) {
        errno=0;again=mmap(page,0x4000,PROT_READ|PROT_WRITE,MAP_FIXED|MAP_ANON|MAP_PRIVATE,-1,0);
        map_errno=again==MAP_FAILED?errno:0;
        if(again==page) {own_page[0]=0x5a;wrote=own_page[0]==0x5a;}
    }
    note("PWBASE %s self_unmap munmap=%d errno=%d remap=%p errno=%d write_ok=%d\n",PWBASE_VARIANT,
         unmapped,unmap_errno,again,map_errno,wrote);
}
#endif

static void measure(void)
{
    int stack_word=0;
    note("PWBASE %s start linked=0x%llx text=%p\n",PWBASE_VARIANT,(unsigned long long)PWBASE_LINKED,(void *)__text_start);
    detail("PWBASE %s addresses main=%p data=%p stack=%p pid=%d\n",PWBASE_VARIANT,
           (void *)measure,(void *)&data_word,(void *)&stack_word,getpid());
    note("PWBASE %s text_delta=0x%llx\n",PWBASE_VARIANT,
         (unsigned long long)((uintptr_t)__text_start-(uintptr_t)PWBASE_LINKED));
    memory_map();
    map_low();
}

/* closes the title; without LoadExec the screen stays and asks the user to close it */
static void close_title(void)
{
    int rc=load_exec("exit");
    note("PWBASE %s close load_exec rc=0x%08x\n",PWBASE_VARIANT,(unsigned)rc);
    if(!rc) for(int i=0;i<100;i++) sceKernelUsleep(100000);
    note("PWBASE %s close the app from the PS4 menu\n",PWBASE_VARIANT);
    for(;;){if(pixels)pw_wine_present(pixels,W,H,W*4);sceKernelUsleep(1000000);}
}

/* starts the next stage that accepts LoadExec; returns only when none is left */
static void start_stages(int next)
{
    for(;next<STAGE_COUNT;next++) {
        char path[64];snprintf(path,sizeof(path),"/app0/pwbase_%s.bin",stages[next]);
        write_state(next,1);
        note("PWBASE driver stage_start %s\n",stages[next]);
        int rc=load_exec(path);
        note("PWBASE driver stage_load_exec %s rc=0x%08x\n",stages[next],(unsigned)rc);
        if(!rc) {for(int i=0;i<100;i++) sceKernelUsleep(100000);return;}
    }
    write_state(STAGE_COUNT,0);
}
#endif

#ifdef PWBASE_CONTROL_ONLY
/* step 1: what H001B does first (the log file, the screen) and nothing else; it stays open
 * like H001B and is closed from the PS4 menu */
int main(void)
{
    mkdir(PWBASE_DIR,0777);
    log_fd=open(PWBASE_LOG,O_WRONLY|O_CREAT|O_APPEND,0666);
    screen_open();
    note("PWBASE control_only log_fd=%d text=%p\n",log_fd,(void *)__text_start);
    note("PWBASE control_only ok: close the app from the PS4 menu\n");
    for(;;){if(pixels)pw_wine_present(pixels,W,H,W*4);sceKernelUsleep(1000000);}
}
#else
int main(void)
{
    mkdir(PWBASE_DIR,0777);
    log_fd=open(PWBASE_LOG,O_WRONLY|O_CREAT|O_APPEND,0666);
    screen_open();
    if(PWBASE_INDEX>=0) {
        /* a stage: it reached main; the driver continues after it */
        write_state(PWBASE_INDEX+1,0);
        measure();
        int rc=load_exec(PWBASE_DRIVER_SELF);
        note("PWBASE %s driver_load_exec rc=0x%08x\n",PWBASE_VARIANT,(unsigned)rc);
        if(!rc) for(int i=0;i<100;i++) sceKernelUsleep(100000);
        close_title();
    }
    /* the first open is only the control: the file, the screen, a pause, and a close */
    int control=open(PWBASE_CONTROL,O_WRONLY|O_CREAT|O_EXCL,0666);
    if(control>=0) {
        close(control);
        note("PWBASE driver control log_fd=%d text=%p\n",log_fd,(void *)__text_start);
        note("PWBASE driver control ok: open the app again for the stages\n");
        sceKernelUsleep(5000000);
        close_title();
    }
    int next,pending;read_state(&next,&pending);
    note("PWBASE driver open next=%d pending=%d stages=%d\n",next,pending,STAGE_COUNT);
    if(next==0 && !pending) {
        measure();
#ifndef PWBASE_NO_SELF_UNMAP
        self_unmap();
#endif
    }
    if(pending && next<STAGE_COUNT) {
        note("PWBASE driver stage_did_not_start %s\n",stages[next]);
        next++;
    }
    if(next<STAGE_COUNT) start_stages(next);
    read_state(&next,&pending);
    if(next>=STAGE_COUNT && !pending) note("PWBASE driver done\n");
    close_title();
    return 0;
}
#endif
