# The L3+R3 overlay menu (04.31)

[English](OVERLAY_MENU.md) | [Español](OVERLAY_MENU-es.md)

Pressing L3 and R3 together opens OrbisDesk's menu over the running program. The program keeps running, and the pad drives only the menu until it closes. From 04.31 the menu is laid out as a quick access menu: a rail of section icons on the left and the selected section's settings on the right, changed in place.

The code is `native/hw_overlay.c` (`draw_panel`, `panel_input`), with the profile selector in `native/hw_overlay_profiles.inc.c`. Existing setting keys remain compatible.

## Executable profiles (04.57)

Every section has a selectable EXE header. Move up from the first item, or up from PERFORMANCE on the rail, and press X on the name. A scrollable native list shows recent launches, including closed/crashed programs, plus saved overlay profiles. File Manager (`wfm.exe`), Explorer and internal service/host executables are excluded; names are deduplicated without case sensitivity. There is no file browser.

**Add EXE** opens a local on-screen name field: enter a basename such as `hl2.exe`, not a path, and press OPTIONS or Enter. This keyboard sends no keys to the running application. Circle returns to the list; L1/R1 move the caret, Square deletes, L2 toggles Shift and R2 changes symbols.

The editor initially selects the current runtime program, or the latest eligible name when the desktop is in front. Its target stays fixed until another profile is chosen or the menu is reopened, even if a program starts or exits. RUNNING reflects launch/exit tracking, not independent foreground-window detection. History retains 128 names and their known architecture as `profile.<exe>=0|32|64` in `overlay.ini`, separately from 64 preference slots; saved preferences also appear after history eviction. Pre-feature launches need an existing saved overlay preference or manual name entry. Registry-only AppDefaults are not enumerated.

FPS, frame generation, stretch, cursor, controller type and key mapping edit the selected EXE. Saves apply immediately only when it owns the runtime's current settings; another profile applies on its next start without changing live settings or input. The footer labels this scope. Renderer always applies on next start, through the existing desktop Wine AppDefaults bridge; a known 64-bit EXE retains the 32-bit-only restriction after restart. An in-flight renderer request prevents switching profiles until completion/timeout and survives the program closing. Failed preference saves retain previous values in memory and on disk. Key mappings are saved atomically.

Statistics, session mouse emulation, the ordinary keyboard and Close Program still act on the current session/window, independently of the selected profile; language remains global. To compare Portal renderers, select/add `hl2.exe`, save GRAPHICS → RENDERER → WINED3D + OPENGL, then relaunch the game. This does not establish the crash's cause.

Validation: host tests exercise the actual overlay's isolation, persistence, failed saves, offline renderer replies during guest exit, internal filtering, architecture retention, navigation, local name keyboard and inactive key mapping. English/Spanish previews use the real native drawing functions, and PS4 compilation passes. Physical interaction and Portal compatibility remain pending console testing.

### Renderer startup and recovery (04.58)

The 04.57 hardware run exposed a startup dependency: the registry consumer started only with the first guest attempt, leaving a desktop-only GET on READING indefinitely. Explorer now starts an independent registry worker during desktop initialization. It uses the existing native request protocol and Wine AppDefaults read/write rules; the native taken gate permits only one consumer, including when the older game closer is running too. No game must be launched to initialize it.

All GET and SET requests now have a three-second deadline, including a GET no worker took. A failed read shows **NO RESPONSE; X: RETRY** instead of a default renderer value; X retries the read. Readback errors are visible and a successful retry restores editing. A failed SET keeps the existing save-error message; it does not claim success. Host tests cover untaken/taken timeouts, retry, error replies, one-consumer routing and the worker parser. The Explorer PE and native overlay compile; physical validation of this fix is pending.

### Controller swaps

CONTROLS adds two independent toggles, off by default and saved per selected EXE: **SWAP STICKS** (`swapsticks.<exe>=on`) exchanges both axes of the left/right sticks and L3/R3; **SWAP A/B AND X/Y** (`swapbuttons.<exe>=on`) exchanges Cross/Circle and Square/Triangle. Swapping sticks moves an existing left-stick mouse function to the physical right stick and vice versa, without rewriting the key profile.

Both use the same live-versus-next-start scope as the other profile settings. Input is remapped once, after the native overlay and Steam menus read the physical pad and before publishing gamepad state or generating mouse/key events. XInput, the HID/DualSense paths and key/mouse profiles therefore share the same logical layout. The overlay's confirmation/back buttons and its navigation remain unchanged; USB keyboard/mouse are unaffected. No polling-time configuration file reads are added. Host tests cover all face/click combinations, axis directions, both toggles together, persistence, rollback and inactive-profile isolation; console behavior remains to be tested.

## Layout

- **Rail.** One icon per section: PERFORMANCE (lightning bolt), GRAPHICS (monitor), CONTROLS (gamepad), SYSTEM (gear). EXIT is the power icon at the rail's foot, in red. The selected section has an accent bar on its left.
- **Section.**
  - The section's title, and `ORBISDESK L3+R3` on the right.
  - Every section shows the selectable `EXE PROFILE` header described above, with the editing target and a RUNNING/CLOSED badge.
  - Then the items, each in one of three forms:
    - a toggle: on or off, the knob right and the track in the accent colour when on;
    - a slider of steps for a choice. The step in effect is named in the accent colour, and the knob sits on the pending step. The pending value's full name is at the right of the item's name, in the accent colour while it differs from the value in effect;
    - an action, with `>` at the right.
- **Band at the bottom**, as on the native Steam client's pages (`native/steam/steam_ui.c`):
  - an accent rule;
  - the selected item's help (on the rail, the section's first item's);
  - the buttons on the last line, in the Steam client's form (`X: SAVE     O: BACK`).

The colours are the Steam client's: page `#1b2838`, band `#171a21`, highlight `#2a475e`, accent `#66c0f4`. The panel is 540 of the output's 1280 pixels.

## Sections and items

| Section | Item | Form | Saved |
| --- | --- | --- | --- |
| PERFORMANCE | FPS LIMIT: off, 30, 60, auto | slider | per program, `fpslimit.<exe>=` |
| | FRAME GEN | toggle | per program, `framegen.<exe>=on` |
| | STATISTICS: the own readout, or MangoHud's key | toggle, or `MANGOHUD` | not saved |
| GRAPHICS | RENDERER: DXVK or wined3d, Vulkan or OpenGL | slider | per 32-bit program, Wine's registry (from its next start) |
| | STRETCH | toggle | per program, `stretch.<exe>=on` |
| CONTROLS | CONTROLLER: generic, Xbox 360, Xbox One, DualSense | slider | per program, `pad.<exe>=` |
| | SWAP STICKS | toggle | per program, `swapsticks.<exe>=on` |
| | SWAP A/B AND X/Y | toggle | per program, `swapbuttons.<exe>=on` |
| | MOUSE | toggle | this run only |
| | CURSOR: game, always, hidden | slider | per program, `cursor.<exe>=` |
| | KEY MAPPING (04.36) | action: a screen of the pad's buttons and their keys | per program, `C:\orbis\padmaps\<exe>.ini` |
| | KEYBOARD | action: the on-screen keyboard | no |
| SYSTEM | LANGUAGE: Spanish, English | slider | `lang=` |
| EXIT | CLOSE THE PROGRAM (BACK TO THE DESKTOP for a program that runs alone) | action | no |

`overlay.ini`, `padtype.txt` and the registry values are written exactly as before. Existing files need no change.

GRAPHICS's item is now called RENDERER, so that it does not repeat the section's name; its messages say RENDERER as well. CONFIG is now SYSTEM → LANGUAGE.

RENDERER only applies to 32-bit programs, so it is greyed out for a 64-bit one:

- It shows `32-BIT ONLY`, with no slider. The buttons line is `O: BACK`, and X only shows the toast `RENDERER: 32-BIT PROGRAMS ONLY`.
- How the menu knows a program's world: kernelbase's guest launch reports each program through xinput's Unix library. A 64-bit guest calls through its 64-bit table and a 32-bit guest through the WoW64 one (`tools/build-xinput-hw.py`). The overlay keeps the answer for the last 16 programs and logs `PWOVERLAY program <exe> bits=64|32`.
- A program whose world is not known keeps RENDERER enabled, as before.

## Navigation

| Where | Up / down | Right | Left | X | O |
| --- | --- | --- | --- | --- | --- |
| Rail | the section (EXIT included, wrapping) | enter the section | — | enter the section | close the menu |
| Section, a choice | the item (wrapping) | the next value (stops at the last) | the previous value (stops at the first) | save the pending value | back to the rail |
| Section, a toggle or an action | the item | — | back to the rail | turn it, or do it | back to the rail |

- A choice is only saved with X, as before.
- Leaving its item, the section or the menu puts the pending value back to the value in effect.
- The menu opens on the rail, at PERFORMANCE. From 04.36 it always does: 04.31 reopened it at the section used last, which after closing a game was nearly always EXIT.
- L3+R3 closes it from anywhere.
- The keyboard and its buttons are unchanged. O on the keyboard still closes the whole menu.

EXIT takes two presses: X on the rail enters the section, then X on CLOSE THE PROGRAM closes it. The help explains that the program is not asked and unsaved work is lost.

## KEY MAPPING (04.36)

CONTROLS → KEY MAPPING gives each button and stick direction a keyboard key or mouse click for the selected EXE profile. It is for games that read only the keyboard and mouse. X opens a screen over the whole output, even with that program closed; first select/add an EXE when no editing target exists.

**What it edits.** The pad's key profile for that program, `C:\orbis\padmaps\<exe>.ini`, which `native/hw_pad.c` already reads at the program's start (W181, W213). The screen writes `source = key` lines and keeps every other line as it is: comments, `stick = mouse`, `rstick = mouse` and the `rstick_speed` / `rstick_deadzone` values.

- **Saving.** OPTIONS writes the file atomically. If the selected EXE owns the runtime's current input, the pad thread reloads it at its next read (`pw_hw_pad_profile_reload`); other profiles apply on their next start.
- **A file with no key line left is removed.** The pad then works as with no profile.
- **A new file** starts with a comment that names the program and this screen.

**The screen.**

- **Left:** a DualShock 4 is drawn: L1/L2/R1/R2, the d-pad, the four face buttons, SHARE, OPTIONS, the touchpad, both sticks and the PS button.
  - Each button is light grey when it has a key and dim when it has none.
  - The chosen row is lit in the accent colour.
- **Right:** every button and direction is listed, with its key at the right:
  - CROSS, CIRCLE, SQUARE, TRIANGLE;
  - D-PAD UP, DOWN, LEFT and RIGHT;
  - L1, R1, L2, R2, L3, R3;
  - LEFT STICK UP, DOWN, LEFT and RIGHT;
  - RIGHT STICK UP, DOWN, LEFT and RIGHT;
  - OPTIONS, TOUCHPAD CLICK, SHARE.
- **The line between them.** A line joins the chosen row to its place on the picture, as the controller pages of PC games' settings do.
- **The value at the right of a row** is one of:
  - its key, in the accent colour while it differs from the saved file;
  - `--`, for no key. It is in the accent colour when a saved key is being cleared;
  - `AUTO: <arrow>`, dim, on a left stick direction without a key. Once a profile has keys, `hw_pad.c` gives the left stick the arrows;
  - `POINTER`, dim, on a stick that `stick = mouse` or `rstick = mouse` keeps as the pointer or mouse look;
  - `SYSTEM`, on SHARE. The system keeps that button: the SDK's pad state has no bit for it, so it cannot be mapped. X on it only shows a toast.
- **The bottom band, as in the menu.** It holds the help and the buttons line:
  - `X: ASSIGN    SQUARE: CLEAR    TRIANGLE: DEFAULT    O: BACK`;
  - with unsaved changes, `OPTIONS: SAVE` is added and O reads `CANCEL`.

**The key picker.** X on a row opens it over the list.

- It is a keyboard of 13 columns: ESC and F1–F12; the digits and BACKSPACE; the letters; TAB, DEL, CTRL, ENTER, SHIFT, INS, HOME, ALT, SPACE, PGUP, PGDN, END; and the four arrows.
- Its last two rows are the mouse: MOUSE LEFT, MOUSE RIGHT, MOUSE MIDDLE, WHEEL UP and WHEEL DOWN.
  - A mouse button is held down while the pad button is held, and clicks where the pointer is. For example, TOUCHPAD CLICK = MOUSE LEFT.
  - A wheel target turns the wheel one notch per press.
- These are exactly the target names `hw_pad.c`'s `profile_vk` takes.
- It opens on the row's current key, which has an accent frame.
- The directions move over the keys. Up and down keep the column.
- X gives the row that key, SQUARE leaves it without one, and O closes the picker.

| Where | Up / down | Left / right | X | SQUARE | TRIANGLE | OPTIONS | O |
| --- | --- | --- | --- | --- | --- | --- | --- |
| List | the row (wrapping) | — | open the picker | clear the row | the default profile | save, when changed | back to CONTROLS; unsaved changes are dropped |
| Picker | the key row, same column | the key (wrapping) | that key | no key | — | — | close the picker |

L3+R3 closes everything from either place, and unsaved changes are dropped.

**DEFAULT** loads the profile OrbisDesk ships for the program, from `C:\orbis\padmaps-default\<exe>.ini`. With none it loads no keys at all. It is pending until OPTIONS.

**Updates keep the user's profiles.**

- `tools/build-wine-hardware.py` also copies `fixtures/padmaps` to `C:\orbis\padmaps-default`, which every update refreshes.
- `tools/console_state.py` lists the shipped profiles in `padmaps` as console-owned files. `upload-hardware.py` and the launcher's installer then copy them only when they are missing, so an edited shipped profile is not replaced.
- A shipped profile changed in a later build reaches a console through DEFAULT.
- The installer keeps at most 16 console-owned files (`HW_INSTALL_MAX_ROOTS`). `console_state.py` refuses more.

**hw_pad.c's side.**

- `rstick_up`, `rstick_down`, `rstick_left` and `rstick_right` are new profile sources: the right stick's directions as keys, past the same threshold as the left stick's.
- A target may also be `mouse_left`, `mouse_right`, `mouse_middle`, `wheel_up` or `wheel_down`:
  - a mouse button goes down at the pointer when its first source is pressed and up when its last is released, as keys do since W182;
  - a wheel target sends one notch on the press.
- The right stick's directions do not apply with `rstick = mouse`. The screen drops that line, and likewise `stick = mouse`, once a direction of that stick gets a key.
- The rules of W181 are unchanged:
  - once a profile has a key, buttons without one send nothing;
  - the left stick sends the arrows unless named or `stick = mouse`;
  - keys do not go while a program reads the pad through XInput (game mode).
- The screen's help says this.

Limits:

- One key per source. A file that names a source twice shows its last line, and saving keeps only that one.
- A file with more than 4 KiB of other lines is shown but not saved; the log says so.
- Key combinations (Shift+key) cannot be mapped, as in W181's profiles.

## MangoHud

Unchanged, and stated in the help:

- STATISTICS sends MangoHud's key (Shift+F12) while MangoHud draws on the program in front, so its show/hide works for 32- and 64-bit programs alike.
- MangoJuice's edits apply to every HUD: the overlay reads `MangoHud.conf` for its own readout and for frame generation's MangoHud rectangle.

## Not changed

- The toast messages and their place.
- The statistics readout and frame generation's MangoHud rectangle.
- The keyboard.
- What each setting does, and the per-program rules: the last program opened that is still open, and what X does with no program open.

## Checks

- A host harness that includes `hw_overlay.c` with stubs for the console calls renders the menu over a 1280x720 frame. It also drives `pw_hw_overlay_pad` with simulated buttons, covering every row of the navigation table above.
- 04.36: the same harness checks:
  - that the menu opens on PERFORMANCE;
  - KEY MAPPING's navigation;
  - its files, starting from copies of `fixtures/padmaps`: SuperMarioKart's profile edited with its comments kept, `stick = mouse` dropped for vlc, a new file with its header, and a file removed when cleared;
  - DEFAULT;
  - that every source and key name the screen writes is one `hw_pad.c`'s own `profile_sources` and `profile_vk` take. Those are extracted from the patched file.
- It also draws the screen's mockups.
- The console run of 04.31 (run-0263) showed the menu working. KEY MAPPING's console run is pending.
