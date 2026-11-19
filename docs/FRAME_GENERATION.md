# Frame generation (experimental)

[English](FRAME_GENERATION.md) | [Español](FRAME_GENERATION-es.md)

Goal: show a game that renders about 30 frames per second at 60 displayed frames per second by inserting, between each pair of real frames, an image interpolated from those two frames. Only the image is used: no motion vectors, depth or engine changes. A generated image never advances the game's input, audio or simulation; it can only make motion look smoother, and it adds latency (below).

This work is staged. Stages 1 to 5 have run on a PS4 Pro (04.15 and 04.19, below): the counters show generated frames reaching the screen between real ones. **No smoothness gain is claimed** beyond those counters, and only for the game tested.

## Status

| Stage | What | State | Evidence |
| --- | --- | --- | --- |
| 1 | Observation: source timestamps, flip/vblank completion, rendered/generated/displayed counters | Implemented | PS4 Pro, 04.15 (W303 physical run 20261117T170454Z, run-0203): `period_us` 16 682–16 684, about 120 vblanks per 2 s, `status_failed=0`, `pending_max=0`. The vblank status layout is right |
| 2 | Ownership of two completed source frames | Implemented (copy on the presenting thread, waited on its own fence since 04.19) | 04.18 (run-0217, NFS Underground 2, 1366x768): the first copy was never seen finished and the generator turned off. 04.19 on PS4 Pro (W303 physical run 20261117T215143Z, run-0218, NFS Underground 2, 1024x768): `PWFG copy 0..2: fence=signalled` after 269–279 µs. The probe's event read `set` there, so the event alone works; what failed in 04.18 is not proven |
| 3 | Compute prototype: coarse/fine motion, one generated frame, GPU timing ("shadow": never shown) | Implemented | Host check passes on Mesa lavapipe (host reference only). Run-0218: about 120 generations per 2 s; average GPU time capture 247, coarse 198, fine 1 237, blend 233 µs (about 1.9 ms in all, against an 8 ms budget) |
| 4 | Display scheduler: generated and real frames in turn at measured vblanks, with fallback | Implemented | Run-0218: `display on reason=pair`, then 10 s windows of `pairs=278 alone=22`, `267/20`, `259/14`, `gave_up=0`. Image quality was not assessed from that run |
| 5 | Per-program switch in the overlay, MangoHud exclusion, history restarts | Implemented | Run-0218: the switch turned display on for the program. The MangoHud rectangle on the console has not been inspected frame by frame |
| 04.20 | MangoHud's FPS row shows the frames on screen while generated frames are shown | Implemented | Compile-checked: native sink and telemetry for the PS4 target, MangoHud `hud_elements.cpp` for x64 and i386. Not run on the console |

## Switch

From 04.37 the periodic `PWFG` reports (`display pairs`, `gpu_us`), `display on|off`, `shown_rate`, the start-up probes and `target sc=` appear only with traces on (`/data/orbisdesk/trace.txt`, see [release traces](RELEASE_TRACES.md#alpha-2-lines)). Failures, `PWFG config`, `PWFG ready` and `PWFG mode=` always log.

Off by default, per program. The overlay's **FRAME GEN** entry (`GENERAR CUADROS` in Spanish, L3+R3, after FPS LIMIT) turns it on or off with X for the last program opened that is still open, as STRETCH does. The choice is saved in `C:\orbis\overlay.ini` as `framegen.<exe>=on` (off writes no line), applies at once, and comes back when that program starts again (`PWOVERLAY framegen=on program=<exe> why=start`). It shows generated frames only while [FPS LIMIT](FPS_LIMIT.md) holds the program at 30, which is the default for every program since 04.18. At 60, Off, or Auto at 60, it neither generates nor shows anything.

The file `/data/orbisdesk/framegen.txt` is no longer needed. It stays as a debug override, read once when the sink shows its first frame (with the kernel's own open first, then libc's). When the file is present, it decides for every program and the overlay's choice is ignored:

| Content | Effect |
| --- | --- |
| absent | The overlay decides per program. Without the file, the 2 s timing lines below are not written |
| `off` | Off for every program, whatever the overlay says. Timing lines on |
| `timing` (or any other word, or empty) | Stage 1 only: timing lines every 2 s, nothing generated |
| `shadow` | Stages 1–3: every present of the followed swapchain is copied and a frame is generated between it and the previous one; the generated frame is **not shown** |
| `display` | Stages 1–4 for every program, as if the overlay had it on everywhere, with timing lines |

Any failure in stages 2–3 logs a `PWFG failed ...` line with the Vulkan result, frees everything the generator made (`PWFG off for this run`, then `PWFG generator off for this run: real frames only from now on`), and leaves the display path as it was.

## Stage 1: what is measured

The Vulkan runtime calls a hook on every present, on the presenting thread, after Mesa's headless WSI has finished its copy into the CPU buffer ([wine_vk_runtime.c](../native/wine_vk_runtime.c) `pw_vk_present_hook`). The hook is a pointer: links without the sink, such as the PoP child, leave it empty. The sink ([pw_wine_sink_ps4.c](../platform/ps4/pw_wine_sink_ps4.c)) records per swapchain the time of each present. Each submitted flip is tagged with the present count Wine had handed over when it was drawn. Before each flip, the sink reads VideoOut's flip status (last completed flip and its time) and vblank status (vblank count and time).

Every 2 s:

```text
PWFG timing window_ms=… vblanks=… period_us=… flips_submitted=… flips_done=… new_frames_shown=… repeat_vblanks=… flip_latency_us_avg=… flip_latency_us_max=… pending_max=… status_failed=… generated=… generated_failed=… generated_shown=… mode=…
PWFG source sc=… WxH format=… intervals=… rate_x10=… interval_us_avg=… sd=… min=… max=… vblank_spans=<0.5,1,2,3,4,5+>
```

| Field | Meaning |
| --- | --- |
| `vblanks`, `period_us` | Vblanks in the window and their measured period. The refresh rate is not assumed |
| `flips_submitted`, `flips_done` | Flips the sink submitted and flips VideoOut reports completed |
| `new_frames_shown` | Completed flips that carried a new Vulkan present: rendered frames that reached the screen |
| `repeat_vblanks` | `vblanks - flips_done`: vblanks that showed the previous buffer again |
| `flip_latency_us_*` | Submit to completion for the newest completed flip, as read at each poll |
| `generated`, `generated_shown` | Stage 3 frames made, and generated frames the presenter flipped (stage 4). A generated flip does not count in `new_frames_shown`; the real flip after it does |
| `vblank_spans` | Source frame intervals rounded to vblank periods. A steady 30 FPS game shows its intervals in the `2` bucket |

Limits of this measurement: the flip status is read when the sink is about to flip, so two flips completing between reads count once each, but only the newest has a time. The vblank status layout is declared locally (the SDK declares the function without parameters), so a first run must confirm that `period_us` is close to 16 683 and that `status_failed` is 0. The present counter is global: with two Vulkan programs presenting at once, `new_frames_shown` mixes them.

The existing sink is the baseline to measure: its asynchronous presenter sleeps 16 ms after each frame it shows. On 04.15 (run-0203) Portal 2 in front still completed 101–117 flips per 2 s, nearly all of them new frames. At 115–140 presents per second only about 57 new frames per second reached the screen, so about half of what was rendered was never seen. `new_frames_shown` is 0 only where no Vulkan frame is on screen, for example the desktop or a GDI window. Stage 4 replaces the fixed sleep with waits on the flip status, but only for the frames it shows as pairs.

## Stage 2: ownership

A presented image is in a CPU-visible buffer that Mesa's headless WSI keeps per swapchain image ([patch-mesa-wsi.py](../tools/vk-h0/patch-mesa-wsi.py)). The next present of the same swapchain image overwrites it, so an address does not keep a frame. In `shadow` mode the hook copies each present of the followed swapchain into one of two history slots owned by the generator, before the present returns:

- The copy is a compute pass on the native compositor's own Vulkan device and queue ([hw_sink_gpu.c](../native/hw_sink_gpu/hw_sink_gpu.c)). It reads the WSI buffer by GPU address, as the compositor already reads image layers. Nothing of the game's device (images, views, semaphores) is used, so no cross-device object exists.
- Since 04.19 the copy is a submission of its own with its own fence. The presenting thread waits for that fence with `vkWaitForFences`, the same wait the compositor does for every frame it draws, and returns once it is signalled, so the game cannot reuse the image while it is being read. The generation is a second submission that starts with a barrier, which orders it after the copy on the same queue. The presenting thread does not wait for it. Kernel sync objects (semaphores) are still avoided, because the PS4 port has proven fences but not semaphores.
- The compositor's queue is shared with the presenter thread, so all submissions take one lock.
- The next copy first waits for the previous generation's fence, because it overwrites the slot that generation read.

### Why 04.19 changed the copy wait

In 04.18 the copy and the generation were one submission. After the copy, the command buffer set a `VkEvent`, and the presenting thread polled it with `vkGetEventStatus`. On the PS4 Pro (run-0217, NFS Underground 2, 32-bit DXVK, swapchain 1366x768), the generator initialised (`FLAT-free, timestamps=1`) and made its buffers. Then `PWFG off for this run: the GPU did not finish a copy`: the event was not seen set within 1 s. The game kept 30 FPS and the compositor, on the same device and queue, kept drawing every frame afterwards without a `PWSINK gpu_failed` line, so the queue did not hang. The 5 s window around the failure lost about 45 of 150 presents (about 1.5 s), which fits a 1 s event timeout plus pipeline creation, rather than a second 1 s fence timeout at shutdown, but the shutdown wait was not logged.

Candidates checked against the code:

| Candidate | Finding |
| --- | --- |
| Event | Never used on this PS4 port before 04.18. On GFX7, RADV turns a compute-stage event into two `EVENT_WRITE_EOP` packets into a CPU-mapped GTT buffer. That is the only primitive in the copy path the port had not proven. Suspected, not proven: the 04.19 probe tells |
| Fence/timeline | The compositor waits on a fence every frame. The PS4 winsys signals fences from its own end-of-pipe write per submission |
| Queue lock vs compositor | Both submit under one lock; the 04.18 polling loop did not hold it. The compositor kept submitting after the failure |
| Submit never flushed | The PS4 winsys hands every submission to the GPU at once and calls submit-done |
| Source image layout or ownership | The copy reads the WSI's linear CPU buffer by address, as the compositor's image layers do; the same image was shown through that path (`path=gpu_layer`) |
| 1366x768 | Within the limits (2560x1440); pitch 5464 is 4-byte aligned; buffers were made |
| Timeout | 1 s for a copy of about 4 MB. The pipelines were created before, so the first submission compiles nothing |

What 04.19 does:

- **The copy waits on a fence**, as described above. The event is no longer used by the copy.
- **A probe once per run**, before the first copy. Three submissions, each alone and each waited on its fence: an empty command buffer, a query-pool reset with two timestamps (read back), and an event set after the compute stage (read back for up to 100 ms after the fence). One line each. A probe whose fence does not signal turns generation off for the run. Timestamps that cannot be read are dropped. The event result is only reported.
- **Wait logging.** The first three copies, and any copy whose fence does not signal, log the fence result and the time waited. A generation fence that does not signal logs the same. Shutdown logs how its waits ended.
- **No freeing under a running GPU.** If a submission is still running at shutdown, its memory is kept instead of freed, because the GPU writing freed memory would fault and the system would kill the app.

Expected lines on the console:

```text
PWFG probe empty: fence=signalled waited_us=<n>
PWFG probe timestamps: fence=signalled waited_us=<n> results=0 ticks=<n>
PWFG probe event: fence=signalled waited_us=<n> event=set|reset (<r>) after_fence_us=<n>
PWFG ready: 4 compute passes, FLAT-free, timestamps=1 period_ns=10.000, copy waits on its fence
PWFG copy 0: fence=signalled (0) waited_us=<n> limit_us=1000000 image=<p> 1366x768 pitch=5464
```

How to read them:

- `event=reset` with the fence signalled confirms the event as the 04.18 cause. Generation then runs, because nothing waits on the event any more.
- `event=set` means the event works alone. The 04.18 failure then came from something in the combined submission, and the copy line shows whether the fence-based copy finishes.
- A probe or copy with `fence=timeout` means the GPU did not finish that submission at all. Its `waited_us` and the shutdown line are the evidence to report.

Followed swapchain: the first one that presents. Another one takes over only after the followed one has not presented for 0.5 s. A new size or byte order reallocates the buffers and restarts the history.

## Stage 3: the compute passes

Four compute shaders, compiled to SPIR-V by the hardware build next to the compositor's shaders. No GLSL compiler runs on the console. All data is in storage buffers, so no image format features are involved. The source must be one of the 32-bit RGBA/BGRA formats the compositor already shows.

| Pass | Grid (1280×720 source) | Work |
| --- | --- | --- |
| [fg_capture](../native/hw_sink_gpu/fg_capture.comp) | 640×360 (one per 2×2 pixels) | Copies the pixels into the history slot; writes half-resolution luminance |
| [fg_coarse](../native/hw_sink_gpu/fg_coarse.comp) | 80×45 cells of 16×16 pixels | 13×13 candidate offsets up to ±24 pixels, 16 samples each; mean absolute difference plus a small charge per unit of motion |
| [fg_fine](../native/hw_sink_gpu/fg_fine.comp) | 160×90 cells of 8×8 pixels | Zero and the 3×3 neighbouring coarse vectors as candidates, one step to the best neighbouring offset, then a sub-texel parabola fit. An exact match keeps a whole-texel offset |
| [fg_blend](../native/hw_sink_gpu/fg_blend.comp) | 1280×720 | Motion interpolated between cell centres; previous frame sampled half a motion back, current one half a motion forward, averaged. It falls back to the current frame where the match error is high or the two warped samples disagree |

Each pass is checked for FLAT memory instructions after compilation, as the compositor's own shader is (W153). A FLAT instruction turns the generator off. The capture reads by address as a uniform base plus a 32-bit offset, the form that compiles to MUBUF on GFX7.

Memory at 1280×720: four colour buffers of 3.5 MiB (two history slots and two outputs), two luminance buffers of 0.9 MiB, and the motion fields (0.3 MiB): about 16 MiB. Source-level load estimate per generated frame: about 20 M luminance reads (coarse), 41 M (fine), 12 M (blend). These are not GPU timings. The `PWFG gpu_us` line measures them with timestamps, together with how long the presenting thread was held (`present_block_us`):

```text
PWFG gpu_us capture=avg/max coarse=avg/max fine=avg/max blend=avg/max (avg/max) present_block_us=avg/max generated=… frame=WxH
```

With traces on, generation 90 writes `previous.bmp`, `current.bmp` and `generated.bmp` to `/data/orbisdesk/framegen/` once. They are for visual inspection of real game content.

### Host check

```sh
python3 tests/test_framegen_host.py
```

It compiles the same shader sources and runs [the four passes](../tests/framegen_host_check.c) on Mesa's lavapipe, over synthetic frames with a known midpoint. Requirements: `libvulkan-dev`, `mesa-vulkan-drivers`, glslang. Result on 2026-11-16 (llvmpipe, LLVM 15.0.7):

```text
motion: mean abs error vs true midpoint: generated=1.16 average=3.33 repeat=3.75
motion: fine field in the square 6.00,3.00 (expect 6,3 texels) err=0.000; background 0.00,0.00 err=0.000
cut: generated vs current frame 0.33 (0 = full fallback)
PASS framegen host check
```

This is host reference behaviour of the shader logic only. It says nothing about the PS4 GPU, the FLAT check, timing, the WSI buffers or real game content. The first run of this check found that the sub-texel fit moved a perfectly static background by 0.05 texel, which would make static text shimmer. The fine pass now keeps whole-texel offsets on exact matches.

Since 04.18 the check also runs the motion case with a kept rectangle over the moving square (stage 5): every pixel inside it must be the current frame's word, unchanged. Result on 2026-11-17: `keep: pixels in the rectangle that differ from the current frame 0 (expect 0); generated pixels outside 3009`.

## Stage 4: showing the generated frames

FPS LIMIT at 30 lets the game's frame N go just after vblank V, two vblanks after frame N-1 (the hold is in the presenting thread, after the generator's copy, so the generation runs during the hold). Frame N then reaches the sink's presenter thread as part of Wine's layer stack. For a frame that qualifies, the presenter:

1. draws the stack with frame N's image replaced by the frame generated between N-1 and N, and flips it (on screen at V+1);
2. waits until VideoOut reports that flip done, then draws the stack with the generator's own copy of N and flips it (V+2);
3. waits for that flip too, so the next drawing never goes into a buffer that is on screen or pending.

N+1 is let go at V+2 and the same follows. On screen that is one frame per vblank, generated and real in turn. The desktop, pointer, title overlay, frame counter and Steam page are drawn by the sink on both flips as on any other, so they are never generated. A frame that does not qualify is shown as before: the stack as Wine handed it, then the usual 16 ms pause.

[pw_framegen_sched.h](../platform/ps4/pw_framegen_sched.h) decides for each new frame of the followed swapchain. A pair needs all of the following, checked in this order. The first one that fails is the reason logged:

| Reason in the log | The frame shows alone because |
| --- | --- |
| `gave_up` | Over budget for too long, see below. Stays until the program in front or the setting changes |
| `generator_off` | The generator failed and freed itself for the run |
| `cap_not_30` | FPS LIMIT is not holding the program at 30: Off, 60, or Auto at 60 |
| `vblank_not_trusted` | FPS LIMIT is pacing by time, not by the vblank count |
| `not_followed` | The image is not the generator's latest copy, for example another swapchain |
| `first` | The first copy after a history restart has no previous frame |
| `warming_up` | Fewer than 30 generations have been timed with GPU timestamps |
| `gpu_over_budget` | The generation's averaged GPU time (copy plus three passes) is over 8 ms |
| `late` | The generation was not done 4 ms after the frame reached the presenter |
| `irregular` | The frame was let go other than exactly two vblanks after the previous one |

**Fallbacks.**
- An average over 8 ms for 60 decisions in a row gives up for that program. Generation stops, so the GPU is no longer charged for frames nobody sees, and `PWFG display off reason=gpu_over_budget ...: gave up for this program, generation stops` is logged. It tries again when the program in front changes or the switch is turned off and on.
- A Vulkan failure in the generator turns it off for the run.
- If the generated flip is not reported done within 50 ms, the real frame is shown as handed.
- On a queue without timestamps the generation is never timed, so it never leaves `warming_up` and only real frames are shown.
- With frame generation on, the generator copies and generates only while the cap is 30.

**Latency.** Each real frame reaches the screen one vblank (16.7 ms) later than without generation, because the frame halfway to it is shown first. Input, audio and the game's own timing are untouched.

**What the counters show.** The overlay's `FPS VK` counts the game's presents (30). Since 04.20, MangoHud's FPS row shows the frames on screen while generated frames are shown (below). The sink's own frame counter (F12 in 32-bit titles) and the overlay readout's frame-time graph count output flips, which become 60 while pairs are shown.

### MangoHud's FPS row (04.20)

MangoHud counts the presents of the swapchain it draws in. The generated frames are added by the sink after MangoHud has drawn, so with FRAME GEN on MangoHud kept showing 30 (run-0218). Since 04.20 the FPS row shows the frames on screen, real plus generated, with `FG` in place of the `FPS` superscript: for example `60 FG` beside `VULKAN`.

Why MangoHud's own row and not a label drawn by the sink:
- **Visibility.** The overlay cannot read whether MangoHud is shown (Shift+F12, or F12 from a keyboard); see stage 5. A sink-drawn label could stay on screen with the HUD hidden. MangoHud's own row is drawn only while MangoHud draws.
- **MangoJuice.** Position, font, size, colours, `fps_only`, `fps_color_change` and the row order are what `MangoHud.conf` says, for every HUD, because MangoHud draws the row itself. A label imitating them could drift from what MangoJuice saves.
- **32 and 64 bit.** The same patch is in both MangoHud builds; the i386 build copies the patched tree.
- **Cost.** It needs a MangoHud rebuild (x64 and i386). A sink label would also have needed MangoHud changes to learn whether the HUD is visible, so it would not have been smaller.

How it works:
1. The presenter counts, for the image frame generation follows, each new real frame once and each generated frame whose flip VideoOut reported done. Once a second it publishes frames a second (tenths): all, real and generated, with the image's size. Nothing is estimated.
2. MangoHud already asks the native side for CPU and GPU use through a private `NtQuerySystemInformation` class ([pw_telemetry.h](../platform/ps4/pw_telemetry.h)). A caller whose buffer holds the larger `struct pw_ps4_telemetry_fg` gets version 2, with those figures added. An 80-byte caller still gets version 1, unchanged, and wow64 passes the query through for 32-bit programs.
3. In MangoHud's `fps` and `fps_only` elements ([patch](../tools/vk-h0/patch-mangohud-orbis-framegen.py)): when the query says generated frames were on screen in a second measured within the last 2.5 s, and the image has this swapchain's size, the value is the frames on screen and the superscript reads `FG`. `FG` shows even with `hide_fps_superscript`, so the number is never read as the game's rate. Otherwise MangoHud shows its own value, as before.

What stays MangoHud's own: the frametime column (`ms`), the frame-time graph, the 1% lows, the FPS limiter and MangoHud's logs keep the game's presents. With FRAME GEN on and nothing generated (cap at 60, gave up, generator off), the row shows MangoHud's own value and no `FG`.

Limits:
- The match is by size: another Vulkan window of exactly the same size would also show `FG`.
- The value updates once a second, as MangoHud's own does.
- The row is inside MangoHud's HUD, whose rectangle the generator copies from the real frame (stage 5). It is not interpolated as long as the HUD stays inside that estimated rectangle.

Log lines:

```text
PWFG shown_rate on 1024x768 shown_x10=… real_x10=… generated_x10=… window_us=…     (when generated frames start or stop showing)
PWTELEM framegen query bytes=112 version=2 fg_flags=…                                 (once, the first version 2 caller)
PWHUD framegen query=00000000 bytes=112 version=2 flags=1 image=1024x768 shown_x10=… real_x10=… generated_x10=… hud=1024x768
```

The `PWHUD` line is MangoHud's (Wine debug output), written when the flags or the image size change.

Log lines:

```text
PWFG mode=display (overlay)
PWFG display on reason=pair cap=2 vblank_trusted=1 span=2 gpu_us=… timed=…
PWFG display off reason=<reason> cap=… vblank_trusted=… span=… gpu_us=… timed=…[: gave up for this program, generation stops]
PWFG display pairs=… alone=… reasons=<reason>:<count>,… gpu_us=… budget_us=8000 timed=… gave_up=0|1   (every 10 s)
```

`on` and `off` are logged when the decision changes. The 10 s line counts pairs and frames shown alone in that window. `PWFG gpu_us` (stage 3) still reports each pass every 120 generations.

### Host check

```sh
python3 tests/test_framegen_sched_host.py
```

It runs the [decisions](../tests/framegen_sched_host_check.c) over simulated frame sequences:
- a steady 30 FPS game at 5 ms of generation shows pairs after 30 warm-up frames;
- 60, an untrusted vblank count and another swapchain never pair;
- a late frame or a late generation shows alone and the next one pairs again;
- 9.5 ms gives up after 60 frames and stays given up;
- bursts over budget shorter than 60 frames do not give up;
- a failed generator shows real frames;
- a reset tries again.

It does not run the sink, VideoOut or the GPU.

## Stage 5: per program, MangoHud and restarts

- **Per program:** the overlay entry and `overlay.ini` line above. The sink reads the choice for the program in front on each present (`PWFG mode=display (overlay)` / `PWFG mode=off (overlay)` when it changes).
- **MangoHud:** MangoHud draws its HUD into the game's image before the present, so the generator would carry its text along with the motion or average two values. While MangoHud draws on the program in front, the overlay gives the generator a rectangle that `fg_blend` copies unchanged from the real frame. The rectangle comes from the overlay's own copy of MangoHud's layout (its readout imitation: rows, position, offsets and `font_size` from the `MangoHud.conf` that MangoJuice saves for every HUD). It is widened by about half plus 16 pixels each way, because MangoHud's exact text widths are not known here. The overlay reads `MangoHud.conf` again within 5 s of a MangoJuice save. Whether the HUD is visible (Shift+F12) is not known, so the rectangle is kept out either way. FRAME GEN never writes `MangoHud.conf`, and the overlay's show/hide of MangoHud works as before in 32-bit and 64-bit programs.
- **History restarts:** another followed swapchain, a new size or byte order, a change of the program in front or of the switch, and any present that went by without a copy (generation paused while the cap was not 30) restart the history (`first`), so nothing is generated against a stale frame. The display decisions start over when the switch or the program in front changes. Scene cuts and menus inside the game rely on the blend's fallback to the current frame. A cut detector is still a later step.

## Latency and quality limits

- To show the frame between N-1 and N, frame N must already exist. The real frame N is therefore shown one vblank (16.7 ms) later than without generation. The generation itself runs while FPS LIMIT holds the presenting thread, so it adds no delay while it stays within budget.
- MangoHud's HUD is inside the captured image. Its rectangle is kept out of the generation (stage 5) by an estimate of its layout, not by its real pixels: a HUD that MangoJuice laid out differently (another font, extra rows) can stick out of it. The desktop, pointer, title overlay and Steam UI are drawn by the sink after composition and are never generated.
- A game's own HUD has no mask. Static HUD keeps zero motion, but HUD over moving content can smear.
- Scene cuts, transparency and occlusions rely on the fallback to the current frame. The host check covers a full cut only.
- The generator follows one swapchain. With two Vulkan programs presenting at once, only the followed one is generated; the other is shown as handed.

## Next steps

1. **Console run of 04.20** (needs the MangoHud x64 and i386 builds, the package build, an upload and the user's approval): FRAME GEN on the same game as run-0218, MangoHud shown. Expected: MangoHud's FPS row reads about 60 with `FG`, the `PWFG shown_rate on` and `PWHUD framegen ... flags=1` lines, and the row back to MangoHud's own value without `FG` when FRAME GEN is turned off. Hide and show MangoHud from the overlay in a 64-bit and a 32-bit Vulkan program; save a change in MangoJuice and check it applies to the row.
2. If the GPU time is over budget on real games: lower the coarse search (fewer candidates, or quarter-resolution luminance) before raising the budget.
3. A cut detector (high mean coarse cost) that shows the real frame alone, and a restart on an in-game resolution change without a new swapchain.
4. Only after stage 4 is measured physically (pairs counted, `generated_shown` against `new_frames_shown` at measured vblanks, and the user's observation) can a smoothness effect be described.

## Licensing

The interpolator is written for OrbisDesk under LGPL-2.1-or-later, like the native compositor it extends. Hierarchical block matching on luminance with a fallback to the real frame is a general technique. The design was informed by reading the algorithm of an existing GPL-2.0-or-later emulator interpolator, but no code, shader or constant set was copied from it (see [third-party notes](../THIRD_PARTY.md) and [release licences](RELEASE_LICENSES.md)).

## Files

- [native/wine_vk_runtime.c](../native/wine_vk_runtime.c): the present hook.
- [platform/ps4/pw_wine_sink_ps4.c](../platform/ps4/pw_wine_sink_ps4.c): stage 1 counters, the switch, the call into the generator, and stage 4's presenter pairs (`fgd_begin`, `fgd_stack`, `fgd_wait_flip`).
- [platform/ps4/pw_framegen_sched.h](../platform/ps4/pw_framegen_sched.h): stage 4's decision for each frame.
- [native/hw_sink_gpu/framegen.inc.c](../native/hw_sink_gpu/framegen.inc.c): stages 2–3 and `pw_sink_gpu_fg_pick`, included by [hw_sink_gpu.c](../native/hw_sink_gpu/hw_sink_gpu.c).
- [native/hw_sink_gpu/fg_common.glsl](../native/hw_sink_gpu/fg_common.glsl) and the four `fg_*.comp` shaders. `fg_blend` takes the kept rectangle.
- [native/hw_overlay.c](../native/hw_overlay.c): the FRAME GEN entry, its `overlay.ini` line, `pw_hw_overlay_framegen` and `pw_hw_overlay_hud_rect`.
- [platform/ps4/pw_telemetry.h](../platform/ps4/pw_telemetry.h) and [native/telemetry.c](../native/telemetry.c): the version 2 telemetry with the frames on screen; the sink's `pw_hw_sink_fg_rate` publishes them.
- [tools/vk-h0/patch-mangohud-orbis-framegen.py](../tools/vk-h0/patch-mangohud-orbis-framegen.py): MangoHud's FPS row, applied by [build-mangohud.sh](../tools/vk-h0/build-mangohud.sh) and checked by [build-mangohud-i386.sh](../tools/vk-h0/build-mangohud-i386.sh).
- [tools/build-wine-hardware.py](../tools/build-wine-hardware.py): compiles the shaders and records their hashes.
- [tests/test_framegen_host.py](../tests/test_framegen_host.py), [tests/framegen_host_check.c](../tests/framegen_host_check.c): shader host check.
- [tests/test_framegen_sched_host.py](../tests/test_framegen_sched_host.py), [tests/framegen_sched_host_check.c](../tests/framegen_sched_host_check.c): decision host check.
