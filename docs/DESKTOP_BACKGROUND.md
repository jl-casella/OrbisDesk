# Desktop background dialog: your own pictures as wallpaper (draft)

[English](DESKTOP_BACKGROUND.md) | [Español](DESKTOP_BACKGROUND-es.md)

Draft. Nothing here was tested on the console.

## Request

User:
- set the desktop wallpaper to their own pictures, not only the built-in set;
- choose them in a dialog like Windows' Desktop Background, opened from the desktop's right-click menu;
- the built-in pictures move from the right-click menu into that dialog, and **Browse…** picks any picture through the file-open dialog.

## What Wine offers

Wine has nothing that sets the wallpaper:
- `desk.cpl` is only the display settings page (resolution);
- winecfg's Desktop Integration tab has themes, colours and fonts, but no wallpaper;
- shell32 has no Display Properties.

So the dialog is OrbisDesk's own. It's built in memory in explorer's desktop code, like the rename dialog from the desktop menu.

## Change

`tools/build-explorer-hw.py`, through `desktop-background-dialog.patch.py` (notes folder). It adds 4 revisions to `desktop.c`, on top of the desktop menu and the earlier Wallpaper block.

- **Menu:** right-clicking empty desktop no longer has the **Wallpaper** submenu. It has **Desktop background…** instead.
- **Dialog:**
  - **Picture:** the built-in pictures (the BMPs in `C:\windows`: Aurora, Dusk, Hills, Meadow) and, at the end, "My picture: *file*" when there is one;
  - a **preview** of the whole screen;
  - **Position:** Fill (cover the screen and crop), Fit (whole picture with black bars), Stretch, or Center (no scaling);
  - **Browse…:** the standard file-open dialog, for BMP, JPEG, PNG, GIF and TIFF. comdlg32 is loaded at run time, so explorer's link doesn't change;
  - a status line with the picture's size, or the reason it can't be used;
  - **OK**, **Cancel** and **Apply**.
- **Pictures:**
  - pictures are decoded with WIC (`windowscodecs`, created with `CoCreateInstance`). Its GUIDs are defined locally, because explorer doesn't link libuuid;
  - the picture is drawn on a screen-sized canvas as Position says;
  - the console's wallpaper layer (ps5drv) reads only 24/32-bit BMPs. So any picture other than a screen-sized built-in BMP is written as a 24-bit BMP to `%APPDATA%\OrbisDesk\wallpaper-1.bmp` or `wallpaper-2.bmp`. The two names alternate because the wallpaper layer reloads only when the path changes. The BMP is then set the usual way (`SPI_SETDESKWALLPAPER`), which also updates the screen immediately;
  - a built-in picture is set as it is, as the old menu did.
- **Memory:**
  - pictures over 16 megapixels are refused before they're decoded. A typical 16-megapixel photo fits;
  - Wine's WIC scaler is nearest-neighbour. A large picture is scaled to at most twice the screen size and averaged 2×2, which looks better and uses about 15 MB, plus the decoder's own copy of the picture (up to 64 MB for 16 megapixels) while the dialog renders;
  - the converted BMP is 2.7 MB at 1280×720.
- **Persistence:**
  - `HKCU\Software\OrbisDesk\Desktop` holds the choice:
    - `Wallpaper` is the BMP that was set, as before;
    - `Source` is the picture chosen;
    - `Style` is the position: 0 Fill, 1 Fit, 2 Stretch, 3 Center;
  - that key is console-owned (`tools/console_state.py`), so updates and the first-run installer keep it;
  - the converted BMP lives in the user's profile, which no update deletes; updates delete only the files they list as obsolete;
  - at start, explorer's existing restore puts the choice back when an update has reset `Control Panel\Desktop` to the default.
  - The build's `user.reg` and `system.reg` aren't changed.
- **Log:** `PWDESK background open|render|browse|apply …`. `render` lines include the source size, the HRESULT and the time taken.

## Build

1. Apply on the main checkout: `python3 desktop-background-dialog.patch.py tools/build-explorer-hw.py`. It refuses if it's already applied, if the W292 Wallpaper block is missing, or if its anchor isn't unique.
2. `python3 tools/build-explorer-hw.py`, then the package (`build-wine-hardware.py`, which checks explorer's manifest).

No other builder needs to run: win32u already switches the wallpaper layer while running, and windowscodecs and comdlg32 are already in the runtime.

Scratch check, on a copy of the builder at sha `2b70355e…` (main checkout, `feat/wine-mono`): 86 revisions, `desktop.c` compiles without warnings, and `explorer.exe` links (sha `3c924afc…`).

## Physical test

1. Right-click empty desktop: **Desktop background…** is there, and the **Wallpaper** submenu is gone.
2. Open it. The list shows Aurora, Dusk, Hills and Meadow, with the current one selected and previewed. Log: `PWDESK background open`.
3. Select Dusk, then **Apply**. The wallpaper changes immediately. Log: `PWDESK background apply … target=C:\windows\orbis-dusk.bmp`.
4. **Browse…**, then pick a JPEG or PNG, for example from Documents or a USB disk. "My picture: …" appears and the preview shows it. Try each Position; the preview follows.
5. **OK**. The wallpaper is your picture. Log: `PWDESK background apply … target=…\AppData\Roaming\OrbisDesk\wallpaper-1.bmp`.
6. Apply another picture: the target alternates to `wallpaper-2.bmp`, and the screen changes again.
7. Restart OrbisDesk: your picture stays. After the next update it still stays. Log: `PWDESK wallpaper start … restored=1`.
8. Pick a picture over 16 megapixels: the status line refuses it, and the wallpaper doesn't change.
9. The dialog works with the pointer and with keys: Tab, the arrows, Enter and Escape.

## Not verified

- Nothing was tested on the console.
- How long a large JPEG takes to decode on the PS4. The `render` log line records it.
- How Wine's file-open dialog looks and behaves with the pad's pointer and the on-screen keyboard.
- GIF and TIFF use WIC's decoders, as shipped. Only the first frame of an animated GIF is used.
- If the original picture is deleted or its USB disk is removed, the wallpaper stays, because it's a copy. The dialog then lists the converted copy as "My picture".
