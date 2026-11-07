# W164: staging de bajadas en memoria con caché (fase 6)

[English](HARDWARE_W164.md) | [Español](HARDWARE_W164-es.md)

APP_VER 02.63. Base W163.

## Problema

Las copias con color key se hacen en la CPU. Cuando el destino es el back buffer que la GPU acaba de dibujar, wined3d lo baja entero (800×600). En W163 eso cuesta ~44 ms, y pasa en la carrera. La bajada lee de un staging en memoria sin caché.

## Cambio

`tools/build-wined3d-hw.py`, `texture_vk.c` (`wined3d_texture_vk_download_plane`):
- **Memoria del staging:** se pide primero `HOST_VISIBLE | HOST_CACHED` (tipos 5 y 6 en la PS4, coherentes). Si no hay, se usa la memoria de antes.
- **Medición:** `PWDOWNLOAD`, en las bajadas de 256 KiB o más (las primeras 40 y una de cada 200 después), deja los ticks de cada paso:
  - esperar a la GPU, que incluye terminar el cuadro que está dibujando;
  - mapear;
  - copiar.

## Qué se espera

- La copia de la bajada en ~1 millón de ticks o menos, como la subida.
- Queda la espera a la GPU, que no se puede evitar mientras estas copias se hagan en la CPU. Si sigue siendo grande, el paso siguiente es hacer las copias con color key en la GPU, sin bajar el back buffer.

## Prueba física

Reporte: `reports/wine-hardware-w164/physical/20261103T160838Z`, `run-0002.log`. Respuesta del usuario: "Más rápido".

**`PWDOWNLOAD`** (800×600, memoria `0xe` con caché), en miles de ticks:

|Paso| Primera | Siguientes |
|---|---|---|
| Esperar a la GPU | 17.436 | ~670–3.300 (0,4–2 ms) |
|Mapear| 47.838 | ~100–900 |
| Copiar | ~1.077 | ~1.000 (~0,65 ms) |

- Cada bajada pasa de ~70 millones de ticks (~44 ms) a ~3–5 millones (~2–3 ms).
- **FPS** (`PWVK present fps`, uno por segundo):
  - unos 170 segundos seguidos entre 35,2 y 36,8;
  - después (otra pista o sección) entre 28 y 66, con la mayoría entre 37 y 57;
  - antes eran 13–17 en la carrera.
- **`PWCS`:** el hilo de wined3d ejecuta el 66–74 % del tiempo y duerme el 23–31 %. Ya no está saturado todo el tiempo.

| Operación | Miles de ticks por ventana |
|---|---|
| `DRAW` | ~1,13–1,17 millones (el primero) |
| `BLT_SUB_RESOURCE` | ~1,02–1,08 millones (~1.050 copias, ~1 ms cada una) |
| `PRESENT` | ~320.000 |

- **`PWVK cpu`:** a 36 fps, el hilo que presenta está al 94 % y el cuadro tarda 27 ms. En la parte de más FPS, al 57 % y 17,7 ms.

**Resultado de W161–W164** para los juegos de 32 bits con wined3d y Vulkan:
- subir memoria de sistema a la GPU: de ~33 ms a ~0,85 ms (W162 + W163);
- bajar de la GPU: de ~44 ms a ~2–3 ms (W164);
- SuperMarioKart: de 13–17 fps a ~36 fps en carrera.
