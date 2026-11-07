<a id="w154-la-imagen-vulkan-sigue-a-su-ventana-al-moverla-fase-6"></a>


# W154: the image Vulkan follows your window when moving it (phase 6)

[English](HARDWARE_W154.md) | [Español](HARDWARE_W154-es.md)

APP_VER 02.53. Base W153.

<a id="problema"></a>


## Problem

In W153 (user photos), by dragging glxgears:
- the window frame was moving and its client area looked white;
- the image Vulkan was in the old position, and returned to its place only when it was released.

While a window is dragged, the motion loop runs in the program thread, so the program does not present new pictures. The layer Vulkan kept the rectangle of the last table presented, and below was the content GDI of the window, which in a program Vulkan is never painted.

<a id="cambio"></a>


## Change

`tools/build-win32u-ps4.py` (ps5drv `ps5_WindowPosChanged`): when the window has an image Vulkan, in each movement or size change its rectangle becomes the new client area (`new_rects->client`, in screen coordinates such as `visible`). In a change of size, the last table is scaled to the new area until the next one comes.

<a id="qué-se-espera"></a>


## What is expected

When dragging glxgears or vkspin, the last picture moves with the window, with no white area. As long as it is dragged, the animation remains still, because the program does not present.

<a id="prueba-física"></a>


## Physical test

Pending.
