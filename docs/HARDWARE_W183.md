<a id="w183-pale-moon-en-su-propio-proceso-fase-9-apply-de-winecfg-sin-bloqueo-y-teclas-del-mando-con-varias-fuentes-fases-5-y-7"></a>


# W183: Pale Moon in its own process (phase 9), Unlocked winecfg Application and control keys with various sources (phases 5 and 7)

[English](HARDWARE_W183.md) | [Español](HARDWARE_W183-es.md)

APP_VER 02.82. Base W182. The result of W182 is in `docs/HARDWARE_W182.md`.

<a id="teclas-del-mando-con-varias-fuentes"></a>


## Control keys with various sources

`native/hw_pad.c` (direct access session; did not enter W182 because it was edited during that build): each key in a profile has the account of how many sources it is held.
- The key goes down with the first source and goes up with the last. Cross and stick up, for example, send both the arrow up.
- Before, when the stick came back from the center with a tight cross, the arrow was loose and the kart stopped accelerating.
- When you enter the game mode you release all the keys held.

<a id="pale-moon-solo-fase-9-sesión-del-navegador"></a>


## Pale Moon alone (phase 9, browser session)

<a id="qué-pasó-en-w182"></a>


### What happened in W182

Reporte: `reports/wine-hardware-w182/physical/20261103T230134Z/`.

1. **The WebView test renders** the local page. Two rows don't run, and it's expected:
   - `es2020`: IE control runs the scripts with Wine jscript, which does not have ES2020.
   - The knot: the mshtml of Wine does not implement knot (there are `getContext` or `HTMLCanvasElement` in `dlls/mshtml`).

   It has nothing to do with acceleration, and it's not a test error. The Gecko engine only draws; The scripts don't go through it.
2. **Pale Moon close the app** (`run-0002.log`, `run-0003.log`).
   - In the two runs the WebView test was opened before, which carried the `mozglue.dll` of Wine Gecko. Gecko's not unloaded, so he's still loaded.
   - When loading `palemoon.exe`, your import `mozglue.dll` was resolved by base name to the already loaded module. The charger does that with a name already loaded (`find_basename_module`), just like Windows.
   - Exports were missing (`No implementation for mozglue.dll.?DllBlocklist_CheckStatus…`, `?Now@TimeStamp…`, `strdup`). The first call aborted (`unimplemented function mozglue.dll.?Now@TimeStamp…`) and closed the entire title.
   - Gecko and Pale Moon share the names `mozglue`, `nss3`, `xul`, `lgpllibs`, `freebl3`, `softokn3`, `mozavcodec`, `mozavutil`, `libEGL` and `libGLESv2`. In the same process only the one that loads first works, in either of the two orders.

<a id="cambio"></a>


### Change

Pale Moon runs alone, in a relaunch of the title, like the programs of 32 bits.

|File|What are you doing?|
|---|---|
| `tools/build-guest-hw.py` (kernelbase, `process.c`) |`ps4_runs_alone(nombre)` read `HKCU\Software\Wine\AppDefaults\<exe>` `"OrbisRunsAlone"="Y"`. A program of 64 bit marked so it is not charged as a guest (`PWGUEST runs_alone app=…`). In the W106 block it follows the path of the 32 bits: a notice to confirm and then `NtCreateUserProcess`, which reproduces the title with that program (`pw_hw_switch_program`). The log says `PWOPEN runs_alone_relaunch image=… answer=…`.|
| `tools/build-wine-hardware.py` (`user.reg`) | `[Software\Wine\AppDefaults\palemoon.exe]` `"OrbisRunsAlone"="Y"`. |

The notice says: "This program runs only: OrbisDesk it restarts to open it and when it closes it, it returns to the desktop. The open programs will be closed. Continue? "

**No change.** `pw_hw_switch_program` (`prepare-wine-boot.py`) relays any image other than an assistant of Wine. The pitcher (`native/wine_hardware.c`) starts the image alone, with WoW64 only if it is 32 bit, in its folder (`PW_PROGRAM_DIR`), and when it comes out it returns to the desktop. Before the guests (W043 - W051), the programs of 64 bits ran like this. The arguments of direct access (`-no-remote -profile "…"`) go through `next.txt`, which supports up to 6 arguments and respects the quotes.

**What changes for the user:**
- Open Pale Moon closes open programs.
- While Pale Moon runs there is no desk or taskbar.
- When you close Pale Moon return the desk.
- Gecko and Pale Moon no longer share process, so the order they open up stops importing.

**What is also earned:**
- Pale Moon does not have the limit of the guest's threads.
- The mozgue hooks in ntdll and a failure of Pale Moon do not affect to explore.
- Later on, by having its own process, Pale Moon could use dxgi/D3D11 of DXVK. It wasn't done in W183.

**Register on the console.** The fusion of `user.reg` when you climb (W172) keeps the blocks AppDefaults of the console and adds those that are only in the build. If the console already has a block `AppDefaults\palemoon.exe` (for example, created from winecfg), the console is left and `OrbisRunsAlone` does not arrive. After uploading, the transfer record (preserved blocks) has to show the new block.

<a id="verificación-sin-consola"></a>


### Console-free verification

- `build-guest-hw.py` and `build-wine-hardware.py` compile as Python.
- I repeated the revisions of `build-guest-hw.py` in a copy (without `make` and without writing in `build/` or `out/`). The revised `process.c` of kernelbase compiles with the exact command of the tree (`compile_commands.json`) and ends with 0.
- The only undeclared (`wcstoul` notice is from the code of W060, which was already.

<a id="construcción-orden"></a>


### Construction (order)

1. `python3 tools/build-guest-hw.py` (recombination kernelbase and ntdll of guests)
2. `python3 tools/build-wine-hardware.py`
3. `python3 -I tools/check-web-closure.py build/wine-hardware-w183/runtime`: it has to end with 0.

<a id="prueba-física"></a>


### Physical test

1. **WebView test (64 -bit):** continues to function as a guest.
2. **Pale Moon from the Start** menu (with the user's copy in `C:\Program Files\Pale Moon`):
   - The warning has to come up.
   - By accepting, the title restarts and opens Pale Moon alone. The log has to show `PWOPEN runs_alone_relaunch … answer=1` and, in the next run, `switch_program image=…palemoon.exe`.
   - The local page is expected with `es5-ok`, `es2020-ok` and `canvas-ok`.
   - When you close Pale Moon, you have to return the desk.
3. **The reverse order:** open Pale Moon first, close it and then open the WebView test. They both have to work.
4. **If Pale Moon fails in your own process:** search `map_view anon mmap error` (the reserve of 1 GB that the main session fixes in `virtual.c`) and repeat with "Pale Moon (not JIT."

<a id="no-verificado"></a>


### Not verified

- Nothing was tested on the console.
- A relaunch of 64 bits from W052 was not tested (those of 32 bits yes, from W116).

<a id="apply-de-winecfg-fase-7-sesión-de-accesos-directos"></a>


## Winecfg application (phase 7, direct access session)

<a id="qué-dijeron-las-marcas-de-w182"></a>


### What did the marks of W182 say

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


### The cause

- `update_window_pos` (`programs/winecfg/theme.c`) travel **all** first level windows with `EnumWindows` and to each of them it makes `SetWindowPos(SWP_FRAMECHANGED)`, so that it takes the new edges.
- In win32u (`NtUserSetWindowPos`, `dlls/win32u/window.c`), if the window is of another thread, the change is sent with `send_message`, **without timeout**: winecfg waits for that thread to read his messages.
- In the console, winecfg runs as a guest within the process of explorer, with the scout threads and other programs. A first-level window of a thread that does not read messages is enough so that Apply will never return.
- It is not a broadcast (so there is no `PWBCAST`), and the thread of the explorer interface is still well (`PWSHELL monitor heartbeat_age_ms=223`).

<a id="cambio-1"></a>


### Change

- `tools/build-winecfg-hw.py`, one more revision in `theme.c`:
  - The windows of **other threads** are passed by `SWP_ASYNCWINDOWPOS`. win32u then send the change with `SendNotifyMessage`, without waiting, and the other thread applies it when you read your messages;
  - the windows of the winecfg thread themselves remain the same;
  - a new mark: `PWCFG window_pos windows=N other_threads=M ms=T`.
- The `PWCFG` marks of W182 are left.
- Separate compiler (copy of the building with output on the scratchpad): 7 reviews, without warning.

<a id="prueba"></a>


### Test

1. winecfg → Desktop integration → choose Moon → Apply. Repeat with Noir and with "(No theme)."
2. winecfg continues to respond; in the log are `PWCFG apply step=refresh` and `PWCFG window_pos`.
3. The open windows (explorer, other programs) take the new edges.

<a id="prueba-física-1"></a>


## Physical test

Report: `reports/wine-hardware-w183/physical/20261103T232154Z/`. User response: "1 reboot but does not start (rescan), 2 when accepting or cancelling the app is closed (it was not frozen when applying now), 3 ok."

- **Pale Moon:** the relaunch works (`PWOPEN runs_alone_relaunch`, and then `pe_machine … palemoon.exe` as a title).
  - Pale Moon fails at ~ 13 s. In `run-0005`: `DxvkMemoryAllocator: Memory allocation failed, Size 4096`, then `c0000005` and a breakpoint of Mozilla (`0x80000003`). In `run-0007`: `c0000005`.
  - Pale Moon creates a device D3D11 (the `d3d11.dll` of DXVK) when starting, although the acceleration is off in its `user.js`, and the Vulkan memory reserve of DXVK fails. It's going to W184.
- **winecfg:** Apply no longer freezes (`step=sysparams` et seq.).
  - When you close with OK or Cancel, winecfg (thread `0040`) ends and is downloaded. Then the applet thread in `rundll32` (`003c`) runs in `0x100782560`, inside the winecfg already downloaded, and the app falls with `0xc0000005`.
  - The accounts of two guests (`rundll32` and winecfg, launched from it) are stepped on. It's going to W184.
- **Start square in Luna/Noir:** well.
