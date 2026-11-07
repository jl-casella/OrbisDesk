<a id="w166-llamadas-vulkan-de-32-bits-en-lotes-fase-6"></a>


# W166: Vulkan calls of 32 bits in lots (phase 6)

[English](HARDWARE_W166.md) | [Español](HARDWARE_W166-es.md)

APP_VER 02.65. Base W165.

<a id="problema"></a>


## Problem

W165, SuperMarioKart: the command stream thread of wined3d makes 80.000 Unix calls per second, one for each Vulkan call. Each pass from 32 to 64 bit with two changes of the record FS (`sysarch`), and only that takes ~ 18 % of thread (profile wow64native).

<a id="cambio"></a>


## Change

The Vulkan call grouping of 32 bits of prospero-win is carried (LGPL- 2.1 +, the same commitment of Wine):
- the `winevulkan` PE of 32 bit caters calls that do not return anything;
- the Unix side reproduces them all in a single call, when one arrives that does return something (or when the tail is emptied).

**`tools/build-winevulkan-batch.py` (new):**
1. **Vulkan record:** verify that `vk.xml` and `video.xml` 1.4.357 they reproduce byte to byte the eight files that Wine generated (`vulkan_thunks.c/h`, `loader_thunks.c/h`, `include/wine/vulkan.h`, `vulkan_driver.h`, `vulkan-1.spec`, `winevulkan.spec`). They were downloaded, with the user's permission, from `github.com/KhronosGroup/Vulkan-Docs`, tag `v1.4.357`, to `~/.cache/wine`.
2. **Tree:** weapon `.deps/wine/winevulkan-batch/tree` with `tools/stage_vk_batch.py` of prospero-win, that:
   - copy the runtime (`wine/ps5/pw_vk_*` and `wine/ps5/vulkan/*`);
   - edita `loader.c`, `vulkan_loader.h` and `vulkan.c`;
   - Regenerates thunks and 385 called codecs.
3. **`winevulkan.dll` of 32 bits:** compiles 11 PE sources with the build-up and link command fixed (`make -n`) and left it in `out/winevulkan-batch`.

**`tools/build-winevulkan-ps4.py`:** the Unix side of ELF is compiled from that tree: `vulkan.c`, `vulkan_thunks.c` and the seven `*_unix.c` (reproduction, record format, descriptor templates, generated codecs).

**`tools/build-wine-hardware.py`:** put that `winevulkan.dll` in `syswow64` and in `i386-windows`.

**64 bit programs:** continue with the thunks normal (the grouping is `#ifndef _WIN64`) and his `winevulkan.dll` is still the one. The Unix table only adds one entry at the end.

**What does not carry:** the asynchronous version of prospero-win (reproduction in native threads). The Unix side does not announce `__wine_pw_vk_batch_async_v2`, so the PE uses the 2, synchronous version.

<a id="contador-de-fps-sólo-en-juegos-de-32-bits"></a>


## FPS counter only in 32 bit games

The user saw that F12 also showed the counter on the scout desk, and that's not what you want. In addition, in the 64 bit programs of the desktop (glxgears, vkspin) runs MangoHud, which uses the same key.
- **`platform/ps4/pw_wine_sink_ps4.c`:**
  - `pw_hw_fps_toggle` just take F12 in a 32 bit (`WINE_PS5_FIT` title, which it launches without MangoHud), and while a program Vulkan in the last 2 s;
  - in another case it returns 0 and changes nothing;
  - the counter is drawn only with recent presentations Vulkan, no longer with the composer's paintings.
- **`native/hw_pad.c`:** if the sink does not take F12, the key reaches the programs like any other, when it is pressed and released. So MangoHud he keeps getting it on the desk.

<a id="qué-se-espera"></a>


## What is expected

- **wow64native profile:** less Unix calls per second and less change time of FS in the wined3d thread.
- **Game:** more FPS in SuperMarioKart.
- **Risk:** is a large change in the Vulkan layer of the 32 bit programs. A playback error can misdraw or close the program.

<a id="prueba-física"></a>


## Physical test

Report: `reports/wine-hardware-w166/physical/20261103T172225Z`, `run-0002.log`. User response: "Faster, all right."

**The grouping was not active..** prospero-win It leaves it off unless the environment has `PW_VK_BATCH=1` (`pw_vk_batch_pe.c`, `initialize`), And the launcher didn't put it. The `winevulkan` He sent every call as before. Coincide with measurements:

|Thread of wined3d| W165 | W166 |
|---|---|---|
|Unix calls per second| ~80.000 | ~73.000 |
|Change of FS| 17,9 % | 16,4 % |

- **FPS of the race:** 27 - 53, similar to W165.
- **What was found:** the `winevulkan` of 32 bit rebuilt and the Unix side of the tree with prospero-win They work without the grouping, with the game and the desktop.

Activation in W167 (`HARDWARE_W167.md`).
