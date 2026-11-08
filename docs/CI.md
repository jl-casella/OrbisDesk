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

No workflow publishes a release, builds the complete Wine desktop, accesses FTP or changes branch protection. A successful matrix uploads a diagnostic bundle only. Product distributions remain later phases of the plan.

## First measured run

1. Merge the workflow implementation into the default branch. GitHub must know the dispatch workflow on that branch before it can be selected in Actions. The timing collector must also exist there.
2. Open **Actions → Manual platform matrix → Run workflow**. Select the intended branch/revision, `profile=platform-v1` and `cache_mode=cold`.
3. Wait for both the matrix and the separate timing collector. A failed setup is a failed pilot, not a matrix pass.
4. Download `matrix-evidence-*` from the matrix run and `matrix-timings-*` from the collector. Record the run URL, source SHA, outcome, wall time, summed job time and phase durations.
5. Optionally repeat with `cache_mode=reuse` at the same revision. This cache contains verified downloads only; compilation still runs. Do not describe it as an incremental build benchmark.

Job/step timeouts bound the pilot: 90 minutes for the Linux job, 45 minutes for its bootstrap step and 20 minutes for execution. Each case has a 60-second timeout. Cancellation or an outer timeout can leave incomplete evidence; absence of a completed report never means success.

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
