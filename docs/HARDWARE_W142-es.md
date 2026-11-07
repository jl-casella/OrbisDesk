# W142: salida a pantalla por GPU (fase 6, paso 1)

[English](HARDWARE_W142.md) | [Español](HARDWARE_W142-es.md)

APP_VER 02.41. Base W141.

## Dónde se va el tiempo hoy

Hay tres trabajos de CPU entre lo que dibuja Windows y la pantalla:

1. **Ventanas al escritorio:** `ps5drv.c` (`ps5_surface_flush`) copia cada actualización de una ventana a su buffer, compone el área sobre el escritorio (`compose_rect`) y avisa al sink. Corre en el hilo de Wine. Es lo que mide `PWBOOT flush_stats`: en W140, ~3,5 ms de promedio y hasta 20 ms por actualización, con unos 690 000 píxeles.
2. **Escritorio a pantalla:** el sink (`platform/ps4/pw_wine_sink_ps4.c`, `show()`) copia el escritorio completo, lo escala, fuerza el alfa y dibuja el puntero en uno de los dos buffers de VideoOut. Después hace el flip. Corre en el hilo presentador, hasta ~60 veces por segundo.
3. **Ventanas Vulkan (juegos):** el swapchain copia cada imagen a memoria de CPU y `pw_vk_show_frame` la pasa a la ventana por GDI. A partir de ahí sigue los pasos 1 y 2.

En SuperMarioKart (~12 FPS) estas copias no son el freno:
- El juego hace ~63 dibujos Direct3D 7 por cuadro, que pasan por wined3d en la CPU, con el log de trazas activo.
- La GPU tarda ~2 ms por cuadro, y las copias suman unos pocos ms de ~83.

La fase 6 apunta al escritorio y a las ventanas.

## Qué hace W142

Saca de la CPU el paso 2. Es la base de Vulkan para los pasos siguientes (composición de ventanas y swapchain directo).

- **Escritorio en memoria de la GPU:**
  - `ps5drv.c` (revisión en `tools/build-win32u-ps4.py`) pide la memoria del escritorio al sink con `pw_wine_screen_memory()`.
  - En la build de hardware el sink la reserva en Vulkan: memoria `HOST_VISIBLE | HOST_COHERENT | HOST_CACHED`, con caché de CPU para que GDI siga rápido.
  - En la PS4 la dirección de CPU es la misma que usa la GPU, así que la GPU lee el escritorio donde GDI lo escribe, sin subirlo.
  - Si no hay GPU, la función devuelve NULL y ps5drv usa `calloc`, como antes.
- **Buffers de VideoOut como imágenes Vulkan:** dos imágenes lineales 1280x720 en memoria `DEVICE_LOCAL | HOST_VISIBLE`, alineadas a 2 MiB y registradas con `sceVideoOutRegisterBuffers`. Es el mismo método que la prueba G001 (`native/vk_probe/main.c`), que ya se vio en la consola.
- **Un shader por cuadro** (`native/hw_sink_gpu/screen.frag`): escalado por vecino más cercano centrado, negro alrededor, alfa opaco y el mismo puntero de 11x17. Los bytes que escribe en el buffer son los mismos que escribe la copia por CPU.
- **Flip:** el hilo presentador espera la fence de la GPU y llama a `sceVideoOutSubmitFlip`, igual que antes.
- **Si algo falla:** cualquier error de Vulkan queda en el log como `PWSINK gpu_failed …` o `PWSINK gpu_draw_failed`, y el sink sigue con la copia por CPU sobre los mismos buffers, que la CPU también puede escribir.
- **Medición:** `PWSINK show_stats path=gpu|cpu n=… avg_us=… max_us=…` cada 300 cuadros.

El módulo es `native/hw_sink_gpu/hw_sink_gpu.c`. Usa el RADV que ya va enlazado en el ELF de hardware, y crea su propia instancia y dispositivo Vulkan. Los shaders se compilan en el build con el glslang de `~/vk-h0/host-tools`.

## Qué se espera

- El escritorio se ve igual que en W141: colores, posición, escala y puntero.
- En el log:
  - `PWSINK gpu_screen 1280x720 …`;
  - `PWBOOT video_out_ready … gpu=1 pitch=1280`;
  - `PWSINK show_stats path=gpu`, sin `gpu_failed`.
- El hilo presentador deja de copiar 1280x720 por cuadro. La GPU tarda poco (G001: ~1 ms con vsync), aunque el hilo sigue esperando esa fence.
- El trabajo del paso 1 sigue en la CPU (`flush_stats`). Es el próximo paso.

## Prueba física

Reporte: `reports/wine-hardware-w142/physical/20261103T090843Z`. Respuesta del usuario: "Se ve igual".

La ruta por GPU **no se activó**: lo que se vio es la copia por CPU de siempre.

- `PWSINK gpu_unavailable screen=0: CPU copy` aparece en la línea 12 del log, justo después del primer cuadro (`frame_presented n=1`, t=1,8 s). Ese cuadro es la pantalla de arranque del launcher y llega antes de que Wine empiece.
- El sink abre VideoOut con ese primer cuadro. En ese momento ps5drv todavía no pidió la memoria del escritorio, así que `gpu_screen` era NULL y `open_video` eligió la copia por CPU.
- `PWSINK gpu_screen 1280x720 memory_type=5 at 0x49ffbe0000` aparece más tarde (línea 1162). La reserva Vulkan funcionó: RADV creó el dispositivo y la memoria con caché quedó mapeada. Pero los buffers de salida ya estaban elegidos.
- No hubo ningún `gpu_failed`.
- El escritorio usó la memoria Vulkan (tipo 5) con GDI sin problemas visibles. Es la primera prueba de que GDI dibuja bien sobre memoria de RADV.

Medidas de la copia por CPU, como referencia para comparar:

| Medida | Valor |
|---|---|
| `show_stats path=cpu` | ~1,0 ms de promedio y 1,3–1,7 ms de máximo por cuadro (n=300…1500) |
| `flush_stats` | 0,4–1,3 ms de promedio y hasta ~19 ms de máximo |

## Corrección (W143)

Los buffers de salida por GPU ya no dependen de que exista el escritorio:
- `pw_sink_gpu_buffers` crea el dispositivo si hace falta. `device_init` corre una sola vez y lo comparten las dos funciones.
- El descriptor del escritorio se escribe cuando aparece la memoria (`bind_screen`), sea antes o después de los buffers.
- La pantalla de arranque, que no está en esa memoria, sigue por copia de CPU sobre los mismos buffers.
- `pw_sink_gpu_draw` devuelve error si todavía no hay escritorio.

Ver `HARDWARE_W143.md`.
