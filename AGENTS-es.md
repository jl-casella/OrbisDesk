# OrbisDesk: guía para desarrollo asistido por IA

[English](AGENTS.md) | [Español](AGENTS-es.md)

Este es el punto de entrada para una IA o una persona que empieza a trabajar en el repositorio. Usa Markdown con un mapa ASCII de carpetas. Los comandos son puntos de entrada con prerrequisitos explícitos; no afirman que un clon nuevo tenga una compilación completa con un solo comando.

## 1. Primera lectura y estado real

1. Leer [README](README-es.md), [estado actual](docs/CURRENT_STATE-es.md), [estado y evidencia](docs/STATUS-es.md) y [estructura y dependencias](docs/REPOSITORY_LAYOUT-es.md).
2. Usar el [índice completo](docs/INDEX-es.md) para encontrar el subsistema o la build correspondiente. Los documentos llamados `borrador`, `plan` o `Wxxx` son propuestas, no evidencia de aceptación. Los incrementos antiguos pueden describir fallos resueltos después.
3. Inspeccionar el builder, sus manifiestos de entrada, el manifiesto de salida y la última evidencia de ejecución/transferencia **antes** de elegir una build o afirmar compatibilidad. Las fechas de archivo y el número más alto no alcanzan.
4. Leer `git status --short`, comprobar trabajo concurrente y preservar cambios ajenos. Muchos builders comparten directorios de salida; no ejecutarlos en paralelo si se pisan.

Al actualizar esta guía por última vez (2026-11-07), el [estado actual](docs/CURRENT_STATE-es.md) registra W288 como la última build subida y W287 como la última con evidencia física ([W285–W288](docs/HARDWARE_W285_W288-es.md)). Conciliarlo con los manifiestos reales, la evidencia de transferencia y el feedback del usuario en cada sesión.

## 2. Modelo del proyecto y reglas fundamentales

OrbisDesk ejecuta un escritorio y aplicaciones Windows en PS4 con Wine y servicios nativos de la consola. El anfitrión nativo es x86-64. Existe la ruta del traductor x86 de prospero-win y una ruta posterior de WoW64 nativo: comprobar el proveedor activo y los marcadores de ejecución; no asumir que se usa el mismo en todos lados.

Explorer aloja varios invitados Windows dentro de un único título/proceso PS4. El código posterior añade un mundo de 32 bits junto a los invitados de 64 bits. Hay adaptaciones por hilo/invitado, pero se comparten espacio de direcciones nativo, servidor y parte del estado gráfico/global. Un invitado no es un proceso nativo aislado. Una colisión de base fija puede requerir el fallback de relanzamiento documentado. Un segundo proceso PS4 arbitrario con su propio Wine no es una solución establecida aquí.

- No simular éxito de capacidades pendientes con stubs, eventos inventados o informes reescritos. Conservar el fallo real y una reproducción mínima.
- Los parches de shadPS4 deben implementar comportamiento general de plataforma, con reproducción independiente cuando sea posible. Cambiar el emulador no cambia el kernel de una PS4 real.
- Separar referencia anfitriona, emulador oficial, fork y hardware físico. No presentar un éxito del fork como compatibilidad oficial.
- El producto visible es **OrbisDesk**. El paquete principal distribuido es `OrbisDesk.pkg`; la versión visible pertenece sólo al selector NORMAL/ROOT. Preservar identidades técnicas de actualización, claves de migración, evidencia antigua y rutas de compatibilidad. Ver [marca](docs/REBRANDING_ORBISDESK-es.md), [constantes](tools/project_brand.py) y [empaquetado](tools/orbis_package.py).
- Mantener documentación pública en inglés con una variante completa `-es.md`, según la [política](docs/DOCUMENTATION_POLICY-es.md). No incorporar investigaciones/comparaciones privadas a la documentación pública.

## 3. Mapa de carpetas y contenido de Git

```text
OrbisDesk/
|-- AGENTS.md / AGENTS-es.md        Entrada para IA/desarrolladores
|-- README.md / README-es.md        Presentación del proyecto
|-- *.lock.json                    Fuentes, archivos, herramientas y entorno observado
|-- native/                        Lanzador, integración de consola y auxiliares nativos
|   |-- hw_sink_gpu/               Presentación/composición GPU
|   |-- pwmpeg1/                   Integración del decodificador MPEG
|   |-- steam/                     Cliente Steam nativo y adaptaciones
|   `-- vk_probe/                  Diagnósticos gráficos nativos y shaders
|-- platform/ps4/                  Adaptadores Wine, VM, TLS, señales, archivos y audio
|-- fixtures/                      Fuentes Windows propias/adaptadas y pequeñas entradas
|-- patches/shadPS4/               17 parches ordenados y overlay pendiente 0018
|-- patches/wine/                  Instantáneas de parches; los generadores son esenciales
|-- tools/                         Descarga, parches, build, staging, ejecución y evidencia
|   `-- vk-h0/                     Recetas y transformaciones Mesa/Zink/Vulkan/MangoHud
|-- tests/                         Comprobaciones enfocadas de host/Windows
|-- docs/                          Documentación pública bilingüe e informes históricos
|-- LICENSES/ / THIRD_PARTY.md      Licencias y atribuciones
|-- private-notes/                 IGNORAR: investigación privada, fuera de publicaciones
|-- upstream/ / .deps/              IGNORAR: fuentes externas, SDKs y descargas
`-- build/ / out/ / reports/        IGNORAR: builds, paquetes, runtimes y evidencia generados
```

WSL también usa `~/vk-h0/` para fuentes gráficas, sysroot, herramientas y builds. Está fuera de la raíz Git. El [inventario](docs/REPOSITORY_LAYOUT-es.md) describe las ubicaciones actuales; no asumir que existen en otra computadora.

No comitear repositorios anidados, submódulos/gitlinks, bibliotecas descargadas completas, DLLs/EXEs/PKGs compilados, prefijos ni archivos de runtimes. Conservar revisiones fijadas, parches, adaptadores y generadores. Ejecutar la [validación de estructura](tools/check-repository-layout.py) antes de preparar/publicar un commit. La evidencia ignorada sirve localmente, pero no existe en un clon nuevo.

## 4. Entorno, fuentes y restauración de parches

Entorno principal: Windows, Ubuntu 22.04 en WSL (`Ubuntu-22.04`), Python 3.10+, OpenOrbis v0.5.4 y Clang/LLVM según la receta. El emulador usa Clang 19/libc++; los diagnósticos antiguos y las compilaciones gráficas tienen otros requisitos. No sustituir silenciosamente un compilador porque exista un comando `clang`.

Trabajar desde la raíz. En PowerShell lanzar comandos Linux con `wsl -d Ubuntu-22.04 -- ...`; en WSL usar la ruta Linux del checkout. No asumir la ruta original `/mnt/c/Users/...`. Revisar [entorno observado](build-environment.lock.json), [artefactos](artifacts.lock.json), [herramientas](fork-tools.lock.json), [emulador Linux](linux-emulator.lock.json) y [libc privada](linux-runtime.lock.json).

```powershell
# Descarga/verifica SDK y emulador oficial de Windows; revisar prerrequisitos primero.
./tools/bootstrap.ps1
```

```sh
# Restauración de fuentes en un clon nuevo; no compila toda la app ni baja todos los recursos.
python3 tools/restore-dependencies.py --fetch

# Inspección de bases; --archives requiere además que existan los archivos gráficos.
python3 tools/restore-dependencies.py --only wine-build-source --only shadps4-fork --only wfm --only dosbox-pure --only mangohud --archives
```

[dependencies.lock.json](dependencies.lock.json) cataloga 19 identidades de fuentes y hashes de archivos gráficos. [sources.lock.json](sources.lock.json) fija las bases originales. La fuente fijada de Wine indica 11.17; manda el commit, no sólo esa etiqueta. El restaurador no reemplaza directorios existentes diferentes o sin Git. Algunas comprobaciones sólo verifican HEAD y aclaran que no evalúan modificaciones locales: inspeccionar el diff cuando se necesite una base limpia.

La recuperación del emulador usa [fork.lock.json](fork.lock.json): base upstream `529ceb32f5546b820588f194b903cc39d08015fe`, 17 parches ordenados y el [overlay 0018](patches/shadPS4/pending/0018-fixed-executable-and-kernel-signals.patch), con hash separado. El lock de dependencias registra el árbol esperado previo al overlay. Los datos del committer pueden cambiar los IDs al reconstruir commits; las comprobaciones de contenido/árbol y overlay evitan declarar idénticas fuentes diferentes. El checkout de shadPS4 de referencia no es la base del fork.

Wine requiere las [instantáneas de parches](patches/wine/) y las transformaciones de [prepare-wine-ps4.py](tools/prepare-wine-ps4.py), [prepare-wine-boot.py](tools/prepare-wine-boot.py), los builders de módulos y los adaptadores. Los tres parches estáticos no representan todo el port actual. Mantener upstream limpio y modificar el generador/overlay, no sólo una copia generada ignorada.

## 5. Compilación: seguir el grafo de dependencias

Muchas herramientas ejecutan trabajo al cargar el módulo. No importar builders arbitrarios, recorrerlos automáticamente con `--help` ni ejecutar todos los `build-*.py` alfabéticamente: algunos compilan de inmediato, vacían sus propios directorios o empaquetan/transfieren. Leer primero su código y argparse.

| Capa | Puntos de entrada | Entradas/resultados a revisar |
| --- | --- | --- |
| Diagnósticos y fixtures PE | [build.py](tools/build.py), [fixture de consola](tools/build-console-bare.py) | SDK/upstream; `out/build.json`, `out/eboot.bin`, EXEs/DLLs de prueba |
| Wine anfitrión/PE | [build-wine.py](tools/build-wine.py), [cierre PE](tools/build-host-wine-closure.py), [cierre Unix](tools/build-host-wine-unix.py) | `.deps/wine/source`, `.deps/wine/runtime/build`, `out/wine/`, `reports/increment15/host-build/` |
| Prefijo preparado | [prepare-host-prefix.py](tools/prepare-host-prefix.py), [package-wine-prefix.py](tools/package-wine-prefix.py), [consumidor](tools/wine_prefix.py) | Primero ejecución anfitriona; paquete verificado en `reports/increment15/prefix-package/` |
| Configure/Unix/servidor PS4 | [probe-wine-unix.py](tools/probe-wine-unix.py), [build-wine-ps4.py](tools/build-wine-ps4.py) | Herramientas de Wine anfitrión y OpenOrbis; `.deps/wine/ps4-unix/Makefile`, overlays, `build/wine-boot/`, `build/wine-server/` |
| CPU/mundo de 32 bits | [wowprospero](tools/build-wowprospero-ps4.py), [wow64native](tools/build-wow64native-ps4.py), [mundo WoW64](tools/build-wow64-world-ps4.py) | Recetas PE/Unix exactas, reemplazos de objetos y manifiestos de proveedores |
| Cargador de invitados/shell | [módulos de invitados](tools/build-guest-hw.py), [Explorer](tools/build-explorer-hw.py), [WFM](tools/build-wfm.py), [protocolo de apertura](platform/ps4/pw_shell_open.h) | Variantes PE32/PE64 y ciclo de vida; manifiestos regenerados de Explorer/WFM |
| Gráficos | [win32u](tools/build-win32u-ps4.py), [winevulkan](tools/build-winevulkan-ps4.py), [batching Vulkan](tools/build-winevulkan-batch.py), [wined3d](tools/build-wined3d-hw.py), [staging DXVK](tools/stage-dxvk.py), [recetas gráficas](tools/vk-h0/) | RADV/GNM, Mesa WGL/Zink, ambas arquitecturas PE y variantes del cargador/capa Vulkan |
| Servicios/entrada/audio | [bibliotecas Unix](tools/build-unixlibs-ps4.py), [audio](tools/build-audio-ps4.py), [señales](tools/build-signal-ps4.py), [filtrado de directorios](tools/build-wine-directory-ps4.py), [servidor de borrado](tools/build-wine-delete-server.py), [HID](tools/build-hidstack-hw.py) | Objetos recompilados y sus hashes/manifiestos |
| Cierre PE/runtime | [GUI](tools/stage-wine-gui.py), [PE64](tools/stage-wine-pe64.py), [i386](tools/stage-wine-i386.py), [programas](tools/stage-wine-programs.py), [extras](tools/stage-wine-extras.py), [cierre web](tools/check-web-closure.py) | Imports, arquitectura, duplicados, archivos de prefijo y hashes |
| Enlace/paquete | [link-wine-boot.py](tools/link-wine-boot.py), [build-wine-hardware.py](tools/build-wine-hardware.py), [SELF](tools/orbis_self.py), [empaquetado](tools/orbis_package.py) | `build/wine-boot/link-report.json`, app/runtime por build y manifiesto del paquete |

Pasos típicos en un **workspace configurado**, no una receta completa desde cero:

```sh
python3 tools/build.py --with-wine-platform
python3 tools/build-wine-ps4.py --boot --all-unix
python3 tools/build-wine-ps4.py --boot --server
# Recompilar aquí los módulos CPU/invitados/UI/gráficos/servicios afectados y sus cierres.
# El mundo WoW64 y los reemplazos para hardware dependen de las recetas base anteriores.
python3 tools/link-wine-boot.py
python3 tools/build-wine-hardware.py
```

Antes de los dos últimos comandos revisar cada manifiesto que consumen. El paquete moderno tiene muchas más entradas que la secuencia antigua del incremento 24. Recompilar consumidores después de cambiar sus entradas; nunca arreglar un manifiesto obsoleto editando sus hashes.

Orden del prefijo: configurar/compilar Wine anfitrión y su cierre PE/Unix, ejecutar [prepare-host-prefix.py](tools/prepare-host-prefix.py) y empaquetar esa corrida exitosa con [package-wine-prefix.py](tools/package-wine-prefix.py). Ver [incremento 15](docs/INCREMENT_15-es.md) e [integración del preflight](docs/INCREMENT_19-es.md). Un prefijo válido no demuestra que arrancó Wine; no distribuir `wow64cpu.dll` del host como proveedor PS4.

Quedan huecos para un clon limpio: rutas absolutas gráficas, configuración anfitriona e informes generados usados como entradas. Recrear informes faltantes con sus productores. Un clon que no los tenga debe fallar visiblemente y no consumir referencias inventadas. Ver [límites de reconstrucción](docs/REPOSITORY_LAYOUT-es.md). Preparar este repositorio Git no ejecutó una build limpia completa.

## 6. Compilar y ejecutar shadPS4

Con compilador/CMake/submódulos fijados disponibles:

```sh
python3 tools/build-shad-linux.py --jobs 12
# Sólo cuando ya existe una configuración CMake coincidente:
python3 tools/build-shad-linux.py --reuse-configure --jobs 12
python3 tools/build-shad-platform-check.py
```

El builder Linux requiere `.deps/linux-tools/cmake/data/bin/cmake`, Clang 19 y libc++. Escribe `build/shadPS4-linux/build-manifest.json`, con hash del binario, HEAD, hash del diff y submódulos. La caché de fuentes requiere además [cache-shad-source.py](tools/cache-shad-source.py) y un manifiesto coincidente; no activarla sobre fuentes cambiadas.

```sh
# Escritorio visible en WSLg desde una build de hardware existente.
# W284 es un ejemplo histórico documentado, no un selector de "última versión".
python3 tools/run-orbisdesk-shad.py --build W284

# Runner general del fork; montar una copia privada del runtime como /data.
python3 tools/run-linux-shad.py --fork --config-clean --fullscreen false --mount /tmp/orbisdesk-test-data /data -g build/shad-platform-check/app/eboot.bin
```

[run-orbisdesk-shad.py](tools/run-orbisdesk-shad.py) verifica hashes ELF/emulador, copia el runtime de forma privada, inicia un proceso persistente y registra PID/directorio en `build/orbisdesk-shad-visible.json`. Eso no es un resultado de prueba con timeout. `--fresh` crea otra copia y puede volver a exponer límites de arranque/native32 ocultos por una copia inicializada. Leer primero [evidencia y límites del escritorio](docs/SHAD_W284_DESKTOP-es.md) y [barra/menús](docs/TASKBAR_CENTER_FIX-es.md).

[run-linux-shad.py](tools/run-linux-shad.py) selecciona el fork sólo con `--fork`. Sin él usa el release oficial Linux con glibc privada. Fuerza Lavapipe en el anfitrión: ver el escritorio no valida la ruta RADV/GNM de consola ni su rendimiento.

El [builder Windows](tools/build-shad.ps1) y el [runner Windows de arranque](tools/run-wine-boot.ps1) conservan condiciones históricas más estrictas sobre HEAD limpio. No reemplazan directamente al fork Linux con overlay 0018. [run-wine-hardware.py](tools/run-wine-hardware.py) está fijado a W011: no usarlo para afirmar que pasó una build nueva.

## 7. Pruebas y matriz local

Elegir pruebas enfocadas en la capa modificada. Ampliar la matriz para cambios centrales de cargador/VM/ABI o una campaña de regresión solicitada. Respetar cuando el usuario pide omitir la matriz local y validar en hardware, aclarando qué se omitió. Un cambio sólo documental no requiere recompilar Wine ni correr juegos.

```sh
# Comprobaciones sin consola ni paquete compilado.
python3 tools/check-repository-layout.py
python3 tools/check-docs-bilingual.py
python3 tests/test_project_brand.py

# Algoritmos anfitriones: requieren fuentes fijadas, compilador y fixtures según el caso.
bash tools/test-vm.sh
bash tools/test-pe32.sh
python3 tools/check-wine-fs.py

# Casos de plataforma mediante el ELF de diagnóstico y el fork Linux.
python3 tools/run-linux-wine.py --fork --baseline --case files
python3 tools/run-linux-wine.py --fork --baseline --case vm-stress

# Campaña histórica del incremento 18, con referencias Windows generadas disponibles.
python3 tools/check-increment18.py --report-dir reports/increment18-new-run
python3 tools/check-increment18.py --verify-only --report-dir reports/increment18-new-run
```

La campaña del incremento 18 contiene 31 ejecuciones con resultados esperados, incluido un bloqueo del emulador oficial. Sus expectativas corresponden a ese diagnóstico, no a todos los invitados modernos. Los [checkers anteriores](tools/check-increment11.py) esperan bloqueos antiguos deliberadamente: ejecutar todos los históricos sobre fuentes actuales no forma una suite universal. `--verify-only` verifica evidencia guardada; no ejecuta pruebas nuevas. Los informes y las referencias Windows están ignorados y pueden faltar en un clon nuevo.

[Matriz de plataforma PowerShell](tools/run-probes.ps1), después de compilar ELF/fixtures:

```powershell
./tools/run-probes.ps1 -Cases files,low-memory,generated-code
# Omitir -Cases para solicitar toda su matriz de plataforma por defecto.
./tools/run-probes.ps1
./tests/report-classification.ps1
```

Por defecto usa el **emulador oficial Windows**, no el fork Linux. Para un fork Windows indicar `-Emulator`, `-EmulatorKind fork`, el `-EmulatorCommit` completo real y su `-BuildManifest`; no pasar el ejecutable Linux a este runner Windows. `-IncludeWine` y `-IncludeWinePlatform` requieren además los manifiestos de fixtures Wine correspondientes.

Para prefijo/arranque usar [run-linux-wine.py](tools/run-linux-wine.py) (`--prepared-prefix`, `--prefix-preflight`, `--wow64-cpu wowprospero`, argumentos GUI/EXE opcionales) y las recetas exactas de los incrementos [19](docs/INCREMENT_19-es.md), [23](docs/INCREMENT_23-es.md), [24](docs/INCREMENT_24-es.md), [25](docs/INCREMENT_25-es.md). No confundir preflight, diagnóstico de servicios/servidor y escritorio empaquetado moderno como si probaran la misma ruta.

## 8. Qué demuestra cada evidencia

Registrar revisión/diff, hashes de entradas y ejecutables, tipo/configuración del emulador, duración, salida/timeout, archivos producidos y rutas de logs. Separar corridas nuevas; no sobrescribir evidencia antigua ni modificar hashes para aprobar una prueba.

| Observación | Qué permite afirmar |
| --- | --- |
| Fixture coincide en Windows/Wine Linux nativos | Comportamiento de referencia; no validación PS4 |
| Preflight de prefijo correcto | Paquete/mapeos/arquitecturas verificados; no arranque Wine |
| Marcador del servidor o ntdll | Se alcanzó esa etapa; no ejecución del EXE |
| Salida esperada y terminación verificada del EXE previsto | Ejecución en esa configuración exacta |
| Cuadro de escritorio / estado `presented` | Presentación, no aceptación general de aplicaciones |
| Abre un menú o suena audio | Esa interacción; comprobar también cierre y respuesta de UI |
| Pasa en el fork | Resultado del fork; separar oficial y hardware |
| Aparece un log viejo tras subir una build | Evidencia vieja hasta correlacionar marcador/manifiesto |

`CE-34878-0` es un síntoma, no un diagnóstico. Empezar por el último marcador, excepción/registros, cierre del hilo/invitado y fuentes coincidentes. No atribuir un fallo concreto sólo por una captura. Crear reproducciones nativas mínimas al decidir si el problema está en Wine, el adaptador SDK, los invitados o el emulador.

## 9. Despliegue y feedback en PS4 física

La consola disponible fue informada como PS4 Pro Baikal, firmware 12.52 y GoldHEN. Describe una instalación del usuario, no una matriz de compatibilidad. FTP usa 2121. Usar siempre la IP actual indicada por el usuario: los defaults todavía incluyen `.107`, mientras entregas recientes usaron `.100`.

1. Compilar e inspeccionar `out/wine-hardware-wNNN/manifest.json`: paquete, ELF, raíz del runtime y hashes de fuentes. Verificar que los scripts de transferencia/recolección reconozcan esa build: mantienen listas explícitas.
2. Con autorización de transferencia, subir paquete **y runtime requerido**, no sólo PKG. Las rutas habituales incluyen `/data/pkg/OrbisDesk.pkg`, `/data/wine-prefix`, `/data/wine-home` y `/data/wine`. No inventar otro montaje a partir de una captura histórica.
3. El usuario cierra la app, instala desde la consola y la inicia manualmente o con su flujo de Remote Play. Subir por FTP no instala ni ejecuta. El usuario elige NORMAL/ROOT.
4. Dar una secuencia corta y, si el chat lo permite, un botón «Ya la probé». Descargar logs cuando el usuario avise que terminó; no sustituir ese feedback por sondeos repetidos del título abierto.
5. Comprobar el marcador de build y la corrida antes de interpretar. Si es la build anterior, informarlo y resolver instalación; no atribuir sus logs a la nueva.

Ejemplo **reemplazando W287/IP por la build y consola previstas**:

```sh
python3 tools/upload-hardware.py --build W287 --host 192.168.68.100 --port 2121
# Después de que el usuario termine la prueba:
python3 tools/fetch-hardware.py --build W287 --host 192.168.68.100 --port 2121
```

[upload-hardware.py](tools/upload-hardware.py) verifica leyendo de vuelta cada archivo, preserva ajustes seleccionados de la consola y retira paquetes anteriores reconocidos sólo después de verificar toda la transferencia. `--keep-old-packages` los conserva; `--skip-runtime` sólo corresponde si el runtime completo requerido ya existe y está verificado. Preservar documentos, juegos, elecciones de registro y partidas del usuario.

[fetch-hardware.py](tools/fetch-hardware.py) archiva en `reports/wine-hardware-wNNN/physical/<UTC>/`, con clasificación, logs, hashes y conversión de cuadros disponible. [watch-hardware-run.py](tools/watch-hardware-run.py) es un observador opcional de larga duración para un programa solicitado; no es el feedback por defecto y una sesión de escritorio puede no terminar.

Secuencia física enfocada para UI/ciclo de vida: abrir la app afectada, interactuar, cerrarla y volver a Start; para cierre gráfico compartido, repetir dos ciclos con vkcube, glxgears y vkspin, cerrando vkcube primero. Añadir operaciones de archivos/directorios WFM o audio cuando cambien esas rutas. Capturar pantalla real y logs correspondientes. No inventar/retocar una captura como evidencia. Comprobar respuesta después de reproducir audio/renderizar, no sólo el primer sonido/cuadro.

## 10. Dónde investigar

| Tema | Navegación principal |
| --- | --- |
| Checks de PR, medición manual de matriz, gates de main y distribuciones | [Plan de implementación de CI](docs/CI_PLAN-es.md) |
| Ejecutar el workflow manual, interpretar tiempos y reproducir diagnósticos | [Operación de CI](docs/CI-es.md) |
| Recuperación de fuentes y límites de build limpia | [Estructura](docs/REPOSITORY_LAYOUT-es.md), [lock](dependencies.lock.json), [restaurador](tools/restore-dependencies.py) |
| Invitados, mundo PE32, base fija y estado compartido | [Investigación y resultados WoW64](docs/investigacion-wow64-en-explorer-es.md), [base fija](docs/investigacion-gta-vc-base-0x400000-es.md) |
| ABI nativa, memoria, TLS, señales, IPC y servicios del emulador | [Incrementos 01–25 en el índice](docs/INDEX-es.md), [adaptadores PS4](platform/ps4/), [reproducción de plataforma](native/shad_platform_check.c) |
| Gráficos, cierre MangoHud y métricas | [Historia gráfica](docs/HARDWARE_G001-es.md), [W098](docs/HARDWARE_W098-es.md), [W102](docs/HARDWARE_W102-es.md), [W104](docs/HARDWARE_W104-es.md), [recetas](tools/vk-h0/) |
| Apertura WFM, asociaciones y borrado recursivo | [W105](docs/HARDWARE_W105-es.md), [W106](docs/HARDWARE_W106-es.md), [W107](docs/HARDWARE_W107-es.md), [W111](docs/HARDWARE_W111-es.md), [operaciones WFM](tools/wfm-operations.h) |
| Mando/USB | [HID](docs/HARDWARE_mando-hid-es.md), [análisis de juegos](docs/HARDWARE_mando-juegos-analisis-es.md), [builder XInput](tools/build-xinput-hw.py), [builder DirectInput](tools/build-dinput-hw.py) |
| Fuentes, glifos, barra, Start y temas | [Texto](docs/INCREMENT_25-es.md), [atribuciones de fuentes](docs/THIRD_PARTY_FONTS-es.md), [barra/menús](docs/TASKBAR_CENTER_FIX-es.md), [Explorer](tools/build-explorer-hw.py) |
| DOS y motores incluidos | [Runtime DOS](docs/HARDWARE_W112-es.md), [juegos](docs/GAMES-es.md), [pins DOS](dos.lock.json), [pins de juegos](games.lock.json) |
| Fases del cliente nativo Steam | [S1](docs/STEAM_S1-es.md), [S2](docs/STEAM_S2-es.md), [S3](docs/STEAM_S3-es.md), [código nativo](native/steam/) |
| Atribuciones, documentos públicos/privados y marca | [Terceros](THIRD_PARTY-es.md), [política documental](docs/DOCUMENTATION_POLICY-es.md), [marca](docs/REBRANDING_ORBISDESK-es.md) |

Que los contadores CPU/GPU respondan no equivale a una calibración absoluta independiente. Que un juego arranque no prueba cierre seguro, concurrencia, aislamiento ni compatibilidad general. Mantener esos límites al comunicar avances.

## 11. Cierre de tarea para una IA

- Explicar qué cambió, por qué, qué se probó realmente y qué sigue pendiente. Responder de forma concisa enlazando artefactos/logs/documentos relevantes.
- Actualizar ambos idiomas y regenerar el [índice](tools/build-doc-index.py) cuando se agregan/mueven documentos públicos. Los checks validan navegación, no exactitud de traducción.
- En código, conservar transformaciones canónicas, comprobaciones de contexto y atribuciones. En evidencia, preservar identidad de fuentes/binarios y clasificaciones separadas oficial/fork/hardware.
- Antes de comitear, ejecutar checks de estructura e idiomas, revisar `git diff --check`, rutas staged, contenido ignorado/privado y gitlinks, y comprobar cambios concurrentes. Comitear/pushear según autorización del usuario; usar SSH cuando se solicita y no forzar sobre historial remoto inesperado.
- No pedir prueba física antes de que la build solicitada esté realmente compilada y transferida. No afirmar una transferencia, captura, salida de proceso o instalación que no se observó.
