<a id="incremento-20-mmap-fallback-de-wine-e-imagen-principal-reubicada"></a>


# 20 increment: mmap, Wine fallback and relocated main image

[English](INCREMENT_20.md) | [Español](INCREMENT_20-es.md)

**The fork already returns EINVAL for invalid file offsets. Wine really read the EXE sections with its fallback and continue to ntdll PE64.** The initialization of ntdll It does not yet end: the following block is an emulator assertion by enabling writing for relocation. EXE was not executed by Wine.

<a id="corrección-del-fork"></a>


## Fork correction

The 0009 patch, commit `bcae5f261c86a79cf7b8ac8ef2bf3f7a9fb2a8c4`, validates the file offset in posix_mmap before calling MemoryManager:: MapFile. The negative or non-aligned offsets to the Orb granularity of 16 KiB return EINVAL. sceKernelMmap retains the output parameter when it fails. Validation occurs before changing the memory map; the behavior of anonymous mappings is not changed or an exception is added for Wine or for a specific program.

The extended reproduction OpenOrbis passes six checks in the fork:

- Discount of offset `0xc00`, negative and 4 KiB not aligned to 16 KiB.
- Valid mapping with offset of 16 KiB and reading of the expected pattern of the file.
- Invalid offset rejection with MAP_FIXED, without changing the output parameter.
- Conservation of the existing memory content after that failed request.

The same ELF in the official emulator reproduces the assertion of the increment 19 in the first request. The test offsets contract is still pending validation in hardware. The nine patches reproduce the fixed tree of the fork.

<a id="carga-real-del-exe-en-wine"></a>


## Actual EXE load in Wine

A trace is added to the existing fallback of virtual.c that records offset, requested bytes, read bytes and errno, without changing its result. In the final run, the four sections of the EXE are read from offsets `0x400`, `0x800`, `0xa00` and `0xc00`, with 1024, 512, 512 and 512 bytes respectively, without errors. The new EINVAL allows that reading to be performed instead of aborting the emulator.

The path of the charger reports `STATUS_IMAGE_NOT_AT_BASE` (`0x40000003`), machine I386 (`0x014c`, image in `0xed0000`. The preferred base `0x400000` is not free. This information state made the initial route attempt start.exe, which is not available and would require another process.

The prospero-win `wine/patches/0130-ntdll-ps5-report-main-exe-load-failure.patch` patch is adapted: it accepts only STATUS_IMAGE_NOT_AT_BASE as a mapped image and leaves the relocation to the Wine PE charger. The other errors are reported and end the process instead of testing start.exe. It is not claimed that the EXE relocations have already been implemented. The prepared bootstrap also sets `WINEARCH=wow64`, to keep the host x86 - 64 when loading PE32. The empty prefix maintains its previous behavior.

The original patch is LGPL- 2.1 -or-later, like Wine and prospero-win. Their terms of reference, the adapted file and the hashes original/adaptado are retained in boot-manifest.json, within `prospero_patches`. The original source of Wine is kept intact; changes occur in the overlay Orbis.

<a id="nuevo-bloqueo-protección-del-mapeo-de-ntdll"></a>


## New lock: protection of the ntdll mapping

Wine opens `/data/wine/lib/wine/x86_64-windows/ntdll.dll` and reads its sections. The final run records sixteen reading fallbacks between the EXE and ntdll, with the bytes actually requested copied. Then load_ntdll calls virtual_relocate_module because the DLL is not on your preferred base either.

By changing protections to read/write, the emulator falls into `address_space.cpp:815 Protect`, with `mprotect failed: Permission denied`. The host's file route uses MAP_SHARED and does not spread the private distinction of mapping up to AddressSpace:: MapFile. This requires a review of both the error contract and the semantics of private mappings and their permissions. The Orbis file permit policy is not changed in this increment.

The independent reproduction `native/wine_file_protect_repro.c` opens a file only reading, mapping it with MAP_PRIVATE and PROT_READ, and asking PROT_READ h124; PROT_WRITE. Both the fork and the official emulator reproduce the same statement, without Wine or translator. The test also checks that a private writing does not alter the file if any platform allows the operation to be completed; That road still hasn't been validated.

The attempt of Wine ends by timeout of this assertion, without CommonStub invoked. They are not reached `ntdll_pe64_ready` or `entering_windows_initialization`. Wine_booted and windows_execution_verified remain in false.

<a id="validación-y-evidencia"></a>


## Validation and evidence

The 31 executions of the increment matrix 18 are repeated with the final fork, including comparison with the official, and their expected results are preserved. The console, lifecycle, twenty cases PE, memory, files, threads, IPC, pipes, directories and metadata of the fork continue to pass. The preflight of twelve prefix checks also passes with the final ELF. Services and GS keep their documented blocks; the empty prefix start retains the wineboot rejection and the state `0xc0000135`.

`reports/increment20/report.json` collects the reports and distinguishes the approved evidence from the Wine block. Individual runtime packages keep the exact ELF, prefix and login. The exploratory runners and the pre-adaptation matrix 0130 are maintained; the ones used by the verifier correspond to the final binary. The emulator capsule records a clean tree and its SHA256. The increment prefix package 15 is not modified and maintains `ps4_runtime_ready: false`.

<a id="reproducción"></a>


## Reproduction

From Ubuntu 22.04/WSL, after applying the fixed fork patches:

```sh
python3 tools/build-shad-linux.py --reuse-configure --jobs 12
python3 tools/build-wine-ps4.py --boot --all-unix
python3 tools/build-wine-ps4.py --boot --server
python3 tools/link-wine-boot.py
python3 tools/check-wine-mmap20.py --official
python3 tools/run-linux-wine.py --fork --prepared-prefix reports/increment15/prefix-package
python3 tools/reproduce-wine-file-protect.py
python3 tools/check-increment20.py
python3 tools/check-increment20.py --verify-only
```

Check-incre20 checks the contract of mmap, the actual fallback and the registered protection block. `--collect-existing` gathers the already executed logs under build/increment20- * .log. A change of the lock requires you to investigate and update the reproduction, not to assume that the next stage works.

<a id="prioridades-siguientes"></a>


## Next priorities

1. Solve file mappings protection: compare MAP_PRIVATE/MAP_SHARED, open files only reading and read/write, file preservation after private scriptures and error return without aborting the emulator. Keep a test OpenOrbis and separate the validated in the hardware fork.
2. Repeat the loading and relocating of ntdll PE64 until you reach your actual finish marker. It is not enough that all its sections have been read.
3. Valid GS by thread with real gs accesses:, isolation, TLS native and restoration.
4. Investigate dispatcher-mixed in Linux and integrate BTCpu * with contexts, called, callbacks, exceptions and translation invalidation.
5. Run console32-bare.exe and console32.exe by using the actual DLL of Wine, with identical result to Windows, completed thread and output 0.

Hardware PS4, graphics, input and audio are still pending.
