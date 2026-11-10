# W292: desktop icons in columns, with File Manager and Steam first (draft)

[English](HARDWARE_W292-escritorio-columnas-borrador.md) | [Español](HARDWARE_W292-escritorio-columnas-borrador-es.md)

Draft to merge into the W292 notes. Nothing here was tested on the console.

## Request

User:
- desktop shortcuts should fill columns from top to bottom, starting a new column to the right when the height above the taskbar is full;
- "File Manager" should always come first, "Open Steam Client" second, and the rest alphabetically.

Before this change, the W168 launcher window filled rows from left to right, in folder order.

## Change

`tools/build-explorer-hw.py`, through `desktop-columns-order.patch.py` (notes folder). It needs the W290 desktop block ([desktop refresh and menu](HARDWARE_W290-escritorio-borrador.md)) and adds 4 revisions to `desktop.c`.

- **Columns:**
  - an icon's position is now its column (index ÷ icons per column) and row (the remainder). `get_icon_rect`, `get_title_rect` and `launcher_from_point` use the same mapping, so painting, double-click and the right-click menu agree;
  - icons per column = the height above the taskbar ÷ the launcher cell. That height is the top of `Shell_TrayWnd` when it's visible (at 1280×720, 720 minus the taskbar), otherwise the work area, otherwise the screen height;
  - the `OrbisDesktopIcons` window is resized to columns × rows. Its height is recomputed on each placement: at start, and on each poll, menu or notification reload.
- **Order:**
  - `File Manager.lnk` first and `Open Steam Client.lnk` second when they exist, then the rest by name, case-insensitive. If two have the same name (user and public Desktop), the path decides;
  - the list is sorted in `place_desktop_icons`, which runs after every load and reload. The order holds after the 2 s poll, a rename or a delete. A deleted shortcut simply isn't there.
- **Log:** one line per placement: `PWDESK order count=N columns=C per_column=R: File Manager | Open Steam Client | ...`, or `PWDESK order count=0`.

## Build

1. Apply: `python3 desktop-columns-order.patch.py tools/build-explorer-hw.py`. It refuses if it's already applied, if the W290 block is missing or if the W179 anchor isn't unique.
2. `python3 tools/build-explorer-hw.py`, then the package (`build-wine-hardware.py` checks explorer's manifest).

Scratch check, on a copy of the builder at sha `b4647688…`:
- 70 revisions;
- `desktop.c` compiles without warnings, and `explorer.exe` links (sha `ed9f3baa…`).

## Physical test

1. **Layout:** with more shortcuts than fit in one column, they go down the left edge and continue in a second column. None is hidden behind the taskbar.
2. **Order:** File Manager is at the top left, Open Steam Client below it, then the rest alphabetically. Log: `PWDESK order`.
3. **Rename:** rename a shortcut from the menu or WFM so it moves in the alphabet. Within about 2 s it moves to its new place, and File Manager and Steam stay first.
4. **Delete:** delete Open Steam Client. The others move up a place. Restore it, and it's second again.
5. **Hit test:** in the second column, double-click opens the right program, and the right-click menu names the right shortcut (Properties).

## Not verified

- Nothing was tested on the console or in the Linux runner.
- The taskbar height on the console: the column count comes from the `Shell_TrayWnd` rectangle, read when the icons are placed. If the taskbar changes size later (for example, a theme change), the icons follow at the next reload, not right away.
- With more icons than fit on screen, the extra columns run off the right edge, as rows did before.
