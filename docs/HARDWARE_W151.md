<a id="w151-sin-los-logs-viejos-del-menú-inicio"></a>


# W151: without the old login of the Start menu

[English](HARDWARE_W151.md) | [Español](HARDWARE_W151-es.md)

APP_VER 02.50. Base W150. The drawing doesn't change.

<a id="cambio"></a>


## Change

Diagnostics of previous increments are drawn that they wrote at each opening of the Start menu. They were left from when the menu did not show folders or icons, or from when to explore was hung:

- `tools/build-wine-directory-ps4.py` (W110): without the lines per file (`native_entry`, `returned`, `matched`, `cached`) nor `read_end` in readings without error. Errors (`read_failed`, `stat_failed`, `ignored`) follow.
- `native/wine_hardware.c` (W092): `WINEDEBUG` goes from `trace+module` to `warn+module`. You continue to show the wrong DLL when you start, which was your purpose, without a line for resource.
- `tools/build-explorer-hw.py`:
  - without the menu icon log (W057);
  - without a line per progress mark, click on the task bar or window notification (W097).
  - The scout observer follows and every 2 s reports the last mark.
- `tools/build-win32u-ps4.py` and `native/hw_pad.c`: without `input_pull` (W061) or `mouse_sample` (W063).

<a id="prueba-física"></a>


## Physical test

Report: `reports/wine-hardware-w151/physical/*`. User response: "Faster."

- The log dropped from 5.613 lines (W150 to 988 in a similar Runs: 0 `PWDIRENUM` and 0 `trace:module`.
- `show_stats path=layers` no change (0,54 ms average after start-up).
- As there are no marks, there is no measurement in milliseconds of the menu opening. The result is the user's response.
