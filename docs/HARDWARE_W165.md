<a id="w165-sprites-con-color-key-en-la-gpu-contador-de-fps-con-f12-y-tiempo-de-las-llamadas-vulkan-fase-6"></a>


# W165: key-colored spites in GPU, FPS counter with F12 and call time Vulkan (phase 6)

[English](HARDWARE_W165.md) | [Español](HARDWARE_W165-es.md)

APP_VER 02.64. Base W164.

<a id="sprites-con-color-key-en-la-gpu"></a>


## Spites with key color in the GPU

In W164, at ~ 36 fps, the HUD spites of SuperMarioKart remain copies of DirectDraw with a key color of origin (`SRC_CKEY_OVERRIDE`). The Vulkan blitter of wined3d does not accept them, and the blitter of CPU makes them:
1. lower the back buffer that the GPU just drew (copy ~ 0,65 ms, plus wait for the GPU);
2. copy the sprites in the CPU;
3. it goes up again (~ 0,85 ms).

It happens in each picture: `BLT_SUB_RESOURCE` sum ~ 6,6 ms per picture.

**Change** (`tools/build-wined3d-hw.py`, `texture_vk.c`, `vk_blitter_blit`): the key color copies are drawn in the GPU.
- The home rectangle is copied into a temporary image that can be sampled.
- It is drawn over the destination with a shader that discards the key color texels. The range is compared by channel, as it does DirectDraw.
- Render pass, pipeline, sampler and shaders (GLSL compiled with the `~/vk-h0/host-tools` glslang) are created once by device and format. View, framebuffer and temporary image are released when the command buffer is finished.
- **It only applies in:** 2D textures of 32 bits BGRA/BGRX, without multisample, with target target and origin with access of GPU.
- Any other case, or a mistake when setting up the pipeline, follows the blitter of CPU as before. There's `PWCKEY …` left in the log.
- The first three copies are recorded (`PWCKEY blit n`).

With the back buffer always in the GPU, the downfall, the rise and the waiting by frame disappear. It serves any program DirectDraw/Direct3D 7 with key color spites on a 3D scene.

**Risk:** is a new path of drawing in GPU. An error in the pipeline or Layout changes can hang the GPU, as it happened in W152.

<a id="contador-de-fps"></a>


## FPS counter

The user asked for it hidden when starting and with F12 to show or hide it, as MangoHud. MangoHud does not run in the programs of 32 bits (W127): it should be compiled for 32 bits and loaded as a layer in the device Vulkan of wined3d. The counter comes out of the composer:

- **`platform/ps4/pw_wine_sink_ps4.c`:**
  - `draw_fps` writes `FPS n.n` in yellow over black in the upper left corner of the output image, after the GPU or CPU drew it and before the flip;
  - the value is the presents per second of the program Vulkan, if any presented in the last 2 s; if not, the composer's paintings per second;
  - `pw_hw_fps_toggle` light it or turn it off (`PWSINK fps_overlay=…`);
  - `pw_wine_vk_fps` receives the value once a second and redraws.
- **`native/wine_vk_runtime.c`:** passes the presents per second that already measures (`PWVK present fps`).
- **`native/hw_pad.c`:** F12 of the keyboard (HID `0x45`) calls `pw_hw_fps_toggle`. The programs don't get that key.
- **`tools/build-wine-hardware.py`:** the sink is compiled with `native/` on the including route, by `hw_text.h`.

It's the same log counter. With MangoHud in 32 bits you could show more (times per picture, CPU, GPU), but it's a separate job.

<a id="medición"></a>


## Measurement

In W164 (~ 36 fps in race), the command stream thread of wined3d passes 76% of the time on the side of 64 bits, in ~ 800 calls Unix per second of ~ 1 ms each.

`tools/build-wined3d-hw.py`, `context_vk.c`: the amount and ticks of these calls are measured:
- `vkAllocateMemory`;
- `vkQueueSubmit`;
- `vkWaitForFences`;
- `vkCreateGraphicsPipelines`;
- `vkAllocateDescriptorSets`;
- `vkUpdateDescriptorSets`.

`cs.c` adds them to each window of `PWCS` as `PWCS vk count/kticks: alloc=… submit=… wait=… pipeline=… descset=… update=…`.

<a id="prueba-física"></a>


## Physical test

Report: `reports/wine-hardware-w165/physical/20261103T165431Z`, `run-0002.log`. User response: "Faster and better": the HUD looks good. The counter was lit with F12 (`PWSINK fps_overlay=1`).

**Spites in GPU:**
- `PWCKEY GPU colour-keyed blits for format 44`. The first copies are the background 800 × 600 (key 0) and the menu spites (key `0xff00ff`, magenta).
- `BLT_SUB_RESOURCE` down from ~ 1,02 - 1,08 million ticks per window (W164) to 0,28 - 0,34 millions, with more pictures by window.

**FPS** (`PWVK present fps`): in the race 31 - 53 (most 35 - 50); in the menu 46 - 82; in some sections 195 - 305, on almost static screens. In W164 they were ~ 36 stable in the race and 37 - 66 in the rest.

**Thread of wined3d:**
- **`PWCS`:** runs 60 - 69 % of the time and sleep 26 - 36%.
- **Operations:** `DRAW` (~19.500 by window, ~78.000 tickets ≈ 49 µs each) is the biggest; `PRESENT` Go second..
- **`PWCS vk` by window:**
  - `vkAllocateDescriptorSets` ~ 20.400 (~ 5,7 µs each);
  - `vkUpdateDescriptorSets` ~ 19.300 (~ 7,8 µs);
  - `vkQueueSubmit` ~ 180 (~ 84 µs);
  - `vkWaitForFences` 0–21;
  - New pipelines 12 - 71.
- **Profile of wow64native:**

| | Unix | Syscalls |Change of FS| 32 bits |Unix calls|
|---|---|---|---|---|---|
|Thread of wined3d| 23,6 % | 34,9 % | **17,9 %** | 23,6 % |~ 80.000 per second|
|Thread the game| — |64,6% (especially `Sleep`)| — | 28,6 % | — |

**Reading:** each call to Vulkan of a program of 32 bits passes next to 64 bits with two changes in the record FS (`sysarch`). With ~ 80.000 per second, only those changes take ~ 18% of the thread. prospero-win group the Vulkan calls of 32 bits to make less transitions; He's the next candidate.
