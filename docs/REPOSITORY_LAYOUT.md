# Repository contents and dependency reconstruction

[English](REPOSITORY_LAYOUT.md) | [Español](REPOSITORY_LAYOUT-es.md)

Source-only repository layout recorded on 2026-11-07. The root repository uses branch `main`. External checkouts and evidence remain local, excluded from the published source tree.

## What belongs in Git

Keep project sources in `native/`, `platform/`, `fixtures/`, scripts and patch generators in `tools/`, focused checks in `tests/`, `patches/`, root lock files, bilingual documentation and attribution/license files. Adapted source fixtures with their attributions remain source inputs; downloaded library trees and compiled applications do not.

Ignore `/upstream/`, `/.deps/`, `/build/`, `/out/`, `/private-notes/` and all `/reports/`, plus generated executables/libraries/packages, archives, caches and local environment files. Previously only `reports/runs/` was ignored; reports can contain full runtimes, prefixes, captured files, binaries and archives. They are not safe candidates for an initial source commit. Ignoring these paths does not delete them. Historical documentation may still link to local evidence that a new clone will not contain.

## External locations

| Folder | Contents | Git treatment |
| --- | --- | --- |
| `private-notes/` | Local research and comparisons, with their language variants | Ignore entire directory; keep public documentation independent of it |
| `upstream/` | prospero-win, DolphinPS4, Crema, Resonance, reference shadPS4, Playden export; Wine can be fetched here too | Ignore entire directory |
| `.deps/wine/` | Clean Wine source, host builds and generated PS4 overlays | Ignore; keep Wine pin, patch snapshots and generators |
| `.deps/shadPS4-fork/` | Local emulator fork and submodules | Ignore; keep base, 17 patches and overlay 0018 |
| `.deps/shadPS4/`, `.deps/shadPS4-linux/` | Official emulator downloads | Ignore; releases/hashes in artifact locks |
| `.deps/sdk/`, `.deps/windows-tools/`, `.deps/linux-tools/`, `.deps/linux-runtime/` | SDK, compilers and private runtimes | Ignore; keep artifact locks |
| `.deps/vk/` | Mesa/libdrm archives, llvm-mingw, MangoHud and reference MangoJuice | Ignore; keep pins and `tools/vk-h0/` recipes |
| `.deps/dosbox-pure/`, `.deps/wfm/`, `.deps/reactos-games/` | Optional application/runtime sources | Ignore; keep pins and adapters |
| `.deps/downloads/`, `.deps/steam/`, `.deps/games/`, `.deps/wallpaper-cc0/` | Downloaded assets, browsers, Vulkan/Direct3D components, game inputs and Steam dependencies | Ignore; versions/hashes remain in locks and staging recipes |
| `.deps/doc-translation/`, `.deps/doc-translate-venv/` | Local translation models and Python environment | Ignore; not application build inputs |
| `~/vk-h0/` in WSL (`/home/jose/vk-h0/` here) | Graphics source copies, toolchain, virtualenv, sysroot and builds | Outside this Git root; reconstruct separately |

## Pinned source revisions

The machine-readable catalogue is `dependencies.lock.json`. Paths beginning with `~/` are WSL home paths. Revisions are source identities, not claims that every checkout is clean or currently used by the main package. MangoJuice is reference material; MangoHud is the active overlay base.

| Dependency | Path | Commit |
| --- | --- | --- |
| prospero-win | `upstream/prospero-win` | `0e7b6b4a53a9aebfeceaf28fabb919e2452bbadc` |
| DolphinPS4 | `upstream/DolphinPS4` | `879b3e57f3d3180bcb5f2234db3903688b28cd7d` |
| Crema | `upstream/Crema` | `475b8d5bd3498dbd5cfefe8175f98d017a017739` |
| Resonance | `upstream/Resonance` | `6b87389033d4f239e97d36c605bf7eea384d1e23` |
| shadPS4 | `upstream/shadPS4` | `1d8004a22feb0d5cc58828bac066018e80b6d73f` |
| wine | `upstream/wine` | `490f6d5dcbb2a5047345b8af88d114bbcaad69a8` |
| wine-build-source | `.deps/wine/source` | `490f6d5dcbb2a5047345b8af88d114bbcaad69a8` |
| dosbox-pure | `.deps/dosbox-pure` | `ba6dcaee84aa2c22d709c3dfdacb7aca5ebc3042` |
| wfm | `.deps/wfm` | `6b1860895885a6d65c37815308260293341acb5f` |
| reactos-games | `.deps/reactos-games` | `5f6ef754f90eef792e4ef90561bcff2cac4d3afb` |
| mangohud | `.deps/vk/mangohud-win/repo` | `52592550824ae11d5c68a6826f07db5f60220d23` |
| mangojuice | `.deps/vk/mangojuice-win` | `e2ec0755f83975be5f0b593ee59cee62e793ed4a` |
| playden-ps5 | `upstream/playden-ps5` | `fb74dbfd6bb96fc19a96afc1f48a4e40a885216b` |
| Vulkan-Headers | `~/vk-h0/src/Vulkan-Headers` | `2fa203425eb4af9dfc6b03f97ef72b0b5bcb8350` |
| Vulkan-Loader | `~/vk-h0/src/Vulkan-Loader` | `052ac24611eced7b0ca62cc5cca2eeeb2051fa28` |
| Vulkan-Tools | `~/vk-h0/src/Vulkan-Tools` | `48b5d246b2d0b1a41ee7ea1b69525ae7bb38a2ae` |

Wine's source `VERSION` says **11.17**. The fork base is `529ceb32f5546b820588f194b903cc39d08015fe` (official emulator v0.20.0); the historical 17-patch HEAD is `9ac99bb2445e86f525519a4041a6c85362790ad2`. The reference shadPS4 revision in `sources.lock.json` is separate; do not substitute it for the fork base.

## Wine and emulator changes

Wine's clean build base is `.deps/wine/source`. Keep `patches/wine/` **and** `tools/prepare-wine-ps4.py`, `tools/prepare-wine-boot.py`, the Wine/module builders, and project adapters. Many current modifications are expressed as checked transformations in these scripts. The three static Wine patches alone do not describe the entire current port. Generated source trees are not tracked.

For shadPS4, `fork.lock.json` defines the upstream base and ordered 17-patch series with SHA256 values. `dependencies.lock.json` additionally records the expected HEAD tree and `patches/shadPS4/pending/0018-fixed-executable-and-kernel-signals.patch`, SHA256 `d37d54454bc340c54e15c2a867c76c5fcca58a3eee860c81d0b1ed72fff4e30f`. It exactly matched the current complete tracked source diff during this preparation. Rebuilding commits can change commit IDs through committer metadata; content is checked against tree `a37a8cb543e0dc107a654f1e998112eb57890bef` before applying the overlay.

## Restore and inspect

Run from the repository root in Ubuntu 22.04 WSL, using Python 3.10 or later:

```sh
# Read-only inspection of the core sources, fork overlay and graphics archives.
python3 tools/restore-dependencies.py --only wine-build-source --only shadps4-fork --only wfm --only dosbox-pure --only mangohud --archives

# On a fresh clone, fetch pinned repositories, replay the fork patches and overlay,
# and initialize its pinned submodules. Existing differing trees are rejected.
python3 tools/restore-dependencies.py --fetch

# Optional: restore only the two central source trees.
python3 tools/restore-dependencies.py --fetch --only wine-build-source --only shadps4-fork

python3 tools/check-repository-layout.py
python3 tools/check-docs-bilingual.py
```

The restore tool does not delete/replace existing trees, download archive assets, extract SDKs, apply every module-specific transformation or compile the package. An existing non-Git Playden export is reported as revision-only during inspection; fetching refuses to replace it. A fresh clone restores it from the pinned upstream commit. Graphics archive URLs and SHA256 values are in `dependencies.lock.json`; SDK/emulator and other tools are covered by `artifacts.lock.json`, `fork-tools.lock.json` and the Linux locks. `build-environment.lock.json` records the installed WSL package versions and graphics Python package versions observed here.

## Validation and remaining rebuild work

Preparation replayed all 17 emulator patches against the exact upstream base using a temporary Git index, reproduced the expected tree, and applied overlay 0018 to that index. The actual fork checkout was unchanged. Core revision checks and the three graphics archive hashes passed. No package compilation or hardware test was performed for this repository change.

Source recovery is demonstrated for the emulator patch series; a complete fresh-clone package build is **not yet demonstrated**. Before claiming that, remove workstation-specific `/mnt/c/Users/JoseCasella/...` paths from graphics recipes, orchestrate host Wine configuration/prefix generation, recreate build-input reports (for example `reports/increment15/host-build/report.json`), and exercise SDK, graphics, PE closure and packaging in dependency order. Do not re-include cached runtimes or reports to hide missing generation steps. Optional downloads also retain pins in their builder/staging scripts; the new catalogue is not a universal package manager.
