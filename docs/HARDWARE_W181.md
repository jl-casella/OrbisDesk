<a id="w181-perfiles-de-teclas-del-mando-para-juegos-que-sólo-usan-teclado-fase-5"></a>


# W181: control key profiles for games that only use keyboard (phase 5)

[English](HARDWARE_W181.md) | [Español](HARDWARE_W181-es.md)

APP_VER 02.80. Base W180. The result of W180 is in `docs/HARDWARE_W180.md`. It was prepared by the direct access session.

<a id="qué-pasó-en-w179-con-supermariokart"></a>


## What happened in W179 with SuperMarioKart

- In `run-0003.log` (`reports/wine-hardware-w179/physical/20261103T221722Z`):
  - SMK load `DINPUT.dll` (line 915) and, through the device W179, `xinput1_4` (2216;
  - `PWPAD game_mode=1` (2218) and, one second later, `game_mode=0` (2825), without reactivation.
- SMK is a game Blitz3D that **only uses keyboard**. His `Read me.txt` (read from the console by FTP, without changing anything) says:
  - arrows: speed, reverse and fold;
  - space: use object;
  - Enter: choose from the menu;
  - Esc: close the game without warning.
- Blitz3D lists joysticks when starting: that's the only reading of XInput. Then the game will not read the command again.
- Without game mode, the command remained mouse: the stick moved the cursor, and **square sent Escape**, which in SMK closes the game.

<a id="cambios"></a>


## Changes

- `native/hw_pad.c`: key profiles per program (`pw_hw_pad_profile`).
  - **Where they are:** `C:\orbis\padmaps\<exe>.ini`, with lines `fuente = tecla`; `#` or `;` start a comment.
  - **Sources:** `cross`, `circle`, `square`, `triangle`, `l1`, `r1`, `l2`, `r2`, `l3`, `r3`, `options`, `touchpad`, `up`, `down`, `left`, `right` (cruise), and `stick_up`, `stick_down`, `stick_left`, `stick_right` (left stick, digital past a threshold).
  - **Keys:** `up`, `down`, `left`, `right`, `space`, `enter`, `escape`, `tab`, `backspace`, `shift`, `ctrl`, `alt`, `home`, `end`, `pageup`, `pagedown`, `insert`, `delete`, `a` - `z`, `0` - `9`, `f1` - `f12`.
  - A line that is not understood remains in the log as `PWPAD profile_line_ignored`.
  - Con perfil:
    - the buttons that the profile names send those keys, and the others do nothing;
    - the left stick sends the arrows (or the keys of `stick_*`), except with `stick = mouse`;
    - the right stick does not scroll;
    - the touchpad is still the pointer, with its click, unless the profile name `touchpad`.
  - The XInput game mode follows first: if the program reads XInput, the profile does not send keys, and when you enter, the ones that were tight are released.
  - No profile, the usual emulation.
  - Log: `PWPAD profile=<exe> keys=N stick=keys|mouse`, or `PWPAD profile=<exe> none errno=...`.
- `native/wine_hardware.c`: When the launcher reproduces a program (`switched`) or runs one of 32 bits, it passes its route to `pw_hw_pad_profile`.
- `fixtures/padmaps/SuperMarioKart.exe.ini` (new), which `tools/build-wine-hardware.py` copies `C:\orbis\padmaps`:
  - cross ↑ (accelerate), square ↓ (reverse);
  - circle and R1: space (object);
  - cruise and stick: arrows;
  - Options and triangle: Enter;
  - It's unassigned.
- A profile can be written or changed with Notepad and read when you start the program.

Check without the console:
- `hw_pad.c` and `wine_hardware.c` compile without warning with the options of the launcher and `-Wall`;
- a partial link resolves `pw_hw_pad_profile`;
- the profile reader, tested separately, loading the `.ini` SMK 14 keys (10 buttons and the 4 arrows of the stick) and gives `none` to explore.

<a id="prueba"></a>


## Test

1. SuperMarioKart: in the log, `PWPAD profile=SuperMarioKart.exe keys=14 stick=keys`.
   - In menus: stick and cross move, options or triangle choose.
   - In the race: speed cross, reverse square, stick or cross fold, circle or R1 use the object.
   - The cursor does not move with the stick; the touchpad does move it.
   - Square no longer closes the game.
2. When you return to the desktop: the command is mouse again (explorer has no profile).
3. An unprofile XInput game behaves as in W178.

Risks:
- The SMK mapping is a proposal; if the user prefers another, only the `.ini` is changed.
- A game that needs Esc (for example, for pause) has to have it on its profile; In SMK it was not assigned on purpose.

<a id="prueba-física"></a>


## Physical test

Report: `reports/wine-hardware-w181/physical/20261103T224806Z/`. On the page the user marked "bad keys," but he clarified that it was unintentionally: "it's okay, yes, I pressed by mistake."

- `PWPAD profile=SuperMarioKart.exe keys=14 stick=keys` when the game is relaunched, and the events `input_event source=profile` come to the game.
- SuperMarioKart is played with the command with the proposed mapping.
- With the new USB disk, `/mnt` still does not exist for the app (`PWUSB path=/mnt stat=-1 errno=2`): it is the sandbox, not the disk format.
