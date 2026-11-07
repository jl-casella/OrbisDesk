# W163: wined3d de 32 bits deja mapeados sus bloques de memoria (fase 6)

[English](HARDWARE_W163.md) | [Español](HARDWARE_W163-es.md)

APP_VER 02.62. Base W162.

## Problema

En W162, cada subida del back buffer de SuperMarioKart tarda ~19,5 ms en mapear el buffer de staging. wined3d de 32 bits desmapea después de cada uso cuando el total mapeado pasa de 128 MB, y el siguiente mapeo es otra vez el bloque entero de 64 MB.

## Cambio

`tools/build-wined3d-hw.py`, `adapter_vk.c` (`wined3d_bo_vk_unmap`): en 32 bits el límite pasa de 128 MB a 512 MB (ocho bloques). En 64 bits sigue sin límite, como antes. Siguen el staging con caché y `PWUPLOAD` de W162.

El límite existe para no gastar el espacio de direcciones de un proceso de 32 bits (2 GiB sin `LARGE_ADDRESS_AWARE`). 512 MB todavía deja la mayor parte libre. Un juego que necesite más memoria mapeada vuelve a desmapear como antes, sin fallar.

## Qué se espera

- `PWUPLOAD … map=` cerca de 0 desde la segunda subida.
- `BLT_SUB_RESOURCE` mucho más barato en `PWCS`, y más FPS en todo el juego.

## Prueba física

Reporte: `reports/wine-hardware-w163/physical/20261103T155150Z`, `run-0002.log`. Respuesta del usuario: "Más rápido".

- **`PWUPLOAD`:** las primeras 40 subidas todavía mapean en ~31 millones de ticks; desde la 200, `map=0–2`. Cuando el total mapeado bajó del nuevo límite, el bloque quedó mapeado.
- **La subida del back buffer al swapchain** (`PWBLT flags=0 800x600`) bajó de ~52 millones de ticks (W161) a 1,32–1,41 millones (~0,85 ms).
- **El cuello pasó a otro lado:**
  - una de cada pocas copias con color key de un sprite chico (73×79) sobre el back buffer que la GPU acaba de dibujar (`loc=TEXTURE_RGB`) cuesta ~68–73 millones de ticks (~44 ms);
  - el blitter de CPU primero baja el back buffer entero de la GPU;
  - `BLT_SUB_RESOURCE` sigue en ~3,1 millones de miles de ticks por ventana, y los FPS de la carrera en 13–17.
- **La bajada** (`wined3d_texture_vk_download_plane`):
  - espera a la GPU;
  - mapea un staging pedido sólo como `HOST_VISIBLE` (sin caché en la PS4);
  - lo lee con la CPU. Leer memoria sin caché es todavía más lento que escribirla.

Corrección en W164 (`HARDWARE_W164.md`).
