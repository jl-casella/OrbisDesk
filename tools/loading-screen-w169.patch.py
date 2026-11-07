#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Pending change (not applied): the launcher's loading screen becomes black with the app logo
and a green bar at the real boot stage. Usage: loading-screen-w169.patch.py DIR rewrites
DIR/wine_hardware.c and DIR/hw_text.h in place (DIR is native/ or a copy of it)."""
import pathlib,sys
root=pathlib.Path(sys.argv[1])
def revise(name,old,new):
    path=root/name;text=path.read_text()
    if text.count(old)!=1:raise SystemExit('Unexpected context in '+name+': '+old[:70])
    path.write_text(text.replace(old,new))

# '%' for the bar's percentage
revise('hw_text.h','''{0,0,0,0,0,4,4},{1,2,2,4,8,8,16}
};''','''{0,0,0,0,0,4,4},{1,2,2,4,8,8,16},
 {24,25,2,4,8,19,3}
};''')
revise('hw_text.h','''else if(c=='.')g=38;else if(c=='/')g=39;''','''else if(c=='.')g=38;else if(c=='/')g=39;else if(c=='%')g=40;''')

revise('wine_hardware.c','#include <limits.h>\n','#include <limits.h>\n#include <pthread.h>\n')

SCREEN=r'''/* W169: the loading screen. Black, the app logo (the PS4-shaped window of
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
        centred_text(590,"LOGS: /DATA/ORBISDESK/" HW_BUILD,0xff8a8a8a,2);
    }
    hw_text(pixels,WIDTH,HEIGHT,24,HEIGHT-30,"WINE " HW_BUILD,0xff404040,2);
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

/* PWBOOT progress markers use the kernel debug channel, invisible on retail hardware;'''
revise('wine_hardware.c','/* PWBOOT progress markers use the kernel debug channel, invisible on retail hardware;',SCREEN)
revise('wine_hardware.c','''    if(log_fd>=0&&text)write(log_fd,text,strlen(text));
    return __real_sceKernelDebugOutText(channel,text);''','''    if(log_fd>=0&&text){write(log_fd,text,strlen(text));boot_marker(text,strlen(text));}
    return __real_sceKernelDebugOutText(channel,text);''')
revise('wine_hardware.c','''    if(!console_fd(fd))return __real_write(fd,buffer,bytes);
    return __real_write(log_fd,buffer,bytes);''','''    if(!console_fd(fd))return __real_write(fd,buffer,bytes);
    ssize_t written=__real_write(log_fd,buffer,bytes);
    boot_marker(buffer,bytes);
    return written;''')
revise('wine_hardware.c','''static void panel(const char *state,const char *detail)
{
    if(!pixels)pixels=malloc(WIDTH*HEIGHT*4);
    if(!pixels)return;
    for(int i=0;i<WIDTH*HEIGHT;i++)pixels[i]=0xff102030;
    hw_text(pixels,WIDTH,HEIGHT,48,48,"ORBISDESK WINE " HW_BUILD,0xffffffff,5);
    hw_text(pixels,WIDTH,HEIGHT,48,130,"HOST LAUNCHER - PE32 CONSOLE TEST",0xffb0ccff,3);
    hw_text(pixels,WIDTH,HEIGHT,48,235,state,0xff77ee99,4);
    hw_text(pixels,WIDTH,HEIGHT,48,315,detail,0xffffffff,2);
    hw_text(pixels,WIDTH,HEIGHT,48,455,"IF THE APP CLOSES - REPORT BACK",0xffb0ccff,3);
    hw_text(pixels,WIDTH,HEIGHT,48,520,"LOGS: /DATA/ORBISDESK/" HW_BUILD,0xffb0ccff,3);
    pw_wine_present(pixels,WIDTH,HEIGHT,WIDTH*4);
}

''','')
revise('wine_hardware.c','''    panel("PREPARING WINE",path);''','''    loading(5,"PREPARING WINE");''')
revise('wine_hardware.c','''    panel("STARTING WINE","THIS RUN MAY EXIT OR STOP AT A REAL PLATFORM BLOCKER");''','''    loading(30,"STARTING WINE");''')
print('applied to',root)
