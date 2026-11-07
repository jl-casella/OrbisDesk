<a id="incremento-6-dll-pe32-e-importaciones-reales-por-iat"></a>


# increment 6: DLL PE32 and actual imports by IAT

[English](INCREMENT_06.md) | [Español](INCREMENT_06-es.md)

The initialization of DLL and TLS later is documented in [increment 7](INCREMENT_07.md). This document retains the above evidence.

<a id="resultado"></a>


## Result

`imports32.exe` load along with your own DLL `testmath.dll`. The IAT is solved with one function per name and one function per ordinary. Both functions are performed in the dispatcher; The EXE returns 42 and that value spreads at the output of the process OpenOrbis. It works both on the preferred bases and by relocating both modules.

The same pair EXE/DLL returns 42 in Windows by your normal loader. The [informe Windows](../reports/increment6-fork-final/host/windows-dll.json) sets the hashes of both files, duration and output code.

No patches or APIs were added to the emulator. The fork `c6de833f6bec304b6f08c37520428ba2ed147a1a` is kept. Wine, kernel32, ntdll and the general initialization of DLL remain outstanding; the functions executed here are own DLL code, without simulated answers to APIs Windows.

<a id="implementación"></a>


## Implementation

`platform/ps4/pw_pe32_tables.c` validates imports/exports and resolves the link, following the format of [PE tables documented by Microsoft](https://learn.microsoft.com/en-us/windows/win32/debug/pe-format). RVAs, sizes, terminators, chains, indexes, ordinals, IAT permissions and dual destination positions are checked. The ordinals are resolved against the base and the export table; the gaps in that table are not considered functions.

The names of DLL are compared without distinguishing capital letters / small letters, while the names of symbols are compared exactly. The solving uses an explicit list of already loaded images: do not search for system DLL or download files. The dispatcher's instruction view can obtain code from any of the registered modules and retains its independent logical permissions.

The resolution calculates all destinations first. Only when all exist are the actual addresses written in the IAT and the image goes to the linked state. A failure leaves all entries intact. The link report identifies DLL, symbol or ordinal and RVA from the slot that could not be solved. An image with outstanding imports cannot deliver instructions or be linked to the state of CPU.

The providers of this stage should be DLL without imports or entry point. A DLL with initialization, own imports, reshipped exports or unimplemented features is rejected; its requirements for making it functional are not omitted.

<a id="fixtures-y-abi"></a>


## Fixtures and ABI

- `testmath.c` and `testmath.def`: export `Scale` by nombre/ordinal 7 and `OrdinalScale` only per ordinary 11. There are holes in the ordinals 8 - 10.
- `imports.c`: invoke both functions by the two entries of IAT. `Scale(1)` calculate 12 using a global DLL factor; the ordinal function adds a global variable 30 and returns 42.
- `nested.c` and `nested.def`: form a real DLL with an additional dependence, used to demonstrate rejection of the graph not yet supported.

The test checks that the IAT contains addresses of the loaded exports and that the code view visits both function entries. Verifies return 42, restored battery and preservation of EBX, EBP, ESI and EDI. It does not use thunks to return constant from the host or to invoke PE32 code directly in x86 - 64 mode.

In the re-located test, the EXE goes from `0x30000000` to `0x34000000` and the DLL from `0x32000000` to `0x36000000`. Four relocations are applied: two in each module.

<a id="pruebas-nuevas"></a>


## New tests

| Caso |Result required|
|---|---|
| `pe-dll-preferred` |Two solved imports, both functions visited, return and output 42|
| `pe-dll-relocated` |The same after moving both modules and applying four fixups|
| `pe-dll-missing` |`PW_ERR_NOT_FOUND`, DLL identified, IAT intact|
| `pe-dll-symbol` |Ask `Xcale`, keep the IAT even if the previous ordinal does exist|
| `pe-dll-ordinal` |Order the empty ordinal 8 and keep the IAT|
| `pe-dll-invalid` |Rejects five changes to unsupported tables or features|
| `pe-dll-dependency` |`nested.dll` contains own imports; return `PW_ERR_UNSUPPORTED` without running or modifying the IAT|

The symbol, ordinal and dependency tests alter the memory copies of the fixture before validating and loading it; the original stored files are not changed. The exact alterations are in `native/dll_probe.c`. The missing DLL test omits the registry provider; It doesn't depend on a search in the system.

The table test covers IAT out of range, unsupported re-export, invalid ordinal index, out-of-range name table and non-zero DLL input. Each case verifies its expected error before accounting for approval.

<a id="evidencia"></a>


## Evidence

The [Fork report](../reports/increment6-fork-final/report.json) records **40 approved, four blocked, zero crashes and zero timeouts**. The 37 cases of the previous increment keep their status. The blocks are the same: sysarch, deleted POSIX from key TLS and the two exclusive tests of the isolated FP emitter.

The [parser with sanitizers](../reports/increment6-fork-final/host/pe32-parser.json) is tested on five files, with 28.620 truncations and 41.486 mutations of headers and directories: ASan, UBSan and leak detection did not detect errors in that coated campaign. It does not amount to a comprehensive audit of hostile files.

The snapshots retain the five fixtures, the 29 sources/headers/definiciones and the own tools identified by `build.json`, logs and manifests of the emulator. The comparator requires the same hashes of ELF and fixtures.

The [informe oficial](../reports/increment6-official-final/report.json), with the same files, records 20 approved, 23 blocked and a failed, without timeouts. The two DLL executions are blocked in publication JIT RX; The five cases of rejection pass. The [comparison by case](../reports/increment6-fork-final/comparison.json) keeps hashes of all fixtures.

The seven new cases pass in three independent executions with the final ELF: `reports/increment6-smoke`, the complete matrix and `reports/increment6-repeat`. They do not invoke stubs and leave zero active reserves; The positive come out with 42 and the rejection tests with 0.

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
    -Cases pe-dll-preferred,pe-dll-relocated,pe-dll-missing,pe-dll-symbol,pe-dll-ordinal,pe-dll-invalid,pe-dll-dependency `
    -TimeoutSeconds 25
```

The builder generates the import library with GNU ld. The entries IAT of the fixtures are not written by hand. Without `-Cases`, the runner runs 44 diagnoses.

<a id="alcance-pendiente"></a>

## Remaining scope

Up to 64 imports, 64 export slots and eight modules are allowed in the running view. The name of DLL is limited to 63 characters and the symbol name is limited to 127. providers should be already loaded and not have their own units; there is no recursive discovery, cycle treatment, or prefix search Windows. No imports bound/delay, multi-name aliases for an export, data exports, forwarders, TLS image and `DllMain` are allowed.

The next stage is initialization of DLL and TLS with order tests, arguments and initialization failure, before you connect the actual start of Wine. The physical validation in PS4 remains pending; the available bank remains shadPS4.
