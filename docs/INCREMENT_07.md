<a id="incremento-7-inicialización-de-dll-y-tls-por-hilo"></a>


# increment 7: initialization of DLL and TLS by thread

[English](INCREMENT_07.md) | [Español](INCREMENT_07-es.md)

<a id="resultado"></a>


## Result

The runtime runs callbacks TLS and `DllMain` real by means of the translator x86. The order of attach/detach, arguments, maintenance of pila/registros, data isolation TLS interthread and cleaning when you return FALSE one DLL. The reference Windows use the same DLL with `LoadLibrary`, `CreateThread` and `FreeLibrary`, and ends with code 42.

All this change is in the implementation; the fork is still in `c6de833f6bec304b6f08c37520428ba2ed147a1a`, without new patches or Orbis APIs. Wine and physical console validation remains pending.

<a id="runtime-y-contrato"></a>


## Runtime and contract

`pw_pe32_lifecycle.c` receive already linked DLL in explicit order. Serialize your notifications with a mutex and prepare a vector TLS and private blocks for each thread. Each block copies the PE template; The virtual FS of IA- 32 points to a minimum TEB with `ThreadLocalStoragePointer` in `FS:[0x2c]`. The TLS native to Orbis and the FS/GS host are not replaced.

The parser validates the TLS directory, its VA addresses, template, index destination and list of callbacks completed. Allows up to 16 callbacks and a template up to 4 KiB. The runtime assigns stable module indexes and allows different blocks for the same module in different threads.

The calls to callbacks and `DllMain` use `pw_guest_callback_enter/leave` of prospero-win, with ABI stdcall and three arguments: real basis, motive and reserved NULL. The command per module is callback TLS and then `DllMain`. Attach runs through the order provided and detach inverts it. This contract was contrasted with [DllMain documentation](https://learn.microsoft.com/en-us/windows/win32/dlls/dllmain), [format TLS PE](https://learn.microsoft.com/en-us/windows/win32/debug/pe-format) and the behavior observed in the Windows test.

The reasons PROCESS_ATTACH, THREAD_ATTACH, THREAD_DETACH and PROCESS_DETACH are tested. The initial thread receives PROCESS_ATTACH; the new thread receives THREAD_ATTACH. The current field corresponds to carga/descarga dynamic, with NULL reserved, not to the entire static start of Windows.

If `DllMain` returns FALSE in PROCESS_ATTACH, detach of the module that rejected the load and of the previous ones is run in reverse order. The runtime returns `PW_PE32_INIT_FAILED` (- 100), does not activate the DLL and blocks its subsequent execution. That code is from our API, not a simulation of `GetLastError` of Windows. The general exceptions and enforcement decisions are not yet converted into SEH.

The outstanding, failed or logically downloaded modules do not deliver code. The dispatcher checks that condition at each step, also when the block is already translated into cache. You can't release an image while a initialization runtime has it registered. TLS and FS virtual are removed by destroying the thread context, before releasing the images.

<a id="fixtures-y-pruebas"></a>


## Fixtures and tests

`lifecycle.c` contains a template TLS with seed 7 and zero fields, a callback, `DllMain` and functions of consulta/mutaci on. The guest code itself checks the basis, motive, reserved, initial state and order; records the events. The test functions write your diagnostic data, without the runtime knowing your layout.

Three DLL: one main, one correct for the second module and one that returns FALSE during attack. They all link without CRT or matter.

| Caso |Validation|
|---|---|
| `pe-init-order` |Two modules, eight notifications, attack in order and reverse detach|
| `pe-init-relocated` |Same contract with both relocated modules|
| `pe-init-failure` |FALSE in the second DLL, detach from both, error - 100 and later run rejected|
| `pe-tls-threads` |New native thread, independent template, isolated mutations 55/99, eight notifications and errno preserved native|
| `pe-tls-invalid` |Six rejected directorio/callbacks alterations before running|

Functional cases also check that a PC already cached is blocked after detach or failure. Everyone checks that there are no active reserves or bytes at the end.

The [helper Windows](../reports/increment7-fork-final/host/windows-lifecycle.json) load the DLL, check attach, create a thread with TLS independent, check detach and download. A copy of the events remains in the EXE before you release the DLL, which allows you to verify the eight notifications after `FreeLibrary`. Also check that the DLL that returns FALSE is not loaded and that Windows reports `ERROR_DLL_INIT_FAILED`. This helper only runs in Windows: it does not implement APIs kernel32 for PS4.

<a id="hallazgos-y-límites-explícitos"></a>


## Specific findings and limits

The initial cache of 64 entradas/256 KiB was exhausted with two initialization DLL. It was extended to 256 entradas/1 MiB. It continues to be cited: executions are not invented or omitted callbacks in the face of exhaustion. The general cache reboot is still pending.

The first reference Windows failed a test of the space declared by `SizeOfZeroFill=8` outside the 16 byte row template. The early return of the helper without CRT would then cause another exception at the end of the last thread, hiding the original failure. The test debugger allowed both facts to be isolated. It is not concluded that all versions of Windows have such behavior or that it is a system failure.

The validated fixture uses a complete row template of 24 bytes, including its zero fields, and `SizeOfZeroFill=0`. **The non-null values of SizeOfZeroFill are expressly rejected** until they investigate that configuration separately. The host test requires the rejection of 8 value in the three DLL TLS. No support for this field is announced based only on the emulator's result.

The first attempt in `reports/increment7-initial-failures`, the intermediate regression in `reports/increment7-pre-guard` and the binario/c d of the unconfirmed configuration in `host/` of the final snapshot are retained. The final evidence uses the complete raw fixtures and the dispatcher that verifies the state by step.

<a id="reproducir"></a>

## Reproduce

```bash
python3 tools/build.py --cc clang-14 --ld ld.lld-14
bash tools/test-pe32.sh
```

```powershell
$revision = (Get-Content fork.lock.json -Raw | ConvertFrom-Json).commit
./tools/run-probes.ps1 -Emulator build/shadPS4-win/shadps4.exe `
    -EmulatorKind fork -EmulatorCommit $revision `
    -BuildManifest build/shadPS4-win/build-manifest.json `
    -Cases pe-init-order,pe-init-relocated,pe-init-failure,pe-tls-threads,pe-tls-invalid `
    -TimeoutSeconds 25
```

Without `-Cases` implemented 49 diagnostics. The test Windows is `out/lifecycle-host.exe`, from the directory that contains these DLL.

<a id="evidencia-final"></a>


## Final evidence

The [Fork report](../reports/increment7-fork-final/report.json) records **45 approved and four blocked**, without crashes or timeouts. The 44 cases of the previous increment keep their results. The known blocks of sysarch remain, the POSIX deleted from TLS key and the two exclusive tests of the FP emitter.

The [official](../reports/increment7-official-final/report.json), with the same files, records 21 approved, 27 blocked and a failed, without timeouts. The cases that run initializers are blocked in the publication JIT RX; the rejection of TLS invalid passes. The [comparison](../reports/increment7-fork-final/comparison.json) identifies ELF and the eight fixtures per hash.

The five new cases pass in three independent executions with the final ELF: `reports/increment7-smoke-final`, the complete matrix and `reports/increment7-repeat`. They do not invoke stubs, end with 0 code and leave zero active reserves. Code 0 of the rejection test means that the expected error - 100 was verified, not that the failed DLL has initialized.

The [parser with sanitizers](../reports/increment7-fork-final/host/pe32-parser.json) runs eight fixtures, with 50.934 truncations and 66.861 mutations. Also explicitly check the rejection of SizeOfZeroFill = 8 in the three DLL TLS. ASan, UBSan and leak detection did not detect errors in this targeted campaign.

The snapshot retains the 35 sources/headers/definiciones and own compilation tools, the eight PE, logs, fork manifests and the exact Windows helper. Lifecycle objects and thread context of API are used initialized to zero and maintain their direction during their life; must not be copied or destroyed as long as there are associated threads.

<a id="pendiente"></a>


## Pending

The order between modules is delivered by the caller. DLL providers are maintained without their own import, recursive discovery or cycles. The Windows lock loader is not implemented, reentrant load from DllMain, `TlsAlloc` / FLS, TLS in EXE, alignment TLS explicit, static start with no nil or SEH reserve. The images are not reinitialized after detach/fallo: should be remaped.

The next work is to prepare the process context and start of Wine, contrasting PEB/TEB, parameters, dependencies and Unix interface of ntdll for PS4. This test runtime does not replace the initialization of Wine nor does it even run the complete fixture Win32 with file and thread.
