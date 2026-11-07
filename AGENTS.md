# OrbisDesk: guide for AI-assisted development

[English](AGENTS.md) | [Español](AGENTS-es.md)

This is the entry point for an AI agent or a developer joining this repository. It is Markdown, with an ASCII directory map. Commands below are entry points with explicit prerequisites, not a claim that a fresh clone already has a complete one-command build.

## 1. Read first and establish the actual state

1. Read [README](README.md), [current state](docs/CURRENT_STATE.md), [status](docs/STATUS.md), and [repository/dependency layout](docs/REPOSITORY_LAYOUT.md).
2. Use the [complete documentation index](docs/INDEX.md) to find the subsystem/build involved. Documents named `borrador`, `plan` or `Wxxx` are drafts, not acceptance evidence. Old increments can intentionally describe failures already resolved later.
3. Inspect the relevant builder, its input manifests, the output manifest and the latest run/transfer evidence **before** choosing a build ID or claiming a feature works. File timestamps and the highest number in a filename are not sufficient.
4. Read `git status --short`, check for concurrent work, and preserve unrelated edits. Many builders share output directories; do not run conflicting builders concurrently.

At the time this guide was prepared (2026-11-07), public state documentation records physical W284 validation, while hardware build/transfer scripts already recognize W287. This is a documentation/code distinction, not proof that W287 was installed or tested. Reconcile it with actual manifests and user feedback on each session.

## 2. Project model and invariants

OrbisDesk runs a Windows desktop and applications on PS4 using Wine and native console services. PS4-native host code is x86-64. The project contains the prospero-win x86 translator route and a later native WoW64 route; inspect the active provider and run markers rather than assuming one is used everywhere.

Explorer hosts multiple Windows guests inside one PS4 title/process. Later code adds a 32-bit world alongside 64-bit guests. Guests have per-thread/per-guest adaptations, but share the native address space, server and some graphics/global state. A guest is not an isolated native process. A fixed-base collision can require the documented relaunch fallback. A second arbitrary PS4 process with its own Wine is not an established solution here.

- Do not make an unsupported capability appear successful through a stub, fabricated event or rewritten report. Keep the real failure and a minimal reproduction.
- A shadPS4 patch must implement general platform behavior, with an independent reproduction when possible. Emulator changes do not change the real PS4 kernel.
- Distinguish host reference, official emulator, fork emulator and physical hardware results. Never relabel fork success as official compatibility.
- The visible product is **OrbisDesk**. The distributed main package is `OrbisDesk.pkg`; the visible version belongs only on the NORMAL/ROOT boot selector. Preserve technical update identities, migration keys, old evidence names and compatibility paths. See [branding](docs/REBRANDING_ORBISDESK.md), [brand constants](tools/project_brand.py) and [package builder](tools/orbis_package.py).
- Keep public documentation in English with a complete `-es.md` counterpart. Follow [documentation policy](docs/DOCUMENTATION_POLICY.md). Do not copy private research/comparisons into the public documentation.

## 3. Directory map and what belongs in Git

```text
OrbisDesk/
|-- AGENTS.md / AGENTS-es.md        AI/developer entry point
|-- README.md / README-es.md        Project overview
|-- *.lock.json                    Sources, archives, tools and observed environment
|-- native/                        Launcher, console integration, native helpers
|   |-- hw_sink_gpu/               GPU presentation/composition
|   |-- pwmpeg1/                   MPEG decoder integration
|   |-- steam/                     Native Steam-client work and adaptations
|   `-- vk_probe/                  Native graphics diagnostics/shaders
|-- platform/ps4/                  Wine, VM, TLS, signals, filesystem, audio adapters
|-- fixtures/                      Own/adapted Windows test sources and small inputs
|-- patches/shadPS4/               17 ordered patches plus pending overlay 0018
|-- patches/wine/                  Wine patch snapshots; generators are also essential
|-- tools/                         Fetch, patch, build, stage, run, package, evidence tools
|   `-- vk-h0/                     Mesa/Zink/Vulkan/MangoHud recipes and transformations
|-- tests/                         Focused host/Windows checks
|-- docs/                          Bilingual public documentation and historical reports
|-- LICENSES/ / THIRD_PARTY.md      License texts and attribution
|-- private-notes/                 IGNORE: private research, never a publication input
|-- upstream/ / .deps/              IGNORE: external source trees, SDKs and downloads
`-- build/ / out/ / reports/        IGNORE: generated builds, packages, runtime/evidence
```

WSL also uses `~/vk-h0/` for graphics sources, sysroot, tools and builds. It is outside the Git root. Existing workstation paths are described in the [layout inventory](docs/REPOSITORY_LAYOUT.md); do not assume they exist on another machine.

Do not commit nested repositories, submodules/gitlinks, downloaded library trees, compiled DLLs/EXEs/PKGs, prefixes or full runtime archives. Keep pinned identities, patches, adapters and generators instead. Run [layout validation](tools/check-repository-layout.py) before staging/publication. Ignored evidence is useful locally but is absent from a fresh clone.

## 4. Environment, sources and patch restoration

Main environment: Windows host, Ubuntu 22.04 in WSL (`Ubuntu-22.04`), Python 3.10+, OpenOrbis v0.5.4, and Clang/LLVM selected by the specific recipe. The emulator uses Clang 19/libc++; older diagnostics and graphics cross-builds have different requirements. Do not silently substitute the compiler just because `clang` exists.

Start in the repository root. In PowerShell, launch Linux commands with `wsl -d Ubuntu-22.04 -- ...`; in WSL use the checkout's Linux path. Avoid assuming the original author's `/mnt/c/Users/...` path. Inspect [observed environment](build-environment.lock.json), [artifact pins](artifacts.lock.json), [tool pins](fork-tools.lock.json), [Linux emulator](linux-emulator.lock.json) and [private libc runtime](linux-runtime.lock.json).

```powershell
# Downloads/checks the SDK and official Windows emulator; inspect prerequisites first.
./tools/bootstrap.ps1
```

```sh
# Fresh-clone source restoration; does not build the complete app or download all assets.
python3 tools/restore-dependencies.py --fetch

# Read-only core check; --archives additionally requires the graphics archives to exist.
python3 tools/restore-dependencies.py --only wine-build-source --only shadps4-fork --only wfm --only dosbox-pure --only mangohud --archives
```

[dependencies.lock.json](dependencies.lock.json) catalogues 19 source identities and graphics archive hashes. [sources.lock.json](sources.lock.json) fixes the original bases. Wine's pinned source says 11.17; the commit, not that version label alone, is authoritative. Existing differing/non-Git directories are not overwritten by restoration. Some checks verify HEAD only and explicitly do not assess local edits; inspect a diff when source cleanliness matters.

The emulator recovery uses [fork.lock.json](fork.lock.json): upstream base `529ceb32f5546b820588f194b903cc39d08015fe`, 17 ordered patches, then the separately hashed [0018 overlay](patches/shadPS4/pending/0018-fixed-executable-and-kernel-signals.patch). Its expected pre-overlay tree is recorded in the dependency lock. Commit metadata can differ after replay; content/tree and overlay checks prevent pretending a different source is identical. The reference shadPS4 checkout is not the fork base.

Wine recovery requires both [patch snapshots](patches/wine/) and the transformations in [prepare-wine-ps4.py](tools/prepare-wine-ps4.py), [prepare-wine-boot.py](tools/prepare-wine-boot.py), module builders and project adapters. The three static Wine patches are not the complete current port. Keep upstream clean; change the generator/overlay, not an ignored generated copy alone.

## 5. Building: follow the dependency graph

Many tools execute at module top level. Do not import arbitrary builders, sweep them with `--help`, or run every `build-*.py` alphabetically: some immediately compile, clear their own work directories, or package/upload. Inspect their source and argparse first.

| Layer | Entry points | Inputs/results to inspect |
| --- | --- | --- |
| Basic diagnostics/PE fixtures | [build.py](tools/build.py), [console fixture](tools/build-console-bare.py) | SDK/upstream sources; `out/build.json`, `out/eboot.bin`, fixture EXEs/DLLs |
| Host Wine/PE build | [build-wine.py](tools/build-wine.py), [host PE closure](tools/build-host-wine-closure.py), [host Unix closure](tools/build-host-wine-unix.py) | `.deps/wine/source`, `.deps/wine/runtime/build`, `out/wine/`, `reports/increment15/host-build/` |
| Prepared prefix | [prepare-host-prefix.py](tools/prepare-host-prefix.py), [package-wine-prefix.py](tools/package-wine-prefix.py), [consumer](tools/wine_prefix.py) | Native-host run first; verified package under `reports/increment15/prefix-package/` |
| PS4 Wine configure/Unix/server | [probe-wine-unix.py](tools/probe-wine-unix.py), [build-wine-ps4.py](tools/build-wine-ps4.py) | Host Wine tools plus OpenOrbis; `.deps/wine/ps4-unix/Makefile`, overlays, `build/wine-boot/`, `build/wine-server/` |
| CPU/32-bit world | [wowprospero](tools/build-wowprospero-ps4.py), [wow64native](tools/build-wow64native-ps4.py), [WoW64 world](tools/build-wow64-world-ps4.py) | Exact PE/Unix recipes, generated object replacements, provider manifests |
| Guest loader/shell | [guest modules](tools/build-guest-hw.py), [Explorer](tools/build-explorer-hw.py), [WFM](tools/build-wfm.py), [open protocol](platform/ps4/pw_shell_open.h) | PE32/PE64 variants and guest lifecycle; regenerated Explorer/WFM manifests |
| Graphics | [win32u](tools/build-win32u-ps4.py), [winevulkan](tools/build-winevulkan-ps4.py), [Vulkan batching](tools/build-winevulkan-batch.py), [wined3d](tools/build-wined3d-hw.py), [DXVK staging](tools/stage-dxvk.py), [graphics recipes](tools/vk-h0/) | RADV/GNM, Mesa WGL/Zink, both PE architectures, Vulkan loader/layer variants |
| Services/input/audio | [Unix libraries](tools/build-unixlibs-ps4.py), [audio](tools/build-audio-ps4.py), [signals](tools/build-signal-ps4.py), [directory filtering](tools/build-wine-directory-ps4.py), [delete server](tools/build-wine-delete-server.py), [HID](tools/build-hidstack-hw.py) | Rebuilt objects and corresponding hashes/manifests |
| PE/runtime closure | [GUI](tools/stage-wine-gui.py), [PE64](tools/stage-wine-pe64.py), [i386](tools/stage-wine-i386.py), [programs](tools/stage-wine-programs.py), [extras](tools/stage-wine-extras.py), [web closure check](tools/check-web-closure.py) | Imports, architecture, duplicate modules, prefix files and runtime hashes |
| Link/package | [link-wine-boot.py](tools/link-wine-boot.py), [build-wine-hardware.py](tools/build-wine-hardware.py), [SELF handling](tools/orbis_self.py), [packaging](tools/orbis_package.py) | `build/wine-boot/link-report.json`, build-specific app/runtime, package manifest |

Typical **configured-workspace** steps, not a complete fresh-clone recipe:

```sh
python3 tools/build.py --with-wine-platform
python3 tools/build-wine-ps4.py --boot --all-unix
python3 tools/build-wine-ps4.py --boot --server
# Rebuild the affected CPU/guest/UI/graphics/service modules and staging closures here.
# WoW64-world and hardware replacements depend on the base recipes above.
python3 tools/link-wine-boot.py
python3 tools/build-wine-hardware.py
```

Before the last two commands, inspect every manifest read by those scripts. The modern hardware package has many more inputs than the early increment-24 command sequence. Rebuild consumers after their inputs change; never repair a stale manifest by editing its hashes.

Prefix order: configure/build host Wine and its PE/Unix closure, run [prepare-host-prefix.py](tools/prepare-host-prefix.py), then package the successful producer run with [package-wine-prefix.py](tools/package-wine-prefix.py). See [increment 15](docs/INCREMENT_15.md) and [preflight integration](docs/INCREMENT_19.md). A valid external prefix is not proof Wine booted; never stage the host's `wow64cpu.dll` as the PS4 provider.

Fresh-clone gaps remain: hardcoded paths in graphics recipes, host configuration and some generated reports used as build inputs. Recreate missing reports through their producers. A fresh clone lacking them must fail visibly rather than consume invented references. See [reconstruction limits](docs/REPOSITORY_LAYOUT.md). No complete clean package rebuild was performed merely by preparing this Git repository.

## 6. Building and running shadPS4

With the pinned compiler/CMake/submodules available:

```sh
python3 tools/build-shad-linux.py --jobs 12
# Only after a matching CMake configuration already exists:
python3 tools/build-shad-linux.py --reuse-configure --jobs 12
python3 tools/build-shad-platform-check.py
```

The Linux builder expects `.deps/linux-tools/cmake/data/bin/cmake`, Clang 19 and libc++. It writes `build/shadPS4-linux/build-manifest.json`, including binary hash, HEAD, tracked source diff hash and submodule identities. The source-cache option additionally requires [cache-shad-source.py](tools/cache-shad-source.py) and a matching cache manifest; never enable it against changed sources.

```sh
# Visible WSLg desktop from an existing, built hardware release.
# W284 is a documented historical example, not "the latest" selector.
python3 tools/run-orbisdesk-shad.py --build W284

# General fork runner; use a private runtime copy as /data.
python3 tools/run-linux-shad.py --fork --config-clean --fullscreen false --mount /tmp/orbisdesk-test-data /data -g build/shad-platform-check/app/eboot.bin
```

[run-orbisdesk-shad.py](tools/run-orbisdesk-shad.py) checks ELF/emulator hashes, copies the release runtime privately, starts a persistent process and records PID/run directory in `build/orbisdesk-shad-visible.json`. This is not a timeout-based test result. `--fresh` creates a new runtime copy; it can re-expose boot/native32 limitations hidden by a previously initialized copy. Read [desktop evidence/limitations](docs/SHAD_W284_DESKTOP.md) and [taskbar/menu checks](docs/TASKBAR_CENTER_FIX.md) first.

[run-linux-shad.py](tools/run-linux-shad.py) selects the fork only with `--fork`. Otherwise it uses the pinned official Linux release with a private glibc. It forces the host Lavapipe ICD: a visible desktop does not demonstrate the console RADV/GNM route or performance.

The older [Windows builder](tools/build-shad.ps1) and [Windows boot runner](tools/run-wine-boot.ps1) have stricter historical clean-HEAD assumptions. They are not drop-in replacements for the current Linux fork with overlay 0018. [run-wine-hardware.py](tools/run-wine-hardware.py) is hardcoded to W011; do not use it to claim a newer build passed.

## 7. Tests and the local matrix

Use focused checks for the changed layer. Run a broader matrix for core loader/VM/ABI changes or an explicitly requested regression campaign. Respect a user's request to skip local runtime matrices and validate on hardware instead; state exactly what was omitted. Documentation-only changes do not require rebuilding Wine or running games.

```sh
# Repository/doc checks require no console or compiled package.
python3 tools/check-repository-layout.py
python3 tools/check-docs-bilingual.py
python3 tests/test_project_brand.py

# Host algorithms: require pinned sources, a host compiler and built fixtures as applicable.
bash tools/test-vm.sh
bash tools/test-pe32.sh
python3 tools/check-wine-fs.py

# One platform case through the Linux fork diagnostic ELF.
python3 tools/run-linux-wine.py --fork --baseline --case files
python3 tools/run-linux-wine.py --fork --baseline --case vm-stress

# Historical increment-18 campaign, with its generated Windows references available.
python3 tools/check-increment18.py --report-dir reports/increment18-new-run
python3 tools/check-increment18.py --verify-only --report-dir reports/increment18-new-run
```

The increment-18 campaign contains 31 runs with expected outcomes, including an official-emulator blocked result. Its fixed expectations concern that diagnostic campaign, not all newer hardware guests. Earlier [increment checks](tools/check-increment11.py) deliberately expect old blockers; rerunning every historical checker against today's sources is not a universal regression suite. `--verify-only` checks saved evidence; it does not execute new tests. Reports and Windows references are ignored and may be missing in a new clone.

PowerShell's [platform matrix](tools/run-probes.ps1), after building the diagnostic ELF/fixtures:

```powershell
./tools/run-probes.ps1 -Cases files,low-memory,generated-code
# Omit -Cases to request its full default platform matrix.
./tools/run-probes.ps1
./tests/report-classification.ps1
```

Its default is the pinned **official Windows emulator**, not the Linux fork. For a Windows fork, supply `-Emulator`, `-EmulatorKind fork`, the actual full `-EmulatorCommit`, and matching `-BuildManifest`; do not pass a Linux ELF emulator binary to this Windows runner. `-IncludeWine` and `-IncludeWinePlatform` additionally require the corresponding built Wine fixture manifests.

For prepared-prefix/boot work, use [run-linux-wine.py](tools/run-linux-wine.py) (`--prepared-prefix`, `--prefix-preflight`, `--wow64-cpu wowprospero`, optional GUI/exe arguments) and the exact [increment 19](docs/INCREMENT_19.md), [23](docs/INCREMENT_23.md), [24](docs/INCREMENT_24.md), [25](docs/INCREMENT_25.md) recipes. Do not mix prefix-preflight, server/services diagnostics and modern packaged-desktop validation as if they tested the same path.

## 8. What evidence means

Record the source revision/diff, input and executable hashes, emulator kind/config, duration, exit/timeout, result files and log paths. Keep new runs in separate directories; never overwrite old evidence or change manifest hashes to make a test pass.

| Observation | What can be claimed |
| --- | --- |
| Native Windows/Linux Wine fixture matches | Reference behavior only; no PS4 validation |
| Prefix preflight succeeds | Package/mappings/architectures verified; not Wine boot |
| Server or ntdll initialization marker | That stage reached; not EXE execution |
| Expected output and verified exit from the intended EXE | Execution for that exact configuration |
| Desktop frame / collector status `presented` | Presentation only; not general application acceptance |
| Menu opens or audio plays | That interaction only; also check teardown and UI responsiveness |
| Fork passes | Fork result; keep official and hardware status separate |
| Old log found after a new upload | Old build evidence until marker/manifest correlation proves otherwise |

`CE-34878-0` is a crash symptom, not a diagnosis. Start from the last build marker, exception/registers, thread/guest exit and matching sources. Do not infer a fixed fault from a screenshot alone. Use minimal native reproductions when deciding whether a failure belongs to Wine, the SDK adapter, the guest model or the emulator.

## 9. Physical PS4 deployment and feedback loop

The available test console was reported as a PS4 Pro Baikal, firmware 12.52 with GoldHEN. This is one user's setup, not a compatibility matrix. FTP uses port 2121. Always use the user's currently supplied address: script defaults still contain historical `.107`, while recent delivery used `.100`.

1. Build and inspect the actual package manifest under `out/wine-hardware-wNNN/manifest.json`; it identifies package, ELF, runtime root and source hashes. Check that upload/fetch tools recognize the chosen build ID. They maintain explicit build lists.
2. With transfer authorization, upload the package **and required runtime**, not just the PKG. Console paths normally include `/data/pkg/OrbisDesk.pkg`, `/data/wine-prefix`, `/data/wine-home` and `/data/wine`. Do not guess a new mount/layout from a historical screenshot.
3. The user closes the current app, installs through the console and launches it manually/through their remote-play workflow. FTP upload is not installation or execution. Let the user select NORMAL/ROOT.
4. Give a short test sequence and, when supported by the chat, a “Ya la probé” reply button. Collect logs when the user reports finishing; do not repeatedly poll a running title instead of respecting that feedback loop.
5. Confirm log build marker and run identity before interpreting results. If it is the old build, report that and help resolve installation; never attribute it to the new one.

Example **after replacing W287/host with the intended build and current console**:

```sh
python3 tools/upload-hardware.py --build W287 --host 192.168.68.100 --port 2121
# After the user finishes testing:
python3 tools/fetch-hardware.py --build W287 --host 192.168.68.100 --port 2121
```

[upload-hardware.py](tools/upload-hardware.py) verifies transfers by reading files back, preserves selected console-owned settings and removes recognized older packages only after successful full verification. `--keep-old-packages` retains them; `--skip-runtime` is only appropriate when the complete required runtime is already present and verified. Preserve user documents, games, registry choices and save data.

[fetch-hardware.py](tools/fetch-hardware.py) archives under `reports/wine-hardware-wNNN/physical/<UTC>/`, including classification, logs, hashes and available frame conversion. [watch-hardware-run.py](tools/watch-hardware-run.py) is an optional long-running watcher for a specifically requested program; it is not the default feedback mechanism and normal desktop sessions need not exit.

For UI/lifecycle changes, a useful focused physical sequence is: open the target app, interact, close it, reopen Start; for shared graphics teardown, repeat two cycles with vkcube, glxgears and vkspin, closing vkcube first. Add WFM file/directory or audio tests when those paths changed. Capture the actual display and the matching logs. Do not fabricate/retouch a screenshot as test evidence. Check responsiveness after successful playback/rendering, not only the first frame or sound.

## 10. Where to investigate next

| Topic | Primary navigation |
| --- | --- |
| Build/dependency recovery and remaining clean-build gaps | [Layout](docs/REPOSITORY_LAYOUT.md), [dependency lock](dependencies.lock.json), [restore tool](tools/restore-dependencies.py) |
| Guest processes, PE32 world, fixed-base games and shared-state limitations | [WoW64/guest investigation and results](docs/investigacion-wow64-en-explorer.md), [fixed-base investigation](docs/investigacion-gta-vc-base-0x400000.md) |
| Native ABI, memory, TLS, signals, IPC and emulator services | [increments 01–25 in the index](docs/INDEX.md), [PS4 adapters](platform/ps4/), [platform reproduction](native/shad_platform_check.c) |
| Graphics, MangoHud teardown and metrics | [graphics history](docs/HARDWARE_G001.md), [W098](docs/HARDWARE_W098.md), [W102](docs/HARDWARE_W102.md), [W104](docs/HARDWARE_W104.md), [graphics recipes](tools/vk-h0/) |
| WFM launch/open protocol, text associations and recursive delete | [W105](docs/HARDWARE_W105.md), [W106](docs/HARDWARE_W106.md), [W107](docs/HARDWARE_W107.md), [W111](docs/HARDWARE_W111.md), [WFM operations](tools/wfm-operations.h) |
| Controller/USB input | [HID](docs/HARDWARE_mando-hid.md), [game input analysis](docs/HARDWARE_mando-juegos-analisis.md), [XInput builder](tools/build-xinput-hw.py), [DirectInput builder](tools/build-dinput-hw.py) |
| Fonts, caption glyphs, taskbar, Start and themes | [text rendering](docs/INCREMENT_25.md), [font attribution](docs/THIRD_PARTY_FONTS.md), [menus/taskbar](docs/TASKBAR_CENTER_FIX.md), [Explorer builder](tools/build-explorer-hw.py) |
| DOS and bundled game engines | [DOS runtime](docs/HARDWARE_W112.md), [games](docs/GAMES.md), [DOS pins](dos.lock.json), [game pins](games.lock.json) |
| Native Steam client phases | [S1](docs/STEAM_S1.md), [S2](docs/STEAM_S2.md), [S3](docs/STEAM_S3.md), [native code](native/steam/) |
| Attribution, public/private documentation and naming | [Third party](THIRD_PARTY.md), [documentation policy](docs/DOCUMENTATION_POLICY.md), [branding](docs/REBRANDING_ORBISDESK.md) |

CPU/GPU counter responses are not an independent absolute calibration. A game's successful launch is not proof of safe shutdown, concurrent guest execution, isolation or general compatibility. Keep these boundaries explicit when reporting progress.

## 11. End-of-task checklist for an agent

- State what changed, why, what was actually tested, and what remains unverified. Keep the final answer concise and link the relevant artifact/log/document.
- Update both documentation languages and regenerate the [index](tools/build-doc-index.py) when public documents are added/moved. Checks validate navigation, not translation accuracy.
- For code changes, retain canonical source transformations, patch context checks and attribution. For evidence, keep source/binary identity and separate official/fork/hardware classifications.
- Before a commit, run layout and bilingual checks, inspect `git diff --check`, inspect staged paths, reject ignored/private content and gitlinks, and verify no concurrent edits were unintentionally captured. Commit/push only within the user's authorization; use SSH when requested and never force-push over unexpected remote history.
- Do not request console testing before the requested build has actually been built and transferred. Do not claim an upload, screenshot, process exit or installation that was not observed.
