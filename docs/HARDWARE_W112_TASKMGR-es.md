<a id="w112-task-manager-performance-processes-y-end-task"></a>


# W112: Administrador de tareas (Performance, Processes y End task)

[English](HARDWARE_W112_TASKMGR.md) | [Español](HARDWARE_W112_TASKMGR-es.md)

Estado: empaquetado en W112 (APP_VER 02.11, junto con el runtime DOS ya sincronizado) y subido con lectura de vuelta verificada: `/data/pkg/orbis-win-W112-a81c9325bbaf.pkg` (SHA-256 a81c9325bbaf8a1f4863dbe4010966bb8baae1f9638bcf673a485b748cfc8942). Informe: reports/wine-hardware-w112/transfers/20261102T192004Z.json; 553 archivos, 549 presentes y 4 subidos, sin fallos de permisos. Se borró por FTP el PKG W112 anterior (b6809b7be979, subido a las 18:45Z sin este arreglo): su ELF ya no coincidía con el runtime de /data. Prueba física pendiente.

## Síntomas informados

- Performance: CPU y memoria en 0, gráficos sin avanzar.
- Processes: vacío.
- Applications lista bien, pero tras End task la ventana se cierra y la fila queda.

## Causas (código)

1. `PerfDataRefresh` (programs/taskmgr/perfdata.c) consulta, en orden, TimeOfDay, Performance, FileCache y ProcessorPerformance, y hace `return` ante cualquier fallo, antes de guardar memoria, tiempos y lista de procesos. En ORBIS, `SystemProcessorPerformanceInformation` devolvía `STATUS_NOT_SUPPORTED` (ntdll/unix/system.c), así que cada refresco moría ahí: todo en 0 y Processes vacío. Además `IdleTime` quedaba en 0; con la consulta 8 resuelta, la CPU habría quedado en 100 % fija.
2. La pasada que quita filas muertas de Applications sólo corría dentro de `AddOrUpdateHwnd`, es decir, cuando se enumeraba otra ventana elegible. Al cerrar la única aplicación no había ninguna y la fila quedaba. La misma pasada miraba el estilo de la ventana enumerada (`hWnd`) en vez del de la fila (`pAPLI->hWnd`).

## Cambios

- `native/telemetry.c`: `pw_ps4_cpu_times` (reloj del título, getrusage SELF, capacidad de la afinidad inicial), las mismas fuentes que el HUD de W104. Devuelve errno negativo si falta un dato; no rellena con ceros.
- `tools/build-telemetry-ps4.py`: en la copia de system.c, la clase 8 en ORBIS llena una entrada por procesador con `idle = wall − busy/capacidad`, `User = (busy−sys)/capacidad`, `Kernel = idle + sys/capacidad`; `IdleTime` de la clase 2 es la suma. El porcentaje de Task Manager queda `busy/(capacidad·wall)`, el mismo valor que el HUD. Si falla, la clase 8 devuelve `STATUS_NOT_SUPPORTED` con `ERR PWTASK`; nada se simula.
- `tools/build-taskmgr-hw.py` (nuevo, mismo método que build-explorer-hw.py): `ApplicationPageRemoveDead()` corre después de cada `EnumWindows`; se corrige `pAPLI->hWnd`. En perfdata.c cada consulta fallida deja `ERR PWTASK <clase> status`, y un fallo de Handle/Process ya no recorre un buffer sin datos.
- `tools/build-wine-hardware.py`: copia `out/taskmgr-hw/taskmgr.exe` en `lib/wine/x86_64-windows` y `system32`, verificando hash y builder; manifest `task_manager`.

Compilación: `out/taskmgr-hw/taskmgr.exe` sha256 9848b2a8cf534639b63bfa138e75cacf26f7ea20dd2ce886ec529c87fbf80725 (11 revisiones, sin warnings). `build/telemetry-ps4/system.o` sha256 e751f9bbaa2a7bd62cf17f1af06b0048c235fdedd2bacdc09bcac45642c33526; sus warnings son los mismos de antes (clases privadas fuera del enum, funciones sin uso).

## Límites

- La CPU es la del proceso del título (OrbisDesk), no la de toda la PS4.
- Los invitados comparten el proceso de explorer: Processes muestra procesos de Wine, no cada aplicación. «End Process» sobre explorer termina el título entero.
- Caché del sistema y memoria de kernel siguen en 0 (Wine tampoco las calcula).

## Prueba física (pendiente)

```sh
python3 tools/build-wine-hardware.py --mangohud enabled
python3 tools/upload-hardware.py --build W112 --host 192.168.68.104 --timeout 60
python3 tools/fetch-hardware.py --build W112 --host 192.168.68.104
```

Abrir Task Manager con vkspin corriendo: CPU parecida al HUD y moviéndose, memoria física, disponible y commit distintas de 0, gráficos avanzando, Processes con explorer.exe. End task sobre glxgears: la fila desaparece en 1–2 s. En el log no debe haber `PWTASK ... status`; debe aparecer `fixme ... SYSTEM_CACHE_INFORMATION` en cada refresco.

## Resultado físico: 20261102T192834Z (logs, sin confirmación visual todavía)

- run-0003: taskmgr nuevo con el ELF del PKG W112 anterior. Registra 47 veces `PWTASK SystemProcessorPerformanceInformation status c00000bb`: la traza nueva muestra exactamente la causa original (clase 8 NOT_SUPPORTED). Ese ELF no tenía el arreglo.
- run-0004 (PKG a81c9325bbaf): taskmgr abierto dos veces (hilos 003c y 0074), cero `PWTASK`, 58 refrescos que pasan por la consulta de caché sin fallos. Durante esa sesión se abrieron y cerraron glxgears (dos veces) y vkcube, todos con salida 0; taskmgr cerró con 0. PWTELEM: 6 núcleos, CPU del título 28,9 % en la muestra comparable.
- Los logs no muestran qué dibujó Performance ni si la fila desapareció tras End task. El usuario lo confirmó después: «Todo anda» (Performance con CPU y memoria, gráficos y End task). Arreglo aceptado para este escenario; no se midió la exactitud de los valores.
