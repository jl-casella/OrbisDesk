<a id="w155-programas-de-32-bits-sin-trazas-y-a-pantalla-completa-fase-6"></a>


# W155: 32 bit-free and full-screen programs (phase 6)

[English](HARDWARE_W155.md) | [Español](HARDWARE_W155-es.md)

APP_VER 02.54. Base W154, which was not tested either: it includes your change (the image Vulkan follows the window when moving it).

<a id="supermariokart-con-w153"></a>


## SuperMarioKart with W153

Reporte: `reports/wine-hardware-w153/physical/20261103T135602Z`, `run-0002.log`.

- **Start:** the game runs as a title apart from 32 bits, `cpu=wow64native`.
- **Presentation:**
  - the game uses DirectDraw/Direct3D 7, which wined3d draws with its render Vulkan (`WINE_D3D_CONFIG=renderer=vulkan`, No DXVK;
  - wined3d presents for `vkQueuePresentKHR` of win32u, so already use the path of W153: `show_frame … 800x600 … path=gpu_layer us=6–13`;
  - Some pictures take 12 - 13 ms because they wait for the desktop lock.
- **FPS** (`PWVK present fps`): between 7,6 and 24,7 (the most repeated value is 24,7), and they go down to ~ 12,5 towards the end. `blit_wait_us` ~ 0,49 ms.
- **Audio:** sounds (`PWAUDIO … peak=10331`).
- **Output:** `process_exit status=0xc000000d` at 83.
- **Log:** 429.035 lines in ~ 80 s, almost all of the traces left behind from the start-up (W131):
  - `trace+file` (`NtReadFile`/`ReadFile`): ~123.000;
  - `trace+ddraw`: `DrawIndexedPrimitiveVB` 67.000, `SetTexture` 65.000, `SetTransform` 24.000, etc.;
  - `trace+virtual`: ~28.000.

- **Display** (user: "it was not fullscreen, on your right there was a large black column"):
  - the game does not order full screen: `SetCooperativeLevel` with hors `0x8` (`DDSCL_NORMAL`), a window without edge of 800 × 600 in (0,0);
  - the title desk measures 1280 × 720, so the window looked 1: 1 up to the left, with black to the right and down.

<a id="cambio"></a>


## Change

- **Adjusted view in 32 bit titles:**
  - `native/wine_hardware.c` adds `WINE_PS5_FIT=1` when the program is PE32.
  - ps5drv (`present_screen`, road by GPU) calculates the binding of visible windows. If you start in (0,0), you pass that size to the sink as a desktop size, instead of 1280 × 720.
  - The sink scale that size at the output while maintaining the ratio: 800 × 600 remains in 960 × 720 centered, with black narrow bars on the sides.
  - The pointer is within that area: `pw_wine_pointer_area` (sink) and `pw_hw_pointer_area` (`native/hw_pad.c`).
  - Log: `PWBOOT fit_view WxH pointer=1` and `PWBOOT pointer_area WxH`.
  - The desk with explorer does not change, because it does not carry `WINE_PS5_FIT`.
- **Traces:** `native/wine_hardware.c` (`pe32_log`: `ddraw`, `file`, `virtual` and `section` go from `trace` to `warn`. They follow the warnings and errors of those channels. `trace+seh` and `trace+loaddll` are left, because they write little.

<a id="qué-se-espera"></a>


## What is expected

- SuperMarioKart occupies the screen (960 × 720 centered) and the pointer reaches the whole game.
- SuperMarioKart with a log of thousands of lines, not hundreds of thousands.
- If the traces limited the game, more FPS than in W153.
- When dragging glxgears, the image moves with the window (W154).

<a id="prueba-física"></a>


## Physical test

Reports: `reports/wine-hardware-w155/physical/20261103T141256Z` and `20261103T142029Z`.

- **Drag (W154):** the user tested glxgears and vkspin and responded "drawn well."
- **Close the app:** after closing glxgears, when opening WFM to launch SuperMarioKart, the app was closed.
  - The log is cut just finished loading WFM, no line `crash` and no report of GPU.
  - Already with glxgears closed the desk had 2 layers, so his image was no longer in the stack.
  - Repeated without opening before Vulkan programs, does not pass ("Now walked").
  - The case is not identified.
- **SuperMarioKart (`run-0003.log`):**
  - **Log:** 8.403 lines, against 429.035 in W153.
  - **FPS:** 15 - 18. No trace did not improve, so they were not the limit.
  - **It didn't go to full screen..** This time the game asked for exclusive mode (`DDSCL_ALLOWREBOOT`, that goes with `EXCLUSIVE`) a 800×600.
    - win32u emulates that mode: for the program the window measures 800 × 600, but on the actual screen it covers 1280 × 720.
    - `pw_vk_show_frame` passed the client area into program coordinates, (0,0) - (800,600, so the image was left in the corner again.
    - The binding of windows measured 1280 × 720, so `fit_view` returned to 1280 × 720 (before it had been adjusted to a window of 116 × 27).
  - **Output:** `status=0xc000000d` again at the end, as in W153.

W156 (`HARDWARE_W156.md` corrections.
