#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""S2: the anonymous Steam download probe (native/steam/steam_s2.cpp) on Playden's Steam backend.
Playden's sources (upstream/playden-ps5, pinned commit in its REVISION) are copied to the build tree
and native/steam/patches/*.patch applied there; upstream/ is never changed. The libraries come from
tools/build-steam-deps.py, and stb_image.h (Playden's inflate) from .deps/steam/downloads/stb.
    python3 tools/build-steam-s2.py --target host   build/steam-s2-host/steam_s2 (run it from there)
    python3 tools/build-steam-s2.py --target ps4    the title ORBS00001 version 01.04 in out/steam-s2
                                                    (--check: stop after the import check)
On the PS4 Playden's backend is built with PLAYDEN_PLATFORM_PS5, its console network code (DNS by
sceNetResolver handed to curl, libSceNet's SO_NBIO), which libSceNet has on the PS4 too, and with
native/steam/orbis/orbis_net_fix.h, which puts back FreeBSD's numbers for the socket constants the
SDK gives as Linux's. Imports: as tools/build-steam-probe.py, what the newest wine.elf or H001B's
hardware.elf import; NEW_IMPORTS lists the others this title is allowed, each one named in the
manifest and exercised by the console run. This builder never uploads."""
import argparse,hashlib,json,os,pathlib,shutil,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1];SDK=ROOT/'.deps/sdk/OpenOrbis/PS4Toolchain'
PLAYDEN=ROOT/'upstream/playden-ps5';REVISION='fb74dbfd6bb96fc19a96afc1f48a4e40a885216b'
STB=(ROOT/'.deps/steam/downloads/stb/stb_image.h','594c2fe35d49488b4382dbfaec8f98366defca819d916ac95becf3e75f4200b3')
CACERT=(ROOT/'.deps/steam/downloads/cacert-2026-09-25.pem','a41b5d356aea97a529fe27e0f7316d2f9d946d75927476cf9cf1b90637d00505')
BUILD='S2';VERSION='01.06';TITLE_ID='ORBS00001';CONTENT='IV0000-ORBS00001_00-ORBISWINSTEAM001'
# what S2 links of Playden's src/steam/backend
BACKEND=['proto_wire','auth_messages','cm_messages','json','token_claims','http_client','ws_client','native_network',
         'cm_client','app_info_http','binary_kv','vdf','app_info','content_language','cdn_client','depot_manifest',
         'depot_chunk','gzip']
# Imports no running eboot has yet; the S2 console run is their first use (docs/STEAM_S2.md)
NEW_IMPORTS={
    'sceNetRecv':'libSceNet; Playden native_network.cpp, the SO_NBIO preflight on a loopback pair',
    'sceNetResolverAbort':'libSceNet; Playden native_network.cpp, a canceled or late DNS lookup',
    'sceNetGetDnsInfo':"libSceNet; the SDK's musl resolver (resolvconf), linked by curl's getaddrinfo, "
                       'which the CURLOPT_RESOLVE entries of native_network.cpp leave unused',
    '__pthread_cleanup_push_imp':"libkernel; the same musl resolver (res_msend)",
    '__pthread_cleanup_pop_imp':"libkernel; the same musl resolver (res_msend)",
    'pthread_equal':"libkernel; libc++'s std::recursive_mutex (mutex.cpp)",
}
parser=argparse.ArgumentParser();parser.add_argument('--target',choices=['host','ps4'],required=True)
parser.add_argument('--check',action='store_true')
args=parser.parse_args()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
if (PLAYDEN/'REVISION').read_text().strip()!=REVISION:raise SystemExit('upstream/playden-ps5 is not at '+REVISION)
for path,expected in (STB,CACERT):
    if not path.is_file() or sha(path)!=expected:raise SystemExit('missing or changed: %s'%path)
deps=ROOT/('build/steam-deps-'+args.target+'/prefix')
if not (deps/'lib/libcurl.a').is_file():raise SystemExit('run tools/build-steam-deps.py --target '+args.target+' first')
work=ROOT/('build/steam-s2-'+args.target);shutil.rmtree(work,ignore_errors=True);work.mkdir(parents=True)
env=dict(os.environ,OO_PS4_TOOLCHAIN=str(SDK))  # create-fself needs it
def run(command,cwd=work):
    with (work/'build.log').open('a') as log:
        log.write('+ '+' '.join(map(str,command))+'\n');log.flush()
        subprocess.run(list(map(str,command)),cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)

# Playden's sources, then our patches on the copy
src=work/'playden/src'
shutil.copytree(PLAYDEN/'src/steam',src/'steam');shutil.copytree(PLAYDEN/'src/platform',src/'platform')
for patch in sorted((ROOT/'native/steam/patches').glob('*.patch')):run(['patch','--fuzz=0','-p1','-i',patch],cwd=work/'playden')
(work/'third_party').mkdir();shutil.copyfile(STB[0],work/'third_party/stb_image.h')

common=['-O2','-g','-fPIC','-DMBEDTLS_USER_CONFIG_FILE="mbedtls_user_config.h"','-DCURL_STATICLIB',
        '-I',src,'-I',deps/'include','-I',work/'third_party','-ffile-prefix-map=%s/='%work]
if args.target=='ps4':
    target=['--target=x86_64-pc-freebsd12-elf','-funwind-tables','-march=btver2','-isysroot',SDK,'-isystem',SDK/'include']
    cc=['clang',*target,*common]
    # _DEFAULT_SOURCE: without it the SDK's musl <time.h> hides nanosleep, which libc++'s <thread> calls
    cxx=['clang++',*target,'-isystem',SDK/'include/c++/v1','-std=c++17','-D_DEFAULT_SOURCE',*common,
         '-DPLAYDEN_PLATFORM_PS5=1','-include',ROOT/'native/steam/orbis/orbis_net_fix.h']
else:
    cc=['clang',*common];cxx=['clang++','-std=c++17',*common,'-DSTEAM_HOST']
objects=[]
for name in BACKEND:
    obj=work/(name+'.o');run([*cxx,'-w','-c',src/'steam/backend'/(name+'.cpp'),'-o',obj]);objects.append(obj)
# cm_client's device seed storage (unused by S2, which seeds each run, but linked): Playden's on
# the host; on the PS4 native/steam/orbis/storage_none.cpp, which fails every call and keeps
# opendir/readdir (getdents) and seteuid out of the imports
storage=[src/'platform/storage.cpp',src/'platform/effective_uid.cpp'] if args.target=='host' else \
        [ROOT/'native/steam/orbis/storage_none.cpp']
for source in storage:
    obj=work/(source.stem+'.o');run([*cxx,'-w','-c',source,'-o',obj]);objects.append(obj)
# Mbed TLS's entropy (native/steam/steam_tls.c, as S1)
obj=work/'steam_tls.o';run([*cc,'-Wall','-Wextra','-Werror','-c',ROOT/'native/steam/steam_tls.c','-o',obj]);objects.append(obj)
probe=work/'steam_s2.o';run([*cxx,'-Wall','-Wextra','-Werror','-c',ROOT/'native/steam/steam_s2.cpp','-o',probe])
# the network diagnosis before the CM (S2 01.03)
obj=work/'steam_netdiag.o';run([*cxx,'-Wall','-Wextra','-Werror','-c',ROOT/'native/steam/steam_netdiag.cpp','-o',obj]);objects.append(obj)
if args.target=='ps4':
    # Linux's clock numbers, as the SDK's headers gave them to everything here, to the kernel's
    obj=work/'orbis_clock.o';run([*cc,'-Wall','-Wextra','-Werror','-c',ROOT/'native/steam/orbis/orbis_clock.c','-o',obj])
    objects.append(obj)

if args.target=='host':
    binary=work/'steam_s2'
    libs=['curl','mbedtls','mbedx509','mbedcrypto','everest','p256m','zstd','lzmadec']
    run(['clang++','-o',binary,probe,*objects,'-L',deps/'lib',*['-l'+l for l in libs],'-lpthread'])
    shutil.copyfile(CACERT[0],work/'cacert.pem')
    print(binary.relative_to(ROOT));raise SystemExit(0)

def imports(elf):
    listing=subprocess.run(['llvm-nm-14','--undefined-only',str(elf)],capture_output=True,text=True,check=True).stdout
    return {line.split()[-1] for line in listing.splitlines() if line.strip()}
wine_elves=sorted(ROOT.glob('build/wine-hardware-w*/wine.elf'),key=lambda p:p.stat().st_mtime)
if not wine_elves:raise SystemExit('no build/wine-hardware-w*/wine.elf to take the proven imports from')
proven_from=[wine_elves[-1],ROOT/'build/hardware-h001b/hardware.elf']
proven=set().union(*(imports(p) for p in proven_from))
elf=work/'steam_s2.elf'
run(['ld.lld','-m','elf_x86_64','-pie','--no-undefined','--eh-frame-hdr','--script',SDK/'link.x',
     '--wrap=clock_gettime','--wrap=clock_getres','-o',elf,probe,*objects,
     SDK/'lib/crt1.o','-L',deps/'lib','-lcurl','-lmbedtls','-lzstd','-llzmadec','-L',SDK/'lib',
     '-lc++','-lc++abi','-lunwind','-lc','-lkernel','-lSceNet','-lSceSysmodule'])
unproven=sorted(imports(elf)-proven)
unexpected=[name for name in unproven if name not in NEW_IMPORTS]
if unexpected:raise SystemExit('steam_s2.elf imports what no running eboot imports: '+', '.join(unexpected))
if args.check:
    print(json.dumps({'build':BUILD,'check':'ok','elf_sha256':sha(elf),'new_imports':unproven}));raise SystemExit(0)

from orbis_package import package_app
app=work/'app';misc=app/'assets/misc';misc.mkdir(parents=True)
run([SDK/'bin/linux/create-fself','-in='+str(elf),'-out='+str(elf.with_suffix('.oelf')),
     '--eboot',app/'eboot.bin','--paid','0x3800000000000011'])
shutil.copyfile(CACERT[0],misc/'cacert.pem')
licences={'GPL-3.0.txt':PLAYDEN/'LICENSE','MbedTLS-Apache-2.0.txt':ROOT/'build/steam-deps-ps4/src/mbedtls-3.6.6/LICENSE',
          'curl-COPYING.txt':ROOT/'build/steam-deps-ps4/src/curl-8.22.0/COPYING',
          'zstd-LICENSE.txt':ROOT/'build/steam-deps-ps4/src/zstd-1.5.6/LICENSE'}
for name,source in licences.items():shutil.copyfile(source,misc/name)
out=ROOT/'out/steam-s2';shutil.rmtree(out,ignore_errors=True)
title='OrbisDesk Steam %s'%BUILD
pkg=package_app(ROOT,app,out,title,TITLE_ID,CONTENT,version=VERSION)
manifest={'build':BUILD,'title':title,'title_id':TITLE_ID,'app_version':VERSION,
    'package':str(pkg.relative_to(ROOT)),'package_sha256':sha(pkg),'eboot_sha256':sha(app/'eboot.bin'),
    'playden_revision':REVISION,'patches':{p.name:sha(p) for p in sorted((ROOT/'native/steam/patches').glob('*.patch'))},
    'sources_sha256':{s:sha(ROOT/s) for s in ['native/steam/steam_s2.cpp','native/steam/steam_tls.c',
        'native/steam/steam_netdiag.cpp','native/steam/mbedtls_user_config.h','native/steam/orbis/curl_config.h','native/steam/orbis/orbis_net_fix.h']},
    'new_imports':{name:NEW_IMPORTS[name] for name in unproven},
    'imports_proven_from':[str(p.relative_to(ROOT)) for p in proven_from],
    'log':'/data/orbisdesk/steam-s2.txt','writes':'/data/orbisdesk/steam/1007/<depot>/'}
(out/'manifest.json').write_text(json.dumps(manifest,indent=1))
print(json.dumps(manifest))
