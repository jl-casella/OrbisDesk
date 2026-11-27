/* SPDX-License-Identifier: GPL-3.0-or-later */
/* The Steam client's drawing (docs/STEAM_BIG_PICTURE.md): a CPU canvas for Big Picture's frames.
 * Coordinates are design units of a 1920x1080 screen, scaled to the canvas (1280x720 inside OrbisDesk's
 * title, 1920x1080 for the standalone title). Colors are 0xAARRGGBB; alpha below 0xff blends.
 * Text is Tahoma (Wine's own, stb_truetype) when sd_fonts_load found it; otherwise native/hw_text.h's
 * 5x7 capitals, scaled, so the standalone title still shows every page. Not thread-safe: one canvas is
 * drawn at a time (steam_ui.c serializes them). */
#ifndef STEAM_DRAW_H
#define STEAM_DRAW_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

typedef struct sd_canvas {
  uint32_t *px;
  int w, h, pitch;   /* pixels */
  float scale;       /* pixels per design unit */
  int cx0, cy0, cx1, cy1;  /* clip, pixels */
} sd_canvas;

typedef struct sd_image {
  int w, h;
  const uint32_t *px;  /* 0xAARRGGBB, w*h */
} sd_image;

void sd_begin(sd_canvas *c, uint32_t *pixels, int width, int height, int pitch);
/* clip to a design-unit rectangle (intersected with the canvas); sd_unclip restores the whole canvas */
void sd_clip(sd_canvas *c, float x, float y, float w, float h);
void sd_unclip(sd_canvas *c);

void sd_gradient(sd_canvas *c, uint32_t top, uint32_t bottom);  /* the whole canvas */
void sd_rect(sd_canvas *c, float x, float y, float w, float h, uint32_t color);
void sd_round(sd_canvas *c, float x, float y, float w, float h, float radius, uint32_t color);
void sd_round_gradient(sd_canvas *c, float x, float y, float w, float h, float radius, uint32_t top, uint32_t bottom);
void sd_round_outline(sd_canvas *c, float x, float y, float w, float h, float radius, float thick, uint32_t color);
void sd_circle(sd_canvas *c, float cx, float cy, float radius, uint32_t color);
void sd_ring(sd_canvas *c, float cx, float cy, float radius, float thick, uint32_t color);
void sd_line(sd_canvas *c, float x0, float y0, float x1, float y1, float thick, uint32_t color);
void sd_triangle(sd_canvas *c, float x0, float y0, float x1, float y1, float x2, float y2, uint32_t color);

/* Icons in a size x size box at (x, y). */
enum { SD_ICON_POWER, SD_ICON_PLAY, SD_ICON_DOWNLOAD, SD_ICON_CHECK, SD_ICON_MONITOR, SD_ICON_ARROW_RIGHT,
       SD_ICON_REFRESH, SD_ICON_STAR, SD_ICON_CROSS, SD_ICON_CIRCLE, SD_ICON_TRIANGLE, SD_ICON_SQUARE, SD_ICON_LOGO,
       SD_ICON_UP, SD_ICON_DOWN, SD_ICON_LEFT, SD_ICON_RIGHT };
void sd_icon(sd_canvas *c, int icon, float x, float y, float size, uint32_t color);

/* Fonts: 0 when both TTF files loaded. The bytes are read once and kept. */
int sd_fonts_load(const char *regular_path, const char *bold_path);
int sd_fonts_ready(void);
/* Text: (x, y) is the top of a line of `size` design units (a CSS font-size); returns the advance in design
 * units. UTF-8. */
float sd_text(sd_canvas *c, float x, float y, float size, int bold, uint32_t color, const char *text);
float sd_text_width(const sd_canvas *c, float size, int bold, const char *text);
/* cut with "..." to max_width */
float sd_text_fit(sd_canvas *c, float x, float y, float size, int bold, uint32_t color, const char *text, float max_width);
/* right-aligned at x_right */
float sd_text_right(sd_canvas *c, float x_right, float y, float size, int bold, uint32_t color, const char *text);
/* word-wrapped to `width`, `line` design units apart, at most max_lines (0: no limit); returns the lines used.
 * pixels NULL in c only measures. */
int sd_text_wrap(sd_canvas *c, float x, float y, float width, float size, float line, int bold, uint32_t color,
                 const char *text, int max_lines);

/* An image scaled (bilinear) into the rectangle, its corners rounded; dim 0..255 darkens it, gray 1 removes
 * its color (a cover on an unplugged drive). */
void sd_image_draw(sd_canvas *c, const sd_image *image, float x, float y, float w, float h, float radius, int dim,
                   int gray);

/* QR modules (1 dark), with a quiet zone of 4 modules, on white, in a side x side square */
void sd_qr(sd_canvas *c, const uint8_t *modules, int size, float x, float y, float side);

#ifdef STEAM_HOST
/* host snapshots: the canvas as an RGB PNG (uncompressed deflate). 0 on success. */
int sd_write_png(const sd_canvas *c, const char *path);
#endif

#ifdef __cplusplus
}
#endif
#endif
