/* SPDX-License-Identifier: GPL-3.0-or-later */
/* S3's screen: one page of text, and optionally a QR code, on a framebuffer of its own (sceVideoOut),
 * with the pad's X, O and triangle. A thread of its own draws and reads the pad, so the page stays up
 * while the caller waits on the network. On the host the page goes to stdout and the buttons come
 * from stdin lines ("x", "o", "t", "u", "d", and "l", "r", "s", "p" for L1, R1, square and OPTIONS). */
#ifndef STEAM_UI_H
#define STEAM_UI_H
#ifdef __cplusplus
extern "C" {
#endif

/* STEAM_UI_L1 is L1 or L2, STEAM_UI_R1 is R1 or R2 (the triggers' digital press): the library's
 * tabs answer either pair. */
enum {
  STEAM_UI_CROSS = 1, STEAM_UI_CIRCLE = 2, STEAM_UI_TRIANGLE = 4, STEAM_UI_UP = 8, STEAM_UI_DOWN = 16,
  STEAM_UI_L1 = 32, STEAM_UI_R1 = 64, STEAM_UI_SQUARE = 128, STEAM_UI_OPTIONS = 256
};

/* A page line that starts with this byte is drawn highlighted (a list's selected entry). */
#define STEAM_UI_MARK '\x01'
/* A page line that starts with this byte begins the footer: it and every line after it are drawn in a
 * band fixed at the bottom of the screen (the page's status and the buttons' help), whatever the
 * length of the list above it, which is cut where the band starts. */
#define STEAM_UI_FOOTER '\x02'
/* A page line that starts with this byte is a warning, drawn in amber (DRM OrbisDesk can't run, an
 * uninstall that can't be undone). */
#define STEAM_UI_WARN '\x03'
/* Inside a line, this byte switches the letters after it to the accent color and back (the library's
 * active tab: the font has no brackets). */
#define STEAM_UI_ACCENT '\x04'

typedef void (*steam_ui_note)(const char *format, ...);

/* 0 when the screen and the pad are ready; otherwise each failing call is logged and the page can't
 * be shown (the caller stops: nothing in S3 runs without the user seeing it). */
int steam_ui_open(steam_ui_note note);
/* Replaces the page. text: lines separated by '\n', wrapped to the page; the first line is the title.
 * qr: text to show as a QR code beside it, or NULL. The QR's text is kept only as the drawn modules,
 * never logged. 0 on success; -1 when the QR text doesn't fit a QR code. */
int steam_ui_show(const char *text, const char *qr);
/* The buttons pressed since the last call (or since the page changed), as STEAM_UI_* bits. */
unsigned steam_ui_take(void);
/* Waits until one of `mask` is pressed and returns it. */
unsigned steam_ui_wait(unsigned mask);
void steam_ui_close(void);

#ifdef STEAM_UI_HOSTED
/* Inside OrbisDesk's title. The sink calls pw_hw_steam_draw() for every frame it shows (1: the Steam
 * page covered the frame); the pad thread calls pw_hw_steam_pad() with every read (1: the client has
 * the pad, which the desktop then reads neutral). `data` is an OrbisPadData. */
#include <stdint.h>
int pw_hw_steam_active(void);
int pw_hw_steam_draw(uint32_t *pixels, unsigned pitch, unsigned width, unsigned height);
struct OrbisPadData;
int pw_hw_steam_pad(const struct OrbisPadData *data);
#endif

#ifdef __cplusplus
}
#endif
#endif
