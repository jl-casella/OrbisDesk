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
enum {OUT_WIDTH=1280,OUT_HEIGHT=720,OUT_BUFFERS=2,MAX_DUMPS=PW_SINK_MAX_DUMPS};
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
#endif
/* time spent in show() per output frame, by path, logged every 300 frames */
static void show_stats(const char *path,uint64_t start)
{
    static uint64_t total,worst,count;
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
    if(dumps<MAX_DUMPS && hash!=last_dump_hash) {
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
extern void pw_hw_overlay_draw(uint32_t *pixels,unsigned pitch,unsigned width,unsigned height);
#endif
static int show(void)
{
    if(handle<0 || (!last.bgra && !layered)) return -1;
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
        if(!(layered?pw_sink_gpu_draw_layers(buffer,layers,layer_count,width,height,(int)left,(int)top,(int)scale_w,
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
    draw_fps(target,sceKernelGetProcessTime());
    pw_hw_overlay_draw(target,pitch,OUT_WIDTH,OUT_HEIGHT);  /* W236 */
#endif
    int rc=sceVideoOutSubmitFlip(handle,(int32_t)(flips%OUT_BUFFERS),FLIP_VSYNC,(int64_t)flips);
    if(rc) fprintf(stderr,"PWBOOT video_out_flip_failed rc=%x\n",rc);
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
        show();
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
    int logged=frames<=8 || !(frames%64);
    uint64_t hash=logged || dumps<MAX_DUMPS?frame_hash(bgra,width,height,stride):0;
    if(logged) {
#if PW_SINK_TIMING
        fprintf(stderr,"PWBOOT frame_presented n=%llu size=%ux%u hash=%016llx t_ms=%llu\n",(unsigned long long)frames,
                width,height,(unsigned long long)hash,(unsigned long long)(sceKernelGetProcessTime()/1000));
#else
        fprintf(stderr,"PWBOOT frame_presented n=%llu size=%ux%u hash=%016llx\n",(unsigned long long)frames,
                width,height,(unsigned long long)hash);
#endif
    }
    if(dumps<MAX_DUMPS && hash!=last_dump_hash) {dump(bgra,width,height,stride);++dumps;last_dump_hash=hash;}
    if(handle<0 && !failed && open_video()) failed=1;
#ifdef PW_SINK_EXTERNAL_INPUT
    frame_handed();  /* W236 */
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
    if(frames<=8 || !(frames%64)) {
        if(dumps<MAX_DUMPS) dump_wanted=1;
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
