<a id="incremento-9-memoria-rutas-y-archivos-del-lado-unix-de-wine"></a>


# 9 increment: memory, routes and files from the Unix side of Wine

[English](INCREMENT_09.md) | [Español](INCREMENT_09-es.md)

Five Unix units of Wine adapted to PS4 are compiled and actual functions of that code are performed within the ELF diagnostic. **It has not been removed Wine complete or executed console32.exe with Wine.**

<a id="validación"></a>


## Validation

|Environment| Pasan |Blocked| Fallan | Timeouts |
|---|---:|---:|---:|---:|
| Fork c6de833f6bec304b6f08c37520428ba2ed147a1a | 51 | 7 | 0 | 0 |
|official emulator v0. 20.0, same ELF and twelve fixtures| 23 | 34 | 1 | 0 |

[Fork](../reports/increment9-fork-final/report.json), [official](../reports/increment9-official-final/report.json), [comparison](../reports/increment9-fork-final/comparison.json) and [regression](../reports/increment9-fork-final/regression.json). The previous 55 results are preserved. The three new diagnoses pass in the fork, without invoking stubs. In the official emulator they pass paths/files and reject functions out of reach; memory is blocked when running the RX page. The official failure is still vm-enforcement. Its process closure also retains the known problem of the increment 1.

The fork did not receive any changes in this increment. Hardware PS4: slope.

<a id="cambio-de-plataforma"></a>


## Change of platform

`pw_wine_platform` uses the same primitive kernel as the proven backend PS4: exact reserve without replacement, flexible mapping, protection and release. Mapping is the property of Wine and does not enter the image record PE/JIT. The direction and size aligned to 16 KiB are required; other invalid flags or protections are rejected. PROT_NONE is reserved without consuming flexible memory.

Orbis can return ENOMEM when the address is busy. Wine needs EEXIST to continue looking for another address. The bridge converts that error only if sceKernelVirtualQuery shows an overlap; If not, keep the original error. Memory exhaustion is not confused with a collision.

The real function anon_mmap_tryfixed of Wine calls that bridge. Wine virtual.c also uses protection / release PS4 and host pages route 16 KiB, following the adaptation of prospero-win 0510. The complete Windows allocator has not yet been exercised: it continues to require the start and other units of ntdll.

For the routes, absolute, existing, and explicit USER are required HOME and WINEPREFIX. No Unix user base is consulted or a home directory is invented. Harness runs set_home_dir and set_config_dir of the loader of Wine with those values. The test uses empty test directories: **It's not a prefix. Wine initialized**, and does not run wineboot or prepare records of Windows.

<a id="dos-incompatibilidades-del-sdk-corregidas"></a>


## Two incompatibilities of the corrected SDK

The SDK public stat structure has mode_t of 32 bits. The kernel structure uses mode/nlink 16 bit and has st_size offset 72, with total size 120. Writing the kernel result directly into the SDK structure moved the size and other fields. The bridge receives the kernel format and converts each field to the public structure; stat/fstat/lstat of Wine file.c pass through it. The size and offsets of the kernel format are checked when compiling. The layout was contrasted with the ABI of shadPS4, without copying its filesystem implementation.

In addition, lstat.lo of libc calls fstatat.lo, which returns unconditionally ENOSYS. The SDK already includes an import lstat of libkernel. The compilation generates a private copy of libc.a and eliminates only lstat.lo to solve that call by actual import. The original SDK remains intact. The hashes original/derivado and the disassembled accompany the evidence.

Lstat was checked on an ordinary file. No symbolic links were validated: in the fixed review of the emulator, posix_lstat delegates in posix_stat. No semantic or follow-up or two-device operation of a complete prefix is stated.

<a id="pruebas-nuevas"></a>


## New tests

- **wine -memory:** seven checks. Accurate reservation, collision by preserving data, RW → RX and native execution with result 42, return to RW and release, reserve PROT_NONE, rejection of invalid inputs and overlap that begins in a free zone and reaches a later reservation. It is called the modified function of Wine, not a copy of its implementation.
- **wine -path:** ten checks. Validation of routes and user, actual functions of initialization of directories of Wine, escritura/lectura/seek, rename, stat/fstat/lstat and preservation of exits before ENOENT/EBADF, in addition to the ENOTDIR rejection. The resulting file is stored between the logs.
- **wine -unsupported:** verifies STATUS_NOT_SUPPORTED (0xc00000bb and no change buffers for CD-ROM and device features. This is a correct rejection test; neither of these two capabilities is declared functional.

They do not run complete NtCreateFile/NtReadFile/NtWriteFile: they need the server and the rest of ntdll. The file operations of the test use libc/libkernel and the bridge ABI; the route functions come from the actual Wine.

<a id="fuentes-y-compilación"></a>


## Sources and compilation

Wine remains in `490f6d5dcbb2a5047345b8af88d114bbcaad69a8`, unchanged. `tools/prepare-wine-ps4.py` generates a overlay of five files and the patch `patches/wine/0001-ps4-memory-paths-files-cdrom.patch`. Its exact application was verified with git apply --check and the original source is still clean. The adaptations of fstab and host pages are based on the patches 0100/0510 of prospero-win, LGPL- 2.1 -or-later, with their preserved powers.

They compile virtual.c, file.c, env.c, loader.c and cdrom.c. Two harness include complete memory and loader units. For the ELF test objects are reduced with ld -r --gc-sections, preserving only the proven functions and their dependencies. This prevents the OpenOrbis KEEP from dragging the Unix tables not yet carried. The complete objects are also preserved. Unsolved symbols are not ignored or simulated services are provided to link.

The snapshot saves 56 compilation inputs, tool versions, commands, complete and reduced objects, derivative libc and exact ELF. See [evidence capsule](../reports/increment9-fork-final/wine-platform/evidence.json). The three DLL PE32 and its NLS are those of the increment 8; The limitation of the experimental parser that rejects them was not reconstructed or changed.

In WSL, after setting the Unix diagnosis of the increment 8:

```sh
python3 tools/build.py --with-wine-platform
python3 tools/build-wine-ps4.py --diagnose-remaining
```

The second command returns error: the remaining five units you examine are still blocked. Your current commands and errors remain at `build/wine-ps4/remaining-report.json` and the login per unit.

```powershell
./tools/run-probes.ps1 -IncludeWine -IncludeWinePlatform
./tools/run-probes.ps1 -IncludeWine -IncludeWinePlatform -Emulator build/shadPS4-win/shadps4.exe -EmulatorKind fork -EmulatorCommit c6de833f6bec304b6f08c37520428ba2ed147a1a -BuildManifest build/shadPS4-win/build-manifest.json
```

<a id="lo-que-sigue-bloqueado"></a>


## What's still blocked

- signal_x86_64.c: machine/segments.h; context of signals and FS/GS pending.
- thread.c: sys/thr.h and thread operations FreeBSD to be adapted.
- sync.c: sys/event.h; synchronization / events PS4 pending.
- socket.c: FONREAD and SIOCATMARK, not replaced by unverified numbers.
- system.c: sysctl, CPU information and device headers FreeBSD.

There is still a missing enlace/carga of ntdll.so PS4, server within the process, I prefer initialized and WoW64 ↔ Unix. The device consultations and the prefix link semantics also require work. The next block is synchronization / threads and signal context, maintaining these tests as regression before trying to complete start Wine.
