/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Big Picture's canvas (steam_draw.h). Tahoma through stb_truetype (public domain / MIT, the OpenOrbis
 * SDK's copy, pinned by the builders); its implementation is static to this file (STBTT_STATIC) so it can't
 * meet another copy in Wine's ELF. Glyphs are rasterized once per size and kept in a small cache. */
#include "steam_draw.h"

#include <fcntl.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#define STBTT_STATIC
#define STB_TRUETYPE_IMPLEMENTATION
#define STBTT_assert(x) ((void)0)
#if defined(__clang__) || defined(__GNUC__)
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wunused-function"
#pragma GCC diagnostic ignored "-Wsign-compare"
#pragma GCC diagnostic ignored "-Wunused-parameter"
#pragma GCC diagnostic ignored "-Wimplicit-fallthrough"
#pragma GCC diagnostic ignored "-Wcast-qual"
#pragma GCC diagnostic ignored "-Wmissing-field-initializers"
#endif
#include "stb_truetype.h"
#if defined(__clang__) || defined(__GNUC__)
#pragma GCC diagnostic pop
#endif

#include "../hw_text.h"

/* ---- pixels ---- */

static inline uint32_t blend(uint32_t dst, uint32_t src, unsigned alpha)
{
  /* alpha 0..255 already multiplied by the color's own */
  if (alpha >= 255) return src | 0xff000000u;
  if (!alpha) return dst;
  const unsigned inv = 255 - alpha;
  const unsigned r = (((src >> 16) & 255) * alpha + ((dst >> 16) & 255) * inv + 127) / 255;
  const unsigned g = (((src >> 8) & 255) * alpha + ((dst >> 8) & 255) * inv + 127) / 255;
  const unsigned b = ((src & 255) * alpha + (dst & 255) * inv + 127) / 255;
  return 0xff000000u | r << 16 | g << 8 | b;
}

static inline void put(sd_canvas *c, int x, int y, uint32_t color, unsigned coverage)
{
  if (x < c->cx0 || y < c->cy0 || x >= c->cx1 || y >= c->cy1 || !c->px) return;
  const unsigned alpha = ((color >> 24) * coverage + 127) / 255;
  uint32_t *p = c->px + (size_t)y * c->pitch + x;
  *p = blend(*p, color, alpha);
}

void sd_begin(sd_canvas *c, uint32_t *pixels, int width, int height, int pitch)
{
  c->px = pixels;
  c->w = width;
  c->h = height;
  c->pitch = pitch;
  c->scale = (float)width / 1920.0f;
  sd_unclip(c);
}

void sd_unclip(sd_canvas *c)
{
  c->cx0 = c->cy0 = 0;
  c->cx1 = c->w;
  c->cy1 = c->h;
}

void sd_clip(sd_canvas *c, float x, float y, float w, float h)
{
  const float s = c->scale;
  int x0 = (int)floorf(x * s), y0 = (int)floorf(y * s), x1 = (int)ceilf((x + w) * s), y1 = (int)ceilf((y + h) * s);
  c->cx0 = x0 < 0 ? 0 : x0;
  c->cy0 = y0 < 0 ? 0 : y0;
  c->cx1 = x1 > c->w ? c->w : x1;
  c->cy1 = y1 > c->h ? c->h : y1;
}

void sd_gradient(sd_canvas *c, uint32_t top, uint32_t bottom)
{
  if (!c->px) return;
  for (int y = 0; y < c->h; ++y) {
    const unsigned t = (unsigned)(y * 255 / (c->h > 1 ? c->h - 1 : 1));
    const uint32_t color = blend(top | 0xff000000u, bottom, t);
    uint32_t *row = c->px + (size_t)y * c->pitch;
    for (int x = 0; x < c->w; ++x) row[x] = color;
  }
}

/* a rounded rectangle's coverage, pixels: AA on the corners only */
static void fill_round(sd_canvas *c, float fx, float fy, float fw, float fh, float fr, uint32_t color)
{
  if (!c->px || fw <= 0 || fh <= 0) return;
  if (fr * 2 > fw) fr = fw / 2;
  if (fr * 2 > fh) fr = fh / 2;
  int y0 = (int)floorf(fy), y1 = (int)ceilf(fy + fh), x0 = (int)floorf(fx), x1 = (int)ceilf(fx + fw);
  if (y0 < c->cy0) y0 = c->cy0;
  if (y1 > c->cy1) y1 = c->cy1;
  if (x0 < c->cx0) x0 = c->cx0;
  if (x1 > c->cx1) x1 = c->cx1;
  const unsigned a = color >> 24;
  for (int y = y0; y < y1; ++y) {
    const float py = (float)y + 0.5f;
    /* vertical edge coverage (fractional top/bottom rows) */
    float vy = 1.0f;
    if (py - 0.5f < fy) vy = (float)y + 1.0f - fy;
    if (py + 0.5f > fy + fh) vy = fy + fh - (float)y;
    if (vy <= 0) continue;
    if (vy > 1) vy = 1;
    const int corner_row = fr > 0 && (py < fy + fr || py > fy + fh - fr);
    uint32_t *row = c->px + (size_t)y * c->pitch;
    for (int x = x0; x < x1; ++x) {
      const float px = (float)x + 0.5f;
      float cover = vy;
      if (px - 0.5f < fx) cover *= (float)x + 1.0f - fx;
      if (px + 0.5f > fx + fw) cover *= fx + fw - (float)x;
      if (corner_row && (px < fx + fr || px > fx + fw - fr)) {
        const float ccx = px < fx + fr ? fx + fr : fx + fw - fr;
        const float ccy = py < fy + fr ? fy + fr : fy + fh - fr;
        const float d = sqrtf((px - ccx) * (px - ccx) + (py - ccy) * (py - ccy));
        float k = fr - d + 0.5f;
        if (k <= 0) continue;
        if (k < 1) cover *= k;
      }
      if (cover <= 0) continue;
      const unsigned alpha = (unsigned)(a * (cover > 1 ? 1 : cover) + 0.5f);
      row[x] = blend(row[x], color, alpha);
    }
  }
}

void sd_round_gradient(sd_canvas *c, float x, float y, float w, float h, float radius, uint32_t top, uint32_t bottom)
{
  /* one row at a time, each in its own color, clipped to the row */
  const float s = c->scale;
  const int y0 = (int)floorf(y * s), y1 = (int)ceilf((y + h) * s);
  const int cy0 = c->cy0, cy1 = c->cy1;
  for (int py = y0; py < y1; ++py) {
    if (py < cy0 || py >= cy1) continue;
    const unsigned t = (unsigned)((py - y0) * 255 / (y1 - y0 > 1 ? y1 - y0 - 1 : 1));
    const unsigned a = ((top >> 24) * (255 - t) + (bottom >> 24) * t) / 255;
    const uint32_t color = (blend(top, bottom, t) & 0xffffff) | a << 24;
    c->cy0 = py;
    c->cy1 = py + 1;
    fill_round(c, x * s, y * s, w * s, h * s, radius * s, color);
  }
  c->cy0 = cy0;
  c->cy1 = cy1;
}

void sd_rect(sd_canvas *c, float x, float y, float w, float h, uint32_t color)
{
  const float s = c->scale;
  fill_round(c, x * s, y * s, w * s, h * s, 0, color);
}

void sd_round(sd_canvas *c, float x, float y, float w, float h, float radius, uint32_t color)
{
  const float s = c->scale;
  fill_round(c, x * s, y * s, w * s, h * s, radius * s, color);
}

/* coverage of a ring band: |d - r| < thick/2 */
static void band(sd_canvas *c, float cx, float cy, float r_in, float r_out, uint32_t color, float gap_angle)
{
  if (!c->px) return;
  int x0 = (int)floorf(cx - r_out - 1), x1 = (int)ceilf(cx + r_out + 1), y0 = (int)floorf(cy - r_out - 1),
      y1 = (int)ceilf(cy + r_out + 1);
  for (int y = y0; y < y1; ++y)
    for (int x = x0; x < x1; ++x) {
      const float dx = (float)x + 0.5f - cx, dy = (float)y + 0.5f - cy, d = sqrtf(dx * dx + dy * dy);
      float k = r_out - d + 0.5f;
      if (k > 1) k = 1;
      float inner = d - r_in + 0.5f;
      if (r_in > 0 && inner < k) k = inner > 1 ? 1 : inner;
      if (k <= 0) continue;
      if (gap_angle > 0) {  /* a gap centred on the top (the power symbol) */
        const float angle = atan2f(dx, -dy);
        if (fabsf(angle) < gap_angle) continue;
      }
      put(c, x, y, color, (unsigned)(k * 255 + 0.5f));
    }
}

void sd_circle(sd_canvas *c, float cx, float cy, float radius, uint32_t color)
{
  const float s = c->scale;
  band(c, cx * s, cy * s, 0, radius * s, color, 0);
}

void sd_ring(sd_canvas *c, float cx, float cy, float radius, float thick, uint32_t color)
{
  const float s = c->scale;
  band(c, cx * s, cy * s, (radius - thick / 2) * s, (radius + thick / 2) * s, color, 0);
}

void sd_round_outline(sd_canvas *c, float x, float y, float w, float h, float radius, float thick, uint32_t color)
{
  /* four sides and four arcs: enough for focus rings */
  const float s = c->scale;
  const float fx = x * s, fy = y * s, fw = w * s, fh = h * s, fr = radius * s, t = thick * s;
  if (!c->px) return;
  int y0 = (int)floorf(fy - 1), y1 = (int)ceilf(fy + fh + 1), x0 = (int)floorf(fx - 1), x1 = (int)ceilf(fx + fw + 1);
  for (int py = y0; py < y1; ++py)
    for (int px = x0; px < x1; ++px) {
      const float cxp = (float)px + 0.5f, cyp = (float)py + 0.5f;
      /* distance from the rounded rectangle's outline, inside positive */
      const float qx = fabsf(cxp - (fx + fw / 2)) - (fw / 2 - fr), qy = fabsf(cyp - (fy + fh / 2)) - (fh / 2 - fr);
      const float ox = qx > 0 ? qx : 0, oy = qy > 0 ? qy : 0;
      const float outside = sqrtf(ox * ox + oy * oy) + (qx > qy ? (qx < 0 ? qx : 0) : (qy < 0 ? qy : 0)) - fr;
      /* outline band: -t <= outside <= 0 */
      float k = fminf(-outside + 0.5f, outside + t + 0.5f);
      if (k <= 0) continue;
      if (k > 1) k = 1;
      put(c, px, py, color, (unsigned)(k * 255 + 0.5f));
    }
}

void sd_line(sd_canvas *c, float ax, float ay, float bx, float by, float thick, uint32_t color)
{
  const float s = c->scale;
  ax *= s, ay *= s, bx *= s, by *= s;
  const float r = thick * s / 2;
  if (!c->px) return;
  int x0 = (int)floorf(fminf(ax, bx) - r - 1), x1 = (int)ceilf(fmaxf(ax, bx) + r + 1);
  int y0 = (int)floorf(fminf(ay, by) - r - 1), y1 = (int)ceilf(fmaxf(ay, by) + r + 1);
  const float dx = bx - ax, dy = by - ay, len2 = dx * dx + dy * dy;
  for (int y = y0; y < y1; ++y)
    for (int x = x0; x < x1; ++x) {
      const float px = (float)x + 0.5f - ax, py = (float)y + 0.5f - ay;
      float t = len2 > 0 ? (px * dx + py * dy) / len2 : 0;
      t = t < 0 ? 0 : t > 1 ? 1 : t;
      const float ex = px - t * dx, ey = py - t * dy, d = sqrtf(ex * ex + ey * ey);
      float k = r - d + 0.5f;
      if (k <= 0) continue;
      put(c, x, y, color, (unsigned)((k > 1 ? 1 : k) * 255 + 0.5f));
    }
}

void sd_triangle(sd_canvas *c, float x0, float y0, float x1, float y1, float x2, float y2, uint32_t color)
{
  const float s = c->scale;
  x0 *= s, y0 *= s, x1 *= s, y1 *= s, x2 *= s, y2 *= s;
  if (!c->px) return;
  const float area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0);
  if (fabsf(area) < 1e-3f) return;
  const float sign = area > 0 ? 1.0f : -1.0f;
  int minx = (int)floorf(fminf(x0, fminf(x1, x2))), maxx = (int)ceilf(fmaxf(x0, fmaxf(x1, x2)));
  int miny = (int)floorf(fminf(y0, fminf(y1, y2))), maxy = (int)ceilf(fmaxf(y0, fmaxf(y1, y2)));
  const float ex[3][4] = {{x0, y0, x1, y1}, {x1, y1, x2, y2}, {x2, y2, x0, y0}};
  for (int y = miny; y <= maxy; ++y)
    for (int x = minx; x <= maxx; ++x) {
      const float px = (float)x + 0.5f, py = (float)y + 0.5f;
      float k = 1;
      for (int e = 0; e < 3; ++e) {
        const float ux = ex[e][2] - ex[e][0], uy = ex[e][3] - ex[e][1], len = sqrtf(ux * ux + uy * uy);
        const float d = sign * (ux * (py - ex[e][1]) - uy * (px - ex[e][0])) / len;  /* inside positive */
        const float edge = d + 0.5f;
        if (edge < k) k = edge;
      }
      if (k <= 0) continue;
      put(c, x, y, color, (unsigned)((k > 1 ? 1 : k) * 255 + 0.5f));
    }
}

void sd_icon(sd_canvas *c, int icon, float x, float y, float size, uint32_t color)
{
  const float cx = x + size / 2, cy = y + size / 2, u = size / 24;
  switch (icon) {
    case SD_ICON_POWER: {
      const float s = c->scale;
      band(c, cx * s, (cy + u) * s, (8 * u - u) * s, (8 * u + u) * s, color, 0.62f);
      sd_line(c, cx, cy - 9 * u, cx, cy + u, 2.2f * u, color);
      break;
    }
    case SD_ICON_PLAY: sd_triangle(c, x + 6 * u, y + 4 * u, x + 20 * u, cy, x + 6 * u, y + 20 * u, color); break;
    case SD_ICON_DOWNLOAD:
      sd_line(c, cx, y + 3 * u, cx, y + 15 * u, 2.4f * u, color);
      sd_line(c, cx - 6 * u, y + 10 * u, cx, y + 16 * u, 2.4f * u, color);
      sd_line(c, cx + 6 * u, y + 10 * u, cx, y + 16 * u, 2.4f * u, color);
      sd_line(c, x + 4 * u, y + 20 * u, x + 20 * u, y + 20 * u, 2.4f * u, color);
      break;
    case SD_ICON_CHECK:
      sd_line(c, x + 5 * u, y + 12.5f * u, x + 9.5f * u, y + 17 * u, 3 * u, color);
      sd_line(c, x + 9.5f * u, y + 17 * u, x + 19 * u, y + 7.5f * u, 3 * u, color);
      break;
    case SD_ICON_MONITOR:
      sd_round_outline(c, x + 3 * u, y + 4 * u, 18 * u, 13 * u, 1.5f * u, 2 * u, color);
      sd_line(c, x + 8 * u, y + 21 * u, x + 16 * u, y + 21 * u, 2 * u, color);
      sd_line(c, cx, y + 17 * u, cx, y + 21 * u, 2 * u, color);
      break;
    case SD_ICON_ARROW_RIGHT:
      sd_line(c, x + 3 * u, cy, x + 20 * u, cy, 2.4f * u, color);
      sd_line(c, x + 13 * u, cy - 7 * u, x + 20 * u, cy, 2.4f * u, color);
      sd_line(c, x + 13 * u, cy + 7 * u, x + 20 * u, cy, 2.4f * u, color);
      break;
    case SD_ICON_REFRESH: {
      const float s = c->scale;
      band(c, cx * s, cy * s, 6.5f * u * s, 8.5f * u * s, color, 0.7f);
      sd_triangle(c, cx + 2 * u, y + 1 * u, cx + 8 * u, y + 4.5f * u, cx + 2 * u, y + 8 * u, color);
      break;
    }
    case SD_ICON_STAR: {
      float px[10], py[10];
      for (int i = 0; i < 10; ++i) {
        const float a = -1.5707963f + i * 0.6283185f, r = (i & 1 ? 4.2f : 10) * u;
        px[i] = cx + cosf(a) * r;
        py[i] = cy + 1 * u + sinf(a) * r;
      }
      for (int i = 0; i < 10; ++i) sd_triangle(c, cx, cy + u, px[i], py[i], px[(i + 1) % 10], py[(i + 1) % 10], color);
      break;
    }
    case SD_ICON_CROSS:
      sd_line(c, x + 7 * u, y + 7 * u, x + 17 * u, y + 17 * u, 2.4f * u, color);
      sd_line(c, x + 17 * u, y + 7 * u, x + 7 * u, y + 17 * u, 2.4f * u, color);
      break;
    case SD_ICON_CIRCLE: sd_ring(c, cx, cy, 5.5f * u, 2.2f * u, color); break;
    case SD_ICON_TRIANGLE:
      sd_line(c, cx, y + 6 * u, x + 18 * u, y + 17 * u, 2.2f * u, color);
      sd_line(c, x + 18 * u, y + 17 * u, x + 6 * u, y + 17 * u, 2.2f * u, color);
      sd_line(c, x + 6 * u, y + 17 * u, cx, y + 6 * u, 2.2f * u, color);
      break;
    case SD_ICON_SQUARE: sd_round_outline(c, x + 7 * u, y + 7 * u, 10 * u, 10 * u, 0.5f * u, 2.2f * u, color); break;
    case SD_ICON_UP: sd_triangle(c, cx, y + 6 * u, x + 19 * u, y + 17 * u, x + 5 * u, y + 17 * u, color); break;
    case SD_ICON_DOWN: sd_triangle(c, x + 5 * u, y + 7 * u, x + 19 * u, y + 7 * u, cx, y + 18 * u, color); break;
    case SD_ICON_LEFT: sd_triangle(c, x + 6 * u, cy, x + 17 * u, y + 5 * u, x + 17 * u, y + 19 * u, color); break;
    case SD_ICON_RIGHT: sd_triangle(c, x + 7 * u, y + 5 * u, x + 18 * u, cy, x + 7 * u, y + 19 * u, color); break;
    case SD_ICON_LOGO: {
      /* OrbisDesk's logo: two panes, each split in a light and a dark half (tools/build-explorer-hw.py's blues) */
      static const float panes[6][8] = {{48, 24, 80, 16, 80, 229, 48, 240}, {99, 16, 216, 42, 216, 224, 99, 229},
                                        {48, 24, 80, 16, 80, 91, 48, 87},   {48, 111, 80, 115, 80, 229, 48, 240},
                                        {99, 16, 216, 42, 216, 109, 99, 94}, {99, 118, 216, 133, 216, 224, 99, 229}};
      static const uint32_t colors[6] = {0xff8fe0ff, 0xff8fe0ff, 0xff3a9cf0, 0xff155cb8, 0xff4fb3ff, 0xff1f7fe6};
      const float k = size / 256;
      for (int i = 0; i < 6; ++i) {
        const float *p = panes[i];
        sd_triangle(c, x + p[0] * k, y + p[1] * k, x + p[2] * k, y + p[3] * k, x + p[4] * k, y + p[5] * k, colors[i]);
        sd_triangle(c, x + p[0] * k, y + p[1] * k, x + p[4] * k, y + p[5] * k, x + p[6] * k, y + p[7] * k, colors[i]);
      }
      (void)color;
      break;
    }
  }
}

/* ---- fonts ---- */

typedef struct font {
  unsigned char *data;
  stbtt_fontinfo info;
  int ok;
  int ascent, descent, gap;
} font;
static font fonts[2];

static unsigned char *read_file(const char *path)
{
  /* read to the end, no fstat: inside OrbisDesk's title the client is built against another libc's
     headers, and 04.71 never loaded Tahoma (PWSTEAM ui fonts=bitmap) while open/read worked elsewhere */
  const int fd = open(path, O_RDONLY);
  if (fd < 0) return NULL;
  size_t size = 0, capacity = 0;
  unsigned char *data = NULL;
  for (;;) {
    if (size == capacity) {
      if (capacity >= (16u << 20)) break; /* no font is this big */
      capacity = capacity ? capacity * 2 : (256u << 10);
      unsigned char *grown = (unsigned char *)realloc(data, capacity);
      if (!grown) break;
      data = grown;
    }
    const ssize_t got = read(fd, data + size, capacity - size);
    if (got < 0) {
      size = 0;
      break;
    }
    if (got == 0) {
      close(fd);
      if (size) return data;
      free(data);
      return NULL;
    }
    size += (size_t)got;
  }
  close(fd);
  free(data);
  return NULL;
}

int sd_fonts_load(const char *regular_path, const char *bold_path)
{
  const char *paths[2] = {regular_path, bold_path};
  int loaded = 0;
  for (int i = 0; i < 2; ++i) {
    if (fonts[i].ok) {
      ++loaded;
      continue;
    }
    unsigned char *data = paths[i] ? read_file(paths[i]) : NULL;
    if (!data) continue;
    if (!stbtt_InitFont(&fonts[i].info, data, stbtt_GetFontOffsetForIndex(data, 0))) {
      free(data);
      continue;
    }
    fonts[i].data = data;
    stbtt_GetFontVMetrics(&fonts[i].info, &fonts[i].ascent, &fonts[i].descent, &fonts[i].gap);
    fonts[i].ok = 1;
    ++loaded;
  }
  /* bold falls back to the regular face */
  if (!fonts[1].ok && fonts[0].ok) {
    fonts[1] = fonts[0];
    fonts[1].data = NULL;  /* shared: not freed */
  }
  return loaded == 2 ? 0 : fonts[0].ok ? 1 : -1;
}

int sd_fonts_ready(void) { return fonts[0].ok; }

/* glyph cache: one alpha bitmap per (codepoint, pixel size, face) */
typedef struct glyph {
  uint32_t code;
  uint16_t px;
  uint8_t bold, used;
  int16_t x0, y0, w, h;
  float advance;  /* pixels */
  unsigned char *bits;
} glyph;
enum { GLYPHS = 1024 };
static glyph cache[GLYPHS];
static int cache_count;

static void cache_clear(void)
{
  for (int i = 0; i < GLYPHS; ++i) {
    free(cache[i].bits);
    cache[i].bits = NULL;
    cache[i].used = 0;
  }
  cache_count = 0;
}

static const glyph *get_glyph(uint32_t code, int px, int bold)
{
  unsigned slot = (code * 2654435761u ^ (unsigned)px * 40503u ^ (unsigned)bold * 977u) % GLYPHS;
  for (int probe = 0; probe < GLYPHS; ++probe, slot = (slot + 1) % GLYPHS) {
    glyph *g = &cache[slot];
    if (!g->used) break;
    if (g->code == code && g->px == px && g->bold == bold) return g;
  }
  if (cache_count > GLYPHS * 3 / 4) {
    cache_clear();
    slot = (code * 2654435761u ^ (unsigned)px * 40503u ^ (unsigned)bold * 977u) % GLYPHS;
  }
  while (cache[slot].used) slot = (slot + 1) % GLYPHS;
  glyph *g = &cache[slot];
  font *f = &fonts[bold ? 1 : 0];
  int index = stbtt_FindGlyphIndex(&f->info, (int)code);
  if (!index && code > 0x7f) index = stbtt_FindGlyphIndex(&f->info, '?');
  const float scale = stbtt_ScaleForMappingEmToPixels(&f->info, (float)px);
  int advance, lsb, x0, y0, x1, y1;
  stbtt_GetGlyphHMetrics(&f->info, index, &advance, &lsb);
  stbtt_GetGlyphBitmapBox(&f->info, index, scale, scale, &x0, &y0, &x1, &y1);
  g->code = code;
  g->px = (uint16_t)px;
  g->bold = (uint8_t)bold;
  g->used = 1;
  g->x0 = (int16_t)x0;
  g->y0 = (int16_t)y0;
  g->w = (int16_t)(x1 - x0);
  g->h = (int16_t)(y1 - y0);
  g->advance = (float)advance * scale;
  g->bits = NULL;
  if (g->w > 0 && g->h > 0) {
    g->bits = (unsigned char *)malloc((size_t)g->w * g->h);
    if (g->bits) stbtt_MakeGlyphBitmap(&f->info, g->bits, g->w, g->h, g->w, scale, scale, index);
  }
  ++cache_count;
  return g;
}

static uint32_t next_code(const char **s)
{
  const unsigned char *p = (const unsigned char *)*s;
  if (p[0] < 0x80) {
    ++*s;
    return p[0];
  }
  int length = p[0] >= 0xf0 ? 4 : p[0] >= 0xe0 ? 3 : p[0] >= 0xc0 ? 2 : 1;
  for (int i = 1; i < length; ++i)
    if ((p[i] & 0xc0) != 0x80) {
      *s += i;
      return 0xfffd;
    }
  uint32_t code = length == 2 ? p[0] & 0x1f : length == 3 ? p[0] & 0x0f : length == 4 ? p[0] & 0x07 : 0xfffd;
  for (int i = 1; i < length; ++i) code = code << 6 | (p[i] & 0x3f);
  *s += length;
  return code;
}

/* the 5x7 fallback: hw_glyphs' index, -1 for a blank */
static int bitmap_index(uint32_t code)
{
  if (code >= 'a' && code <= 'z') code -= 32;
  /* Latin-1 letters with marks drop their mark */
  static const char latin1[] = "AAAAAAACEEEEIIIIDNOOOOOxOUUUUYTsaaaaaaaceeeeiiiidnooooo/ouuuuyty";
  if (code >= 0xc0 && code <= 0xff) code = (uint32_t)latin1[code - 0xc0];
  if (code >= 'a' && code <= 'z') code -= 32;
  if (code >= 'A' && code <= 'Z') return (int)(code - 'A');
  if (code >= '0' && code <= '9') return 26 + (int)(code - '0');
  switch (code) {
    case ':': return 36;
    case '-': return 37;
    case '.': return 38;
    case '/': return 39;
    case '%': return 40;
  }
  return -1;
}

static int bitmap_scale(float px)
{
  const int k = (int)(px * 0.72f / 7 + 0.5f);
  return k < 1 ? 1 : k;
}

/* draws (pixels non-NULL) or measures; returns the advance in pixels */
static float run(sd_canvas *c, float x, float y, float size, int bold, uint32_t color, const char *text, int draw)
{
  const float px_f = size * c->scale;
  const int px = (int)(px_f + 0.5f) < 4 ? 4 : (int)(px_f + 0.5f);
  float pen = x;
  (void)hw_text;  /* hw_text.h's own drawer assumes pitch == width; this one clips */
  if (!fonts[0].ok) {
    const int k = bitmap_scale(px_f);
    const int top = (int)(y + (px_f * 1.2f - 7 * k) / 2);
    while (*text) {
      const uint32_t code = next_code(&text);
      const int g = bitmap_index(code);
      if (draw && g >= 0)
        for (int yy = 0; yy < 7; ++yy)
          for (int xx = 0; xx < 5; ++xx)
            if (hw_glyphs[g][yy] & (1 << (4 - xx)))
              for (int dy = 0; dy < k * (bold ? 1 : 1); ++dy)
                for (int dx = 0; dx < k + (bold ? 1 : 0); ++dx)
                  put(c, (int)pen + xx * k + dx, top + yy * k + dy, color, 255);
      pen += 6 * k;
    }
    return pen - x;
  }
  font *f = &fonts[bold ? 1 : 0];
  const float scale = stbtt_ScaleForMappingEmToPixels(&f->info, (float)px);
  /* the line box is 1.25 em (the mockups' CSS line-height): ascent+descent centred in it */
  const float content = (float)(f->ascent - f->descent) * scale;
  const int baseline = (int)(y + (px * 1.25f - content) / 2 + (float)f->ascent * scale + 0.5f);
  uint32_t previous = 0;
  while (*text) {
    const uint32_t code = next_code(&text);
    if (code == '\n') continue;
    if (previous) pen += (float)stbtt_GetCodepointKernAdvance(&f->info, (int)previous, (int)code) * scale;
    const glyph *g = get_glyph(code, px, bold);
    if (draw && g->bits && c->px) {
      const int gx = (int)(pen + 0.5f) + g->x0, gy = baseline + g->y0;
      for (int yy = 0; yy < g->h; ++yy) {
        const int py = gy + yy;
        if (py < c->cy0 || py >= c->cy1) continue;
        for (int xx = 0; xx < g->w; ++xx) {
          const unsigned a = g->bits[yy * g->w + xx];
          if (a) put(c, gx + xx, py, color, a);
        }
      }
    }
    pen += g->advance;
    previous = code;
  }
  return pen - x;
}

float sd_text(sd_canvas *c, float x, float y, float size, int bold, uint32_t color, const char *text)
{
  if (!text) return 0;
  return run(c, x * c->scale, y * c->scale, size, bold, color, text, 1) / c->scale;
}

float sd_text_width(const sd_canvas *c, float size, int bold, const char *text)
{
  if (!text) return 0;
  return run((sd_canvas *)c, 0, 0, size, bold, 0, text, 0) / c->scale;
}

float sd_text_right(sd_canvas *c, float x_right, float y, float size, int bold, uint32_t color, const char *text)
{
  const float w = sd_text_width(c, size, bold, text);
  return sd_text(c, x_right - w, y, size, bold, color, text);
}

float sd_text_fit(sd_canvas *c, float x, float y, float size, int bold, uint32_t color, const char *text, float max_width)
{
  if (!text) return 0;
  if (sd_text_width(c, size, bold, text) <= max_width) return sd_text(c, x, y, size, bold, color, text);
  char buffer[512];
  size_t length = strlen(text);
  if (length > sizeof(buffer) - 4) length = sizeof(buffer) - 4;
  while (length > 0) {
    /* back to a character boundary */
    while (length > 0 && ((unsigned char)text[length] & 0xc0) == 0x80) --length;
    memcpy(buffer, text, length);
    while (length > 0 && buffer[length - 1] == ' ') --length;
    memcpy(buffer + length, "...", 4);
    if (sd_text_width(c, size, bold, buffer) <= max_width) break;
    --length;
  }
  return sd_text(c, x, y, size, bold, color, buffer);
}

int sd_text_wrap(sd_canvas *c, float x, float y, float width, float size, float line, int bold, uint32_t color,
                 const char *text, int max_lines)
{
  if (!text) return 0;
  int lines = 0;
  char buffer[1024];
  while (*text) {
    if (max_lines && lines >= max_lines) break;
    const char *newline = strchr(text, '\n');
    const size_t paragraph = newline ? (size_t)(newline - text) : strlen(text);
    size_t take = 0, best = 0;
    /* the longest run of whole words that fits */
    while (take < paragraph) {
      size_t next = take;
      while (next < paragraph && text[next] == ' ') ++next;
      while (next < paragraph && text[next] != ' ') ++next;
      const size_t n = next < sizeof(buffer) - 1 ? next : sizeof(buffer) - 1;
      memcpy(buffer, text, n);
      buffer[n] = 0;
      if (best && sd_text_width(c, size, bold, buffer) > width) break;
      best = n;
      take = next;
      if (n == sizeof(buffer) - 1) break;
    }
    if (!best) best = paragraph < sizeof(buffer) - 1 ? paragraph : sizeof(buffer) - 1;
    memcpy(buffer, text, best);
    buffer[best] = 0;
    const int last = max_lines && lines + 1 == max_lines && best < paragraph;
    if (c->px) {
      if (last) sd_text_fit(c, x, y + lines * line, size, bold, color, text, width);  /* the rest, cut */
      else sd_text(c, x, y + lines * line, size, bold, color, buffer);
    }
    ++lines;
    text += best;
    while (*text == ' ') ++text;
    if (*text == '\n') ++text;
  }
  return lines;
}

/* ---- images ---- */

void sd_image_draw(sd_canvas *c, const sd_image *image, float x, float y, float w, float h, float radius, int dim,
                   int gray)
{
  if (!c->px || !image || !image->px || image->w < 1 || image->h < 1) return;
  const float s = c->scale, fx = x * s, fy = y * s, fw = w * s, fh = h * s, fr = radius * s;
  int x0 = (int)floorf(fx), y0 = (int)floorf(fy), x1 = (int)ceilf(fx + fw), y1 = (int)ceilf(fy + fh);
  if (x0 < c->cx0) x0 = c->cx0;
  if (y0 < c->cy0) y0 = c->cy0;
  if (x1 > c->cx1) x1 = c->cx1;
  if (y1 > c->cy1) y1 = c->cy1;
  const float sx = (float)image->w / fw, sy = (float)image->h / fh;
  for (int py = y0; py < y1; ++py) {
    float v = ((float)py + 0.5f - fy) * sy - 0.5f;
    if (v < 0) v = 0;
    int iy = (int)v;
    if (iy > image->h - 2) iy = image->h > 1 ? image->h - 2 : 0;
    float ty = image->h > 1 ? v - (float)iy : 0;
    if (ty > 1) ty = 1;
    const uint32_t *r0 = image->px + (size_t)iy * image->w, *r1 = image->h > 1 ? r0 + image->w : r0;
    uint32_t *out = c->px + (size_t)py * c->pitch;
    const int corner_row = fr > 0 && ((float)py + 0.5f < fy + fr || (float)py + 0.5f > fy + fh - fr);
    for (int px = x0; px < x1; ++px) {
      float cover = 1;
      if (corner_row) {
        const float cxp = (float)px + 0.5f, cyp = (float)py + 0.5f;
        if (cxp < fx + fr || cxp > fx + fw - fr) {
          const float ccx = cxp < fx + fr ? fx + fr : fx + fw - fr, ccy = cyp < fy + fr ? fy + fr : fy + fh - fr;
          const float k = fr - sqrtf((cxp - ccx) * (cxp - ccx) + (cyp - ccy) * (cyp - ccy)) + 0.5f;
          if (k <= 0) continue;
          if (k < 1) cover = k;
        }
      }
      float u = ((float)px + 0.5f - fx) * sx - 0.5f;
      if (u < 0) u = 0;
      int ix = (int)u;
      if (ix > image->w - 2) ix = image->w > 1 ? image->w - 2 : 0;
      float tx = image->w > 1 ? u - (float)ix : 0;
      if (tx > 1) tx = 1;
      const uint32_t a = r0[ix], b = r0[ix + (image->w > 1)], d = r1[ix], e = r1[ix + (image->w > 1)];
      float ch[3];
      for (int k = 0; k < 3; ++k) {
        const int sh = 16 - 8 * k;
        const float top = (float)((a >> sh) & 255) * (1 - tx) + (float)((b >> sh) & 255) * tx;
        const float bottom = (float)((d >> sh) & 255) * (1 - tx) + (float)((e >> sh) & 255) * tx;
        ch[k] = top * (1 - ty) + bottom * ty;
      }
      if (gray) ch[0] = ch[1] = ch[2] = ch[0] * 0.3f + ch[1] * 0.59f + ch[2] * 0.11f;
      const float keep = (float)(255 - dim) / 255;
      const uint32_t color = 0xff000000u | (uint32_t)(ch[0] * keep) << 16 | (uint32_t)(ch[1] * keep) << 8 |
                             (uint32_t)(ch[2] * keep);
      out[px] = blend(out[px], color, (unsigned)(cover * 255 + 0.5f));
    }
  }
}

void sd_qr(sd_canvas *c, const uint8_t *modules, int size, float x, float y, float side)
{
  const int total = size + 8;
  sd_round(c, x, y, side, side, 10, 0xffffffff);
  /* whole pixels per module, so every module is the same size and the code scans */
  const float s = c->scale;
  int m = (int)(side * s / (float)total);
  if (m < 1) m = 1;
  const int left = (int)((x + side / 2) * s) - m * size / 2, top = (int)((y + side / 2) * s) - m * size / 2;
  for (int my = 0; my < size; ++my)
    for (int mx = 0; mx < size; ++mx)
      if (modules[my * size + mx])
        for (int py = top + my * m; py < top + (my + 1) * m; ++py)
          for (int px = left + mx * m; px < left + (mx + 1) * m; ++px) put(c, px, py, 0xff000000u, 255);
}

#ifdef STEAM_HOST
/* ---- host PNG ---- */
static uint32_t crc_table[256];
static uint32_t crc32_update(uint32_t crc, const unsigned char *data, size_t n)
{
  if (!crc_table[1])
    for (uint32_t i = 0; i < 256; ++i) {
      uint32_t c = i;
      for (int k = 0; k < 8; ++k) c = c & 1 ? 0xedb88320u ^ (c >> 1) : c >> 1;
      crc_table[i] = c;
    }
  crc = ~crc;
  for (size_t i = 0; i < n; ++i) crc = crc_table[(crc ^ data[i]) & 255] ^ (crc >> 8);
  return ~crc;
}
static void be32(unsigned char *p, uint32_t v)
{
  p[0] = (unsigned char)(v >> 24), p[1] = (unsigned char)(v >> 16), p[2] = (unsigned char)(v >> 8), p[3] = (unsigned char)v;
}
static int chunk(FILE *f, const char *type, const unsigned char *data, size_t n)
{
  unsigned char head[8];
  be32(head, (uint32_t)n);
  memcpy(head + 4, type, 4);
  uint32_t crc = crc32_update(0, (const unsigned char *)type, 4);
  crc = crc32_update(crc, data, n);
  unsigned char tail[4];
  be32(tail, crc);
  return fwrite(head, 1, 8, f) == 8 && (n == 0 || fwrite(data, 1, n, f) == n) && fwrite(tail, 1, 4, f) == 4;
}
int sd_write_png(const sd_canvas *c, const char *path)
{
  const size_t row = (size_t)c->w * 3 + 1, raw_n = row * c->h;
  unsigned char *raw = (unsigned char *)malloc(raw_n);
  if (!raw) return -1;
  for (int y = 0; y < c->h; ++y) {
    unsigned char *r = raw + row * y;
    r[0] = 0;
    for (int x = 0; x < c->w; ++x) {
      const uint32_t p = c->px[(size_t)y * c->pitch + x];
      r[1 + x * 3] = (unsigned char)(p >> 16), r[2 + x * 3] = (unsigned char)(p >> 8), r[3 + x * 3] = (unsigned char)p;
    }
  }
  /* zlib with stored blocks */
  const size_t blocks = (raw_n + 65534) / 65535;
  const size_t z_n = 2 + raw_n + blocks * 5 + 4;
  unsigned char *z = (unsigned char *)malloc(z_n);
  if (!z) {
    free(raw);
    return -1;
  }
  size_t at = 0;
  z[at++] = 0x78, z[at++] = 0x01;
  uint32_t s1 = 1, s2 = 0;
  for (size_t i = 0; i < raw_n; ++i) s1 = (s1 + raw[i]) % 65521, s2 = (s2 + s1) % 65521;
  for (size_t done = 0; done < raw_n;) {
    const size_t n = raw_n - done > 65535 ? 65535 : raw_n - done;
    z[at++] = done + n == raw_n ? 1 : 0;
    z[at++] = (unsigned char)n, z[at++] = (unsigned char)(n >> 8);
    z[at++] = (unsigned char)~n, z[at++] = (unsigned char)(~n >> 8);
    memcpy(z + at, raw + done, n);
    at += n;
    done += n;
  }
  be32(z + at, s2 << 16 | s1);
  at += 4;
  FILE *f = fopen(path, "wb");
  int ok = f != NULL;
  if (f) {
    static const unsigned char signature[8] = {0x89, 'P', 'N', 'G', 13, 10, 26, 10};
    unsigned char ihdr[13];
    be32(ihdr, (uint32_t)c->w);
    be32(ihdr + 4, (uint32_t)c->h);
    ihdr[8] = 8, ihdr[9] = 2, ihdr[10] = 0, ihdr[11] = 0, ihdr[12] = 0;
    ok = fwrite(signature, 1, 8, f) == 8 && chunk(f, "IHDR", ihdr, 13) && chunk(f, "IDAT", z, at) &&
         chunk(f, "IEND", NULL, 0);
    ok = fclose(f) == 0 && ok;
  }
  free(raw);
  free(z);
  return ok ? 0 : -1;
}
#endif
