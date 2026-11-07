<a id="w145-capas-en-gpu-sin-marco-negro-fase-6-paso-2"></a>


# W145: layers in GPU without black frame (phase 6, step 2)

[English](HARDWARE_W145.md) | [Español](HARDWARE_W145-es.md)

APP_VER 02.44. Base W144.

<a id="problema-en-w144"></a>


## Problem in W144

The windows and menus had a black frame of 3 to 5 pixels. It was the part of the visible rectangle that the window never paints. With the composition by CPU there you saw the bottom; with layers in GPU the memory was seen in zero. Detail in `HARDWARE_W144.md`.

<a id="cambio"></a>


## Change

- **Pixel "unpainted":**
  - While the GPU stacks the windows, the memory of a new or resized window begins with the value `0x01ff00ff` (`PS5_UNPAINTED` in `ps5drv.c`), not with zero.
  - GDI write the 32 bit pixels with alpha 0, so a painted pixel does not take that value.
  - The shader (`screen.frag`) treats that value as transparent and continues with the layer below. So it does the same thing as `compose_rect`: where the window did not paint, you see what is below.
- **Return to CPU:** if you move to the composition by CPU (`gpu_layers_off`, Those pixels become zero before you compose the desk.
- **Window released when redimensioning:**
  - Before, the sink took it out of the stocked pile and a picture redrawn by the pointer could come out without that window: a blink.
  - Now the saved pile is marked as old and is not drawn until ps5drv sends the new one, which comes immediately.

<a id="qué-se-espera"></a>


## What is expected

- No black frame. The windows and menus are seen as in W143, with the composition by CPU.
- The times remain as in W144: `flush_stats` 0,1 ms on average.
- No `gpu_layers_off` or `gpu_failed`.

<a id="prueba-física"></a>


## Physical test

Report: `reports/wine-hardware-w145/physical/20261103T110137Z`. User response: "Follow the framework."

The framework follows the same:
- In `frame-000192.bmp` (glxgears) the edge of the window goes `2d2d30`, `19191c`, `0a0a0a` and then 4 pixels `000000`
- Those pixels are not "unpainted." Wine initializes the surface of each blank window (`0xff`, `window_surface_create` in `dce.c`), and these arrive in a flush measuring zero.
- The hypothesis of W145 was incorrect. The correction is left (not annoying), but it was not the cause.
- The visible rectangle is the rectangle of the window (`get_visible_rect` in `window.c`), so that margin is inside the window.

**Next hypothesis (W146):**
- Wine the shape of the window (`shape_bits`: region, key color or alpha) passes on each flush, and `ps5drv.c` never used it.
- If the margin is out that way, in Windows it would be transparent.
- With the composition by CPU it probably didn't look because `compose_rect` only redraws the dirty regions. This is not verified.
- See `HARDWARE_W146.md`.
