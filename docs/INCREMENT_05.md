<a id="incremento-5-secciones-pe-de-4-kib-sobre-páginas-ps4-de-16-kib"></a>


# increment 5: PE sections of 4 KiB over pages PS4 of 16 KiB

[English](INCREMENT_05.md) | [Español](INCREMENT_05-es.md)

The load of DLL and subsequent import resolution is documented in [increment 6](INCREMENT_06.md). This document retains the above evidence.

<a id="cambio-de-plataforma"></a>


## Change of platform

The charger now accepts section alignment of 4 KiB and retains the support of 16 KiB. Valid `SizeOfImage` and logical ranges using that alignment; the host reserve is rounded to pages PS4. The relationship between alignment and headers was contrasted with [PE specification](https://learn.microsoft.com/en-us/windows/win32/debug/pe-format).

The mapper is preparing a physical page plan. Each occupied page is committed and put to zero only once before copying the sections; So one section does not delete bytes from another that shares page. Then it applies relocations and the binding of read/write permissions needed on each physical page.

The image's IA- 32 bytes are used as input data to the translator: they are not run directly in x86 - 64 mode. This is why the original image pages do not receive EXEC; the generated host code lives in the separate caches JIT RX. This also applies to images of 16 KiB. There are no RWX image pages to accommodate the code and data mix.

The logical permissions Windows remain separate: R headers, RX code, RW data and R sections according to their attributes. The dispatcher records logical ranges without overlaps and the instruction view only accepts executable sections. Physical protection is broader when several logical regions share a page; **the isolation of 4 KiB is tested by software**, not by a `mprotect` of 4 KiB that the backend does not offer.

`shared_pages` has pages with several contributors and `widened_pages` those that contain a logical region without writing next to another scribable. They are the meters of the applied mapping plan, not an independent hardware consultation. The 4 KiB fixture has two shared pages and two with extended permissions.

This increment only changes our application. It does not add patches, syscalls or capabilities to shadPS4. The actual PS4 validation remains pending, depending on hardware availability.

<a id="accesos-de-fallback"></a>


## Fallback access

The dispatcher now checks the full range of memory operands before calling hostexec. Allows ADDPS without prefixes and LDMXCSR/STMXCSR with explicit operands; requires reading of 16 bytes, reading of 4 bytes, or writing of 4 bytes, respectively. It runs adjacent regions and rejects any part of the interval that lacks the requested permit, including overflow outside 32 bits. The high reserved bits of the LDMXCSR operation are rejected.

Other forms of fallback are not supported until they have audited their operands; they are not executed without a check. The direct call to hostexec in previous diagnoses remains a test with reliable operands and is not the API of the dispatcher for applications. This does not implement all the FP exceptions and does not even convert the errors into Windows exceptions.

<a id="pruebas-nuevas"></a>


## New tests

`minimal4k32.exe` is built from the same `minimal.c` of the previous increment, changing `SectionAlignment` to 4 KiB. It preserves BSS, the pointer and the five HIGHLOW relocations. The original fixture of 16 KiB is still compiled and tested.

| Caso |Verification|
|---|---|
| `pe-fourk-preferred` |Run the input in `0x30000000`, return 42 and process ends with 42|
| `pe-fourk-relocated` |Run in `0x34000000`, apply five relocations and end with 42|
| `pe-subpage` |Two scriptures prohibited by hostexec and two by the issuer, a valid writing and code rejection from data|

The permit test loads a real image and uses diagnostic instructions to try to write on your code and cross from RW data to an R. section It is found that the destinations do not change and the EIP is kept in the rejections. Only valid writing comes to run a stub hostexec. This instruction test is not presented as execution of another EXE input.

The previous cases of rejection continue to happen. The unadmitted alignment mutation now uses 2 KiB: a valid alignment of 4 KiB should no longer be rejected. Truncated file tests and mutations with sanitizers are performed on both fixtures.

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
    -Cases pe-fourk-preferred,pe-fourk-relocated,pe-subpage -TimeoutSeconds 25
```

The runner identifies and conserves both EXE by SHA256. Without `-Cases` it runs the extended matrix of 37 diagnoses.

<a id="evidencia-preservada"></a>


## Conserved evidence

The [Fork report](../reports/increment5-fork-final/report.json) records **33 approved, four blocked and zero fallos/timeouts**. The previous 34 cases keep their results. The same cases of sysarch, the POSIX import of TLS key erasing and the two of the isolated FP issuer remain blocked.

The [4 KiB in Windows fixture](../reports/increment5-fork-final/host/windows-pe32-fourk.json) also returns 42. His SHA256 is `fa5da821add741a82036f74f4b1131a181f91df1335e500bbb3f4b21dbb254a1`. The [parser with sanitizers](../reports/increment5-fork-final/host/pe32-parser.json) traverse 5.606 truncations and 8.220 mutations per fixture: 11.212 truncations and 16.440 total mutations, no errors detected in this campaign.

The snapshot contains both EXE, own sources, hashes, logs and manifests of the same fork `c6de833f6bec304b6f08c37520428ba2ed147a1a`. The attempt to extend the issuer's checks is kept in `reports/increment5-smoke-initial`; the final validation uses the ELF identified in `increment5-fork-final`.

The [official](../reports/increment5-official-final/report.json), using the same ELF and both EXE, records 15 approved, 21 blocked and a failed, without timeouts. The three new cases are blocked in the publication of the JIT RX code. The [comparison by case](../reports/increment5-fork-final/comparison.json) also retains the hashes of both fixtures.

The three new cases pass with the final ELF in three independent executions: `reports/increment5-smoke`, the complete matrix and `reports/increment5-repeat`. They end with their expected codes, without stubs active reserves.

<a id="siguiente-incremento"></a>


## Next increment

Load of a own PE32 DLL and resolution of imports/exports real, with a call between modules that runs the IAT. It shall be a test of link between own modules; it will not amount to having kernel32, ntdll or Wine integrated. You will follow the initialization of Wine, file APIs and threads, exceptions Windows and real console compatibility.
