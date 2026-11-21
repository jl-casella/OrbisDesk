#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""FPS LIMIT host check (docs/FPS_LIMIT.md).

Builds tests/fps_limit_host_check.c with the host C compiler and runs it: platform/ps4/pw_fps_limit.h's pacing and
Auto decisions against simulated synchronous and queued (DXVK-like) games on a 60 Hz output. Host model only; it
does not exercise VideoOut's vblank status, the sink's hold or the console.

    python3 tests/test_fps_limit_host.py
"""
import os, pathlib, shutil, subprocess, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]


def main():
    compiler = os.environ.get('CC') or shutil.which('cc') or shutil.which('gcc') or shutil.which('clang')
    if not compiler:
        raise SystemExit('SKIP: no host C compiler')
    with tempfile.TemporaryDirectory() as work:
        binary = pathlib.Path(work) / 'fps_limit_host_check'
        subprocess.run([compiler, '-O2', '-Wall', '-Wextra', '-Werror', '-I' + str(ROOT / 'platform/ps4'),
                        str(ROOT / 'tests/fps_limit_host_check.c'), '-o', str(binary)], check=True)
        result = subprocess.run([str(binary)])
    return result.returncode


if __name__ == '__main__':
    sys.exit(main())
