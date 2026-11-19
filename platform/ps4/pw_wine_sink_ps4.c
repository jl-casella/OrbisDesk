/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Presentation sink of the in-process Wine user driver (win32u ps5drv.c).
 * Each composed desktop frame is scaled into one of two 1280x720 linear
 * sceVideoOut buffers and flipped. Each frame whose content changed is also written to
 * /data/frames as a BMP file (up to 24) and frame hashes are logged, so a run leaves
 * evidence that can be compared outside the emulator. There is no input
 * source yet: pw_wine_next_input reports no events.
 * W142: built with PW_SINK_GPU (hardware), the desktop lives in GPU-readable memory and RADV
 * draws each output frame (native/hw_sink_gpu); the CPU copy below stays as the fallback,
 * into the same buffers. */
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#include <orbis/libkernel.h>
#include <orbis/VideoOut.h>

/* A build may lower the BMP dumps (each is a synchronous ~2 MB write before the flip)
 * and add process time to the frame markers. The defaults keep the fork evidence. */
#ifndef PW_SINK_MAX_DUMPS
#define PW_SINK_MAX_DUMPS 24
#endif
#ifndef PW_SINK_TIMING
#define PW_SINK_TIMING 0
#endif
/* frame generation's display (stage 4) needs the GPU compositor, the presenter thread and the hardware launcher */
#if defined(PW_SINK_GPU) && defined(PW_SINK_ASYNC) && defined(PW_SINK_EXTERNAL_INPUT)
#define PW_FG_DISPLAY 1
#endif
enum {OUT_WIDTH=1280,OUT_HEIGHT=720,OUT_BUFFERS=2,MAX_DUMPS=PW_SINK_MAX_DUMPS};
/* alpha-1 (pw_trace.h): without traces no BMP dumps (each a synchronous multi-MB write, and the CPU path hashed
 * every frame while dumps were left), no periodic frame lines, no show() timing. The first 8 frame_presented
 * lines stay: they are the run's "presented" evidence (tools/fetch-hardware.py). */
#include "pw_trace.h"
#define DUMP_LIMIT (pw_trace_on()?MAX_DUMPS:0)
enum {FORMAT_A8R8G8B8_SRGB=(int)0x80000000,TILING_LINEAR=1,USER_MAIN=255,FLIP_VSYNC=1};
static pthread_mutex_t lock=PTHREAD_MUTEX_INITIALIZER;
static int handle=-1,failed;
static uint32_t *buffers[OUT_BUFFERS];
static unsigned pitch=OUT_WIDTH;
/* W144: a window or the wallpaper as ps5drv stacks them (struct ps5_layer in ps5drv.c).
 * W152: or a Vulkan program's presented image, scaled from source_width x source_height to the
 * rect (flags: 1 an image outside the pool, 2 its words are R,G,B,A; native/hw_sink_gpu). */
struct pw_wine_layer {const uint32_t *pixels;int left,top,right,bottom;unsigned stride,flags,source_width,source_height;};
enum {MAX_LAYERS=65};
static int layered;     /* the last frame is layers[], not last.bgra */
#ifdef PW_SINK_GPU
extern void *pw_sink_gpu_alloc(size_t bytes);
extern int pw_sink_gpu_free(void *pixels);
extern int pw_sink_gpu_images(void);
extern int pw_sink_gpu_draw_layers(unsigned buffer,const struct pw_wine_layer *layers,unsigned count,unsigned width,
                                   unsigned height,int left,int top,int scale_w,int scale_h,int cursor_x,int cursor_y);
static struct pw_wine_layer layers[MAX_LAYERS];
static unsigned layer_count,layer_width,layer_height;
static int dump_wanted; /* dump the next drawn output buffer (layers have no desktop buffer to dump) */
static int layers_stale;/* a layer was freed since the last stack: wait for the next one */
extern void *pw_sink_gpu_screen(unsigned width,unsigned height);
extern int pw_sink_gpu_buffers(int video,unsigned width,unsigned height,uint32_t **pixels,unsigned *pitch);
extern int pw_sink_gpu_draw(unsigned buffer,unsigned stride,int left,int top,int scale_w,int scale_h,int cursor_x,int cursor_y);
static const void *gpu_screen;
static unsigned gpu_width,gpu_height;
static int gpu;
#endif
/* ps5drv's desktop memory: GPU-readable when the sink draws through the GPU, else NULL (calloc) */
void *pw_wine_screen_memory(unsigned int width,unsigned int height);
void *pw_wine_screen_memory(unsigned int width,unsigned int height)
{
#ifdef PW_SINK_GPU
    pthread_mutex_lock(&lock);
    if(!gpu_screen && (gpu_screen=pw_sink_gpu_screen(width,height))) {gpu_width=width;gpu_height=height;}
    void *result=(void *)gpu_screen;
    pthread_mutex_unlock(&lock);
    return result;
#else
    (void)width;(void)height;
    return NULL;
#endif
}
static uint64_t frames;
static unsigned dumps;
/* W242: the windows Vulkan swapchains presented to (win32u vulkan.c pw_vk_show_frame), for the overlay:
 * MangoHud counts only for the program in front (kernelbase's closer, through native/hw_pad.c). Outside
 * PW_SINK_EXTERNAL_INPUT: win32u calls it in every ELF. */
enum {VK_WINDOWS=4,VK_WINDOW_FRESH_US=2000000};
static pthread_mutex_t vk_windows_lock=PTHREAD_MUTEX_INITIALIZER;
static struct {unsigned long long hwnd;uint64_t us;} vk_windows[VK_WINDOWS];
void pw_wine_vk_window_presented(unsigned long long hwnd);
void pw_wine_vk_window_presented(unsigned long long hwnd)
{
    uint64_t now=sceKernelGetProcessTime();
    unsigned i,slot=0;
    pthread_mutex_lock(&vk_windows_lock);
    for(i=0;i<VK_WINDOWS;i++) {
        if(vk_windows[i].hwnd==hwnd) {slot=i;break;}
        if(vk_windows[i].us<vk_windows[slot].us) slot=i;  /* else the oldest, or an empty one */
    }
    vk_windows[slot].hwnd=hwnd;vk_windows[slot].us=now;
    pthread_mutex_unlock(&vk_windows_lock);
}
/* those presented in the last 2 s; returns how many */
int pw_hw_sink_vk_windows(unsigned long long *out,int max);
int pw_hw_sink_vk_windows(unsigned long long *out,int max)
{
    uint64_t now=sceKernelGetProcessTime();
    int n=0;
    pthread_mutex_lock(&vk_windows_lock);
    for(unsigned i=0;i<VK_WINDOWS && n<max;i++)
        if(vk_windows[i].hwnd && now-vk_windows[i].us<VK_WINDOW_FRESH_US) out[n++]=vk_windows[i].hwnd;
    pthread_mutex_unlock(&vk_windows_lock);
    return n;
}
static uint64_t last_dump_hash;

static int open_video(void)
{
    const size_t bytes=(size_t)OUT_WIDTH*OUT_HEIGHT*4,aligned=(bytes+0x1fffff)&~(size_t)0x1fffff;
    off_t physical=0;void *memory=NULL;
    handle=sceVideoOutOpen(USER_MAIN,0,0,NULL);
    if(handle<0) {fprintf(stderr,"PWBOOT video_out_blocked open rc=%x\n",handle);return -1;}
#ifdef PW_SINK_GPU
    if(!pw_sink_gpu_buffers(handle,OUT_WIDTH,OUT_HEIGHT,buffers,&pitch)) {
        gpu=1;
        fprintf(stderr,"PWBOOT video_out_ready %ux%u buffers=%u gpu=1 pitch=%u\n",OUT_WIDTH,OUT_HEIGHT,OUT_BUFFERS,pitch);
        return 0;
    }
    fprintf(stderr,"PWSINK gpu_unavailable: CPU copy\n");
#endif
    int rc=sceKernelAllocateDirectMemory(0,sceKernelGetDirectMemorySize(),aligned*OUT_BUFFERS,0x200000,3,&physical);
    if(!rc) rc=sceKernelMapDirectMemory(&memory,aligned*OUT_BUFFERS,0x33,0,physical,0x200000);
    if(rc) {fprintf(stderr,"PWBOOT video_out_blocked memory rc=%x\n",rc);return -1;}
    OrbisVideoOutBufferAttribute attribute;memset(&attribute,0,sizeof(attribute));
    sceVideoOutSetBufferAttribute(&attribute,FORMAT_A8R8G8B8_SRGB,TILING_LINEAR,0,OUT_WIDTH,OUT_HEIGHT,OUT_WIDTH);
    void *addresses[OUT_BUFFERS];
    for(int i=0;i<OUT_BUFFERS;++i) {
        buffers[i]=(uint32_t *)((char *)memory+aligned*i);memset(buffers[i],0,bytes);addresses[i]=buffers[i];
    }
    rc=sceVideoOutRegisterBuffers(handle,0,addresses,OUT_BUFFERS,&attribute);
    if(rc) {fprintf(stderr,"PWBOOT video_out_blocked register rc=%x\n",rc);return -1;}
    fprintf(stderr,"PWBOOT video_out_ready %ux%u buffers=%u\n",OUT_WIDTH,OUT_HEIGHT,OUT_BUFFERS);
    return 0;
}
static uint64_t frame_hash(const uint8_t *bgra,uint32_t width,uint32_t height,uint32_t stride)
{
    uint64_t hash=UINT64_C(0xcbf29ce484222325);
    for(uint32_t y=0;y<height;++y)
        for(uint32_t x=0;x<width*4;++x) hash=(hash^bgra[(size_t)y*stride+x])*UINT64_C(0x100000001b3);
    return hash;
}
static void put32(uint8_t *at,uint32_t value) {for(int i=0;i<4;++i) at[i]=(uint8_t)(value>>(8*i));}
static void dump(const uint8_t *bgra,uint32_t width,uint32_t height,uint32_t stride)
{
    char path[64];uint8_t header[54]={'B','M'};
    mkdir("/data/frames",0755);
    snprintf(path,sizeof(path),"/data/frames/frame-%06llu.bmp",(unsigned long long)frames);
    int fd=open(path,O_CREAT|O_TRUNC|O_WRONLY,0644);
    if(fd<0) return;
    put32(header+2,54+width*height*4);put32(header+10,54);put32(header+14,40);put32(header+18,width);
    put32(header+22,(uint32_t)-(int32_t)height);header[26]=1;header[28]=32;put32(header+34,width*height*4);
    int ok=write(fd,header,sizeof(header))==(ssize_t)sizeof(header);
    for(uint32_t y=0;ok && y<height;++y) ok=write(fd,bgra+(size_t)y*stride,width*4)==(ssize_t)(width*4);
    close(fd);
}
/* The desktop buffer win32u presents stays allocated for the whole run. */
static struct {const uint8_t *bgra;uint32_t width,height,stride;} last;
static uint64_t flips;
#ifdef PW_SINK_EXTERNAL_INPUT
extern int pw_hw_cursor(int *x,int *y,int *width,int *height);
/* An 11x17 arrow: 1 outline, 2 fill, anything else transparent. */
static const char *const arrow[]={
    "1","11","121","1221","12221","122221","1222221","12222221","122222221","1222222221",
    "12222211111","1221221","121 1221","11  1221","1    1221","     1221","      11"};
/* W256: hidden in a full-screen game without a cursor of its own (ps5drv.c ps5_SetCursor). W261: the overlay's
 * cursor mode for the program in front decides: game (that rule), always, or hidden */
static volatile int pointer_hidden;
extern int pw_hw_cursor_mode(void);  /* native/hw_overlay.c: 0 game, 1 always, 2 hidden */
extern int pw_hw_overlay_stretch(void);  /* W266: native/hw_overlay.c, 1 to fill the output */
extern int pw_hw_busy_frame(void);  /* W293: native/hw_overlay.c, 0-7 while a program starts, -1 otherwise */
static int pointer_off(void)
{
    int mode=pw_hw_cursor_mode();
    return mode==2 || (mode!=1 && pointer_hidden);
}
static void draw_cursor(uint32_t *target,uint32_t left,uint32_t top,uint32_t scale_w,uint32_t scale_h)
{
    int x,y,w,h;
    if(pointer_off() || !pw_hw_cursor(&x,&y,&w,&h) || w<=0 || h<=0) return;
    int ox=(int)left+(int)((int64_t)x*scale_w/w),oy=(int)top+(int)((int64_t)y*scale_h/h);
    for(int r=0;r<(int)(sizeof(arrow)/sizeof(arrow[0]));++r)
        for(int c=0;arrow[r][c];++c) {
            int px=ox+c,py=oy+r;
            if(px<0 || py<0 || px>=OUT_WIDTH || py>=OUT_HEIGHT) continue;
            if(arrow[r][c]=='1') target[(size_t)py*pitch+px]=0xff000000u;
            else if(arrow[r][c]=='2') target[(size_t)py*pitch+px]=0xffffffffu;
        }
}
/* where draw_cursor puts the arrow's top-left pixel; 0 when there is no pointer */
static int cursor_origin(uint32_t left,uint32_t top,uint32_t scale_w,uint32_t scale_h,int *ox,int *oy)
{
    int x,y,w,h;
    if(pointer_off() || !pw_hw_cursor(&x,&y,&w,&h) || w<=0 || h<=0) return 0;
    *ox=(int)left+(int)((int64_t)x*scale_w/w);*oy=(int)top+(int)((int64_t)y*scale_h/h);
    return 1;
}
/* W293: while a program starts (native/hw_overlay.c), eight dots in a ring by the arrow, lower right, as Windows'
 * IDC_APPSTARTING; the brightest turns with the frame. Drawn into the output after the GPU or CPU has drawn it. */
static void draw_busy(uint32_t *target,uint32_t left,uint32_t top,uint32_t scale_w,uint32_t scale_h)
{
    static const signed char dots[8][2]={{6,0},{4,4},{0,6},{-4,4},{-6,0},{-4,-4},{0,-6},{4,-4}};
    int frame=pw_hw_busy_frame(),ox,oy;
    if(frame<0 || !cursor_origin(left,top,scale_w,scale_h,&ox,&oy)) return;
    for(int i=0;i<8;++i) {
        int age=(frame-i+8)%8;  /* 0 the brightest, then the ones behind it */
        uint32_t color=!age?0xffffffffu:age<3?0xffb0b0b0u:0xff606060u;
        int cx=ox+18+dots[i][0],cy=oy+18+dots[i][1];
        for(int y=-2;y<2;++y)
            for(int x=-2;x<2;++x) {
                int px=cx+x,py=cy+y;
                if(px<0 || py<0 || px>=OUT_WIDTH || py>=OUT_HEIGHT) continue;
                target[(size_t)py*pitch+px]=x==-2 || y==-2 || x==1 || y==1?0xff000000u:color;
            }
    }
}
#endif
/* time spent in show() per output frame, by path, logged every 300 frames */
static void show_stats(const char *path,uint64_t start)
{
    static uint64_t total,worst,count;
    if(!pw_trace_on()) return;
    uint64_t spent=sceKernelGetProcessTime()-start;
    total+=spent;if(spent>worst) worst=spent;
    if(++count%300) return;
    fprintf(stderr,"PWSINK show_stats path=%s n=%llu avg_us=%llu max_us=%llu\n",path,(unsigned long long)count,
            (unsigned long long)(total/300),(unsigned long long)worst);
    total=worst=0;
}
#ifdef PW_SINK_GPU
static void dump_output(const uint32_t *target)
{
    dump_wanted=0;
    uint64_t hash=frame_hash((const uint8_t *)target,OUT_WIDTH,OUT_HEIGHT,pitch*4);
    if(dumps<DUMP_LIMIT && hash!=last_dump_hash) {
        dump((const uint8_t *)target,OUT_WIDTH,OUT_HEIGHT,pitch*4);++dumps;last_dump_hash=hash;
        fprintf(stderr,"PWSINK dump frame=%llu layers=%u\n",(unsigned long long)frames,layer_count);
    }
}
#endif
#ifdef PW_SINK_EXTERNAL_INPUT
/* W165: a frame counter in the output's top-left corner, hidden at start and toggled with F12
 * (native/hw_pad.c), as MangoHud's. It shows the presents per second of a Vulkan program
 * (native/wine_vk_runtime.c reports them once a second) while one presents, else the frames this
 * sink shows. Drawn into the output buffer after the GPU or CPU has drawn it, before the flip. */
#include "hw_text.h"
static int fps_overlay;
static unsigned vk_fps_tenths,sink_fps_tenths,sink_second_flips;
static uint64_t vk_fps_us,sink_second_us;
static void draw_fps(uint32_t *target,uint64_t now)
{
    ++sink_second_flips;
    if(!sink_second_us) sink_second_us=now;
    if(now-sink_second_us>=1000000) {
        sink_fps_tenths=(unsigned)(sink_second_flips*10000000ull/(now-sink_second_us));
        sink_second_flips=0;sink_second_us=now;
    }
    /* W166: only while a Vulkan program presents (a game, glxgears): not over the plain desktop */
    if(!fps_overlay || !vk_fps_us || now-vk_fps_us>=2000000) return;
    unsigned tenths=vk_fps_tenths;
    char text[24];
    snprintf(text,sizeof(text),"FPS %u.%u",tenths/10,tenths%10);
    enum {SCALE=3,X=12,Y=12,PAD=6};
    int w=(int)strlen(text)*6*SCALE+2*PAD,h=7*SCALE+2*PAD;
    for(int y=Y-PAD;y<Y-PAD+h;++y)
        for(int x=X-PAD;x<X-PAD+w;++x) target[(size_t)y*pitch+x]=0xff000000u;
    hw_text(target,(int)pitch,OUT_HEIGHT,X,Y,text,0xffffff00u,SCALE);
}
/* W236: the frames Wine hands to the sink (pw_wine_present, pw_wine_present_layers), per second with
 * their mean and longest interval, for the overlay's readout (native/hw_overlay.c); lock held */
static uint64_t handed_last_us,handed_second_us,handed_sum_us,handed_max_us;
static unsigned handed_count,handed_tenths,handed_avg_us,handed_peak_us;
static void frame_handed(void)
{
    uint64_t now=sceKernelGetProcessTime();
    if(handed_last_us) {
        uint64_t interval=now-handed_last_us;
        handed_sum_us+=interval;if(interval>handed_max_us) handed_max_us=interval;++handed_count;
    }
    handed_last_us=now;
    if(!handed_second_us) handed_second_us=now;
    if(now-handed_second_us>=1000000 && handed_count) {
        handed_tenths=(unsigned)(handed_count*10000000ull/(now-handed_second_us));
        handed_avg_us=(unsigned)(handed_sum_us/handed_count);handed_peak_us=(unsigned)handed_max_us;
        handed_second_us=now;handed_sum_us=handed_max_us=0;handed_count=0;
    }
}
/* fresh: measured within the last 2 s */
void pw_hw_sink_stats(unsigned *vk_tenths,int *vk_fresh,unsigned *frames_tenths,unsigned *avg_us,unsigned *max_us,int *frames_fresh);
void pw_hw_sink_stats(unsigned *vk_tenths,int *vk_fresh,unsigned *frames_tenths,unsigned *avg_us,unsigned *max_us,int *frames_fresh)
{
    pthread_mutex_lock(&lock);
    uint64_t now=sceKernelGetProcessTime();
    *vk_tenths=vk_fps_tenths;*vk_fresh=vk_fps_us && now-vk_fps_us<2000000;
    *frames_tenths=handed_tenths;*avg_us=handed_avg_us;*max_us=handed_peak_us;
    *frames_fresh=handed_tenths && handed_last_us && now-handed_last_us<2000000;
    pthread_mutex_unlock(&lock);
}
/* Frame generation, stage 1 (docs/FRAME_GENERATION.md): observation only, nothing shown changes.
 * - sources: every Vulkan present (native/wine_vk_runtime.c pw_vk_present_hook) with its process time, per
 *   swapchain: presents, intervals (mean, deviation, extremes) and how many vblank periods each one spans;
 * - the output: each flip this sink submits carries the present count Wine had handed over when it was drawn;
 *   VideoOut's flip status says which flip completed last and when, its vblank status how many vblanks went by,
 *   so a window reports flips submitted and completed, completed flips that carried a new source frame, vblanks
 *   that showed no new flip (the previous buffer again), and submit-to-completion time;
 * - generated frames: counted apart from rendered and displayed ones (stage 3 makes them, nothing shows them).
 * A line every 2 s ("PWFG timing", "PWFG source") only with /data/orbisdesk/framegen.txt present (traces alone
 * hook nothing, so every other run is unchanged).
 * The flip status is read when the sink is about to flip, so two flips completing between two reads count
 * once each but only the newest has a completion time. */
#define FG_CONFIG "/data/orbisdesk/framegen.txt"
enum {FT_SOURCES=4,FT_FLIPS=64,FT_BUCKETS=6,FT_REPORT_US=2000000,FT_FRESH_US=1000000,FT_NOMINAL_PERIOD_US=16683};
struct ft_source {
    const void *swapchain;unsigned width,height;int format;
    uint64_t last_us,presents;                       /* since the swapchain (or its size) appeared */
    uint64_t n,sum_us,sumsq_us,min_us,max_us;        /* intervals in the current window */
    unsigned bucket[FT_BUCKETS];                     /* interval in vblank periods: <0.5,1,2,3,4,5+ */
};
static pthread_mutex_t ft_lock=PTHREAD_MUTEX_INITIALIZER;   /* the presenting threads write sources */
static struct ft_source ft_sources[FT_SOURCES];
static uint64_t ft_present_seq;                      /* presents of every swapchain together */
static volatile unsigned ft_period_us=FT_NOMINAL_PERIOD_US;  /* measured from vblanks when known */
static int ft_logging=-1;                            /* -1 not decided yet */
/* 0 off; 1 timing only; 2 shadow: generated, never shown (stage 3); 3 display: shown between real frames (stage 4) */
enum {FG_OFF,FG_TIMING,FG_SHADOW,FG_DISPLAY};
static const char *const fg_mode_words[4]={"off","timing","shadow","display"};
static int fg_file_mode=-1;                          /* framegen.txt's mode, -1 without the file (the overlay decides) */
static volatile int fg_mode;                         /* in force: the file's, else the overlay's for the program in front */
static volatile int fg_generator_off;                /* the generator failed and freed itself for the run */
/* sink lock held from here on */
static uint64_t ft_handed_seq;                       /* ft_present_seq when Wine last handed a frame over */
static struct {uint64_t arg,seq,submit_us;int generated;} ft_flip[FT_FLIPS];
static uint64_t ft_done_arg,ft_shown_seq,ft_window_us,ft_vb_count0,ft_vb_us0;
static unsigned ft_submitted,ft_done,ft_new_shown,ft_latency_n,ft_latency_max_us,ft_pending_max,ft_status_failed;
static uint64_t ft_latency_sum_us;
static volatile unsigned ft_generated,ft_generated_failed,ft_generated_shown;
/* VideoOut's vblank status. The SDK declares sceVideoOutGetVblankStatus without parameters (VideoOut.h); this
 * is its layout as libSceVideoOut fills it: count, process time (us), TSC, then flags. */
struct pw_vblank_status {uint64_t count,process_time,tsc,reserved;uint8_t flags,pad[7];};
static int vblank_status(struct pw_vblank_status *status)
{
    return ((int (*)(int,struct pw_vblank_status *))sceVideoOutGetVblankStatus)(handle,status);
}
/* FPS LIMIT (docs/FPS_LIMIT.md): the overlay's per-program choice (native/hw_overlay.c pw_hw_overlay_fps_limit), Off,
 * 30, 60 or Auto, paces the program's Vulkan presents (DXVK, wined3d's Vulkan renderer, Zink under wined3d's OpenGL,
 * native Vulkan; 32- and 64-bit guests alike: they all present through win32u's vkQueuePresentKHR). The thread that
 * presents is held, before its present returns, until the vblank pw_fps_limit.h names; the frame then goes on to the
 * window and this sink as before. Nothing is dropped or made up and the game's own timing is not touched: a game
 * that waits on its present simply runs at the cap.
 * The vblank count is trusted once it has been seen to advance at about the refresh rate over a second; until then
 * (or if it stops) the hold is by time from the last release. */
#include "pw_fps_limit.h"
extern int pw_hw_overlay_fps_limit(void);
enum {FL_CHAINS=4,FL_REPORT_US=5000000,FL_POLL_US=250,FL_EARLY_US=1500,FL_SLACK_US=4000,FL_TRUST_US=1000000};
static pthread_mutex_t fl_lock=PTHREAD_MUTEX_INITIALIZER;
static struct pw_fpsl_auto fl_auto;
static struct pw_fpsl_chain fl_chains[FL_CHAINS];
static unsigned fl_period_us=FT_NOMINAL_PERIOD_US;
static int fl_vblank_trusted;
static uint64_t fl_vb_count0,fl_vb_us0,fl_report_us;
static unsigned fl_presents,fl_held,fl_late,fl_held_max_us,fl_status_failed,fl_switches;
static uint64_t fl_held_sum_us;
static const char *fl_word(int setting)
{
    return setting==FPSL_30?"30":setting==FPSL_60?"60":setting==FPSL_AUTO?"auto":"off";
}
/* fl_lock held: the vblank count against the clock, over at least FL_TRUST_US */
static void fl_check_vblank(uint64_t now,int vb_ok,const struct pw_vblank_status *vb)
{
    if(!vb_ok) {++fl_status_failed;fl_vblank_trusted=0;fl_vb_us0=0;return;}
    if(!fl_vb_us0) {fl_vb_count0=vb->count;fl_vb_us0=now;return;}
    if(now-fl_vb_us0<FL_TRUST_US) return;
    uint64_t counted=vb->count>fl_vb_count0?vb->count-fl_vb_count0:0,expected=(now-fl_vb_us0)/FT_NOMINAL_PERIOD_US;
    int trusted=counted*2>=expected && counted<=expected*2;
    if(trusted) {
        unsigned period=(unsigned)((now-fl_vb_us0)/counted);
        if(period>5000 && period<50000) fl_period_us=period;
    }
    if(trusted!=fl_vblank_trusted)
        if(pw_trace_on()) fprintf(stderr,"PWFPS vblank count %s: %llu in %llu us (period_us=%u)\n",trusted?"trusted":"not trusted",
                (unsigned long long)counted,(unsigned long long)(now-fl_vb_us0),fl_period_us);
    fl_vblank_trusted=trusted;fl_vb_count0=vb->count;fl_vb_us0=now;
}
/* fl_lock held */
static void fl_report(uint64_t now)
{
    if(!pw_trace_on()) return;  /* alpha 2: a line every 5 s, traces only */
    if(!fl_report_us) {fl_report_us=now;return;}
    if(now-fl_report_us<FL_REPORT_US) return;
    fprintf(stderr,"PWFPS limit=%s cap=%d presents=%u held=%u held_us_avg=%u held_us_max=%u late=%u pacing=%s "
            "period_us=%u potential_x10=%u high_needed=%d switches=%u status_failed=%u\n",fl_word(fl_auto.setting),
            fl_auto.cap,fl_presents,fl_held,fl_held?(unsigned)(fl_held_sum_us/fl_held):0,fl_held_max_us,fl_late,
            fl_vblank_trusted?"vblank":"time",fl_period_us,fl_auto.last_potential_x10,fl_auto.high_needed,fl_switches,
            fl_status_failed);
    fl_presents=fl_held=fl_late=fl_held_max_us=fl_status_failed=fl_switches=0;fl_held_sum_us=0;fl_report_us=now;
}
/* the presenting thread, before its present returns (after the frame-generation copy, which needs the pixels).
 * Returns how many vblanks after the swapchain's previous release this present was let go, 0 when that is not
 * known (no limit, no previous release, the vblank count not trusted): frame generation's display needs 2. */
static int fl_present(const void *swapchain)
{
    int setting=pw_hw_overlay_fps_limit(),cap,was,span=0;
    if(setting==FPSL_OFF && fl_auto.setting==FPSL_OFF) return 0;  /* no lock */
    uint64_t now=sceKernelGetProcessTime(),target_vb=0,target_us=0,start=now;
    struct pw_vblank_status vb;memset(&vb,0,sizeof(vb));
    int vb_ok=!vblank_status(&vb);
    pthread_mutex_lock(&fl_lock);
    if(pw_fpsl_setting(&fl_auto,setting)) {
        fprintf(stderr,"PWFPS limit=%s cap=%d\n",fl_word(setting),fl_auto.cap);
        memset(fl_chains,0,sizeof(fl_chains));
        fl_presents=fl_held=fl_late=fl_held_max_us=fl_switches=0;fl_held_sum_us=0;fl_report_us=0;
    }
    if(setting==FPSL_OFF) {pthread_mutex_unlock(&fl_lock);return 0;}
    fl_check_vblank(now,vb_ok,&vb);
    struct pw_fpsl_chain *c=NULL;
    for(unsigned i=0;i<FL_CHAINS && !c;i++) if(fl_chains[i].swapchain==swapchain) c=&fl_chains[i];
    if(!c) {
        c=&fl_chains[0];
        for(unsigned i=1;i<FL_CHAINS;i++) if(fl_chains[i].release_us<c->release_us) c=&fl_chains[i];
        memset(c,0,sizeof(*c));c->swapchain=swapchain;
    }
    if(c->release_us && pw_fpsl_auto_frame(&fl_auto,now,now-c->release_us,&was)) {
        ++fl_switches;
        if(pw_trace_on()) fprintf(stderr,"PWFPS auto cap %d->%d potential_x10=%u high_needed=%d\n",was,fl_auto.cap,
                fl_auto.last_potential_x10,fl_auto.high_needed);
    }
    cap=fl_auto.cap;
    int trusted=fl_vblank_trusted && vb_ok;
    unsigned period=fl_period_us;
    if(trusted && c->release_vblank) target_vb=pw_fpsl_target_vblank(c,cap,vb.count);
    else target_us=pw_fpsl_target_time(c,cap,period,now);
    if(c->release_us && cap && !target_vb && !target_us) ++fl_late;
    pthread_mutex_unlock(&fl_lock);

    if(target_vb) {
        uint64_t deadline=now+(target_vb-vb.count)*period+FL_SLACK_US;
        /* asleep until just before the vblank, when VideoOut's time for the last one reads as this clock's */
        if(vb.process_time<=now && now-vb.process_time<period+2000) {
            uint64_t predicted=vb.process_time+(target_vb-vb.count)*period;
            if(predicted>now+FL_EARLY_US) sceKernelUsleep((unsigned)(predicted-FL_EARLY_US-now));
        }
        while(vb.count<target_vb && sceKernelGetProcessTime()<deadline) {
            sceKernelUsleep(FL_POLL_US);
            if(vblank_status(&vb)) {vb_ok=0;break;}
        }
    } else if(target_us) sceKernelUsleep((unsigned)(target_us-now));
    uint64_t release=target_vb || target_us?sceKernelGetProcessTime():now;

    pthread_mutex_lock(&fl_lock);
    if(c->swapchain==swapchain) {
        uint64_t release_vblank=vb_ok && fl_vblank_trusted?vb.count:0;
        if(release_vblank && c->release_vblank && release_vblank>c->release_vblank && release_vblank-c->release_vblank<8)
            span=(int)(release_vblank-c->release_vblank);
        c->release_us=release;c->release_vblank=release_vblank;
    }
    ++fl_presents;
    if(release>start) {
        unsigned held=(unsigned)(release-start);
        ++fl_held;fl_held_sum_us+=held;if(held>fl_held_max_us) fl_held_max_us=held;
    }
    fl_report(release);
    pthread_mutex_unlock(&fl_lock);
    return span;
}
/* 04.27 (docs/SHADER_CACHE.md): frame time against shader and pipeline compiles. RADV
 * (tools/vk-h0/patch-mesa-pipeline-trace.py) notes every vkCreate*Pipelines and vkCreateShadersEXT create, so DXVK's,
 * Zink's and native Vulkan programs' compiles all land here, on whichever thread made them. Every 5 s one PWPERF line
 * gives the window's present intervals, its compiles and their time, the compile time that fell inside the longest
 * frame and inside each hitch (a frame over twice the previous window's average and at least 40 ms), and the GPU's,
 * the process's and the presenting thread's busy share. Hitches with compile time in them point at compiles; every
 * frame long with few compiles and a busy GPU or thread points at a sustained limit instead. Independent of
 * FPS LIMIT and frame generation: one call per present, one per create. */
#include <sys/resource.h>
#ifndef RUSAGE_THREAD
#define RUSAGE_THREAD 1
#endif
enum {PF_REPORT_US=5000000,PF_SLOW_US=50000,PF_SLOW_LINES=8,PF_HITCH_MIN_US=40000,PF_HITCH_COMPILE_NS=10000000};
enum {PF_GFX,PF_LIB,PF_COMPUTE,PF_SHADER,PF_KINDS};
static const char *const pf_kind_words[PF_KINDS]={"gfx","lib","compute","shader"};
static pthread_mutex_t pf_lock=PTHREAD_MUTEX_INITIALIZER;
static uint64_t pf_window_us,pf_last_us,pf_since_ns,pf_prev_avg_us;
static uint64_t pf_frame_sum_us,pf_frame_max_us,pf_worst_frame_ns,pf_kind_ns[PF_KINDS],pf_miss_ns;
static unsigned pf_frames,pf_over_50ms,pf_over_100ms,pf_hitches,pf_hitch_compiles;
static unsigned pf_kind_count[PF_KINDS],pf_hits,pf_disk,pf_misses,pf_max_us,pf_slow_lines;
static uint64_t pf_gpu_busy0,pf_gpu_span0,pf_gpu_lost0,pf_cpu_ns0,pf_thread_ns0;
static pthread_t pf_thread;
static int pf_thread_set;
/* the RADV winsys's GPU timestamp union (tools/vk-h0/patch-crema-telemetry.py); weak: absent in links without RADV */
extern void ac_ps4_get_gpu_app_busy(uint64_t *busy,uint64_t *span,uint64_t *lost) __attribute__((weak));
void pw_vk_pipeline_note(unsigned kind,uint64_t ns,unsigned flags);
/* RADV, on the creating thread: kind (pw_pipeline_trace.h), the create's time, flags 1 found in a cache, 2 read from
 * the disk cache */
void pw_vk_pipeline_note(unsigned kind,uint64_t ns,unsigned flags)
{
    unsigned us=ns/1000>UINT32_MAX?UINT32_MAX:(unsigned)(ns/1000);
    int slow=0;
    if(!pw_trace_on()) return;  /* alpha 2: PWPERF, traces only */
    if(kind>=PF_KINDS) kind=PF_GFX;
    pthread_mutex_lock(&pf_lock);
    ++pf_kind_count[kind];pf_kind_ns[kind]+=ns;pf_since_ns+=ns;
    if(flags&1) ++pf_hits; else {++pf_misses;pf_miss_ns+=ns;}
    if(flags&2) ++pf_disk;
    if(us>pf_max_us) pf_max_us=us;
    if(us>=PF_SLOW_US && pf_slow_lines<PF_SLOW_LINES) {++pf_slow_lines;slow=1;}
    pthread_mutex_unlock(&pf_lock);
    if(slow) fprintf(stderr,"PWPERF slow_compile kind=%s us=%u cached=%u disk=%u\n",pf_kind_words[kind],us,flags&1,
                     (flags>>1)&1);
}
static uint64_t pf_cpu_ns(int who)
{
    struct rusage u;memset(&u,0,sizeof(u));
    if(getrusage(who,&u) || u.ru_utime.tv_sec<0 || u.ru_stime.tv_sec<0) return 0;
    return ((uint64_t)u.ru_utime.tv_sec+(uint64_t)u.ru_stime.tv_sec)*1000000000ull+
           ((uint64_t)u.ru_utime.tv_usec+(uint64_t)u.ru_stime.tv_usec)*1000ull;
}
/* pf_lock held: the busy counters a window starts from */
static void pf_start(uint64_t now)
{
    uint64_t lost=0;
    pf_gpu_busy0=pf_gpu_span0=0;
    if(ac_ps4_get_gpu_app_busy) ac_ps4_get_gpu_app_busy(&pf_gpu_busy0,&pf_gpu_span0,&lost);
    pf_gpu_lost0=lost;
    pf_cpu_ns0=pf_cpu_ns(RUSAGE_SELF);pf_thread_ns0=pf_cpu_ns(RUSAGE_THREAD);
    pf_thread=pthread_self();pf_thread_set=1;
    pf_window_us=now;
}
/* pf_lock held, on a presenting thread: the window's line into line, its counters cleared */
static void pf_report(uint64_t now,char *line,size_t size)
{
    uint64_t busy=0,span=0,lost=0,window=now-pf_window_us;
    uint64_t cpu=pf_cpu_ns(RUSAGE_SELF),thread=pf_cpu_ns(RUSAGE_THREAD),compile_ns=0;
    unsigned compiles=0;
    int gpu_pct=-1,cores_x10=-1,thread_pct=-1;
    if(ac_ps4_get_gpu_app_busy) ac_ps4_get_gpu_app_busy(&busy,&span,&lost);
    if(pf_gpu_span0 && span>pf_gpu_span0 && busy>=pf_gpu_busy0 && lost==pf_gpu_lost0 &&
       busy-pf_gpu_busy0<=span-pf_gpu_span0)
        gpu_pct=(int)((busy-pf_gpu_busy0)*100/(span-pf_gpu_span0));
    if(window && pf_cpu_ns0 && cpu>=pf_cpu_ns0) cores_x10=(int)((cpu-pf_cpu_ns0)/1000*10/window);
    /* the thread that presented at both ends: Zink's GL thread; DXVK presents from its own queue thread */
    if(window && pf_thread_set && pthread_equal(pf_thread,pthread_self()) && pf_thread_ns0 && thread>=pf_thread_ns0)
        thread_pct=(int)((thread-pf_thread_ns0)/1000*100/window);
    for(unsigned k=0;k<PF_KINDS;k++) {compiles+=pf_kind_count[k];compile_ns+=pf_kind_ns[k];}
    unsigned avg=pf_frames?(unsigned)(pf_frame_sum_us/pf_frames):0;
    snprintf(line,size,"PWPERF window_ms=%llu frames=%u frame_us_avg=%u frame_us_max=%llu over_50ms=%u over_100ms=%u "
             "hitches=%u hitches_with_compile=%u worst_frame_compile_us=%llu compiles=%u compile_ms=%llu "
             "compile_max_us=%u cached=%u disk=%u misses=%u miss_ms=%llu gfx=%u/%llums lib=%u/%llums "
             "compute=%u/%llums shader=%u/%llums gpu_busy_pct=%d cpu_cores_x10=%d present_thread_pct=%d\n",
             (unsigned long long)(window/1000),pf_frames,avg,(unsigned long long)pf_frame_max_us,pf_over_50ms,
             pf_over_100ms,pf_hitches,pf_hitch_compiles,(unsigned long long)(pf_worst_frame_ns/1000),compiles,
             (unsigned long long)(compile_ns/1000000),pf_max_us,pf_hits,pf_disk,pf_misses,
             (unsigned long long)(pf_miss_ns/1000000),
             pf_kind_count[PF_GFX],(unsigned long long)(pf_kind_ns[PF_GFX]/1000000),
             pf_kind_count[PF_LIB],(unsigned long long)(pf_kind_ns[PF_LIB]/1000000),
             pf_kind_count[PF_COMPUTE],(unsigned long long)(pf_kind_ns[PF_COMPUTE]/1000000),
             pf_kind_count[PF_SHADER],(unsigned long long)(pf_kind_ns[PF_SHADER]/1000000),gpu_pct,cores_x10,thread_pct);
    if(pf_frames) pf_prev_avg_us=avg;
    pf_frame_sum_us=pf_frame_max_us=pf_worst_frame_ns=pf_miss_ns=0;
    pf_frames=pf_over_50ms=pf_over_100ms=pf_hitches=pf_hitch_compiles=0;
    pf_hits=pf_disk=pf_misses=pf_max_us=pf_slow_lines=0;
    memset(pf_kind_count,0,sizeof(pf_kind_count));memset(pf_kind_ns,0,sizeof(pf_kind_ns));
}
/* each present, before FPS LIMIT holds it: the interval since the previous one, as the game sees it */
static void pf_present(void)
{
    if(!pw_trace_on()) return;  /* alpha 2: PWPERF, traces only */
    uint64_t now=sceKernelGetProcessTime();
    char line[640];line[0]=0;
    pthread_mutex_lock(&pf_lock);
    if(!pf_window_us) pf_start(now);
    else if(pf_last_us && now>pf_last_us) {
        uint64_t frame=now-pf_last_us;
        ++pf_frames;pf_frame_sum_us+=frame;
        if(frame>pf_frame_max_us) {pf_frame_max_us=frame;pf_worst_frame_ns=pf_since_ns;}
        if(frame>=50000) ++pf_over_50ms;
        if(frame>=100000) ++pf_over_100ms;
        if(pf_prev_avg_us && frame>2*pf_prev_avg_us && frame>=PF_HITCH_MIN_US) {
            ++pf_hitches;
            if(pf_since_ns>=PF_HITCH_COMPILE_NS) ++pf_hitch_compiles;
        }
    }
    pf_last_us=now;pf_since_ns=0;
    if(now-pf_window_us>=PF_REPORT_US) {pf_report(now,line,sizeof(line));pf_start(now);}
    pthread_mutex_unlock(&pf_lock);
    if(line[0]) fputs(line,stderr);
}
static void fg_read_config(void)
{
    /* 04.14 (run-0193): the file was there (rwx, written over FTP, owner 0) and libc's fopen still failed in the
     * jailbroken start, so the mode stayed off; the kernel's own open first, as for C:\\orbis\\winedebug.txt (W271). */
    char word[16]={0};
    int found=0,fd=sceKernelOpen(FG_CONFIG,0 /* O_RDONLY */,0),open_errno=0;
    if(fd>=0) {
        int n=sceKernelRead(fd,word,sizeof(word)-1);
        sceKernelClose(fd);
        found=1;
        word[n>0?n:0]=0;
        for(int i=0;word[i];i++) if(word[i]=='\n'||word[i]=='\r'||word[i]==' ') {word[i]=0;break;}
    } else {
        FILE *file=fopen(FG_CONFIG,"r");
        open_errno=errno;
        if(file) {found=1;if(fscanf(file,"%15s",word)!=1) word[0]=0;fclose(file);}
    }
    /* stage 5: the overlay's GENERAR CUADROS decides per program; the file, when present, overrides it for debugging */
    fg_file_mode=!found?-1:!strcmp(word,"off")?FG_OFF:!strcmp(word,"shadow")?FG_SHADOW:!strcmp(word,"display")?FG_DISPLAY
                :FG_TIMING;
    ft_logging=found;
    fprintf(stderr,"PWFG config mode=%s logging=%d kernel_open=%#x libc_errno=%d\n",
            fg_file_mode<0?"overlay":fg_mode_words[fg_file_mode],ft_logging,(unsigned)fd,open_errno);
}
#ifdef PW_SINK_GPU
/* native/hw_sink_gpu/framegen.inc.c (stage 3): 1 a frame was generated, 0 none (no history yet, another swapchain),
 * -1 failed (the generator turned itself off); keep: MangoHud's rectangle, taken unchanged (stage 5) */
extern int pw_sink_gpu_fg_frame(const void *swapchain,const void *pixels,unsigned pitch,unsigned width,
                                unsigned height,int rgba,const int *keep,int restart);
/* stage 4: the generated and real frames for the image a layer shows (pw_framegen_sched.h FGD_PICK_*) */
extern int pw_sink_gpu_fg_pick(const void *pixels,unsigned width,unsigned height,unsigned wait_us,const void **generated,
                               const void **real,unsigned *gpu_us,unsigned *timed);
#endif
#include "pw_framegen_sched.h"
/* native/hw_overlay.c: GENERAR CUADROS for the program in front (1 on), and MangoHud's rectangle in a width x height
 * image while MangoHud draws on that program (1) */
extern int pw_hw_overlay_framegen(void);
extern int pw_hw_overlay_hud_rect(unsigned width,unsigned height,int *rect);
/* stage 4: the latest present of a capped swapchain, as the hook saw it, for the presenter (fgd_lock) */
static pthread_mutex_t fgd_lock=PTHREAD_MUTEX_INITIALIZER;
static struct {const void *pixels;unsigned width,height;int span;uint64_t seq;} fgd_note;
static struct pw_fgd fgd;                            /* the presenter's decisions (sink lock) */
static uint64_t fgd_seen_seq,fgd_report_us;          /* sink lock */
static unsigned fgd_pairs,fgd_alone;                 /* in the current report */
static volatile int fgd_reset_wanted=1;
static int fg_restart_wanted=1;                      /* presenting threads: a present went by without a copy */
extern unsigned pw_hw_overlay_program_serial(void);  /* native/hw_overlay.c: changes with the program in front */
static unsigned fg_program_serial;
/* sink lock: what show() draws for the followed image: 0 the layers as Wine handed them, 1 its generated frame,
 * 2 its real frame (the generator's copy) */
static int fgd_variant;
/* pw_vk_present_hook: the presenting thread, before its present returns */
static void ft_present(const void *swapchain,const void *pixels,unsigned pitch,unsigned width,unsigned height,int format,
                       uint64_t us)
{
    pthread_mutex_lock(&ft_lock);
    struct ft_source *s=NULL;
    for(unsigned i=0;i<FT_SOURCES && !s;i++) if(ft_sources[i].swapchain==swapchain) s=&ft_sources[i];
    if(!s) {s=&ft_sources[0];for(unsigned i=1;i<FT_SOURCES;i++) if(ft_sources[i].last_us<s->last_us) s=&ft_sources[i];}
    if(s->swapchain!=swapchain || s->width!=width || s->height!=height || s->format!=format) {
        if(ft_logging>0) fprintf(stderr,"PWFG source_new sc=%p %ux%u format=%d (was %p %ux%u)\n",swapchain,width,height,
                                 format,s->swapchain,s->width,s->height);
        memset(s,0,sizeof(*s));
        s->swapchain=swapchain;s->width=width;s->height=height;s->format=format;
    } else if(s->last_us && us>s->last_us) {
        uint64_t interval=us-s->last_us,period=ft_period_us?ft_period_us:FT_NOMINAL_PERIOD_US;
        unsigned b=(unsigned)((interval+period/2)/period);
        s->sum_us+=interval;s->sumsq_us+=interval*interval;++s->n;
        if(!s->min_us || interval<s->min_us) s->min_us=interval;
        if(interval>s->max_us) s->max_us=interval;
        ++s->bucket[b<FT_BUCKETS?b:FT_BUCKETS-1];
    }
    s->last_us=us;++s->presents;__atomic_add_fetch(&ft_present_seq,1,__ATOMIC_RELAXED);
    pthread_mutex_unlock(&ft_lock);
#ifdef PW_SINK_GPU
    /* display: only while FPS LIMIT holds the program at 30 and the scheduler has not given up, so a GPU is not
     * charged for frames nobody will see */
    int mode=fg_mode;
    if(!fg_generator_off && (mode==FG_SHADOW || (mode==FG_DISPLAY && fl_auto.cap==2 && !fgd.gave_up))) {
        int keep[4]={0,0,0,0};
        if(mode==FG_DISPLAY) pw_hw_overlay_hud_rect(width,height,keep);
        /* VK_FORMAT_R8G8B8A8_UNORM 37, _SRGB 43: words R,G,B,A; the B8G8R8A8 ones are B,G,R,A */
        int r=pw_sink_gpu_fg_frame(swapchain,pixels,pitch,width,height,format==37 || format==43,keep,fg_restart_wanted);
        fg_restart_wanted=0;
        if(r>0) __atomic_add_fetch(&ft_generated,1,__ATOMIC_RELAXED);
        else if(r<0) {
            __atomic_add_fetch(&ft_generated_failed,1,__ATOMIC_RELAXED);
            fg_generator_off=1;
            fprintf(stderr,"PWFG generator off for this run: real frames only from now on\n");
        }
    } else fg_restart_wanted=1;
#else
    (void)pixels;(void)pitch;
#endif
}
static unsigned isqrt64(uint64_t v)
{
    uint64_t r=v,next;
    if(v<2) return (unsigned)v;
    for(next=(r+v/r)/2;next<r;next=(r+v/r)/2) r=next;  /* Newton from above */
    return (unsigned)r;
}
static void ft_report(uint64_t now,const struct pw_vblank_status *vb,int vb_ok)
{
    uint64_t vblanks=vb_ok && ft_vb_count0?vb->count-ft_vb_count0:0;
    unsigned period=vblanks?(unsigned)((vb->process_time-ft_vb_us0)/vblanks):0;
    if(period>5000 && period<50000) ft_period_us=period;
    fprintf(stderr,"PWFG timing window_ms=%llu vblanks=%llu period_us=%u flips_submitted=%u flips_done=%u "
            "new_frames_shown=%u repeat_vblanks=%lld flip_latency_us_avg=%u flip_latency_us_max=%u pending_max=%u "
            "status_failed=%u generated=%u generated_failed=%u generated_shown=%u mode=%d\n",
            (unsigned long long)((now-ft_window_us)/1000),(unsigned long long)vblanks,period,ft_submitted,ft_done,
            ft_new_shown,vblanks?(long long)vblanks-(long long)ft_done:-1LL,
            ft_latency_n?(unsigned)(ft_latency_sum_us/ft_latency_n):0,ft_latency_max_us,ft_pending_max,ft_status_failed,
            __atomic_exchange_n(&ft_generated,0,__ATOMIC_RELAXED),__atomic_exchange_n(&ft_generated_failed,0,__ATOMIC_RELAXED),
            __atomic_exchange_n(&ft_generated_shown,0,__ATOMIC_RELAXED),fg_mode);
    pthread_mutex_lock(&ft_lock);
    for(unsigned i=0;i<FT_SOURCES;i++) {
        struct ft_source *s=&ft_sources[i];
        if(!s->swapchain || now-s->last_us>=FT_FRESH_US || !s->n) {memset(s->bucket,0,sizeof(s->bucket));s->n=0;continue;}
        uint64_t mean=s->sum_us/s->n,square=s->sumsq_us/s->n,var=square>mean*mean?square-mean*mean:0;
        fprintf(stderr,"PWFG source sc=%p %ux%u format=%d intervals=%llu rate_x10=%llu interval_us_avg=%llu sd=%u min=%llu "
                "max=%llu vblank_spans=%u,%u,%u,%u,%u,%u\n",s->swapchain,s->width,s->height,s->format,
                (unsigned long long)s->n,(unsigned long long)(mean?10000000ull/mean:0),(unsigned long long)mean,isqrt64(var),
                (unsigned long long)s->min_us,(unsigned long long)s->max_us,s->bucket[0],s->bucket[1],s->bucket[2],
                s->bucket[3],s->bucket[4],s->bucket[5]);
        s->n=s->sum_us=s->sumsq_us=s->min_us=s->max_us=0;memset(s->bucket,0,sizeof(s->bucket));
    }
    pthread_mutex_unlock(&ft_lock);
    ft_submitted=ft_done=ft_new_shown=ft_latency_n=ft_latency_max_us=ft_pending_max=ft_status_failed=0;
    ft_latency_sum_us=0;ft_window_us=now;
    if(vb_ok) {ft_vb_count0=vb->count;ft_vb_us0=vb->process_time;}
}
/* before each flip: what completed since the last one */
static void ft_poll(void)
{
    if(ft_logging<=0) return;
    uint64_t now=sceKernelGetProcessTime();
    OrbisVideoOutFlipStatus status;memset(&status,0,sizeof(status));
    if(!sceVideoOutGetFlipStatus(handle,&status)) {
        uint64_t arg=status.flipArg>0?(uint64_t)status.flipArg:0;
        if(arg>ft_done_arg) {
            for(uint64_t a=arg>ft_done_arg+FT_FLIPS?arg-FT_FLIPS+1:ft_done_arg+1;a<=arg;a++) {
                if(ft_flip[a%FT_FLIPS].arg!=a) continue;
                ++ft_done;
                /* a generated frame is counted apart (generated_shown), and its real frame after it is the new one */
                if(ft_flip[a%FT_FLIPS].generated) continue;
                if(ft_flip[a%FT_FLIPS].seq!=ft_shown_seq) {++ft_new_shown;ft_shown_seq=ft_flip[a%FT_FLIPS].seq;}
            }
            if(ft_flip[arg%FT_FLIPS].arg==arg && status.ptime>=ft_flip[arg%FT_FLIPS].submit_us) {
                unsigned latency=(unsigned)(status.ptime-ft_flip[arg%FT_FLIPS].submit_us);
                ft_latency_sum_us+=latency;++ft_latency_n;if(latency>ft_latency_max_us) ft_latency_max_us=latency;
            }
            ft_done_arg=arg;
        }
        if(status.numFlipPending>0 && (unsigned)status.numFlipPending>ft_pending_max) ft_pending_max=(unsigned)status.numFlipPending;
    } else ++ft_status_failed;
    struct pw_vblank_status vb;memset(&vb,0,sizeof(vb));
    int vb_ok=!vblank_status(&vb);
    if(!ft_window_us) {ft_window_us=now;if(vb_ok) {ft_vb_count0=vb.count;ft_vb_us0=vb.process_time;}return;}
    if(now-ft_window_us>=FT_REPORT_US) ft_report(now,&vb,vb_ok);
}
static void ft_flipped(uint64_t arg)
{
    if(ft_logging<=0) return;
    ft_flip[arg%FT_FLIPS].arg=arg;ft_flip[arg%FT_FLIPS].seq=ft_handed_seq;ft_flip[arg%FT_FLIPS].generated=fgd_variant==1;
    ft_flip[arg%FT_FLIPS].submit_us=sceKernelGetProcessTime();++ft_submitted;
}
/* the sink's hook into the Vulkan runtime; weak: a link without native/wine_vk_runtime.c has none */
extern void (*pw_vk_present_hook)(const void *swapchain,const void *pixels,unsigned pitch,unsigned width,unsigned height,
                                  int format,uint64_t present_us) __attribute__((weak));
/* the hook: frame generation's counters and copy (framegen.txt, or the overlay's GENERAR CUADROS for the program in
 * front), then FPS LIMIT's hold, then the note the display scheduler reads when this frame reaches the presenter */
static void sink_present_hook(const void *swapchain,const void *pixels,unsigned pitch,unsigned width,unsigned height,
                              int format,uint64_t us)
{
    int mode=fg_file_mode>=0?fg_file_mode:pw_hw_overlay_framegen()?FG_DISPLAY:FG_OFF;
    unsigned serial=pw_hw_overlay_program_serial();
    if(mode!=fg_mode) {
        fprintf(stderr,"PWFG mode=%s (%s)\n",fg_mode_words[mode],fg_file_mode>=0?"framegen.txt":"overlay");
        fg_mode=mode;fgd_reset_wanted=1;fg_restart_wanted=1;
    }
    if(serial!=fg_program_serial) {  /* a gave-up is per program, and the old program's frame is no history */
        fg_program_serial=serial;fgd_reset_wanted=1;fg_restart_wanted=1;
    }
    pf_present();
    if(ft_logging>0 || mode>=FG_SHADOW) ft_present(swapchain,pixels,pitch,width,height,format,us);
    int span=fl_present(swapchain);
    if(mode==FG_DISPLAY) {
        pthread_mutex_lock(&fgd_lock);
        fgd_note.pixels=pixels;fgd_note.width=width;fgd_note.height=height;fgd_note.span=span;++fgd_note.seq;
        pthread_mutex_unlock(&fgd_lock);
    }
}
static void ft_start(void)
{
    if(ft_logging>=0) return;
    fg_read_config();
    /* always hooked: FPS LIMIT can be chosen at any time; with framegen.txt absent and the limit off, a present
     * costs one call and two loads */
    if(&pw_vk_present_hook) pw_vk_present_hook=sink_present_hook;
    else fprintf(stderr,"PWFG no present hook in this link\n");
}
#ifdef PW_FG_DISPLAY
/* Stage 4, the display scheduler (docs/FRAME_GENERATION.md). FPS LIMIT lets a capped game's frame N go just after
 * vblank V; it reaches this presenter, which draws the stack with N's image replaced by the frame generated between
 * N-1 and N and flips it (shown at V+1), waits for that flip, draws the stack again with N's own copy and flips it
 * (V+2), and waits for that flip too. N+1 is let go at V+2 and the same follows: one frame per vblank, generated and
 * real in turn, each real frame one vblank later than without generation. The desktop, pointer, overlay and Steam
 * page are drawn on both flips as on any other: only the game's image is ever generated.
 * Every other frame, and every frame pw_framegen_sched.h turns down, is shown as before. */
enum {FGD_WAIT_US=4000,FGD_FLIP_WAIT_US=50000,FGD_FLIP_POLL_US=500,FGD_REPORT_US=10000000};
static const void *fgd_image,*fgd_generated,*fgd_real;  /* sink lock: the followed image and what replaces it */
static unsigned fgd_width,fgd_height;
static struct pw_wine_layer fgd_layers[MAX_LAYERS];
/* sink lock: the stack to draw, with the followed image replaced for fgd_variant; NULL when it is not in the stack */
static const struct pw_wine_layer *fgd_stack(void)
{
    const struct pw_wine_layer *found=NULL;
    memcpy(fgd_layers,layers,layer_count*sizeof(*layers));
    for(unsigned i=0;i<layer_count;i++) {
        struct pw_wine_layer *l=&fgd_layers[i];
        if(!(l->flags&1) || l->pixels!=fgd_image || l->source_width!=fgd_width || l->source_height!=fgd_height) continue;
        l->pixels=fgd_variant==1?fgd_generated:fgd_real;l->stride=fgd_width;found=fgd_layers;
    }
    return found;
}
/* sink lock */
static void fgd_report(uint64_t now)
{
    if(!pw_trace_on()) return;  /* alpha 2: a line every 10 s, traces only */
    if(!fgd_report_us) {fgd_report_us=now;return;}
    if(now-fgd_report_us<FGD_REPORT_US) return;
    char reasons[256];int at=0;
    reasons[0]=0;
    for(int r=1;r<FGD_REASONS;r++)
        if(fgd.counts[r] && at<(int)sizeof(reasons))
            at+=snprintf(reasons+at,sizeof(reasons)-at,"%s%s:%u",at?",":"",pw_fgd_reason_words[r],fgd.counts[r]);
    unsigned gpu_us=0,timed=0;const void *g,*r;
    pw_sink_gpu_fg_pick(NULL,0,0,0,&g,&r,&gpu_us,&timed);   /* only the averages */
    fprintf(stderr,"PWFG display pairs=%u alone=%u reasons=%s gpu_us=%u budget_us=%u timed=%u gave_up=%d\n",fgd_pairs,
            fgd_alone,at?reasons:"-",gpu_us,FGD_BUDGET_US,timed,fgd.gave_up);
    fgd_pairs=fgd_alone=0;
    for(int i=0;i<FGD_REASONS;i++) fgd.counts[i]=0;
    fgd_report_us=now;
}
/* 04.20: what the screen shows of the followed image, a second at a time, for MangoHud's FPS row (native/telemetry.c,
 * struct pw_ps4_telemetry_fg). MangoHud counts the game's own presents, inside its swapchain, so with frame generation
 * it kept showing 30. Counted here, at the presenter: each new real frame of the followed image once (shown alone,
 * or as the second flip of a pair), and each generated frame whose flip VideoOut reported done. Nothing is estimated:
 * a second without a generated frame on screen publishes 0 generated, and MangoHud then shows its own value. */
enum {FGR_WINDOW_US=1000000,FGR_FRESH_US=2500000};
static pthread_mutex_t fgr_lock=PTHREAD_MUTEX_INITIALIZER;
static struct {unsigned width,height,shown_tenths,real_tenths,generated_tenths;uint64_t us;} fgr_published;  /* fgr_lock */
static unsigned fgr_real,fgr_generated,fgr_width,fgr_height;  /* sink lock: in the current second */
static uint64_t fgr_start_us;                                  /* sink lock */
static int fgr_was_shown;                                      /* sink lock: for the log line when it changes */
/* sink lock */
static void fgr_forget(void)
{
    fgr_start_us=0;fgr_real=fgr_generated=0;
    pthread_mutex_lock(&fgr_lock);memset(&fgr_published,0,sizeof(fgr_published));pthread_mutex_unlock(&fgr_lock);
}
/* sink lock: a new real frame of the followed image (fgd_begin) */
static void fgr_tick(uint64_t now,unsigned width,unsigned height)
{
    if(!fgr_start_us || width!=fgr_width || height!=fgr_height) {
        fgr_start_us=now;fgr_real=fgr_generated=0;fgr_width=width;fgr_height=height;
    }
    ++fgr_real;
    if(now-fgr_start_us<FGR_WINDOW_US) return;
    uint64_t span=now-fgr_start_us;
    /* the frame that ends the second starts the next one */
    unsigned real=(unsigned)(((uint64_t)(fgr_real-1)*10000000+span/2)/span);
    unsigned generated=(unsigned)(((uint64_t)fgr_generated*10000000+span/2)/span);
    pthread_mutex_lock(&fgr_lock);
    fgr_published.width=width;fgr_published.height=height;fgr_published.real_tenths=real;
    fgr_published.generated_tenths=generated;fgr_published.shown_tenths=real+generated;fgr_published.us=now;
    pthread_mutex_unlock(&fgr_lock);
    int shown=generated>0;
    if(shown!=fgr_was_shown)
        if(pw_trace_on()) fprintf(stderr,"PWFG shown_rate %s %ux%u shown_x10=%u real_x10=%u generated_x10=%u window_us=%llu\n",
                shown?"on":"off",width,height,real+generated,real,generated,(unsigned long long)span);
    fgr_was_shown=shown;
    fgr_start_us=now;fgr_real=1;fgr_generated=0;
}
/* native/telemetry.c (MangoHud's FPS row): 1 while a second measured in the last FGR_FRESH_US had generated frames on
 * screen, with that second's frames a second (tenths) of the followed image, all, real and generated */
int pw_hw_sink_fg_rate(unsigned *width,unsigned *height,unsigned *shown_tenths,unsigned *real_tenths,
                       unsigned *generated_tenths,uint64_t *sample_us);
int pw_hw_sink_fg_rate(unsigned *width,unsigned *height,unsigned *shown_tenths,unsigned *real_tenths,
                       unsigned *generated_tenths,uint64_t *sample_us)
{
    uint64_t now=sceKernelGetProcessTime();
    pthread_mutex_lock(&fgr_lock);
    int fresh=fgr_published.us && now-fgr_published.us<FGR_FRESH_US && fgr_published.generated_tenths>0;
    if(fresh) {
        *width=fgr_published.width;*height=fgr_published.height;*shown_tenths=fgr_published.shown_tenths;
        *real_tenths=fgr_published.real_tenths;*generated_tenths=fgr_published.generated_tenths;*sample_us=fgr_published.us;
    }
    pthread_mutex_unlock(&fgr_lock);
    return fresh;
}
/* sink lock, before show(): 1 when the frame to show is a new frame of the followed image that shows as a pair,
 * fgd_variant then 1 for the generated frame */
static int fgd_begin(void)
{
    if(fgd_reset_wanted) {
        fgd_reset_wanted=0;pw_fgd_reset(&fgd);fgd_pairs=fgd_alone=0;fgd_report_us=0;
        pthread_mutex_lock(&fgd_lock);fgd_seen_seq=fgd_note.seq;pthread_mutex_unlock(&fgd_lock);
        fgr_forget();
    }
    if(fg_mode!=FG_DISPLAY || !layered || !gpu || layers_stale) return 0;
    pthread_mutex_lock(&fgd_lock);
    const void *pixels=fgd_note.pixels;unsigned width=fgd_note.width,height=fgd_note.height;int span=fgd_note.span;
    uint64_t seq=fgd_note.seq;
    pthread_mutex_unlock(&fgd_lock);
    if(seq==fgd_seen_seq) return 0;          /* the pointer moved, the desktop changed: no new game frame */
    int in_stack=0;
    for(unsigned i=0;i<layer_count && !in_stack;i++) in_stack=(layers[i].flags&1) && layers[i].pixels==pixels;
    if(!in_stack) return 0;                  /* the frame has not reached the stack yet: its turn comes */
    fgd_seen_seq=seq;
    struct pw_fgd_in in={.cap=fl_auto.cap,.vblank_trusted=fl_vblank_trusted,.span=span};
    const void *generated=NULL,*real=NULL;
    in.pick=fg_generator_off?FGD_PICK_OFF:pw_sink_gpu_fg_pick(pixels,width,height,FGD_WAIT_US,&generated,&real,&in.gpu_us,
                                                               &in.timed);
    int was_showing=fgd.showing,was_given_up=fgd.gave_up;
    int r=pw_fgd_decide(&fgd,&in);
    if(r==FGD_PAIR) ++fgd_pairs;else ++fgd_alone;
    if(fgd.showing!=was_showing || fgd.gave_up!=was_given_up)
        if(pw_trace_on()) fprintf(stderr,"PWFG display %s reason=%s cap=%d vblank_trusted=%d span=%d gpu_us=%u timed=%u%s\n",
                fgd.showing?"on":"off",pw_fgd_reason_words[r],in.cap,in.vblank_trusted,span,in.gpu_us,in.timed,
                fgd.gave_up && !was_given_up?": gave up for this program, generation stops":"");
    uint64_t now=sceKernelGetProcessTime();
    fgr_tick(now,width,height);
    fgd_report(now);
    if(r!=FGD_PAIR) return 0;
    fgd_image=pixels;fgd_width=width;fgd_height=height;fgd_generated=generated;fgd_real=real;fgd_variant=1;
    return 1;
}
/* no lock: 1 once VideoOut reports flip arg done, 0 after FGD_FLIP_WAIT_US or when the status cannot be read */
static int fgd_wait_flip(uint64_t arg)
{
    uint64_t start=sceKernelGetProcessTime();
    for(;;) {
        OrbisVideoOutFlipStatus status;memset(&status,0,sizeof(status));
        if(sceVideoOutGetFlipStatus(handle,&status)) return 0;
        if(status.flipArg>=0 && (uint64_t)status.flipArg>=arg) return 1;
        if(sceKernelGetProcessTime()-start>=FGD_FLIP_WAIT_US) return 0;
        sceKernelUsleep(FGD_FLIP_POLL_US);
    }
}
#endif
extern void pw_hw_overlay_draw(uint32_t *pixels,unsigned pitch,unsigned width,unsigned height);
/* the Steam client inside the title (native/steam/steam_ui.c): its page over the whole frame while open */
extern int pw_hw_steam_draw(uint32_t *pixels,unsigned pitch,unsigned width,unsigned height);
/* PoP Phase C (native/pop_loader_spawn.h): a separate process's window pixels, at its desktop rectangle */
extern int pw_hw_separate_draw(uint32_t *target,unsigned pitch,unsigned out_w,unsigned out_h,unsigned left,unsigned top,
                               unsigned scale_w,unsigned scale_h,unsigned desk_w,unsigned desk_h);
#endif
static int show(void)
{
    if(handle<0 || (!last.bgra && !layered)) return -1;
#ifdef PW_SINK_EXTERNAL_INPUT
    ft_start();
#endif
    const uint8_t *bgra=last.bgra;uint32_t width=last.width,height=last.height,stride=last.stride;
#ifdef PW_SINK_GPU
    if(layered && layers_stale) return 0;
    if(layered) {width=layer_width;height=layer_height;}
#endif
    ++flips;
    uint32_t *target=buffers[flips%OUT_BUFFERS];
    /* Nearest scaling that keeps the aspect, centred. */
    uint32_t scale_w=OUT_WIDTH,scale_h=(uint32_t)((uint64_t)height*OUT_WIDTH/width);
    if(scale_h>OUT_HEIGHT) {scale_h=OUT_HEIGHT;scale_w=(uint32_t)((uint64_t)width*OUT_HEIGHT/height);}
#ifdef PW_SINK_EXTERNAL_INPUT
    /* W266: the overlay's ESTIRAR for the program in front: the whole output, each axis on its own; the pointer
     * is drawn with the same scale (draw_cursor, cursor_origin) */
    if(pw_hw_overlay_stretch()) {scale_w=OUT_WIDTH;scale_h=OUT_HEIGHT;}
#endif
    uint32_t left=(OUT_WIDTH-scale_w)/2,top=(OUT_HEIGHT-scale_h)/2;
    uint64_t start=sceKernelGetProcessTime();
#ifdef PW_SINK_GPU
    if(gpu && (layered || (bgra==gpu_screen && width==gpu_width && height==gpu_height))) {
        int ox=-1000,oy=-1000;
#ifdef PW_SINK_EXTERNAL_INPUT
        cursor_origin(left,top,scale_w,scale_h,&ox,&oy);
#endif
        unsigned buffer=(unsigned)(flips%OUT_BUFFERS);
        const struct pw_wine_layer *stack=layers;
#ifdef PW_FG_DISPLAY
        /* stage 4: the followed image as its generated frame or its own copy; gone from the stack, as handed */
        if(fgd_variant && layered && !(stack=fgd_stack())) {stack=layers;fgd_variant=0;}
#endif
        if(!(layered?pw_sink_gpu_draw_layers(buffer,stack,layer_count,width,height,(int)left,(int)top,(int)scale_w,
                                             (int)scale_h,ox,oy)
                    :pw_sink_gpu_draw(buffer,stride,(int)left,(int)top,(int)scale_w,(int)scale_h,ox,oy))) {
            show_stats(layered?"layers":"gpu",start);
            if(dump_wanted) dump_output(target);
            goto flip;
        }
        fprintf(stderr,"PWSINK gpu_draw_failed: CPU copy from now on\n");
        gpu=0;
        /* layers have no desktop buffer to copy: ps5drv composes one at its next present */
        if(layered) return -1;
    }
#endif
    if(scale_w==width && scale_h==height && scale_w==OUT_WIDTH && scale_h==OUT_HEIGHT) {
        /* a desktop of the output size: a straight copy, no clear, no per-pixel division */
        for(uint32_t y=0;y<height;++y) {
            const uint32_t *row=(const uint32_t *)(bgra+(size_t)y*stride);
            uint32_t *out=target+(size_t)y*pitch;
            for(uint32_t x=0;x<width;++x) out[x]=row[x]|0xff000000u;
        }
    } else {
        memset(target,0,(size_t)pitch*OUT_HEIGHT*4);
        for(uint32_t y=0;y<scale_h;++y) {
            const uint32_t *row=(const uint32_t *)(bgra+(size_t)(y*height/scale_h)*stride);
            uint32_t *out=target+(size_t)(top+y)*pitch+left;
            for(uint32_t x=0;x<scale_w;++x) out[x]=row[x*width/scale_w]|0xff000000u;
        }
    }
#ifdef PW_SINK_EXTERNAL_INPUT
    draw_cursor(target,left,top,scale_w,scale_h);
#endif
    show_stats("cpu",start);
#ifdef PW_SINK_GPU
flip:;
#endif
#ifdef PW_SINK_EXTERNAL_INPUT
    if(pw_hw_separate_draw(target,pitch,OUT_WIDTH,OUT_HEIGHT,left,top,scale_w,scale_h,width,height))
        draw_cursor(target,left,top,scale_w,scale_h);  /* the pointer stays over the separate window */
    draw_busy(target,left,top,scale_w,scale_h);  /* W293 */
    draw_fps(target,sceKernelGetProcessTime());
    pw_hw_steam_draw(target,pitch,OUT_WIDTH,OUT_HEIGHT);
    pw_hw_overlay_draw(target,pitch,OUT_WIDTH,OUT_HEIGHT);  /* W236 */
#endif
#ifdef PW_SINK_EXTERNAL_INPUT
    ft_poll();  /* stage 1 */
#endif
    int rc=sceVideoOutSubmitFlip(handle,(int32_t)(flips%OUT_BUFFERS),FLIP_VSYNC,(int64_t)flips);
    if(rc) fprintf(stderr,"PWBOOT video_out_flip_failed rc=%x\n",rc);
#ifdef PW_SINK_EXTERNAL_INPUT
    else ft_flipped(flips);
#endif
    return rc;
}
#ifdef PW_SINK_ASYNC
/* Hardware (W043): the Wine thread only marks the frame pending; this thread shows it,
 * at most about once per refresh, so a burst of small flushes costs one copy and one
 * flip instead of one each. The desktop buffer is read while Wine may write it; a torn
 * read is replaced by the next pending frame. */
static pthread_cond_t wake=PTHREAD_COND_INITIALIZER;
static int pending,presenter_started;
static void *presenter(void *unused)
{
    (void)unused;
    for(;;) {
        pthread_mutex_lock(&lock);
        while(!pending) pthread_cond_wait(&wake,&lock);
        pending=0;
#ifdef PW_FG_DISPLAY
        /* stage 4: a pair, the generated frame now and the real one on the next vblank (fgd_begin) */
        int pair=fgd_begin();
        int rc=show();
        if(pair && !rc && fgd_variant==1) {
            uint64_t generated_flip=flips,real_flip=0;
            fgd_variant=0;
            __atomic_add_fetch(&ft_generated_shown,1,__ATOMIC_RELAXED);
            pthread_mutex_unlock(&lock);
            int shown=fgd_wait_flip(generated_flip);
            pthread_mutex_lock(&lock);
            if(shown) ++fgr_generated;   /* 04.20: on screen, for MangoHud's FPS row */
            if(shown && layered && !layers_stale) {
                fgd_variant=2;
                if(!show()) real_flip=flips;
                fgd_variant=0;
            }
            if(!real_flip) pending=1;    /* the real frame must not stay behind the generated one: show as handed */
            pthread_mutex_unlock(&lock);
            /* the next draw goes to the other buffer: it must be off screen, so this flip has to be done first */
            if(real_flip) fgd_wait_flip(real_flip);
            continue;
        }
        fgd_variant=0;
#else
        show();
#endif
        pthread_mutex_unlock(&lock);
        usleep(16000);
    }
    return NULL;
}
/* lock held */
static void request_show(void)
{
    if(!presenter_started) {
        pthread_t thread;
        presenter_started=1;
        if(pthread_create(&thread,NULL,presenter,NULL)) {presenter_started=0;show();return;}
        fprintf(stderr,"PWBOOT presenter_thread started\n");
    }
    pending=1;pthread_cond_signal(&wake);
}
#endif
int pw_wine_present(const void *pixels,unsigned int width,unsigned int height,unsigned int stride)
{
    const uint8_t *bgra=pixels;
    if(!bgra || !width || !height || stride<width*4) return -1;
    pthread_mutex_lock(&lock);
    ++frames;
    /* hashing reads every byte: only for frames that are logged or may be dumped */
    int logged=frames<=8 || (!(frames%64) && pw_trace_on());
    uint64_t hash=logged || dumps<DUMP_LIMIT?frame_hash(bgra,width,height,stride):0;
    if(logged) {
#if PW_SINK_TIMING
        fprintf(stderr,"PWBOOT frame_presented n=%llu size=%ux%u hash=%016llx t_ms=%llu\n",(unsigned long long)frames,
                width,height,(unsigned long long)hash,(unsigned long long)(sceKernelGetProcessTime()/1000));
#else
        fprintf(stderr,"PWBOOT frame_presented n=%llu size=%ux%u hash=%016llx\n",(unsigned long long)frames,
                width,height,(unsigned long long)hash);
#endif
    }
    if(dumps<DUMP_LIMIT && hash!=last_dump_hash) {dump(bgra,width,height,stride);++dumps;last_dump_hash=hash;}
    if(handle<0 && !failed && open_video()) failed=1;
#ifdef PW_SINK_EXTERNAL_INPUT
    frame_handed();  /* W236 */
    ft_handed_seq=__atomic_load_n(&ft_present_seq,__ATOMIC_RELAXED);  /* stage 1 */
#endif
    last.bgra=bgra;last.width=width;last.height=height;last.stride=stride;layered=0;
#ifdef PW_SINK_ASYNC
    int rc=handle<0?-1:0;
    if(!rc) request_show();
#else
    int rc=show();
#endif
    pthread_mutex_unlock(&lock);
    return rc?-1:0;
}
/* W144: ps5drv's windows stacked by the GPU. pw_wine_layers says whether the GPU draws;
 * window contents come from pw_wine_layer_alloc; pw_wine_present_layers shows a stack of them,
 * bottom first. Each fails when the GPU does not draw, and ps5drv composes on the CPU again. */
int pw_wine_layers(void)
{
#ifdef PW_SINK_GPU
    pthread_mutex_lock(&lock);
    int on=gpu;
    pthread_mutex_unlock(&lock);
    return on;
#else
    return 0;
#endif
}
/* W155: the screen shows only the desktop's width x height corner (ps5drv.c present_screen):
 * the pointer stays inside it. 1 when the pointer is the hardware launcher's (native/hw_pad.c). */
#ifdef PW_SINK_EXTERNAL_INPUT
extern void pw_hw_pointer_area(int width,int height);
#endif
/* W256: ps5drv.c hides the pointer in a full-screen game that sets no cursor (W261: none at all); the frame is
 * shown again */
/* W293: ps5drv.c, a top-level window shown for the first time: it ends the "app starting" pointer */
void pw_wine_window_shown(void *hwnd,const char *class_name);
void pw_wine_window_shown(void *hwnd,const char *class_name)
{
#ifdef PW_SINK_EXTERNAL_INPUT
    extern void pw_hw_overlay_window_shown(void *hwnd,const char *class_name);
    pw_hw_overlay_window_shown(hwnd,class_name);
#else
    (void)hwnd;(void)class_name;
#endif
}
void pw_wine_pointer_hidden(int hidden);
#ifdef PW_SINK_EXTERNAL_INPUT
void pw_hw_cursor_moved(void);
#endif
void pw_wine_pointer_hidden(int hidden)
{
#ifdef PW_SINK_EXTERNAL_INPUT
    if(pointer_hidden==!!hidden) return;
    pointer_hidden=!!hidden;
    pw_hw_cursor_moved();
#else
    (void)hidden;
#endif
}
int pw_wine_pointer_area(unsigned int width,unsigned int height)
{
#ifdef PW_SINK_EXTERNAL_INPUT
    pw_hw_pointer_area((int)width,(int)height);
    return 1;
#else
    (void)width;(void)height;return 0;
#endif
}
/* W152: whether a layer may be an image outside the pool (a Vulkan program's frame) */
int pw_wine_layer_images(void)
{
#ifdef PW_SINK_GPU
    pthread_mutex_lock(&lock);
    int on=gpu && pw_sink_gpu_images();
    pthread_mutex_unlock(&lock);
    return on;
#else
    return 0;
#endif
}
void *pw_wine_layer_alloc(size_t bytes)
{
#ifdef PW_SINK_GPU
    pthread_mutex_lock(&lock);
    void *pixels=gpu?pw_sink_gpu_alloc(bytes):NULL;
    pthread_mutex_unlock(&lock);
    return pixels;
#else
    (void)bytes;return NULL;
#endif
}
/* 1 when pixels came from pw_wine_layer_alloc (now free), 0 when they are ps5drv's own */
int pw_wine_layer_free(void *pixels)
{
#ifdef PW_SINK_GPU
    pthread_mutex_lock(&lock);
    /* the last frame is shown again when the pointer moves: it must not read freed memory.
     * W145: it is not drawn until ps5drv presents the new stack, which follows the free;
     * dropping the layer showed a frame without the window (a flicker on every resize). */
    for(unsigned i=0;i<layer_count;++i) if(layers[i].pixels==pixels) layers_stale=1;
    int owned=pw_sink_gpu_free(pixels);
    pthread_mutex_unlock(&lock);
    return owned;
#else
    (void)pixels;return 0;
#endif
}
int pw_wine_present_layers(const struct pw_wine_layer *stack,unsigned int count,unsigned int width,unsigned int height)
{
#ifdef PW_SINK_GPU
    if(!width || !height || count>MAX_LAYERS) return -1;
    pthread_mutex_lock(&lock);
    if(!gpu || handle<0) {pthread_mutex_unlock(&lock);return -1;}
    ++frames;
    /* the output buffer is dumped only for logged frames (a BMP write costs ~100 ms) */
    if(frames<=8 || (!(frames%64) && pw_trace_on())) {
        if(dumps<DUMP_LIMIT) dump_wanted=1;
#if PW_SINK_TIMING
        fprintf(stderr,"PWBOOT frame_presented n=%llu size=%ux%u layers=%u t_ms=%llu\n",(unsigned long long)frames,
                width,height,count,(unsigned long long)(sceKernelGetProcessTime()/1000));
#else
        fprintf(stderr,"PWBOOT frame_presented n=%llu size=%ux%u layers=%u\n",(unsigned long long)frames,width,height,count);
#endif
    }
    memcpy(layers,stack,count*sizeof(*layers));
#ifdef PW_SINK_EXTERNAL_INPUT
    frame_handed();  /* W236 */
    ft_handed_seq=__atomic_load_n(&ft_present_seq,__ATOMIC_RELAXED);  /* stage 1 */
#endif
    layer_count=count;layer_width=width;layer_height=height;layered=1;layers_stale=0;
#ifdef PW_SINK_ASYNC
    request_show();
    int rc=0;
#else
    int rc=show();
#endif
    pthread_mutex_unlock(&lock);
    return rc?-1:0;
#else
    (void)stack;(void)count;(void)width;(void)height;return -1;
#endif
}
#ifdef PW_SINK_EXTERNAL_INPUT
/* The hardware launcher's pad thread moved the pointer: show the last frame again. */
#ifdef PW_SINK_EXTERNAL_INPUT
/* W165: F12 (native/hw_pad.c) shows or hides the frame counter. W166: only in a 32-bit title
 * (WINE_PS5_FIT, native/wine_hardware.c), which runs without MangoHud, and while it presents
 * through Vulkan. On the desktop MangoHud's own F12 toggle must keep the key, so it is not taken
 * (0) and goes to the programs like any other. */
int pw_hw_fps_toggle(void);
int pw_hw_fps_toggle(void)
{
    static int title=-1;
    if(title<0) title=getenv("WINE_PS5_FIT")!=NULL;
    if(!title) return 0;
    pthread_mutex_lock(&lock);
    uint64_t now=sceKernelGetProcessTime();
    if(!vk_fps_us || now-vk_fps_us>=2000000) {pthread_mutex_unlock(&lock);return 0;}
    fps_overlay=!fps_overlay;
    fprintf(stderr,"PWSINK fps_overlay=%d\n",fps_overlay);
#ifdef PW_SINK_ASYNC
    if((last.bgra || layered) && handle>=0) request_show();
#else
    if(last.bgra || layered) show();
#endif
    pthread_mutex_unlock(&lock);
    return 1;
}
/* W165: a Vulkan program's presents per second (native/wine_vk_runtime.c), once a second; the
 * counter is redrawn with it even when nothing else on screen changes */
void pw_wine_vk_fps(unsigned tenths);
void pw_wine_vk_fps(unsigned tenths)
{
    pthread_mutex_lock(&lock);
    vk_fps_tenths=tenths;vk_fps_us=sceKernelGetProcessTime();
#ifdef PW_SINK_ASYNC
    if(fps_overlay && (last.bgra || layered) && handle>=0) request_show();
#endif
    pthread_mutex_unlock(&lock);
}
#endif
void pw_hw_cursor_moved(void)
{
    pthread_mutex_lock(&lock);
#ifdef PW_SINK_ASYNC
    if((last.bgra || layered) && handle>=0) request_show();
#else
    if(last.bgra || layered) show();
#endif
    pthread_mutex_unlock(&lock);
}
#else
struct PwWineInput;
int pw_wine_next_input(struct PwWineInput *event) {(void)event;return 0;}
int pw_wine_input_fd(void) {return -1;}
#endif
