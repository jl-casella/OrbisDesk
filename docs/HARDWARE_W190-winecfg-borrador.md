<a id="w190-parte-de-winecfg-el-tema-elegido-se-mantiene-al-reiniciar"></a>


# W190, part of winecfg: the chosen theme is maintained when restart

[English](HARDWARE_W190-winecfg-borrador.md) | [Español](HARDWARE_W190-winecfg-borrador-es.md)

Eraser of the configuration session of Wine. The main session adds it to `HARDWARE_W190.md`.

<a id="qué-pasó-en-w189"></a>


## What happened in W189

- The user changed the theme in winecfg, Apply and OK worked, but when the app was reopened the theme was again Luna.
- In the `user.reg` of the console (`/data/wine-prefix/user.reg`, read by FTP), `ThemeManager`, `Control Panel\Colors` and `WindowMetrics` have the time mark of 2026-11-03 22: 56: the session where Luna was chosen. No subsequent change came to the file.
- The record is kept in the console: keys to the same run (`Shell Folders`, 03: 07: 31) and the following start (`Fonts`, 03: 08: 15 are in the file.
- In `run-0001.log` (`reports/wine-hardware-w189/physical/20261104T030929Z`), winecfg runs between t 205 s and t 226 s (OK). The log ends at t-h 232 s: the app was closed about 7 s later.

<a id="la-causa"></a>


## The cause

- The Wine (`server/registry.c` server writes the record to disk every 30 s (`periodic_save`) and when it is turned off (`flush_registry`).
- On the console the title is killed; the server does not turn off. What changed in the last 30 s before closing the app is lost. The theme was applied about 7 s before closing.
- `RegFlushKey` was no service: on the server, `flush_key` he did nothing.
- It's not the start (nothing gets Luna back on; the default value of the build is style-free, W177) nor the rise (`upload-hardware.py` already conserves `ThemeManager` and the other keys to the theme of the console, W175).

<a id="cambio"></a>


## Change

- `tools/build-wine-delete-server.py`, one more unit, `server/registry.c` (only with `__ORBIS__`):
  - `flush_key` writes to the disk the branches changed (`flush_registry`), as `RegFlushKey` in Windows;
  - The newspaper kept goes from 30 s to 5. `save_branch` just write the branches that changed, so `system.reg` (1,4 MB is rewritten rarely.
- `tools/build-winecfg-hw.py`: Apply ends with `RegFlushKey(HKEY_CURRENT_USER)`. Accept goes by Apply.
- The two builders run: the server compiles `registry.c` without warnings and links 45 units; winecfg is left with 2 reviews, no warnings.

<a id="prueba"></a>


## Test

1. winecfg → Desktop integration → choose Noir → OK. Close the app immediately (less than 5 s).
2. Open the app: the theme is still Noir.
3. In the `user.reg` of the console, the time mark of `ThemeManager` is the time to accept.
4. Repeat with "(No theme)" and with Luna.
