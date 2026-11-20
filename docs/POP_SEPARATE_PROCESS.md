# Separate Windows processes (PoP phases B–D)

[English](POP_SEPARATE_PROCESS.md) | [Español](POP_SEPARATE_PROCESS-es.md)

OrbisDesk runs every Windows program inside one PS4 title process. That model fails for a launcher and a game that both need the same fixed image base. Prince of Persia's launcher and `POP.exe` both use `0x400000`. This document records how a program marked **Separate processes** in winecfg now runs in a second native process. That process runs Wine as a client of the title's wineserver, with the title's desktop, registry and object namespace.

The research substrate (phase A, the GoldHEN loader and its scheduler fix) is in [Process-family probes](PROCESS_FAMILY_PROBES.md). OrbisDesk targets GoldHEN consoles, so the resident loader is a stated requirement and not a blocker. It still has to be sent again after every console reboot.

## What works on hardware (PS4 Pro Baikal, 12.50, ROOT boot, 2026-11-12 to 16)

| Phase | Result | Evidence (`reports/pop-phase-b/physical/`) |
| --- | --- | --- |
| B.1 | A loader-started process connects to the title's wineserver, registers (version 961), and creates `\KernelObjects\OrbisSeparateJoin` in the shared namespace | `20261112T032514Z` |
| C | That process creates a window on the title's desktop through raw wineserver requests. It receives mouse input, and the title composites its pixels | `20261112T085655Z` |
| D.1 | Wine itself runs in that process. A console PE64 program linked at `0x400000` loads there unrelocated and exits with 42. Three title boots in a row are stable | `20261112T130124Z` |
| D.2 | A GDI program's window appears on the desktop. It takes clicks, keys and drags, and the desktop stays open when it exits | `20261112T132927Z` |
| D.3 | `separate_launcher.exe` runs inside the title at `0x400000`. It calls `CreateProcess` on `separate_game.exe`, which is marked separate and also linked at `0x400000`, and the game runs in the second process. The launcher gets real handles and the game's exit code 44. The game gets 8 clicks and 11 keys | `20261112T141146Z`, `20261112T150746Z` |
| D.4a | The title's Vulkan probe, run in the separate process, loads `libSceGnmDriver.sprx` from `/system/common/lib` and then the console stops with *Fatal trap 9: general protection fault while in kernel mode*. The separate process cannot use the GPU | `20261112T154040Z`, `20261112T154358Z`, `20261112T155318Z` |
| D.4 | Inverse route: `separate_inverse.exe` runs in the separate process at `0x400000`. Its `CreateProcess` on `separate_game.exe`, also at `0x400000`, is handed to the title, and the game runs there as a 32-bit guest with input and a clean exit | `20261112T194224Z` |
| D.4b | The separate launcher stays inside `CreateProcess` until the game ends, as Prince of Persia's launcher must for `PrinceSM`. The game gets the launcher's argument (`argc` 2) through msvcrt. The title replies *started* then *ended* | `20261112T232400Z` |
| D.5 | Prince of Persia's own launcher runs separately and `POP.exe` runs in the title with the GPU. The launcher's `CreateProcess` returns at once, so its 25-second start check passes, and it reads the game's real exit code when the game ends | `20261113T132532Z`, `20261113T142613Z` |
| D.6 | With no execution mode set, Prince of Persia's and Worms 3D's launchers start as guests, meet the base collision and move to a separate process by themselves. The guest copy's named objects (`POP_Launcher`) are closed, and the launcher started again runs the game | `20261113T152940Z`, `20261113T155813Z` |
| Full screen | `POP.exe` (DXVK, a topmost window) sets 800x600 and is shown full screen, scaled to the output | `20261113T174954Z` |
| D.7 | A separate launcher that starts DirectInput and XInput threads (Tony Hawk's American Wasteland) no longer stalls the title's wineserver. A separate process ends with the title, so the next OrbisDesk start works without a console reboot. After a console reboot the title sends the resident loader itself | `20261113T203301Z` |

These results cover the configurations named here only. They do not show general application compatibility. The separate process has no GPU of its own, so a game that draws runs in the title and only its launcher runs separately (see *The inverse route* and *Limits*).

## How a launch flows

1. **kernelbase.** `CreateProcessInternalW` sees execution mode `separate` for the image. Its generator is `tools/build-guest-hw.py`. It writes `/data/orbisdesk/process-p014/spawn-request` with four lines: a token, the image, the command line and the current directory. It then waits up to 30 s for `started-<token>`, and stops at once on `failed-<token>`.
2. **Title watcher.** `native/pop_loader_spawn.h` turns the request into the child's job. It then sends `/data/orbisdesk/pop-wine-join.elf` to the resident loader on port 9021.
3. **Payload-SDK child.** `native/process_p014_child.c` takes the title's uid and loads `pop-wine-child.prx` with `dlopen`, so the system linker resolves its imports, TLS and initialisers. It connects to the title's bridge socket and calls `pop_wine_child_run_job`.
4. **Wine PRX.** `native/pop_wine_child.c` sets `WINESERVERSOCKET` to the bridge descriptor and calls `__wine_main`. ntdll then joins the title's server instead of starting one. Once joined, the process writes `pid tid` under the token, and kernelbase opens real process and thread handles for the caller.
5. **Display.** The child's win32u driver hands its window stack to `native/pop_child_sink.c`, which never opens VideoOut. The sink sends the top window and its handle over `surface.sock`. The title composites the frame at the window's rectangle. A pointer over that rectangle is delivered to that window by handle (`pw_hw_separate_window`, `tools/build-win32u-ps4.py`).

## The inverse route (D.4)

The GPU belongs to the title (D.4a). For a launcher and a game that both need `0x400000`, the launcher is marked **Separate processes** and the game stays a normal guest.

1. The user opens the launcher. kernelbase starts it in the separate process, as in the steps above.
2. In the separate process, the launcher's `CreateProcess` reaches `pw_hw_switch_program` (`native/pop_wine_child_stubs.c`). It writes `/data/orbisdesk/process-p014/title-launch` with the image, the command line, the directory and a token.
3. Explorer's watcher (`tools/patch-explorer-open.py`) reads the file every 500 ms. It posts `PW_SHELL_LAUNCH_MESSAGE` to the desktop window, which calls `CreateProcessW` in the title. A 32-bit image becomes a guest of explorer's 32-bit world at its own base.
4. Explorer creates the named event `Global\PWTitleLaunch_<token>` and writes `title-launch-reply`: `<token> started <pid>`, or `<token> failed <error>`. After *started*, a thread waits on the guest's process and main thread handles, writes `<token> ended <exit code>` and signals the event. A 32-bit guest's process handle is the title's, which is never signalled, so its main thread is the one that ends, and the exit code is that thread's.
5. **D.5.** In the separate process, `CreateProcess` returns at once (`__wrap_NtCreateUserProcess`, `native/pop_wine_child_stubs.c`). Its process and thread handles are that named event, as the title's own guests' process handles are their end events (W267). `NtQueryInformationProcess` answers `STILL_ACTIVE`, then the exit code from the reply. A wait on the handle ends when the game ends. Prince of Persia's launcher sets an event after `CreateProcess` returns and waits 25 s for it; with D.4b's blocking `CreateProcess` it reported that the game could not start. Named objects the launcher keeps, such as `PrinceSM`, live while it waits. On *failed* the launcher's `CreateProcess` fails. Not forwarded: `TerminateProcess` on that handle (it fails), and the process and thread ids (0). Against a title without the named event the separate process falls back to D.4b: the calling thread waits for *ended*, then the process exits.

The protocol is in `platform/ps4/pw_shell_open.h`.

## Closing, reopening and hangs (D.7)

- **Server reads.** wineserver's `read_request` reads a client request in a loop that ends on `EAGAIN`, so it relies on a non-blocking request descriptor. The console refuses `O_NONBLOCK` on these sockets, and a separate process's threads hand theirs over the bridge. Tony Hawk's launcher froze the title with `PWSERVER stuck_s=60 ... func=thread_poll_event`. Each read now asks `poll` first with no wait, and nothing to read counts as `EAGAIN` (`tools/build-wine-delete-server.py`).
- **Ending with the title.** The separate process watches its bridge socket to the title's server. When the title goes the socket hangs up, and the process ends (`native/pop_wine_child.c`, `P024 title_gone`). A launcher left open therefore no longer blocks the next start.
- **Loader after a reboot.** When the resident loader does not answer on port 9021, the title sends the bundled `elfldr.elf` to GoldHEN's BinLoader on `127.0.0.1:9090`, as `tools/start-process-loader.py --start` does from a PC, and tries again for 10 s. If the start still fails it writes `failed-<token>`, and kernelbase stops waiting (`native/pop_loader_spawn.h`, `PWSEP separate_failed_reported`). GoldHEN's BinLoader must be enabled.

### Tony Hawk launcher drag regression

The November 16 runs exposed two problems after the initial D.7 test. A large HID request from the title left the wineserver waiting for more data even though the pipe repeatedly signaled it was readable. The title and PRX now use the shared writer in `platform/ps4/pw_wine_request_write.c` for requests with payload, with writes capped at 512 bytes. The server defers a request descriptor that reports zero bytes while keeping other descriptors in service. The separate launcher also created its dialog without delivering a complete frame. P031 uses the PS4 signal-mask adapter when starting the presenter and sends frames on that thread with a socket send timeout. The GUI thread can keep updating the pending frame while the socket is busy.

The verified pair was the W303 small PKG, version **04.05**, and the external **P031** PRX.

| Artifact | SHA-256 |
| --- | --- |
| `OrbisDesk.pkg` | `d731542d774c60e456ba76d9959ab3b465fcfefa70dac3d83844f14178b10269` |
| `pop-wine-child.prx` | `a083506ffd67e92e7b66e5d25aa1597d8b3096205d17868982584a9c9ec35d7e` |

The local evidence is `reports/pop-phase-b/physical/20261116T155602Z/run-0149.log` and its companion logs. The title received 143 and 359 frames on the first and second opens, respectively. The second launcher logged 120 window moves and exited with code 0. The title restored desktop focus. This run closes the launcher drag regression for this configuration. The game `THAW.exe` launched as a guest and needed forced thread termination after it failed to exit within three seconds of `WM_CLOSE` from the overlay. The desktop stayed responsive and could reopen the launcher afterward.

## Without a winecfg choice (D.6)

A 32-bit guest that starts another 32-bit program needing the base it holds (error 487) used to get the prompt to restart OrbisDesk with that program alone. Now, when that starter has no execution mode chosen, kernelbase first writes `AppDefaults\<exe>\OrbisExecutionMode=separate` for it, as winecfg's **Separate processes** does. It then starts the starter again in a separate process and ends the guest copy. The launcher's window opens again, the user chooses Play again, and from then on the launcher opens separately. If the separate start fails (no resident loader, for instance), the value is removed and the prompt follows. A starter that is a game rather than a launcher would move too, and then has no GPU; set it to guest in winecfg.

Some games are the starter and start a small helper at the same base: Vampire - Bloodlines' `vampire.exe` starts a "CleanUp Application" from `%TEMP%`. Moving the game would leave it without the GPU. Before D.6, kernelbase now reads the started program's import table. A program that imports no graphics library (Direct3D, DirectDraw or OpenGL), and whose folder and `bin` folder hold no DLL that imports one, runs in a separate process itself, and the starter stays in the title. Hardware, 2026-11-16 (run-0160): `vampire.exe` stayed in the title and its helper ran separately (`PWSEP base_taken helper_to_separate=1`). The game then stopped in its SafeDisc check, which needs a Windows kernel driver.

The first version read only the program's own imports. Warcraft III's `war3.exe` loads `Game.dll` at run time, and `Game.dll` imports `d3d8`. Sent to the separate process, the game found no Direct3D 8 and said DirectX 8 was missing (run-0164). The same run sent `vampire.exe` there once, because its renderer is in `Bin\*.dll`. The folder and its `bin` folder now count, up to 64 DLLs, and `PWSEP base_taken` logs how many were read. Programs that import a graphics library themselves, such as `THAW.exe` and `pes2014.exe`, were never affected.

With that fix (app version 04.09, run-0174) `war3.exe` counted as drawing (`folder_dlls=1 last=Game.dll`), its launcher moved to the separate process, and the game ran in the title. It then said "Warcraft III was unable to initialize": the launcher handed it over with no working directory, so explorer started it in its own and the game found none of its `.mpq` files. Explorer now uses the program's own folder when the hand-over names none, and logs it as `PWLAUNCH ... dir=` ([patch-explorer-open.py](../tools/patch-explorer-open.py)). Not yet checked on the console.

A guest that ends now also closes the named mutexes and events that its own code created with `CreateMutexA/W` and `CreateEventA/W`, as it already closed its files (W206). Without that, Prince of Persia's launcher started again found the guest copy's `POP_Launcher` and said the game was running. Semaphores, the `...Ex` variants and `OpenMutex`/`OpenEvent` are not tracked.

## Direct3D in the separate process

Launchers often test the graphics card. Prince of Persia's runs Ubisoft's detection (`detectionapi.dll`, `directx8tests.dll`, `directx9tests.dll`). In the separate process Direct3D 8/9 use wined3d's `no3d` adapter: `WINE_D3D_CONFIG=renderer=no3d` and builtin d3d8, d3d9, ddraw, dxgi, d3d10core and d3d11 (`native/pop_wine_child.c`). That adapter answers without the GPU. `/data/orbisdesk/process-p014/gpu-probe` disables it.

The detection then sees an adapter without formats. Prince of Persia's launcher writes that into `Hardware.ini`, and `POP.exe` stops with *Unable to find a display mode*. A `Hardware.ini` with real values, made read-only, avoids it until the detection can see the title's GPU.

## Ending a game from the overlay

A game ended by the overlay's Salir does not release its DirectInput devices. dinput's thread is process-wide in explorer (W281). Its low-level hook and its 8 ms pad polling kept the controller in game mode, so the desktop looked frozen. The thread now releases, every 500 ms, the devices whose cooperative window is gone (`tools/build-dinput-hw.py`, `PWINPUT ... released`).

## A game's own display mode

win32u keeps the last display mode a game set below the desktop size (`pw_mode_set_width/height`, `tools/build-win32u-ps4.py`). The highest shown window that covers that mode from 0,0, with at most 64 pixels of frame more, is shown full screen and scaled, topmost windows included. For Prince of Persia's DXVK window the monitor rectangle the driver read stayed at 1280x720, and its launcher's window lay above the game, so the W248 rule did not apply (`PWSINK fullscreen on ... 800x600 of 1280x720`).

## What the Wine PRX needed on this console

Each item was found on hardware. The comment next to the code gives the run and the reason.

- **Loading.** The loader only copies an image: no imports, no TLS, no initialisers. Wine is therefore a fake-signed PRX loaded with `dlopen`. musl's `__init_libc` is called by hand, because a PRX never runs `crt1`.
- **Fixed base.** The borrowed system process has its eboot at `0x400000–0x588000`. That code never runs again, and its regions are unmapped before Wine starts.
- **Shared page.** With 16 KiB pages, ntdll's syscall-dispatcher slot (`0x7ffe1000`) shares a host page with the shared `KUSER_SHARED_DATA` view. A second process overwrote the title's dispatcher, and explorer then jumped into the other process's ntdll. In the separate process that page is private and refreshed from the shared view every 15 ms.
- **Desktop lifetime.** The server closes a desktop when only the desktop owner's threads remain. The separate process makes itself a Wine *system* process right after joining, so its exit leaves the title's desktop open.
- **Desktop name.** `ProcessParameters->Desktop` is set to `WinSta0\shell` before ntdll copies the parameters for a 32-bit image. Every program therefore lands on the title's desktop.
- **PE32.** The CPU is `wow64native.dll` with `PW_NATIVE_SIGNALS=1`, as in the title.
- **Waits** use the kernel's `poll` instead of a `sceNetEpoll` per call. The reason is precautionary: the title aborted at boot inside `sceNetEpollControl` after child sessions, until a reboot. The cause was not proven.
- **Process exit.** An assertion ends the process with `_exit`. Wine handles `SIGABRT`, and asserting children used to stay hung.

## Build and deploy

```sh
python3 tools/build-wine-hardware.py --runtime-outside-package   # the title (its link command feeds the PRX)
python3 tools/build-pop-wine-child.py                            # PRX, probe, child, test programs + manifest
python3 tools/upload-hardware.py --build W303 --host CONSOLE_IP --port 2121 --skip-runtime
python3 tools/upload-pop-separate.py --host CONSOLE_IP
```

`tools/build-guest-hw.py` and `tools/build-winecfg-hw.py` produce the kernelbase and winecfg that the title stages. If those change, the runtime copies under `/data/wine` and the prefix need updating as well. `/data/wine` belongs to the title's uid with mode 755. FTP can still change modes, so open a directory only for the upload and restore its mode afterwards.

Two GoldHEN FTP behaviours matter here. Overwriting a PRX in place kept the old one loaded, so delete it before storing the new one. `RETR` of a SELF/PRX returns the decrypted ELF, so verify by content and not by hash. `tools/upload-pop-separate.py` does both. The boot self-test runs only when `/data/orbisdesk/process-p014/selftest` exists.

## Limits

- **No GPU in the separate process.** RADV/GNM and VideoOut belong to the title, and loading the GNM driver in the second process faulted the kernel (D.4a). A Direct3D, OpenGL or Vulkan program cannot draw there. Drawing programs use the inverse route: they run in the title. Direct3D 8/9 answer through wined3d's `no3d` adapter, so a launcher's hardware detection sees no formats.
- **32-bit OpenGL uses Mesa.** In explorer's 32-bit world, Wine's builtin `opengl32` has no driver. D.4b's `ChoosePixelFormat` returned 0 with error 203. From W264 Mesa i386 (Zink) was used when `C:\orbis\opengl32native.txt` existed; since alpha 2 it is the default, and `C:\orbis\opengl32builtin.txt` goes back to Wine's builtin. Direct3D 8/9 games can also use DXVK or wined3d.
- **Late 32-bit world.** In one session that had already run MangoJuice, a Unity game and WFM, the first 32-bit guest stopped with `c0000005` before its image was checked. The same test in a fresh session worked (`20261112T232131Z`, then `20261112T232400Z`). It has not been reproduced yet.
- **One window, always on top.** Only the top window of the separate process is shown, and it is drawn above every title window. z-order against the title, several windows and cursor shapes are not handled.
- **Stale cursor in the child.** Inside the separate process, `GetCursorPos` may return a stale point. That matters for menus and drags handled by the program itself.
- **Signals and suspension.** The server cannot signal or suspend a separate process's threads (`pw_wine_thread_kill` reaches only the title's own threads).
- **GoldHEN loader.** The title sends the resident loader through GoldHEN's BinLoader (D.7). With BinLoader disabled, a separate start fails.

Development history is in the comments next to each change, and in `native/pop_separate.h` (`P014`–`P021`).
