#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Steam client inside OrbisDesk's title (ORBW00002): one relocatable object for the hardware ELF.
Same sources as the standalone title (tools/build-steam-s4.py, which stays buildable), built with
STEAM_UI_HOSTED: no VideoOut or pad of its own (native/steam/steam_ui.c draws in the sink's frame and
reads the pad thread's state), the CA bundle and gbe_fork's DLLs from C:\\orbis\\steam, and Wine's
sceNetInit accepted (patch 0003).
What differs from the standalone build, for living in Wine's ELF:
  - C++ with clang-19 against ~/vk-h0/sysroot's libc++ headers, the libc++ the hardware ELF links
    (tools/build-wine-hardware.py), not the SDK's older one;
  - curl rebuilt with STEAM_UI_HOSTED: Wine's --wrap=setsockopt turns Linux TCP option numbers itself
    (native/steam/orbis/orbis_net_fix.h);
  - clock_gettime/clock_getres renamed in the Steam objects only (objcopy --redefine-sym) to
    native/steam/orbis/orbis_clock.c's pw_steam_* (a global --wrap would also turn Wine's and Mesa's);
  - every defined symbol made local except the four OrbisDesk calls: pw_hw_steam_open,
    pw_hw_steam_draw, pw_hw_steam_pad and pw_hw_steam_active. Nothing else can clash with Wine's.
Then every symbol the object still needs must be defined or imported by the newest
build/wine-hardware-w*/wine.elf, or be one of S2's console-proven imports (NEW_IMPORTS).
Outputs, in build/steam-hosted/:
  steam_client_hosted.o   for the hardware ELF's link (staged patch: notes, steam-hosted-integration.md)
  prefix/orbis/steam/     cacert.pem, gbe-x86-steam_api.dll, gbe-x64-steam_api64.dll and their
                          licence and source notes, for C:\\orbis\\steam in the uploaded prefix
  prefix/orbis/steam-open.exe   the Desktop link's and Start menu's helper (native/steam/orbis_steam_open.c)
  manifest.json
This builder never uploads and never touches the hardware ELF's build."""
import hashlib,json,os,pathlib,shutil,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1];SDK=ROOT/'.deps/sdk/OpenOrbis/PS4Toolchain'
PLAYDEN=ROOT/'upstream/playden-ps5';REVISION='fb74dbfd6bb96fc19a96afc1f48a4e40a885216b'
VK=pathlib.Path.home()/'vk-h0'
STB=(ROOT/'.deps/steam/downloads/stb/stb_image.h','594c2fe35d49488b4382dbfaec8f98366defca819d916ac95becf3e75f4200b3')
CACERT=(ROOT/'.deps/steam/downloads/cacert-2026-09-25.pem','a41b5d356aea97a529fe27e0f7316d2f9d946d75927476cf9cf1b90637d00505')
QRDIR=ROOT/'.deps/steam/downloads/qrcodegen-1.8.0'
QRCODEGEN={'qrcodegen.c':'300eff07ee25baaa7578f20284411638154716379437391e7e689c0e6ce81403',
           'qrcodegen.h':'e82df4bff37d18b5863b9e7486fe6bda1b6cda8c3b9ecebfec473907265cb589'}
GBEDIR=ROOT/'.deps/steam/downloads/gbe_fork-2026_09_27';GBE_TAG='release-2026_09_27'
GBE={'emu-win-release-vs22.7z':'300186c34f49a9ea75b33ce2af299267cc1dad0225cf45e81a229578d4e11c85',
     'gbe_fork-release-2026_09_27-source.tar.gz':'ce3ce7aee0439f1b7aff2404106fe68184185a8d0b7ca5ab2677a046ea464cbd'}
BUILD='SH1'
BACKEND=['proto_wire','auth_messages','cm_messages','json','token_claims','http_client','ws_client','native_network',
         'cm_client','app_info_http','binary_kv','vdf','app_info','content_language','cdn_client','depot_manifest',
         'depot_chunk','gzip','game_path','auth_client','password_crypto','library_client']
EXPORTS=['pw_hw_steam_open','pw_hw_steam_draw','pw_hw_steam_pad','pw_hw_steam_active']
# what the object may need that Wine's ELF doesn't have yet: the S2 imports the standalone title proved
# on the console (docs/STEAM_S2.md), and OrbisDesk's optional ROOT accessor (weak)
NEW_IMPORTS={'sceNetRecv','sceNetResolverAbort','sceNetGetDnsInfo','__pthread_cleanup_push_imp',
             '__pthread_cleanup_pop_imp','pthread_equal','pw_hw_root_mode'}
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
if (PLAYDEN/'REVISION').read_text().strip()!=REVISION:raise SystemExit('upstream/playden-ps5 is not at '+REVISION)
for path,expected in (STB,CACERT,*((QRDIR/n,h) for n,h in QRCODEGEN.items()),*((GBEDIR/n,h) for n,h in GBE.items())):
    if not path.is_file() or sha(path)!=expected:raise SystemExit('missing or changed: %s'%path)
deps=ROOT/'build/steam-deps-ps4/prefix';curl_src=ROOT/'build/steam-deps-ps4/src/curl-8.22.0'
if not (deps/'lib/libmbedtls.a').is_file() or not curl_src.is_dir():
    raise SystemExit('run tools/build-steam-deps.py --target ps4 first')
if not (VK/'sysroot/include/c++/v1/__config').is_file():raise SystemExit('no ~/vk-h0/sysroot libc++ headers')
work=ROOT/'build/steam-hosted';shutil.rmtree(work,ignore_errors=True);work.mkdir(parents=True)
env=dict(os.environ,OO_PS4_TOOLCHAIN=str(SDK))
def run(command,cwd=work):
    with (work/'build.log').open('a') as log:
        log.write('+ '+' '.join(map(str,command))+'\n');log.flush()
        subprocess.run(list(map(str,command)),cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)

src=work/'playden/src'
for part in ('steam','platform','library'):shutil.copytree(PLAYDEN/'src'/part,src/part)
for patch in sorted((ROOT/'native/steam/patches').glob('*.patch')):run(['patch','--fuzz=0','-p1','-i',patch],cwd=work/'playden')
(work/'third_party').mkdir();shutil.copyfile(STB[0],work/'third_party/stb_image.h')

target=['--target=x86_64-pc-freebsd12-elf','-D__ORBIS__','-fPIC','-funwind-tables','-march=btver2','-O2','-g',
        '-ffile-prefix-map=%s/='%work,'-DSTEAM_UI_HOSTED','-DMBEDTLS_USER_CONFIG_FILE="mbedtls_user_config.h"',
        '-DCURL_STATICLIB']
# the libc overlay Mesa's Wine variant is built with (tools/vk-h0/build-mesa.sh): FreeBSD's clock numbers and
# no C++ overloads in <math.h> (libc++ 21 brings its own), with the same feature macros. __PS4__ and
# __OPENORBIS__ keep the patched libc++ off its FreeBSD paths (upstream/DolphinPS4/toolchain/env.sh), as
# when the libc++ the hardware ELF links was built
include=['-D_GNU_SOURCE','-D__PS4__','-D__OPENORBIS__','-D__BSD_VISIBLE','-D_BSD_SOURCE','-isysroot',SDK,
         '-isystem',VK/'sysroot/libc-overlay-wine',
         '-isystem',SDK/'include','-I',src,'-I',deps/'include','-I',work/'third_party','-I',QRDIR,'-I',ROOT/'native/steam']
cc=['clang',*target,*include]
cxx=['clang++-19',*target,'-nostdinc++','-isystem',VK/'sysroot/include/c++/v1',*include,'-std=c++17','-D_DEFAULT_SOURCE',
     '-DPLAYDEN_PLATFORM_PS5=1','-include',ROOT/'native/steam/orbis/orbis_net_fix.h']
objects=[]
def compile(compiler,source,name=None,strict=False,extra=()):
    obj=work/'obj'/((name or source.stem)+'.o');obj.parent.mkdir(exist_ok=True)
    run([*compiler,*extra,*(['-Wall','-Wextra','-Werror'] if strict else ['-w']),'-c',source,'-o',obj]);objects.append(obj)
for name in BACKEND:compile(cxx,src/'steam/backend'/(name+'.cpp'))
compile(cxx,src/'library/store.cpp')
compile(cxx,ROOT/'native/steam/orbis/storage_none.cpp')
compile(cc,QRDIR/'qrcodegen.c')
compile(cc,ROOT/'native/steam/steam_tls.c',strict=True)
compile(cc,ROOT/'native/steam/steam_ui.c',strict=True)
for name in ('steam_session','steam_install','steam_shortcut','steam_emu','steam_client'):
    compile(cxx,ROOT/'native/steam'/(name+'.cpp'),strict=True)
# curl again, with STEAM_UI_HOSTED's TCP option numbers (orbis_net_fix.h, through curl_config.h)
lib=curl_src/'lib';curl_objects=[]
for source in sorted([*lib.glob('*.c'),*[s for d in ('curlx','vauth','vdns','vquic','vssh','vtls') for s in (lib/d).glob('*.c')]]):
    obj=work/'curl'/(source.parent.name+'_'+source.stem+'.o');obj.parent.mkdir(exist_ok=True)
    run([*cc,'-w','-DHAVE_CONFIG_H','-DBUILDING_LIBCURL','-I',ROOT/'native/steam/orbis','-I',curl_src/'include','-I',lib,
         '-c',source,'-o',obj]);curl_objects.append(obj)
run(['llvm-ar-14','rcs',work/'libcurl-hosted.a',*curl_objects])

# one object: what the client pulls from the libraries, clocks renamed, then orbis_clock's pw_steam_*
bundle=work/'bundle.o'
run(['ld.lld','-r','-o',bundle,*objects,work/'libcurl-hosted.a',deps/'lib/libmbedtls.a',deps/'lib/libzstd.a',
     deps/'lib/liblzmadec.a'])
renamed=work/'bundle-clocks.o'
run(['objcopy','--redefine-sym','clock_gettime=pw_steam_clock_gettime','--redefine-sym','clock_getres=pw_steam_clock_getres',
     bundle,renamed])
clock=work/'obj/orbis_clock.o'
run([*cc,'-Wall','-Wextra','-Werror','-c',ROOT/'native/steam/orbis/orbis_clock.c','-o',clock])
joined=work/'joined.o';run(['ld.lld','-r','-o',joined,renamed,clock])
out=work/'steam_client_hosted.o'
# Local: every strong global but the four calls. Weak ones stay weak and global: they are the COMDAT
# copies of inline and template functions (libc++'s, compiled from the same libc++ 21 headers as the
# title's libc++-vk.a). Made local they still win the COMDAT group first on the link line, the
# archive's copy is dropped, and libc++'s own objects then point into a discarded section: W289's link
# failed with "R_X86_64_PC32 out of range" for basic_string's and __hash_table's members. Global and
# weak, the link keeps one copy that every object reaches.
def strong_globals(path):
    listing=subprocess.run(['llvm-nm-14','--defined-only','--extern-only',str(path)],capture_output=True,text=True,check=True).stdout
    names=[]
    for line in listing.splitlines():
        parts=line.split()
        if len(parts)>=3 and parts[1] in 'TDBRCA' and parts[1] not in 'WVwvu':names.append(parts[2])
    return names
localize=work/'localize.txt'
localize.write_text(''.join(name+'\n' for name in strong_globals(joined) if name not in EXPORTS))
# without the DWARF (most of its size); build/steam-hosted/joined.o keeps it for a crash's addresses
run(['objcopy','--strip-debug','--localize-symbols='+str(localize),joined,out])

def symbols(path,undefined):
    flag=['--undefined-only'] if undefined else ['--defined-only']
    listing=subprocess.run(['llvm-nm-14',*flag,'--extern-only',str(path)],capture_output=True,text=True,check=True).stdout
    return {line.split()[-1] for line in listing.splitlines() if line.strip()}
exported=set(strong_globals(out))
if exported!=set(EXPORTS):raise SystemExit('strong global symbols of the object: %s (want %s)'%(sorted(exported),EXPORTS))
# the weak ones may only be C++ names (inline and template members): a weak C name could meet Wine's
# (but the two every clang C++ object carries, Mesa's too: the personality's reference and the terminate helper)
COMPILER_WEAK={'DW.ref.__gxx_personality_v0','__clang_call_terminate'}
weak_c=sorted(name for name in symbols(out,False)-exported-COMPILER_WEAK if not name.startswith('_Z'))
if weak_c:raise SystemExit('weak C symbols in the object: '+', '.join(weak_c))
wine_elves=sorted(ROOT.glob('build/wine-hardware-w*/wine.elf'),key=lambda p:p.stat().st_mtime)
if not wine_elves:raise SystemExit('no build/wine-hardware-w*/wine.elf to check against')
wine=wine_elves[-1]
# what the hardware ELF's link resolves: wine.elf's own symbols (any binding: __dso_handle comes from its
# link script, compiler-rt's helpers are hidden) and its imports, plus whatever its static libraries
# hold that wine.elf hasn't pulled yet (libc++'s regex and locale, libc's getaddrinfo), in its link order
# (tools/link-wine-boot.py, tools/build-wine-hardware.py)
def every_name(path):
    listing=subprocess.run(['llvm-nm-14',str(path)],capture_output=True,text=True,check=True).stdout
    return {line.split()[-1] for line in listing.splitlines() if line.strip() and len(line.split())>=2}
link_libraries=[ROOT/'build/wine-boot/lib/libc.a',SDK/'lib/libc.a',SDK/'lib/libm.a',VK/'sysroot/lib/libc++.a',
                VK/'sysroot/lib/libc++abi.a',SDK/'lib/libclang_rt.builtins-x86_64.a']
available=every_name(wine)|symbols(wine,True)
for library in link_libraries:
    if library.is_file():available|=symbols(library,False)
needed=symbols(out,True)
missing=sorted(needed-available-NEW_IMPORTS)
if missing:raise SystemExit('steam_client_hosted.o needs what %s neither defines nor imports: %s'%(wine.relative_to(ROOT),', '.join(missing)))
new=sorted((needed-available)&NEW_IMPORTS)

# the files for C:\orbis\steam in the prefix, and the helper
prefix=work/'prefix/orbis';steam=prefix/'steam';steam.mkdir(parents=True)
shutil.copyfile(CACERT[0],steam/'cacert.pem')
unpack=work/'gbe-unpack';unpack.mkdir()
run(['7z','x','-y','-o'+str(unpack),GBEDIR/'emu-win-release-vs22.7z','release/regular/x86/steam_api.dll',
     'release/regular/x64/steam_api64.dll'])
for arch,name in (('x86','steam_api.dll'),('x64','steam_api64.dll')):
    shutil.copyfile(unpack/'release/regular'/arch/name,steam/('gbe-%s-%s'%(arch,name)))
run(['tar','-xzf',GBEDIR/'gbe_fork-release-2026_09_27-source.tar.gz','-C',unpack,'gbe_fork-release-2026_09_27/LICENSE'])
shutil.copyfile(unpack/'gbe_fork-release-2026_09_27/LICENSE',steam/'gbe-LICENSE-LGPL-3.0.txt')
(steam/'gbe-SOURCE.txt').write_text('gbe_fork '+GBE_TAG+' (LGPL-3.0)\n'
    'Binary: https://github.com/Detanup01/gbe_fork/releases/download/'+GBE_TAG+'/emu-win-release-vs22.7z\n'
    'Source: https://github.com/Detanup01/gbe_fork/archive/refs/tags/'+GBE_TAG+'.tar.gz\n'
    +''.join('sha256 %s %s\n'%(h,n) for n,h in GBE.items())+
    'Used unmodified: release/regular/x86/steam_api.dll and release/regular/x64/steam_api64.dll.\n')
# The helper's icon. Wine's explorer (programs/explorer/desktop.c, add_launcher) leaves out a Desktop
# link whose IconLocation and target have no icon, so the helper carries one: the Start menu glyph's blue
# disc (RGB 0x66c0f4) with a white hub, drawn here at 16, 32 and 48 pixels with 4x4 supersampling.
import struct
def icon_image(size):
    rows=[];mask=[];sub=4;centre=size/2;outer=size/2-0.5;hub=size*5/32
    for y in range(size-1,-1,-1):  # DIB rows go bottom-up
        row=bytearray();bits=0
        for x in range(size):
            disc=white=0
            for sy in range(sub):
                for sx in range(sub):
                    d=((x+(sx+0.5)/sub-centre)**2+(y+(sy+0.5)/sub-centre)**2)**0.5
                    if d<=outer:disc+=1
                    if d<=hub:white+=1
            alpha=disc/(sub*sub);white=white/max(disc,1)
            r,g,b=(round(0x66+(0xff-0x66)*white),round(0xc0+(0xff-0xc0)*white),round(0xf4+(0xff-0xf4)*white))
            row+=bytes((b,g,r,round(255*alpha)))
            bits=bits<<1|(alpha==0)
        stride=(size+31)//32*4  # AND mask rows: 1 bit per pixel, left-aligned, padded to 32 bits
        rows.append(bytes(row));mask.append((bits<<(stride*8-size)).to_bytes(stride,'big'))
    header=struct.pack('<IiiHHIIiiII',40,size,size*2,1,32,0,0,0,0,0,0)
    return header+b''.join(rows)+b''.join(mask)
images=[(s,icon_image(s)) for s in (16,32,48)]
ico=struct.pack('<HHH',0,1,len(images));offset=6+16*len(images)
for s,data in images:ico+=struct.pack('<BBBBHHII',s,s,0,0,1,32,len(data),offset);offset+=len(data)
ico+=b''.join(data for _,data in images)
(work/'steam-open.ico').write_bytes(ico)
(work/'steam-open.rc').write_text('1 ICON "steam-open.ico"\n')
run(['x86_64-w64-mingw32-windres','-O','coff','steam-open.rc','-o','steam-open-res.o'])
run(['x86_64-w64-mingw32-gcc','-O2','-Wall','-Wextra','-Werror','-mwindows','-Wl,--no-insert-timestamp',
     ROOT/'native/steam/orbis_steam_open.c',work/'steam-open-res.o','-o',prefix/'steam-open.exe','-lntdll'])
# the Desktop link, in tools/make-start-menu.py's .lnk format (the Start menu's item is explorer's own,
# tools/build-explorer-hw.py)
LINK_CLSID=bytes.fromhex('0114020000000000c000000000000046')
def lnk_string(text):return struct.pack('<H',len(text))+text.encode('utf-16-le')
def shortcut(target,description,directory):
    volume=struct.pack('<IIII',17,3,0,16)+b'\0';base=target.encode('ascii')+b'\0';suffix=b'\0'
    header=0x1c;base_at=header+len(volume);suffix_at=base_at+len(base)
    info=struct.pack('<IIIIIII',suffix_at+len(suffix),header,1,header,base_at,0,suffix_at)+volume+base+suffix
    flags=0x2|0x4|0x10|0x40|0x80
    head=struct.pack('<I16sII',0x4c,LINK_CLSID,flags,0x20)+bytes(24)+struct.pack('<IiIHHII',0,0,1,0,0,0,0)
    return head+info+lnk_string(description)+lnk_string(directory)+lnk_string(target)+b'\0\0\0\0'
desktop=work/'prefix/users/orbis/Desktop';desktop.mkdir(parents=True)
(desktop/'Open Steam Client.lnk').write_bytes(shortcut('C:\\orbis\\steam-open.exe','Open Steam Client','C:\\orbis'))

sources=['native/steam/steam_client.cpp','native/steam/steam_install.cpp','native/steam/steam_shortcut.cpp',
         'native/steam/steam_emu.cpp','native/steam/steam_session.cpp','native/steam/steam_ui.c','native/steam/steam_tls.c',
         'native/steam/orbis/orbis_clock.c','native/steam/orbis/orbis_net_fix.h','native/steam/orbis/curl_config.h',
         'native/steam/orbis_steam_open.c','native/steam/mbedtls_user_config.h']
manifest={'build':BUILD,'object':str(out.relative_to(ROOT)),'object_sha256':sha(out),'exports':EXPORTS,
    'checked_against':str(wine.relative_to(ROOT)),'new_imports':new,'playden_revision':REVISION,
    'patches':{p.name:sha(p) for p in sorted((ROOT/'native/steam/patches').glob('*.patch'))},
    'gbe_fork':{'tag':GBE_TAG,**GBE},'qrcodegen':QRCODEGEN,'sources_sha256':{s:sha(ROOT/s) for s in sources},
    'prefix_files':{str(p.relative_to(work/'prefix')):sha(p) for p in sorted((work/'prefix').rglob('*')) if p.is_file()},
    'link_needs':['the vk sysroot libc++/libc++abi the hardware ELF already links','-lSceNet','-lScePad (types only)']}
(work/'manifest.json').write_text(json.dumps(manifest,indent=1))
print(json.dumps(manifest,indent=1))
