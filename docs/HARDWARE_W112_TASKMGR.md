<a id="w112-task-manager-performance-processes-y-end-task"></a>

# W112: Task Manager (Performance, Processes and End task)

[English](HARDWARE_W112_TASKMGR.md) | [Español](HARDWARE_W112_TASKMGR-es.md)

Status: packaged in W112 (APP_VER 02.11, along with the runtime DOS already synchronized) and uploaded with verified back reading: `/data/pkg/orbis-win-W112-a81c9325bbaf.pkg` (SHA-256 a81c9325bbaf8a1f4863dbe4010966bb8baae1f9638bcf673a485b748cfc8942). Report: reports/wine-hardware-w112/transfers/20261102T192004Z.json; 553 files, 549 present and 4 Up, no permit failure. It was erased by FTP the PKG W112 previous (b6809b7be979, up to 18:45Z without this arrangement): ELF It no longer coincided with the / data runtime. Physical evidence pending.

<a id="síntomas-informados"></a>


## Informed symptoms

- Performance: CPU and memory in 0, unadvanced graphics.
- Processes: empty.
- Applications ready well, but after End task the window closes and the row is left.

<a id="causas-código"></a>


## Causes (code)

1. `PerfDataRefresh` (programs/taskmgr/perfdata.c) consult, in order, TimeOfDay, Performance, FileCache and ProcessorPerformance, and makes `return` to any failure, before saving memory, times and list of processes. In ORBIS, `SystemProcessorPerformanceInformation` returned `STATUS_NOT_SUPPORTED` (ntdll/unix/system.c), so every soda died there: all in 0 and empty processes. In addition `IdleTime` was left in 0; with the 8 consultation resolved, the CPU would have been left 100% fixed.
2. The past that removed dead rows of Applications only ran within `AddOrUpdateHwnd`, that is, when another eligible window was listed. When the only application was closed, there was none and the line was left. The same past looked at the style of the listed window (`hWnd`) rather than the style of the row (`pAPLI->hWnd`).

<a id="cambios"></a>


## Changes

- `native/telemetry.c`: `pw_ps4_cpu_times` (title clock, getrusage SELF, initial affinity capacity), the same sources as the W104 HUD. Returns errno negative if a data is missing; It doesn't fill with zeros.
- `tools/build-telemetry-ps4.py`: in the copy of system.c, the class 8 in ORBIS fills one input per processor with `idle = wall − busy/capacidad`, `User = (busy−sys)/capacidad`, `Kernel = idle + sys/capacidad`; `IdleTime` of the class 2 is the sum. The Task Manager's percentage is `busy/(capacidad·wall)`, the same value as the HUD. If it fails, the class 8 returns `STATUS_NOT_SUPPORTED` with `ERR PWTASK`; Nothing is simulated.
- `tools/build-taskmgr-hw.py` (new, same method as build-explorer-hw.py): `ApplicationPageRemoveDead()` runs after each `EnumWindows`; is corrected `pAPLI->hWnd`. In perfdata.c each failed query leaves `ERR PWTASK <clase> status`, and a failure of Handle/Process no longer travels a buffer without data.
- `tools/build-wine-hardware.py`: copy `out/taskmgr-hw/taskmgr.exe` in `lib/wine/x86_64-windows` and `system32`, verifying hash and build; manifest `task_manager`.

Compilation: `out/taskmgr-hw/taskmgr.exe` sha256 9848b2a8cf534639b63bfa138e75cacf26f7ea20dd2ce886ec529c87fbf80725 (11 revisions, without warnings). `build/telemetry-ps4/system.o` sha256 e751f9bbaa2a7bd62cf17f1af06b0048c235fdedd2bacdc09bcac45642c33526; their warnings are the same as before (private classes outside the enum, no-use functions).

<a id="límites"></a>


## Limits

- The CPU is the process of the title (OrbisDesk), not the whole PS4.
- Guests share the scanning process: Processes shows processes of Wine, not each application. "End Process" over explorer ends the entire title.
- System cache and kernel memory are still in 0 (Wine nor are they calculated).

<a id="prueba-física-pendiente"></a>


## Physical test (pending)

```sh
python3 tools/build-wine-hardware.py --mangohud enabled
python3 tools/upload-hardware.py --build W112 --host 192.168.68.104 --timeout 60
python3 tools/fetch-hardware.py --build W112 --host 192.168.68.104
```

Open Task Manager with vkspin running: CPU similar to HUD and moving, physical memory, available and commit other than 0, moving graphics, Processes with explorer.exe. End task on glxgears: the row disappears in 1 - 2. In the log there should be `PWTASK ... status`; `fixme ... SYSTEM_CACHE_INFORMATION` should appear in each soda.

<a id="resultado-físico-20261102t192834z-logs-sin-confirmación-visual-todavía"></a>


## Physical result: 20261102T192834Z (logs, without visual confirmation yet)

- run- 0003: new taskmgr with the ELF of the previous PKG W112. It records 47 times `PWTASK SystemProcessorPerformanceInformation status c00000bb`: the new trace shows exactly the original cause (class 8 NOT_SUPPORTED). That ELF had no arrangement.
- run- 0004 (PKG a81c9325bbaf): taskmgr opened twice (003c and 0074 threads), zero `PWTASK`, 58 refreshments that go through the cache consultation without any flaw. During that session, glxgears (twice) and vkcube were opened and closed, all with 0 output; taskmgr closed with 0. PWTELEM: 6 cores, CPU of the title 28,9% in the comparable sample.
- The logs do not show what Performance drew or if the row disappeared after End task. The user then confirmed it: "Everything goes" (Performance with CPU and memory, graphics and End task). Agreement accepted for this scenario; the accuracy of the values was not measured.
