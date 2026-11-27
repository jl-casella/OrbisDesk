/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef PW_HW_PAD_REMAP_H
#define PW_HW_PAD_REMAP_H
/* Apply once, after native menus consume the physical pad and before pad_last is
 * published. XInput, HID/DualSense and keyboard/mouse profiles share this state. */
enum {PW_PAD_SWAP_STICKS=1,PW_PAD_SWAP_BUTTONS=2};
static inline uint32_t pw_pad_swap_pair(uint32_t buttons,uint32_t a,uint32_t b)
{
    return (buttons&~(a|b)) | (buttons&a?b:0) | (buttons&b?a:0);
}
static inline void pw_pad_remap(OrbisPadData *data,unsigned options)
{
    if(options&PW_PAD_SWAP_STICKS) {
        uint8_t x=data->leftStick.x,y=data->leftStick.y;
        data->leftStick.x=data->rightStick.x;data->leftStick.y=data->rightStick.y;
        data->rightStick.x=x;data->rightStick.y=y;
        data->buttons=pw_pad_swap_pair(data->buttons,ORBIS_PAD_BUTTON_L3,ORBIS_PAD_BUTTON_R3);
    }
    if(options&PW_PAD_SWAP_BUTTONS) {
        data->buttons=pw_pad_swap_pair(data->buttons,ORBIS_PAD_BUTTON_CROSS,ORBIS_PAD_BUTTON_CIRCLE);
        data->buttons=pw_pad_swap_pair(data->buttons,ORBIS_PAD_BUTTON_SQUARE,ORBIS_PAD_BUTTON_TRIANGLE);
    }
}
#endif
