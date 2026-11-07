#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Reproduce unpatched Wine Unix-side build against actual OpenOrbis headers.
Never use host headers/libraries to conceal an unavailable PS4 interface.
"""
import hashlib
import json
import os
import pathlib
import shlex
import subprocess
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
source = ROOT / '.deps/wine/source'
work = ROOT / '.deps/wine/ps4-unix'
sdk = ROOT / '.deps/sdk/OpenOrbis/PS4Toolchain'
work.mkdir(parents=True, exist_ok=True)
commit = json.loads((ROOT / 'sources.lock.json').read_text())['sources']['wine']['commit']
actual = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
if actual != commit:
    raise SystemExit('Wrong Wine revision')
cc = work / 'orbis-cc'
flags = ['clang', '--target=x86_64-pc-freebsd12-elf', '-fPIC', '-march=btver2',
         '-isysroot', str(sdk), '-isystem', str(sdk / 'include')]
link = ['-nostdlib', '-fuse-ld=lld', '-Wl,--script,'+str(sdk/'link.x'),
        '-L'+str(sdk/'lib'), str(sdk/'lib/crt1.o'), '-lc', '-lkernel']
cc.write_text('#!/bin/sh\ncase " $* " in\n*" -c "*|*" -E "*|*" -S "*|*" --version "*|*" -v "*) exec '+
              shlex.join(flags)+' "$@";;\n*) exec '+shlex.join(flags)+' "$@" '+shlex.join(link)+';;\nesac\n')
cc.chmod(0o755)
command = [str(source/'configure'), '--host=x86_64-unknown-freebsd12', '--build=x86_64-pc-linux-gnu',
           '--enable-archs=i386,x86_64', '--disable-tests', '--without-x', '--without-freetype',
           '--without-fontconfig', '--without-alsa', '--without-pulse', '--without-dbus',
           '--without-gstreamer', '--without-sdl', '--without-udev', '--without-usb',
           '--without-v4l2', '--without-wayland', '--without-opengl', '--without-oss',
           '--without-pcap', '--without-pcsclite', '--without-sane', '--without-krb5',
           '--without-gphoto', '--without-netapi', '--without-inotify', '--without-capi',
           '--without-cups', '--without-gssapi', '--without-ffmpeg', '--without-gnutls',
           '--with-wine-tools='+str(ROOT/'.deps/wine/runtime/build'), 'CC='+str(cc),
           'CXX='+str(cc), 'CPP='+str(cc)+' -E', 'LD=ld.lld']
start = time.monotonic()
with (work/'configure.log').open('w') as log:
    result = subprocess.run(command, cwd=work, stdout=log, stderr=subprocess.STDOUT,
                            env=dict(os.environ, LC_ALL='C', TZ='UTC'))
stage = 'configure'
if not result.returncode:
    stage = 'compile-ntdll'
    with (work/'make-ntdll.log').open('w') as log:
        result = subprocess.run(['make', '-j8', 'dlls/ntdll/ntdll.so'], cwd=work, stdout=log, stderr=subprocess.STDOUT)
report = {'schema_version': 1, 'wine_commit': actual, 'status': 'blocked' if result.returncode else 'built-unvalidated',
          'stage': stage, 'exit_code': result.returncode, 'duration_seconds': round(time.monotonic()-start, 3),
          'command': command, 'compiler_wrapper_sha256': hashlib.sha256(cc.read_bytes()).hexdigest(),
          'environment': 'OpenOrbis cross-build, not emulator execution', 'logs': '.deps/wine/ps4-unix/',
          'hardware_status': 'pending', 'prospero_patches_applied': False}
(ROOT/'out/wine-unix-probe.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(report))
raise SystemExit(result.returncode)
