<a id="w163-wined3d-de-32-bits-deja-mapeados-sus-bloques-de-memoria-fase-6"></a>


# W163: wined3d of 32 bit leaves its memory blocks mapped (phase 6)

[English](HARDWARE_W163.md) | [Español](HARDWARE_W163-es.md)

APP_VER 02.62. Base W162.

<a id="problema"></a>


## Problem

In W162, each rise of the back buffer of SuperMarioKart takes ~ 19,5 ms to map the staging buffer. wined3d of 32 bits unmapped after each use when the total mapped is 128 MB, and the next mapeo is again the entire block of 64 MB.

<a id="cambio"></a>


## Change

`tools/build-wined3d-hw.py`, `adapter_vk.c` (`wined3d_bo_vk_unmap`): in 32 bit the limit goes beyond 128 MB to 512 MB (eight blocks). In 64 bits it's still limitless, as before. They follow the staging with cache and `PWUPLOAD` of W162.

The limit exists not to spend the address space of a 32 bit process (2 GiB without `LARGE_ADDRESS_AWARE`). 512 MB still leaves the majority free. A game that needs more mapped memory will unmapped as before, without failing.

<a id="qué-se-espera"></a>


## What is expected

- `PWUPLOAD … map=` about 0 from the second rise.
- `BLT_SUB_RESOURCE` much cheaper in `PWCS`, and more FPS in the whole game.

<a id="prueba-física"></a>


## Physical test

Report: `reports/wine-hardware-w163/physical/20261103T155150Z`, `run-0002.log`. User response: "Faster."

- **`PWUPLOAD`:** the first 40 up still map in ~ 31 million tickets; from 200, `map=0–2`. When the total mapped down from the new limit, the block was mapped.
- **The rise of the back buffer to the swapchain** (`PWBLT flags=0 800x600`) fell from ~ 52 million ticks (W161) a 1,32 - 1,41 million (~ 0,85 ms).
- **The neck passed to the other side:**
  - one of every few key-colored copies of a small sprite (73 × 79) on the back buffer that the GPU just drew (`loc=TEXTURE_RGB`) costs ~ 68 - 73 millions of ticks (~ 44 ms);
  - the blitter of CPU first lower the entire back buffer of GPU;
  - `BLT_SUB_RESOURCE` is still in ~ 3,1 thousands of ticks per window, and the FPS of the race in 13 - 17.
- **The drop** (`wined3d_texture_vk_download_plane`:
  - wait for GPU;
  - mapped a staging order only as `HOST_VISIBLE` (without cache in PS4);
  - He reads it with the CPU. Reading memory without cache is even slower than writing it.

Correction in W164 (`HARDWARE_W164.md`).
