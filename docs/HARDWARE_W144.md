<a id="w144-la-gpu-apila-las-ventanas-fase-6-paso-2"></a>


# W144: the GPU stacks the windows (phase 6, step 2)

[English](HARDWARE_W144.md) | [Español](HARDWARE_W144-es.md)

APP_VER 02.43. Base W143, where the screen output already passes through GPU.

<a id="qué-quedaba-en-la-cpu"></a>


## What was left in the CPU

With W143 the GPU weapon the output box from the desktop. The desk itself still composed it `ps5drv.c` in the thread of Wine. In every update of a window this happened:

1. copied the dirty region from the surface of the window at `window->pixels`;
2. With `compose_rect`, he made that region of the desktop row by row: the bottom, above each window that touches it, from the bottom up, and copy it to the desktop.

`flush_stats` measures the total: up to 19 ms per update in W142. Step 2 removes the second part.

<a id="cambio"></a>


## Change

- **Memory tool in GPU** (`native/hw_sink_gpu/hw_sink_gpu.c`:
  - It is a single buffer of 96 MiB with cache of CPU and visible for GPU. It's a little thin if `maxTexelBufferElements` it's a minor.
  - It has a first-fit in blocks of 256 bytes (`pw_sink_gpu_alloc` / `pw_sink_gpu_free`).
  - From there comes the content of each window, the wallpaper and the backup desk of W142.
- **Capes:**
  - A picture is a list of layers, from the bottom up, in a uniform buffer: rectangle on the desktop, position on the pool and strip.
  - The shader (`screen.frag`) takes, for each pixel on the desktop, the highest layer that covers it. If no one covers it, it puts black: it's the same rule as `compose_rect`.
  - The W142 desktop becomes a single layer picture.
- **`ps5drv.c`** (revisions W144 in `tools/build-win32u-ps4.py`):
  - If the sink draws by GPU (`pw_wine_layers()`), the contents of the windows and the background are reserved in the pool.
  - In that mode `compose_rect` does nothing, and each present sends the stack with `pw_wine_present_layers`: the background and each visible window, cut to its visible rectangle.
  - The surface copy at `window->pixels` (part 1) remains the same.
- **Sink** (`platform/ps4/pw_wine_sink_ps4.c`):
  - Save the last pile and draw it back when the pointer moves.
  - If a window is released, it is removed from the saved stack, so that it is not read free memory.
  - As in this mode there is no desktop to turn to BMP, the picture-turning keeps the output buffer already drawn. He does it only in the pictures that go to the log.
- **If you fail:** any pool, drawing or presentation failure leaves `PWBOOT gpu_layers_off <motivo>: CPU composition`. ps5drv then composes the complete desktop in the CPU and follows as in W143.

<a id="qué-se-espera"></a>


## What is expected

- In the log:
  - `PWSINK gpu_pool bytes=… max_texels=…`;
  - `PWBOOT gpu_layers=1`;
  - `PWBOOT frame_presented … layers=N`;
  - `PWSINK show_stats path=layers`, if the session reaches 300 pictures;
  - No `gpu_layers_off`, `gpu_failed` or `gpu_pool_full`.
- The desktop, the Start menu and the windows look the same as in W143. The windows move, overlap and close without leaving any remains.
- `flush_stats` low, because it no longer includes the composition. A session with a lot of activity (more than 100 updates) is needed to show up.

<a id="prueba-física"></a>


## Physical test

Report: `reports/wine-hardware-w144/physical/20261103T103359Z`. The session lasted about 158 s with quite a lot of activity: 16 128 tables presented, {15 700 window updates, 120 window movements. User response: "There are remains or blink," in detail "a black frame in panels, menus and windows; the rest ok, "and a picture.

**Operation:**
- `gpu_pool bytes=100663296 memory_type=5 max_texels=536870912`. The pool was complete: the limit of texels allows 2 GiB.
- `gpu_layers=1` and the wallpaper was left as a layer.
- There was no `gpu_layers_off`, `gpu_failed` or `gpu_pool_full`.

**Times:**

|Action| W142 (CPU) |W144 (layers in GPU)|
|---|---|---|
|`flush_stats` average| 0,4–1,3 ms | 0,06–0,13 ms |
|`flush_stats`| ~19 ms |0,8 - 1,4 ms (some peak of 8,6 ms)|
|`show_stats` average| ~1,0 ms | 0,6–0,95 ms (path=layers) |
|`show_stats` maximum| 1,3–1,7 ms |up to ~ 12 ms, few times|

The Wine thread now devotes about one tenth of the time to each window update. The presenter takes the same or less than before. The peaks of ~ 11 - 12 ms match pictures that also fly to BMP.

**The black frame:**
- In the overturned pictures (`frames/frame-000129.bmp`) there is an edge of 3 to 5 pixels exactly black (`0x000000`) around WineMine, of the Start menu and its submenus.
- They are pixels of the visible rectangle of the window that were never painted: the memory of the window begins at zero.
- With the composition by CPU they were not seen because `compose_rect` only redraw the regions the window commands (flush), so under an unpainted margin there was the background.
- With layers the GPU draws the full rectangle, and those zeros were coming out black.

It is corrected in W145, see `HARDWARE_W145.md`.
