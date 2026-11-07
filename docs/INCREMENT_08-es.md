# Incremento 8: proceso PE32 y primer bring-up de Wine

[English](INCREMENT_08.md) | [Español](INCREMENT_08-es.md)

El contexto de proceso funciona en el fork fijado de shadPS4. Se compilaron las tres DLL PE32 reales de Wine y se probaron como entradas del cargador PS4. **Wine todavía no arranca ni ejecuta console32.exe.** El lado Unix tiene bloqueos de compilación reproducibles contra OpenOrbis.

## Resultado medido

| Entorno |Pasan| Bloqueados |Fallan| Casos |
|---|---:|---:|---:|---:|
| Fork c6de833f6bec304b6f08c37520428ba2ed147a1a | 48 | 7 | 0 | 55 |
| Oficial v0.20.0, mismo ELF y doce fixtures | 21 | 33 | 1 | 55 |

[Informe del fork](../reports/increment8-fork-final/report.json), [oficial](../reports/increment8-official-final/report.json) y [comparación](../reports/increment8-fork-final/comparison.json). Se mantienen los 49 resultados anteriores y se añaden tres pruebas de proceso que pasan en el fork y tres diagnósticos Wine bloqueados. La falla oficial conocida sigue siendo vm-enforcement. Ninguna ejecución alcanzó el timeout. No se modificó el fork de shadPS4 en este incremento. Hardware PS4: pendiente.

## Contexto de proceso

`pw_process_ps4` reserva un bloque de 16 KiB bajo 4 GiB con PEB32, parámetros normalizados, cadenas UTF-16, entorno vacío terminado dos veces, PEB_LDR_DATA y tres listas circulares de módulos. La lista de inicialización excluye el EXE. Los parámetros admiten texto ASCII que se convierte a UTF-16; otra codificación se rechaza explícitamente. No hay implementación de heap o handles Windows.

La asociación a un TEB privado publica FS:[0x30] y añade la memoria del proceso a las regiones del traductor. El contador de asociaciones impide destruir el proceso mientras un TEB lo usa. Unbind restaura el puntero anterior y elimina la región. El llamador conserva el proceso y los módulos mapeados y serializa sus operaciones. Los TEB del lifecycle ahora incluyen límites de pila y el sentinela de ExceptionList; esto no implementa SEH.

El EXE propio process32.exe comprueba desde x86 traducido PEB, TEB, imagen base, parámetros, Unicode, entorno y listas, y devuelve 42. Se valida en su dirección preferida, reubicado y con un intento de reserva superpuesta. También se rechazan asociación duplicada y destrucción con asociaciones activas. Cada caso termina con cero reservas vivas y sin stubs del emulador.

Dieciséis static_assert contra las cabeceras de la revisión real de Wine confirman los offsets usados. Es una comprobación de ABI mediante compilación i686, separada de la ejecución en shadPS4. Código y objeto de esa comprobación acompañan la [evidencia Wine](../reports/increment8-fork-final/wine/evidence.json).

## Wine compilado

Revisión: `490f6d5dcbb2a5047345b8af88d114bbcaad69a8`. Fuentes privadas y sin modificaciones en `.deps/wine/source`; no se altera `upstream/prospero-win`. La herramienta `tools/build-wine.py` adapta el constructor fijado de prospero-win: normaliza CRLF, corrige la localización de su validador, desactiva X/FreeType Linux y usa make incremental. Estas transformaciones y sus hashes quedan registrados. No se ejecutó una campaña de reproducibilidad de dos reconstrucciones: los hashes identifican esta compilación, sin afirmar que una toolchain distinta produzca bytes idénticos.

| DLL | Bytes del archivo | Secciones |Importaciones| Slots de export |Adelante.| Exports de datos |
|---|---:|---:|---:|---:|---:|---:|
| ntdll.dll | 3.711.290 | 18 | 0 | 1500 | 0 | 8 |
| kernelbase.dll | 4.888.849 | 18 | 428 | 1436 | 94 | 0 |
| kernel32.dll | 2.067.770 | 18 | 933 | 1532 | 250 | 0 |

Se incluyen 76 archivos NLS y un manifiesto de distribución verificado por el validador original. Distribución SHA256: `7fcf303f4c9a1325a10740d6e624ab01dd60ca08e1b1e15414565a949e9d3c60`. DLL y datos se conservan bajo `reports/increment8-fork-final/wine/out/wine/`.

Los tres casos wine-* verifican las identidades del manifiesto, montan las DLL exactas y las entregan al parser/cargador real dentro de shadPS4. Retornan PW_ERR_LIMIT (-7), registrado como bloqueado, sin inicializar ninguna DLL. El parser de diagnóstico admite 16 secciones, 64 exports, 64 imports y archivos de hasta 4 MiB. Las DLL exceden esos límites; también requieren características no implementadas, como exports de datos y forwarders. El inventario del host no altera esos límites ni sustituye la validación del parser.

Ese rechazo describe el cargador experimental. No demuestra que el cargador de Wine sea incapaz de manejar sus propias DLL: la ruta final debe incorporar su inicialización y sus servicios Unix. Aumentar constantes del parser actual no equivale a implementar esa ruta.

## Wine Unix: bloqueo real y reproducción

`tools/probe-wine-unix.py` configura Wine sin parches PS5 usando Clang para x86_64 FreeBSD, headers, CRT y bibliotecas OpenOrbis. C, C++ y CPP usan el mismo sysroot PS4; las herramientas winebuild/widl corren en el host. Configure pasa; la compilación de ntdll.so falla. Una pasada serial con `make -k -j1` recorre también wineserver y conserva los errores sin mezclar las salidas de compiladores.

Entre las incompatibilidades observadas están:

- cdrom.c: tipos/ioctls FreeBSD ausentes; env.c: TIOCGWINSZ.
- file.c: fstab.h; thread.c: sys/thr.h.
- signal_x86_64.c: machine/segments.h; no se llegó a validar el ABI de señales.
- virtual.c: MAP_EXCL, necesario revisar junto al backend de reserva sin reemplazo.
- system.c: sysctl y tipos/constantes FreeBSD, además de dev/acpica/acpiio.h.
- wineserver: supuestos de sockets/filtros y otras interfaces del host.

La lista exacta por archivo, los logs, config.h, comandos y hashes están en `reports/increment8-fork-final/wine/evidence.json`. No hay ntdll.so ni wineserver PS4 funcionales, prefijo preparado, puente WoW64↔Unix ni servidor en proceso. Los parches de PS5 no se aplicaron mecánicamente: sus supuestos ABI siguen requiriendo adaptación. No se añadieron definiciones de éxito para ocultar errores.

Desde Ubuntu 22.04/WSL, con `.deps/wine/source` en la revisión fijada:

```sh
python3 tools/build-wine.py --jobs 12
python3 tools/audit-wine.py
python3 tools/probe-wine-unix.py
```

El último comando devuelve error mientras ese port esté bloqueado. Para la pasada exhaustiva, desde `.deps/wine/ps4-unix`:

```sh
make -k -j1 dlls/ntdll/ntdll.so server/wineserver
```

Desde PowerShell, después de `tools/build.py` y la compilación PE de Wine:

```powershell
./tools/run-probes.ps1 -IncludeWine
./tools/run-probes.ps1 -IncludeWine -Emulator build/shadPS4-win/shadps4.exe -EmulatorKind fork -EmulatorCommit c6de833f6bec304b6f08c37520428ba2ed147a1a -BuildManifest build/shadPS4-win/build-manifest.json
```

El runner devuelve error si hay bloqueos o fallas; el JSON los distingue.

## Siguiente trabajo

Portar el lado Unix de ntdll por servicios: primero memoria y entorno/archivos, después hilos, contexto de señales y transición PE64↔Unix. Las funciones fuera del alcance pueden devolver un error real de no soportado cuando corresponda; los servicios imprescindibles deben funcionar para continuar el arranque. Comparar las adaptaciones pertinentes de prospero-win y el runtime PS4 de Dolphin/Resonance antes de incorporar código con sus atribuciones.

Después, integrar el servidor dentro del proceso, preparar el prefijo fuera de PS4 y conectar Wine WoW64 al traductor. La aceptación sigue siendo console32.exe con archivo, hilo, carga de DLL y salida comprobados. Los contextos de este incremento son una base verificada; no reemplazan la inicialización de Wine. GDI, audio, entrada y DXVK continúan después de ese arranque.
