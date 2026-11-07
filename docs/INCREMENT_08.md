<a id="incremento-8-proceso-pe32-y-primer-bring-up-de-wine"></a>


# increment 8: process PE32 and first bring-up Wine

[English](INCREMENT_08.md) | [Español](INCREMENT_08-es.md)

The process context works in the set fork of shadPS4. The three actual PE32 DLL of Wine was compiled and tested as a charger input PS4. **Wine still does not start or run console32.exe.** The Unix side has reproducible compilation blocks against OpenOrbis.

<a id="resultado-medido"></a>


## Measured result

|Environment| Pasan |Blocked| Fallan |Cases|
|---|---:|---:|---:|---:|
| Fork c6de833f6bec304b6f08c37520428ba2ed147a1a | 48 | 7 | 0 | 55 |
|official emulator v0. 20.0, same ELF and twelve fixtures| 21 | 33 | 1 | 55 |

[Fork report](../reports/increment8-fork-final/report.json), [official](../reports/increment8-official-final/report.json) and [comparison](../reports/increment8-fork-final/comparison.json). The previous 49 results are maintained and three process tests are added to the fork and three Wine diagnoses are blocked. The known official failure remains vm-enforcement. No execution reached the timeout. The fork of shadPS4 in this increment was not changed. Hardware PS4: slope.

<a id="contexto-de-proceso"></a>


## Process context

`pw_process_ps4` reserve a block of 16 KiB low 4 GiB with PEB32, standard parameters, UTF- 16 chains, empty environment completed twice, PEB_LDR_DATA and three circular lists of modules. The initialization list excludes EXE. The parameters support ASCII text that is converted to UTF- 16; another codification is explicitly rejected. There is no implementation of heap or hands Windows.

The association to a private TEB publishes FS: [0x30] and adds the memory of the process to the regions of the translator. The association counter prevents the process from being destroyed while a TEB uses it. Unbind restores the previous pointer and eliminates the region. The caller retains the process and the mapped modules and serializes its operations. Lifecycle TEB now include battery limits and the ExceptionList sentinel; This does not implement SEH.

The own EXE process32.exe checks from x86 translated PEB, TEB, base image, parameters, Unicode, environment and lists, and returns 42. It is valid in its preferred direction, relocated and with an attempt to reserve overlay. duplicate association and destruction with active associations are also rejected. Each case ends with zero live reserves and without stubs of the emulator.

Sixteen static_assert against the headers of the actual review of Wine confirm the used offsets. It is a check of ABI by i686 compilation, separated from the execution in shadPS4. Code and subject matter of this check accompany [evidence Wine](../reports/increment8-fork-final/wine/evidence.json).

<a id="wine-compilado"></a>


## Wine compiled

Review: `490f6d5dcbb2a5047345b8af88d114bbcaad69a8`. Private sources and not modified in `.deps/wine/source`; does not alter `upstream/prospero-win`. The `tools/build-wine.py` tool adapts the fixed prospero-win builder: it normalizes CRLF, fixes the location of its validator, disables X/FreeType Linux and uses incremental make. These transformations and their hashes are recorded. There was no reproductivity campaign of two reconstructions: the hashes identify this compilation, without stating that a different toolchain produces identical bytes.

|DLL|File bytes|Sections| Imports |Export slots| Forwarders |Data exports|
|---|---:|---:|---:|---:|---:|---:|
| ntdll.dll | 3.711.290 | 18 | 0 | 1500 | 0 | 8 |
| kernelbase.dll | 4.888.849 | 18 | 428 | 1436 | 94 | 0 |
| kernel32.dll | 2.067.770 | 18 | 933 | 1532 | 250 | 0 |

76 files NLS and a distribution manifesto verified by the original validator are included. Distribution SHA256: `7fcf303f4c9a1325a10740d6e624ab01dd60ca08e1b1e15414565a949e9d3c60`. DLL and data are stored under `reports/increment8-fork-final/wine/out/wine/`.

The three cases wine - * verify the identities of the manifesto, mount the exact DLL and deliver them to the actual parser/cargador within shadPS4. They return PW_ERR_LIMIT (- 7), registered as blocked, without initializing any DLL. The diagnostic parser supports 16 sections, 64 exports, 64 imports and files up to 4 MiB. The DLL exceeds those limits; They also require unimplemented characteristics, such as data exports and forwarders. The host inventory does not alter these limits or replace the validation of the parser.

That rejection describes the experimental charger. It does not show that the Wine charger is unable to handle its own DLL: the final route should incorporate its initialization and its Unix services. To increase the current parser constants does not amount to implementing that route.

<a id="wine-unix-bloqueo-real-y-reproducción"></a>


## Wine Unix: real lock and reproduction

`tools/probe-wine-unix.py` configure Wine without patches PS5 using Clang for x86_64 FreeBSD, headers, CRT and libraries OpenOrbis. C, C + + and CPP use the same sysroot PS4; The tools winebuild/widl run in the host. Configure passes; the compilation of ntdll.so fails. A serial pass with `make -k -j1` also travels wineserver and preserves errors without mixing the compiler outputs.

The observed incompatibilities include:

- cdrom.c: tipos/ioctls FreeBSD absent; env.c: TIOCGWINEZ.
- file.c: fstab.h; thread.c: sys/thr.h.
- signal_x86_64.c: machine/segments.h; The ABI signal was not validated.
- virtual.c: MAP_EXCL, need to be reviewed next to the reserve backend without replacement.
- system.c: sysctl and tipos/constantes FreeBSD, plus dev/acpica/acpiio.h.
- wineserver: assumptions of sockets/filtros and other host interfaces.

The exact list by file, the logs, config.h, commands and hashes are in `reports/increment8-fork-final/wine/evidence.json`. There is no functional ntdll.so or wineserver PS4, prefix prepared, bridge WoW64 ↔ Unix or server in process. The PS5 patches were not mechanically applied: their ABI assumptions still require adaptation. No definitions of success were added to hide errors.

From Ubuntu 22.04/WSL, with `.deps/wine/source` in the fixed review:

```sh
python3 tools/build-wine.py --jobs 12
python3 tools/audit-wine.py
python3 tools/probe-wine-unix.py
```

The last command returns error while that port is blocked. For the exhaustive pass, from `.deps/wine/ps4-unix`:

```sh
make -k -j1 dlls/ntdll/ntdll.so server/wineserver
```

From PowerShell, after `tools/build.py` and the EP compilation of Wine:

```powershell
./tools/run-probes.ps1 -IncludeWine
./tools/run-probes.ps1 -IncludeWine -Emulator build/shadPS4-win/shadps4.exe -EmulatorKind fork -EmulatorCommit c6de833f6bec304b6f08c37520428ba2ed147a1a -BuildManifest build/shadPS4-win/build-manifest.json
```

The runner returns error if there are blockages or failures; JSON distinguishes them.

<a id="siguiente-trabajo"></a>


## Next job

Carte the Unix side of ntdll for services: first memory and entorno/archivos, then threads, signal context and transition PE64 ↔ Unix. The out-of-reach functions may return a real unsupported error where appropriate; the essential services must work to continue the start-up. Compare the relevant adaptations of prospero-win and the runtime PS4 of Dolphin/Resonance before incorporating code with your powers.

Then integrate the server into the process, prepare the prefix out of PS4 and connect Wine WoW64 to the translator. Acceptance remains console32.exe with file, thread, loading of DLL and proven output. The contexts of this increment are a verified basis; do not replace the initialization of Wine. GDI, audio, input and DXVK continue after that start.
