#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""W266 (W264: Call of Duty's "zink: could not create swapchain" after vkCreateWin32SurfaceKHR for hwnd 0): traces of
the WGL framebuffer's window, kopper's surface, its support and its capabilities, in 32-bit builds only (!_WIN64); the
64-bit build compiles as before. Nothing changes behaviour.  patch-mesa-zink-trace.py <mesa source>"""
import sys as _brand_sys
from pathlib import Path as _BrandPath
_brand_sys.path.insert(0,str(_BrandPath(__file__).resolve().parents[1]))
from project_brand import normalize_marker

import pathlib, sys
src = pathlib.Path(sys.argv[1])
MARK = 'OrbisDesk W266'

def patch(rel, edits):
    p = src / rel
    t = normalize_marker(p.read_text())
    if MARK in t:
        print(rel, 'already traced')
        return
    for old, new in edits:
        if t.count(old) != 1:
            raise SystemExit('unexpected ' + rel + ': ' + old[:60])
        t = t.replace(old, new)
    p.write_text(t)
    print(rel, 'traced')

patch('src/gallium/drivers/zink/zink_kopper.c', [
("""#include "zink_kopper.h"
""", """#include "zink_kopper.h"

#if defined(_WIN32) && !defined(_WIN64)  /* OrbisDesk W266: traces in the 32-bit build */
#define PW_ZINK_TRACE(...) mesa_loge(__VA_ARGS__)
#else
#define PW_ZINK_TRACE(...) ((void)0)
#endif
"""),
("""      error = VKSCR(CreateWin32SurfaceKHR)(screen->instance, win32, NULL, &surface);
      break;""", """      error = VKSCR(CreateWin32SurfaceKHR)(screen->instance, win32, NULL, &surface);
      PW_ZINK_TRACE("PWZINK surface hwnd=%p window=%d res=%d", (void *)win32->hwnd,
                    win32->hwnd && IsWindow(win32->hwnd) ? 1 : 0, (int)error);
      break;"""),
("""   error = VKSCR(GetPhysicalDeviceSurfaceSupportKHR)(screen->pdev, screen->gfx_queue, surface, &supported);
""", """   error = VKSCR(GetPhysicalDeviceSurfaceSupportKHR)(screen->pdev, screen->gfx_queue, surface, &supported);
   PW_ZINK_TRACE("PWZINK surface support res=%d supported=%u", (int)error, error == VK_SUCCESS ? (unsigned)supported : 0u);
"""),
("""   VkResult error = VKSCR(GetPhysicalDeviceSurfaceCapabilitiesKHR)(screen->pdev, cdt->surface, &cdt->caps);
""", """   VkResult error = VKSCR(GetPhysicalDeviceSurfaceCapabilitiesKHR)(screen->pdev, cdt->surface, &cdt->caps);
#if defined(_WIN32) && !defined(_WIN64)  /* OrbisDesk W266: failures, and the extents when they change */
   {
      static uint32_t pw_last[6];
      uint32_t pw_now[6] = {cdt->caps.currentExtent.width, cdt->caps.currentExtent.height,
                            cdt->caps.minImageExtent.width, cdt->caps.minImageExtent.height,
                            cdt->caps.maxImageExtent.width, cdt->caps.maxImageExtent.height};
      if (error != VK_SUCCESS) {
         mesa_loge("PWZINK caps res=%d", (int)error);
      } else if (memcmp(pw_last, pw_now, sizeof(pw_now))) {
         memcpy(pw_last, pw_now, sizeof(pw_now));
         mesa_loge("PWZINK caps current=%ux%u min=%ux%u max=%ux%u images=%u-%u", pw_now[0], pw_now[1], pw_now[2],
                   pw_now[3], pw_now[4], pw_now[5], cdt->caps.minImageCount, cdt->caps.maxImageCount);
      }
   }
#endif
"""),
("""   cdt->surface = kopper_CreateSurface(screen, cdt);
   if (!cdt->surface)
      goto out;

   if (update_swapchain(screen, cdt, width, height) != VK_SUCCESS)
      goto out;
""", """   cdt->surface = kopper_CreateSurface(screen, cdt);
   if (!cdt->surface) {
      PW_ZINK_TRACE("PWZINK displaytarget %ux%u: no surface", width, height);  /* OrbisDesk W266 */
      goto out;
   }

   {
      VkResult pw_swapchain = update_swapchain(screen, cdt, width, height);
      if (pw_swapchain != VK_SUCCESS) {
         PW_ZINK_TRACE("PWZINK displaytarget %ux%u: swapchain res=%d", width, height, (int)pw_swapchain);
         goto out;
      }
   }
"""),
])

patch('src/gallium/frontends/wgl/stw_framebuffer.c', [
("""#include "util/os_time.h"
""", """#include "util/os_time.h"
#include "util/log.h"  /* OrbisDesk W266 */
"""),
("""   fb->hWnd = hWnd;
   fb->hDC = hdc;
""", """   fb->hWnd = hWnd;
   fb->hDC = hdc;
#if !defined(_WIN64)  /* OrbisDesk W266: the window the framebuffer (and kopper's surface) gets */
   mesa_loge("PWSTW framebuffer hdc=%p hwnd=%p window_from_dc=%p window=%d owner=%d format=%d", (void *)hdc,
             (void *)hWnd, hdc ? (void *)WindowFromDC(hdc) : NULL, hWnd && IsWindow(hWnd) ? 1 : 0, (int)owner,
             pfi ? pfi->iPixelFormat : 0);
#endif
"""),
])

# W269 (W267: Call of Duty ended with status 3 after its GL start): the GL strings a 32-bit program gets; Quake III-engine
# games copy GL_EXTENSIONS into a fixed buffer. ("OrbisDesk W266" marks the traced file.)
patch('src/mesa/main/getstring.c', [
("""#include "api_exec_decl.h"
""", """#include "api_exec_decl.h"
#include "util/log.h"  /* OrbisDesk W266 traces (W269) */
"""),
("""         if (!ctx->Extensions.String)
            ctx->Extensions.String = _mesa_make_extension_string(ctx);
""", """         if (!ctx->Extensions.String)
            ctx->Extensions.String = _mesa_make_extension_string(ctx);
#if !defined(_WIN64)  /* OrbisDesk W266 traces (W269): the extension string a 32-bit program gets */
         {
            static int pw_logged;
            if (!pw_logged++)
               mesa_loge("PWGL version=%s extensions_length=%u", ctx->VersionString ? ctx->VersionString : "",
                         ctx->Extensions.String ? (unsigned)strlen((const char *)ctx->Extensions.String) : 0u);
         }
#endif
"""),
("""      case GL_RENDERER: {
         const GLubyte *str = (const GLubyte *)screen->get_name(screen);
""", """      case GL_RENDERER: {
         const GLubyte *str = (const GLubyte *)screen->get_name(screen);
#if !defined(_WIN64)  /* OrbisDesk W266 traces (W269) */
         {
            static int pw_logged;
            if (!pw_logged++)
               mesa_loge("PWGL vendor=%s renderer=%s", screen->get_vendor(screen) ? screen->get_vendor(screen) : "",
                         str ? (const char *)str : "");
         }
#endif
"""),
])

patch('src/gallium/frontends/wgl/stw_st.c', [
("""#include "util/u_atomic.h"
""", """#include "util/u_atomic.h"
#include "util/log.h"  /* OrbisDesk W266 */
"""),
("""   win32->hwnd = stwfb->fb->hWnd;
""", """   win32->hwnd = stwfb->fb->hWnd;
#if !defined(_WIN64)  /* OrbisDesk W266 */
   mesa_loge("PWSTW kopper hwnd=%p window=%d hdc=%p window_from_dc=%p", (void *)win32->hwnd,
             win32->hwnd && IsWindow(win32->hwnd) ? 1 : 0, (void *)stwfb->fb->hDC,
             stwfb->fb->hDC ? (void *)WindowFromDC(stwfb->fb->hDC) : NULL);
#endif
"""),
])
