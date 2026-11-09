/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Input for the hardware launcher (W028-W037). The win32u user driver (ps5drv.c)
 * pulls events through pw_wine_next_input() and is woken through pw_wine_input_fd().
 * A thread polls every 16 ms:
 *   controller   left stick and touchpad finger move the pointer; right stick scrolls;
 *                cross and a one-finger touchpad press left button; circle, a
 *                two-finger press or a two-finger tap right button; d-pad arrows,
 *                triangle Enter, square Escape, options Windows key
 *   USB mouse    relative motion moves the same pointer; left, right, middle buttons, wheel
 *   USB keyboard USB HID usages translated to Windows virtual keys, with modifiers
 * W178: the controller's state is also xinput's (pw_wine_pad); while a program reads it there,
 * its sticks and buttons stop driving the pointer and keys (game mode).
 * W181: a program with a key profile (C:\orbis\padmaps\<exe>.ini) gets keys from the buttons and
 * the left stick instead (pw_hw_pad_profile), for games that read only the keyboard.
 * The sink draws the pointer, since the driver has no cursor of its own. */
#include <errno.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <unistd.h>
#include <sys/socket.h>
#include "pw_trace.h"  /* alpha-1: the first input events and stick reports, traces only */
#include <sys/time.h>
#include <orbis/libkernel.h>
#include <orbis/Pad.h>
#include <orbis/_types/keyboard.h>
#include <orbis/Sysmodule.h>
#include <orbis/UserService.h>

struct PwWineInput {uint32_t type,code;int32_t x,y;uint32_t down;};  /* ps5drv struct ps5_input */
/* Mouse layout and calls as in the shadPS4 mouse module (mouse.h); the SDK has no
 * prototypes. Mouse and keyboard libraries are loaded at run time and resolved by name,
 * so a console where one is unavailable still starts with the controller. */
typedef struct {uint64_t timestamp;bool connected;uint32_t buttons;int32_t x,y,wheel,tilt;uint8_t reserve[8];} PwMouseData;
typedef struct {uint8_t flag;uint8_t reserve[7];} PwMouseOpenParam;
static int32_t (*mouse_init)(void);
static int32_t (*mouse_open)(int32_t,int32_t,int32_t,PwMouseOpenParam *);
static int32_t (*mouse_read)(int32_t,PwMouseData *,int32_t);
static int32_t (*keyboard_init)(void);
static int32_t (*keyboard_open)(int32_t,int32_t,int32_t,void *);
static int32_t (*keyboard_read)(int32_t,OrbisKeyboardData *);
static int load_library(const char *name,unsigned sysmodule,int internal)
{
    int rc_sys=internal?(int)sceSysmoduleLoadModuleInternal(sysmodule):(int)sceSysmoduleLoadModule((uint16_t)sysmodule);
    /* W030: /system/... is not visible to the application (0x80020002); the system
     * libraries appear under the sandbox's random word. */
    const char *word=sceKernelGetFsSandboxRandomWord();
    char dirs[3][64];
    snprintf(dirs[0],sizeof(dirs[0]),"/%s/common/lib/",word?word:"system");
    snprintf(dirs[1],sizeof(dirs[1]),"/%s/priv/lib/",word?word:"system");
    snprintf(dirs[2],sizeof(dirs[2]),"/system/common/lib/");
    int module=-1;char path[128];
    for(unsigned i=0;i<3 && module<0;i++) {
        snprintf(path,sizeof(path),"%s%s",dirs[i],name);
        module=(int)sceKernelLoadStartModule(path,0,NULL,0,NULL,NULL);
    }
    fprintf(stderr,"PWBOOT input_module name=%s sysmodule=0x%08x module=0x%08x path=%s\n",name,(unsigned)rc_sys,(unsigned)module,path);
    return module;
}
static void *symbol(int module,const char *name)
{
    void *address=NULL;
    int rc=module<0?-1:sceKernelDlsym(module,name,&address);
    if(rc || !address) {fprintf(stderr,"PWBOOT input_symbol %s rc=0x%08x\n",name,(unsigned)rc);return NULL;}
    return address;
}

enum {QUEUE=512,DEADZONE=24,POLL_US=16000,MOUSE_SAMPLES=16};
enum {VK_BACK=0x08,VK_TAB=0x09,VK_RETURN=0x0d,VK_SHIFT=0x10,VK_CONTROL=0x11,VK_MENU=0x12,VK_CAPITAL=0x14,
      VK_ESCAPE=0x1b,VK_SPACE=0x20,VK_LEFT=0x25,VK_UP=0x26,VK_RIGHT=0x27,VK_DOWN=0x28,VK_LWIN=0x5b};
static const struct {uint32_t button,type,code;} pad_map[]={
    {ORBIS_PAD_BUTTON_CROSS,3,0},{ORBIS_PAD_BUTTON_CIRCLE,3,1},
    {ORBIS_PAD_BUTTON_UP,1,VK_UP},{ORBIS_PAD_BUTTON_DOWN,1,VK_DOWN},
    {ORBIS_PAD_BUTTON_LEFT,1,VK_LEFT},{ORBIS_PAD_BUTTON_RIGHT,1,VK_RIGHT},
    {ORBIS_PAD_BUTTON_TRIANGLE,1,VK_RETURN},{ORBIS_PAD_BUTTON_SQUARE,1,VK_ESCAPE},
    {ORBIS_PAD_BUTTON_OPTIONS,1,VK_LWIN},
};
/* USB HID modifier byte: left ctrl, shift, alt, gui, then the right-hand ones. */
static const uint32_t modifier_vk[8]={VK_CONTROL,VK_SHIFT,VK_MENU,VK_LWIN,VK_CONTROL,VK_SHIFT,VK_MENU,VK_LWIN};
static uint32_t hid_to_vk(unsigned usage)
{
    static const uint8_t punctuation[]={  /* 0x28 .. 0x38 */
        VK_RETURN,VK_ESCAPE,VK_BACK,VK_TAB,VK_SPACE,0xbd,0xbb,0xdb,0xdd,0xdc,0,0xba,0xde,0xc0,0xbc,0xbe,0xbf};
    static const uint8_t navigation[]={  /* 0x49 .. 0x52 */
        0x2d,0x24,0x21,0x2e,0x23,0x22,VK_RIGHT,VK_LEFT,VK_DOWN,VK_UP};
    if(usage>=0x04 && usage<=0x1d) return 'A'+(usage-0x04);
    if(usage>=0x1e && usage<=0x26) return '1'+(usage-0x1e);
    if(usage==0x27) return '0';
    if(usage>=0x28 && usage<=0x38) return punctuation[usage-0x28];
    if(usage==0x39) return VK_CAPITAL;
    if(usage>=0x3a && usage<=0x45) return 0x70+(usage-0x3a);  /* F1-F12 */
    if(usage>=0x49 && usage<=0x52) return navigation[usage-0x49];
    return 0;
}
static pthread_once_t once=PTHREAD_ONCE_INIT;
static pthread_mutex_t lock=PTHREAD_MUTEX_INITIALIZER;
static struct PwWineInput queue[QUEUE];
/* The wheel has its own log budget per source: in W038 key and click events used up the
 * 48 lines before any scroll (W040), and in W040 the mouse used up the 16 before the stick (W041). */
static unsigned head,count,logged,mouse_wheel_logged,pad_wheel_logged;
static int pad=-1,mouse=-1,keyboard=-1,input_user=-1;
static int width=800,height=600;
static volatile int cursor_x,cursor_y,cursor_valid;
static double fx,fy;
extern void pw_hw_cursor_moved(void);
extern int pw_hw_fps_toggle(void);  /* W165: platform/ps4/pw_wine_sink_ps4.c; 0 when the key is not taken */
/* W236: the control overlay (native/hw_overlay.c): 1 while it has the pad */
extern int pw_hw_overlay_pad(const OrbisPadData *data);
/* The Steam client inside the title (native/steam/steam_ui.c, STEAM_UI_HOSTED): its screen takes the pad
 * while open, and "<steam-open>" (C:\orbis\steam-open.exe) opens it (native/steam/steam_client.cpp) */
extern int pw_hw_steam_pad(const OrbisPadData *data);
extern const char *pw_hw_steam_open(void);

static void push(uint32_t type,uint32_t code,uint32_t down,const char *source)
{
    pthread_mutex_lock(&lock);
    if(count<QUEUE) {queue[(head+count++)%QUEUE]=(struct PwWineInput){type,code,cursor_x,cursor_y,down};}
    pthread_mutex_unlock(&lock);
    if(type!=2 && logged<48 && pw_trace_on()) {++logged;fprintf(stderr,"PWBOOT input_event source=%s type=%u code=%u down=%u at=%d,%d\n",
                                               source,type,code,down,cursor_x,cursor_y);}
}
/* Wheel (W038): ps5drv type 4 carries the signed delta in y, in WHEEL_DELTA (120) units,
 * positive away from the user as on Windows. */
static void push_wheel(int delta,const char *source)
{
    pthread_mutex_lock(&lock);
    if(count<QUEUE) {queue[(head+count++)%QUEUE]=(struct PwWineInput){4,0,cursor_x,delta,0};}
    pthread_mutex_unlock(&lock);
    unsigned *wheel_logged=source[0]=='p'?&pad_wheel_logged:&mouse_wheel_logged;
    if(*wheel_logged<16 && pw_trace_on()) {++*wheel_logged;fprintf(stderr,"PWBOOT input_event source=%s type=4 delta=%d at=%d,%d\n",source,delta,cursor_x,cursor_y);}
}
/* W248: relative motion (ps5drv type 5: x and y the delta), for mouse look; the first few are logged */
static void push_relative(int dx,int dy)
{
    static unsigned relative_logged;
    pthread_mutex_lock(&lock);
    if(count<QUEUE) {queue[(head+count++)%QUEUE]=(struct PwWineInput){5,0,dx,dy,0};}
    pthread_mutex_unlock(&lock);
    if(relative_logged<8 && pw_trace_on()) {++relative_logged;fprintf(stderr,"PWPAD rstick mouse dx=%d dy=%d\n",dx,dy);}
}
static int move_by(double dx,double dy)
{
    fx+=dx;fy+=dy;
    if(fx<0) fx=0; if(fy<0) fy=0;
    if(fx>width-1) fx=width-1; if(fy>height-1) fy=height-1;
    if((int)fx==cursor_x && (int)fy==cursor_y) return 0;
    cursor_x=(int)fx;cursor_y=(int)fy;return 1;
}
/* W178 (phase 7): the pad for xinput (tools/build-xinput-hw.py, after prospero-win 0470). This
 * thread stays the pad's only reader and keeps its last state for pw_wine_pad. While any program
 * read it through xinput in the last second (game mode), the sticks and buttons stop driving the
 * pointer and keys, so a game does not also get clicks, arrows, Enter and Escape. The touchpad
 * still moves the pointer (XInput has no touchpad); its click is the game's Back. */
struct PwXinputPad {uint32_t packet;uint16_t buttons;uint8_t left_trigger,right_trigger;
                    int16_t thumb_lx,thumb_ly,thumb_rx,thumb_ry;uint8_t connected;};  /* the overlay's dlls/xinput1_3/unixlib.h */
enum {GAME_MODE_US=1000000};
static pthread_mutex_t pad_state_lock=PTHREAD_MUTEX_INITIALIZER;
static OrbisPadData pad_last;
static uint32_t pad_packet,touch_press_code;
static uint64_t xinput_read_us;
static int game_mode;
static int mouse_off;  /* W236: the overlay turned the pad as mouse off */
static const struct {uint32_t orbis;uint16_t xinput;} xinput_map[]={
    {ORBIS_PAD_BUTTON_UP,0x0001},{ORBIS_PAD_BUTTON_DOWN,0x0002},{ORBIS_PAD_BUTTON_LEFT,0x0004},
    {ORBIS_PAD_BUTTON_RIGHT,0x0008},{ORBIS_PAD_BUTTON_OPTIONS,0x0010},{ORBIS_PAD_BUTTON_TOUCH_PAD,0x0020},
    {ORBIS_PAD_BUTTON_L3,0x0040},{ORBIS_PAD_BUTTON_R3,0x0080},{ORBIS_PAD_BUTTON_L1,0x0100},
    {ORBIS_PAD_BUTTON_R1,0x0200},{ORBIS_PAD_BUTTON_CROSS,0x1000},{ORBIS_PAD_BUTTON_CIRCLE,0x2000},
    {ORBIS_PAD_BUTTON_SQUARE,0x4000},{ORBIS_PAD_BUTTON_TRIANGLE,0x8000}};
/* a stick axis 0..255 as XInput's -32768..32767; XInput's y grows upwards */
static int16_t thumb(uint8_t value,int up)
{
    int scaled=(int)value*257-32768;
    return (int16_t)(up?-1-scaled:scaled);
}
static void start(void);
/* the launcher has a pad; pw_wine_unixlibs.c's weak default says no */
int pw_wine_pad_available(void)
{
    return 1;
}
static int pad_state(struct PwXinputPad *state,int xinput)
{
    pthread_once(&once,start);
    pthread_mutex_lock(&pad_state_lock);
    OrbisPadData data=pad_last;uint32_t packet=pad_packet;
    if(xinput) xinput_read_us=sceKernelGetProcessTime();
    pthread_mutex_unlock(&pad_state_lock);
    memset(state,0,sizeof(*state));
    if(pad<0 || !data.connected) return 0;
    state->packet=packet;state->connected=1;
    for(unsigned i=0;i<sizeof(xinput_map)/sizeof(xinput_map[0]);i++)
        if(data.buttons&xinput_map[i].orbis) state->buttons|=xinput_map[i].xinput;
    state->left_trigger=data.analogButtons.l2;state->right_trigger=data.analogButtons.r2;
    state->thumb_lx=thumb(data.leftStick.x,0);state->thumb_ly=thumb(data.leftStick.y,1);
    state->thumb_rx=thumb(data.rightStick.x,0);state->thumb_ry=thumb(data.rightStick.y,1);
    return 1;
}
int pw_wine_pad(struct PwXinputPad *state)
{
    return pad_state(state,1);
}
/* HID stack (tools/build-hidstack-hw.py): winebus's pad bus reads the state every 8 ms whether or
 * not a game listens, so its reads do not count for game mode; a game that pairs the HID gamepad
 * with XInput (Unity, SDL) turns game mode on through pw_wine_pad. */
int pw_wine_pad_peek(struct PwXinputPad *state)
{
    return pad_state(state,0);
}
void pw_wine_set_rumble(uint32_t left,uint32_t right)
{
    /* XInput's left motor is the large one */
    OrbisPadVibeParam vibe={(uint8_t)(left>>8),(uint8_t)(right>>8)};
    static int logged;
    int rc=pad>=0?scePadSetVibration(pad,&vibe):-1;
    if(rc && logged<4) {++logged;fprintf(stderr,"PWPAD rumble_failed rc=0x%08x handle=%d\n",(unsigned)rc,pad);}
}

/* W181: key profiles. SuperMarioKart (Blitz3D) reads only the keyboard: it enumerates joysticks once
 * at start (one xinput read, then game mode ends) and the stick went on moving the pointer, while
 * Square sent Escape, which quits it. A profile names a key per button and per direction of the left
 * stick, read as digital past a threshold; buttons it does not name do nothing, the right stick does
 * not scroll, and the touchpad stays the pointer (its click too, unless the profile names it).
 * Lines are "source = key", "#" or ";" start a comment; "stick = mouse" keeps the stick as pointer. */
enum {STICK_UP=1,STICK_DOWN=2,STICK_LEFT=4,STICK_RIGHT=8,STICK_THRESHOLD=64,PROFILE_KEYS=32};
static struct {uint32_t button,stick,vk;} profile_keys[PROFILE_KEYS];
static unsigned profile_count;
static int profile_active,profile_stick_mouse,profile_touchpad;
static uint32_t stick_keys_down;
/* W182: sources holding each key. In W181 two sources on one key (cross and the stick up, both
 * VK_UP in SMK's profile) sent their own up: letting go of one released the key while the other
 * still held it, and the kart stopped accelerating. A key goes down with its first source and up
 * with its last. */
static uint8_t profile_held[256];
static char profile_name[96];  /* W213: the program whose profile is active */
/* W248: "rstick = mouse": the right stick as relative mouse motion, also in game mode */
enum {RSTICK_SPEED=900};
static int rstick_mouse,rstick_speed=RSTICK_SPEED,rstick_deadzone=DEADZONE;
static double rstick_fx,rstick_fy;
static int profile_key(uint32_t vk,int down)
{
    if(down? profile_held[vk&0xff]++ : (!profile_held[vk&0xff] || --profile_held[vk&0xff])) return 0;
    push(1,vk,down,"profile");return 1;
}
static const struct {const char *name;uint32_t button,stick;} profile_sources[]={
    {"cross",ORBIS_PAD_BUTTON_CROSS,0},{"circle",ORBIS_PAD_BUTTON_CIRCLE,0},{"square",ORBIS_PAD_BUTTON_SQUARE,0},
    {"triangle",ORBIS_PAD_BUTTON_TRIANGLE,0},{"l1",ORBIS_PAD_BUTTON_L1,0},{"r1",ORBIS_PAD_BUTTON_R1,0},
    {"l2",ORBIS_PAD_BUTTON_L2,0},{"r2",ORBIS_PAD_BUTTON_R2,0},{"l3",ORBIS_PAD_BUTTON_L3,0},{"r3",ORBIS_PAD_BUTTON_R3,0},
    {"options",ORBIS_PAD_BUTTON_OPTIONS,0},{"touchpad",ORBIS_PAD_BUTTON_TOUCH_PAD,0},
    {"up",ORBIS_PAD_BUTTON_UP,0},{"down",ORBIS_PAD_BUTTON_DOWN,0},{"left",ORBIS_PAD_BUTTON_LEFT,0},
    {"right",ORBIS_PAD_BUTTON_RIGHT,0},{"stick_up",0,STICK_UP},{"stick_down",0,STICK_DOWN},
    {"stick_left",0,STICK_LEFT},{"stick_right",0,STICK_RIGHT}};
static uint32_t profile_vk(const char *name)
{
    static const struct {const char *name;uint32_t vk;} keys[]={
        {"up",VK_UP},{"down",VK_DOWN},{"left",VK_LEFT},{"right",VK_RIGHT},{"space",VK_SPACE},{"enter",VK_RETURN},
        {"escape",VK_ESCAPE},{"tab",VK_TAB},{"backspace",VK_BACK},{"shift",VK_SHIFT},{"ctrl",VK_CONTROL},
        {"alt",VK_MENU},{"home",0x24},{"end",0x23},{"pageup",0x21},{"pagedown",0x22},{"insert",0x2d},{"delete",0x2e}};
    for(unsigned i=0;i<sizeof(keys)/sizeof(keys[0]);i++) if(!strcasecmp(name,keys[i].name)) return keys[i].vk;
    if(strlen(name)==1 && ((name[0]|0x20)>='a' && (name[0]|0x20)<='z')) return (uint32_t)((name[0]|0x20)-'a'+'A');
    if(strlen(name)==1 && name[0]>='0' && name[0]<='9') return (uint32_t)name[0];
    if((name[0]=='f' || name[0]=='F') && atoi(name+1)>=1 && atoi(name+1)<=12) return 0x6f+(uint32_t)atoi(name+1);
    return 0;
}
/* the launcher (native/wine_hardware.c) names the program it runs, by its Windows path, before
 * the input thread starts */
void pw_hw_pad_profile(const char *exe)
{
    const char *base=exe;
    for(const char *at=exe;at && *at;at++) if(*at=='\\' || *at=='/') base=at+1;
    char file[256],line[160];
    snprintf(file,sizeof(file),"/data/wine-prefix/drive_c/orbis/padmaps/%s.ini",base?base:"");
    FILE *ini=fopen(file,"r");
    if(!ini) {fprintf(stderr,"PWPAD profile=%s none errno=%d\n",base?base:"-",errno);return;}
    int stick_set=0;
    while(fgets(line,sizeof(line),ini)) {
        char source[32],key[32];
        if(line[0]=='#' || line[0]==';' || sscanf(line," %31[^= \t] = %31s",source,key)!=2) continue;
        if(!strcasecmp(source,"stick")) {profile_stick_mouse=!strcasecmp(key,"mouse");stick_set=1;continue;}
        /* W248: the right stick as mouse look */
        if(!strcasecmp(source,"rstick")) {
            if(!strcasecmp(key,"mouse")) rstick_mouse=1; else fprintf(stderr,"PWPAD profile_line_ignored %s",line);
            continue;
        }
        if(!strcasecmp(source,"rstick_speed") || !strcasecmp(source,"rstick_deadzone")) {
            int value=atoi(key),speed=!strcasecmp(source,"rstick_speed");
            if(speed && value>0 && value<=5000) rstick_speed=value;
            else if(!speed && value>=0 && value<=100) rstick_deadzone=value;
            else fprintf(stderr,"PWPAD profile_line_ignored %s",line);
            continue;
        }
        uint32_t vk=profile_vk(key);unsigned i;
        for(i=0;i<sizeof(profile_sources)/sizeof(profile_sources[0]);i++) if(!strcasecmp(source,profile_sources[i].name)) break;
        if(!vk || i==sizeof(profile_sources)/sizeof(profile_sources[0]) || profile_count==PROFILE_KEYS) {
            fprintf(stderr,"PWPAD profile_line_ignored %s",line);continue;
        }
        profile_keys[profile_count].button=profile_sources[i].button;profile_keys[profile_count].stick=profile_sources[i].stick;
        profile_keys[profile_count++].vk=vk;
        if(profile_sources[i].button==ORBIS_PAD_BUTTON_TOUCH_PAD) profile_touchpad=1;
    }
    fclose(ini);
    /* the stick sends the arrows unless the profile names other keys for it or keeps it as pointer */
    static const struct {uint32_t stick,vk;} arrows[]={{STICK_UP,VK_UP},{STICK_DOWN,VK_DOWN},{STICK_LEFT,VK_LEFT},{STICK_RIGHT,VK_RIGHT}};
    /* W248: only for a key profile: one with only rstick lines leaves the emulation as it is */
    for(unsigned a=0;!profile_stick_mouse && (profile_count || stick_set) && a<4 && profile_count<PROFILE_KEYS;a++) {
        unsigned i;
        for(i=0;i<profile_count;i++) if(profile_keys[i].stick==arrows[a].stick) break;
        if(i==profile_count) {profile_keys[profile_count].button=0;profile_keys[profile_count].stick=arrows[a].stick;profile_keys[profile_count++].vk=arrows[a].vk;}
    }
    profile_active=profile_count>0 || stick_set;
    if(profile_active || rstick_mouse) snprintf(profile_name,sizeof(profile_name),"%s",base);
    fprintf(stderr,"PWPAD profile=%s keys=%u stick=%s rstick=%s speed=%d deadzone=%d\n",base,profile_count,
            profile_stick_mouse?"mouse":"keys",rstick_mouse?"mouse":"-",rstick_speed,rstick_deadzone);
}

/* W213: profiles for guests. A 64-bit program runs as a guest in this process, so the profile of
 * W181 (read once when the title starts a program on its own) never applied to it. kernelbase's
 * guest launch and exit reach pw_wine_pad_profile through xinput's Unix library; the pad thread
 * applies the request (poll_input), so the profile never changes under poll_controller. A guest
 * without a profile file leaves the active one (The Lost Forest starts UnityCrashHandler64.exe as
 * another guest); a guest's exit clears only its own profile. */
static pthread_mutex_t profile_request_lock=PTHREAD_MUTEX_INITIALIZER;
static char profile_request[96];
static int profile_request_kind;  /* 0 none, 1 load, 2 clear */
/* W238: kernelbase's overlay closer reports MangoHud through this call ("<mangohud>", which no file
 * name can be): native/hw_overlay.c */
extern void pw_hw_overlay_mangohud(int loaded);
/* W261: and whether the desktop is in front ("<overlay-desktop>") */
extern void pw_hw_overlay_desktop(int in_front);
/* W239: and polls Salir's request: the answer goes back in the call's own buffer (xinput's
 * xinput_profile_params.exe, 260 bytes, which the caller reads after the call) */
extern int pw_hw_overlay_exit_poll(void);
extern void pw_hw_overlay_exit_result(const char *result);
/* W261: and which program the overlay's cursor mode is for */
extern void pw_hw_overlay_program(const char *exe,int load);
void pw_wine_pad_profile(const char *exe,int load)
{
    /* Steam: the answer ("opened", "busy" or "error ...") goes back in the call's 260-byte buffer */
    if(exe && !strcmp(exe,"<steam-open>")) {snprintf((char *)exe,260,"%s",pw_hw_steam_open());return;}
    if(exe && !strcmp(exe,"<mangohud>")) {pw_hw_overlay_mangohud(load);return;}
    /* W292: explorer's "Reset as Root" / "Reset as Sandbox": the mode chosen at start, and the relaunch
     * into the other one, which answers only when it failed (native/wine_hardware.c) */
    if(exe && !strcmp(exe,"<root-mode>")) {
        extern int pw_hw_boot_root(void) __attribute__((weak));
        snprintf((char *)exe,260,"%s",!pw_hw_boot_root?"error: unavailable":pw_hw_boot_root()?"root":"normal");
        return;
    }
    if(exe && (!strcmp(exe,"<reset-root>") || !strcmp(exe,"<reset-sandbox>"))) {
        extern const char *pw_hw_reset_mode(int root) __attribute__((weak));
        int root=!strcmp(exe,"<reset-root>");
        fprintf(stderr,"PWROOT request reset to=%s\n",root?"root":"normal");
        snprintf((char *)exe,260,"%s",pw_hw_reset_mode?pw_hw_reset_mode(root):"error: unavailable");
        fprintf(stderr,"PWROOT request reply=%s\n",exe);
        return;
    }
    if(exe && !strcmp(exe,"<overlay-desktop>")) {pw_hw_overlay_desktop(load);return;}
    /* W242: "exit" or "-", then the windows Vulkan presented to in the last 2 s, in hex (the closer
     * counts MangoHud only for the one in front) */
    if(exe && !strcmp(exe,"<overlay-poll>")) {
        extern int pw_hw_sink_vk_windows(unsigned long long *out,int max);
        unsigned long long windows[4];
        int n=pw_hw_sink_vk_windows(windows,4),at;
        char *reply=(char *)exe;  /* xinput_profile_params.exe: 260 bytes */
        at=snprintf(reply,260,"%s",pw_hw_overlay_exit_poll()?"exit":"-");
        for(int i=0;i<n && at>0 && at<200;i++) at+=snprintf(reply+at,(size_t)(260-at)," %llx",windows[i]);
        return;
    }
    /* W287: and GRAFICOS (native/hw_overlay.c): the request goes back in the call's buffer, the result comes as text */
    if(exe && !strcmp(exe,"<overlay-render-poll>")) {
        extern void pw_hw_overlay_render_poll(char *reply,size_t size);
        pw_hw_overlay_render_poll((char *)exe,260);  /* xinput_profile_params.exe: 260 bytes */
        return;
    }
    if(exe && !strncmp(exe,"<overlay-render-result>",23)) {
        extern void pw_hw_overlay_render_result(const char *result);
        pw_hw_overlay_render_result(exe+23);
        return;
    }
    if(exe && !strncmp(exe,"<overlay-result>",16)) {pw_hw_overlay_exit_result(exe+16);return;}
    const char *base=exe;
    for(const char *at=exe;at && *at;at++) if(*at=='\\' || *at=='/') base=at+1;
    pw_hw_overlay_program(base,load);
    pthread_mutex_lock(&profile_request_lock);
    snprintf(profile_request,sizeof(profile_request),"%s",base?base:"");
    profile_request_kind=load?1:2;
    pthread_mutex_unlock(&profile_request_lock);
}
static void profile_reset(uint32_t *previous)
{
    for(unsigned vk=0;vk<256;vk++) if(profile_held[vk]) {profile_held[vk]=0;push(1,vk,0,"profile");}
    /* and what the emulation held when a profile takes over */
    for(unsigned i=0;i<sizeof(pad_map)/sizeof(pad_map[0]);i++)
        if(*previous&pad_map[i].button) push(pad_map[i].type,pad_map[i].code,0,"pad");
    *previous=0;
    stick_keys_down=0;profile_count=0;profile_active=0;profile_stick_mouse=0;profile_touchpad=0;profile_name[0]=0;
    rstick_mouse=0;rstick_speed=RSTICK_SPEED;rstick_deadzone=DEADZONE;rstick_fx=rstick_fy=0;  /* W248 */
}
static void profile_apply_request(uint32_t *previous)
{
    char name[96],file[256];int kind;
    pthread_mutex_lock(&profile_request_lock);
    kind=profile_request_kind;profile_request_kind=0;
    snprintf(name,sizeof(name),"%s",profile_request);
    pthread_mutex_unlock(&profile_request_lock);
    if(kind==1) {
        snprintf(file,sizeof(file),"/data/wine-prefix/drive_c/orbis/padmaps/%s.ini",name);
        FILE *ini=fopen(file,"r");
        if(!ini) {fprintf(stderr,"PWPAD guest profile=%s none, keeps %s\n",name,profile_name[0]?profile_name:"-");return;}
        fclose(ini);
        profile_reset(previous);
        pw_hw_pad_profile(name);
    } else if(kind==2 && profile_name[0] && !strcasecmp(name,profile_name)) {
        profile_reset(previous);
        fprintf(stderr,"PWPAD guest profile=%s cleared\n",name);
    }
}

static int poll_controller(unsigned reads,uint32_t *previous,int *moved)
{
    OrbisPadData data;memset(&data,0,sizeof(data));
    int rc=scePadReadState(pad,&data);
    /* a failing read is recorded now and then; the input path itself is proven (W035-W037) */
    if(rc && reads%625==1) fprintf(stderr,"PWBOOT pad_read_failed n=%u rc=0x%08x\n",reads,(unsigned)rc);
    if(rc) return 0;
    /* W236: while the overlay has the pad (L3+R3), programs and the emulation read it neutral: connected,
     * nothing pressed, sticks centred, no finger. What they held is released below, as on any release. */
    if(pw_hw_overlay_pad(&data) || pw_hw_steam_pad(&data)) {
        data.buttons=0;data.leftStick.x=data.leftStick.y=data.rightStick.x=data.rightStick.y=128;
        data.analogButtons.l2=data.analogButtons.r2=0;data.touch.fingers=0;
    }
    /* W178: the state xinput reads; a new packet number whenever an input changed */
    pthread_mutex_lock(&pad_state_lock);
    if(pad_last.buttons!=data.buttons || pad_last.connected!=data.connected ||
       memcmp(&pad_last.leftStick,&data.leftStick,sizeof(data.leftStick)) ||
       memcmp(&pad_last.rightStick,&data.rightStick,sizeof(data.rightStick)) ||
       memcmp(&pad_last.analogButtons,&data.analogButtons,sizeof(data.analogButtons))) ++pad_packet;
    pad_last=data;
    uint64_t read_us=xinput_read_us;
    pthread_mutex_unlock(&pad_state_lock);
    int gaming=read_us && sceKernelGetProcessTime()-read_us<GAME_MODE_US,changed=0;
    if(gaming!=game_mode) {
        game_mode=gaming;
        fprintf(stderr,"PWPAD game_mode=%d\n",gaming);
        /* what the emulation holds is released, or it would stay down during the game */
        for(unsigned i=0;gaming && i<sizeof(pad_map)/sizeof(pad_map[0]);i++)
            if(*previous&pad_map[i].button) {push(pad_map[i].type,pad_map[i].code,0,"pad");changed=1;}
        if(gaming && (*previous&ORBIS_PAD_BUTTON_TOUCH_PAD)) {push(3,touch_press_code,0,"touchpad");changed=1;}
        /* W181: and the profile's keys */
        for(unsigned vk=0;gaming && vk<256;vk++)
            if(profile_held[vk]) {profile_held[vk]=0;push(1,vk,0,"profile");changed=1;}
        if(gaming) stick_keys_down=0;
    }
    int dx=(int)data.leftStick.x-128,dy=(int)data.leftStick.y-128;
    /* quadratic response: fine aim near the centre, fast at full tilt */
    if(!game_mode && !mouse_off && !(profile_active && !profile_stick_mouse) && (abs(dx)>DEADZONE || abs(dy)>DEADZONE))
        if(move_by(abs(dx)>DEADZONE?(double)dx*abs(dx)/1400.0:0,abs(dy)>DEADZONE?(double)dy*abs(dy)/1400.0:0)) *moved=1;
    /* W181: a profile's stick keys, on each change of direction */
    if(profile_active && !profile_stick_mouse && !game_mode) {
        uint32_t stick=(dy<-STICK_THRESHOLD?STICK_UP:0)|(dy>STICK_THRESHOLD?STICK_DOWN:0)|
                       (dx<-STICK_THRESHOLD?STICK_LEFT:0)|(dx>STICK_THRESHOLD?STICK_RIGHT:0);
        for(unsigned i=0;i<profile_count;i++) {
            uint32_t now=stick&profile_keys[i].stick,before=stick_keys_down&profile_keys[i].stick;
            if(profile_keys[i].stick && now!=before && profile_key(profile_keys[i].vk,now!=0)) changed=1;
        }
        stick_keys_down=stick;
    }
    /* touchpad (W037): the first finger moves the pointer relatively, like a laptop
     * trackpad; the pad reports about 1920x943 touch units across its surface */
    static int touching,last_finger,last_tx,last_ty;
    if(data.touch.fingers>0) {
        int finger=data.touch.touch[0].finger,tx=data.touch.touch[0].x,ty=data.touch.touch[0].y;
        if(touching && finger==last_finger && !mouse_off && move_by((tx-last_tx)*0.75,(ty-last_ty)*0.75)) *moved=1;
        touching=1;last_finger=finger;last_tx=tx;last_ty=ty;
    } else touching=0;
    /* right stick (W038): vertical tilt scrolls; one notch per 120 accumulated units,
     * faster at full tilt; up scrolls up */
    static double scroll;
    int ry=(int)data.rightStick.y-128;
    /* W042: in W041 the right stick never left the dead zone on y; record any movement of
     * either axis, with the first 16 bytes of the report, to see where it lands */
    static int stick_logged;
    if((abs(ry)>DEADZONE || abs((int)data.rightStick.x-128)>DEADZONE) && stick_logged<8 && pw_trace_on()) {
        const uint8_t *raw=(const uint8_t *)&data;++stick_logged;
        fprintf(stderr,"PWBOOT right_stick x=%u y=%u raw=",data.rightStick.x,data.rightStick.y);
        for(int i=0;i<16;i++) fprintf(stderr,"%02x",raw[i]);
        fprintf(stderr,"\n");
    }
    /* W248: a profile's right stick as mouse look, in game mode too (VC reads the pad through DirectInput and
     * turns its camera with the mouse): relative motion, quadratic past the dead zone up to rstick_speed pixels
     * a second at full tilt; the remainder carries to the next read. Off with the overlay's Mouse off. */
    if(rstick_mouse && !mouse_off) {
        int axes[2]={(int)data.rightStick.x-128,ry};
        double *carry[2]={&rstick_fx,&rstick_fy},range=128.0-rstick_deadzone;
        int delta[2];
        for(int a=0;a<2;a++) {
            int tilt=abs(axes[a]);
            double v=tilt>rstick_deadzone?(tilt-rstick_deadzone)/range:0;
            if(v>1) v=1;
            *carry[a]+=(axes[a]<0?-1:1)*v*v*rstick_speed*(POLL_US/1e6);
            delta[a]=(int)*carry[a];*carry[a]-=delta[a];
        }
        if(delta[0] || delta[1]) {
            push_relative(delta[0],delta[1]);changed=1;
            if(move_by(delta[0],delta[1])) pw_hw_cursor_moved();  /* the sink's arrow follows */
        }
    } else rstick_fx=rstick_fy=0;
    if(!game_mode && !profile_active && !mouse_off && !rstick_mouse && abs(ry)>DEADZONE) {
        scroll+=-(double)ry*abs(ry)/160.0;
        while(scroll>=120) {push_wheel(120,"pad");scroll-=120;changed=1;}
        while(scroll<=-120) {push_wheel(-120,"pad");scroll+=120;changed=1;}
    } else scroll=0;
    for(unsigned i=0;i<sizeof(pad_map)/sizeof(pad_map[0]);i++) {
        uint32_t now=data.buttons&pad_map[i].button,before=*previous&pad_map[i].button;
        if(now!=before && !game_mode && !profile_active && !(mouse_off && pad_map[i].type==3)) {push(pad_map[i].type,pad_map[i].code,now!=0,"pad");changed=1;}
    }
    /* W181: a profile's button keys instead */
    for(unsigned i=0;profile_active && !game_mode && i<profile_count;i++) {
        uint32_t now=data.buttons&profile_keys[i].button,before=*previous&profile_keys[i].button;
        if(profile_keys[i].button && now!=before && profile_key(profile_keys[i].vk,now!=0)) changed=1;
    }
    /* touchpad buttons (W038), as on a laptop: a press with two fingers is the right
     * button, with one the left; a short two-finger tap without pressing is a right click */
    uint32_t now=data.buttons&ORBIS_PAD_BUTTON_TOUCH_PAD,before=*previous&ORBIS_PAD_BUTTON_TOUCH_PAD;
    if(now && !before && !game_mode && !profile_touchpad && !mouse_off) {touch_press_code=data.touch.fingers>=2?1:0;push(3,touch_press_code,1,"touchpad");changed=1;}
    if(!now && before && !game_mode && !profile_touchpad && !mouse_off) {push(3,touch_press_code,0,"touchpad");changed=1;}
    static int tap_fingers,tap_x,tap_y,tap_moved,tap_pressed;static uint64_t tap_start;
    uint64_t now_us=sceKernelGetProcessTime();
    if(data.touch.fingers>=2) {
        if(tap_fingers<2) {tap_start=now_us;tap_x=data.touch.touch[0].x;tap_y=data.touch.touch[0].y;tap_moved=0;tap_pressed=0;}
        if(abs(data.touch.touch[0].x-tap_x)>40 || abs(data.touch.touch[0].y-tap_y)>40) tap_moved=1;
        if(now) tap_pressed=1;
    } else if(!game_mode && !mouse_off && !data.touch.fingers && tap_fingers>=2 && !tap_moved && !tap_pressed && now_us-tap_start<300000) {
        push(3,1,1,"touchpad");push(3,1,0,"touchpad");changed=1;
    }
    if(data.touch.fingers>=2 || !data.touch.fingers) tap_fingers=data.touch.fingers;
    *previous=data.buttons;
    return changed;
}
static int poll_mouse(uint32_t *previous,int *moved)
{
    PwMouseData samples[MOUSE_SAMPLES];memset(samples,0,sizeof(samples));
    int got=mouse_read(mouse,samples,MOUSE_SAMPLES),changed=0;
    for(int i=0;i<got && i<MOUSE_SAMPLES;i++) {
        if(!samples[i].connected) continue;
        if((samples[i].x || samples[i].y) && move_by(samples[i].x,samples[i].y)) *moved=1;
        /* one wheel notch per unit; the sign follows the device, checked on hardware */
        if(samples[i].wheel) {
            if(*moved) {push(2,0,0,"mouse");*moved=0;}
            push_wheel(samples[i].wheel*120,"mouse");changed=1;
        }
        for(uint32_t b=0;b<3;b++) {
            uint32_t now=samples[i].buttons&(1u<<b),before=*previous&(1u<<b);
            if(now!=before) {
                if(*moved) {push(2,0,0,"mouse");*moved=0;}  /* the click lands where the pointer is */
                push(3,b,now!=0,"mouse");changed=1;
            }
        }
        *previous=samples[i].buttons;
    }
    return changed;
}
static int poll_keyboard(uint16_t *held,unsigned *held_count,uint32_t *mods)
{
    OrbisKeyboardData data;memset(&data,0,sizeof(data));
    if(keyboard_read(keyboard,&data)) return 0;
    int changed=0;unsigned n=data.nkeys>32?32:(unsigned)data.nkeys;
    for(unsigned bit=0;bit<8;bit++) {
        uint32_t now=data.mods&(1u<<bit),before=*mods&(1u<<bit);
        if(now!=before) {push(1,modifier_vk[bit],now!=0,"keyboard");changed=1;}
    }
    *mods=data.mods;
    /* W165: F12 (HID 0x45) shows or hides the sink's frame counter, as MangoHud's toggle, and
     * programs do not see it. W166: only while a Vulkan program presents (the sink says whether it
     * took the key); otherwise F12 goes to the programs, press and release. */
    enum {HID_F12=0x45};
    static int f12_taken;
    for(unsigned i=0;i<*held_count;i++) {  /* released */
        unsigned j=0;while(j<n && data.keycodes[j]!=held[i]) ++j;
        uint32_t vk=hid_to_vk(held[i]);
        if(j==n && held[i]==HID_F12 && f12_taken) {f12_taken=0;continue;}
        if(j==n && vk) {push(1,vk,0,"keyboard");changed=1;}
    }
    for(unsigned j=0;j<n;j++) {  /* pressed */
        unsigned i=0;while(i<*held_count && held[i]!=data.keycodes[j]) ++i;
        uint32_t vk=hid_to_vk(data.keycodes[j]);
        if(i==*held_count && data.keycodes[j]==HID_F12 && pw_hw_fps_toggle()) f12_taken=1;
        else if(i==*held_count && vk) {push(1,vk,1,"keyboard");changed=1;}
    }
    memcpy(held,data.keycodes,n*sizeof(*held));*held_count=n;
    return changed;
}
/* Mouse and keyboard, opened by the input thread on its first poll (W031 showed that
 * loading these modules does not disturb the controller). */
static void open_usb_devices(void)
{
    /* merged: every connected mouse feeds the one handle */
    int module=load_library("libSceMouse.sprx",ORBIS_SYSMODULE_MOUSE,0);
    mouse_init=symbol(module,"sceMouseInit");mouse_open=symbol(module,"sceMouseOpen");mouse_read=symbol(module,"sceMouseRead");
    if(mouse_init && mouse_open && mouse_read) {
        PwMouseOpenParam merged={1,{0}};
        int rc_mouse_init=mouse_init();
        mouse=mouse_open(input_user,0,0,&merged);
        fprintf(stderr,"PWBOOT mouse_open init=0x%08x handle=0x%08x\n",(unsigned)rc_mouse_init,(unsigned)mouse);
    }
    module=load_library("libSceKeyboard.sprx",ORBIS_SYSMODULE_KEYBOARD,0);
    if(module<0) module=load_library("libSceKeyboard.sprx",ORBIS_SYSMODULE_INTERNAL_KEYBOARD,1);
    keyboard_init=symbol(module,"sceKeyboardInit");keyboard_open=symbol(module,"sceKeyboardOpen");
    keyboard_read=symbol(module,"sceKeyboardReadState");
    if(keyboard_init && keyboard_open && keyboard_read) {
        int rc_keyboard_init=keyboard_init();
        keyboard=keyboard_open(input_user,0,0,NULL);
        fprintf(stderr,"PWBOOT keyboard_open init=0x%08x handle=0x%08x\n",(unsigned)rc_keyboard_init,(unsigned)keyboard);
    }
}
/* W059: one wake socket pair per Wine thread. All threads used to register dups of a
 * single socket with the in-process server, which turns a queue's polling off after each
 * event until its thread waits again; on hardware that silenced the other threads' copies
 * too, and a window drag got its pointer moves in bursts with 1-4 s gaps (W057). The
 * input thread now writes to every thread's own socket. */
enum {WAKE_SLOTS=256};
static struct {pthread_t thread;int read,write;} wakes[WAKE_SLOTS];
static unsigned wake_count;
static pthread_mutex_t wake_lock=PTHREAD_MUTEX_INITIALIZER;
static void wake_all(void)
{
    char byte=1;
    pthread_mutex_lock(&wake_lock);
    for(unsigned i=0;i<wake_count;i++) send(wakes[i].write,&byte,1,MSG_DONTWAIT);
    pthread_mutex_unlock(&wake_lock);
}
/* W236: the overlay's keys (on-screen keyboard, Salir's F24) go to the focused window as the USB
 * keyboard's do. Not logged: they may be a password. */
void pw_hw_pad_key(uint32_t vk,int down);
void pw_hw_pad_key(uint32_t vk,int down)
{
    pthread_mutex_lock(&lock);
    if(count<QUEUE) {queue[(head+count++)%QUEUE]=(struct PwWineInput){1,vk,cursor_x,cursor_y,(uint32_t)(down!=0)};}
    pthread_mutex_unlock(&lock);
    wake_all();
}
/* W236: the overlay's Mouse entry; called on this thread (poll_controller), as mouse_off is read */
void pw_hw_pad_set_mouse(int on);
void pw_hw_pad_set_mouse(int on)
{
    mouse_off=!on;
    fprintf(stderr,"PWPAD mouse=%s\n",on?"on":"off");
}
/* W236: the pad as a DualSense's USB input report 1 (64 bytes), for winebus's DualSense device
 * (native/winebus_orbis.c) when the overlay's controller type is DualSense. It reads the state xinput
 * reads (neutral while the overlay is open) and, like pw_wine_pad_peek, does not count for game mode.
 * The PS4 pad gives no Create, PS or mute button to a title; gyro and accelerometer are left at zero
 * (not converted); the touchpad's 1920x943 units are scaled to the DualSense's 1920x1080; the battery
 * reads as wired and full, as xinput's does. The counter (byte 7) and timestamp (49-52) are winebus's.
 * 0 when there is no pad. */
int pw_wine_pad_dualsense(uint8_t *report);
int pw_wine_pad_dualsense(uint8_t *report)
{
    static const uint8_t hat[16]={8,0,4,8,6,7,5,6,2,1,3,2,8,0,4,8};  /* up|down<<1|left<<2|right<<3 */
    OrbisPadData data;
    pthread_once(&once,start);
    pthread_mutex_lock(&pad_state_lock);
    data=pad_last;
    pthread_mutex_unlock(&pad_state_lock);
    memset(report,0,64);
    if(pad<0 || !data.connected) return 0;
    uint32_t b=data.buttons;
    unsigned dir=(b&ORBIS_PAD_BUTTON_UP?1:0)|(b&ORBIS_PAD_BUTTON_DOWN?2:0)|(b&ORBIS_PAD_BUTTON_LEFT?4:0)|(b&ORBIS_PAD_BUTTON_RIGHT?8:0);
    report[0]=0x01;
    report[1]=data.leftStick.x;report[2]=data.leftStick.y;report[3]=data.rightStick.x;report[4]=data.rightStick.y;
    report[5]=data.analogButtons.l2;report[6]=data.analogButtons.r2;
    report[8]=hat[dir]|(b&ORBIS_PAD_BUTTON_SQUARE?0x10:0)|(b&ORBIS_PAD_BUTTON_CROSS?0x20:0)|
              (b&ORBIS_PAD_BUTTON_CIRCLE?0x40:0)|(b&ORBIS_PAD_BUTTON_TRIANGLE?0x80:0);
    report[9]=(b&ORBIS_PAD_BUTTON_L1?0x01:0)|(b&ORBIS_PAD_BUTTON_R1?0x02:0)|(b&ORBIS_PAD_BUTTON_L2?0x04:0)|
              (b&ORBIS_PAD_BUTTON_R2?0x08:0)|(b&ORBIS_PAD_BUTTON_OPTIONS?0x20:0)|(b&ORBIS_PAD_BUTTON_L3?0x40:0)|
              (b&ORBIS_PAD_BUTTON_R3?0x80:0);
    report[10]=b&ORBIS_PAD_BUTTON_TOUCH_PAD?0x02:0;
    for(unsigned i=0;i<2;i++) {
        uint8_t *at=report+33+4*i;
        if(i>=data.touch.fingers) {at[0]=0x80;continue;}
        unsigned x=data.touch.touch[i].x,y=data.touch.touch[i].y*1080u/943u;
        if(x>1919) x=1919;
        if(y>1079) y=1079;
        at[0]=data.touch.touch[i].finger&0x7f;
        at[1]=(uint8_t)x;at[2]=(uint8_t)(((x>>8)&0x0f)|((y&0x0f)<<4));at[3]=(uint8_t)(y>>4);
    }
    report[53]=0x2a;  /* charging complete, level 10 of 10 */
    return 1;
}
/* W236: the DualSense's light bar (output report 2) on the PS4 pad's */
void pw_wine_set_lightbar(unsigned int r,unsigned int g,unsigned int b);
void pw_wine_set_lightbar(unsigned int r,unsigned int g,unsigned int b)
{
    OrbisPadColor color={(uint8_t)r,(uint8_t)g,(uint8_t)b,255};
    static int logged;
    int rc=pad>=0?scePadSetLightBar(pad,&color):-1;
    if(rc && logged<4) {++logged;fprintf(stderr,"PWPAD lightbar_failed rc=0x%08x handle=%d\n",(unsigned)rc,pad);}
}
static void *poll_input(void *unused)
{
    (void)unused;
    uint32_t pad_buttons=0,mouse_buttons=0,mods=0;uint16_t held[32];unsigned held_count=0,reads=0;
    for(;;) {
        int moved=0,changed=0;
        ++reads;
        /* W031 showed the USB modules do not disturb the controller: open them at once. */
        if(reads==1) open_usb_devices();
        if(profile_request_kind) profile_apply_request(&pad_buttons);  /* W213: guest profiles */
        if(pad>=0) changed|=poll_controller(reads,&pad_buttons,&moved);
        if(mouse>=0) changed|=poll_mouse(&mouse_buttons,&moved);
        if(keyboard>=0) changed|=poll_keyboard(held,&held_count,&mods);
        if(moved) {push(2,0,0,"pointer");pw_hw_cursor_moved();}
        if(moved || changed) wake_all();
        sceKernelUsleep(POLL_US);
    }
    return NULL;
}
/* Phase 10: the pad is opened once, by the launcher's boot choice (native/wine_hardware.c reads it
 * before Wine starts; the title has no scePadClose to give a handle back) or by start() */
static pthread_once_t pad_once=PTHREAD_ONCE_INIT;
static int pad_user=-1;
static void open_pad(void)
{
    int rc_service=sceUserServiceInitialize(NULL);
    int rc_user=sceUserServiceGetInitialUser(&pad_user);
    int rc_init=scePadInit();
    pad=scePadOpen(pad_user,0,0,NULL);
    fprintf(stderr,"PWBOOT pad_open service=0x%08x user_rc=0x%08x user=%d init=0x%08x handle=0x%08x\n",
            (unsigned)rc_service,(unsigned)rc_user,pad_user,(unsigned)rc_init,(unsigned)pad);
}
int pw_hw_pad_handle(void)
{
    pthread_once(&pad_once,open_pad);
    return pad;
}
static void start(void)
{
    const char *size=getenv("WINE_PS5_DESKTOP");unsigned w,h;
    if(size && sscanf(size,"%ux%u",&w,&h)==2 && w>=320 && h>=200 && w<=3840 && h<=2160) {width=(int)w;height=(int)h;}
    cursor_x=width/2;cursor_y=height/2;fx=cursor_x;fy=cursor_y;
    pw_hw_pad_handle();
    input_user=pad_user;
    cursor_valid=1;
    pthread_t thread;int rc=pthread_create(&thread,NULL,poll_input,NULL);
    fprintf(stderr,"PWBOOT input_thread rc=%d\n",rc);
}
int pw_wine_next_input(struct PwWineInput *event)
{
    /* win32u's first request is recorded: before W035 it never came (QS_DRIVER was not raised) */
    static int asked;
    pthread_once(&once,start);
    if(!asked++) fprintf(stderr,"PWBOOT input_first_request\n");
    pthread_mutex_lock(&lock);
    int got=count>0;
    if(got) {*event=queue[head];head=(head+1)%QUEUE;--count;}
    pthread_mutex_unlock(&lock);
    return got;
}
int pw_wine_input_fd(void)
{
    pthread_once(&once,start);
    pthread_t self=pthread_self();int fd=-1;
    pthread_mutex_lock(&wake_lock);
    for(unsigned i=0;i<wake_count && fd<0;i++) if(pthread_equal(wakes[i].thread,self)) fd=wakes[i].read;
    if(fd<0 && wake_count<WAKE_SLOTS) {
        /* The driver drains the wake socket with plain read() until it fails; a short receive
         * timeout ends that loop, since sockets cannot be made non-blocking (W013: EACCES). */
        int pair[2];struct timeval timeout={0,1000};
        errno=0;int rc=socketpair(AF_UNIX,SOCK_STREAM,0,pair);int pair_errno=errno;
        errno=0;int rcvtimeo=rc?-1:setsockopt(pair[0],SOL_SOCKET,SO_RCVTIMEO,&timeout,sizeof(timeout));int rcvtimeo_errno=errno;
        if(wake_count<8) fprintf(stderr,"PWBOOT input_wake n=%u pair=%d errno=%d rcvtimeo=%d errno=%d\n",
                                 wake_count,rc,pair_errno,rcvtimeo,rcvtimeo_errno);
        if(!rc && !rcvtimeo) {wakes[wake_count].thread=self;wakes[wake_count].read=pair[0];wakes[wake_count].write=pair[1];wake_count++;fd=pair[0];}
        else if(!rc) {close(pair[0]);close(pair[1]);}
    }
    pthread_mutex_unlock(&wake_lock);
    return fd;
}
/* W155: the pointer stays inside a smaller area when the screen shows only that part of the
 * desktop (ps5drv.c present_screen, 32-bit titles); 0 restores the whole desktop */
void pw_hw_pointer_area(int w,int h);
void pw_hw_pointer_area(int w,int h)
{
    static int full_width,full_height;
    if(!full_width) {full_width=width;full_height=height;}
    /* W265: or larger, a display mode above the desktop's size shown full screen (ps5drv.c) */
    if(w<=0 || h<=0 || w>3840 || h>2160) {w=full_width;h=full_height;}
    if(w==width && h==height) return;
    width=w;height=h;
    if(move_by(0,0)) pw_hw_cursor_moved();
    fprintf(stderr,"PWBOOT pointer_area %dx%d\n",w,h);
}
int pw_hw_cursor(int *x,int *y,int *w,int *h)
{
    *x=cursor_x;*y=cursor_y;*w=width;*h=height;return cursor_valid;
}
