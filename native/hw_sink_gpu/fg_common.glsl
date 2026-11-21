// SPDX-License-Identifier: LGPL-2.1-or-later
// Frame generation (docs/FRAME_GENERATION.md): what the four compute passes share. framegen.inc.c binds one of
// two descriptor sets: in set s the current frame is history slot s and the previous one slot 1-s, and the
// generated frame goes to output s. Colours are the presented image's 32-bit words, in its own byte order
// (p.rgba says which); luminance is one float per 2x2 pixels; motion is in luminance texels, from the previous
// frame to the current one: content at q in the current frame was at q - motion in the previous one.
layout(push_constant) uniform Push {
  uvec2 source;     // capture: the presented image's GPU address (uniform: base of every read)
  uint stride;      // its row length in pixels
  uint rgba;        // 1: its words are R,G,B,A in memory; 0: B,G,R,A
  uvec2 size;       // frame size in pixels
  uvec2 luma;       // luminance size: half the frame size, rounded up
  uvec2 coarse;     // coarse cells: 8x8 luminance texels each
  uvec2 fine;       // fine cells: 4x4 luminance texels each
  uvec4 keep;       // blend: pixels x0,y0 up to x1,y1 (exclusive) keep the current frame unchanged (MangoHud's
                    // rectangle, stage 5); x1 <= x0 for none
} p;
layout(set = 0, binding = 0, std430) buffer CurrentColor { uint cur_color[]; };
layout(set = 0, binding = 1, std430) buffer CurrentLuma { float cur_luma[]; };
layout(set = 0, binding = 2, std430) readonly buffer PreviousColor { uint prev_color[]; };
layout(set = 0, binding = 3, std430) readonly buffer PreviousLuma { float prev_luma[]; };
layout(set = 0, binding = 4, std430) buffer CoarseField { vec4 coarse_field[]; };  // motion.xy, cost, 0
layout(set = 0, binding = 5, std430) buffer FineField { vec4 fine_field[]; };      // motion.xy, error, 0
layout(set = 0, binding = 6, std430) writeonly buffer Generated { uint out_color[]; };

float luma_of(uint word) {
  vec4 c = unpackUnorm4x8(word);
  vec3 rgb = p.rgba != 0u ? c.rgb : c.bgr;
  return dot(rgb, vec3(0.2126, 0.7152, 0.0722));
}
// clamped reads: a search near an edge repeats the edge
float luma_cur(ivec2 q) {
  q = clamp(q, ivec2(0), ivec2(p.luma) - 1);
  return cur_luma[q.y * int(p.luma.x) + q.x];
}
float luma_prev(ivec2 q) {
  q = clamp(q, ivec2(0), ivec2(p.luma) - 1);
  return prev_luma[q.y * int(p.luma.x) + q.x];
}
