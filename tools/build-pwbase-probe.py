#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""B006: the PWBASE probe (native/pwbase_probe.c) as its own PKG, beside OrbisDesk. Every probe
uses the same title (ORBB00001) with a higher app version, so each one installs over the last,
and is uploaded as /data/pkg/orbisdesk-pwbase-probe.pkg.
B001-B003 all closed at open, B003 even in its first-open control. --control h001b or
--control w212 packages that build's proven eboot.bin, unchanged, under this same title: if it
also closes, the title or package is at fault, not the probe's code. B004's h001b control ran
under this title, so B001-B003 failed in their own ELF. B005 builds every ELF as
tools/build-hardware-boot.py built H001B: -Werror, H001B's own sink (build/hardware-h001b/sink.c,
frames moved to /data/orbisdesk/pwbase-frames) and only libkernel and libSceVideoOut as needed
libraries; LoadExec is looked up at run time instead of linking libSceSystemService.
B005 also closed before main, so B006 bisects from H001B with --step:
  1  the driver with only the log file and the screen (PWBASE_CONTROL_ONLY), no other files
  2  the same eboot.bin, plus the four stage files in /app0 (not started)
  3  the full driver and stages without own_page (PWBASE_NO_SELF_UNMAP)
  4  the full probe, as B005
No Wine. eboot.bin is the driver, linked at 0 like every working eboot; each stage is
/app0/pwbase_<name>.bin, started in turn by the driver with sceSystemServiceLoadExec
(looked up at run time):
  z   linked at 0, ET_SCE_EXEC_ASLR       control: LoadExec of a second file works at all
  a2  linked at 0x10000000, ASLR type     does a non-zero link address load at all
  a   linked at 0x1000000000, ASLR type   B001's eboot, now as a stage
  b   linked at 0x1100000000, ET_SCE_EXEC no ASLR type at a high address
B001 (variant A as eboot.bin) was refused at open. B002 closed at open with no file; it
imported two kernel functions no running eboot here imports. Now every ELF may import only
what the newest build/wine-hardware-w*/wine.elf or H001B's hardware.elf import (checked
below), and the driver's first open is a control that only writes the log.
Run in WSL like the other builders:
    python3 tools/build-pwbase-probe.py [--step 1|2|3|4 | --control h001b|w212] [--upload HOST]"""
import argparse,ftplib,hashlib,json,os,pathlib,shutil,struct,subprocess
from orbis_package import package_app
ROOT=pathlib.Path(__file__).resolve().parents[1];sdk=ROOT/'.deps/sdk/OpenOrbis/PS4Toolchain'
BUILD='B006'
# the same title installs over itself only with a higher version: one per mode, in the order
# they are meant to run (control h001b, then control w212 if needed, then the probe)
# (01.06 was B004's probe, built but not installed; 01.07 was B005)
VERSIONS={'h001b':'01.04','w212':'01.05',1:'01.08',2:'01.09',3:'01.10',4:'01.11'}
TITLE_ID='ORBB00001';CONTENT='IV0000-ORBB00001_00-ORBISWINPWBASE01';REMOTE='/data/pkg/orbisdesk-pwbase-probe.pkg'
ET_SCE_EXEC=0xFE00;ET_SCE_EXEC_ASLR=0xFE10
STAGES=(('z',0,False),('a2',0x10000000,False),('a',0x1000000000,False),('b',0x1100000000,True))
# a proven eboot.bin and the app files it reads, taken unchanged from its own build
CONTROLS={'h001b':('build/hardware-h001b/app',('eboot.bin','hardware-marker.txt')),
          'w212':('build/wine-hardware-w212/app',('eboot.bin',))}
parser=argparse.ArgumentParser();parser.add_argument('--control',choices=sorted(CONTROLS))
parser.add_argument('--step',type=int,choices=(1,2,3,4),default=1);parser.add_argument('--upload')
args=parser.parse_args();VERSION=VERSIONS[args.control or args.step]
name=BUILD.lower()+('-'+args.control if args.control else '-step%d'%args.step)
work=ROOT/('build/pwbase-probe-'+name);app=work/'app';out=ROOT/('out/pwbase-probe-'+name)
shutil.rmtree(work,ignore_errors=True);app.mkdir(parents=True)
env=dict(os.environ,OO_PS4_TOOLCHAIN=str(sdk))
def run(command):
    with (work/'build.log').open('a') as log:
        log.write('+ '+' '.join(map(str,command))+'\n');log.flush()
        subprocess.run(list(map(str,command)),cwd=work,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
flags=['--target=x86_64-pc-freebsd12-elf','-fPIC','-march=btver2','-O2','-g','-Wall','-Wextra','-Werror',
       '-isysroot',sdk,'-isystem',sdk/'include']
stage_list=','.join('"%s"'%name for name,_,_ in STAGES)
script=(sdk/'link.x').read_text()
if not script.startswith('SECTIONS\n{'):raise SystemExit('unexpected link.x start; the base cannot be set')
def imports(elf):
    listing=subprocess.run(['llvm-nm-14','--undefined-only',str(elf)],capture_output=True,text=True,check=True).stdout
    return {line.split()[-1] for line in listing.splitlines() if line.strip()}
wine_elves=sorted(ROOT.glob('build/wine-hardware-w*/wine.elf'),key=lambda p:p.stat().st_mtime)
if not wine_elves:raise SystemExit('no build/wine-hardware-w*/wine.elf to take the proven imports from')
proven_from=[wine_elves[-1],ROOT/'build/hardware-h001b/hardware.elf']
proven=set().union(*(imports(p) for p in proven_from))
def first_load(elf):
    data=elf.read_bytes();phoff,=struct.unpack_from('<Q',data,0x20);phent,phnum=struct.unpack_from('<HH',data,0x36)
    for i in range(phnum):
        kind,=struct.unpack_from('<I',data,phoff+i*phent)
        if kind==1:return struct.unpack_from('<Q',data,phoff+i*phent+16)[0]
    raise SystemExit('no PT_LOAD in '+str(elf))
sink=None
def build_sink():
    # H001B's sink as it ran (tools/build-hardware-boot.py), with its frames in their own folder
    source=(ROOT/'build/hardware-h001b/sink.c').read_text()
    if source.count('"/data/orbisdesk/hw01/frames')!=2:raise SystemExit('unexpected H001B sink.c: frames path')
    copy=work/'sink.c';copy.write_text(source.replace('"/data/orbisdesk/hw01/frames','"/data/orbisdesk/pwbase-frames'))
    obj=work/'sink.o';run(['clang',*flags,'-c',copy,'-o',obj]);return obj
def build_elf(name,base,index,defines=()):
    obj=work/('pwbase_%s.o'%name);elf=work/('pwbase_%s.elf'%name)
    run(['clang',*flags,'-DPWBASE_VARIANT="%s"'%name,'-DPWBASE_LINKED=0x%xull'%base,'-DPWBASE_INDEX=%d'%index,
         '-DPWBASE_STAGES='+stage_list,*defines,'-c',ROOT/'native/pwbase_probe.c','-o',obj])
    # link.x unchanged except the location counter: the first segment starts at base, not 0
    linker=sdk/'link.x'
    if base:linker=work/('link-%s.x'%name);linker.write_text('SECTIONS\n{\n\t. = 0x%x;\n'%base+script[len('SECTIONS\n{'):])
    run(['ld.lld','-pie','--no-undefined','--eh-frame-hdr','--script',linker,'-o',elf,obj,sink,
         sdk/'lib/crt1.o','-L',sdk/'lib','-lc','-lkernel','-lSceVideoOut'])
    vaddr=first_load(elf)
    if vaddr!=base:raise SystemExit('%s: first PT_LOAD at 0x%x, expected 0x%x'%(elf.name,vaddr,base))
    unproven=sorted(imports(elf)-proven)
    if unproven:raise SystemExit('%s imports what no running eboot imports: %s'%(elf.name,', '.join(unproven)))
    return elf
def fself(elf,target):
    run([sdk/'bin/linux/create-fself','-in='+str(elf),'-out='+str(elf.with_suffix('.oelf')),
         '--eboot',target,'--paid','0x3800000000000011'])
# ET_SCE_EXEC: create-fself has no option for the type and always writes ET_SCE_EXEC_ASLR;
# the SDK's make_fself.py is Python 2 only. The fake SELF holds a copy of the OELF's ELF
# header (after the entry table) and the SHA-256 of the whole OELF; the segment digests do
# not cover the header. Both are changed, each checked first.
def set_exec_type(elf,target):
    oelf=bytearray(elf.with_suffix('.oelf').read_bytes());signed=bytearray(target.read_bytes())
    kind,=struct.unpack_from('<H',oelf,0x10)
    if kind!=ET_SCE_EXEC_ASLR:raise SystemExit('%s e_type 0x%x, expected 0x%x'%(elf.name,kind,ET_SCE_EXEC_ASLR))
    entries,=struct.unpack_from('<H',signed,0x18);header=0x20+entries*0x20
    if signed[header:header+0x40]!=oelf[:0x40]:raise SystemExit('%s: ELF header copy not at 0x%x'%(target.name,header))
    old=hashlib.sha256(oelf).digest()
    if signed.count(old)!=1:raise SystemExit('%s: OELF digest found %d times'%(target.name,signed.count(old)))
    digest_at=signed.find(old)
    struct.pack_into('<H',oelf,0x10,ET_SCE_EXEC);struct.pack_into('<H',signed,header+0x10,ET_SCE_EXEC)
    signed[digest_at:digest_at+32]=hashlib.sha256(oelf).digest()
    elf.with_suffix('.exec.oelf').write_bytes(oelf);target.write_bytes(signed)
if args.control:
    source,files=CONTROLS[args.control];source=ROOT/source
    for file in files:shutil.copyfile(source/file,app/file)
    title='OrbisDesk probe %s control %s'%(BUILD,args.control)
else:
    sink=build_sink()
    defines={1:['-DPWBASE_CONTROL_ONLY'],2:['-DPWBASE_CONTROL_ONLY'],3:['-DPWBASE_NO_SELF_UNMAP'],4:[]}[args.step]
    fself(build_elf('driver',0,-1,defines),app/'eboot.bin');files=['eboot.bin']
    if args.step>=2:
        stage_defines=[] if args.step==4 else ['-DPWBASE_NO_SELF_UNMAP']
        for index,(stage,base,exec_type) in enumerate(STAGES):
            elf=build_elf(stage,base,index,stage_defines);target=app/('pwbase_%s.bin'%stage)
            fself(elf,target)
            if exec_type:set_exec_type(elf,target)
        files+=['pwbase_%s.bin'%stage for stage,_,_ in STAGES]
    title='OrbisDesk base probe %s step %d'%(BUILD,args.step)
pkg=package_app(ROOT,app,out,title,TITLE_ID,CONTENT,version=VERSION)
manifest={'build':BUILD,'control':args.control,'step':None if args.control else args.step,'title':title,'title_id':TITLE_ID,'app_version':VERSION,
    'package':str(pkg.relative_to(ROOT)),'package_sha256':sha(pkg),'files':{file:sha(app/file) for file in files}}
if args.control:manifest['control_source']=str(source.relative_to(ROOT))
else:manifest.update({
    'stages':[{'name':stage,'linked':hex(base),'type':'ET_SCE_EXEC' if exec_type else 'ET_SCE_EXEC_ASLR'}
              for stage,base,exec_type in STAGES],
    'source_sha256':sha(ROOT/'native/pwbase_probe.c'),
    'imports_proven_from':[str(p.relative_to(ROOT)) for p in proven_from],
    'log':'/data/orbisdesk/probe-base.txt','frames':'/data/orbisdesk/pwbase-frames','control_marker':'/data/orbisdesk/probe-base.control',
    'state':'/data/orbisdesk/probe-base.state'})
(out/'manifest.json').write_text(json.dumps(manifest,indent=1))
print(json.dumps(manifest))
if args.upload:
    # one fixed name: the previous probe package is replaced, not added to
    ftp=ftplib.FTP();ftp.connect(args.upload,2121,timeout=60);ftp.login()
    with pkg.open('rb') as f:ftp.storbinary('STOR '+REMOTE,f)
    print(json.dumps({'uploaded':REMOTE,'remote_size':ftp.size(REMOTE),'local_size':pkg.stat().st_size}))
    ftp.quit()
