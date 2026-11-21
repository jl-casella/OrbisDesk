#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""PoP Phase D: everything the separate Wine process needs under /data/orbisdesk (docs/POP_SEPARATE_PROCESS.md).

Builds, into build/pop-wine-child/:
  pop-wine-child.prx   the title's W303 Wine unix side as a fake-signed PRX: out/wine-hardware-w303/manifest.json's
                       link_command without the title-only parts (its main and exit/write wrappers, pad, overlay,
                       Steam, Mesa/GPU sink), with native/pop_wine_child.c as entry, native/pop_child_sink.c as the
                       display sink and native/pop_wine_child_stubs.c
  pop-prx-probe.prx    P016: OpenOrbis code hosted through the system linker (native/pop_prx_probe.c)
  pop-wine-join.elf    the payload-SDK child the loader starts (native/process_p014_child.c)
  separate_d1.exe, separate_d2.exe, separate_launcher.exe, separate_game.exe   test programs (fixtures/win32)
and manifest.json with every output's sha256 and the inputs' hashes. Run after tools/build-wine-hardware.py (its
link command and objects are this PRX's input). tools/build-wine-hardware.py also builds pop-wine-child.prx itself and
ships it in the package (orbisdesk/pop-wine-child.prx, installed like the runtime); tools/upload-pop-separate.py
uploads these outputs for development and the test programs.
"""
import hashlib, json, os, pathlib, re, subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
SDK = ROOT / '.deps/sdk/OpenOrbis/PS4Toolchain'
PAYLOAD_SDK = ROOT / '.deps/process-loader/sdk/ps4-payload-sdk'
WORK = ROOT / 'build/pop-wine-child'
PREFIX_MAP = '-ffile-prefix-map=%s=.' % ROOT
HW = 'build/wine-hardware-w303/'


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def run(command, **kw):
    subprocess.run(list(map(str, command)), check=True, **kw)


def fself_lib(elf, prx):
    run([SDK / 'bin/linux/create-fself', '-in=' + elf.name, '-out=' + elf.stem + '.oelf', '--lib=' + prx.name,
         '--paid', '0x3800000000000011'], cwd=elf.parent, env=dict(os.environ, OO_PS4_TOOLCHAIN=str(SDK)),
        stdout=subprocess.DEVNULL)


def build_wine_prx(command=None, request_writer=None, eboot_sha256=None):
    """The Wine PRX from the title's link command. tools/build-wine-hardware.py calls this with its own command
    and request writer while it builds, and ships the PRX in the package (2026-11-20); run alone, this reads both
    from the last build's manifest."""
    if command is None:
        manifest = json.loads((ROOT / 'out/wine-hardware-w303/manifest.json').read_text())
        command, request_writer, eboot_sha256 = manifest['link_command'], manifest['request_writer'], manifest.get('eboot_sha256')
    WORK.mkdir(parents=True, exist_ok=True)
    flags = json.loads((ROOT / 'build/wine-boot/link-report.json').read_text())['helper_compile_flags']
    drop = {HW + 'wine_hardware.o', HW + 'hw_pad.o', HW + 'hw_overlay.o', 'build/steam-hosted/steam_client_hosted.o',
            HW + 'wine_boot_entry.o', 'build/wine-boot/wine_boot_services.o', '.deps/sdk/OpenOrbis/PS4Toolchain/lib/crt1.o',
            HW + 'hw_sink_gpu.o'}   # D.4: RADV, its probe and runtime and libc++ stay; the VideoOut sink does not
    title_wraps = {'--wrap=' + n for n in ('exit', '_exit', 'sceKernelDebugOutText', 'write', 'vfprintf', 'fprintf', 'fputs', 'fwrite')}
    # Use exactly the same bounded request writer and redirected Wine object as the title.
    for key in ('client_object', 'writer_object'):
        path = ROOT / request_writer[key]
        if command.count(str(path)) != 1 or sha(path) != request_writer[key + '_sha256']:
            raise SystemExit(f'{path} differs from the title request writer manifest')
    out, i = [], 0
    while i < len(command):
        arg = command[i]
        rel = arg.replace(str(ROOT) + '/', '')
        if arg == '-o':
            out += ['-o', str(WORK / 'pop_wine_child.elf')]; i += 2; continue
        if arg == '--script':
            # the SDK script with W303's collection fixes, without its fixed base: a PRX is relocated
            text = (SDK / 'link.x').read_text()
            for old, new in (('*(.init_array);', 'KEEP(*(SORT_BY_INIT_PRIORITY(.init_array.*))); KEEP(*(.init_array));'),
                             ('*(.data)', '*(.data .data.*)'), ('*(.tdata)', '*(.tdata .tdata.*)'),
                             ('*(.tbss)', '*(.tbss .tbss.*)'),
                             ('*(.bss .bss.*)', '__pop_bss_start = .; *(.bss .bss.*) __pop_bss_end = .;')):
                if old not in text:
                    raise SystemExit('unexpected SDK link.x: no ' + old)
                text = text.replace(old, new)
            (WORK / 'link.x').write_text(text)
            out += ['--script', str(WORK / 'link.x')]; i += 2; continue
        if rel in drop or arg in title_wraps:
            i += 1; continue
        if rel == HW + 'sink.o':
            out.append(str(WORK / 'pop_child_sink.o')); i += 1; continue
        out.append(arg); i += 1
    objects = []
    for source, obj in (('native/pop_child_sink.c', 'pop_child_sink.o'), ('native/pop_wine_child.c', 'pop_wine_child.o'),
                        ('native/pop_wine_child_stubs.c', 'pop_wine_child_stubs.o')):
        run([*flags, '-DPOP_CHILD_GPU', '-I' + str(ROOT / 'native'), '-c', ROOT / source, '-o', WORK / obj])
        if obj != 'pop_child_sink.o':
            objects.append(str(WORK / obj))
    # musl's aligned allocators come in strongly through Mesa/libc++ in the title; here nothing else asks for them
    wraps = ['exit', 'sceKernelDebugOutText', '__assert_fail', 'mmap', 'pread', 'mprotect', 'munmap', 'fstat',
             'sceKernelMapFlexibleMemory', 'sceKernelMapDirectMemory', 'pw_wine_poll',
             'virtual_map_user_shared_data', 'virtual_set_large_address_space', 'nl_langinfo', 'sceKernelLoadStartModule',
             'NtCreateUserProcess', 'NtQueryInformationProcess',   # D.5: CreateProcess returns (pop_wine_child_stubs.c)
             'write']   # D.7: capture simple writes, alongside the Wine request writer above
    out[1:1] = ['-u', 'aligned_alloc', '-u', '__memalign', '-u', 'memalign', '-u', 'posix_memalign',
                '--export-dynamic-symbol=pop_wine_child_run', '--export-dynamic-symbol=pop_wine_child_run_job',
                *('--wrap=' + w for w in wraps), *objects]
    lib_at = next(k for k, a in enumerate(out) if a.startswith('-L'))
    out.insert(lib_at, str(SDK / 'lib/crtlib.o'))
    result = subprocess.run(out, capture_output=True, text=True)
    (WORK / 'link.log').write_text(result.stdout + result.stderr)
    missing = sorted(set(re.findall(r'undefined(?: hidden)? symbol: ([^\n]+)', result.stdout + result.stderr)))
    if result.returncode or missing:
        raise SystemExit('PRX link failed; undefined: %s (build/pop-wine-child/link.log)' % ', '.join(missing))
    fself_lib(WORK / 'pop_wine_child.elf', WORK / 'pop-wine-child.prx')
    return {'base_link_eboot_sha256': eboot_sha256, 'wraps': wraps,
            'request_writer': request_writer}


def build_probe_prx():
    flags = ['clang', '--target=x86_64-pc-freebsd12-elf', '-D__ORBIS__', '-fPIC', '-O2', '-funwind-tables',
             '-isysroot', str(SDK), '-isystem', str(SDK / 'include'), PREFIX_MAP]
    run([*flags, '-c', ROOT / 'native/pop_prx_probe.c', '-o', WORK / 'pop_prx_probe.o'])
    run(['ld.lld', '-m', 'elf_x86_64', '-pie', '--script', SDK / 'link.x', '--eh-frame-hdr',
         '--export-dynamic-symbol=pop_prx_probe', '-o', WORK / 'pop_prx_probe.elf', WORK / 'pop_prx_probe.o',
         '-L' + str(SDK / 'lib'), '-lc', '-lkernel', SDK / 'lib/crtlib.o'])
    fself_lib(WORK / 'pop_prx_probe.elf', WORK / 'pop-prx-probe.prx')


def build_child():
    run([PAYLOAD_SDK / 'bin/orbis-clang', '-Wall', '-O2', PREFIX_MAP, '-I', ROOT / 'native', '-o',
         WORK / 'pop-wine-join.elf', ROOT / 'native/process_p014_child.c'],
        cwd=ROOT, env=dict(os.environ, PS4_PAYLOAD_SDK=str(PAYLOAD_SDK)))


def build_fixtures():
    common = ['-O2', '-Wall', '-Wl,--no-insert-timestamp']
    fixed = ['-Wl,--image-base,0x400000', '-Wl,--disable-dynamicbase']
    jobs = (('x86_64-w64-mingw32-gcc', [*fixed], 'separate_d1.c', 'separate_d1.exe'),
            ('x86_64-w64-mingw32-gcc', ['-mwindows'], 'separate_d2.c', 'separate_d2.exe'),
            ('i686-w64-mingw32-gcc', [*fixed], 'separate_pair.c', 'separate_launcher.exe'),
            ('i686-w64-mingw32-gcc', [*fixed, '-mwindows', '-DSEPARATE_GAME'], 'separate_pair.c', 'separate_game.exe'),
            ('i686-w64-mingw32-gcc', [*fixed, '-DSEPARATE_INVERSE'], 'separate_pair.c', 'separate_inverse.exe'))
    for compiler, extra, source, exe in jobs:
        run([compiler, *common, *extra, '-o', WORK / exe, ROOT / 'fixtures/win32' / source])


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    wine = build_wine_prx()
    build_probe_prx()
    build_child()
    build_fixtures()
    outputs = ['pop-wine-child.prx', 'pop-prx-probe.prx', 'pop-wine-join.elf', 'separate_d1.exe', 'separate_d2.exe',
               'separate_launcher.exe', 'separate_game.exe', 'separate_inverse.exe']
    inputs = ['native/pop_wine_child.c', 'native/pop_child_sink.c', 'native/pop_wine_child_stubs.c', 'native/pop_prx_probe.c',
              'platform/ps4/pw_wine_request_write.c',
              'native/process_p014_child.c', 'native/pop_separate.h', 'native/pop_wine_join_core.h', 'native/pop_wine_proto.h',
              'native/pop_separate_window.h', 'fixtures/win32/separate_d1.c', 'fixtures/win32/separate_d2.c',
              'fixtures/win32/separate_pair.c', 'tools/build-pop-wine-child.py']
    manifest = {'schema_version': 1, 'remote_dir': '/data/orbisdesk', **wine,
                'outputs': {name: {'sha256': sha(WORK / name), 'bytes': (WORK / name).stat().st_size} for name in outputs},
                'inputs': {name: sha(ROOT / name) for name in inputs}}
    (WORK / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    for name, entry in manifest['outputs'].items():
        print(name, entry['bytes'], entry['sha256'][:16])


if __name__ == '__main__':
    main()
