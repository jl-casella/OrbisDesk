# Release traces: one switch for alpha-1

[English](RELEASE_TRACES.md) | [Español](RELEASE_TRACES-es.md)

**Status:** the switch ran on the console in W299 (`W299 trace level=0 source=build release=1`). The second round (W299 log review) ran in W300: the release log went from 403 KB to 217 KB. The third round (W300: hang dumps) is in the sources, not yet in a W build. Alpha 2's own lines follow the switch from 04.37 (see [Alpha 2 lines](#alpha-2-lines)); not yet run on the console.

Alpha-1 is built for speed. Diagnostic traces are off by default, and one switch turns them back on without rebuilding. Build markers, real errors, crashes and exits are always logged. Turning traces off never turns a failure into a silent success.

## The switch

The header is [pw_trace.h](../platform/ps4/pw_trace.h). The hardware launcher, [wine_hardware.c](../native/wine_hardware.c), decides once, before Wine starts:

| Where | Value | Traces |
|---|---|---|
| Build | `ORBIS_RELEASE=1` (default) | off |
| Build | `-DORBIS_RELEASE=0` | on |
| Run: `/data/orbisdesk/trace.txt` | present and empty, or `1` | on (overrides the build) |
| Run: `/data/orbisdesk/trace.txt` | `0` | off (overrides the build) |

The run log records the decision: `Wnnn trace level=N source=build|trace.txt release=N`.

The launcher hands the answer to every layer:

- **Native side** (launcher, sink, pad, platform adapters): `pw_trace_on()`, which reads `pw_trace_level`. The variable is defined in [pw_wine_platform.c](../platform/ps4/pw_wine_platform.c).
- **Wine's Unix side** (ntdll, win32u, wineserver, audio driver), all in the same ELF: `pw_trace_enabled()`.
- **RADV's winsys** (Mesa, same ELF): the weak `pw_trace_level`, through [patch-crema-traces.py](../tools/vk-h0/patch-crema-traces.py).
- **Windows side** (explorer, kernelbase, wow64, the i386 ntdll, the 32-bit world host): the `PW_TRACE=0|1` variable.

Anything that links these objects without the hardware launcher keeps every trace, as before the switch. That covers fork and host diagnostics, and `wine_boot.c` alone. An unset `PW_TRACE` also counts as on.

The standalone S4 Steam title ([build-steam-s4.py](../tools/build-steam-s4.py)) links no OrbisDesk platform code, and the console's loader refuses an import that no eboot provides, even a weak one. Its build passes `-DPW_TRACE_DEFINE_LEVEL` to the one source that includes `pw_trace.h`, which then defines the level itself, with traces on.

`C:\orbis\winedebug.txt` still adds Wine debug channels in both modes. `C:\orbis\dxvkdebug.txt` still turns on DXVK's debug log for the 32-bit world.

## What changes without traces

- **Wine.** `WINEDEBUG=fixme-all,warn+module`: Wine's errors, plus DLLs that fail to load or initialise. With traces, the earlier channels come back: `trace+seh`, `trace+loaddll`, `warn+debugstr`, and the extra channels for 32-bit programs.
- **DXVK.** `DXVK_LOG_PATH=none`, level `error`; `warn` with traces. Unset, DXVK wrote `<exe>_d3d9.log` and similar files into the game's own folder.
- **Video output.** No BMP frame dumps, and no periodic frame lines or timing. The first 8 `PWBOOT frame_presented` lines stay: [fetch-hardware.py](../tools/fetch-hardware.py) uses them to classify a run as `presented`.
- **32-bit programs.**
  - wow64 no longer reads the clock around every system call. That measurement only existed for the W272 wait lines.
  - The per-DLL line for each new thread is only built with `-DORBIS_RELEASE=0`.
- **Lines that repeat during a session, now traced only:**
  - presents per second, telemetry samples
  - pointer moves, window flush statistics, slow-wait reports
  - late server timers
  - per-entry directory listings
  - successful deletes and renames, successful name lookups
  - explorer's shell clock, the audio mixer and level reports
  - the first input events
  - the launcher's platform probes
  - a PE image read in place of a mapping (`PWBOOT image_read_fallback`) when the whole image was read, and a DLL placed away from the server's base (`image_map_addr_unavailable`)
  - the 32-bit world's thread lines (`PWWOW ... thread_init`, `loader_init`, `ends`) and the Vulkan begin/end lines of 32-bit programs (`PWVK32`); a failed Vulkan call still logs
  - a guest's per-DLL `system_module` lines (the `system_modules` summary and `system_unloaded` stay), and the `exit_caller` stack words of a guest that exits with status 0
  - RADV: the per-device startup lines, the first 40 and every 1000th submission, the verbose mapping lines and its startup trace points; a failed check or step, a refused submission, hangs and GPU faults still log
- **Rate-limited and still always logged:**
  - wined3d's GDI present (8-bit swapchains): the first 4, then one in 1000;
  - a failing audio port: the first 8, then one in 1000.
- **Logged on change.** `GetLogicalDrives` (`PWFS logical_drives`) logs its first answer and each change, not every call.
- **Hang dumps.** A `PWHUNG` or a stopped shell logs one line, and the full thread dump becomes one summary line, `PWDUMP skipped age_ms=N threads=N loader_owner=N`. The full dump comes back with traces, or on request through `C:\orbis\dumpnow.txt`. In W300 four full dumps of 37 threads were 70% of the log, for a game that was loading, not hung.
- **Logged once.** RADV wrote each line both to stderr and to the console debug output, and the launcher logs both; it now writes stderr only.

## Alpha 2 lines

Alpha 2 (04.23–04.36) added log lines for the shader cache, frame generation, FPS LIMIT, the overlay, guest memory release, SeaMonkey and the desktop background. From 04.37 they follow the same switch. To see them in a run, create `/data/orbisdesk/trace.txt` (empty, or `1`) before starting OrbisDesk. `0` or no file means release behaviour. No rebuild is needed.

Three opt-in markers predate this and stay separate: `/data/orbisdesk/framegen.txt` (frame generation's timing lines), `C:\orbis\nativeprofile.txt` (wow64native's per-thread profile) and `C:\orbis\vkbatch32.off`. They do not depend on the switch.

**Traced only from 04.37:**

- **Shader cache and frame time.** `PWPERF` (the 5 s window line and `slow_compile`). Without traces nothing is measured: the sink returns before its counters.
- **FPS LIMIT.** The 5 s `PWFPS limit=… presents=…` report, `PWFPS vblank count trusted|not trusted` and `PWFPS auto cap`.
- **Frame generation.** The 10 s `PWFG display pairs=…` report, `PWFG display on|off`, `PWFG shown_rate`, `PWFG gpu_us` (every 120 generated frames), the start-up probes (`PWFG probe …`, `PWFG buffers`), `PWFG target sc=` and the first copy lines.
- **Overlay.** `PWOVERLAY open|close|keyboard|stats=`, the MangoHud key lines, `PWOVERLAY mangohud|desktop in_front` (native and kernelbase), `PWOVERLAY program … bits`, `PWOVERLAY hud:` (the MangoHud.conf summary), `PWOVERLAY keymap program=`, `PWOVERLAY render set … requested`, `PWOVERLAY exit taken by the closer`, and `PWOVERLAY control wait` when the pad became ready.
- **Guest memory release** (kernelbase and win32u). `PWGUEST heap_usage`, `heap_large`, `heap_small`, `heap_unowned`, the `kept bytes … from` lists, `heaps … claimed`, `heap … kept: held by`, `PWGUEST vulkan module=… devices=`, `PWGUEST gl module=… result=`, `PWVK guest_memory`, `PWVK guest_release`, `PWVK guest_teardown … ms=`, and `PWAUDIO guest …: N streams out of the mixer`.
- **Guest lifecycle detail.** `PWGUEST thread_new`, `thread_starts`, `ended: thread`, `class … unregistered`, `ilonly entry`, `mangohud excluded`.
- **Windows and graphics.** `PWVK size`, `PWVK layer`, `PWRECT`, `PWSINK monitor`, `PWSINK fullscreen off|not|image`, `PWINPUT warp`, and Mesa WGL's `PWGL viewport` and `PWSTW size` (both appear in the log as `MESA: error:`).
- **Desktop background.** `PWDESK wallpaper menu`, `PWDESK background open|apply`; `render` and `browse` only when they succeed.
- **Video.** `PWAVI open` and the per-stream description, `first_sample`, `eos`, and `stopped` when it stopped cleanly.
- **Platform and Wine's Unix side.** `PWFS descriptor_growth`, `PWMEM direct_free source=` switches, `PWIPC request_chunked`, `PWSERVER request_deferred`, `PWLOAD shared_section_private` after a full copy, and RADV's `device … gave back N bytes` lines.

**Kept in release, and why:**

- Every line that reports a failure, a refusal or something kept. Examples: `PWFG failed …`, `PWFG off for this run`, `PWFG generator off for this run`, `PWOVERLAY … not saved`, `… refused`, `config line ignored`, `PWGUEST … release failed`, `heaps not recorded`, `kept: … more than listed`, `PWVK guest_teardown … kept`, `PWAVI stream … not offered|unreadable`, `PWAVI reject`, `PWFS lock_failed`, `PWDESK background apply … error|refused`, and RADV's `ended with submissions unfinished`. These are what a field report needs, and they cost nothing while nothing fails.
- **Settings the user changed, once per change.** `PWOVERLAY framegen=`, `fpslimit=`, `control type=`, `control pad.…=`, `render … program=`, `keymap saved`, `PWFG mode=`, `PWFPS limit=… cap=`, and `PWPAD profile=… reload`. A crash report needs to know what was on.
- **The exit path.** `PWOVERLAY exit requested|title|result`, and the "no answer from the closer" lines. They are rare, and are the last lines before a title closes.
- **A pad that did not become ready.** `PWOVERLAY control wait … ready=0`.
- **One-time startup state.** `PWFG config`, `PWFG ready`, `PWFG no present hook`, `PWTELEM framegen query`, `PWHID dualsense unavailable`, `PWNET kernel_poll`, `PWBOOT memory_info`, `PWINSTALL plan`, `PWCACHE radv disk_cache=` and `address32_hi`. `PWCACHE` stays because its Mesa patch keeps its marker on an existing source tree; it is one line per device.
- **Rare anomalies.** `PWGUEST leftover thread`, `own_modules … kept`, `PWWOW tls_slot`, `PWSINK mode kept|restore`, `PWFONT`, `PWWOW win32u`, `PWCRT`, `PWTOP`, and the guest `fault` lines.
- **Process separation and launch.** `PWSEP …`, `PWOPEN …`, `PWLAUNCH`: one line per launch decision, needed when a game does not start.
- **Network, HID and DirectInput.** `PWNSI` (one notice per run, one line per console network change), `PWHID winebus unlink again ignored` and `PWINPUT device … gone: released`. Each is rare and points at a real event.

Three things are unchanged: `PW_NATIVE_PROFILE` stays opt-in through `nativeprofile.txt`; `PW_VK_BATCH` turns batching on and is not a trace; and the MangoHud `PWHUD` debug string only appears with Wine's `warn+debugstr` channel.

## Always logged

- launcher `Wnnn` markers
- the `PWBOOT` milestones the loading screen and the evidence tools read (`server_ready`, `static_unixlib ...win32u.so`, `gpu_layers=`, `frame_presented`)
- crash and exit records, `PWNATIVE lost signal`, `PWFAULT`
- hang reports (`PWHUNG`, the `PWDUMP` summary, `PWLOCK`, `PWSERVER stuck`)
- every failure line

## Not yet covered

- **Steam client.** It flushes its log to storage after every line except the install's progress line without traces (W299).
- **The MangoHud HUD.** It is shown by default. Setting `MANGOHUD=0` would not load the layer at all, so the overlay's STATISTICS toggle could not show it.
- **`C:\orbis\dxvkdebug.txt`.** A leftover copy on the console turned DXVK's debug log on in W299; it is a manual override, removed from the console.
- **A full-screen game that does not pump messages.** While it loads or plays a video, Wine reports its window hung and `PWHUNG` logs it. A possible improvement is to skip the report while the program still presents Vulkan frames. The native side already counts presents. Not done for alpha-1.
- **wined3d's `validate_state_table` errors.** Upstream consistency reports at device creation, left as they are.

These are listed as follow-ups.
