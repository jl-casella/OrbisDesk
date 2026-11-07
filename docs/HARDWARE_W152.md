<a id="w152-cuadros-vulkan-como-capa-de-la-gpu-fase-6-pasos-2-y-3"></a>


# W152: tables Vulkan as a layer of GPU (phase 6, steps 2 and 3)

[English](HARDWARE_W152.md) | [Español](HARDWARE_W152-es.md)

APP_VER 02.51. Base W151.

<a id="problema"></a>


## Problem

Up to W151, each picture presenting a program Vulkan, or DXVK over Vulkan, went through CPU:

1. The WSI headless of Mesa copies the image with the GPU to a linear buffer reading the CPU (W072/W074) and awaits that copy.
2. `pw_vk_show_frame` (win32u `vulkan.c`):
   - turns RGBA to BGRA into the CPU if necessary;
   - draw with `StretchDIBits` in the window: 0,8 - 1,6 ms to 1280 × 701 in W14x;
   - the flush of the window copies those pixels to their content.
3. The composer stares the windows.

In a full screen game, the step 2 is work of CPU in each box.

<a id="cambio"></a>


## Change

The buffer where the WSI leaves the image is already memory that the GPU reads. In the PS4, the direction of CPU of that memory is its direction of GPU. The composer reads it directly:

- **`native/hw_sink_gpu/hw_sink_gpu.c`:**
  - The sink device is active `bufferDeviceAddress` (`VK_KHR_buffer_device_address`).
  - When creating the pool, compare your GPU address to that of CPU and leave it in the log: `PWSINK gpu_address pool cpu=… gpu=… images=N`.
  - Only if they match (`images=1`) does it accept layers that are an image outside the pool, given by its pointer.
  - Each layer now has a direction, a size of origin and lags (image, RGBA).
- **`native/hw_sink_gpu/screen.frag`:**
  - Each layer makes the two readings, the one of the pool by index and the one of the image by direction (`GL_EXT_buffer_reference`), and chooses one without branches, as requested W149.
  - A no-image layer reads in the direction of the pool, which is valid.
  - The images are climbed to the rectangle of the layer (nearest neighbor) and the exchange rojo/azul of RGBA is made in the GPU.
- **`platform/ps4/pw_wine_sink_ps4.c`:** `struct pw_wine_layer` with new fields, and `pw_wine_layer_images()`.
- **`tools/build-win32u-ps4.py`:**
  - **ps5drv:**
    - each window keeps the last image Vulkan presented and the client area on screen;
    - `present_screen` puts it as a layer just above the window;
    - `ps5_vulkan_frame` records and presents it;
    - `ps5_vulkan_forget` takes it out.
  - **`vulkan.c`:**
    - `pw_vk_show_frame` first try `ps5_vulkan_frame`, and if you don't take it draw with GDI as before;
    - `vkDestroySwapchainKHR` call `ps5_vulkan_forget` before destroying the swapchain, so that the GPU does not read free memory.
  - The log `PWBOOT gpu_layers=… gpu_images=…` says if the road is active.

A full screen game is the same case: its layer covers the screen. The CPU no longer copies, converts or composes that picture.

<a id="límites"></a>


## Limits

- The copy of the GPU to the WSI buffer follows, and the present expects it to end (`blit_wait_us` in `PWVK present fps`). What is eliminated is the work of the CPU.
- If the sink fails or the pool does not have the same direction of GPU and CPU, everything returns to the path of W151 (GDI and composition by CPU) with the motive on the log.
- A window Vulkan shows its last picture until the swapchain is destroyed or the window is closed or hidden.

<a id="qué-se-espera"></a>


## What is expected

- `PWSINK gpu_address … images=1` and `PWBOOT gpu_layers=1 gpu_images=1`.
- `PWVK show_frame … path=gpu_layer us=N`, with N much lower than 800 - 1600 µs of `gdi_us`.
- glxgears or vkspin look the same as before, with correct colors, in window and maximized.

<a id="prueba-física"></a>


## Physical test

Report: `reports/wine-hardware-w152/physical/20261103T133501Z`. User response: "It was hung or closed."

- The address check was the same as: `PWSINK gpu_address pool cpu=0x43f9f60000 gpu=0x43f9f60000 images=1`, `PWBOOT gpu_layers=1 gpu_images=1`.
- The first layer frame, with only the bottom, did not end: `PWSINK gpu_failed vkWaitForFences(...) = 2` (timeout of 1 s).
- The sink returned to the copy by CPU and ps5drv to the composition by CPU (`gpu_layers_off alloc`). The desk continued, but the GPU was hung for the Vulkan programs that were opened later.
- In that picture there was no image: the reading by direction read the pool. The only new thing in the GPU was that reading.

**probable cause:**
- The Mesa (ACO) shaker in GFX7 reads a 64 bit address that varies by pixel with FLAT instructions (`aco_select_nir_intrinsics.cpp`: `gfx_level >= GFX7 && address VGPR` → `Format::FLAT`).
- FLAT decides whether an address is global, shared (LDS) or private (scratch) memory according to the openings that make up the driver of the kernel (`SH_MEM_BASES`).
- In Linux, amdgpu puts them in high directions. In the PS4 we have no evidence of how they are, and if they remain in 0 our directions fall into an opening.
- It is a deduction of the code of Mesa and the hanging; It's not confirmed on the hardware.

Correction in W153 (`HARDWARE_W153.md`).
