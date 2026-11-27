#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Real SDK pad records through the production remap, XInput and DualSense serializers."""
from pathlib import Path
import re,subprocess,tempfile
r=Path(__file__).resolve().parents[1];source=(r/'native/hw_pad.c').read_text()
sdk=r/'.deps/sdk/OpenOrbis/PS4Toolchain/include/orbis/_types/pad.h'
def fn(name):
    m=re.search(r'^(?:static )?(?:int|int16_t) '+name+r'\([^;]*?\)\n\{',source,re.M);assert m,name
    a=m.start();b=source.index('{',a)+1;depth=1
    while depth:depth+=(source[b]=='{')-(source[b]=='}');b+=1
    return source[a:b]+'\n'
def decl(prefix):
    a=source.index(prefix);return source[a:source.index('};',a)+2]+'\n'
code='''#include <assert.h>
#include <stdint.h>
#include <string.h>
#include <pthread.h>
'''+f'#include "{sdk}"\n#include "{r / "native/hw_pad_remap.h"}"\n'+decl('struct PwXinputPad {')+decl('static const struct {uint32_t orbis;uint16_t xinput;} xinput_map[]')+r'''
static pthread_once_t once=PTHREAD_ONCE_INIT;
static pthread_mutex_t pad_state_lock=PTHREAD_MUTEX_INITIALIZER;
static OrbisPadData pad_last;
static uint32_t pad_packet=17;
static uint64_t xinput_read_us;
static int pad=1;
static void start(void){}
static uint64_t sceKernelGetProcessTime(void){return 123456;}
'''+''.join(fn(n) for n in ('thumb','pad_state','pw_wine_pad_dualsense'))+r'''
int main(void){
 const uint32_t physical[]={ORBIS_PAD_BUTTON_CROSS,ORBIS_PAD_BUTTON_CIRCLE,ORBIS_PAD_BUTTON_SQUARE,ORBIS_PAD_BUTTON_TRIANGLE,ORBIS_PAD_BUTTON_L3,ORBIS_PAD_BUTTON_R3};
 const unsigned xb[]={0x1000,0x2000,0x4000,0x8000,0x40,0x80},ds[]={0x20,0x40,0x10,0x80,0x40,0x80};
 for(unsigned options=0;options<4;options++)for(unsigned mask=0;mask<64;mask++){
  OrbisPadData d={0};d.connected=1;d.buttons=ORBIS_PAD_BUTTON_UP|ORBIS_PAD_BUTTON_R1;
  for(unsigned i=0;i<6;i++)if(mask&(1u<<i))d.buttons|=physical[i];
  d.leftStick.x=10;d.leftStick.y=240;d.rightStick.x=220;d.rightStick.y=7;
  d.analogButtons.l2=13;d.analogButtons.r2=201;d.touch.fingers=1;d.touch.touch[0].finger=3;d.touch.touch[0].x=800;d.touch.touch[0].y=100;
  pw_pad_remap(&d,options);pad_last=d;
  struct PwXinputPad x;uint8_t report[64];
  xinput_read_us=0;assert(pad_state(&x,0));assert(!xinput_read_us && x.packet==17 && x.connected);
  assert(pw_wine_pad_dualsense(report));assert(!xinput_read_us);
  unsigned expected_xb=0x0001|0x0200,expected_ds_face=0,expected_ds_click=0;
  for(unsigned i=0;i<6;i++) {
   unsigned from=i<4 && (options&PW_PAD_SWAP_BUTTONS)?i^1:i>=4 && (options&PW_PAD_SWAP_STICKS)?i^1:i;
   if(mask&(1u<<from)){expected_xb|=xb[i];if(i<4)expected_ds_face|=ds[i];else expected_ds_click|=ds[i];}
  }
  assert(x.buttons==expected_xb && report[8]==expected_ds_face && report[9]==(expected_ds_click|2));
  assert(x.thumb_lx==((options&1)?23772:-30198) && x.thumb_ly==((options&1)?30968:-28913));
  assert(x.thumb_rx==((options&1)?-30198:23772) && x.thumb_ry==((options&1)?-28913:30968));
  assert(report[1]==((options&1)?220:10) && report[2]==((options&1)?7:240));
  assert(report[3]==((options&1)?10:220) && report[4]==((options&1)?240:7));
  assert(x.left_trigger==13 && x.right_trigger==201 && report[5]==13 && report[6]==201);
  assert(report[33]==3 && report[34]==(800&255));
  assert(pad_state(&x,1) && xinput_read_us==123456);
 }
 pad_last.connected=0;struct PwXinputPad x;memset(&x,0xff,sizeof(x));assert(!pad_state(&x,0));assert(!x.connected && !x.buttons);
 uint8_t report[64];assert(!pw_wine_pad_dualsense(report));
 puts("PASS: 256 real-SDK pad cases through actual XInput and DualSense encoders; axes, A/B, X/Y, L3/R3, triggers, touch and game-mode read tracking");
}
'''
with tempfile.TemporaryDirectory() as tmp:
    d=Path(tmp);(d/'check.c').write_text(code)
    subprocess.run(['cc','-std=gnu11','-O1','-g','-fsanitize=address,undefined','-no-pie',str(d/'check.c'),'-lpthread','-o',str(d/'check')],check=True)
    subprocess.run([str(d/'check')],check=True,timeout=15)
