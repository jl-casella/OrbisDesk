# Process-family probes for fixed-base launchers

[English](PROCESS_FAMILY_PROBES.md) | [Español](PROCESS_FAMILY_PROBES-es.md)

These probes reproduce the process contract needed by launchers whose child must run while the parent remains alive. They do not implement a separate-process backend or change the existing guest launcher. The first investigation used dev `a17f5eb` and the unmodified local W303 product ELF.

**Current handoff, 2026-11-11:** P007 now verifies a fixed-base freestanding helper and bidirectional descriptor transfer on physical 12.50 hardware. The next gate is the OpenOrbis SELF bootstrap in P009/P010, not another P005 mapping-hint test. The main product remains W303. See the revised plan at the end of this guide.

**Update, 2026-11-12:** phases B–D (a separate process running Wine as a client of the title's wineserver, with windows, input and real `CreateProcess` handles) are in [Separate Windows processes](POP_SEPARATE_PROCESS.md).

## Own Win32 reproduction

[process_family.c](../fixtures/win32/process_family.c) produces two PE32 executables with preferred base `0x400000`, `IMAGE_FILE_RELOCS_STRIPPED`, and no relocation directory. The builder verifies these properties. They import only kernel32 and use no CRT startup.

The parent creates a fresh named shared mapping, publishes its PID and image base, and creates the child suspended. After resuming the child, it advances a heartbeat while waiting for a verified exit code. The child opens the mapping, checks that its PID differs, opens the parent's process handle, and requires the parent to remain alive and advance the heartbeat. Both record their actual loaded bases. Successful evidence includes `family_verified`, `child_verified`, parent exit 0 and child exit 42.

This tests real process creation, suspended creation/resume, environment inheritance, named memory, concurrent parent progress, process identity and wait/exit behavior. It is a synthetic contract inspired by the [fixed-base launcher finding](investigacion-wow64-en-explorer.md#363-prince-of-persia-dos-exe-con-base-fija), not a recreation of the game's unknown `PrinceSM` protocol. A relocatable parent at `0x24000000` is also built as `family-control.exe` to distinguish fixed-base conflicts from other process limitations.

## Native export inventory

[process_capabilities.c](../native/process_capabilities.c) lists loaded modules and searches their exports for several process-related names. It writes `/data/process-capabilities.jsonl` and invokes none of the discovered functions. It does not try `fork`, `rfork`, payload injection, privilege changes or application replacement.

Export discovery is intentionally narrow: absence from the loaded-module list does not establish absence from the PS4 kernel, unloaded libraries or the emulator's separate HLE symbol table. Finding a symbol would not prove that the call works either. `discovery_only=true` and `native_child_started=false` must not be reported as a successful native spawn.

## Build and run

Use the existing configured WSL/OpenOrbis and MinGW environment described in [AGENTS](../AGENTS.md). Outputs are isolated under `build/process-probes` and `out/process-probes`; no product runtime is rebuilt.

```sh
python3 tools/build-process-probes.py
python3 tools/run-process-probes.py --target host-wine --timeout 120
python3 tools/run-process-probes.py --target shad-capabilities --timeout 15
python3 tools/run-process-probes.py --target shad-family --build W303 --timeout 45
```

`host-wine` uses the pinned Linux Wine build, a new private prefix and its own wineserver. Prefix initialization may take over 45 seconds; the recorded successful reference took about 86 seconds, including initialization. It is not a runtime performance benchmark. A native Windows Python can alternatively run `--target windows`; local Windows policy/loading behavior may independently refuse a nonrelocatable image.

`shad-family` verifies the product eboot and fork binary against their build manifests, copies the existing runtime into a private `/var/tmp/orbisdesk-process-*` directory, stages the fixtures and selects the parent through that copy's `orbisdesk/launch.txt`. It also sets a private `XDG_DATA_HOME`, with the emulator's default data path linked to the same copy, so a restart losing CLI mounts cannot escape into the regular emulator profile. Copy preparation is separate from the bounded emulator run and can take several minutes on a Windows-mounted workspace. It never changes console data or the source product runtime. Core dumps are disabled for launched Linux processes.

For a bounded retry of the same private data:

```sh
python3 tools/run-process-probes.py --target shad-family --build W303 --timeout 45 \
  --resume-from reports/process-probes/REPLACE_WITH_RUN/report.json
```

Resume checks the prior fixture identities, product ELF, emulator identity and private-directory location. Previous fixture records are archived before the next run. A real failed first-start probe may leave its existing once-per-build marker, affecting subsequent startup; record that distinction. Do not invent a successful native32 marker. Missing temporary data cannot be resumed. `/var/tmp` is used because this WSL setup can clear `/tmp` when its session stops.

Add `--control` to run the relocatable parent. Each invocation creates a separate report directory with hashes, command, emulator/product manifests where applicable, timeout/exit and the parent/child JSONL records. The JSON's `status`, `family_contract_passed` and capability-discovery result are separate. A completed inventory exits successfully as a diagnostic while its family status remains blocked. Host reference success is never native PS4 acceptance. A successful process contract alone does not prove any game starts.

## Initial observations

Evidence is under `reports/process-probes/` (local, ignored):

| Run | Observation |
| --- | --- |
| `20261111T024546910018Z` | Fresh host Wine prefix exceeded 45 seconds before the fixture; retained as a timeout. |
| `20261111T025026571221Z` | Host Wine reference passed: parent PID 32, child PID 320, both at `0x400000`; shared memory, parent progress and expected exit codes verified. |
| `20261111T024546910069Z` | Fork export inventory completed, one loaded module, no matches for the searched names. No native process was started. |
| `20261111T024619495646Z` | Fresh W303 in the fork timed out before fixture entry, at its native32 compatibility probe after mapping `0x30000000`. No parent/child records. |
| `20261111T025247883640Z` | Same first-start native32 timeout with persistent private data, bounded at 15 seconds. |
| `20261111T025535571801Z` | Reusing that actual attempt marker reached the fixed parent at `0x400000`. Its log stops at `create_child_attempt`; the product calls `switch_program`/LoadExec for the child. The emulator restart drops CLI mounts and falls back to its normal local user data, then aborts with stack-smashing output (exit 127). This older attempt was not isolated across restart; it touched local default-profile startup files, not PS4 data or the source product runtime. |
| `20261111T025859128715Z` | Retry with private XDG profile preserved isolation but timed out before launcher entry; no parent/child records and the new profile's log stayed empty. This does not supersede the earlier observed LoadExec behavior. |
| `windows-20261111T0247354026543Z` and `windows-control-20261111T0249160656069Z` | Native Windows refused the fixed image with error 623. The relocatable parent started and recorded error 623 when creating its fixed child; this does not invalidate the separately passing Wine contract. |

The fork's `sceSystemServiceLaunchApp` is a success-returning stub, `sceSystemServiceLoadExec` restarts the title, and its raw-syscall dispatcher does not implement spawn. `Emulator::Restart` also omits custom mounts when reconstructing its command line. None is a validated second-process backend. Do not turn a stub result or two manually launched emulator instances into a claim of PS4 multiprocess support.

Next: preserve any additional bootstrap results separately, then establish a real PS4 auxiliary-process loader/transport before wiring a per-program separate-process option into Wine. Until that prerequisite is demonstrated, the original shared guest path remains unchanged and the fixed-base launcher case is unresolved on PS4.

## P001: installable physical-console prerequisite check

Build with `python3 tools/build-process-hardware-probe.py`. The standalone package is `out/process-hardware-p001/OrbisDesk-Process-Check-P001.pkg`, title **OrbisDesk Process Check P001**, ID `ORBP00001`, version `01.00`. It does not replace OrbisDesk (`ORBW00002`) or the older probe titles. The builder validates the PKG and records executable/package/source hashes in `out/process-hardware-p001/manifest.json`.

P001 uses the existing CPU presentation sink and Orbis message-ABI adapter. It checks a scratch file mapped at two distinct addresses with `MAP_SHARED`, bidirectional visibility between those mappings, and an actual file descriptor transferred over a local Unix socket with `SCM_RIGHTS`. The receiver must successfully use the transferred descriptor. It also inventories loaded-module exports. Socket messages are nonblocking, and no process-creation export is invoked. No privilege changes, Wine execution, title relaunch, external listener or kernel payload is included.

The screen explicitly says **SECOND PROCESS: NOT TESTED** and labels IPC results **LOCAL**. These results are useful prerequisites, not proof of cross-process mappings, IPC or process creation. Each console run creates `/data/orbisdesk/process-p001/run-NNNN/report.jsonl` and removes only its own scratch file. The screen remains open for a photo; close the app through the PS4 menu afterward.

Fork validation `reports/process-hardware-p001/20261111T031337036221Z/report.json` completed in about 1.9 seconds: both mappings were coherent, descriptor send/receive and receiver I/O passed, and export inventory completed. No searched spawn exports were found in the loaded modules. The test runner stopped the persistent diagnostic after completion; exit -9 records that deliberate stop, not an app crash. Physical-console status is pending.

On 2026-11-11 the console was off. The package is ready; **no FTP transfer was attempted**. Its handoff is `out/process-hardware-p001/ftp-handoff.json`. Once the user confirms the console/FTP is on and its current address, upload only this diagnostic to `/data/pkg/OrbisDesk-Process-Check-P001.pkg`. Do not remove or replace the main `OrbisDesk.pkg`. Have the user install/start the diagnostic, send the result photo and close it, then retrieve its new JSONL report by FTP.

### Physical P001 result, 2026-11-11

The later transfer to `192.168.68.106:2121` completed and a full FTP readback matched package SHA-256 `694e2182c953109dfbb29b791375781d8f68e1561f59b6c29e630779b64a402a`. The user confirmed testing; the downloaded evidence is `reports/process-hardware-p001/physical/20261111T124733314388Z/run-0001/report.jsonl`, SHA-256 `6e8d2e4db40c281457eabac42611eae908a4445218fbeac54777c0423d8eb73b`.

- Both shared mappings, coherence and unmapping passed. This is still a single-process test of shared backing, not cross-process acceptance.
- Socketpair creation and descriptor send passed. Descriptor receive returned -1 with errno 45, and the diagnostic completed with a failed prerequisite. Do not mark all of P001 passed. The report does not identify whether the failure came from the kernel or adapter validation.
- The loaded-module inventory found `execve` in `libkernel.sprx` (handle 8193) and **`posix_spawn` in `libSceLibcInternal.sprx` (handle 2)**. Neither was called. This is a hardware finding absent from the fork inventory, and a concrete candidate to investigate; an exported name alone does not prove usable process creation.

For the next descriptor probe, compare P001 with the existing hardware-used `scm_duplicate` path in `platform/ps4/pw_wine_fs.c`: that path uses flags 0 and a receive control buffer twice `CMSG_SPACE(sizeof(int))`, whereas P001 uses `MSG_DONTWAIT` and a single-sized buffer. Capture the adapter/kernel failure stage and compare both variables independently before blaming descriptor passing generally. Separately establish the retail `posix_spawn` ABI and behavior before a bounded native parent/child attempt. No physical second-process capability is yet verified.

## P002: receive variants and a native child attempt

Build with `python3 tools/build-process-hardware-probe.py --build P002`. P002 uses the same diagnostic title `ORBP00001`, version `01.01`, and packages `/app0/process-child.bin` beside its parent. It updates P001, not OrbisDesk. The package and manifests are under `out/process-hardware-p002/`.

Five fresh socketpairs isolate the receive failure. Cases 0–3 retain P001's send flags; their receive flags/control capacities are `(0,24)`, `(0,256)`, `(MSG_DONTWAIT,24)` and `(MSG_DONTWAIT,256)` on this SDK. Case 4 uses send/receive flags 0 and capacity 256 as a production-style control. The builder instruments a private generated copy of `pw_wine_net.c` to record the failure stage, returned wire flags and control length. The production adapter is unchanged. An IPC worker keeps the display responsive; a call still pending after about 15 seconds is reported, without cancelling a thread inside a system call or proceeding to spawn.

The ABI review compared OpenOrbis's `spawn.h` with the [official FreeBSD 9.1 header](https://github.com/freebsd/freebsd-src/blob/releng/9.1/include/spawn.h) and [implementation](https://github.com/freebsd/freebsd-src/blob/releng/9.1/lib/libc/gen/posix_spawn.c). The six-argument interface agrees, but auxiliary object layouts differ: FreeBSD uses opaque pointer types while the SDK declares inline structures. P002 resolves the retail export and passes **NULL file actions and attributes** and an explicit empty environment. This avoids those layouts; it is not proof that Sony's implementation behaves identically. Return code and errno are recorded separately. No raw fork/rfork syscall or privilege change is attempted.

Native testing requires both `posix_spawn` and `waitpid` exports. A separate worker first calls the spawn API with a nonexistent image as a negative control, then requests the packaged child. The parent publishes a file-backed shared state with its PID and advances an atomic heartbeat. The child records its real PID/PPID, maps that state, rejects equal parent/child PIDs, and requires continued parent progress. It then exits with code 42. The parent verifies the reported child PID against shared state and requires a reaped exit code 42 before displaying **NATIVE CHILD: PASS**.

The child waits for progress for at most about three seconds after entering its probe. The parent polls child exit for about five seconds; its UI waits at most about 15 seconds for the overall spawn worker. A stuck spawn API is reported as pending: the worker is not forcibly cancelled, and API return itself cannot be guaranteed to obey a user-space deadline. Close a pending diagnostic through the PS4 menu. Any child startup or early-exit failure remains a failure, even when the API returned success.

Both processes also request an anonymous RW mapping with address `0x400000` as a **hint**, without MAP_FIXED. They write different markers. Only if both mappings actually land there does the parent check low-address isolation; otherwise that subtest is inconclusive. This does not replace the separate PE32 fixed-EXE test and does not overwrite existing mappings.

Logs are under `/data/orbisdesk/process-p002/run-NNNN/report.jsonl`, with `child.jsonl` and `state.bin` when the native branch reaches them. No graphics/audio service is opened by the child. Wine, game files and the OrbisDesk runtime remain untouched. A later process option still needs bootstrap, shared Wine-server semantics and graphics/input/audio integration; one passing native probe would not make PoP compatible.

Run `python3 tools/run-process-hardware-probe.py --build P002` for the short fork check. The current fork can validate IPC cases and the unavailable-export branch; it cannot validate the retail spawn call. The runner stops the persistent panel after `panel_ready` and records that deliberate stop separately from probe completion. Physical results must come from the console's own new run logs.

The final package passed the fork smoke run `reports/process-hardware-p002/20261111T130258266381Z/report.json`: all five local IPC cases completed successfully and native spawning was skipped because its exports were absent. On 2026-11-11 it was uploaded to `192.168.68.106:2121` as `/data/pkg/OrbisDesk-Process-Check-P002.pkg`; full FTP readback matched SHA-256 `a70d9e6cc5179df6d50461a8d1335bddb38dc14c927f952fe428f2f6fa46c2e9`. The archived P001 package was removed from that remote package directory only after its hash was checked; local P001 evidence remains. Physical P002 execution is pending user feedback.

### Physical P002: IPC cause isolated, spawn closed the app

The user's later run produced `reports/process-hardware-p002/physical/20261111T130746161012Z/run-0001/report.jsonl`, SHA-256 `70e6594719c29ecccc251bbcb7cf35723bce645cb8417d18cbdd53fd50013882`. Cases 0, 1 and 4 passed descriptor reception and receiver I/O. Cases 2 and 3 failed in **adapter flag validation**, not in `kernel_recvmsg`: both returned wire flags `128` (`0x80`) and control length 24 before the adapter generated errno 45. Buffer size did not explain this failure. The console echoed the requested `MSG_DONTWAIT` operation bit in the output flags.

The production adapter now excludes that echoed bit from event-flag validation **only when nonblocking was requested**. Unrequested or otherwise unknown bits still fail. `python3 tools/test-wine-recvmsg-flags.py` runs a focused host regression against production code with synthetic kernel replies: the reconstructed old behavior fails the first nonblocking case; the fix accepts it, preserves known truncation flags, and still rejects unexpected flags/control overflow and preserves EAGAIN. This is unit evidence, not a physical IPC pass for the changed code.

The native branch found both exports and created its worker, but the last spawn-stage record is `negative_spawn_enter`. There is no return record, real-child request, child log or panel completion. The user confirmed red IPC 2/3 followed by **the app closing**. No exact termination signal or fault address was captured. Do not describe this as a returned spawn error, successful process creation or a proven timeout. `state.bin` could not be retrieved by FTP; the absence of a successful retrieval does not establish that it was never created. Further direct spawn attempts are withheld pending inspection.

## P003: validate the flag fix and inspect without invoking spawn

Build with `python3 tools/build-process-hardware-probe.py --build P003`; version `01.02`, same diagnostic title. The five IPC cases use the corrected production adapter. P003 does **not call `posix_spawn`**, package its child helper, perform a raw fork/rfork or change privileges. It displays **SPAWN: NOT CALLED** separately from whether a code snapshot was saved.

For an exported `posix_spawn`, it obtains that module's segment information and verifies that the address falls inside a readable segment. It writes at most 512 bytes, bounded by the segment end, to `posix-spawn-HANDLE.bin`, with address/segment-offset metadata in `report.jsonl`. No address is made readable or executable; unavailable information leaves the snapshot unavailable. This reads a small portion of an already loaded function, not the whole firmware module. Captures remain local ignored research evidence and must not be committed or distributed as project source.

Logs are under `/data/orbisdesk/process-p003/run-NNNN/`. The next review should disassemble the captured entry and establish why the P002 call terminated before any further native creation experiment. A five-case IPC pass here would validate the adapter correction locally on PS4; it would not establish cross-process IPC, Wine integration or PoP compatibility.

P003 completed the fork smoke run `reports/process-hardware-p003/20261111T131656645434Z/report.json`. The package uploaded to `.106:2121` on 2026-11-11 was verified by full readback, SHA-256 `6b5eb31878d8dbb01271310f02f144269c6e7b49550a0561cb6bd5c1a3555cc7`. The previous remote P002 package was removed after checking its archived hash. Physical P003 validation remains pending; the main OrbisDesk package was not rebuilt or replaced by this adapter-source change.

### Physical P003: local IPC fix validated

Evidence: `reports/process-hardware-p003/physical/20261111T132421573148Z/`. All five cases passed receive and descriptor I/O, including the two previously failing nonblocking cases. The report SHA-256 is `62bdef6e72cffacc15c5cb685341fd319a1d3220f56451c3f522fe4c601a35c4`. This validates the adapter correction for these local PS4 descriptor transfers; cross-process IPC remains untested.

The 512-byte entry capture was saved from module 2; SHA-256 `e9c7fe177c06966340f3283eb2905f1f2dbaeb7e8e7043efe7fcab00581ef452`. The disassembly and analysis remain with the ignored evidence. The entry wrapper passes six arguments into a local helper. That helper branches on an unresolved call's -1/zero/positive result; the zero-result path eventually calls another target with argument 127, followed by UD2. This matches the shape of FreeBSD's vfork/exec spawn implementation. It does not identify the actual imported targets or prove which path P002 executed. The P002 closure cause remains unproven; that inference alone is insufficient technical justification to repeat the call.

## P004: inspect call targets, without executing them

Version `01.03` updates the same diagnostic. Build using the P003 run folder:

```sh
python3 tools/build-process-hardware-probe.py --build P004 \
  --inspection-source reports/process-hardware-p003/physical/20261111T132421573148Z/run-0001
python3 tools/run-process-hardware-probe.py --build P004
```

The builder disassembles the reference and records direct-call targets outside the captured window before the first UD2, up to eight targets. This reference yields seven: imported-call thunks plus two nearby helpers. The generated header contains only relative offsets and a reference fingerprint, not firmware code. The manifest records the reference SHA-256 and offsets; fresh environments need their own matching console capture to reconstruct this diagnostic.

At runtime P004 checks the live 512-byte entry against that FNV-64 identity guard before using the plan. This is a consistency guard, not cryptographic authorization. Changed/unreadable references are skipped. Each target must be inside a readable module segment before saving 32 bytes. Only a recognized `FF 25` indirect-jump stub is used to locate a GOT slot; the slot must also be readable before its pointer is read. The pointed-to target must belong to a readable loaded-module segment before saving 64 bytes. P004 also records the addresses of available related exports such as `vfork`, `execve`, `_exit` and `__error` for offline comparison. It calls none of those exports.

Logs add `call_inspection` and `related_export`; captures are `call-N-stub.bin` and, where resolved/readable, `call-N-target.bin`. Missing or unresolved targets are not treated as successful identification. As with P003, these small captures remain ignored local research evidence. The native child and Wine are not launched. The objective is to identify the first internal call and the error/exit path before deciding whether another native process attempt is justified.

P004 completed fork smoke run `reports/process-hardware-p004/20261111T133256904423Z/report.json`. On 2026-11-11 it was uploaded to `.106:2121` and full readback matched SHA-256 `4b1be9181c9e5cb2d29148086558199e6e9a4249a4f948e18023b1ae3f54d7f1`; the old remote P003 package was removed only after hash verification.

### Physical P004: invalid first indirect-call destination

The console completed all five local IPC cases, matched the P003 entry fingerprint and reached `panel_ready` without calling spawn. Evidence is archived under `reports/process-hardware-p004/physical/20261111T134733398802Z/`; the report SHA-256 is `5b6c1b5344e7110d49e113c1fe1f7bfae7ed8740ad37587ccf029e2dcf926ed6`. Offline analysis verified every downloaded file against the fetch manifest and saved disassemblies and `analysis.json` beside the evidence.

The first helper call reaches an `FF 25` indirect-jump thunk at `0x8000906a8`, whose GOT slot at `0x8001c81d8` contains **`0xeffffffe0000005f`**. This is a noncanonical x86-64 address, not a callable function or a readable loaded-module destination. The inspector correctly did not dereference it. Other captured slots match exported libkernel `__error`, `execve`/`_execve` and `_exit`; two nearby targets are local helpers. The first import's symbol name and the origin of the invalid value are not established. Its position resembles the vfork call in FreeBSD, but that resemblance does not identify the import.

This is a strong static explanation for P002 closing before `negative_spawn_return`: reaching the same jump would fault. P004 is not an execution trace of P002, and no P002 fault address/register context was captured, so the precise historical exception remains unverified. There is no evidence of a child being created, nor of the earlier hypothesized child-side exit 127 actually being reached.

**Next prerequisite:** establish a supported PS4 process-creation backend and its bootstrap requirements before another creation test. Exported `posix_spawn` is unusable through this captured path in the tested title environment. Do not repair its GOT by guessing an address, substitute raw fork/rfork, or mark native process support available. Per-program separate processes and PoP launcher/game coexistence remain blocked; the existing shared-process mode is unchanged. The validated local IPC fix is useful independently, but does not demonstrate cross-process IPC or a rebuilt main OrbisDesk package.

## P005: observer and a freestanding external helper

P005 (`01.04`, same diagnostic title) prepares the first external-loader coexistence experiment. It does not bootstrap the loader, invoke retail spawn, fork the title or execute Wine. Build and check the unavailable-loader branch:

```sh
python3 tools/build-process-hardware-probe.py --build P005
python3 tools/run-process-hardware-probe.py --build P005 --timeout 20
python3 tools/test-process-loader-helper.py
```

The OpenOrbis observer connects only to loopback port 9021. If a compatible loader is present, it sends the packaged `process-helper.elf` and records its output in `loader-stream.log`. Connection failure remains **LOADER UNAVAILABLE**, never successful process creation. Sending the ELF is a launch request, not proof of readiness. The title continues updating its heartbeat while its network worker runs. Its bounded UI can finish even if the worker has not returned; closing the title remains the final recovery action.

The [helper](../native/process_loader_helper.c) is a separate freestanding PIE with no undefined imports, SDK startup objects, kernel-patching initialization, graphics or audio. Its entry realigns its stack and uses a small explicit Orbis syscall wrapper for userland files, memory, identity, sleep and exit. It never performs a process-creation or kexec syscall. [Protocol structures](../native/process_loader_protocol.h) have compile-time size checks. The request selects a fresh run directory and random token; the token rejects stale sessions but is not authentication against privileged local code.

The helper maps that run's state file, validates its token and observer identity, records real PID/PPID and requires both observer progress and the observer acknowledging its distinct PID. The observer independently requires helper progress. A passing **COEXISTENCE HANDSHAKE** requires this bidirectional exchange and helper completion code 42. This code is self-reported in shared memory; the title does not pretend it reaped an external loader's child. **NATIVE EXIT STATUS: NOT REAPED BY TITLE** remains explicit. A later supervisor must establish native disappearance and real exit status separately.

Each side also requests `0x400000` as a non-destructive mmap hint, without MAP_FIXED. Low-address isolation passes only if both actually obtain that address and retain different markers. Otherwise it is inconclusive. This is not yet two Windows EXEs at their fixed bases. These experiments start testing cross-process mappings, but do not validate cross-process SCM_RIGHTS or the Wine server connection.

Run evidence is `/data/orbisdesk/process-p005/run-NNNN/`: `report.jsonl`, `state.bin`, and, if reached, `helper.jsonl` and `loader-stream.log`. `request.bin` in the parent directory identifies the current run. Probe files/directories allow a separate helper identity to access them and contain no product/user data. Do not use these permissive diagnostic modes as product defaults.

### External loader artifact and deployment boundary

[build-process-loader.py](../tools/build-process-loader.py) builds a separate GPL-3.0-or-later research artifact using [pinned archives](../tools/process-loader.lock.json). It does not execute or deploy it. The SDK binary release is **v0.9**, source tag commit `1a85cb5a8ea12dc2dcfbcc878700d0d097245de7`; it is not the newer SDK HEAD studied earlier. The release's kernel source also contains 12.50 and 12.52 cases in the same branch. Its startup and the loader bootstrap perform privileged initialization and kernel/session changes; neither Root mode nor FTP availability establishes their prerequisites.

```sh
python3 tools/build-process-loader.py --fetch
# Stages files, verifies full FTP readback and removes only hash-matched older diagnostic PKGs.
# It never sends a payload to BinLoader or starts the loader.
python3 tools/transfer-process-probe.py --build P005 --host PS4_IP --include-loader
```

Artifacts are `out/process-loader/{elfldr.bin,elfldr.elf,socksrv.elf,manifest.json,upstream-source.tar.gz}`. The FTP command now stages the package in `/data/pkg/`, the ELF bootstrap in `/data/payloads/OrbisDesk-elfldr-P005.elf`, and the loader source archive beside P005's diagnostic files. The earlier BIN transfer is historical: GoldHEN rejected that headerless BIN, as established below. No main OrbisDesk PKG is replaced. Establish the actual GoldHEN build and compatible bootstrap before executing this separate payload. Starting it is a distinct action from installing P005. Once the loader is running, launch P005, wait up to about 15 seconds for the final panel, photograph it and close through the PS4 menu. A run without a loader can only verify the unavailable-loader branch.

### Focused local evidence

The fork run `reports/process-hardware-p005/20261111T143905267179Z/report.json` reached its final panel in 2.523 seconds, recording loader connection refused (`-61`), no helper PID, and no coexistence pass. The runner then deliberately stopped the persistent panel (exit -9). It did not execute the external loader or establish native process support.

The Linux reference compiles the actual helper with a host-only syscall-number adapter. It verifies bidirectional heartbeat completion with a distinct native child and observed exit 42, plus rejection of a stale token with exit 83. This caught and corrected entry-stack alignment and a result-reader indexing error before deployment. Its report is `build/process-loader-helper-reference/report.json`; temporary evidence remains under `/var/tmp/orbisdesk-p005-reference-*`. These are host checks, not physical PS4 acceptance. No full product test matrix is needed for this isolated increment. Physical loader bootstrap and P005 coexistence remain pending.

### P005 staging and first bootstrap attempt

On 2026-11-11, full FTP readback verified the P005 package SHA-256 `5dffddf47b31f37435db84a8e8b9f2af66824ab4850505513bec86d9c933e359` and bootstrap BIN SHA-256 `f917c03a4d11844892b22cdd27833705a9c291c4d00e94da24525f1da197d57d`. Transfer evidence is `reports/process-hardware-p005/ftp-20261111T144434955398Z/transfer.json`; the hash-matched P004 PKG was removed, while its local evidence and the product PKG were preserved.

[start-process-loader.py](../tools/start-process-loader.py) first sends an unrecognized four-byte magic to port 9021 and checks the audited service's rejection response, without requesting a payload launch. With `--start`, if no connection is available, it verifies the local bootstrap hash and sends the selected artifact once to GoldHEN 9090. **ELF is now the default**, following the format rejection diagnosed below; BIN remains only an explicit historical-reproduction option. It does not replace an already identified service or overwrite an unknown responding endpoint. This command executes a privileged bootstrap; it is distinct from the non-executing FTP command:

```sh
python3 tools/start-process-loader.py --host PS4_IP --firmware 12.50 --start
```

The first attempt, `reports/process-hardware-p005/loader-20261111T144600293992Z/report.json`, successfully sent 263,540 bytes to 9090. Port 9021 timed out before and after; the service was **not identified remotely**. This does not establish whether bootstrap execution failed, remained pending or produced a service inaccessible over the network. A subsequent FTP check succeeded, so the console still responded. The user reported GoldHEN `2.4`, without a beta suffix. Do not retry the bootstrap automatically. The next user-run P005 local-loopback result should distinguish a reachable local service from a missing one; no native helper has yet been verified on hardware.

### Console firmware correction

On 2026-11-11 the user corrected the firmware: their PS4 Pro Baikal runs **12.50**, not 12.52. P001–P004 and the initial loader bootstrap attempt belong to that 12.50 console; the earlier reports did not detect firmware automatically. The original bootstrap report retains the earlier reported 12.52 value and is not overwritten; this correction is supplemental evidence. The bootstrap and SDK group 12.50/12.52 in the same branch; P005 does not hardcode a 12.52 selection and needs no rebuild for this correction. This does not make the bootstrap attempt successful: the loader remains unidentified and physical coexistence remains pending. The startup command now requires explicit `--firmware` with `--start`; this is operator metadata, not automatic detection.

### Physical P005: observer completed, loader unavailable locally

The user ran P005 on that 12.50 console. The archived run is `reports/process-hardware-p005/physical/20261111T145120101532Z/run-0001/`, with hashes and the corrected operator-reported firmware in `fetch.json` in its parent directory. The observer logged PID 116, local loader connection refused (`loader_unavailable: -61`), no helper PID or progress, and `panel_ready`. Only `report.jsonl` and `state.bin` were present; the request never reached the ELF transfer stage. Coexistence, native exit and low-address isolation remain unverified.

This confirms the unavailable-loader branch on physical hardware and rules out a solely remote-access problem as the explanation for this run: the title could not reach the loopback service either. It does not establish why the earlier bootstrap failed to produce an accessible listener. Investigate the bootstrap's entry/CRT/kexec/privilege stages before another launch attempt. Do not repeat P005 expecting helper execution without first resolving that prerequisite, and do not interpret this as a Wine or PoP failure.

## P006: GoldHEN bootstrap format corrected, resident loader verified

The first bootstrap and an instrumented BIN produced no file trace. A separate 392-byte P007 entry probe performed only file I/O and returned; it also produced no marker. These absences did not establish an ABI, permission or runtime failure. A proposed remote permission change was rejected by automatic approval review and was not applied. Read-only klog capture then established the actual cause: GoldHEN received all three BINs (263,540, 267,844 and 392 bytes) and explicitly logged **`invalid payload format... skipping.`** They never reached their entry points. Do not describe this as a kexec/CRT crash.

The fix is to send **`elfldr.elf` directly**, rather than this upstream headerless BIN wrapper. This is an observed result for these artifacts and this GoldHEN session, not a claim that GoldHEN rejects every BIN. The launcher now defaults to ELF and records the actual format and hash. It never probes 9090 with an empty connection; identification uses only the resident loader's 9021 protocol.

P006 also adds file-only stage tracing to the pinned SDK CRT and loader, through [process_loader_stage.h](../native/process_loader_stage.h), [the trace builder](../tools/build-process-loader-trace.py) and the generated [SDK patch](../patches/process-loader/0001-sdk_source-bootstrap-trace.patch)/[loader patch](../patches/process-loader/0001-elfldr-bootstrap-trace.patch). No shared SDK CRT or product runtime is replaced. The header logs without libc initialization or additional kernel writes; the underlying bootstrap retains its audited privileged operations. Exact source revisions/archive hashes remain in [the lock](../tools/process-loader.lock.json).

```sh
python3 tools/build-process-loader.py --fetch
python3 tools/build-process-loader-trace.py --fetch
python3 tools/transfer-process-probe.py --build P005 --host PS4_IP --include-loader \
  --loader-dir out/process-loader-p006
python3 tools/start-process-loader.py --host PS4_IP --firmware 12.50 \
  --artifact-dir out/process-loader-p006 --payload-format elf --start
```

On the physical PS4, GoldHEN accepted the ELF, selected `ScePartyDaemon` PID 47 and logged payload launch success. The SDK's klog/kernel/dynamic-linker/patch initialization stages all returned 0. The bootstrap created a separate service PID **120**, returned that PID and reached **`service_listening: 9021`**. The identification request received the expected `elfldr.elf` rejection response. The SDK's recorded firmware value `0x12508001` selects its 12.50 branch, independently matching the user's correction.

Evidence:

- `reports/process-loader-p006/klog-20261111T150446824106Z/`: original format rejections.
- `reports/process-loader-p006/elf-attempt-20261111T150618910025Z/`: klog captured across the successful ELF send.
- `reports/process-loader-p006/loader-20261111T150619007851Z/report.json`: positive loader identification; ELF SHA-256 `84c26c87891b18302fbcb5184bbe3f0d2c3d6bd784233fe0993e0cd41eae0c5c`.
- `reports/process-loader-p006/trace-20261111T150716558679Z/`: downloaded stage trace SHA-256 `7ebbe982de1a1f8d363564fc043ccd681dd58d3738a5921310971923caf6d4c4`.

This validates resident-loader bootstrap and service creation on physical 12.50 hardware. It does **not** yet validate the title/helper coexistence handshake, two independent fixed-address mappings, native child-exit supervision or Wine/PoP. P005 can now be rerun **without reinstalling** while the loader is active. A console restart can remove this session prerequisite. The trace is `/data/orbisdesk/process-loader-p006.jsonl`; GPL source/patch inputs accompany the optional FTP-staged ELF in `loader-source-bundle.tar.gz`. Full console-state restoration is not claimed.

## Physical P005 rerun: native coexistence and shared-state handshake passed

With the loader active, the user reran the unchanged P005 package. Evidence is `reports/process-hardware-p005/physical/20261111T152515872916Z/run-0002/`; `analysis.json` in its parent verifies all downloaded file hashes and cross-checks observer logs, helper logs, the socket output and the binary shared-state fields. The report SHA-256 is `0c2eaa7db8959a61ce39588e6ee5b280743746dc4e707708482532244c10667e`; helper report SHA-256 is `b4ce81d492e1343560309afbc6b10d7ae5f00c1dd5136f4f2b06164d65456ec2`.

| Observation | Physical 12.50 result |
| --- | --- |
| Observer title PID | 123 |
| Helper PID / native parent PID | 124 / 120 (resident loader) |
| Observer / helper heartbeat ticks | 18 / 11 |
| Observer acknowledged distinct helper / helper observed observer progress | Both 1 |
| Helper completion | Self-reported 42; not reaped by title |
| Helper JSONL versus loader socket output | Byte-identical |
| Coexistence handshake / final panel | Passed / reached |
| Requested mmap hint | `0x400000`, without MAP_FIXED |
| Actual observer / helper mappings | `0x41c000` / `0x588000` |

This is physical evidence that an independently created native helper and the title remain active concurrently and exchange state bidirectionally through a shared file mapping. The title did not restart or act as the helper's native parent. It is not merely a thread running in the title. Original run-0001 remains archived as the unavailable-loader case.

**Remaining gates:** fixed-address isolation is inconclusive because neither side obtained the requested hint; do not label it a pass or infer which image occupies that range without a module/mapping inventory. Native exit code/disappearance supervision, repeated cleanup and cross-process SCM_RIGHTS are still unverified. No Wine helper, Windows process-object contract or PoP result has been established. Inspect the native image/mapping layout and prove simultaneous independent mappings at the fixed PE32 base before integrating Wine. Do not overwrite existing mappings with MAP_FIXED as a substitute for that investigation.

## Follow-up review: P007 passed, P009/P010 bootstrap is next

The subsequent work extends [the diagnostic builder](../tools/build-process-hardware-probe.py) with P007/P009 and [the external loader builder](../tools/build-process-loader-trace.py) with P010. These new results supersede the earlier pending assessments only where supported by evidence; earlier runs remain archived.

**P007 verified:** `reports/process-hardware-p007/physical/20261111T164219043252Z/run-0002/`. All downloaded file hashes were rechecked against its fetch manifest. The title retained its native mapping at `0x400000`; helper PID 135 (native parent 120) identified and unmapped three bootstrap executable regions in its own process, then mapped a **16 MiB span at `0x400000`** and retained its marker. Both sides verified received descriptor contents through AF_UNIX/SCM_RIGHTS, and coexistence passed. This is a freestanding helper result: its unmapping routine is not established as safe for an initialized OpenOrbis/Wine runtime with libc/TLS/global references. Peer EOF and completion 42 are not reaped native exit status; two external Wine helpers sharing the same preferred PE base remain unverified.

**P009/P010 state:** P009 is an OpenOrbis fake SELF linked at `0x1100000000`, with Wine-like native dependencies and intended thread, 64 MiB heap, fixed-base and production network-adapter checks. An earlier physical run stopped in Sysmodule loading `/app0/sce_module/libSceFios2.prx`, before `child_entered`. System/NPDRM variants are recorded as ENOEXEC failures in implementation notes. P010's [sandbox patch](../patches/process-loader/0002-elfldr-orbisdesk-sandbox-root.patch) adds an opt-in path adopting the observer title's rootdir/jaildir/prison before the SELF exec. Compatible `/app0` and module initialization remain pending acceptance.

Current artifacts and observations:

- P009 **01.11**, package SHA-256 `b0765eed7287d0396013ce4b29acc9bbd7bba672ff9f10ecbb4badd995a81e03`; verified transfer `reports/process-hardware-p009/ftp-20261111T183323923852Z/transfer.json`.
- P010 ELF SHA-256 `1e4964e8a0aba6ef32315440d52aa19d8c550cf88b6765acc1c21649d6938987`; startup identified in `reports/process-loader-p010/loader-20261111T183316445826Z/report.json`.
- Latest P009 fetch `20261111T184918946303Z`: run-0009 reached the loader without a child PID; run-0010 received local connection refused. The later read-only check `reports/process-loader-p010/loader-20261111T185030669844Z/report.json` also found no accessible loader. This does not explain its disappearance or prove the sandbox patch caused it.
- Several P009 package revisions use the same textual run marker. Transfer order alone does not identify the installed revision of every historical run; correlate the actual candidate and klog for the next acceptance.

Revised order:

1. Establish and record a stable P010 service for the exact candidate; investigate service termination before repeating a child launch, preserving klog.
2. Reach P009's own child entry with the intended `/app0` and modules, then pass its thread/heap, fixed-base, shared-state and descriptor checks on hardware.
3. Verify two simultaneous helpers with independent contents at the fixed base, repeated cleanup and native exit supervision. Do not repeat the passing freestanding campaign as the first blocker.
4. Integrate a headless Wine family with one server/object namespace; run the fixed-base PE32 parent/child fixture before graphics and PoP.
5. Continue the execution selector independently. Automatic/Desktop/Exclusive can function now; Separate processes must remain visibly unavailable until Wine integration passes.

The selector's 14-case host registry-policy reference passed (`reports/execution-modes/20261111T162625766752Z/report.json`), with source hashes matching the current policy. Winecfg matches its builder and UI inputs. The i386 guest manifest no longer matches the current builder, so rebuild the guest DLL consumers before packaging the selector. This is not a new product build or selector hardware acceptance.
