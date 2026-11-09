# W292: "Reset as Root" and "Reset as Sandbox" in the Start menu (draft)

[English](HARDWARE_W292-reset-root-borrador.md) | [Español](HARDWARE_W292-reset-root-borrador-es.md)

Draft to merge into the W292 notes. Nothing here was tested on the console.

## Request

User:
- Start always has one item between "Open Steam Client" and "Exit desktop", depending on the current mode:
  - in NORMAL, "Reset as Root" restarts in ROOT;
  - in ROOT, "Reset as Sandbox" restarts in NORMAL;
  - each has its own icon;
- the restart skips the NORMAL/ROOT screen, or says clearly why it can't.

## How it works

- **Mode:**
  - the launcher (`native/wine_hardware.c`) keeps the mode chosen at start in `boot_root`. That comes from the selector, from `boot-mode.txt` on a program relaunch, or from a reset;
  - explorer runs as a guest in the same process, so it asks the native side directly, through the channel `C:\orbis\steam-open.exe` already uses: xinput1_3's Unix library, call 3, whose 260-byte name `native/hw_pad.c` reads as a request and answers in place;
  - `<root-mode>` answers `root` or `normal`. No new environment variable is needed.
- **Relaunch:** `pw_hw_reset_mode(root)` writes `/data/orbisdesk/force-mode.txt` (`root` or `normal`), leaves the jailbreak, and relaunches the title with `sceSystemServiceLoadExec("/app0/eboot.bin")`. A program started from the desktop does the same (W043, `pw_hw_switch_program`).
  - On the next start, `boot_choose()` reads and removes that file first. It takes that mode without the selector, writes `boot-mode.txt` as the selector would, and logs `PWJB mode=root|normal source=reset`. In ROOT the jailbreak then follows as usual.
  - The file is used once: a later manual start shows the selector again.
- **Errors are shown, not hidden:**
  - if the file can't be written, the relaunch is refused, or the system doesn't close the title within 10 s, the request answers `error: …`. The file is removed, ROOT takes the jailbreak back, and explorer shows the reply in a message box;
  - a request for the mode already running, or from a program's run, is refused;
  - if the native side doesn't answer `<root-mode>`, the item isn't added, and the log says so.

## Change

1. `reset-root-native.patch.py` (notes folder) → `native/wine_hardware.c` and `native/hw_pad.c`:
   - `pw_hw_boot_root`, `pw_hw_reset_mode` and the force-mode read in `boot_choose`;
   - the `<root-mode>`, `<reset-root>` and `<reset-sandbox>` requests. `hw_pad.c` references them weakly, so a build without them answers `error: unavailable`.
2. `reset-root-explorer.patch.py` → `tools/build-explorer-hw.py` (4 revisions in `startmenu.c`):
   - `MENU_ID_ROOT` and the native call, which asks for the mode once;
   - the item between Steam and Exit, labelled for the current mode;
   - two glyphs, drawn like the Run, Steam and Exit glyphs: an amber restart arrow for Root, and a green shield with a white bar for Sandbox.
   - Choosing it asks first, with No as the default, because open programs close without saving. It calls `RegFlushKey` on HKCU and HKLM, so recent settings such as a wallpaper choice aren't lost to the wineserver's 30 s save, then sends the request.
3. Log: `PWROOT explorer mode=…`, `PWROOT explorer reset to=… flush …`, `PWROOT request reset to=…`, `PWROOT reset to=… relaunch` / `load_exec rc=…` / `still_running`, `PWROOT force_mode=… removed=0`, `PWJB mode=… source=reset`.

## Build

1. Apply `reset-root-native.patch.py .` (repository root) and `reset-root-explorer.patch.py tools/build-explorer-hw.py`.
2. Run `build-explorer-hw.py`, then `build-wine-hardware.py`, which compiles `wine_hardware.c` and `hw_pad.c` into the ELF.

Scratch check:
- explorer, with the columns, wallpaper and Reset patches applied on top of builder sha `b4647688…`: 79 revisions, and `desktop.c` and `startmenu.c` compile without warnings;
- `wine_hardware.c` and `hw_pad.c` (working-tree shas `c6435309…` and `d6f6bff6…`), patched: both compile without warnings with the boot ELF's helper flags.

## Physical test

1. Start in NORMAL. Start shows "Reset as Root" between "Open Steam Client" and "Exit desktop", with an amber arrow. Log: `PWROOT explorer mode=0 reply="normal"`.
2. Choose it, then No: nothing happens.
3. Choose it, then Yes. The title closes and starts again, without the NORMAL/ROOT screen, straight to the loading bar. Log of the new run: `PWROOT force_mode=root`, `PWJB mode=root source=reset`, then `PWJB jailbreak rc=0 …`.
4. In that ROOT run, Start shows "Reset as Sandbox" in the same place, with a green shield, and USB disks appear as D: and later letters.
5. Choose "Reset as Sandbox", then Yes. The title starts again in NORMAL without the screen. Log: `PWJB mode=normal source=reset`, and no jailbreak lines.
6. Close OrbisDesk and open it again. The NORMAL/ROOT screen is back, because each reset is used once.

## Not verified

- Nothing was tested on the console.
- That `sceSystemServiceLoadExec` of the title itself works from the desktop run with no program pending. It's the call program switches already make, but always with `next.txt` present.
- Whether `RegFlushKey` makes this wineserver save the registry right away. Its result is only logged.
- Programs open at the time close without saving, as with any program switch.
