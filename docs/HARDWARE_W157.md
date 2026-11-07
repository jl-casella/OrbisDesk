<a id="w157-medición-de-cpu-por-cuadro-fase-6"></a>


# W157: measurement of CPU per frame (phase 6)

[English](HARDWARE_W157.md) | [Español](HARDWARE_W157-es.md)

APP_VER 02.56. Base W156, which was not tested separately: this build includes it (image Vulkan in the actual client area, with its proportion).

<a id="para-qué"></a>


## What for?

SuperMarioKart go to 15 - 18 fps (W155). What is already measured:
- **Presentation:** the image reaches the screen with 6 - 16 µs of CPU by table (`show_frame … path=gpu_layer`).
- **GPU:** each present waits 0,5 ms to have the GPU finish all the glued, including the table (`blit_wait_us`). The GPU is almost always out of work.
- **Logs:** with 8.400 lines instead of 429.000, the fps did not change (W155).

The limit is in the CPU: in the 32 bit code of the game, in wined3d or in the passage from 32 to 64 bits of each call. It's still missing which thread.

<a id="cambio"></a>


## Change

`native/wine_vk_runtime.c`: each second, next to `PWVK present fps`, the log adds:

`PWVK cpu process_pct=P present_thread_pct=T frame_ms=F`

- **P:** CPU of the whole process (`getrusage(RUSAGE_SELF)`), in% of a core. 100 is equivalent to a whole second occupied core.
- **T:** CPU of the thread it presents (`RUSAGE_THREAD`). In Direct3D 7 with wined3d is the thread of the command stream, which translates to Vulkan.
- **F:** average time between frames.
- If the kernel does not give those times, it is seen `PWVK cpu unavailable …` with the errno.

**How to read:**
- If T is close to 100, the neck is in wined3d or in calls to Vulkan.
- If P − T is close to 100, it is in the game thread: 32 bit code or your system calls.
- If none approaches 100, the game expects something: a timer or synchronization.

<a id="prueba-física"></a>


## Physical test

Report: `reports/wine-hardware-w157/physical/20261103T143810Z`, `run-0002.log` (SuperMarioKart, ~ 90 s, unopened before Vulkan programs. User response: "Full screen well."

**Display (W156):** the view follows 1280 × 720 (`fit_view 1280x720`), because the window in an exclusively emulated mode covers the screen, and the image of 800 × 600 is located focused with its proportion. The user confirms it.

**CPU:** 55 samples of a second with `frame_ms` < 80:

| |Average|
|---|---|
|Process|202% (two cores occupied)|
|Thread (command stream of wined3d)|90% (between 92 and 97% in the races)|
|Time per box| 60,9 ms (39 ms a 25,5 fps, 63 ms a 15,8 fps) |

- There are loose seconds with 0,2 - 10 fps and the thread from wined3d to 16 - 37 %: at that time the time does not go in that thread (resource load or compilation).
- `blit_wait_us` ~ 0,5 ms and `show_frame` 16 µs, as in W153.
- The output is again `status=0xc000000d`.

**Conclusion:**
- The limit is the command stream thread of wined3d. It is occupied all the time and spends 39 - 63 ms of CPU per picture in translation Direct3D 7 to Vulkan and make calls.
- The game thread uses the other ~ 100%. With the full command stream, wined3d makes the application thread wait active, so you don't know how much of that is game work.
- The GPU and the presentation do not limit.

The code of wined3d (32 bit) must be separated from the passage of each call to Vulkan by thunk WoW64 within that thread. to the 64 bit Unix side.
