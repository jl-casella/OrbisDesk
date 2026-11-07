<a id="w141-flechas-como-teclas-extendidas-por-vk-fase-5"></a>


# W141: arrows as extended keys, by VK (phase 5)

[English](HARDWARE_W141.md) | [Español](HARDWARE_W141-es.md)

APP_VER 02.40. Base W140.

<a id="problema"></a>


## Problem

In W140 the driver asked `MapVirtualKeyEx(..., MAPVK_VK_TO_VSC_EX)` and marked the key as extended if the result had prefix `E0`. For arrows that never happens, because in the table `kbdus` of Wine the can code 0x4d without prefix also corresponds to `VK_RIGHT`, and is the first to find. DirectInput then received the 6 of the numerical keyboard instead of the arrow.

<a id="cambio"></a>


## Change

In `ps5drv.c` (overlay of `tools/build-win32u-ps4.py`) the driver commands with `KEYEVENTF_EXTENDEDKEY` keys that a PC keyboard sends with prefix `E0`:
- the arrows;
- Insert/Delete/Home/End/ReP ág / AvPág;
- Ctrl and Alt rights;
- `/` of the numerical keyboard, the keys Windows and Menu.

The scan code is still that of `MAPVK_VK_TO_VSC`.

The log of the 32 bit programs adds up `trace+dinput`, to see which DIK code receives DirectInput for each key.

<a id="qué-se-espera"></a>


## What is expected

- The arrows move the selection of the SuperMarioKart menu.
- In the log, `dinput_keyboard_hook` with `vkCode 0x27` and the key `cd` (`DIK_RIGHT`) in `setting key`.

<a id="prueba-física"></a>


## Physical test

`reports/wine-hardware-w141/physical/20261103T074002Z`. The user confirms: **the arrows move the selection of the** menu.

With `trace+dinput` it is seen that the game creates a keyboard device of DirectInput (256 bytes format, `DISCL_EXCLUSIVE | DISCL_FOREGROUND`, 32 buffer), But he never gets it. There are no `Acquire`, no state readings, no hook events. The keys come to you through the window messages. The arrangement works because the game weapons the key code with the scan code and the `lParam` extended key bit of `WM_KEYDOWN`, which also depend on `KEYEVENTF_EXTENDEDKEY`. The notes of W140 that speak of DirectInput describe the mechanism of Wine, but the game does not pass through.

<a id="estado-de-supermariokart-fase-5"></a>


## SuperMarioKart state (phase 5)

- Start with CPU of 32 native bits (W137).
- MIDI music with battery (W139/W140).
- Sound effects.
- Enter, Back and arrows in the menu (W141).
- pending: ~ 12 FPS (presentation or game limit) and xinput for controls.
