/* SPDX-License-Identifier: GPL-3.0-or-later */
/* 2026-11-20: MANAGE INSTALLATION on the loading screen.
 *
 * A gear at the bottom right of the loading screen says that OPTIONS opens this menu. The launcher reads the
 * pad from its first screen until Wine starts (hw_manage_watch). A press is acted on at the next checkpoint
 * (hw_manage_checkpoint): after the jailbreak, so the title deletes as root what the console's FTP server could
 * not (the files Wine and the installer made), and once more just before Wine starts. Nothing is deleted while
 * Wine runs.
 *
 * The menu, its confirmation pages and the X/O answers follow the Steam client's uninstall and sign-out pages:
 * only X goes on, O goes back. Choices:
 * - REINSTALL DATA: deletes what DELETE DATA deletes, then relaunches the title, whose installer puts the
 *   package's runtime back (native/hw_install.h finds no install record).
 * - DELETE DATA - KEEP GAMES AND SAVES: the four folders the runtime and the title write, except the Steam games
 *   and the Steam sign-in, the user's Documents, Saved Games and Desktop, and the Steam shortcuts. Then the
 *   title closes.
 * - DELETE EVERYTHING: the four folders as they are. Then the title closes.
 * - BACK: the start goes on.
 * Included by native/wine_hardware.c after the loading screen (draw_logo, centred_text, pixels, screen_lock),
 * note(), the jailbreak and the relaunch. */
#include <dirent.h>
extern int pw_hw_pad_handle(void);  /* native/hw_pad.c: opens the pad once */

static volatile int manage_accepting=1;  /* the gear is drawn and OPTIONS is read until Wine starts */
static volatile int manage_requested;
static const char *const hw_manage_roots[]={"/data/orbisdesk","/data/wine-prefix","/data/wine-home","/data/wine"};
/* what DELETE DATA keeps (and REINSTALL DATA): the folders and files themselves, with what they hold */
static const char *const hw_manage_keep[]={
    "/data/orbisdesk/steam-games","/data/orbisdesk/steam","/data/orbisdesk/steam-client.txt",
    "/data/orbisdesk/steam-client.prev.txt","/data/orbisdesk/steam-library.txt",
    "/data/wine-prefix/drive_c/users/orbis/Documents","/data/wine-prefix/drive_c/users/orbis/Saved Games",
    "/data/wine-prefix/drive_c/users/orbis/Desktop",
    "/data/wine-prefix/drive_c/ProgramData/Microsoft/Windows/Start Menu/Programs/Steam"};

/* ---- drawing (screen_lock held) ---- */
static void hw_manage_fill(int x,int y,int w,int h,uint32_t color)
{
    for(int yy=y;yy<y+h;yy++)for(int xx=x;xx<x+w;xx++)
        if(xx>=0&&xx<WIDTH&&yy>=0&&yy<HEIGHT)pixels[yy*WIDTH+xx]=color;
}
/* a gear: eight teeth (rectangles at 45 degrees) around a ring with a hole, 4x4 samples a pixel; no libm */
static void hw_manage_gear(int cx,int cy,int r,uint32_t color)
{
    for(int y=-r-1;y<=r+1;y++)for(int x=-r-1;x<=r+1;x++){
        int hits=0;
        for(int sy=0;sy<4;sy++)for(int sx=0;sx<4;sx++){
            static const float dir[8][2]={{1,0},{0.7071f,0.7071f},{0,1},{-0.7071f,0.7071f},
                                          {-1,0},{-0.7071f,-0.7071f},{0,-1},{0.7071f,-0.7071f}};
            float fx=x+(sx+0.5f)/4-0.5f,fy=y+(sy+0.5f)/4-0.5f,d2=fx*fx+fy*fy;
            int in=d2>r*r*0.34f*0.34f&&d2<r*r*0.72f*0.72f;
            for(int k=0;k<8&&!in;k++){
                float along=fx*dir[k][0]+fy*dir[k][1],across=-fx*dir[k][1]+fy*dir[k][0];
                in=along>r*0.6f&&along<r&&across>-r*0.2f&&across<r*0.2f;
            }
            hits+=in;
        }
        int px=cx+x,py=cy+y;
        if(hits&&px>=0&&px<WIDTH&&py>=0&&py<HEIGHT){
            uint32_t back=pixels[py*WIDTH+px],out=0xff000000;
            for(int s=0;s<24;s+=8){
                unsigned a=(back>>s)&255,b=(color>>s)&255;
                out|=(uint32_t)((a*(16-hits)+b*hits)/16)<<s;
            }
            pixels[py*WIDTH+px]=out;
        }
    }
}
/* the loading screen's hint, bottom right (draw_screen calls it while the bar is up) */
static void hw_manage_hint(void)
{
    if(!manage_accepting)return;
    const char *label=manage_requested?"OPENING MANAGE INSTALLATION":"OPTIONS: MANAGE INSTALLATION";
    int width=((int)strlen(label)*6-1)*2,x=WIDTH-24-width;
    hw_manage_gear(x-22,HEIGHT-24,11,manage_requested?0xffffffff:0xff8a8a8a);
    hw_text(pixels,WIDTH,HEIGHT,x,HEIGHT-30,label,manage_requested?0xffffffff:0xff606060,2);
}
/* text in lines of at most columns characters, broken at spaces; returns the y below it */
static int hw_manage_wrap(int x,int y,const char *text,uint32_t color,int scale,int columns)
{
    char line[128];
    while(*text){
        int n=(int)strlen(text),take=n<columns?n:columns;
        if(take<n){int cut=take;while(cut>0&&text[cut]!=' ')cut--;if(cut>0)take=cut;}
        if(take>(int)sizeof(line)-1)take=(int)sizeof(line)-1;
        memcpy(line,text,(size_t)take);line[take]=0;
        hw_text(pixels,WIDTH,HEIGHT,x,y,line,color,scale);
        y+=11*scale;text+=take;while(*text==' ')text++;
    }
    return y;
}
static void hw_manage_frame(const char *title)
{
    for(int i=0;i<WIDTH*HEIGHT;i++)pixels[i]=0xff000000;
    draw_logo(64,40,0.18f);
    hw_text(pixels,WIDTH,HEIGHT,140,58,title,0xffffffff,4);
    hw_manage_gear(WIDTH-80,72,22,0xff8a8a8a);
    hw_manage_fill(64,126,WIDTH-128,2,0xff2a2a2a);
}
static void hw_manage_footer(const char *text)
{
    hw_manage_fill(64,HEIGHT-74,WIDTH-128,2,0xff2a2a2a);
    hw_text(pixels,WIDTH,HEIGHT,64,HEIGHT-54,text,0xffb0b0b0,2);
    hw_text(pixels,WIDTH,HEIGHT,WIDTH-64-((int)strlen("VERSION " HW_VERSION)*6-1)*2,HEIGHT-54,
            "VERSION " HW_VERSION,0xff404040,2);
}
static void hw_manage_present(void){pw_wine_present(pixels,WIDTH,HEIGHT,WIDTH*4);}

enum {HW_MANAGE_REINSTALL,HW_MANAGE_DELETE_KEEP,HW_MANAGE_DELETE_ALL,HW_MANAGE_BACK,HW_MANAGE_CHOICES};
static const char *const hw_manage_items[HW_MANAGE_CHOICES]={
    "REINSTALL DATA","DELETE DATA - KEEP GAMES AND SAVES","DELETE EVERYTHING","BACK"};
/* the lettering of hw_text.h has letters, digits and : - . / %: no commas */
/* the lettering of hw_text.h has letters, digits and : - . / %: no commas */
static const char *const hw_manage_about[HW_MANAGE_CHOICES]={
    "DELETES WINE - ITS SETTINGS AND THE LOGS. THEN ORBISDESK STARTS AGAIN AND INSTALLS THEM FROM THE PACKAGE "
    "AS ON ITS FIRST START. THE STEAM GAMES AND SIGN-IN - DOCUMENTS - SAVED GAMES AND THE DESKTOP STAY.",
    "DELETES WINE - ITS SETTINGS AND THE LOGS. THEN ORBISDESK CLOSES. THE STEAM GAMES AND SIGN-IN - "
    "DOCUMENTS - SAVED GAMES AND THE DESKTOP STAY. USE IT BEFORE UNINSTALLING TO KEEP THEM.",
    "DELETES ALL THE DATA OF ORBISDESK. THEN ORBISDESK CLOSES. THAT IS WINE - ITS SETTINGS - THE LOGS - THE "
    "STEAM GAMES AND SIGN-IN - DOCUMENTS AND SAVES. USE IT BEFORE UNINSTALLING TO LEAVE NOTHING BEHIND.",
    "CLOSES THIS MENU. ORBISDESK STARTS."};
static void hw_manage_draw_menu(int selected)
{
    hw_manage_frame("MANAGE INSTALLATION");
    for(int i=0;i<HW_MANAGE_CHOICES;i++){
        int y=170+i*62;
        if(i==selected){hw_manage_fill(64,y-14,WIDTH-128,46,0xff1b3a66);hw_manage_fill(64,y-14,6,46,0xff62c4ff);}
        hw_text(pixels,WIDTH,HEIGHT,92,y,hw_manage_items[i],
                i==selected?0xffffffff:(i==HW_MANAGE_DELETE_ALL?0xffff8a8a:0xffb0b0b0),3);
    }
    hw_manage_wrap(92,440,hw_manage_about[selected],0xff8a8a8a,2,90);
    hw_manage_footer("UP/DOWN: CHOOSE     X: SELECT     O: BACK");
}
static void hw_manage_draw_confirm(int choice)
{
    hw_manage_frame(hw_manage_items[choice]);
    int y=hw_manage_wrap(64,160,hw_manage_about[choice],0xffffffff,2,96)+14;
    hw_text(pixels,WIDTH,HEIGHT,64,y,"DELETED:",0xffff6a6a,2);y+=26;
    for(unsigned i=0;i<sizeof(hw_manage_roots)/sizeof(hw_manage_roots[0]);i++,y+=22)
        hw_text(pixels,WIDTH,HEIGHT,92,y,hw_manage_roots[i],0xffb0b0b0,2);
    if(choice!=HW_MANAGE_DELETE_ALL){
        y+=8;hw_text(pixels,WIDTH,HEIGHT,64,y,"KEPT:",0xff5be36a,2);y+=26;
        static const char *const kept[]={"STEAM GAMES AND SIGN-IN","DOCUMENTS - SAVED GAMES - DESKTOP","STEAM SHORTCUTS"};
        for(unsigned i=0;i<sizeof(kept)/sizeof(kept[0]);i++,y+=22)hw_text(pixels,WIDTH,HEIGHT,92,y,kept[i],0xffb0b0b0,2);
    }
    y+=10;hw_text(pixels,WIDTH,HEIGHT,64,y,"IT CANNOT BE UNDONE.",0xffff6a6a,2);
    hw_manage_footer(choice==HW_MANAGE_REINSTALL?"X: DELETE AND REINSTALL     O: CANCEL":"X: DELETE     O: CANCEL");
}
static void hw_manage_draw_progress(const char *title,unsigned long long files,unsigned failed,const char *state)
{
    char line[96];
    hw_manage_frame(title);
    centred_text(300,state,0xffffffff,3);
    snprintf(line,sizeof(line),"FILES DELETED: %llu",files);
    centred_text(360,line,0xffb0b0b0,2);
    if(failed){snprintf(line,sizeof(line),"NOT DELETED: %u - SEE THE LOG",failed);centred_text(392,line,0xffff6a6a,2);}
}

/* ---- the pad ---- */
static void *hw_manage_watch(void *unused)
{
    (void)unused;
    int pad=pw_hw_pad_handle();uint32_t last=0;
    note(HW_BUILD " PWMANAGE watch pad=0x%08x\n",(unsigned)pad);
    while(manage_accepting&&!manage_requested){
        OrbisPadData data;memset(&data,0,sizeof(data));
        if(pad>=0&&!scePadReadState(pad,&data)){
            if((data.buttons&ORBIS_PAD_BUTTON_OPTIONS)&&!(last&ORBIS_PAD_BUTTON_OPTIONS)){
                manage_requested=1;note(HW_BUILD " PWMANAGE requested\n");
                pthread_mutex_lock(&screen_lock);
                if(!screen_handed)draw_screen(boot_percent,boot_state,NULL);
                pthread_mutex_unlock(&screen_lock);
            }
            last=data.buttons;
        }
        sceKernelUsleep(20000);
    }
    return NULL;
}
static void hw_manage_start(void)
{
    pthread_t thread;int rc=pthread_create(&thread,NULL,hw_manage_watch,NULL);
    if(!rc)pthread_detach(thread);
    note(HW_BUILD " PWMANAGE watch_thread rc=%d\n",rc);
}
/* the next button of mask pressed (released before, so the press that opened a page is not taken again) */
static uint32_t hw_manage_wait(uint32_t mask)
{
    int pad=pw_hw_pad_handle();uint32_t last=0xffffffffu;
    for(;;){
        OrbisPadData data;memset(&data,0,sizeof(data));
        if(pad>=0&&!scePadReadState(pad,&data)){
            uint32_t pressed=data.buttons&~last&mask;last=data.buttons;
            if(pressed)return pressed&-pressed;
        }
        sceKernelUsleep(20000);
    }
}

/* ---- deleting ---- */
struct hw_manage_count {unsigned long long files;unsigned failed;const char *title;uint64_t shown;int keep;};
static int hw_manage_kept(const char *path)
{
    for(unsigned i=0;i<sizeof(hw_manage_keep)/sizeof(hw_manage_keep[0]);i++)if(!strcmp(path,hw_manage_keep[i]))return 1;
    return 0;
}
static void hw_manage_failed(struct hw_manage_count *c,const char *what,const char *path)
{
    if(c->failed++<32)note(HW_BUILD " PWMANAGE %s_failed errno=%d %s\n",what,errno,path);
}
static void hw_manage_tick(struct hw_manage_count *c)
{
    uint64_t now=sceKernelGetProcessTime();
    if(now-c->shown<250000)return;
    c->shown=now;
    pthread_mutex_lock(&screen_lock);
    hw_manage_draw_progress(c->title,c->files,c->failed,"DELETING");hw_manage_present();
    pthread_mutex_unlock(&screen_lock);
}
/* everything under path, then path itself; what is kept stays with the folders that hold it */
static void hw_manage_remove(const char *path,struct hw_manage_count *c)
{
    struct stat st;
    if(c->keep&&hw_manage_kept(path))return;
    if(lstat(path,&st)){if(errno!=ENOENT)hw_manage_failed(c,"stat",path);return;}
    if(S_ISDIR(st.st_mode)){
        DIR *dir=opendir(path);
        if(dir){
            struct dirent *e;char child[PATH_MAX];
            while((e=readdir(dir))){
                if(!strcmp(e->d_name,".")||!strcmp(e->d_name,".."))continue;
                if(snprintf(child,sizeof(child),"%s/%s",path,e->d_name)>=(int)sizeof(child)){hw_manage_failed(c,"name",path);continue;}
                hw_manage_remove(child,c);
            }
            closedir(dir);
        } else hw_manage_failed(c,"open",path);
        if(rmdir(path)&&!(c->keep&&(errno==ENOTEMPTY||errno==EEXIST)))hw_manage_failed(c,"rmdir",path);
    } else {
        if(unlink(path)&&errno!=ENOENT){chmod(path,0666);if(unlink(path)&&errno!=ENOENT)hw_manage_failed(c,"unlink",path);else c->files++;}
        else c->files++;
        hw_manage_tick(c);
    }
}
static void hw_manage_delete(int choice,struct hw_manage_count *c)
{
    memset(c,0,sizeof(*c));
    c->title=hw_manage_items[choice];c->keep=choice!=HW_MANAGE_DELETE_ALL;
    uint64_t start=sceKernelGetProcessTime();
    note(HW_BUILD " PWMANAGE delete choice=%s root=%d uid=%d\n",hw_manage_items[choice],jailbroken,getuid());
    for(unsigned i=0;i<sizeof(hw_manage_roots)/sizeof(hw_manage_roots[0]);i++)hw_manage_remove(hw_manage_roots[i],c);
    note(HW_BUILD " PWMANAGE delete done files=%llu failed=%u ms=%llu\n",c->files,c->failed,
         (unsigned long long)((sceKernelGetProcessTime()-start)/1000));
}

/* ---- the menu ---- */
/* returns when the start goes on (BACK, or nothing was asked); a deletion ends in a close or a relaunch */
static void hw_manage_checkpoint(const char *where)
{
    if(!manage_requested)return;
    note(HW_BUILD " PWMANAGE menu at=%s root=%d\n",where,jailbroken);
    int selected=HW_MANAGE_BACK;
    for(;;){
        pthread_mutex_lock(&screen_lock);hw_manage_draw_menu(selected);hw_manage_present();pthread_mutex_unlock(&screen_lock);
        uint32_t key=hw_manage_wait(ORBIS_PAD_BUTTON_UP|ORBIS_PAD_BUTTON_DOWN|ORBIS_PAD_BUTTON_CROSS|ORBIS_PAD_BUTTON_CIRCLE);
        if(key==ORBIS_PAD_BUTTON_UP){selected=(selected+HW_MANAGE_CHOICES-1)%HW_MANAGE_CHOICES;continue;}
        if(key==ORBIS_PAD_BUTTON_DOWN){selected=(selected+1)%HW_MANAGE_CHOICES;continue;}
        if(key==ORBIS_PAD_BUTTON_CIRCLE||selected==HW_MANAGE_BACK)break;
        pthread_mutex_lock(&screen_lock);hw_manage_draw_confirm(selected);hw_manage_present();pthread_mutex_unlock(&screen_lock);
        if(hw_manage_wait(ORBIS_PAD_BUTTON_CROSS|ORBIS_PAD_BUTTON_CIRCLE)!=ORBIS_PAD_BUTTON_CROSS){
            note(HW_BUILD " PWMANAGE canceled choice=%s\n",hw_manage_items[selected]);continue;
        }
        struct hw_manage_count count;hw_manage_delete(selected,&count);
        int reinstall=selected==HW_MANAGE_REINSTALL;
        pthread_mutex_lock(&screen_lock);
        hw_manage_draw_progress(hw_manage_items[selected],count.files,count.failed,
                                reinstall?"DELETED - ORBISDESK STARTS AGAIN":"DELETED - ORBISDESK CLOSES");
        hw_manage_present();
        pthread_mutex_unlock(&screen_lock);
        sceKernelUsleep(3000000);
        if(reinstall){
            /* as "Reset as Root": the relaunch's installer finds no record and installs the package's runtime */
            pw_hw_unjailbreak("reinstall");
            int rc=sceSystemServiceLoadExec(HW_SELF,NULL);
            note(HW_BUILD " PWMANAGE relaunch rc=0x%08x\n",(unsigned)rc);
            if(!rc)wait_for_system_close("reinstall");
            pthread_mutex_lock(&screen_lock);
            hw_manage_draw_progress(hw_manage_items[selected],count.files,count.failed,"CLOSE ORBISDESK AND OPEN IT AGAIN");
            hw_manage_present();
            pthread_mutex_unlock(&screen_lock);
            for(;;)sceKernelUsleep(1000000);
        }
        exit(0);
    }
    note(HW_BUILD " PWMANAGE back at=%s\n",where);
    manage_requested=0;
    pthread_mutex_lock(&screen_lock);
    if(!screen_handed)draw_screen(boot_percent,boot_state,NULL);
    pthread_mutex_unlock(&screen_lock);
    hw_manage_start();  /* OPTIONS can open it again until Wine starts */
}
