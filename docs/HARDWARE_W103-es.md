# W103: porcentajes nativos para MangoHud

[English](HARDWARE_W103.md) | [Español](HARDWARE_W103-es.md)

APP_VER 02.02. W102 conserva la referencia física de estabilidad: dos ciclos, seis cierres 0, Start operativo y salida final 0. W103 añade métricas; su exactitud y disponibilidad quedan pendientes de la ejecución en consola.

## Qué se mide

- **CPU app**: diferencia del reloj CPU del proceso (clock_gettime, reloj FreeBSD 15) dividida por tiempo transcurrido y cantidad de CPU disponibles en la afinidad inicial del título. Incluye OrbisDesk y sus invitados, no la utilización global de la PS4. Si el reloj o la afinidad no están disponibles, muestra N/A.
- **GPU app**: unión de los intervalos de trabajo GFX medidos con timestamps GPU de Crema, entre todos los dispositivos del título y en orden de envío. Divide trabajo por el intervalo entre muestras GPU completadas. No mide ocupación de shaders ni actividad de otros títulos o del sistema.
- Muestreo cada 500 ms. El primer intervalo y los contadores no válidos muestran N/A. Una pérdida de eventos invalida esa muestra; no se convierte en un porcentaje inventado. No se publican porcentajes por núcleo.

Se conserva el muestreo en el frame de W102, sin nuevos hilos de estadísticas. El anillo de telemetría GPU tiene capacidad limitada y registra pérdidas en vez de bloquear los envíos. El proveedor registra PWTELEM con valores crudos, estados y pérdidas; MangoHud registra PWHUD native_metrics.

La consulta privada NtQuerySystemInformation 0x50573454 usa una estructura versionada de 80 bytes. No se modifican las clases estándar de CPU de Windows. tools/build-telemetry-ps4.py recompila únicamente system.o desde la fuente probada, con la receta original, y reconstruye el archivo AMD de Mesa. El enlace sustituye ese objeto y añade native/telemetry.c. No se ejecuta el borrador anterior de CPU de prepare-wine-boot.py.

Los parches de Crema y MangoHud se aplican sobre las copias de compilación; los checkouts upstream se conservan. Manifiesto y reportes incluyen hashes de fuentes, objetos, archivo AMD, DLL, ELF y PKG. Evidencia archivada en reports/wine-hardware-w103/release-w103 y build-report.json.

## Construcción y validación física

Desde WSL Ubuntu-22.04, en la raíz del proyecto:

```sh
python3 tools/build-telemetry-ps4.py
bash tools/vk-h0/build-mangohud.sh
python3 tools/build-wine-hardware.py --mangohud enabled
python3 tools/upload-hardware.py --build W103 --host 192.168.68.104 --timeout 60
```

Compilación y enlace completados; matriz local omitida a pedido del usuario. PKG SHA-256: 913c7e7df41bb6af6540e0f8997839e18e368db2a2356a0ab94134d2ba94a429. ELF SHA-256: fac0deea9426fb36a583ac163ee8b35cd2ad229266481ca22d1fae856d3a86e4.

Tras instalar, observar CPU app/GPU app con una aplicación y con las tres. Repetir dos ciclos de abrir/cerrar glxgears, vkcube y vkspin, cerrando vkcube primero, y volver a Start. Comprobar cambios de carga y avisar si N/A persiste. Al recibir «Ya la probé», descargar los logs y comprobar estados, deltas, pérdidas y cierres antes de declarar los porcentajes validados:

```sh
python3 tools/fetch-hardware.py --build W103 --host 192.168.68.104
```

Transferencia completada con lectura de vuelta verificada: `/data/pkg/orbis-win-W103-913c7e7df41b.pkg`. Informe: `reports/wine-hardware-w103/transfers/20261102T135850Z.json`. Runtime: 548 archivos, 545 presentes y 3 subidos, sin fallos de permisos. W102 retirado de /data/pkg después de verificar. Evidencia local conservada.

Transferencia y resultado físico se registran por separado; compilar no prueba que el reloj CPU o el contador GPU sean válidos en esta consola.

## Primera sesión física: 20261102T140357Z

Se recogieron 74 muestras. Las tres aplicaciones se abrieron y cerraron con código 0. Sin marcador de crash; el escritorio continuó presentando cuadros. El log no registra salida final del título ni permite acreditar dos ciclos o la respuesta de Start. Análisis: physical/20261102T140357Z/analysis.json dentro de reports/wine-hardware-w103.

GPU varió de 0,356 a 8,909 %, con cero eventos perdidos. Hay evidencia de respuesta a la carga, sin calibración independiente. CPU queda **rechazada**: las muestras válidas dan 16,666 % y el supuesto reloj CPU avanza prácticamente igual que el tiempo transcurrido. No se considera un porcentaje funcional. W104 sustituye esa fuente por getrusage(RUSAGE_SELF), usuario + kernel, y retira «app» de las etiquetas a pedido del usuario.
