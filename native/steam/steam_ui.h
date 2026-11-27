/* SPDX-License-Identifier: GPL-3.0-or-later */
/* The Steam client's screen and pad. Two kinds of frames, both drawn by the caller's thread into a frame of
 * their own (never on the compositor's), then published:
 *   - pages of text, optionally with a QR code (steam_ui_show), drawn in Big Picture's look as a dialog;
 *   - Big Picture's screens (docs/STEAM_BIG_PICTURE.md): steam_ui_begin hands a canvas (steam_draw.h), the
 *     caller draws, steam_ui_end publishes it.
 * The pad's X, O, triangle, square, the directions (d-pad or left stick, repeated while held), L1/L2, R1/R2 and
 * OPTIONS. On the host the frames go to stdout as text (and to PNG files with STEAM_UI_SNAPSHOTS=<dir>) and
 * the buttons come from stdin lines ("x", "o", "t", "s", "u", "d", "<", ">", "l", "r", "p"). */
#ifndef STEAM_UI_H
#define STEAM_UI_H
#ifdef __cplusplus
extern "C" {
#endif

/* STEAM_UI_L1 is L1 or L2, STEAM_UI_R1 is R1 or R2 (the triggers' digital press). */
enum {
  STEAM_UI_CROSS = 1, STEAM_UI_CIRCLE = 2, STEAM_UI_TRIANGLE = 4, STEAM_UI_UP = 8, STEAM_UI_DOWN = 16,
  STEAM_UI_L1 = 32, STEAM_UI_R1 = 64, STEAM_UI_SQUARE = 128, STEAM_UI_OPTIONS = 256, STEAM_UI_LEFT = 512,
  STEAM_UI_RIGHT = 1024
};

/* A page line that starts with this byte is drawn highlighted (a list's selected entry). */
#define STEAM_UI_MARK '\x01'
/* A page line that starts with this byte begins the footer: its last line is the buttons' help, drawn as
 * Big Picture's hint bar ("X: ACCEPT     O: EXIT": segments two or more spaces apart); the lines before it a
 * status under the dialog. */
#define STEAM_UI_FOOTER '\x02'
/* A page line that starts with this byte is a warning, drawn in amber. */
#define STEAM_UI_WARN '\x03'
/* Inside a line, this byte draws the line in the highlight color. */
#define STEAM_UI_ACCENT '\x04'

typedef void (*steam_ui_note)(const char *format, ...);

/* 0 when the screen and the pad are ready; otherwise each failing call is logged and nothing can be shown. */
int steam_ui_open(steam_ui_note note);
/* Replaces the screen with a page. text: lines separated by '\n'; the first line is the dialog's label, a
 * short second one its title. qr: text to show as a QR code beside it, or NULL (kept only as the drawn
 * modules, never logged). Buttons pressed before it are dropped. 0 on success; -1 when the QR text doesn't fit. */
int steam_ui_show(const char *text, const char *qr);

/* A Big Picture frame: steam_ui_begin returns the canvas to draw on (the caller's thread draws; one frame at a
 * time), steam_ui_end publishes it. summary: the frame as text, for the host's stdout and tests (never logged
 * on the console). Buttons pressed meanwhile are kept. */
struct sd_canvas;
void steam_ui_begin(struct sd_canvas *canvas);
void steam_ui_end(const char *summary);

/* The buttons pressed since the last call (or since the last page), as STEAM_UI_* bits. */
unsigned steam_ui_take(void);
/* Waits until one of `mask` is pressed and returns it. */
unsigned steam_ui_wait(unsigned mask);
/* As steam_ui_wait, for at most timeout_ms; 0 when the time ran out or steam_ui_poke woke it. */
unsigned steam_ui_wait_for(unsigned mask, int timeout_ms);
/* Wakes a steam_ui_wait_for (a cover arrived, a download moved on): the screen should be drawn again. */
void steam_ui_poke(void);

/* Inside OrbisDesk's title: while a game started from Big Picture is in front the client's screen is hidden
 * and the game has the pad. steam_ui_show_requested() is 1 once after the overlay's Steam entry (or the Start
 * menu's) asked for the client again. Elsewhere hiding only stops drawing. */
void steam_ui_hide(void);
void steam_ui_unhide(void);
int steam_ui_hidden(void);
void steam_ui_request_show(void);
int steam_ui_show_requested(void);

void steam_ui_close(void);

/* The client is past its start (network, session, library): it shows Big Picture, the sign-in or a failure page
 * of its own. Only then does a Big Picture start count as one that worked (pw_hw_bigpicture_ready): a client
 * that dies earlier leaves the marker, and the next start is the desktop's (hardware 2026-11-25: an abort in the
 * network's start looped every Big Picture start, its first frame had already cleared the marker). */
void steam_ui_started(void);

#ifdef STEAM_UI_HOSTED
/* Inside OrbisDesk's title. The sink calls pw_hw_steam_draw() for every frame it shows (1: the Steam
 * frame covered it); the pad thread calls pw_hw_steam_pad() with every read (1: the client has the pad,
 * which the desktop then reads neutral). `data` is an OrbisPadData. */
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
