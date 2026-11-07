#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""S3: the user's Steam sign-in by QR code and their library (native/steam/steam_s3.cpp), on Playden's
Steam backend as S2 (tools/build-steam-s2.py: the same Playden copy and patches, libraries, console
flags and import check). Adds Playden's AuthClient, LibraryClient and src/library/store.cpp, the
title's screen (native/steam/steam_ui.c, with Nayuki's qrcodegen 1.8.0 from .deps/steam/downloads)
and its sealed session file (native/steam/steam_session.cpp).
    python3 tools/build-steam-s3.py --target host   build/steam-s3-host/steam_s3 (run it from there;
                                                    buttons from stdin: x, o, t)
    python3 tools/build-steam-s3.py --target ps4    the title ORBS00001 version 01.07 in out/steam-s3
                                                    (--check: stop after the import check)
This builder never uploads and never signs in: the sign-in is the user's, on the console."""
import argparse,hashlib,json,os,pathlib,shutil,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1];SDK=ROOT/'.deps/sdk/OpenOrbis/PS4Toolchain'
PLAYDEN=ROOT/'upstream/playden-ps5';REVISION='fb74dbfd6bb96fc19a96afc1f48a4e40a885216b'
STB=(ROOT/'.deps/steam/downloads/stb/stb_image.h','594c2fe35d49488b4382dbfaec8f98366defca819d916ac95becf3e75f4200b3')
CACERT=(ROOT/'.deps/steam/downloads/cacert-2026-09-25.pem','a41b5d356aea97a529fe27e0f7316d2f9d946d75927476cf9cf1b90637d00505')
QRDIR=ROOT/'.deps/steam/downloads/qrcodegen-1.8.0'
QRCODEGEN={'qrcodegen.c':'300eff07ee25baaa7578f20284411638154716379437391e7e689c0e6ce81403',
           'qrcodegen.h':'e82df4bff37d18b5863b9e7486fe6bda1b6cda8c3b9ecebfec473907265cb589'}
BUILD='S3';VERSION='01.07';TITLE_ID='ORBS00001';CONTENT='IV0000-ORBS00001_00-ORBISWINSTEAM001'
# what S3 links of Playden's src/steam/backend: S2's, and the sign-in and owned-games clients
BACKEND=['proto_wire','auth_messages','cm_messages','json','token_claims','http_client','ws_client','native_network',
         'cm_client','app_info_http','binary_kv','vdf','app_info','content_language','gzip',
         'auth_client','password_crypto','library_client']
# Imports no running eboot had before the Steam title; S2's are proven by its console run (01.06)
NEW_IMPORTS={
    'sceNetRecv':'libSceNet; Playden native_network.cpp, the SO_NBIO preflight (proven by S2 01.06)',
    'sceNetResolverAbort':'libSceNet; Playden native_network.cpp, a canceled or late DNS lookup (linked by S2 01.06)',
    'sceNetGetDnsInfo':"libSceNet; the SDK's musl resolver, unused behind CURLOPT_RESOLVE (linked by S2 01.06)",
    '__pthread_cleanup_push_imp':'libkernel; the same musl resolver (linked by S2 01.06)',
    '__pthread_cleanup_pop_imp':'libkernel; the same musl resolver (linked by S2 01.06)',
    'pthread_equal':"libkernel; libc++'s std::recursive_mutex (proven by S2 01.06)",
}
parser=argparse.ArgumentParser();parser.add_argument('--target',choices=['host','ps4'],required=True)
parser.add_argument('--check',action='store_true')
args=parser.parse_args()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
if (PLAYDEN/'REVISION').read_text().strip()!=REVISION:raise SystemExit('upstream/playden-ps5 is not at '+REVISION)
for path,expected in (STB,CACERT,*((QRDIR/n,h) for n,h in QRCODEGEN.items())):
    if not path.is_file() or sha(path)!=expected:raise SystemExit('missing or changed: %s'%path)
deps=ROOT/('build/steam-deps-'+args.target+'/prefix')
if not (deps/'lib/libcurl.a').is_file():raise SystemExit('run tools/build-steam-deps.py --target '+args.target+' first')
work=ROOT/('build/steam-s3-'+args.target);shutil.rmtree(work,ignore_errors=True);work.mkdir(parents=True)
env=dict(os.environ,OO_PS4_TOOLCHAIN=str(SDK))  # create-fself needs it
def run(command,cwd=work):
    with (work/'build.log').open('a') as log:
        log.write('+ '+' '.join(map(str,command))+'\n');log.flush()
        subprocess.run(list(map(str,command)),cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)

src=work/'playden/src'
for part in ('steam','platform','library'):shutil.copytree(PLAYDEN/'src'/part,src/part)
for patch in sorted((ROOT/'native/steam/patches').glob('*.patch')):run(['patch','--fuzz=0','-p1','-i',patch],cwd=work/'playden')
(work/'third_party').mkdir();shutil.copyfile(STB[0],work/'third_party/stb_image.h')

common=['-O2','-g','-fPIC','-DMBEDTLS_USER_CONFIG_FILE="mbedtls_user_config.h"','-DCURL_STATICLIB',
        '-I',src,'-I',deps/'include','-I',work/'third_party','-I',QRDIR,'-ffile-prefix-map=%s/='%work]
if args.target=='ps4':
    target=['--target=x86_64-pc-freebsd12-elf','-funwind-tables','-march=btver2','-isysroot',SDK,'-isystem',SDK/'include']
    cc=['clang',*target,*common]
    cxx=['clang++',*target,'-isystem',SDK/'include/c++/v1','-std=c++17','-D_DEFAULT_SOURCE',*common,
         '-DPLAYDEN_PLATFORM_PS5=1','-include',ROOT/'native/steam/orbis/orbis_net_fix.h']
else:
    cc=['clang',*common,'-DSTEAM_HOST'];cxx=['clang++','-std=c++17',*common,'-DSTEAM_HOST']
objects=[]
def compile(compiler,source,strict=False):
    obj=work/(source.stem+'.o')
    run([*compiler,*(['-Wall','-Wextra','-Werror'] if strict else ['-w']),'-c',source,'-o',obj]);objects.append(obj)
for name in BACKEND:compile(cxx,src/'steam/backend'/(name+'.cpp'))
compile(cxx,src/'library/store.cpp')
# cm_client's Storage (S3 keeps the device seed itself): as S2
if args.target=='host':
    for source in (src/'platform/storage.cpp',src/'platform/effective_uid.cpp'):compile(cxx,source)
else:compile(cxx,ROOT/'native/steam/orbis/storage_none.cpp')
compile(cc,QRDIR/'qrcodegen.c')
compile(cc,ROOT/'native/steam/steam_tls.c',strict=True)
compile(cc,ROOT/'native/steam/steam_ui.c',strict=True)
compile(cxx,ROOT/'native/steam/steam_session.cpp',strict=True)
compile(cxx,ROOT/'native/steam/steam_s3.cpp',strict=True)
if args.target=='ps4':compile(cc,ROOT/'native/steam/orbis/orbis_clock.c',strict=True)

if args.target=='host':
    binary=work/'steam_s3'
    libs=['curl','mbedtls','mbedx509','mbedcrypto','everest','p256m','zstd','lzmadec']
    run(['clang++','-o',binary,*objects,'-L',deps/'lib',*['-l'+l for l in libs],'-lpthread'])
    shutil.copyfile(CACERT[0],work/'cacert.pem')
    print(binary.relative_to(ROOT));raise SystemExit(0)

def imports(elf):
    listing=subprocess.run(['llvm-nm-14','--undefined-only',str(elf)],capture_output=True,text=True,check=True).stdout
    return {line.split()[-1] for line in listing.splitlines() if line.strip()}
wine_elves=sorted(ROOT.glob('build/wine-hardware-w*/wine.elf'),key=lambda p:p.stat().st_mtime)
if not wine_elves:raise SystemExit('no build/wine-hardware-w*/wine.elf to take the proven imports from')
proven_from=[wine_elves[-1],ROOT/'build/hardware-h001b/hardware.elf']
proven=set().union(*(imports(p) for p in proven_from))
elf=work/'steam_s3.elf'
run(['ld.lld','-m','elf_x86_64','-pie','--no-undefined','--eh-frame-hdr','--script',SDK/'link.x',
     '--wrap=clock_gettime','--wrap=clock_getres','-o',elf,*objects,
     SDK/'lib/crt1.o','-L',deps/'lib','-lcurl','-lmbedtls','-lzstd','-llzmadec','-L',SDK/'lib',
     '-lc++','-lc++abi','-lunwind','-lc','-lkernel','-lSceNet','-lSceSysmodule','-lSceVideoOut','-lScePad',
     '-lSceUserService'])
unproven=sorted(imports(elf)-proven)
unexpected=[name for name in unproven if name not in NEW_IMPORTS]
if unexpected:raise SystemExit('steam_s3.elf imports what no running eboot imports: '+', '.join(unexpected))
if args.check:
    print(json.dumps({'build':BUILD,'check':'ok','elf_sha256':sha(elf),'new_imports':unproven}));raise SystemExit(0)

from orbis_package import package_app
app=work/'app';misc=app/'assets/misc';misc.mkdir(parents=True)
run([SDK/'bin/linux/create-fself','-in='+str(elf),'-out='+str(elf.with_suffix('.oelf')),
     '--eboot',app/'eboot.bin','--paid','0x3800000000000011'])
shutil.copyfile(CACERT[0],misc/'cacert.pem')
licences={'GPL-3.0.txt':PLAYDEN/'LICENSE','MbedTLS-Apache-2.0.txt':ROOT/'build/steam-deps-ps4/src/mbedtls-3.6.6/LICENSE',
          'curl-COPYING.txt':ROOT/'build/steam-deps-ps4/src/curl-8.22.0/COPYING',
          'zstd-LICENSE.txt':ROOT/'build/steam-deps-ps4/src/zstd-1.5.6/LICENSE',
          'qrcodegen-README.txt':QRDIR/'LICENSE-README.md'}
for name,source in licences.items():shutil.copyfile(source,misc/name)
out=ROOT/'out/steam-s3';shutil.rmtree(out,ignore_errors=True)
title='OrbisDesk Steam'
pkg=package_app(ROOT,app,out,title,TITLE_ID,CONTENT,version=VERSION,filename='OrbisDesk-Steam-S3-%s.pkg'%VERSION)
sources=['native/steam/steam_s3.cpp','native/steam/steam_session.cpp','native/steam/steam_ui.c','native/steam/steam_tls.c',
         'native/steam/mbedtls_user_config.h','native/steam/orbis/curl_config.h','native/steam/orbis/orbis_net_fix.h']
manifest={'build':BUILD,'title':title,'title_id':TITLE_ID,'app_version':VERSION,
    'package':str(pkg.relative_to(ROOT)),'package_sha256':sha(pkg),'eboot_sha256':sha(app/'eboot.bin'),
    'playden_revision':REVISION,'patches':{p.name:sha(p) for p in sorted((ROOT/'native/steam/patches').glob('*.patch'))},
    'qrcodegen':QRCODEGEN,'sources_sha256':{s:sha(ROOT/s) for s in sources},
    'new_imports':{name:NEW_IMPORTS[name] for name in unproven},
    'imports_proven_from':[str(p.relative_to(ROOT)) for p in proven_from],
    'log':'/data/orbisdesk/steam-s3.txt',
    'writes':['/data/orbisdesk/steam/notice-accepted','/data/orbisdesk/steam/device-seed',
              '/data/orbisdesk/steam/session.bin','/data/orbisdesk/steam/session.key','/data/orbisdesk/steam-library.txt']}
(out/'manifest.json').write_text(json.dumps(manifest,indent=1))
print(json.dumps(manifest))
