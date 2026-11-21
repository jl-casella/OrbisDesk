#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""MangoHud's RAM and swap rows in GiB on Windows, as the HUD labels them (04.26).

src/memory_win32.cpp, the fork's Windows update_meminfo, divides GlobalMemoryStatusEx's bytes by 1024 * 1024 and
so keeps memused, memmax and swapused in MiB. src/hud_elements.cpp prints them with "GiB", as Linux MangoHud's
src/memory.cpp keeps them (/proc/meminfo's kB divided by 1024 * 1024).
Hardware 2026-11-18 (04.25, SeaMonkey with OpenGL on): MangoHud's RAM row read "859.8 GiB", which is 859.8 MiB. Every
HUD with the RAM row has it, 32-bit and 64-bit. Here the three values are kept in GiB. The i386 build copies this tree
(build-mangohud-i386.sh) and checks the marker.
"""
import pathlib, sys

MARKER = 'OrbisDesk 04.26: RAM in GiB'
path = pathlib.Path(sys.argv[1]) / 'src/memory_win32.cpp'
text = path.read_text()
if MARKER in text:
    print('memory patch already applied')
    sys.exit(0)
edits = (
    ('        memmax = float(memInfo.ullTotalPhys) / (1024.f * 1024.f); // MiB\n',
     '        /* ' + MARKER + ' (tools/vk-h0/patch-mangohud-win-memory.py): hud_elements.cpp prints GiB, as on Linux */\n'
     '        memmax = float(memInfo.ullTotalPhys) / (1024.f * 1024.f * 1024.f); // GiB\n'),
    ('        float memfree = float(memInfo.ullAvailPhys) / (1024.f * 1024.f);\n',
     '        float memfree = float(memInfo.ullAvailPhys) / (1024.f * 1024.f * 1024.f);\n'),
    ('        float swaptotal = float(memInfo.ullTotalPageFile - memInfo.ullTotalPhys) / (1024.f * 1024.f);\n',
     '        float swaptotal = float(memInfo.ullTotalPageFile - memInfo.ullTotalPhys) / (1024.f * 1024.f * 1024.f);\n'),
    ('        float swapfree = float(memInfo.ullAvailPageFile - memInfo.ullAvailPhys) / (1024.f * 1024.f);\n',
     '        float swapfree = float(memInfo.ullAvailPageFile - memInfo.ullAvailPhys) / (1024.f * 1024.f * 1024.f);\n'),
)
for old, new in edits:
    if text.count(old) != 1:
        raise SystemExit('unexpected update_meminfo in src/memory_win32.cpp: ' + old.strip())
    text = text.replace(old, new)
path.write_text(text)
print('memory patch applied')
