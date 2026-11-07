<a id="w143-salida-a-pantalla-por-gpu-orden-de-arranque-corregido-fase-6-paso-1"></a>


# W143: output to screen by GPU, corrected start order (phase 6, step 1)

[English](HARDWARE_W143.md) | [Español](HARDWARE_W143-es.md)

APP_VER 02.42. Base W142.

<a id="problema-en-w142"></a>


## Problem in W142

In W142 the route by GPU was not used. The sink opens VideoOut with the first picture, which is the boot screen of the launcher, and chooses the buffers at that time. He demanded that the memory of the desk already exist, but ps5drv asks for it a few seconds later. Detail in `HARDWARE_W142.md`.

<a id="cambio"></a>


## Change

- **`native/hw_sink_gpu/hw_sink_gpu.c`:**
  - `device_init` run once and use it both `pw_sink_gpu_screen` and `pw_sink_gpu_buffers`.
  - The buffers of VideoOut by Vulkan are created even if there is no desk yet.
  - The desktop descriptor is written when creating the memory (`bind_screen`), in any order.
  - `pw_sink_gpu_draw` fails with error if there is no desk yet.
- **`platform/ps4/pw_wine_sink_ps4.c`:**
  - `open_video` always try the buffers for GPU.
  - The pictures that do not come out of the desktop memory, such as the boot screen, are copied by CPU to those same buffers.
  - If you fail Vulkan, keep recording `PWSINK gpu_unavailable: CPU copy` and use the direct memory, as before.

<a id="qué-se-espera"></a>


## What is expected

- In the log:
  - `PWSINK gpu_buffer 0/1 …`;
  - `PWBOOT video_out_ready … gpu=1 pitch=…`;
  - then, `PWSINK gpu_screen …`;
  - `show_stats path=cpu` only in the first tables and then `show_stats path=gpu`;
  - No `gpu_failed` or `gpu_draw_failed`.
- The desk looks the same as in W142.
- Comparison of times: in W142 the copy by CPU took ~ 1,0 ms on average per picture. On the way by GPU that time becomes the wait of the fence.

<a id="prueba-física"></a>


## Physical test

Report: `reports/wine-hardware-w143/physical/20261103T095328Z`. User response: "It looks the same."

The route by GPU **was active**:
- `PWSINK gpu_buffer 0/1 memory_type=3 … row_pitch=5120` and `PWBOOT video_out_ready 1280x720 buffers=2 gpu=1 pitch=1280` appear in the lines 92 - 100, before it starts Wine.
- `PWSINK gpu_screen 1280x720 memory_type=5` appears in the line 1171.
- From the table 3 (line 1346) the pictures come out of that memory and are drawn with the shader.
- There was no `gpu_failed`, `gpu_draw_failed` or `gpu_unavailable`.
- The capture `screen.png` and user response match W142: colors, position, taskbar and clock.

No times yet:
- The session was short and with little activity: 64 paintings in ~ 49 s, against 1600 in W142.
- `show_stats` comes out every 300 paintings and `flush_stats` every 100, so neither of them came to appear.

The time measure with the GPU is left for the next build. It's gonna take a score with less pictures, or a longer session.
