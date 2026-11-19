# Shader compiles, frame time and the disk shader cache

[English](SHADER_CACHE.md) | [Español](SHADER_CACHE-es.md)

Games can lose frame rate during cutscenes and scripted fast camera moves and recover once control returns to the character. This was seen in Alan Wake's American Nightmare (OpenGL through Mesa Zink on RADV) and PES 2013 (Direct3D 9 through DXVK on RADV). Two different causes look alike on screen:

- **compile hitches**: a new material or effect needs a shader or pipeline that has not been compiled in this session, and one frame waits for the compile. Mesa is built with its disk shader cache disabled (`-Dshader-cache=disabled` in `tools/vk-h0/build-mesa*.sh`), so every pipeline compiles again in every session. DXVK 2.7.1 no longer has its own state cache, so RADV is the only place compiled pipelines could persist;
- **a sustained limit**: every frame of the scene takes longer than the cap allows, because the GPU or one of the game's threads is saturated. A cache does not help here.

04.27 adds a measurement that tells them apart, and an opt-in disk cache for RADV.

## The measurement: `PWPERF`

From 04.37 `PWPERF` is measured and logged only with traces on (`/data/orbisdesk/trace.txt`, see [release traces](RELEASE_TRACES.md#alpha-2-lines)).

RADV notes every `vkCreateGraphicsPipelines` (full and library), `vkCreateComputePipelines` and `vkCreateShadersEXT` create to the sink ([pipeline trace patcher](../tools/vk-h0/patch-mesa-pipeline-trace.py), [sink](../platform/ps4/pw_wine_sink_ps4.c)). DXVK's, Zink's and native Vulkan programs' pipelines all reach RADV in the title process, on whichever thread compiles them. Each note carries the create's time and whether RADV found the pipeline in a cache, and whether it read it from the disk cache.

Every 5 seconds while a program presents, the run log gets one line, independent of FPS LIMIT and frame generation:

```text
PWPERF window_ms=5001 frames=98 frame_us_avg=51020 frame_us_max=183400 over_50ms=61 over_100ms=1 hitches=1
  hitches_with_compile=1 worst_frame_compile_us=131000 compiles=34 compile_ms=812 compile_max_us=129800 cached=20
  disk=0 misses=14 miss_ms=790 gfx=12/640ms lib=22/172ms compute=0/0ms shader=0/0ms gpu_busy_pct=88
  cpu_cores_x10=31 present_thread_pct=97
```

(one line in the log; wrapped here)

| Field | Meaning |
| --- | --- |
| `frames`, `frame_us_avg`, `frame_us_max` | present-to-present intervals in the window, as the game sees them (before FPS LIMIT holds a present) |
| `over_50ms`, `over_100ms` | intervals of at least 3 and 6 vblanks |
| `hitches`, `hitches_with_compile` | frames over twice the previous window's average and at least 40 ms; those with at least 10 ms of compiles (any thread) since the previous present |
| `worst_frame_compile_us` | compile time inside the longest frame |
| `compiles`, `compile_ms`, `compile_max_us` | creates, their total and longest time |
| `cached`, `disk`, `misses`, `miss_ms` | found in a cache (memory or disk), read from disk, compiled, time spent compiling |
| `gfx`, `lib`, `compute`, `shader` | count/time per kind: full graphics pipelines, graphics pipeline libraries (DXVK and Zink link these quickly and build optimised pipelines in the background), compute, shader objects |
| `gpu_busy_pct` | share of the window the GPU spent on the title's GFX work (the same timestamp union as MangoHud's GPU load) |
| `cpu_cores_x10` | the process's CPU time in the window, in tenths of a core |
| `present_thread_pct` | the presenting thread's CPU share; -1 when another thread presented at the window's end. With Zink it is the game's GL thread; DXVK presents from its own queue thread |

Each create that takes 50 ms or more also gets a `PWPERF slow_compile kind=… us=… cached=… disk=…` line, at most 8 per window.

How to read it:

- hitches with compile time in them, `misses` and `miss_ms` high in the windows where the drop happens, then near zero after: compile hitches;
- almost every frame over 50 ms with few compiles: a sustained limit. `gpu_busy_pct` near 100 points at the GPU; a `present_thread_pct` near 100 with a lower GPU share points at that thread.

Limits: the time Zink spends in the guest before its pipeline reaches RADV (GLSL to NIR, NIR to SPIR-V) is not included. Compiles on background threads are counted in the frame they overlapped even when they did not block it; `hitches_with_compile` is a correlation, not proof. With two programs presenting at once the intervals mix.

## What the W303 Alan Wake run already shows

In run 0238 (W303, FPS LIMIT 30, frame generation on) the menu holds 150 presents a window (30 fps). In the slow windows `held=0` and `late` equals `presents` (66–109 a window): no present arrived early enough to be held, so every frame took longer than 2 vblanks, not just a few. The frame-generation lines that give the vblank span between released presents agree: 971 of them show 3 vblanks and 95 show 4, against 6 at 5 or more. That is a steady 15–20 fps rather than isolated long frames, so most of that drop is a **sustained limit**, which the disk cache cannot remove. Compile hitches may still add the occasional long frame; the `PWPERF` line settles both, and `gpu_busy_pct` against `present_thread_pct` says whether the sustained part is the GPU or the game's thread.

## The disk shader cache (opt-in build change)

A separate change enables Mesa's disk cache in the RADV build that Wine links (`VARIANT=wine` of `tools/vk-h0/build-mesa.sh`). Findings:

- **Build dependencies**: Mesa requires zlib or zstd for its cache. zlib is already found from the PS4 sysroot (`~/vk-h0/sysroot/lib/libz.a`, built by `build-probe.sh`) and already linked into the hardware ELF by `tools/build-wine-hardware.py`. zstd stays disabled; Mesa then compresses with zlib.
- **Zink cannot have its own cache**: Mesa refuses `shader-cache` on Windows hosts (`Shader Cache does not currently work on Windows`), and Zink is built as a Windows DLL. Zink's pipelines still reach RADV, so RADV's disk cache covers their final compile, which is the expensive part; Zink's own GLSL/NIR/SPIR-V work stays per session.
- **DXVK**: 2.7.1 has no state cache (its `dxvk.conf` has no such option); RADV's disk cache is what persists its pipelines too.
- **Cache identity**: RADV keys its cache with `-Dradv-build-id`. It was the fixed string `mesa-26.0.8-ps4-h0`, which would let a later build with changed Mesa patches reuse binaries compiled by an older one. The build now derives it from a hash of the patched Mesa sources and the cross file, so any change to the compiler or the port starts a fresh cache.
- **Location and size**: the title sets `MESA_SHADER_CACHE_DIR=/data/orbisdesk/shader-cache`, the database cache type (`MESA_DISK_CACHE_DATABASE=1`, 8 parts, so at most 16 open files), and a 256 MB cap compiled in (`-Dshader-cache-max-size=256M`); the database evicts the least recently used entries past it. An existing value in the environment wins. Creating `/data/orbisdesk/shader-cache.off` turns the cache off (`MESA_SHADER_CACHE_DISABLE=1`).
- **PS4 specifics**: every Mesa cache type maps an index file shared and sizes it with `posix_fallocate` first. On the PS4 an allocation error falls back to `ftruncate`, and a failed shared map to an anonymous one ([disk cache patcher](../tools/vk-h0/patch-mesa-disk-cache-ps4.py)); only the title uses the cache. Mesa also turns its cache off when the real and effective user differ. RADV logs once `PWCACHE radv disk_cache=on|failed|none type=… path=… max_mb=… uid=… euid=…`.
- **First-run cost**: misses compile exactly as before; each new pipeline is additionally compressed and written by one background queue thread. On later runs a hit replaces the compile with a read and decompression.

Nothing has been measured on hardware yet. A useful test is the same cutscene twice in a row, with the title restarted in between: the second run should show `disk` hits and lower `miss_ms`, and fewer `hitches_with_compile`. If its frame rate stays the same, the drop is the sustained limit described above.

## 04.28: what the first console runs showed, and the changes

Runs 0244–0246 on W303 with the 04.27 changes (`reports/wine-hardware-w303/physical/20261119T110411Z`), summed over the `PWPERF` windows:

| Run | Pipeline creates | Compile time | Disk hits | Misses | Of which shader objects |
| --- | --- | --- | --- | --- | --- |
| 0244: Alan Wake, first run, plus Portal 2 | 591 | 27.5 s | 4 | 576 | 306 (7.6 s) |
| 0245: Alan Wake, second run | 325 | 8.1 s | 28 | 290 | 282 (6.4 s) |
| 0246: Doom 3 | 119 | 3.4 s | 15 | 97 | 37 (1.3 s) |

- **The cache works for pipelines.** Pipeline libraries fell from 213 creates and 16.3 s in 0244 to 7 and 45 ms in 0245.
- **The cache was not where the launcher put it.** Mesa reads `MESA_SHADER_CACHE_DIR` and `XDG_CACHE_HOME` with `secure_getenv`. In the title's ELF the OpenOrbis libc's secure flag is set, so that returns NULL for every name. RADV then fell back to `$HOME/.cache` (`/data/wine-home/.cache/mesa_shader_cache_db`). The two RADV devices made before Wine sets `HOME` (the sink's and the launcher's Vulkan probe) got no cache at all (`PWCACHE … disk_cache=failed`). One of them is the sink's device, so frame generation's compute pipelines (~1.4 s) compile again on every launch. On the PS4 those lookups now use `getenv`: a title has no setuid boundary to protect.
- **Most remaining misses are shader objects.** RADV caches pipelines but compiles every `VK_EXT_shader_object` shader on each `vkCreateShadersEXT`. Zink uses shader objects on RADV, and Zink's own disk cache cannot exist in a Windows build. RADV now also caches unlinked SPIR-V shader objects in the same disk cache. The key covers the create info (code, entry point, stages, flags, specialization, push constant ranges, set layout hashes, required subgroup size) and RADV's device cache hash. A hit is created from the stored `vkGetShaderBinaryDataEXT` blob, and a stale entry falls back to compiling. Linked shaders, create infos with other `pNext` structures, and devices RADV would not cache for compile as before. Hits count as `cached`/`disk` in `PWPERF` ([shader object cache patcher](../tools/vk-h0/patch-mesa-shader-object-cache.py)).

### What limits the frame rate in Alan Wake

In run 0245 the menu holds 30 fps (`frames=150`, `held=150`). Gameplay windows show 55–85 frames per 5 s (11–17 fps), every frame over 50 ms, without compiles. In the same windows `gpu_busy_pct` is 15–23, the process uses ~2.8 cores (`cpu_cores_x10≈28`) and the presenting thread 3–4%. The GPU is therefore not the limit. The presenting thread is Zink's submit thread, not the game's thread, so its low figure does not clear the CPU.

Alan Wake is a 32-bit program in explorer's 32-bit world (`wow64native`, no translator), with Zink as a 32-bit DLL. Every Vulkan call Zink makes is its own 32→64-bit crossing with two FS switches. W165 measured that cost at ~18% of wined3d's thread at ~80,000 calls a second, and W167's call batching (`PW_VK_BATCH=1`) reduced it, but only for the relaunch: the world has never had it ([WoW64 investigation](investigacion-wow64-en-explorer.md)). The likely limit is one CPU-bound thread, the game's or Zink's, made heavier by the crossings. That is not proven yet. Two opt-in markers in `C:\orbis` (read by `native/wine_hardware.c` at launch; the log says `wow64world vk_batch=… native_profile=…`) let one run check it:

- `nativeprofile.txt` turns on wow64native's per-thread profile (`PW_NATIVE_PROFILE version=2` every ~2 s per 32-bit thread: Unix calls, syscalls, FS-switch time). The busiest thread, and how much of it is crossings, says whether batching can help.
- `vkbatch32.txt` turns the 32-bit Vulkan batching on in the world. It was tested only in the relaunch (W167–W169), never next to explorer's 64-bit guests. Compare `PWPERF frames` in the same scene with and without it.

## 04.30: what the per-thread profile showed

Runs 0252 (profile only) and 0253 (profile and the 32-bit Vulkan batching) on 04.29 (`reports/wine-hardware-w303/physical/20261119T144942Z`). Shares are of each thread's wall time from consecutive `PW_NATIVE_PROFILE version=2` lines: *guest* is 32-bit code, *unix* is Unix calls (Vulkan among them), and *sys* is system calls, waits included. These are typical gameplay windows of 0252 (55–85 frames per 5 s):

| Thread | Started by | Guest | Unix | Sys |
| --- | --- | --- | --- | --- |
| 0074, the game's main thread | the program | 70–85% | 0% | 15–30% |
| 00e4, Zink's driver thread | `libgallium_wgl.dll` | 50–60% | 22–25% | 15–25% |
| 00a8, wined3d's command stream | `wined3d.dll` | ~40% | ~10% | ~50% |
| 0084, Zink's submit/present thread | `libgallium_wgl.dll` | 1% | 3% | 95% (waiting) |

- Alan Wake is drawn through four layers in its process: Direct3D 9 → wined3d (OpenGL renderer) → Mesa WGL/Zink → Vulkan (RADV). It is on wined3d + OpenGL because the overlay's Render choice for it is `wined3d-gl`; with DXVK it lost the device after 5 frames on 04.08 (`reports/pop-phase-b/physical/20261116T211401Z/run-0165.log`).
- No single stage is at 100%. The game thread is closest. The game, wined3d's thread and Zink's thread each run part-busy and hand work to the next. The frame rate is set by that serial chain on Jaguar cores. The GPU (8–20% busy) is not the limit.
- Vulkan calls are ~25% of one of the three stages. That is why the batching (run 0253: same frame rate, no `PW_VK_BATCH fatal`) changed nothing visible.
- The next real gain is to remove layers: run the game on DXVK (Direct3D 9 → Vulkan, without wined3d's thread or Zink) once its device loss is understood, or on wined3d's Vulkan renderer. Neither is measured on the current build.
- The profile timed itself against a 20 ms measurement (3.43 GHz) where the TSC runs at ~1.6 GHz. The shares above are right, but rates and seconds in the lines were about 2× off. From 04.30, `nativeprofile.txt` also passes the kernel's TSC frequency (`PW_QPC_TSC_HZ`, as W160–W177 did).

## 04.32: the cache restarted the console with GTA San Andreas

On 04.31, opening GTA San Andreas (32-bit, DXVK) restarted the whole console twice (`reports/wine-hardware-w303/physical/20261119T175955Z`, runs 0263 and 0264). Both times it happened during the game's first Vulkan work, before its first frame. With `/data/orbisdesk/shader-cache.off` it plays (`20261119T181659Z`, run 0266).

**Cause.** RADV and ACO build the upper half of every pointer to descriptor sets, push constants and rings from a constant: the device's `address32_hi`. Upstream, that value is fixed for each GPU, so RADV's cache identity leaves it out. Crema reserves a new 4 GiB window for every device it opens, wherever the kernel finds room (`ac_drm_device_initialize`), and reports `address32_hi` from that window. Its value depends on what the process opened before. RADV's own clear and blit shaders and DXVK's internal pipelines are the same for every program. So GTA San Andreas's device, created after wined3d's probe devices, loaded entries that another device had compiled for a different window. Its shaders then addressed memory outside its own window.

**Fix** ([cache window patcher](../tools/vk-h0/patch-mesa-cache-va32.py)). On the PS4, `address32_hi` is part of RADV's cache UUID. That UUID keys the disk cache (both the main one and the builtin-shader one), `VkPipelineCache` data and shader binaries, so a hit can only come from a device with the same window. Each device logs `PWCACHE radv address32_hi=…`. Runs that repeat the same sequence, such as starting the same game after the same steps, get the same window and keep their hits. The new UUID makes every old entry unreachable.

A later improvement would be one 32-bit window per process, shared by every device. That would make hits independent of the order devices are opened. It is a change to Crema's address windows and is not part of this fix.

## 04.33: the 32-bit Vulkan call batching never ran in explorer's world

The 04.30 profile, recomputed with the console's TSC rate (1.594 GHz), puts numbers on the three stages of Alan Wake's frame in gameplay:

| Thread | 32-bit code | Calls to the 64-bit side | Syscalls |
| --- | --- | --- | --- |
| Game | 57–83% | ~100/s | 13,000–41,000/s at ~12 µs each, 17–43% of the time |
| Zink driver | 55–58% | ~228,000/s at ~1.1 µs each, ~25% of the time | ~220/s waits of ~1 ms |
| wined3d command stream | ~40% | ~6,000/s at ~18 µs | ~360/s waits of ~1.3 ms |

The game thread's syscall share rises exactly when its own code share falls. It spins in short system calls while it waits for the rest of the chain, so the chain also sets the frame rate. A quarter of Zink's thread goes to crossings into the 64-bit side, one per Vulkan call.

Run 0253 turned the batching on (`vkbatch32.txt`), and Zink's thread still made ~225,000 crossings a second. The batching never engaged. In explorer's world, every 32-bit program reaches winevulkan through the Khronos loader with MangoHud's implicit layer, and the loader passes on the program's create info with its own `VK_STRUCTURE_TYPE_LOADER_INSTANCE_CREATE_INFO` links still in `pNext`. The batch's guard treats any instance `pNext` as unsafe, so it turned the batching off for the whole process at the first `vkCreateInstance`. The W167 relaunch had no loader or layer in the 32-bit process, which is why batching worked only there.

`tools/build-winevulkan-batch.py` now lets the guard accept a chain made only of the loader's links. Any other structure, such as debug messengers or validation features, still turns the batching off. The marker stays opt-in until a console run shows the gain and a clean exit.

**Who it affects.** Every 32-bit program in the world that uses Vulkan:
- Alan Wake: wined3d over Zink, the overlay's `wined3d-gl` choice.
- Doom 3: OpenGL straight to Zink.
- GTA San Andreas, PES 2013, PES 2014, Portal 2 and GTA IV: DXVK.

64-bit programs keep Wine's plain calls (the batching is 32-bit only).

## 04.34: the batching engaged, and Alan Wake's game thread is the limit

On 04.33 (`reports/wine-hardware-w303/physical/20261119T200114Z`), run 0274 played Alan Wake without the batching and run 0275 with it. Both runs have two phases. In the first ~65 s, the overlay's 30 FPS limit holds every present for ~29 ms (`PWFPS … held_us_avg=29000`), so the limit sets the rate. In gameplay after that, nothing is held and the game runs at 8–19 fps. A run's average mixes the two phases, so it says nothing about the batching.

Gameplay only, from the per-thread profile:

| Thread | Without batching (0274) | With batching (0275) |
| --- | --- | --- |
| Zink driver: Unix calls per second | 192,680 | 80,960 |
| Zink driver: FS switching | 33% | 15% |
| Zink driver: waiting in syscalls | 30% | 31% |
| Game: own 32-bit code | 67% | 78% |
| Game: syscalls per second | 20,100 | 16,200 |
| Frames per 5 s | 42–85 (mean 65) | 46–95 (mean 70) |

The batching worked: Zink's crossings fell by 58%. Zink's thread was already waiting ~30% of the time without it, so it was not what held the frame rate. With the batching, the game thread waits less and spends 78% of its time in its own code. Whatever helps now has to take work off that thread. Gameplay frames rose ~7%, but the two runs played different stretches, so that is within the noise.

GTA San Andreas in run 0275 holds 124–125 frames per 5 s in play, as in run 0266 without the batching: 25 fps, the game's own Frame Limiter. Its main thread makes ~64,000 syscalls a second waiting on that limiter. Turning off Frame Limiter in the game's display options is needed before any change can show up there.

`tools/build-winevulkan-batch.py` now adds three log lines to the batching, each at most once per process:
- `PW_VK_BATCH on=1` when a process starts the batching;
- `PW_VK_BATCH off from the start` when `PW_VK_BATCH=1` was asked for but the layer environment or opcode mask keeps it off;
- `PW_VK_BATCH off for the rest of the process: unix call N (name)` when a call turns it off.

## 04.35: DXVK's device loss was an empty submission, not a GPU fault

Alan Wake on DXVK (04.08 run 0165, 04.33 runs 0276 and 0277), Left 4 Dead 2 (run 0266) and POP (run 0115) all ended the same way, a few frames in or later:

```text
radv/amdgpu: Failed to query the last GPUVM fault (-22).
err:   DxvkSubmissionQueue: Command submission failed: VK_ERROR_DEVICE_LOST
```

**What the lines mean.**
- RADV prints the first line only when a `vkQueueSubmit` returns an error, before it marks the device lost. The `-22` is Crema's answer to every GPUVM fault query: the PS4 has none (`ac_drm_query_gpuvm_fault_info` returns `-EINVAL`). The line says nothing about a fault.
- No `GPU hang?` line and no `gpu-fault.txt` came with it, so the GPU had not stopped.
- In Crema, every failing step of a submission with command buffers prints a `radv: … -> fail` line. None appeared.

**Cause.** The submission that failed had no command buffers. RADV sends a submission with only semaphores to `radv_amdgpu_cs_submit_zero`, which merges the semaphores it waits on into the queue's syncobj through sync files. Crema has no sync files, so those calls return `-ENOSYS`. That function then returns `VK_ERROR_DEVICE_LOST` without a line, except for a timeline point the GPU had already finished.
- A binary semaphore always lost the device.
- A timeline semaphore lost it whenever the GPU was still on that point. That race explains why it came after a few frames, or only when frames took longer (menus, overlay, mode changes).

**Fix** ([empty submission patcher](../tools/vk-h0/patch-mesa-empty-submit.py)). On the PS4, an empty submission waits on the CPU until its semaphores have signalled, as RADV's sparse-binding submission already does. It then signals its own semaphores from the queue's last submission, which Crema supports. The Vulkan runtime calls the driver only after every wait has been submitted, and the PS4's single GPU queue runs submissions in order, so the wait always ends. Any submission that still fails now prints `radv: vkQueueSubmit = <result>: N command buffers, N waits, N signals`.

## 04.35: 32-bit Vulkan batching on by default

From 04.35 the batching of 32-bit Vulkan calls is on by default in Explorer's world (04.33, run-0275: zink's calls fell 58% in Alan Wake, and Alan Wake and GTA SA ran and quit cleanly). The frame rate gain in Alan Wake is small, because its own game thread is the limit. To turn it off, create `C:\orbiskbatch32.off` and restart OrbisDesk; `vkbatch32.txt` is no longer read.
