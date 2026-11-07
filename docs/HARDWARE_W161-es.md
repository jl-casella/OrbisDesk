# W161: qué son las copias 2D de SuperMarioKart (fase 6)

[English](HARDWARE_W161.md) | [Español](HARDWARE_W161-es.md)

APP_VER 02.60. Base W160.

## Para qué

En W160 las copias 2D (`WINED3D_CS_OP_BLT_SUB_RESOURCE`) se llevan el 64–71 % del hilo de wined3d, ~6 ms cada una y ~7 por cuadro. Antes de cambiar nada hay que saber qué copias son y por qué camino van.

## Cambio

`tools/build-wined3d-hw.py`, `cs.c` (`wined3d_cs_exec_blt_sub_resource`): las primeras 80 copias, y una de cada 200 después, dejan `PWBLT` con:
- los flags y el efecto;
- el filtro;
- formato, tamaño, rectángulo, acceso (GPU/CPU) y uso de cada superficie;
- dónde estaban sus datos antes y después (`loc=antes->después`: textura en la GPU, memoria de sistema, buffer);
- si son parte del swapchain;
- cuánto tardó.

Con eso se ve si van por el blitter de CPU (color key, alpha test, memoria de sistema, escalado o conversión de formato) y qué conviene hacer: soportarlas en la GPU o evitar el viaje GPU→CPU→GPU.

## Prueba física

Reporte: `reports/wine-hardware-w161/physical/20261103T152548Z`, `run-0002.log`. Respuesta del usuario: "Anduvo", y en el chat que sigue lento.

**Cada cuadro del menú hace estas copias** (`PWBLT`, 100 registradas):

|Copias|Banderas| Datos | Cada una |
|---|---|---|---|
| 2–3 sprites (512×450, 468×152) al back buffer del juego |`0x41010000`, tecla de color| memoria de sistema → memoria de sistema (CPU) | 1–3 millones de ticks (0,6–1,9 ms) |
| Back buffer del juego (800×600) → buffer del swapchain | `0` | memoria de sistema → textura sólo de GPU (`access=0x1`) | **~52 millones de ticks (~33 ms)** |

- La primera copia con color key sobre el back buffer lo baja de la GPU (n=17: 206 millones de ticks, ~129 ms, una vez). Desde ahí el back buffer queda en memoria de sistema, y todas las copias siguientes van por la CPU.
- La subida del back buffer al swapchain va por la rama "Upload" de `texture2d_blt`:
  - `wined3d_texture_upload_from_texture` → `wined3d_texture_vk_upload_plane`;
  - crea un buffer de staging con sólo `VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT`, lo mapea, copia con `wined3d_format_copy_data` y encola `vkCmdCopyBufferToImage`.
- 1,9 MB en ~33 ms son ~58 MB/s.
- En el RADV de la PS4, el primer tipo de memoria visible desde la CPU es el 2 (flags `0x6`, sin caché). Una copia a memoria sin caché ni combinación de escrituras va a esa velocidad. Los tipos 5 y 6 (`0xe`) tienen caché y coherencia, y son los que usa el pool de presentación desde W144.
- El mapeo de 32 bits es directo (`VK_EXT_map_memory_placed` en win32u `vulkan.c`), sin copia a una sombra.

Prueba y medición en W162 (`HARDWARE_W162.md`).
