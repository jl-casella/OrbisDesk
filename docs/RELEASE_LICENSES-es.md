# Licencias del release (alpha-1)

[English](RELEASE_LICENSES.md) | [Español](RELEASE_LICENSES-es.md)

Revisión de licencias para publicar OrbisDesk alpha-1 como un solo paquete con el runtime embebido (unos 1,1 GB, que se extraen a `/data` en el primer arranque). Cubre el ELF de la W301 y `build/wine-hardware-w301/runtime` (1835 archivos, unos 1,08 GB), que hoy van a la consola por FTP. Registrada el 2026-11-08.

**Esto es un análisis técnico, no asesoría legal.** Registra qué código hay en cada binario, qué licencia declara cada archivo o proyecto y qué piden esas licencias a una distribución binaria. Donde una conclusión depende de interpretación legal, lo dice. Antes de un release con más alcance conviene que lo revise un abogado.

## Resumen

| Tema | Estado | ¿Bloquea el alpha-1? |
| --- | --- | --- |
| Compatibilidad GPL del ELF (Playden GPL-3.0-or-later con Wine, Mesa, Crema, DolphinPS4 y código propio) | No se encontró código GPL-2.0-only; la combinación se puede distribuir como GPL-3.0-or-later | No |
| Textos de licencia, avisos de copyright e indicación de la fuente dentro del paquete/runtime | Faltan en la W301 (también los de Steam, desde que el cliente pasó al ELF). Cambio aplicado en `tools/build-wine-hardware.py` después de la W301; todavía sin build | **Sí**, hasta que una build los lleve |
| Fuente correspondiente publicada con el release (código propio, Wine, Mesa, VLC, Wine Gecko, DOSBox Pure, gbe_fork y las bibliotecas del ELF) | Todavía no hay tag de release ni archivo de fuentes | **Sí** |
| `libcdio.dll` (GPL-3.0-or-later) es un binario precompilado del repositorio de WFM, sin fuente correspondiente conocida | Quitada (decisión del usuario): WFM se compila sin ella y pierde "Load ISO image"; la subida borra la copia de la consola. Todavía sin build | No, cuando salga una build sin ella |
| Identidad de la PC de build en el runtime (`C:\users\jose`, `JCASELLA`, cadenas `/mnt/c/Users/...`) | Encontrada; los nombres del registro se corrigen en el builder (todavía sin build) | No (privacidad/prolijidad) |
| Entradas de `THIRD_PARTY.md` | Agregadas (MangoHud, VLC, Wine Gecko, cargador Vulkan, DXVK, DOSBox Pure, GeneralUser GS, WFM, libcdio, pl_mpeg, mingw-w64, código incluido en Mesa, archivos de paquete de OpenOrbis) | Hecho |
| Textos en `LICENSES/` | Agregados MIT, Apache-2.0, Apache-2.0 WITH LLVM-exception, MPL-2.0, Zlib, BSD-2-Clause, BSD-3-Clause, BSL-1.0, CC0-1.0, curl y `NOTICE.txt` | Hecho |
| Riesgos que no son de licencia (gbe_fork, libdvdcss, módulos de sistema de la consola en el paquete, acceso directo a SeaMonkey sin el programa) | Documentados abajo. El usuario mantiene libdvdcss y los módulos de la consola | Aceptados por el usuario |

## 1. Qué hay en el ELF y bajo qué licencia

El enlace de la W301 (`tools/build-wine-hardware.py`, `build/wine-boot/link-report.json`) mete esto en `eboot.bin`:

| Código | Licencia declarada | ¿Compatible con GPL-3.0-or-later? |
| --- | --- | --- |
| Código propio en `native/` | GPL-2.0-or-later | Sí ("or later") |
| Adaptadores propios en `platform/ps4/` | LGPL-2.1-or-later | Sí |
| Lado Unix de Wine, wineserver (en proceso) y partes de prospero-win | LGPL-2.1-or-later | Sí |
| Cliente de Steam: código de Playden (`native/steam/`, `build/steam-hosted/steam_client_hosted.o`) | GPL-3.0-or-later (cabeceras SPDX en los archivos de Playden) | Sí; es lo que fija la GPL-3 |
| `generate_interfaces.cpp` de gbe_fork, adaptado en `native/steam/steam_emu.cpp` | LGPL-3.0 | Sí (la LGPL-3.0 permite GPL-3) |
| curl 8.22.0 | curl (tipo MIT) | Sí |
| Mbed TLS 3.6.6 | Apache-2.0 (elegida entre Apache-2.0 y GPL-2.0-or-later) | Sí con GPL-3 (Apache-2.0 no es compatible con GPL-2) |
| zstd 1.5.6, LZMA SDK, stb_image, qrcodegen | BSD-3-Clause, dominio público, MIT/dominio público, MIT | Sí |
| Mesa 26.0.8 (RADV, ACO, NIR, util, vulkan util) | MIT; 723 etiquetas SPDX `MIT` y 2 `BSL-1.0` en los directorios enlazados, ninguna GPL | Sí |
| `include/drm-uapi/sync_file.h` de Mesa (vía `src/util/libsync.h`) | GPL-1.0-or-later WITH Linux-syscall-note | Sí; es sólo la interfaz del kernel en una cabecera, y la syscall note excluye a quien usa esa interfaz |
| Winsys de Crema `ac_ps4_drm.c` | `Copyright 2026 DolphinPS4. SPDX-License-Identifier: MIT` | Sí |
| Cabeceras de `port/mesa-overlay/` y `patches/mesa-ps4*.patch` de Crema | Sin aviso por archivo; el repositorio de Crema es MPL-2.0 y los parches vienen de DolphinPS4 (GPL-2.0-or-later). Los parches modifican archivos MIT de Mesa | Sí con cualquiera de las dos lecturas: la MPL-2.0 sin el aviso "Incompatible With Secondary Licenses" (no aparece en Crema) permite una obra mayor GPL (MPL §3.3); la GPL-2.0-or-later permite GPL-3 |
| Sonda Vulkan de DolphinPS4 (`native/vk_probe/main.c`, `vk_probe.o`) y su receta de toolchain (ediciones al build de libc++, cabeceras del overlay de libc) | GPL-2.0-or-later (README y LICENSE de DolphinPS4) | Sí |
| libc++/libc++abi 21.1.6 de LLVM | Apache-2.0 WITH LLVM-exception | Sí con GPL-3 |
| zlib (`~/vk-h0/sysroot/lib/libz.a`, zlib-ng) | Zlib | Sí |
| CRT, libc (basada en musl) y stubs del SDK de OpenOrbis | Repositorio GPL-3.0; libc de musl (MIT) | Sí; la propia GPL-3.0 del SDK hace además que el ELF no pueda ser GPL-2.0-only |

**Resonance.** `THIRD_PARTY.md` la listaba como "GPL-2.0; revisar componentes individualmente". Su README dice GPL-2.0 (la licencia de Flycast, sin "or later"). Se comparó línea por línea cada archivo fuente de `upstream/Resonance` (`port/`, `patches/`, `toolchain/`, `scripts/`, `tools/`, sin `port/third_party`) contra `native/`, `platform/`, `tools/`, `fixtures/` y `patches/`, y no apareció ninguna línea exclusiva de Resonance: sólo líneas que comparte con DolphinPS4 o Crema (el mismo `ac_ps4_drm.c`, la receta de toolchain y dlmalloc) y texto estándar de la GPL. Ningún builder lee `upstream/Resonance`. Es sólo referencia, nada suyo se distribuye, y no hace falta pedir relicencia ni reescribir.

**Conclusión.** No se encontró código GPL-2.0-only en el ELF, así que la combinación se puede distribuir bajo GPL-3.0-or-later, como dice `THIRD_PARTY.md`. Si hubiera estado enlazado código de Resonance (o de Flycast), las opciones habrían sido: reescribir ese código, dejarlo fuera del ELF o pedirle al autor permiso "or later". Conviene repetir la comprobación cada vez que se adopte código de otro port de PS4: compararlo contra el árbol de Resonance como se hizo acá.

## 2. Componentes del runtime

La tabla completa está en [THIRD_PARTY](../THIRD_PARTY-es.md#componentes-del-runtime-w301). El recorrido listó todo archivo PE sin la marca de builtin de Wine (111 archivos fuera de VLC) y todo archivo de datos que no es de Wine. Además de Wine, el runtime contiene: MangoHud y sus subproyectos, el cargador Vulkan de Khronos y vkcube, DXVK 2.7.1, VLC 3.0.24 con unos 100 plugins, Wine Gecko 2.47.4, DOSBox Pure, WFM, libcdio, pl_mpeg (en `pwmpeg1.ax`), los juegos de ReactOS, las DLL de gbe_fork, GeneralUser GS 2.0.3, el bundle de CA de Mozilla, Mesa WGL/Zink con el runtime de mingw-w64, las fuentes de Wine, programas de prueba propios, íconos, temas y fondos. Tres archivos son marcadores que genera el propio Wine (`dosx.exe`, `ddhelp.exe`, `dsound.vxd`: "Wine placeholder DLL") y los `winmetadata/*.winmd` salen del build de Wine.

Qué pide cada licencia a esta distribución binaria:

| Licencia | Componentes | Qué pide |
| --- | --- | --- |
| GPL-3.0-or-later | El ELF completo | Texto de la licencia; Fuente Correspondiente de todo el ELF (cada biblioteca enlazada y los scripts de build) ofrecida de una de las formas de la GPL-3 §6; Avisos Legales Apropiados en las interfaces interactivas donde el programa ya los muestra (§5d) |
| GPL-2.0(-or-later) | VLC, DOSBox Pure, Spider de ReactOS | Texto de la licencia; fuente completa junto al binario u oferta escrita válida por tres años (§3). Ofrecer la fuente desde el mismo lugar que el binario cuenta |
| LGPL-2.1/3.0 | Wine (PE y Unix), libVLC, cards.dll, las partes FFmpeg de Gecko, gbe_fork | Texto de la licencia; fuente de la biblioteca tal como se distribuye, con sus cambios |
| MPL-2.0 | Wine Gecko, bundle de CA, archivos del repositorio de Crema | Texto de la licencia y cómo obtener la forma fuente de los archivos MPL |
| MIT, BSD, Zlib, BSL, Apache-2.0 | Mesa, MangoHud, ImGui, DXVK, cargador Vulkan, curl, Mbed TLS, zstd, etc. | Mantener el texto de la licencia y los avisos de copyright junto al binario (Apache: también su NOTICE si lo hay; ninguno de los proyectos Apache incluidos tiene) |

## 3. Textos de licencia y cómo viajan

`LICENSES/` tiene ahora GPL-2.0, GPL-3.0, LGPL-2.1, LGPL-3.0, MIT, Apache-2.0, Apache-2.0 WITH LLVM-exception, MPL-2.0, Zlib, BSD-2-Clause, BSD-3-Clause, BSL-1.0, CC0-1.0 y curl. De dónde salen: los textos GNU ya estaban; MIT y BSL-1.0 son los de `licenses/` de Mesa (sin las líneas de cabecera), Apache-2.0 es `LICENSES/Apache-2.0.txt` de Vulkan-Headers, el texto de LLVM es `LICENSE.TXT` de libc++, MPL-2.0 es el `LICENSE` de Crema, curl es el `COPYING` de curl 8.22.0, CC0-1.0 es la copia de `common-licenses` de Ubuntu, y BSD-2-Clause, BSD-3-Clause y Zlib son las plantillas SPDX. `LICENSES/NOTICE.txt` lista el aviso de copyright de cada componente, que los textos genéricos MIT/BSD/Zlib dejan como marcador.

Disposición propuesta en lo que se distribuye:

- **Runtime:** `C:\orbis\licenses\` (`/data/wine-prefix/drive_c/orbis/licenses`): todos los `LICENSES/*.txt`, `NOTICE.txt`, `THIRD_PARTY.md` y un `SOURCE.txt` generado que indica el repositorio, el tag del release, el commit exacto (y si el árbol tenía cambios locales) y dónde están las fuentes de terceros. Los componentes que ya llevan su propio texto lo conservan (`COPYING.txt` de VLC, `DOSBox-Pure-LICENSE.txt`, los textos de ReactOS, los de gbe, GeneralUser GS, las licencias de las fuentes de Wine).
- **Paquete:** el paquete único que embebe el runtime debería llevar además la misma carpeta fuera del archivo que extrae, en `/app0/assets/licenses/` (`pkg_build` sólo acepta `sce_sys`, `sce_module` y `assets/*`), para que se puedan leer aunque nunca se arranque el título. Eso corresponde a la tarea del runtime embebido.
- **Aviso legal en la interfaz (recomendado):** una línea en el selector NORMAL/ROOT o en el overlay de control: "OrbisDesk es software libre bajo la GNU GPL v3 o posterior, sin garantía. Licencias: C:\orbis\licenses". La GPL-3 §5(d) lo pide sólo si el programa adaptado ya muestra esos avisos; agregarlo cuesta poco.

El cambio de builder (`release-licenses.patch.py`, aplicado a `tools/build-wine-hardware.py` después de la W301 con el visto bueno de la sesión integradora) stagea la carpeta de arriba, guarda los hashes de sus archivos en `manifest['licenses']` y reemplaza el nombre de la PC de build en el registro que se distribuye (sección 4). El builder compila con el cambio; todavía no corrió en una build. `SOURCE.txt` nombra la build y el tag (`W301`, `04.00`) como literales, igual que el resto del builder, así que se actualizan con el número de build.

## 4. Identidad de la PC de build en el runtime

| Rastro | Dónde | Origen | Propuesta |
| --- | --- | --- | --- |
| Perfil `C:\users\jose\`, con `AppData\Roaming\MangoHud\MangoHud.conf` | Árbol del prefijo; carpetas de shell de `user.reg` (`AppData`, `Desktop`, `Personal`, `TEMP`...), `ProfileImagePath` y `Common Favorites` de `system.reg` | El prefijo se arma en el host con `prepare-host-prefix.py` como el usuario del host. `build-wine-hardware.py` escribe ahí `MangoHud.conf` a propósito y `make-start-menu.py` apunta ahí "MangoHud Config" | Ver abajo |
| `ComputerName`=`JCASELLA`, `Hostname` de Tcpip=`jcasella` | `system.reg`, `system.reg.build` | Prefijo del host | Reemplazar por `ORBISDESK`/`orbisdesk` (aplicado en el builder) |
| `USERDOMAIN`, `LOGONSERVER` = `JCASELLA` | `user.reg` (Volatile Environment) | Prefijo del host | Igual (aplicado en el builder) |
| Cadenas `/mnt/c/Users/JoseCasella/DEV/Codex/PS4/.deps/...` | 114 binarios del runtime (módulos PE de Wine, explorer, WFM, objetos de Steam) y el ELF | `__FILE__` en los nombres de secciones críticas y asserts de Wine | Agregar `-ffile-prefix-map=/mnt/c/Users/JoseCasella/DEV/Codex/PS4=.` (y `~/vk-h0=vk-h0`) a los flags de compilación de PE y ELF. Toca muchos builders compartidos; no está preparado |

No se encontró `/home/jose`, direcciones de correo ni otros datos personales en el runtime.

**¿La consola usa `orbis`?** Sólo en parte. `native/wine_boot.c` arranca Wine como usuario `orbis` y el builder crea `C:\users\orbis` (W048), pero las carpetas de shell del registro que se distribuye siguen nombrando `C:\users\jose`. La evidencia física de W091/W092 ([historia de gráficos](HARDWARE_G001-es.md)) registró `APPDATA` = `C:\users\jose\AppData\Roaming` en la consola, y por eso W092 movió `MangoHud.conf` ahí. Hoy `%APPDATA%`, `%TEMP%` y las carpetas Documentos y Escritorio del shell resuelven a `C:\users\jose`, mientras que algunas rutas usan `C:\users\orbis` (los accesos del Escritorio que copia `build-wine-hardware.py`, el perfil de SeaMonkey).

Cambiar sólo `MangoHud.conf` a `orbis` rompería la configuración de MangoHud. Una mudanza real necesita, todo junto: reescribir `C:\\users\\jose` como `C:\\users\\orbis` en el `user.reg` y el `system.reg` que se stagean (en `build-wine-hardware.py`, después de copiar el árbol del perfil del host), escribir `MangoHud.conf` bajo `orbis`, cambiar `tools/make-start-menu.py`, y mover una vez en la consola, antes de que arranque Wine, lo que el usuario ya guardó en `C:\users\jose` (partidas guardadas en `AppData`, Documentos) a `C:\users\orbis`. `upload-hardware.py` reemplaza `user.reg` en cada subida, así que la parte del registro es segura, pero los archivos del usuario no. La extracción del primer arranque del runtime embebido es el lugar natural para esa mudanza única. Recomendación: hacerlo en esa tarea, no como un parche aparte.

## 5. Fuente correspondiente por release

Mecanismo propuesto: un tag de Git por versión (`orbisdesk-04.00` para el alpha-1) en el repositorio público y, en la misma página del release que `OrbisDesk.pkg`, un archivo `orbisdesk-04.00-third-party-sources` con su lista de SHA-256. Ofrecer la fuente desde el mismo lugar que el binario cumple la GPL-2 §3 y la GPL-3 §6(d) sin oferta escrita; `SOURCE.txt` además ofrece las fuentes a pedido durante tres años, lo que cubre a quien consiga el paquete por otro lado.

Qué tiene que contener el archivo (o el tag):

| Fuente | Por qué | Hoy |
| --- | --- | --- |
| Este repositorio en el tag: `native/`, `platform/`, `tools/` (con las recetas de `tools/vk-h0/`), `patches/`, `fixtures/`, locks | Fuente Correspondiente GPL-3 del ELF, con los scripts de build; cambios LGPL a Wine | En Git, sin tag |
| Fuente de Wine en `490f6d5dcbb2a5047345b8af88d114bbcaad69a8`, más los overlays generados que compiló la build (`.deps/wine/ps4-overlay`, `ps4-win32u-overlay`, `explorer-hw-overlay` y los demás overlays de módulos) | LGPL: la fuente de la biblioteca modificada. Los generadores están en Git, pero incluir los árboles generados quita toda duda sobre la "forma preferida" | Sin empaquetar |
| prospero-win en `0e7b6b4a53a9aebfeceaf28fabb919e2452bbadc` | LGPL, compilado en el ELF | Fijado |
| Tarball de Mesa 26.0.8, `patches/` y `port/` de Crema en `475b8d5b`, cabeceras de libdrm, zlib-ng, runtimes de LLVM 21.1.6, toolchain de DolphinPS4 en `879b3e57` | Parte del ELF GPL-3 | Tarball fijado; el resto fijado por commit |
| Fuente de OpenOrbis PS4 Toolchain v0.5.4 (CRT, libc, stubs) | Enlazado en el ELF | Archivo del release fijado en `artifacts.lock.json` |
| Playden en `fb74dbfd`, curl 8.22.0, Mbed TLS 3.6.6, zstd 1.5.6, LZMA SDK 24.09, stb, qrcodegen 1.8.0 | Cliente de Steam en el ELF | Descargados y fijados por SHA-256 |
| Fuente de VLC 3.0.24 (`vlc-3.0.24.tar.xz`) y las fuentes de contrib que usó VideoLAN para el build win64 | GPL-2/LGPL; se distribuye sin modificar, pero quien distribuye igual debe la fuente | Sin descargar |
| Fuente de Wine Gecko 2.47.4 (`wine-gecko-2.47.4-src.tar.xz`) | Partes MPL-2.0 y LGPL | Sin descargar |
| DOSBox Pure en `ba6dcaee` | GPL-2.0-or-later | Ya viaja como `DOS-runtime-source.tar.gz` |
| Juegos de ReactOS en `5f6ef754` | GPL-2.0, LGPL-2.1 | Ya viaja como `games-source.tar.gz` |
| Tarball de fuente de gbe_fork `release-2026_09_27` | LGPL-3.0 | Fijado; sólo viaja una referencia (`gbe-SOURCE.txt`) |
| libcdio que corresponda a `libcdio.dll` (solo W058-W301) | GPL-3.0-or-later | **Desconocida**: la DLL la precompiló el autor de WFM. Se quitó de las builds siguientes; para los releases nuevos, quitarla es la respuesta |

Huecos que hoy impiden reconstruir desde un clone limpio (ver [disposición del repositorio](REPOSITORY_LAYOUT-es.md)):

- Las recetas gráficas de `tools/vk-h0/` tienen fijo `/mnt/c/Users/JoseCasella/DEV/Codex/PS4` y trabajan en `~/vk-h0`, fuera del repositorio.
- La configuración de Wine en el host y la generación del prefijo no están orquestadas; el paquete consume `reports/increment15/prefix-package` y `reports/increment15/host-build/report.json`, que Git ignora.
- El builder final lee muchos `out/*/manifest.json` y `build/wine-boot/link-report.json` que producen otros builders; no hay una build única ordenada.
- `libcdio.dll` era un binario precompilado (ya quitado); los módulos de paquete de OpenOrbis salen de los ejemplos del SDK.
- No se demostró una build limpia completa del paquete.

Para el alpha-1 esto significa que la fuente publicada está completa pero reconstruirla requiere los pasos manuales documentados; la GPL pide la fuente y los scripts de build, no una build de un solo comando, pero los huecos deberían figurar en las notas del release.

## 6. Riesgos que no son de licencia

- **gbe_fork en `C:\orbis\steam`.** Un emulador de la API de Steam, que se distribuye sin modificar como reemplazo opcional de `steam_api(64).dll` por juego. Su licencia (LGPL-3.0) se cumple, pero permite que los juegos corran sin los controles del cliente propio de Steam. El acuerdo de suscriptor de Valve, posibles pedidos de baja contra el repositorio y cómo se percibe el proyecto son riesgos. OrbisDesk no agrega ninguna evasión de DRM, y esta revisión no ayuda con ninguna.
- **libdvdcss dentro de los plugins de DVD de VLC.** El build win64 de VideoLAN la incluye para leer DVD cifrados con CSS. Su licencia es GPL-2.0-or-later, pero distribuirla está restringido por leyes contra la elusión en algunos países. Opciones: mantenerla (como la distribuye VideoLAN) o distribuir VLC sin ella, lo que limita la reproducción a discos sin cifrar. **Decisión: el usuario la mantiene**; el riesgo queda documentado acá.
- **Módulos de sistema de la consola en el paquete.** `sce_module/libc.prx`, `sce_module/libSceFios2.prx` y `sce_sys/about/right.sprx` se copian de los ejemplos del SDK de OpenOrbis, como hace la mayoría del homebrew. Son archivos de sistema de la consola sin licencia indicada. `THIRD_PARTY.md` ahora los nombra. **Decisión: el usuario los mantiene**; el riesgo queda documentado acá.
- **Acceso directo a SeaMonkey sin el programa.** El acceso del menú Inicio y el perfil stageado (`fixtures/browser/seamonkey-user.js`) suponen la copia propia del usuario de SeaMonkey en el prefijo; una instalación nueva no la tiene, así que el acceso falla. Ocultarlo o quitarlo cuando falta el programa, o explicarlo en las notas del release.
- **Marcas.** Windows, PlayStation, Steam y Valve son marcas de sus dueños; el texto del release debería aclarar que OrbisDesk no está afiliado a ellos (el cliente de Steam ya lo dice).

## 7. Qué se comprobó y qué no

Comprobado: cabeceras de licencia y README de Crema, DolphinPS4, Resonance, Playden y OpenOrbis; las entradas del enlace de la W301; las etiquetas SPDX de los directorios de Mesa enlazados en el ELF; una comparación de líneas de Resonance contra este repositorio; un recorrido de archivos del runtime de la W301; cadenas del registro y de los binarios en busca de rastros del host; el `APPDATA` de la consola según la evidencia física de W091/W092. No se hizo: build, enlace, subida ni cambios en builders compartidos. La carpeta de licencias y el cambio de registro no se probaron en hardware. La lista exacta de bibliotecas incluidas en VLC 3.0.24 no se auditó más allá de su `COPYING.txt`/`README.txt`.
