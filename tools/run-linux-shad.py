#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Run the pinned Linux AppImage with a private glibc on Ubuntu 22.04."""
import os,pathlib,subprocess,sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
app=ROOT/'.deps/shadPS4-linux/squashfs-root'
runtime=ROOT/'.deps/linux-runtime/usr/lib/x86_64-linux-gnu'
paths=[runtime,app/'usr/lib',app/'usr/optional/libstdc++.so.6',app/'usr/optional/libgcc_s.so.1']
command=[str(runtime/'ld-linux-x86-64.so.2'),'--library-path',':'.join(map(str,paths)),str(app/'usr/bin/shadps4'),*sys.argv[1:]]
if len(sys.argv)>1 and sys.argv[1]=='--fork':
    binary=ROOT/'build/shadPS4-linux/shadps4'
    command=[str(binary),*sys.argv[2:]]
env=dict(os.environ,VK_ICD_FILENAMES='/usr/share/vulkan/icd.d/lvp_icd.x86_64.json')
os.execve(command[0],command,env)
