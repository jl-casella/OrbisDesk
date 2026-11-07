#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""S1: the Steam client's HTTPS probe (native/steam/steam_probe.c) as the title ORBS00001, the
Steam client's own title (OrbisDesk is ORBW00002; ORBB00001 stays for the replaceable probes).
Mbed TLS 3.6.6 is built from its pinned tarball with native/steam/mbedtls_user_config.h, and
Mozilla's CA bundle goes into the package as /app0/assets/misc/cacert.pem (create-gp4 declares
only sce_sys, sce_module and assets/*: a file in another folder fails pkg_build). Docs: docs/STEAM_S1.md.
Built as tools/build-disc-probe.py builds J002 (flags, link.x, fself, tools/orbis_package.py),
and it may import only what the newest build/wine-hardware-w*/wine.elf or H001B's hardware.elf
import. This builder never uploads: the build session uploads out/steam-probe-s1/*.pkg.
Run in WSL like the other builders:
    python3 tools/build-steam-probe.py [--check]   PS4 title (--check: stop after the import check)
    python3 tools/build-steam-probe.py --host      the same probe for this PC, in build/steam-probe-host
The title is GPL-3.0-or-later (it carries code from Playden, upstream/playden-ps5); the package
holds the licence texts beside the bundle, in /app0/assets/misc."""
import argparse,hashlib,json,os,pathlib,shutil,subprocess,tarfile
ROOT=pathlib.Path(__file__).resolve().parents[1];sdk=ROOT/'.deps/sdk/OpenOrbis/PS4Toolchain'
BUILD='S1';VERSION='01.05'  # 01.00: CA bundle sized by fstat, 0 roots on the console
TITLE_ID='ORBS00001';CONTENT='IV0000-ORBS00001_00-ORBISWINSTEAM001'
DOWNLOADS=ROOT/'.deps/steam/downloads'
MBEDTLS=('mbedtls-3.6.6','mbedtls-3.6.6.tar.bz2','8fb65fae8dcae5840f793c0a334860a411f884cc537ea290ce1c52bb64ca007a')
CACERT=('cacert-2026-09-25.pem','a41b5d356aea97a529fe27e0f7316d2f9d946d75927476cf9cf1b90637d00505')
SOURCES=['native/steam/steam_probe.c','native/steam/steam_tls.c']
parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');parser.add_argument('--host',action='store_true')
args=parser.parse_args()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def pinned(name,expected):
    path=DOWNLOADS/name
    if not path.is_file():raise SystemExit('missing %s: download it as docs/STEAM_S1.md says'%path)
    if sha(path)!=expected:raise SystemExit('hash mismatch for %s'%path)
    return path
work=ROOT/('build/steam-probe-host' if args.host else 'build/steam-probe-s1');out=ROOT/'out/steam-probe-s1'
shutil.rmtree(work,ignore_errors=True);work.mkdir(parents=True)
env=dict(os.environ,OO_PS4_TOOLCHAIN=str(sdk))
def run(command,cwd=None):
    with (work/'build.log').open('a') as log:
        log.write('+ '+' '.join(map(str,command))+'\n');log.flush()
        subprocess.run(list(map(str,command)),cwd=cwd or work,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)

# Mbed TLS, extracted fresh from the pinned tarball (the sources never reach the repo)
tarball=pinned(MBEDTLS[1],MBEDTLS[2])
with tarfile.open(tarball) as archive:archive.extractall(work/'src',filter='data')
mbedtls=work/'src'/MBEDTLS[0]
config=['-DMBEDTLS_USER_CONFIG_FILE="mbedtls_user_config.h"','-I',ROOT/'native/steam','-I',mbedtls/'include']
if args.host:
    cc=['clang','-O2','-g','-fPIC','-ffile-prefix-map=%s/='%work]
else:
    cc=['clang','--target=x86_64-pc-freebsd12-elf','-fPIC','-march=btver2','-O2','-g',
        '-isysroot',sdk,'-isystem',sdk/'include','-ffile-prefix-map=%s/='%work]
objects=[]
for source in sorted((mbedtls/'library').glob('*.c')):
    obj=work/'mbedtls'/(source.stem+'.o');obj.parent.mkdir(exist_ok=True)
    run([*cc,'-w',*config,'-I',mbedtls/'library','-c',source,'-o',obj]);objects.append(obj)
library=work/'libmbedtls-all.a';run(['llvm-ar-14','rcs',library,*objects])

probe=[]
for source in SOURCES:
    obj=work/(pathlib.Path(source).stem+'.o')
    run([*cc,'-Wall','-Wextra','-Werror',*(['-DSTEAM_HOST'] if args.host else []),*config,'-c',ROOT/source,'-o',obj]);probe.append(obj)
cacert=pinned(*CACERT)

if args.host:
    binary=work/'steam_probe';run(['clang','-o',binary,*probe,library,'-lpthread'])
    shutil.copyfile(cacert,work/'cacert.pem')
    print(json.dumps({'build':BUILD,'host':str(binary.relative_to(ROOT)),
                      'run':'cd %s && ./steam_probe'%work.relative_to(ROOT)}));raise SystemExit(0)

def imports(elf):
    listing=subprocess.run(['llvm-nm-14','--undefined-only',str(elf)],capture_output=True,text=True,check=True).stdout
    return {line.split()[-1] for line in listing.splitlines() if line.strip()}
wine_elves=sorted(ROOT.glob('build/wine-hardware-w*/wine.elf'),key=lambda p:p.stat().st_mtime)
if not wine_elves:raise SystemExit('no build/wine-hardware-w*/wine.elf to take the proven imports from')
proven_from=[wine_elves[-1],ROOT/'build/hardware-h001b/hardware.elf']
proven=set().union(*(imports(p) for p in proven_from))
elf=work/'steam_probe.elf'
run(['ld.lld','-pie','--no-undefined','--eh-frame-hdr','--script',sdk/'link.x','-o',elf,*probe,library,
     sdk/'lib/crt1.o','-L',sdk/'lib','-lc','-lkernel','-lSceNet','-lSceSysmodule'])
unproven=sorted(imports(elf)-proven)
if unproven:raise SystemExit('steam_probe.elf imports what no running eboot imports: '+', '.join(unproven))
if args.check:
    print(json.dumps({'build':BUILD,'check':'ok','elf_sha256':sha(elf),'imports':sorted(imports(elf)),
                      'imports_proven_from':[str(p.relative_to(ROOT)) for p in proven_from]}));raise SystemExit(0)

from orbis_package import package_app
app=work/'app';misc=app/'assets/misc';misc.mkdir(parents=True)
run([sdk/'bin/linux/create-fself','-in='+str(elf),'-out='+str(elf.with_suffix('.oelf')),
     '--eboot',app/'eboot.bin','--paid','0x3800000000000011'])
shutil.copyfile(cacert,misc/'cacert.pem')
licences={'GPL-3.0.txt':ROOT/'upstream/playden-ps5/LICENSE','MbedTLS-Apache-2.0.txt':mbedtls/'LICENSE'}
for name,source in licences.items():shutil.copyfile(source,misc/name)
shutil.rmtree(out,ignore_errors=True)
title='OrbisDesk Steam %s'%BUILD
pkg=package_app(ROOT,app,out,title,TITLE_ID,CONTENT,version=VERSION)
manifest={'build':BUILD,'title':title,'title_id':TITLE_ID,'app_version':VERSION,
    'package':str(pkg.relative_to(ROOT)),'package_sha256':sha(pkg),'eboot_sha256':sha(app/'eboot.bin'),
    'sources_sha256':{s:sha(ROOT/s) for s in [*SOURCES,'native/steam/steam_tls.h','native/steam/mbedtls_user_config.h']},
    'mbedtls':{'tarball':MBEDTLS[1],'sha256':MBEDTLS[2]},'ca_bundle':{'file':CACERT[0],'sha256':CACERT[1]},
    'imports':sorted(imports(elf)),'imports_proven_from':[str(p.relative_to(ROOT)) for p in proven_from],
    'log':'/data/orbisdesk/steam-probe.txt'}
(out/'manifest.json').write_text(json.dumps(manifest,indent=1))
print(json.dumps(manifest))
