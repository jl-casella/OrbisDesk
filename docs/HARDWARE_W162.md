<a id="w162-staging-de-subidas-en-memoria-con-caché-fase-6"></a>


# W162: cache-in-memory staging (phase 6)

[English](HARDWARE_W162.md) | [Español](HARDWARE_W162-es.md)

APP_VER 02.61. Base W161.

<a id="problema"></a>


## Problem

In SuperMarioKart, each picture rises to GPU the back buffer of 800 × 600 from system memory, and that takes ~ 33 ms (W161) wined3d order for the staging buffer only memory `HOST_VISIBLE`, and in the PS4 that gives the type 2, without cache.

<a id="cambio"></a>


## Change

`tools/build-wined3d-hw.py`, `texture_vk.c` (`wined3d_texture_vk_upload_plane`):
- **Staging memory:** is first ordered `HOST_VISIBLE | HOST_CACHED` (type 5 or 6 in PS4, with cache and consistency). If there is no, you use the memory from before. The GPU reads that memory with consistency, as does the presentation pool from W144.
- **Measurement:** in the rises of 256 KiB or more (the first 40 and one of each 200 after), `PWUPLOAD` leaves the size, if the cache memory was used, its hors and the ticks of each step: create the buffer, map, copy, unmap.

The key color copies follow the CPU. Pass them to the GPU remains for later, if necessary.

<a id="qué-se-espera"></a>


## What is expected

- `PWUPLOAD … cached=1` with the copy pass well below ~ 52 million ties of W161.
- `BLT_SUB_RESOURCE` much cheaper in `PWCS`, and more FPS.

<a id="prueba-física"></a>


## Physical test

Report: `reports/wine-hardware-w162/physical/20261103T154053Z`, `run-0002.log`. User response: "The same."

**`PWUPLOAD`** (800 600, 1.920.000 bytes, memory `0xe` with cache), in thousands of ticks:

| Paso |First|Next|
|---|---|---|
| Crear | 375 | ~36 |
| Mapear | ~31.000 | ~31.000 (~19,5 ms) |
|Copy| ~1.000 | ~1.000 (~0,65 ms) |
| Desmapear | ~3 | ~3 |

- The copy is already cheap. The cost is in mapping: each rise mapeia again.
- `PWCS`: `BLT_SUB_RESOURCE` is still in ~ 2,6 millions of ticks per window (~ 60% of the thread).
- **FPS:** the most repeated value is 34,6 (17 seconds), against a maximum of 25,5 in W157 - W160. There are sections of 15 - 17, so the user noticed it the same.

**Cause of the mapping:**
- wined3d of 32 bits leaves the memory mapped only as long as the total mapped is 128 MB or less (`MAX_PERSISTENT_MAPPED_BYTES`, `wined3d_private.h`).
- The memory reserve Vulkan goes into blocks of 64 MB. With the new memory block with cache, the limit is passed, and from there `wined3d_bo_vk_unmap` demapia after each use.
- Each climb remap the entire block of 64 MB, with a map WoW64 to a fixed direction (`VK_EXT_map_memory_placed`).

Correction in W163 (`HARDWARE_W163.md`).
