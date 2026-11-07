<a id="incremento-19-consumir-el-prefijo-externo-en-shadps4"></a>


# increment 19: consume the external prefix in shadPS4

[English](INCREMENT_19.md) | [Español](INCREMENT_19-es.md)

**The actual increment prefix 15 is already mounted and verified within the fork Linux. Wine consumes it without throwing wineboot. The EXE is not yet executed by Wine.** The boot finds a lock before the complete load of ntdll PE64: the emulator claims that a mmap failed. file with offset `0xc00` and does not return the error to the guest. Fork was not changed: it is still in `bf96b33`.

<a id="consumidor-del-paquete-y-política-de-arranque"></a>


## Package consumer and boot policy

The launcher supports `--prepared-prefix <directorio>` and `--prefix-preflight`. The second requires the first and ends after the native checks, without entering Wine. This modality is not combined with previous diagnoses. In this increment it only supports the console32-bare.exe packaging and verifies that your hash matches the local fixture. Wine receives `C:\orbis\console32.exe`.

The consumer contrasts the revision of Wine with the compiled runtime, the hash of the tar file and each declared input. It rejects additional, duplicated, non-directories, escape routes, external links, absent records, invalid PE headers and incorrect architectures. The only accepted symbolic entries are `c: -> ../drive_c` and `z: -> ../..`. The extraction uses a private copy of the verified file, writes the files before creating the links and keeps the original package intact.

The bootstrap erases the inherited policy, initializes the routes and runs the preflight. Only if it passes and the ready start is requested enabled `WINE_PS4_EXTERNAL_PREFIX=1`. The overlay Orbis then omits the automatic call to run_wineboot and records `external_prefix_ready`. This consumes a real initialization made by Wine native in the increment 15; does not create false events or simulate processes. Other attempts to create processes continue to be rejected. The client's cwd passes to the physical folder of the EXE.

<a id="pruebas-y-criterios-de-aceptación"></a>


## Evidence and acceptance criteria

Twelve checks are passed OpenOrbis in the fork:

- Head of the three records of Wine.
- Fates of the links c: and z:, and complete resolution of a route for each unit.
- Identity between stat by route DOS and fstat of open file.
- EXE PE32; ntdll, kernel32 and kernelbase PE32; six modules PE64, including wow64 and wow64win.
- Absence of host provider wow64cpu.dll.

The preflight comes out with 0 and does not enter __ wine _ main. The comparison with the official emulator is blocked: readlink invokes a CommonStub and the prefix is not valid; The guest leaves with 95 and the emulator's closure is the timeout. It is not counted as approved by the official emulator.

They also pass the valid package and eight rejections in the host: hash of the wrong tar, altered file, deleted record, external link, route with escape, incorrect architecture, different revision and duplicate input. The architecture, route and link variants update your hashes to check these validations beyond the cryptographic check. It is not written in fate before it is rejected.

The increment matrix 18 is repeated, saving it in `reports/increment19/regressions-18/` by the new option `--report-dir`. It retains the results of console, lifecycle, the twenty cases PE and the tests of files, threads, memory, IPC, pipes, directories and metadata. The services and GS diagnoses keep the increment blocks 15. The empty prefix retains the rejection of wineboot and STATUS_DLL_NOT_FOUND.

<a id="siguiente-bloqueo-real"></a>


## Next real lock

With the prefix prepared, `prefix_preflight_passed`, `server_ready` and `external_prefix_ready` are reached. Wine solves the route DOS and opens console32.exe. Then try to map a private section of 4 KiB, with file offset `0xc00`. The fork spreads that offset to the mmap host, which fails with EINVAL; `address_space.cpp` treats him like a fatal assertion. He does not return to the guest and the execution ends by timeout. It is not reached `ntdll_pe64_ready` or `entering_windows_initialization`. There are no invocation of CommonStub in this prepared attempt, although there are other log of incomplete functions.

Wine already includes `EINVAL` by offset not aligned in `map_file_into_view` of virtual.c and has a reading fallback. That fallback cannot be executed while the emulator aborts before returning the error. It was not yet proven that returning EINVAL will solve the other image mapping requirements.

`native/wine_mmap_repro.c` reproduces the problem without Wine or translator: it opens a file and requests `sceKernelMmap(NULL, 0x1000, 3, 2, fd, 0xc00, &out)`. The expected outcome of the diagnosis is EINVAL, maintaining the output parameter. Both the fork and the official emulator reproduce the assertion and the timeout, without returning to the program. Both executions are kept separately. This program also serves as a test of future hardware; it was not run on a console.

<a id="reproducción"></a>


## Reproduction

From Ubuntu 22.04/WSL, at the root of the workspace:

```sh
python3 tools/build-wine-ps4.py --boot --all-unix
python3 tools/build-wine-ps4.py --boot --server
python3 tools/link-wine-boot.py
python3 tools/run-linux-wine.py --fork --prepared-prefix reports/increment15/prefix-package --prefix-preflight
python3 tools/run-linux-wine.py --prepared-prefix reports/increment15/prefix-package --prefix-preflight
python3 tools/run-linux-wine.py --fork --prepared-prefix reports/increment15/prefix-package
python3 tools/reproduce-wine-mmap.py
python3 tools/check-increment19.py
python3 tools/check-increment19.py --verify-only
```

Check-incre19 checks the matrix and the registered lock; a different result requires investigation, not automatically update the expectation. `--collect-existing` brings together the executions already carried out from their built-up logs, avoiding repeating them. The index is in `reports/increment19/report.json`; the individual reports and their runtime.tar.gz remain in linux- wine -runs. The capsules Wine and the emulator are low `reports/increment19/`. The package manifesto continues to declare `ps4_runtime_ready: false`.

<a id="ruta-siguiente-hasta-ejecutar-mediante-wine"></a>


## Next route to run by Wine

1. Correct the general error contract of mmap in a separate patch of the fork, validating it first with the OpenOrbis reproduction. Repeat Wine to check the reading fallback and review the interaction between 4 KiB PE pages and 16 KiB Orbis pages. The criterion is to really load the images, not just change the error code.
2. Complete and verify the load of ntdll PE64. If another platform block appears, keep the playback and solve it before moving forward.
3. Resolve GS by thread: actual readings g:, inter-thread isolation, preservation of the TLS native and restoration of the original base. The --gs-services test must pass; Only one variable is not enough to store.
4. Investigate dispatcher-mixed in Linux before reusing that border. Integrate the contract BTCpu * with contexts I386_CONTEXT, TEB32, called Unix and system, callbacks, exceptions and invalidation of the translated code. Wine must manage its actual modules; kernel32/msvcrt synthetic is not used as evidence of this integration.
5. Run console32-bare.exe and then console32.exe by Wine. Require file identical to Windows, completed thread and output 0, without shortcuts of the own modules. Only then will you mark the execution Windows by Wine as verified.

GDI, input, audio and Vulkan continue later. Hardware PS4: slope.
