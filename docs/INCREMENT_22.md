<a id="incremento-22-gs-por-hilo-contextos-de-señal-y-arranque-de-windows-hasta-wow64"></a>


# 22 increment: GS by thread, signal contexts and start from Windows to WoW64

[English](INCREMENT_22.md) | [Español](INCREMENT_22-es.md)

**In the fork Linux, Wine already install your GS, manage your page failures and run the ntdll 64 bit PE: creates the heap of the process and load `wow64.dll`. The start stops clean with `STATUS_DLL_NOT_FOUND` (`0xc0000135`) because the provider of CPU WoW64 (`wow64cpu.dll` is missing. The EXE is not yet run by Wine.** Hardware: slope.

The increment 21 was stopped with the output 93: `sysarch` did not install GS. When it was resolved, four other blockades appeared, one behind the other. Each has its own proof and its correction.

<a id="1-gs-libre-para-el-invitado-parches-0011-y-0012-del-fork"></a>


## 1. GS free for the guest (patches 0011 and 0012 from the fork)

In Linux, shadPS4 he kept the guest's TCB at the base GS of the thread (`tls.cpp`, `arch_prctl(ARCH_SET_GS)`) and rewrote the TCB readings `fs:` as readings `gs:` (`cpu_patches.cpp`). If a guest installed his own GS (Wine installs the TEB), all access TLS patched from the ELF went on to read the TEB. To implement `sysarch` on that design would have broken the TLS native.

- **0011**: the pointer to the TCB passes to a `thread_local` of the host, with a fixed offset compared to the threat pointer of FS. TCB readings, comparisons and XOR are generated in the same way as in Windows, by a trampoline: load the pointer from `fs:[offset]` and, if necessary, the field. In Linux the AOT patch emits those trampolines and, if there is no space, the execution fails with an explicit assertion rather than leaving a reading without a patch. Each thread checks that the offset is the same. GS is free, as in the console, where the TLS goes by FS.
- **0012**: `sysarch` (`b7uXQmnfB2s`. `AMD64_GET_FSBASE` returns the TCB; `AMD64_GET_GSBASE` and `AMD64_SET_GSBASE` use the base GS of the host thread. `AMD64_SET_FSBASE` and the unknown operations return EINVAL; in other hosts, ENOSYS. If it fails, the output parameter is not modified.

It is a change of the emulator for any title in Linux, not an exception for Wine. In the host Windows GS is the TEB of the process itself; it was neither changed nor valid there.

`native/wine_gs_probe.c` (`--gs-services`) adds the case `gs-fsbase-contract` (FSBASE equal to the TCB seen by `fs:0`, SET_FSBASE rejected without touching the output) to the existing case: real readings `gs:0` / `gs:8` in the main thread and in two threads, `__thread` native preserved and restoration of the base. It happens in the fork; in the official emulator is still blocked by the stub of `sysarch`. `segments`, blocked from the initial reference by stub, also passes in the fork.

<a id="2-contexto-completo-en-los-handlers-de-señal-parche-0013-del-fork"></a>


## 2. Full context in signal handlers (fork patch 0013)

With GS installed, Wine recorded `segv_handler Got unexpected trap 0`. The fork sent the faults to the guest's handler with an `ucontext` incomplete Orbis:

- without `mc_trapno`, `mc_err`, `rflags` or FPU status, and without bases FS/GS;
- with `si_addr` equal to the RIP instead of the direction of the failure.

Wine in Orbis is compiled with the definitions FreeBSD: it classifies the failure by the code `T_*` and by the error code. With `trapno` 0, a page failure did not go through `virtual_handle_fault` (guard pages, cell growth) and became illegal instruction.

**0013** translates the vector from Linux to `T_*` code of FreeBSD, copy the error code, `RFLAGS`, `CS`, the FXSAVE area (`mc_fpformat` XMM) and the bases FS/GS, and on returning from the handler writes `RFLAGS` and the FPU state in the context of the host. For SIGSEGV and SIGBUS, `si_addr` retains the address of the failure.

<a id="3-traducción-de-señales-en-la-plataforma-propia"></a>


## 3. Signal translation on your own platform

The same test showed a defect of ours, not of the emulator. The heads of the SDK take signal numbers, `SA_*` and `SIG_*` of the `bits/signal.h` of musl (Linux), but `sigaction` and `sigprocmask` of libkernel implement the ABI FreeBSD. `platform/ps4/pw_wine_signals.c` passed those values without translating:

- `SA_SIGINFO` of musl (4) is `SA_RESETHAND` in FreeBSD: the handler of Wine was lost after the first failure, without `SA_ONSTACK` or `SA_RESTART`;
- `SIG_UNBLOCK` of musl (1) is `SIG_BLOCK` in FreeBSD: Unlock was blocked;
- SIGBUS, SIGUSR1, SIGUSR2, SIGSYS and others have other numbers.

Now, signals (including real-time signals), lags, masks and operation are translated; an unequivalent value returns EINVAL. The handler is installed behind a trampoline that gives you the signal number of musl. The `siginfo_t` of the SDK already has the layout FreeBSD.

`native/wine_signal_probe.c` (`--signal-services`) check in the fork:

| Caso |What it requires|
|---|---|
| `signal-read-page-fault` |`T_PAGEFLT`, write-off bit, failure address, `RFLAGS`, FSBASE and GSBASE|
| `signal-write-page-fault` |`T_PAGEFLT` with writing bit and rewriting|
| `signal-fpu-state-read` |XMM and MXCSR format of the thread (control bits)|
| `signal-fpu-state-write` |an MXCSR edited on the handler is active when you return|
| `signal-mask-translation` |block and unlock SIGUSR1 and SIGBUS by the thread mask|

In the fork, all five of them pass. The official emulator doesn't pass.

<a id="4-imágenes-de-64-bits-reubicadas-a-una-dirección-inexistente"></a>


## 4. Images of 64 bits relocated to a non-existing direction

The wineserver assigns to the 64 bit DLL a dynamic base between `0x600000000000` and `0x700000000000`. In the fork Linux the user space ends in `0x54FFFFFFFFFF`, so `map_image_view` mapped ntdll in another direction (`0x7fc70000`), But `map_image_into_view` it relocated it equally to `0x6fffffd00000`. His absolute pointers pointed to non-existent memory.

The revision of the overlay (`tools/prepare-wine-boot.py`, patch `0003-ps4-static-server-and-paths.patch`) uses the direction where the view really left the eye and records it as `PWBOOT image_map_addr_unavailable` as the basis for relocation. The server's range policy was not changed.

<a id="5-kuser_shared_data-sin-inicializar"></a>


## 5. Uninitialized KUSER_SHARED_DATA

Without wineboot, `RtlCreateHeap` returned null and Wine reported `unsafe_heap_from_handle Invalid handle 0`. `virtual_init_user_shared_data`, which among other things puts `SystemCall = 1`, is only called since `run_wineboot`, and the policy of the external prefix (increment 19) skipped it whole. With the server within the process, each execution creates a new USD. Without that bit, the stub syscall of ntdll PE executed the instruction `syscall` against Linux instead of jumping to the dispatcher of Wine: `NtAllocateVirtualMemory` (id 0x18) ended up as `sched_yield`, which returns 0 without memory.

The external prefix branch now initializes that part of the USD and records it (`PWBOOT user_shared_data_ready system_call=1`). The part that fills `wineboot.exe` from the PE side (processor characteristics, version) remains undone.

<a id="resultado-de-wine"></a>


## Wine result

With the prefix prepared, in the fork:

- reaches `user_shared_data_ready`, `external_prefix_ready`, `ntdll_pe64_ready`, `entering_windows_initialization` and `dispatcher_slot_ready`;
- ntdll PE64 is relocated to its actual base; the heap of the process is created;
- `wow64.dll` load (`build_module Loaded ... wow64.dll`);
- ends with `wow:load_64bit_module failed to load dll c0000135`, output `0xc0000135`, no timeout, stubs and no access violations.

The missing DLL is that of `get_cpu_dll_name()`, the provider of CPU WoW64. The prefix package does not include `wow64cpu.dll` from the increment 19, by the way: in PS4 that provider has to be the translator. `Wine_booted` and `windows_execution_verified` are still in false.

<a id="hallazgo-aparte-exceptions-en-linux"></a>


## Separate finding: exceptions in Linux

`exceptions` fails in the fork Linux with `signal=0 resumed=0 value=0`: reading a reserved region with `sceKernelReserveVirtualRange` does not fail. The official emulator Linux gives the same line, so it's a difference from the host Linux and not a regression. The test had been validated only in Windows. It is registered with `dispatcher-mixed`.

<a id="validación"></a>


## Validation

`tools/check-increment22.py` repeats and demands:

- GS and signals: `passed` in the fork; `blocked` or not approved by the official emulator;
- `segments` passed; `exceptions` with the same detail in fork and official;
- `services` equal to the historical one except `gs-query-output`, which goes from blocked to passed (`fstatfs-output` remains blocked);
- the preflight of 12 checks; the empty prefix with its wineboot and `0xc0000135` rejection;
- the file mapping contract (10 cases, with official comparison) and that of mmap (6 cases), stored in `reports/increment22/`;
- the matrix of the increment 18 in `reports/increment22/regressions-18`;
- the start of Wine described above, the absence of the previous blocks (`GS base could not be installed`, `unexpected trap`, zero heap, mprotect sawing) and the intact hashes of ntdll PE64 and PE32 in the execution package.

The runs are made without `--winedebug`, an option of diagnosis added to the runner. `--report-dir` was added to `check-wine-file-mapping21.py` and `check-wine-mmap21.py` so as not to overwrite the evidence of the increment 21.

<a id="reproducción"></a>


## Reproduction

In Ubuntu 22.04/WSL:

```sh
python3 tools/build-shad-linux.py --reuse-configure --jobs 12
python3 tools/prepare-wine-boot.py
python3 tools/build-wine-ps4.py --boot --all-unix
python3 tools/build-wine-ps4.py --boot --server
python3 tools/link-wine-boot.py
python3 tools/run-linux-wine.py --fork --gs-services
python3 tools/run-linux-wine.py --fork --signal-services
python3 tools/run-linux-wine.py --fork --prepared-prefix reports/increment15/prefix-package
python3 tools/check-increment22.py
python3 tools/check-increment22.py --verify-only
```

`fork.lock.json` fix the commit `f1dcef5` and the patches 0001 to 0013.

<a id="próximo-hito"></a>


## Next milestone

1. **provider WoW64 over the translator**: a `wow64cpu.dll` (`BTCpu*` use `pw_cpu_ps4` from `upstream/prospero-win/wine/wow64native/`. You have to cover `I386_CONTEXT`, TEB32, system calls and Unix, callbacks, exceptions and code invalidation. Before it is necessary to solve `dispatcher-mixed` in Linux.
2. Complete the PE part of the USD that fills `wineboot.exe`, if the boot needs it.
3. `console32-bare.exe` and then `console32.exe` by Wine, with `result.txt` identical to Windows and output 0.
