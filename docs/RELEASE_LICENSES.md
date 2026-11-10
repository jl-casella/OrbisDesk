# Release licenses (alpha-1)

[English](RELEASE_LICENSES.md) | [Español](RELEASE_LICENSES-es.md)

Licence review for publishing OrbisDesk alpha-1 as one package with its runtime embedded (about 1.1 GB, extracted to `/data` on first start). The review covers the W301 ELF and `build/wine-hardware-w301/runtime` (1835 files, about 1.08 GB), which today go to the console by FTP. Recorded on 2026-11-08.

**This is a technical analysis, not legal advice.** It records which code is in each binary, the licence each file or project declares, and what those licences ask of a binary distribution. Where a conclusion depends on legal interpretation, it says so. A lawyer should review it before a release with wider reach.

## Summary

| Item | Status | Blocks alpha-1? |
| --- | --- | --- |
| GPL compatibility of the ELF (Playden GPL-3.0-or-later with Wine, Mesa, Crema, DolphinPS4, own code) | No GPL-2.0-only code found; the combination can be distributed as GPL-3.0-or-later | No |
| Licence texts, copyright notices and source pointer inside the package/runtime | Missing in W301 (the Steam texts too, since the client moved into the ELF). Builder change applied to `tools/build-wine-hardware.py` after W301; not yet built | **Yes**, until a build ships it |
| Corresponding source published with the release (own code, Wine, Mesa, VLC, Wine Gecko, DOSBox Pure, gbe_fork and the ELF's libraries) | Publishing from `main` creates the tag and attaches the source archive (section 5); no release published yet | **Yes**, until the first published release |
| `libcdio.dll` (GPL-3.0-or-later) is a prebuilt binary from the WFM repository with no known corresponding source | Removed (the user's decision): WFM is built without it and loses "Load ISO image"; the upload deletes the console's copy. Not yet built | No, once a build without it ships |
| Build PC identity in the runtime (`C:\users\jose`, `JCASELLA`, `/mnt/c/Users/...` strings) | Found; the registry names are fixed in the builder (not yet built) | No (privacy/cleanliness) |
| `THIRD_PARTY.md` entries | Added (MangoHud, VLC, Wine Gecko, Vulkan loader, DXVK, DOSBox Pure, GeneralUser GS, WFM, libcdio, pl_mpeg, mingw-w64, Mesa's bundled code, OpenOrbis package files) | Done |
| `LICENSES/` texts | Added MIT, Apache-2.0, Apache-2.0 WITH LLVM-exception, MPL-2.0, Zlib, BSD-2-Clause, BSD-3-Clause, BSL-1.0, CC0-1.0, curl and `NOTICE.txt` | Done |
| Non-licence risks (gbe_fork, libdvdcss, console system modules in the package, SeaMonkey shortcut without the program) | Documented below. The user keeps libdvdcss and the console modules | Accepted by the user |

## 1. What is in the ELF and under which licence

The W301 link (`tools/build-wine-hardware.py`, `build/wine-boot/link-report.json`) puts these in `eboot.bin`:

| Code | Declared licence | Compatible with GPL-3.0-or-later? |
| --- | --- | --- |
| Own code in `native/` | GPL-2.0-or-later | Yes ("or later") |
| Own adapters in `platform/ps4/` | LGPL-2.1-or-later | Yes |
| Wine Unix side, wineserver (in process) and prospero-win parts | LGPL-2.1-or-later | Yes |
| Steam client: Playden code (`native/steam/`, `build/steam-hosted/steam_client_hosted.o`) | GPL-3.0-or-later (SPDX headers in Playden's files) | Yes; this is what sets GPL-3 |
| gbe_fork's `generate_interfaces.cpp`, adapted in `native/steam/steam_emu.cpp` | LGPL-3.0 | Yes (LGPL-3.0 allows GPL-3) |
| curl 8.22.0 | curl (MIT-style) | Yes |
| Mbed TLS 3.6.6 | Apache-2.0 (chosen of Apache-2.0 / GPL-2.0-or-later) | Yes with GPL-3 (Apache-2.0 is not compatible with GPL-2) |
| zstd 1.5.6, LZMA SDK, stb_image, qrcodegen | BSD-3-Clause, public domain, MIT/public domain, MIT | Yes |
| Mesa 26.0.8 (RADV, ACO, NIR, util, vulkan util) | MIT; 723 SPDX `MIT` and 2 `BSL-1.0` tags in the linked directories, no GPL tag | Yes |
| Mesa's `include/drm-uapi/sync_file.h` (via `src/util/libsync.h`) | GPL-1.0-or-later WITH Linux-syscall-note | Yes; header-only kernel interface, the syscall note excludes users of the interface |
| Crema's winsys `ac_ps4_drm.c` | `Copyright 2026 DolphinPS4. SPDX-License-Identifier: MIT` | Yes |
| Crema's `port/mesa-overlay/` headers and `patches/mesa-ps4*.patch` | No per-file notice; Crema's repository is MPL-2.0 and the patches come from DolphinPS4 (GPL-2.0-or-later). The patches modify MIT Mesa files | Yes under either reading: MPL-2.0 without the "Incompatible With Secondary Licenses" notice (none found in Crema) allows a larger GPL work (MPL §3.3); GPL-2.0-or-later allows GPL-3 |
| DolphinPS4 Vulkan probe (`native/vk_probe/main.c`, `vk_probe.o`) and its toolchain recipe (libc++ build edits, libc overlay headers) | GPL-2.0-or-later (DolphinPS4 README and LICENSE) | Yes |
| LLVM libc++/libc++abi 21.1.6 | Apache-2.0 WITH LLVM-exception | Yes with GPL-3 |
| zlib (`~/vk-h0/sysroot/lib/libz.a`, zlib-ng) | Zlib | Yes |
| OpenOrbis SDK CRT, libc (musl-based) and stubs | Repository GPL-3.0; libc from musl (MIT) | Yes; the SDK's own GPL-3.0 also means the ELF could not be GPL-2.0-only |

**Resonance.** `THIRD_PARTY.md` listed it as "GPL-2.0; review components individually". Resonance's README says GPL-2.0 (Flycast's licence, without "or later"). A line-by-line comparison of every source file in `upstream/Resonance` (`port/`, `patches/`, `toolchain/`, `scripts/`, `tools/`, excluding `port/third_party`) against `native/`, `platform/`, `tools/`, `fixtures/` and `patches/` found no line unique to Resonance: only lines it shares with DolphinPS4 or Crema (the same `ac_ps4_drm.c`, toolchain recipe and dlmalloc) and GPL boilerplate. No builder reads `upstream/Resonance`. It is a reference only, nothing of it ships, and no relicensing or rewrite is needed.

**Conclusion.** No GPL-2.0-only code was found in the ELF, so the combination can be distributed under GPL-3.0-or-later as `THIRD_PARTY.md` states. Had Resonance (or Flycast) code been linked, the options would have been: rewrite that code, keep it out of the ELF, or ask the author for an "or later" grant. The check should be repeated whenever code from another PS4 port is adopted: compare it against Resonance's tree as done here.

## 2. Runtime components

The full table is in [THIRD_PARTY](../THIRD_PARTY.md#runtime-components-w301). The scan listed every PE file without Wine's builtin marker (111 files outside VLC) and every non-Wine data file. Other than Wine itself, the runtime contains: MangoHud and its subprojects, the Khronos Vulkan loader and vkcube, DXVK 2.7.1, VLC 3.0.24 with about 100 plugins, Wine Gecko 2.47.4, DOSBox Pure, WFM, libcdio, pl_mpeg (in `pwmpeg1.ax`), the ReactOS games, gbe_fork's DLLs, GeneralUser GS 2.0.3, the Mozilla CA bundle, Mesa WGL/Zink with the mingw-w64 runtime, Wine's fonts, own test programs, icons, themes and wallpapers. Three files are placeholders Wine itself generates (`dosx.exe`, `ddhelp.exe`, `dsound.vxd`: "Wine placeholder DLL") and the `winmetadata/*.winmd` files come from the Wine build.

What each licence asks of this binary distribution:

| Licence | Components | Ask |
| --- | --- | --- |
| GPL-3.0-or-later | The ELF as a whole | Licence text; Corresponding Source of the whole ELF (every linked library and the build scripts) offered in one of the GPL-3 §6 ways; Appropriate Legal Notices in interactive interfaces where the program already shows them (§5d) |
| GPL-2.0(-or-later) | VLC, DOSBox Pure, ReactOS Spider | Licence text; complete source accompanying the binary or a written offer valid three years (§3). Offering the source from the same place as the binary counts |
| LGPL-2.1/3.0 | Wine (PE and Unix), libVLC, cards.dll, Gecko's FFmpeg parts, gbe_fork | Licence text; source of the library as distributed, including changes |
| MPL-2.0 | Wine Gecko, CA bundle, Crema's repository files | Licence text and how to obtain the source form of MPL files |
| MIT, BSD, Zlib, BSL, Apache-2.0 | Mesa, MangoHud, ImGui, DXVK, Vulkan loader, curl, Mbed TLS, zstd, etc. | Keep the licence text and copyright notices with the binary (Apache: also its NOTICE if any; none of the shipped Apache projects has one) |

## 3. Licence texts and how they travel

`LICENSES/` now holds GPL-2.0, GPL-3.0, LGPL-2.1, LGPL-3.0, MIT, Apache-2.0, Apache-2.0 WITH LLVM-exception, MPL-2.0, Zlib, BSD-2-Clause, BSD-3-Clause, BSL-1.0, CC0-1.0 and curl. Their sources: the GNU texts were already present; MIT and BSL-1.0 are Mesa's `licenses/` texts (header lines removed), Apache-2.0 is Vulkan-Headers' `LICENSES/Apache-2.0.txt`, the LLVM text is libc++'s `LICENSE.TXT`, MPL-2.0 is Crema's `LICENSE`, curl is curl 8.22.0's `COPYING`, CC0-1.0 is Ubuntu's `common-licenses` copy, and BSD-2-Clause, BSD-3-Clause and Zlib are the SPDX templates. `LICENSES/NOTICE.txt` lists each component's copyright notice, which the generic MIT/BSD/Zlib texts leave as placeholders.

Proposed layout in what is distributed:

- **Runtime:** `C:\orbis\licenses\` (`/data/wine-prefix/drive_c/orbis/licenses`): every `LICENSES/*.txt`, `NOTICE.txt`, `THIRD_PARTY.md` and a generated `SOURCE.txt` that names the repository, the release tag, the exact commit (and whether the tree had local changes) and where the third-party sources are. Components that already carry their own text keep it (VLC's `COPYING.txt`, `DOSBox-Pure-LICENSE.txt`, the ReactOS texts, gbe's texts, GeneralUser GS, Wine's font licences).
- **Package:** the single package that embeds the runtime should also carry the same folder outside the archive it extracts, under `/app0/assets/licenses/` (`pkg_build` accepts only `sce_sys`, `sce_module` and `assets/*`), so a user who never starts the title can still read them. This belongs to the embedded-runtime task.
- **Legal notice in the interface (recommended):** one line in the NORMAL/ROOT boot selector or the control overlay: "OrbisDesk is free software under the GNU GPL v3 or later, without warranty. Licences: C:\orbis\licenses". GPL-3 §5(d) asks for this only when the adapted program already shows such notices; adding it is cheap.

The builder change (`release-licenses.patch.py`, applied to `tools/build-wine-hardware.py` after W301 with the integrator's go) stages the folder above, hashes its files into `manifest['licenses']`, and replaces the build PC's name in the shipped registry (section 4). The builder compiles with it; it has not run in a build yet. `SOURCE.txt` names the build and the tag (`W301`, `04.00`) as literals, like the rest of the builder, so they move with the build number.

## 4. Build PC identity in the runtime

| Trace | Where | Origin | Proposal |
| --- | --- | --- | --- |
| `C:\users\jose\` profile, with `AppData\Roaming\MangoHud\MangoHud.conf` | Prefix tree; `user.reg` shell folders (`AppData`, `Desktop`, `Personal`, `TEMP`...), `system.reg` `ProfileImagePath` and `Common Favorites` | The prefix is made on the host by `prepare-host-prefix.py` as the host user. `build-wine-hardware.py` writes `MangoHud.conf` there on purpose and `make-start-menu.py` points "MangoHud Config" there | See below |
| `ComputerName`=`JCASELLA`, Tcpip `Hostname`=`jcasella` | `system.reg`, `system.reg.build` | Host prefix | Replace with `ORBISDESK`/`orbisdesk` (applied in the builder) |
| `USERDOMAIN`, `LOGONSERVER` = `JCASELLA` | `user.reg` (Volatile Environment) | Host prefix | Same (applied in the builder) |
| `/mnt/c/Users/JoseCasella/DEV/Codex/PS4/.deps/...` strings | 114 runtime binaries (Wine PE modules, explorer, WFM, Steam objects) and the ELF | `__FILE__` in Wine's critical-section names and asserts | Add `-ffile-prefix-map=/mnt/c/Users/JoseCasella/DEV/Codex/PS4=.` (and `~/vk-h0=vk-h0`) to the PE and ELF compile flags. Touches many shared builders; not prepared |

No `/home/jose`, e-mail address or other personal data was found in the runtime.

**Does the console use `orbis`?** Only partly. `native/wine_boot.c` starts Wine as user `orbis` and the builder creates `C:\users\orbis` (W048), but the shell folders in the shipped registry still name `C:\users\jose`. Physical evidence of W091/W092 ([graphics history](HARDWARE_G001.md)) recorded `APPDATA` = `C:\users\jose\AppData\Roaming` on the console, which is why W092 moved `MangoHud.conf` there. Today `%APPDATA%`, `%TEMP%`, Documents and Desktop shell folders resolve to `C:\users\jose`, while some paths use `C:\users\orbis` (the Desktop links that `build-wine-hardware.py` copies, the SeaMonkey profile).

Changing only `MangoHud.conf` to `orbis` would break MangoHud's configuration. A real move needs, together: rewriting `C:\\users\\jose` to `C:\\users\\orbis` in the staged `user.reg` and `system.reg` (in `build-wine-hardware.py`, after the copy of the host profile tree), writing `MangoHud.conf` under `orbis`, changing `tools/make-start-menu.py`, and moving on the console whatever users already saved under `C:\users\jose` (game saves in `AppData`, Documents) into `C:\users\orbis` once, before Wine starts. `upload-hardware.py` replaces `user.reg` on each upload, so the registry part is safe, but the user files are not. The embedded-runtime first-start extraction is the natural place for that one-time move. Recommendation: do it in that task, not as a separate patch.

**Status (2026-11-09, branch `feature/embedded-runtime`).** Done in the builder, not yet built or tested on the console:
- `build-wine-hardware.py` rewrites the host profile's registry paths to `C:\users\orbis` in `system.reg`, `user.reg` and `userdef.reg`, no longer ships the host profile folder, and writes `MangoHud.conf` under `orbis`; `make-start-menu.py` points there.
- It refuses to package while the checkout or home path appears in the ELF or any runtime file. `--allow-build-paths` is the recorded opt-out for development builds.
- The first-start installer ([RELEASES](RELEASES.md#first-start-install)) moves what the user saved in the old profile's Desktop, Documents, Downloads, Favorites, Music, Pictures and Videos to `C:\users\orbis` without replacing anything.
- The `-ffile-prefix-map` flags are added to the builders separately. A re-audit on 2026-11-09 also found `/home/jose/vk-h0` strings from the graphics recipes; the same flags cover them.

## 5. Corresponding source per release

Mechanism: a Git tag per version on the public repository, and on the same release page as `OrbisDesk.pkg`, an archive of the third-party sources with a SHA-256 list. Offering the source from the same place as the binary satisfies GPL-2 §3 and GPL-3 §6(d) without a written offer; `SOURCE.txt` also offers the sources on request for three years, which covers anyone who got the package elsewhere.

Implemented in `tools/ci/release.py publish`. The tag is `orbisdesk-<version>-<commit[:12]>`, the same name the package's `C:\orbis\licenses\SOURCE.txt` gives (`tools/build-wine-hardware.py`). Before tagging, the publish job fetches every source pinned in [third-party-sources.lock.json](../third-party-sources.lock.json) and checks it against its SHA-256 or commit:

- VLC, Wine Gecko, SeaMonkey and OpenOrbis toolchain source archives;
- the source downloads of `product-assets.lock.json` (LLVM, the Steam client's libraries, gbe_fork, pl_mpeg);
- the Mesa and libdrm archives;
- a `git archive` of each pinned repository in `dependencies.lock.json` except the emulator.

They go into `<tag>-third-party-sources.tar`, split into `.partNNN` files above 1900 MiB, with `SOURCES.txt` inside it listing each file's SHA-256 and origin. The lock is kept apart from `product-assets.lock.json` so that adding a source does not change the prebuilt block keys.

Still not packed: the generated Wine overlays (their generators are in the tag) and VLC's contrib sources.

What the archive (or the tag) must contain:

| Source | Why | Today |
| --- | --- | --- |
| This repository at the tag: `native/`, `platform/`, `tools/` (including `tools/vk-h0/` recipes), `patches/`, `fixtures/`, locks | GPL-3 Corresponding Source of the ELF, including build scripts; LGPL changes to Wine | In Git, untagged |
| Wine source at `490f6d5dcbb2a5047345b8af88d114bbcaad69a8`, plus the generated overlays the build compiled (`.deps/wine/ps4-overlay`, `ps4-win32u-overlay`, `explorer-hw-overlay` and the other module overlays) | LGPL: the modified library's source. The generators are in Git, but shipping the generated trees removes any doubt about "preferred form" | Not packed |
| prospero-win at `0e7b6b4a53a9aebfeceaf28fabb919e2452bbadc` | LGPL, compiled into the ELF | Pinned |
| Mesa 26.0.8 tarball, Crema's `patches/` and `port/` at `475b8d5b`, libdrm headers, zlib-ng, LLVM 21.1.6 runtimes, DolphinPS4 toolchain at `879b3e57` | Part of the GPL-3 ELF | Tarball pinned; others pinned by commit |
| OpenOrbis PS4 Toolchain v0.5.4 source (CRT, libc, stubs) | Linked into the ELF | Release archive pinned in `artifacts.lock.json` |
| Playden at `fb74dbfd`, curl 8.22.0, Mbed TLS 3.6.6, zstd 1.5.6, LZMA SDK 24.09, stb, qrcodegen 1.8.0 | Steam client in the ELF | Downloaded and pinned by SHA-256 |
| VLC 3.0.24 source (`vlc-3.0.24.tar.xz`) and the contrib sources VideoLAN used for the win64 build | GPL-2/LGPL; distributed unmodified, but the distributor still owes the source | Not downloaded |
| Wine Gecko 2.47.4 source (`wine-gecko-2.47.4-src.tar.xz`) | MPL-2.0 and LGPL parts | Not downloaded |
| DOSBox Pure at `ba6dcaee` | GPL-2.0-or-later | Already shipped as `DOS-runtime-source.tar.gz` |
| ReactOS games at `5f6ef754` | GPL-2.0, LGPL-2.1 | Already shipped as `games-source.tar.gz` |
| gbe_fork `release-2026_09_27` source tarball | LGPL-3.0 | Pinned; only a pointer (`gbe-SOURCE.txt`) ships |
| libcdio matching `libcdio.dll` (W058-W301 only) | GPL-3.0-or-later | **Unknown**: the DLL was prebuilt by WFM's author. Removed from later builds; the removal is the answer for new releases |

Gaps that prevent rebuilding from a clean clone today (see [repository layout](REPOSITORY_LAYOUT.md)):

- Graphics recipes in `tools/vk-h0/` hardcode `/mnt/c/Users/JoseCasella/DEV/Codex/PS4` and work in `~/vk-h0`, outside the repository.
- Host Wine configuration and prefix generation are not orchestrated; the package consumes `reports/increment15/prefix-package` and `reports/increment15/host-build/report.json`, which are ignored by Git.
- The final builder reads many `out/*/manifest.json` files and `build/wine-boot/link-report.json` produced by other builders; there is no single ordered build.
- `libcdio.dll` was a prebuilt binary (now removed); the OpenOrbis package modules come from SDK samples.
- No complete clean package build has been demonstrated.

For alpha-1 this means the published source is complete but its rebuild needs the documented manual steps; the GPL asks for the source and build scripts, not for a one-command build, but the gaps should be listed in the release notes.

## 6. Risks that are not licence issues

- **gbe_fork in `C:\orbis\steam`.** A Steam API emulator, shipped unmodified as an optional per-game replacement of `steam_api(64).dll`. Its licence (LGPL-3.0) is met, but it lets games run without Steam's own client checks. Valve's subscriber agreement, possible takedown requests against the repository, and how the project is perceived are risks. OrbisDesk does not add any DRM circumvention, and this review does not help with any.
- **libdvdcss inside VLC's DVD plugins.** VideoLAN's win64 build includes it to read CSS-encrypted DVDs. Its licence is GPL-2.0-or-later, but distributing it is restricted by anti-circumvention law in some countries. Options: keep it (as VideoLAN distributes it), or ship VLC without it, which limits DVD playback to unencrypted discs. **Decision: the user keeps it**; the risk stays documented here.
- **Console system modules in the package.** `sce_module/libc.prx`, `sce_module/libSceFios2.prx` and `sce_sys/about/right.sprx` are copied from the OpenOrbis SDK samples, as most homebrew does. They are console system files with no stated licence. `THIRD_PARTY.md` now names them. **Decision: the user keeps them**; the risk stays documented here.
- **SeaMonkey shortcut without the program.** Resolved in W303: the package ships SeaMonkey 2.53.24 (MPL-2.0, pinned in `product-assets.lock.json`) in `C:\Program Files\SeaMonkey`, so the shortcut works on a fresh install.
- **Trademarks.** Windows, PlayStation, Steam and Valve are trademarks of their owners; the release text should state that OrbisDesk is not affiliated with them (the Steam client already says so).

## 7. What was checked and what was not

Checked: licence headers and READMEs of Crema, DolphinPS4, Resonance, Playden and OpenOrbis; the W301 link inputs; SPDX tags in the Mesa directories linked into the ELF; a line comparison of Resonance against this repository; a file scan of the W301 runtime; registry and binary strings for host traces; the console's `APPDATA` from W091/W092 physical evidence. Not done: a build, a link, an upload, or any change to shared builders. The licence folder and registry change are untested on hardware. VLC's exact list of bundled libraries for 3.0.24 was not audited beyond its own `COPYING.txt`/`README.txt`.
