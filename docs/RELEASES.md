# Product builds, releases and the development branch

[English](RELEASES.md) | [Español](RELEASES-es.md)

## Status and scope

`Build PKG and release` is an **experimental product workflow** supporting cold builds and verified dependency snapshots, separate from the diagnostic matrix. Its first complete GitHub-hosted product build has not yet been demonstrated. It does not copy a developer build tree, run a self-hosted runner or use the home PS4. A missing prerequisite, compilation error, package error or inconsistent runtime fails the run and prevents publication.

The first pilot may expose further assumptions in the historical recipes. Do not describe this workflow as a proven complete rebuild until the successful run and its artifacts have been inspected. The local validation covered workflow syntax, Python compilation and rejection tests for altered/escaping distribution inputs; it did not build or boot a new product.

## Manual pilot

Open **Actions → Build PKG and release → Run workflow**. The workflow must already exist on the default branch; build-only fixes can be tested from their pushed branch before merging:

1. Select the branch to test, for example `ci/release-llvm-lit`, or `main` for the integrated recipe.
2. Leave `publish` unchecked for the first build-only pilot and keep `cache_mode=reuse`. Select `cold` when deliberately rebuilding all dependency blocks.
3. Run the workflow. Download `product-evidence-*` even when the build fails. The last `product-*` phase and its log identify the next portability problem.
4. On success, inspect `product-candidate-*`, its hashes and the complete runtime. Test the exact candidate on the emulator and/or console as appropriate; building is not boot validation.
5. For a published candidate, first merge the tested fix through `dev` to `main`, then select `main` and run manually with `publish` checked. This makes a new clean build at that run's SHA; it does not promote a previously tested binary or carry over hardware acceptance.

The actor and rerun actor of manual runs must both equal the repository owner. Other writers may still see GitHub's Run workflow button, but authorization fails before building. Manual build-only runs (`publish=false`) accept branch refs; publication and automatic builds require `refs/heads/main`. The authorization script, publisher job condition and publication helper keep that boundary explicit. This is a workflow guard, not a replacement for protecting edits to workflows or `main` itself. See [GitHub contexts](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts).

## Product dependency caches

`cache_mode=reuse` is the manual default and is also used by automatic main builds. `cold` bypasses all three Actions cache restores and rebuilds both dependency blocks; it can still populate verified caches for later runs. A fresh workspace is required in either mode. Caches are restored into isolated `.deps/product-cache/` bundles, not directly over an existing SDK, prefix, Wine source or runtime. The recipe fetches/verifies pinned sources and the SDK before installing any dependency snapshot.

| Cache | Contents | Behavior |
| --- | --- | --- |
| Verified downloads | Explicit locked archives/assets, named by SHA-256 under `.deps/product-downloads` | Every consumed file is rehashed; save new completed downloads even after a later failure, preferring complete cache entries on restore |
| Graphics | Allowlisted build/source/tool directories under `~/vk-h0`, including libc++, glslang, RADV, both Zink builds, loaders, MangoHud and vkcube | Skip the expensive graphics block only after validating the snapshot; recreate the Python venv each run |
| Host Wine | Native build tree/tools, staged base PE files and host closure reports | Skip the three host build steps only after validating the snapshot; generate and test a new prefix every run |

Each block has its own exact key binding source/SDK pins, recipes, ordered fork patch inputs where relevant, installed packages, compiler/tool hashes and versions, architecture/kernel, build environment and absolute workspace/home paths. The application's commit alone is not a cache key. Changing `build-host-wine-unix.py`, for example, invalidates Wine without invalidating graphics. Shared infrastructure/recipe changes invalidate both; graphics keys conservatively include native/platform inputs. Fresh Wine source file timestamps are normalized only after checking a clean pinned checkout, preventing a new checkout's timestamps from forcing recompilation of every cached object. Generated outputs retain their producer timestamps and modes.

`product_cache.py` seals each completed block before proceeding to the next stage. After the product step, `always()` save steps retain newly sealed blocks even if prefix creation, console compilation or packaging subsequently failed. Failed/incomplete blocks are not saved. A hit is not uploaded again. Cache manifests record producer commit/run, input identity and a complete file/link inventory; payload and individual file hashes are checked before live restoration. Absolute/traversing archive paths, unexpected archive links, external symlinks, linked destination ancestors, changed payloads and overwrites of existing outputs are rejected. Explicit SDK/source symlinks are permitted only into pinned restored inputs. Restore moves verified staged files into place to avoid retaining a second full expanded copy.

Only fixed dependency mounts are snapshotted. Git metadata, private notes, the graphics venv and the separately restored Vulkan/LLVM source inputs are excluded. Prefix producers, registries, user documents, console data, final PKGs, SSH keys and the rest of `.deps/` are not cache inputs. Prefix creation/fixture validation, PS4 adapters, final staging, packaging and distribution checks still execute for the current SHA. `build-provenance.json` includes block reuse/producer identities; caches never transfer Wine boot or hardware acceptance.

Inspect `reports/ci/product-cache-inputs.json`, `product-cache-status.json`, `product-download-cache.json` and the `product-cache-restore-*` / `product-cache-seal-*` phases. They distinguish reused/rebuilt blocks and record restore times and newly sealed archive sizes. The first run normally populates caches; the following run on the same branch/environment can measure savings. New branches/main cannot necessarily read caches produced by a feature branch, and caches can be evicted. See [GitHub cache scope](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching). Use only trusted build triggers for snapshot publication; these checksums provide integrity checks, not signatures or trust in arbitrary PR artifacts.

Local validation covers filesystem roundtrips, preserved modes/times, allowed SDK links, tamper/path/link rejection, cold behavior, source timestamp checks, independent keys and retaining a completed block after later failure. A read-only audit checked real prepared graphics output paths and link shapes without copying that workstation tree into a release cache. A hosted cold population and subsequent warm hit remain to be measured; no speedup or full product acceptance is asserted yet.

## Automatic releases from main

The workflow declares `push: branches: [main]`, which covers both direct pushes and merged PRs. Automatic runs remain skipped until the owner sets the repository Actions variable **`ORBISDESK_AUTO_RELEASE=true`** after a successful manual pilot. Remove or set that variable to false to return to manual operation. This rollout switch avoids publishing on the merge that first introduces the unproven build recipe.

Once enabled, each main push runs the same checks and clean product build, then creates the tag and publishes an **experimental prerelease** only after every required job succeeds. There is no trigger on `dev`, pull requests or tag pushes. Publication failures leave a draft rather than a partially uploaded public release. Build jobs have read-only repository permissions; only the separate publisher has `contents: write`.

GitHub repository settings should protect main with the verified PR checks. Optional environment reviewer rules can provide a later manual promotion gate; no reviewer configuration is installed by these files. GitHub documents those settings in [deployments and environments](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments).

## Versions, tags and notes

The SFO version and the NORMAL/ROOT boot-selector version use the same `NN.NN` value. It is calculated as `ORBISDESK_RELEASE_VERSION_BASE + workflow run_number - 1`, with a default base of `400` (04.00 on run number 1). Skipped/failed runs consume run numbers; gaps are expected. Reruns retain the same version. Before enabling automation, choose a base above all installed/manual versions and coordinate that namespace with manual hardware builders. Exhausting 99.99 fails explicitly; versions never wrap.

The tag is `orbisdesk-<NN.NN>-<12-character SHA>`, attached to the exact built commit. Existing tags are never moved. An already published release is never overwritten. A retry can finish an existing draft only for the same tag/commit. No stable/latest release is claimed automatically during this initial rollout.

Release notes use GitHub's generated notes plus the Git commit subjects since the closest prior published OrbisDesk release on the target's ancestry. The first release includes the available history. The source SHA and validation scope appear in the notes. See [GitHub release APIs](https://docs.github.com/en/rest/releases/releases).

## What is built and uploaded

[build-product.py](../tools/ci/build-product.py) restores pinned sources, SDK and archives into ignored directories, prepares native Wine and the sealed prefix, builds PS4 Unix services, both PE architectures, RADV/Zink/loaders/layers, shell and guests, and finally invokes the canonical [hardware package builder](../tools/build-wine-hardware.py). The order follows the input-manifest graph; it is not an alphabetical sweep of builders. Native Steam is a separate product and is not built here.

The recipe uses Ubuntu 22.04, Python 3.12, the checked toolchain versions and .NET 8 for the SDK's managed package tool. Graphics scripts resolve the current checkout instead of the author's Windows path. `~/vk-h0` is populated on the fresh runner from pinned sources, not copied from a workstation. Additional asset URLs/hashes are in [product-assets.lock.json](../product-assets.lock.json); existing dependencies remain in their original locks.

The historical Windows System.Drawing wallpaper conversion is replaced by a recorded Pillow RGB/crop/bicubic conversion in the clean recipe; it uses the same pinned CC0 photograph but its BMP hash may differ. Package identities remain `ORBW00002` and the existing Content ID. The internal W288 builder/runtime names are retained as recipe/evidence identities; release provenance records the actual Git SHA and SFO version. Default local builds retain 03.87 unless `--app-version` is explicitly provided.

The candidate contains:

- `OrbisDesk.pkg` and the matching fresh `OrbisDesk-runtime.tar.gz` (contents rooted at `data/`).
- Product/build/release manifests with source identity, runtime inventory and hashes.
- `SHA256SUMS`, `THIRD_PARTY.md`, `LICENSES.tar.gz` and installation notes.

Large runtime archives are split into ordered `.partNNN` files below GitHub's per-asset size limit. No console registries, documents, credentials, downloaded source checkouts or private notes are collected from a developer machine. Existing required source/notice material explicitly staged into the product runtime remains part of that runtime.

[release.py](../tools/ci/release.py) rejects changed PKGs, changed sources, extra/missing runtime files, altered payloads, symlinks and paths escaping the runtime. It uploads assets to a draft, checks the remote asset inventory and SHA-256 digests, and then publishes. A failed build never reaches this job. Packaging/import checks are the current gate: Wine boot, GUI smoke and physical hardware acceptance are explicitly pending, not implied by publication. The 31-case diagnostic matrix remains a separate manual workflow and is not yet a release prerequisite.

The workflow allows six hours for the clean build. This is a limit, not a measured duration. Hosted-runner disk/memory, archive availability, source configuration, graphics subprojects and obsolete assumptions may be the first pilot's blockers. Preserve their real failure logs and fix the canonical recipe; do not restore a local runtime to turn the build green.

## First hosted pilot: missing LLVM runtime source

Run `42503388231` on `7d8ccdd5a58679432f41c645c5eda6ea3574bba8` passed source restoration, pinned downloads, graphics environment setup and LLVM-MinGW setup, then failed during `product-setup-libcxx`. CMake could not find `llvm/utils/llvm-lit/CMakeLists.txt`: the clean product's partial LLVM extraction included `llvm/utils/lit` but omitted the separate `llvm/utils/llvm-lit` directory required by the pinned runtime CMake configuration. This is a source preparation failure, before a PKG or Wine boot test.

The extraction now includes both directories and matches complete path components, avoiding similarly named unrelated trees. The setup wrapper also retains full libc++ output instead of piping it through `tail -15`; `product-setup-libcxx.log` will contain the complete configure/build diagnostics. Keep the LLVM archive revision/hash unchanged. The next build-only hosted pilot can select the pushed fix branch with `publish=false`; publication still requires promotion through `dev` to `main`. Rerunning the old SHA cannot test the correction. Full product build, packaging and boot acceptance remain pending.

A focused local check used the original archive with verified SHA-256 `ae67086eb04bed7ca11ab880349b5f1ab6f50e1b88cda376eaf8a845b935762b`, fresh extracted sources, isolated build directories and the prepared PS4 compiler/sysroot. The original selection reproduced the missing-directory configure failure (exit 1); adding `llvm/utils/llvm-lit` allowed CMake configuration/generation to finish (exit 0). This verifies the source/configure correction only, not compilation of libc++ or the full hosted product.

## Zink build status and evidence

A later excerpt on `f42fa6141ac4bc91a391aecf21be2fd52821475e` reaches `product-build-mesa-zink` and reports exit 1 after 129.636 seconds; it does not include the compiler error or establish whether Ninja failed. Inspection found a separate reproducible shell bug: the PE64 wrapper's diagnostic `grep` pipelines return 1 when a successful build contains no matching failure lines, and `set -euo pipefail` treats that as a build failure. Those redundant summaries are removed. Both PE64 and PE32 wrappers now stream Ninja output through `tee` into the product log while preserving Ninja's exit code with `pipefail`, and retain complete Meson setup output. This also exposes actual compiler errors that previously remained in `~/vk-h0/build/mesa-zink*.log` outside the evidence upload paths.

Focused tests execute each actual shell trailer with controlled Ninja outcomes: zero with no error lines succeeds, and a nonzero status remains a failure while retaining output. They validate shell status/log handling only, not Mesa compilation. The supplied traceback alone does not prove this bug caused that hosted failure; inspect the corresponding `product-evidence-*` archive or the next run's complete log before claiming the Zink stage is fixed in GitHub.

## Host Wine PE closure: run 42512489326

Run `42512489326` at `78225f28a32da0315271b5691a54484b17cb4139` passed libc++, glslang, Mesa/RADV, both Vulkan loaders, PE64/PE32 Mesa Zink, both MangoHud builds, vkcube, fixtures and the initial Wine PE build. It failed immediately in `product-build-host-wine-closure` with `Missing required PE64 targets: ['wineusb.sys']`. This establishes hosted progress beyond the Zink wrapper correction, not a complete product build.

The pinned Wine configure disables `wineusb.sys` when libusb development files are absent. The working prepared host build used an additional `--enable-wineusb-sys` flag, missing from the reproducible builder. The builder now explicitly enables the real PE resource module. This matches the existing host-prefix design: `build-host-wine-unix.py` omits the unused host USB Unix backend, while the PE closure requires the driver resources. It does not enable console USB support or replace a module with a stub; the required-target/import checks remain unchanged.

A focused local check used the pinned Wine source and a fresh temporary build, explicitly passing `--without-usb` to avoid relying on installed libusb. Without the new option, configure omitted the PE64 target; with it, the target appeared and `make -j2 dlls/wineusb.sys/x86_64-windows/wineusb.sys` compiled the actual PE successfully (exit 0). This verifies the configuration/module correction, not the complete host closure, prefix boot or hosted release.

Release evidence now also includes native Wine configure/compiler logs, the host closure logs/reports and generated prefix-producer logs/report JSON. Prefix archives and user content are not added to the evidence upload. A fresh build/configuration is needed to apply the option; rerunning the old workflow revision or reusing its configured Makefile does not verify the fix.

## Wine delayed-import aliases: run 42521647656

Run `42521647656` on `52634fb50e231665afc9a765bd568badf3cf01d3` built the required Wine PE targets, including the previously missing USB resources. The host closure compiled 156 modules over six make batches, then rejected four dependencies: `winspool.dll` from `gdi32.dll` and `comdlg32.dll` on both architectures. The report records them as source-derived delayed imports. The pinned `dlls/winspool.drv/Makefile.in` declares `MODULE = winspool.drv` and `IMPORTLIB = winspool`: appending `.dll` to every extensionless alias invented the wrong dependency name.

The host closure now builds an architecture-specific alias map from `IMPORTLIB` declarations belonging to configured PE targets, resolving each source delayed import to its actual module filename. Missing imports still reach the existing rejection check; conflicting aliases and unexpanded variables fail explicitly. No PE file is renamed or patched. Local checks exercised the alias map against 1,490 configured targets (478 aliases), resolving `winspool` to `winspool.drv` on both architectures, and tested malformed/missing/ambiguous cases. This is resolver validation, not a new complete closure build or hosted product acceptance. The next fresh branch build must compile the added driver/dependencies and continue prefix preparation.

## Native Wine entry points: run 42526738112

Run `42526738112` at `9a844ba31aba52cab493d750af9f124d83d23e54` passed the PE closure and Unix-library build. Prefix preparation then failed before starting Wine: `loader/wine` did not exist. Selecting the closure's Unix libraries did not implicitly build the native launcher or wineserver on a clean runner; the prepared workstation had those additional build outputs already.

`build-host-wine-unix.py` now explicitly builds `loader/all` and `server/wineserver` alongside the libraries/data. The loader target also generates `loader/wine.inf` and the Linux preloader. `unix-report.json` records hashes for the launcher, preloader, server and INF in addition to existing library/data hashes. Prefix preparation checks these files, executable permissions and its PE/fixture inputs before launching, reporting missing prerequisites directly. A successful native tools build still does not establish that wineboot, the prefix fixture or the PS4 product runs; those subsequent gates remain unchanged.

A local fresh temporary build of the pinned source successfully ran `make -j2 loader/all server/wineserver`, produced all three native ELF executables and `wine.inf`, and returned exit 0 from `wineserver --version` (`Wine 11.17`). This verifies compilation of the native entry points, not a complete runtime or prefix boot.

## API-set schema and forwarded exports: run 42533695365

Run `42533695365` on `473f337e81ebf66016fce6405b25b5eae6b826e1` started the native loader and wineserver, but wineboot exited 1 after approximately 41 seconds. It wrote all three registry files, yet the fixture was never executed and `prefix_ready_for_packaging` remained false. Its log reports a missing API-set schema (`c000000f`) and an unavailable `cryptbase.SystemFunction036` forwarder exported by `advapi32.dll`. The later cache-only change does not fix those runtime dependencies: a successfully compiled host block can still have an incomplete boot closure, and prefix verification must keep running.

The host closure now requires real `apisetschema.dll` targets for both architectures and reads PE export directories as well as normal/delayed imports. Forwarded exports add their actual provider modules to the recursive build graph (including `cryptbase.dll` and `cryptsp.dll` for advapi32), with providers recorded in `forwarded_imports`. Target discovery also includes additional PE suffixes: Wine's `krnl386.exe16`, for example, is a PE32 wrapper despite its legacy name. Files still pass the PE parser; this is not a new Win16 compatibility claim or a stub substitution.

Local validation compiled real PE32/PE64 forwarder fixtures and checked real pinned advapi32/kernel32/API-schema images. A read-only graph audit visited 171 nodes without finding unconfigured dependencies among parsed images; one local x64 bcrypt binary was absent and was not parsed. This is partial local graph validation, not a new hosted prefix boot. The closure builder and existing module resolver are Wine-only cache inputs, so this correction invalidates the Wine block without changing the graphics key. Run a new branch build with `cache_mode=reuse`; wineboot and the fixture must still pass before the prefix can be accepted.

## Installation and the dev → main flow

A PKG alone is insufficient: its matching runtime must also be staged into `/data`. Follow the candidate's installation notes, back up existing registries/documents/settings/saves and use a merge-aware update procedure for an existing installation. The archive represents a fresh runtime; blindly replacing an installed prefix can lose user state. No FTP upload or console installation occurs in Actions.

`dev` has been created from main. Day-to-day feature/fix PRs target `dev` and run the quick checks plus the complete diagnostic matrix, as described in [CI operation](CI.md). When a coherent group of changes is ready, open a `dev → main` PR, review/test that group, and merge. With automatic releases enabled, that main push builds and publishes the group. Keep main protected, do not automatically merge dev, and retain manual builds for investigations.

See also [CI operation](CI.md), [CI rollout plan](CI_PLAN.md), [dependency layout](REPOSITORY_LAYOUT.md) and the [developer guide](../AGENTS.md).
