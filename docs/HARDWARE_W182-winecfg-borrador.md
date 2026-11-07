<a id="w182-parte-de-winecfg-y-del-aspecto-diagnóstico-del-congelamiento-al-aplicar-un-tema-iconos-del-panel-de-control-y-botón-inicio-recto"></a>


# W182, part of winecfg and appearance: a diagnosis of freezing when applying a theme, control panel icons and straight Start button

[English](HARDWARE_W182-winecfg-borrador.md) | [Español](HARDWARE_W182-winecfg-borrador-es.md)

Eraser of the configuration session of Wine. The main session adds it to `HARDWARE_W182.md`.

<a id="por-qué"></a>


## Why?

- In W180, winecfg was frozen by choosing a desktop integration theme and pressing Apply.
- The log in that Runs doesn't say what call he didn't come back. There are two suspicions:
  - `update_now` (repainted with `RDW_UPDATENOW`) in an endless loop, because a window of another thread continues to ask `WM_PAINT`;
  - several `broadcast_message` that deplete their timeout of 2 s, one behind the other, for each window that does not respond.
- W182 just add marks on the log to know which of the two is. It doesn't change the behavior.

<a id="cambios-de-diagnóstico"></a>


## Diagnostic changes

- `tools/build-winecfg-hw.py` (new): winecfg of Wine set with `PWCFG` marks to apply.
  - Each step of `PSN_APPLY` has `begin` and `end` with milliseconds: `settings`, `theme`, `shell_folders`, `sysparams`, `refresh`.
  - Within `theme`: `ApplyTheme` (stylish and unstyled) and `refresh_sysparams`.
  - Within `sysparams`: `SPI_SETNONCLIENTMETRICS` and `SetSysColors`.
  - It comes out `out/winecfg-hw/winecfg.exe` (sha256 `bc36725e…`), without warning.
  - `tools/build-wine-hardware.py` copies it over that of `out/wine-programs`, `lib/wine/x86_64-windows` and `system32`, just like `taskmgr-hw`. Check that the manifest comes from the current builder.
  - `winecfg.cpl` (W179) does not change: it is another program that starts `winecfg.exe`.
- `tools/build-win32u-ps4.py`, with revisions of `tools/paint-broadcast-diag-w182.patch.py`:
  - `dce.c` `update_now`: if the loop reaches 256 turns, one line per process: `PWPAINT update_now_loop hwnd child tid flags`;
  - `message.c` `broadcast_message`: measures each shipment; If a window spends all the timeout, `PWBCAST timeout msg hwnd tid elapsed_ms`, once by window and up to 32 windows.
  - Compilation: 47 units, no fault.

<a id="cambios-de-aspecto-pedidos-por-el-usuario"></a>


## Changes in appearance (user orders)

- **Icons in the control panel menu** (`tools/build-explorer-hw.py`).
  - Before, the elements of the Control Panel in the Start menu were coming out with the generic icon, because they are not files.
  - Now, if an element does not bring icon, explore it to your folder: `IShellFolder::GetUIObjectOf(IID_IExtractIconW)` and `GetIconLocation(GIL_FORSHELL)`.
    - If the location is a file, use `ExtractIconExW` with that index.
    - If it is `GIL_NOTFILENAME`, use `IExtractIconW::Extract`.
    - If everything fails, the generic icon of before remains.
  - Compilation: 44 reviews, without warning; `explorer.exe` sha256 `53d66e00…`.
- **Straight Start button on Moon and Noir** (`tools/build-msstyles-hw.py`).
  - The green button (Moon) and orange (Noir) had the right edge rounded, as in XP. Now it's straight from both sides.
  - `SizingMargins = 4, 4, 12, 12`.
  - Recompiled: Moon `e316876118aaa794`, Noir `a6a299a396a26ff5`, 35 bitmaps each drawn.
  - Preview in `out/msstyles-preview/desktop-luna.png` and `desktop-noir.png`.

<a id="perfil-de-teclas-de-supermariokart"></a>


## Key profile of SuperMarioKart

The W181 "Bad Keys" was an error touch: the user confirmed that the keys are on. When it was reviewed, the error below appeared as well, which happens only when two buttons of the same key are pressed together.

- In `run-0002.log` (`reports/wine-hardware-w181/physical/20261103T224806Z`) the load profile (`PWPAD profile=SuperMarioKart.exe keys=14 stick=keys`, line 367) and send keys (`source=profile`.
- The codes are virtual keys of Windows: 37 - 40 are the arrows and 13 is Enter. ps5drv puts the can code with `MapVirtualKeyEx` and marks the arrows as extended (W141), so DirectInput reads `DIK_LEFT`, `DIK_UP`, `DIK_RETURN`, etc. That path was already tested with the USB keyboard.
- The `.ini` matches the controls of the `Read me.txt` game (arrows, space and Enter).
- **Error found** in `native/hw_pad.c`: each source sent its own loose key. With two sources on the same key, let go of the key even if the other one was still tight:
  - cross and stick above, the two `up`: if when the stick was folded, it passed over and returned, the kart stopped accelerating with the cross tight;
  - the same with cross and stick, circle and R1 (`space`), and triangle and Options (`enter`).
- **fix:** one counter per key. The key goes down with the first source and goes up with the last. When you enter game mode you release all those that are tight.
  - Comply with the link options, no warnings. Prove apart: two pulsations and two loose ones give a single down and a single up.
  - **It does not enter W182:** was edited with W182 already compiling (`hw_pad.o` it was already done). Get in W183.
- If the user says another key is wrong, it changes only the `.ini`.

<a id="prueba-en-la-consola"></a>


## Test on the console

1. winecfg → Desktop integration → choose Moon → Apply.
2. In the log:
   - the last line `PWCFG … begin` that does not have its `end` says what call does not return;
   - `PWPAINT` says which window keeps the repainted in loop;
   - `PWBCAST` says which windows are draining the 2.
   - If Apply ends well, all the marks have `end`, and the milliseconds say what step it takes.
3. Home Menu → Control panel: each item with its own icon.
4. With Moon or Noir: the Start button without the right curve.

<a id="pendiente"></a>


## Pending

- The arrangement of the freezing is left for W183, according to what these marks say.
