# W152: cuadros Vulkan como capa de la GPU (fase 6, pasos 2 y 3)

[English](HARDWARE_W152.md) | [Español](HARDWARE_W152-es.md)

APP_VER 02.51. Base W151.

## Problema

Hasta W151, cada cuadro que presenta un programa Vulkan, o DXVK sobre Vulkan, pasaba por la CPU:

1. El WSI headless de Mesa copia la imagen con la GPU a un buffer lineal que lee la CPU (W072/W074) y espera esa copia.
2. `pw_vk_show_frame` (win32u `vulkan.c`):
   - convierte RGBA a BGRA en la CPU si hace falta;
   - dibuja con `StretchDIBits` en la ventana: 0,8–1,6 ms a 1280×701 en W14x;
   - el flush de la ventana copia esos píxeles a su contenido.
3. El compositor apila las ventanas.

En un juego a pantalla completa, el paso 2 es trabajo de CPU en cada cuadro.

## Cambio

El buffer donde el WSI deja la imagen ya es memoria que la GPU lee. En la PS4, la dirección de CPU de esa memoria es su dirección de GPU. El compositor la lee directamente:

- **`native/hw_sink_gpu/hw_sink_gpu.c`:**
  - El dispositivo del sink activa `bufferDeviceAddress` (`VK_KHR_buffer_device_address`).
  - Al crear el pool, compara su dirección de GPU con la de CPU y lo deja en el log: `PWSINK gpu_address pool cpu=… gpu=… images=N`.
  - Sólo si coinciden (`images=1`) acepta capas que son una imagen fuera del pool, dada por su puntero.
  - Cada capa lleva ahora una dirección, un tamaño de origen y flags (imagen, RGBA).
- **`native/hw_sink_gpu/screen.frag`:**
  - Cada capa hace las dos lecturas, la del pool por índice y la de la imagen por dirección (`GL_EXT_buffer_reference`), y elige una sin ramas, como pide W149.
  - Una capa no-imagen lee en la dirección del pool, que es válida.
  - Las imágenes se escalan al rectángulo de la capa (vecino más cercano) y el intercambio rojo/azul de RGBA se hace en la GPU.
- **`platform/ps4/pw_wine_sink_ps4.c`:** `struct pw_wine_layer` con los campos nuevos, y `pw_wine_layer_images()`.
- **`tools/build-win32u-ps4.py`:**
  - **ps5drv:**
    - cada ventana guarda la última imagen Vulkan presentada y el área cliente en pantalla;
    - `present_screen` la pone como capa justo encima de la ventana;
    - `ps5_vulkan_frame` la registra y presenta;
    - `ps5_vulkan_forget` la saca.
  - **`vulkan.c`:**
    - `pw_vk_show_frame` primero intenta `ps5_vulkan_frame`, y si no la toma dibuja con GDI como antes;
    - `vkDestroySwapchainKHR` llama a `ps5_vulkan_forget` antes de destruir el swapchain, para que la GPU no lea memoria liberada.
  - El log `PWBOOT gpu_layers=… gpu_images=…` dice si el camino está activo.

Un juego a pantalla completa es el mismo caso: su capa cubre la pantalla. La CPU ya no copia, convierte ni compone ese cuadro.

## Límites

- La copia de la GPU al buffer del WSI sigue, y el present espera que termine (`blit_wait_us` en `PWVK present fps`). Lo que se elimina es el trabajo de la CPU.
- Si el sink falla o el pool no tiene la misma dirección de GPU y CPU, todo vuelve al camino de W151 (GDI y composición por CPU) con el motivo en el log.
- Una ventana Vulkan muestra su último cuadro hasta que el swapchain se destruye o la ventana se cierra o se oculta.

## Qué se espera

- `PWSINK gpu_address … images=1` y `PWBOOT gpu_layers=1 gpu_images=1`.
- `PWVK show_frame … path=gpu_layer us=N`, con N bastante menor que los 800–1600 µs de `gdi_us`.
- glxgears o vkspin se ven igual que antes, con colores correctos, en ventana y maximizados.

## Prueba física

Reporte: `reports/wine-hardware-w152/physical/20261103T133501Z`. Respuesta del usuario: "Se colgó o cerró".

- La comprobación de direcciones dio igual: `PWSINK gpu_address pool cpu=0x43f9f60000 gpu=0x43f9f60000 images=1`, `PWBOOT gpu_layers=1 gpu_images=1`.
- El primer cuadro por capas, con sólo el fondo, no terminó: `PWSINK gpu_failed vkWaitForFences(...) = 2` (timeout de 1 s).
- El sink volvió a la copia por CPU y ps5drv a la composición por CPU (`gpu_layers_off alloc`). El escritorio siguió, pero la GPU quedó colgada para los programas Vulkan que se abrieron después.
- En ese cuadro no había ninguna imagen: la lectura por dirección leía el pool. Lo único nuevo en la GPU era esa lectura.

**Causa probable:**
- El compilador de shaders de Mesa (ACO), en GFX7, lee una dirección de 64 bits que varía por píxel con instrucciones FLAT (`aco_select_nir_intrinsics.cpp`: `gfx_level >= GFX7 && address VGPR` → `Format::FLAT`).
- FLAT decide si una dirección es memoria global, compartida (LDS) o privada (scratch) según las aperturas que configura el driver del kernel (`SH_MEM_BASES`).
- En Linux, amdgpu las pone en direcciones altas. En la PS4 no tenemos evidencia de cómo están, y si quedan en 0 nuestras direcciones caen dentro de una apertura.
- Es una deducción del código de Mesa y del cuelgue; no está confirmada en el hardware.

Corrección en W153 (`HARDWARE_W153.md`).
