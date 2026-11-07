<a id="incremento-2-teb-de-32-bits-y-ejecución-hostexec"></a>


# 2 increment: 32 bit TEB and execution hostexec

[English](INCREMENT_02.md) | [Español](INCREMENT_02-es.md)

The posterior common dispatcher is implemented and documented in [increment 3](INCREMENT_03.md). This document retains the evidence of the increment 2.

<a id="cambio-realizado"></a>


## Change made

The ELF now links `pw_x86_hostexec.c` to the same fixed revision of prospero-win. It is the actual route of execution of IA- 32 instructions by stubs x86 - 64; no instructions were replaced by results calculated by the diagnosis. The backend PS4 publishes its stubs by changing pages from RW to RX.

`native/translator_runtime.c` adds four tests and maintains the previous tests. `tools/build.py` also records hashes of sources and headers in `out/build.json` to identify the diagnostic inputs.

<a id="separación-de-tls"></a>


## TLS separation

There are three different contexts in the proven execution:

1. The emulator's runtime Windows uses its TLS host. The implementation of `RetrieveTcbPointer` in the fork obtains the TCB of PS4 from the TLS slots of Windows by GS.
2. The OpenOrbis program uses the PS4 TCB. Its native reading `fs:0` is treated by the emulator's instruction patches.
3. The translated IA- 32 instructions use `PwX86State.fs_base` and `fs_bytes`. The test TEB lives under 4 GiB, separated from the TCB OpenOrbis and TLS from Windows.

The first two statements describe the fork code set at `src/core/cpu_patches.cpp` and `src/core/tls.cpp`. They're not a hardware measure PS4.

The PS5 adaptation of Wine in the upstream patch `wine/patches/0500-ntdll-ps5-signal-context-and-segment-bases.patch` keeps FS for libc and uses GS for the 64 bit TEB. Apply that to the runtime Windows of shadPS4 will require virtualizing the guest's GS accesses or demonstrating another equivalent route. The host GS was not changed nor was it implemented `sysarch` returning a fictitious success. As a reference ABI, the [FreeBSD code](https://cgit.freebsd.org/src/tree/sys/amd64/amd64/sys_machdep.c?id=fdee312d0c97cf6d907eec0b96efd51bfc9a7567) implements the operations of segment bases; That doesn't prove his behavior in a PS4.

<a id="pruebas-nuevas"></a>


## New tests

| Caso |Behavior proven|
|---|---|
| `translator-teb` |64 executions; read `fs:[0x18]`, `fs:[0x30]`, write `fs:[0x34]`; conserves lags, native TCB, `errno` and pthread key|
| `translator-teb-threads` |Two strands with different native TEB and TCB bases, 64 yarn-based performance synchronized by condition, independent status and release of reserves|
|Both TEB cases|They reject a writing outside the TEB even if their page is mapped; refuse base overflow + offset before access|
| `hostexec-fp` |Run `LDMXCSR` and `ADDPS`, check four exact results, EIP, Lands, MXCSR guest and store CW/MXCSR hosts|
| `hostexec-cache` |Reuse the stub without recombinant when repeating bytes; by changing the immediate on the same PC compiles again and gets the new value|

The TEB data are a minimum own fixture. They do not constitute a TB created by Wine or validate `NtCurrentTeb`, SEH or DLL initialization of Windows. The mutex/condici barrier requires both threads to establish their `errno` before checking in each iteration; a failure aborts and awakens the other thread. The FP test uses known and mapped operands: it does not value the safety of the route hostexec against arbitrary directions or malicious instructions. The cache test covers the byte check of stub hostexec, not the complete invalidation of blocks, links or modified code in operation.

The cases `translator-fp-control` and `translator-fp-add` retain their original meaning: they test the block emitter only and remain blocked. The hostexec cases show a route available for these instructions, but it still needs to be connected to the WoW64 dispatcher and checked for state transitions.

<a id="reproducir"></a>

## Reproduce

In WSL, from the root of the project:

```bash
python3 tools/build.py --cc clang-14 --ld ld.lld-14
```

In PowerShell:

```powershell
$revision = (Get-Content fork.lock.json -Raw | ConvertFrom-Json).commit
./tools/run-probes.ps1 -Emulator build/shadPS4-win/shadps4.exe `
    -EmulatorKind fork -EmulatorCommit $revision `
    -BuildManifest build/shadPS4-win/build-manifest.json -TimeoutSeconds 25
```

The emulator retains the three patches of the previous increment. No new emulator patch is necessary for these four tests.

<a id="resultado-preservado"></a>


## Result preserved

|Environment, same ELF|Approved|Blocks|Failed| Timeouts |
|---|---|---|---|---|
| shadPS4 oficial v0.20.0 | 13 | 12 | 1 | 0 |
| Fork `c6de833f6bec304b6f08c37520428ba2ed147a1a` | 22 | 4 | 0 | 0 |

Full reports: [official](../reports/increment2-official-final/report.json), [fork](../reports/increment2-fork-final/report.json) and [comparison by case](../reports/increment2-fork-final/comparison.json). The results of the 22 above cases are kept in the fork. The four new tests pass there and are blocked in the official emulator when publishing RX code. The official judgement of effective permits is still recorded, without concealing it.

Snapshots include logs, binary hashes and exact `inputs/` own sources, contrasted against `build.json`. The fork report also includes the emulator compilation manifesto and the locks of its patches and tools. The above reference and intermediate attempts are kept separately; This table uses the completed directories in `-final`.

The four new tests also pass in two additional rounds with new processes: `reports/increment2-repeat-1` and `reports/increment2-repeat-2`. Each has four approvals, no blockages or timeouts. This gives three independent executions per case with the final ELF, including the complete matrix.

<a id="siguiente-paso"></a>


## Next step

Integrate the block dispatcher and hostexec with own yarn states, and test a sequence that passes from one route to another without losing lags, FP or EIP. After that, separate the minimum load PE32 from the initialization Wine: a non-import PE can check load, relocations and input; The complete fixture `console32.exe` also requires the real services of Wine for file and thread. The GS native route Wine of 64 bit, its signals and its ABI remain pending.

This increment does not run an EXE of Windows or value a real PS4 console.
