# Licencias y procedencia

[English](THIRD_PARTY.md) | [Español](THIRD_PARTY-es.md)

Las fuentes descargadas permanecen en `upstream/`; sus revisiones exactas están en `sources.lock.json`. Las descargas binarias oficiales están fijadas por SHA256 en `artifacts.lock.json`. No se incluyen juegos, BIOS, claves ni módulos de firmware.

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
| Crema | Referencia del port Cemu y del driver PS4 | MPL-2.0; revisar componentes individualmente |
| Resonance | Referencia de memoria, recompilación y reutilización de infraestructura | GPL-2.0; revisar componentes individualmente |
| shadPS4 | Emulador oficial, referencia ABI y fork local con parches reproducibles en `patches/shadPS4/` |GPL-2.0-o-later|
| OpenOrbis | SDK, CRT, libc y stubs usados para generar homebrew | Sus licencias incluidas en `.deps/sdk/OpenOrbis/PS4Toolchain` |
| ReactOS Solitaire y cardlib (J Brown, 2001), revisión 5f6ef754 | `sol.exe` (W114, Start → Programs → Games), compilado sin cambios con `tools/build-games.py` | Dominio público (`ReadMe.txt` de solitaire y de cardlib) |
| ReactOS Spider Solitaire (Gregor Schneider), revisión 5f6ef754 | `spider.exe` (W114) | GPL-2.0 (los archivos remiten a `COPYING` de ReactOS); fuente y comandos en `out/games/games-source.tar.gz` |
| ReactOS cards.dll (Filip Navara), revisión 5f6ef754 | `cards.dll` (W114), cartas que cardlib carga en ejecución | LGPL-2.1-or-later; imágenes de las cartas de uso libre según `dll/win32/cards/COPYING` |
| SpaceCadetPinball (Andrey Muzychenko), SDL2 2.32.8 - Sí. SDL2_mixer 2.8.1 | Opcional (`build-games.py --pinball`), todavía no compilado; sin datos del juego | MIT; SDL2 y SDL2_mixer Zlib. Los datos (PINBALL.DAT, WAV, MID) son de Microsoft y no se incluyen |

Los diagnósticos de `native/` se distribuyen bajo GPL-2.0-or-later. El ELF de diagnóstico enlaza ese código y componentes LGPL, y se entrega bajo GPL-2.0-or-later. Los adaptadores nuevos de `platform/ps4/`, fixtures y herramientas propias se licencian bajo LGPL-2.1-or-later. Ver los textos en `LICENSES/`.

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
