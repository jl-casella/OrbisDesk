# OrbisDesk

[English](README.md) | [Español](README-es.md)

Documentation: [language policy](docs/DOCUMENTATION_POLICY.md).

Git preparation: [dependencies and reconstruction](docs/REPOSITORY_LAYOUT.md).

Start with AI: [development guide](AGENTS.md) and [complete documentation index](docs/INDEX.md).

Windows desktop and applications for PS4, based on Wine, WoW64 and native graphics.
Since W283, the interface, packages and project code use the OrbisDesk name.
See [renaming and compatibility](docs/REBRANDING_ORBISDESK.md).

**Current status, 2026-11-07: OrbisDesk** built as `OrbisDesk.pkg` (W284).
The version is visible only in the normal/root selector. See [clean package naming](docs/HARDWARE_W284.md).
The rename covers code, interface, documentation and packages; PS4 identifiers are
preserved so the existing installation can be updated. Steam S1/S2 have also been
rebuilt. See [current state](docs/CURRENT_STATE.md) and
[rename verification](docs/REBRANDING_ORBISDESK.md).
The earlier build statuses retained below are historical.

Experimental base for porting prospero-win to PS4 and measuring its requirements in shadPS4.
**It already runs a PE32 EXE that calls a project DLL through its IAT in the local
shadPS4 fork**, returning 42 with verified relocations. The ELF incorporates the
actual prospero-win x86 translator and PS4 memory, TLS and process adapters.
Actual Wine PE32 DLLs are built. In the Linux fork, Wine starts inside the process
and runs console32-bare.exe with the translator as its WoW64 provider (increment 23);
the official emulator remains blocked in that historical campaign. Later validation
on physical PS4 hardware is detailed below.

<a id="estado-verificado"></a>

## Verified State

Current iteration: [W112](docs/HARDWARE_W112.md), first runtime DOSBox Pure PE64 for games DOS from WFM; compiled, physical validation pending. The core, front, bridge AudioOut and sources travel with distribution, without games.

W105 list units and files in WFM. Previous correction: [W111](docs/HARDWARE_W111.md), filter BSD records of deleted inputs that produce residual names and error 145 when checking empty folders. In PS4 actual rmdir, missing and renamed folder with spaces were already verified. The user also confirmed the complete deletion of the tree with active content. W106 opens EXE and W107 already opened texts with Notepad in PS4. Independent calibration CPU/GPU postponed by the user.

context update, 2026-11-02: **Wine already runs the EXE PE32 bare in the actual PS4 by wowprospero**, with result identical to Windows and output 0. The desktop, command input and USB, PE64 applications and Vulkan/OpenGL graphics are also operated by RADV and Zink. W094 shows MangoHud over Vulkan without the assertion of W093. See [current state and point of recoup](docs/CURRENT_STATE.md), [hardware Wine](docs/HARDWARE_W003_W011.md) and [graphics](docs/HARDWARE_G001.md).

W095 has physical evidence of execution and failure by combining graphic applications. [W096](docs/HARDWARE_W096.md) allowed them to be executed together in PS4, but there were failures after the closure. [W098](docs/HARDWARE_W098.md) captured a cut during cleaning of a worker when vkcube closed; [W099](docs/HARDWARE_W099.md) fixes the waiting unit of MangoHud and allows for closures and recharges. After another cycle there is a failure in native malloc; [W100](docs/HARDWARE_W100.md) adds synchronization to the SDK allocator, but the failure persists in your test. [W101](docs/HARDWARE_W101.md) completed two cycles without loading MangoHud. [W102](docs/HARDWARE_W102.md) reactivates the layer with sampling in the frame, and completed two cycles in PS4 with six closures 0, Start operating and final output 0. [W103](docs/HARDWARE_W103.md) recorded GPU variable without loss and three closures 0, but CPU was fixed. [W104](docs/HARDWARE_W104.md) uses process CPU accounting and simplifies the labels to CPU/GPU. In PS4 both respond to load, without count errors or losses GPU; three closures 0. The following increment sections describe historical campaigns and their limits from then.

The increment 25 adds **real text by FreeType for Orbis** in the fork Linux. The fixture PE64 draws text, numbers, accented characters and ñ, with pixel reading and check of the table presented, in three of three runs. `explorer.exe /desktop` shows the label **Start** using Wine fonts registered in the private prefix. The protection of the final partial DLL page was also corrected to respect the 16 KiB of Orbis. The final campaign and the regressions pass; no patches were added to shadPS4. See [increment 25](docs/INCREMENT_25.md) e [acceptance report](reports/increment25-accepted/report.json). In this campaign, the entry and validation in PS4 real remained pending; later hardware tests are linked up.

The increment 24 puts **Wine UI on screen** in the fork Linux. `win32u` runs with a driver user within the process (adapted to prospero-win) that composes the windows and presents them by `sceVideoOut`:

- a 64 bit GUI fixture paints its window and gives the same `result.txt` as Windows native;
- `explorer.exe /desktop` shows the Wine desktop with your taskbar.

This initial evidence did not include text or input. See [24 increment and evidence](docs/INCREMENT_24.md). Hardware: pending.

The increment 23 runs **console32-bare.exe by Wine in the fork Linux**. Wine load your actual modules (ntdll of 64 and 32 bits, kernelbase, kernel32) and the 32 bit code runs over the prospero-win translator, adapted as a provider WoW64 (`wowprospero`). The EXE creates your thread, loads your DLL and writes a `result.txt` identical to that of Windows native, with 0 output, in three runs and without stubs. In shadPS4 official emulator is still locked. `console32.exe` with CRT was not yet tested by Wine. Hardware: pending. See [23 increment and evidence](docs/INCREMENT_23.md).

The increment 22 releases GS in the fork Linux: the guest's TCB no longer uses the base GS and `sysarch` install and verify the GS of each thread. The signal handlers receive a full context and the signals are translated between musl and ABI FreeBSD. With that and two overlay corrections (relocating images of 64 bits and USD without wineboot), Wine runs ntdll PE of 64 bits, create heap and load `wow64.dll`. It stops clean with `0xc0000135`: the provider of CPU WoW64 is missing. **The EXE does not yet run by Wine.** See [22 increment and evidence](docs/INCREMENT_22.md).

The increment 21 corrects private file mappings in the fork Linux and returns EACCES for incompatible protection changes. Wine completes the load and relocation of ntdll PE64 and reaches the initialization phase Windows. The GS block is then displayed by `sysarch`, no longer assertions or timeout. The syscall slot is also adapted to pages of 16 KiB. EXE is not running by Wine. See [21 increment and evidence](docs/INCREMENT_21.md).

The increment 20 corrects the offset error of `mmap` in the fork and verifies the reading fallback of Wine. The image PE32 is mapped and Wine continues to ntdll PE64 with the policy WoW64 explicit. The following block is an assertion of `mprotect` during the relocation of ntdll, reproduced without Wine. **The EXE does not yet run by Wine.** See [increment 20, following tests and priorities](docs/INCREMENT_20.md).

The increment 19 mounts and verifies the external prefix in the fork Linux. Twelve checks are passed inside the guest and Wine consumes the prefix without throwing wineboot. The following block is a `mmap` file with offset `0xc00` that causes the emulator to fall into an assertion, before completing the load of ntdll PE64. **The EXE does not yet run by Wine.** See [19 increment, minimum reproduction and next steps](docs/INCREMENT_19.md).

The increment 18 run **console32.exe with CRT of mingw, without Wine**, in the fork Linux. Run over a msvcrt own minimum with guest heap, TLS of the EXE, critical sections and `FNINIT` in the fallback of the CPU. `result.txt` It matches Windows native and the output is 0. The official emulator is still blocked by the emulator. See [18 increment and evidence](docs/INCREMENT_18.md). Hardware: pending.

Increment 17 loads **DLLs from disk without Wine**. In the Linux fork, lifecycle-host.exe loads `lifecycle.dll` with `DllMain`, TLS and thread notifications, unloads it, and receives `ERROR_DLL_INIT_FAILED` from a DLL that rejects its attach notification. It exits with 42, as on native Windows. The official emulator remains blocked by emulator limitations. See [increment 17 and evidence](docs/INCREMENT_17.md). Hardware: pending.

The increment 16 runs **console32-bare.exe without Wine** in the fork Linux. Use your own loader PE32 and a minimum kernel32 (`pw_k32_ps4.c`) whose thunks leave the translator to the host. `result.txt` matches byte to byte with the reference of Windows and the output is 0, without stubs. In shadPS4 official the guest does not reach a clean closure: in Linux it falls into the output assertion and in Windows when publishing RX code. See [16 increment and evidence](docs/INCREMENT_16.md). Hardware: pending.

The increment 15 retains the identity of files and exposes symbols in the fork. It also produces an initialized prefix by `wineboot --init` where console32-bare.exe runs, but **only with Wine native in Linux**. In shadPS4 the EXE is not yet running: it is necessary to mount that prefix and define its boot policy. See [15 increment and evidence](docs/INCREMENT_15.md).

The increment 14 adapts relative directories and routes in the runtime PS4. Wine conserves `server_ready` and records that it requests `wineboot.exe`; This process is explicitly rejected. **The EXE is not yet running by Wine**: a validated external prefix and its boot policy are missing. See [14 increment and evidence](docs/INCREMENT_14.md).

The increment 13 adds real pipes in Linux and readv/writev for pipes and sockets. Wine complete the initialization with wineserver and reach `server_ready`. **The EXE does not yet run by Wine**: imports are still pending after the handshake. See [13 increment and tests](docs/INCREMENT_13.md).

The increment 12 implements SCM_RIGHTS transfer of files and sockets in local fork pairs Linux. Wine overcomes that block and finds `pipe`, which now explicitly fails. **The EXE does not yet run by Wine.** See [12 increment and tests](docs/INCREMENT_12.md).

The increment 11 adds shared descriptors and lags, messages with several buffers and IPC tests in the fork Linux. Wine stops with an explicit error when trying to transfer descriptors to the server (`SCM_RIGHTS` pending). The reference EXE works in Windows; **is not yet run by Wine**. See [11 increment and outstanding requirements](docs/INCREMENT_11.md).

The increment 10 compiles and links ntdll Complete Unix and wineserver in process. In shadPS4 official Linux reach the routes, NLS and reserve the first TEB; is blocked during the initialization of the server by pending services of the emulator. Includes minimum reproduction of `dup`, `fcntl`, `fstatfs`, GS and poll. **You still don't run an EXE by Wine.** See [increment 10](docs/INCREMENT_10.md).

The increment 9 validated **51 of 58 diagnoses in the local fork of shadPS4**, with seven blocks and no fault. They compile five Unix units of Wine with PS4 memory adaptations, routes and files. The ELF test actual functions of that code, including RW → RX execution with result 42, and correct the ABI stat and the selection of lstat of SDK. Wine complete does not start yet. See [evidence, limits and next steps](docs/INCREMENT_09.md).

The initial reference is retained below:

In official shadPS4 v0. 20.0 for Windows, eight platform tests pass and four are blocked. The translator runs PE32/x86 test instructions from RWX and gets `EAX=42`, `EIP=0x1008`. This test uses bytes of instructions; does not load a PE or demonstrate execution of Win32 complete applications.

The further progress of the backend, the extended tests and the local fork are described in [increment 1](docs/INCREMENT_01.md). The counts in this section correspond to the initial preserved reference, not to the extended matrix.

- The files, low address reserve 4 GiB, collisions rejection, backend `PwVmBackend` for PS4, RWX memory, threads with the TLS adapter work, TLS destroyers and recovery of an access exception.
- The RW → RX transition aborts within shadPS4 in Windows. Initial RWX does work.
- `sysarch` and the POSIX import of `pthread_key_delete` from libkernel are stubs. The second one is solved using `scePthreadKeyDelete`; FS/GS remains locked.
- The guest's `exit(0)` also causes an emulator assertion. The reports separate the result of the test of that closure failure.

See [results and blockages](docs/STATUS.md) and the report preserved in `reports/baseline/report.json`. No result is validated in hardware PS4.

<a id="preparar-y-compilar"></a>


## Prepare and compile

In PowerShell, from the root:

```powershell
./tools/bootstrap.ps1 -InstallBuildTools
wsl -d Ubuntu-22.04
```

In WSL, enter this directory and run:

```bash
python3 tools/fetch_sources.py
python3 tools/build.py
```

`fetch_sources.py` uses only `sources.lock.json`; refuse to overwrite checkouts from another review. The source of Wine is fixed to the same commit as upstream. Unload it does not imply that your port PS4 has been built.

`build.py` verifies the sources, compiles for `x86_64-pc-freebsd12-elf` and Jaguar, generates the OLF and `eboot.bin`, and builds the EXE i386 `console32.exe` and `gdi32.exe`. It also checks its architectures and rejects PT_LOAD duplicate segments. The `out/build.json` manifesto records tools, sources and hashes.

For this milestone of C it is used OpenOrbis official v0. 5.4 and Clang 14 of Ubuntu 22.04. The sysroot C + + / Clang 21 of DolphinPS4 and Mesa are reserved for the graphic milestone; They have not yet been built or validated. `--sdk`, `--cc` and `--ld` allow to indicate another SDK/compilador to the builder, which is recorded in the manifesto.

<a id="ejecutar-los-diagnósticos"></a>


## Run the diagnoses

In PowerShell:

```powershell
./tools/run-probes.ps1
./tools/run-probes.ps1 -Cases translator-rwx,vm-backend,threads-adapter
./tests/report-classification.ps1
```

Each case starts a new process with an isolated profile and `/data`. The reports are left in `reports/runs/<fecha UTC>/report.json`, along with stdout, stderr and the emulator's log. A matrix with blocked tests returns 1 code.

For a modified emulator use `-Emulator <ruta> -EmulatorKind fork -EmulatorCommit <SHA completo>`. The official binary is identified by hash; a fork is never labeled as an official emulator. The later local fork is prepared and compiled with `tools/prepare-shad-fork.ps1` and `tools/build-shad.ps1`.

The runner requires a start and a guest result, detects calls to stubs and treats timeouts/crashes as blockages. A simulated response of shadPS4 does not turn a test into approved. The warnings about unused imports are kept in the logs and are distinguished from stubs actually invoked.

<a id="organización"></a>


## Organization

- `platform/ps4/`: new adapters that consume the original interface of prospero-win.
- `native/`: diagnosis OpenOrbis, with one case per execution.
- `fixtures/win32/`: own programs PE32 for future milestones Wine/GDI.
- `tools/`: fixed sources, verified downloads, build and capture evidence.
- `upstream/`, `.deps/`, `build/`, `out/`: regenerable local sources and artifacts.

The EXs themselves are objectives of future acceptance, we do not have declared them functional in the runtime. The single-test software, thread, loading DLL and file writing; The GDI color changes when you receive input.

<a id="continuación"></a>


## Continuation

Two parallel tracks:

1. Without Wine: the increments [16](docs/INCREMENT_16.md) to [18](docs/INCREMENT_18.md) already run console32-bare.exe, lifecycle-host.exe and console32.exe with CRT. Its parts (translator as CPU of 32 bits, thunks, callbacks nested, TEB/TLS) are the ones that the WoW64 provider of the Wine track needs.
2. Wine: from the increment [23](docs/INCREMENT_23.md), console32-bare.exe runs by Wine in the fork Linux, with the translator as a provider WoW64. They follow console32.exe with CRT, exceptions of 32 bits and auto-difiable code.

Without hardware available, the assumptions of RWX/JIT and `sysarch` remain unvalidated in real console.

GDI/VideoOut, Pad, AudioOut, RADV/Vulkan and DXVK remain pending from the start Win32. There are no published PKG and no FPS measurements in the console.

The licences and provenance are detailed in [THIRD_PARTY.md](THIRD_PARTY.md).
