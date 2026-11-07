# W143: salida a pantalla por GPU, orden de arranque corregido (fase 6, paso 1)

[English](HARDWARE_W143.md) | [Español](HARDWARE_W143-es.md)

APP_VER 02.42. Base W142.

## Problema en W142

En W142 la ruta por GPU no llegó a usarse. El sink abre VideoOut con el primer cuadro, que es la pantalla de arranque del launcher, y elige los buffers en ese momento. Exigía que ya existiera la memoria del escritorio, pero ps5drv la pide unos segundos después. Detalle en `HARDWARE_W142.md`.

## Cambio

- **`native/hw_sink_gpu/hw_sink_gpu.c`:**
  - `device_init` corre una vez y lo usan tanto `pw_sink_gpu_screen` como `pw_sink_gpu_buffers`.
  - Los buffers de VideoOut por Vulkan se crean aunque todavía no haya escritorio.
  - El descriptor del escritorio se escribe al crear la memoria (`bind_screen`), en el orden que sea.
  - `pw_sink_gpu_draw` falla con error si todavía no hay escritorio.
- **`platform/ps4/pw_wine_sink_ps4.c`:**
  - `open_video` intenta siempre los buffers por GPU.
  - Los cuadros que no salen de la memoria del escritorio, como la pantalla de arranque, se copian por CPU a esos mismos buffers.
  - Si falla Vulkan, sigue registrando `PWSINK gpu_unavailable: CPU copy` y usa la memoria directa, como antes.

## Qué se espera

- En el log:
  - `PWSINK gpu_buffer 0/1 …`;
  - `PWBOOT video_out_ready … gpu=1 pitch=…`;
  - después, `PWSINK gpu_screen …`;
  - `show_stats path=cpu` sólo en los primeros cuadros y después `show_stats path=gpu`;
  - ningún `gpu_failed` ni `gpu_draw_failed`.
- El escritorio se ve igual que en W142.
- Comparación de tiempos: en W142 la copia por CPU tardaba ~1,0 ms de promedio por cuadro. En el camino por GPU ese tiempo pasa a ser la espera de la fence.

## Prueba física

Reporte: `reports/wine-hardware-w143/physical/20261103T095328Z`. Respuesta del usuario: "Se ve igual".

La ruta por GPU **quedó activa**:
- `PWSINK gpu_buffer 0/1 memory_type=3 … row_pitch=5120` y `PWBOOT video_out_ready 1280x720 buffers=2 gpu=1 pitch=1280` aparecen en las líneas 92–100, antes de que arranque Wine.
- `PWSINK gpu_screen 1280x720 memory_type=5` aparece en la línea 1171.
- Desde el cuadro 3 (línea 1346) los cuadros salen de esa memoria y se dibujan con el shader.
- No hubo `gpu_failed`, `gpu_draw_failed` ni `gpu_unavailable`.
- La captura `screen.png` y la respuesta del usuario coinciden con W142: colores, posición, barra de tareas y reloj.

Sin tiempos todavía:
- La sesión fue corta y con poca actividad: 64 cuadros en ~49 s, contra 1600 en W142.
- `show_stats` sale cada 300 cuadros y `flush_stats` cada 100, así que no llegó a aparecer ninguno de los dos.

La medida de tiempo con la GPU queda para la próxima build. Va a hacer falta un marcador con menos cuadros, o una sesión más larga.
