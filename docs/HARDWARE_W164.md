<a id="w164-staging-de-bajadas-en-memoria-con-caché-fase-6"></a>


# W164: cache-in-memory stacking (phase 6)

[English](HARDWARE_W164.md) | [Español](HARDWARE_W164-es.md)

APP_VER 02.63. Base W163.

<a id="problema"></a>


## Problem

The key color copies are made in the CPU. When the destination is the back buffer that the GPU just drew, wined3d the whole low (800 × 600). In W163 that costs ~ 44 ms, and it happens in the race. The downfall reads of a staging in memory without cache.

<a id="cambio"></a>


## Change

`tools/build-wined3d-hw.py`, `texture_vk.c` (`wined3d_texture_vk_download_plane`):
- **Staging memory:** is first ordered `HOST_VISIBLE | HOST_CACHED` (types 5 and 6 in PS4, consistent). If there is no, you use the memory from before.
- **Measurement:** `PWDOWNLOAD`, in the drops of 256 KiB or more (the first 40 and one in each 200 after), leave the tickets for each step:
  - wait for the GPU, which includes finishing the picture you are drawing;
  - mapear;
  - copy.

<a id="qué-se-espera"></a>


## What is expected

- The copy of the down in ~ 1 million ticks or less, like the up.
- The waiting is at the GPU, which cannot be avoided as long as these copies are made in the CPU. If it remains large, the next step is to make the copies with key color in the GPU, without lowering the back buffer.

<a id="prueba-física"></a>


## Physical test

Report: `reports/wine-hardware-w164/physical/20261103T160838Z`, `run-0002.log`. User response: "Faster."

**`PWDOWNLOAD`** (800 600, memory `0xe` with cache), in thousands of ticks:

| Paso |First|Next|
|---|---|---|
|Wait for the GPU| 17.436 | ~670–3.300 (0,4–2 ms) |
| Mapear | 47.838 | ~100–900 |
|Copy| ~1.077 | ~1.000 (~0,65 ms) |

- Each drop goes from ~ 70 million ticks (~ 44 ms) to ~ 3 - 5 million (~ 2 - 3 ms).
- **FPS** (`PWVK present fps`, one per second):
  - about 170 seconds in a row between 35,2 and 36,8;
  - after (another track or section) between 28 and 66, with the majority between 37 and 57;
  - before were 13 - 17 in the race.
- **`PWCS`:** the thread of wined3d runs 66 - 74 % of the time and sleep 23 - 31%. It's not saturated all the time.

|Operation|Thousands of tickets by window|
|---|---|
| `DRAW` |~ 1,13 - 1,17 million (the first)|
| `BLT_SUB_RESOURCE` |~ 1,02 - 1,08 million (~ 1.050 copies, ~ 1 ms each)|
| `PRESENT` | ~320.000 |

- **`PWVK cpu`:** to 36 fps, the thread it presents is to 94 % and the picture takes 27 ms. In the over part FPS, at 57% and 17,7 ms.

**W161 - W164** result for 32 games bits with wined3d and Vulkan:
- system memory up to the GPU: from ~ 33 ms to ~ 0,85 ms (W162 + W163);
- down from GPU: from ~ 44 ms to ~ 2 - 3 ms (W164)
- SuperMarioKart: from 13 - 17 fps to ~ 36 fps in race.
