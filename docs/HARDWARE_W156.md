<a id="w156-la-imagen-vulkan-en-el-área-cliente-real-con-su-proporción-fase-6"></a>


# W156: the image Vulkan in the actual client area, with its proportion (phase 6)

[English](HARDWARE_W156.md) | [Español](HARDWARE_W156-es.md)

APP_VER 02.55. Base W155.

<a id="problema"></a>


## Problem

In W155, SuperMarioKart asked for full screen exclusive to 800 × 600 and was seen in the corner with a black column. win32u emulates that mode: the program sees a window of 800 × 600, but in screen coordinates its client area covers 1280 × 720. The image was located with the passing area `vulkan.c`, which is in program coordinates. Detail in `HARDWARE_W155.md`.

<a id="cambio"></a>


## Change

`tools/build-win32u-ps4.py` (ps5drv):
- Each window keeps its client area in screen coordinates (`new_rects->client` in `WindowPosChanged`), the same as `visible`.
- `ps5_vulkan_frame` places the image in that area and uses the image of `vulkan.c` only if ps5drv does not yet know it.
- `fit_image`: the image occupies the area as large as possible, with its proportion and focus.
  - With 800 × 600 in an area of 1280 × 720 left in 960 × 720, focused.
  - A normal window, whose image measures the same as your client area, does not change.
  - While changing the size of a window, the last table is seen with its proportion until the next one comes.
- `fit_view` (W155) no longer fits windows of less than 320 × 200.

<a id="qué-se-espera"></a>


## What is expected

- SuperMarioKart in exclusive mode: the image centered at 960 × 720 with bars on the sides.
- In window mode at 800 × 600 in (0,0), as in W153: the same, thanks to `fit_view`.
- glxgears and vkspin, as in W155.

<a id="pendiente"></a>


## Pending

The closure of the app when opening WFM after using programs Vulkan (W155) remains without an identified cause. This building doesn't fix it.

<a id="prueba-física"></a>


## Physical test

It was not tested alone: it did not run on the console (no folder `w156`). It was tested within W157 (`HARDWARE_W157.md`).
