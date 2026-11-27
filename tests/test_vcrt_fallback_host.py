#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""VC++ runtime fallback host check (docs/VCRUNTIME_FALLBACK.md).

1. tools/console_state.py's rule: which runtime paths are VC++ runtime files, and the Wine builtin signature.
2. Builds tests/vcrt_fallback_host_check.c with the host C compiler and runs it: native/hw_install.h's installer
   keeps a Microsoft copy, restores a missing one on every start and leaves present copies alone, against
   temporary folders standing in for /app0/runtime and /data.
3. With a built runtime (optional argument: its root, e.g. build/wine-hardware-w303/runtime), every VC++ runtime
   file in it must be a Wine builtin, as tools/build-wine-hardware.py requires.
Host model only: no console, Wine or MSI.

    python3 tests/test_vcrt_fallback_host.py [runtime-root]
"""
import os, pathlib, shutil, subprocess, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from console_state import is_vcrt_file, is_wine_builtin, vcrt_fallback_path  # noqa: E402

S32 = 'wine-prefix/drive_c/windows/system32/'
W64 = 'wine-prefix/drive_c/windows/syswow64/'


def check_rule():
    yes = [W64 + 'vcruntime140.dll', S32 + 'vcruntime140_1.dll', W64 + 'msvcp140_atomic_wait.dll',
           W64 + 'MSVCP140.DLL', S32 + 'concrt140.dll', S32 + 'vccorlib140.dll', S32 + 'vcomp140.dll',
           S32 + 'msvcr120_app.dll', S32 + 'msvcp100.dll', S32 + 'atl110.dll', S32 + 'mfc140u.dll']
    no = [S32 + 'msvcrt.dll', W64 + 'msvcrt40.dll', S32 + 'ucrtbase.dll', S32 + 'kernel32.dll',
          'wine-prefix/drive_c/Program Files/SeaMonkey/msvcp140.dll', 'wine/lib/wine/i386-windows/msvcp140.dll',
          W64 + 'sub/vcruntime140.dll', S32 + 'msvcp90.dll', W64 + 'msvcr80.dll', S32 + 'atl80.dll',
          'wine/lib/wine/vcrt-fallback/syswow64/vcruntime140.dll']
    bad = [p for p in yes if not is_vcrt_file(p)] + [p for p in no if is_vcrt_file(p)]
    if bad:
        raise SystemExit('VC++ runtime rule misclassifies: %r' % bad)
    if (vcrt_fallback_path(W64 + 'vcruntime140.dll') != 'wine/lib/wine/vcrt-fallback/syswow64/vcruntime140.dll'
            or vcrt_fallback_path(S32 + 'msvcp140.dll') != 'wine/lib/wine/vcrt-fallback/system32/msvcp140.dll'):
        raise SystemExit('VC++ fallback path is wrong')
    wine = b'MZ' + b'\0' * 0x3e + b'Wine builtin DLL' + b'\0' * 16
    microsoft = b'MZ' + b'\0' * 0x3e + b'\x0e\x1f\xba\x0e\x00\xb4\x09\xcd\x21\xb8\x01\x4c\xcd\x21This program'
    if not is_wine_builtin(wine) or is_wine_builtin(microsoft) or is_wine_builtin(b'MZ'):
        raise SystemExit('Wine builtin signature check is wrong')
    print('VC++ runtime rule: ok (%d paths)' % (len(yes) + len(no)))


def check_runtime(runtime):
    files = [p.relative_to(runtime).as_posix() for p in runtime.rglob('*.dll') if p.is_file()]
    vcrt = sorted(p for p in files if is_vcrt_file(p))
    native = [p for p in vcrt if not is_wine_builtin((runtime / p).read_bytes()[:0x50])]
    if not vcrt or native:
        raise SystemExit('runtime %s: %d VC++ runtime files, not Wine builtins: %r' % (runtime, len(vcrt), native))
    print('runtime %s: %d VC++ runtime files, all Wine builtins' % (runtime, len(vcrt)))


def check_installer():
    compiler = os.environ.get('CC') or shutil.which('cc') or shutil.which('gcc') or shutil.which('clang')
    if not compiler:
        print('SKIP installer: no host C compiler')
        return 0
    with tempfile.TemporaryDirectory() as work:
        work = pathlib.Path(work)
        binary = work / 'vcrt_fallback_host_check'
        defines = ['-DHW_INSTALL_ROOT="%s"' % (work / 'app0'), '-DHW_INSTALL_DATA="%s"' % (work / 'data')]
        subprocess.run([compiler, '-O1', '-Wall', '-Wextra', '-Wno-unused-function', '-Wno-sign-compare', '-Wno-format-truncation',
                        *defines, '-I' + str(ROOT / 'native'), str(ROOT / 'tests/vcrt_fallback_host_check.c'),
                        '-o', str(binary), '-lpthread'], check=True)
        return subprocess.run([str(binary)]).returncode


def main():
    check_rule()
    if len(sys.argv) > 1:
        check_runtime(pathlib.Path(sys.argv[1]).resolve())
    return check_installer()


if __name__ == '__main__':
    sys.exit(main())
