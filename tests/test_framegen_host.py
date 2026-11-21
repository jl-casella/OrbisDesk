#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Frame generation host check (docs/FRAME_GENERATION.md).

Compiles native/hw_sink_gpu/fg_*.comp with glslang (the pinned ~/vk-h0/host-tools one when present, else
glslang/glslangValidator from PATH) and tests/framegen_host_check.c with the host C compiler, then runs it on
Mesa's lavapipe. Needs the Vulkan loader headers/library (libvulkan-dev) and lavapipe (mesa-vulkan-drivers).
Host reference behaviour only; it does not exercise the PS4 GPU.

    python3 tests/test_framegen_host.py
"""
import os, pathlib, shutil, subprocess, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
SHADERS = ROOT / 'native/hw_sink_gpu'


def glslang():
    pinned = pathlib.Path.home() / 'vk-h0/host-tools/bin/glslang'
    if pinned.exists():
        return str(pinned)
    for name in ('glslang', 'glslangValidator'):
        if shutil.which(name):
            return name
    raise SystemExit('SKIP: no glslang')


def lavapipe():
    for folder in ('/usr/share/vulkan/icd.d', '/etc/vulkan/icd.d'):
        for name in ('lvp_icd.x86_64.json', 'lvp_icd.json'):
            if pathlib.Path(folder, name).exists():
                return str(pathlib.Path(folder, name))
    raise SystemExit('SKIP: no lavapipe ICD')


def main():
    icd = lavapipe()
    with tempfile.TemporaryDirectory() as work:
        work = pathlib.Path(work)
        for name in ('capture', 'coarse', 'fine', 'blend'):
            subprocess.run([glslang(), '-V', '--target-env', 'vulkan1.1', '--vn', f'fg_{name}_comp',
                            '-o', str(work / f'fg_{name}_comp.h'), str(SHADERS / f'fg_{name}.comp')],
                           check=True, stdout=subprocess.DEVNULL)
        binary = work / 'framegen_host_check'
        subprocess.run([os.environ.get('CC', 'cc'), '-std=c11', '-O1', '-Wall', '-Wextra', '-I', str(work),
                        str(ROOT / 'tests/framegen_host_check.c'), '-o', str(binary), '-lvulkan', '-lm'], check=True)
        env = dict(os.environ, VK_ICD_FILENAMES=icd, VK_DRIVER_FILES=icd)
        return subprocess.run([str(binary)], env=env).returncode


if __name__ == '__main__':
    sys.exit(main())
