# GPU memory of guests that end inside explorer

[English](HARDWARE_guest-gpu-memory.md) | [Español](HARDWARE_guest-gpu-memory-es.md)

## Symptom

On 2026-11-16 (console app 04.08, W303 base), Alan Wake's American Nightmare (Steam, 32-bit, run as a guest) was
started eight times in one OrbisDesk session (`reports/pop-phase-b/physical/20261116T211401Z/run-0165.log`). The
last start ran with wined3d + OpenGL and closed while loading a level, with
`PWVM commit_backing ... direct memory failed; no memory`. `tools/check-guest-memory.py` on that log:

| Start | Free at start | How it ended | Lost before the next start |
| --- | --- | --- | --- |
| 1 | 4.97 GB | exit 1 (early, wined3d) | 0.03 GB |
| 3 | 4.92 GB | overlay terminate after `VK_ERROR_DEVICE_LOST` (DXVK) | 0.75 GB |
| 4 | 4.17 GB | overlay terminate after `VK_ERROR_DEVICE_LOST` (DXVK) | 0.72 GB |
| 5 | 3.46 GB | ended with its console before drawing | 0.13 GB |
| 6 | 3.33 GB | overlay terminate | 0.63 GB |
| 7 | 2.70 GB | overlay terminate (wined3d-vulkan selected) | 0.66 GB |
| 8 | 2.04 GB | exit 0 at an MSAA error dialog, before drawing | 0.02 GB |
| 9 | 2.03 GB | wined3d + OpenGL, 6 commits found no memory | - |

Every run that drew with Direct3D and was then terminated lost 0.63-0.75 GB. The runs that ended by themselves
lost 0.02-0.13 GB, but none of them had drawn a level, so the log has no clean "drew, then exited normally"
control. Start 2 (`steam-open.exe`) and the non-GPU guests of the previous session (`run-0164.log`, 31 starts) lost
at most 0.02 GB each.

## Cause

The guests share explorer's process, so memory a guest does not give back stays lost until OrbisDesk ends.
RADV's buffers on the console are direct memory: Crema's `ac_ps4_drm.c` allocates each one with
`sceKernelAllocateDirectMemory` and gives it back only when the buffer is freed (`vkFreeMemory`), after the GPU has
finished with it. `ac_drm_device_deinitialize` does nothing. A guest whose threads are terminated (the overlay's
close, a crash) never releases its Direct3D device, so DXVK or wined3d never frees the device memory that holds its
textures and buffers. The unload logs show what was released: `PWGUEST memory module=00400000 regions=0 released=0`,
`detach skipped (terminated)`, and `system_modules ... loaded=48 unloaded=12`, with DXVK's `d3d9.dll` still loaded.
Nothing frees the Vulkan objects.

## Change

- `tools/build-win32u-ps4.py`: win32u's Vulkan layer records which guest created each `VkDevice`, using the
  creating thread's `TEB.UserReserved[0]` (the 32-bit TEB for a WoW64 thread, as the W285 audio streams do). It
  also records the device of each `VkDeviceMemory`. A new call, `pw_guest_unix_call_funcs[0]` (with a WoW64 table),
  frees the device memory that a guest's devices still hold. Memory is never freed twice: memory that is not in the
  record has already been freed, either with its guest or with its device. A program's own `vkDestroyDevice` first
  frees any device memory the program left.
- `platform/ps4/pw_wine_unixlibs.c`: the static Unix library `pwguest.so` with those tables.
- `tools/build-guest-hw.py`: `ps4_guest_unload` calls it after the guest's threads have ended and after its modules'
  and the system modules' `DllMain(DETACH)` have run. The result is logged as
  `PWGUEST vulkan module=... devices=... memories=... bytes=... shared=... others=...`. win32u logs
  `PWVK guest_release`.
- `tools/check-guest-memory.py`: the table above, from any console log. `--max-loss-gb` fails on a large loss.

## Deliberately not changed, still open

- The guest's `VkDevice` objects are kept. Destroying one waits for its queues, and a terminated thread may have
  left them busy or locked. Device-level RADV buffers, command pools, descriptor pools and swapchain images stay.
- Zink's device (`libgallium_wgl.dll`, pinned for every guest) is excluded from the per-guest release, along with
  its memory. It is the process's device, so its memory is freed only as described in the next section.
- Crema keeps up to 96 MB of freed buffers per device in quarantine. This memory is only given back by later
  activity on the same device, so up to about 0.1 GB per dead device can remain.
- After `PWOVERLAY terminate`, the log shows threads of the terminated guest faulting in its unloaded modules
  (`PWFAULT ... thread=00c0 ... stack overflow`). Terminated threads can keep running for a while after the wait
  returns. Their stacks are not counted here.

## A terminated OpenGL guest (run-0178)

`reports/wine-hardware-w303/physical/20261117T105502Z/run-0178.log` (console app 04.11, which already has the
change above): the same game ran with wined3d + OpenGL (`choice=wined3d-gl`), so it drew through Mesa's
`libgallium_wgl.dll` and Zink. It was closed from the overlay: WM_CLOSE first, then, after 3 s,
`PWOVERLAY terminate ... threads=38`. Free memory at the next start was 3.50 GB, after 4.77 GB at its own start, a
loss of 1.27 GB. The release did run on that path: `PWGUEST vulkan module=00400000 devices=0 memories=0 bytes=0
shared=1 others=1`. The guest's only device was Zink's, which the release skips.

Mesa's WGL has one screen, and so one Zink `VkDevice`, for the whole process (one per world). The first OpenGL guest
creates it, and `libgallium_wgl.dll` stays loaded (W173). A guest whose threads are terminated never deletes its GL
contexts, so their textures and buffers stay in that device's memory. Zink's queue threads, created from the
guest's threads, are terminated with them. Deleting the contexts from another thread can wait for those threads or
for locks they held. Instead:

- `tools/vk-h0/patch-mesa-wgl-guest.py` (run by both `build-mesa-zink*.sh`): each WGL context records the guest of
  the thread that created it, read from `TEB.UserReserved[0]` (0 for the desktop's own threads). A new export,
  `pw_wgl_release_screen`, makes the WGL device forget its screen, contexts and framebuffers without touching them,
  unless a desktop thread's context is left. The next context creates a new screen with new threads.
- `tools/build-guest-hw.py`: `ps4_guest_release_vulkan` first calls it, but only when no other guest is running in
  the same world. It logs `PWGUEST gl module=... result=... contexts=... desktop=...`, or `kept: N other guests
  running`.
- `tools/build-win32u-ps4.py`: with `PW_GUEST_RELEASE_GL`, the memory of that world's Zink devices is freed and
  logged as `gl_devices=... gl_memories=... gl_bytes=...`. The devices are kept, as for any guest.
- `tools/check-guest-memory.py` adds `gl_bytes` to "vk freed" and shows the `PWGUEST gl` result.

What this does not cover:

- With another guest running in the same world, nothing is released. The memory stays until a later guest ends
  alone.
- The old screen's CPU-side objects (contexts, Zink's caches in heap memory) are left in place.
- Free memory is direct memory. The 32-bit world's virtual memory first comes from the flexible pool, and
  `pw_flexible_low` (66 MB left, under the 64 MiB reserve) means later commits came from direct memory. A guest's
  heap blocks are not among the regions recorded since W208 (`regions=0`), and `pw_decommit_host` keeps the direct
  memory of a decommitted range. Part of the 1.27 GB may therefore be the game's heap rather than Zink's. The new
  `gl_bytes` value shows how much was Zink's.
- This change requires rebuilding Mesa for both architectures (`build-mesa-zink.sh`, `build-mesa-zink-i386.sh`).
  Without the new export, kernelbase logs `kept: libgallium_wgl has no pw_wgl_release_screen`.

## What was still lost after that change (run-0185)

`reports/wine-hardware-w303/physical/20261117T132951Z/run-0185.log` (console app 04.12, with the change above and Mesa
rebuilt): the same game, with wined3d + OpenGL, was terminated from the overlay. The release ran:
`PWGUEST gl module=00400000 result=1 contexts=1 desktop=0`, then `gl_devices=1 gl_memories=112 gl_bytes=523534416`.
Free memory at the next start was still 0.71 GB lower (4.96 GB, then 4.25 GB).

The free figure in these logs is `GlobalMemoryStatusEx`'s available memory: the free direct memory plus the free
flexible memory (`platform/ps4/pw_wine_memory.c`). This build adds up every allocated direct range to find the free
direct memory (`free_source=summed` in the `PWBOOT memory_info` line, and no `PWMEM direct_free` switch afterwards). The
logged total is the direct memory size plus the free flexible memory, so a change in the total is the flexible part
alone. `tools/check-guest-memory.py` now prints the split:

| Log | Loss | Flexible | Direct |
| --- | --- | --- | --- |
| run-0178, before the change | 1.27 GB | 0.21 GB | 1.06 GB |
| run-0185 | 0.71 GB | 0.22 GB | 0.49 GB |
| run-0165, DXVK runs that drew and were terminated | 0.63-0.75 GB | 0.03-0.11 GB | 0.60-0.66 GB |

The change took 0.57 GB off the direct part, close to the 524 MB it freed. The flexible part is about the same in
both logs, so the Mesa change did not affect it. run-0185 has no `pw_flexible_low` line, so the pool did not run low
there.

Direct memory has two users here: RADV's buffers and, since W175, Wine's own commits of 1 MiB or more, made with
`sceKernelAllocateDirectMemory` (`tools/build-audio-ps4.py`). A commit goes back only when Wine releases or decommits
its range. From the code, the remaining 0.49 GB can be:

- Large commits the terminated guest left: the game's heap segments and `VirtualAlloc` blocks, and wined3d's
  system-memory copies of textures and buffers. The guest's `Direct3D` device is never released, and
  `PWGUEST memory module=00400000 regions=0 released=0` shows that no region of the guest was given back.
- Crema frees a buffer once the GPU has finished with it, and keeps the newest 96 MB of freed buffers per device. It
  releases them only when that device allocates or frees again. The next OpenGL program's screen uses the same Zink
  instance, so its activity should release them. Until then, up to 96 MB stays.
- The kept Zink `VkDevice` and the objects Zink created on it are not destroyed. RADV allocates their direct memory
  itself, not through `vkAllocateMemory`, so win32u's record does not hold it. This includes command buffers,
  descriptor pools, query pools, compiled shader code, and the queue's ring and scratch buffers.

The flexible part, 0.22 GB, is CPU memory the guest left in smaller commits, for example heap blocks under 1 MiB,
the abandoned screen's objects and the stacks of its threads.

This log cannot tell these apart. The next build therefore adds a probe and no further release:

- `tools/build-audio-ps4.py`: ntdll's `pw_vm_direct_bytes` returns how much direct memory Wine's commits hold now.
- `tools/build-win32u-ps4.py`: `PWVK guest_memory owner=... why=... direct_free=... flexible=... wine_direct=...
  wine_runs=... heaps=...`, with `why=release_before` and `why=release_after` around the release, and a new call,
  `pw_guest_unix_call_funcs[1]`, for `why=start`.
- `tools/build-guest-hw.py`: kernelbase makes that call after `PWGUEST load_begin`, and passes the world's process
  heap count (`RtlGetProcessHeaps`) in both calls.
- `tools/check-guest-memory.py` shows `of the direct: Wine commits ..., other ...` and the heap counts from start to
  start, and `release gave back direct ... MB`.

How to read the next log:

- Most of the direct loss in `Wine commits`: the guest's own memory. The next step would be releasing a terminated
  guest's commits, which W208's region record does not cover today.
- Most of it in `other`, with `release gave back direct` well below `gl_bytes`: freed buffers still waiting in
  Crema's quarantine or for the GPU.
- Most of it in `other`, with `release gave back direct` close to `gl_bytes`: memory of the kept device's own
  objects. The next step would be destroying that device and the objects Zink made on it.
- More heaps at the next start than at the guest's start: heaps the guest created and never destroyed.

Console test for this probe: start the game with wined3d + OpenGL, let it draw, and close it from the overlay. Do
this twice, to see whether the loss repeats and whether the second screen releases the quarantine. Then start a
program that does not use the GPU (WFM), so there is one more start line.

## Heaps, and the second OpenGL guest (run-0190)

`reports/wine-hardware-w303/physical/20261117T151510Z/run-0190.log` (04.13, with the probe above): the same game
on wined3d + OpenGL was started, terminated from the overlay, then WFM was started, then the game again, also
terminated. `tools/check-guest-memory.py` gives, for the first run:

| | GB |
| --- | --- |
| Lost until the next start | 0.86 |
| Flexible | 0.29 |
| Direct, Wine commits of 1 MiB or more | 0.41 |
| Direct, other | 0.16 |
| Direct memory the release gave back (`gl_bytes` 532 MB) | 0.55 |

The 32-bit world's process heaps went from 2 at the game's start to 5 at its unload, and `PWGUEST memory ...
regions=0`: the game's own code reserved nothing with `VirtualAlloc` that W208 could release. In Wine's heap a
block of about 508 KB or more is a separate commit (direct memory from 1 MiB, W175), and smaller blocks grow the heap
in 64 KB steps (flexible memory). So both parts can be heap memory that the terminated guest never freed, and no heap
was ever destroyed. The game loads `msvcr100.dll` from `syswow64`; that module counts as a system module and stays
loaded after the guest (`system_modules ... unloaded=0`), so its C runtime heap is a likely holder. The log does not
say which heap holds the bytes.

The second run printed `PWGUEST gl ... result=1`, but `release_before` and `release_after` show the same free
memory and there is no `PWVK guest_release` line. Zink keeps one `VkDevice` per physical device in a static
`device_table` (`zink_screen.c`, `get_device`), and its instance is static too, so the screen Mesa's WGL makes after
`pw_wgl_release_screen` takes the same device again. win32u had marked that device `abandoned` after the first
release and skipped it from then on.

The `wine_direct` values are real. The hardware ELF (`build/wine-hardware-w303/wine.elf`) has one global
`pw_vm_direct_bytes`, 319 bytes long, next to `pw_direct_release` in `virtual.c`. Only the boot ELF, which links the
proven `virtual.o`, has the weak 14-byte default from win32u, which answers 0.

Changes:

- `tools/build-win32u-ps4.py`: every time kernelbase passes `PW_GUEST_RELEASE_GL`, the memory recorded on this
  world's Zink devices is freed, not only the first time.
- `tools/build-guest-hw.py`: kernelbase's `HeapCreate` records a heap created on a guest's thread, or while its
  image loads, with the code address that created it. `HeapDestroy` removes the record first. After the guest's own
  modules are unloaded, `ps4_guest_release_heaps` logs the free memory (`PWVK guest_memory ... why=heaps_before`).
  It then destroys each recorded heap of that guest whose creating code is no longer in any loaded module, or was
  outside every module. It logs a heap whose creating module is still loaded as `PWGUEST heap ... kept: made by
  <module>, still loaded`, and the total as `PWGUEST heaps module=... destroyed= kept= gone=`. The process heap,
  and a heap no longer in the process's list, are never destroyed.
- `tools/check-guest-memory.py`: `heaps destroyed N, kept M (<modules>), gave back direct X MB, flexible Y MB`,
  from `heaps_before` to `release_before`. The heap counts in the `of the direct` note are now the guest's own
  world's, at its unload; the next start can be in the other world.

What this does not cover:

- A heap of a module that stays loaded is kept, because that module's globals still point at it. If the next log
  names `msvcr100.dll` (or another C runtime) and most of the loss stays, the next step is retiring that runtime when
  a terminated guest was the last user in its world: unmapping it without `DllMain` and then destroying its heap.
  That is not done blindly. Other kept modules may import it, and the second run in run-0190 shows that the next
  guest currently reuses the kept runtime without a problem.
- Process heap blocks the guest left (wined3d allocates there) are not attributed to a guest, so they stay.
- The guest's threads that could not be signalled (`PWBOOT thread_signal unavailable`) still run after the unload
  and fault in unmapped code (`PWFAULT`). A heap destroyed under one of them adds to faults that happen already.
- Zink's shared device has one `queue_lock`. A terminated thread that held it would block the next screen.
  `pw_wgl_release_screen` resets only the WGL frontend's locks.

Console test: as for run-0190. Start the game on wined3d + OpenGL, let it draw, and close it from the overlay. Do
it twice, with WFM between the two, then start WFM once more so the second run has a following start. Then run
`python3 -I tools/check-guest-memory.py <run log>`. Expected: `release gave back direct` close to `gl_bytes` on both
runs, a `heaps ...` note on both, and the `PWGUEST heap ... kept` lines naming any C runtime that keeps a heap.

## Pinned imports, and heaps nothing recorded (run-0203)

`reports/wine-hardware-w303/physical/20261117T170454Z/run-0203.log` (04.15, with the run-0190 change): Alan Wake on
wined3d + OpenGL, terminated from the overlay, then WFM, vkcube and Task Manager, then Portal 2, which ended by
itself (status 100), then WFM again. `tools/check-guest-memory.py` gives:

| | Alan Wake | Portal 2 |
| --- | --- | --- |
| Lost until the next start (GB) | 0.81 | 0.75 |
| Flexible (GB) | 0.27 | 0.02 |
| Direct, Wine commits of 1 MiB or more (GB) | 0.38 | 0.63 |
| Direct, other (GB) | 0.16 | 0.10 |
| Vulkan memory freed | 511 MB (`gl_bytes`) | 271 MB |
| Heaps of the 32-bit world, start -> unload | 2 -> 5 | 5 -> 8 |
| `PWGUEST heaps` | destroyed 0, kept 0 | destroyed 0, kept 0 |

Portal 2 starts with 5 heaps: the 3 that Alan Wake left are still there. The log shows two causes.

**Nothing was recorded.** The run-0190 record was in kernelbase's `HeapCreate`, and nothing called it. Wine's
kernel32 has its own `HeapCreate` (`dlls/kernel32/heap.c`), not a forward to kernelbase. Programs and their C runtimes
import the kernel32 one, and this build does not rebuild kernel32. So the record list stayed empty, and
`destroyed=0 kept=0 gone=0` was printed for every guest.

**The guest's system modules stopped unloading in 04.13.** In run-0185 (04.12), the same terminated game unloaded 13
of its 48 system modules, `msvcr100.dll`, `MSVCP100.dll`, `d3dx9_43.dll` and `XINPUT1_3.dll` among them. Their
`DllMain(DETACH)` ran, and the C runtime destroyed its own heap. In run-0190 and run-0203 the count is
`system_modules ... loaded=48 unloaded=0`, and Portal 2 unloaded 4 of 57. Wine's `process_attach` pins every module
it attaches with a non-NULL `lpReserved` (`if (lpReserved) wm->ldr.LoadCount = -1`), because on Windows a process
keeps its static imports for its whole life. The run-0183 change for Warcraft III passes a context as `lpReserved` to
a guest EXE's imports, and `process_attach` hands the same pointer down the whole import tree. Every module the guest
EXE imports, directly or indirectly, became pinned:

- Its own modules were unpinned again at its end by d13 (`was pinned by the program: unpinned`): no such line in
  run-0185, 15 in run-0203.
- Its system modules stayed for the life of the title, with their C runtime heaps. The next guest that used them
  started on the earlier guest's runtime state.

Changes (`tools/build-guest-hw.py`; they replace the run-0190 record in kernelbase):

- ntdll `loader.c`: the run-0183 context moves to file scope, and `process_attach` does not pin a module when
  `lpReserved` is that context. `DllMain` still gets a non-NULL `lpReserved`, which is what Storm.dll checks. At the
  guest's end its imports unload with its own modules again, as in 04.12, and their `DllMain(DETACH)` runs.
- ntdll `heap.c`: `RtlCreateHeap`, where every `HeapCreate` ends, records the guest of the creating thread
  (`TEB.UserReserved`). A heap created while a guest EXE loads (`UserReserved[2]` is the load mark, as in the
  `DllMain` of its imports) is recorded as 1. `RtlDestroyHeap` removes the record. kernelbase reads and sets the record
  through `RtlQueryHeapInformation` and `RtlSetHeapInformation` with a class Windows does not have, `PW_HEAP_GUEST`.
  The process heap is never recorded.
- kernelbase `process.c`:
  - At the guest's `load_end`, the heaps recorded as 1 become that guest's (`PWGUEST heaps ... claimed=N made while
    it loaded`).
  - After its own modules are unloaded, `ps4_guest_release_heaps` logs `why=heaps_before`. It then takes each heap
    still recorded for the guest and looks for the heap handle in the writable sections of every loaded module
    except ntdll. A heap held by a module's global is kept and logged as `PWGUEST heap ... kept: held by <module>`;
    any other heap is destroyed. The total is logged as `PWGUEST heaps module=... destroyed= kept=`.
- `tools/check-guest-memory.py` reads both the old `made by` and the new `held by` lines.

What this does not cover:

- Blocks the guest left in heaps that it did not create stay: the process heap and the heap of `msvcrt.dll`, which
  DXVK and other MinGW-built modules use. Portal 2's 0.63 GB of Wine commits may be partly there. The next log
  separates it: `heaps_before` to `release_before` is what destroying the guest's own heaps gave back, and the
  `system_unloaded` lines show what the unpinned imports took with them.
- A system DLL that stays loaded and keeps a heap it made on a guest's thread anywhere but in a global loses that
  heap. Among Wine's DLLs, wined3d (a deferred context's upload heap), dbghelp (a pool) and webservices (a `WS_HEAP`)
  keep a heap in an allocated object. wined3d's belongs to the ended guest's device; the other two are objects a
  program creates.
- The threads that could not be signalled, and Zink's `queue_lock`, as in the run-0190 section.
- With the pin gone, a terminated guest's system modules run `DllMain(DETACH)` again, as they did up to 04.12
  (run-0185). Warcraft III (run-0183) still gets its non-NULL `lpReserved`; its start should be checked again.

Console test, after a build that contains this change:

1. Start Alan Wake on wined3d + OpenGL, let it draw, and close it from the overlay.
2. Start WFM.
3. Start Portal 2 and quit it from its menu.
4. Start WFM again.
5. Start Warcraft III, check that it reaches its menu, and quit.
6. Run `python3 -I tools/check-guest-memory.py <run log>`.

Expected:

- Both games: `system_unloaded` lines, `msvcr100.dll` among them for Alan Wake.
- `heaps destroyed N` with N above 0, or `kept` lines that name the holder.
- Portal 2 starts with the same heap count that Alan Wake started with.

## Large heap blocks in heaps the guest did not create (run-0212)

`reports/wine-hardware-w303/physical/20261117T190919Z/run-0212.log` (04.17, with the run-0203 change):
`tools/check-guest-memory.py` gives:

| | Alan Wake, terminated from the overlay | Portal 2, quit from its menu |
| --- | --- | --- |
| Lost until the next start (GB) | 0.69 (04.15: 0.81) | 0.15 (04.15: 0.75) |
| Flexible (GB) | 0.22 | 0.03 |
| Direct, Wine commits of 1 MiB or more (GB) | 0.32 | 0.05 |
| Direct, other (GB) | 0.15 | 0.07 |
| System modules unloaded | 13 of 48, `msvcr100.dll` among them | 2 of 46 |
| `PWGUEST heaps` | destroyed 1, kept 1 (`msacm32.dll`) | destroyed 1, kept 1 (`SHELL32.dll`) |

With the pin gone, a normal exit loses little. The overlay's terminate still keeps 0.32 GB of Wine commits and
0.22 GB of flexible memory. The heap the release destroyed gave nothing back: `wine_direct` and `flexible` are the
same at `heaps_before` and `release_before`. The C runtime's heap was already gone at that point:
`msvcr100.dll` unloads with the guest's own modules, before `heaps_before`, and its `DllMain(DETACH)` destroys its
heap. What is left is in heaps the guest did not create:

- The process heap: `HeapAlloc(GetProcessHeap())`, the malloc of `ucrtbase.dll` and of a statically linked C runtime.
- The heap of `msvcrt.dll`: the malloc of Wine's own DLLs (wined3d among them), of DXVK and of Mesa's WGL.

A terminated guest never frees its objects there, and these heaps stay for the life of the title.

Changes (`tools/build-guest-hw.py`):

- ntdll `heap.c`:
  - A heap block of `HEAP_MIN_LARGE_BLOCK_SIZE` or more (about 508 KB on i386, 1020 KB on x86_64) is a virtual
    allocation of its own.
  - Each one now ends in a tag past its `block_size`, so an in-place resize cannot reach it. The tag records the guest
    of the allocating thread (`TEB.UserReserved[0]`), the code that called `RtlAllocateHeap` or
    `RtlReAllocateHeap`, and the frame above it.
  - `RtlQueryHeapInformation` with a class Windows does not have, `PW_HEAP_LARGE`, lists a guest's tagged blocks. It
    also gives a heap's subheap commits and large blocks.
- kernelbase `process.c`:
  - At each guest's start, every heap of 1 MiB or more is logged (`PWGUEST heap_usage ... why=start`).
  - After the guest's own heaps are destroyed, `ps4_guest_release_large` logs every heap again (`why=release`, with
    the module that holds it). It then takes the guest's tagged blocks in each heap that stays.
  - A block whose allocating code is in no loaded module any more is freed. That code was the guest's own modules, or
    a system module that went with them.
  - Any other block is kept and counted by the module that called and the module above it
    (`PWGUEST heap_large ... kept bytes= ... from <module> via <module>`).
- `tools/check-guest-memory.py` prints the growth of each heap from the guest's start to its release
  (`heap growth`), and the large blocks freed and kept (`large blocks`).

What this does not cover:

- Blocks allocated through a C runtime that stays loaded, such as `msvcrt.dll` or `ucrtbase.dll`, are kept, even
  when the module above it is gone. This includes blocks the guest's own code allocated through `ucrtbase.dll`'s
  malloc. On i386 the frame above comes from the frame-pointer chain, which can be wrong in code built without frame
  pointers, so it names the block but does not decide its release. The next log shows how much these blocks are.
- Blocks under the large size: they grow a heap's subheaps (the flexible part), and nothing tags them.
  `heap growth` shows which heap they are in.
- A block the guest's code allocated and handed to a module that stays, which keeps it, is freed under that module.
  No case is known; the log names each freed amount (`freed_bytes`).
- GTA SA's "other" direct memory after a normal exit (run-0210, 04.16: 0.40 to 0.49 GB) is not from Wine's commits
  and is not changed here. It needs a run on 04.17 or later first.

Console test, after a build that contains this change:

1. Start Alan Wake on wined3d + OpenGL, let it draw, and close it from the overlay.
2. Start WFM.
3. Start Portal 2 and quit it from its menu.
4. Start WFM again.
5. Start Warcraft III, check that it reaches its menu, and quit.
6. Run `python3 -I tools/check-guest-memory.py <run log>`.

Expected:

- `heap growth` names the heap that kept Alan Wake's Wine commits and flexible memory.
- `large blocks` shows what was freed and, for what was kept, which modules allocated it.
- Nothing faults after a release (`PWFAULT`), and the next guest starts.

## The Vulkan device and Crema device a normal exit left (run-0215)

`reports/wine-hardware-w303/physical/20261117T194648Z/run-0215.log` (04.17): GTA San Andreas on wined3d's Vulkan
renderer, ended twice through its own exit (status 0). `tools/check-guest-memory.py` gives:

| | First run | Second run |
| --- | --- | --- |
| Lost until the next start (GB) | 0.63 | 0.45 |
| Direct, Wine commits of 1 MiB or more (GB) | 0.11 | 0.04 |
| Direct, other (GB) | 0.47 | 0.39 |
| Device memory freed at its end | 170 MB in 19 objects | 170 MB |

The game did not release its Direct3D device before it exited, so the release found its VkDevice with 19 device
memory objects. The release freed them, kept the device as it always did, and nothing changed up to the next start.
Two holders were left:

- **The kept VkDevice.** Some of its memory never goes through `vkAllocateMemory`, so win32u's record does not see
  it: what RADV allocates for itself (queue rings, scratch, shader arenas, the internal command buffers), and the
  buffers of the objects the program never destroyed (command, descriptor and query pools, the images of a
  swapchain). All of it stays until the device is destroyed.
- **The Crema device of its instance.** Crema creates a new device for each RADV winsys, which means one per
  instance, and its `ac_drm_device_deinitialize` did nothing: "the device lives for the whole process". A Crema
  device keeps up to 96 MB of freed buffers in quarantine against late GPU writes (`PS4_QUARANTINE_BYTES`), plus
  any buffer that is still allocated. Nothing gave these back once the instance was gone.

`guest-heap-large-run0212.patch` does not cover this: it acts only on Wine's own commits.

Changes:

- `tools/vk-h0/patch-crema-release.py` (new, run by `tools/vk-h0/build-mesa.sh` with `VARIANT=wine`):
  - `ac_drm_device_deinitialize` runs when a winsys ends, that is when its instance is destroyed, after all of
    its devices. No submission can come through that Crema device any more.
  - It waits up to 1.5 s for the last submission. Then it runs every deferred unmap and free, the quarantine
    included, and unmaps and frees every buffer still in the device's table.
  - The device structure, its fence page and its address windows stay, because W103's GPU time records keep the
    device pointer.
  - A device whose submissions have not finished keeps everything, as before. The line
    `radv/ps4: device ... ended: gave back N bytes` gives the bytes given back.
- `tools/build-win32u-ps4.py`:
  - Swapchains record their device, and instances record the guest that created them. The program's own
    `vkDestroySwapchainKHR` and `vkDestroyInstance` drop the records.
  - When a guest that ended by itself is released (`PW_GUEST_RELEASE_DEVICES`), its devices leave the records
    after their memory is freed.
  - Its swapchains stop being GPU layers (`ps5_vulkan_forget`) on the calling thread.
  - A helper thread then destroys those swapchains, waits for each device to be idle (`vkDeviceWaitIdle`) and
    destroys the device. Then it destroys each instance the guest created that has no device left, except Zink's
    shared one.
  - The caller waits at most 3 s. A queue left busy, or a lock left held, by one of the guest's threads that was
    terminated at its exit blocks only the helper. What the helper has not destroyed stays, out of the records, as
    a kept device did before this change.
  - Logged lines: `PWVK guest_teardown owner=... swapchains= devices= instances= ms=` from the helper, and the free
    memory after it (`PWVK guest_memory ... why=teardown_after`). If the helper is still running at 3 s:
    `PWVK guest_teardown ... still running after N ms`.
- `tools/build-guest-hw.py`: kernelbase passes `PW_GUEST_RELEASE_DEVICES` unless the guest was terminated (the
  overlay's close, a crash; W209).
- `tools/check-guest-memory.py`: `teardown: swapchains, devices, instances, Crema gave back, gave back direct`.

What stays as it was:

- A terminated guest, such as one closed from the overlay, still only has its device memory freed. Its threads were
  stopped wherever they were, and a queue wait or a device lock could block. Alan Wake's terminated runs are
  unchanged by this.
- Zink's device and instance, which every OpenGL guest shares.
- The address windows of an ended Crema device (virtual address space, not memory).

Risks:

- The helper runs without a TEB. It calls only Vulkan entry points, win32u's object removal and `fprintf`. The
  window part (`ps5_vulkan_forget`) runs on the caller's thread before it.
- A guest thread that was terminated inside RADV can leave a lock held. Then the helper blocks there for good, and
  it holds no lock of its own. Only that device and its instance stay, as before.
- A program that keeps using a device after its own exit does not exist in this model: its code is unloaded first.

The safest subset is the Crema change alone (`patch-crema-release.py` and its line in `build-mesa.sh`). It frees
buffers only after the GPU has finished everything that device submitted. It helps every program that destroys its
own instance, but not GTA SA, which keeps its device and instance.

Console test, after a build that contains this change and `guest-heap-large-run0212.patch`:

1. Start GTA San Andreas, load a game, and quit through its menu.
2. Start GTA San Andreas again, load a game, and quit through its menu.
3. Start vkcube and close it; start Portal 2 and quit through its menu.
4. Start Alan Wake on wined3d + OpenGL, let it draw, and close it from the overlay.
5. Start WFM, and check that the desktop and the taskbar still respond.
6. Run `python3 -I tools/check-guest-memory.py <run log>`.

Expected:

- After each GTA SA run: `teardown: swapchains 1+, devices 1, instances 1+`, a `radv/ps4: device ... ended` line,
  and the "other" direct loss well under 0.39 GB.
- No `still running` line, and no GPU fault or `PWFAULT` after a teardown.
- Alan Wake, terminated: no teardown line; its figures as in run-0212.

## Every later start died in vkCreateDevice (run-0219)

`reports/wine-hardware-w303/physical/20261117T220342Z/run-0219.log` (04.19, with the run-0215 change): GTA San
Andreas ended through its own exit (status 0). The teardown destroyed 1 swapchain, 1 device and 2 instances in 10 ms,
and gave back 155 MB of direct memory after the release's 130 MB. Its next two starts died before their first frame:
`vkCreateDevice Exception 0xc0000005 in Unix call`, exit status 3.

The cause is the instances. GTA San Andreas's real device is DXVK's: `PWOVERLAY render ... choice=dxvk-vulkan`, and
the first start loads `openvr_api_dxvk.dll` and `wineopenxr.dll` just before it. The earlier run-0215 section calls
it wined3d's renderer; only the hidden-window devices before it are wined3d's.

- DXVK 2.7.1's `d3d9.dll` keeps one `DxvkInstance` for the whole process: `Singleton<DxvkInstance> g_dxvkInstance`
  in `src/d3d9/d3d9_interface.cpp`. The last Direct3D 9 object releases it, and the game never released its object.
- The 32-bit world keeps the system DLLs a guest loaded: `PWGUEST system_modules module=00400000 loaded=46
  unloaded=1`. `d3d9.dll` stayed loaded with its singleton, its `VkInstance` and its `VkPhysicalDevice`.
- The next start took that instance again. Its DXVK did not load `openvr_api_dxvk.dll` again, because the VR
  probing also runs only once per process. `vkCreateDevice` on its physical device read the win32u objects the
  teardown had freed.

Before run-0215 the leaked instance was still alive, so the next start worked on it. The device is not affected the
same way: DXVK makes a new `VkDevice` for each Direct3D 9 device.

Changes, against 04.19 (`guest-vk-teardown-instances-run0219.patch`):

- `tools/build-win32u-ps4.py`: the teardown destroys the guest's swapchains and devices, as before, but no
  instance. The instance records (`pw_vk_instances`, with the owner and the list kept by `vkCreateInstance` and
  `vkDestroyInstance`) are gone. The line is now `PWVK guest_teardown owner=... swapchains= devices= ms=`.
- `tools/vk-h0/patch-crema-release.py`, as the instance stays:
  - A Crema device counts RADV's contexts, one per queue (`ac_drm_cs_ctx_create2`, `ac_drm_cs_ctx_free`).
  - When the last one goes, nothing can submit through that device, so no late write through a stale descriptor
    is possible. The quarantine goes: every freed buffer whose submissions have finished is given back. While the
    device has no queue, each later free runs as soon as its submissions have finished, with no quarantine. That
    takes in the buffers `vkDestroyDevice` frees after its queues.
  - Line: `radv/ps4: device ... has no queues: gave back N bytes; M bytes in buffers now`. A new queue on the same
    device (the same instance's next `VkDevice`) brings the quarantine back.
  - The end of a device (`ac_drm_device_deinitialize`, when a program destroys its instance) still runs the
    deferred operations. It no longer frees the buffers left in its table. They are a program's leaked objects, and
    their GPU mappings would have to be taken down first, as Crema's own unmap does. Its line is
    `radv/ps4: device ... ended: gave back N bytes; M bytes in K buffers its users left are kept, J operations still
    wait`.
- `tools/build-guest-hw.py`: its comment only.
- `tools/check-guest-memory.py`:
  - The teardown line can have no instances.
  - Crema's "has no queues" lines count as "Crema gave back".
  - A Crema line counts only for the last released run until the next start. Before, run-0219's first run was
    also given the second run's probe devices: 246 MB instead of 51 MB.

What stays:

- The instance and its Crema device, with the buffers the program's leaked objects hold. For GTA San Andreas these
  were 9 MB in 160 buffers in run-0219. A later start reuses them through DXVK's instance.
- A program whose instance nothing reuses keeps it until the console's process ends, as before run-0215.

Risks:

- Destroying the device stays. A module that stays loaded could also keep a `VkDevice` and use it at the next
  start. DXVK 2.7.1's process-wide objects are its instance, its adapters and its VR probing. wined3d's devices
  belong to a Direct3D object. MangoHud's layer keeps its record of the destroyed device, and nothing calls through
  that record again.
- A queue count of 0 also happens briefly while RADV checks whether a queue priority is allowed. It only gives
  back buffers the GPU has finished with.

Console test (needs the user's approval), after a build with this change:

1. Start GTA San Andreas, load a game, and quit through its menu. Do this three times.
2. Start vkcube and close it; start Portal 2 and quit through its menu.
3. Start Alan Wake on wined3d + OpenGL and close it from the overlay.
4. Start WFM, and check that the desktop and the taskbar still respond.
5. Run `python3 -I tools/check-guest-memory.py <run log>`.

Expected:

- Every GTA San Andreas start reaches its menu. No `vkCreateDevice Exception`.
- After each run: `teardown: swapchains 1, devices 1, Crema gave back ...`, with no instances, and "gave back
  direct" near run-0219's 155 MB.
- No `still running`, no GPU fault and no `PWFAULT`.
- Alan Wake, terminated: no teardown line.

## Terminated guests: a guest with no DLLs of its own, and wined3d's blocks (04.27 runs)

`tools/check-guest-memory.py` on `reports/wine-hardware-w303/physical/20261119T111322Z/` (04.27):

| Run | Program, end | Lost | Notes |
| --- | --- | --- | --- |
| run-0244 #2 | Alan Wake, terminated | 0.78 GB | process heap +409 MB; 114 MB of large blocks kept "from ucrtbase via wined3d" |
| run-0244 #3 | Portal 2, terminated | 0.33 GB | no large block kept |
| run-0246 #1 | Doom 3, terminated | 0.44 GB | heaps 2 -> 4; no heap or large-block line at all |

Doom 3 has no DLLs of its own: `PWGUEST own_modules ... count=0 ... terminated=1`. `ps4_guest_unload_own` returned at
once when that count was 0, so the guest's heaps (`ps4_guest_release_heaps`) and its large blocks
(`ps4_guest_release_large`) were never released. The next start still listed Doom 3's heap: `heap_usage ... heap=09040000
holder=- committed=78839808`. Every guest without DLLs of its own (wfm, notepad, Doom 3) skipped that step.

In Alan Wake, the large blocks whose allocating code was gone were freed (7 MB). The 114 MB that wined3d.dll had
allocated through ucrtbase were kept, because wined3d stays loaded in the 32-bit world.

Changes (`tools/build-guest-hw.py`, kernelbase):

- `ps4_guest_unload_own`: with no own module, it goes on to the memory the guest's code reserved and to its heaps and
  large blocks, as after its own modules have been unloaded. Leftovers (the unload at a later launch) still skip
  the heaps, as before.
- `ps4_guest_release_large`: for a terminated guest (overlay close or crash), a large block whose allocating module,
  or the frame above it, is `wined3d.dll` is freed too.
  - wined3d's process-wide state holds small entries only: the window-procedure and swapchain-state tables and the
    budget notifications. Its large blocks belong to the objects a program made: resource copies in system memory,
    the command-stream queues.
  - A terminated guest never releases those objects, and its windows, through which wined3d would reach its device,
    were destroyed before.
  - DXVK is not included: its `d3d9.dll` keeps one instance for the whole process (run-0219).
  - A guest that exits by itself keeps today's rule.
  - New line, part of the `freed_bytes` of the `heap_large ... heap=` lines: `PWGUEST heap_large module=... objects
    freed_bytes=N blocks=M: the terminated guest's, made through wined3d.dll`.

Not changed, still open:

- The process heap's own growth (+409 MB for Alan Wake): small blocks carry no owner tag, and the process heap is
  shared with every other guest of the world.
- The flexible memory (0.17-0.23 GB) and the other direct memory (0.12-0.19 GB) of a terminated guest.

Expected: Doom 3, terminated, gives back its own heap (79 MB in run-0246) and its large blocks; Alan Wake, terminated,
about 114 MB more. Portal 2 does not change.

Verification: compile-only. kernelbase's `process.c` for i386 and x86_64, with the same warnings as without the change.
Not built or run on the console.

Console test (needs the user's approval), after a build with this change:

1. Start Doom 3, then close it from the overlay.
2. Start Alan Wake (wined3d + OpenGL), then close it from the overlay.
3. Start Portal 2, then quit through its menu; start it again and close it from the overlay.
4. Start WFM and Notepad, close them, and check that the desktop and the taskbar still respond.
5. Run `python3 -I tools/check-guest-memory.py <run log>`.

Expected:

- Doom 3: `PWGUEST heaps module=00400000 destroyed=...` and `heap_large ... heap=` lines, and "heaps" back to its
  start count.
- Alan Wake: the `objects freed_bytes=` line near 114 MB, and no `kept ... via L"wined3d.dll"` line.
- No PWFAULT after a release, and the next game starts and renders.

## Small blocks of the process heap, and large blocks of no guest (04.29 runs)

`tools/check-guest-memory.py` on `reports/wine-hardware-w303/physical/20261119T144942Z/` (04.29, with the change
above):

| Run | Program, end | Lost | Process heap at the release |
| --- | --- | --- | --- |
| run-0252 #1 | Alan Wake, terminated | 0.65 GB | 199 MB of subheaps, 204 MB of large blocks (146), 68 of them the guest's |
| run-0253 #1 | Alan Wake, terminated | 0.64 GB | 194 MB of subheaps, 220 MB of large blocks (146), 69 of them the guest's |
| run-0253 #2 | Alan Wake, terminated | 0.42 GB | 364 MB of subheaps (+170 MB), 307 MB of large blocks (239, +157), 69 the guest's |

The change above worked: 123 MB of large blocks were freed each time, 116 MB of them made through wined3d.dll. What
stays is in the process heap:

- Its subheaps grow by 170-200 MB per start and the next start does not reuse them: small blocks, below the large-block
  size, still in use. A small block carries no owner, so nothing could be freed.
- 88 large blocks of about 83 MB per start are not tagged with the guest: a thread that is no guest's made them.
- msacm32.dll's heap, kept because msacm32 holds it, is below 1 MiB.

Changes (`tools/build-guest-hw.py`):

- ntdll, i386: a small block that a guest's thread allocates in the process heap carries its allocation site in the
  heap's user-value slot (`HEAP_ADD_USER_INFO`, as `RtlSetUserValueHeap` uses it): the guest, the code that called
  `RtlAllocateHeap` or `RtlReAllocateHeap`, and the frame above it. A site counts its live blocks and bytes. A resized
  block keeps its site, in place or moved, whoever resizes it. These blocks do not go through the LFH, so all of them
  are reached under the heap lock. `C:\orbis\nosmalltags.txt` turns this off without a rebuild.
- kernelbase, after a guest's large blocks: its sites are listed (`PW_HEAP_SITES`), and the blocks of the chosen sites
  are freed in one pass over the process heap under its lock (`PW_HEAP_SITES_FREE`). Then all its sites end. The rules
  are those of the large blocks: the allocating code is gone, or, for a terminated guest, the site is in wined3d.dll.
- "Code gone" now also covers a block that a C runtime (ucrtbase, msvcr*, kernelbase, kernel32) allocated for code that
  is gone: the frame above it is in no loaded module. This holds for large blocks too.
- The large blocks of no guest's thread record the frame above too. After each release they are listed, the ones whose
  code is gone are freed, and the rest are logged by module.
- New lines: `PWGUEST heap_small module=... sites=N blocks=N bytes=N listed=N missed=N freed=N freed_bytes=N`, then up
  to eight `... kept bytes=N blocks=N from <module> via <module>` lines by size, and `... objects bytes=N ...` for the
  wined3d share; `PWGUEST heap_unowned module=... blocks=N bytes=N listed=N freed=N freed_bytes=N` and its `kept`
  lines. `check-guest-memory.py` shows them as "small blocks" and "unowned large".

Costs and limits:

- Each tagged block is 8 bytes larger, and a guest's small allocations in the process heap take the heap lock instead
  of the LFH. Each new site takes the stack walk that large blocks already take.
- x86_64 is unchanged: its stack walk unwinds through tables, which is too slow for every allocation.
- Blocks a thread of no guest allocates (winmm's timer thread, the loader thread while a guest's EXE loads) are not
  tagged.
- A shared module that keeps a block the gone code made would be left with a freed block. The large blocks already
  have this risk.
- A guest thread killed while it holds the site table's spin lock would block later site inserts. The window is a few
  instructions, and the heap's own lock has the same exposure.

Verification: compile-only for the console; ntdll's `heap.c` and kernelbase's `process.c` build for i386 and x86_64
with the same warnings as without the change. On the host, a private copy of the host Wine build had its ntdll relinked
with the generated `heap.c` (both arches): `wineboot -i` worked, and an i386 test program passed. That program set
`TEB.UserReserved[0]` as a guest's threads have it, and covered allocations, resizes (in place, moved, by a thread of no
guest, small to large) and frees. The site counts matched the live blocks exactly (1500 blocks, 3130254 bytes). Freeing
the sites freed exactly those, `HeapValidate` passed before and after, and the untagged blocks kept their contents. A
4-thread stress run of 100,000 operations per thread, with a thread of no guest beside them, also matched (1241 blocks).
A tagged allocation and free cost about 3 times an untagged one on the host (0.16 s against 0.05 s per million).
kernelbase's release code was not run on the host.

Expected on the console: for a terminated Alan Wake, the `heap_small` line shows most of the 170-200 MB, and the
`kept` lines name what stays (wined3d's share is freed). The process heap's growth in "heap growth" goes down by the
freed amount. `heap_unowned` names the 83 MB of large blocks of no guest.

Console test (needs the user's approval), after a build with this change:

1. Start Alan Wake (wined3d + OpenGL), play briefly, and close it from the overlay. Do this twice.
2. Start Portal 2, quit through its menu, start it again, and close it from the overlay.
3. Start Doom 3 and close it from the overlay.
4. Start WFM and Notepad, close them, and check that the desktop and the taskbar respond.
5. Run `python3 -I tools/check-guest-memory.py <run log>`.

Expected: lower loss per Alan Wake start than 0.42-0.65 GB, no PWFAULT after a release, the next game starts and
renders, and no slower frame times than 04.29 in Alan Wake.

## Small blocks the C runtime made through more of itself (04.30 runs)

`tools/check-guest-memory.py` on `reports/wine-hardware-w303/physical/20261119T173323Z/` (04.30, with the change
above):

| Run | Program, end | Lost | Small blocks of the guest | Freed | Largest kept |
| --- | --- | --- | --- | --- | --- |
| run-0261 #1 | Alan Wake, terminated | 0.58 GB | 206 MB | 127 MB | 74 MB "ucrtbase.dll via ucrtbase.dll" |
| run-0261 #2 | Alan Wake, terminated | 0.21 GB | 186 MB | 124 MB | 59 MB "ucrtbase.dll via ucrtbase.dll" |
| run-0258 #1 | PES 2013, crash (c0000005) | 0.49 GB | none tagged | - | - |
| run-0258 #2 | PES 2013, terminated | 0.36 GB | none tagged | - | - |

The loss per Alan Wake start went from 0.78 GB (04.27) and 0.64/0.42 GB (04.29) to 0.58/0.21 GB. The first start's
flexible memory (0.22 GB) and most of its "other" direct memory (0.18 GB) do not come back on the second start (0.00
and 0.05 GB), so they are taken once. msacm32.dll's heap is msacm32's own: it is made on the first guest that loads
msacm32 and kept while msacm32 stays loaded; the second start keeps none. The 1-4 MB of large blocks kept as
"ucrtbase.dll via ucrtbase.dll" do not grow from one start to the next.

What stays per start is mostly the small blocks kept as "ucrtbase.dll via ucrtbase.dll". The C runtime made them
through more of itself: `_aligned_malloc` calls `_aligned_offset_malloc`, which calls `malloc`, and `_strdup` and
`realloc` call `malloc` too. The frame above the caller is then the C runtime again, so neither "code gone" nor the
wined3d rule saw the code that asked for the block.

Change (`tools/build-guest-hw.py`):

- ntdll, i386: a small-block site also records the three frames above the frame it already had. Wine builds its i386
  PE modules with frame pointers, so the frames inside the C runtime are exact.
- kernelbase: when the caller is a C runtime and the frame above is one too, the frame that counts is the first of the
  three above that is not a C runtime's. "Code gone", the wined3d rule and the `kept` lines use it, so what stays is
  named by the module that asked.
- Large blocks are unchanged.

Verification: compile-only for the console; ntdll's `heap.c` and kernelbase's `process.c` build for i386 and x86_64
with the same warnings as without the change. On the host, ntdll was relinked with the generated `heap.c` in a private
copy of the host Wine build, and the i386 heap test passed again (site counts, freeing, `HeapValidate`, 4-thread
stress). A new part of it allocates through ucrtbase's `_aligned_malloc`, `realloc(NULL)`, `malloc`, `calloc` and
`_strdup`, and applies kernelbase's rule to the listed sites: all 100 blocks reached the test program's frame. The host
ucrtbase needed the third frame for `_aligned_malloc` (`malloc`, `_aligned_offset_malloc`, `_aligned_malloc`).
kernelbase's release code was not run on the host.

Not changed: PES 2013 had no tagged small block, yet its process heap grew by 55 MB per start (committed 59 MB, then
114 MB). Those blocks come from threads that are no guest's, or from allocations that are not tagged, and need another
look.

Console test (needs the user's approval), after a build with this change:

1. Start Alan Wake (wined3d + OpenGL), play briefly, and close it from the overlay. Do this twice.
2. Start PES 2013 and close it from the overlay.
3. Start Portal 2, quit through its menu, and start it again.
4. Start WFM and Notepad, close them, and check that the desktop and the taskbar respond.
5. Run `python3 -I tools/check-guest-memory.py <run log>`.

Expected: the "ucrtbase.dll via ucrtbase.dll" `kept` lines are gone or small. Their blocks are freed (wined3d's, or of
gone code), or kept under the module that asked, for example libgallium_wgl.dll. The second Alan Wake start loses less
than 0.21 GB. No PWFAULT after a release, the next game starts and renders, and frame times are no worse than in 04.30.

## Related: a failed guest load kept its base taken

`reports/pop-phase-b/physical/20261113T192438Z/run-0121.log`: PES 2014's `settings.exe`, an IL-only .NET EXE,
loaded at 0x400000 and failed with `mscoree.dll not found` (c0000135). Its next start then logged
`image_not_at_base preferred=0x400000 size=0x156000 status=0xc0000018 occupied=0x400000+0x156000`, which is its own
image. When Wine's `build_module` cannot resolve imports, it takes the module off the loader's lists but sets
`*module` to NULL, so `load_native_dll` does not unmap the view. A failed process normally ends, so upstream leaves
the view. A guest EXE inside explorer's process kept its fixed base taken until OrbisDesk ended. The ntdll revision
in `tools/build-guest-hw.py` now unmaps the view of a guest EXE whose imports fail and logs
`PWGUEST load_failed unmap`. The modref stays allocated, as upstream leaves it.

The other reported case, `vampire.exe` in `run-0164.log` (lines 503-505), is not a leak. `PATCH 1.2.exe` was still
running at 0x400000 (`live=1`; its `exits status 1607` comes at line 531), and the existing `base_taken` relaunch
handled it. `leftovers=1` in `PWGUEST own_modules` is the flag of the sweep before every start, not a count.

## Verification and what remains

- Compile-only checks in an isolated root: win32u `vulkan.c` with every revision applied, built with the Orbis recipe,
  gives the same three warnings as the committed generator, and both call tables are global symbols. The guests'
  `kernelbase/process.c` and `ntdll/loader.c` build for x86_64 and i386 with the same warnings as before.
- run-0178 change, also compile-only: the Mesa patch applies to a copy of the WGL frontend twice (the second run
  changes nothing). `stw_context.c` and `stw_device.c` build with the recipe's i386 and x86_64 commands with no
  warnings, and export `pw_wgl_release_screen`. The kernelbase and win32u units give the same warnings as before
  this change.
- run-0185 probe, also compile-only, built from the generators it was written for: win32u `vulkan.c` gives the same
  warnings as before it, and leaves `pw_vm_direct_bytes`, `pw_wine_memory_info` and `sceKernelGetDirectMemorySize`
  to the final link. `pw_vm_direct_bytes` was compiled on its own with the console flags, not as part of the whole
  `virtual.c`. The kernelbase unit gives the same warnings as before it, for x86_64 and i386.
- run-0190 change, also compile-only, against the generators of 04.13 plus that build's own fixes: win32u `vulkan.c`
  gives the same warnings as before it. The kernelbase `process.c` and `memory.c` units, for x86_64 and i386, give
  the same warnings as before it. The checker reads run-0190 as before, with the heap counts taken within the world.
- run-0203 change, also compile-only, against the generator of 04.15: the ntdll `loader.c` and `heap.c` units and
  the kernelbase `process.c` and `memory.c` units, for x86_64 and i386, give the same warnings as before it (none for
  ntdll). The checker reads run-0203 as before.
- run-0212 change, also compile-only, against the generator of 04.17: the ntdll `heap.c` and `loader.c` units and
  the kernelbase `process.c` and `memory.c` units, for x86_64 and i386, give the same warnings as before it. The
  checker prints run-0212 as before, and reads the new lines from a log with them added by hand.
- run-0215 change, also compile-only, against the generators of 04.18 with the run-0212 change: win32u's `vulkan.c`
  and the kernelbase `process.c` unit (x86_64 and i386) give the same warnings as before it, and Crema's
  `ac_ps4_drm.c` with `patch-crema-release.py` (idempotent) the same warning as without it. The checker prints
  run-0212, run-0213 and run-0215 as before, and reads the new lines from a log with them added by hand.
- run-0219 change, also compile-only, against the generators of 04.19: win32u's `vulkan.c` gives the same warnings
  as before it, and Crema's `ac_ps4_drm.c` with the new `patch-crema-release.py` (idempotent) the same warning as
  without it. The checker prints run-0212 and run-0215 as before, and run-0219 with 51 MB from Crema for its first
  run instead of 246 MB. It reads the new lines from a log with them added by hand.
- No package was built, and nothing was run on the emulator or the console.
- Console test, after a build that contains this change: start the same DXVK game, let it draw, close it from the
  overlay, and repeat three times. Then run `python3 -I tools/check-guest-memory.py <run log> --max-loss-gb 0.25`
  and look for the `PWGUEST vulkan` lines.
