<a id="w178-parte-del-mando-xinput-con-el-mando-de-la-ps4-modo-juego-y-joycpl-fase-7"></a>


# W178, part of the control: XInput with the control of PS4, game mode and joy.cpl (phase 7)

[English](HARDWARE_W178-mando-borrador.md) | [Español](HARDWARE_W178-mando-borrador-es.md)

Eraser of the side setting session of Wine. The main session adds it to `HARDWARE_W178.md`. DirectInput is left for W179.

<a id="punto-de-partida"></a>


## Point of departure

- `native/hw_pad.c` reads the control every 16 ms and turns it into mouse and keyboard:
  - left stick and touchpad: pointer; right stick: wheel;
  - X: click; Circle: right click;
  - cruise: arrows; Triangle: Enter; Square: Escape; Options: key Windows.
- No game saw the command:
  - xinput was not in the prefix;
  - the xinput of Wine seeks controls for HID (winebus and hidclass under winedevice), which a title of PS4 does not have.

<a id="cambios"></a>


## Changes

- `tools/build-xinput-hw.py` (new): xinput with the console control as the 0 controller. It is the 0470 patch method of prospero-win, rewritten for the Wine set, whose context is different.
  - xinput wins a Unix bookstore by name (`xinput1_3`), shared by xinput1_1, 1 _ 2, 1 _ 3 and 1 _ 4 (x86_64 and i386).
  - If you respond, the 0 controller is the control and does not start the HID thread:
    - `XInputGetState(Ex)` and `XInputGetKeystroke` read their status;
    - `XInputSetState` and `XInputEnable` pass the vibration;
    - `XInputGetCapabilities(Ex)` reports a command of Xbox 360 with cable (045e: 028e), which is what games are looking for;
    - `XInputGetBatteryInformation`: cable.
  - `xinput9_1_0` sends to `xinput1_4` And it goes unchanged. The `hid.dll` of 64 bits, which xinput matters and the prefix did not have.
  - The Unix part calls direct to `pw_wine_pad_available`, `pw_wine_pad` and `pw_wine_set_rumble`, because the ELF is static. Its tables are called `pw_xinput_unix_call_funcs` and `pw_xinput_unix_call_wow64_funcs`.
  - One single command: the four of 0471 are left for later.
- `native/hw_pad.c`:
  - remains the only one who reads the command and saves its last state, with a package number that changes with each input;
  - `pw_wine_pad` gives it in terms of XInput:
    - Cruz/C circle / Cuadrado/Tri angle → A/B/X/Y; L1/R1 → LB/RB; L2/R2 → analog triggers; L3/R3 → press the sticks;
    - Options → Start; clic del touchpad → Back; cruceta → DPAD;
    - sticks from 0.. 255 to − 32768.. 32767, with Y up;
  - `pw_wine_set_rumble`: `scePadSetVibration` (left engine = large). If it fails, `PWPAD rumble_failed rc=...`.
- **Game mode** in `hw_pad.c`:
  - as long as some program has read the command by XInput in the last second, the sticks and buttons stop moving the pointer and send clicks and keys; so a game does not also receive clicks, arrows, Enter and Escape;
  - When entering, the buttons that the emulation had tight are released;
  - the touchpad movement continues to move the pointer (XInput has no touchpad), and its click is the Game Back;
  - the mouse and USB keyboard do not change;
  - one line `PWPAD game_mode=1` or `PWPAD game_mode=0` at each change.
- `platform/ps4/pw_wine_unixlibs.c`:
  - the entry `xinput1_3.so`;
  - weak "no-command" definitions for `ntdll.so` and `bootstrap.elf`, which do not carry `hw_pad.c`: there xinput follows for HID;
  - the name load accepts a name without extension (`xinput1_3` → `xinput1_3.so`), in addition to `<x>.drv`.
- `tools/link-wine-boot.py`: ties `xinput-unix.o`, with verification of your sha256.
- `tools/stage-wine-programs.py`:
  - sum `control.exe` and `joy.cpl`;
  - the closing leaves `xinput*`. Without that, `joy.cpl` he brought the `xinput1_3.dll` without patching.
- `tools/make-start-menu.py`: "Game Controllers" in System Tools (`control.exe joy.cpl`). The other accesses don't change, not even your hash.
- `tools/build-wine-hardware.py`:
  - xinput and `hid.dll` copy to the building folders and to `system32` / `syswow64`;
  - the `user_reg_reset` of W177, which was one time, is removed.

Check without the console:
- all compiles without warning (`hw_pad.c` and `pw_wine_unixlibs.c` with the options of the launcher and `-Wall`; xinput with the fixed build commands);
- a partial link of `hw_pad.o` + `pw_wine_unixlibs.o` + `xinput-unix.o` resolves the three functions to those of `hw_pad.c`.

To build:
1. `tools/build-xinput-hw.py`, `tools/stage-wine-programs.py` and `tools/make-start-menu.py` (all three already running);
2. `tools/link-wine-boot.py`, because it changes the ELF;
3. the usual chain.

<a id="prueba"></a>


## Test

1. Start → System Tools → Game Controllers → XInput tab:
   - the 0 controller is connected;
   - the buttons, sticks and triggers move in the drawing;
   - The vibration button vibrates the control.
2. With that open tab: on the log, `PWPAD game_mode=1`.
   - The sticks and buttons do not move the pointer; The touchpad does.
   - When changing the tab or closing the panel, `PWPAD game_mode=0` and the control is again mouse.
3. A game with XInput, 32 or 64 bit:
   - Responds to command;
   - no more clicks or keys appear;
   - If the game vibrates, it vibrates the command.
4. Return: without open games the control remains mouse and keyboard as before; mouse and USB keyboard, same.

Risks:
- A program that reads XInput without being a game (`joy.cpl`) also activates the game mode while doing it. The touchpad keeps moving the pointer.
- A game that reads the command only from time to time (less than once per second) would receive clicks of the emulation between readings.
- The DirectInput tab of `joy.cpl` does not list anything until W179.
