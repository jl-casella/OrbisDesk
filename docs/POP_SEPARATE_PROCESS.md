# Separate Windows processes (PoP phases B–D)

[English](POP_SEPARATE_PROCESS.md) | [Español](POP_SEPARATE_PROCESS-es.md)

OrbisDesk runs every Windows program inside one PS4 title process. That model fails for a launcher and a game that both need the same fixed image base. Prince of Persia's launcher and `POP.exe` both use `0x400000`. This document records how a program marked **Separate processes** in winecfg now runs in a second native process. That process runs Wine as a client of the title's wineserver, with the title's desktop, registry and object namespace.

The research substrate (phase A, the GoldHEN loader and its scheduler fix) is in [Process-family probes](PROCESS_FAMILY_PROBES.md). OrbisDesk targets GoldHEN consoles, so the resident loader is a stated requirement and not a blocker. It still has to be sent again after every console reboot.

## What works on hardware (PS4 Pro, 12.50, ROOT boot, 2026-11-12)

| Phase | Result | Evidence (`reports/pop-phase-b/physical/`) |
| --- | --- | --- |
| B.1 | A loader-started process connects to the title's wineserver, registers (version 961), and creates `\KernelObjects\OrbisSeparateJoin` in the shared namespace | `20261112T032514Z` |
| C | That process creates a window on the title's desktop through raw wineserver requests. It receives mouse input, and the title composites its pixels | `20261112T085655Z` |
| D.1 | Wine itself runs in that process. A console PE64 program linked at `0x400000` loads there unrelocated and exits with 42. Three title boots in a row are stable | `20261112T130124Z` |
| D.2 | A GDI program's window appears on the desktop. It takes clicks, keys and drags, and the desktop stays open when it exits | `20261112T132927Z` |
| D.3 | `separate_launcher.exe` runs inside the title at `0x400000`. It calls `CreateProcess` on `separate_game.exe`, which is marked separate and also linked at `0x400000`, and the game runs in the second process. The launcher gets real handles and the game's exit code 44. The game gets 8 clicks and 11 keys | `20261112T141146Z`, `20261112T150746Z` |

These results cover the configurations named here only. They do not show general application compatibility. The separate process has no GPU of its own (see *Limits*).

## How a launch flows

1. **kernelbase.** `CreateProcessInternalW` sees execution mode `separate` for the image. Its generator is `tools/build-guest-hw.py`. It writes `/data/orbisdesk/process-p014/spawn-request` with four lines: a token, the image, the command line and the current directory. It then waits up to 30 s for `started-<token>`.
2. **Title watcher.** `native/pop_loader_spawn.h` turns the request into the child's job. It then sends `/data/orbisdesk/pop-wine-join.elf` to the resident loader on port 9021.
3. **Payload-SDK child.** `native/process_p014_child.c` takes the title's uid and loads `pop-wine-child.prx` with `dlopen`, so the system linker resolves its imports, TLS and initialisers. It connects to the title's bridge socket and calls `pop_wine_child_run_job`.
4. **Wine PRX.** `native/pop_wine_child.c` sets `WINESERVERSOCKET` to the bridge descriptor and calls `__wine_main`. ntdll then joins the title's server instead of starting one. Once joined, the process writes `pid tid` under the token, and kernelbase opens real process and thread handles for the caller.
5. **Display.** The child's win32u driver hands its window stack to `native/pop_child_sink.c`, which never opens VideoOut. The sink sends the top window and its handle over `surface.sock`. The title composites the frame at the window's rectangle. A pointer over that rectangle is delivered to that window by handle (`pw_hw_separate_window`, `tools/build-win32u-ps4.py`).

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

- **No Direct3D yet.** RADV/GNM and VideoOut belong to the title. A Direct3D or Vulkan program in the separate process cannot render. Prince of Persia therefore still needs a graphics path, either GPU access in the second process or frames sent to the title.
- **One window, always on top.** Only the top window of the separate process is shown, and it is drawn above every title window. z-order against the title, several windows and cursor shapes are not handled.
- **Stale cursor in the child.** Inside the separate process, `GetCursorPos` may return a stale point. That matters for menus and drags handled by the program itself.
- **Signals and suspension.** The server cannot signal or suspend a separate process's threads (`pw_wine_thread_kill` reaches only the title's own threads).
- **GoldHEN loader.** The resident loader must be sent again after each console reboot.

Development history is in the comments next to each change, and in `native/pop_separate.h` (`P014`–`P019`).
