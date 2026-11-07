<a id="incremento-1-memoria-administrada-y-fork-reproducible"></a>


# increment 1: administered memory and reproducible fork

[English](INCREMENT_01.md) | [Español](INCREMENT_01-es.md)

## Backend PS4

The backend keeps a process-protected mutex record. Each reservation receives an identifier that is not reused, and each page of 16 KiB retains its commitment status and its registered permissions. The copies of `PwVmRegion` remain valid until the reservation is released; reuse the output variable for another reservation does not invalidate a copy kept by the caller.

Other or altered regions, expired references, out-of-limits ranges, overlapping commitments and changes of protection on uncommitted pages are rejected. The kernel call failures do not advance the status of the record. This record does not make an atomic a defective kernel implementation: the injection failure tests verify the backend status and the OpenOrbis tests verify the observed emulator behavior.

`pw_vm_ps4_stats` allows to check reservations, reserved bytes and committed bytes. The backend still uses flexible memory; the direct memory and granularity emulation Windows of 4 KiB correspond to a later stage.

New evidence:

- Host WSL: reserve/map/protect/unmap failures, invalid ranges, overlap, copies, reuse of addresses and 400 concurrent cycles. Executed with AddressSanitizer, UndefinedBehaviorSanitizer and leak detection.
- OpenOrbis: `vm-ownership`, `vm-stress` and `vm-enforcement`. The latter checks real errors of read/write and does not agree with the permission declared by the emulator.
- Translator: llamadas/retornos and stack; arithmetic x87 and whole SSE2 operations; preservation of host FP control; explicit retranslation of changed code.
- Closing: different expected results for `exit(0)` and `exit(7)`.

The retranslation test is not yet valid for automatic cache or code invalidation that is modified during its own execution.

<a id="fork-de-shadps4"></a>


## shadPS4 Fork

The fork is local, without publication or modification of `upstream/shadPS4`. Their base, commons and patches are in `fork.lock.json`; The portable tools are verified with `fork-tools.lock.json`.

The three compiled and tested patches correct:

1. The RAM backup views in Windows allow execution from its creation and are immediately restricted to the required permissions before returning the mapping. This allows RW → RX back without permanently granting RWX. The external file mapping retains its own treatment.
2. The closing of the guest uses the existing `quick_exit` route and retains its output code.
3. The conversion of permissions tests the writing bit individually. Using `True(prot & ReadWrite)` granted writing even when only reading was requested.
4. The access handler monitored by the GPU check the mapping permissions before retrying. A really prohibited writing must reach the guest's exception handler; retry indefinitely caused a timeout.

The first patch brings together the corrections of executable views and closure. The third party avoids the bug loop; it does not include exceptions for this programme.

The independent reproduction of Windows is in `tests/windows-view-protection.ps1`: a view created as RW makes error 87 when moving to RX; a view with running capacity, first restricted to RW, allows the transition. This reproduction does not replace the complete fork test.

<a id="construcción-y-evidencia"></a>


## Construction and evidence

Prerequirements: Visual Studio with tools C + + x64 and Windows SDK; WSL with OpenOrbis and `p7zip-full` to extract portable tools.

```powershell
./tools/bootstrap-fork-tools.ps1
./tools/prepare-shad-fork.ps1
./tools/build-shad.ps1 -Jobs 6
```

The builder generates `build/shadPS4-win/build-manifest.json` with commit, patches, executable hash, tool versions and submodule reviews.

```powershell
$revision = (Get-Content fork.lock.json -Raw | ConvertFrom-Json).commit
./tools/run-probes.ps1 -Emulator build/shadPS4-win/shadps4.exe `
    -EmulatorKind fork -EmulatorCommit $revision `
    -BuildManifest build/shadPS4-win/build-manifest.json -TimeoutSeconds 30
```

To check the host backend, run `bash tools/test-vm.sh` in WSL. To verify the classification of results, run `./tests/report-classification.ps1` in PowerShell.

The initial reference remains at `reports/baseline`. The final official matrix is preserved in `reports/increment1-official-final`: 13 approved, 8 blocked and 1 failed. It is a different matrix from the initial one; compare only the number of approvals between the two does not measure regressions.

The fork matrix is in [your report](../reports/increment1-fork/report.json): **18 approved and 4 blocked**, No faults, no timeouts. Use exactly the same ELF as the final official matrix (SHA256 recorded in both reports). The [comparison by case](../reports/increment1-fork/comparison.json) records:

| Caso |official emulator| Fork |
|---|---|---|
| `generated-code` RW→RX |Blocked|Approved, return 42|
|`translator` in RX|Blocked|Approved, EAX = 42|
| `vm-enforcement` |Failed|Approved, recovers two real failures|
| `process-exit-zero` |Blocked|Approved, host ends with 0|
| `process-exit-seven` |Blocked|Approved, host ends with 7|

Commit tasted: `c6de833f6bec304b6f08c37520428ba2ed147a1a`. The compilation manifesto and the set patches accompany the fork report. `tests/fork-patches.ps1` reconstruct your tree from the base using an isolated Git index and verify that it matches the commitment published in the local manifesto.

Two additional rounds of six critical cases pass complete in new processes: `reports/increment1-repeat-1` and `reports/increment1-repeat-2`. They include RW → RX, effective permissions, RX translator, reservation and output property 0/7. Along with the complete matrix, there are three independent executions of each of these cases; do not amount to application stability tests Windows.

The dedicated closure tests require an end to no assertions; the historical exception that separates the result of a platform test from the closing failure does not allow approval `process-exit-zero` or `process-exit-seven`.

<a id="fronteras-que-siguen-pendientes"></a>


## The remaining remaining borders

`sysarch` / FS/GS and the POSIX import of `pthread_key_delete` are still blocked. The adapter you use `scePthreadKeyDelete` passes, with TLS and real destroyers. The tests of `LDMXCSR` and `ADDPS` record that the linked emission route does not yet run them. The complete runtime needs to integrate the remaining execution routes of prospero-win before using that evidence to affirm Wine compatibility.

Harness requires a single block fixture to be translated completely: to accept only your prefix can no longer appear as execution of all instructions. The errors observed during this extension are also preserved in `reports/increment1-fp-frontier`.

This increment does not yet integrate Wine, WoW64, GDI or DXVK, and does not validate PS4 hardware.

<a id="siguiente-incremento"></a>


## Next increment

1. Seal FS/GS with minimum cases of reading, writing and thread change; define the coexistence between TLS of the host and TEB of Windows before integrating Wine.
2. Integrate the remaining routes of the translator and extend PIC control instructions, exceptions and cache coherence; keep the blocks until they are executed.
3. Carte Unix initialization of Wine and load PE32, starting with `console32.exe`. The objective will be to check calculation, file, thread and output code in a new process, before moving to GDI.
