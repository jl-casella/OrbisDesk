#!/usr/bin/env python3
"""Build packaged graphics samples and convert the pinned CC0 wallpaper on Linux."""
import json
from pathlib import Path
from common import ROOT, RESULTS, run, sha, write_json


def main():
    home = Path.home() / 'vk-h0'
    headers = home / 'vk-headers/include'
    libs = home / 'build/vk-loader/loader'
    # The window demos the Start menu opens (vkspin64, glxgears) are GUI programs, as the binaries every build up
    # to W303 shipped: built as console programs they open a console window behind them, and glxgears (made with
    # MinGW g++) exited with status 1 on the console. The probes stay console programs.
    for name, gui in (('vkprobe64', False), ('vkspin64', True), ('vklayers64', False)):
        run(['x86_64-w64-mingw32-gcc', '-O2', '-Wl,--no-insert-timestamp', *(['-mwindows'] if gui else []),
             '-I' + str(headers), ROOT / 'fixtures/win32' / (name + '.c'),
             '-L' + str(libs), '-lvulkan-1', '-luser32', '-lgdi32', '-lm',
             '-o', ROOT / 'out' / (name + '.exe')], RESULTS / ('fixture-' + name + '.log'))
    run(['x86_64-w64-mingw32-gcc', '-O2', '-static-libgcc', '-Wl,--no-insert-timestamp',
         ROOT / 'fixtures/win32/gltest64.c', '-lopengl32', '-lgdi32', '-luser32', '-lm',
         '-o', ROOT / 'out/gltest64.exe'], RESULTS / 'fixture-gltest64.log')
    # glxgears as G001 built it: llvm-mingw (UCRT, libc++ linked in), a GUI program
    run([home / 'llvm-mingw/bin/x86_64-w64-mingw32-clang++', '-O2', '-static', '-mwindows', '-Wl,--no-insert-timestamp',
         ROOT / 'fixtures/win32/glxgears/main.cpp', '-lopengl32', '-lgdi32', '-luser32',
         '-o', ROOT / 'out/glxgears.exe'], RESULTS / 'fixture-glxgears.log')
    from PIL import Image
    source = ROOT / '.deps/wallpaper-cc0/green-hill.jpg'
    assets = json.loads((ROOT / 'product-assets.lock.json').read_text())['downloads']
    if sha(source) != assets['wallpaper']['sha256']:
        raise ValueError('Wallpaper input differs')
    destination = ROOT / 'out/wallpaper-cc0'
    destination.mkdir()
    with Image.open(source) as photo:
        photo = photo.convert('RGB').crop((0, 316, 6016, 3700))
        photo.resize((1280, 720), Image.Resampling.BICUBIC).save(destination / 'orbis-hills.bmp')
    write_json(destination / 'manifest.json', {'wallpaper': {
        'path': 'orbis-hills.bmp', 'sha256': sha(destination / 'orbis-hills.bmp'),
        'width': 1280, 'height': 720, 'source': assets['wallpaper'],
        'license': 'CC0 / public domain (goodfreephotos.com)',
        'conversion': 'Pillow RGB, centre crop 6016x3384 at 0,316, bicubic 1280x720, BMP'}})


if __name__ == '__main__':
    main()
