#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""W264 (W262: every 32-bit program that loaded Mesa's i386 opengl32 ended the app, CE-34878): Mesa's WGL frontend
(src/gallium/frontends/wgl/stw_tls.c, stw_tls_init from DllMain PROCESS_ATTACH) installs its WH_CALLWNDPROC hook on every
thread of the process, so threads that existed before the load track their windows. In explorer's process (its 32-bit
world) that means explorer's own 64-bit threads and other programs' threads, and in a 32-bit title Wine's 64-bit-only
threads: a 32-bit hook procedure called by a 64-bit thread. A thread with no hook data gets it when it first uses WGL
(stw_tls_get_data) and threads created later from DLL_THREAD_ATTACH, so 32-bit builds (!_WIN64) skip the enumeration;
the 64-bit build is unchanged.  patch-mesa-wgl-hooks.py <mesa source>"""
import sys as _brand_sys
from pathlib import Path as _BrandPath
_brand_sys.path.insert(0,str(_BrandPath(__file__).resolve().parents[1]))
from project_brand import normalize_marker

import pathlib, sys
p = pathlib.Path(sys.argv[1]) / 'src/gallium/frontends/wgl/stw_tls.c'
t = normalize_marker(p.read_text())
old = """#ifndef _GAMING_XBOX
   DWORD dwCurrentProcessId = GetCurrentProcessId();"""
new = """#if !defined(_GAMING_XBOX) && defined(_WIN64)  /* OrbisDesk W264: no hooks on other threads in 32-bit builds */
   DWORD dwCurrentProcessId = GetCurrentProcessId();"""
if new in t:
    print('wgl hooks already patched')
elif t.count(old) == 1:
    p.write_text(t.replace(old, new))
    print('wgl hooks patched')
else:
    raise SystemExit('unexpected stw_tls.c')
