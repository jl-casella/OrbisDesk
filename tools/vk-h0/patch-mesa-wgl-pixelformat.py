#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""W304 (W303 run-0085/0087: Half-Life and Counter-Strike drew with 4 bits per channel): Mesa's WGL ChoosePixelFormat
(src/gallium/frontends/wgl/stw_pixelformat.c, stw_pixelformat_choose) gives the format with the fewest bits that still
meets the request. The GoldSrc engine (SDL2) asks for a small colour buffer, so it got pixel format 99,
PIPE_FORMAT_B4G4R4A4_UNORM, and Zink created a VK_FORMAT_A4R4G4B4_UNORM_PACK16 swapchain (PWVK "format 1000340000"),
while every other OpenGL guest got B8G8R8A8 (format 44). On Windows with an ICD the desktop-depth formats are the
accelerated ones and ChoosePixelFormat returns a 32-bit format on a 32-bit desktop whatever smaller sizes are asked for;
Mesa on Windows only lists the shallow formats when the winsys can display them, which Zink's can. So when the device is
24 bits or deeper, a format with fewer colour bits than 24 costs more than any channel-size difference (still less than a
missing depth/stencil/alpha buffer). The shallow formats stay listed (DescribePixelFormat and an explicit SetPixelFormat
on them are unchanged).
04.78 (04.77 run-0118: SDL's probe windows now got format 3, but the game window still 99): SDL picks the game window's
format with wglChoosePixelFormatARB (src/gallium/frontends/wgl/stw_ext_pixelformat.c), which scores the same way (each
extra bit over a minimum costs a point). The same rule there: on a 24-bit or deeper device, RGBA formats with fewer than
24 colour bits sort after every deeper format that matches; they are still returned, last.
patch-mesa-wgl-pixelformat.py <mesa source>"""
import sys as _brand_sys
from pathlib import Path as _BrandPath
_brand_sys.path.insert(0,str(_BrandPath(__file__).resolve().parents[1]))
from project_brand import normalize_marker

import pathlib, sys
wgl = pathlib.Path(sys.argv[1]) / 'src/gallium/frontends/wgl'
patches = {
    'stw_pixelformat.c': ('OrbisDesk W304', [
        ("""   count = stw_pixelformat_get_extended_count(hdc);
   bestindex = 0;
   bestdelta = ~0U;
""", """   count = stw_pixelformat_get_extended_count(hdc);
   bestindex = 0;
   bestdelta = ~0U;
   /* OrbisDesk W304: as Windows, prefer the desktop's colour depth over a shallower format that fits the request */
   const int device_bits = hdc ? GetDeviceCaps(hdc, BITSPIXEL) : 0;
"""),
        ("""      else if (ppfd->cColorBits < pfi->pfd.cColorBits)
         delta++;

      if (ppfd->cDepthBits && !pfi->pfd.cDepthBits)""", """      else if (ppfd->cColorBits < pfi->pfd.cColorBits)
         delta++;

      if (device_bits >= 24 && ppfd->iPixelType == PFD_TYPE_RGBA &&
          pfi->pfd.cRedBits + pfi->pfd.cGreenBits + pfi->pfd.cBlueBits < 24)
         delta += 1000; /* OrbisDesk W304 */

      if (ppfd->cDepthBits && !pfi->pfd.cDepthBits)"""),
    ]),
    'stw_ext_pixelformat.c': ('OrbisDesk 04.78', [
        ("""   /* Bubble-sort the resulting scores. Pixelformats with higher scores go
    * first.  TODO: Find out if there are any patent issues with it.
    */""", """   /* OrbisDesk 04.78 (W304 for wglChoosePixelFormatARB): as Windows, on a 24-bit or deeper desktop the formats of
    * that depth go first; an RGBA format with fewer colour bits still matches, after them */
   {
      const int device_bits = hdc ? GetDeviceCaps(hdc, BITSPIXEL) : 0;

      for (i = 0; device_bits >= 24 && i < count; i++) {
         const struct stw_pixelformat_info *pfi = stw_pixelformat_get_info(i + 1);

         if (scores[i].points > 0 && pfi && pfi->pfd.iPixelType == PFD_TYPE_RGBA &&
             pfi->pfd.cRedBits + pfi->pfd.cGreenBits + pfi->pfd.cBlueBits < 24)
            scores[i].points -= 0x10000000;
      }
   }

   /* Bubble-sort the resulting scores. Pixelformats with higher scores go
    * first.  TODO: Find out if there are any patent issues with it.
    */"""),
    ]),
}
for name, (marker, edits) in patches.items():
    p = wgl / name
    t = normalize_marker(p.read_text())
    if marker in t:
        print(f'wgl pixelformat: {name} already patched')
        continue
    for old, new in edits:
        if t.count(old) != 1:
            raise SystemExit(f'unexpected {name}')
        t = t.replace(old, new)
    p.write_text(t)
    print(f'wgl pixelformat: {name} patched')
