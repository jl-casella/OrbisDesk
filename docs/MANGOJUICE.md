# MangoJuice: the MangoHud settings program

[English](MANGOJUICE.md) | [Español](MANGOJUICE-es.md)

MangoJuice (`C:\Program Files\MangoJuice\bin\mangojuice.exe`) lets the user change the HUD options without editing `MangoHud.conf` by hand. **Graphics Tools > MangoJuice** opens it, with MangoJuice's own icon, and it replaces the old **MangoHud Config** item, which opened the file in Notepad. The program is MangoJuice-Windows, `https://github.com/Leclowndu93150/mangojuice-Windows.git` @ `e2ec0755`, GPL-3.0.

## Decision

[G001](HARDWARE_G001.md) left MangoJuice out: it is a Vala application on GTK4, libadwaita-1 and libgee with no releases, and building it needs the GTK4 stack for Windows and `valac`. A first version of this work recommended a small native Win32 form instead. It was smaller (70 KiB against 52 MiB) and covered only the 12 keys OrbisDesk reads. The user chose MangoJuice, so that form was removed before release. The cost of this route is listed below so it can be revisited with evidence.

## How it is built

[build-mangojuice-hw.py](../tools/build-mangojuice-hw.py) runs in WSL Ubuntu-22.04. Every input is pinned by SHA-256 in [mangojuice.lock.json](../mangojuice.lock.json):

| Input | Why |
| --- | --- |
| MangoJuice source at the commit in `dependencies.lock.json` | The program. It must be at that commit and clean. |
| 84 MSYS2 **ucrt64** packages: libadwaita and libgee with their full dependency closure (gtk4 4.24.1, libadwaita 1.10.0, glib2 2.90.1, libgee 0.20.8, …) | Headers, import libraries, DLLs, schemas, icons and licence texts. The older mingw64 repository no longer carries gtk4 or libadwaita. |
| MSYS2 `vala` 0.56.19 | Only its vapis. Ubuntu's valac 0.56.0 ships a GTK 4.6 `gtk4.vapi`, and MangoJuice uses GTK 4.10+ API (`ColorDialogButton`, `FileDialog`). |
| Ubuntu .debs: `valac`, `valac-bin`, `libvala-0.56-0`, `libvalacodegen-0.56-0`, `zstd`, `librsvg2-bin` | Host tools, unpacked without installing: Vala to C, `.pkg.tar.zst` extraction, and the icon. |
| llvm-mingw 20260922 (UCRT), from `dependencies.lock.json` | MSYS2's DLLs use the UCRT. The distro MinGW gcc 10 links msvcrt. |

Steps:

1. `--fetch` downloads whatever is missing into `.deps/mangojuice`, and the builder verifies every hash.
2. The MSYS2 packages are unpacked into `build/mangojuice-hw/sysroot`, about 1 GiB, which is deleted after the build unless `--keep-work` is given. Vala generates C.
3. llvm-mingw compiles it and links it twice. The two links must be identical.
4. The program's DLL closure is copied from the MSYS2 tree, together with GTK's GSettings schemas (compiled on the host), the Adwaita and hicolor icon themes, MangoJuice's own icons and the licence texts.
5. The `.ico` (16, 32 and 48 px) is rendered from MangoJuice's SVG with `rsvg-convert`.

`--lock` re-resolves the pins from MSYS2's current database. MSYS2 removes old package versions eventually, so a lock this old may need re-resolving, followed by a rebuild and new tests. `ORBISDESK_DEPS` points a worktree at the main checkout's `.deps`.

Two revisions are made to MangoJuice, and both are recorded in the manifest:

- `main()` sets `GSK_RENDERER=cairo` and `GDK_DISABLE=gl,vulkan` unless the user has set them. The title has no GL for GTK, and its Vulkan belongs to the games, so GTK draws the window in software.
- `main()` also sets `PANGOCAIRO_BACKEND=fontconfig` and loads a little CSS that removes the shadow and rounded corners of popovers and tooltips (see "Rendering on the console" below).
- The **Games** page is removed. It starts a standalone `MangoHud.exe` against a running game and registers the layer under HKLM through `reg.exe`. OrbisDesk already loads MangoHud as an implicit layer and ships no `MangoHud.exe`.

The upstream `requireAdministrator` manifest is not linked.

`build-wine-hardware.py`:

- checks the manifest against the builder and the lock;
- copies `out/mangojuice-hw/MangoJuice` to `C:\Program Files\MangoJuice`, which the debug strip leaves alone, as it does VLC;
- fails if any Windows DLL the program imports, directly or through another Wine DLL, is not in system32 once the prefix is final (the `api-ms-win-*` ones resolve through the apiset);
- deletes the old `Graphics Tools\MangoHud Config.lnk` from the console.

`tools/ci/build-product.py` runs the builder with `--fetch`, and MangoJuice's source is now restored in CI.

### DirectWrite

MSYS2's `libharfbuzz-0.dll` and `libpangowin32-1.0-0.dll` import `DWrite.dll`, which OrbisDesk did not ship. On the console (W303 combined package, run-0060) MangoJuice did not open: DWrite.dll was not found, and harfbuzz, freetype, fontconfig, cairo and GTK then failed one after another. Wine's own dwrite is now staged:

- [stage-wine-extras.py](../tools/stage-wine-extras.py) copies `dwrite.dll` for both views from the pinned host Wine build, unpatched. `build-wine-hardware.py` puts it in the builtin folders and in system32/syswow64, and keeps it there: `stage-wine-i386.py`'s `W261_LEFT_OUT` lists dwrite, which had been left out because it had no Unix side (SeaMonkey drew pages without text and VLC's Qt quit). With only the builtin folder's copy it still failed (run-0061). Now that dwrite has its Unix side, SeaMonkey and VLC use DirectWrite again and need retesting.
- dwrite draws glyphs through FreeType on its Unix side, `dwrite.so`. The title has no dynamic loader. [build-unixlibs-ps4.py](../tools/build-unixlibs-ps4.py) compiles Wine's `dlls/dwrite/freetype.c` unchanged, with its `dlopen`/`dlsym` renamed to [pw_dwrite_unix.c](../platform/ps4/pw_dwrite_unix.c). That file answers from the FreeType win32u already links into the boot ELF, and [pw_wine_unixlibs.c](../platform/ps4/pw_wine_unixlibs.c) registers `dwrite.so`.

The rest of the closure, 64 DLLs, was present in W303. The 8 KiB `usp10.dll` is Wine's forwarder to gdi32, not a stub. The Unix side compiles with the console toolchain, and its only undefined symbols are FreeType's 28 functions, which `build/freetype-ps4` defines, plus ntdll's debug output and libc. It needs a new boot ELF (`build-unixlibs-ps4.py`, then `link-wine-boot.py`); it was not linked or run.

### Rendering on the console

In run-0062 MangoJuice opened, but its text had strokes and whole letters missing ("GPU" read "GP"), and the "…" menu sat in a black rectangle.

- **Text.** Pango 1.58's Windows backend lists fonts through DirectWrite, and pangocairo draws them with cairo's DirectWrite font faces, so every glyph went through Wine's dwrite and its new FreeType Unix side on the console. That route is where the strokes were lost; exactly which step was not isolated. pangocairo has a second backend: `PANGOCAIRO_BACKEND=fontconfig` uses fontconfig and MSYS2's own FreeType inside the process, as GIMP and Inkscape do on Windows. MSYS2's `etc/fonts` (fonts.conf and conf.d) ships next to `bin`, where fontconfig looks for it. It scans `C:\windows\Fonts` and caches in `%LOCALAPPDATA%\fontconfig`. The console has only Tahoma and Marlett there, so a generated `local.conf` makes Tahoma the choice for sans-serif, serif, monospace, system-ui, Adwaita Sans, Cantarell and Segoe UI.
- **Black popovers.** GTK draws popovers and tooltips as separate windows with a transparent shadow margin. Without DirectComposition, which is opt-in (`GDK_DEBUG=dcomp`) and would need Direct3D 11, it asks DWM for alpha through `DwmEnableBlurBehindWindow`. Wine composites no alpha, so the margin came out black. CSS at user priority (`window, window.csd, window.background, popover, popover > contents, popover > arrow, tooltip { box-shadow: none; border-radius: 0; } popover > contents { margin: 0; }`) leaves no transparent pixels around the shadow. Two transparent bands were still left:
  - The main window kept a black frame until it was maximized (run-0064). CSS alone did not remove it (run-0066), because a decorated client-side window keeps a margin as wide as GTK's resize handles. Every window is now undecorated (`set_decorated (false)` on `window_added`); libadwaita draws its own header bar and window buttons inside the window.
  - The popovers kept their arrow's band. The main menu, the font popover and the presets hint popover have no arrow.

The desktop is 1280×720 scaled up to the TV, so MangoJuice will never look as sharp there as on a PC.

### The test button

The Windows fork stubs vkcube and glxgears out as Linux tools. Every start showed a "vkcube and glxgears not found" toast, and the test button only made sure `MangoHud.conf` existed. OrbisDesk ships both programs in `C:\orbis` (Start > Graphics Tools, [make-start-menu.py](../tools/make-start-menu.py)). Each is reported available when its file exists, and the test button starts vkcube, or glxgears without it, through `WinExec`, as a guest with MangoHud on it. Whether one is already running is not tracked, so a save does not restart it.

### Reopening after a close

MangoJuice runs as a guest in explorer's shared process, so whatever its DLLs leave behind outlives it. Its second start failed until three leftovers were removed. All three fixes are general guest-lifecycle changes in [build-guest-hw.py](../tools/build-guest-hw.py):

1. **A GLib thread in its own code** (run-0065). `guest->threads` tracks only threads that guest threads create through `CreateThread`, so a threadpool thread running in `libglib` was not tracked, and the unload kept every module of the program. Threads still running in the guest's own modules are now ended, with the loader lock held, before those modules are unloaded.
2. **A pinned GIO** (run-0076). GIO pins itself, so `libgio` outlived the program, and with it the first start's GApplication type and class, whose property specs pointed into the freed `libgobject`. The next start's first `g_object_new` jumped there (c000001d at an address inside `libgraphene`, run-0075). A module from the program's own folder that the program pinned is now unpinned and unloaded with it, as its process's end would do; the leftovers pass at a launch still skips pinned modules.
3. **GDK's window classes** (run-0077). With GIO gone, the second start got past `g_object_new` and then aborted with status 3. GDK registers `gdkSurfaceToplevel`, `GdkDisplayChange` and `GdkClipboardNotification` under libgtk's instance, which the unload's class pass never visited, and libgtk is unloaded with the EXE. The pass now also visits the modules of the guest's own folder loaded after its start, while they are still loaded. A class registered under one of them whose procedure is in the guest's own code is unregistered.

An unhandled exception on a guest thread now also logs the module and offset of the faulting address, of the argument registers and of up to 16 return addresses on the stack (`PWGUEST fault`). That is how cause 2 was found.

## Result of this build

| | |
| --- | --- |
| `mangojuice.exe` | sha256 `000df9f886710b74b988f22c3acaaf0d89dca51fbb4948b1663ca625e5db8f31`, one build with the window, popover and test-button revisions (run-0062's was `b672c722…`, two links identical) |
| Staged | 989 files, 52.2 MiB: 62 DLLs (`libgtk-4-1.dll` alone is 12.0 MiB), icons 4.9 MiB |
| Windows DLLs from Wine | 46, including `opengl32`, `d3d11`, `d3d12`, `dcomp`, `dwrite`, `gdiplus` and `usp10` |
| Not shipped | MSYS2's `vulkan-1.dll`: system32's is OrbisDesk's Khronos loader |
| Build time | 7 to 10 minutes on `/mnt/c`, most of it unpacking the MSYS2 tree |

Each staged DLL is read whole into memory when it loads, inside explorer's shared process (W095), so MangoJuice costs memory while it is open. That cost was not measured on the console.

## The settings file

MangoJuice writes `%APPDATA%\MangoHud\MangoHud.conf`, which is `/data/wine-prefix/drive_c/users/orbis/AppData/Roaming/MangoHud/MangoHud.conf` on the console. Each save rewrites the whole file: it starts with `legacy_layout=false`, lists the enabled rows as bare keys and leaves the disabled ones out. With `legacy_layout` off, MangoHud shows only the rows the file names (`overlay_params.cpp`, `sort_elements`). The title overlay's Estadisticas HUD (`native/hw_overlay.c`) now does the same, where it used to start from MangoHud's default rows. Its log line gains `legacy_layout=`. The overlay still draws rows in its own fixed order, not the file's.

The user's file survives updates. `tools/console_state.py` lists it in `CONSOLE_OWNED_FILES`. The FTP uploader and the first-run installer (`install.txt` `P` lines, `native/hw_install.h`) copy it only when it is missing. Before this, every update replaced it with the build's default.

### MangoHud did not read it (2026-11-16)

MangoJuice saved the options and MangoHud drew its own defaults, so unticking GPU, for one, changed nothing on a Vulkan program. MangoHud looks for `$XDG_CONFIG_HOME`, or `$HOME/.config`, plus `/MangoHud/MangoHud.conf` (`src/config.cpp` `enumerate_config_files`, `src/file_utils.cpp` `get_config_dir`). `HOME` is `/data/wine-home` here (`platform/ps4/pw_wine_platform.c`), a Unix path, and the layer is a PE inside the guest, so that name resolves against the current drive and no candidate exists. MangoHud kept its defaults: `fps`, `frametime`, `frame_timing`, `cpu_stats` and `gpu_stats`. Estadisticas, the title overlay's own HUD, did not find it either, for a different reason: it looked at the right
path but asked for the file's record through the SDK's `OrbisKernelStat`, which does not match the record the kernel
returns (`platform/ps4/pw_wine_platform.c` `PwOrbisStat`, W230). The modification time read the wrong bytes and came
back 0 for every candidate, so no path was chosen and the HUD fell back to MangoHud's defaults as well
(`PWOVERLAY hud: no MangoHud.conf`, run-0150 and run-0151). It now asks through `pw_wine_stat`, which converts that
record, and takes the file's size as the change stamp where the console reports no time.

The title now passes `MANGOHUD_CONFIGFILE=C:\users\orbis\AppData\Roaming\MangoHud\MangoHud.conf` next to the `MANGOHUD=1` it already passed (`native/wine_hardware.c`), so both HUDs read the file MangoJuice writes. Where `C:\mangohud\MangoHud.conf` exists MangoHud still reads that one first: it is its own Windows candidate, tried before the variable, and nothing here writes it.

The hardware check that found this: a probe config at that path, with `fps` alone and `position=bottom-right`, moved MangoHud's HUD and left Estadisticas where it was. It was removed afterwards.

### The overlay's show/hide stopped (2026-11-16)

Once MangoHud read MangoJuice's file, the overlay's show/hide stopped working in 32-bit and 64-bit programs alike. The overlay sends Shift+F12, which MangoHud reads as its default F12 (`native/hw_overlay.c`, `HUD_HOLD_US`), and the log still showed the key being sent. MangoJuice always writes `toggle_hud` (`Shift_R+F12`, and on the console once `Shift_L+0xffffff`). MangoHud parses key names with xkbcommon, which it only builds with X11 or Wayland. Without them, which is every Windows build, `src/overlay_params.cpp` defines `parse_toggle_hud` and the other hotkey parsers as `{}`, so a line naming a hotkey left an empty key list that never matched. The fork's `_WIN32` redefinition in `parse_overlay_config` comes after the functions that use those parsers, so it never applied.

[patch-mangohud-win-hotkeys.py](../tools/vk-h0/patch-mangohud-win-hotkeys.py) now makes those parsers keep the current value: the Windows defaults, F12 for `toggle_hud`. A hotkey written in `MangoHud.conf` is therefore ignored and the default stays. [build-mangohud.sh](../tools/vk-h0/build-mangohud.sh) applies it, and [build-mangohud-i386.sh](../tools/vk-h0/build-mangohud-i386.sh) checks its marker in the copied tree.

Hardware, app version 04.08 (run-0158): d3d9test32 ran as a 32-bit guest with MangoHud loaded (`loaded32=1`). The overlay sent `Shift+F12 held 250 ms` twice, and the user saw the HUD hide and come back. The GPU row disappearing after unticking it was seen on vkcube with 04.06. The other combinations were not checked on 04.08: the toggle on a 64-bit program, the GPU row on a 32-bit program, and Estadisticas reading the file.

## What was checked, and what was not

- The builder ran start to finish.
- On the console (PS4 Pro, W303 package with test runtimes, NORMAL/ROOT launched by the user):
  - MangoJuice opens with readable text (run-0062 onwards) and no black frame around its window (run-0068 onwards).
  - The "…" menu has no black edge, there is no "not found" toast, and the test button opened vkcube, which started and closed cleanly (run-0074).
  - It opened, closed and opened again with its window both times, each start ending with status 0. On each close the three GDK classes were unregistered and GIO was unpinned (run-0078, `reports/pop-phase-b/physical/20261113T055814Z`).
  - The user also reported WFM and a game working after MangoJuice closed (run-0074). The guest-lifecycle changes were not checked with other programs' repeated starts, nor with two guests from the same folder at once.
- `hw_overlay.c` compiles with the console's own compiler flags (`helper_compile_flags`). In the host preview harness:
  - a MangoJuice-style file (`legacy_layout=false`, `fps`, `ram`) gave `gpu=0 cpu=0 ram=1 fps=1 frametime=0 frame_timing=0`;
  - the build's default file still gave the default rows.
- `native/hw_install.h`: host syntax check only.
- The icons were previewed at 16, 32 and 48 px on the dark menu (38,38,40), the light menu (240,240,240) and the selection colour (0,120,215).
- **Not checked:**
  - MangoJuice natively on the build PC, or on shadPS4;
  - its memory use and controller navigation (it takes about 14 s to its first window on the console, `PWSINK busy end … ms=14426`);
  - saving settings and the Estadisticas HUD following them (`PWOVERLAY hud:`);
  - the settings surviving the next update.

## vkSpin's icon

The vkSpin icon used to be a bare triangle. Its blue corner disappeared on the dark menu and on the highlight, and its white centre on the light menu. A fault in `tools/make-icons.py` made it worse: `raster()` took a pixel's alpha from its most frequent subsample colour. A gradient makes every subsample a different colour, so the triangle came out about 1/16 opaque.

Alpha is now the coverage, and the colour is the mean of the subsamples. vkSpin is now the same triangle on a rounded yellow-to-magenta tile with a dark rim and a white edge, and it stands out on all three backgrounds. The other icons look the same or slightly cleaner, with fewer edge halos, but their bytes change.
