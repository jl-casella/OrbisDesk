#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Frame generation display-decision host check (docs/FRAME_GENERATION.md, stage 4).

Builds tests/framegen_sched_host_check.c with the host C compiler and runs it: platform/ps4/pw_framegen_sched.h's
choice between a generated/real pair and the real frame alone, over simulated frame sequences (cap, vblank trust,
spans, generation readiness, GPU time). Host model only; it does not exercise the sink, VideoOut or the GPU.

    python3 tests/test_framegen_sched_host.py
"""
import os, pathlib, shutil, subprocess, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]


def main():
    compiler = os.environ.get('CC') or shutil.which('cc') or shutil.which('gcc') or shutil.which('clang')
    if not compiler:
        raise SystemExit('SKIP: no host C compiler')
    with tempfile.TemporaryDirectory() as work:
        binary = pathlib.Path(work) / 'framegen_sched_host_check'
        subprocess.run([compiler, '-O2', '-Wall', '-Wextra', '-Werror', '-I' + str(ROOT / 'platform/ps4'),
                        str(ROOT / 'tests/framegen_sched_host_check.c'), '-o', str(binary)], check=True)
        result = subprocess.run([str(binary)])
    return result.returncode


if __name__ == '__main__':
    sys.exit(main())
