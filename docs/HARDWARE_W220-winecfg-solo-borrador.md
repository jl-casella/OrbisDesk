<a id="w220-casilla-run-alone-en-la-pestaña-applications-de-winecfg-borrador"></a>


# W220: "Run alone" box in the Winecfg Applications tab (draft)

[English](HARDWARE_W220-winecfg-solo-borrador.md) | [Español](HARDWARE_W220-winecfg-solo-borrador-es.md)

Eraser of the Wine configuration session, to join `HARDWARE_W220.md`. None of this was tested on the console.

<a id="qué-pasó-en-w217"></a>


## What happened in W217

Reporte: `reports/wine-hardware-w217/physical/20261104T192336Z/run-0004.log`.

- The user added `C:\Program Files\SeaMonkey\seamonkey.exe` in the Winecfg Applications tab to run alone.
- SeaMonkey started as a guest (line 1939), without `runs_alone`.
- The `user.reg` of the console does not have the `AppDefaults\seamonkey.exe` key.

<a id="causa"></a>

## Cause

- winecfg had no control for `OrbisRunsAlone`. That value reads it `ps4_runs_alone` (kernelbase, `tools/build-guest-hw.py`), and `winecfg.exe` of W217 It doesn't contain that name.
- **"Add application" does not write anything:** in Wine (`programs/winecfg/appdefaults.c`, `on_add_app_click` just add a row to the list. The key `AppDefaults\<programa>` appears only when you change some value with that chosen program.
- **Nothing was lost when saving:** AppDefaults is from the console in each climb, and the server keeps the record every 5 s (W190).

<a id="cambio"></a>


## Change

`tools/build-winecfg-hw.py`, with `winecfg-runs-alone-w220.patch.py`. The builder now reviews `appdefaults.c` in addition to `theme.c`: `make -n` with the two and three commands.

- **The box:**
  - dice "Run alone (the title restarts with this program)" y va debajo de Windows Version;
  - is created with the tab. The list is a shorter row, and the bottom line goes up. The resources of the dialogue do not change;
  - it is only enabled with a chosen program, not Default Settings, and shows the value it already has;
  - marked put `OrbisRunsAlone="Y"`; Unmarked erases it. It goes through the winecfg change list, so it's written with Apply or OK.
- **"Add application":** Enables Apply, and Apply creates `AppDefaults\<programa>` even if nothing else is changed. If the program is removed before implementation, the key is deleted equally.
- **Apply in this tab:** creates the keys of the added programs, applies the changes and ends with `RegFlushKey(HKEY_CURRENT_USER)`, as W190 on the theme.

<a id="construcción"></a>


## Build

1. `python3 tools/build-winecfg-hw.py`. It must give 8 reviews and 0 warnings. `build-wine-hardware.py` requires the manifest to correspond to the current builder.
2. `tools/build-wine-hardware.py`.

<a id="prueba-física"></a>


## Physical test

1. In winecfg, tab Applications: "Add application...," choose `seamonkey.exe`, mark "Run alone" and press OK.
2. Open SeaMonkey. The log must show `PWGUEST runs_alone app=…seamonkey.exe` and the title restarts with SeaMonkey.
3. **Persistence:** lower the `user.reg` of the console. You must have `[Software\\Wine\\AppDefaults\\seamonkey.exe]` with `"OrbisRunsAlone"="Y"`, and stay there after the next climb.
4. **Undial:** undial the box and apply. The value disappears, and SeaMonkey reboot as a guest.

<a id="no-verificado"></a>


## Not verified

- Nothing was tested on the console.
- The builder ran on a copy (8 reviews, 0 warnings, `winecfg.exe` armed), without touching `build/` or `out/`.
- The place of the box was calculated with the dialog measurements, without viewing it on screen.
