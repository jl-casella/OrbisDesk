# SeaMonkey responsiveness on the console

[English](SEAMONKEY_RESPONSIVENESS.md) | [Español](SEAMONKEY_RESPONSIVENESS-es.md)

Status: two console runs, two profile changes and a launcher fix, 2026-11-17. The frame counts of 04.15 (run-0207) were measured on the console. The smooth-scrolling change and the trace.txt fix are not built yet.

## The symptom

On 04.14, SeaMonkey loads YouTube completely ([file locks](SEAMONKEY_FILE_LOCKS.md)), but the interface lags:
- while a page loads;
- between asking for a full-screen video and the video filling the screen;
- while scrolling.

## What run-0192.log shows

The run is `reports/wine-hardware-w303/physical/20261117T152946Z/run-0192.log`, a release log (`trace level=0`).

- **Full screen goes through a transition window.** Each of the three switches to full screen first starts a new thread (`0ae0`, `039c`, `0488`). That thread takes the foreground and shows its own 1280x720 window (`PWSINK fullscreen on hwnd=0xc000f8`, `0x7b010e`, `0xfb0104`). Only after that does SeaMonkey's window (`0x500c2`) move to 0,0 and go full screen. This is Gecko's full-screen transition on Windows: a window on its own thread fades the screen to black and back, by default over 200 ms each way. The log has no times for it.
- **Moving a window is cheap.** The window-drag lines time each move: `move_loop_setpos took_us` is 1.3–2.6 ms.
- **Presentation does not wait for the display.** When a window's content changes (`ps5_surface_flush` in win32u), the dirty rectangle is copied and the window stack is handed to the sink's presenter thread (`pw_wine_present_layers`, `PW_SINK_ASYNC`). The painting thread does not wait for a flip.
- **Nothing in the release log measures painting, input or server time.** These lines exist but are turned off in a release log: `flush_stats`, `show_stats`, `PWSERVER late_*` and `PWFG`. So the log cannot say how many frames SeaMonkey draws or where its main thread waits.
- SeaMonkey started more than 256 threads (`thread_overflow`). As in [descriptors](SEAMONKEY_DESCRIPTORS.md), that only stops them from being tracked; it is not a stall.

## What follows from the profile and the platform

These follow from the profile and the hardware, not from a measurement:

- **One thread does most of the work.** SeaMonkey runs without e10s (one process, as every guest must). The interface, the page's JavaScript, layout and painting share one main thread, so a long YouTube script blocks clicks, scrolling and the switch to full screen alike.
- **Scrolling runs on that same thread.** In the Firefox 60 platform, async pan/zoom (scrolling done by the compositor) needs e10s.
- **Compositing is in software.** The profile sets `layers.acceleration.disabled`, because D3D11 through DXVK in the browser's process failed (Pale Moon W183/W184). So Gecko composites with its Basic (CPU) compositor, and every repaint is rasterized by the CPU.
- **The CPU is slow per core.** The title gets 6 of the console's Jaguar cores (`affinity=3f cores=6`). They run at 1.6 GHz on a PS4 and 2.1 GHz on a Pro. Single-thread speed matters most for one main thread.

Whether this is simply the platform's limit, or a Wine-side wait on top of it, needs the numbers below.

## The change

[seamonkey-user.js](../fixtures/browser/seamonkey-user.js) sets `full-screen-api.transition-duration.enter` and `.leave` to `"0 0"`. With both durations 0, Gecko skips the transition: no extra thread, no extra window and no fade. The full-screen switch itself is unchanged.

This removes only the step the log shows. It does not speed up scrolling or page loads. Run-0207 (04.15) has no transition window: its switch to full screen only moves SeaMonkey's window.

## 04.15 measurement (run-0207.log)

The run is `reports/wine-hardware-w303/physical/20261117T173525Z/run-0207.log`: about 30 s of a YouTube video playing in the page, about 15 s of scrolling, then full screen and back.

`framegen.txt` worked (`PWFG config mode=timing … kernel_open=0x14`) and gave 184 `PWFG timing` lines, one per 2–3 s window. `trace.txt` did not (`trace level=0 source=build`). The launcher read it with libc's `open`, which fails on that file as it did for `framegen.txt` and `winedebug.txt`. So the run has no `flush_stats`, `show_stats` or `PWSERVER` lines.

Displayed frames per second (`flips_done` × 1000 / `window_ms`):

| Stretch | Frames/s |
| --- | --- |
| Desktop idle, SeaMonkey closed | 1 |
| SeaMonkey starting and loading YouTube | 1–46, uneven |
| Video playing in the page (from the first audio stream) | 57–58 for 8 windows, then 31–55 |
| Around the switch to full screen (window to 0,0, then back) | 5–39, then 49–57 |
| The rest of the page activity | mostly 10–45 |

In all 184 windows:
- `pending_max=0`, and `flips_submitted` equals `flips_done`. The presenter never had a frame waiting, and no flip failed (`status_failed=0`).
- `flip_latency_us` is at most 16.7 ms, the time to the next vblank (`period_us=16683`). It is the wait for vsync, about 8 ms on average, not a backlog.

What follows:
- **The Wine/sink path is not what limits the page.** The same window, through the same flush and presenter, shows 57–58 frames a second while a video plays, close to the 60 Hz display. Full-screen video updates the whole 1280x720 window at 49–57. When the page scrolls or loads, the rate drops to 10–45 while the presenter stays idle. So SeaMonkey hands over fewer frames: the time is spent before the flush, inside the browser.
- **This log cannot show what the browser does there.** A video frame is an image that the compositor scales. A scroll or a page load is JavaScript, layout and software rasterizing of text and images on the main thread. With the trace.txt fix, `flush_stats` would add the cost of each flush and the number of flushes per second. It cannot see inside the browser's main thread.
- **This is the platform's limit for this browser**, with the numbers above: one main thread on a 1.6 or 2.1 GHz Jaguar core, without async scrolling, with CPU compositing. What helps is less main-thread work, not a faster present.

## Changes after 04.15

- In [wine_hardware.c](../native/wine_hardware.c), `trace_setup` reads `trace.txt` with the kernel's `sceKernelOpen` first and falls back to libc's `open`, as `fg_read_config` does for `framegen.txt`. Its log line adds `kernel_open=` and `libc_errno=`.
- [seamonkey-user.js](../fixtures/browser/seamonkey-user.js) sets `general.smoothScroll` to false. A smooth scroll animates each wheel notch or key press over several frames, and without async scrolling each frame is a main-thread repaint. Without smooth scrolling, a notch is one repaint, and the page jumps instead of gliding.

Considered and not changed:
- **GPU compositing** (`layers.acceleration.disabled` set to false) stays off. D3D11 through DXVK in the browser's process failed (Pale Moon W183/W184), and the measurement does not point at compositing.
- **Off-main-thread painting** (`layers.omtp.enabled`): in the Firefox 60 platform it depends on the content backend and the process model. about:support shows whether it is available here (Graphics, Decision Log). Without that check, turning it on is a guess.
- **A lower refresh rate** (`layout.frame_rate`) would cap animations, and also the video in the page, which the measurement shows is already fine.

## Measuring (no build needed)

1. Create `/data/orbisdesk/trace.txt` (empty) and `/data/orbisdesk/framegen.txt` containing `timing`. Traces add log lines and cost a little themselves, so remove both files afterwards. `trace.txt` needs a build with the 04.15 `trace_setup` fix: check that the run's `trace level=` line says `source=trace.txt`.
2. Start OrbisDesk and open SeaMonkey. Open `about:support` and photograph the Graphics section. **Compositing** should say `Basic`.
3. Open a YouTube video:
   - wait 30 s while it plays in the page;
   - scroll the page up and down for 15 s;
   - switch to full screen, wait 10 s, and leave full screen.

   Note roughly when each step happened.
4. Fetch the log. The lines that answer the question:
   - `PWFG timing … flips_submitted=… vblanks=…` every 2 s: frames the console actually displayed. 120 vblanks in a 2 s window means 60 Hz.
   - `PWBOOT flush_stats n=… avg_us=… max_us=… avg_px=… over_ms=…` every 100 window updates: what one update costs Wine (copy, compose and hand-over), and how often SeaMonkey updates (100 updates in `over_ms`).
   - `PWSINK show_stats path=… avg_us=… max_us=…` every 300 output frames: the presenter's cost per frame.
   - `PWSERVER late_timer`, `late_wake` and `stuck_s`: the in-process wineserver late or stuck.

How to read them:
- **Small update cost, few updates per second, no `PWSERVER` lines:** the time is inside SeaMonkey (JavaScript, layout, software painting on the main thread). That is the platform's limit for this browser. What would help is less work: smaller pages, `general.smoothScroll` false, or a lighter YouTube front end.
- **Large `flush_stats` or `show_stats`:** the Wine/sink path is the cost. Next would be to compose only the dirty rectangle, or to skip the copy.
- **`PWSERVER` lines during the lag:** the in-process server is late or stuck. `stuck_s` names the request and the client thread.

## What was tested

- The trace switches and their lines were read in the source (`platform/ps4/pw_trace.h`, `pw_wine_sink_ps4.c`, `tools/build-win32u-ps4.py`, `tools/build-wine-delete-server.py`).
- The preference names are the Firefox 60 platform's. Whether SeaMonkey 2.53.24 applies them was not checked on the console.
- The 04.15 frame counts come from run-0207 on the console (PS4 Pro). The trace.txt failure is its `trace level=0 source=build` line.
- With the fix, `trace_setup` compiles cleanly with the recorded helper flags and `-Wall`. It has not been built into a package.
- **Not tested:** the smooth-scrolling change and the trace.txt fix have not run on the console.
