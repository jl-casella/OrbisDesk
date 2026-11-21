#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Build isolated process-discovery and PoP-shaped Win32 fixtures under WSL."""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SDK = ROOT / '.deps/sdk/OpenOrbis/PS4Toolchain'
WORK = ROOT / 'build/process-probes'
OUT = ROOT / 'out/process-probes'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    commands = []

    def run(command):
        command = list(map(str, command))
        commands.append(command)
        subprocess.run(command, check=True, cwd=ROOT,
                       env=dict(os.environ, OO_PS4_TOOLCHAIN=str(SDK)))

    for name, base, child, fixed in (
        ('family-parent.exe', '0x400000', False, True),
        ('family-child.exe', '0x400000', True, True),
        ('family-control.exe', '0x24000000', False, False),
    ):
        command = ['i686-w64-mingw32-gcc', '-O2', '-Wall', '-Wextra', '-Werror',
                   '-Wno-missing-field-initializers', '-ffreestanding', '-fno-stack-protector',
                   '-fno-asynchronous-unwind-tables', '-nostdlib']
        if child:
            command.append('-DFAMILY_CHILD')
        command += [ROOT / 'fixtures/win32/process_family.c',
                    '-Wl,--entry,_entry,--image-base,' + base + ',--no-insert-timestamp,' +
                    ('--disable-reloc-section,--disable-dynamicbase' if fixed else '--enable-reloc-section'),
                    '-lkernel32', '-o', OUT / name]
        run(command)
        header = subprocess.check_output(['i686-w64-mingw32-objdump', '-p', OUT / name], text=True)
        (WORK / (name + '.headers.txt')).write_text(header)
        # The test must really have fixed, identical bases rather than relocated images.
        data = (OUT / name).read_bytes()
        pe = struct.unpack_from('<I', data, 0x3c)[0]
        if struct.unpack_from('<H', data, pe + 4)[0] != 0x14c:
            raise RuntimeError('Fixture is not PE32: ' + name)
        if struct.unpack_from('<I', data, pe + 52)[0] != int(base, 16):
            raise RuntimeError('Wrong fixture image base: ' + name)
        if fixed and (not struct.unpack_from('<H', data, pe + 22)[0] & 1 or
                      any(struct.unpack_from('<II', data, pe + 24 + 96 + 5 * 8))):
            raise RuntimeError('Fixture relocations were not stripped: ' + name)
        if 'DLL Name: KERNEL32.dll' not in header and 'DLL Name: kernel32.dll' not in header:
            raise RuntimeError('Missing kernel32 fixture dependency')

    flags = ['--target=x86_64-pc-freebsd12-elf', '-fPIC', '-march=btver2', '-O2', '-g',
             '-Wall', '-Wextra', '-Werror', '-isysroot', SDK, '-isystem', SDK / 'include']
    run(['clang', *flags, '-c', ROOT / 'native/process_capabilities.c', '-o', WORK / 'capabilities.o'])
    run(['ld.lld', '-pie', '--no-undefined', '--eh-frame-hdr', '--script', SDK / 'link.x',
         '-o', OUT / 'capabilities.elf', WORK / 'capabilities.o', SDK / 'lib/crt1.o',
         '-L', SDK / 'lib', '-lc', '-lkernel'])
    run([SDK / 'bin/linux/create-fself', '-in=' + str(OUT / 'capabilities.elf'),
         '-out=' + str(OUT / 'capabilities.oelf'), '--eboot', OUT / 'eboot.bin',
         '--paid', '0x3800000000000011'])
    inputs = [ROOT / 'fixtures/win32/process_family.c', ROOT / 'native/process_capabilities.c', Path(__file__).resolve()]
    outputs = [OUT / name for name in ('family-parent.exe', 'family-child.exe', 'family-control.exe',
                                       'capabilities.elf', 'capabilities.oelf', 'eboot.bin')]
    manifest = {'schema_version': 1, 'commands': commands,
                'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                'inputs': {str(p.relative_to(ROOT)): sha(p) for p in inputs},
                'artifacts': {p.name: sha(p) for p in outputs},
                'native_spawn_implemented': False, 'runtime_verified': False}
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest))


if __name__ == '__main__':
    main()
