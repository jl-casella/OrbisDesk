/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* W120: the title's audio sink for Wine's audio driver (wineps4, from prospero-win's
 * wineps5): one AudioOut main port, 48 kHz signed 16-bit stereo, played
 * PW_WINE_AUDIO_GRAIN frames at a time. */
#ifndef PW_WINE_AUDIO_H
#define PW_WINE_AUDIO_H
#include <stdint.h>
enum { PW_WINE_AUDIO_RATE=48000,PW_WINE_AUDIO_GRAIN=256 };
/* 1 when the port can be opened (or is open), 0 with the reason in the log */
int pw_wine_audio_available(void);
/* plays one grain; blocks until the port takes it. 0, or the AudioOut error */
int pw_wine_audio_output(const int16_t *frames);
#endif
