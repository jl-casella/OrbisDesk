# Product builds, releases and the development branch

[English](RELEASES.md) | [Español](RELEASES-es.md)

## Status and scope

`Build PKG and release` is an **experimental clean-build workflow**, separate from the diagnostic matrix. Its first complete GitHub-hosted product build has not yet been demonstrated. It does not copy a developer build tree, run a self-hosted runner or use the home PS4. A missing prerequisite, compilation error, package error or inconsistent runtime fails the run and prevents publication.

The first pilot may expose further assumptions in the historical recipes. Do not describe this workflow as a proven complete rebuild until the successful run and its artifacts have been inspected. The local validation covered workflow syntax, Python compilation and rejection tests for altered/escaping distribution inputs; it did not build or boot a new product.

## Manual pilot

After merging this implementation into `main`, open **Actions → Build PKG and release → Run workflow**:

1. Select `main`.
2. Leave `publish` unchecked for the first build-only pilot.
3. Run the workflow. Download `product-evidence-*` even when the build fails. The last `product-*` phase and its log identify the next portability problem.
4. On success, inspect `product-candidate-*`, its hashes and the complete runtime. Test the exact candidate on the emulator and/or console as appropriate; building is not boot validation.
5. For a published candidate, run manually with `publish` checked. This makes a new clean build at that run's SHA; it does not promote a previously tested binary or carry over hardware acceptance.

The actor and rerun actor of manual runs must both equal the repository owner. Other writers may still see GitHub's Run workflow button, but authorization fails before building. The workflow also requires `refs/heads/main`. This is a workflow guard, not a replacement for protecting edits to workflows or `main` itself. See [GitHub contexts](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts).

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

The extraction now includes both directories and matches complete path components, avoiding similarly named unrelated trees. The setup wrapper also retains full libc++ output instead of piping it through `tail -15`; `product-setup-libcxx.log` will contain the complete configure/build diagnostics. Keep the LLVM archive revision/hash unchanged. The next hosted pilot must use the fix merged into `dev` and promoted to `main`, since manual release runs require `main`. Rerunning the old SHA cannot test the correction. Full product build, packaging and boot acceptance remain pending.

A focused local check used the original archive with verified SHA-256 `ae67086eb04bed7ca11ab880349b5f1ab6f50e1b88cda376eaf8a845b935762b`, fresh extracted sources, isolated build directories and the prepared PS4 compiler/sysroot. The original selection reproduced the missing-directory configure failure (exit 1); adding `llvm/utils/llvm-lit` allowed CMake configuration/generation to finish (exit 0). This verifies the source/configure correction only, not compilation of libc++ or the full hosted product.

## Installation and the dev → main flow

A PKG alone is insufficient: its matching runtime must also be staged into `/data`. Follow the candidate's installation notes, back up existing registries/documents/settings/saves and use a merge-aware update procedure for an existing installation. The archive represents a fresh runtime; blindly replacing an installed prefix can lose user state. No FTP upload or console installation occurs in Actions.

`dev` has been created from main. Day-to-day feature/fix PRs target `dev` and run the quick checks plus the complete diagnostic matrix, as described in [CI operation](CI.md). When a coherent group of changes is ready, open a `dev → main` PR, review/test that group, and merge. With automatic releases enabled, that main push builds and publishes the group. Keep main protected, do not automatically merge dev, and retain manual builds for investigations.

See also [CI operation](CI.md), [CI rollout plan](CI_PLAN.md), [dependency layout](REPOSITORY_LAYOUT.md) and the [developer guide](../AGENTS.md).
