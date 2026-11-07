<a id="w205-pale-moon-como-invitado-se-traba-al-abrir-una-segunda-pestaña-borrador"></a>


# W205: Pale Moon as a guest it is stuck when opening a second tab (draft)

[English](HARDWARE_W205-palemoon-pestana-borrador.md) | [Español](HARDWARE_W205-palemoon-pestana-borrador-es.md)

Eraser of the browser side session, to join `HARDWARE_W205.md`. None of this was tested on the console.

<a id="qué-mostró-w204"></a>


## What did he show W204

Report: `reports/wine-hardware-w204/physical/20261104T135801Z/run-0001.log`. The user said, "It was frozen when it opened a second tab."

- **The memory arrangement of W204:**
  - there is no line `map_fixed_area mmap error`;
  - There are no lines `PWVM tryfixed_hint`, so the new path was not needed in this run.
- **The desk is still alive to the end:**
  - The scout beat is left in ~ 216 ms and pictures continue to be presented;
  - There is no `PWSERVER`, `PWLOCK` or `PWDUMP`.
  
  Only Pale Moon is stranded (main thread `0110`, line 5170).
- **Two new windows:** the thread `0110` creates two first-level windows, with the same sequence (`WTSRegisterSessionNotification`, a `tmpmap` of the server, `DwmExtendFrameIntoClientArea`):
  - `0x30166` in line 6675: then Pale Moon goes on, with dozens of resolutions of names;
  - `0x7012A` in the line 6879: then no thread of Pale Moon records anything else.
- **Direct3D 11 remains active in Pale Moon** (lines 5981 a 6400):
  - `VK_KHR_EXTERNAL_MEMORY_WIN32 not supported`;
  - `D3D11DXGIKeyedMutex::AcquireSync: Not supported`;
  - no `PWVK show_frame` appears;
  - after `0x7012A` there are no new lines of DXVK.
  
  The `layers.acceleration.enabled` preference remains in `true` in the default profile you use `palemooncopy.exe`.
- **Why there is no overflow:** `PWDUMP` only runs when the scout thread is stopped, so it didn't run.

It is not known what the thread `0110` is waiting for.

<a id="prueba-sin-construir-nada-w204"></a>


## Test without building anything (W204)

As in W197:
1. In `palemooncopy.exe`, go to `about:config` and put `layers.acceleration.enabled` in `false`.
2. Reset Pale Moon.
3. Open a second tab.

**What to look for in the log:** that there are no lines of DXVK (`D3D11InternalCreateDevice`).

**How to read the result:** if it does not fit, the cause is in the composer Direct3D 11 of Pale Moon within the process of exploring. As a separate title, Pale Moon runs with the acceleration off and `d3d11` disabled.

<a id="cambio-diagnóstico"></a>


## Change (diagnosis)

`tools/build-explorer-hw.py`, with `hung-window-w205.patch.py`:
- **What you review:** every 2 s, the explorer observer looks for a visible first-level window of another thread (not the explorer) that Wine considers hanging. `IsHungAppWindow` the mark like this after 5 s without reading messages.
- **When it acts:** when you're wearing 8 like this, and again to the 70 s.
- **What does it record?:** `PWHUNG` with:
  - the window, its thread and how many windows are hanging;
  - the class;
  - the title, read with `InternalGetWindowText`, which does not send messages.
  
  Then he runs the same wire-tilt (`PWDUMP`) that already exists.
- **Just reading:** nothing is sent to the hanging window and nothing is recovered.

<a id="construcción"></a>


## Build

1. `python3 tools/build-explorer-hw.py`.
2. `tools/link-wine-boot.py`.
3. `tools/build-wine-hardware.py`.

<a id="prueba-física"></a>


## Physical test

1. Open `palemooncopy.exe` and open a second tab.
2. Wait 2 minutes.
3. **What to look for in the log:**
   - `PWHUNG hwnd=… tid=… class=… title=…`;
   - the two bands `PWDUMP`. The thread of `PWHUNG` and its frames show what call Wine you are waiting for (`win32u`, `ntdll`, `user32`, ...), and the other threads of Pale Moon, what do they do.

<a id="no-verificado"></a>


## Not verified

- Nothing was tested on the console.
- The change was compiled only with `-fsyntax-only` (mingw), on a copy of the current overlay.
- The frameworks within the `xul.dll` they come out as displacements (`xul.dll+…`); Pale Moon no symbols.
- If the hanging thread does not respond to `GetThreadContext`, the tilt stops on that thread.
