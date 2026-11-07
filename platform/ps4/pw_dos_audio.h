/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef PW_DOS_AUDIO_H
#define PW_DOS_AUDIO_H
#include <stdint.h>
#define PW_DOS_AUDIO_CLASS 0x50444155u
enum {PW_DOS_AUDIO_OPEN=1,PW_DOS_AUDIO_SUBMIT=2,PW_DOS_AUDIO_CLOSE=3};
struct pw_dos_audio_packet {
    uint32_t size,version,action,sample_rate,frames,flags;
    uint64_t pcm,token;
    int32_t status;
    uint32_t reserved;
};
_Static_assert(sizeof(struct pw_dos_audio_packet)==48,"DOS audio ABI");
#endif
