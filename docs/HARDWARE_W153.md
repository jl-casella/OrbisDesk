<a id="w153-lectura-de-imágenes-sin-flat-con-chequeo-previo-fase-6-pasos-2-y-3"></a>


# W153: reading images without FLAT, with prior check-up (phase 6, steps 2 and 3)

[English](HARDWARE_W153.md) | [Español](HARDWARE_W153-es.md)

APP_VER 02.52. Base W152.

<a id="problema"></a>


## Problem

In W152 the first layer painting hung the GPU. The probable cause is that ACO reads with FLAT instructions a direction of 64 bits that varies by pixel, and in the PS4 the FLAT openings are not configured. Detail in `HARDWARE_W152.md`.

<a id="cambio"></a>


## Change

- **`native/hw_sink_gpu/screen.frag`:**
  - The direction is armed as a uniform base (`packUint2x32` of the UBO) plus an offset of 32 bits per pixel converted with `uint64_t(uint)` (`u2u64`).
  - With this pattern, `ac_nir_lower_global_access` separates base and offset, and ACO, with the base in scalar records, uses MUBUF (`buffer_load_dword`), the normal memory instruction of GFX7, without opening.
  - Compile with `-DPOOL_ONLY`, the same file gives the shader of W151, without reading by direction (`screen_frag_pool.h`).
- **`native/hw_sink_gpu/hw_sink_gpu.c`:**
  - The device also activates `shaderInt64` and `VK_KHR_pipeline_executable_properties`.
  - When creating the pipeline with images, ask RADV for its compiled code (ACO IR and disassembled) and search for instructions `flat_`.
  - If there is no, use it: `PWSINK gpu_images shader=address flat=0`.
  - If there is, or if you could not read the code, use the shader without images and leave `PWSINK gpu_images off: …`. The tables Vulkan then return to GDI, as in W151.
- **`tools/build-wine-hardware.py`:** also compiles the shader `POOL_ONLY`.

So, a shader who reads with FLAT doesn't get to draw.

<a id="riesgo-que-queda"></a>


## Remaining risk

If the compiled code does not have FLAT and yet the GPU is hung, the cause was not FLAT. The symptom would be W152: `vkWaitForFences … = 2` in the first layer.

<a id="qué-se-espera"></a>


## What is expected

- In the log: `PWSINK gpu_images looked at …`, and `shader=address flat=0` or `off: …` with the motive.
- If activated:
  - the desk looks like in W151;
  - glxgears and vkspin look good in window and maximized;
  - appears `PWVK show_frame … path=gpu_layer`.

<a id="prueba-física"></a>


## Physical test

Report: `reports/wine-hardware-w153/physical/20261103T134857Z`. User response: "They look good" (glxgears and vkspin, in window and maximized).

- The check read the three representations of RADV (NIR, ACO IR and assembly) and did not find FLAT: `PWSINK gpu_images shader=address flat=0`. `gpu_layers=1 gpu_images=1`.
- There was neither `gpu_failed` nor `gpu_layers_off`, and the GPU did not hang. That confirms that in W152 the problem was reading by FLAT.
- **CPU per table Vulkan** (`show_frame … path=gpu_layer us`:
  - usually from 5 to 40 µs, against 771 - 1.600 µs of `gdi_us` in W14x to 1280 × 701;
  - Some pictures take 12 - 14 ms: they are waiting for the desktop lock while moving the window.
- **FPS to 1280 × 701** (`PWVK present fps`): a program went between 52 and 66, as in W149 (49 - 63, and another between 425 and 482. What limits the first is not the presentation.
- `show_stats path=layers`: 0,79 - 0,81 ms average with a window Vulkan On top, against ~ 0,6 ms without it.
- The picture continues to go through the copy that makes the GPU to the WSI buffer (`blit_wait_us`: ~ 0,11 ms to 300 × 300 and ~ 0,52 ms to 1280 × 701).

This makes the steps 2 and 3 of the phase 6 for glxgears (Zink) and vkspin. DXVK presents it by the same `vkQueuePresentKHR` of win32u, but it needs to be tested with a game, for example SuperMarioKart.
