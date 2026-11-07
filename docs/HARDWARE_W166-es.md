# W166: llamadas Vulkan de 32 bits en lotes (fase 6)

[English](HARDWARE_W166.md) | [Español](HARDWARE_W166-es.md)

APP_VER 02.65. Base W165.

## Problema

W165, SuperMarioKart: el hilo de command stream de wined3d hace ~80.000 llamadas Unix por segundo, una por cada llamada Vulkan. Cada una pasa de 32 a 64 bits con dos cambios del registro FS (`sysarch`), y sólo eso se lleva ~18 % del hilo (perfil de wow64native).

## Cambio

Se porta el agrupamiento de llamadas Vulkan de 32 bits de prospero-win (LGPL-2.1+, mismo commit de Wine):
- el `winevulkan` PE de 32 bits encola las llamadas que no devuelven nada;
- el lado Unix las reproduce todas en una sola llamada, cuando llega una que sí devuelve algo (o al vaciar la cola).

**`tools/build-winevulkan-batch.py` (nuevo):**
1. **Registro de Vulkan:** verifica que `vk.xml` y `video.xml` 1.4.357 reproducen byte a byte los ocho archivos que Wine generó (`vulkan_thunks.c/h`, `loader_thunks.c/h`, `include/wine/vulkan.h`, `vulkan_driver.h`, `vulkan-1.spec`, `winevulkan.spec`). Se descargaron, con permiso del usuario, de `github.com/KhronosGroup/Vulkan-Docs`, tag `v1.4.357`, a `~/.cache/wine`.
2. **Árbol:** arma `.deps/wine/winevulkan-batch/tree` con `tools/stage_vk_batch.py` de prospero-win, que:
   - copia el runtime (`wine/ps5/pw_vk_*` y `wine/ps5/vulkan/*`);
   - edita `loader.c`, `vulkan_loader.h` y `vulkan.c`;
   - regenera los thunks y los codecs de 385 llamadas.
3. **`winevulkan.dll` de 32 bits:** compila las 11 fuentes PE con el comando de compilación y de link del build fijado (`make -n`) y lo deja en `out/winevulkan-batch`.

**`tools/build-winevulkan-ps4.py`:** el lado Unix del ELF se compila desde ese árbol: `vulkan.c`, `vulkan_thunks.c` y los siete `*_unix.c` (reproducción, formato de registros, plantillas de descriptores, codecs generados).

**`tools/build-wine-hardware.py`:** pone ese `winevulkan.dll` en `syswow64` y en `i386-windows`.

**Programas de 64 bits:** siguen con los thunks normales (el agrupamiento es `#ifndef _WIN64`) y su `winevulkan.dll` sigue siendo el fijado. La tabla Unix sólo suma una entrada al final.

**Qué no se porta:** la versión asíncrona de prospero-win (reproducción en hilos nativos). El lado Unix no anuncia `__wine_pw_vk_batch_async_v2`, así que el PE usa la versión 2, sincrónica.

## Contador de FPS sólo en juegos de 32 bits

El usuario vio que F12 también mostraba el contador sobre el escritorio de explorer, y eso no se quiere. Además, en los programas de 64 bits del escritorio (glxgears, vkspin) corre MangoHud, que usa la misma tecla.
- **`platform/ps4/pw_wine_sink_ps4.c`:**
  - `pw_hw_fps_toggle` sólo toma F12 en un título de 32 bits (`WINE_PS5_FIT`, que lanza sin MangoHud), y mientras un programa Vulkan presentó en los últimos 2 s;
  - en otro caso devuelve 0 y no cambia nada;
  - el contador sólo se dibuja con presents Vulkan recientes, ya no con los cuadros del compositor.
- **`native/hw_pad.c`:** si el sink no toma F12, la tecla llega a los programas como cualquier otra, al apretarla y al soltarla. Así MangoHud la sigue recibiendo en el escritorio.

## Qué se espera

- **Perfil de wow64native:** menos llamadas Unix por segundo y menos tiempo de cambio de FS en el hilo de wined3d.
- **Juego:** más FPS en SuperMarioKart.
- **Riesgo:** es un cambio grande en la capa Vulkan de los programas de 32 bits. Un error en la reproducción puede dibujar mal o cerrar el programa.

## Prueba física

Reporte: `reports/wine-hardware-w166/physical/20261103T172225Z`, `run-0002.log`. Respuesta del usuario: "Más rápido, todo bien".

**El agrupamiento no estaba activo.** prospero-win lo deja apagado salvo que el entorno tenga `PW_VK_BATCH=1` (`pw_vk_batch_pe.c`, `initialize`), y el launcher no lo ponía. El `winevulkan` nuevo mandó cada llamada como antes. Coincide con las mediciones:

| Hilo de wined3d | W165 | W166 |
|---|---|---|
| Llamadas Unix por segundo | ~80.000 | ~73.000 |
| Cambio de FS | 17,9 % | 16,4 % |

- **FPS de la carrera:** 27–53, parecido a W165.
- **Lo que sí se comprobó:** el `winevulkan` de 32 bits recompilado y el lado Unix del árbol con prospero-win funcionan sin el agrupamiento, con el juego y el escritorio.

Activación en W167 (`HARDWARE_W167.md`).
