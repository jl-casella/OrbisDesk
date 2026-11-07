# W085: Zink on the PS4 does not emulate GL_QUADS with a geometry shader. In W084 a ring drawn
# with GL_QUADS or GL_QUAD_STRIP (converted to quads) lost parts from frame to frame, whatever
# the shading, face culling or display lists, while the same vertices as a GL_TRIANGLE_STRIP
# drew whole: Zink draws quads through a generated geometry shader (zink_program.c,
# zink_create_quads_emulation_gs), and geometry shaders misbehave on Liverpool through RADV
# (Crema investigates its GS rings, upstream/Crema/patches/mesa-ps4-gs-ring-probe.patch).
# Without quads among the supported primitives, Mesa's frontend turns them into indexed
# triangles. Other geometry shader uses remain affected.  patch-mesa-zink.py <mesa source>
import sys as _brand_sys
from pathlib import Path as _BrandPath
_brand_sys.path.insert(0,str(_BrandPath(__file__).resolve().parents[1]))
from project_brand import normalize_marker

import pathlib, sys
p = pathlib.Path(sys.argv[1]) / 'src/gallium/drivers/zink/zink_screen.c'
t = normalize_marker(p.read_text())
old = '''      if (!screen->have_triangle_fans || !screen->info.feats.features.geometryShader)
         modes &= ~BITFIELD_BIT(MESA_PRIM_QUADS);'''
new = '''      /* OrbisDesk (tools/vk-h0/patch-mesa-zink.py): no geometry shader quads on the PS4 */
      modes &= ~BITFIELD_BIT(MESA_PRIM_QUADS);'''
if new in t:
    print('zink already patched')
elif t.count(old) == 1:
    p.write_text(t.replace(old, new))
    print('zink patched')
else:
    raise SystemExit('unexpected zink_screen.c')
