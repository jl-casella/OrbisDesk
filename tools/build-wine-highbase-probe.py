#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""B007: an OrbisDesk build's own eboot relinked away from 0x400000, as the probe PKG ORBB00001.
B006 stage b ran an ET_SCE_EXEC eboot linked at 0x1100000000 at that address, with nothing left
below 4 GiB (docs/investigacion-gta-vc-base-0x400000.md). This takes the link command that
tools/build-wine-hardware.py saved in out/wine-hardware-wNNN/manifest.json, without changing
that tool or its build:
  1. replays the link unchanged and requires a byte-identical wine.elf (the inputs are still
     those of WNNN: run this right after WNNN is built);
  2. links again with the same link.x starting at --base, and checks every PT_LOAD moved by
     exactly --base and the imports are the same;
  3. create-fself as build-wine-hardware.py does, then ET_SCE_EXEC (tools/orbis_self.py);
  4. packages it under the probe title, uploaded as /data/pkg/orbisdesk-pwbase-probe.pkg.
The eboot uses the Wine prefix and runtime already on /data, and logs to /data/orbisdesk/wNNN
like WNNN itself. Run in WSL:
    python3 tools/build-wine-highbase-probe.py [--build W215] [--base 0x1100000000] [--upload HOST]"""
import argparse,ftplib,hashlib,json,os,pathlib,re,shutil,subprocess
from orbis_package import package_app
from orbis_self import load_segments,set_exec_type
ROOT=pathlib.Path(__file__).resolve().parents[1];sdk=ROOT/'.deps/sdk/OpenOrbis/PS4Toolchain'
BUILD='B007';VERSION='01.12'   # after B006 step 4 (01.11): the probe title only installs over a lower version
TITLE_ID='ORBB00001';CONTENT='IV0000-ORBB00001_00-ORBISWINPWBASE01';REMOTE='/data/pkg/orbisdesk-pwbase-probe.pkg'
parser=argparse.ArgumentParser();parser.add_argument('--build');parser.add_argument('--base',default='0x1100000000')
parser.add_argument('--upload');args=parser.parse_args()
base=int(args.base,0)
if base%0x4000 or base<0x800000000:raise SystemExit('base must be 16 KiB aligned and above 32 GiB (Wine addr_space_limit)')
builds=sorted((p for p in ROOT.glob('out/wine-hardware-w*') if re.fullmatch(r'wine-hardware-w\d+',p.name)),
              key=lambda p:int(p.name.split('-w')[1]))
source=ROOT/('out/wine-hardware-'+args.build.lower()) if args.build else builds[-1]
manifest=json.loads((source/'manifest.json').read_text())
command=list(manifest['link_command']);original=pathlib.Path(command[command.index('-o')+1])
script=pathlib.Path(command[command.index('--script')+1])
work=ROOT/('build/wine-highbase-'+manifest['build'].lower());app=work/'app';out=ROOT/('out/wine-highbase-'+manifest['build'].lower())
shutil.rmtree(work,ignore_errors=True);app.mkdir(parents=True)
env=dict(os.environ,OO_PS4_TOOLCHAIN=str(sdk))
def run(cmd):
    with (work/'build.log').open('a') as log:
        log.write('+ '+' '.join(map(str,cmd))[:4000]+'\n');log.flush()
        subprocess.run(list(map(str,cmd)),cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def link(output,linker):
    cmd=list(command);cmd[cmd.index('-o')+1]=str(output);cmd[cmd.index('--script')+1]=str(linker);run(cmd)
def imports(elf):
    listing=subprocess.run(['llvm-nm-14','--undefined-only',str(elf)],capture_output=True,text=True,check=True).stdout
    return {line.split()[-1] for line in listing.splitlines() if line.strip()}
# 1. the saved link still gives WNNN's wine.elf
replay=work/'replay.elf';link(replay,script)
if sha(replay)!=sha(original):
    raise SystemExit('%s: replayed link differs from %s; its inputs changed since, rebuild %s first'%(manifest['build'],original,manifest['build']))
# 2. the same link.x with the location counter at base
text=script.read_text()
if not text.startswith('SECTIONS\n{'):raise SystemExit('unexpected link.x start: '+str(script))
# lld defines __dso_handle at the ELF header, which is vaddr 0 at base 0 (the image start) but
# stays at 0 when the image moves, out of R_X86_64_PC32 range of Mesa's C++ objects: it only
# has to be an address of this image (__cxa_atexit), so it becomes the new image start.
high_script=work/'link-high.x'
high_script.write_text('SECTIONS\n{\n\t. = 0x%x;\n\tHIDDEN(__dso_handle = .);\n'%base+text[len('SECTIONS\n{'):])
elf=work/'wine-high.elf';link(elf,high_script)
before,after=load_segments(original),load_segments(elf)
if [(v+base,m) for v,m in before]!=after:raise SystemExit('PT_LOAD layout did not move by exactly 0x%x: %s -> %s'%(base,before,after))
if imports(elf)!=imports(original):raise SystemExit('imports changed with the base')
end=max(v+m for v,m in after)
# 3. the eboot, as build-wine-hardware.py makes it, then ET_SCE_EXEC
oelf=work/'wine-high.oelf'
run([sdk/'bin/linux/create-fself','-in='+str(elf),'-out='+str(oelf),'--eboot',app/'eboot.bin','--paid','0x3800000000000011'])
(work/'wine-high.exec.oelf').write_bytes(set_exec_type(oelf,app/'eboot.bin'))
# 4. the probe package
title='OrbisDesk base probe %s (%s at 0x%x)'%(BUILD,manifest['build'],base)
pkg=package_app(ROOT,app,out,title,TITLE_ID,CONTENT,version=VERSION)
result={'build':BUILD,'from_build':manifest['build'],'from_app_version':manifest['app_version'],'base':hex(base),
    'image_end':hex(end),'title':title,'title_id':TITLE_ID,'app_version':VERSION,
    'package':str(pkg.relative_to(ROOT)),'package_sha256':sha(pkg),'eboot_sha256':sha(app/'eboot.bin'),
    'original_wine_elf_sha256':sha(original),'high_wine_elf_sha256':sha(elf),
    'log_directory':'/data/orbisdesk/'+manifest['build'].lower()}
(out/'manifest.json').write_text(json.dumps(result,indent=1))
print(json.dumps(result))
if args.upload:
    # one fixed name: the previous probe package is replaced, not added to
    ftp=ftplib.FTP();ftp.connect(args.upload,2121,timeout=60);ftp.login()
    with pkg.open('rb') as f:ftp.storbinary('STOR '+REMOTE,f)
    print(json.dumps({'uploaded':REMOTE,'remote_size':ftp.size(REMOTE),'local_size':pkg.stat().st_size}))
    ftp.quit()
