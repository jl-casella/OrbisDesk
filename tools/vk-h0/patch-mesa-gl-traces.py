#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Alpha 2: Mesa WGL's PWGL viewport and PWSTW size lines (tools/vk-h0/patch-mesa-gl-viewport-trace.py, 04.30-04.32)
follow OrbisDesk's trace switch. The launcher passes PW_TRACE=0|1 to Windows programs (platform/ps4/pw_trace.h); unset
counts as on, as before the switch. Run after patch-mesa-gl-viewport-trace.py. Its own marker, so a source tree that
already has the 04.30/04.32 lines gets the switch too.
patch-mesa-gl-traces.py <mesa source>"""
import sys as _brand_sys
from pathlib import Path as _BrandPath
_brand_sys.path.insert(0,str(_BrandPath(__file__).resolve().parents[1]))
from project_brand import normalize_marker

import pathlib, sys
src = pathlib.Path(sys.argv[1])
MARK = 'OrbisDesk alpha 2: GL traces follow PW_TRACE'
HELPER = '''#include <stdlib.h>  /* ''' + MARK + ''' */
static int pw_gl_traced(void)
{
   static int traced = -1;
   if (traced < 0) {
      const char *value = getenv("PW_TRACE");
      traced = !(value && value[0] == '0' && !value[1]);
   }
   return traced;
}
'''


def patch(rel, include, call):
    p = src / rel
    t = normalize_marker(p.read_text())
    if MARK in t:
        print(rel, 'already applied:', MARK)
        return
    for old, new in ((include, include + HELPER), (call, 'if (pw_gl_traced())\n         ' + call)):
        if t.count(old) != 1:
            raise SystemExit('unexpected ' + rel + ' (run patch-mesa-gl-viewport-trace.py first): ' + old.strip()[:60])
        t = t.replace(old, new)
    p.write_text(t)
    print(rel, 'applied:', MARK)


patch('src/mesa/main/viewport.c', '#include "util/log.h"  /* OrbisDesk 04.30: viewport trace */\n',
      'mesa_loge("PWGL viewport')
patch('src/gallium/frontends/wgl/stw_framebuffer.c', '#include "util/log.h"  /* OrbisDesk 04.32: Mesa errors to the Wine log */\n',
      'mesa_loge("PWSTW size')
