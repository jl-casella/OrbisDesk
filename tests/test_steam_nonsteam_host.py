#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run the non-Steam games code (native/steam/steam_nonsteam.cpp) against a made-up console: exes with a
version resource, .lnk shortcuts, game folders on C: and a USB drive, the saved list and the store search."""
import pathlib, shutil, subprocess, tempfile
r=pathlib.Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='orbisdesk-nonsteam-') as temp:
    work=pathlib.Path(temp)
    # the Playden copy the builders compile: upstream plus native/steam/patches, in order
    shutil.copytree(r/'upstream/playden-ps5/src',work/'playden/src')
    for patch in sorted((r/'native/steam/patches').glob('*.patch')):
        subprocess.run(['patch','--fuzz=0','-s','-p1','-i',str(patch)],cwd=work/'playden',check=True)
    subprocess.run(['clang++','-std=c++17','-DSTEAM_HOST','-g','-O1','-fsanitize=address,undefined','-fno-sanitize=vptr',
        '-mllvm','-asan-globals=0','-fno-omit-frame-pointer','-no-pie','-Wall','-Wextra','-Werror',
        '-I'+str(r/'native/steam'),'-I'+str(work/'playden/src'),
        str(r/'tests/steam_nonsteam_host.cpp'),str(r/'native/steam/steam_nonsteam.cpp'),
        str(work/'playden/src/steam/backend/json.cpp'),'-o',str(work/'test')],check=True)
    subprocess.run([str(work/'test'),str(work/'sandbox')],check=True,timeout=120)
