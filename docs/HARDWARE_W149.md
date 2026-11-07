<a id="w149-shader-de-capas-sin-divergencia-fase-6-paso-2"></a>


# W149: non-divergence layer shader (phase 6, step 2)

[English](HARDWARE_W149.md) | [Español](HARDWARE_W149-es.md)

APP_VER 02.48. Base W148.

<a id="problema"></a>


## Problem

The black frame around the windows (W144 - W148) follows the grid of 8 × 8 pixels of the GPU. It was produced by the layer shader when a block of 8 × 8 had pixels in and out of a window. Detail in `HARDWARE_W148.md`.

<a id="cambio"></a>


## Change

`native/hw_sink_gpu/screen.frag`:
- The loop always runs all the layers, from bottom up. `count` comes from push constants, so it's the same for all pixels.
- `texelFetch` is always run (index 0 when the layer does not cover the pixel), and the result is chosen with a selection: a layer that covers the pixel and is not "unpainted" replaces the above value.
- There is no `return` or `continue`. The pointer is also resolved with selections at the end.

The rule of composition is the same: the highest layer covering the pixel; black where none of them cover it and outside the desk area.

The cost is a reading per layer and per pixel. With 3 to 6 layers on a normal desktop is little for GPU.

Diagnostics of W146 - W148 are still active in this building (`flush_shape`, `layer_stack`, 40 ), to check the edges in the catches. They are taken out once confirmed.

<a id="qué-se-espera"></a>


## What is expected

- No black frame in the taskbar, menus or windows.
- In the overlaps, the edge of each window passes directly to the bottom or to the window below.

<a id="prueba-física"></a>


## Physical test

Report: `reports/wine-hardware-w149/physical/20261103T125915Z`. User response: the black frame left, but the first opening of the Start menu is very slow.

- There was no `gpu_layers_off` or `gpu_failed`: all use was by layers.
- `show_stats path=layers`: average 0,58 - 0,85 ms per block of 300 pictures, just like W144. Read all the layers in each pixel is not noticed.
- The slowness of the menu is the diagnoses: 38 BMP turned in the first 83 pictures, just when the menu is first opened (peak of 144 ms in the first block of `show_stats`), plus ~ 960 lines `layer_stack` / `layer` and 80 lines `flush_shape`.

The diagnoses are taken in W150 (`HARDWARE_W150.md`).
