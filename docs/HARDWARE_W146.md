<a id="w146-forma-de-las-ventanas-como-transparencia-con-diagnóstico-fase-6-paso-2"></a>


# W146: shape of windows as transparency, with diagnosis (phase 6, step 2)

[English](HARDWARE_W146.md) | [Español](HARDWARE_W146-es.md)

APP_VER 02.45. Base W145.

<a id="problema"></a>


## Problem

With the layers by GPU (W144/W145) the windows and menus have a frame of 4 black pixels (`0x000000`). Those pixels come in the flush at zero, so it's not unpainted memory (`HARDWARE_W145.md`).

<a id="cambio"></a>


## Change

- **Window shape (`ps5drv.c`, `apply_shape`):**
  - Wine passes on each flush the shape of the window: a bitmap of 1 bit per pixel of the surface, on where the window is seen. It leaves the region of the window, key color or alpha (`set_surface_shape` in `dce.c`).
  - While the GPU stacks the windows, the pixels out that way go to `PS5_UNPAINTED`, and the shader shows what's below.
  - `compose_rect` continues to ignore the form, as always.
- **Diagnosis (`PWBOOT flush_shape`):** the first 80 flashes to touch the left edge of a window are recorded, with:
  - the visible rectangle, the surface rectangle and the dirty rectangle;
  - if there is form and if it changed;
  - the raw values, with alpha, of the pixels 0, 1, 3, 4 and 5 of the left edge, at half height;
  - the value left in column 2.

<a id="qué-se-espera"></a>


## What is expected

- **If the margin is out of shape:** the black frame disappears and the log shows `shape=1`.
- **If there is no form (`shape=0`):** the edge values say what it paints Wine there, and the next step comes out of those values.

<a id="prueba-física"></a>


## Physical test

Report: `reports/wine-hardware-w146/physical/20261103T111131Z`. User response: "Follow the framework."

What shows the 34 `flush_shape` recorded (taskbar, Start menu and submenus, Computer window, a dialog):
- **Form:** in all, `shape=0`. No window has region, key color or alpha, so `apply_shape` He's doing nothing..
- **Left edge:** the pixel 0 of each window is `46464a` (ButtonLight and the 1 is `5a5a5f` (ButtonHilight), the standard 3D edge. The black edge is not inside the window.
- **Rectangles:** the rectangle of the surface always begins in (0,0) of the visible rectangle.

**Conclusion:**
- The 3 - 5 black pixels around each window are **outside** of your rectangle.
- It draws them another layer of the stack, approximately 4 larger pixels per side and in color 0. The color `Background` of the theme is also black.
- You still don't know which layer it is. W147 records the full pile (`HARDWARE_W147.md`).
