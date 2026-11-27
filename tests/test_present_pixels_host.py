#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Actual converter and prepared driver entry points with host boundary models."""
import pathlib,subprocess,tempfile
r=pathlib.Path(__file__).resolve().parents[1]
driver=(r/'.deps/wine/ps4-win32u-overlay/dlls/win32u/ps5drv.c').read_text()
def function(text,start):
 at=text.index(start);brace=text.index('{',at);depth=0
 for i in range(brace,len(text)):
  if text[i]=='{':depth+=1
  elif text[i]=='}':
   depth-=1
   if not depth:return text[at:i+1]
 raise AssertionError(start)
frame=function(driver,'BOOL ps5_vulkan_frame(')
forget=function(driver,'void ps5_vulkan_forget(')
assert 'pw_present_layer(' in frame and 'pw_present_storage_clear' in forget
code=r"""
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include "pw_present_pixels.h"
typedef int BOOL;typedef unsigned UINT;typedef uint64_t UINT64;typedef void *HWND;
typedef struct {int left,top,right,bottom;} RECT;
#define FALSE 0
#define TRUE 1
#define GA_ROOT 2
#define PS5_LAYER_RGBA 2
struct ps5_window { HWND hwnd;const uint32_t *vk_pixels;unsigned vk_stride,vk_width,vk_height,vk_flags;
 RECT client,vk_rect,visible;BOOL vk_child;UINT64 vk_swapchain;struct pw_present_storage vk_converted;int vk_source_format; };
static struct ps5_window windows[3];static unsigned window_count=2,pw_stack_log;
static int locked,gpu_images=1,allocations,frees,fail_alloc,presents,root_calls;
static unsigned normalized_calls;
void pw_wine_framegen_normalized(const void *swapchain,const void *source,const void *bgra,unsigned width,unsigned height){
 assert(locked && bgra && source!=bgra && width && height && swapchain);++normalized_calls;
}
static void *pw_wine_layer_alloc(size_t bytes){assert(locked);if(fail_alloc)return NULL;allocations++;return malloc(bytes);}
static void pw_present_release(void *p){if(p){assert(locked);frees++;free(p);}}
static void screen_lock_enter(void){assert(!locked);locked=1;}
static void screen_lock_leave(void){assert(locked);locked=0;}
static HWND NtUserGetAncestor(HWND h,int kind){assert(!locked);root_calls++;return windows[0].hwnd;}
static struct ps5_window *find_window(HWND h){assert(locked);for(unsigned i=0;i<window_count;i++)if(windows[i].hwnd==h)return &windows[i];return NULL;}
static int IsRectEmpty(const RECT *r){return r->left>=r->right||r->top>=r->bottom;}
static RECT fit_image(const RECT *r,unsigned w,unsigned h){return *r;}
static int pw_trace_enabled(void){return 0;}
static void present_screen(void){
 assert(locked&&gpu_images);presents++;
 for(unsigned i=0;i<window_count;i++)if(windows[i].vk_pixels){
  assert(windows[i].vk_stride>=windows[i].vk_width);
  assert(windows[i].vk_width&&windows[i].vk_height);
 }
}
""" + frame + '\n' + forget + r"""
int main(void){
 /* VkFormat-specific primary colour vectors: no reliance on the implementation's shifts. */
 const struct {int format;uint16_t red,green,blue,white,black;} vectors[]={
 {2,0xf00f,0x0f0f,0x00ff,0xffff,0x000f},{3,0x00ff,0x0f0f,0xf00f,0xffff,0x000f},
 {4,0xf800,0x07e0,0x001f,0xffff,0x0000},{5,0x001f,0x07e0,0xf800,0xffff,0x0000},
 {6,0xf801,0x07c1,0x003f,0xffff,0x0001},{7,0x003f,0x07c1,0xf801,0xffff,0x0001},
 {8,0xfc00,0x83e0,0x801f,0xffff,0x8000},
 {1000340000,0xff00,0xf0f0,0xf00f,0xffff,0xf000},
 {1000340001,0xf00f,0xf0f0,0xff00,0xffff,0xf000}};
 uint32_t want[]={0xffff0000,0xff00ff00,0xff0000ff,0xffffffff,0xff000000},dst[10];
 for(unsigned n=0;n<sizeof(vectors)/sizeof(*vectors);n++){
  unsigned char raw[29];memset(raw,0xa5,sizeof(raw));
  uint16_t row[]={vectors[n].red,vectors[n].green,vectors[n].blue,vectors[n].white,vectors[n].black};
  memcpy(raw+1,row,10);memcpy(raw+15,row,10);
  assert(pw_present_to_bgra(dst,raw+1,14,5,2,vectors[n].format));
  for(unsigned i=0;i<10;i++)assert(dst[i]==want[i%5]);
 }
 assert(pw_present_unpack16(0x8123,1000340000)==0x88112233);
 assert(pw_present_unpack16(0x8123,1000340001)==0x88332211);
 unsigned char rgba[12]={0xff,0,0,0x7f,0,0xff,0,0x80,0,0,0xff,0xff};
 assert(pw_present_to_bgra(dst,rgba,12,3,1,37));
 assert(dst[0]==0x7fff0000&&dst[1]==0x8000ff00&&dst[2]==0xff0000ff);
 assert(pw_present_to_bgra(dst,dst,12,3,1,44)&&dst[0]==0x7fff0000);
 assert(!pw_present_layout(1000340000,0,640,480));
 assert(!pw_present_layout(1000340000,1279,640,480));
 assert(pw_present_layout(1000340000,2560,1280,720));
 assert(!pw_present_layout(44,2560,1280,720));
 assert(!pw_present_layout(99999,4096,640,480));
 assert(!pw_present_layout(44,UINT_MAX,UINT_MAX,UINT_MAX));
 assert(!pw_present_layout(44,4,1,0));
 /* Production driver: retained BGRA storage, no global GPU fallback, reallocation and close/reopen. */
 windows[0].hwnd=(HWND)1;windows[1].hwnd=(HWND)2;
 windows[0].client=(RECT){0,0,1280,720};windows[1].client=windows[0].client;
 uint16_t source[6]={0xff00,0xf0f0,0xf00f,0xffff,0xf000,0xf000};
 RECT client={0,0,1280,720};
 assert(ps5_vulkan_frame((HWND)1,10,source,6,3,2,1000340000,&client));
 const uint32_t *owned=windows[0].vk_pixels;
 assert(owned!=(void *)source&&owned==windows[0].vk_converted.pixels);
 assert(owned[0]==0xffff0000&&owned[1]==0xff00ff00&&owned[2]==0xff0000ff);
 assert(windows[0].vk_stride==3&&allocations==1&&!frees&&gpu_images&&!locked);
 source[0]=0xf00f;assert(owned[0]==0xffff0000); /* caller storage can change independently */
 assert(ps5_vulkan_frame((HWND)1,10,source,6,3,2,1000340000,&client));
 assert(windows[0].vk_pixels==owned&&owned[0]==0xff0000ff&&allocations==1);
 int before=presents;
 assert(!ps5_vulkan_frame((HWND)1,11,source,6,3,2,99999,&client));
 assert(!ps5_vulkan_frame((HWND)1,11,source,5,3,2,1000340000,&client));
 assert(gpu_images&&presents==before&&windows[0].vk_pixels==owned&&!locked);
 uint16_t *large=malloc(1280*720*2);
 for(unsigned i=0;i<1280*720;i++)large[i]=0xf0f0;
 fail_alloc=1;
 assert(!ps5_vulkan_frame((HWND)1,12,large,2560,1280,720,1000340000,&client));
 assert(gpu_images&&!windows[0].vk_pixels&&windows[0].vk_converted.pixels==owned&&!locked);
 fail_alloc=0;
 assert(ps5_vulkan_frame((HWND)1,12,large,2560,1280,720,1000340000,&client));
 assert(windows[0].vk_stride==1280&&windows[0].vk_pixels[1280*720-1]==0xff00ff00);
 assert(allocations==2&&frees==1);
 free(large); /* retained layer must not alias caller memory */
 assert(windows[0].vk_pixels[0]==0xff00ff00);
 ps5_vulkan_forget((HWND)1,11);assert(windows[0].vk_pixels); /* stale swapchain cannot clear a newer one */
 ps5_vulkan_forget((HWND)1,12);assert(!windows[0].vk_pixels&&!windows[0].vk_converted.pixels&&frees==2);
 assert(ps5_vulkan_frame((HWND)2,20,source,6,3,2,1000340000,&client));
 ps5_vulkan_forget((HWND)3,20);assert(!windows[1].vk_pixels&&root_calls==1&&frees==3);
 uint32_t rgb32[]={0xff123456,0xffabcdef};
 assert(ps5_vulkan_frame((HWND)1,30,rgb32,8,2,1,44,&client));
 assert(windows[0].vk_pixels==rgb32&&!windows[0].vk_converted.pixels&&allocations==3);
 ps5_vulkan_forget((HWND)1,30);
 for(int cycle=0;cycle<32;cycle++){
  assert(ps5_vulkan_frame((HWND)1,100+cycle,source,6,3,2,1000340000,&client));
  ps5_vulkan_forget((HWND)1,100+cycle);
 }
 assert(allocations==frees&&gpu_images&&!locked);
 assert(normalized_calls>0);
 puts("PASS: packed colour bars, alpha, padded/unaligned rows, format/stride rejection, retained GPU storage, resize, allocation failure, stale swapchains, child lookup, 32-bit zero-copy and repeated close/reopen.");
}
"""
with tempfile.TemporaryDirectory() as tmp:
 p=pathlib.Path(tmp);(p/'check.c').write_text(code)
 subprocess.run(['cc','-std=gnu11','-O1','-g','-fsanitize=address,undefined','-no-pie','-I'+str(r/'platform/ps4'),str(p/'check.c'),'-o',str(p/'check')],check=True)
 subprocess.run([str(p/'check')],check=True)
vulkan=(r/'.deps/wine/ps4-win32u-overlay/dlls/win32u/vulkan.c').read_text()
show=function(vulkan,'static void pw_vk_show_frame(')
assert show.index('pw_present_layout(')<show.index('ps5_vulkan_frame(')
assert 'pw_present_to_bgra(converted,pixels,pitch,width,height,format)' in show
assert 'pitch = width * 4;' in show and show.index('NtGdiStretchDIBitsInternal')<show.rindex('free( converted )')
# Ownership is explicitly released by both window teardown paths as well as swapchain teardown.
assert 'pw_present_storage_clear(&window->vk_converted,pw_present_release);\n        free_pixels( window->pixels );' in driver
assert 'pw_present_storage_clear(&windows[i].vk_converted,pw_present_release);\n        free_pixels( windows[i].pixels );' in driver
print('PASS: prepared Vulkan/GDI path validates before publication; window destroy and purge release owned buffers.')
