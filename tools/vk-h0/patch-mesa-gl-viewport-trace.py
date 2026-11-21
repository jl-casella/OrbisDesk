#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""04.30 (04.29 on the console, SeaMonkey with OpenGL on, run-0254/run-0255): the window's GL image showed 34 pixels too
high, with black under it. win32u logged "PWVK size hwnd=0x1c00b4 image=1154x617 client=1154x617 window=1162x651" and
placed the image at the client area ("PWVK layer ... at=(74,50)-(1228,667)"), so the image itself carries the shift.
That fits a program drawing a frame as tall as the window (651) into a drawable as tall as the client area (617): GL's
rows go bottom-up, so the top 34 rows fall off and the last 34 stay black. Basic (GDI, top-down) would hide the same
size. This logs glViewport on a window's drawable when its size is not the drawable's, at each change, the first 16
times in a process, in both builds.

04.32 (04.30 on the console, run-0262): no "PWGL viewport" line came, and none could. On Windows mesa_loge goes to the
program's stderr and to OutputDebugStringA. A guest's stderr is not the console log, and Wine prints
OutputDebugStringA only on its warn+debugstr channel; the launcher's WINEDEBUG is "fixme-all,warn+module" (W267's
PWSTW lines came from a run with warn+debugstr). So Mesa's error-level lines now go through ntdll's __wine_dbg_output
when it exists (Wine), which writes to the console log whatever WINEDEBUG says; elsewhere, and for the other levels,
nothing changes. Error-level lines are rare: the traces below, W266's 32-bit window traces, and real errors. And
stw_framebuffer_get_size logs what GetClientRect and GetWindowRect return for the framebuffer's window, on which
thread, when that changes, the first 16 times: the drawable's size as Mesa reads it at each swap. With the viewport
line it says whether Gecko's size or the drawable's is the window's. It changes nothing else.
patch-mesa-gl-viewport-trace.py <mesa source>"""
import sys as _brand_sys
from pathlib import Path as _BrandPath
_brand_sys.path.insert(0,str(_BrandPath(__file__).resolve().parents[1]))
from project_brand import normalize_marker

import pathlib, sys
src = pathlib.Path(sys.argv[1])
MARK = 'OrbisDesk 04.30: viewport trace'
MARK2 = 'OrbisDesk 04.32: Mesa errors to the Wine log'


def patch(rel, mark, edits):
    p = src / rel
    t = normalize_marker(p.read_text())
    if mark in t:
        print(rel, 'already applied:', mark)
        return
    for old, new in edits:
        if t.count(old) != 1:
            raise SystemExit('unexpected ' + rel + ': ' + old.strip()[:60])
        t = t.replace(old, new)
    p.write_text(t)
    print(rel, 'applied:', mark)


patch('src/mesa/main/viewport.c', MARK, (
    ('#include "api_exec_decl.h"\n',
     '#include "api_exec_decl.h"\n#include "util/log.h"  /* ' + MARK + ' */\n'),
    ('''   /* Clamp the viewport to the implementation dependent values. */
   clamp_viewport(ctx, &input.X, &input.Y, &input.Width, &input.Height);
''', '''   /* Clamp the viewport to the implementation dependent values. */
   clamp_viewport(ctx, &input.X, &input.Y, &input.Width, &input.Height);

   /* ''' + MARK + ''' (tools/vk-h0/patch-mesa-gl-viewport-trace.py): a viewport on a window's drawable whose size is not
    * the drawable's, at each change, the first 16 times */
   {
      static int pw_count;
      static float pw_last[4];
      const struct gl_framebuffer *pw_fb = ctx->DrawBuffer;
      float pw_now[4] = {input.Width, input.Height, pw_fb ? (float)pw_fb->Width : 0.0f,
                         pw_fb ? (float)pw_fb->Height : 0.0f};

      if (pw_fb && !pw_fb->Name && pw_fb->Width && pw_fb->Height &&
          (input.Width != (float)pw_fb->Width || input.Height != (float)pw_fb->Height) &&
          memcmp(pw_now, pw_last, sizeof(pw_now)) && pw_count < 16) {
         pw_count++;
         memcpy(pw_last, pw_now, sizeof(pw_now));
         mesa_loge("PWGL viewport %gx%g at %g,%g on a %ux%u window drawable", (double)input.Width,
                   (double)input.Height, (double)input.X, (double)input.Y, pw_fb->Width, pw_fb->Height);
      }
   }
'''),
))

patch('src/util/log.c', MARK2, (
    ('''   OutputDebugStringA(msg);
''', '''   /* ''' + MARK2 + ''' (tools/vk-h0/patch-mesa-gl-viewport-trace.py): Wine prints
    * OutputDebugStringA only on its warn+debugstr channel, so error-level lines go through ntdll's __wine_dbg_output,
    * which writes to Wine's own log, when it exists */
   {
      static int (__cdecl *pw_wine_dbg_output)(const char *);
      static int pw_wine_dbg_looked;

      if (!pw_wine_dbg_looked) {
         HMODULE pw_ntdll = GetModuleHandleA("ntdll.dll");

         if (pw_ntdll)
            pw_wine_dbg_output = (int (__cdecl *)(const char *))(void *)GetProcAddress(pw_ntdll, "__wine_dbg_output");
         pw_wine_dbg_looked = 1;
      }
      if (level == MESA_LOG_ERROR && pw_wine_dbg_output)
         pw_wine_dbg_output(msg);
      else
         OutputDebugStringA(msg);
   }
'''),
))

patch('src/gallium/frontends/wgl/stw_framebuffer.c', MARK2, (
    ('#include "util/os_time.h"\n',
     '#include "util/os_time.h"\n#include "util/log.h"  /* ' + MARK2 + ' */\n'),
    ('''   width  = client_rect.right  - client_rect.left;
   height = client_rect.bottom - client_rect.top;
''', '''   width  = client_rect.right  - client_rect.left;
   height = client_rect.bottom - client_rect.top;

   /* ''' + MARK2 + ''' (tools/vk-h0/patch-mesa-gl-viewport-trace.py): the drawable's size as read here at
    * each swap, against the window's, on which thread, when it changes, the first 16 times */
   {
      static int pw_count;
      static LONG pw_last[5];
      RECT pw_window = {0};
      LONG pw_now[5];

      GetWindowRect(fb->hWnd, &pw_window);
      pw_now[0] = (LONG)(INT_PTR)fb->hWnd;
      pw_now[1] = width;
      pw_now[2] = height;
      pw_now[3] = pw_window.right - pw_window.left;
      pw_now[4] = pw_window.bottom - pw_window.top;
      if (memcmp(pw_now, pw_last, sizeof(pw_now)) && pw_count < 16) {
         pw_count++;
         memcpy(pw_last, pw_now, sizeof(pw_now));
         mesa_loge("PWSTW size hwnd=%p thread=%04lx client=%ldx%ld window=%ldx%ld drawable=%dx%d", (void *)fb->hWnd,
                   (unsigned long)GetCurrentThreadId(), width, height, pw_now[3], pw_now[4], fb->width, fb->height);
      }
   }
'''),
))
