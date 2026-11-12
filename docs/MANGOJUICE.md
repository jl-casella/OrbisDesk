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
- The **Games** page is removed. It starts a standalone `MangoHud.exe` against a running game and registers the layer under HKLM through `reg.exe`. OrbisDesk already loads MangoHud as an implicit layer and ships no `MangoHud.exe`.

The upstream `requireAdministrator` manifest is not linked.

`build-wine-hardware.py`:

- checks the manifest against the builder and the lock;
- copies `out/mangojuice-hw/MangoJuice` to `C:\Program Files\MangoJuice`, which the debug strip leaves alone, as it does VLC;
- fails if any Windows DLL the program imports, directly or through another Wine DLL, is in neither Wine's builtin folder nor system32 (the `api-ms-win-*` ones resolve through the apiset);
- deletes the old `Graphics Tools\MangoHud Config.lnk` from the console.

`tools/ci/build-product.py` runs the builder with `--fetch`, and MangoJuice's source is now restored in CI.

### DirectWrite

MSYS2's `libharfbuzz-0.dll` and `libpangowin32-1.0-0.dll` import `DWrite.dll`, which OrbisDesk did not ship. On the console (W303 combined package, run-0060) MangoJuice did not open: DWrite.dll was not found, and harfbuzz, freetype, fontconfig, cairo and GTK then failed one after another. Wine's own dwrite is now staged:

- [stage-wine-extras.py](../tools/stage-wine-extras.py) copies `dwrite.dll` for both views from the pinned host Wine build, unpatched. `build-wine-hardware.py` puts it in the builtin folders and in system32/syswow64.
- dwrite draws glyphs through FreeType on its Unix side, `dwrite.so`. The title has no dynamic loader. [build-unixlibs-ps4.py](../tools/build-unixlibs-ps4.py) compiles Wine's `dlls/dwrite/freetype.c` unchanged, with its `dlopen`/`dlsym` renamed to [pw_dwrite_unix.c](../platform/ps4/pw_dwrite_unix.c). That file answers from the FreeType win32u already links into the boot ELF, and [pw_wine_unixlibs.c](../platform/ps4/pw_wine_unixlibs.c) registers `dwrite.so`.

The rest of the closure, 64 DLLs, was present in W303. The 8 KiB `usp10.dll` is Wine's forwarder to gdi32, not a stub. The Unix side compiles with the console toolchain, and its only undefined symbols are FreeType's 28 functions, which `build/freetype-ps4` defines, plus ntdll's debug output and libc. It needs a new boot ELF (`build-unixlibs-ps4.py`, then `link-wine-boot.py`); it was not linked or run.

## Result of this build

| | |
| --- | --- |
| `mangojuice.exe` | sha256 `51a7bb9b50d233ef63e085ccac76e8c63e7ba0c376ef2f418a3ccb7c3cf55788`; two links identical, and the same in three separate builds |
| Staged | 963 files, 52.1 MiB: 62 DLLs (`libgtk-4-1.dll` alone is 12.0 MiB), icons 4.9 MiB |
| Windows DLLs from Wine | 46, including `opengl32`, `d3d11`, `d3d12`, `dcomp`, `dwrite`, `gdiplus` and `usp10` |
| Not shipped | MSYS2's `vulkan-1.dll`: system32's is OrbisDesk's Khronos loader |
| Build time | 7 to 10 minutes on `/mnt/c`, most of it unpacking the MSYS2 tree |

Each staged DLL is read whole into memory when it loads, inside explorer's shared process (W095), so MangoJuice costs memory while it is open. That cost was not measured on the console.

## The settings file

MangoJuice writes `%APPDATA%\MangoHud\MangoHud.conf`, which is `/data/wine-prefix/drive_c/users/orbis/AppData/Roaming/MangoHud/MangoHud.conf` on the console. Each save rewrites the whole file: it starts with `legacy_layout=false`, lists the enabled rows as bare keys and leaves the disabled ones out. With `legacy_layout` off, MangoHud shows only the rows the file names (`overlay_params.cpp`, `sort_elements`). The title overlay's Estadisticas HUD (`native/hw_overlay.c`) now does the same, where it used to start from MangoHud's default rows. Its log line gains `legacy_layout=`. The overlay still draws rows in its own fixed order, not the file's.

The user's file survives updates. `tools/console_state.py` lists it in `CONSOLE_OWNED_FILES`. The FTP uploader and the first-run installer (`install.txt` `P` lines, `native/hw_install.h`) copy it only when it is missing. Before this, every update replaced it with the build's default.

## What was checked, and what was not

- The builder ran start to finish. Both links were identical.
- On the console, MangoJuice failed to load because DWrite.dll was missing (run-0060, above). That is now fixed in the build, but the fix has not been tested on the console.
- `hw_overlay.c` compiles with the console's own compiler flags (`helper_compile_flags`). In the host preview harness:
  - a MangoJuice-style file (`legacy_layout=false`, `fps`, `ram`) gave `gpu=0 cpu=0 ram=1 fps=1 frametime=0 frame_timing=0`;
  - the build's default file still gave the default rows.
- `native/hw_install.h`: host syntax check only.
- The icons were previewed at 16, 32 and 48 px on the dark menu (38,38,40), the light menu (240,240,240) and the selection colour (0,120,215).
- **Not run anywhere:**
  - MangoJuice itself: running the downloaded GTK binaries natively on the build PC was not allowed in this session, and the host Wine build has no display driver;
  - not on shadPS4, and on the PS4 only as far as the DWrite.dll failure;
  - its startup time, memory use and controller navigation;
  - whether GTK 4.24's cairo path works under OrbisDesk's Wine at all.

A first console test:

1. Open Graphics Tools > MangoJuice and note the time to the first window.
2. Untick a few metrics, change the position, and save.
3. Turn Estadisticas off and on, and compare its `PWOVERLAY hud:` line.
4. Start vkcube and look at MangoHud.
5. Close MangoJuice, reopen Start, and check the desktop is still responsive.
6. Install the next build and check that the settings were kept.

## vkSpin's icon

The vkSpin icon used to be a bare triangle. Its blue corner disappeared on the dark menu and on the highlight, and its white centre on the light menu. A fault in `tools/make-icons.py` made it worse: `raster()` took a pixel's alpha from its most frequent subsample colour. A gradient makes every subsample a different colour, so the triangle came out about 1/16 opaque.

Alpha is now the coverage, and the colour is the mean of the subsamples. vkSpin is now the same triangle on a rounded yellow-to-magenta tile with a dark rim and a white edge, and it stands out on all three backgrounds. The other icons look the same or slightly cleaner, with fewer edge halos, but their bytes change.
