#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run the Steam client's library cache code (round trip, account check, damaged files, sign-out)."""
import pathlib, shutil, subprocess, tempfile
r=pathlib.Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='orbisdesk-library-cache-') as temp:
    work=pathlib.Path(temp)
    # the Playden copy the builders compile: upstream plus native/steam/patches, in order
    shutil.copytree(r/'upstream/playden-ps5/src',work/'playden/src')
    for patch in sorted((r/'native/steam/patches').glob('*.patch')):
        subprocess.run(['patch','--fuzz=0','-s','-p1','-i',str(patch)],cwd=work/'playden',check=True)
    subprocess.run(['clang++','-std=c++17','-g','-O1','-fsanitize=address,undefined','-fno-sanitize=vptr',
        '-mllvm','-asan-globals=0','-fno-omit-frame-pointer','-no-pie','-Wall','-Wextra','-Werror',
        '-I'+str(r/'native/steam'),'-I'+str(work/'playden/src'),
        str(r/'tests/steam_library_cache_host.cpp'),'-o',str(work/'test')],check=True)
    subprocess.run([str(work/'test'),str(work/'sandbox')],check=True,timeout=120)
