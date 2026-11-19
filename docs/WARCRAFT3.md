# Warcraft III 1.07: Storm's static imports and the AVI intro movies

[English](WARCRAFT3.md) | [Español](WARCRAFT3-es.md)

Status: two fixes, both confirmed on the console, 2026-11-17. The game starts, plays its intro movie with sound, reaches its menu and exits with status 0 on 04.15 (`run-0205.log`). The user's own copy of Warcraft III 1.07 was run from a USB drive (`E:\PC\Warcraft III`). This is one game on one console, not a compatibility claim for other Blizzard games or versions.

## 1. "Warcraft III was unable to initialize"

Up to 04.12 the game stopped at once with "unable to initialize". No file was missing and nothing faulted.

**Cause (ours, the guest loader).** Storm.dll's `DllMain` looks at `lpReserved` on `DLL_PROCESS_ATTACH`:
- Windows passes a non-NULL `lpReserved` to the DLLs a process imports statically, and NULL to a DLL loaded with `LoadLibrary`.
- With NULL, Storm assumes it was loaded by another program and builds its MPQ decryption table from a different seed. Every hash table in the game's archives then decrypts to garbage, and every file lookup inside them fails without reading anything.
- `war3.exe` imports Storm statically. OrbisDesk starts a guest EXE through `LoadLibraryExW`, so the guest EXE's static imports were attached with NULL, as if loaded by `LoadLibrary`.

Two small probes showed it on the console (04.12): a DLL that records its `lpReserved` got NULL as a static import, and a program importing the game's Storm.dll statically found every archive's hash table garbled, byte for byte as with `LoadLibrary` on host Wine.

**Fix.** [build-guest-hw.py](../tools/build-guest-hw.py) adds one revision to the guest `ntdll` loader. When a guest image is loaded and the module is the guest EXE itself, `process_attach` gets a pointer to a static `CONTEXT` instead of NULL, as Wine's `loader_init` does for a process. DLLs that a `DllMain` loads meanwhile still get NULL. It applies to both guest `ntdll` builds (64-bit and i386). From 04.13 on, the game initializes.

## 2. The intro movies

On 04.13 the game crashed right after initializing: `PWFAULT` in Game.dll, Storm's "FATAL ERROR" dialog, and then the whole title ended.

**Cause (ours, a missing DirectShow capability).**
- The movies in `Movies\*.mpq` are AVI files: video in Blizzard's DivX ("BLZ0"), audio in MP3.
- Game.dll plays them with DirectShow. On Windows the graph is File Source → AVI Splitter → the game's own `blizzard.ax` ("DivX for Blizzard Decoder Filter", registered by `war3.exe` at each start) → Video Renderer, with the MP3 stream going to an MP3 decoder and the DirectSound renderer.
- The 32-bit DirectShow on the console (`stage-dshow-i386.py`, W225) had no AVI splitter. Wine's AVI splitter is part of winegstreamer, and the console has no GStreamer. So `IGraphBuilder::RenderFile` failed.
- Game.dll ignores that failure, starts its movie timer anyway and dereferences the NULL graph on the first tick. That is the game's own bug, but it only shows when `RenderFile` fails, which it does not on Windows.

**Fix: an AVI splitter for 32-bit guests.**
- [pwavi.c](../native/pwmpeg1/pwavi.c) adds "PW AVI Splitter" as a second filter in `pwmpeg1.ax`. Like Windows' AVI Splitter it only splits; the decoders downstream do the decoding.
  - It reads the AVI headers (`hdrl`, `strh`/`strf`) and the `idx1` index, or walks the `movi` list when there is no index.
  - Each video or audio stream gets an output pin with the stream's own format: `VIDEOINFOHEADER` with the FOURCC as subtype, or `WAVEFORMATEX` with the format tag as subtype.
  - Each pin has its own delivery thread. Sample times come from the stream's `dwScale`/`dwRate`, and key frames from the index flags.
  - Each pin reports the stream's duration through `IMediaSeeking`. Without it Wine's filter graph keeps its position at 0, and Game.dll reads that position on every timer tick. Seeking is not offered.
  - A file it cannot parse is refused (`PWAVI reject` in the log), and `RenderFile` fails as before.
- [pwmpeg1.c](../native/pwmpeg1/pwmpeg1.c) hands out both filters. The MPEG-1 decoder is unchanged.
- [stage-dshow-i386.py](../tools/stage-dshow-i386.py) compiles `pwavi.c` into `pwmpeg1.ax` and registers the splitter in the 32-bit view, with a merit just above winegstreamer's "AVI Splitter" (still registered in the base prefix, but it cannot load on the console).

Nothing is faked: video is decoded by the game's own `blizzard.ax`, and MP3 by Wine's PE decoders, which have no Unix side.

On host Wine, `RenderFile` succeeded on the same movie, the video decoded at real time to its last frame (3260), and the graph position reached the movie's duration (135.47 s).

## 3. On the console: 04.15 (`run-0205.log`)

Evidence: `reports/wine-hardware-w303/physical/20261117T171642Z/` (local, not in Git).

- The first 04.15 start still crashed. The console merges new keys from the build's `system.reg` into the prefix only once per build ID (marker `/data/orbisdesk/w303/system-reg-merged.txt`). That merge had already run for W303 with an earlier release, so the splitter's registration was not there. After that marker was deleted, the next start merged 110 keys (`system_reg_merge … added=110 … rc=0x00000000`).
- On that start:
  - `PWAVI open size=103433e streams=2 indexed=1`: both streams parsed, video `BLZ0` and audio MP3 (format tag `0x55`).
  - Both streams delivered (`first_sample hr=0`). The intro played with picture and sound until it was stopped: 2137 video and 1723 audio samples, about 89 s of the 135 s movie. The movie window was presented at about 24 frames per second, the movie's rate.
  - The game then set 1024x768 and drew its menu through d3d8 (wined3d, OpenGL renderer).
  - No `PWFAULT`, no "FATAL ERROR". `war3.exe` exited with status 0.
- The same log has five later starts of `war3.exe`, each exiting with status 0. They play no intro movie.

### The "MPEG Layer-3 Decoder" line

The log has:

```
err:winediag:mpeg_layer3_decoder_create GStreamer doesn't support MP3 audio decoding, please install appropriate plugins.
err:quartz:autoplug Failed to create filter for L"MPEG Layer-3 Decoder", hr 0xd0000005.
```

This is harmless here:
- "MPEG Layer-3 Decoder" (`l3codecx.ax`) is the highest-merit MP3 filter in the prefix. In Wine it is a front for winegstreamer, which cannot work without GStreamer, so creating it fails. Its failure is returned as an error code (`0xd0000005` is `HRESULT_FROM_NT(STATUS_ACCESS_VIOLATION)`), not a fault in the game: there is no `PWFAULT`, and the game carried on.
- quartz then tried the next MP3 filter. The log shows `qasf.dll` (the DMO wrapper) and `mp3dmod.dll` (Wine's MP3 decoder DMO, PE code with its own mpg123) loading right after, then the audio stream starting. `l3codeca.acm` was never loaded, so the ACM Wrapper path was not used.
- The cost is one failed attempt per movie: winegstreamer, mfplat, propsys and rtworkq are loaded into the game for nothing. Removing the entry would only change the log line and that loading, so it was left alone.

## Limits

- The splitter does not handle OpenDML files (AVIs larger than their first RIFF segment), palette changes or seeking. It offers up to 4 streams, and only video and audio ones.
- A movie that plays to its end without being skipped, and the game moving on by itself, was not confirmed on the console. On the host, audio output stopped at about 32 s for reasons of the host's own sound output, so it could not be checked there either.
- Only the main menu was reached. Campaign cinematics and gameplay were not tested.
- The once-per-build-ID registry merge affects any release that adds registry keys without a new build ID: a console that already ran an earlier release of that build ID does not get the new keys until the marker is removed. A clean install is not affected.
- Not fixed: a fault inside a guest's own top-level exception filter (as on 04.13, where the second Game.dll fault happened inside Storm's crash dialog) ends the whole title rather than only that guest. The unhandled second-chance exception goes to Wine's Unix `NtRaiseException`, which terminates the process; the per-guest exits added in W208 and W262 do not cover that path.
