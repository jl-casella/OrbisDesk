# Running CI and measuring the platform matrix

[English](CI.md) | [Español](CI-es.md)

## What is implemented

The first three implementation phases of [the CI plan](CI_PLAN.md) provide fast PR checks, independent fixture/service builds and a manual platform matrix. A fresh GitHub-hosted run is still required to establish the cold timing baseline. Local runs using already installed dependencies do not establish that baseline.

The workflows are:

| Workflow | Trigger | Purpose |
| --- | --- | --- |
| `PR checks` | Pull request or manual | Documentation, layout, locks, Python checks and sanitized host VM/parser tests |
| `Manual platform matrix` | Manual only | Produce fixtures, run the same binaries on Windows, prepare Linux dependencies, build and run the diagnostic contract |
| `Collect matrix timings` | Completion of the manual workflow | Read final job and step timings from GitHub; upload `timings.json` |

These diagnostic workflows do not publish releases, build the complete Wine desktop, access FTP or change branch protection. A successful matrix uploads a diagnostic bundle only. The separate experimental [product release workflow](RELEASES.md) attempts the clean full build; its first successful hosted pilot is still pending.

## First measured run

1. Merge the workflow implementation into the default branch. GitHub must know the dispatch workflow on that branch before it can be selected in Actions. The timing collector must also exist there.
2. Open **Actions → Manual platform matrix → Run workflow**. Select the intended branch/revision, `profile=platform-v1` and `cache_mode=cold`.
3. Wait for both the matrix and the separate timing collector. A failed setup is a failed pilot, not a matrix pass.
4. Download `matrix-evidence-*` from the matrix run and `matrix-timings-*` from the collector. Record the run URL, source SHA, outcome, wall time, summed job time and phase durations.
5. Repeat with `cache_mode=reuse` (now the default) to measure warm behavior. This restores verified downloads, an exactly matched emulator binary when available, and a compiler cache for rebuilds. The diagnostic ELFs/fixtures are rebuilt and every selected test still executes. Cold runs bypass all cache restoration but can populate the caches for later runs.

Job/step timeouts bound the pilot: 200 minutes for the Linux job, 20 for preparation, an 80-minute internal emulator budget inside a 90-minute Actions step, and 40 for matrix execution. The separate internal/outer limits leave time to terminate the build process group, record compiler-cache statistics and save evidence. Each case still has a 60-second timeout. The 31-case worst-case timeout sum is 31 minutes, so the old 20-minute outer execution budget could interrupt a legitimate failure campaign. Reports are checkpointed before and after each case, with active/pending cases and `execution_completed=false` until the loop finishes. Cancellation or an outer timeout never means success; per-case failures remain failures.

## Emulator and compiler caches

Only `.deps/emulator-cache`, `.deps/ccache` and the existing verified-download directory are cached. The emulator bundle contains the fork binary, its original build manifest, source diff and cache proof. Its key binds the actual restored fork commit/tree/diff, clean submodule revisions, locked patch/overlay identities, build recipes, compiler/scanner/linker/CMake/Ninja/ccache binaries and versions, installed package versions, architecture, build environment and checkout path. The current OrbisDesk commit alone is deliberately not the key: unrelated application or documentation changes can reuse the same emulator.

The download cache is limited to three completed files: `openorbis.tar.gz`, `shadps4-linux.zip` and `libc6.deb`. After preparation, even if a later preparation stage failed, a separate check verifies every present file against its lock and saves it before compilation. Restore prefers complete three-file entries, then verified partial entries; `.part` files are never saved. Thus a later emulator failure no longer prevents preserving the SDK download. Cold runs also save completed verified downloads for future reuse.

The downloader retries transient HTTP 408/429/500/502/503/504 and transport errors up to six attempts, with 5/10/20/40/60-second backoffs and a bounded numeric Retry-After override. It logs attempts in Actions and `download-attempts.jsonl`. Permanent HTTP errors and hash mismatches still fail; downloaded and restored files must match SHA-256 before extraction. If the remote service remains unavailable, the job still fails rather than changing the SDK version or accepting incomplete bytes. `--check-download-cache` only checks completed archive files and never extracts them.

Restoration rechecks that identity, the manifest hash and ELF64 binary hash before installing the binary for the matrix. A corrupt or mismatched cache fails explicitly; it is not relabeled as a compatible build. Use `cold` and remove the bad cache in GitHub if necessary. The original build provenance is preserved; `emulator-cache.json` records reuse separately for the current run. A cache hit is not a test result or hardware validation.

When the exact binary is unavailable, the emulator configures from scratch with ccache as the C/C++ compiler launcher. The compiler cache is capped at 2 GiB and can restore compatible objects across source changes; normal dependency/content hashing remains enabled. Successful emulator builds are saved **before** matrix execution, so a later test failure does not discard the 40-minute build. Partial compiler work can also be saved after a failed compile. Stats are in `ccache-stats.log`; keys and input identities are in `emulator-inputs.json`.

During compilation, the helper prints the latest configure/build lines once per minute. On failure it also prints those inner logs, not just the outer Python traceback. POSIX timed subprocesses launched by CI own a process group; a timeout terminates the driver and its Ninja/compiler descendants before collecting statistics. `emulator-build-failure.json` records the error type and available inner logs. These changes improve diagnosis and cleanup; a larger time budget is not proof that an underlying stall is fixed.

The first run of this implementation still needs to build: earlier workflows did not save the binary or object cache. GitHub caches can expire, be evicted, or be unavailable across branch scopes; a feature-branch cache is not necessarily reusable after merging to main. The cache rollout must be measured on GitHub before claiming a warm duration. The product release workflow continues to require its own clean product build and does not reuse a console runtime.

The `platform-core` profile runs the 27 baseline cases without the four service cases. It is useful for diagnosis, but cannot produce the full diagnostic bundle or substitute for the 31-case acceptance run.

## Scope and evidence

[tests/ci-matrix.json](../tests/ci-matrix.json) is the versioned contract: 27 loader/translator/platform cases and four native service cases containing 45 named assertions. Each case gets a fresh emulator process and private data directory. Native Windows runs validate the exact fixture binaries and provide output references; hashes and source revisions must match before Linux execution.

The official-emulator comparison is an expected **blocked** result with an exact assertion signature, successful guest markers and matching reference output. An arbitrary crash, missing marker or timeout does not satisfy that contract. Fork passes are reported separately. Hardware remains pending, and `Wine_booted` remains false: these probes do not start Wine.

Evidence under ignored `reports/ci/` includes:

- `matrix-report.json`: actual cases, outcomes, hashes, emulator provenance and setup errors.
- `cases/<case>/`: stdout, stderr, per-case report and applicable output files.
- `windows-reference.json`: native reference exit codes, output bytes and fixture identity.
- `timings.jsonl` and `phase-timings.json`: internal preparation/build/execution durations.
- `environment.json` and build logs: installed packages, lock hashes and preparation details when setup reaches those stages.

The evidence artifact also preserves `build/shadPS4-linux/configure.log`, `build.log`, `CMakeCache.txt` and `CMakeFiles/CMakeConfigureLog.yaml` when present. A failed builder prints the last 64 KiB of its log through both capture layers into the Actions step output, while the complete logs remain in the artifact. Missing files from stages not reached are not successes.

The first hosted pilot, run `42429594632`, attempt 1 at source `12eae3a4db4cbf46ec15914449c597743ec6a0a3` on 2026-11-07 (Argentina time), failed in CMake configuration of the fork. Source restoration, SDK/official extraction, diagnostic ELF and service ELF builds completed; matrix execution did not start. About three minutes refers to the bootstrap step, not execution of the 31 cases. Its original artifact omitted the CMake configure log, so the underlying configuration error could not be determined from that evidence. The subsequent logging change fixes that evidence gap; it does not claim to fix the still-unknown configuration error. Start a **new manual run at updated main** after merging it; rerunning the old SHA retains the old workflow.

The next pilot at `cbf26969c4ecc8e82b65d693abd550bf6abee15e` exposed `SDL_missing_dependency` at `externals/sdl3/cmake/sdlchecks.cmake:521`: the pinned SDL3 requires XRANDR headers and a library. The runner installation omitted `libxrandr-dev`. The installer now explicitly includes it and verifies `pkg-config xrandr` before configuration. This fixes the identified prerequisite; completion of the emulator build and matrix still requires a new hosted run. The product installer uses this same runner installer and receives the fix too.

The following pilot at `b2f2d8e3e38b22bb727d8581f5e544a40df466bc` completed configuration, then failed during C++ dependency scanning with `CMAKE_CXX_COMPILER_CLANG_SCAN_DEPS-NOTFOUND`. `clang-19` alone did not install the scanner. The runner now installs `clang-tools-19`, verifies `clang-scan-deps-19 --version`, and passes its resolved executable to CMake. It also installs private Ninja 1.13.0: scanning needs Ninja 1.11+, while Ubuntu 22.04's system Ninja can be 1.10. The builder checks these tools before configuration, records their identities in its manifest and rejects reused caches with missing/different tool paths. A local standalone C++23 smoke build with CMake 4.2.3, LLVM 19.1.7 and the pinned Ninja successfully scanned, compiled, linked and executed; that is toolchain validation, not a completed shadPS4 build or matrix run. The next hosted run must establish the latter.

The branch run at `b6ad6331104955be70f176756968d2c2588349c7` then completed emulator compilation in 2,489.7 seconds (41 min 30 s) and preparation in approximately 43 min 11 s. Its matrix step reached the old 20-minute limit; the supplied excerpt does not establish individual failure causes or a completed matrix result. This observation prompted the cache and timeout/checkpoint changes above. The current implementation still needs its hosted cache-hit and complete-matrix validation.

Run `42447432083` at `1573d57d4619c8f8c09e8d0cce33d69a490a44bb` took 3,868 seconds overall and hit the old 3,600-second internal emulator limit (the Actions step lasted 3,605 seconds). Preparation took 142 seconds. The compiler-cache save step succeeded in four seconds; the verified binary save and matrix execution were skipped. The supplied timing artifact does not include cache sizes/hits or the inner build log, so it cannot establish the cause of the slowdown. The internal and outer limits previously expired together; they are now separated as above. Inspect `matrix-evidence-*`, especially `build/shadPS4-linux/build.log` and `reports/ci/ccache-stats.log`, before attributing the delay to compilation, configuration or caching.

The subsequent run at `49c95f07c1ef7a759be007a3a5dd1cdb77925ab0` completed source restoration in 106 seconds, then failed downloading the SDK with HTTP 504 after about 14 seconds. It did not reach compilation. The retry/early-download-cache changes address that observed transport failure; they do not demonstrate that the remote service recovered or that the earlier compile delay is resolved. Local tests cover bounded transient retries, permanent errors, rejected hashes and partial-cache verification without downloading/extracting a real SDK.

The collector's separate `timings.json` includes all final jobs and steps. Wall time spans run start to the last completed job; summed job time includes parallel work and therefore differs. Queue time is reported separately. The collector reads GitHub metadata and never downloads or executes artifacts from the tested run.

## Reproduce or investigate locally

Use a separate clean checkout with Python 3.12 and Ubuntu 22.04; dependency restoration writes ignored directories. The install script targets a disposable runner and uses sudo to install system packages. See [dependency restoration](REPOSITORY_LAYOUT.md), [the developer guide](../AGENTS.md) and the scripts for exact lock sources and patch order.

```sh
bash tools/ci/install-runner.sh
python3 tools/ci/bootstrap.py --fixtures
```

Execute `tools/ci/windows-reference.ps1` on Windows with the same `out/` fixtures and `ci-fixtures.json`, then return its `reports/ci/windows-reference.json` without regenerating fixtures. Continue in Linux:

```sh
python3 tools/ci/bootstrap.py
xvfb-run -a python3 tools/ci/run-matrix.py --profile platform-v1
python3 tools/ci/report.py
```

For a focused investigation, use a new report directory:

```sh
xvfb-run -a python3 tools/ci/run-matrix.py --case metadata --report-dir reports/ci-metadata-retry
```

Focused runs are explicitly incomplete and cannot certify the full contract. Preserve earlier reports. The source-only checks can be run without the SDK:

```sh
python3 tools/ci/check-locks.py
python3 -m unittest discover -s tools/ci -p 'test_*.py'
python3 tools/check-docs-bilingual.py
python3 tools/build-doc-index.py --check
```

The canonical builder supports `--fixtures-only` without the SDK and `--diagnostics-only` to reuse those fixtures. Service probes use the same private libc derivation as the Wine builder; neither edits the SDK archive. No external source checkout, prefix, emulator binary, credential or private note is committed or uploaded as a source artifact.

## Deciding the next CI phase

Implementation validation used a prepared local WSL environment, not a cold runner: documentation/lock/brand checks, four evaluator failure-path tests, native Windows references and sanitized host tests passed. The first full matrix recorded 29 expected outcomes out of 31 in about 6.4 minutes, including the expected official blocker and all four service cases. Two fork cases timed out during startup; a focused retry passed `pe-fourk-preferred` but still timed out on `pe-dll-symbol`. The original full report remains failed. Xvfb was unavailable locally, so these runs used WSLg; CI installs Xvfb. The GitHub pilot must establish whether that startup failure reproduces there.

Use the first completed cold pilot to decide which checks can run on PRs or main within acceptable time and cost. Required-check names and protections should be configured only after successful GitHub runs. Full product staging, GUI smoke tests and console validation need their own acceptance criteria before a main build can produce an OrbisDesk distribution.
