<a id="incremento-16-console32-bareexe-sin-wine"></a>


# increment 16: console32-bare.exe without Wine

[English](INCREMENT_16.md) | [Español](INCREMENT_16-es.md)

**console32-bare.exe is complete in the Linux fork of shadPS4 with the loader PE32 and a minimum kernel32, without Wine.** Write `result.txt` with the same content as the reference of Windows And it comes out with 0. It is not Windows or Wine: it is a bounded subset of kernel32 on the adapters PS4. Hardware: pending.

<a id="kernel32-sintético"></a>


## kernel32 synthetic

`platform/ps4/pw_k32_ps4.c` records an image `kernel32.dll` in the explicit list of modules it uses `pw_pe32_link` (`pw_pe32_tables.c`). It has no PE headers: it is a read-only page with 13 slots of 16 bytes full of `HLT`, one per export. The source view of the translator returns `PW_ERR_NOT_FOUND` on that page, so no block is translated there. When the EIP reaches a slot, the running loop goes out to the host and attends to the call with `pw_guest_call` (stdcall), the same border of `pw_guest_call` / `pw_guest_callback` that uses the increment lifecycle 7. `pw_guest_call_finish` check that EBX, EPL, ESI and EDI do not change, unstack the arguments and return to the direction of return.

|Function|Adapter|
|---|---|
| CreateFileA, WriteFile, CloseHandle |`open` / `write` / `close` low `/data/orbis-win/console-bare`, as test `files`|
| CreateThread |pthread of the host with its own `PwPs4Cpu`, stack of 64 KiB and TEB of `pw_pe32_thread_create`|
| WaitForSingleObject, GetExitCodeThread |the status of the process; `pthread_cond_timedwait` for finite periods|
| LoadLibraryA, GetProcAddress, FreeLibrary |already loaded modules and their exports (`PwPe32Info.exports`)|
| GetCurrentProcessId | `getpid` |
| GetLastError, SetLastError |`LastErrorValue` in the teb + 0x34 of the thread|
| ExitProcess |stop all guest threads and deliver the code to ELF|

The main thread is created with `pw_pe32_lifecycle_create` + `pw_pe32_process_attach`, and each new thread with `pw_pe32_thread_create` + `pw_pe32_thread_attach`. Each has its own TEB and its TLS block. The new thread inherits the creator's regional table (minus its TEB); so you can write on the main thread pile, as the EXE does.

The arguments that the kernel32 does not serve fail with an error Win32 and a line `PWK32` with `refused`. Examples: non-flat routes, `SECURITY_ATTRIBUTES`, templates, attributes other than `FILE_ATTRIBUTE_NORMAL`, E/S overlapping, `CREATE_SUSPENDED`, batteries more than 64 KiB and DLL that are not pre-filled. A simulated success is never returned; the `refused` counter of the detail adds them.

Known limits:

- `LoadLibraryA` only solves already loaded modules (`kernel32.dll` and EXE). Load a DLL from disk returns `ERROR_MOD_NOT_FOUND`. Both modules are fixed during the process, so `FreeLibrary` just move the counter.
- The `CreateFileA` sharing modes are accepted, but are not applied.
- There's no PEB, SEH, heap, and no console handles. A failure of a thread ends the process with `0xc0000005` and a line `fault`.
- `ExitProcess` in another thread it stops others in their next call to kernel32. If a thread is only in guest code, it stops when the budget of steps is exhausted.
- The EXE is charged in `0x30000000` (preferred base `0x400000`, 14 HIGHLOW relocations). He's got `DYNAMIC_BASE`, just like the ASLR of Windows would treat him.

<a id="caso-console-bare"></a>

## Console-bare case

`native/pe32_probe.c` adds `probe_console`, which runs with `--case console-bare`. The runner copies `console32-bare.exe` and the reference `reports/increment11-windows-reference/result.txt` to `/data`. Before, check that the EXE has the hash of that reference (`83bd9d59…`). The test requires:

- output by `ExitProcess` with code 0;
- `result.txt` identical byte to byte to the reference;
- a thread created and no thread failure;
- no rejection and no unclosed handle;
- exact call count per function;
- no living memory reserve at the end.

The count is CloseHandle × 2; CreateFileA, CreateThread, WaitForSingleObject, GetExitCodeThread, LoadLibraryA, GetProcAddress, FreeLibrary, WriteFile and ExitProcess × 1. `GetCurrentProcessId` is only resolved; It's not called. `run-linux-wine.py` and `run-probes.ps1` also compare the file from the host. `tools/build.py` compiles `pw_k32_ps4.c` and generates `console32-bare.exe` with `tools/build-console-bare.py`. The binary is reproducible: the hash remains the same.

<a id="resultados"></a>


## Results

|Environment, same ELF| console-bare |Reasons|
|---|---|---|
| Fork Linux `bf96b33` | **passed** |`result.txt` equal to Windows, output 0, without stubs|
| shadPS4 oficial Linux v0.20.0 | blocked |The guest passes and the file matches; The emulator falls into `process.cpp:312 exit: Unreachable code!` when it comes out with 0 and it exhausts the timeout. `files` does the same thing.|
| shadPS4 oficial Windows v0.20.0 | blocked |The first `sceKernelMprotect` RW → RX from JIT reaches `address_space.cpp:603 Protect: Unreachable code!`, as the translator's cases from the increment 2|

Detail in the fork: `steps=23` counts steps of the dispatcher, not instructions. GCC fold the sum 1.. 1000 to the constant `0x7a314`, so the thread only writes it in the main thread pile. The calculation of the EXE does not exercise a translated loop; if the increments do so 3 - 7.

`check-increment16.py` repeats the returns of the increment 15 in the fork. They pass files, menads-adapter, pe-dll-relocated, vm-stress, ipc, pipes, filesystem and methadata. No patch was added to the emulator.

<a id="reproducción-y-evidencia"></a>


## Reproduction and evidence

```sh
python3 tools/build.py --with-wine-platform
python3 tools/run-linux-wine.py --fork --baseline --case console-bare
python3 tools/check-increment16.py
python3 tools/check-increment16.py --verify-only
```

In PowerShell, with the official binary of Windows:

```powershell
./tools/run-probes.ps1 -Cases console-bare,files -TimeoutSeconds 25
```

`reports/increment16/report.json` indexes the runs: fork and official emulator Linux separately, plus the eight regressions. It also includes the trace `PWK32` and the hashes of ELF and the emulator. The official report of Windows is left in `reports/runs/20261030T202259693Z/`. Hardware: pending.

<a id="próximo-hito"></a>


## Next milestone

Expand the minimum kernel32 only with what you ask for the following real EXE: heap, console, `GetModuleHandle` and load DLL from disk with the 7 increment lifecycle. The track Wine is still in parallel: mount the increment prefix 15 and define its boot policy.
