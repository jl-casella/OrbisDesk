# FPS limit (per program)

[English](FPS_LIMIT.md) | [Español](FPS_LIMIT-es.md)

The overlay's **FPS LIMIT** entry (L3+R3, below GRAPHICS) caps how often the program in front presents frames: **30** (the default since 04.18), **60**, **Auto** or **Off**. It paces the game's real presents onto vblank boundaries so they reach the screen at an even rate. It does not drop frames, make up frames, or change the game's simulation speed: a game that waits on its present simply runs at the cap.

**State:**
- **04.16, on a PS4 Pro** (W303 physical runs 0208 and 0209, 20261117T182036Z): vkcube and Prince of Persia held 30, with `presents=150 held=150 late=0-2` per 5 s and `period_us≈16683`. The per-program choice was saved and applied at start (`fpslimit=30 program=POP.exe why=start`).
- **04.18:** 30 is the default for every program with no choice saved. This has not run on a PS4 yet.
- No smoothness or performance gain is claimed beyond what those logs show.

## Choosing it

1. Open the program, then open the overlay with L3+R3.
2. Move to **FPS LIMIT**. The panel shows the program the choice is for: the last program opened that is still open, as for CURSOR and STRETCH.
3. Use Left and Right to choose, then X to save. The choice applies at once and is saved in `C:\orbis\overlay.ini` as `fpslimit.<exe>=60`, `auto` or `off`. 30, the default, writes no line.

A program with no line runs at 30 from its start (`PWOVERLAY fpslimit=30 program=<exe> why=start`). Lines written by 04.16 keep their value. A program that was Off in 04.16 had no line, so it now starts at 30: choose Off again to keep it unlimited. With no program open (the desktop in front) nothing is limited. With no program open, X shows "FPS LIMIT: NO PROGRAM OPEN" and saves nothing. The entry's value on the right is the limit in force for that program.

## What each option does

| Option | Effect |
| --- | --- |
| 30 (default) | A present waits for the second vblank after the previous release, so frames go out on every other vblank. |
| 60 | A present waits for the vblank after the one the previous present was released on. This only matters for games that would present faster than 60. |
| Off | No hold. With the limit off for the program in front, a present costs one function call. |
| Auto | Starts at 60. Over windows of about one second it measures how fast the game could go without the hold: frames divided by the game's own time on them, from one release to the next present. Two windows in a row below 52 FPS switch to 30. While at 30, three windows in a row at or above 57 FPS switch back to 60. |

A present that arrives later than its allowed vblank is released at once and the count starts again from there. A game slower than the cap is never delayed further.

**Auto and DXVK.** DXVK presents from its own thread, with the next frame usually ready, so while held at 30 such a game looks able to reach 60 and Auto tries 60 again. If the game cannot keep up, two windows below 52 bring it back to 30 (about 2 s of uneven pacing). Each failed return doubles the windows Auto waits before the next try: 3, 6, 12, 24, 48, then 96. After that warm-up, a game that cannot hold 60 retries about every 100 s. A return that lasts 10 windows resets the wait to 3.

## What it covers

- **Covered:** presents that reach Wine's win32u `vkQueuePresentKHR`, in 32-bit and 64-bit guests alike:
  - DXVK (D3D8 to D3D11);
  - wined3d's Vulkan renderer;
  - native Vulkan games;
  - wined3d's OpenGL renderer through Mesa WGL/Zink, which presents through a Vulkan swapchain. This is expected but not yet checked on the console.
- **Not covered:**
  - programs that draw only with GDI;
  - programs started as a separate process (the PoP launcher route), whose presents happen in another process.
- **Several swapchains:** the limit applies to every Vulkan swapchain while the program it is set for is the last opened. Each swapchain is paced on its own, but Auto's measurement is shared, so two programs presenting Vulkan at the same time are not handled well.

## MangoHud's own limit

MangoHud has its own `fps_limit`, set with MangoJuice. MangoJuice edits apply to every program that shows the HUD. FPS LIMIT does not read or change `MangoHud.conf`, and the overlay's HUD show/hide works the same in 32-bit and 64-bit programs with or without it.

When both are set, both apply in turn: MangoHud sleeps inside its layer first, then FPS LIMIT waits for its vblank. **The lower limit wins.** For example, MangoHud at 40 plus FPS LIMIT at 30 gives 30, and MangoHud at 30 plus FPS LIMIT at 60 gives MangoHud's 30. MangoHud's sleep is timed and not aligned to vblanks, so for even pacing set MangoHud's `fps_limit` to 0 (unlimited) and use FPS LIMIT. Under Auto, a lower MangoHud limit also lowers what Auto measures.

## With frame generation

A game held to an even 30 by FPS LIMIT is the input [frame generation](FRAME_GENERATION.md) needs. With the overlay's FRAME GEN on for the same program, the sink shows a generated frame on the vblank between each two of the game's, so the screen changes 60 times a second while the game still presents 30. At 60, Off, or Auto at 60, FRAME GEN shows real frames only. Frame generation has not run on a PS4 yet.

## Logs

The title's log gets the lines below. From 04.37 the `PWFPS vblank count`, `PWFPS auto cap` and 5 s report lines appear only with traces on (`/data/orbisdesk/trace.txt`, see [release traces](RELEASE_TRACES.md#alpha-2-lines)); the setting lines always do.

- `PWOVERLAY fpslimit=<off|30|60|auto> program=<exe> saved=<0|1> errno=<n> why=menu`: the choice was made in the overlay. With `why=start` or `why=exit`, the program in front changed and its saved choice took effect.
- `PWFPS limit=<setting> cap=<vblanks>`: the sink took the new setting (cap 2 = 30, 1 = 60, 0 = off).
- `PWFPS vblank count trusted|not trusted: <n> in <us> us (period_us=<p>)`: whether VideoOut's vblank count advanced at about 60 Hz over a second. Until it is trusted, holds are timed from the last release instead (`pacing=time`).
- `PWFPS auto cap <a>-><b> potential_x10=<f> high_needed=<n>`: Auto switched. `potential_x10` is the measured potential FPS × 10.
- Every 5 s while a limit is on: `PWFPS limit=… cap=… presents=… held=… held_us_avg=… held_us_max=… late=… pacing=vblank|time period_us=… potential_x10=… high_needed=… switches=… status_failed=…`.
  - `held` counts presents that waited.
  - `late` counts presents that came after their allowed vblank and were released at once.
  - `status_failed` counts failed vblank status reads.

## Checks

- `python3 tests/test_fps_limit_host.py` builds `tests/fps_limit_host_check.c` with the host compiler. It runs the decisions in `platform/ps4/pw_fps_limit.h` against simulated synchronous and queued games:
  - 30 and 60 give exact 2- and 1-vblank spacing;
  - a 25 FPS game is never held;
  - Auto keeps 100, 83 and 57 FPS games at 60;
  - Auto moves a 45 FPS synchronous game to 30 within 3 s, and back to 60 when it speeds up;
  - Auto keeps a queued 45 FPS game at 30 for at least 95% of a 10-minute run.

  This is a host model: it does not exercise VideoOut, the sink's hold, or the console.

## Files

- [hw_overlay.c](../native/hw_overlay.c): the FPS LIMIT entry, its strings and `overlay.ini` lines, and `pw_hw_overlay_fps_limit`.
- [pw_fps_limit.h](../platform/ps4/pw_fps_limit.h): pacing targets and Auto's decisions.
- [pw_wine_sink_ps4.c](../platform/ps4/pw_wine_sink_ps4.c): `fl_present`, the hold in the presenting thread, the vblank checks and the log lines. It runs from the present hook that [wine_vk_runtime.c](../native/wine_vk_runtime.c) calls.
- [fps_limit_host_check.c](../tests/fps_limit_host_check.c), [test_fps_limit_host.py](../tests/test_fps_limit_host.py).
