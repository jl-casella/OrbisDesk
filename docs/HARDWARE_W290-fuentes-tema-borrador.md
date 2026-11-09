# W290: system fonts keep their size after a visual-style change (draft)

[English](HARDWARE_W290-fuentes-tema-borrador.md) | [Español](HARDWARE_W290-fuentes-tema-borrador-es.md)

Draft to merge into the W290 notes. Nothing here was tested on the console.

## Report

User: after changing the theme, text looks smaller until the next app restart.

## Cause

1. **The style passes points as pixels.** Choosing a style in winecfg calls uxtheme's `ApplyTheme`, which reads the style's fonts from its INI. Aero, and Luna and Noir (built from it by `tools/build-msstyles-hw.py`), set:
   - `MenuFont`, `StatusFont`, `MsgBoxFont` and `IconTitleFont` = Tahoma 8;
   - `CaptionFont` = Tahoma 10 bold.

   `parse_handle_nonclient_font` (`dlls/uxtheme/msstyles.c`) passes the point size to `SPI_SETNONCLIENTMETRICS` unconverted, as a positive `lfHeight`.
2. **win32u keeps it as pixels.** `set_font_entry` (`dlls/win32u/sysparams.c`) keeps a positive height unchanged, and `get_font_entry` scales it as a pixel height. The result is an 8-pixel cell instead of 8 points, which is 11 pixels at 96 dpi: smaller text in menus, the taskbar, titles, message boxes and icon labels.
3. **A restart undoes it.** uxtheme sets the fonts without `SPIF_UPDATEINIFILE`, so they go only to the volatile key (`save_entry`), which is cleared at restart. Also, when a font is loaded from the registry, `load_entry` already reads a positive height as points. So after a restart the size is right again.

## Change

`tools/build-win32u-ps4.py`, through `theme-font-size.patch.py` (notes folder). One revision to `sysparams.c`: `set_font_entry` treats a positive height as points (`-muldiv(h, 96, 72)`), as `load_entry` does. Negative heights go through `map_from_system_dpi` as before.

- **Why win32u and not uxtheme:**
  - win32u read the same stored value two ways: a positive height was pixels when set and points when loaded at the next start. Now both read it as points;
  - uxtheme has no project builder; its PE64 and PE32 copies come straight from the pinned build;
  - win32u's Unix side is shared by both worlds, so this one revision covers them.
- **Side effect:** a program that sets a system font with a positive cell height in pixels now gets it as points, about a third larger. Windows keeps such a value as pixels. Nothing in OrbisDesk does this other than uxtheme.

## Build

1. Apply: `python3 theme-font-size.patch.py tools/build-win32u-ps4.py`.
2. `python3 tools/build-win32u-ps4.py`, then `tools/link-wine-boot.py` (win32u goes into the boot ELF), then `tools/build-wine-hardware.py`.

Scratch check, on a copy of the builder at sha `d1c972fa…`:
- all 47 win32u units compile;
- no warnings in `sysparams.c`.

## Physical test

1. Note the size of text in Start, the taskbar clock, a window title and a desktop icon label.
2. In winecfg, Desktop Integration: switch Luna, then Noir, then Aero, and press Apply each time. The text keeps the size from step 1.
3. Restart OrbisDesk. The size is the same as before the restart.
4. Open a program (WFM, Notepad) after the switch. Its menus and message boxes keep the normal size.

## Not verified

- Nothing was tested on the console.
- The analysis comes from the pinned source: uxtheme, win32u and Aero's INI. Font heights weren't measured on screen.
- Programs that cache a font they created earlier (`HFONT`) and don't recreate it on `WM_SETTINGCHANGE` keep it. This affects only programs already open during the switch.
