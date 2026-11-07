<a id="licencias-y-procedencia"></a>


# Licences and provenance

[English](THIRD_PARTY.md) | [Español](THIRD_PARTY-es.md)

The downloaded sources remain at `upstream/`; Your exact reviews are in `sources.lock.json`. The official binary downloads are set by SHA256 at `artifacts.lock.json`. No games, BIOS, keys or firmware modules are included.

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
| Crema |Cemu port and driver PS4 port reference|MPL- 2.0; review components individually|
| Resonance |Memory reference, repurchase and re-use of infrastructure|GPL- 2.0; review components individually|
| shadPS4 |Official emulator, reference ABI and local fork with reproducing patches in `patches/shadPS4/`| GPL-2.0-or-later |
| OpenOrbis |SDK, CRT, libc and stubs used to generate homebrew|Your licenses included in `.deps/sdk/OpenOrbis/PS4Toolchain`|
|ReactOS Solitaire and cardlib (J Brown, 2001), review 5f6ef754|`sol.exe` (W114, Start → Programs → Games), unchanged with `tools/build-games.py`|Public domain (`ReadMe.txt` of solitaire and cardlib)|
|ReactOS Spider Solitaire (Gregor Schneider), review 5f6ef754| `spider.exe` (W114) |GPL- 2.0 (files refer to `COPYING` of ReactOS); source and commands in `out/games/games-source.tar.gz`|
|ReactOS cards.dll (Filip Navara), review 5f6ef754|`cards.dll` (W114), cards that load in execution|LGPL- 2.1 -or-later; free-use card images according to `dll/win32/cards/COPYING`|
| SpaceCadetPinball (Andrey Muzychenko), SDL2 2.32.8 y SDL2_mixer 2.8.1 |Optional (`build-games.py --pinball`), not yet compiled; no game data|MIT; SDL2 and SDL2_mixer Zlib. Data (PINBALL.DAT, WAV, MID) are Microsoft and are not included|

Diagnostics of `native/` are distributed under GPL- 2.0 -or-later. The ELF diagnostic links that code and LGPL components, and is delivered under GPL- 2.0 -or-later. New adapters of `platform/ps4/`, fixtures and own tools are licensed under LGPL- 2.1 -or-later. See the texts in `LICENSES/`.

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

W114 adds games to the Start menu (`docs/GAMES.md`). The sources come out of a partial check of ReactOS set at `games.lock.json` and are compiled without modification; only the own resources of ReactOS (`reactos/version.rc`, `reactos/manifest_exe.rc` are replaced by empty files. As Spider is GPL- 2.0 and cards.dll LGPL- 2.1 -or-later, `out/games/games-source.tar.gz` carries the sources of the checkout, the stubs, the builder and the exact commands, and travels next to the binaries in `C:\windows\system32` with `ReactOS-COPYING.txt`, `ReactOS-COPYING.LIB.txt` and `cards-images-COPYING.txt`. Space Cadet Pinball has no free data: the code (MIT) can be compiled, but the data files must be provided by the user from a licensed Windows installation.

The phase 9 (browser and webviews) includes Wine Gecko 2.47.4 (MPL - 2.0), tarbals x86_64 and x86 of https://dl.winehq.org/wine/wine-gecko/2.47.4/ unchanged, fixed by SHA- 256 in `tools/stage-wine-gecko.py`. The corresponding sources are in the same directory (`wine-gecko-2.47.4-src.tar.xz`). Pale Moon is not included: your redistribution license requests prior permission from Moonchild Productions to include it in another package. Direct access to the Start menu uses the user's own copy, without changing your files or your default preferences; The preferences of `fixtures/browser` go only in a profile of its own that is passed with `-profile`.
