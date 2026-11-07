<a id="incremento-17-carga-de-dll-desde-disco-sin-wine"></a>


# increment 17: load of DLL from disk without Wine

[English](INCREMENT_17.md) | [Español](INCREMENT_17-es.md)

**lifecycle-host.exe is complete in the Linux fork of shadPS4 without Wine.** Load `lifecycle.dll` from `/data` and run your `DllMain` and your callback TLS. Create a thread that receives DLL_THREAD_ATTACH/DETACH and download the DLL with DLL_PROCESS_DETACH. Check that `lifecycle-fail.dll` fails with `ERROR_DLL_INIT_FAILED` and comes out with 42, as in Windows native. It's still a minimum kernel32, not Windows. Hardware: pending.

<a id="referencia-de-windows"></a>


## Windows

`reports/increment17-windows-reference/report.json` records the native execution in this host (Windows 11 Pro 10.0.26200): `lifecycle-host.exe` from a directory with all three DLL comes out with 42. The report keeps the hash of the four binaries. The runners compare those hashes to the copied files to `/data` before they consider a run valid. The EXE itself verifies the order of the eight events of `lifecycle.dll` (0x11, 0x21, 0x12, 0x22, 0x13, 0x23, 0x10, 0x20), and it only returns 42.

<a id="lifecycle-dinámico"></a>


## Dynamic lifecycle

`platform/ps4/pw_pe32_lifecycle.c` left the list of images fixed when created. Now:

- Each thread region reserves a block TLS for each `PW_PE32_MAX_MODULES` slot: `(2+8)` pages of 16 KiB. Thus, a loaded module then receives a block on all living threads without moving the TEB.
- The lifecycle keeps a record of living threads. That's why a `PwPe32Thread` must keep his address between create and destroy.
- `pw_pe32_lifecycle_load` assigns the free slot as an index TLS, installs the block with its template on each thread and executes PROCESS_ATTACH on the flaming thread. If `DllMain` returns FALSE, runs PROCESS_DETACH, releases the slot and returns `PW_PE32_INIT_FAILED`.
- `pw_pe32_lifecycle_unload` runs PROCESS_DETACH and releases the slot. None of the two functions unmapped the image.
- `pw_pe32_lifecycle_set_runner` replaces the coarse execution of the notifications. The kernel32 uses it so that the `DllMain` code can call its functions.

The five cases of the increment 7 (`pe-init-*`, `pe-tls-*`) continue to pass unchanged.

## kernel32

`platform/ps4/pw_k32_ps4.c` from 13 to 15 exports:

- **`LoadLibraryA`:** if the DLL is not loaded, read `/data/<nombre>.dll` (flat name in small cases) and load with `pw_pe32_load` on its preferred base. If the base is occupied, it replaces it in `0x34000000`, `0x35000000`... Then it links it against the modules loaded with `pw_pe32_link` and calls `pw_pe32_lifecycle_load`.
- **`FreeLibrary`:** if the counter reaches zero, call `pw_pe32_lifecycle_unload` and unmap the DLL. kernel32 and the EXE are still fixed.
- **`GetCurrentProcess`:** returns the pseudo-handle `0xffffffff`.
- **`TerminateProcess`:** only accept that pseudo- handle and come out as `ExitProcess`. With any other handle he rejects the call.

The list of modules is dynamic. Each thread reconstructs the module part of its regional table when a generation counter is changed. It does so before its next step, always in its own thread, so it never changes the status of another CPU. The source view runs the list under the process mutex.

Known limits, also recorded in the report:

- A DLL can only import from modules without their own importance: it is the rule of `pw_pe32_link` (today, kernel32).
- `LoadLibraryA`, `FreeLibrary` and `CreateThread` from a DLL notification are rejected with `refused`. The lifecycle is not reentrant, unlike the Windows loader lock.
- Download a DLL not invalidating the translated blocks of your range. If another thread continues to run it, or if another code is loaded in the same direction, the result is indefinite.
- When you come out, the remaining DLL loads receive PROCESS_DETACH also with `TerminateProcess`. In Windows, `TerminateProcess` does not notify them.

<a id="resultados"></a>


## Results

|Environment, same ELF| lifecycle-host |Reasons|
|---|---|---|
| Fork Linux `bf96b33` | **passed** |Output 42, as Windows; 12 notifications (8 from `lifecycle.dll`, 4 from the rejected DLL); without stubs or rejections|
| shadPS4 oficial Linux v0.20.0 | blocked |The guest passes; `process.cpp:312 exit: Unreachable code!` and timeout, as in the increment 16|
| shadPS4 oficial Windows v0.20.0 | blocked |`address_space.cpp:603 Protect: Unreachable code!` when publishing the first RX block|

`console-bare` of the increment 16 continues to happen, now with 15 exports. `check-increment17.py` repeats in the fork the five cases of the increment 7 and the eight regressions of the increment 15: files, amenads-adapter, pe-dll-relocated, vm-stress, ipc, pipes, filesystem and methadata. No patch was added to the emulator.

<a id="reproducción-y-evidencia"></a>


## Reproduction and evidence

```sh
python3 tools/build.py --with-wine-platform
python3 tools/run-linux-wine.py --fork --baseline --case lifecycle-host
python3 tools/check-increment17.py
python3 tools/check-increment17.py --verify-only
```

```powershell
./tools/run-probes.ps1 -Cases lifecycle-host -TimeoutSeconds 25
```

`reports/increment17/report.json` indexes the runs, the trace `PWK32` and the case detail. The official report of Windows is in `reports/runs/20261030T203956399Z/`. Hardware: pending.

<a id="próximo-hito"></a>


## Next milestone

Go to `console32.exe`, which uses the CRT of mingw. It matters 26 functions of `msvcrt.dll` and also critical sections, `TlsGetValue`, `VirtualProtect`, `VirtualQuery`, `GetModuleHandleA`, `GetStartupInfoA`, `Sleep` and `SetUnhandledExceptionFilter`. It requires a minimum msvcrt or allow a DLL to amount from another with imports. The track Wine is still in parallel.
