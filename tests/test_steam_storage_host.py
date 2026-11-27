#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run the real Steam storage/record/shortcut code with deterministic I/O faults."""
import pathlib, subprocess, tempfile
r=pathlib.Path(__file__).resolve().parents[1]
def patched_playden(work):
    # the Playden copy the builders compile: upstream plus native/steam/patches, in order
    import shutil
    shutil.copytree(r/'upstream/playden-ps5/src',work/'playden/src')
    for patch in sorted((r/'native/steam/patches').glob('*.patch')):
        subprocess.run(['patch','--fuzz=0','-s','-p1','-i',str(patch)],cwd=work/'playden',check=True)
    return work/'playden/src'
with tempfile.TemporaryDirectory(prefix='orbisdesk-storage-') as temp:
    work=pathlib.Path(temp)
    playden=patched_playden(work)
    sources=['tests/steam_storage_host.cpp','native/steam/steam_storage.cpp',
             'native/steam/steam_install.cpp','native/steam/steam_shortcut.cpp',
             str(playden/'steam/backend/json.cpp'),
             str(playden/'steam/backend/game_path.cpp')]
    subprocess.run(['clang++','-std=c++17','-DSTEAM_HOST','-DSTEAM_STORAGE_TEST',
        '-g','-O1','-fsanitize=address,undefined','-fno-sanitize=vptr',
        '-mllvm','-asan-globals=0','-fno-omit-frame-pointer','-no-pie',
        '-ffunction-sections','-fdata-sections','-Wl,--gc-sections','-pthread',
        '-I'+str(r/'native/steam'),'-I'+str(playden),
        '-I'+str(r/'build/steam-deps-ps4/prefix/include'),
        *[s if s.startswith('/') else str(r/s) for s in sources],'-o',str(work/'test')],check=True)
    subprocess.run([str(work/'test'),str(work/'sandbox')],check=True,timeout=120)
