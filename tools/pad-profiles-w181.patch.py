#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Pending change for native/hw_pad.c (W181): per-program key profiles for keyboard-only games.
Usage: pad-profiles-w181.patch.py DIR rewrites DIR/hw_pad.c (DIR is native/ or a copy of it),
on top of the W178 change (tools/xinput-pad-w178.patch.py)."""
import pathlib,sys
path=pathlib.Path(sys.argv[1])/'hw_pad.c';text=path.read_text()
def revise(old,new):
    global text
    if text.count(old)!=1:raise SystemExit('Unexpected context in hw_pad.c: '+old[:70])
    text=text.replace(old,new)

revise('#include <string.h>\n','#include <string.h>\n#include <strings.h>\n')
revise(''' * W178: the controller's state is also xinput's (pw_wine_pad); while a program reads it there,
 * its sticks and buttons stop driving the pointer and keys (game mode).
''',''' * W178: the controller's state is also xinput's (pw_wine_pad); while a program reads it there,
 * its sticks and buttons stop driving the pointer and keys (game mode).
 * W181: a program with a key profile (C:\\orbis\\padmaps\\<exe>.ini) gets keys from the buttons and
 * the left stick instead (pw_hw_pad_profile), for games that read only the keyboard.
''')
revise('''static int poll_controller(unsigned reads,uint32_t *previous,int *moved)
{''','''/* W181: key profiles. SuperMarioKart (Blitz3D) reads only the keyboard: it enumerates joysticks once
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
    for(const char *at=exe;at && *at;at++) if(*at=='\\\\' || *at=='/') base=at+1;
    char file[256],line[160];
    snprintf(file,sizeof(file),"/data/wine-prefix/drive_c/orbis/padmaps/%s.ini",base?base:"");
    FILE *ini=fopen(file,"r");
    if(!ini) {fprintf(stderr,"PWPAD profile=%s none errno=%d\\n",base?base:"-",errno);return;}
    int stick_set=0;
    while(fgets(line,sizeof(line),ini)) {
        char source[32],key[32];
        if(line[0]=='#' || line[0]==';' || sscanf(line," %31[^= \\t] = %31s",source,key)!=2) continue;
        if(!strcasecmp(source,"stick")) {profile_stick_mouse=!strcasecmp(key,"mouse");stick_set=1;continue;}
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
    for(unsigned a=0;!profile_stick_mouse && a<4 && profile_count<PROFILE_KEYS;a++) {
        unsigned i;
        for(i=0;i<profile_count;i++) if(profile_keys[i].stick==arrows[a].stick) break;
        if(i==profile_count) {profile_keys[profile_count].button=0;profile_keys[profile_count].stick=arrows[a].stick;profile_keys[profile_count++].vk=arrows[a].vk;}
    }
    profile_active=profile_count>0 || stick_set;
    fprintf(stderr,"PWPAD profile=%s keys=%u stick=%s\\n",base,profile_count,profile_stick_mouse?"mouse":"keys");
}

static int poll_controller(unsigned reads,uint32_t *previous,int *moved)
{''')
revise('''        if(gaming && (*previous&ORBIS_PAD_BUTTON_TOUCH_PAD)) {push(3,touch_press_code,0,"touchpad");changed=1;}
    }''','''        if(gaming && (*previous&ORBIS_PAD_BUTTON_TOUCH_PAD)) {push(3,touch_press_code,0,"touchpad");changed=1;}
        /* W181: and the profile's keys */
        for(unsigned i=0;gaming && i<profile_count;i++)
            if((profile_keys[i].button && (*previous&profile_keys[i].button)) || (profile_keys[i].stick&stick_keys_down)) {
                push(1,profile_keys[i].vk,0,"profile");changed=1;
            }
        if(gaming) stick_keys_down=0;
    }''')
revise('''    if(!game_mode && (abs(dx)>DEADZONE || abs(dy)>DEADZONE))''',
       '''    if(!game_mode && !(profile_active && !profile_stick_mouse) && (abs(dx)>DEADZONE || abs(dy)>DEADZONE))''')
revise('''    /* touchpad (W037): the first finger moves the pointer relatively, like a laptop''','''    /* W181: a profile's stick keys, on each change of direction */
    if(profile_active && !profile_stick_mouse && !game_mode) {
        uint32_t stick=(dy<-STICK_THRESHOLD?STICK_UP:0)|(dy>STICK_THRESHOLD?STICK_DOWN:0)|
                       (dx<-STICK_THRESHOLD?STICK_LEFT:0)|(dx>STICK_THRESHOLD?STICK_RIGHT:0);
        for(unsigned i=0;i<profile_count;i++) {
            uint32_t now=stick&profile_keys[i].stick,before=stick_keys_down&profile_keys[i].stick;
            if(profile_keys[i].stick && now!=before) {push(1,profile_keys[i].vk,now!=0,"profile");changed=1;}
        }
        stick_keys_down=stick;
    }
    /* touchpad (W037): the first finger moves the pointer relatively, like a laptop''')
revise('''    if(!game_mode && abs(ry)>DEADZONE) {''','''    if(!game_mode && !profile_active && abs(ry)>DEADZONE) {''')
revise('''        if(now!=before && !game_mode) {push(pad_map[i].type,pad_map[i].code,now!=0,"pad");changed=1;}
    }''','''        if(now!=before && !game_mode && !profile_active) {push(pad_map[i].type,pad_map[i].code,now!=0,"pad");changed=1;}
    }
    /* W181: a profile's button keys instead */
    for(unsigned i=0;profile_active && !game_mode && i<profile_count;i++) {
        uint32_t now=data.buttons&profile_keys[i].button,before=*previous&profile_keys[i].button;
        if(profile_keys[i].button && now!=before) {push(1,profile_keys[i].vk,now!=0,"profile");changed=1;}
    }''')
revise('''    if(now && !before && !game_mode) {touch_press_code''','''    if(now && !before && !game_mode && !profile_touchpad) {touch_press_code''')
revise('''    if(!now && before && !game_mode) {push(3,touch_press_code,0,"touchpad");changed=1;}''',
       '''    if(!now && before && !game_mode && !profile_touchpad) {push(3,touch_press_code,0,"touchpad");changed=1;}''')
path.write_text(text);print('applied to',path)
