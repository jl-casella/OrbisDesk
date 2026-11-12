# MangoHud Settings: an editor for the HUD options

[English](MANGOHUD_SETTINGS.md) | [Español](MANGOHUD_SETTINGS-es.md)

MangoHud Settings (`C:\orbis\mangohudcfg.exe`) lets the user choose what the HUD shows without editing `MangoHud.conf` by hand. The Start menu item **Graphics Tools > MangoHud Config** now opens it. The new item **MangoHud Config (text)** opens the same file in Notepad.

## Decision: a small Win32 program, not MangoJuice

The candidate was MangoJuice-Windows (`https://github.com/Leclowndu93150/mangojuice-Windows.git` @ `e2ec0755`, pinned as reference only in `dependencies.lock.json`). [G001](HARDWARE_G001.md) already left it out. This decision checked that again:

| Question | MangoJuice-Windows | Native Win32 editor |
| --- | --- | --- |
| Code | 7,701 lines of Vala. Most of it covers MangoHud options that neither OrbisDesk reader uses: CPU/GPU temperatures, clocks, power, fan, battery, Steam/game launch, presets. | One C file for the 12 keys OrbisDesk reads. |
| Runtime | GTK4, libadwaita-1 and gee-0.8 for Windows, together with GLib, Pango, HarfBuzz, Cairo, FreeType, graphene, an icon theme and their data. It would need a mingw cross-build of the whole stack, or MSYS2 packages pinned by hash. Their sizes were not measured. | `comctl32`, `shell32`, `user32`, `gdi32`, `kernel32`, `msvcrt`. All are Wine builtins that are already staged. |
| Host tools | `valac`, meson and the GTK4 build stack. None of them is installed. | The pinned MinGW-w64 compiler that already builds the other `C:\orbis` programs. |
| Under the title | GTK4's default renderer uses GL. It would have to run with `GSK_RENDERER=cairo`, which was not tried. The title reads every image whole into memory, and every program shares explorer's process (W095, in the comment in `build-wine-hardware.py`), so each GTK DLL costs memory for as long as it is loaded. | 70,656 bytes. |
| Process model | It runs helpers through `Process.spawn_sync` (game manager), and its preview starts vkcube/glxgears. A guest started from a guest can end when its parent ends ([W180](HARDWARE_W180.md)). | Starts nothing. |
| Effort to keep it working | No releases, so we would maintain a fork of an upstream that only targets desktop Windows. | Inside this repository. |

The editor takes about 1/1000 of MangoJuice's runtime and has no new dependencies. MangoJuice's extra options would show the user settings that have no effect here. The native route is recommended and implemented. MangoJuice stays pinned as a reference only.

## What the editor shows and writes

Two programs read `%APPDATA%\MangoHud\MangoHud.conf`, which is `/data/wine-prefix/drive_c/users/orbis/AppData/Roaming/MangoHud/MangoHud.conf` on the console:

- MangoHud's own layer (`overlay_params.cpp`). It reads the file when a Vulkan program starts. The last value of a key wins, `full` is applied first and then every other key.
- The title overlay's **Estadisticas** HUD (`native/hw_overlay.c`, `hud_read_conf`). It reads the file each time Estadisticas is turned on, and handles each line in order. Its log line is `PWOVERLAY hud: ...`.

The form edits only the keys both of them read:

| Form | Key | Range |
| --- | --- | --- |
| Show: frames per second, frame time, frame time graph, GPU, CPU, memory, video memory | `fps`, `frametime`, `frame_timing`, `gpu_stats`, `cpu_stats`, `ram`, `vram` | on/off |
| Position | `position` | the 8 positions both readers accept |
| Font size | `font_size` | 8–96. `hw_overlay.c` ignores other values. |
| Background opacity | `background_alpha` | 0–100 %, written as 0.00–1.00 |
| Horizontal/vertical offset | `offset_x`, `offset_y` | 0–2000. MangoHud reads them as unsigned. |

The form opens with the values `hw_overlay.c` would use: MangoHud's defaults, then the file. On the PS4, VRAM is always shown as "--", because memory is unified (`native/hw_overlay.c`).

On **Save**, the program reads the file again and writes it back:

- every other line is kept as it was: comments, `full`, `toggle_hud` and any other MangoHud option;
- every edited key is removed wherever it was, and then written once at the end with an explicit `key=0`/`key=1` or value, after a marker comment.

So both readers end with the same values, whatever their order rules. Saving twice gives the same file. The program writes `MangoHud.conf.new` first and renames it over the old file.

**Defaults** shows MangoHud's defaults, which take effect only after Save. The interface follows Wine's UI language: Spanish or English. An argument names another file, for tests.

## The user's file survives updates

Before this change, every update replaced `MangoHud.conf` with the build's copy whenever the two differed: the FTP upload (`tools/upload-hardware.py`) and the first-run installer (`native/hw_install.h`). That would have erased what the user saved. The file is now console-owned. `tools/console_state.py` lists it in `CONSOLE_OWNED_FILES`. The uploader skips it if it exists. `build-wine-hardware.py` writes a `P` line to `install.txt`, and the installer copies the file only when it is missing (`PWINSTALL plan ... kept=1`). The build's file stays the clean-install default.

## Build and staging

```sh
# WSL Ubuntu-22.04 from the repository root; the compiler package must match build-environment.lock.json
python3 tools/build-mangohudcfg-hw.py
python3 tests/test_mangohudcfg.py
```

[build-mangohudcfg-hw.py](../tools/build-mangohudcfg-hw.py):

- compiles [mangohudcfg.c](../fixtures/win32/mangohudcfg.c) with `x86_64-w64-mingw32-gcc`, using `-Werror` and no timestamp;
- links it twice into `build/mangohudcfg-hw/{a,b}` and requires identical output;
- checks the imports;
- writes `out/mangohudcfg-hw/mangohudcfg.exe` and `manifest.json`, which records the source hash, builder hash and compiler packages.

It uses only its own directories. `build-wine-hardware.py` checks the manifest against the builder and the source, and copies the program to `C:\orbis\mangohudcfg.exe`. `tools/ci/build-product.py` runs the builder before the product build, and the PR host job runs the test.

[test_mangohudcfg.py](../tests/test_mangohudcfg.py) compiles the program's file logic for the host. It checks a save against models of both readers: the build's default file, a user file with CRLF, `full`, duplicate keys, other options and an out-of-range font, and a missing file.

## What was checked, and what was not

- Builder: two identical links. `out/mangohudcfg-hw/mangohudcfg.exe` is 70,656 bytes, sha256 `0e09c86b2c77af2063eff7106de0ce245801708af8d851b1fb9da66163073aaa`, with gcc-mingw-w64-x86-64 `10.3.0-14ubuntu1+24.3`.
- Host logic test: 16 checks passed.
- Native Windows 11, which is reference behaviour only, not Wine or PS4:
  - the window opened in Spanish;
  - the file's `full` showed all rows ticked;
  - unticking video memory and saving wrote `vram=0` after `full`, and kept `# my HUD`, `full` and `toggle_hud`.
- `native/hw_install.h`: host syntax check only, with stubs.
- **Not run:**
  - under Wine: the host Wine build has no display driver;
  - in a W package, or on shadPS4 or the PS4;
  - the upload and installer rules on the console;
  - whether MangoHud's layer picks up a change without restarting the program, and how the controller moves through the form.

A first console test:

1. Open Graphics Tools > MangoHud Config.
2. Untick the frame time graph, set the position to bottom right and the font size to 30, then press Save.
3. Turn Estadisticas off and on. The log should show `PWOVERLAY hud: ... frame_timing=0 position=bottom-right font_size=30`.
4. Start vkcube and look at MangoHud.
5. Install the next build and check that the settings are still there.
