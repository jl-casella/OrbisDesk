# Licencias y procedencia

[English](THIRD_PARTY.md) | [Español](THIRD_PARTY-es.md)

Las fuentes descargadas permanecen en `upstream/`; sus revisiones exactas están en `sources.lock.json`. Las descargas binarias oficiales están fijadas por SHA256 en `artifacts.lock.json`. No se incluyen juegos, BIOS ni claves. Los únicos archivos de sistema de la consola en el paquete son los tres módulos de paquete de OpenOrbis listados en [componentes del runtime](#componentes-del-runtime-w301).

| Componente |Uso real| Licencia de referencia |
|---|---|---|
| prospero-win, mpereiraesaa y colaboradores | Se compilan emisor x86, motor, caché, reencoder, hostexec, estado FP, x87, llamadas y contrato VM desde el checkout fijado |LGPL-2.1-o-later|
| Wine | DLL PE32/PE64, NLS, ntdll Unix completo y wineserver en proceso; arranque completo todavía bloqueado |LGPL-2.1-o-later|
| DolphinPS4, iHaiDeeZ y colaboradores | Referencia de toolchain y diagnóstico ABI. El probe G001 (`native/vk_probe/main.c`) es su `probe-vk` adaptado, y enlaza su runtime (`port/ps4_*`), `port/mesa/ac_ps4_drm.c` (MIT) y `patches/mesa-ps4.patch` | GPL-2.0-o más tarde; `ac_ps4_drm.c` MIT |
| Mesa 26.0.8 (RADV, ACO, NIR; WGL y Zink) | Driver Vulkan del probe G001 y del ELF de Wine desde W070, compilado sin LLVM con `tools/vk-h0/`; desde W076 también `opengl32.dll` y `libgallium_wgl.dll` (WGL+Zink) para Windows; tarball oficial, SHA256 en `docs/HARDWARE_G001.md` | MIT |
|LLVM libc+/libc++abi 21.1.6| Biblioteca C++ del probe G001 |Apache-2.0 Con LLVM-excepción|
| zlib-ng (copia de shadPS4) | Compresión usada por Mesa en el probe G001 |Zlib|
| llvm-mingw 20260922 (UCRT) | Compilador de `opengl32.dll`/`libgallium_wgl.dll` (Mesa WGL+Zink) y de glxgears en W076; SHA256 bb7bb765...65c21, el mismo que fija prospero-win | Apache-2.0 WITH LLVM-exception y licencias de mingw-w64 |
| windows-glxgears (Brian Paul; port de CalvinHartwell, 8c27987) | `fixtures/win32/glxgears/main.cpp`, con registro de FPS agregado | MIT (aviso en el archivo) |
| Crema (iHaiDeeZ/ShiroKlein), commit `475b8d5b` | Su port de Mesa se compila dentro del ELF de OrbisDesk: `port/mesa/ac_ps4_drm.c` (cabecera: `Copyright 2026 DolphinPS4. SPDX-License-Identifier: MIT`, modificado por `tools/vk-h0/patch-crema-*.py` y `patch-mesa-placed.py`), las cabeceras de `port/mesa-overlay/` y `patches/mesa-ps4.patch` más `mesa-ps4-aligned-vertex-fetch.patch` (que vienen de DolphinPS4), aplicados a Mesa 26.0.8. No se usa código de Cemu | Winsys: MIT. Repositorio: MPL-2.0 sin aviso "Incompatible With Secondary Licenses"; los parches de Mesa también están en DolphinPS4 (GPL-2.0-or-later). Ver [licencias del release](docs/RELEASE_LICENSES-es.md) |
| Resonance (iHaiDeeZ/ShiroKlein), commit `6b873890` | Sólo referencia. Una comparación línea por línea de su `port/`, `patches/` y `toolchain/` con este repositorio no encontró código exclusivo de Resonance (sólo líneas que comparte con DolphinPS4/Crema y texto estándar de la GPL). Nada suyo va en el paquete | GPL-2.0 (Flycast); no se distribuye |
| shadPS4 | Emulador oficial, referencia ABI y fork local con parches reproducibles en `patches/shadPS4/` |GPL-2.0-o-later|
| OpenOrbis | SDK, CRT, libc y stubs usados para generar homebrew | Sus licencias incluidas en `.deps/sdk/OpenOrbis/PS4Toolchain` |
| ReactOS Solitaire y cardlib (J Brown, 2001), revisión 5f6ef754 | `sol.exe` (W114, Start → Programs → Games), compilado sin cambios con `tools/build-games.py` | Dominio público (`ReadMe.txt` de solitaire y de cardlib) |
| ReactOS Spider Solitaire (Gregor Schneider), revisión 5f6ef754 | `spider.exe` (W114) | GPL-2.0 (los archivos remiten a `COPYING` de ReactOS); fuente y comandos en `out/games/games-source.tar.gz` |
| ReactOS cards.dll (Filip Navara), revisión 5f6ef754 | `cards.dll` (W114), cartas que cardlib carga en ejecución | LGPL-2.1-or-later; imágenes de las cartas de uso libre según `dll/win32/cards/COPYING` |
| SpaceCadetPinball (Andrey Muzychenko), SDL2 2.32.8 - Sí. SDL2_mixer 2.8.1 | Opcional (`build-games.py --pinball`), todavía no compilado; sin datos del juego | MIT; SDL2 y SDL2_mixer Zlib. Los datos (PINBALL.DAT, WAV, MID) son de Microsoft y no se incluyen |

Los diagnósticos de `native/` se distribuyen bajo GPL-2.0-or-later. Los adaptadores nuevos de `platform/ps4/`, fixtures y herramientas propias se licencian bajo LGPL-2.1-or-later. El paquete de OrbisDesk (`OrbisDesk.pkg`, su ELF) enlaza todo eso junto con el cliente de Steam de abajo. La obra combinada se distribuye bajo **GPL-3.0-or-later**, lo que todas las licencias anteriores permiten. Ver los textos en `LICENSES/` (GPL-2.0, GPL-3.0, LGPL-2.1, LGPL-3.0).

## Cliente de Steam

El cliente de Steam se armó primero como un título aparte (ORBS00001) y se está integrando a OrbisDesk. Reutiliza código de Playden, así que se distribuye bajo la **GNU General Public License v3.0 o posterior**.

| Componente | Versión / origen | Licencia | Uso |
|---|---|---|---|
| Playden for PS5 (Leo Lobato) | commit `fb74dbfd6bb96fc19a96afc1f48a4e40a885216b`, <https://github.com/leolobato/playden-ps5> | GPL-3.0-or-later | Cliente del protocolo de Steam (`src/steam/`, `src/diagnostics/`), adaptado a PS4. Los archivos modificados lo indican en su cabecera; parches en `native/steam/patches/`. |
| curl | 8.22.0, <https://curl.se/> (SHA-256 `f7ef3ae8a22e521f289803fe93543eb64c329b58aa73a9e224dfd915a2a5f4f7`) | curl (tipo MIT) | HTTPS y WebSocket |
| Mbed TLS | 3.6.6, <https://github.com/Mbed-TLS/mbedtls> (SHA-256 `8fb65fae8dcae5840f793c0a334860a411f884cc537ea290ce1c52bb64ca007a`) | Apache-2.0 (elegida entre Apache-2.0 y GPL-2.0-or-later) | TLS, AES, SHA-1, RSA |
| Bundle de CA de Mozilla | `cacert-2026-09-25.pem`, <https://curl.se/ca/> (SHA-256 `a41b5d356aea97a529fe27e0f7316d2f9d946d75927476cf9cf1b90637d00505`) | MPL-2.0 | Raíces para validar certificados |
| zstd | 1.5.6, <https://github.com/facebook/zstd> (SHA-256 `8c29e06cf42aacc1eafc4077ae2ec6c6fcb96a626157e0593d5e82a34fd403c1`) | BSD-3-Clause (elegida entre BSD y GPL-2.0) | Descompresión de chunks |
| LZMA SDK (sólo `LzmaDec`) | 24.09, <https://github.com/ip7z/7zip/tree/24.09/C> | Dominio público | Descompresión de chunks |
| stb_image.h (Sean Barrett) | v2.30, <https://github.com/nothings/stb> (SHA-256 `594c2fe35d49488b4382dbfaec8f98366defca819d916ac95becf3e75f4200b3`) | Dominio público / MIT | Inflate (gzip y zip) del backend de Playden |
| QR Code generator (Project Nayuki), versión C | 1.8.0, <https://github.com/nayuki/QR-Code-generator> (`qrcodegen.c` SHA-256 `300eff07ee25baaa7578f20284411638154716379437391e7e689c0e6ce81403`, `qrcodegen.h` `e82df4bff37d18b5863b9e7486fe6bda1b6cda8c3b9ecebfec473907265cb589`) | MIT | Código QR del login |
| gbe_fork (fork de Goldberg Steam Emulator) | `release-2026_09_27`, <https://github.com/Detanup01/gbe_fork> (binario `emu-win-release-vs22.7z` SHA-256 `300186c34f49a9ea75b33ce2af299267cc1dad0225cf45e81a229578d4e11c85`; código fuente `ce3ce7aee0439f1b7aff2404106fe68184185a8d0b7ca5ab2677a046ea464cbd`) | LGPL-3.0 | Reemplazo opcional de `steam_api(64).dll` por juego, distribuido sin modificar. `native/steam/steam_emu.cpp` incluye una adaptación a C++ de su `generate_interfaces.cpp`, distribuida bajo GPL-3.0-or-later como permite la LGPL-3.0. |
| LLVM libc++, libc++abi, libunwind (SDK de OpenOrbis) | SDK v0.5.4 | Apache-2.0 WITH LLVM-exception | Runtime de C++ |

El paquete independiente ORBS00001 llevaba los textos de licencia de estos componentes en `/app0/assets/misc/`. El paquete de OrbisDesk (W301) todavía no los lleva; [licencias del release](docs/RELEASE_LICENSES-es.md) describe dónde van. La fuente correspondiente es este repositorio (`native/steam/`, `tools/build-steam-*.py`) más las fuentes de las dependencias, fijadas por SHA-256. El cliente no es oficial y Valve no lo respalda. Steam es marca de Valve Corporation.

## Componentes del runtime (W301)

El runtime que va a `/data` (`wine/`, `wine-prefix/`) contiene además estos programas y datos de terceros. La lista sale de recorrer `build/wine-hardware-w301/runtime` (1835 archivos): todo archivo PE sin la marca de builtin de Wine y todo archivo de datos que no es de Wine. Los hashes son los que fija el builder de la última columna.

| Componente | Versión / origen | Licencia | Dónde / builder |
|---|---|---|---|
| MangoHud para Windows (flightlessmango; fork para Windows de Leclowndu93150) | commit `52592550824ae11d5c68a6826f07db5f60220d23`, <https://github.com/Leclowndu93150/MangoHud-Windows>, parcheado por `tools/vk-h0/patch-mangohud-*.py` | MIT | `libMangoHud.dll` y `MangoHud.x86*.json` en `system32` y `syswow64`; `tools/vk-h0/build-mangohud.sh`, `build-mangohud-i386.sh` |
| Subproyectos Meson de MangoHud: Dear ImGui 1.91.6, ImPlot 0.16, spdlog 1.14.1 (con fmt), MinHook, Vulkan-Headers y Vulkan-Utility-Libraries 1.4.346 | Archivos wrap de MangoHud | ImGui, ImPlot, spdlog, fmt: MIT; MinHook: BSD-2-Clause; cabeceras y utilidades de Vulkan: Apache-2.0 (las cabeceras también MIT) | Estáticos dentro de `libMangoHud.dll` |
| Cargador Vulkan de Khronos | tag `v1.4.335` (Vulkan-Loader `052ac24611eced7b0ca62cc5cca2eeeb2051fa28`), compilado con llvm-mingw | Apache-2.0 | `vulkan-1.dll` en `system32` y `syswow64`; `tools/vk-h0/build-vulkan-loader.sh`, `build-vulkan-loader-i386.sh` |
| vkcube (Khronos Vulkan-Tools) | tag `v1.4.335` (`48b5d246b2d0b1a41ee7ea1b69525ae7bb38a2ae`) | Apache-2.0 | `C:\orbis\vkcube.exe`; `tools/vk-h0/build-vkcube.sh` |
| DXVK (Philip Rebohle y colaboradores) | 2.7.1, <https://github.com/doitsujin/dxvk/releases/tag/v2.7.1>, `dxvk-2.7.1.tar.gz` SHA-256 `d85ce7c79f57ecd765aaa1b9e7007cb875e6fde9f6d331df799bce73d513ce87`, sin modificar | Zlib | `d3d8`, `d3d9`, `d3d10core`, `d3d11`, `dxgi` (+ `dxvk_dxgi.dll`) en `system32` y `syswow64`; `tools/stage-dxvk.py` |
| VLC media player (VideoLAN) | 3.0.24 win64, `vlc-3.0.24-win64.7z` SHA-256 `1ed59c09152e78aff84663fa76efab26057716576db74332858810e5ef54ae1f`, sin modificar, unos 100 de sus plugins | VLC: GPL-2.0-or-later; libVLC/libvlccore: LGPL-2.1-or-later; bibliotecas incluidas con sus propias licencias (libavcodec/libavformat de FFmpeg LGPL-2.1-or-later o GPL según la compilación de VideoLAN, libdvdnav/libdvdread GPL-2.0-or-later, libdvdcss GPL-2.0-or-later, Qt LGPL, otras listadas en su `COPYING.txt`/`README.txt`) | `C:\Program Files\VLC`; `tools/stage-vlc.py` |
| Wine Gecko | 2.47.4 x86_64 (SHA-256 `fd88fc7e537d058d7a8abf0c1ebc90c574892a466de86706a26d254710a82814`) y x86 (`2cfc8d5c948602e21eff8a78613e1826f2d033df9672cace87fed56e8310afb6`), <https://dl.winehq.org/wine/wine-gecko/2.47.4/>, sin modificar | MPL-2.0; sus `mozavcodec`/`mozavutil` (FFmpeg) y `lgpllibs` son LGPL-2.1-or-later; NSS MPL-2.0 | `system32\gecko`, `syswow64\gecko`; `tools/stage-wine-gecko.py` |
| DOSBox Pure (Bernhard Schelling; DOSBox Team) | commit `ba6dcaee84aa2c22d709c3dfdacb7aca5ebc3042`, <https://codeberg.org/schelling/dosbox-pure> (`dos.lock.json`) | GPL-2.0-or-later | `dosbox_pure_libretro.dll` con `DOSBox-Pure-LICENSE.txt` y `DOS-runtime-source.tar.gz` en `system32` |
| Administrador de archivos WFM (BrunoSX) | commit `6b1860895885a6d65c37815308260293341acb5f` con los cambios de OrbisDesk en `tools/build-wfm.py` | MIT | `wfm.exe` en `system32`; `tools/build-wfm.py` |
| libcdio (**quitada después de la W301**) | `libcdio.dll` precompilado del repositorio de WFM (informa 2.2.0, x86_64), SHA-256 `cc9b86da2a437fd6859acaaf7de71ef271d4b7ba8274ebe7cfc92d86ce51ed09` | GPL-3.0-or-later | Se distribuyó en `system32` hasta la W301 sin fuente correspondiente conocida. `tools/build-wfm.py` ya no la enlaza, "Load ISO image" de WFM avisa que no está disponible, y la próxima subida borra la copia de la consola (ver [licencias del release](docs/RELEASE_LICENSES-es.md)) |
| pl_mpeg (Dominic Szablewski) | commit `c871f2be`, `pl_mpeg.h` SHA-256 `3a8cb30c83c2a1147719c30fe0c8b93da2987aa43140077c575b39aaa75fc2c9` | MIT | Compilado dentro de `pwmpeg1.ax` (`syswow64`); `tools/stage-dshow-i386.py` |
| GeneralUser GS (S. Christian Collins) | 2.0.3, commit `684543d5e5efaef08d02be50dcda8d552478fa60` de <https://github.com/mrbumpy409/GeneralUser-GS>, `.sf2` SHA-256 `9575028c7a1f589f5770fccc8cff2734566af40cd26ed836944e9a5152688cfe` | Licencia de GeneralUser GS (permite uso y redistribución; el texto va como `GeneralUser-GS-LICENSE.txt`) | `C:\windows\GeneralUser-GS.sf2`; `tools/build-wine-hardware.py` |
| Runtime de mingw-w64 y libc++/libunwind de LLVM (llvm-mingw 20260922) | Enlazados estáticamente en los PE compilados con llvm-mingw (Mesa WGL, MangoHud, el cargador Vulkan, vkcube, glxgears, fixtures propios) | Runtime de mingw-w64: ZPL-2.1 / dominio público con algunos archivos BSD/MIT; LLVM: Apache-2.0 WITH LLVM-exception | Avisos en `NOTICE` (ver [licencias del release](docs/RELEASE_LICENSES-es.md)) |
| Código incluido en Mesa dentro del ELF | BLAKE3, xxHash, parson y otros dentro de `src/util` | BLAKE3: CC0-1.0 o Apache-2.0; xxHash: BSD-2-Clause; parson: MIT; algunos archivos BSL-1.0 | Enlazados desde `~/vk-h0/build/mesa-wine` |
| Archivos de paquete de OpenOrbis | `sce_module/libc.prx`, `sce_module/libSceFios2.prx`, `sce_sys/about/right.sprx`, copiados de los ejemplos del SDK de OpenOrbis por `tools/orbis_package.py` | OpenOrbis no indica licencia; son módulos del sistema de la consola (ver [licencias del release](docs/RELEASE_LICENSES-es.md), riesgos que no son de licencia) | `OrbisDesk.pkg` |

Las fuentes propias de Wine (`tahoma.ttf`, `tahomabd.ttf`, `marlett.ttf`, LGPL-2.1-or-later, con fuentes y licencia en `C:\windows\Fonts\licenses`), los fondos que dibuja `tools/make-wallpaper-set.py`, la foto CC0 descrita abajo, los íconos, los temas y los fixtures de prueba de `C:\orbis` están cubiertos por las filas de arriba o son archivos del proyecto.

El cargador PE32 de `platform/ps4/pw_pe32.c` y el fixture `minimal.c` son código propio; se contrastó el formato con la especificación PE de Microsoft. El fixture se enlaza sin CRT ni bibliotecas Windows y su binario exacto acompaña los informes del incremento 4.

Los fixtures DLL/EXE y definiciones `.def` del incremento 6 también son propios. La biblioteca de importación se genera con la toolchain MinGW; no se incluyen DLL comerciales ni copias de kernel32/ntdll de Windows.

Los fixtures TLS y su helper de contraste del incremento 7 también son propios. El helper usa kernel32 únicamente al ejecutarse en Windows como referencia; esa biblioteca del sistema no se incorpora ni se simula en el runtime PS4.

El incremento 9 conserva los copyrights de las unidades Wine modificadas en su overlay y parche. Las adaptaciones de fstab y páginas de host siguen los parches 0100 y 0510 de prospero-win (sus colaboradores, LGPL-2.1-or-later), ajustados a PS4. Los harness propios incluyen código Wine real; el ELF de diagnóstico sigue siendo GPL-2.0-or-later. El SDK OpenOrbis original no se modifica: una copia de libc omite lstat.lo para usar la importación existente de libkernel; se conservan hashes, licencia del SDK y evidencia de esa transformación. Las estructuras ABI se contrastaron con el código de shadPS4, sin incorporar su filesystem al runtime.

La disposición de estructuras ABI se contrastó con `DolphinPS4/probe/main.cpp` y `shadPS4/src/core/libraries/kernel/threads/exception.h`. No se copió el runtime completo de ninguno de esos proyectos. La infraestructura RADV/GNM, Zink y DXVK no se incorpora en este hito. Antes de distribuirlos habrá que conservar sus licencias y publicar las modificaciones correspondientes.

Para distribuir un diagnóstico binario, acompañarlo con estas fuentes y los checkouts fijados de prospero-win, además de las licencias del SDK y las instrucciones de construcción. Este workspace no crea una release ni publica artefactos por sí mismo.

W170 usa como fondo de escritorio la foto "Green hill landscape under sky and clouds" de goodfreephotos.com, de dominio público (CC0). El original, su hash y la conversión a 1280x720 están en `out/wallpaper-cc0/manifest.json`.

La fase 8 (red) adapta `wine/ps5/pw_ws2_32_libc.c` de prospero-win (LGPL-2.1-or-later, sus colaboradores) en `platform/ps4/pw_ws2_32_libc.c`: las mismas reglas de resolución (numéricas, loopback, nombre local, nombres con punto por `sceNetResolverStartNtoa`, caché negativa de 5 s), con nombres PS4, sin los ganchos de su prueba de host y con una tabla corta de servicios.

W166 incorpora el agrupamiento de llamadas Vulkan de 32 bits de prospero-win (LGPL-2.1-or-later): `wine/ps5/pw_vk_*`, `wine/ps5/vulkan/*` y sus herramientas `tools/stage_vk_batch.py`, `stage_vk_replay_lifecycle.py` y `generate_vk_codecs.py`, aplicadas sin cambios a una copia de `dlls/winevulkan` (`tools/build-winevulkan-batch.py` guarda sus hashes). Los codecs se generan con el registro de Vulkan de Khronos 1.4.357 (`vk.xml`, `video.xml`; Apache-2.0 o MIT), el mismo que fija Wine.

El incremento 10 adapta los parches Wine 0101, 0102, 0110 y 0111 de prospero-win (LGPL-2.1-or-later). Sus originales, hashes y adaptaciones se identifican en el boot-manifest del overlay y la cápsula de evidencia. Los parches conservan los avisos de Wine. El código propio de señales, rutas y poll conserva la licencia LGPL indicada en cada archivo; el bootstrap y su homebrew de reproducción son GPL-2.0-or-later.

El emulador Linux se usa como herramienta externa. Su runtime privado glibc proviene del paquete Ubuntu indicado en linux-runtime.lock.json (LGPL-2.1-or-later para libc, con los avisos correspondientes del paquete). La distribución de estas dependencias requiere acompañar sus licencias y fuentes aplicables.

El incremento 11 añade parches propios al filesystem y a las exportaciones de mensajes de shadPS4, bajo GPL-2.0-or-later como sus archivos originales. Los adaptadores de mensajes Wine conservan LGPL-2.1-or-later; las pruebas homebrew conservan GPL-2.0-or-later. No se incorpora código de los filesystems de otros emuladores en el runtime de la consola. El build Linux usa LLVM/libc++ y libgcc_s como dependencias externas con sus licencias y excepciones correspondientes.

El incremento 12 añade referencias compartidas y controles SCM_RIGHTS propios al fork GPL-2.0-or-later de shadPS4. Las pruebas OpenOrbis son homebrew propio; no se incorporan pruebas al repositorio del emulador. La disposición del ABI se contrasta con las definiciones públicas de FreeBSD 9 y el SDK; no se copia su implementación de sockets. El adaptador de mensajes Wine mantiene LGPL-2.1-or-later.

El incremento 13 añade un backend propio que usa APIs de pipes de Linux, y su integración con los descriptores de shadPS4 conserva GPL-2.0-or-later. El homebrew de pipes también es propio bajo GPL-2.0-or-later. No se incorpora código del kernel Linux ni se modifica el SDK OpenOrbis original para proporcionar estos pipes.

El incremento 14 añade adaptadores propios de directorios bajo LGPL-2.1-or-later y homebrew propio bajo GPL-2.0-or-later. Las guardas de proceso se aplican al overlay LGPL de Wine y conservan sus avisos originales. No se incorpora una implementación de libc ajena ni se modifica el SDK; se usan sus declaraciones y las operaciones existentes de Orbis. El fork del emulador conserva la revisión del incremento 13.

W114 agrega juegos al menú Start (`docs/GAMES.md`). Las fuentes salen de un checkout parcial de ReactOS fijado en `games.lock.json` y se compilan sin modificar; sólo se reemplazan por archivos vacíos los includes de recursos propios de ReactOS (`reactos/version.rc`, `reactos/manifest_exe.rc`). Como Spider es GPL-2.0 y cards.dll LGPL-2.1-or-later, `out/games/games-source.tar.gz` lleva las fuentes del checkout, los stubs, el builder y los comandos exactos, y viaja junto a los binarios en `C:\windows\system32` con `ReactOS-COPYING.txt`, `ReactOS-COPYING.LIB.txt` y `cards-images-COPYING.txt`. Space Cadet Pinball no tiene datos libres: el código (MIT) puede compilarse, pero los archivos de datos deben aportarlos el usuario desde una instalación de Windows con licencia.

La fase 9 (navegador y webviews) incluye Wine Gecko 2.47.4 (MPL-2.0), los tarballs x86_64 y x86 de https://dl.winehq.org/wine/wine-gecko/2.47.4/ sin modificar, fijados por SHA-256 en `tools/stage-wine-gecko.py`. Las fuentes correspondientes están en el mismo directorio (`wine-gecko-2.47.4-src.tar.xz`). Pale Moon no se incluye: su licencia de redistribución pide permiso previo de Moonchild Productions para incluirlo en otro paquete. El acceso directo del menú Start usa la copia propia del usuario, sin cambiar sus archivos ni sus preferencias por defecto; las preferencias de `fixtures/browser` van sólo en un perfil propio que se pasa con `-profile`.
