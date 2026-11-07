<a id="incremento-10-enlace-completo-e-intento-real-de-arranque-de-wine"></a>


# 10 increment: complete link and actual attempt to start Wine

[English](INCREMENT_10.md) | [Español](INCREMENT_10-es.md)

The complete Unix part of ntdll and wineserver within the process PS4 was compiled and linked. It runs `__wine_main` in shadPS4 official for Linux, with routes, NLS, initial memory and first approved TEB. **Wine has not yet completed its start and console32.exe has not been executed by Wine.**

<a id="implementación"></a>


## Implementation

- 24 native units of ntdll, in addition to the two diagnostic harness, and 45 server units. The full link uses `--no-undefined` and keeps service tables. The symbols defined by wineserver are renamed to live with ntdll in it ELF; external services are not replaced.
- Private overlay over Wine `490f6d5dcbb2a5047345b8af88d114bbcaad69a8`. The original checkout was not changed. The overlay is generated twice with identical hash. The own patches are 0002/0003 and are selectively adapted 0101/0102/0110/0111 of prospero-win, with hashes and attribution.
- Current directory adapters separated for client and server, route resolution, signal ABI, 16 memory KiB and `poll` over `sceNetEpoll`. The routes are resolved before calling the real filesystem; the operation `chdir` of the emulator is not used as a guarantee of road change.
- The SDK retains its original libc. A derivative library omits its fallback members indicated in the reports to link kernel imports. That an import link does not prove that the emulator implicates it.
- Real PE64 DLL ntdll, wow64, wow64win and apisetschema were prepared since the same revision Wine, in addition to the DLL PE32 and NLS already preserved. This does not yet integrate the CPU of WoW64 backend with our translator.
- Launchers for Windows and Linux with new process, time limit, ELF copied by execution, hashes and reports. The arguments were corrected: this review of shadPS4 also requires to supply `argv[0]` after `--`.

<a id="resultado-observado"></a>


## Result observed

The final attempt is in [boot report](../reports/linux-wine-runs/20261030T080525487901Z/report.json), with logs and `runtime.tar.gz` that keeps the ELF and the files mounted.

These points were reached after each operation:

1. Entry in `__wine_main`.
2. Initialization of routes and virtual memory.
3. Initialization of the environment and reading of NLS.
4. First TEB reservation. This does not yet install GS.
5. Creation of `dosdevices`, `drive_c` and internal server directories.

It was not reached `server_ready`. During initialization, stubs of `fcntl`, `_fstatfs` and `dup` are invoked, followed by a violation of access. The address of the failure is resolved at `pwserver_release_object`; a prior call to `dup` in `pwserver_dup_fd_object` received zero without a valid duplicate descriptor. Not all of the failure is attributed exclusively to that call: the server has already used other results of stubs.

The executable includes an independent reproduction `--services` that checks the effects of the operations, not just their returns. His [informe final](../reports/linux-wine-runs/20261030T080542573923Z/report.json) records:

|Service|Results in shadPS4 official Linux|
|---|---|
|Temporary file: writing and seek|Validated|
| Socketpair, shutdown y poll/EOF mediante sceNetEpoll |Validated|
|dup with shared offset|Block: return 0 without double|
|fcntl SETFD/GETFD with FD_CLOEXEC|Blocked: the bit is not preserved|
|fstatfs with written output|Blocked: returns 0 without changing the buffer|
|Base consultation GS|Blocked: returns 0 without changing the sentinel|

The diagnosis ends with guest code 92, without access violation. The closure of the official emulator remains in detention to the limit of the runner; is recorded separately from the result of the guest. No timeout is counted as a correct start.

<a id="por-qué-se-usa-también-linux"></a>


## Why is it also used Linux

In Windows, KUSER_SHARED_DATA occupies `0x7ffe0000`, direction you need Wine. The attempt [Windows](../reports/wine-runs/20261030T072446572Z/report.json) is blocked in that reservation. The required address was not changed to Windows to show compatibility. In WSL, shadPS4 official does reserve that range.

The release is fixed Linux at `linux-emulator.lock.json`. Use private glibc extracted according to `linux-runtime.lock.json`, without replacing the system, and Vulkan with lavapipe software. This allows you to test startup; does not measure PS4 graphic performance or value the presentation backend PS4. The fork of shadPS4 was not changed during this increment.

<a id="reproducir"></a>

## Reproduce

With the SDK, the Unix source and configuration already prepared, from WSL:

```sh
python3 tools/build-wine-ps4.py --boot --server
python3 tools/build-wine-ps4.py --boot --all-unix
python3 tools/stage-wine-pe64.py
python3 tools/link-wine-boot.py
python3 tools/run-linux-wine.py --services --timeout 12
python3 tools/run-linux-wine.py --timeout 12
```

The PE64 modules should be previously compiled in `.deps/wine/runtime/build`. The runners require the binaries Linux and glibc indicated above; The lock files identify the downloads, they are not automatic installers.

Do not run at once preparadores/builds that share overlay. The previous diagnostic build (`tools/build.py --with-wine-platform`) remains separate from the ELF start `build/wine-boot/eboot.bin`.

The [compilation capsule](../reports/increment10/wine-boot/evidence.json) retains its own sources, overlay, patches, configuration, complete objects, derivative library, commands, versions and hashes. The executions keep their ELF and actual distribution separately. Route algorithms also pass ASan, UBSan and host leak detection; This does not value the ABI of PS4.

<a id="trabajo-imprescindible-para-ejecutar-el-exe-por-wine"></a>


## Work required to run the EXE by Wine

The [regression of the previous 58 diagnoses](../reports/increment10-regression/report.json) keeps 51 approved and 7 blocked, without crashes or timeouts. The [comparison](../reports/increment10-regression/comparison.json) checks that the ELF diagnosis is identical to that of the 9 increment and retains all the results. This refers to the ELF previous diagnosis, separated from the new bootstrap Wine.

1. Implement and validate in the fork the required descriptor operations: duplicate with shared offset, hors, lock and filesystem queries. Use the homebrew playback included and try filesystem regressions.
2. Complete the channel cliente/servidor, including sendmsg/recvmsg and transfer of descriptors. It is not yet validated SCM_RIGHTS.
3. To implement semantics GS by thread and validate the code accesses PE64; to return a variable in sysarch is not enough. The Wine adapter rejects an installation of GS that it cannot verify. There is a lack of validation of FP, Lands and Traps from the context of exceptions.
4. Complete carga/inicializaci on PE64 and prefer, actually connect WoW64 to the translator x86 and verify output, file and thread of console32.exe.

Each requirement remains pending until actual evidence is passed. All results are emulator; hardware PS4 is still pending.
