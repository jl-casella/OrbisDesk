<a id="w183-parte-de-winecfg-aplicar-un-tema-ya-no-se-congela"></a>


# W183, part of winecfg: Apply a theme no longer freezes

[English](HARDWARE_W183-winecfg-borrador.md) | [Español](HARDWARE_W183-winecfg-borrador-es.md)

Eraser of the configuration session of Wine. The main session adds it to `HARDWARE_W183.md`.

<a id="qué-dijeron-las-marcas-de-w182"></a>


## What did the marks of W182 say

In `run-0001.log` (`reports/wine-hardware-w182/physical/20261103T230134Z`, lines 1423 - 1442, thread `0040`:

|Step to Apply| ms |
|---|---|
| `settings` | 0 |
| `theme` (`ApplyTheme` 168, `refresh_sysparams` 15) | 216 |
| `shell_folders` | 11 |
| `sysparams` (`SPI_SETNONCLIENTMETRICS` 21, `SetSysColors` 124) | 145 |
| `refresh` |It's not over.|

- There is no line `PWPAINT` or `PWBCAST`. There is no repainted loop or broadcast that runs out of time.
- The 7 lines `open_mountmgr failed` after `sysparams` come from `read_shell_folder_link_targets`, the first step of `refresh`. The same 7 come out within `shell_folders`, which does end. Those calls come back.
- The following in `refresh` is `update_shell_folder_listview` (the list of the page itself), `update_mime_types` (a key to the record) and `update_window_pos`.

<a id="la-causa"></a>


## The cause

- `update_window_pos` (`programs/winecfg/theme.c`) travel **all** first level windows with `EnumWindows` and to each of them it makes `SetWindowPos(SWP_FRAMECHANGED)`, so that it takes the new edges.
- In win32u (`NtUserSetWindowPos`, `dlls/win32u/window.c`), if the window is of another thread, the change is sent with `send_message`, **without timeout**: winecfg waits for that thread to read his messages.
- In the console, winecfg runs as a guest within the process of explorer, with the scout threads and other programs. A first-level window of a thread that does not read messages is enough so that Apply will never return.
- It is not a broadcast (so there is no `PWBCAST`), and the thread of the explorer interface is still well (`PWSHELL monitor heartbeat_age_ms=223`).

<a id="cambio"></a>


## Change

- `tools/build-winecfg-hw.py`, one more revision in `theme.c`:
  - The windows of **other threads** are passed by `SWP_ASYNCWINDOWPOS`. win32u then send the change with `SendNotifyMessage`, without waiting, and the other thread applies it when you read your messages;
  - the windows of the winecfg thread themselves remain the same;
  - a new mark: `PWCFG window_pos windows=N other_threads=M ms=T`.
- The `PWCFG` marks of W182 are left.
- Separate compiler (copy of the building with output on the scratchpad): 7 reviews, without warning.

<a id="prueba"></a>


## Test

1. winecfg → Desktop integration → choose Moon → Apply. Repeat with Noir and with "(No theme)."
2. winecfg continues to respond; in the log are `PWCFG apply step=refresh` and `PWCFG window_pos`.
3. The open windows (explorer, other programs) take the new edges.
