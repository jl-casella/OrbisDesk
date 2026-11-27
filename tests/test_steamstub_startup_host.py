#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Execute the real startup helper using Win32 fixtures in an isolated Wine prefix.

Does not execute games or establish PS4 acceptance. Needs a configured Wine host,
llvm-mingw and tools/build-steamstub-addon.py outputs.
"""
import argparse
import contextlib
import hashlib
import json
import os
import pathlib
import shutil
import struct
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--wine', type=pathlib.Path, required=True)
parser.add_argument('--toolchain', type=pathlib.Path, default=pathlib.Path.home() / 'vk-h0/llvm-mingw')
parser.add_argument('--variant-exe', type=pathlib.Path, help='private PE input: copy its .bind into a non-executing fixture')
args = parser.parse_args()
results = []
def stop_fixture_server(wine, env):
    for parent in (wine.parent, wine.parent.parent):
        server = parent / 'server/wineserver'
        if server.is_file():
            subprocess.run([str(server), '-k'], env=env, capture_output=True, timeout=10)
            return

with contextlib.ExitStack() as resources:
    temp = resources.enter_context(tempfile.TemporaryDirectory(prefix='orbisdesk-steamstub-'))
    work = pathlib.Path(temp)
    prefix = work / 'prefix'
    env = dict(os.environ, WINEPREFIX=str(prefix), WINEDEBUG='-all', WINEDLLOVERRIDES='winemenubuilder.exe=d',
               DISPLAY='', WAYLAND_DISPLAY='')
    for key in ('WINE_PS4_GUESTS', 'WINE_PS4_EXTERNAL_PREFIX', 'WINESERVERSOCKET', 'WINEARCH'):
        env.pop(key, None)
    resources.callback(stop_fixture_server, args.wine, env)
    # All writes are in the temporary prefix; do not use the user's Wine prefix.
    first = subprocess.run([str(args.wine), 'cmd', '/c', 'exit'], env=env, capture_output=True, timeout=90)
    if first.returncode:
        raise RuntimeError(first.stderr.decode(errors='replace'))
    dll_dir = prefix / 'drive_c/orbis/steam/coldclient'
    dll_dir.mkdir(parents=True)
    (prefix / 'dosdevices/z:').unlink(missing_ok=True)
    data = work / 'data'; (data / 'orbisdesk').mkdir(parents=True)
    (prefix / 'dosdevices/z:').symlink_to(data)
    for target, arch in (('i686', 'x86'), ('x86_64', 'x64')):
        compiler = args.toolchain / 'bin' / (target + '-w64-mingw32-clang')
        exe = prefix / 'drive_c' / ('startup-' + arch + '.exe')
        subprocess.run([str(compiler), '-O1', '-Wall', '-Wextra', '-Werror',
                        '-I' + str(ROOT / 'platform/ps4'), str(ROOT / 'tests/steamstub_startup_fixture.c'),
                        '-lntdll', '-o', str(exe)], check=True)
        before = hashlib.sha256(exe.read_bytes()).hexdigest()
        payload = dll_dir / ('orbisdesk_steamstub_' + arch + '.dll')
        payload.unlink(missing_ok=True)
        for mode in ('disabled', 'invalid', 'missing', 'loaded', 'unsupported'):
            if mode == 'loaded':
                source = work / 'test-dll.c'
                source.write_text('#include <windows.h>\nBOOL WINAPI DllMain(HINSTANCE h,DWORD why,void *r)'
                                  '{if(why==DLL_PROCESS_ATTACH)SetEnvironmentVariableW(L"PW_STUB_TEST_ATTACHED",L"1");return TRUE;}\n')
                subprocess.run([str(compiler), '-shared', str(source), '-o', str(payload)], check=True)
            elif mode == 'unsupported':
                shutil.copyfile(ROOT / 'build/steamstub-addon' / payload.name, payload)
            test = subprocess.run([str(args.wine), 'C:\\' + exe.name, mode], env=env,
                                  capture_output=True, timeout=30)
            assert test.returncode == 0, (arch, mode, test.returncode, test.stderr.decode(errors='replace'))
            assert b'PASS startup fixture' in test.stdout, (arch, mode, test.stdout)
            assert hashlib.sha256(exe.read_bytes()).hexdigest() == before, 'fixture EXE changed on disk'
            results.append({'arch': arch, 'case': mode, 'status': 'passed',
                            'stderr': test.stderr.decode(errors='replace')})
        if args.variant_exe and arch == 'x86':
            raw = args.variant_exe.read_bytes()
            pe = struct.unpack_from('<I', raw, 60)[0]
            machine, sections = struct.unpack_from('<HH', raw, pe + 4)
            assert machine == 0x14c, 'this optional fixture expects a PE32 input'
            optional_size = struct.unpack_from('<H', raw, pe + 20)[0]
            bind = None
            for index in range(sections):
                offset = pe + 24 + optional_size + 40 * index
                if raw[offset:offset + 8].rstrip(b'\0') == b'.bind':
                    size, start = struct.unpack_from('<II', raw, offset + 16)
                    assert start + size <= len(raw)
                    bind = raw[start:start + size]
            assert bind, 'input has no .bind'
            blob = work / 'private-bind.bin'
            blob.write_bytes(bind)
            source = work / 'private-bind-fixture.S'
            # Same section protections as the wrapper code: VirtualQuery must
            # see one executable .bind region, as it does in the input image.
            source.write_text('.section .bind,"xr"\n.globl _pw_fixture_bind\n_pw_fixture_bind:\n.incbin "' + str(blob) + '"\n')
            armed = prefix / 'drive_c/variant-fixture.exe'
            subprocess.run([str(compiler), '-O1', '-DPW_STUB_VARIANT', '-I' + str(ROOT / 'platform/ps4'),
                            str(ROOT / 'tests/steamstub_startup_fixture.c'), str(source), '-Wl,--entry,_pw_fixture_entry',
                            '-lntdll', '-o', str(armed)], check=True)
            original_hash = hashlib.sha256(armed.read_bytes()).hexdigest()
            result = subprocess.run([str(args.wine), 'C:\\' + armed.name, 'armed'], env=env, capture_output=True, timeout=30)
            assert result.returncode == 0, ('armed lifecycle', result.returncode, result.stderr.decode(errors='replace'))
            assert hashlib.sha256(armed.read_bytes()).hexdigest() == original_hash
            results.append({'arch': arch, 'case': 'recognized_bind_arm_restore', 'status': 'passed',
                            'stderr': result.stderr.decode(errors='replace')})
    log = data / 'orbisdesk/steamstub-startup.log'
    assert log.exists() and 'phase=not_armed' in log.read_text(), 'real addon did not report unsupported input'
    if args.variant_exe:
        assert 'phase=armed' in log.read_text() and 'phase=restore' in log.read_text()
    report = ROOT / 'reports/steamstub-startup-host.json'
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({'classification': 'host Wine fixtures, not PS4', 'cases': results,
                                  'addon_log': log.read_text()}, indent=2) + '\n')
print('PASS', len(results), 'startup cases; EXEs unchanged on disk; real unsupported payload rejected')
