#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Host check of MangoHud Settings' file logic (fixtures/win32/mangohudcfg.c).

Compiles tests/mangohudcfg_conf.c with the host C compiler (cc, or $CC) and checks that what a save
writes is read the same by both readers of MangoHud.conf, modelled here from their sources:
native/hw_overlay.c's hud_read_conf (each line in order) and MangoHud's overlay_params.cpp (a map in
which the last value of a key wins, "full" applied before the other keys). Also: other lines kept,
the edited keys written once, a second save identical to the first. No Windows or console needed.
"""
import os,pathlib,subprocess,sys,tempfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
ROWS=('fps','frametime','frame_timing','gpu_stats','cpu_stats','ram','vram')
POSITIONS=('top-left','top-right','top-center','middle-left','middle-right','bottom-left','bottom-right','bottom-center')
DEFAULTS={'fps':1,'frametime':1,'frame_timing':1,'gpu_stats':1,'cpu_stats':1,'ram':0,'vram':0,
          'position':'top-left','offset_x':0,'offset_y':0,'font_size':24,'alpha_pct':50}
def atoi(text):
    digits=''
    for i,ch in enumerate(text.lstrip()):
        if ch.isdigit() or (i==0 and ch in '+-'):digits+=ch
        else:break
    try:return int(digits)
    except ValueError:return 0
def split(line):
    for stop in '#\r\n':line=line.split(stop,1)[0]
    key,eq,value=line.partition('=')
    return key.strip(' \t'),(value.lstrip(' \t') if eq else None)
def overlay_read(text):
    """hw_overlay.c's hud_read_conf"""
    c=dict(DEFAULTS)
    for line in text.split('\n'):
        key,value=split(line)
        if not key:continue
        on=1 if value is None or atoi(value)!=0 else 0
        if key in ROWS:c[key]=on
        elif key=='full' and on:c.update({k:1 for k in ROWS})
        elif key=='position' and value is not None and value in POSITIONS:c['position']=value
        elif key in ('offset_x','offset_y') and value is not None:c[key]=atoi(value)
        elif key=='font_size' and value is not None and 8<=atoi(value)<=96:c['font_size']=atoi(value)
        elif key=='background_alpha' and value is not None:
            a=float(value)
            if 0<=a<=1:c['alpha_pct']=int(a*100+0.5)
    return c
def mangohud_read(text):
    """overlay_params.cpp: options[key]=value (last wins), full first, then each other key"""
    options={}
    for line in text.split('\n'):
        key,value=split(line)
        if key:options[key]=value if value is not None else '1'
    c=dict(DEFAULTS)
    if options.get('full','0')!='0':c.update({k:1 for k in ROWS})
    options.pop('full',None)
    for key,value in options.items():
        if key in ROWS:c[key]=1 if atoi(value)!=0 else 0
        elif key=='position':c['position']=value if value in POSITIONS else 'top-left'
        elif key in ('offset_x','offset_y'):c[key]=atoi(value)
        elif key=='font_size':c['font_size']=atoi(value)
        elif key=='background_alpha':c['alpha_pct']=int(float(value)*100+0.5)
    return c

def main():
    compiler=os.environ.get('CC','cc')
    with tempfile.TemporaryDirectory() as tmp:
        harness=pathlib.Path(tmp)/'mangohudcfg_conf'
        subprocess.run([compiler,'-std=gnu11','-Wall','-Wextra','-Werror','-O1',str(ROOT/'tests/mangohudcfg_conf.c'),
                        '-o',str(harness)],check=True)
        def run(text,*args):
            return subprocess.run([str(harness),*args],input=text.encode('latin-1'),capture_output=True,check=True).stdout.decode('latin-1')
        def form(text):
            c={}
            for line in run(text,'read').splitlines():
                k,_,v=line.partition('=');c[k]=v if k=='position' else int(v)
            return c
        failures=[]
        def check(name,condition):
            if not condition:failures.append(name)
            print(('ok   ' if condition else 'FAIL ')+name)
        # build-wine-hardware.py's file
        build_file=('# MangoHud settings (OrbisDesk). Save and restart OrbisDesk to apply.\n'
                    '# Options: https://github.com/flightlessmango/MangoHud#hud-configuration\n'
                    'fps\nframetime\nframe_timing=1\ncpu_stats\ngpu_stats\nram\nposition=top-left\n')
        check('build file: form shows what the overlay reads',form(build_file)==overlay_read(build_file))
        check('build file: overlay and MangoHud agree',overlay_read(build_file)==mangohud_read(build_file))
        saved=run(build_file,'merge')
        check('unchanged save: same values for the overlay',overlay_read(saved)==overlay_read(build_file))
        check('unchanged save: same values for MangoHud',mangohud_read(saved)==overlay_read(build_file))
        check('unchanged save: comments kept',saved.startswith(build_file.split('fps\n')[0]))
        check('second save identical',run(saved,'merge')==saved)
        # a user file: CRLF, full, a key twice, another MangoHud option, an out-of-range font, a non-ASCII comment
        user=('# my HUD \xe9\r\nfull\r\nfps=0\r\ntoggle_hud=Shift_R+F12\r\nfont_size=200\r\n'
              'fps=1 # again\r\nposition=bottom-right\r\nbackground_alpha=0.25\r\n\r\n\r\n')
        check('user file: form shows what the overlay reads',form(user)==overlay_read(user))
        edits=('fps=0','vram=0','ram=1','position=middle-left','font_size=30','alpha_pct=80','offset_x=12','offset_y=7')
        saved=run(user,'merge',*edits)
        expected=dict(overlay_read(user));expected.update(fps=0,vram=0,ram=1,position='middle-left',font_size=30,
                                                         alpha_pct=80,offset_x=12,offset_y=7)
        check('edited save: overlay reads the edits',overlay_read(saved)==expected)
        check('edited save: MangoHud reads the edits',mangohud_read(saved)==expected)
        check('edited save: other lines kept in order',
              [l for l in saved.split('\n')[:3]]==['# my HUD \xe9','full','toggle_hud=Shift_R+F12'])
        check('edited save: each edited key once',all(sum(1 for l in saved.split('\n') if split(l)[0]==k)==1
                                                     for k in ROWS+('position','offset_x','offset_y','font_size','background_alpha')))
        check('edited save: one marker line',saved.count('# OrbisDesk: the HUD options below')==1)
        check('edited save: no CR left',('\r' not in saved))
        check('edited save twice identical',run(saved,'merge',*edits)==saved)
        # no file
        saved=run('','merge')
        check('empty file: MangoHud defaults written',overlay_read(saved)==DEFAULTS and mangohud_read(saved)==DEFAULTS)
        check('empty file: form shows defaults',form('')==DEFAULTS)
        if failures:sys.exit('%d failed'%len(failures))
        print('all passed')
main()
