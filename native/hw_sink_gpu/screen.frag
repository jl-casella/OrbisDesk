#version 450
// W142: the sink's output pixel, as platform/ps4/pw_wine_sink_ps4.c show() computes it on the
// CPU: the desktop scaled by nearest neighbour into a centred rectangle, black around it,
// alpha forced to opaque, and the 11x17 arrow pointer on top. Pixels are read as 32-bit
// words (B,G,R,X in memory) and written to an R8G8B8A8 attachment byte for byte, so the
// VideoOut buffer gets the same B,G,R,A bytes the CPU copy writes.
// W144: the desktop is a stack of layers (wallpaper, windows; bottom first) in one pool, as
// ps5drv.c compose_rect stacks them on the CPU: a desktop pixel comes from the top layer that
// covers it, black where none does.
// W145: a window pixel no flush wrote yet (PS5_UNPAINTED in ps5drv.c) shows the layer below,
// as compose_rect leaves the screen under parts of a window that never paint.
// W149: no early return or continue around the fetch. With them, the pixels outside a window in
// an 8x8 block (one wave) that also holds pixels inside it came out black on the PS4 (W144-W148:
// a black margin from every window edge out to the next multiple of 8). The loop now runs the
// same for every pixel (count is uniform), always fetches, and keeps the result by selection.
// W152: a layer may also be a Vulkan program's presented image, read where Mesa's headless WSI
// left it (its GPU address, outside the pool) and scaled to the window's client area. Every
// layer does both reads (the pool at an index, the image at a valid address) and selects one,
// with no branch, as W149 requires.
// W153: in W152 the first frame hung the GPU. On GFX7 Mesa's ACO reads a 64-bit address held per
// pixel with FLAT instructions, which go through the shared/private apertures the PS4 never sets
// up. The address is now a uniform base plus a 32-bit per-pixel offset (u2u64), which ACO reads
// with MUBUF (ac_nir_lower_global_access). hw_sink_gpu.c checks the compiled code for FLAT before
// using it; built with POOL_ONLY (no image layers) this is the shader it falls back to.
#ifndef POOL_ONLY
#extension GL_EXT_buffer_reference : require
#extension GL_EXT_shader_explicit_arithmetic_types_int64 : require
layout(buffer_reference, std430, buffer_reference_align = 4) readonly buffer Image { uint pixel; };
#endif
const uint UNPAINTED = 0x01ff00ffu;
const int EXTERNAL = 1;               // the layer is an image at source.xy, not pool pixels
const int RGBA = 2;                   // its words are R,G,B,A in memory: swap red and blue
layout(set = 0, binding = 0) uniform usamplerBuffer pool;
struct Layer {
  ivec4 rect;                         // left, top, right, bottom in desktop pixels
  ivec4 at;                           // x: first pixel in the pool, y: stride in pixels, z: flags
  uvec4 source;                       // xy: GPU address of an image (valid for every layer), zw: its size
};
layout(set = 0, binding = 1, std140) uniform Layers { Layer layer[65]; } l;
layout(push_constant) uniform Push {
  int width, height, count;           // desktop, layers
  int left, top, scale_w, scale_h;    // where it goes in the output
  int cursor_x, cursor_y;             // output pixels; far outside when there is no pointer
} p;
layout(location = 0) out vec4 color;

// the arrow of pw_wine_sink_ps4.c, one bit per column: outline (black) and fill (white)
const uint outline[17] = uint[](0x1u, 0x3u, 0x5u, 0x9u, 0x11u, 0x21u, 0x41u, 0x81u, 0x101u, 0x201u,
                                0x7c1u, 0x49u, 0x95u, 0x93u, 0x121u, 0x120u, 0xc0u);
const uint fill[17] = uint[](0x0u, 0x0u, 0x2u, 0x6u, 0xeu, 0x1eu, 0x3eu, 0x7eu, 0xfeu, 0x1feu,
                             0x3eu, 0x36u, 0x62u, 0x60u, 0xc0u, 0xc0u, 0x0u);

void main() {
  ivec2 at = ivec2(gl_FragCoord.xy);
  int x = at.x - p.left, y = at.y - p.top;
  bool desktop = x >= 0 && y >= 0 && x < p.scale_w && y < p.scale_h;
  ivec2 d = ivec2(max(x, 0) * p.width / p.scale_w, max(y, 0) * p.height / p.scale_h);
  uint pixel = 0xff000000u;           // black: outside the desktop, or no layer covers it
  for (int i = 0; i < p.count; ++i) { // bottom to top: a covering layer above replaces the pixel
    ivec4 r = l.layer[i].rect;
    ivec4 a = l.layer[i].at;
    uvec4 s = l.layer[i].source;
    bool inside = desktop && d.x >= r.x && d.y >= r.y && d.x < r.z && d.y < r.w;
    bool image_layer = (a.z & EXTERNAL) != 0;
    // the layer's pixel; pool layers have their own size as source size, so this is d - r.xy
    ivec2 sp = ivec2((d.x - r.x) * int(s.z) / max(r.z - r.x, 1), (d.y - r.y) * int(s.w) / max(r.w - r.y, 1));
    int index = inside ? sp.y * a.y + sp.x : 0;
    uint pooled = texelFetch(pool, image_layer ? 0 : a.x + index).r;
#ifdef POOL_ONLY
    uint texel = pooled;
#else
    uint64_t base = packUint2x32(s.xy);  // uniform: the same for every pixel
    uint image = Image(base + uint64_t(uint(image_layer ? index : 0) * 4u)).pixel;
    uint texel = image_layer ? image : pooled;
#endif
    texel = (a.z & RGBA) != 0 ? (texel & 0xff00ff00u) | ((texel & 0xffu) << 16) | ((texel >> 16) & 0xffu) : texel;
    pixel = inside && (image_layer || texel != UNPAINTED) ? texel | 0xff000000u : pixel;
  }
  int row = at.y - p.cursor_y, column = at.x - p.cursor_x;
  bool arrow = row >= 0 && row < 17 && column >= 0 && column < 16;
  uint bit = arrow ? 1u << uint(column) : 0u;
  uint outline_row = outline[clamp(row, 0, 16)], fill_row = fill[clamp(row, 0, 16)];
  pixel = (outline_row & bit) != 0u ? 0xff000000u : (fill_row & bit) != 0u ? 0xffffffffu : pixel;
  color = unpackUnorm4x8(pixel);
}
