<a id="fase-7-resto-mando-de-la-ps4-por-xinput-y-directinput-y-joycpl-plan-borrador"></a>


# Phase 7, rest: command of PS4 by XInput and DirectInput, and joy.cpl (plan, draft)

[English](HARDWARE_fase7-mando-plan-borrador.md) | [Español](HARDWARE_fase7-mando-plan-borrador-es.md)

<a id="punto-de-partida"></a>


## Point of departure

- `native/hw_pad.c` is the only one who reads the command: `scePadReadState` every 16 ms in a thread, and everything becomes a mouse and keyboard.
  - Left stick and touchpad: pointer. Right stick: wheel.
  - X: left click. Circle, or two fingers on the touchpad: right click.
  - Cruise: arrows. Triangle: Enter. Square: Escape. Options: key Windows.
- In the prefix are not xinput (1 _ 1, 1 _ 2, 1 _ 3, 1 _ 4, 9 _ 1 _ 0), `joy.cpl` or `control.exe`. They are compiled in the tree fixed, x86_64 and i386.
- The Wine xinput looks for HID controls (winebus/hidclass, with winedavice), which in a title does not exist. The DirectInput of Wine finds joysticks only by HID (`dinput/joystick_hid.c`). The `hid.dll` 64 bit is not even in the prefix.
- prospero-win resolved XInput with 0470/0471:
  - xinput wins a Unix bookstore (`xinput1_3.so`, by name) that reads the state of the command that keeps the title and passes the vibration;
  - with a title, the 0 controller is that of the title and does not start the HID thread;
  - `XInputGetCapabilities` reports a command of Xbox 360 with cable (045e: 028e).
- `joy.cpl` has an XInput tab (`dlls/joy.cpl/xinput.c`: `XInputGetCapabilities`, `XInputGetStateEx` and `XInputSetState` to test vibration) and a tab DirectInput (`EnumDevices DI8DEVCLASS_GAMECTRL`.

<a id="diseño"></a>


## Design

1. **A single control reader.** `hw_pad.c` remains the only one calling `scePadReadState`. Save the last state with a package number and export:
   - `pw_wine_pad(state)`: the state in terms of `XINPUT_GAMEPAD`.
     - Cruz/C circle / Cuadrado/Tri angle → A/B/X/Y.
     - L1/R1 → LB/RB; L2/R2 → analog triggers; L3/R3 → press the sticks.
     - Options → Start; Touchpad pressed → Back (Share takes it from the system).
     - Cruise → DPAD. Stick from 0.. 255 to − 32768.. 32767, with Y inverted as in XInput.
   - `pw_wine_set_rumble(left, right)`: `scePadSetVibration`.
2. **XInput.**
   - New build `tools/build-xinput-hw.py`: overlay of `dlls/xinput1_3` with 0470/0471 adapted.
     - The Unix part calls `pw_wine_pad` and `pw_wine_set_rumble` directly (all is a ELF static: there is `dlsym`).
     - Compound the PE of xinput1_1, 1 _ 2, 1 _ 3 and 1 _ 4 (the four leave that source) in x86_64 and i386; xinput9_1_0 is reviewed separately.
     - Compile the Unix object with `__wine_unix_call_funcs` renamed.
   - A single command (the initial user). 0471 (four controls) is left for later: today `hw_pad.c` only opens the initial user.
   - The Unix part enters the table of `platform/ps4/pw_wine_unixlibs.c` as `xinput1_3.so`.
     - `pw_wine_static_unixlib_by_name` today only accept names `.drv`; you also have to accept a name without extension (`xinput1_3` → `xinput1_3.so`), because it is thus charged 0470.
3. **Who receives the command (the main risk).** No change, a game reading XInput would receive the command **and** in addition to clicks, arrows, Enter and Escape from emulation.
   - **Game mode:** as long as some program has read XInput in the last second, `hw_pad.c` stop turning the sticks and buttons into mouse and keyboard. The game only gets XInput.
   - When the game is closed, or when you stop reading XInput, you return the emulation alone, in less than a second.
   - The **touchpad movement** continues to move the pointer also in game mode: XInput has no touchpad. It serves not to be left without a pointer, for example in the `joy.cpl` XInput tab, which reads the control while it is visible. The click of the touchpad becomes Back.
   - The mouse and USB keyboard do not change.
   - A log line when entering and leaving the game mode (`PWPAD game_mode=1/0 reader=...`).
4. **DirectInput.** Without HID, Wine does not see joysticks. It's a device of its own in dinput (`joystick_pad.c` in a overlay of `dlls/dinput`, x86_64 e i386, same method as the other builders):
   - a gamepad with axes X/Y (left stick), Rx/Ry (right stick), Z (trigger), 10 buttons and a POV (cross-section);
   - read with `XInputGetStateEx(0)` of the xinput above, so share the game mode;
   - is listed as `DI8DEVTYPE_GAMEPAD` next to HID (which still does not appear).
   - It is the largest of the plan: the model is `dinput/mouse.c`, with the objects and data format of a joystick. You can go in the next building if W178 is extended.
5. **joy.cpl.**
   - `control.exe` and `joy.cpl` (x86_64) in `system32` and the builtin folder.
   - "Game Controllers" in Start → System Tools: `control.exe joy.cpl`.
   - Test: the XInput tab shows the control 0 with its buttons, sticks and trigger, and the vibration button vibrates the control; the DirectInput tab list "Orbis Pad."

<a id="archivos"></a>


## Files

|File|Change|Shared|
|---|---|---|
| `tools/build-xinput-hw.py` |new: PE xinput x2 architectures, Unix object|no|
| `tools/build-dinput-hw.py` |new: dinput with `joystick_pad.c`, x2 architectures|no|
| `native/hw_pad.c` |share, `pw_wine_pad`, `pw_wine_set_rumble`, game mode|yes|
| `platform/ps4/pw_wine_unixlibs.c` |entry `xinput1_3.so`; by name without `.drv`|yes|
| `tools/link-wine-boot.py` |link the Unix object of xinput|yes|
| `tools/stage-wine-programs.py` |`control` and the module `joy.cpl`|yes|
| `tools/make-start-menu.py` | "Game Controllers" |yes|
| `tools/build-wine-hardware.py` |copy xinput, dinput, `joy.cpl`; remove the `user_reg_reset` of W177|yes|

Order: `build-xinput-hw.py`, `build-dinput-hw.py`, `stage-wine-programs.py`, `make-start-menu.py`, then the chain (with `link-wine-boot.py`, because it changes the ELF).

<a id="riesgos"></a>


## Risks

- **Double entry** (point 3). The game mode is activated by reading XInput. A game that only uses DirectInput also activates it, because the dinput device reads XInput.
  - A program that reads XInput without being a game (`joy.cpl`) also activates it while it does. The touchpad keeps moving the pointer.
- **Games that read the command once when starting and then not:** the emulation returns to the second and the game would receive clicks if you read again later. It's rare; is registered in the log.
- **Vibration:** `scePadSetVibration` needs the handle of `hw_pad.c`. If it fails, the code is recorded and not hidden.
- **xinput9_1_0** has its own `main.c`: see if it sends to xinput1_3 Or if you have to park it too.
- **WoW64:** the 32 bit Unix table is the same (the parameters do not have points, as in 0470).
- **The own dinput is new code, not prospero-win:** is what the most tests you need.
