<a id="incremento-4-primer-pe32-sin-importaciones"></a>


# increment 4: first PE32 without imports

[English](INCREMENT_04.md) | [Español](INCREMENT_04-es.md)

The back support of sections of 4 KiB and their shared permissions is documented in [increment 5](INCREMENT_05.md). This document retains the previous evidence.

<a id="resultado"></a>


## Result

The fork runs the entry of the own EXE `minimal32.exe` from a real PE32 file. Returns 42 in `0x30000000` and also in `0x34000000`, after applying five HIGHLOW relocations. The return spreads to the OpenOrbis process and the runner checks that shadPS4 ends with 42 code in both cases.

The same file was also run directly in Windows and ended with 42. His SHA256 is `2aa89653551212b3868bf82e7254c3c017cd95d90b3a8d3f6587dc824ce61037`. The [reference Windows](../reports/increment4-fork-final/host/windows-pe32.json) records that hash, output code and duration.

This validates the load and execution of the own EP. It is not valid to initialize processes Windows, `ExitProcess`, DLL, CRT or Wine: the harness prepares an IA- 32 pile, call the entrance and check a real return by `RET`.

<a id="cargador-y-fixture"></a>


## Loader and fixture

`platform/ps4/pw_pe32.c` implements the initial subset, compared to [Microsoft PE specification](https://learn.microsoft.com/en-us/windows/win32/debug/pe-format). Check signatures, i386 architecture, optional header PE32, sizes and ranges, executable input, sections without overlaps and relocation blocks.

Each image is reserved without replacing existing memory. Headers and sections are copied, section pages are initialized to zero, HIGHLOW relocations are applied and final permissions are set per section. The relocation scriptures are made before restricting the code to RX. The W + X sections are rejected. Uncompromised gaps remain inaccessible. The instruction view only delivers bytes belonging to executable sections; the dispatcher table records separately the header, data and code permissions.

The reservation supports the preferred base or an explicit alternative address. It does not automatically choose another base in a collision. The relocated route requires valid relocation; only HIGHLOW supports and ABSOLUTE filling inputs, and rejects overlapping destinations or outside the sections.

`fixtures/win32/minimal.c` is compiled with MinGW i686 without CRT or libraries. It has a seed 7 in `.data`, a pointer that requires relocation and a result in `.bss`. The entry checks that BSS starts at zero, reads through the pointer, calculates `7 * 5 + 7`, saves the result and returns. The five relocations are in code and data; It is not enough to move a single entry address.

GNU ld emits a completely zero import descriptor. Only that empty terminator of 20 bytes is accepted; a descriptor of not-null DLL is rejected. No imports are resolved by simulated responses.

<a id="validación"></a>


## Validation

| Caso |Fold results|
|---|---|
| `pe-preferred` |Entrance executed, EAX = 42, restored battery, process output 42|
| `pe-relocated` |Five fixups on another base, EAX = 42, restored stack, output 42|
| `pe-invalid` |Twelve invalid or unadmitted cases rejected; the result of parseus retains its previous value|
| `pe-collision` |Occupied reservation rejected without overwriting its content|

The two positive executions pass through two real blocks of the dispatcher, without needing hostexec for this program. All cases release their reserves and verify zero active committed bytes at the end.

The [Fork report](../reports/increment4-fork-final/report.json) records **30 approved and four blocked**, without crashes or timeouts. The previous 30 cases keep their results. The remaining blocks remain `sysarch` / FS/GS native, the POSIX import of `pthread_key_delete` and the two exclusive emitter cases for LDMXCSR/ADDPS; their routes hostexec pass.

The [official](../reports/increment4-official-final/report.json), with the same ELF and EXE, records 15 approved, 18 blocked and a failed, without timeouts. The rejections of tickets and collisions pass; Both EP executions are blocked in the RX publication. The [comparison](../reports/increment4-fork-final/comparison.json) contains hashes of ELF and EXE together with the results per case.

The four PE tests pass in three independent processes per case with the same binaries: `reports/increment4-smoke`, the complete matrix and `reports/increment4-repeat`. They do not invoke stubs. Positive executions end with code 42; The two rejection tests end with 0.

The host test of the parser runs 5.606 truncations and 8.220 mutations of headers and relocations with ASan, UBSan and leakage detection. No errors appeared in that campaign; It's not an exhaustive test of hostile entrances. The [informe host](../reports/increment4-fork-final/host/pe32-parser.json) sets compiler, source and EXE hashes. The snapshot also preserves the test and its script.

The reports identify both ELF and the fixtures by SHA256. The exact EXE is left in `fixtures/` of the snapshot, the 21 sources/headers/herramientas of its own compilation in `inputs/`, along with fork manifests and logs. The comparator requires that ELF, fixtures and set of cases match before comparing states.

<a id="reproducir"></a>

## Reproduce

In WSL:

```bash
python3 tools/build.py --cc clang-14 --ld ld.lld-14
bash tools/test-pe32.sh
```

In PowerShell:

```powershell
$revision = (Get-Content fork.lock.json -Raw | ConvertFrom-Json).commit
./tools/run-probes.ps1 -Emulator build/shadPS4-win/shadps4.exe `
    -EmulatorKind fork -EmulatorCommit $revision `
    -BuildManifest build/shadPS4-win/build-manifest.json `
    -Cases pe-preferred,pe-relocated,pe-invalid,pe-collision -TimeoutSeconds 25
```

The runner copies the EXE to the `/data` isolated from each test and verifies its hash against the compilation manifesto. Without `-Cases`, run the matrix of 34 diagnoses. No patches of shadPS4 were added; the first increment fork is preserved.

<a id="alcance-pendiente"></a>

## Remaining scope

This charger requires sections of 16 KiB and limits the image to 32 MiB, the file to 4 MiB, sections to 16 and relocations to 4.096. Reject DLL, active imports, TLS image, load config and other unimplemented directories. Normal PE with sections of 4 KiB are not yet admitted.

It does not initialize PEB, TEB of Wine, arguments Windows, CRT, DLL or its callbacks. The dispatcher maintains its unchanging code contract and reliable operands at hostexec. This result does not convert the prototype into a general EXE executor or value PS4 hardware.

The next increment should allow PE sections of 4 KiB with consistent permissions on pages PS4 of 16 KiB and prepare a real Win32 call with solved imports. The integration of Wine will continue to be necessary for the complete file and thread fixture; shall not be counted as made by stubs of its own.
