# W156: la imagen Vulkan en el área cliente real, con su proporción (fase 6)

[English](HARDWARE_W156.md) | [Español](HARDWARE_W156-es.md)

APP_VER 02.55. Base W155.

## Problema

En W155, SuperMarioKart pidió pantalla completa exclusiva a 800×600 y se vio en la esquina con una columna negra. win32u emula ese modo: el programa ve una ventana de 800×600, pero en coordenadas de pantalla su área cliente cubre 1280×720. La imagen se ubicaba con el área que pasa `vulkan.c`, que está en coordenadas del programa. Detalle en `HARDWARE_W155.md`.

## Cambio

`tools/build-win32u-ps4.py` (ps5drv):
- Cada ventana guarda su área cliente en coordenadas de pantalla (`new_rects->client` en `WindowPosChanged`), las mismas de `visible`.
- `ps5_vulkan_frame` ubica la imagen en esa área y usa la de `vulkan.c` sólo si ps5drv todavía no la conoce.
- `fit_image`: la imagen ocupa el área lo más grande posible, con su proporción y centrada.
  - Con 800×600 en un área de 1280×720 queda en 960×720, centrada.
  - Una ventana normal, cuya imagen mide lo mismo que su área cliente, no cambia.
  - Mientras se cambia el tamaño de una ventana, el último cuadro se ve con su proporción hasta que llegue el siguiente.
- `fit_view` (W155) ya no se ajusta a ventanas de menos de 320×200.

## Qué se espera

- SuperMarioKart en modo exclusivo: la imagen centrada a 960×720 con barras a los costados.
- En modo ventana a 800×600 en (0,0), como en W153: lo mismo, gracias a `fit_view`.
- glxgears y vkspin, igual que en W155.

## Pendiente

El cierre de la app al abrir WFM después de usar programas Vulkan (W155) sigue sin causa identificada. Esta build no lo corrige.

## Prueba física

No se probó sola: no llegó a ejecutarse en la consola (no hay carpeta `w156`). Se probó dentro de W157 (`HARDWARE_W157.md`).
