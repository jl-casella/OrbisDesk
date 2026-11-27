#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Steam Big Picture's screens on the host (docs/STEAM_BIG_PICTURE.md): tests/steam_bp_gallery.cpp draws every
screen from made-up views with the real renderer (native/steam/steam_draw.c, steam_bp.cpp) and checks each
frame's text; covers are decoded, saved and read back (steam_covers.cpp). Three runs: Tahoma at the title's
1280x720, Tahoma at the standalone title's 1920x1080, and the 5x7 bitmap fallback without fonts.
    python3 tests/test_steam_bigpicture_host.py [--out DIR]   (DIR keeps the PNG snapshots to look at)
Needs clang/clang++, the pinned qrcodegen and stb copies (.deps) and Wine's Tahoma (.deps/wine/source/fonts)."""
import argparse,pathlib,shutil,subprocess,tempfile
r=pathlib.Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--out');args=parser.parse_args()
qr=r/'.deps/steam/downloads/qrcodegen-1.8.0';fonts=r/'.deps/wine/source/fonts'
for need in (qr/'qrcodegen.c',r/'.deps/steam/downloads/stb/stb_image.h',
             r/'.deps/sdk/OpenOrbis/PS4Toolchain/include/stb/stb_truetype.h',fonts/'tahoma.ttf',fonts/'tahomabd.ttf'):
    if not need.is_file():raise SystemExit('missing '+str(need))
with tempfile.TemporaryDirectory(prefix='orbisdesk-bigpicture-') as temp:
    work=pathlib.Path(temp);out=pathlib.Path(args.out) if args.out else work/'shots'
    # the Playden copy the builders compile (upstream plus native/steam/patches): covers read the store's JSON
    shutil.copytree(r/'upstream/playden-ps5/src',work/'playden/src')
    for patch in sorted((r/'native/steam/patches').glob('*.patch')):
        subprocess.run(['patch','--fuzz=0','-s','-p1','-i',str(patch)],cwd=work/'playden',check=True)
    inc=['-I'+str(r/'native/steam'),'-I'+str(work/'playden/src'),'-I'+str(qr),'-I'+str(r/'.deps/steam/downloads/stb'),
         '-I'+str(r/'.deps/sdk/OpenOrbis/PS4Toolchain/include/stb')]
    flags=['-DSTEAM_HOST','-g','-O1','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-sanitize=vptr','-mllvm','-asan-globals=0']
    subprocess.run(['clang',*flags,*inc,'-c',str(r/'native/steam/steam_draw.c'),'-o',str(work/'draw.o')],check=True)
    subprocess.run(['clang','-g','-O1','-c',str(qr/'qrcodegen.c'),'-o',str(work/'qr.o')],check=True)
    subprocess.run(['clang++','-std=c++17',*flags,*inc,str(r/'native/steam/steam_bp.cpp'),
                    str(r/'native/steam/steam_covers.cpp'),str(r/'tests/steam_bp_gallery.cpp'),
                    str(work/'playden/src/steam/backend/json.cpp'),
                    str(work/'draw.o'),str(work/'qr.o'),'-pthread','-no-pie','-o',str(work/'gallery')],check=True)
    for name,font,size in (('1280x720',str(fonts),('1280','720')),('1920x1080',str(fonts),('1920','1080')),
                           ('bitmap',  '-',('1280','720'))):
        target=out/name;target.mkdir(parents=True,exist_ok=True)
        subprocess.run([str(work/'gallery'),str(target),font,*size],check=True,timeout=120)
    print('PASS Big Picture screens, text pages, QR and covers'+(' (snapshots in %s)'%out if args.out else ''))
