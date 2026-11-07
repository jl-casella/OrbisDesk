<a id="wxxx-pale-moon-como-invitado-congela-el-escritorio-diagnóstico-borrador"></a>


# Wxxx: Pale Moon as guest freezes the desktop (diagnosis, draft)

[English](HARDWARE_Wxxx-palemoon-invitado-borrador.md) | [Español](HARDWARE_Wxxx-palemoon-invitado-borrador-es.md)

Eraser of the browser side session. The main session assigns the number and binds it to the `HARDWARE_Wxxx.md` you touch. None of this was tested on the console.

<a id="qué-se-sabe"></a>


## What is known

Reports: W192 `reports/wine-hardware-w192/physical/20261104T101756Z/run-0003.log` (from the line 3912) and W195 `reports/wine-hardware-w195/physical/20261104T112911Z/run-0002.log` (from 1656).

- **How it starts:** `C:\Program Files\Pale Moon\palemooncopy.exe` does not have the mark `OrbisRunsAlone`. That's why it opens as a guest within an explorer (`PWGUEST load_begin`, main thread `0040` in W195).
- **Do not use our profile:**
  - writes in `…\Pale Moon\Profiles\e3nzp9am.default` (lines `PWDELETE` of W195);
  - solves names with `family=0` (IPv4 and IPv6), while our `user.js` requests only IPv4.
  
  Nor does it get the `DllOverrides` of `AppDefaults\palemoon.exe` (`d3d11=""`, `d3d10core=""`), because that key uses the name of the executable. So use the hardware acceleration: DXVK create a device D3D11 in the two runs.
- **What he records DXVK:**
  - `Failed to create shared resource: VK_KHR_EXTERNAL_MEMORY_WIN32 not supported`;
  - `D3D11DXGIKeyedMutex::AcquireSync: Not supported`;
  - no `PWVK show_frame` of Pale Moon appears: its composer did not come to present with Vulkan.
- **The timing of the hang:** the scout interface thread (`0024`) stops beating:
  - W195: at ~ 107 s, while solving `palemoon.start.me`, `static.cloudflareinsights.com` and `c.start.me`;
  - W192: just after solving `www.palemoon.org` and `start.palemoon.org`.
  
  Its last mark is `stage=36`, which is after `sync_taskbar_buttons()`: the thread returned to its message loop and was stuck into something without a mark.
- **Then:** no thread records anything else. They only follow:
  - the scout observer (`0030`), which still gets `GetGUIThreadInfo` and `GetForegroundWindow` from the server;
  - the pitcher (`input_event`).
- **It's not a critical section of Win32:** W192 He waited. 139 s and the notice of 60 s of `RtlpWaitForCriticalSection`.
- **It doesn't look like a hang of GPU:**
  - the composer (`native/hw_sink_gpu/hw_sink_gpu.c`) expects his fence with 1 s limit and would warn `PWSINK gpu_failed`;
  - RADV (`ac_ps4_drm.c`, `ps4_wait_seq`) would warn `GPU hang?` after 2 s.
  
  Neither one of us shows up.
- **It's not the W184/W185:** hang monitor, no lines `PWTHREAD`.

**Hypothesis, unconfirmed:** a thread of Pale Moon is stuck while having a lock of the Unix part that the desktop also uses. The candidates shall:
- the USER lock of win32u (`user_mutex`);
- the `screen_lock` of ps5drv;
- the lock of the composer (`pw_wine_sink_ps4.c`, taken with `screen_lock` taken).

A pthread lock doesn't give notice when waiting, and that matches the silence. The logs are not enough to know which one is or what the owner does.

<a id="prueba-sin-construir-nada-w195-o-w196"></a>


## Test without building anything (W195 or W196)

Separates hardware acceleration from the execution as a guest:

1. Open `palemooncopy.exe`.
2. Write `about:config` in the address bar and put `layers.acceleration.enabled` in `false`. It's the same preference that our `user.js` uses. In the Pale Moon options is the "Use hardware acceleration when available."
3. Close Pale Moon and reopen `palemooncopy.exe`.
4. Sail to two or three places and wait 2 minutes.

**What to look for in the log:**
- if `Creating resource descriptor heap` or `D3D11` of DXVK no longer appears;
- if `heartbeat_age_ms` is still in ~ 230.

**How to read the result:**
- If it does not freeze, the cause is on the path D3D11/DXVK within the process of exploring.
- If it freezes the same, it doesn't have to do with the GPU.

<a id="cambio-diagnóstico"></a>


## Change (diagnosis)

It only adds traces: nothing recovers the hang, shortens a wait, or jumps a lock. The changes are in `tools/build-explorer-hw.py` and `tools/build-win32u-ps4.py`.

- **scout (`PWDUMP`):** the scout observer goes through all the process threads, Pale Moon included. It does it once when the beat of the interface thread has 8 s and another at 70 s. For each thread it records:
  - its start address (module + displacement);
  - their records;
  - up to 20 side frames Windows.
  
  A thread strapped into a Unix call shows the call you made (`win32u`, `ntdll`, `winevulkan`). Each thread is suspended only for `GetThreadContext` (depends on the signals by thread of W195). The path of the stack is within the limits of the thread pile and in the code of loaded modules. The first line, `PWDUMP begin`, shows the owner of the loader lock.
- **win32u (`PWLOCK`):** if a thread expects more than 5 s the USER lock or ps5drv `screen_lock` is recorded with the own thread (`PWLOCK wait lock=… tid=… owner=… waited_s=…`). When it gets there, it is recorded `PWLOCK got`. The waiting is still limitless, as before.
  
  If `pthread_mutex_timedlock` does not work on the console, there is a line `PWLOCK timedlock … rc=…` and the locks return to normal waiting without notice.

<a id="construcción"></a>


## Build

1. `tools/build-explorer-hw.py` and `tools/build-win32u-ps4.py` already have the changes (applied with `diag-freeze.patch.py`).
2. Run those two builders and then `tools/link-wine-boot.py` and `tools/build-wine-hardware.py`, as in any W you touch explore and win32u.

<a id="prueba-física"></a>


## Physical test

1. Open `palemooncopy.exe` (with acceleration as it comes) and navigate until it freezes.
2. Wait 2 minutes before you download the log.
3. **What to look for in the log:**
   - `PWLOCK wait …`: what a lock and what thread it has;
   - the two bands `PWDUMP` (at 8 s and 70 s): what does the master thread do, what does `0024` and in what call is each thread of Pale Moon;
   - If a band is cut after a line `start` without `rip`, that thread did not give its context.

<a id="no-verificado"></a>


## Not verified

- Nothing was tested on the console.
- The two changes were compiled only with `-fsyntax-only`, with the recipe of each builder, on copies of the current overlay; The builders didn't run.
- It was not found in the console that `pthread_mutex_timedlock` of the SDK works. If it doesn't work, `PWLOCK` let it know once and don't report any more waiting.
- It is not known if `GetThreadContext` responds for a stranded thread within a pthread lock. If you don't respond, the band `PWDUMP` stops on that thread.
