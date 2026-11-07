<a id="w161-qué-son-las-copias-2d-de-supermariokart-fase-6"></a>


# W161: what are the 2D copies of SuperMarioKart (phase 6)

[English](HARDWARE_W161.md) | [Español](HARDWARE_W161-es.md)

APP_VER 02.60. Base W160.

<a id="para-qué"></a>


## What for?

In W160 the 2D copies (`WINED3D_CS_OP_BLT_SUB_RESOURCE`) are carried 64 - 71% of the thread of wined3d, ~ 6 ms each and ~ 7 per picture. Before you change anything, you have to know what copies they are and what way they go.

<a id="cambio"></a>


## Change

`tools/build-wined3d-hw.py`, `cs.c` (`wined3d_cs_exec_blt_sub_resource`): the first 80 copies, and one in each 200 then leave `PWBLT` with:
- the lags and the effect;
- the filter;
- format, size, rectangle, access (GPU/CPU) and use of each surface;
- where your data were before and after (`loc=antes->después`: texture in the GPU, system memory, buffer);
- if they are part of the swapchain;
- How long it took.

This shows if you go through the CPU blitter (key color, alpha test, system memory, scaling or format conversion) and what you should do: support them in the GPU or avoid travel GPU → CPU → GPU.

<a id="prueba-física"></a>


## Physical test

Report: `reports/wine-hardware-w161/physical/20261103T152548Z`, `run-0002.log`. User response: "Anduvo," and in the chat that is still slow.

**Each menu box makes these copies** (`PWBLT`, 100 recorded):

| Copia | Flags |Data|Each|
|---|---|---|---|
|2 - 3 spites (512 × 450, 468 × 152 back buffer game| `0x41010000`, color key |system memory → system memory (CPU)|1 - 3 million ticks (0,6 - 1,9 ms|
|Back buffer of the game (800 × 600) → swapchain buffer| `0` |system memory → texture only of GPU (`access=0x1`)|**~ 52 million ticks (~ 33 ms)**|

- The first key color copy on the back buffer is the lower of the GPU (n = 17: 206 million ticks, ~ 129 ms, once). From there the back buffer is in system memory, and all the following copies go by CPU.
- The rise from the back buffer to the swapchain goes through the "Upload" branch of `texture2d_blt`:
  - `wined3d_texture_upload_from_texture` → `wined3d_texture_vk_upload_plane`;
  - create a staging buffer with only `VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT`, map it, copy it with `wined3d_format_copy_data` and glue it `vkCmdCopyBufferToImage`.
- 1,9 MB in ~ 33 ms are ~ 58 MB/s.
- In RADV of PS4, the first type of memory visible from CPU is 2 (hors `0x6`, without cache). A memory copy without cache or a combination of scriptures goes at that speed. The types 5 and 6 (`0xe`) have cache and consistency, and are the ones that use the presentation pool since W144.
- The 32 bit mapping is direct (`VK_EXT_map_memory_placed` in win32u `vulkan.c`), without a copy of a shadow.

Test and measurement in W162 (`HARDWARE_W162.md`).
