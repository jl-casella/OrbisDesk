#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""G001 (H0): the Vulkan probe (native/vk_probe, DolphinPS4's probe-vk) on RADV over GNM, as its
own PKG ORBG00001. Mesa, libc++ and the probe ELF come from tools/vk-h0/*.sh (run in WSL, tree in
~/vk-h0); this makes the eboot, the PKG, and uploads it.  build-vk-probe.py [--upload HOST]"""
import argparse,ftplib,hashlib,json,os,pathlib,shutil,subprocess
from orbis_package import package_app
ROOT=pathlib.Path(__file__).resolve().parents[1];sdk=ROOT/'.deps/sdk/OpenOrbis/PS4Toolchain'
BUILD='G001';work=ROOT/'build/vk-probe-g001';app=work/'app';out=ROOT/'out/vk-probe-g001'
parser=argparse.ArgumentParser();parser.add_argument('--upload');args=parser.parse_args()
elf=pathlib.Path.home()/'vk-h0/build/probe/vk_probe.elf'
if not elf.is_file():raise SystemExit('missing '+str(elf)+': run tools/vk-h0/build-probe.sh')
shutil.rmtree(work,ignore_errors=True);app.mkdir(parents=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
shutil.copyfile(elf,work/'vk_probe.elf')
# DolphinPS4's probe identity (scripts/build-vk-probe.sh, toolchain/ps4-love-style.cmake):
# homebrew program authority ID and the love-ps4 auth info, no Piglet
authinfo=('000000000000000000000000001C004000FF000000000080000000000000000000000000000000000000008000'
          '400040000000000000008000000000000000080040FFFF000000F000000000000000000000000000000000000000'
          '000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000')
env=dict(os.environ,OO_PS4_TOOLCHAIN=str(sdk))
subprocess.run([str(sdk/'bin/linux/create-fself'),'-in='+str(work/'vk_probe.elf'),'-out='+str(work/'vk_probe.oelf'),
    '--eboot',str(app/'eboot.bin'),'--paid','0x3800000000000035','--authinfo',authinfo],env=env,check=True,
    stdout=subprocess.DEVNULL)
pkg=package_app(ROOT,app,out,'OrbisDesk Vulkan probe G001','ORBG00001','IV0000-ORBG00001_00-ORBISWINVKPROBE1')
manifest={'build':BUILD,'elf_sha256':sha(work/'vk_probe.elf'),'package':str(pkg.relative_to(ROOT)),'package_sha256':sha(pkg),
    'log_dir':'/data/orbisdesk/g001'}
(out/'manifest.json').write_text(json.dumps(manifest,indent=1))
print(json.dumps(manifest))
if args.upload:
    remote='/data/pkg/orbisdesk-%s-%s.pkg'%(BUILD,manifest['package_sha256'][:12])
    ftp=ftplib.FTP();ftp.connect(args.upload,2121,timeout=60);ftp.login()
    with pkg.open('rb') as f:ftp.storbinary('STOR '+remote,f)
    print(json.dumps({'uploaded':remote,'remote_size':ftp.size(remote),'local_size':pkg.stat().st_size}))
    ftp.quit()
