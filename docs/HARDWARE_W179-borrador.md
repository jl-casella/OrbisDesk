<a id="w179-partes-de-la-sesión-de-configuración-de-wine-directinput-del-mando-y-aspecto-xp-de-luna-y-noir"></a>


# W179, parts of the Wine configuration session: DirectInput of the control and XP look of Moon and Noir

[English](HARDWARE_W179-borrador.md) | [Español](HARDWARE_W179-borrador-es.md)

Eraser. The main session adds it to `HARDWARE_W179.md`, along with the browser bcrypt arrangement.

<a id="1-directinput-con-el-mando-de-la-ps4-fase-7"></a>


## 1. DirectInput with the control of PS4 (phase 7)

- The DirectInput of Wine finds joysticks only by HID (`dlls/dinput/joystick_hid.c`), which a title of PS4 has no game DirectInput I saw a command, and the DirectInput tab of `joy.cpl` was empty.
- `tools/build-dinput-hw.py` (new) compiles dinput and dinput8 (x86_64 and i386) with a new device, `joystick_pad.c`. It's own code, not prospero-win.
  - Shows the XInput 0 driver (the control, from W178) as a gamepad with the provision of driver Xbox 360 of Windows:
    - X/Y: left stick; Rx/Ry: right stick; Z: the two triggers together;
    - 10 buttons: A B X AND LB RB Back Start LS RS;
    - the cruise as POV.
  - It is presented as "Controller (XBOX 360 For Windows)," VID/PID 045e: 028e.
  - Read XInput every 8 ms in the input thread of dinput (a timer like `read_event`), and also in `Poll()`.
  - The axles respect the range, the dead area and the saturation that the program sets, with the same calculation as `scale_axis_value` of `joystick_hid.c`.
  - No force feedback: the command vibrates by XInput.
- `dinput.c`: the control first appears among the game drivers (`EnumDevices`) and is created by your instance or product GUID.
- Read the command by DirectInput reads XInput, so activate the game mode of `hw_pad.c` just like a XInput game.
- `tools/build-wine-hardware.py` copy the four DLL folders to build and to `system32` / `syswow64`. The dinput of 64 bits was not in the prefix.
- No warning when compiling. The imports of the four DLL are already in the prefix.

<a id="2-luna-y-noir-más-parecidos-a-xp-y-a-royale-noir"></a>


## 2. Moon and Noir more like XP and Royale Noir

User's request after testing W177: Moon looked too much like Aero. He wanted the full edge and title bar in blue XP, the blue task bar and the green Start button; in Noir the same, but orange.

- `tools/build-msstyles-hw.py` (already in W178):
  - **Moon:** full title and edge blue XP (0,84,227), and blue grey (122,150,223) in inactive windows.
  - **Noir:** title and orange edge (232,112,24), and dark grey in the inactive.
  - Three new pieces with XP shell classes:
    - `[Taskbar.BackgroundBottom]`: blue XP / black bright;
    - `[Start::Button.Pushbutton]`: green / orange, square to the left and rounded to the right;
    - `[TaskBand::Toolbar.Button]`: the buttons in the windows, with the darkest active.
- `tools/build-explorer-hw.py` (`tools/taskbar-theme-w179.patch.py`):
  - Explore uxtheme load in running time and open "Taskbar" in the bar window;
  - if the style has it, draw from the style the background, the Start button (`SetWindowTheme "Start"`, Button class) and the window buttons (`SetWindowTheme "TaskBand"`, Toolbar class);
  - the text goes in the color of the style: "start" in bold and italic, and the watch on the color of the bar;
  - with `WM_THEMECHANGED` (choose another style in winecfg) recharge;
  - with Aero or without style the classic drawing is left.
- `tools/build-win32u-ps4.py` (`tools/flat-frame-w179.patch.py`), on the window edge (`defwnd.c` paint:
  - if the edge color of the style is different from the button face, the whole edge, including the 3D edges, is drawn in full in that color;
  - with the usual dark scheme (edge equal to face) does not change anything.

What Wine does not draw with the style: the buttons to minimize, maximize and close remain the classic, without the red X of XP.

Check without the console: the modified explorer compiles and links without warnings, and `defwnd.c` modified compiles without warnings with the recipe of win32u.

<a id="prueba"></a>


## Test

1. Game Controllers → tab DirectInput: "Controller (XBOX 360 For Windows appears," and its axes, buttons and POV move.
2. A game DirectInput (for example, one of 32 bits that requests joystick) responds to the command, without clicks of the emulation.
3. winecfg → Moon:
   - full edge and title in blue;
   - blue task bar, green start, blue window buttons (the darkest asset), blank watch.
4. The same with Noir: orange and black.
5. "(No theme)" and Aero: taskbar and edges as before.

Risks:
- List DirectInput devices reads XInput, so it activates the game mode for a second even if the program does not use the command.
- The dinput device is new code: a game with a rare data format can show something rare on the axes; The log of `dinput` would say so.
- The buttons of the stylish task bar are drawn with the small icon of the window class. A window that only has an icon set with `WM_SETICON` appears without an icon, because reading it would ask for a message to its thread.
