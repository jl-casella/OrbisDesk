#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Steam client's libraries (title ORBS00001), from the pinned downloads in .deps/steam/downloads:
Mbed TLS 3.6.6 (with native/steam/mbedtls_user_config.h), curl 8.22.0 on it (HTTPS and WebSocket
only), zstd 1.5.6 (decompression only) and the LZMA SDK 24.09 decoder. Each run starts from clean
sources in build/steam-deps-<target>/ and installs headers and static archives under its prefix/.
    python3 tools/build-steam-deps.py --target host   this PC (WSL), for S2's host runs
    python3 tools/build-steam-deps.py --target ps4    the console, with OpenOrbis (.deps/sdk)
For the PS4 nothing is configured by CMake (its checks link test programs, which a cross build
with OpenOrbis can't): Mbed TLS, zstd and the LZMA decoder are compiled file by file, and curl
with native/steam/orbis/curl_config.h, written by hand, plus Playden's curl-ps5-native-nonblock
patch (upstream/playden-ps5/scripts/network-deps/patches), which sets libSceNet's SO_NBIO."""
import argparse,hashlib,pathlib,shutil,subprocess,tarfile
ROOT=pathlib.Path(__file__).resolve().parents[1];DOWNLOADS=ROOT/'.deps/steam/downloads'
# Keep the checkout and $HOME out of __FILE__ strings and debug info.
PREFIX_MAP=['-ffile-prefix-map=%s=.'%ROOT,'-ffile-prefix-map=%s=vk-h0'%(pathlib.Path.home()/'vk-h0')]
SDK=ROOT/'.deps/sdk/OpenOrbis/PS4Toolchain'
PINS={'mbedtls-3.6.6.tar.bz2':'8fb65fae8dcae5840f793c0a334860a411f884cc537ea290ce1c52bb64ca007a',
      'curl-8.22.0.tar.xz':'f7ef3ae8a22e521f289803fe93543eb64c329b58aa73a9e224dfd915a2a5f4f7',
      'zstd-1.5.6.tar.gz':'8c29e06cf42aacc1eafc4077ae2ec6c6fcb96a626157e0593d5e82a34fd403c1',
      'lzma-24.09/LzmaDec.c':'b9ca2b8707400347c75d6fef288d1354a3b4cf93e8da42f26207b8bd4c4d5e59',
      'lzma-24.09/LzmaDec.h':'3aaf07b4ae4173a2d103179455dc7089b5ddbc7fc3db3c0e40964a7499c69266',
      'lzma-24.09/7zTypes.h':'5de943c886d5d7bbcf16203e9b292a9e7be327b43fe3dfd9f4ad07d6d0870ef6',
      'lzma-24.09/Precomp.h':'fea249c753dfbbdd69d9397e91497205452b784279f70cad4658dc567cd2f85f',
      'lzma-24.09/Compiler.h':'959dac87ac7109502f6467e910d0722b932176e243153bf8c663479aa8c29b20'}
CURL_PATCH=(ROOT/'upstream/playden-ps5/scripts/network-deps/patches/curl-ps5-native-nonblock.patch',
            '8ad3d3b23ed6c526d89e289c0acc11784df994f6ba99a3d6392cac0f5065e526')
parser=argparse.ArgumentParser();parser.add_argument('--target',choices=['host','ps4'],required=True)
args=parser.parse_args()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for name,expected in PINS.items():
    path=DOWNLOADS/name
    if not path.is_file() or sha(path)!=expected:
        raise SystemExit('missing or changed: %s (docs/STEAM_S1.md lists the downloads)'%path)
if args.target=='ps4' and sha(CURL_PATCH[0])!=CURL_PATCH[1]:raise SystemExit('changed: %s'%CURL_PATCH[0])
work=ROOT/('build/steam-deps-'+args.target);src=work/'src';prefix=work/'prefix'
shutil.rmtree(work,ignore_errors=True);src.mkdir(parents=True);(prefix/'lib').mkdir(parents=True);(prefix/'include').mkdir()
def run(command,cwd=work,env=None):
    with (work/'build.log').open('a') as log:
        log.write('+ '+' '.join(map(str,command))+'\n');log.flush()
        subprocess.run(list(map(str,command)),cwd=cwd,stdout=log,stderr=subprocess.STDOUT,check=True,env=env)
for name in ('mbedtls-3.6.6.tar.bz2','curl-8.22.0.tar.xz','zstd-1.5.6.tar.gz'):
    with tarfile.open(DOWNLOADS/name) as archive:archive.extractall(src,filter='data')
mbedtls_config=['-DMBEDTLS_USER_CONFIG_FILE="mbedtls_user_config.h"','-I',ROOT/'native/steam']
if args.target=='ps4':
    cc=['clang','--target=x86_64-pc-freebsd12-elf','-fPIC','-funwind-tables','-march=btver2','-O2','-g',
        '-isysroot',SDK,'-isystem',SDK/'include',*PREFIX_MAP,'-ffile-prefix-map=%s/='%src]
else:
    cc=['clang','-O2','-g','-fPIC',*PREFIX_MAP,'-ffile-prefix-map=%s/='%src]
def archive(name,sources,flags,subdir):
    objects=[]
    for source in sources:
        obj=work/subdir/(source.parent.name+'_'+source.stem+'.o');obj.parent.mkdir(exist_ok=True)
        run([*cc,*flags,'-c',source,'-o',obj]);objects.append(obj)
    run(['llvm-ar-14','rcs',prefix/'lib'/name,*objects])

# Mbed TLS: the user config's header is installed too, so every user of the headers sees the
# same configuration (the context layouts include mutexes with MBEDTLS_THREADING_C)
mbedtls=src/'mbedtls-3.6.6'
if args.target=='ps4':
    # one archive with the whole library (libmbedtls.a); Everest and p256-m are off by default
    archive('libmbedtls.a',sorted((mbedtls/'library').glob('*.c')),
            ['-w',*mbedtls_config,'-I',mbedtls/'include','-I',mbedtls/'library'],'mbedtls')
    for folder in ('mbedtls','psa'):shutil.copytree(mbedtls/'include'/folder,prefix/'include'/folder)
else:
    cflags=' '.join(PREFIX_MAP)+' -O2 -g -fPIC -ffile-prefix-map=%s/= -DMBEDTLS_USER_CONFIG_FILE=\\"mbedtls_user_config.h\\" -I%s'%(src,ROOT/'native/steam')
    cmake=['cmake','-G','Ninja','-DCMAKE_BUILD_TYPE=Release','-DCMAKE_C_COMPILER=clang','-DCMAKE_C_FLAGS='+cflags,
           '-DCMAKE_INSTALL_PREFIX='+str(prefix),'-DCMAKE_INSTALL_LIBDIR=lib']
    run([*cmake,'-S',mbedtls,'-B',work/'mbedtls','-DENABLE_PROGRAMS=OFF','-DENABLE_TESTING=OFF',
         '-DUSE_SHARED_MBEDTLS_LIBRARY=OFF','-DUSE_STATIC_MBEDTLS_LIBRARY=ON'])
    run(['cmake','--build',work/'mbedtls']);run(['cmake','--install',work/'mbedtls'])
shutil.copyfile(ROOT/'native/steam/mbedtls_user_config.h',prefix/'include/mbedtls_user_config.h')

# curl: as Playden's PS5 build (scripts/network-deps/prepare-ps5-deps.sh), plus no CA paths of its
# own: the client hands the bundle as a blob (CURLOPT_CAINFO_BLOB), since MBEDTLS_FS_IO is off
curl=src/'curl-8.22.0'
if args.target=='ps4':
    run(['patch','--fuzz=0','-p1','-i',CURL_PATCH[0]],cwd=curl)
    lib=curl/'lib'
    sources=sorted([*lib.glob('*.c'),*[s for d in ('curlx','vauth','vdns','vquic','vssh','vtls') for s in (lib/d).glob('*.c')]])
    archive('libcurl.a',sources,['-w','-DHAVE_CONFIG_H','-DBUILDING_LIBCURL','-DCURL_STATICLIB','-I',ROOT/'native/steam/orbis',
                                 '-I',curl/'include','-I',lib,'-I',prefix/'include',*mbedtls_config],'curl')
    shutil.copytree(curl/'include/curl',prefix/'include/curl')
else:
    run([*cmake,'-S',curl,'-B',work/'curl','-DBUILD_CURL_EXE=OFF','-DBUILD_EXAMPLES=OFF',
         '-DBUILD_LIBCURL_DOCS=OFF','-DBUILD_MISC_DOCS=OFF','-DBUILD_SHARED_LIBS=OFF','-DBUILD_STATIC_LIBS=ON',
         '-DBUILD_TESTING=OFF','-DCURL_USE_MBEDTLS=ON','-DMBEDTLS_INCLUDE_DIR='+str(prefix/'include'),
         '-DMBEDTLS_LIBRARY='+str(prefix/'lib/libmbedtls.a'),'-DMBEDX509_LIBRARY='+str(prefix/'lib/libmbedx509.a'),
         '-DMBEDCRYPTO_LIBRARY='+str(prefix/'lib/libmbedcrypto.a'),'-DCURL_DISABLE_WEBSOCKETS=OFF',
         '-DCURL_CA_BUNDLE=none','-DCURL_CA_PATH=none','-DCURL_CA_FALLBACK=OFF',
         '-DENABLE_IPV6=OFF','-DENABLE_THREADED_RESOLVER=OFF','-DCURL_DISABLE_SOCKETPAIR=ON','-DCURL_USE_LIBPSL=OFF',
         '-DCURL_USE_LIBSSH2=OFF','-DCURL_ZLIB=OFF','-DCURL_BROTLI=OFF','-DCURL_ZSTD=OFF','-DUSE_NGHTTP2=OFF',
         '-DUSE_LIBIDN2=OFF','-DCURL_DISABLE_NETRC=ON',
         # each protocol but HTTP(S) and WebSocket off one by one: HTTP_ONLY would turn WebSocket off too
         *['-DCURL_DISABLE_%s=ON'%p for p in ('DICT','FILE','FTP','GOPHER','IMAP','IPFS','LDAP','LDAPS','MQTT',
                                              'POP3','RTSP','SMTP','TELNET','TFTP')],'-DCURL_ENABLE_SMB=OFF'])
    run(['cmake','--build',work/'curl']);run(['cmake','--install',work/'curl'])

# zstd: the decompressor alone (Playden's depot_chunk.cpp calls ZSTD_decompress)
zstd=src/'zstd-1.5.6/lib'
archive('libzstd.a',sorted([*(zstd/'common').glob('*.c'),*(zstd/'decompress').glob('*.c')]),
        ['-DZSTD_DISABLE_ASM','-DZSTD_MULTITHREAD=0','-DZSTD_NO_TRACE','-I',zstd],'zstd')
shutil.copyfile(zstd/'zstd.h',prefix/'include/zstd.h');shutil.copyfile(zstd/'zstd_errors.h',prefix/'include/zstd_errors.h')

# LZMA SDK: the decoder alone
lzma=DOWNLOADS/'lzma-24.09'
for name in ('LzmaDec.h','7zTypes.h','Precomp.h','Compiler.h'):shutil.copyfile(lzma/name,prefix/'include'/name)
archive('liblzmadec.a',[lzma/'LzmaDec.c'],['-I',prefix/'include'],'lzma')
print('\n'.join(sorted(str(p.relative_to(ROOT)) for p in (prefix/'lib').glob('*.a'))))
