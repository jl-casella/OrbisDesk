#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""J002: the optical drive probe (native/disc_probe.c) as the probe PKG ORBB00001, beside OrbisDesk.
With a disc inserted, it looks at /mnt/disc (stat, fstatfs, listing, kind of disc, CSS on a
DVD-Video title VOB), /dev and the nodes that may be the drive (open, sizes, raw sectors 16-18 and
256) three times: from the sandbox, after GoldHEN's SDK jailbreak as uid 0, and jailbroken as the
app's own uid (OrbisDesk's ROOT, W228). Each line goes to /data/orbisdesk/probe-disc.txt with its
errno. No Wine, no screen: it closes after 2 s.
Built as tools/build-mnt-probe.py builds J001: the same flags and link.x, and it may import only
what the newest build/wine-hardware-w*/wine.elf or H001B's hardware.elf import.
The probe title installs over itself only with a higher app version (J001 was 01.13), and the
package is uploaded as /data/pkg/orbisdesk-pwbase-probe.pkg, replacing the previous probe.
Run in WSL like the other builders:
    python3 tools/build-disc-probe.py [--check] [--upload HOST]
--check stops after the link and the import check (no package)."""
import argparse,ftplib,hashlib,json,os,pathlib,shutil,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1];sdk=ROOT/'.deps/sdk/OpenOrbis/PS4Toolchain'
BUILD='J002';VERSION='01.14'
TITLE_ID='ORBB00001';CONTENT='IV0000-ORBB00001_00-ORBISWINPWBASE01';REMOTE='/data/pkg/orbisdesk-pwbase-probe.pkg'
parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');parser.add_argument('--upload')
args=parser.parse_args()
work=ROOT/'build/disc-probe-j002';app=work/'app';out=ROOT/'out/disc-probe-j002'
shutil.rmtree(work,ignore_errors=True);app.mkdir(parents=True)
env=dict(os.environ,OO_PS4_TOOLCHAIN=str(sdk))
def run(command):
    with (work/'build.log').open('a') as log:
        log.write('+ '+' '.join(map(str,command))+'\n');log.flush()
        subprocess.run(list(map(str,command)),cwd=work,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
flags=['--target=x86_64-pc-freebsd12-elf','-fPIC','-march=btver2','-O2','-g','-Wall','-Wextra','-Werror',
       '-isysroot',sdk,'-isystem',sdk/'include']
def imports(elf):
    listing=subprocess.run(['llvm-nm-14','--undefined-only',str(elf)],capture_output=True,text=True,check=True).stdout
    return {line.split()[-1] for line in listing.splitlines() if line.strip()}
wine_elves=sorted(ROOT.glob('build/wine-hardware-w*/wine.elf'),key=lambda p:p.stat().st_mtime)
if not wine_elves:raise SystemExit('no build/wine-hardware-w*/wine.elf to take the proven imports from')
proven_from=[wine_elves[-1],ROOT/'build/hardware-h001b/hardware.elf']
proven=set().union(*(imports(p) for p in proven_from))
obj=work/'disc_probe.o';elf=work/'disc_probe.elf'
run(['clang',*flags,'-c',ROOT/'native/disc_probe.c','-o',obj])
run(['ld.lld','-pie','--no-undefined','--eh-frame-hdr','--script',sdk/'link.x','-o',elf,obj,
     sdk/'lib/crt1.o','-L',sdk/'lib','-lc','-lkernel'])
unproven=sorted(imports(elf)-proven)
if unproven:raise SystemExit('disc_probe.elf imports what no running eboot imports: '+', '.join(unproven))
if args.check:
    print(json.dumps({'build':BUILD,'check':'ok','elf_sha256':sha(elf),'imports':sorted(imports(elf)),
                      'imports_proven_from':[str(p.relative_to(ROOT)) for p in proven_from]}));raise SystemExit(0)
from orbis_package import package_app
run([sdk/'bin/linux/create-fself','-in='+str(elf),'-out='+str(elf.with_suffix('.oelf')),
     '--eboot',app/'eboot.bin','--paid','0x3800000000000011'])
title='OrbisDesk disc probe %s'%BUILD
pkg=package_app(ROOT,app,out,title,TITLE_ID,CONTENT,version=VERSION)
manifest={'build':BUILD,'title':title,'title_id':TITLE_ID,'app_version':VERSION,
    'package':str(pkg.relative_to(ROOT)),'package_sha256':sha(pkg),'eboot_sha256':sha(app/'eboot.bin'),
    'source_sha256':sha(ROOT/'native/disc_probe.c'),'imports':sorted(imports(elf)),
    'imports_proven_from':[str(p.relative_to(ROOT)) for p in proven_from],'log':'/data/orbisdesk/probe-disc.txt'}
(out/'manifest.json').write_text(json.dumps(manifest,indent=1))
print(json.dumps(manifest))
if args.upload:
    # one fixed name: the previous probe package is replaced, not added to
    ftp=ftplib.FTP();ftp.connect(args.upload,2121,timeout=60);ftp.login()
    with pkg.open('rb') as f:ftp.storbinary('STOR '+REMOTE,f)
    print(json.dumps({'uploaded':REMOTE,'remote_size':ftp.size(REMOTE),'local_size':pkg.stat().st_size}))
    ftp.quit()
