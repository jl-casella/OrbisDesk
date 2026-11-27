#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise the real overlay with host declarations, never a console acceptance claim."""
import argparse,hashlib,json,re,subprocess,tempfile
from pathlib import Path
r=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--preview-dir',type=Path);args=parser.parse_args()
source=r/'native/hw_overlay.c';text=source.read_text()
pad=(r/'native/hw_pad.c').read_text()
poll=pad[pad.index('static int poll_controller('):pad.index('static int poll_mouse(')]
assert poll.index('pw_hw_overlay_pad(&data)')<poll.index('pw_pad_remap(&data,')<poll.index('pad_last=data;')<poll.index('int dx=')
assert pad.count('pw_pad_remap(')==1
code=r'''
#include <assert.h>
#define CONFIG_FILE "overlay.ini"
#define TYPE_FILE "padtype.txt"
#define PADMAP_DIR "padmaps"
#define PADMAP_DEFAULT_DIR "padmaps-default"
static int fail_rename;
#include <stdio.h>
#include <errno.h>
static int test_rename(const char *a,const char *b){if(fail_rename){errno=EACCES;return -1;}return rename(a,b);}
#define rename test_rename
#include "OVERLAY_SOURCE"
static int key_events,reloads;
int pw_trace_level=0;
uint64_t sceKernelGetProcessTime(void){return 1000000;}
void pw_hw_pad_key(uint32_t vk,int down){key_events++;}
void pw_hw_pad_set_mouse(int on){}
void pw_hw_cursor_moved(void){}
int pw_hw_overlay_exit_title(int ask){return 0;}
unsigned int pw_wine_vk_presents(void){return 0;}
void pw_hw_pad_profile_reload(const char *exe){reloads++;}
static void reply_get(void){char b[128],c[128],second[8];pw_hw_overlay_render_poll(b,sizeof(b));assert(!strncmp(b,"get ",4));pw_hw_overlay_render_poll(second,sizeof(second));assert(!strcmp(second,"-"));snprintf(c,sizeof(c),"get 0 0 %s",b+4);pw_hw_overlay_render_result(c);}
static void expect_file(const char *name,const char *needle){char b[32768];FILE *f=fopen(name,"r");assert(f);size_t n=fread(b,1,sizeof(b)-1,f);fclose(f);b[n]=0;assert(strstr(b,needle));}
static void expect_live(void){assert(fps_limit==30 && !framegen_on && !stretch_on && cursor_mode==CURSOR_GAME && pad_type==TYPE_GENERIC);}
static void name_type(const char *name){for(const char *p=name;*p;p++){struct key k;assert(char_key(*p,&k));profile_name_key(k.vk,k.label);}}
static void tests(void){
 /* Every face-button combination, both stick clicks, unaffected controls, and involution. */
 for(unsigned options=0;options<4;options++)for(unsigned mask=0;mask<64;mask++) {
  const uint32_t faces[]={ORBIS_PAD_BUTTON_CROSS,ORBIS_PAD_BUTTON_CIRCLE,ORBIS_PAD_BUTTON_SQUARE,ORBIS_PAD_BUTTON_TRIANGLE,ORBIS_PAD_BUTTON_L3,ORBIS_PAD_BUTTON_R3};
  OrbisPadData d={0};d.connected=1;d.buttons=ORBIS_PAD_BUTTON_OPTIONS|ORBIS_PAD_BUTTON_UP;
  for(unsigned b=0;b<6;b++)if(mask&(1u<<b))d.buttons|=faces[b];
  d.leftStick.x=9;d.leftStick.y=210;d.rightStick.x=222;d.rightStick.y=33;memset(d.unrelated,0xa5,sizeof(d.unrelated));OrbisPadData original=d;
  pw_pad_remap(&d,options);
  for(unsigned b=0;b<6;b++) {
   unsigned partner=b<4 && (options&PW_PAD_SWAP_BUTTONS)?b^1:b>=4 && (options&PW_PAD_SWAP_STICKS)?b^1:b;
   assert(!!(d.buttons&faces[b])==!!(original.buttons&faces[partner]));
  }
  assert(d.leftStick.x==((options&PW_PAD_SWAP_STICKS)?222:9) && d.leftStick.y==((options&PW_PAD_SWAP_STICKS)?33:210));
  assert(d.rightStick.x==((options&PW_PAD_SWAP_STICKS)?9:222) && d.rightStick.y==((options&PW_PAD_SWAP_STICKS)?210:33));
  assert((d.buttons&(ORBIS_PAD_BUTTON_OPTIONS|ORBIS_PAD_BUTTON_UP))==(ORBIS_PAD_BUTTON_OPTIONS|ORBIS_PAD_BUTTON_UP));
  pw_pad_remap(&d,options);assert(!memcmp(&d,&original,sizeof(d)));
 }
 const char *bad[]={"wfm.exe","WFM.EXE","explorer.exe","services.exe","orbis32host.exe","../hl2.exe","x\\hl2.exe","C:hl2.exe","hl2.exe\nlang=es",".exe","hl2","hl2.exe=1"," hl2.exe"};
 for(unsigned i=0;i<sizeof(bad)/sizeof(bad[0]);i++)assert(!pw_profile_allowed(bad[i]));
 assert(pw_profile_allowed("hl2.exe") && pw_profile_allowed("game name.exe"));
 struct pw_profiles cat={0};char name[64];
 for(int i=0;i<200;i++){snprintf(name,sizeof(name),"game%d.exe",i);assert(pw_profiles_note(&cat,name,32,0));}
 assert(cat.count==128 && !strcmp(cat.rows[0].name,"game199.exe") && !strcmp(cat.rows[127].name,"game72.exe"));
 pw_profiles_note(&cat,"GAME199.EXE",0,0);assert(cat.count==128 && cat.rows[0].bits==32);
 pw_profiles_note(&cat,"game100.exe",64,0);assert(cat.count==128 && cat.rows[0].bits==64);
 assert(!pw_profiles_note(&cat,"wfm.exe",0,0));
 for(int l=0;l<LANGS;l++)for(int i=0;i<STRINGS;i++)assert(strings[l][i]);
 init();view=VIEW_PANEL;profile_default_pad=TYPE_GENERIC;
 strcpy(programs[0],"left4dead2.exe");program_count=1;cursor_apply("test");expect_live();
 unsigned serial=program_serial;
 pw_profiles_note(&profile_history,"hl2.exe",32,0);
 pw_profiles_note(&profile_history,"Unity64.exe",64,0);
 assert(profile_select("hl2.exe"));reply_get();
 /* Regression: a desktop GET expires even if no registry consumer took it. */
 assert(profile_select("hl2.exe"));uint64_t deadline=render_deadline_us;
 assert(!render_taken && !render_expire(deadline-1));
 assert(render_expire(deadline) && render_error && render_request==RENDER_NONE);
 render_choose();assert(render_request==RENDER_GET && !render_error);reply_get();
 /* A taken GET is bounded too; retry can recover from a registry error. */
 assert(profile_select("hl2.exe"));char waiting[128];pw_hw_overlay_render_poll(waiting,sizeof(waiting));
 assert(render_taken && render_expire(render_deadline_us));
 render_choose();pw_hw_overlay_render_poll(waiting,sizeof(waiting));
 pw_hw_overlay_render_result("get - 5 hl2.exe");assert(render_error && render_saved<0);
 render_choose();reply_get();assert(!render_error && render_saved==0);
 fps_choice=2;fps_choose();framegen_toggle();stretch_toggle();cursor_choice=CURSOR_HIDDEN;cursor_choose();type_choice=TYPE_XONE;pad_choose();
 profile_store(IT_SWAPSTICKS,1);profile_store(IT_SWAPBUTTONS,1);
 expect_live();assert(program_serial==serial && !pw_hw_overlay_input_options());expect_file(TYPE_FILE,"generic");
 assert(profile_value(IT_FPS)==60 && profile_value(IT_FRAMEGEN) && profile_value(IT_STRETCH) && profile_value(IT_CONTROL)==TYPE_XONE && profile_value(IT_CURSOR)==CURSOR_HIDDEN);
 render_choice=3;render_choose();char q[128];pw_hw_overlay_render_poll(q,sizeof(q));assert(!strcmp(q,"set 3 hl2.exe"));
 assert(!profile_select("left4dead2.exe"));
 pw_hw_overlay_render_result("get 0 0 hl2.exe");assert(render_request==RENDER_SET && render_taken);
 pw_hw_overlay_render_result("set 3 0 other.exe");assert(render_request==RENDER_SET);
 /* Active program exits while the editor's renderer SET is in flight. */
 program_count=0;cursor_apply("exit-test");assert(!strcmp(edit_program,"hl2.exe") && render_request==RENDER_SET);
 pw_hw_overlay_render_result("set 3 0 hl2.exe");assert(render_saved==3 && !render_request);
 assert(profile_select("Unity64.exe"));assert(render_unavailable());reply_get();
 /* Save and reload a closed executable's architecture/history without preference slots. */
 assert(write_config(LANG_EN));int saved_count=cursor_saved_count;
 memset(&profile_history,0,sizeof(profile_history));memset(cursor_saved,0,sizeof(cursor_saved));cursor_saved_count=0;read_config();
 assert(cursor_saved_count==saved_count && profile_history.count==2 && profile_history.rows[0].bits==64);
 int remap_slot=cursor_slot("hl2.exe",0);assert(remap_slot>=0 && cursor_saved[remap_slot].swapsticks && cursor_saved[remap_slot].swapbuttons);
 assert(profile_select("hl2.exe"));reply_get();assert(profile_value(IT_FPS)==60);
 fail_rename=1;fps_choice=0;fps_choose();assert(profile_value(IT_FPS)==60);expect_file(CONFIG_FILE,"fpslimit.hl2.exe=60");
 assert(profile_select("new.exe"));reply_get();int count=cursor_saved_count;framegen_toggle();assert(cursor_saved_count==count && cursor_slot("new.exe",0)<0);
 fail_rename=0;
 strcpy(programs[0],"hl2.exe");program_count=1;cursor_apply("remap-activation");assert(pw_hw_overlay_input_options()==3);
 /* Selecting current runtime owner applies settings only after successful persistence. */
 strcpy(programs[0],"left4dead2.exe");program_count=1;cursor_apply("test");
 assert(!pw_hw_overlay_input_options());
 assert(profile_select("left4dead2.exe"));reply_get();fps_choice=2;fps_choose();assert(fps_limit==60);
 profile_store(IT_SWAPSTICKS,1);assert(pw_hw_overlay_input_options()==PW_PAD_SWAP_STICKS);
 fail_rename=1;assert(!profile_store(IT_SWAPSTICKS,0));assert(pw_hw_overlay_input_options()==PW_PAD_SWAP_STICKS);fail_rename=0;
 fail_rename=1;fps_choice=0;fps_choose();assert(fps_limit==60);fail_rename=0;
 /* Header/list navigation and internal filtering; list order remains fixed on guest exit. */
 cursor_slot("wfm.exe",1);cursor_slot("explorer.exe",1);focus=FOCUS_ITEMS;section=SEC_PERF;item=0;
 panel_input(0,NAV_UP);assert(focus==FOCUS_PROFILE);
 panel_input(ORBIS_PAD_BUTTON_CROSS,0);assert(view==VIEW_PROFILES);
 for(int i=0;i<profile_rows_count;i++)assert(pw_profile_allowed(profile_rows[i].name));
 profile_row=profile_rows_count;profile_picker_input(ORBIS_PAD_BUTTON_CROSS,0);assert(view==VIEW_PROFILE_NAME);
 /* OSK keys belong to the local name field, even on commit/cancel. */
 kb_row=1;kb_col=0;keyboard_input(ORBIS_PAD_BUTTON_CROSS,0);assert(!strcmp(profile_name,"q") && !key_events);
 keyboard_input(ORBIS_PAD_BUTTON_SQUARE,0);assert(!profile_name[0]);
 name_type("portal.exe");profile_name_key(VK_HOME,"");profile_name_key(VK_DELETE,"");assert(!strcmp(profile_name,"ortal.exe"));
 profile_name_key('p',"p");profile_name_key(VK_END,"");assert(!strcmp(profile_name,"portal.exe"));
 keyboard_input(ORBIS_PAD_BUTTON_OPTIONS,0);assert(view==VIEW_PANEL && !strcmp(edit_program,"portal.exe") && !key_events);reply_get();
 map_open();assert(!strcmp(map_program,"portal.exe"));strcpy(map_key[MAP_CROSS],"space");assert(map_save());assert(!reloads);
 strcpy(map_key[MAP_CROSS],"enter");fail_rename=1;assert(!map_save());fail_rename=0;
 expect_file("padmaps/portal.exe.ini","cross = space");assert(!reloads);
 view=VIEW_PANEL;focus=FOCUS_PROFILE;profile_picker_open();profile_row=profile_rows_count;profile_picker_input(ORBIS_PAD_BUTTON_CROSS,0);
 name_type("wfm.exe");keyboard_input(ORBIS_PAD_BUTTON_OPTIONS,0);assert(view==VIEW_PROFILE_NAME && !key_events);
 keyboard_input(ORBIS_PAD_BUTTON_CIRCLE,0);assert(view==VIEW_PROFILES && !key_events);
 /* Recent launch survives its crash/exit, without a saved setting or file picker. */
 pw_hw_overlay_program("E:\\Games\\crashes.exe",1);pw_hw_overlay_program("E:\\Games\\crashes.exe",0);
 assert(!strcmp(profile_history.rows[0].name,"crashes.exe") && cursor_slot("crashes.exe",0)<0);
 desktop_front=1;view=VIEW_PANEL;profile_editor_begin();assert(!strcmp(edit_program,"crashes.exe"));reply_get();
 expect_file(CONFIG_FILE,"profile.crashes.exe=0");
 puts("PASS: real overlay profile isolation, failure rollback, offline renderer RPC, crash history, architecture, internal filtering, navigation, local OSK and keymap isolation");
}
static void ppm(const char *path,const struct surface *s){FILE *f=fopen(path,"wb");assert(f);fprintf(f,"P6\n%d %d\n255\n",s->width,s->height);for(int y=0;y<s->height;y++)for(int x=0;x<s->width;x++){uint32_t c=s->pixels[y*s->pitch+x];unsigned char rgb[]={c>>16,c>>8,c};fwrite(rgb,1,3,f);}fclose(f);}
static void previews(void){
 enum {W=1280,H=720};uint32_t *pixels=calloc(W*H,sizeof(*pixels));assert(pixels);struct surface s={pixels,W,W,H};
 for(int l=0;l<2;l++)for(int scene=0;scene<7;scene++){
  lang=l;section=scene==4?SEC_CONTROLS:SEC_GRAPHICS;focus=FOCUS_PROFILE;item=0;view=VIEW_PANEL;
  strcpy(edit_program,"hl2.exe");strcpy(render_program,edit_program);render_saved=render_choice=3;reset_choices();
  render_error=0;render_request=RENDER_NONE;
  if(scene==5){render_saved=-1;render_request=RENDER_GET;}
  if(scene==6){render_saved=-1;render_error=1;focus=FOCUS_ITEMS;}
  for(int i=0;i<W*H;i++)pixels[i]=0xff303640;
  if(scene==3){memset(edit_program,'a',59);strcpy(edit_program+59,".exe");}
  draw_panel(&s,0,0);
  if(scene==1){profile_picker_open();draw_profiles(&s);}
  if(scene==2){view=VIEW_PROFILE_NAME;strcpy(profile_name,"hl2.exe");profile_caret=7;kb_row=1;kb_col=0;draw_keyboard(&s);}
  char file[64];snprintf(file,sizeof(file),"%s-%d.ppm",l==LANG_ES?"es":"en",scene);ppm(file,&s);
 }
 free(pixels);
}
int main(int argc,char **argv){unlink(CONFIG_FILE);unlink(TYPE_FILE);tests();if(argc>1)previews();return 0;}
'''.replace('OVERLAY_SOURCE',str(source))
def run(d):
    inc=d/'include/orbis';inc.mkdir(parents=True,exist_ok=True)
    (inc/'libkernel.h').write_text('#include <stdint.h>\n#include <sys/types.h>\nuint64_t sceKernelGetProcessTime(void);size_t sceKernelGetDirectMemorySize(void);int sceKernelAvailableDirectMemorySize(void);\n')
    buttons=sorted(set(re.findall(r'ORBIS_PAD_BUTTON_\w+',text)))
    (inc/'Pad.h').write_text('typedef struct {unsigned buttons;int connected;struct {unsigned char x,y;} leftStick,rightStick;unsigned char unrelated[32];} OrbisPadData;\n'+''.join('#define %s (1u<<%d)\n'%(name,i) for i,name in enumerate(buttons)))
    (d/'check.c').write_text(code)
    subprocess.run(['cc','-std=gnu11','-O1','-g','-ffunction-sections','-fdata-sections','-fsanitize=address,undefined','-no-pie','-Wl,--gc-sections','-I'+str(d/'include'),'-I'+str(r/'native'),'-I'+str(r/'platform/ps4'),str(d/'check.c'),'-lpthread','-o',str(d/'check')],check=True)
    subprocess.run([str(d/'check')]+(['preview'] if args.preview_dir else []),cwd=d,check=True,timeout=30)
    if args.preview_dir:
        from PIL import Image
        for p in d.glob('*.ppm'):Image.open(p).save(p.with_suffix('.png'))
        (d/'provenance.json').write_text(json.dumps({'kind':'Host rendering of real overlay; not PS4 evidence','source_hashes':{str(p.relative_to(r)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (source,r/'native/hw_overlay_profiles.inc.c',r/'native/hw_overlay_profiles_draw.inc.c',r/'platform/ps4/pw_overlay_profiles.h')},'languages':['es','en']},indent=2)+'\n')
if args.preview_dir:
    d=args.preview_dir.resolve();d.mkdir(parents=True,exist_ok=True);run(d)
else:
    with tempfile.TemporaryDirectory() as tmp:run(Path(tmp))
