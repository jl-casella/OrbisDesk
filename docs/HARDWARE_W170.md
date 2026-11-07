<a id="w170-salida-de-hilo-con-null-diagnóstico-del-fallo-del-heap-escritorio-sin-duplicado-y-apariencia-fase-6"></a>


# W170: yarn output with NULL, heap failure diagnosis, unduplicated desk and appearance (phase 6)

[English](HARDWARE_W170.md) | [Español](HARDWARE_W170-es.md)

APP_VER 02.69. Base W169. The result of W169 is in `docs/HARDWARE_W169.md`.

<a id="cambios"></a>


## Changes

**1. `TerminateThread(NULL)` no longer erases the state of the thread** (`tools/build-wow64native-ps4.py`, `cpu.c` adaptation:
- `BTCpuThreadTerm` only erases the state if the handle is the pseudo-handle of the current thread, or a real handle whose `ClientId` is that of the current thread.
- With NULL, he's doing nothing. `NtTerminateThread(0)` fails with `STATUS_INVALID_HANDLE` and the thread is still in 32 bit code with its FS intact.
- It affects all output of SuperMarioKart. It doesn't fix the heap failure, which is what triggers the exit at the end of the race.

**2. Diagnosis of heap failure** (only log, result does not change):
- `tools/build-audio-ps4.py`, `virtual.c` of ntdll, `virtual_handle_fault`: when an access fails on a page that Wine has as accessible, records `PWVM fault`. The line includes the direction, the view that contains it (base, size, protection) and the result of reapplying the protection that Wine already has recorded. `ENOMEM` indicates that the page is not mapped in the host.
- `tools/build-win32u-ps4.py`, `vulkan.c`: `PWVK placed map` and `PWVK placed free` with each range of the mapping locations, to see if the direction of the failure was before memory Vulkan.

**3. Exobsolete files of the prefix** (`tools/build-wine-hardware.py`, `tools/upload-hardware.py`):
- The manifest list `obsolete_files`. The rise erases them by FTP after the runtime: only low routes `wine-prefix/` that the build does not install, and if they are no longer there, it is no mistake.
- First entry: `C:\users\Public\Desktop\File Manager.lnk` of W168, which doubled the icon on the desktop.

**4. Appearance**, prepared at the user-approved direct access session:
- PKG icon: a window in the shape of PS4 (`out/app-icon/icon0.png`, `tools/orbis_package.py`).
- Start button: the same icon drawn with GDI, instead of the class icon (`tools/build-explorer-hw.py`).
- Desktop background: public domain photo CC0 converted to 1280x720 (`out/wallpaper-cc0/`, credit in `THIRD_PARTY.md`).
- Load screen: black, with the logo and a progress bar that advances with the starter marks (`native/wine_hardware.c`, glyphus `%` in `native/hw_text.h`).

<a id="qué-se-espera"></a>


## What is expected

- A single icon of File Manager on the desk.
- When you leave SuperMarioKart from the menu, no failure `fs:0x18` or output `0xc000000d`.
- At the end of the race the heap failure can be repeated. If it passes, the log has `PWVM fault` with the view and the status of the page, to decide the correction.

<a id="prueba-física"></a>


## Physical test

Report: `reports/wine-hardware-w170/physical/20261103T184320Z/`. User's response: "It closed on departure."

- **Desktop:** `PWDESK launchers=1`. The rise erased the old access (`obsolete_deleted 1`).
- **Output:** the process comes out with `status=0x00000000`, without failure `fs:0x18`; The change 1 worked. What the user saw as closing is the game's output after its exception management.
- **The heap failure** passed again, now as you leave the menu, in the same direction as W169: `PWVM fault addr=0x1f95000c err=1 vprot=0x23 view=0x1f950000 size=0x2f0000 protect=0x3 reprotect=0 errno=0`.
  - The view is of the heap (3 MB), Wine has it compromised and read/write, and reapply that protection returns 0.
  - There are no maps Vulkan located nearby: the 56 `PWVK placed map` are between `0x10240000` and `0x1ABD0000`.
- **Hypothesis:** in Orbis a reservation `PROT_NONE` has no memory behind it and the kernel ignores any changes in protection over it. `pw_wine_memory_protect` compromises with flexible memory only what `sceKernelVirtualQuery` reports as uncompromised. If a page remains in a state that the kernel reports as compromised but without the protection requested, `mprotect` returns 0 without effect. W171 checks.
