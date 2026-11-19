# SeaMonkey GPU compositing

[English](SEAMONKEY_GPU.md) | [Español](SEAMONKEY_GPU-es.md)

Status: GPU compositing shipped in 04.19 and crashed on the console at the second start (run-0218). From 04.20 the default is Basic again, and OpenGL is an opt-in. Run-0234 traced the second start's crash to MangoHud; the 04.26 fix is not built. 2026-11-18.

## Goal

Until 04.18, SeaMonkey uses Gecko's Basic compositor: the CPU blends the layers, converts video from YUV and scales it. The goal is to move that work to the console's GPU, without a hang, with a clean fallback to Basic, and within the title's memory.

This only moves compositing. Page JavaScript, layout and the painting of content (Skia on the CPU, already split over 4 off-main-thread painting workers) stay where they are ([responsiveness](SEAMONKEY_RESPONSIVENESS.md)).

## OpenGL on, 04.32: Gecko sizes its GL frame from the window rectangle (04.34)

On 04.32, with OpenGL on, the window was drawn 34 pixels too high again, and YouTube's video did not play. Run-0270 has all three traces:
- `PWGL viewport 1163x651 at 0,0 on a 1155x617 window drawable` (line 1408): Gecko sets a viewport as large as the window rectangle, frame included.
- `PWSTW size hwnd=…200f8 thread=0124 client=1155x617 window=1163x651 drawable=1155x617` (line 1316): Mesa's WGL reads the client area and gets it right.
- `PWRECT client hwnd=0x200f8 thread=0124 owner=00a0 … rect=(0,0)-(1155,617)` (line 1039): win32u returns the client size to Gecko's compositor thread. `PWVK size … image=1155x617 client=1155x617` (line 1042): the swapchain is the client size too.

So win32u, Mesa and Zink all agree on the client size. Only Gecko's frame has the window's size.

**Where Gecko gets that size (Firefox 60 platform, mozilla-esr60 source):**
- `ClientLayerManager::BeginTransactionWithTarget` sends `mWidget->GetNaturalBounds()` to the compositor. `nsIWidget::GetNaturalBounds()` returns `GetBounds()`.
- On Windows, `nsWindow::GetBounds()` is `GetWindowRect`: the window with its frame.
- `CompositorBridgeParent::ShadowLayersUpdated` passes that as the render bounds (`UpdateRenderBounds(targetConfig.naturalBounds())`). `CompositorOGL::BeginFrame` makes the window's render target that size, and `PrepareViewport` sets `glViewport` to it.
- The page itself is laid out at the client size. So the frame is drawn 34 rows taller than the drawable. GL's rows go bottom-up, so the top 34 rows (the menu bar) fall off, and the last 34 stay black.
- The frame is the default one on Windows too. Gecko changes the non-client area only for a window with a `chromemargin` attribute (`nsWindow::SetNonClientMargins` sets `mCustomNonClient`, and only then does its `WM_NCCALCSIZE` handler shrink the frame). SeaMonkey 2.53's chrome never sets it on Windows. The only setter in `omni.ja` is `LightweightThemeConsumer.jsm`, and only on macOS. win32u sends `WM_NCCALCSIZE` and uses its result (Wine's `calc_ncsize`, not changed by our generators). The client area in run-0270 is the default frame: 4-pixel borders and a 26-pixel caption.
- Gecko's GL context is on that framed top-level window (`hwnd=0x200f8` in `PWSTW` and `PWVK`), not on a frameless child.
- The other compositors hide this. Basic draws top-down into the client area through GDI, so the extra rows fall off at the bottom and right, where nothing is drawn. Direct3D 11 sizes its swapchain from `GetClientRect`. Gecko's OpenGL compositor is not used on Windows by default, and bug [1125754](https://bugzilla.mozilla.org/show_bug.cgi?id=1125754) reports a window cut off with `layers.prefer-opengl` on Windows.
- So the fault is Gecko's, on any Windows with any OpenGL driver, not the console's. The 04.26 note that the host placed everything right was wrong: the host runs in "Host test" below had the window minimized, so they did not check the drawn image.
- **Host check (04.34, Windows 11, AMD, reference only):** SeaMonkey 2.53.24 with W303's 64-bit `opengl32.dll` and `libgallium_wgl.dll` next to `seamonkey.exe`, `GALLIUM_DRIVER=zink`, the console's user.js with acceleration on and `layers.prefer-opengl` true, in a restored window of 1163x651 (client 1147x612).
  - With OpenGL, the menu bar is missing, the navigation toolbar is cut at its top, and a black band about 39 pixels tall is under the status bar: the window's height minus the client's. This is the console's fault, with Windows 11's taller frame.
  - With `layers.prefer-opengl` false (Basic), in the same window, everything is in place.

**The other lines:**
- `PWGL viewport 1163x651 at 0,0 on a 1x1 window drawable` (line 1037) is the first frame, before Mesa's first swap had read the window. That is expected.
- `PWGL viewport 766x23 at 0,0 on a 766x132 window drawable` (line 2182) is a popup that shrank from 132 to 23 rows. Gecko drew one frame at the new size before Mesa's next swap read it, and the next swapchain is `766x23` (line 2185). It lasts one frame and is not the 34-pixel fault.

**This change (04.34):** no code change for the offset. Nothing in Wine, Mesa or Zink returns a wrong size, so changing them would give every other program the wrong size. [seamonkey-gpu.js](../fixtures/browser/seamonkey-gpu.js) keeps GPU compositing off by default (Basic), and its comment now names the cause. With OpenGL turned on in about:config, the offset stays. The 04.30 and 04.32 traces stay as they are; they are capped and read-only.

**Ways to fix it, all outside our Wine and Mesa (not done; a decision):**
- Patch SeaMonkey's `xul.dll`: in `ClientLayerManager::BeginTransactionWithTarget`, call `GetClientBounds` instead of `GetNaturalBounds`. That changes one virtual call slot, and gives the size Direct3D 11 already uses. The call site has to be found without symbols. The exact bytes have to be checked against the pinned archive, and the change published as source (`xul.dll` is MPL 2.0).
- Make SeaMonkey's windows frameless (`chromemargin` set to `0,0,0,0` from orbisdesk.cfg), so the client area is the window. SeaMonkey's theme does not draw a title bar, so the windows would lose their caption and its buttons. Dialogs and popups would need the same.
- Keep Basic, as now. YouTube does not play with OpenGL either (below).

**YouTube:** still the open Zink video-path issue (see "Video stays black with OpenGL on" below). In the 04.32 photo the player area showed a blue advertisement, and the video did not play. Not changed here.

## OpenGL on, 04.30: the traces stayed silent (04.32)

On 04.30 OpenGL was turned on in about:config. The window was drawn shifted as before, and YouTube videos did not play; the user saw the player area change colour (dark teal in the photo). In run-0262, `PWVK size hwnd=0x800c2 image=1154x617 client=1154x617 window=1162x651` came again (line 781), and no `PWGL viewport` or `PWRECT` line.

**Why the Mesa trace could not show:**
- Both traces were in the uploaded build: `PWGL viewport` is in the 64-bit `libgallium_wgl.dll`, and `PWRECT` is in win32u's `window.o`.
- On Windows, `mesa_loge` writes to the program's stderr and to `OutputDebugStringA`. A guest's stderr is not the console log, and Wine prints `OutputDebugStringA` only on its `warn+debugstr` channel. The launcher's `WINEDEBUG` is `fixme-all,warn+module`. W267's `PWSTW` lines came from a run that had `warn+debugstr`.
- So a missing `PWGL viewport` line says nothing about Gecko's viewport.

**Why the win32u trace said nothing:**
- It was armed at the first present of a framed window (`0x800c2` at line 781) and logged reads of that window from other threads only.
- The presents come from thread `0178`, which Mesa made (`by=L"libgallium_wgl.dll"`); Gecko's compositor thread is `00e8`. Mesa's WGL reads the client rect of its window at each swap, so a read from `00e8` was expected, and none was logged.
- Which window those reads named, or whether they came before the trace was armed, is not in the log.

**This change (not built):**
- [patch-mesa-gl-viewport-trace.py](../tools/vk-h0/patch-mesa-gl-viewport-trace.py) now also sends Mesa's error-level lines through ntdll's `__wine_dbg_output` when it exists, which writes to the console log whatever `WINEDEBUG` says. Other levels, and Mesa outside Wine, are unchanged. Error-level lines are rare: these traces, W266's 32-bit window traces, and real errors. It also adds `PWSTW size hwnd=… thread=… client=WxH window=WxH drawable=WxH`: what WGL's `GetClientRect` and `GetWindowRect` return at each swap, when it changes, the first 16 times.
  - The patched files compile for both builds (64-bit and i386) with the recorded recipe and `-Wall`, without warnings. The i386 build shares the Mesa source folder, so it gets the change when it is built after the 64-bit one.
- [build-win32u-ps4.py](../tools/build-win32u-ps4.py): `PWRECT client|window` is now logged for any window read by a thread other than its own, from the start, once per window, thread, kind and returned size, the first 48. `window.c` compiles with the recorded recipe without warnings; `vulkan.c` drops the 04.30 arming and keeps its 3 earlier warnings.

**What one run with OpenGL on will say:**
- `PWGL viewport 1162x651 … on a 1154x617 window drawable`: Gecko's size is the window's.
- `PWSTW size … client=1162x651`: the drawable WGL reads is already the window's size.
- `PWRECT client hwnd=0x… thread=00e8 … rect=(0,0)-(1162,651)`: win32u returns the window's size to Gecko's compositor thread.

**YouTube not playing:** still the open Zink issue on Gecko's video path (see "Video stays black with OpenGL on" below). The colours changing in the player area fit video frames drawn with the wrong colour conversion, as on the host (magenta). Not fixed here.

## OpenGL on, 04.29: the image still 34 pixels too high, YouTube not playing (04.30)

On 04.29 the console's `user.js` was edited by hand: `layers.acceleration.disabled` false, `layers.acceleration.force-enabled` true, `webgl.disabled` false and `webgl.force-enabled` true. about:support showed Compositing OpenGL, and WebGL worked. The window was drawn shifted again, with black at the bottom, and YouTube videos did not play (run-0254, run-0255).

**What the size trace shows:**
- `PWVK size hwnd=0x1c00b4 swapchain=… image=1154x617 client=1154x617 window=1162x651` (run-0255 line 774, run-0254 line 1550). The swapchain image is the client area's size.
- The next line places it at the client area: `PWVK layer … client=(74,50)-(1228,667) … at=(74,50)-(1228,667)`, and the sink's stack has it there (`stack 4/5 … rect=(74,50)-(1228,667) flags=0x1 source=1154x617`).
- So the image is not placed at the window's origin, and moving it would misplace every correct program. The shift is inside the image.
- It fits a frame drawn for the window's size, 1162x651, into a drawable of the client's size, 1154x617. GL's rows go bottom-up, so the frame's top 34 rows fall off the top and its last 34 rows are left black. Basic draws top-down through GDI, so the same oversized frame only loses rows past the bottom, where the page has nothing, and looks right.
- Mesa's WGL takes the drawable's size from `GetClientRect` at each swap, and Zink's swapchain is the surface's `currentExtent` (the client area). Gecko's compositor reads its widget's size on its own thread. On real Windows the same SeaMonkey, Mesa and profile are right, so one of these reads gets the window's size on our route. Which one is not in these logs.

**This change (not built), two traces for one run:**
- [patch-mesa-gl-viewport-trace.py](../tools/vk-h0/patch-mesa-gl-viewport-trace.py), run by [build-mesa-zink.sh](../tools/vk-h0/build-mesa-zink.sh): `PWGL viewport WxH at X,Y on a WxH window drawable` when a viewport on a window's drawable is not the drawable's size (at each change, the first 16). `1162x651 … on a 1154x617` means Gecko's size is the window's. It compiles with the recorded recipe without warnings. The i386 build shares the same Mesa source folder, so it gets the trace too when it is built after the 64-bit one.
- [build-win32u-ps4.py](../tools/build-win32u-ps4.py): for the first framed window with a Vulkan swapchain, `PWRECT client|window hwnd=… thread=… owner=… dpi=… rect=…` for `GetClientRect` and `GetWindowRect` from threads other than the window's (the first 48). This shows what Gecko's compositor thread reads. `vulkan.c` and `window.c` compile with the recorded recipe, with the same warnings as before.

**YouTube not playing:** the logs show the decoder (`mozavcodec.dll`) loaded and its threads started, and no fault. On the Windows host, the same video path drawn by Zink is wrong too (magenta, see "Video stays black with OpenGL on" below), so it is still the open Zink issue on Gecko's video path, not fixed here.

**The GPU switches are defaults now (04.30, not built):**
- [seamonkey-user.js](../fixtures/browser/seamonkey-user.js) no longer sets `layers.acceleration.disabled`, `layers.acceleration.force-enabled` and `webgl.disabled`. [seamonkey-gpu.js](../fixtures/browser/seamonkey-gpu.js) sets them, with `webgl.force-enabled`, as SeaMonkey's defaults. So a change in about:config stays across starts and uploads.
- They stay off until the offset and the video are fixed. Turning both on by default is setting the two `disabled` defaults to false there.
- Up to 04.29, Gecko saved the user.js values in each profile's `prefs.js` (hand-edited ones too), where they would override the new defaults. [seamonkey-orbisdesk.cfg](../fixtures/browser/seamonkey-orbisdesk.cfg), installed as `orbisdesk.cfg` next to `seamonkey.exe` and named by `general.config.filename`, clears those four saved values once per profile, at the end of startup, and records `orbisdesk.prefs-migration` = 1.
- Host check with SeaMonkey 2.53.24: a profile whose `prefs.js` had the four values on lost them at the first start and got the marker. At the next start, `layers.acceleration.disabled` false set by the user stayed.
- **Turning OpenGL on from 04.30:** in about:config, set `layers.acceleration.disabled` to false (and `webgl.disabled` to false for WebGL), then restart SeaMonkey. about:support shows Compositing OpenGL. The `user.js` steps in "From 04.20" apply up to 04.29.

**Next console run (04.30):** OpenGL on as above, open SeaMonkey on a page, and send the log. The `PWGL viewport` and `PWRECT` lines say which size was the window's.

## SeaMonkey ended when another program opened (04.27, 04.28)

On 04.27, SeaMonkey ended with the same access violation in both runs (run-0244, run-0245): `0xc0000005` at `nss3.dll+13c67d`, reading `7f82950d2`, on one of its threads, then its crash reporter. The address is inside `nssckbi.dll` (loaded at `7F8230000`, size `0x75000`), NSS's built-in root certificates. Shortly before, the log has `PWGUEST own L"nssckbi.dll" ... leftovers=1 live=2`, right as WFM started. So `nssckbi.dll` was unloaded while SeaMonkey still used it.

- **Why:** at each launch, kernelbase unloads the DLLs that guests left behind when they ended (W209). It keeps a DLL whose path starts with the folder of a running guest. NSS loads `nssckbi.dll` by its 8.3 path, `C:\PROG~FBU\SEAM~E5Z\nssckbi.dll`, which does not start with `C:\Program Files\SeaMonkey\`. So it counted as nobody's.
- **Not the 04.26 changes:** the banner pref and the MangoHud exclusion do not touch NSS or the profile. 04.25 had the same path; its runs did not open another program while SeaMonkey ran. Any program whose DLLs load by a short path had it, at another program's launch and at another guest's exit.
- **Fix (04.28, not built):** [build-guest-hw.py](../tools/build-guest-hw.py) compares a folder or a DLL path that has a `~` by its long form too (`GetLongPathNameW`). The log then has `PWGUEST own ...: by its 8.3 path in a live guest's folder` instead of the unload. kernelbase's `process.c` compiles for x86_64 and i386 with the builder's recorded commands, with the same warnings as before.
- **Size trace:** run-0244 and run-0245 have `PWVK size` lines only for games (all 1280x720, image equal to client). SeaMonkey did not present through Vulkan in them, so the 34-pixel offset is still open.

**Console test:** open SeaMonkey, then WFM (or another program) while it runs, and keep browsing. SeaMonkey keeps running, and the log has the `8.3 path` line.

## The GPU image 34 pixels too high (04.25 screenshot, 04.26)

A console screenshot of 04.25 with OpenGL on (2026-11-18, 19:52) shows SeaMonkey on YouTube:
- The menu bar is missing, and the navigation toolbar is cut at its top.
- There is a black band under the status bar, inside the window frame.
- The user reports that clicks act higher than where they are shown.

So the image Gecko draws is shown about 34 pixels higher than Gecko's own coordinates. Measured on the screenshot, the band is 34 pixels tall at the console's 1280x720. In run-0224 the same window was `visible=(90,46)-(976,720)` with `client=(94,76)-(972,716)`: its window is 34 pixels taller than its client area (a 26-pixel title bar and two 4-pixel borders). The page itself was still the earlier test page while YouTube loaded; the status bar says so. That is a page that had not loaded yet, not a stale frame.

**Which side is wrong:**
- The sink does not crop. `fit_image` in win32u's `ps5drv.c` scales an image to its client area, keeping its proportions and centring it. A wrong placement would give bands on two sides or a scaled image, not one band at the bottom with the content at its own scale.
- The pattern fits OpenGL's bottom-up rows. If Gecko draws a frame 34 rows taller than the image, its top 34 rows (the menu bar) fall above the image, and its last 34 rows are left empty at the bottom. The same holds if Zink flips rows with a drawable 34 rows taller than its swapchain image. Clicks then land 34 pixels below what is shown, which is what the user sees.
- So one of Gecko's compositor size, Mesa WGL's drawable size (`GetClientRect`) and Zink's swapchain (the surface's `currentExtent`, also the client area in win32u) is the window's height rather than the client's. The logs cannot say which. The only `PWVK layer` line for SeaMonkey's window is for its first swapchain (`image=878x640`, the client area; run-0234: `1280x694`, also the client). SeaMonkey replaced that swapchain at once (`PWVK forget … cleared=0`), and the new one's size was not logged.
- On the Windows host, the same SeaMonkey, Mesa and profile place everything right. So it is our route, not Gecko or Zink alone.

**This change (not built), a diagnostic:** [build-win32u-ps4.py](../tools/build-win32u-ps4.py) logs `PWVK size hwnd=… swapchain=… image=WxH client=WxH window=WxH` whenever a window's image, client or window size changes, with `differs` when the image is not the client's size, for the first 64 changes of the title. win32u's `vulkan.c` compiles with the recorded recipe, with the same three warnings as before.

**Next console run:** OpenGL on. Open SeaMonkey, then YouTube, and send the log and a photo. `differs` with an image as tall as the window points at the swapchain. An image equal to the client, with the picture still too high, points at Gecko's or WGL's drawable size.

## Other 04.26 changes for SeaMonkey

- The red bar "Your copy of SeaMonkey is old and probably has known security flaws" is gone. With updates off, SeaMonkey's `nsSuiteGlue.js` shows it at start once the build is 90 days old. [seamonkey-user.js](../fixtures/browser/seamonkey-user.js) sets `app.updatecheck.override` to `true`, its "never show".
- MangoHud is never shown for SeaMonkey, and MangoHud's RAM row now shows GiB ([MangoJuice](MANGOJUICE.md)).

## Video stays black with OpenGL on (04.26)

The user reports that with OpenGL compositing (04.25), the video area is black on YouTube and elsewhere. Run-0234 shows the decoder running: no Media Foundation decoder exists here (`h264_decoder_create GStreamer doesn't support H.264`), and Gecko decodes with its own ffvpx (`mozavcodec.dll` starts its decoding threads). So the frames are decoded on the CPU and handed to the compositor as three planes (Y, Cb, Cr).

**Host reproduction (Windows 11, AMD; reference only).** SeaMonkey 2.53.24 used this build's 64-bit `opengl32.dll` and `libgallium_wgl.dll` with the console's `user.js`. A test page recorded an animated canvas with `MediaRecorder` (VP8) and played it in a `<video>`, next to the same video drawn into a canvas.
- Basic compositing: the video is right.
- OpenGL through Mesa's llvmpipe: the video is right.
- OpenGL through Zink: the video in the canvas is right, so decoding is right. The `<video>` element shows only its brightness, tinted magenta and pink. The measured colours fit Cb and Cr both read as full scale (1.0) by Gecko's YCbCr shader, while Y is right.
- Not changed by: hiding `GL_ARB_texture_rg` (Gecko then uploads `GL_LUMINANCE` instead of `GL_R8`), GL 2.1, hiding rectangle textures, sync objects or pixel buffer objects, and `ZINK_DEBUG` `sync`, `noopt`, `optimal_keys`, `gpl`, `noshobj`, `compact`, `nobgc` or `nopc`.
- Small native programs on the same Zink pass: three planes with Gecko's sizes, strides, alignments and formats, updated every frame with `glTexSubImage2D`, Gecko's YCbCr shader text from `xul.dll` with its uniforms, and other programs drawn in between. So the GL sequence that Gecko uses and these programs do not is not found yet.

So the fault is in Zink's handling of what Gecko's OpenGL compositor does for video, not in decoding and not in Gecko alone. On the console's RADV it shows black, on the host's driver magenta. That is the same symptom family but not proven to be the same cause. It is not fixed in this change.

**Next step:** record Gecko's GL calls on the host (an API trace of the run above, with the user's approval to download the tracer), replay them on Zink and on llvmpipe, and cut the trace down to the call that differs.

## Run-0234: the second start's crash is MangoHud's (04.26)

**MangoHud is never shown for SeaMonkey (04.26).** The user's decision: [MangoJuice](MANGOJUICE.md) explains the exclusion and the show/hide fix that came with it.

Run-0234 is 04.25 with OpenGL on, in `reports/wine-hardware-w303/physical/20261118T215511Z/`. The first start presented GPU frames and exited with status 0. The second start ended about 6 s in, as in run-0218, run-0222 and run-0223.

**What `PWTOP` caught:**
- An unhandled exception with code `0x20474343` on thread `056c`, which starts at `xul.dll+8e8ff0` (Gecko's thread start; this one is the compositor). That code is the one llvm-mingw's C++ runtime raises to throw a C++ exception. So a C++ exception reached the top-level filter with no `catch` for it.
- Just before it, thread `056c` had started three threads from `libgallium_wgl.dll`: Zink's queue threads. So it was inside the GL setup, where Zink makes its Vulkan device and swapchain through MangoHud's layer.
- The stack around it is `libMangoHud.dll` and ucrtbase. Against the built DLL (its SHA-256 matches the W303 manifest), the `libMangoHud.dll` entries are libunwind and libc++abi's throw code, plus `typeinfo for std::regex_error`. The thrown object is a `std::regex_error`.
- Gecko's crash reporter (`crashreporter.exe`, `minidump-analyzer.exe`) followed, then `TerminateProcess( own process, 1 )`. Runs 0218, 0222 and 0223 ended the same way, on the compositor thread, with no `PWFAULT` and no `PWCRT`. An uncaught C++ exception explains that, since it raises no access violation and goes through none of ucrt's handlers. So those were most likely the same crash.

**Why MangoHud throws only on the second start:**
- MangoHud's Windows build has one `std::regex`: `remove_parentheses` in `src/file_utils.cpp`. `overlay_CreateSwapchainKHR` calls it on every swapchain to clean up the GPU name. The pattern is a constant and is valid.
- libc++'s regex classifies the pattern's characters with the `ctype<char>` facet of `std::locale::classic()`. With the Microsoft C runtime, libc++ fills that facet once with `__pctype_func()`, the character table of the calling thread's locale at that moment. MangoHud's static iostream setup does this when the DLL loads.
- MangoHud stays loaded from one guest to the next. SeaMonkey switches ucrt's locale away from `"C"` at start, and Wine's ucrt allocates the table of every locale except `"C"`. So the pointer MangoHud kept can outlive its table. If `(` or `)` then reads as a letter or digit, the parser throws `regex_error`.
- The second step is inferred, not observed: the log does not show which table MangoHud held. But a constant, valid pattern can only fail to parse when that table changed. The first start made the same swapchains without an exception.

**This change (not built):**
- [patch-mangohud-gpu-name.py](../tools/vk-h0/patch-mangohud-gpu-name.py): `remove_parentheses` becomes a loop. Each `(` with a `)` after it is removed up to and including that `)`, and an unmatched `(` stays. This is the regex's result, without a locale. On 12 names it gives the same text as `std::regex_replace`, and it compiles with llvm-mingw for x86_64 and i686 with `-Wall -Wextra`, without warnings.
- [build-mangohud.sh](../tools/vk-h0/build-mangohud.sh) runs it and records `src/file_utils.cpp` in its build record. [build-mangohud-i386.sh](../tools/vk-h0/build-mangohud-i386.sh) checks the marker in the tree it copies, so both HUDs get it.
- [build-wine-hardware.py](../tools/build-wine-hardware.py) refuses a 32-bit or 64-bit MangoHud tree without the marker, and records the patch's hash.
- MangoHud's settings, its hotkeys and the overlay's show/hide are not touched. MangoJuice's file still applies to every HUD.
- libc++'s other uses of that facet in MangoHud (stream `>>` into a string, for example) can still read a stale table. They do not throw, and none of them is on this path.

**The `PWFAULT` at `00000007F98C0705` is the same consequence as before.** `xul.dll` loaded at `00000007F8930000` again, so the address is `xul.dll+0xF90705`, the return from `DwmFlush` on the vsync thread. Thread `0568` could not be signalled (`PWBOOT thread_signal unavailable thread=0568 sig=3`), and it returned into the unmapped `xul.dll` after the crash. It is the same teardown problem as in run-0218 and run-0222, and the crash triggered it. It is not a second bug in this run.

**Next console run, with this change built:** OpenGL on. Start SeaMonkey, close it, start it again, and close it again. Then start one 32-bit and one 64-bit game with the HUD, and toggle it with Shift+F12. There should be no `PWTOP … code=0x20474343`, and the HUD should show the GPU name without the parenthesized part.

## 04.19 on the console (run-0218.log)

The run is `reports/wine-hardware-w303/physical/20261117T215143Z/run-0218.log`.

- **First start (module `0x101720000`, line 1733): OpenGL worked.**
  - Thread `01c8` loads system32's `opengl32.dll` and `libgallium_wgl.dll`. The `LdrGetProcedureAddress "wgl…ARB"/"gl…" not found in Opengl32.dll` warnings are Gecko looking up extension and GL 2+ entry points by export first. It gets them through `wglGetProcAddress`, as on Windows.
  - The window is presented through Zink's swapchain (`PWVK forget swapchain` lines), with full screen and the overlay. MangoHud's 64-bit layer attaches (`mangohud … guest64=1`).
  - The browser exits with status 0. On exit, `PWGUEST gl … result=1` and `PWVK guest_release … gl_devices=1 gl_memories=23 gl_bytes=33868200`: Zink's device was released and 34 MB came back.
- **Second start (module `0x101410000`): it crashed before its window.**
  - After 7.3 s, with no window yet, Gecko's own crash handler (thread `0308`) starts `crashreporter.exe`, and the guest ends with `TerminateProcess( own process, 1 )`.
  - Gecko handled that exception itself, so the log has no `PWFAULT` for it. Where it crashed is in the minidump that crashreporter wrote.
  - At that start, `opengl32.dll`, `libgallium_wgl.dll` and 64-bit `libMangoHud.dll` were still loaded (`gl=`, `gallium=` and `hud=` are non-zero). Mesa had a new screen after the release, and win32u had freed the old Zink device.
- **The `PWFAULT … address=00000007F9840705 access=8` is a consequence, not the cause.**
  - That address is `xul.dll`+0xF90705, the return address after `call DwmFlush` (`dwmapi`). It is Gecko's vsync thread (`0374`) waiting in `DwmFlush`.
  - The thread could not be signalled (`thread_signal unavailable thread=0374`). It was still in `DwmFlush` when `xul.dll` was unmapped, then returned into memory that was no longer there: an execute fault.
  - This can happen whenever a Gecko guest is ended, with Basic too. It is a guest-teardown problem of its own.
- **Host check (reference):** a 64-bit program does Gecko's WGL steps with W303's Mesa DLLs: a dummy context, `wglCreateContextAttribsARB`, 30 frames on a window, and contexts left undeleted, as with terminated threads. It then calls `pw_wgl_release_screen` and does it all again, three rounds. All three rounds succeed (`release=1`). So Mesa's release alone does not reproduce the crash. Not reproduced on the host: win32u freeing the old Zink device, and the 64-bit MangoHud layer that stays loaded across both starts.

To find the cause, the second start's crash report is needed:
- `C:\users\orbis\AppData\Roaming\Mozilla\SeaMonkey\Crash Reports\pending\` (`/data/wine-prefix/drive_c/users/orbis/AppData/Roaming/Mozilla/SeaMonkey/Crash Reports/pending/`): the `.dmp` file and its `.extra` file;
- or, in SeaMonkey, `about:crashes`, photographed.

## The crash reports and the blue area (run-0218, run-0219)

**Crash reports.** `reports/wine-hardware-w303/physical/20261117T220342Z/seamonkey-minidumps/` has two `.extra` files and two 0-byte `.dmp` files.
- **`335276ed…`: run-0218's second start.**
  - It crashed 4 s after starting (`StartupTime` 1794952528, `CrashTime` 1794952532).
  - Its `ThreadIdNameMapping` names thread 884 (0x374) `WindowsVsyncThread`, the thread of the later `PWFAULT`.
  - Adapter `0x1002`/`0x9920`, driver `35.0.21025.1024`.
- **`c05db0a6…`: another crash, 67 s later** (`SecondsSinceLastCrash`). Adapter `0x0000`/`0x0000`.
- **Neither file has a `MozCrashReason` or a `GraphicsCriticalError`.** So it was not a Gecko assertion (`MOZ_CRASH`/`MOZ_RELEASE_ASSERT`) and not a graphics error Gecko reported.
- `Notes` shows `OMTP+4`, `D2D1.1-`, `WR-`.

**The second-start crash happened before OpenGL was touched.**
- That start has none of the `LdrGetProcedureAddress … Opengl32.dll` lines that Gecko's WGL setup prints in every new browser. It crashed 4 s in; the first start's window took 12 s.
- No `PWFAULT` was logged for it. The tracer (`ps4_guest_fault_trace`, first in the handler chain) takes access violations and float exceptions only. So the exception had another code: a fast fail (an `abort`, a `/GS` failure, ucrt's invalid parameter), an illegal instruction, a stack overflow, heap corruption or a breakpoint.
- Gecko's crash reporter took it, and its minidump writer (Wine's dbghelp `MiniDumpWriteDump` over a process that is explorer plus every guest) wrote nothing.
- What the second start had that a Basic run does not: Mesa's `opengl32`/`libgallium_wgl` and the 64-bit `libMangoHud.dll` resident from the first start, a Mesa screen reset by `pw_wgl_release_screen`, and the old Zink device's memory freed by win32u.

**The `PWFAULT` at `00000007F9840705` (access 8)** is the vsync thread returning from `DwmFlush` into the unmapped `xul.dll` after the crash (see above). It is a consequence.

**The blue area.**
- In run-0219, SeaMonkey's GL compositor presents straight into its top-level window (`PWVK forget swapchain=… hwnd=0xa00c8 window=0xa00c8`). This SeaMonkey has a `MozillaCompositorWindowClass`, but nothing in the log shows such a window.
- win32u stacks each window's CPU pixels (Wine's frame and caption included), then its Vulkan image over the client area (`ps5_vulkan_frame`, `fit_image`). The release log has no line with these rectangles, so it cannot show what covers the title bar: a window of its own, or the image placed over the frame.
- There is no "decorator" component in OrbisDesk. The blue is most likely Wine's caption colour.

**Diagnostics added in 04.20:**
- [build-win32u-ps4.py](../tools/build-win32u-ps4.py): the first frame of each new swapchain in a window logs `PWVK layer hwnd=… window=… child=… image=WxH visible=… client=… passed=… at=…`, and the next two stacks handed to the sink are listed (`PWSINK stack i/n … rect=… flags=…`). The Vulkan image is `flags=0x1`.
- [build-guest-hw.py](../tools/build-guest-hw.py): `PWFAULT` also traces `0xc0000409`, `0xc000001d`, `0xc0000096`, `0xc00000fd`, `0xc0000374`, `0xc0000420` and `0x80000003`, still the first 8 of the title. For a fast fail, `access=` is its `FAST_FAIL` code.

**Next console run.** Both steps are needed for a fix.
1. **No build:** turn on the opt-in in the profile's `user.js`, and write `+seh,+loaddll,warn+debugstr` into `C:\orbis\winedebug.txt` (`/data/wine-prefix/drive_c/orbis/winedebug.txt`).
   - Start SeaMonkey, close it, and start it again.
   - Photograph the blue area, with the HUD hidden.
   - `+seh` logs every exception with its code and address. `+loaddll` gives each DLL's base address, so the address can be placed in a module. `warn+debugstr` shows what Mesa and Gecko print with `OutputDebugString`.
   - Remove `winedebug.txt` afterwards.
2. **With this change built:** the same steps. Read `PWVK layer` and the `PWSINK stack` lines for the blue area, and `PWFAULT` for the crash.

## Run-0223: the trace run on 04.21

Run-0223 is 04.21 with OpenGL on in the console's `user.js`. SeaMonkey was started, closed and started again. It is in `reports/wine-hardware-w303/physical/20261118T011404Z/`, and its crash report is `ff451770-…` in `20261117T220342Z/seamonkey-minidumps/` (the `.dmp` is empty again).

**The second start crashed 3 s in, before any WGL call.**
- There are no `Opengl32.dll` lookups after the second start, as in run-0218. Run-0222 got past the `wgl…ARB` lookups. So the crash is not tied to one point of Mesa's setup.
- `StartupTime` 1794964308, `CrashTime` 1794964311.
- Breakpad's handler thread (0x218, unnamed in `ThreadIdNameMapping`) started `crashreporter.exe` and called `TerminateProcess( own process, 1 )`.

**No `PWCRT` line and no `PWFAULT` line before the crash.**
- 04.21's ucrtbase has the `PWCRT` code (in `system32` and `x86_64-windows`). SeaMonkey's own `ucrtbase.dll` is not loaded: its `api-ms-win-crt-*` files resolve to the one already in the process.
- So no guest thread took an access violation, a float exception or a traced fatal code, and none went through ucrt's invalid parameter, pure virtual call or `abort` paths.
- Both traces covered only guest threads. Gecko's top-level filter and its ucrt handlers are the process's: a thread of no guest (explorer's, ntdll's thread pool, a thread shared by modules) reaches them as well. That is what is left, and 04.21 does not trace it.

**The first start's exit left one thread running and waited for none.**
- `PWBOOT thread_signal unavailable thread=0188 sig=3`: one of SeaMonkey's 103 other threads could not be signalled when it was terminated. It was running outside the server, so it stayed alive until its next server call. Run-0222 shows the same (`018c`).
- `other_threads_wait=4294967295 count=103`: `WaitForMultipleObjects` takes at most 64 handles and failed at once. Every guest with more than 64 threads has unloaded its modules without waiting (the archive has this result for all 144 such exits, counts 69 to 255).
- The second start mapped `xul.dll` at the same address, `00000007F8930000`.

**The blue area.** Run-0223 has the same `PWVK layer` line as run-0222: the GPU image covers the client area exactly. MangoHud drew over it (`PWOVERLAY mangohud in_front=1 presented=0x600b4 guest64=1`). `screen.png` is an older capture and the frames are black boot frames, so there is still no photo. Without one, the blue cannot be told apart from Wine's blue caption.

**This change (not built):**
- [build-guest-hw.py](../tools/build-guest-hw.py): a guest's exit waits for its other threads 64 handles at a time, within the same 2 s. This fixes the failed wait, but it does not end a thread that cannot be signalled.
- `PWGUEST thread_starts module=… id=module+offset …`: the start of each thread of the exiting guest, six to a line, so the `thread_signal unavailable` line names its code.
- `PWTOP n=… thread=… guest=… code=… address=… start=… filter=…` and up to 12 `PWTOP … stack[i] module+offset` lines: whatever reaches the top-level filter, on any thread, before the filter is called. The first 8 of the title.
- `PWCRT` now covers every thread where a handler is set, and `abort`, with `guest=` and `start=`.
- Both kernelbase units and both ucrtbase units compile for x86_64 and i386 with the builder's recipe and `-Wall`, with no new warnings.

**The default stays Basic.** The console keeps the GPU-on `user.js` for one more run.

**Next console run, with this change built:** OpenGL on. Start SeaMonkey, close it, start it again. Read `PWTOP` (or `PWCRT`) for the thread that entered the crash reporter, and the `thread_starts` entry of the unsignallable thread. If the window is blue, photograph it with the HUD hidden.

## Run-0222: the diagnostics on 04.20

Run-0222 is 04.20 with OpenGL turned on in the console's `user.js`. SeaMonkey was started, closed and started again. It is in `reports/wine-hardware-w303/physical/20261117T233219Z/`, and its crash report is `45680939-…` in `seamonkey-minidumps/`.

**The GPU image is placed correctly.**
- `PWVK layer hwnd=0xb00b4 window=0xb00b4 child=0 image=878x640 visible=(90,46)-(976,720) client=(94,76)-(972,716) … at=(94,76)-(972,716)`.
- The stack after it has five layers: the desktop, two desktop windows, SeaMonkey's frame (`(90,46)-(976,720)`, its CPU pixels) and the GPU image (`flags=0x1`) over the client area exactly. The sink draws layers opaque, without blending.
- So the GPU image does not cover the title bar, and nothing else covers the window. A blue area, if the user saw one, is inside SeaMonkey's own frame pixels (Wine's caption is blue in this theme) or inside the GPU image. Only a photo can tell which.
- In its first 7 s, SeaMonkey presented 8 frames (`PWFPS … presents=8`).

**The second start ended on Gecko's Compositor thread, in Mesa's WGL setup.**
- The `.extra`'s `ThreadIdNameMapping` names thread 664 (0x298) `Compositor` and 660 (0x294) `WindowsVsyncThread`.
- Thread 0x298 printed the `wgl…ARB` lookups that Gecko makes once a first WGL context is current. In the first start, the `gl…` entry point lookups followed them, after the compositor's own context was created. In the second start nothing followed: the crash reporter started.
- Run-0218's second start ended earlier, before the `wgl…ARB` lookups. Both ended inside Mesa's WGL setup, at different points.
- No `PWFAULT` was logged, though 04.20 traces access violations, float exceptions, fast fails, illegal and privileged instructions, stack overflows, heap corruption, assertion failures and breakpoints. So no exception reached the handlers. Gecko's crash reporter has three ways in that raise none, all through ucrt (shared by every guest, Mesa and MangoHud): the invalid parameter handler, the pure virtual call handler and `abort`'s `SIGABRT`.
- After the report, the reporter's thread 0x220 ended SeaMonkey with `TerminateProcess( own process, 1 )`.

**What the second start finds from the first:**
- Mesa's `opengl32`/`libgallium_wgl`, pinned, with its screen released while a context was left (`PWGUEST gl … result=1 contexts=1`).
- The 64-bit `libMangoHud.dll`, a Vulkan layer of Zink.
- ucrtbase's process state.
- The 32-bit world restarts Mesa after `contexts=1` (Alan Wake in run-0190). This is the first 64-bit program that does it.

**The `PWFAULT` at `00000007F98C0705` is the same one as in run-0218.** `xul.dll` loaded at `00000007F8930000` both times. So the address is `xul.dll+0xF90705`, the return from `DwmFlush` in the vsync thread. That thread could not be signalled (`PWBOOT thread_signal unavailable thread=0294`) and returned into the unmapped `xul.dll`. It is a consequence of the crash.

**Diagnostics in this change (not built):**
- [build-guest-hw.py](../tools/build-guest-hw.py): on a guest thread, ucrtbase's `_invalid_parameter`, `_get_purecall_handler`, `_purecall` and `abort` log `PWCRT <path> thread=… handler=…` and up to 12 frames as `module+offset`, the first 8 of the title.
- `PWFAULT` also traces `0xc0000417`, ucrt's invalid parameter with no handler.
- Both ucrtbase units compile for x86_64 and i386 with the builder's recipe and `-Wall`, without warnings.

**The default stays Basic.** The console has the GPU-on `user.js` from this run. Keep it for the next diagnostic run, then put the safe one back.

**Next console run, with this change built:** OpenGL on, start SeaMonkey, close it, start it again. Read the `PWCRT` lines; the frame after ucrtbase's names the module that called it. Photograph the window if it is blue.

## From 04.20: Basic by default, OpenGL as an opt-in

- [seamonkey-user.js](../fixtures/browser/seamonkey-user.js) sets `layers.acceleration.disabled` true and `layers.acceleration.force-enabled` false again, the graphics settings of 04.18.
  - Both values are set explicitly, because 04.19's user.js stored false and true in every console's `prefs.js`, and a later user.js would otherwise inherit them.
  - The Direct3D 11 block stays.
- [seamonkey-gpu.js](../fixtures/browser/seamonkey-gpu.js) stays installed. Without the opt-in it does nothing.
- **Opt-in, for testing:** in the profile's `user.js` (`/data/wine-prefix/drive_c/users/orbis/AppData/Roaming/Mozilla/SeaMonkey/Profiles/orbis/user.js`), change the two lines to `layers.acceleration.disabled` false and `layers.acceleration.force-enabled` true. Each upload replaces user.js, so the opt-in has to be made again after it.
- With the opt-in, the first start in a session was fine in run-0218. Starting SeaMonkey a second time in the same session is what crashed.

## The three paths

| Path | Verdict |
| --- | --- |
| Direct3D 11 through DXVK | Not used. In explorer's process, system32's `d3d11.dll` is DXVK's and `dxgi` is Wine's builtin (`WINEDLLOVERRIDES=…dxgi=b`). Pale Moon's D3D11 compositor there (W204/W205) logged `VK_KHR_EXTERNAL_MEMORY_WIN32 not supported` and `D3D11DXGIKeyedMutex::AcquireSync: Not supported`, never presented a frame, and hung on a second tab. 64-bit Direct3D 11 programs run alone for this reason (W190/W191), and a browser cannot. |
| Direct3D 9 layers | Do not exist in this Gecko. SeaMonkey 2.53's `xul.dll` has no `layers.prefer-d3d9`: the D3D9 compositor was removed before the Firefox 60 platform. |
| OpenGL through Mesa's WGL/Zink | **Used.** The 64-bit `opengl32.dll` in system32 is Mesa's (Zink on the linked RADV). OpenGL already runs in 64-bit guests, and Wine's kernelbase releases Zink's device when a guest ends (`pw_wgl_release_screen`, run-0178). Gecko's OpenGL compositor is not on by default on Windows. `layers.prefer-opengl` turns it on. |

## The change

- [seamonkey-user.js](../fixtures/browser/seamonkey-user.js):
  - `layers.acceleration.disabled` false and `layers.acceleration.force-enabled` true. Acceleration is on, and forced past Gecko's blocklist, which does not know Wine's adapter.
  - `gfx.blacklist.layers.direct3d11` = 3 (blocked device), with the failure ID `ORBISDESK_NO_D3D11`. That turns off D3D11 compositing, Direct2D and D3D11 ANGLE before `d3d11.dll` is loaded. user.js sets it again at every start, over a downloaded blocklist.
  - Unchanged: Direct2D off, Skia for canvas and content, no hardware video decoding, WebGL off, ANGLE off.
- [seamonkey-gpu.js](../fixtures/browser/seamonkey-gpu.js): `layers.prefer-opengl` true. [build-wine-hardware.py](../tools/build-wine-hardware.py) installs it as `C:\Program Files\SeaMonkey\defaults\pref\orbisdesk-gpu.js`.
  - This is SeaMonkey's default value, not a user.js value. So a change in about:config is stored in the console's `prefs.js` and survives starts and uploads.
  - Gecko copies user.js values into `prefs.js`, so the consoles already have `layers.acceleration.disabled` true stored there. That is why the switch is a pref that was never in user.js.

Gecko's backend order is OpenGL (only with `layers.prefer-opengl`), then D3D11 (blocked here), then Basic.

## Switching it off (04.19)

This is how 04.19 worked. From 04.20 the default is Basic; see above.


In SeaMonkey, open `about:config`, set `layers.prefer-opengl` to `false`, and restart SeaMonkey. about:support then shows Compositing `Basic`. "Reset" on the same pref turns OpenGL back on.

If SeaMonkey does not get that far, delete `/data/wine-prefix/drive_c/Program Files/SeaMonkey/defaults/pref/orbisdesk-gpu.js` over FTP. Without that file the default is false, and SeaMonkey uses Basic.

## Host test (Windows 11, AMD Radeon, AMD Vulkan driver)

This is reference only. It runs SeaMonkey 2.53.24 (the pinned archive) with W303's 64-bit `opengl32.dll` and `libgallium_wgl.dll` next to `seamonkey.exe`, `GALLIUM_DRIVER=zink`.

The data comes from about:support itself: a host-only autoconfig script writes the `Troubleshoot.jsm` graphics snapshot to a file after 20 s, with the window minimized.

| Configuration | Compositing | Notes |
| --- | --- | --- |
| 04.18 user.js | Basic | `HW_COMPOSITING` disabled by pref; `OMTP` available, 4 paint workers |
| acceleration on, D3D11 not blocked | Direct3D 11 | the system's driver: Gecko loads `d3d11.dll` from system32, so DXVK next to the exe is not used (no DXVK log) |
| + `layers.prefer-opengl`, D3D11 not blocked | Direct3D 11 | OpenGL compositing force-enabled, but D3D11 is chosen |
| + D3D11 blocked (this change) | **OpenGL** | modules: SeaMonkey's `opengl32.dll` and `libgallium_wgl.dll`, `vulkan-1.dll`, AMD's Vulkan driver; no `d3d11.dll` |
| the same + WebGL forced on | OpenGL | WebGL 1 renderer `Mesa -- zink Vulkan 1.3(AMD Radeon (TM) Graphics (AMD_PROPRIETARY))`, version `4.6 (Compatibility Profile) Mesa 26.0.8` |
| this change, Zink broken (`GALLIUM_DRIVER=nosuchdriver`) | **Basic** | Failure Log: `[OPENGL] Failed to init compositor with reason: FEATURE_FAILURE_OPENGL_CREATE_CONTEXT` |
| this change with `layers.prefer-opengl` false in `prefs.js` | **Basic** | the switch |
| this change with the old `prefs.js` (`layers.acceleration.disabled` true) | OpenGL | user.js wins |

Working set right after start: about 150–175 MB with Basic, and 285–305 MB with OpenGL through Zink (host driver included). The window was minimized, so these runs prove initialization and the choice of backend, not drawing or speed.

## Console test (04.19, or 04.18 with the two files)

On 04.18 nothing has to be built. Replace the profile's `user.js` (`/data/wine-prefix/drive_c/users/orbis/AppData/Roaming/Mozilla/SeaMonkey/Profiles/orbis/user.js`) with this change's file, and add `orbisdesk-gpu.js` in `/data/wine-prefix/drive_c/Program Files/SeaMonkey/defaults/pref/`.

1. Create `/data/orbisdesk/framegen.txt` containing `timing`. Add an empty `/data/orbisdesk/trace.txt` only on a build with the trace.txt fix ([responsiveness](SEAMONKEY_RESPONSIVENESS.md)).
2. Start OrbisDesk, open SeaMonkey and go to `about:support`. Photograph:
   - **Graphics → Compositing**: `OpenGL` expected; `Basic` means the fallback (see the Failure Log).
   - **GPU #1**: Description, Vendor ID, Device ID, Driver Version. This is what Gecko reads from Wine.
   - **WebGL 1 Driver Renderer**: `WebGL is currently disabled.` expected.
   - **Decisions**: the `OPENGL_COMPOSITING` and `D3D11_COMPOSITING` lines (`#BLOCKLIST_ORBISDESK_NO_D3D11` expected).
   - **Failure Log**, if there is one.
3. YouTube, as in run-0207: 30 s of a video playing in the page, 15 s of scrolling, then full screen for 10 s and back.
4. Open and close a menu and a tooltip, and open a second tab (Pale Moon's D3D11 compositor hung there, W205).
5. With SeaMonkey in front, show and hide the overlay and MangoHud.
6. Close SeaMonkey, open it again, check Compositing again, and close it. Then open another program (glxgears or vkcube), and close it.
7. Switch it off in about:config (`layers.prefer-opengl` false), restart SeaMonkey and check that Compositing is `Basic`. Then reset the pref.
8. Fetch the log.

What to read in the log:
- `PWGUEST load_begin … gl= gallium=`: 0 at the first start, non-zero once Mesa is loaded (it stays resident).
- `PWGUEST gl module=… result=…` when SeaMonkey exits: `result=1` released Zink's device; `kept: … other guests running` when another guest was open.
- `PWVK guest_memory … direct_free=` at each start and after each exit. It should come back after closing.
- No `DXVK` and no `d3d11` lines from SeaMonkey.
- `PWFG timing` against run-0207 (57–58 frames/s for in-page video; 10–45 while scrolling or loading).
- `PWHUNG` / `PWDUMP` if a window stops answering.

## Is it safe for 04.19?

Reasonably, with the switch, but only after one console run with the steps above.

- The fallback when the OpenGL context cannot be made is tested on the host. A Vulkan device loss or a hang in Zink later is not covered by a fallback. Gecko's own guards act only after a crash, at the next start.
- Zink's memory goes to direct memory (about 4.6 GB free in run-0207), not to the flexible pool that limited SeaMonkey before. That still has to be measured on the console.
- What it gains is not measured: the GPU does the compositing and the video's YUV conversion and scaling, but each frame still goes through Zink's present into the sink.

If the console run shows a hang, missing frames or memory that does not come back, ship 04.19 without `orbisdesk-gpu.js` (or with `layers.prefer-opengl` false). user.js alone then gives Basic, as before.

## What was tested

- Host, as in the table above. Not PS4 evidence: the console's Zink runs on the linked RADV, not on AMD's Windows driver, and draws through OrbisDesk's sink.
- `tools/build-wine-hardware.py` compiles (`py_compile`). Nothing was built.
- **Not tested:** anything on the console, WebGL in a page, drawing speed, and MangoHud with SeaMonkey on OpenGL.

## 04.34: WebGL on, compositing Basic

From 04.34, `seamonkey-gpu.js` sets `webgl.disabled` to false by default. GPU compositing (`layers.acceleration.disabled`) stays true, so pages are composited by Basic, which shows video and draws the window in the right place. WebGL canvases render through Mesa/Zink and are read back into Basic. Both switches can still be changed in about:config.
