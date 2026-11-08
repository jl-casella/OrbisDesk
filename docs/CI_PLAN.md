# CI plan: fast PR checks, a manual matrix pilot and distributions

[English](CI_PLAN.md) | [Español](CI_PLAN-es.md)

Status: phases 1–3 implemented for review, 2026-11-07; the first cold GitHub pilot remains pending. See [running CI](CI.md) for workflow inputs, evidence and activation. Phases 4–6 remain proposed. Branch protections and product releases are unchanged; the first manual run supplies the data for deciding where the heavier checks belong.

Follow-up on 2026-11-07: the owner requested a clean hosted product build and manual/automatic main releases. The separate [release runbook](RELEASES.md) describes the experimental implementation, rollout switch and current limits. The first successful clean product pilot remains pending; the diagnostic matrix is not yet an automatic release gate. The promotion proposal below remains a future stricter policy, not the active workflow behavior.

## Goal and rollout

```text
PR 1: fast checks on pull requests
  -> PR 2: recreate test prerequisites and define the matrix contract
  -> PR 3: workflow_dispatch matrix + one measured cold pilot
  -> decide using the measured total and phase durations
  -> PR 4: put selected checks on PRs and/or push to main
  -> PR 5: make the full product build portable from a clean clone
  -> PR 6: successful main validation produces a distribution candidate
```

The manual workflow comes before automatically imposing the emulator matrix on contributors. A passing platform matrix certifies its declared diagnostic scope; it does not certify the modern Wine desktop, hardware compatibility or arbitrary games.

## Timing baseline

These are local WSL measurements or historical reports, not GitHub runner benchmarks:

| Work | Observed time | Qualification |
| --- | --- | --- |
| Documentation, index, repository layout and brand checks | About 16 seconds | Measured with the working tree available |
| VM and PE parser host checks | About 4 seconds | Sources and generated fixtures already present |
| Historical increment-18 campaign, 31 runs | About 4 minutes wall time | Emulator/ELFs/references already built; 162 seconds recorded execution total |
| Historical GUI/text campaign, four runs | About 5 minutes wall time | Prepared Wine/runtime; separate from the platform matrix |
| Recent incremental emulator build | About 2 minutes | Not a cold compiler/submodule/build measurement |

Initial targets: fast PR jobs finish in 2–5 minutes including setup; manual pilot has a 90-minute outer timeout, a 45-minute bootstrap/build budget and a 20-minute test budget, with explicit per-case timeouts. These are guardrails to tune after the pilot, not promised run times. Install/download steps must also have finite retry/time limits.

## PR 1 — fast checks on pull requests

Proposed files: `.github/workflows/ci-pr.yml` and small helpers if necessary. Use Ubuntu 22.04 x64 initially, matching the established host environment; pin external actions to reviewed commit SHAs.

Trigger on `pull_request` and optionally `workflow_dispatch`. Start with:

```sh
python3 tools/check-repository-layout.py
python3 tools/check-docs-bilingual.py
python3 tools/build-doc-index.py --check
python3 tests/test_project_brand.py
python3 -m compileall -q tools tests
```

Add a host-VM job that fetches only the pinned `prospero-win` source and runs `bash tools/test-vm.sh`. Add a lock/patch checksum check that reads the committed locks without downloading every dependency. Add `bash tools/test-pe32.sh` after PR 2 can generate its fixtures independently.

No SDK, Wine build, emulator build, FTP or console is required for the initial metadata/brand jobs. Set a 10-minute job timeout, read-only repository permissions and concurrency cancellation for superseded runs of the same PR. Fail on a failed check; upload relevant failure logs. Do not run untrusted PR code through `pull_request_target` with write permissions or console credentials.

Acceptance: a small documentation PR and a deliberately invalid link/patch checksum demonstrate success and failure paths; no dependency/private directory enters an artifact. Branch-protection required checks are enabled only after their names and workflow behavior are verified in GitHub.

## PR 2 — self-contained matrix prerequisites and contract

Proposed entry points (new, not existing commands): `tools/ci/build-prerequisites.py`, `tools/ci/run-matrix.py`, and a versioned `tests/ci-matrix.json` case contract. Reuse existing implementations rather than copying their test logic into YAML.

The historical [increment-18 checker](../tools/check-increment18.py) is a reference for coverage, not a fresh-clone CI entry point. Its 31 top-level runs consist of **27 baseline/PE executions** (including the official-emulator comparison) and **4 service executions**. The report also contains many service assertions below those top-level runs.

Required preparation:

1. Restore only the dependencies for the selected profile, verifying commits and archive hashes. Automate Linux emulator/private-runtime extraction and the minimal OpenOrbis/toolchain setup currently assumed to exist locally. Respect the runner's disk budget and report available/peak usage.
2. Add an independent fixture-generation target for the host PE parser and emulator tests. Avoid requiring a complete Wine/graphics build merely to create own PE fixtures; use pinned MinGW settings and deterministic timestamps.
3. Generate reference output on a Windows runner from the **same fixture binaries**. Pass the fixture and reference artifacts to Linux with their SHA256 values and source SHA. Do not download a historical developer `reports/` directory as the test baseline or invent a reference when it is absent.
4. Build the pinned shadPS4 fork plus locked overlay and the diagnostic ELF. Preserve the source/tree/diff and binary identity checks. A cache hit is not a substitute for verifying inputs.
5. Decouple the four existing IPC/pipe/filesystem/metadata probes from the current full Wine bootstrap link if their native implementations can be built as a dedicated service-test ELF with unchanged assertions. Inspect [wine_boot.c](../native/wine_boot.c) and the existing native probes. Prove equivalence to the existing probe path. If that extraction cannot preserve semantics, restore the actual Wine prerequisites instead and report the extra cost; do not stub the dependencies.
6. Review every historical expectation against current intended behavior before freezing `platform-v1`. Deliberate fixes may invalidate an old assertion. Keep historical reports historical; do not silently rewrite old results or accept every failure as a known blocker.

Contract rules:

- Each case declares ID, emulator kind, ELF/fixture identity, expected outcome, timeout, required markers and expected output/exit conditions.
- The pinned official-emulator case may be an explicitly expected blocker. Its specific failure signature must match; an arbitrary timeout/crash is not equivalent. Report `contract_passed` separately from individual `passed`/`blocked` outcomes and from Wine boot status. An unexpected success requires reviewing the contract too.
- Missing prerequisites fail setup. An explicitly selected incomplete `platform-core` profile can run the 27 baseline cases during development, but must not be labelled the full 31-case profile. A full-profile run cannot become green by skipping its service cases.
- Prefer a fresh emulator process/private data copy per case. Give each case distinct logs/reports and preserve exact exit, timeout and last-marker details.
- The GUI/Wine path is a separate future profile. The platform matrix does not run the current packaged desktop or establish PE32 native/GPU compatibility in the fork.

Acceptance: the full diagnostic profile can be prepared and run without pre-existing `build/`, `out/` or `reports/`. A missing fixture/reference and one intentionally wrong expectation produce visible failures. First validate on a Linux filesystem, not only the original Windows-mounted workspace.

## PR 3 — manual matrix workflow and the first measured run

Proposed workflow: `.github/workflows/matrix-manual.yml`, using `workflow_dispatch` only at first. GitHub must have the dispatch workflow on its default branch before the manual trigger is available. Put the test implementation in reusable scripts/workflows so PR and main triggers can reuse it later.

Inputs:

| Input | Initial values/purpose |
| --- | --- |
| `profile` | `platform-v1` by default; `platform-core` clearly marked incomplete |
| `cache_mode` | `cold` or `reuse`; cold bypasses all build/dependency caches |
| `official_comparison` | Required for the full profile; optional omissions change the declared profile |

Use GitHub's branch/ref selector and record the resolved checked-out commit SHA. Avoid an arbitrary default of “latest”. Pin runner family/toolchain and use Xvfb/Lavapipe where needed; keep official and fork results separate. Initially run cases sequentially in one Linux job, matching the local timing baseline. Parallelize only after it is clear cases do not share a prefix, emulator profile or output directory.

The **first pilot is one cold run** on the selected commit. Measure independently:

1. checkout and source/artifact downloads;
2. dependency verification and extraction;
3. fixture build and Windows reference job;
4. emulator and diagnostic/service ELF builds;
5. each test and total matrix execution;
6. report/artifact compression and upload;
7. total workflow wall time, job durations and peak disk usage.

Persist `timings.json`, `matrix-report.json`, a job-summary table, manifests, failure logs and relevant reference/results. Upload diagnostic evidence with `always()` after a test failure; use an allowlist, redact credentials and cap sizes/retention. A failed run may upload debugging evidence, but cannot upload a successful distribution candidate.

The summary must identify cold/warm state, runner, source SHA, lock hashes, emulator build/source identities, selected profile, expected/observed outcomes and counts. Total wall time and summed job duration are different when Windows/Linux jobs overlap; report both. Queuing delay can be reported separately from execution.

An optional second run on the same SHA with cache reuse measures warm behavior. It is useful but not required before reviewing the first result. One run gives an initial estimate; it does not establish p95 duration or flake rate. If the cold run fails in setup, that is still useful timing, but not a completed matrix benchmark.

Acceptance: launch from GitHub Actions, retrieve the report, and use its actual timings/outcomes to choose PR 4. No change to the local PS4 or FTP deployment is part of this pilot.

## PR 4 — select PR/main coverage after measurement

Proposed decision thresholds, adjustable after the first run:

| Measured behavior | Proposed placement |
| --- | --- |
| Complete matrix reliably fits roughly 10 minutes including preparation | Consider it for relevant PRs; keep quick checks on every PR |
| Roughly 10–25 minutes | Full profile on `push` to `main`; a smaller verified profile on relevant PRs |
| More than 25 minutes or substantial instability | Keep full profile manual/nightly while splitting work or improving cache/bootstrap |

Initially prefer fast required PR checks and full validation on main. Filter heavy PR work by loader/VM/ABI, Wine adapters, graphics/runtime builders, fixtures and lock/patch changes. Documentation-only PRs retain fast checks. Never make path-filtered required jobs disappear and leave branch protection waiting indefinitely; use a stable gate/check result that records a legitimate non-applicable path decision.

`push` to `main` validates the actual merged SHA; a PR merge-ref result is not automatically evidence for that new SHA. If using a merge queue later, add the appropriate merge-group coverage before requiring the workflow there. Preserve `workflow_dispatch` for manual reruns and investigations.

Cache only explicit SDK/source/tool/intermediate paths, with keys derived from OS/architecture, compiler, source locks, ordered patch hashes, recipe changes and source SHA as appropriate. Verify restored binary/manifests before using them. Never cache the entire `.deps/`: this workstation has `.deps/ssh/` there. Prefixes, user state, credentials and private notes do not belong in shared caches/artifacts. Keep PR caches distinct from trusted publication inputs.

Acceptance: branch protection has stable required check names; a PR touching runtime gets the intended coverage, a doc-only PR completes normally, and a merged commit is tested as its own SHA. The decision records the cold pilot and any warm result, rather than treating local historical timings as a GitHub measurement.

## PR 5 — portable full product build

This is separate from making the 31-case diagnostic suite runnable. Resolve the gaps in [repository layout](REPOSITORY_LAYOUT.md): workstation paths, host Wine configuration, prefix production, graphics/compiler prerequisites, PE closures and build-input reports. The relevant graph is mapped in [AGENTS](../AGENTS.md).

Proposed reusable workflow: `.github/workflows/build-product.yml`. Generate the current main package, its complete runtime and manifests from one resolved source SHA. Keep selected optional assets/dependency pins explicit. Validate package/SFO identities, PE architectures/import closures, hashes, licences and the runtime layout expected by the uploader. Preserve console settings/update identity semantics.

Acceptance: a clean runner produces `OrbisDesk.pkg` and its matching runtime without copying a developer build tree. Record full cold and incremental/cache timings separately. Add a fresh-runtime packaged-desktop smoke profile; existing fork/native32/graphics limitations remain visible and cannot be hidden by reusing an initialized local runtime. Static packaging success alone is not a desktop smoke pass.

## PR 6 — distribution candidates only after successful main validation

Two outputs have different scopes:

- **Diagnostic bundle:** the exact tested diagnostic/service ELF, own PE fixtures, results and provenance. This can be an artifact once PR 3 works; it is not the full OrbisDesk application distribution.
- **Product candidate:** `OrbisDesk.pkg`, complete matching `/data` runtime payload, install instructions, dependency/attribution information, checksums and build/test provenance. This requires PR 5 and testing the exact candidate binaries.

Proposed `.github/workflows/dist.yml`, or a gated job in the main workflow:

```text
push main -> fast checks -> required platform matrix
          -> product build -> fresh packaged smoke
          -> distribution artifact (only when every required dependency passed)
          -> optional manual promotion after PS4 feedback
```

Use explicit `needs` and success gates. Prefer same-run job dependencies to loosely associating separate workflows by branch name. If using `workflow_run`, fetch artifacts from the exact successful run ID/head SHA and check provenance; do not execute untrusted PR artifacts with publication permissions. Never test one binary and silently rebuild a different one for distribution: package first and test that output, or require identical verified hashes.

Name candidates by commit/run, for example `OrbisDesk-dist-<shortsha>.zip`; include `SHA256SUMS` and a manifest containing source SHA, compiler/lock/patch identities, binary/runtime hashes, matrix report and smoke scope. A green diagnostic contract can contain a declared official blocker; it does not justify claiming official emulator/hardware compatibility. Required packaged-smoke failure blocks product distribution even if diagnostic checks passed.

Start with downloadable Actions artifacts, not an automatically published stable GitHub Release. A separate protected/manual promotion can create a prerelease/release from the same verified candidate after the required PS4 feedback. FTP upload/install stays a separate explicitly requested workflow; do not put a home-console deployment in every PR or main check.

Acceptance: a deliberately failed test blocks the candidate; the candidate's SHA matches the tested build; users receive both package and runtime; reports label emulator presentation and physical validation accurately. Release notes distinguish experimental candidates from hardware-accepted releases.

## Files and implementation order

The workflow and helper names above are proposed files, not commands available today. First implement PR 1; then PR 2 and PR 3 to obtain the requested real timing. Do not implement the main/release placement decision before reviewing that pilot. PRs 5–6 may require several smaller implementation PRs once their build graph is measured.

Keep this plan bilingual, regenerate the [documentation index](INDEX.md), and record the first GitHub run URL, source SHA, outcome and phase durations in a new report/document when it exists. Do not attach local timing as if it were that run.

Primary references: [manual workflows](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow), [workflow syntax and dependencies](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax), [artifacts](https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts), [dependency caching](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching).
