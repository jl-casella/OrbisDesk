<a id="evidencia-y-bloqueos"></a>


# Evidence and blockages

[English](STATUS.md) | [Español](STATUS-es.md)

## Current status, 2026-11-10

The product base is **W303 / 04.02**, with the runtime embedded in `OrbisDesk.pkg` and clean-install console validation recorded in commit `208803d`. The complete GitHub-hosted product build now succeeds. CI assigns the candidate's SFO version separately from the local default.

Use [current state](CURRENT_STATE.md) for the handoff and [product builds and releases](RELEASES.md) for the verified cache/prebuilt flow, installation and candidate checks. Installation, desktop/application behavior and publication are separate acceptance steps; use the exact candidate's SHA, manifests and logs.

## Historical evidence through W284

At the W284 handoff, the local package was **OrbisDesk.pkg**, W284 / 03.83, with installation and visual testing pending. See [W284](HARDWARE_W284.md). The entries below retain the status reported at each historical date.


**Delivery W283 completed:** `/data/pkg/orbisdesk-W283-a3a72e1401c2.pkg`, FTP 192.168.68.100:2121. PKG and 1.823 runtime files verified by reading (83 uploaded, 1.740 already present); a previous package removed after verification. No permission failures. Console settings preserved. Installation and physical testing pending. Evidence: `reports/wine-hardware-w283/transfers/20261107T142853Z.json`.

Current mark: **OrbisDesk**, W283 / 03.82. Built and verified package; installation and physical testing pending. See [current recovery](CURRENT_STATE.md) and [change of name](REBRANDING_ORBISDESK.md). The following entries are historical.

Updated handoff to 2026-11-03: **W188 (02.87)** is up and verified; His physical evidence is still pending in the local evidence. First consult [CURRENT_STATE](CURRENT_STATE.md) and [W188](HARDWARE_W188.md). The following W112 and lower content is historical and does not define the next build.

Status updated to 2026-11-02: consult [CURRENT_STATE](CURRENT_STATE.md). W105 list drives/files and W106 open EXE without reboot, depending on the user. W107 has already opened texts with Notepad. Priority chosen: support DOS. [W112](HARDWARE_W112.md) integrates DOSBox Pure PE64, front GDI and AudioOut; completed compilation, compatibility and audio in PS4 pending. Previous correction: [W111](HARDWARE_W111.md), deleted entry records: W110 list names with stat ENOENT, also non-existent by FTP. The zero-inode BSD filter has already been validated in PS4: rmdir 0, folder absent and rename with confirmed spaces. The user also confirmed the complete deletion of the tree with active content; physical acceptance recorded by explicit feedback, without attributing new erases to the log. Next priority chosen: DOS; desk postponed. After: desktop with files/folders in addition to * .lnk. Calibration CPU/GPU deferred. W096 has already run three graphic applications together in PS4 and closed them with 0; Start stopped opening later. W099 complete closures and recharges, but after another cycle there is invalid access in native malloc. W100 adds a common block to the SDK, but the physical test also ends with CE-34878-0. W101 completed two cycles without loading MangoHud and final output 0. W102 reactivate the layer with sampling in the frame and completed two cycles with the loaded layer: six closures 0, Operating start and end output 0 (63455 ms). Evidence in `reports/wine-hardware-w102/physical/20261102T131731Z/acceptance.json`. W103 recorded three closures 0 and GPU loss-free variable; CPU was fixed at 16,666 % and was rejected. [W104](HARDWARE_W104.md) replace its source with getrusage and remove "app" from the labels CPU/GPU. Keep the sampling in the frame. In PS4: 90 samples, CPU 6,917–32,801 %, GPU 0,08–9,5 %, no errors or losses GPU and three closures 0. The defect of CPU fixed is resolved in this session; independent calibration and two complete cycles not accredited. The details of recent iterations are in [HARDWARE_G001](HARDWARE_G001.md) and [HARDWARE_W003_W011](HARDWARE_W003_W011.md). Previous campaigns that continue to preserve their historical results and blockages.

Hardtrack: [H001](HARDWARE_H001.md) executed in the user's PS4 Pro Baikal (informed firmware 12.52, GoldHEN). Pass VideoOut, log, roundtrip in `/data`, protection R/RW, reserve under 4 GiB and TLS/threads. Read `/app0/sce_sys/param.sfo` returns ENOENT (2; does not demonstrate a general failure of APP0. H001B, version 01.01, uses an asset of its own for that check and records the SFO separately as an optional metadata. H001B also passed on the console, including reading APP0 (`reports/hardware-h001b/physical/20261031T051942Z/`).

[W001](HARDWARE_W001.md), the first start of Wine on the console (`console32-bare.exe` by wowprospero), is up with its runtime: 430 files and 294 MB in `/data`, all verified by reading back. In the console it remained `blocked` before starting Wine: `readlink` returns ENOSYS (78) and `dup2` return - 1. The `dosdevices` links of the prefix do not exist in the hardware.

With W002 - W013 ([W002](HARDWARE_W002.md), [W003–W013](HARDWARE_W003_W011.md)), **`console32-bare.exe` run in the real PS4 by Wine and wowprospero.** W013 left a `result.txt` identical to that of Windows (`sum=500500;thread=ok;dll=ok`, same SHA- 256) and went out with 0.
- Evidence: `reports/wine-hardware-w013/physical/20261031T195509Z/`.
- Runs: two, both `passed` with the same hash. The second one is in `reports/wine-hardware-w013/physical/20261031T195721Z/`.
- It was possible thanks to documented platform decisions for what a retail app cannot do:
  - without symbolic links;
  - `lstat` with EPERM;
  - `dup` with EPERM;
  - `fcntl` with EINVAL.
- W013 ended with SIGSYS in the `_exit` of libkernel. W014 close the app with `sceSystemServiceLoadExec("exit")`. Your log ends up clean, without signals or `err:seh`, and according to the user the app returns to the menu without the error CE-34878-0 (`reports/wine-hardware-w014/physical/20261031T204439Z/`, `passed`).
- **GUI on the console** ([detalle](HARDWARE_W003_W011.md)): `gui-window64.exe` (PE64 open your window, paint it and read a pixel. Its `result.txt` is identical to that of Windows.
  - W023: two out of two. W025: with correct text.
  - This required three platform decisions on memory:
    - do not reserve the area `0x7ffffe000000-0x7fffffff0000`;
    - let the kernel choose the virtual heap;
    - cut `host_addr_space_limit` to `0xfc00000000`.
  - The FreeType adapter now opens the files by the assembly table. From W025 the title is drawn in Tahoma Bold and the buttons, with Marlett.
- Pending:
  - entry (control);
  - The text already works: `gui-text64.exe` passed in W026, with the same ink as in the fork.
  - Explore shows on the console the desktop of 1280 × 720 with the task bar, in about 5.
  - From W035 the Start menu is opened with the USB mouse or control buttons. The USB keyboard also reaches Wine.
  - That was what it took:
    - `native/hw_pad.c`;
    - a real `dup` by SCM_RIGHTS;
    - that `pw_wine_poll` accept descriptors without events.
  - The left stick, touchpad and control buttons (W037, confirmed by the user, work. The right stick is not assigned.
  - "Exit desktop" closes the title with output 0.
  - non-blocking sockets (EACCES);
  - The Linux matrix passes with ELF of W038 (`reports/wine-hardware-w038/regressions-25/`). He failed with the memory cap of W023, which shadPS4 does not support; W038 it's down to `0x7ffff0000`.

Most recent state: [increment 25](INCREMENT_25.md). FreeType 2.14.1 is linked to Orbis, with Tahoma of the fixed review of Wine and explicit record in the private prefix. The text fixture PE64 passes three out of three runs: 1.252 ink pixels both in the DIB and in the window, and verification of the picture presented. Explorer sample Start (77 tested label pixels). The protection of private final sections of DLL was corrected to rounding to the range of 16 KiB already mapped. The acceptance campaign and the regressions pass; evidence in `reports/increment25-accepted/`. No patches were added to the emulator. Entry, GUI PE32 and hardware: pending; The official emulator's still locked.

Timely tracking: it is packed and also records Marlett of Wine. A graphical fixture Runs in the fork confirms the icons to minimize, maximize and close; output 0. Capture and report in `reports/marlett-caption/`. The full suite was not repeated.

Status of increment 24: [increment 24](INCREMENT_24.md). In the fork Linux, Wine presents windows for `sceVideoOut` with `win32u` and a driver of the user in process. A 64 bit GUI fixture gives the same result as Windows in three of three runs, and `explorer.exe /desktop` shows the desktop with its taskbar. No text (no FreeType) or input. The official emulator's still locked. Hardware: pending.

Status of increment 23: [increment 23](INCREMENT_23.md). In the fork Linux, console32-bare.exe runs by Wine with the translator as a provider WoW64 (`--wow64-cpu wowprospero`): `result.txt` identical to Windows, output 0, three of three runs and without stubs. The official emulator is still blocked; console32.exe with CRT by Wine is pending. Hardware: pending.

Status of increment 22: [increment 22](INCREMENT_22.md). In the fork Linux pass GS by thread (`--gs-services`), the signal contexts (`--signal-services`) and `segments`. Wine execute ntdll PE64, create heap and load `wow64.dll`; ends with `0xc0000135` because the provider of CPU WoW64 is missing. EXE is not yet executed by Wine. `exceptions` the same failure in the fork and the official emulator Linux (difference from the host). Hardware: pending.

Status of increment 21: [increment 21](INCREMENT_21.md). Private file mappings and protection denials in the fork Linux pass. Wine reaches ntdll_pe64_ready, entering_windows_initialization and dispatcher_slot_ready. The syscall slot is adapted to pages of 16 KiB. The following block is to install and verify GS by sysarch: clean output 93, without assertion or timeout. EXE is not yet run by Wine. Hardware: pending.

Status of increment 20: [increment 20](INCREMENT_20.md). The fork returns EINVAL for invalid offsets of mmap; Wine take the fallback and map the EXE PE32. The policy of relocated images of prospero-win and is strong WoW64. The load of ntdll PE64 find an assertion of mprotect, reproduced separately. Initialization Windows and the implementation of the EXE by Wine They're still pending. Hardware: pending.

Status of increment 19: [increment 19](INCREMENT_19.md). The 12 tests of the external prefix are passed in the fork Linux. Wine consumes that prefix without throwing wineboot, but the load of the EXE is blocked in an assertion of mmap with non-aligned offset. The load of ntdll PE64 was not completed and the EXE was not executed by Wine. The recressions of the increment 18 are preserved. Hardware: pending.

Status of increment 18: [increment 18](INCREMENT_18.md). console32.exe, with the CRT of mingw, run without Wine in the fork Linux over a kernel32 and a msvcrt minimum of its own, with the same output as in Windows. The official emulator is blocked by the emulator. Hardware: pending.

Status of increment 17: [increment 17](INCREMENT_17.md). lifecycle-host.exe load and download DLL from disk without Wine in the fork Linux and it comes out with 42, as in Windows. The official emulator is blocked by the emulator. Hardware: pending.

Status of increment 16: [increment 16](INCREMENT_16.md). console32-bare.exe runs without Wine in the fork Linux, with the loader PE32 own and a kernel32 minimum; its output is equal to that of Windows. The official emulator is blocked by the emulator. Hardware: pending.

Status of increment 15: [increment 15](INCREMENT_15.md). They pass the identity of files and symbols in the fork. An external prefix initialized and verified with Wine native is packed; The execution of the EXE by Wine in shadPS4 is still pending.

Status of increment 14: [increment 14](INCREMENT_14.md). The directory adapters PS4 are passed; the attempt to launch wineboot is confirmed and rejected.

Status of increment 13: [increment 13](INCREMENT_13.md). They work in Linux; Wine complete server_init_process. The execution of the EXE is still blocked after the handshake by outstanding imports, with GS, I prefer and WoW64 still to be solved.

Status of increment 12: [increment 12](INCREMENT_12.md). SCM_RIGHTS is already tested with files and sockets in the fork Linux. The next start block is pipe; the above results are kept as a record.

Status of increment 11: [increment 11](INCREMENT_11.md). The fork Linux verifies dup, lags per descriptor and messages with several buffers. The complete start is still blocked in the `SCM_RIGHTS` transfer; GS and the provider WoW64 are also still pending. The following matrix retains historical results.

This document describes the initial reference. For further work and extended matrices, see [increment 1](INCREMENT_01.md) e [increment 2: TEB and hostexec](INCREMENT_02.md) e [increment 3: common dispatcher](INCREMENT_03.md) e [increment 4: first PE32](INCREMENT_04.md) e [increment 5: sections of 4 KiB](INCREMENT_05.md) e [increment 6: DLL e IAT](INCREMENT_06.md) e [increment 7: initialization and TLS](INCREMENT_07.md) e [8 increment: process and bring-up of Wine](INCREMENT_08.md) e [increment 9: memory and files Wine Unix](INCREMENT_09.md) e [increment 10: complete link and partial start](INCREMENT_10.md).

<a id="entorno"></a>

## Environment

Tests carried out on October 29 of 2026 in Windows and Ubuntu 22.04 low WSL. OpenOrbis v0. 5.4 Clang/LLD 14; MinGW i686. The official binary of shadPS4 v0. 20.0 reports the commitment `529ceb32f5546b820588f194b903cc39d08015fe`. The reference checkout of your source `main` has another review, recorded separately in `sources.lock.json`. You must not be confused.

<a id="matriz"></a>

## Matrix

|Test|Guest result in shadPS4 official|
|---|---|
| `files` |Read, write, seek, close and delete correct|
| `low-memory` |Book at `0x20000000`, low 4 GiB|
| `reserve-collision` |The second reservation is rejected and it retains the content|
| `vm-backend` |Accurate reservation, commit, collision, RW → R → RW and correct release|
| `generated-code` |Blocking when changing RW → RX, before running|
| `generated-rwx` |Code generated return 42|
| `threads` |Locked by real call to stub POSIX `pthread_key_delete`|
| `threads-adapter` |Two threads, 2000 increments, TLS independent and two destroyers; deleted with ScePthread|
| `exceptions` |SIGSEGV recovered; RIP on offset 224; return `0x5a5a`|
| `segments` |Blocked by stub of `sysarch`; outputs remain intact|
| `translator` | Bloqueo RW→RX |
| `translator-rwx` |Real upstream translator runs `mov eax,7; add eax,35`|

All the tests that reach `return 0` also show the limitation of the emulator closure. The above approval corresponds to the behaviour measured by each test, not to a clean closure or to the overall operation of Wine.

<a id="bloqueos-concretos"></a>


## Specific blocks

<a id="fsgs-para-wine"></a>


### FS/GS for Wine

Reproduction: `./tools/run-probes.ps1 -Cases segments`.

The import `sysarch` (`b7uXQmnfB2s`) is resolved at CommonStub. The operations AMD64_GET_FSBASE and AMD64_GET_GSBASE return zero without changing the output values `UINTPTR_MAX`. The runner detects the invocation and classifies it as blocked. A host syscall is not run to try to circumvent it.

This prevents validation of the TEB/GS route using the PS5 port. It requires work of emulation by thread, preserving the GS used by Windows and the translation of TLS of shadPS4. A function that only saves a variable with the new GS does not set the semantic of access to memory of the instructions PE64.

Subsequent state, separated by emulator (increment 22):

- **Fork Linux**: solved. The guest's TCB stops using the base GS (patch 0011) and `sysarch` serves GET_FSBASE, GET_GSBASE and SET_GSBASE (patch 0012). `segments` and `--gs-services` pass, with real readings `gs:`, between threads and TLS native preserved.
- **shadPS4 official**: remains blocked by stub.
- **Host Windows**: no change or validation; GS is the TEB of the process itself.

<a id="cambios-de-protección-ejecutable-en-windows"></a>


### Executable protection changes in Windows

Reproduction: `./tools/run-probes.ps1 -Cases generated-code,generated-rwx`.

The same flexible allocation class allows execution if created with RWX. If created with RW and then ordered RX, the emulator aborts in `AddressSpace::Protect`, with the error of Windows "The parameter is incorrect." It is an independent reproduction of Wine. It does not show that PS4 real has this failure.

RWX allows you to test the DBT; does not automatically solve the image and memory protection changes you will need Wine. Not replaced mprotect for a simulated success, nor was an exception added for this title to the emulator.

<a id="tls-y-cierre"></a>


### TLS and closing

`pthread_key_delete` is not registered for the import of libkernel used by OpenOrbis, although the API `scePthreadKeyDelete` is available. The PS4 adapter calls the latter and normalizes its error code; retains the original POSIX test as a reproduction of the problem.

The guest's `exit(0)` comes to an assertion of `process.cpp` in the emulator. The report retains the actual host process code and labels it `guest-zero-exit-traps-in-emulator`; It doesn't present it as a clean closure.

<a id="estado-de-los-hitos-de-la-referencia-inicial-histórico"></a>


## Status of the milestones of the initial (historical) reference

1. Diagnosis: implemented and implemented; there are reproductable platform blocks.
2. Wine Unix, server and modules: pending; integration blocked by the border FS/GS.
3. PE32 complete: compiled fixtures; EXE not yet executed on the runtime PS4.
4. GDI, control and audio: fixture GDI compiled; presentation adapters still pending.
5. Vulkan/DXVK: fixed references; not built or tested.

DBT integer tests do not cover x87/SSE, code automation, calls Win32, DLL loading or WoW64. The initial backend uses flexible memory: there is a lack of accounting and direct memory for large loads. There is no hardware validation or performance or game compatibility statements.
