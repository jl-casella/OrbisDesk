# SeaMonkey y la memoria flexible

[English](SEAMONKEY_FLEXIBLE_MEMORY.md) | [Español](SEAMONKEY_FLEXIBLE_MEMORY-es.md)

Estado: cambio de fuentes y un programa de reproducción, 2026-11-16. Todavía no está compilado en un paquete ni probado en la consola.

## El síntoma

SeaMonkey 2.53.24 (`C:\Program Files\SeaMonkey`, incluido desde W303) carga sitios remotos. Las páginas con mucho JavaScript se quedan a medias.

## Causa

Un título tiene dos clases de memoria. Los logs las muestran al arrancar:

```text
PWBOOT memory_info direct=4831838208 direct_free=4692967424 (rc=0) flexible_free=391118848 (rc=0)
```

El título entero, con explorer, wineserver, Mesa y todos los invitados, tiene unos 390 MB de memoria **flexible**. Tiene unos 4,6 GB de memoria **directa**. El heap de la libc de Wine, wineserver y Mesa solo pueden usar la flexible.

Desde W175 y W184, los commits de Wine de 1 MiB o más, y las vistas nuevas comprometidas de 1 MiB o más, toman memoria directa. Lo más pequeño toma memoria flexible.

El asignador de SeaMonkey, mozjemalloc, funciona así en Windows:

1. Asigna cada chunk de 1 MiB comprometido. Esa vista toma memoria directa (W184).
2. Descompromete de una vez todo lo que sigue a la cabecera del chunk (`MALLOC_DECOMMIT`).
3. Compromete tramos de pocas páginas según los necesita. Al purgar, los descompromete y los vuelve a comprometer.

El paso 2 pasaba por `decommit_pages` → `pw_rereserve`, que devolvía la memoria directa. Cada commit del paso 3 es de menos de 1 MiB, así que tomaba memoria flexible. Con el tiempo, todo el heap de malloc del navegador (DOM, cadenas, código fuente de scripts, bytecode, datos del JIT) pasaba de la memoria directa a la reserva de 390 MB. Una página pesada terminaba de agotarla.

Las ejecuciones W224 y W225 muestran el momento en que se agota. Eran SeaMonkey con YouTube, con logs en `reports/wine-hardware-w224/physical/20261104T204513Z/run-0001.log` y `reports/wine-hardware-w225/physical/20261104T211135Z/run-0001.log`:

```text
PWVM commit_backing page=0x267704000 flexible map=0x80020016 at=0x267704000; direct memory instead (1)
...
map_view anon mmap error Invalid argument, size 0x14000, unix_prot 0x3
try_map_free_area mmap() error Invalid argument, range 0x102100000-0x102210000, unix_prot 0x3.
PWFAULT n=1 thread=0060 address=00000007FEF42EE5 access=1 target=0    (ucrtbase.dll, desde xul.dll)
```

Con la reserva vacía, el kernel rechaza un mapeo flexible con `EINVAL` (`0x80020016`), no con `ENOMEM`. La alternativa de W224 mantenía con memoria directa los commits dentro de reservas. Las vistas pequeñas nuevas (`map_view`) y el lado Unix no tenían alternativa. Fallaban, y se escribía en un `NULL` devuelto por una asignación.

Las ejecuciones de SeaMonkey de W303 en `reports/wine-hardware-w303/` no muestran esas líneas. Los logs no registran qué páginas se abrieron, y ninguno muestra una página pesada fallando. Todavía no se ha recogido un log del síntoma actual.

El JIT no es la causa. SpiderMonkey reserva 1 GiB `PAGE_NOACCESS` (una reserva del kernel desde W182) y después compromete piezas de 64 KiB y las cambia entre `PAGE_READWRITE` y `PAGE_EXECUTE_READ`. Eso usa poca memoria. W215 también descartó el JIT en el bloqueo de Pale Moon con YouTube. El JIT solo importa aquí porque también toma memoria flexible. Apagarlo (`javascript.options.baselinejit`, `ion`, `wasm` y `native_regexp` en `false`, como el antiguo perfil "Pale Moon (no JIT)") sirve para probar esa diferencia. No es el arreglo.

## El cambio

El cambio está en el generador [build-audio-ps4.py](../tools/build-audio-ps4.py), que parchea el `virtual.c` de Wine:

- **Descomprometer conserva la memoria directa.** `decommit_pages` llama ahora a `pw_decommit_host` para las páginas host completas de un decommit:
  - Las páginas bajo un registro de memoria directa conservan su memoria.
  - Antes se ponen a cero las páginas de 4 KiB que Wine tiene comprometidas. Windows entrega a cero una página comprometida de nuevo, y mozjemalloc cuenta con ello (W222).
  - Después el rango pasa a `PROT_NONE`, así que un acceso falla como en Windows.
  - Las páginas que no están bajo memoria directa se vuelven a reservar como antes.
  - Liberar la región (`MEM_RELEASE`, `unmap_area`) sigue devolviendo la memoria.
  - Línea de log: `PWVM decommit_host … keeps direct memory` (las 8 primeras).
- **El nuevo commit la encuentra.** `pw_commit_backing` salta las páginas host que el kernel reporta como memoria directa (bit 1 de los flags de la consulta), con una consulta por región del kernel. Volver a comprometer una página conservada no mapea nada ni usa memoria flexible. En un commit de 1 MiB o más, no se mapea un segundo bloque de memoria directa encima del conservado.
- **Una reserva para el lado Unix.** Con menos de 64 MiB de memoria flexible libre (`PW_FLEXIBLE_RESERVE`), los commits y las vistas nuevas comprometidas de **cualquier** tamaño toman memoria directa. El resto de la reserva queda para wineserver, libc y Mesa, que no tienen otra. Línea de log: `PWVM flexible low: … direct memory instead` (las 8 primeras).
- **Más registros.** La tabla de registros de memoria directa pasa de 8192 a 32768 entradas, porque ahora los tramos pequeños también ocupan registros.

El perfil de SeaMonkey ([seamonkey-user.js](../fixtures/browser/seamonkey-user.js)) no cambia.

## Reproducción

[jitmem.c](../fixtures/win32/jitmem.c) es un invitado de 64 bits. [build-wine-hardware.py](../tools/build-wine-hardware.py) lo instala como `C:\orbis\jitmem64.exe`. Hace las asignaciones de SeaMonkey sin el navegador y añade sus resultados a `C:\orbis\jitmem-result.txt`:

| Paso | Qué hace |
|---|---|
| `heap` | 384 chunks de 1 MiB al modo de mozjemalloc: comprometidos, todo menos 16 KiB descomprometido y vuelto a comprometer en tramos de 16/32/64 KiB. Cada tramo se comprueba a cero y se escribe. |
| `purge` | En uno de cada cuatro chunks se descomprometen dos tramos, se vuelven a comprometer y se comprueban a cero otra vez. |
| `views` | 256 vistas nuevas comprometidas de 80 KiB, el tamaño que W224 vio rechazado. |
| `jit` | 1 GiB reservado `PAGE_NOACCESS` y después 256 piezas de 64 KiB. Cada pieza se escribe en `RW`, se pasa a `RX`, se vacía la caché de instrucciones y se llama por ambos extremos, se vuelve a `RW` y se parchea, y se pasa otra vez a `RX`. |
| `release` | Todo se libera con `MEM_RELEASE`. |

Argumentos, todos opcionales: número de chunks, número de piezas del JIT y otro archivo de salida. Un paso que falla registra el error Win32 y lo que llevaba hecho. Un paso que no puede ejecutarse se registra como `skipped=…`, nunca como `ok`.

Antes de este cambio, en la consola, `heap` debería llevar unos 384 MB a la reserva flexible. Eso termina como en W224, con `views` fallando o el título con un fallo. Después del cambio, todos los pasos deberían dar `ok`, con `PWVM decommit_host … keeps direct memory` en el log.

## Qué se probó

- El `virtual.c` parcheado se genera a partir de la entrada probada (su hash coincidió) y compila con su propia receta (`orbis-cc`, `-Wall`, código de salida 0). No se escribió nada en `build/` ni en `out/`.
- `jitmem.c` compila con mingw (`-O2 -Wall`, sin avisos). En Windows 11 nativo (solo referencia, no es evidencia de PS4), todos los pasos dan `ok`: `heap` 384, `purge` 96, `views` 256, `jit` 256 piezas, `release` 641.
- **No probado:** no se compiló ningún paquete y nada se ejecutó en la consola ni en el emulador. El emulador no modela el límite de memoria flexible de la consola.

## Prueba en la consola (requiere una compilación y la aprobación del usuario)

1. Ejecutar `C:\orbis\jitmem64.exe` desde WFM. Traer `jitmem-result.txt` y el log.
2. Abrir en SeaMonkey la página pesada que antes se quedaba a medias. Desplazarse por ella, y después cerrar y volver a abrir SeaMonkey. Buscar en el log `PWVM flexible low`, `decommit_host`, `anon mmap error` y `PWFAULT`.
3. Si una página pesada sigue parándose y no aparece ninguna de esas líneas, repetirla con un perfil con el JIT apagado (ver arriba). Así se separa un problema del JIT de uno de renderizado o de red.

## Riesgos

- Un decommit dentro de memoria directa ya no devuelve memoria hasta que se libera la región. Un programa que reserva mucho, lo compromete una vez y lo descompromete se queda con ella. La memoria directa es de 4,6 GB, y las regiones de un invitado se liberan al salir (W208/W211).
- Con la reserva baja, las páginas ejecutables (el JIT) pueden recibir memoria directa. La alternativa de W224 ya lo hacía. No se ha probado por separado si la consola permite ejecutar en memoria directa con GoldHEN. El paso `jit` solo lo prueba si la reserva está baja cuando se ejecuta.
