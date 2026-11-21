/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Phase C / P015 (child side): the separate native process becomes a WINDOW owner in OrbisDesk's desktop.
 * After the Phase B join (pop_wine_join_core.h) it speaks plain wineserver requests -- the same ones
 * win32u issues -- to:
 *   1. attach to the title's window station and desktop (WinSta0 \ "shell", explorer /desktop=shell),
 *   2. register a local window class and create a visible top-level popup window in that desktop, so the
 *      SERVER's window tree (z-order, hit testing, input routing) knows a window owned by this process,
 *   3. run a message loop on its own server queue: hardware mouse/keyboard messages the server routes to the
 *      window are accepted and counted; messages other threads SEND are replied to (a real window must answer
 *      them, or the sender -- possibly the title's explorer -- would wait),
 *   4. render its own pixels and stream them to the title over an AF_UNIX socket (POP_SEP_SURFACE); the
 *      title's sink composites them at the window's rectangle (pop_loader_spawn.h, pw_hw_separate_draw).
 * There is no win32u/PE loader here: this is the window/input/surface plumbing a separate Wine process needs,
 * proven with the real server, not a full Wine guest. Loader-dependent research substrate. */
#ifndef POP_SEPARATE_WINDOW_H
#define POP_SEPARATE_WINDOW_H
#include <time.h>
#include "pop_separate.h"
#include "pop_wine_join_core.h"

#define POP_STATUS_PENDING 0x103u
#define POP_WS_POPUP   0x80000000u
#define POP_WS_VISIBLE 0x10000000u
#define POP_SWP_NOSIZE 0x0001u
#define POP_SWP_NOMOVE 0x0002u
#define POP_SWP_NOREDRAW 0x0008u
#define POP_SWP_NOACTIVATE 0x0010u
#define POP_SWP_SHOWWINDOW 0x0040u
#define POP_SWP_HIDEWINDOW 0x0080u
#define POP_RDW_VALIDATE 0x0008u
#define POP_RDW_NOCHILDREN 0x0040u
#define POP_PM_REMOVE 1u
#define POP_GENERIC_ALL 0x10000000u

static unsigned int pop_c_simple(struct pop_join *j,union pop_request *req,size_t extra_len,const void *extra,
                                 union pop_reply *rep){
    return pop_call(j,req,extra_len,extra,rep,0,NULL);
}
static size_t pop_c_wstr(uint16_t *out,const char *ascii){
    size_t n=strlen(ascii);for(size_t i=0;i<n;i++)out[i]=(uint16_t)(unsigned char)ascii[i];return n*2;
}

/* ---- a tiny 5x7 font for the window's own text (A-Z, 0-9, space and a few marks) ---- */
static const char *pop_c_glyph(char c){
    static const struct {char c;const char rows[7];} font[]={
        {'A',{14,17,17,31,17,17,17}},{'B',{30,17,17,30,17,17,30}},{'C',{14,17,16,16,16,17,14}},
        {'D',{30,17,17,17,17,17,30}},{'E',{31,16,16,30,16,16,31}},{'F',{31,16,16,30,16,16,16}},
        {'G',{14,17,16,23,17,17,15}},{'H',{17,17,17,31,17,17,17}},{'I',{14,4,4,4,4,4,14}},
        {'J',{7,2,2,2,2,18,12}},{'K',{17,18,20,24,20,18,17}},{'L',{16,16,16,16,16,16,31}},
        {'M',{17,27,21,21,17,17,17}},{'N',{17,17,25,21,19,17,17}},{'O',{14,17,17,17,17,17,14}},
        {'P',{30,17,17,30,16,16,16}},{'Q',{14,17,17,17,21,18,13}},{'R',{30,17,17,30,20,18,17}},
        {'S',{15,16,16,14,1,1,30}},{'T',{31,4,4,4,4,4,4}},{'U',{17,17,17,17,17,17,14}},
        {'V',{17,17,17,17,17,10,4}},{'W',{17,17,17,21,21,21,10}},{'X',{17,17,10,4,10,17,17}},
        {'Y',{17,17,10,4,4,4,4}},{'Z',{31,1,2,4,8,16,31}},
        {'0',{14,17,19,21,25,17,14}},{'1',{4,12,4,4,4,4,14}},{'2',{14,17,1,2,4,8,31}},
        {'3',{30,1,1,14,1,1,30}},{'4',{2,6,10,18,31,2,2}},{'5',{31,16,30,1,1,17,14}},
        {'6',{6,8,16,30,17,17,14}},{'7',{31,1,2,4,8,8,8}},{'8',{14,17,17,14,17,17,14}},
        {'9',{14,17,17,15,1,2,12}},{':',{0,4,4,0,4,4,0}},{'.',{0,0,0,0,0,12,12}},
        {'-',{0,0,0,31,0,0,0}},{'/',{1,1,2,4,8,16,16}},{'=',{0,0,31,0,31,0,0}},{'(',{2,4,8,8,8,4,2}},
        {')',{8,4,2,2,2,4,8}},{',',{0,0,0,0,12,4,8}},
    };
    if(c>='a'&&c<='z')c=(char)(c-32);
    for(size_t i=0;i<sizeof(font)/sizeof(font[0]);i++)if(font[i].c==c)return font[i].rows;
    return NULL;
}
static void pop_c_text(uint32_t *px,int w,int h,int x,int y,const char *s,uint32_t color,int scale){
    for(;*s;s++,x+=6*scale){
        const char *g=pop_c_glyph(*s);if(!g)continue;
        for(int r=0;r<7;r++)for(int c=0;c<5;c++)if(g[r]&(16>>c))
            for(int dy=0;dy<scale;dy++)for(int dx=0;dx<scale;dx++){
                int X=x+c*scale+dx,Y=y+r*scale+dy;if(X>=0&&Y>=0&&X<w&&Y<h)px[Y*w+X]=color;
            }
    }
}
static void pop_c_fill(uint32_t *px,int w,int h,int x,int y,int fw,int fh,uint32_t color){
    for(int Y=y;Y<y+fh;Y++)for(int X=x;X<x+fw;X++)if(X>=0&&Y>=0&&X<w&&Y<h)px[Y*w+X]=color;
}

struct pop_c_state {
    unsigned int window,pid;
    int x,y,w,h;
    unsigned frame,mouse_moves,clicks,keys,sent_replied,paints;
    int last_x,last_y;unsigned last_msg;
    int pressed;
};

static void pop_c_render(struct pop_c_state *s,uint32_t *px,unsigned seconds_left){
    int w=s->w,h=s->h;
    for(int y=0;y<h;y++)for(int x=0;x<w;x++){   /* moving gradient: proves the frames are live */
        unsigned v=(unsigned)(x+y+(int)s->frame*4);
        px[y*w+x]=0xff000000u|((40+(v&63))<<16)|((30+((v>>1)&63))<<8)|(90+((v>>2)&63));
    }
    uint32_t edge=s->pressed?0xffffd040u:0xff60c0ffu;
    pop_c_fill(px,w,h,0,0,w,4,edge);pop_c_fill(px,w,h,0,h-4,w,4,edge);
    pop_c_fill(px,w,h,0,0,4,h,edge);pop_c_fill(px,w,h,w-4,0,4,h,edge);
    pop_c_fill(px,w,h,4,4,w-8,34,0xff203048u);
    pop_c_text(px,w,h,14,12,"PROCESO SEPARADO",0xffffffffu,3);
    char line[96];
    snprintf(line,sizeof(line),"PID NATIVO %d   WINE PID %u",(int)getpid(),s->pid);pop_c_text(px,w,h,14,56,line,0xffe0e8ffu,2);
    snprintf(line,sizeof(line),"VENTANA %X",s->window);pop_c_text(px,w,h,14,80,line,0xffe0e8ffu,2);
    snprintf(line,sizeof(line),"CLICKS %u   TECLAS %u",s->clicks,s->keys);pop_c_text(px,w,h,14,116,line,0xffffffffu,2);
    snprintf(line,sizeof(line),"MOUSE %u  EN %d,%d",s->mouse_moves,s->last_x,s->last_y);pop_c_text(px,w,h,14,140,line,0xffffffffu,2);
    snprintf(line,sizeof(line),"ULTIMO MENSAJE %X",s->last_msg);pop_c_text(px,w,h,14,164,line,0xffffffffu,2);
    snprintf(line,sizeof(line),"CUADRO %u   CIERRA EN %u S",s->frame,seconds_left);pop_c_text(px,w,h,14,h-60,line,0xffc0ffc0u,2);
    pop_c_text(px,w,h,14,h-32,"HACE CLICK ACA",0xffffd040u,2);
}

/* stream one frame: header then BGRA pixels (blocking, the title reads them on its own thread) */
static int pop_c_send_all(int fd,const void *data,size_t len){
    const char *p=data;
    while(len){ssize_t r=send(fd,p,len,0);if(r<0){if(errno==EINTR)continue;return -1;}p+=r;len-=(size_t)r;}
    return 0;
}
static int pop_c_surface_connect(struct pop_join *j){
    struct sockaddr_un addr;memset(&addr,0,sizeof(addr));addr.sun_family=AF_UNIX;
    snprintf(addr.sun_path,sizeof(addr.sun_path),"%s",POP_SEP_SURFACE);
#if defined(__FreeBSD__)||defined(__ORBIS__)
    addr.sun_len=(uint8_t)(sizeof(addr)-sizeof(addr.sun_path)+strlen(addr.sun_path)+1);
#endif
    for(int attempt=0;attempt<50;attempt++){
        int fd=socket(AF_UNIX,SOCK_STREAM,0);if(fd<0)break;
        if(connect(fd,(struct sockaddr*)&addr,sizeof(addr))==0){
            pop_logf(j,"{\"build\":\"P015\",\"event\":\"surface_connected\",\"attempt\":%d}",attempt+1);return fd;
        }
        int e=errno;close(fd);if(attempt==0)pop_logf(j,"{\"build\":\"P015\",\"event\":\"surface_retry\",\"errno\":%d}",e);
        usleep(100000);
    }
    pop_logf(j,"{\"build\":\"P015\",\"event\":\"surface_unavailable\",\"errno\":%d}",errno);
    return -1;
}

/* attach this (already joined) process to the title's window station and desktop */
static int pop_c_attach_desktop(struct pop_join *j){
    union pop_request req;union pop_reply rep;char buf[512];uint16_t *w=(uint16_t*)buf;
    char name[128];snprintf(name,sizeof(name),"\\Sessions\\%u\\Windows\\WindowStations\\" POP_SEP_WINSTA,j->session_id);
    memset(&req,0,sizeof(req));req.ows.__header.req=POP_REQ_open_winstation;req.ows.access=POP_GENERIC_ALL;
    unsigned int err=pop_c_simple(j,&req,pop_c_wstr(w,name),buf,&rep);
    unsigned int winsta=rep.ows.handle;
    pop_logf(j,"{\"build\":\"P015\",\"event\":\"open_winstation\",\"name\":\"%s\",\"status\":\"0x%08x\",\"handle\":%u}",
             "WinSta0",err,winsta);
    if(err||!winsta)return 0;
    memset(&req,0,sizeof(req));req.spw.__header.req=POP_REQ_set_process_winstation;req.spw.handle=winsta;
    err=pop_c_simple(j,&req,0,NULL,&rep);
    pop_logf(j,"{\"build\":\"P015\",\"event\":\"set_process_winstation\",\"status\":\"0x%08x\"}",err);
    if(err)return 0;
    memset(&req,0,sizeof(req));req.od.__header.req=POP_REQ_open_desktop;req.od.winsta=winsta;req.od.access=POP_GENERIC_ALL;
    err=pop_c_simple(j,&req,pop_c_wstr(w,POP_SEP_DESKTOP),buf,&rep);
    unsigned int desktop=rep.od.handle;
    pop_logf(j,"{\"build\":\"P015\",\"event\":\"open_desktop\",\"name\":\"%s\",\"status\":\"0x%08x\",\"handle\":%u}",
             POP_SEP_DESKTOP,err,desktop);
    if(err||!desktop)return 0;
    memset(&req,0,sizeof(req));req.std.__header.req=POP_REQ_set_thread_desktop;req.std.handle=desktop;
    err=pop_c_simple(j,&req,0,NULL,&rep);
    pop_logf(j,"{\"build\":\"P015\",\"event\":\"set_thread_desktop\",\"status\":\"0x%08x\"}",err);
    return !err;
}

static int pop_c_create_window(struct pop_join *j,struct pop_c_state *s){
    union pop_request req;union pop_reply rep;char buf[512];
    /* local class: VARARG = struct class_info, then the class name */
    struct pop_class_info info;memset(&info,0,sizeof(info));
    memcpy(buf,&info,sizeof(info));size_t len=sizeof(info)+pop_c_wstr((uint16_t*)(buf+sizeof(info)),"OrbisSeparateWindow");
    memset(&req,0,sizeof(req));req.cc.__header.req=POP_REQ_create_class;
    unsigned int err=pop_c_simple(j,&req,len,buf,&rep);
    unsigned int atom=rep.cc.atom;
    pop_logf(j,"{\"build\":\"P015\",\"event\":\"create_class\",\"status\":\"0x%08x\",\"atom\":%u}",err,atom);
    if(err||!atom)return 0;
    memset(&req,0,sizeof(req));req.cw.__header.req=POP_REQ_create_window;
    req.cw.atom=atom;req.cw.style=POP_WS_POPUP|POP_WS_VISIBLE;
    req.cw.dpi.num=req.cw.dpi.den=req.cw.raw_dpi.num=req.cw.raw_dpi.den=96;
    err=pop_c_simple(j,&req,0,NULL,&rep);
    s->window=rep.cw.handle;
    pop_logf(j,"{\"build\":\"P015\",\"event\":\"create_window\",\"status\":\"0x%08x\",\"handle\":%u,\"parent\":%u}",
             err,s->window,rep.cw.parent);
    if(err||!s->window)return 0;
    uint16_t *w=(uint16_t*)buf;
    memset(&req,0,sizeof(req));req.swt.__header.req=POP_REQ_set_window_text;req.swt.handle=s->window;
    err=pop_c_simple(j,&req,pop_c_wstr(w,"OrbisDesk proceso separado"),buf,&rep);
    pop_logf(j,"{\"build\":\"P015\",\"event\":\"set_window_text\",\"status\":\"0x%08x\"}",err);
    /* show it at the top of the z-order. SWP_NOREDRAW: our pixels arrive through the surface socket, so the
     * server need not invalidate this window (no WM_PAINT loop with nothing to validate it). */
    memset(&req,0,sizeof(req));req.swp.__header.req=POP_REQ_set_window_pos;
    req.swp.swp_flags=POP_SWP_SHOWWINDOW|POP_SWP_NOACTIVATE|POP_SWP_NOREDRAW;req.swp.handle=s->window;req.swp.previous=0;
    req.swp.window.left=req.swp.client.left=s->x;req.swp.window.top=req.swp.client.top=s->y;
    req.swp.window.right=req.swp.client.right=s->x+s->w;req.swp.window.bottom=req.swp.client.bottom=s->y+s->h;
    err=pop_c_simple(j,&req,0,NULL,&rep);
    pop_logf(j,"{\"build\":\"P015\",\"event\":\"set_window_pos\",\"status\":\"0x%08x\",\"new_style\":\"0x%08x\",\"x\":%d,\"y\":%d,\"w\":%d,\"h\":%d}",
             err,rep.swp.new_style,s->x,s->y,s->w,s->h);
    return !err;
}

/* drain this thread's server queue once; returns the number of messages handled */
static int pop_c_pump(struct pop_join *j,struct pop_c_state *s){
    static char data[16384];int handled=0;
    for(;;){
        union pop_request req;union pop_reply rep;
        memset(&req,0,sizeof(req));req.gm.__header.req=POP_REQ_get_message;
        req.gm.flags=POP_PM_REMOVE;req.gm.get_last=~0u;
        unsigned int err=pop_call(j,&req,0,NULL,&rep,sizeof(data),data);
        if(err==POP_STATUS_PENDING)return handled;
        if(err){pop_logf(j,"{\"build\":\"P015\",\"event\":\"get_message_error\",\"status\":\"0x%08x\"}",err);return handled;}
        handled++;
        unsigned msg=rep.gm.msg;int type=rep.gm.type;
        s->last_msg=msg;
        if(type==POP_MSG_HARDWARE){
            unsigned hw_id=0;if(rep.gm.__header.reply_size>=20)memcpy(&hw_id,data+16,sizeof(hw_id));
            memset(&req,0,sizeof(req));req.ahm.__header.req=POP_REQ_accept_hardware_message;req.ahm.hw_id=hw_id;
            pop_c_simple(j,&req,0,NULL,&rep);
        }
        if(msg==0x200){s->mouse_moves++;s->last_x=rep.gm.x;s->last_y=rep.gm.y;
            if(s->mouse_moves==1||s->mouse_moves%50==0)
                pop_logf(j,"{\"build\":\"P015\",\"event\":\"input\",\"msg\":\"WM_MOUSEMOVE\",\"x\":%d,\"y\":%d,\"count\":%u}",
                         rep.gm.x,rep.gm.y,s->mouse_moves);}
        else if(msg==0x201||msg==0x204||msg==0x207){s->clicks++;s->pressed=1;s->last_x=rep.gm.x;s->last_y=rep.gm.y;
            pop_logf(j,"{\"build\":\"P015\",\"event\":\"input\",\"msg\":\"0x%x\",\"x\":%d,\"y\":%d,\"clicks\":%u}",msg,rep.gm.x,rep.gm.y,s->clicks);}
        else if(msg==0x202||msg==0x205||msg==0x208){s->pressed=0;}
        else if(msg>=0x100&&msg<=0x109){if(msg==0x100||msg==0x104)s->keys++;
            pop_logf(j,"{\"build\":\"P015\",\"event\":\"input\",\"msg\":\"0x%x\",\"wparam\":%llu}",msg,(unsigned long long)rep.gm.wparam);}
        else if(msg==0x000f){   /* WM_PAINT: validate, our pixels come through the surface */
            s->paints++;
            memset(&req,0,sizeof(req));req.rw.__header.req=POP_REQ_redraw_window;req.rw.window=s->window;
            req.rw.flags=POP_RDW_VALIDATE|POP_RDW_NOCHILDREN;pop_c_simple(j,&req,0,NULL,&rep);
        }
        else if(handled<=40)
            pop_logf(j,"{\"build\":\"P015\",\"event\":\"message\",\"msg\":\"0x%x\",\"type\":%d,\"win\":%u}",msg,type,rep.gm.win);
        /* a message another thread SENT waits for our answer: reply like DefWindowProc's 0 */
        if(type==POP_MSG_ASCII||type==POP_MSG_UNICODE||type==POP_MSG_CALLBACK||type==POP_MSG_OTHER_PROCESS||type==POP_MSG_HOOK_LL){
            memset(&req,0,sizeof(req));req.rm.__header.req=POP_REQ_reply_message;req.rm.remove=1;req.rm.result=0;
            pop_c_simple(j,&req,0,NULL,&rep);s->sent_replied++;
        }
    }
}

/* Phase C run: window + input + surface for `seconds`, then hide and destroy the window. 1 = window shown
 * and frames delivered, 0 otherwise. */
static int pop_separate_window_run(struct pop_join *j,int seconds){
    struct pop_c_state s;memset(&s,0,sizeof(s));
    s.pid=j->wine_pid;s.x=POP_SEP_WIN_X;s.y=POP_SEP_WIN_Y;s.w=POP_SEP_WIN_W;s.h=POP_SEP_WIN_H;
    if(!pop_c_attach_desktop(j))return 0;
    if(!pop_c_create_window(j,&s))return 0;
    int surface=pop_c_surface_connect(j);
    uint32_t *px=malloc((size_t)s.w*s.h*4);if(!px)return 0;
    struct timespec t0;clock_gettime(CLOCK_MONOTONIC,&t0);
    unsigned sent_frames=0;int last_logged_second=-1;
    for(;;){
        struct timespec now;clock_gettime(CLOCK_MONOTONIC,&now);
        int elapsed=(int)(now.tv_sec-t0.tv_sec);if(elapsed>=seconds)break;
        pop_c_pump(j,&s);
        pop_c_render(&s,px,(unsigned)(seconds-elapsed));
        if(surface>=0){
            struct pop_sep_frame hdr;memset(&hdr,0,sizeof(hdr));
            hdr.magic=POP_SEP_FRAME_MAGIC;hdr.x=s.x;hdr.y=s.y;hdr.w=s.w;hdr.h=s.h;hdr.frame=s.frame;
            hdr.window=s.window;hdr.clicks=s.clicks;
            if(pop_c_send_all(surface,&hdr,sizeof(hdr))||pop_c_send_all(surface,px,(size_t)s.w*s.h*4)){
                pop_logf(j,"{\"build\":\"P015\",\"event\":\"surface_send_failed\",\"errno\":%d,\"frame\":%u}",errno,s.frame);
                close(surface);surface=-1;
            }else sent_frames++;
        }
        if(elapsed%15==0&&elapsed!=last_logged_second){last_logged_second=elapsed;
            pop_logf(j,"{\"build\":\"P015\",\"event\":\"alive\",\"second\":%d,\"frames\":%u,\"mouse\":%u,\"clicks\":%u,\"keys\":%u,\"replied\":%u,\"paints\":%u}",
                     elapsed,sent_frames,s.mouse_moves,s.clicks,s.keys,s.sent_replied,s.paints);}
        s.frame++;
        usleep(100000);  /* about 10 frames a second */
    }
    union pop_request req;union pop_reply rep;
    /* hide first (the server then exposes what was underneath to the title's windows), then destroy */
    memset(&req,0,sizeof(req));req.swp.__header.req=POP_REQ_set_window_pos;
    req.swp.swp_flags=POP_SWP_HIDEWINDOW|POP_SWP_NOACTIVATE|POP_SWP_NOMOVE|POP_SWP_NOSIZE;req.swp.handle=s.window;
    req.swp.window.left=req.swp.client.left=s.x;req.swp.window.top=req.swp.client.top=s.y;
    req.swp.window.right=req.swp.client.right=s.x+s.w;req.swp.window.bottom=req.swp.client.bottom=s.y+s.h;
    unsigned int herr=pop_c_simple(j,&req,0,NULL,&rep);
    memset(&req,0,sizeof(req));req.dw.__header.req=POP_REQ_destroy_window;req.dw.handle=s.window;
    unsigned int derr=pop_c_simple(j,&req,0,NULL,&rep);
    pop_logf(j,"{\"build\":\"P015\",\"event\":\"window_closed\",\"hide\":\"0x%08x\",\"destroy\":\"0x%08x\",\"frames\":%u,\"mouse\":%u,\"clicks\":%u,\"keys\":%u,\"replied\":%u}",
             herr,derr,sent_frames,s.mouse_moves,s.clicks,s.keys,s.sent_replied);
    if(surface>=0)close(surface);
    free(px);
    return sent_frames>0;
}

#endif
