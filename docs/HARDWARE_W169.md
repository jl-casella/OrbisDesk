<a id="w169-fs-al-reanudar-mapeos-ubicados-al-liberar-y-acceso-directo-en-el-escritorio-del-usuario-fase-6"></a>


# W169: FS when you resume, maps located when you release and direct access to the user's desktop (phase 6)

[English](HARDWARE_W169.md) | [Español](HARDWARE_W169-es.md)

APP_VER 02.68. Base W168.

<a id="prueba-de-w168"></a>


## W168 test

Report: `reports/wine-hardware-w168/physical/*`. User's response: "It closed the same."

- **Desktop:** `PWDESK launchers=1`, with an icon.
- **Spites:** a single image of origin (`PWCKEY source image 1: 832x640`); 1.420 framebuffers in 5.000 copies (before, one per copy).
- **`PWNATIVE fs32_selector=0x13`**, but the arrangement did not reach:
  - the context of the derogation follows with `fs=0000`;
  - Then the failure returned in `fs:0x18`.
  - The context that reaches `NtRaiseException` / `NtContinue` is captured by the code of 32 bits (`RtlCaptureContext`), not `wow64native`, and the path `RESET_STATE` of `cpu.c` loads its `SegFs` as it is.
- **What closed the race this time** It was the other fault.:
  - `heap_allocate_large` writes in `0x1F66000C` at the end of the race, when the game releases resources and copies files.
  - It had happened once before, in W167.

<a id="cambios"></a>


## Changes

**1. FS when resumed** (`tools/build-wow64native-ps4.py`, `cpu.c` adaptation): `iretq` of `RESET_STATE` load `fs32_sel` (`0x13`) instead of `context->SegFs`. The FS of the 32 bit code is never another: its base is the TEB, which `pw_native_restore_guest_fs` puts right away.

**2. Release a map located** (`tools/build-win32u-ps4.py`, `vulkan.c`, `win32u_vkFreeMemory`):
- In the 32 bit programs, the Vulkan mapped memory is seen in a direction that Wine reserves. RADV mapia it there with an alias of its direct memory (`tools/vk-h0/patch-mesa-placed.py`), and its unmap leaves the alias for Wine to release.
- Wine release with `MEM_RELEASE` and remap your reservation on top. If that does not replace the alias, or if by releasing the direct memory there was a gap, Wine he believes that the range is reserved and not. The big block the heap then puts there fails to write.
- **Change:** in Orbis is made `munmap` of the alias (rounded to 16 KiB) before `NtFreeVirtualMemory`. If it fails, there is `PWVK placed unmap … failed`.
- It is the most likely cause according to the code and the time of the failure, but it is not confirmed.

**3. Direct access to the user's desktop** (`tools/build-wine-hardware.py`):
- Access to File Manager goes from `C:\users\Public\Desktop` to `C:\users\orbis\Desktop`.
- The user saw that WFM's "Desktop," which opens that folder, was empty; What he put there didn't show up and access to File Manager wasn't there either.
- Explorer read the two folders, so the icon remains the same on screen, and what the user adds from WFM is also seen.

<a id="qué-se-espera"></a>


## What is expected

- Full runs without `EXCEPTION_ACCESS_VIOLATION` or output `0xc000000d`.
- In WFM, the "Desktop" shows access to File Manager. A `.lnk` copied there appears on the desk.

<a id="prueba-física"></a>


## Physical test

Report: `reports/wine-hardware-w169/physical/20261103T182143Z/`. User's response: "It closed the same." The process comes out with `0xc000000d` at 178.

**Desktop:** `PWDESK launchers=2`. File Manager appears twice because the console conserves `/data/wine-prefix` between buildings and the upload only adds files: the access of W168 in `C:\users\Public\Desktop` is still there next to that of W169 in `C:\users\orbis\Desktop`. The WFM Desktop folder appears only once, as expected.

**Career, in order:**
1. `heap_allocate_large` (ntdll i386, `+0x55a64`) fails to write the header of a block that `allocate_region` just returned (`0x1F950000`). It is the same failure of W167 (`0x1F1A0000`) and W168 (`0x1F660000`), always in heap `0x2F0000`. There was no `PWVK placed unmap … failed`.
2. The game drivers catch him and launch an exception C + +.
3. The game calls `TerminateThread(NULL)` and then fails `RtlNtStatusToDosError` reading `fs:0x18` with `eax=c0000008`.

**Why FS** fails (step 3; the change 1 did not reach because the problem is not the selector):
- `NtTerminateThread(0)` is not the current thread: Wine returns `STATUS_INVALID_HANDLE` and the thread follows.
- But `BTCpuThreadTerm` of `wow64native` took NULL as the current thread and erased its state before, including the FS base of 32 bit code. The next return of a call to the system set the basis 0, and the error code of kernelbase read `fs:0x18`.
- The evidence: in the five failures `fs:0x18` from W165 to W169, the previous line is the `PW_NATIVE_PROFILE` end of that thread, which prints `thread_term` before you erase the state.
- The exception C + + and this failure appear in all the game's login from W160, also when you leave without a career. The heap failure appears only from W167, the first build with `PW_VK_BATCH=1`. That's why the closure in the race comes from the heap, and the FS turns any output into an error closure.

The change 2 (unmap of the alias before release) did not change the heap failure. His cause is still unidentified.
