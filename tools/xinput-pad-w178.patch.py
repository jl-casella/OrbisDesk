#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Pending change for native/hw_pad.c (W178, phase 7): the pad for xinput and game mode.
Usage: xinput-pad-w178.patch.py DIR rewrites DIR/hw_pad.c (DIR is native/ or a copy of it)."""
import pathlib,sys
path=pathlib.Path(sys.argv[1])/'hw_pad.c';text=path.read_text()
def revise(old,new):
    global text
    if text.count(old)!=1:raise SystemExit('Unexpected context in hw_pad.c: '+old[:70])
    text=text.replace(old,new)

revise(''' *   USB keyboard USB HID usages translated to Windows virtual keys, with modifiers
''',''' *   USB keyboard USB HID usages translated to Windows virtual keys, with modifiers
 * W178: the controller's state is also xinput's (pw_wine_pad); while a program reads it there,
 * its sticks and buttons stop driving the pointer and keys (game mode).
''')
revise('''static int poll_controller(unsigned reads,uint32_t *previous,int *moved)
{''','''/* W178 (phase 7): the pad for xinput (tools/build-xinput-hw.py, after prospero-win 0470). This
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
int pw_wine_pad(struct PwXinputPad *state)
{
    pthread_once(&once,start);
    pthread_mutex_lock(&pad_state_lock);
    OrbisPadData data=pad_last;uint32_t packet=pad_packet;
    xinput_read_us=sceKernelGetProcessTime();
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
void pw_wine_set_rumble(uint32_t left,uint32_t right)
{
    /* XInput's left motor is the large one */
    OrbisPadVibeParam vibe={(uint8_t)(left>>8),(uint8_t)(right>>8)};
    static int logged;
    int rc=pad>=0?scePadSetVibration(pad,&vibe):-1;
    if(rc && logged<4) {++logged;fprintf(stderr,"PWPAD rumble_failed rc=0x%08x handle=%d\\n",(unsigned)rc,pad);}
}

static int poll_controller(unsigned reads,uint32_t *previous,int *moved)
{''')
revise('''    if(rc) return 0;
    int dx=(int)data.leftStick.x-128,dy=(int)data.leftStick.y-128;
    /* quadratic response: fine aim near the centre, fast at full tilt */
    if(abs(dx)>DEADZONE || abs(dy)>DEADZONE)''','''    if(rc) return 0;
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
        fprintf(stderr,"PWPAD game_mode=%d\\n",gaming);
        /* what the emulation holds is released, or it would stay down during the game */
        for(unsigned i=0;gaming && i<sizeof(pad_map)/sizeof(pad_map[0]);i++)
            if(*previous&pad_map[i].button) {push(pad_map[i].type,pad_map[i].code,0,"pad");changed=1;}
        if(gaming && (*previous&ORBIS_PAD_BUTTON_TOUCH_PAD)) {push(3,touch_press_code,0,"touchpad");changed=1;}
    }
    int dx=(int)data.leftStick.x-128,dy=(int)data.leftStick.y-128;
    /* quadratic response: fine aim near the centre, fast at full tilt */
    if(!game_mode && (abs(dx)>DEADZONE || abs(dy)>DEADZONE))''')
revise('''    } else touching=0;
    int changed=0;''','''    } else touching=0;''')
revise('''    if(abs(ry)>DEADZONE) {
        scroll+=''','''    if(!game_mode && abs(ry)>DEADZONE) {
        scroll+=''')
revise('''        if(now!=before) {push(pad_map[i].type,pad_map[i].code,now!=0,"pad");changed=1;}''',
       '''        if(now!=before && !game_mode) {push(pad_map[i].type,pad_map[i].code,now!=0,"pad");changed=1;}''')
revise('''    static uint32_t press_code;
    uint32_t now=data.buttons&ORBIS_PAD_BUTTON_TOUCH_PAD,before=*previous&ORBIS_PAD_BUTTON_TOUCH_PAD;
    if(now && !before) {press_code=data.touch.fingers>=2?1:0;push(3,press_code,1,"touchpad");changed=1;}
    if(!now && before) {push(3,press_code,0,"touchpad");changed=1;}''','''    uint32_t now=data.buttons&ORBIS_PAD_BUTTON_TOUCH_PAD,before=*previous&ORBIS_PAD_BUTTON_TOUCH_PAD;
    if(now && !before && !game_mode) {touch_press_code=data.touch.fingers>=2?1:0;push(3,touch_press_code,1,"touchpad");changed=1;}
    if(!now && before && !game_mode) {push(3,touch_press_code,0,"touchpad");changed=1;}''')
revise('''    } else if(!data.touch.fingers && tap_fingers>=2 && !tap_moved && !tap_pressed && now_us-tap_start<300000) {''',
       '''    } else if(!game_mode && !data.touch.fingers && tap_fingers>=2 && !tap_moved && !tap_pressed && now_us-tap_start<300000) {''')
path.write_text(text);print('applied to',path)
