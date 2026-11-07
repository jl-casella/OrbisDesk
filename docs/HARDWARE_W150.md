<a id="w150-sin-los-diagnósticos-del-marco-negro-fase-6-paso-2"></a>


# W150: without black frame diagnoses (phase 6, step 2)

[English](HARDWARE_W150.md) | [Español](HARDWARE_W150-es.md)

APP_VER 02.49. Base W149. The drawing doesn't change.

<a id="cambio"></a>


## Change

W149 He fixed the black frame. The diagnosis of W146–W148, that made the first opening of the Start menu slow:

- `tools/build-win32u-ps4.py`: without log `flush_shape` (W146) or cell record `layer_stack` / `layer` (W147 - W148). `apply_shape` follows: window forms are transparency on the way by GPU.
- `platform/ps4/pw_wine_sink_ps4.c`: with layers, the output buffer is turned only into the tables that go to the log (the first 8 and one in each 64), as in W144 - W147.
- `tools/build-wine-hardware.py`: `PW_SINK_MAX_DUMPS` returns from 40 to 8.

<a id="qué-se-espera"></a>


## What is expected

- The first opening of the Start menu as fast as the following.
- No black frame, like in W149.

<a id="prueba-física"></a>


## Physical test

Report: `reports/wine-hardware-w150/physical/20261103T131357Z`. User response: "Keep slow."

- There were only 5 overturned and no log of batteries: what was taken was not the main cause.
- In the log, each opening of the Start menu writes hundreds of old diagnostic lines (5.613 lines in a Runs of ~ 40 s):
  - `PWDIRENUM` folder listing of W110: 2.420 lines
  - `trace+module` in `WINEDEBUG`, W092: 1.308 lines, one for each resource search (menu icons);
  - `PWSHELL` scout marks of W097, and `startmenu icon` menu icons of W057;
  - mouse and input (`mouse_sample`, `input_pull`), of W061/W063.
- With the scout marks, the first opening of the menu takes ~ 1 s from the click: 0,3 s before filling it and 0,7 s filling it. The following take ~ 0,5. The first submenu takes another 0,8.

Those logs are removed in W151 (`HARDWARE_W151.md`).
