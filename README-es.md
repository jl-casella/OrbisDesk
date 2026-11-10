# OrbisDesk

[English](README.md) | [Español](README-es.md)

Documentación: [política de idiomas](docs/DOCUMENTATION_POLICY-es.md).

Preparación de Git: [dependencias y reconstrucción](docs/REPOSITORY_LAYOUT-es.md).

Empezar con IA: [guía de trabajo](AGENTS-es.md) e [índice completo](docs/INDEX-es.md).

Escritorio y aplicaciones Windows para PS4, basado en Wine, WoW64 y gráficos nativos. Desde W283, la interfaz, los paquetes y el código propio usan OrbisDesk. Ver [cambio de nombre y compatibilidad](docs/REBRANDING_ORBISDESK-es.md).


**Estado actual, 2026-11-10:** la base del producto es **W303 / 04.02**, con el runtime integrado en `OrbisDesk.pkg` y validación de instalaciones limpias en consola. La construcción completa del producto en GitHub ya pasa; CI asigna su propia versión SFO a cada candidato. La versión visible queda en el selector NORMAL/ROOT. Ver [estado actual](docs/CURRENT_STATE-es.md) y [builds, instalación y releases](docs/RELEASES-es.md). Los estados de builds anteriores conservados más abajo son históricos.

Base experimental para portar prospero-win a PS4 y medir sus requisitos en shadPS4. **Ya ejecuta un EXE PE32 que llama a una DLL propia por su IAT en el fork local de shadPS4**, con retorno 42 y relocaciones verificadas. El ELF incorpora el traductor x86 real de prospero-win y adaptadores de memoria, TLS y proceso para PS4. Se compilan DLL PE32 reales de Wine. En el fork Linux, Wine arranca dentro del proceso y ejecuta console32-bare.exe con el traductor como proveedor WoW64 (incremento 23); el oficial sigue bloqueado en esa campaña histórica. Ya hay validación posterior en PS4 real, detallada a continuación.

## Estado verificado

Hito histórico W112: [W112](docs/HARDWARE_W112-es.md) introdujo el runtime DOSBox Pure PE64 para juegos DOS desde WFM. En esa etapa estaba compilado y su validación física seguía pendiente. El núcleo, frontend, puente AudioOut y fuentes viajan con la distribución, sin juegos. Para retomar hoy, usar los enlaces al estado actual de arriba.

W105 lista unidades y archivos en WFM. Corrección anterior: [W111](docs/HARDWARE_W111-es.md), filtrar registros BSD de entradas borradas que producen nombres residuales y error 145 al comprobar carpetas vacías. En PS4 ya se verificaron rmdir real, carpeta ausente y renombrado con espacios. El usuario confirmó también el borrado completo del árbol con contenido activo. W106 abre EXE y W107 ya abrió textos con Notepad en PS4. Calibración independiente CPU/GPU aplazada por el usuario.

Actualización de contexto, 2026-11-02: **Wine ya ejecuta el EXE PE32 bare en la PS4 real mediante wowprospero**, con resultado idéntico a Windows y salida 0. También funcionan el escritorio, entrada de mando y USB, aplicaciones PE64 y gráficos Vulkan/OpenGL mediante RADV y Zink. W094 muestra MangoHud sobre Vulkan sin la aserción de W093. Ver [estado actual y punto de retoma](docs/CURRENT_STATE-es.md), [hardware Wine](docs/HARDWARE_W003_W011-es.md) y [gráficos](docs/HARDWARE_G001-es.md).

W095 tiene evidencia física de ejecución y fallos al combinar aplicaciones gráficas. [W096](docs/HARDWARE_W096-es.md) permitió ejecutarlas juntas en la PS4, pero hubo fallos después del cierre. [W098](docs/HARDWARE_W098-es.md) capturó un corte durante limpieza de un worker al cerrar vkcube; [W099](docs/HARDWARE_W099-es.md) corrige la dependencia de espera de MangoHud y permite cierres y recargas. Tras otro ciclo aparece un fallo en malloc nativo; [W100](docs/HARDWARE_W100-es.md) añade sincronización al asignador del SDK, pero el fallo persiste en su prueba. [W101](docs/HARDWARE_W101-es.md) completó dos ciclos sin cargar MangoHud. [W102](docs/HARDWARE_W102-es.md) reactiva la capa con muestreo en el frame, y completó dos ciclos en PS4 con seis cierres 0, Start operativo y salida final 0. [W103](docs/HARDWARE_W103-es.md) registró GPU variable sin pérdidas y tres cierres 0, pero CPU quedó fija. [W104](docs/HARDWARE_W104-es.md) usa contabilidad CPU del proceso y simplifica las etiquetas a CPU/GPU. En PS4 ambas responden a carga, sin errores de contadores ni pérdidas GPU; tres cierres 0. Las secciones de incrementos siguientes describen campañas históricas y sus límites de entonces.

El incremento 25 añade **texto real mediante FreeType para Orbis** en el fork Linux. El fixture PE64 dibuja texto, números, acentos y eñe, con lectura de píxeles y comprobación del cuadro presentado, en tres de tres corridas. `explorer.exe /desktop` muestra la etiqueta **Start** usando fuentes de Wine registradas en el prefijo privado. Se corrigió además la protección de la última página parcial de DLL para respetar los 16 KiB de Orbis. La campaña final y las regresiones pasan; no se agregaron parches a shadPS4. Ver [incremento 25](docs/INCREMENT_25-es.md) e [informe de aceptación](reports/increment25-accepted/report.json). En esa campaña, la entrada y la validación en PS4 real seguían pendientes; las pruebas posteriores de hardware se enlazan arriba.

El incremento 24 pone **UI de Wine en pantalla** en el fork Linux. `win32u` corre con un driver de usuario dentro del proceso (adaptado de prospero-win) que compone las ventanas y las presenta por `sceVideoOut`:

- un fixture GUI de 64 bits pinta su ventana y da el mismo `result.txt` que Windows nativo;
- `explorer.exe /desktop` muestra el escritorio de Wine con su barra de tareas.

Esa evidencia inicial no incluía texto ni entrada. Ver [incremento 24 y evidencia](docs/INCREMENT_24-es.md). Hardware: pendiente.

El incremento 23 ejecuta **console32-bare.exe mediante Wine en el fork Linux**. Wine carga sus módulos reales (ntdll de 64 y 32 bits, kernelbase, kernel32) y el código de 32 bits corre sobre el traductor de prospero-win, adaptado como proveedor WoW64 (`wowprospero`). El EXE crea su hilo, carga su DLL y escribe un `result.txt` idéntico al de Windows nativo, con salida 0, en tres corridas y sin stubs. En shadPS4 oficial sigue bloqueado. `console32.exe` con CRT todavía no se probó mediante Wine. Hardware: pendiente. Ver [incremento 23 y evidencia](docs/INCREMENT_23-es.md).

El incremento 22 libera GS en el fork Linux: el TCB del invitado ya no usa la base GS y `sysarch` instala y verifica el GS de cada hilo. Los handlers de señal reciben un contexto completo y las señales se traducen entre musl y el ABI FreeBSD. Con eso y dos correcciones del overlay (reubicación de imágenes de 64 bits y USD sin wineboot), Wine ejecuta el ntdll PE de 64 bits, crea el heap y carga `wow64.dll`. Se detiene limpio con `0xc0000135`: falta el proveedor de CPU WoW64. **El EXE todavía no corre mediante Wine.** Ver [incremento 22 y evidencia](docs/INCREMENT_22-es.md).

El incremento 21 corrige los mappings privados de archivos en el fork Linux y devuelve EACCES para cambios de protección incompatibles. Wine completa la carga y reubicación de ntdll PE64 y llega a la fase de inicialización Windows. Aparece después el bloqueo de GS mediante `sysarch`, ya sin aserciones ni timeout. También queda adaptado el slot de syscalls a páginas de 16 KiB. El EXE todavía no corre mediante Wine. Ver [incremento 21 y evidencia](docs/INCREMENT_21-es.md).

El incremento 20 corrige el error de offset de `mmap` en el fork y verifica el fallback de lectura de Wine. La imagen PE32 se mapea reubicada y Wine continúa hacia ntdll PE64 con la política WoW64 explícita. El siguiente bloqueo es una aserción de `mprotect` durante la reubicación de ntdll, reproducida sin Wine. **El EXE todavía no corre mediante Wine.** Ver [incremento 20, pruebas y prioridades siguientes](docs/INCREMENT_20-es.md).

El incremento 19 monta y verifica el prefijo externo en el fork Linux. Pasan doce comprobaciones dentro del invitado y Wine consume el prefijo sin lanzar wineboot. El siguiente bloqueo es un `mmap` de archivo con offset `0xc00` que hace caer al emulador en una aserción, antes de completar la carga de ntdll PE64. **El EXE todavía no corre mediante Wine.** Ver [incremento 19, reproducción mínima y siguientes pasos](docs/INCREMENT_19-es.md).

El incremento 18 ejecuta **console32.exe con el CRT de mingw, sin Wine**, en el fork Linux. Corre sobre un msvcrt mínimo propio con heap invitado, TLS del EXE, critical sections y `FNINIT` en el fallback de la CPU. `result.txt` coincide con Windows nativo y la salida es 0. El oficial sigue bloqueado por el emulador. Ver [incremento 18 y evidencia](docs/INCREMENT_18-es.md). Hardware: pendiente.

El incremento 17 carga **DLL desde disco sin Wine**. En el fork Linux, lifecycle-host.exe carga `lifecycle.dll` con `DllMain`, TLS y notificaciones de hilo, la descarga y recibe `ERROR_DLL_INIT_FAILED` de una DLL que rechaza su attach. Sale con 42, igual que en Windows nativo. El oficial sigue bloqueado por el emulador. Ver [incremento 17 y evidencia](docs/INCREMENT_17-es.md). Hardware: pendiente.

El incremento 16 ejecuta **console32-bare.exe sin Wine** en el fork Linux. Usa el loader PE32 propio y un kernel32 mínimo (`pw_k32_ps4.c`) cuyos thunks salen del traductor al host. `result.txt` coincide byte a byte con la referencia de Windows y la salida es 0, sin stubs. En shadPS4 oficial el invitado no llega a un cierre limpio: en Linux cae en la aserción de salida y en Windows al publicar código RX. Ver [incremento 16 y evidencia](docs/INCREMENT_16-es.md). Hardware: pendiente.

El incremento 15 conserva la identidad de archivos y expone symlinks en el fork. Además produce un prefijo inicializado por `wineboot --init` donde console32-bare.exe corre, pero **sólo con Wine nativo en Linux**. En shadPS4 el EXE todavía no corre: falta montar ese prefijo y definir su política de arranque. Ver [incremento 15 y evidencia](docs/INCREMENT_15-es.md).

El incremento 14 adapta directorios y rutas relativas en el runtime PS4. Wine conserva `server_ready` y registra que solicita `wineboot.exe`; esa creación de proceso se rechaza explícitamente. **El EXE todavía no corre mediante Wine**: falta un prefijo externo validado y su política de arranque. Ver [incremento 14 y evidencia](docs/INCREMENT_14-es.md).

El incremento 13 añade pipes reales en Linux y readv/writev para pipes y sockets. Wine completa la inicialización con wineserver y alcanza `server_ready`. **El EXE todavía no corre mediante Wine**: aparecen imports pendientes después del handshake. Ver [incremento 13 y pruebas](docs/INCREMENT_13-es.md).

El incremento 12 implementa transferencia SCM_RIGHTS de archivos y sockets en pares locales del fork Linux. Wine supera ese bloqueo y encuentra `pipe`, que ahora falla explícitamente. **El EXE todavía no corre mediante Wine.** Ver [incremento 12 y pruebas](docs/INCREMENT_12-es.md).

El incremento 11 añade descriptores compartidos y flags, mensajes con varios buffers y pruebas de IPC en el fork Linux. Wine se detiene con un error explícito al intentar transferir descriptores al servidor (`SCM_RIGHTS` pendiente). El EXE de referencia funciona en Windows; **todavía no se ejecuta mediante Wine**. Ver [incremento 11 y requisitos pendientes](docs/INCREMENT_11-es.md).

El incremento 10 compila y enlaza ntdll Unix completo y wineserver en proceso. En shadPS4 oficial Linux alcanza las rutas, NLS y reserva del primer TEB; se bloquea durante la inicialización del servidor por servicios pendientes del emulador. Incluye reproducción mínima de `dup`, `fcntl`, `fstatfs`, GS y poll. **Todavía no ejecuta un EXE mediante Wine.** Ver [incremento 10](docs/INCREMENT_10-es.md).

El incremento 9 validó **51 de 58 diagnósticos en el fork local de shadPS4**, con siete bloqueos y ninguna falla. Compilan cinco unidades Unix de Wine con adaptaciones PS4 de memoria, rutas y archivos. El ELF prueba funciones reales de ese código, incluida ejecución RW→RX con resultado 42, y corrige el ABI stat y la selección de lstat del SDK. Wine completo todavía no arranca. Ver [evidencia, límites y próximos pasos](docs/INCREMENT_09-es.md).

La referencia inicial se conserva a continuación:

En shadPS4 oficial v0.20.0 para Windows, ocho pruebas de plataforma pasan y cuatro quedan bloqueadas. El traductor ejecuta instrucciones PE32/x86 de prueba desde memoria RWX y obtiene `EAX=42`, `EIP=0x1008`. Esta prueba usa bytes de instrucciones; no carga un PE ni demuestra ejecución de aplicaciones Win32 completas.

El avance posterior del backend, las pruebas ampliadas y el fork local se describen en [Incremento 1](docs/INCREMENT_01-es.md). Los conteos de esta sección corresponden a la referencia inicial preservada, no a la matriz ampliada.

- Funcionan archivos, reserva de direcciones bajo 4 GiB, rechazo de colisiones, el backend `PwVmBackend` para PS4, memoria RWX, hilos con el adaptador de TLS, destructores de TLS y recuperación de una excepción de acceso.
- La transición RW→RX aborta dentro de shadPS4 en Windows. RWX inicial sí funciona.
- `sysarch` y la importación POSIX de `pthread_key_delete` desde libkernel son stubs. El segundo se resuelve usando `scePthreadKeyDelete`; FS/GS sigue bloqueado.
- El `exit(0)` del invitado también provoca una aserción del emulador. Los informes separan el resultado de la prueba de ese fallo de cierre.

Ver [resultados y bloqueos](docs/STATUS-es.md) y el informe preservado en `reports/baseline/report.json`. Ningún resultado está validado en hardware PS4.

## Preparar y compilar

En PowerShell, desde la raíz:

```powershell
./tools/bootstrap.ps1 -InstallBuildTools
wsl -d Ubuntu-22.04
```

En WSL, entrar a este directorio y ejecutar:

```bash
python3 tools/fetch_sources.py
python3 tools/build.py
```

`fetch_sources.py` utiliza exclusivamente `sources.lock.json`; rehúsa sobrescribir checkouts de otra revisión. La fuente de Wine se fija al mismo commit que upstream. Descargarla no implica que se haya construido su port PS4.

`build.py` verifica las fuentes, compila para `x86_64-pc-freebsd12-elf` y Jaguar, genera el OELF y `eboot.bin`, y construye los EXE i386 `console32.exe` y `gdi32.exe`. También comprueba sus arquitecturas y rechaza segmentos PT_LOAD duplicados. El manifiesto `out/build.json` registra herramientas, fuentes y hashes.

Para este hito de C se usa OpenOrbis oficial v0.5.4 y Clang 14 de Ubuntu 22.04. El sysroot C++/Clang 21 de DolphinPS4 y Mesa se reservan para el hito gráfico; todavía no se han construido ni validado. `--sdk`, `--cc` y `--ld` permiten indicar otro SDK/compilador al builder, que queda registrado en el manifiesto.

## Ejecutar los diagnósticos

En PowerShell:

```powershell
./tools/run-probes.ps1
./tools/run-probes.ps1 -Cases translator-rwx,vm-backend,threads-adapter
./tests/report-classification.ps1
```

Cada caso arranca un proceso nuevo con perfil y `/data` aislados. Los informes quedan en `reports/runs/<fecha UTC>/report.json`, junto con stdout, stderr y los logs del emulador. Una matriz con pruebas bloqueadas devuelve código 1.

Para un emulador modificado usar `-Emulator <ruta> -EmulatorKind fork -EmulatorCommit <SHA completo>`. El binario oficial se identifica por hash; un fork nunca se etiqueta como oficial. El fork local posterior se prepara y compila con `tools/prepare-shad-fork.ps1` y `tools/build-shad.ps1`.

El runner requiere un inicio y un resultado del invitado, detecta llamadas a stubs y trata timeouts/crashes como bloqueos. Una respuesta simulada de shadPS4 no convierte una prueba en aprobada. Las advertencias sobre imports sin uso se conservan en los logs y se distinguen de stubs efectivamente invocados.

## Organización

- `platform/ps4/`: adaptadores nuevos que consumen la interfaz original de prospero-win.
- `native/`: diagnóstico OpenOrbis, con un caso por ejecución.
- `fixtures/win32/`: programas propios PE32 para los futuros hitos Wine/GDI.
- `tools/`: fuentes fijadas, descargas verificadas, build y captura de evidencia.
- `upstream/`, `.deps/`, `build/`, `out/`: fuentes y artefactos locales regenerables.

Los EXE propios son objetivos de aceptación futuros, no demos declaradas como funcionales en el runtime. El programa de consola prueba cálculo, hilos, carga de DLL y escritura de archivo; el de GDI cambia de color al recibir entrada.

## Continuación

Dos pistas en paralelo:

1. Sin Wine: los incrementos [16](docs/INCREMENT_16-es.md) a [18](docs/INCREMENT_18-es.md) ya ejecutan console32-bare.exe, lifecycle-host.exe y console32.exe con CRT. Sus piezas (traductor como CPU de 32 bits, thunks, callbacks anidados, TEB/TLS) son las que necesita el proveedor WoW64 de la pista Wine.
2. Wine: desde el incremento [23](docs/INCREMENT_23-es.md), console32-bare.exe corre mediante Wine en el fork Linux, con el traductor como proveedor WoW64. Siguen console32.exe con CRT, excepciones de 32 bits y código automodificable.

Sin hardware disponible, los supuestos de RWX/JIT y `sysarch` siguen sin validar en consola real.

GDI/VideoOut, Pad, AudioOut, RADV/Vulkan y DXVK permanecen pendientes del arranque Win32. No hay PKG publicable ni mediciones de FPS en consola.

## Licencia

El paquete de OrbisDesk (`OrbisDesk.pkg` y su ELF) se distribuye bajo la **GNU General Public License v3.0 o posterior**. Incluye el cliente nativo de Steam, que reutiliza código de [Playden for PS5](https://github.com/leolobato/playden-ps5) (GPL-3.0-or-later). Por eso la obra combinada es GPL-3.0-or-later.

Cada archivo fuente mantiene la licencia indicada en su cabecera:
- adaptadores, herramientas y fixtures propios: LGPL-2.1-or-later;
- diagnósticos de `native/`: GPL-2.0-or-later;
- Wine: LGPL-2.1-or-later.

Todas son compatibles con GPL-3.0-or-later. La emulación opcional de la API de Steam por juego usa las DLL de [gbe_fork](https://github.com/Detanup01/gbe_fork) sin modificar (LGPL-3.0).

Los textos de las licencias están en [LICENSES/](LICENSES). Los componentes, versiones y procedencia se detallan en [THIRD_PARTY.md](THIRD_PARTY-es.md).

El cliente de Steam no es oficial y Valve no lo respalda. Steam es marca de Valve Corporation.
