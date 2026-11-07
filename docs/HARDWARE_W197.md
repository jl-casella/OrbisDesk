<a id="w196-y-w197-cerrar-un-juego-unity-sin-cerrar-la-app"></a>


# W196 and W197: close a Unity game without closing the app

[English](HARDWARE_W197.md) | [Español](HARDWARE_W197-es.md)

W196: APP_VER 02.95, base W195. W197: APP_VER 02.96, base W196. The result of W195 is in `docs/HARDWARE_W195.md`.

<a id="cambios"></a>


## Changes

- **W196, `tools/build-guest-hw.py`, kernelbase `TerminateProcess`:** If a guest thread ends its own process (`GetCurrentProcess()` or a handle with the same id), it is called at the guest's exit, `ps4_guest_exit_process`, as with `ExitProcess`. The log leaves `PS4 guest module … TerminateProcess( own process, N )`.
- **W197, `tools/build-guest-hw.py`, ntdll:**
  - `thread.c` has `ps4_fls_free_image`, which releases with `RtlFlsFree` the FLS slots whose cleaning function is inside an image.
  - `loader.c` calls it from `free_modref` when the module is an EXE, that is, a guest. The log leaves `PWGUEST fls_free module=… freed=N`.
  - The motif: an EXE with the CRT static MSVC records a FLS function in its own image (data cleaning by thread, with `FlsAlloc` obtained by `GetProcAddress`). Windows never download the EXE from a process, so no one releases those slots.
- **W197 Manifesto:** `tools/build-explorer-hw.py` and `tools/build-win32u-ps4.py` changed during the build (browser session diagnoses). The W197 manifesto records its new Sha, but W197 uses the previous outputs. Those diagnoses go into W198.

<a id="pruebas-físicas"></a>


## Physical evidence

**W196:** report `reports/wine-hardware-w196/physical/20261104T114634Z/`. Answer: "I closed from the game menu and again it closed OrbisDesk."
- The intercept was wide: `TerminateProcess( own process, 0 )`, 37 threads were finished and the EXE was downloaded.
- Then, at the end, the thread 0040 ran `00000001007C1FAC` into the already downloaded image: the offset 0x1fac of `The Lost Forest.exe`, a function of CRT with `if (ptd != &__acrt_initial_ptd)`.
- There was an unhandled invalid access and the title came out with `process_exit … status=0xc0000005`.

**W197:** report `reports/wine-hardware-w197/physical/20261104T120328Z/`. Answer: "It no longer closes OrbisDesk, just the game."
- `PWGUEST fls_free module=00000001007C0000 freed=2` for the game. The other guests who left leave `freed=0`.
- The desk followed and then opened Pale Moon twice.

<a id="pendiente"></a>


## Pending

- W198: the control as HID device, MangoHud with DXVK and the diagnosis of the freezing of Pale Moon as a guest.
