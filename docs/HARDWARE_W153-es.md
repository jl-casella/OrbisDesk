# W153: lectura de imágenes sin FLAT, con chequeo previo (fase 6, pasos 2 y 3)

[English](HARDWARE_W153.md) | [Español](HARDWARE_W153-es.md)

APP_VER 02.52. Base W152.

## Problema

En W152 el primer cuadro por capas colgó la GPU. La causa probable es que ACO lee con instrucciones FLAT una dirección de 64 bits que varía por píxel, y en la PS4 las aperturas de FLAT no se configuran. Detalle en `HARDWARE_W152.md`.

## Cambio

- **`native/hw_sink_gpu/screen.frag`:**
  - La dirección se arma como base uniforme (`packUint2x32` del UBO) más un offset de 32 bits por píxel convertido con `uint64_t(uint)` (`u2u64`).
  - Con ese patrón, `ac_nir_lower_global_access` separa base y offset, y ACO, con la base en registros escalares, usa MUBUF (`buffer_load_dword`), la instrucción de memoria normal de GFX7, sin aperturas.
  - Compilado con `-DPOOL_ONLY`, el mismo archivo da el shader de W151, sin lectura por dirección (`screen_frag_pool.h`).
- **`native/hw_sink_gpu/hw_sink_gpu.c`:**
  - El dispositivo activa también `shaderInt64` y `VK_KHR_pipeline_executable_properties`.
  - Al crear el pipeline con imágenes, pide a RADV su código compilado (IR de ACO y desensamblado) y busca instrucciones `flat_`.
  - Si no hay, lo usa: `PWSINK gpu_images shader=address flat=0`.
  - Si hay, o si no se pudo leer el código, usa el shader sin imágenes y deja `PWSINK gpu_images off: …`. Los cuadros Vulkan vuelven entonces a GDI, como en W151.
- **`tools/build-wine-hardware.py`:** compila también el shader `POOL_ONLY`.

Así, un shader que lee con FLAT no llega a dibujar.

## Riesgo que queda

Si el código compilado no tiene FLAT y aun así la GPU se cuelga, la causa no era FLAT. El síntoma sería el de W152: `vkWaitForFences … = 2` en el primer cuadro por capas.

## Qué se espera

- En el log: `PWSINK gpu_images looked at …`, y `shader=address flat=0` o `off: …` con el motivo.
- Si se activa:
  - el escritorio se ve como en W151;
  - glxgears y vkspin se ven bien en ventana y maximizados;
  - aparece `PWVK show_frame … path=gpu_layer`.

## Prueba física

Reporte: `reports/wine-hardware-w153/physical/20261103T134857Z`. Respuesta del usuario: "Se ven bien" (glxgears y vkspin, en ventana y maximizados).

- El chequeo leyó las tres representaciones de RADV (NIR, IR de ACO y ensamblador) y no encontró FLAT: `PWSINK gpu_images shader=address flat=0`. `gpu_layers=1 gpu_images=1`.
- No hubo `gpu_failed` ni `gpu_layers_off`, y la GPU no se colgó. Eso confirma que en W152 el problema era la lectura por FLAT.
- **CPU por cuadro Vulkan** (`show_frame … path=gpu_layer us`):
  - normalmente de 5 a 40 µs, contra 771–1.600 µs de `gdi_us` en W14x a 1280×701;
  - algunos cuadros tardan 12–14 ms: son esperas del lock del escritorio mientras se mueve la ventana.
- **FPS a 1280×701** (`PWVK present fps`): un programa anduvo entre 52 y 66, como en W149 (49–63), y otro entre 425 y 482. Lo que limita al primero no es la presentación.
- `show_stats path=layers`: 0,79–0,81 ms de promedio con una ventana Vulkan encima, contra ~0,6 ms sin ella.
- El cuadro sigue pasando por la copia que hace la GPU al buffer del WSI (`blit_wait_us`: ~0,11 ms a 300×300 y ~0,52 ms a 1280×701).

Con esto quedan hechos los pasos 2 y 3 de la fase 6 para glxgears (Zink) y vkspin. DXVK presenta por el mismo `vkQueuePresentKHR` de win32u, pero falta probarlo con un juego, por ejemplo SuperMarioKart.
