<a id="incremento-3-dispatcher-común-de-cpu"></a>


# increment 3: common dispatcher CPU

[English](INCREMENT_03.md) | [Español](INCREMENT_03-es.md)

The load and subsequent execution of a PE32 own is documented in [increment 4](INCREMENT_04.md). This document retains the previous evidence.

<a id="implementación"></a>


## Implementation

`platform/ps4/pw_cpu_ps4.c` adds an execution context with IA- state 32, block engine, cache and hostexec of prospero-win. It is a self-contained PS4 layer on the same set upstream review; does not change these sources.

Each step calls first at `pw_x86_engine_step`. Only `PW_ERR_UNSUPPORTED` enables the fallback of an instruction: it materializes deferred lags, synchronizes the FP state and gets bytes in the current EIP before calling hostexec. Memory and source errors spread. The code already executed by a partial block is not repeated when an unsupported instruction is reached.

The context belongs to the thread that creates it. The operations from another thread return `PW_ERR_STATE`, without running or destroying the context. Direct access to the state is for the owner; is not a safety barrier between threads C.

`pw_cpu_ps4_run` receives a stop border and a step budget. Exhaust the budget returns `PW_ERR_LIMIT`. The border is only a limit of the caller; does not simulate `ExitProcess`, a syscall or a return of Wine. The limit counts steps of the dispatcher and does not replace an external process timeout.

The engine reserves 256 KiB code and 64 cache inputs; hostexec reserve 64 KiB. Chaining, reencoder and FP native to the reencoder remain deactivated. The large context is also reserved with the backend PS4. Thus their release does not depend on the libc route that invoked the stub `madvise` in shadPS4. This real block is retained in `reports/increment3-allocator-blocker`, although the guest's calculations already produced the values expected in that attempt.

<a id="casos-nuevos"></a>


## New cases

| Caso |Validation|
|---|---|
| `dispatcher-mixed` |Run translator → hostexec → translator → hostexec → translator, twice; Verifies EIP at each crossing, cartage, lags, XMM, MXCSR, TEB and result 42|
| `dispatcher-fault` |Rejects a table permissions writing, retains data and EIP, and records zero fallback attempts|
| `dispatcher-stops` |A loop runs out exactly three steps; HLT is not supported; an off-range source returns `PW_ERR_NOT_FOUND`|
| `dispatcher-owner` |A foreign thread cannot obtain status, run, consult statistics or destroy; the owner continues to run correctly|

The mixed sequence calculates CF = ZF = 1 with whole arithmetic; `LDMXCSR`, load SSE and `ADDPS` must keep those flags. `ADC` consumes the cartage and gets 42. The four floating results are written in memory and compared to exact values. It is also found that CW/MXCSR hosts are preserved. The second execution reuses three blocks and two stubs: six block executions, four instructions hostexec, three block compilations and two of stubs.

All cases release your reservations and check that there are no bytes left in the backend.

<a id="reproducir"></a>

## Reproduce

```bash
python3 tools/build.py --cc clang-14 --ld ld.lld-14
```

```powershell
$revision = (Get-Content fork.lock.json -Raw | ConvertFrom-Json).commit
./tools/run-probes.ps1 -Emulator build/shadPS4-win/shadps4.exe `
    -EmulatorKind fork -EmulatorCommit $revision `
    -BuildManifest build/shadPS4-win/build-manifest.json `
    -Cases dispatcher-mixed,dispatcher-fault,dispatcher-stops,dispatcher-owner `
    -TimeoutSeconds 25
```

Without `-Cases`, the runner includes these cases in the complete matrix.

<a id="evidencia-preservada"></a>


## Conserved evidence

The [Fork report](../reports/increment3-fork-final/report.json) records 26 approved tests and four blocked, no failures or timeouts. The results of the 26 cases of the previous increment are preserved: there are no changes of status in these cases. The four added to the dispatcher pass.

The preserved blocks are `sysarch` / FS/GS native, the POSIX import of `pthread_key_delete` and the two exclusive emitter cases for `LDMXCSR` and `ADDPS`. These last instructions are executed by hostexec in the mixed sequence; the classification of its tests of the isolated issuer was not changed.

The fork retains the commit `c6de833f6bec304b6f08c37520428ba2ed147a1a`; no patches of the emulator were added in this increment. The snapshot contains its manifests, logs, hashes of the binaries and the 17 sources/headers/herramientas own identified by `build.json` in `inputs/`.

The [official](../reports/increment3-official-final/report.json), with the same ELF, records 13 approved, 16 blocked and a failed, without timeouts. The [comparison by case](../reports/increment3-fork-final/comparison.json) shows 13 state changes to approved fork. The four cases of the dispatcher are blocked in the official emulator when publishing RX code.

The four new tests pass in three independent executions with the same ELF: `reports/increment3-smoke`, the complete matrix and `reports/increment3-repeat`. They do not invoke stubs and each process ends with 0 code.

<a id="límites-y-siguiente-paso"></a>


## Limits and next step

The engine source must remain mapped and immutable during the life of the context. The code invalidation and the reboot of cache by exhaustion have not been connected: these limits are returned to the caller. The route hostexec retains the restriction of the previous increment: reliable memory operands, without general conversion of host failures to exceptions Windows. It should not be used as an arbitrary program performer in this state.

The next step is a minimum PE32 charger: validate headers and sections, apply relocations and run the entry of a own EXE without imports. The real imports, initialization of DLL, files and threads of Win32 need the integration of Wine later. This dispatcher does not include Wine nor does it yet show execution of an EXE.
