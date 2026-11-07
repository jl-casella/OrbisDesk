/* SPDX-License-Identifier: GPL-3.0-or-later */
/* S3's screen: one page of text, and optionally a QR code, on a framebuffer of its own (sceVideoOut),
 * with the pad's X, O and triangle. A thread of its own draws and reads the pad, so the page stays up
 * while the caller waits on the network. On the host the page goes to stdout and the buttons come
 * from stdin lines ("x", "o", "t"). */
#ifndef STEAM_UI_H
#define STEAM_UI_H
#ifdef __cplusplus
extern "C" {
#endif

enum { STEAM_UI_CROSS = 1, STEAM_UI_CIRCLE = 2, STEAM_UI_TRIANGLE = 4 };

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

#ifdef __cplusplus
}
#endif
#endif
