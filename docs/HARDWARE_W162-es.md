# W162: staging de subidas en memoria con caché (fase 6)

[English](HARDWARE_W162.md) | [Español](HARDWARE_W162-es.md)

APP_VER 02.61. Base W161.

## Problema

En SuperMarioKart, cada cuadro sube a la GPU el back buffer de 800×600 desde memoria de sistema, y eso tarda ~33 ms (W161). wined3d pide para el buffer de staging sólo memoria `HOST_VISIBLE`, y en la PS4 eso da el tipo 2, sin caché.

## Cambio

`tools/build-wined3d-hw.py`, `texture_vk.c` (`wined3d_texture_vk_upload_plane`):
- **Memoria del staging:** se pide primero `HOST_VISIBLE | HOST_CACHED` (tipo 5 o 6 en la PS4, con caché y coherencia). Si no hay, se usa la memoria de antes. La GPU lee esa memoria con coherencia, igual que el pool de presentación desde W144.
- **Medición:** en las subidas de 256 KiB o más (las primeras 40 y una de cada 200 después), `PWUPLOAD` deja el tamaño, si se usó la memoria con caché, sus flags y los ticks de cada paso: crear el buffer, mapear, copiar, desmapear.

Las copias con color key siguen por la CPU. Pasarlas a la GPU queda para después, si hace falta.

## Qué se espera

- `PWUPLOAD … cached=1` con el paso de copia muy por debajo de los ~52 millones de ticks de W161.
- `BLT_SUB_RESOURCE` mucho más barato en `PWCS`, y más FPS.

## Prueba física

Reporte: `reports/wine-hardware-w162/physical/20261103T154053Z`, `run-0002.log`. Respuesta del usuario: "Igual".

**`PWUPLOAD`** (800×600, 1.920.000 bytes, memoria `0xe` con caché), en miles de ticks:

|Paso| Primera | Siguientes |
|---|---|---|
|Crear| 375 | ~36 |
|Mapear| ~31.000 | ~31.000 (~19,5 ms) |
| Copiar | ~1.000 | ~1.000 (~0,65 ms) |
|Desmapear| ~3 | ~3 |

- La copia ya es barata. El costo está en mapear: cada subida mapea de nuevo.
- `PWCS`: `BLT_SUB_RESOURCE` sigue en ~2,6 millones de miles de ticks por ventana (~60 % del hilo).
- **FPS:** el valor más repetido es 34,6 (17 segundos), contra un máximo de 25,5 en W157–W160. Hay tramos de 15–17, por eso el usuario lo notó igual.

**Causa del mapeo:**
- wined3d de 32 bits deja la memoria mapeada sólo mientras el total mapeado sea de 128 MB o menos (`MAX_PERSISTENT_MAPPED_BYTES`, `wined3d_private.h`).
- La reserva de memoria Vulkan va en bloques de 64 MB. Con el bloque nuevo de memoria con caché se pasa el límite, y desde ahí `wined3d_bo_vk_unmap` desmapea después de cada uso.
- Cada subida vuelve a mapear el bloque entero de 64 MB, con un mapeo WoW64 a dirección fija (`VK_EXT_map_memory_placed`).

Corrección en W163 (`HARDWARE_W163.md`).
