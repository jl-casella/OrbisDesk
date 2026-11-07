<a id="w142-salida-a-pantalla-por-gpu-fase-6-paso-1"></a>


# W142: display output by GPU (phase 6, step 1)

[English](HARDWARE_W142.md) | [Español](HARDWARE_W142-es.md)

APP_VER 02.41. Base W141.

<a id="dónde-se-va-el-tiempo-hoy"></a>


## Where the weather goes today

There are three works of CPU between what it draws Windows and the screen:

1. **Windows to the desktop:** `ps5drv.c` (`ps5_surface_flush`) copy each update of a window to your buffer, make up the area on the desktop (`compose_rect`) and tell the sink. It runs in the thread of Wine. It's what it measures `PWBOOT flush_stats`: in W140, 3,5 ms on average and up to 20 ms per update, with about 690 000 pixels.
2. **Desktop to screen:** the sink (`platform/ps4/pw_wine_sink_ps4.c`, `show()`) copies the full desktop, scale it, force the alpha and draw the pointer on one of the two VideoOut buffers. Then he does the flip. It runs on the present thread, up to ~ 60 times per second.
3. **Windows Vulkan (games):** the swapchain copies each memory image of CPU and `pw_vk_show_frame` it passes to the window by GDI. From there follow the steps 1 and 2.

In SuperMarioKart (~ 12 FPS these copies are not the brake:
- The game makes ~ 63 drawings Direct3D 7 per picture, which pass by wined3d in the CPU, with the log of active traces.
- The GPU takes ~ 2 ms per picture, and the copies add up a few ms of ~ 83.

The 6 phase points to the desk and windows.

<a id="qué-hace-w142"></a>


## What does W142

Get out of the CPU the step 2. It is the basis of Vulkan for the next steps (composition of windows and direct swapchain).

- **Desktop in memory of GPU:**
  - `ps5drv.c` (revision in `tools/build-win32u-ps4.py`) requests the memory from the desktop to the sink with `pw_wine_screen_memory()`.
  - In the hardware build the sink reserves in Vulkan: memory `HOST_VISIBLE | HOST_COHERENT | HOST_CACHED`, with cache of CPU so that GDI will continue fast.
  - In the PS4 the address of CPU is the same as the GPU, so the GPU reads the desk where GDI He writes it, without going up.
  - If there is no GPU, the function returns NULL and ps5drv uses `calloc`, as before.
- **Buffers of VideoOut as images Vulkan:** two linear images 1280x720 in memory `DEVICE_LOCAL | HOST_VISIBLE`, aligned to 2 MiB and recorded with `sceVideoOutRegisterBuffers`. It is the same method as the test G001 (`native/vk_probe/main.c`), which was already seen on the console.
- **One shader per box** (`native/hw_sink_gpu/screen.frag`): climbed by nearest centered neighbor, black around, opaque alpha and the same 11x17 pointer. The bytes you write in the buffer are the same as the one that writes the copy by CPU.
- **Flip:** the presenter thread awaits the fence of GPU and calls `sceVideoOutSubmitFlip`, as before.
- **If anything fails:** any error of Vulkan is left in the log as `PWSINK gpu_failed …` or `PWSINK gpu_draw_failed`, and the sink continues with the copy by CPU over the same buffers, which the CPU can also write.
- **Measurement:** `PWSINK show_stats path=gpu|cpu n=… avg_us=… max_us=…` each 300 pictures.

The module is `native/hw_sink_gpu/hw_sink_gpu.c`. Use the RADV that is already linked to the ELF hardware, and create its own instance and device Vulkan. The shakers are compiled in the build with the glslang of `~/vk-h0/host-tools`.

<a id="qué-se-espera"></a>


## What is expected

- The desktop looks just like in W141: colors, position, scale and pointer.
- In the log:
  - `PWSINK gpu_screen 1280x720 …`;
  - `PWBOOT video_out_ready … gpu=1 pitch=1280`;
  - `PWSINK show_stats path=gpu`, without `gpu_failed`.
- The presenter thread stops copying 1280x720 per box. The GPU takes little (G001: ~ 1 ms with vsync), although the thread is still waiting for that fice.
- The work of the pass 1 is still in the CPU (`flush_stats`). It's the next step.

<a id="prueba-física"></a>


## Physical test

Report: `reports/wine-hardware-w142/physical/20261103T090843Z`. User response: "It looks the same."

The route by GPU **was not activated**: what was seen is the copy by CPU of the same.

- `PWSINK gpu_unavailable screen=0: CPU copy` appears in the log line 12, just after the first picture (`frame_presented n=1`, t = 1,8 s). That picture is the boot screen of the launcher and it comes before Wine starts.
- The sink opens VideoOut with that first picture. At that time ps5drv still didn't ask for the memory of the desk, so `gpu_screen` was NULL and `open_video` chose the copy by CPU.
- `PWSINK gpu_screen 1280x720 memory_type=5 at 0x49ffbe0000` appears later (line 1162). The reserve Vulkan worked: RADV created the device and the cache memory was mapped. But the exit buffers were already chosen.
- There was no `gpu_failed`.
- The desktop used the memory Vulkan (type 5) with GDI without visible problems. It is the first proof that GDI draws well on memory of RADV.

Copy measurements by CPU, as a reference to compare:

|Action|Value|
|---|---|
| `show_stats path=cpu` |~ 1,0 ms average and 1,3 - 1,7 ms of maximum per frame (n = 300... 1500)|
| `flush_stats` |0,4 - 1,3 ms average and up to 19 ms of a maximum|

<a id="corrección-w143"></a>


## Correction (W143)

The output buffers by GPU no longer depend on the desktop:
- `pw_sink_gpu_buffers` create the device if necessary. `device_init` runs once and is shared by both functions.
- The desktop descriptor is written when the memory (`bind_screen`) appears, either before or after the buffers.
- The boot screen, which is not in that memory, follows by a copy of CPU on the same buffers.
- `pw_sink_gpu_draw` returns error if there is no desk yet.

See `HARDWARE_W143.md`.
