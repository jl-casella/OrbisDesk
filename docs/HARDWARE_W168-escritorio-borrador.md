<a id="w168-borrador-accesos-directos-en-el-escritorio"></a>


# W168 (draft): direct access to the desktop

[English](HARDWARE_W168-escritorio-borrador.md) | [Español](HARDWARE_W168-escritorio-borrador-es.md)

Desktop side session eraser. The number of buildings is set by the main session; If this change comes in with another, it's reborn.

<a id="por-qué-no-había-accesos-directos"></a>


## Why there were no direct access

There are two cases, and the two corrections are needed.

1. **The desktop does not receive what it scans paints.** The scout of Wine loads the `.lnk` of the Desktop folders (`FOLDERID_Desktop` and `FOLDERID_PublicDesktop`) as pitchers and draws them in the `WM_PAINT` of the desktop window (`desktop.c`: `initialize_launchers`, `draw_launchers`. We run with `/desktop=shell,1280x720`, so it's not the root desk and the pitchers do load (`NoDesktop` is not in the record). But in ps5drv the desktop window has no surface (W045: the composer only arms the first-level windows on the bottom layer that loads the driver from `WINE_PS5_WALLPAPER`. What you explore paints on your desktop, background and icons, never gets to the screen.
2. **Desktop folders are empty.** In the prefixes of W126 a W167, `C:\users\orbis\Desktop`, `C:\users\jose\Desktop` and `C:\users\Public\Desktop` they exist but have no `.lnk`. `tools/build-wine-hardware.py` copy the accesses of `tools/make-start-menu.py` only to the Start menu.

The records of W166 do not show errors of this part (`Could not get user desktop folder` does not appear); The bottom is loaded by the driver (`PWBOOT wallpaper_loaded 1280x720 bpp=24`).

<a id="cambio"></a>


## Change

`tools/build-explorer-hw.py`, over `desktop.c`:
- the pitchers move to a first level (`OrbisDesktopIcons`) own window, with the size of the icon grid from the upper left corner;
- paint the bottom with `PaintDesktop` and above the icons with `draw_launchers` of Wine;
- double-click opens access with `ShellExecuteW`, just like the original code of Wine;
- it stays below everything (`HWND_BOTTOM`, also when reordering in `WM_WINDOWPOSCHANGING`), does not take the activation (`WS_EX_NOACTIVATE`, `MA_NOACTIVATE`) and is `WS_EX_TOOLWINDOW`;
- if the contents of the Desktop folders change, the monitor of Wine the redimensione and the repainting; without launchers, it is hidden;
- a line `PWDESK launchers=… panel=… size=… per_row=… desktop=… public=…` when starting; if the class or window fails, `PWDESK class error=` or `PWDESK window error=`, and the pitchers remain in the desktop window as before.

`tools/build-wine-hardware.py`: copy File Manager, Notepad, Command Prompt and Solitaire (the same `.lnk` from the Start menu, with its verified hash) to `C:\users\Public\Desktop`.

To build you have to run `tools/build-explorer-hw.py` before `tools/build-wine-hardware.py`.

Built in a separate copy, no warnings. Not tested on the console.

<a id="qué-se-espera"></a>


## What is expected

- `PWDESK launchers=4` with `panel` other than zero.
- Four icons with their name up to the left, on the bottom, without a visible edge where the window ends.
- Double-click opens the program; the icon does not cover the open windows or appear in the task bar.

<a id="riesgos-y-límites"></a>


## Risks and limits

- If `ExtractIconExW` does not give a large icon for an access, Wine discard that pitcher without notice; The count of `PWDESK` shows it.
- `PaintDesktop` draw the focused and unscalated bitmap; The driver scale it to the screen. With `orbis-hills.bmp` (1280x720) and 1280x720 display match; with another size there would be a visible edge around the icons.
- If a program sends another window to `HWND_BOTTOM`, it's under the icons.
- The folder guard uses `ReadDirectoryChangesW`; if it does not work on the console, new accesses appear only when restart.
- One more layer in the composition, the size of the grid (a row of 4 icons).
