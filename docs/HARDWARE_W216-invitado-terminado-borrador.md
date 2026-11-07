<a id="w216-el-último-hilo-de-un-invitado-terminado-sale-sin-dll_thread_detach-borrador"></a>


# W216: the last thread of a finished guest comes out without DLL_THREAD_DETACH (draft)

[English](HARDWARE_W216-invitado-terminado-borrador.md) | [Español](HARDWARE_W216-invitado-terminado-borrador-es.md)

Eraser of the Wine configuration session, to join `HARDWARE_W216.md`. None of this was tested on the console.

<a id="qué-pasó-en-w214"></a>


## What happened in W214

Report: `reports/wine-hardware-w214/physical/20261104T173546Z/run-0002.log`, from the line 4807.

- **The judgment:** `C:\orbis\glxgears.exe` (OpenGL by Zink) with MangoHud failed in `libMangoHud.dll+fa984`, within `vkCreateSwapchainKHR`. The symbols of the deployed DLL give this chain:
  - `overlay_CreateSwapchainKHR`;
  - `check_fonts` and `create_fonts`;
  - `ImFontAtlas::Build`;
  - `ImFont::GrowIndex`.
- **Why?:** `ImGui::MemAlloc` asked for some 249 KB, received NULL and `GrowIndex` wrote in the direction 0 (r9 = c0000017, `STATUS_NO_MEMORY`).
  - Pale Moon was still open and tied with YouTube.
  - The flexible memory of the whole title is about 400 MB, and the boy growth of the heap comes out of there.
  - The user says that glxgears never fell without Pale Moon open.
  - The log doesn't record what kernel call failed.
- **The network of W208 worked:**
  - `0x011c` is the guest's thread;
  - their other 3 threads ended (`other_threads_wait=0`);
  - His window was destroyed and the module was downloaded.
- **The title fell the same:** The last line is `unload_own` (`count=0`). Then they just run `ps4_guest_live_remove` and `RtlExitUserThread`, and the log is cut: no beat `PWSHELL`, no tables, `process_exit`.
- **The difference with W208:** the failure output of Pale Moon in W208 He followed the same path and the title continued to walk.
  - `RtlExitUserThread` call `LdrShutdownThread`, which sends `DLL_THREAD_DETACH` to each DLL: OPENGL32, libgallium_wgl, libMangoHud, vulkan- 1 and winevulkan.
  - Here he did it on a thread with the swapchain of GL and Vulkan in half-arm, and with the working threads just finished.

<a id="cambio"></a>


## Change

`tools/build-guest-hw.py` (kernelbase `process.c`, `ps4_guest_exit_process`), with `guest-terminated-exit-w216.patch.py`:
- **What changes:** if the guest ended by `TerminateProcess` or by a failure (`guest->terminated`, W209), his last thread comes out with `NtTerminateThread`, without `DLL_THREAD_DETACH`. Windows nor does it send ads to DLL when a process is over.
- **What does not change:** the normal output.
- **Trace:** `PWGUEST last thread of module … ends (terminated, no thread detach)` or `(exit)`.

<a id="construcción"></a>


## Build

1. `python3 tools/build-guest-hw.py`.
2. `tools/link-wine-boot.py`.
3. `tools/build-wine-hardware.py`.

<a id="prueba-física"></a>


## Physical test

1. **Repeat W214:** open Pale Moon with a heavy page and then glxgears with MangoHud.
   - Si la memoria alcanza, glxgears anda.
   - If you fail again, the log should show `PWGUEST unhandled exception`, then `PWGUEST last thread … (terminated, no thread detach)`, and the desk should keep walking (beats `PWSHELL`, pictures).
2. **If the title falls before that line:** the cause is not detach, and the line marks how far it got.

<a id="no-verificado"></a>


## Not verified

- Nothing was tested on the console.
- The patch was applied on copies. `build-guest-hw.py` compiles with Python, and `process.c` passes `-fsyntax-only` with the command of `out/guest-hw/manifest.json`. There is a warning that was already before (`wcstoul`). The builder didn't run.
- That the title fell in `DLL_THREAD_DETACH` comes out of the order of the code, not a trace.
- The lack of background memory remains the same: it is only contained.
