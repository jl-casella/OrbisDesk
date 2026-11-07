<a id="w160-tiempo-por-operación-de-wined3d-y-syscalls-por-hilo-fase-6"></a>


# W160: time per operation of wined3d and syscalls per thread (phase 6)

[English](HARDWARE_W160.md) | [Español](HARDWARE_W160-es.md)

APP_VER 02.59. Base W159.

<a id="para-qué"></a>


## What for?

W159 showed that in SuperMarioKart:
- the wined3d command stream thread passes 74% of the time in 32 bit code;
- the game thread passes 80% in about 59.000 syscalls per second.

There are two missing data:
- **In wined3d:** the 74% includes the time the thread turns without work (`YieldProcessor` up to `WINED3D_CS_SPIN_COUNT`, 2000 turns) before sleep. If that turn weighs, the limit is not wined3d but that gives you work.
- **In the game:** What syscall does so many times.

<a id="cambio"></a>


## Change

- **`tools/build-wined3d-hw.py` (new):**
  - the `wined3d.dll` weapon of 32 bits with `cs.c` revised, by the same method as `build-ddraw-hw.py`;
  - `tools/build-wine-hardware.py` puts it on the stage;
  - the command stream thread reports every 2 ° ² TSC ticks (~ 2,7 s):
    - `PWCS window kticks wall=… exec=… spin=… wait=… waits=…`: total time, running operations, turning with empty tail, and sleeping waiting for work;
    - `PWCS ops count/kticks: …`: the eight most expensive operations, with quantity and time, in thousands of ticks.
- **`tools/build-wow64native-ps4.py`:**
  - `Wow64SystemServiceEx` count each syscall and its ticks by thread (the first eight);
  - each ~ 2,7 s, `PWSYSCALL tid=… total=… count/kticks: …` with the six most frequent of each thread;
  - ntdll are by name and win32u as `w32:<id>`, which is translated with the list of win32u syscalls.
- **`native/wine_hardware.c`:** passes `PW_QPC_TSC_HZ` with `sceKernelGetTscFrequency()` in the 32 bit runs, for the wow64native profile to use the actual frequency (in W159 measured 22 GHz).

<a id="prueba-física"></a>


## Physical test

Report: `reports/wine-hardware-w160/physical/20261103T151524Z`, `run-0002.log` (SuperMarioKart, ~ 80 s). User's response: "I went the same way." ~ 16 fps.

**Reloj:** `tsc_hz=1594020272` (sceKernelGetTscFrequency).

**Command stream thread of wined3d (`PWCS`, 2 ³ ² window ticks 2,7 s):**
- **Time sharing:** performs operations 88 - 91%; turns with an empty tail less than 1%; sleep 7 - 10%. He's not waiting for a job: he's really busy.

|Operation|By window|Thousands of tickets|% of thread|Each|
|---|---|---|---|---|
| `BLT_SUB_RESOURCE` | 279–308 | 2,75–3,1 million | 64–71 % | ~6,2 ms |
| `DRAW` | 9.100–10.500 | 610.000–680.000 | ~15 % |~ 2,7 µs|
| `UPDATE_SUB_RESOURCE` | 12.600–14.300 | ~140.000 | ~3 % |~ 6 µs|
| `PRESENT` | 40–44 | ~65.000 | ~1,5 % | ~1 ms |

- With ~ 40 tables per window are about 7 2D copies per box, ~ 44 ms of the ~ 64 ms of the picture.

**Syscalls (`PWSYSCALL`):**
- **Game thread (0024):** ~ 147.000 by window, ~ 54.000 per second; 99% are `NtDelayExecution` (`Sleep` short), ~ 65% of your time. Wait for wined3d sleeping slowly; It's not work.
- **Other threads:** almost only `NtWaitForSingleObject` and `NtDelayExecution`, that is, you wait.

**Conclusion:**
- The neck is the 2D copies (`Blt` of DirectDraw): each cost ~ 6 ms in the thread of wined3d.
- The Vulkan blitter of wined3d (`vk_blitter_blit_supported`, `texture_vk.c` only accepts simple copies (`COLOR_BLIT` / `RAW_BLIT`) between resources with access of GPU. Those with key or alpha test color, or system memory surfaces, fall to the blitter of CPU: lower the image of GPU, copy and reupload it.
- It is most likely, but it is not confirmed: W161 records what these copies are.
