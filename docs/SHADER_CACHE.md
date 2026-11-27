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

From 04.35 the batching of 32-bit Vulkan calls is on by default in Explorer's world (04.33, run-0275: zink's calls fell 58% in Alan Wake, and Alan Wake and GTA SA ran and quit cleanly). The frame rate gain in Alan Wake is small, because its own game thread is the limit. To turn it off, create `C:\orbis\vkbatch32.off` and restart OrbisDesk; `vkbatch32.txt` is no longer read.

## Experimental asynchronous empty submissions (local 04.47)

The [asynchronous patcher](../tools/vk-h0/patch-mesa-async-empty-submit.py), applied after the 04.35 fix, replaces its GPU-completion wait on supported PS4 GFX queues with a regular submission of the queue's already finalized, immutable cache-flush command stream. All original semaphore waits and signals are forwarded to the normal winsys path. Crema orders that submission after submitted prerequisites on its hardware queue; the CPU can continue without waiting for their GPU completion. No semaphore is discarded or signalled early. Other rings and queues without that command stream retain the CPU fallback; errors are propagated without retrying an accepted submission.

This targets unnecessary CPU/GPU serialization and may improve real frame rate where these waits are significant. It is not a measured FPS improvement or a hardware acceptance claim. The [host check](../tests/test_async_empty_submit_host.py) compiles the transformed function from the pinned Mesa archive and exercises binary/timeline forwarding, deferred signals, fallback and failures. It does not execute the PS4 driver or GPU.

The [diagnostics host check](../tests/test_perf_diagnostics_host.py) also compiles the native runtime and verifies that summaries still work with `pw_trace_level=0`, including timing totals and failures.

For an A/B control, create `/data/orbisdesk/perf-empty-submit-cpu.txt` before starting OrbisDesk to restore the CPU path; remove it and restart to use the asynchronous path. The launcher logs `PWPERF config ... empty_submit=cpu-control|async-gfx`. Compare the same save/scene with a warm shader cache, fixed renderer, resolution, cap and FG setting. The changed Mesa build identity starts a new cache, so a cold first run must not be compared with an old warm run.

`tools/build-wine-hardware.py --performance-diagnostics` enables bounded native summaries independently of `trace.txt`, while leaving verbose Wine channels and frame dumps under the existing trace switch. `PWPERF`, `PWFPS`, periodic `PWFG`, and `PWVK present` report frame intervals, compile work, pacing, generated-frame decisions, GPU generation time and WSI blit wait. `PWPERF` also counts intervals of at least 34 and 250 ms. `PWQUEUE` reports, about every five seconds of empty submissions, asynchronous/CPU counts, total and maximum host duration, waits and failures. Totals can overlap across threads; they are not GPU execution time. Quiet queues may not emit a final partial window. The option and patch hash are recorded in the package manifest. A package made with `--runtime-outside-package` relies on an already installed compatible `/data` runtime and is not a fresh-install package.

## Local 04.48: thread profiling and complete queue accounting

This diagnostic candidate retains the 04.47 submission policy. With `--performance-diagnostics`, it also enables the existing WoW64 profiler in Explorer's 32-bit world and passes the kernel TSC frequency. Every cumulative `PW_NATIVE_PROFILE version=2` report is accompanied by `PWTHREADPERF`: Wine/native thread IDs, wall timestamp, per-thread user/kernel CPU time, block-I/O counts, voluntary/involuntary context switches and page faults. The hook runs on that thread with host FS active. It is installed through an internal function pointer, so a base Wine diagnostic ELF has no unresolved callback import.

Compare two reports of the same thread: CPU-time delta divided by wall-time delta estimates its CPU occupancy. The remainder includes blocking and time descheduled, not just waits. Correlate this with the WoW64 guest/Unix/syscall wall-time buckets and frame windows; none of these values is a sampled call stack. Kernel block-I/O counts are not bytes, do not cover all cached I/O, and zero is not proof of no I/O. A failed `getrusage` emits `cpu_available=0` instead of fabricated counters. Sleeping threads report only after they return to a profiling boundary. This covers WoW64 threads, not every 64-bit/native worker.

`PWQUEUE` now reports its first use immediately, maintains lifetime totals and flushes every five seconds from a native monitor, including zero-use intervals. Program changes and process exits also flush partial windows. This closes the 04.47 ambiguity where a short burst followed by silence could produce no report. User feedback on 04.47 was better responsiveness with remaining drops; no controlled FPS gain or significant use of the asynchronous path was established. The new instrumentation itself adds overhead, so compare diagnostic runs with the same instrumentation before selecting another optimization.

## Local 04.49: process-local thread alerts

This experimental candidate replaces the server round trip for `NtAlertThreadByThreadId` and `NtWaitForAlertByThreadId` with a PS4 kernel event flag. One bit coalesces pending alerts and an atomic OR/CLEAR_PAT wait consumes it. It preserves wake-before-wait, zero-timeout consumption, finite and infinite waits, and interruption retries. Long finite waits use bounded microsecond chunks with the original deadline. Other Windows synchronization objects and cross-process handles retain their existing paths.

Wine uses these alerts behind `RtlWaitOnAddress`/`RtlWakeAddress*`, including contended SRW locks and condition variables. This targets sleeping and waking between application/graphics workers; uncontended user-space lock paths remain unchanged. How often a particular game reaches this path must be measured rather than inferred from the overall syscall bucket.

The [canonical overlay](../tools/wine_thread_alert.py) includes the [native implementation](../platform/ps4/pw_wine_thread_alert.inc.c) in Wine's Unix `sync.c`. Racing initializers publish one backend per entry and delete losing kernel objects. A creation failure permanently selects the original Wine auto-reset event for that entry; failures while setting or waiting remain failures. Like the original Wine table, entries persist for the process lifetime. Later resource exhaustion falls back to the server rather than pretending to create an event.

Create `/data/orbisdesk/perf-thread-alert-server.txt` and restart OrbisDesk to select the original server path for an A/B comparison. Remove it and restart for the kernel path. The launcher records `PWALERT config backend=kernel-event|server-control`. With performance diagnostics, each WoW64 thread report includes cumulative `PWALERTPERF` counts of native/fallback sets and waits, timeouts, errors, total wait TSC ticks and maximum wait ticks. Use counter deltas and the measured TSC frequency; elapsed waits include blocking and scheduling, not just execution cost. Native 64-bit threads do not acquire a periodic WoW64 report merely by using these functions.

The [host check](../tests/test_thread_alert_host.py) compiles the actual transformed Wine functions with a kernel event model. It exercises pending/coalesced alerts, a blocked waiter, 4096 two-thread handshakes, zero/finite/infinite deadlines, long timeout chunks, interruption and error handling, original-server fallback, 16 simultaneous initializers and the table boundary under undefined-behavior sanitization. These checks do not validate the physical PS4 event implementation. No real-FPS gain is established by the code or host test alone; correlate alert usage, context switches and frame intervals in matching hardware runs.

## Local 04.50: Vulkan housekeeping and FG preparation

The [batch overlay](../tools/wine_vk_batch_hotpath.py) skips producer-list locking when the accepted ticket prefix is already drained, skips producer reclamation when no producer has retired, and avoids descriptor-template metadata locking for unrelated calls. Reserved but unpublished tickets still wait, unread retired streams remain alive, and commands, wire codecs, ordering and synchronous driver calls retain their existing behavior. The retire counter is published before the retire flag; a race can delay reclamation but cannot free an active node. The [host check](../tests/test_vk_batch_hotpath_host.py) compiles the transformed functions with the original SPSC/framing implementation, including interleaved producers, publication gaps and pending retirement.

Performance builds enable the existing Vulkan batch/fallback counters. Normal batch and present summaries now log the first sample and every 300 presents, rather than each present; the fallback report names the eight most frequent unbatched APIs. `PW_VK_FASTPATH` counts the housekeeping paths skipped. These diagnostics identify remaining crossings; removing housekeeping does not itself eliminate the required Unix calls.

When any saved program has FG enabled, startup prepares its four compute pipelines and runs the existing ISA and fence probes before Wine starts, serialized with the loading-screen presenter. Explicit `framegen.txt` off/timing overrides are honored. The first source frame reuses initialization but still starts with empty image history. The [host check](../tests/test_framegen_prepare_host.py) covers reuse, failure shutdown, saved choices, overrides and startup accounting. `/data/orbisdesk/perf-fg-prewarm.off` restores lazy preparation for comparison. `PWFG prepare` records elapsed startup time; startup compilation gets a separate performance report. IR capture and FLAT inspection remain required, so this moves the compilation out of gameplay rather than claiming an FG pipeline cache hit. Periodic `PWFG shown_rate` reports are enabled with performance diagnostics: generated counts require completed flips, while the real-frame counter tracks observed source submissions.

The small PKG needs the matching updated **32-bit winevulkan.dll** in both runtime locations; uploading only that PKG leaves the PE housekeeping changes unapplied. Preserve the installed runtime and update only those two verified copies. This candidate does not add adaptive interpolation or change the 30-to-60 scheduler. Hardware performance and visual acceptance remain pending.

## Local 04.51: synchronous descriptor cache

The 04.50 hardware log `run-0006` attributed 11,499,129 of 11,752,506 synchronous fallbacks (97.84%) to `vkGetDescriptorEXT`. This identifies call volume, not an independently measured cost per call or a guaranteed FPS gain. Candidate 04.51 adds a bounded cache in each PE32 producer, keyed by device, descriptor type, size and descriptor values. Cache hits copy the descriptor before the API returns, including CPU destinations. No descriptor write is deferred. Unknown types, extension chains, oversized outputs and overlapping inputs retain the original path.

On a miss, a negotiated private batch operation executes two real driver queries with different initial output bytes after replaying the accepted prefix once. Equal output bytes identify driver writes; unchanged gaps preserve each caller's original bytes. Other differences disable caching. Resource destruction, memory rebinding/freeing and sparse binding advance a global generation before the operation. The first 16 hits per producer and every 4096th subsequent hit are audited against fresh driver results; a mismatch disables caching and returns the fresh result. The cache has 1024 sets and two entries per set per producer; it is process-local and discarded with the producer.

The [checked overlay](../tools/wine_vk_descriptor_cache.py), [cache core](../platform/ps4/pw_vk_descriptor_cache.h) and [PE adapter](../platform/ps4/pw_vk_descriptor_cache_pe.inc.c) retain standard batch v1/v2 framing. An older native runtime does not advertise the private capability, so the updated DLL uses its previous synchronous path. The native async backend is excluded from this optimization. `/data/orbisdesk/perf-descriptor-cache.off` disables the cache on the next start. `PW_DESCRIPTOR_CACHE` and `PW_DESCRIPTOR_TYPES` report cumulative usage alongside the periodic batch reports. The [host test](../tests/test_descriptor_cache_host.py) checks synchronous output, padding, keys, collisions, resource generations, audit shutdown, fallback and native packet validation under ASan/UBSan. Physical cache hit rate, performance and visual acceptance remain pending. Shader-cache policy and FG scheduling retain 04.50 behavior. Deployment requires the small PKG and both matching 32-bit winevulkan DLLs; the separate-process native helper is not part of this main-title performance test.

## Local 04.52: compilation policy and native exit acknowledgement

Physical 04.51 `run-0007` exercised the descriptor cache: 68.7% hits at present 3000, 3041 audits and no rejection. The recorded source-present rate was 29.18 FPS over 110.339 seconds, versus 23.29 over 90.365 seconds in 04.50; frames above 50 ms were 0.65% versus 22.09%. These are uncontrolled runs with different inputs, durations and additional cache warming, not an isolated causal FPS benchmark. FG pair admission rose from 55.6% to 93.8%; generated flips and source submissions remain distinct counters. The worst five-second window still included 359 pipeline creates and 804 ms of aggregate compilation work.

Candidate 04.52 requests an executable-specific `DXVK_CONFIG` section for `alan_wakes_american_nightmare.exe`: `dxvk.enableGraphicsPipelineLibrary=True` and `dxvk.numCompilerThreads=2`. In [DXVK 2.7.1's configuration](https://github.com/doitsujin/dxvk/blob/v2.7.1/dxvk.conf), True retains pipeline libraries but disables optimized pipeline compilation, and the thread setting bounds compiler workers. This trades potential GPU optimization for less CPU competition; new required shaders still compile, so no elimination of compilation hitches is claimed. Other executable names do not receive these options. Explicit process/launch environment configuration takes precedence; this experimental section overrides matching options in a game-local `dxvk.conf`. `/data/orbisdesk/perf-aw-pipelines.off` restores the original policy at next start. The [host check](../tests/test_aw_pipeline_profile_host.py) runs the actual upstream parser, pinned by digest, against the launcher's profile and unrelated executable names. RADV shader-cache identity and FG scheduling remain unchanged: 04.51 measured roughly 2 ms of FG GPU work and no budget shutdown, so this candidate targets the source cadence instead.

The same run exposed a separate teardown failure: the server marked guest threads terminated while rejecting SIGQUIT, then unloaded DLLs before those native threads stopped. The server now uses the existing thread-directed pthread mapping for SIGQUIT only when Wine's current raw handler is installed. It never uses a process-wide signal fallback. Registry critical sections mask SIGQUIT to prevent a terminated owner from deadlocking its exit destructor. A tagged, private extension of ThreadTimes acknowledges the native Wine exit boundary, with generation tokens to distinguish reused native thread IDs. Standard ThreadTimes callers and WoW64 syscall tables retain their previous interface. Before unloading guest code or resources, kernelbase waits for this acknowledgement from tracked threads. Unsupported, unknown or still-active execution retains the mappings and logs the reason; it does not report a successful unload. The existing WM_CLOSE grace period and forced-close fallback remain, so cooperative application shutdown is not claimed fixed by this change.

The [native overlay](../tools/wine_guest_quiesce.py), [wire structure](../platform/ps4/pw_thread_quiesce.h) and [guest guard](../platform/ps4/pw_guest_quiesce.inc.c) are canonical build inputs. The [host check](../tests/test_guest_quiesce_host.py) exercises the actual native registry, native/server completion distinction, thread-ID reuse, tagged/ordinary ThreadTimes, and refusal to unload on older, unknown or failing backends under ASan/UBSan. Hardware signal delivery, teardown, reopening games and performance remain pending. The small PKG requires the matching guest DLL closure, with the console's previous files backed up before replacement; uploading the PKG alone does not install the new guard.

## Local 04.53: optional compiler workers

The combined 04.52 pipeline profile produced green/magenta game rendering on the PS4 Pro Baikal (12.50). Disabling that profile restored normal colours while leaving the descriptor cache enabled. This isolates the combined profile, not either individual DXVK option. Physical runs also recorded native exit acknowledgement before guest unload and successful reopen cycles. Cooperative shutdown and universal compatibility remain unproven.

04.53 removes the hardcoded profile. GRAPHICS places **COMPILER THREADS** directly below **RENDERER**, with **AUTO / 2 THREADS**. Auto is the default and preserves existing DXVK configuration. The experimental two-worker choice emits only `dxvk.numCompilerThreads=2`; it never overrides graphics pipeline library policy. Help and the save notification explain that, like Renderer, the choice takes effect the next time the game starts. It is not a live adjustment or a promise of higher FPS, and has no effect on WineD3D or other non-DXVK renderers.

The overlay atomically saves `compiler.<executable basename>=2` in `C:\orbis\overlay.ini`; Auto removes that override. All saved executable sections coexist without applying one game's limit to another. Guest startup refreshes the environment before game DLL initialization, including both PE architectures; the separate-process native helper reads the same file before starting Wine. The matching helper and guest DLLs are required alongside the small PKG. Other per-game settings and shader-cache identity remain intact. FG preparation, admission and display scheduling retain the prior implementation.

[Parser checks](../tests/test_aw_pipeline_profile_host.py) use the original pinned DXVK parser; [overlay checks](../tests/test_compiler_overlay_host.py) cover persistence, unrelated settings, Auto and failed atomic saves; [guest checks](../tests/test_compiler_guest_host.py) exercise next-start refresh, guest allocation ownership and read/allocation failures. These host models and successful compilation do not establish console performance or separate-process acceptance for 04.53. Compare Auto and two workers on the same game section after reopening, checking colours, frame intervals and subsequent close/reopen behaviour.

### Unreleased follow-up: exception diagnostics

The existing first-eight guest exception trace now includes original general-purpose registers, up to sixteen instruction bytes and eight stack words through the existing safe memory-read helper. Unreadable memory is reported explicitly. The exception context and handler result remain unchanged. [Host checks](../tests/test_guest_fault_context_host.py) compile both context layouts and verify bounded reads, failed reads and context preservation. These diagnostics are not a fix for DXVK compatibility or shared DLL state, and successful host checks do not establish hardware exception-path acceptance.

## Local 04.54 candidate: timed waits and operation/frame correlation

L4D2 subsequently started and presented with DXVK/Vulkan in two 04.53 sessions, publishing Auto and then two-worker configuration at startup. The earlier startup exception was not reproduced; no new fix was deployed between those runs. Source-present rates in regular five-second windows were 25.84 and 23.97 FPS, with different scenes and cache history. These samples do not isolate the effect of worker count. Auto remains the default. In the Auto session, 44 of 55 detected hitches overlapped instrumented compilation; this is correlation, not a sampled blocked call stack.

The [timed-yield transformation](../tools/wine_delay_yield.py) preserves the yield before a nonzero, non-alertable `NtDelayExecution`, but omits two per-thread `getrusage` calls whose result is discarded. Zero-duration sleeps retain the original `NtYieldExecution` and its status. Alertable and infinite waits retain their original paths. [Tests](../tests/test_delay_yield_host.py) compare actual original/transformed functions for zero, relative, absolute, expired, interrupted, alertable and infinite waits. An FPS improvement is not established by this code change.

The package builder automatically runs [the operation builder](../tools/build-wine-optrace.py), using the proven Unix compile recipe and exact Wine signatures. Six Unix calls are observed: read, single/multiple wait, delay, yield and performance-counter query. The [recorder](../platform/ps4/pw_optrace.inc.c) uses the kernel TSC frequency and thread-local counters; diagnostics off takes a branch without reading the clock. Nested calls count only toward the outer observed operation. Original arguments, outputs, status and errno are retained. Read sizes are requested bytes; pending reads are not treated as completed I/O. At most three operation summaries per thread per five seconds and eight process-wide slow events per five seconds are emitted. These timings include blocking and descheduling. Reporting is enabled in this candidate's main title; the separate helper retains its existing trace-off policy.

Pipeline slow events now renew their bounded budget every five seconds and include monotonic timestamps and native thread IDs. `PWFRAME` records bounded source intervals above 100 ms and overlapping aggregate compile work; aggregate work can span several threads. `PWPERF` windows include end timestamps. This supports correlation with operation events without weakening Vulkan synchronization, skipping draws, altering cache identity or changing FG scheduling. [Recorder](../tests/test_optrace_host.py), [wrapper](../tests/test_optrace_wrappers_host.py) and [frame](../tests/test_pipeline_frame_trace_host.py) tests cover forwarding, pending/error cases, errno preservation, nested accounting and log bounds. Hardware performance, wrapper coverage and diagnostic overhead remain pending measurement on the matching candidate.

### Unreleased follow-up: effective workers and read stages

The two 04.54 L4D2 sessions used the same map and a similar route, according to the tester. Published two-worker and Auto settings do not establish the actual worker counts: DXVK 2.7.1 snapshots its configuration in a shared D3D9 instance, which OrbisDesk can retain after forced guest termination. The overlay now requests an OrbisDesk restart after compiler-policy changes instead of promising application merely by reopening a game. Environment messages explicitly say that the effective count is unverified. Performance builds enable DXVK's INFO worker announcements in the main title and separate helper; the 32-bit host preserves this diagnostic selection. Normal builds retain the previous warning/error policy and no game-local log files. A fresh title process avoids prior retained instances, but another DXVK client can initialize the shared instance first; actual worker evidence remains necessary. No per-device configuration refresh or DXVK DLL replacement is implemented by this follow-up.

[Read instrumentation](../tools/wine_read_trace.py) separates handle lookup, destination-buffer validation, I/O and completion processing within the original Unix `NtReadFile`. Independent `PWREAD` summaries cover file/socket/other/unknown calls, requested bytes, known inline bytes, asynchronous/pending outcomes, events, APCs and server completion delivery. These are not disk-bandwidth measurements: scheduling and blocking remain included, and delegated results are reported with unknown byte counts rather than inspecting an unsafe or pending IOSB. Slow-event budgets are now eight per operation per five seconds so background sleeps cannot exhaust read-event coverage. The recorder preserves status, outputs, errno and completion order. [Contract checks](../tests/test_read_trace_contract.py) compare the original and transformed pinned Wine function; [stage checks](../tests/test_read_stages_host.py) verify accounting and bounds. Cache keys, descriptor policy and FG scheduling are unchanged. No new package, hardware acceptance or FPS gain is established by these source changes.

### Follow-up: retire compiler controls and distinguish CPU/presentation waits

The 04.55 L4D2 test confirmed two actual compiler workers, without a demonstrated FPS advantage over the earlier requested-Auto reference. A saved per-game choice also cannot describe DXVK's retained shared instance reliably. The compiler selector and its persistence are therefore removed. Existing `compiler.*` rows are ignored and disappear on the overlay's next successful settings save. Startup cleanup removes only the marked OrbisDesk-generated `DXVK_CONFIG` suffix in both guest architectures and the separate helper, preserving explicit user options, including manual compiler settings. Restarting OrbisDesk is required to discard existing DXVK instances. [Migration](../tests/test_aw_pipeline_profile_host.py), [guest/helper](../tests/test_compiler_guest_host.py) and [overlay](../tests/test_compiler_overlay_host.py) checks cover cleanup, failure preservation and unrelated preferences. Shader caches stay enabled; their identities are unchanged.

In the measured 04.55 intervals after process time 160 seconds, the game's main thread occupied about 69% of one core while the presentation thread occupied about 5%; two-second counter intervals do not identify a blocked stack. The next diagnostic set adds `NtWaitForAlertByThreadId`, `NtAlertThreadByThreadId`, event set/reset and user message peek/wait calls to the existing exact-ABI wrappers. `PWPRESENT` independently measures time outside the presentation callback, metadata lock/work, preparation including FG, limiter and tail work. Time outside the callback includes producer, driver and scheduling work; preparation wall time is not FG GPU execution time, and the supplied blit wait can overlap the outside interval. Neither is reported as CPU time. [Recorder checks](../tests/test_present_trace_host.py) cover stage accounting, independent swapchains, logging exclusion, clock regression, errno and bounded output. These changes retain pacing, synchronization and FG scheduling. They prepare attribution for the next build and do not establish a hardware FPS improvement.

### Pending thread alerts (04.58 candidate)

The hardware sync replacement adds a process-local pending bit to thread alerts. An already queued alert is consumed in userspace; kernel event flags park threads only when no alert is ready. Waiter registration and signaling use sequentially consistent atomics. Kernel wakes are rechecked against the pending bit, so a stale kernel wake never creates an NT alert; repeated signals still coalesce, and finite waits retain one deadline across stale wakes and interruptions. Cross-process Windows event handles stay on their existing server path, including the per-entry server fallback selected when the native backend is unavailable. Kernel errors remain errors.

`PWPENDINGALERT` reports logical waits, immediate/armed ready cases, skipped kernel sets and stale wakes, alongside the existing kernel counters. The [host protocol test](../tests/test_thread_alert_pending_host.py) covers 65,536 ping-pong iterations, pending/blocked delivery, coalescing, races during initialization, relative/absolute/long deadlines, stale wakes, errors and fallback. This validates the protocol model, not PS4 speed. Hardware FPS benefit remains pending measurement; shader-cache identity, renderer policy and FG scheduling are unchanged.
