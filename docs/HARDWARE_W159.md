<a id="w159-perfil-de-wow64native-en-programas-de-32-bits-fase-6"></a>


# W159: wow64native profile in 32 bit programs (phase 6)

[English](HARDWARE_W159.md) | [Español](HARDWARE_W159-es.md)

APP_VER 02.58. Base W158, which was not tested separately: includes its arrangement of `dlopen`.

<a id="para-qué"></a>


## What for?

In W157, the command stream thread of wined3d of SuperMarioKart was at 90 - 97 % of a core, with 39 - 63 ms of CPU per frame. You need to know how much of that is 32 bit code (wined3d) and how much the 64 bit side: calls to Vulkan of winevulkan and RADV, and the syscalls.

<a id="cambio"></a>


## Change

`native/wine_hardware.c` adds `PW_NATIVE_PROFILE=1` in the runs PE32. It is the profiler that already brings `wow64native` (prospero-win):
- each 2 s, by thread, writes `PW_NATIVE_PROFILE version=2 tid=… tsc=… tsc_hz=… unix_calls=… syscall_calls=… unix_host_ticks=… syscall_host_ticks=… other_host_ticks=…`;
- when starting and once a minute, `PW_NATIVE_PROFILE cpu_clock_mhz=…`.

`upstream/prospero-win/tools/native_profile_split.py` distribute the time of each thread in:
- `unix%`: side of 64 bits within Unix (Vulkan and driver calls;
- `syscall%`: syscalls, including waiting in them;
- `other%`;
- `fs%`: change of the record FS in each transition;
- `guest%`: 32 bit code, plus time without CPU.

He also gives the calls a second.

The cost: a `rdtsc` and a few meters per transition, and a line per thread each 2.

<a id="qué-se-espera"></a>


## What is expected

- **If in the thread of wined3d dominates `guest%`:** the cost is wined3d. The output is another translation of Direct3D 7, as dgVoodoo2 and DXVK.
- **If it dominates `unix%`, with many calls per second:** the cost is the step at 64 bit of each call at Vulkan or the driver. It can be grouped or covered.
- **If it dominates `syscall%`:** the time goes in wait or synchronization.

<a id="prueba-física"></a>


## Physical test

Report: `reports/wine-hardware-w159/physical/20261103T145658Z`. User's response: "Everything was going."

**Sequence of W155 (`run-0001.log`):** notepad, WFM, a game DOS, glxgears, WFM. No `handle_syscall_fault` or closure. It's a single test, and the previous failure was intermittent.

**SuperMarioKart (`run-0002.log`):**
- Some 15 fps, with the thread that presents 87% (`PWVK cpu`).
- The frequency of the TSC reporting the profile is wrong (`tsc_hz=22072826350`): it qualifies against `CLOCK_MONOTONIC`, and in PS4 the clock identifiers of SDK do not match those of the kernel. Percentages, which are quotient of `rdtsc`, are worth. The rates per second of `native_profile_split.py` are inflated about 14 times.
- With the actual TSC (~ 1,59 GHz: 31,1 · 10 ¢ticks in 304 pictures to ~ 15,5 fps), between the second and last report of each thread:

|Yarn| 32 bits (`guest`) | Unix | Syscalls |Change of FS|Calls|
|---|---|---|---|---|---|
| 0048, command stream de wined3d | 74 % | 14,6 % | 6,4 % | 4,9 % |~ 1.395 Unix per frame (~ 6,7 µs each)|
|0024, game thread| 7,3 % | 0,2 % | 79,6 % | 12,9 % |~ 58.800 syscalls per second (~ 13,5 µs each)|

**Lectura:**
- In the thread of wined3d, for each picture of ~ 64 ms:
  - ~ 41 ms of CPU are 32 bit code of wined3d: 74% `guest`, discounted 13% that the thread was not in CPU;
  - ~ 9 ms are called to Vulkan on the Unix side;
  - ~ 3 ms are changes of FS.
- The step to 64 bits is not the main thing: what weighs is the work of wined3d, about 0,8 ms for each of the ~ 50 Drawing calls from the picture, which is a lot.
- The thread of the game spends almost all its time going in and out of syscalls, about 58.800 per second. It looks like an active wait (over wined3d or over a clock), but you don't know what syscall is.

**Next:** show what functions wined3d is the 32 bit thread in, and tell what syscalls the game thread does.
