# W292: choosing the desktop wallpaper, with three more to pick from (draft)

[English](HARDWARE_W292-fondos-borrador.md) | [Español](HARDWARE_W292-fondos-borrador-es.md)

Draft to merge into the W292 notes. Nothing here was tested on the console.

## Request

User: be able to change the desktop wallpaper, with 2 or 3 more built-in wallpapers besides `orbis-hills.bmp`.

## How the wallpaper reached the screen

- The launcher passes `WINE_PS5_WALLPAPER=/data/wine-prefix/drive_c/windows/orbis-hills.bmp` (`native/wine_hardware.c`).
- ps5drv (`tools/build-win32u-ps4.py`, W045/W144) reads that BMP once, when the driver is installed. It draws it as its own bottom layer, under every window: the desktop window has no surface on this driver.
- explorer's icon window paints the wallpaper under the icons with `PaintDesktop`, from user32's bitmap. user32 loads that bitmap from `HKCU\Control Panel\Desktop\Wallpaper`, which the build sets to `orbis-hills.bmp`.
- win32u's `update_desktop_wallpaper` runs for every `SPI_SETDESKWALLPAPER`, including explorer's at start. It only dropped its cached path. So a change from a program reached user32's bitmap but not ps5drv's layer, and the screen kept the boot image.

## Change: the wallpaper changes immediately

The change applies right away, without restarting. The launcher doesn't change: its environment variable remains the boot image, shown until explorer starts.

1. **win32u** (`wallpaper-live-win32u.patch.py` → `tools/build-win32u-ps4.py`, 3 revisions):
   - `update_desktop_wallpaper` reads the registry's `Wallpaper` and passes it to the new `ps5_set_wallpaper`;
   - ps5drv converts the DOS path with `ntdll_get_unix_file_name` and loads the BMP into a new layer. Under `screen_lock`, it swaps the layer in, frees the old one and presents the stack again. CPU composition redraws the whole screen too;
   - the same path is skipped. A file that doesn't load keeps the current wallpaper, and an empty value means black;
   - log: `PWBOOT wallpaper_set <path> unix=<path>`.
   - explorer calls `SPI_SETDESKWALLPAPER` at start, so the registry's choice replaces the boot image as soon as explorer runs. The launcher doesn't need to read the registry.
2. **explorer** (`desktop-wallpaper.patch.py` → `tools/build-explorer-hw.py`, 5 revisions; needs the W290 desktop block):
   - right-clicking empty desktop shows **Wallpaper**, a submenu with the `*.bmp` files in `C:\windows`, sorted, with the current one checked. `orbis-dusk.bmp` shows as "Dusk";
   - choosing one calls `SPI_SETDESKWALLPAPER` with `SPIF_UPDATEINIFILE`. That updates `HKCU\Control Panel\Desktop\Wallpaper`, user32's bitmap and ps5drv's layer, and the icon window is repainted;
   - **another program's change:** explorer gets `WM_SETTINGCHANGE` for the wallpaper. It copies the new value and repaints the icons;
   - log: `PWDESK wallpaper menu|set|changed|start …`.
3. **Surviving uploads:**
   - `Control Panel\Desktop` belongs to the build: each upload replaces it, putting `orbis-hills.bmp` back;
   - explorer keeps a copy of the choice in `HKCU\Software\OrbisDesk\Desktop\Wallpaper`, and `tools/upload-hardware.py` now treats `Software\OrbisDesk` as console-owned (`wallpaper-package-upload.patch.py`);
   - at start, if Control Panel holds the default but the copy names another file that exists, explorer restores the copy. Otherwise it copies the current value, so a change from regedit is kept too. If regedit sets exactly `orbis-hills.bmp` while the copy holds another file, the copy wins at the next start.
4. **Wallpapers:**
   - `make-wallpaper-set.py` (notes folder; meant for `tools/`) draws `orbis-dusk.bmp`, `orbis-aurora.bmp` and `orbis-meadow.bmp`;
   - each is a 1280×720 procedural landscape with a fixed seed, in pure Python, taking about 20 s for all three. Nothing is downloaded or copied, so there's no third-party attribution;
   - output: `out/wallpaper-set/` with a manifest of hashes;
   - `build-wine-hardware.py` copies them, hash-checked, next to `orbis-hills.bmp` in `C:\windows`. The default doesn't change.

| File | sha256 |
| --- | --- |
| `orbis-dusk.bmp` (sunset, layered hills) | `c52e12f7…` |
| `orbis-aurora.bmp` (night, aurora, lake) | `5fda4043…` |
| `orbis-meadow.bmp` (morning fields) | `f8e4c4e7…` |

## Build

1. `python3 make-wallpaper-set.py .`, run from the repository root, or from `tools/` once copied there.
2. Apply:
   - `wallpaper-live-win32u.patch.py tools/build-win32u-ps4.py`;
   - `desktop-wallpaper.patch.py tools/build-explorer-hw.py`;
   - `wallpaper-package-upload.patch.py .` (patches `build-wine-hardware.py` and `upload-hardware.py`).
3. Run `build-win32u-ps4.py`, `build-explorer-hw.py`, `link-wine-boot.py` (win32u goes into the boot ELF), then `build-wine-hardware.py`.

## Physical test

1. Right-click empty desktop, then **Wallpaper**: Aurora, Dusk, Hills and Meadow are listed, with Hills checked.
2. Pick Dusk. The screen changes right away, under the windows and the icons. Log: `PWDESK wallpaper set` and `PWBOOT wallpaper_set`.
3. Open a window and move it over the desktop: nothing old shows through.
4. Restart OrbisDesk: Dusk stays. A short boot image of the hills, before explorer starts, is expected.
5. After the next upload, Dusk is still the wallpaper. Log: `PWDESK wallpaper start … restored=1`.
6. Pick Hills again, then restart: Hills stays.

## Not verified

- Nothing was tested on the console or in the Linux runner.
- Whether freeing the old layer while the GPU path presents shows a flicker. The sink marks the last stack stale on free, and the new stack follows at once, as on a window resize.
- Each wallpaper layer is a full-screen buffer in the GPU pool (about 3.7 MB at 1280×720). Only one is kept at a time.
- Programs that cache their own copy of the wallpaper keep it until they repaint.
