# W165: sprites con color key en la GPU, contador de FPS con F12 y tiempo de las llamadas Vulkan (fase 6)

[English](HARDWARE_W165.md) | [Español](HARDWARE_W165-es.md)

APP_VER 02.64. Base W164.

## Sprites con color key en la GPU

En W164, a ~36 fps, los sprites del HUD de SuperMarioKart siguen siendo copias de DirectDraw con color key de origen (`SRC_CKEY_OVERRIDE`). El blitter Vulkan de wined3d no las acepta, y las hace el blitter de CPU:
1. baja el back buffer que la GPU acaba de dibujar (copia ~0,65 ms, más la espera a la GPU);
2. copia los sprites en la CPU;
3. lo sube de nuevo (~0,85 ms).

Pasa en cada cuadro: `BLT_SUB_RESOURCE` suma ~6,6 ms por cuadro.

**Cambio** (`tools/build-wined3d-hw.py`, `texture_vk.c`, `vk_blitter_blit`): las copias con color key se dibujan en la GPU.
- El rectángulo de origen se copia a una imagen temporal que se puede muestrear.
- Se dibuja sobre el destino con un shader que descarta los texels del color key. El rango se compara por canal, como hace DirectDraw.
- Render pass, pipeline, sampler y shaders (GLSL compilado con el glslang de `~/vk-h0/host-tools`) se crean una vez por dispositivo y formato. Vistas, framebuffer e imagen temporal se liberan cuando termina el command buffer.
- **Sólo se aplica en:** texturas 2D de 32 bits BGRA/BGRX, sin multisample, con destino render target y origen con acceso de GPU.
- Cualquier otro caso, o un error al armar el pipeline, sigue por el blitter de CPU como antes. Queda `PWCKEY …` en el log.
- Las primeras tres copias quedan registradas (`PWCKEY blit n`).

Con el back buffer siempre en la GPU, desaparecen la bajada, la subida y la espera por cuadro. Sirve para cualquier programa DirectDraw/Direct3D 7 con sprites con color key sobre una escena 3D.

**Riesgo:** es un camino nuevo de dibujo en la GPU. Un error en el pipeline o en los cambios de layout puede colgar la GPU, como pasó en W152.

## Contador de FPS

El usuario lo pidió oculto al arrancar y con F12 para mostrarlo u ocultarlo, como MangoHud. MangoHud no corre en los programas de 32 bits (W127): habría que compilarlo para 32 bits y cargarlo como capa en el dispositivo Vulkan de wined3d. El contador sale del compositor:

- **`platform/ps4/pw_wine_sink_ps4.c`:**
  - `draw_fps` escribe `FPS n.n` en amarillo sobre negro en la esquina superior izquierda de la imagen de salida, después de que la GPU o la CPU la dibujaron y antes del flip;
  - el valor son los presents por segundo del programa Vulkan, si alguno presentó en los últimos 2 s; si no, los cuadros por segundo del compositor;
  - `pw_hw_fps_toggle` lo prende o lo apaga (`PWSINK fps_overlay=…`);
  - `pw_wine_vk_fps` recibe el valor una vez por segundo y vuelve a dibujar.
- **`native/wine_vk_runtime.c`:** pasa los presents por segundo que ya mide (`PWVK present fps`).
- **`native/hw_pad.c`:** F12 del teclado (HID `0x45`) llama a `pw_hw_fps_toggle`. Los programas no reciben esa tecla.
- **`tools/build-wine-hardware.py`:** el sink se compila con `native/` en la ruta de includes, por `hw_text.h`.

Es el mismo contador de los logs. Con MangoHud en 32 bits se podría mostrar más (tiempos por cuadro, CPU, GPU), pero es un trabajo aparte.

## Medición

En W164 (~36 fps en carrera), el hilo de command stream de wined3d pasa el 76 % del tiempo en el lado de 64 bits, en ~800 llamadas Unix por segundo de ~1 ms cada una.

`tools/build-wined3d-hw.py`, `context_vk.c`: se miden la cantidad y los ticks de estas llamadas:
- `vkAllocateMemory`;
- `vkQueueSubmit`;
- `vkWaitForFences`;
- `vkCreateGraphicsPipelines`;
- `vkAllocateDescriptorSets`;
- `vkUpdateDescriptorSets`.

`cs.c` las agrega a cada ventana de `PWCS` como `PWCS vk count/kticks: alloc=… submit=… wait=… pipeline=… descset=… update=…`.

## Prueba física

Reporte: `reports/wine-hardware-w165/physical/20261103T165431Z`, `run-0002.log`. Respuesta del usuario: "Más rápido y bien": el HUD se ve bien. El contador se prendió con F12 (`PWSINK fps_overlay=1`).

**Sprites en la GPU:**
- `PWCKEY GPU colour-keyed blits for format 44`. Las primeras copias son el fondo 800×600 (key 0) y los sprites del menú (key `0xff00ff`, magenta).
- `BLT_SUB_RESOURCE` baja de ~1,02–1,08 millones de miles de ticks por ventana (W164) a 0,28–0,34 millones, con más cuadros por ventana.

**FPS** (`PWVK present fps`): en la carrera 31–53 (la mayoría 35–50); en el menú 46–82; en algunos tramos 195–305, en pantallas casi estáticas. En W164 eran ~36 estables en la carrera y 37–66 en el resto.

**Hilo de wined3d:**
- **`PWCS`:** ejecuta el 60–69 % del tiempo y duerme el 26–36 %.
- **Operaciones:** `DRAW` (~19.500 por ventana, ~78.000 ticks ≈ 49 µs cada uno) es lo más grande; `PRESENT` va segundo.
- **`PWCS vk` por ventana:**
  - `vkAllocateDescriptorSets` ~20.400 (~5,7 µs cada uno);
  - `vkUpdateDescriptorSets` ~19.300 (~7,8 µs);
  - `vkQueueSubmit` ~180 (~84 µs);
  - `vkWaitForFences` 0–21;
  - pipelines nuevos 12–71.
- **Perfil de wow64native:**

| |Unix|Syscalls| Cambio de FS |32 bits| Llamadas Unix |
|---|---|---|---|---|---|
| Hilo de wined3d | 23,6 % | 34,9 % | **17,9 %** | 23,6 % | ~80.000 por segundo |
| Hilo del juego | — | 64,6 % (sobre todo `Sleep`) | — | 28,6 % | — |

**Lectura:** cada llamada a Vulkan de un programa de 32 bits pasa al lado de 64 bits con dos cambios del registro FS (`sysarch`). Con ~80.000 por segundo, sólo esos cambios se llevan ~18 % del hilo. prospero-win agrupa las llamadas Vulkan de 32 bits para hacer menos transiciones; es el candidato siguiente.
