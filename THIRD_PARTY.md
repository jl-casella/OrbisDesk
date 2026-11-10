<a id="licencias-y-procedencia"></a>


# Licences and provenance

[English](THIRD_PARTY.md) | [Español](THIRD_PARTY-es.md)

The downloaded sources remain at `upstream/`; Your exact reviews are in `sources.lock.json`. The official binary downloads are set by SHA256 at `artifacts.lock.json`. No games, BIOS or keys are included. The only console system files in the package are the three OpenOrbis package modules listed under [runtime components](#runtime-components-w301).

|Component| Uso actual |Reference licence|
|---|---|---|
|prospero-win, mpereiraesaa and collaborators| Issuer compiled x86, engine, cache, reencoder, hostexec, FP status, x87, VM calls and contract from the fixed checkout | LGPL-2.1-or-later |
| Wine |DLL PE32/PE64, NLS, ntdll Complete Unix and wineserver in process; complete start still locked| LGPL-2.1-or-later |
|DolphinPS4, iHaiDeeZ and collaborators|Toolchain reference and diagnosis ABI. The probe G001 (`native/vk_probe/main.c`) is its `probe-vk` adapted, and links its runtime (`port/ps4_*`), `port/mesa/ac_ps4_drm.c` (MIT) and `patches/mesa-ps4.patch`| GPL-2.0-or-later; `ac_ps4_drm.c` MIT |
|Mesa 26.0.8 (RADV, ACO, NIR; WGL and Zink)|Driver Vulkan of the probe G001 and ELF of Wine from W070, compiled without LLVM with `tools/vk-h0/`; from W076 also `opengl32.dll` and `libgallium_wgl.dll` (WGL + Zink) for Windows; official tarball, SHA256 in `docs/HARDWARE_G001.md`|MIT|
| LLVM libc++/libc++abi 21.1.6 |Probe C + + library G001| Apache-2.0 WITH LLVM-exception |
|zlib-ng (copy of shadPS4)|Compression used by Mesa in the probe G001| Zlib |
|lvm-mingw 20260922 (UCRT)| Compilator `opengl32.dll`/`libgallium_wgl.dll` (Mesa WGL+Zink) and glxgears in W076; SHA256 bb7b765... 65c21, the same one that fixes prospero-win |Apache - 2.0 WITH LLVM -exception and licences of mingw-w64|
|windows-glxgears (Brian Paul; port of CalvinHartwell, 8c27987)|`fixtures/win32/glxgears/main.cpp`, with FPS added record|MIT (notice in file)|
| Crema (iHaiDeeZ/ShiroKlein), commit `475b8d5b` | Its Mesa port is built into the OrbisDesk ELF: `port/mesa/ac_ps4_drm.c` (header: `Copyright 2026 DolphinPS4. SPDX-License-Identifier: MIT`, modified by `tools/vk-h0/patch-crema-*.py` and `patch-mesa-placed.py`), `port/mesa-overlay/` headers and `patches/mesa-ps4.patch` plus `mesa-ps4-aligned-vertex-fetch.patch` (which originate in DolphinPS4) applied to Mesa 26.0.8. No Cemu code is used | Winsys: MIT. Repository: MPL-2.0 without an "Incompatible With Secondary Licenses" notice; the Mesa patches are also in DolphinPS4 (GPL-2.0-or-later). See [release licenses](docs/RELEASE_LICENSES.md) |
| Resonance (iHaiDeeZ/ShiroKlein), commit `6b873890` | Reference only. A line-by-line comparison of its `port/`, `patches/` and `toolchain/` with this repository found no code unique to Resonance (only lines it shares with DolphinPS4/Crema and GPL boilerplate). Nothing from it is in the package | GPL-2.0 (Flycast); not distributed |
| shadPS4 |Official emulator, reference ABI and local fork with reproducing patches in `patches/shadPS4/`| GPL-2.0-or-later |
| OpenOrbis |SDK, CRT, libc and stubs used to generate homebrew|Your licenses included in `.deps/sdk/OpenOrbis/PS4Toolchain`|
|ReactOS Solitaire and cardlib (J Brown, 2001), review 5f6ef754|`sol.exe` (W114, Start → Programs → Games), unchanged with `tools/build-games.py`|Public domain (`ReadMe.txt` of solitaire and cardlib)|
|ReactOS Spider Solitaire (Gregor Schneider), review 5f6ef754| `spider.exe` (W114) |GPL- 2.0 (files refer to `COPYING` of ReactOS); source and commands in `out/games/games-source.tar.gz`|
|ReactOS cards.dll (Filip Navara), review 5f6ef754|`cards.dll` (W114), cards that load in execution|LGPL- 2.1 -or-later; free-use card images according to `dll/win32/cards/COPYING`|

Diagnostics of `native/` are distributed under GPL-2.0-or-later. New adapters of `platform/ps4/`, fixtures and own tools are licensed under LGPL-2.1-or-later. The OrbisDesk package (`OrbisDesk.pkg`, its ELF) links these together with the Steam client below. The combined work is distributed under **GPL-3.0-or-later**, which all of the licenses above allow. See the texts in `LICENSES/` (GPL-2.0, GPL-3.0, LGPL-2.1, LGPL-3.0).

## Steam client

The Steam client was first built as a separate title (ORBS00001) and is being integrated into OrbisDesk. It reuses code from Playden, so it is distributed under the **GNU General Public License v3.0 or later**.

| Component | Version / origin | License | Use |
|---|---|---|---|
| Playden for PS5 (Leo Lobato) | commit `fb74dbfd6bb96fc19a96afc1f48a4e40a885216b`, <https://github.com/leolobato/playden-ps5> | GPL-3.0-or-later | Steam protocol client (`src/steam/`, `src/diagnostics/`), adapted to PS4. Modified files say so in their header; patches in `native/steam/patches/`. |
| curl | 8.22.0, <https://curl.se/> (SHA-256 `f7ef3ae8a22e521f289803fe93543eb64c329b58aa73a9e224dfd915a2a5f4f7`) | curl (MIT-style) | HTTPS and WebSocket |
| Mbed TLS | 3.6.6, <https://github.com/Mbed-TLS/mbedtls> (SHA-256 `8fb65fae8dcae5840f793c0a334860a411f884cc537ea290ce1c52bb64ca007a`) | Apache-2.0 (chosen from Apache-2.0 / GPL-2.0-or-later) | TLS, AES, SHA-1, RSA |
| Mozilla CA bundle | `cacert-2026-09-25.pem`, <https://curl.se/ca/> (SHA-256 `a41b5d356aea97a529fe27e0f7316d2f9d946d75927476cf9cf1b90637d00505`) | MPL-2.0 | Roots for certificate validation |
| zstd | 1.5.6, <https://github.com/facebook/zstd> (SHA-256 `8c29e06cf42aacc1eafc4077ae2ec6c6fcb96a626157e0593d5e82a34fd403c1`) | BSD-3-Clause (chosen from BSD / GPL-2.0) | Chunk decompression |
| LZMA SDK (`LzmaDec` only) | 24.09, <https://github.com/ip7z/7zip/tree/24.09/C> | Public domain | Chunk decompression |
| stb_image.h (Sean Barrett) | v2.30, <https://github.com/nothings/stb> (SHA-256 `594c2fe35d49488b4382dbfaec8f98366defca819d916ac95becf3e75f4200b3`) | Public domain / MIT | Inflate (gzip, zip) in Playden's backend |
| QR Code generator (Project Nayuki), C version | 1.8.0, <https://github.com/nayuki/QR-Code-generator> (`qrcodegen.c` SHA-256 `300eff07ee25baaa7578f20284411638154716379437391e7e689c0e6ce81403`, `qrcodegen.h` `e82df4bff37d18b5863b9e7486fe6bda1b6cda8c3b9ecebfec473907265cb589`) | MIT | Sign-in QR code |
| gbe_fork (Goldberg Steam Emulator fork) | `release-2026_09_27`, <https://github.com/Detanup01/gbe_fork> (binary `emu-win-release-vs22.7z` SHA-256 `300186c34f49a9ea75b33ce2af299267cc1dad0225cf45e81a229578d4e11c85`; source `ce3ce7aee0439f1b7aff2404106fe68184185a8d0b7ca5ab2677a046ea464cbd`) | LGPL-3.0 | Optional per-game replacement of `steam_api(64).dll`, shipped unmodified. `native/steam/steam_emu.cpp` contains a C++ adaptation of its `generate_interfaces.cpp`, distributed under GPL-3.0-or-later as LGPL-3.0 allows. |
| LLVM libc++, libc++abi, libunwind (OpenOrbis SDK) | SDK v0.5.4 | Apache-2.0 WITH LLVM-exception | C++ runtime |

The standalone ORBS00001 package carried the license texts of these components in `/app0/assets/misc/`. The OrbisDesk package (W301) does not yet carry them; [release licenses](docs/RELEASE_LICENSES.md) describes where they go. The corresponding source is this repository (`native/steam/`, `tools/build-steam-*.py`) plus the dependency sources pinned by SHA-256. The client is not official and is not endorsed by Valve. Steam is a trademark of Valve Corporation.

## Runtime components (W301)

The runtime that goes to `/data` (`wine/`, `wine-prefix/`) also contains these third-party programs and data. The list comes from a scan of `build/wine-hardware-w301/runtime` (1835 files): every PE file without Wine's builtin marker, and every non-Wine data file. Hashes are those pinned by the builder named in the last column.

| Component | Version / origin | License | Where / builder |
|---|---|---|---|
| MangoHud for Windows (flightlessmango; Windows fork by Leclowndu93150) | commit `52592550824ae11d5c68a6826f07db5f60220d23`, <https://github.com/Leclowndu93150/MangoHud-Windows>, patched by `tools/vk-h0/patch-mangohud-*.py` | MIT | `libMangoHud.dll` and `MangoHud.x86*.json` in `system32` and `syswow64`; `tools/vk-h0/build-mangohud.sh`, `build-mangohud-i386.sh` |
| MangoHud's Meson subprojects: Dear ImGui 1.91.6, ImPlot 0.16, spdlog 1.14.1 (with fmt), MinHook, Vulkan-Headers and Vulkan-Utility-Libraries 1.4.346 | MangoHud's wrap files | ImGui, ImPlot, spdlog, fmt: MIT; MinHook: BSD-2-Clause; Vulkan headers/utilities: Apache-2.0 (headers also MIT) | Statically inside `libMangoHud.dll` |
| Khronos Vulkan loader | tag `v1.4.335` (Vulkan-Loader `052ac24611eced7b0ca62cc5cca2eeeb2051fa28`), built with llvm-mingw | Apache-2.0 | `vulkan-1.dll` in `system32` and `syswow64`; `tools/vk-h0/build-vulkan-loader.sh`, `build-vulkan-loader-i386.sh` |
| vkcube (Khronos Vulkan-Tools) | tag `v1.4.335` (`48b5d246b2d0b1a41ee7ea1b69525ae7bb38a2ae`) | Apache-2.0 | `C:\orbis\vkcube.exe`; `tools/vk-h0/build-vkcube.sh` |
| DXVK (Philip Rebohle and contributors) | 2.7.1, <https://github.com/doitsujin/dxvk/releases/tag/v2.7.1>, `dxvk-2.7.1.tar.gz` SHA-256 `d85ce7c79f57ecd765aaa1b9e7007cb875e6fde9f6d331df799bce73d513ce87`, unmodified | Zlib | `d3d8`, `d3d9`, `d3d10core`, `d3d11`, `dxgi` (+ `dxvk_dxgi.dll`) in `system32` and `syswow64`; `tools/stage-dxvk.py` |
| VLC media player (VideoLAN) | 3.0.24 win64, `vlc-3.0.24-win64.7z` SHA-256 `1ed59c09152e78aff84663fa76efab26057716576db74332858810e5ef54ae1f`, unmodified, about 100 of its plugins | VLC: GPL-2.0-or-later; libVLC/libvlccore: LGPL-2.1-or-later; bundled libraries under their own licenses (FFmpeg's libavcodec/libavformat LGPL-2.1-or-later or GPL as built by VideoLAN, libdvdnav/libdvdread GPL-2.0-or-later, libdvdcss GPL-2.0-or-later, Qt LGPL, others listed in its `COPYING.txt`/`README.txt`) | `C:\Program Files\VLC`; `tools/stage-vlc.py` |
| SeaMonkey (SeaMonkey project and Mozilla contributors) | 2.53.24 win64 en-US, `seamonkey-2.53.24.en-US.win64.zip` SHA-256 `2b6eefd9a1f5c7d7e39d43d4a92221dd9bfb4e1b1de885687ae75560f3a61262` (product-assets.lock.json), unmodified | MPL-2.0 (`LICENSES/MPL-2.0.txt`); source: <https://gitlab.com/seamonkey-project/seamonkey-2.53-comm>, tag `2_53_24_final` | `C:\Program Files\SeaMonkey`; `tools/build-wine-hardware.py` (W303) |
| Wine Gecko | 2.47.4 x86_64 (SHA-256 `fd88fc7e537d058d7a8abf0c1ebc90c574892a466de86706a26d254710a82814`) and x86 (`2cfc8d5c948602e21eff8a78613e1826f2d033df9672cace87fed56e8310afb6`), <https://dl.winehq.org/wine/wine-gecko/2.47.4/>, unmodified | MPL-2.0; its `mozavcodec`/`mozavutil` (FFmpeg) and `lgpllibs` are LGPL-2.1-or-later; NSS MPL-2.0 | `system32\gecko`, `syswow64\gecko`; `tools/stage-wine-gecko.py` |
| DOSBox Pure (Bernhard Schelling; DOSBox Team) | commit `ba6dcaee84aa2c22d709c3dfdacb7aca5ebc3042`, <https://codeberg.org/schelling/dosbox-pure> (`dos.lock.json`) | GPL-2.0-or-later | `dosbox_pure_libretro.dll` with `DOSBox-Pure-LICENSE.txt` and `DOS-runtime-source.tar.gz` in `system32` |
| WFM file manager (BrunoSX) | commit `6b1860895885a6d65c37815308260293341acb5f` with OrbisDesk changes in `tools/build-wfm.py` | MIT | `wfm.exe` in `system32`; `tools/build-wfm.py` |
| libcdio (**removed after W301**) | prebuilt `libcdio.dll` from the WFM repository (reports 2.2.0, x86_64), SHA-256 `cc9b86da2a437fd6859acaaf7de71ef271d4b7ba8274ebe7cfc92d86ce51ed09` | GPL-3.0-or-later | Shipped in `system32` up to W301 with no known corresponding source. `tools/build-wfm.py` no longer links it, WFM's "Load ISO image" reports that it is unavailable, and the next upload deletes the console's copy (see [release licenses](docs/RELEASE_LICENSES.md)) |
| pl_mpeg (Dominic Szablewski) | commit `c871f2be`, `pl_mpeg.h` SHA-256 `3a8cb30c83c2a1147719c30fe0c8b93da2987aa43140077c575b39aaa75fc2c9` | MIT | Compiled into `pwmpeg1.ax` (`syswow64`); `tools/stage-dshow-i386.py` |
| GeneralUser GS (S. Christian Collins) | 2.0.3, commit `684543d5e5efaef08d02be50dcda8d552478fa60` of <https://github.com/mrbumpy409/GeneralUser-GS>, `.sf2` SHA-256 `9575028c7a1f589f5770fccc8cff2734566af40cd26ed836944e9a5152688cfe` | GeneralUser GS license (use and redistribution allowed; text shipped as `GeneralUser-GS-LICENSE.txt`) | `C:\windows\GeneralUser-GS.sf2`; `tools/build-wine-hardware.py` |
| mingw-w64 runtime and LLVM libc++/libunwind (llvm-mingw 20260922) | Statically linked into the PE files built with llvm-mingw (Mesa WGL, MangoHud, the Vulkan loader, vkcube, glxgears, own fixtures) | mingw-w64 runtime: ZPL-2.1 / public domain with some BSD/MIT files; LLVM: Apache-2.0 WITH LLVM-exception | Notices in `NOTICE` (see [release licenses](docs/RELEASE_LICENSES.md)) |
| Mesa's bundled code in the ELF | BLAKE3, xxHash, parson, others inside `src/util` | BLAKE3: CC0-1.0 or Apache-2.0; xxHash: BSD-2-Clause; parson: MIT; a few files BSL-1.0 | Linked from `~/vk-h0/build/mesa-wine` |
| OpenOrbis package files | `sce_module/libc.prx`, `sce_module/libSceFios2.prx`, `sce_sys/about/right.sprx`, copied from the OpenOrbis SDK samples by `tools/orbis_package.py` | No license stated by OpenOrbis; these are console system modules (see [release licenses](docs/RELEASE_LICENSES.md), non-license risks) | `OrbisDesk.pkg` |

Wine's own fonts (`tahoma.ttf`, `tahomabd.ttf`, `marlett.ttf`, LGPL-2.1-or-later, sources and license in `C:\windows\Fonts\licenses`), the wallpapers drawn by `tools/make-wallpaper-set.py`, the CC0 photograph described below, icons, themes and the test fixtures in `C:\orbis` are covered by the rows above or are project files.

The PE32 charger of `platform/ps4/pw_pe32.c` and the fixture `minimal.c` are own code; The format was compared with Microsoft's PE specification. The fixture is linked without CRT or libraries Windows and its exact binary accompanies the reports of the increment 4.

The fixtures DLL/EXE and definitions `.def` of the increment 6 are also unique. The import library is generated with the toolchain MinGW; no commercial DLL or copies of kernel32/ntdll of Windows are included.

The fixtures TLS and their contrast helper of increment 7 are also own. The helper uses kernel32 only when it is executed in Windows as a reference; that library of the system is not incorporated or simulated in the runtime PS4.

The increment 9 retains the copyright of the units Wine modified in its overlay and patch. The adaptations of fstab and host pages follow the patches 0100 and 0510 of prospero-win (its collaborators, LGPL- 2.1 -or-later), adjusted to PS4. Own harness includes real Wine code; The ELF diagnosis remains GPL- 2.0 -or-later. The original SDK OpenOrbis is not modified: a copy of libc omite lstat.lo to use the existing import of libkernel; Hash, license of SDK and evidence of that transformation are preserved. The structures ABI were contrasted with the code of shadPS4, without incorporating your filesystem into the runtime.

The arrangement of structures ABI was contrasted with `DolphinPS4/probe/main.cpp` and `shadPS4/src/core/libraries/kernel/threads/exception.h`. No full runtime was copied from any of these projects. The infrastructure RADV/GNM, Zink and DXVK is not incorporated into this milestone. Before they are distributed, their licences will have to be kept and the corresponding amendments published.

To distribute a binary diagnosis, accompany it with these sources and the fixed checkouts of prospero-win, in addition to the licenses of SDK and the construction instructions. This workspace does not create a release or publish artifacts on its own.

W170 uses the public domain photo "Green hill landscape under sky and clouds" of goodfreephotos.com (CC0) as a desktop background. The original, its hash and the conversion to 1280x720 are in `out/wallpaper-cc0/manifest.json`.

The 8 (network) phase adapts `wine/ps5/pw_ws2_32_libc.c` of prospero-win (LGPL- 2.1 -or-later, its collaborators) in `platform/ps4/pw_ws2_32_libc.c`: the same resolution rules (numeric, loopback, local name, names with point by `sceNetResolverStartNtoa`, negative cache of 5 s), with names PS4, without the hooks of your host test and with a short table of services.

W166 incorporates the Vulkan 32 bit prospero-win call grouping (LGPL- 2.1 -or-later): `wine/ps5/pw_vk_*`, `wine/ps5/vulkan/*` and its tools `tools/stage_vk_batch.py`, `stage_vk_replay_lifecycle.py` and `generate_vk_codecs.py`, applied unchanged to a copy of `dlls/winevulkan` (`tools/build-winevulkan-batch.py` save your hashes). The codecs are generated with the Khronos Vulkan record 1.4.357 (`vk.xml`, `video.xml`; Apache - 2.0 or MIT), the same as it fixes Wine.

The increment 10 adapts the patches Wine 0101, 0102, 0110 and 0111 of prospero-win (LGPL- 2.1 -or-later). Its originals, hashes and adaptations are identified in the overlay boot-manifest and the evidence capsule. The patches keep the Wine notices. The own signal, route and poll code retains the LGPL license indicated in each file; the bootstrap and its playback homerew are GPL- 2.0 -or-later.

The emulator Linux is used as an external tool. Your private run glibc comes from the Ubuntu package indicated in linux-runtime.lock.json (LGPL- 2.1 -or-later for libc, with the corresponding package notices). The distribution of these units requires accompanying their applicable licences and sources.

The increment 11 adds own patches to the filesystem and to the messages exports of shadPS4, under GPL- 2.0 -or-later as its original files. The Wine message adapters keep LGPL- 2.1 -or-later; the homerew tests retain GPL- 2.0 -or-later. No code of the filesystems of other emulators is incorporated in the console run. The build Linux uses LLVM/libc++ and libgcc_s as external dependencies with their corresponding licenses and exceptions.

The increment 12 adds shared references and controls SCM_RIGHTS specific to the GPL- 2.0 -or-later fork of shadPS4. The OpenOrbis tests are homebrew's own; no tests are incorporated into the emulator repository. The provision of ABI contrasts with the public definitions of FreeBSD 9 and SDK; your socket implementation is not copied. The Wine message adapter keeps LGPL- 2.1 -or-later.

The increment 13 adds an own backend using Linux Pipes APIs, and its integration with shadPS4 descriptors conserves GPL- 2.0 -or-later. Pipes homebrew is also own under GPL- 2.0 -or-later. No kernel code Linux is incorporated and the original SDK OpenOrbis is not modified to provide these pipes.

The increment 14 adds own directories adapters under LGPL- 2.1 -or-later and homebrew itself under GPL- 2.0 -or-later. The process guards apply to overlay LGPL of Wine and keep their original warnings. No other libc implementation is incorporated or SDK modified; their statements and the existing Orbis operations are used. The emulator fork retains the increment review 13.

W114 adds games to the Start menu (`docs/GAMES.md`). The sources come out of a partial check of ReactOS set at `games.lock.json` and are compiled without modification; only the own resources of ReactOS (`reactos/version.rc`, `reactos/manifest_exe.rc` are replaced by empty files. As Spider is GPL- 2.0 and cards.dll LGPL- 2.1 -or-later, `out/games/games-source.tar.gz` carries the sources of the checkout, the stubs, the builder and the exact commands, and travels next to the binaries in `C:\windows\system32` with `ReactOS-COPYING.txt`, `ReactOS-COPYING.LIB.txt` and `cards-images-COPYING.txt`.

The phase 9 (browser and webviews) includes Wine Gecko 2.47.4 (MPL - 2.0), tarbals x86_64 and x86 of https://dl.winehq.org/wine/wine-gecko/2.47.4/ unchanged, fixed by SHA- 256 in `tools/stage-wine-gecko.py`. The corresponding sources are in the same directory (`wine-gecko-2.47.4-src.tar.xz`). Pale Moon is not included: your redistribution license requests prior permission from Moonchild Productions to include it in another package. Direct access to the Start menu uses the user's own copy, without changing your files or your default preferences; The preferences of `fixtures/browser` go only in a profile of its own that is passed with `-profile`.
