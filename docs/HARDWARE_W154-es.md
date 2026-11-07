# W154: la imagen Vulkan sigue a su ventana al moverla (fase 6)

[English](HARDWARE_W154.md) | [Español](HARDWARE_W154-es.md)

APP_VER 02.53. Base W153.

## Problema

En W153 (fotos del usuario), al arrastrar glxgears:
- el marco de la ventana se movía y su área cliente se veía blanca;
- la imagen Vulkan quedaba en la posición vieja, y volvía a su lugar recién al soltar.

Mientras se arrastra una ventana, el bucle de movimiento corre en el hilo del programa, así que el programa no presenta cuadros nuevos. La capa Vulkan conservaba el rectángulo del último cuadro presentado, y debajo se veía el contenido GDI de la ventana, que en un programa Vulkan nunca se pinta.

## Cambio

`tools/build-win32u-ps4.py` (ps5drv `ps5_WindowPosChanged`): cuando la ventana tiene una imagen Vulkan, en cada movimiento o cambio de tamaño su rectángulo pasa a ser el área cliente nueva (`new_rects->client`, en coordenadas de pantalla como `visible`). En un cambio de tamaño, el último cuadro se escala al área nueva hasta que llegue el siguiente.

## Qué se espera

Al arrastrar glxgears o vkspin, el último cuadro se mueve con la ventana, sin área blanca. Mientras se arrastra, la animación queda quieta, porque el programa no presenta.

## Prueba física

Pendiente.
