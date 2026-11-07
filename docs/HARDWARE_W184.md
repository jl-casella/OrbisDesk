<a id="w184-memoria-para-vistas-grandes-y-perfil-de-pale-moon-fase-9-salida-de-invitados-sin-atexit-ajenos-fase-7"></a>


# W184: memory for large views and profile of Pale Moon (phase 9), departure of guests without other atexes (phase 7)

[English](HARDWARE_W184.md) | [Español](HARDWARE_W184-es.md)

APP_VER 02.83. Base W183. The result of W183 is in `docs/HARDWARE_W183.md`.

<a id="vistas-grandes-comprometidas-desde-el-principio"></a>


## Large views engaged from the beginning

`tools/build-audio-ps4.py`, `virtual.c`, `map_view`, in Orbis only:
- **Before:** in W183, Pale Moon (running alone) asked 8 MiB of read/write (`size 0x810000, unix_prot 0x3`). The console rejected the `mmap` anonymous with `EINVAL`, and xul read `NULL+0x80`.
- **Now:** a new view of 1 MiB or more that is born compromised is first reserved in the kernel (W182). When the alignment left-over is cut, it receives direct memory in zero, as large commitments (W175/W176). It is released with the view (`unmap_area`).
- **If you fail:** if the direct memory fails, the change of protection compromises flexible memory over the reservation. If that also fails, the reservation returns `STATUS_NO_MEMORY` with `PWVM view … got no memory`, instead of a memory-free address.
- Only changes the path of the views without direction limits (64 bit programs); The 32 bit ones are still by `map_free_area`.

<a id="pale-moon-preferencias-y-d3d11-fase-9-sesión-del-navegador"></a>


## Pale Moon: preferences and D3D11 (phase 9, browser session)

<a id="qué-pasó-en-w183"></a>


### What happened in W183

Report: `reports/wine-hardware-w183/physical/20261103T232154Z/`. The relaunch works: run- 0004 and run- 0006 rewind, and run- 0005 and run- 0007 run `palemoon.exe` as a title. Pale Moon falls to 13 s more or less and the app returns to the desktop.

- **run- 0005 (first profile start):**
  - The main thread loads `opengl32`, the `dxgi` building of Wine and then the `d3d11.dll` of DXVK (W124).
  - DXVK tell `D3D11InternalCreateDevice: Adapter is not a DXVK adapter` and create your own device Vulkan. Then it gives `DxvkMemoryAllocator: Memory allocation failed` (4096 bytes, memory types 0,2,3,5, piles of 1024 and 2048 MiB almost empty).
  - Access failure in `7F8941618`: `d3d11.dll` (DXVK), displacement `0xe1618`.
  - Then there is a breakpoint in `7FA464E69`: `xul.dll` of Pale Moon, displacement `0x734e69` (Mozilla's abort). It ends with `0x80000003`.
- **run- 0007 (second start):**
  - Pale Moon delete `d3d11layers.guard` from the profile. It is your guard against D3D11 failures, which was left from the previous failure, so this time you don't use D3D11.
  - Then, `map_view anon mmap error Invalid argument, size 0x810000, unix_prot 0x3`: a reservation of 8 MB reading and writing that the console rejected.
  - `xul.dll` read the address `0x80` in `7F9FD958E` (`xul.dll`, displacement `0x2a958e` and ends with `0xc0000005`.
  - It's a memory problem other than that of D3D11. It belongs to the work of the main session in `virtual.c` (the reserve of 1 GB of W180 was without permits; This is 8 MB with reading and writing).

**Why Pale Moon created a device D3D11.** The `user.js` of W177 - W183 asked `layers.acceleration.disabled`. Pale Moon 35 (UXP) has no such preference. Yours is `layers.acceleration.enabled` (the names are in `xul.dll`). There is no `layers.prefer-d3d9`. Pale Moon ignored both and left the composition for GPU on.

<a id="cambio"></a>


### Change

|File|What are you doing?|
|---|---|
| `fixtures/browser/palemoon-user.js` |`layers.acceleration.enabled=false` instead of `layers.acceleration.disabled`. Take out `layers.prefer-d3d9`. Add `webgl.disable-angle=true` (ANGLE also uses D3D11). They follow `gfx.direct2d.disabled`, `webgl.disabled` and `media.hardware-video-decoding.enabled=false`. All these preferences are in `xul.dll`.|
|`tools/build-wine-hardware.py` (`user.reg`, pending the OK of the main session)|`[Software\Wine\AppDefaults\palemoon.exe\DllOverrides]` `"d3d11"=""` and `"d3d10core"=""`: if any Pale Moon still requests D3D11, the load fails clean and does not reach DXVK. `dxgi` remains the building (Pale Moon uses it to read the adapter). `d3d9` does not touch: `xul.dll` it matters in a static way.|

The `user.js` is from the build, so the rise replaces it. What Pale Moon wrote in the profile (`prefs.js`, guards) remains.

<a id="para-después-vulkan-en-un-título-de-64-bits-relanzado"></a>


### For later: Vulkan in a 64 bit retracted title

In run- 0005, DXVK could not reserve 4 KB of memory Vulkan in a process of 64 bits. The 32 bit relegated programs do use DXVK and wined3d over Vulkan. It was not investigated in W184. It is recorded for when Pale Moon (or a game of 64 bits) use D3D11 in your own process.

<a id="construcción-orden"></a>


### Construction (order)

1. `python3 tools/build-wine-hardware.py` (copy the new `user.js` and, with the OK, write the block `DllOverrides`)
2. `python3 -I tools/check-web-closure.py build/wine-hardware-w184/runtime`

<a id="prueba-física"></a>


### Physical test

1. **Open Pale Moon:**
   - The log does not have to appear `d3d11.dll` loaded by Pale Moon or any line of DXVK (`info:  DXVK: v2.7.1`.
   - The local page is expected with `es5-ok`, `es2020-ok` and `canvas-ok`.
2. **If you return `map_view anon mmap error Invalid argument`** (as in run- 0007), the failure is of memory and not of graphics: it is left for the arrangement of `virtual.c`.
3. **Close Pale Moon:** you have to return the desk.

<a id="no-verificado"></a>


### Not verified

- Nothing was tested on the console.
- It is not confirmed that, with the composition by GPU off, Pale Moon 35 does not create a device D3D11 for anything else (reading the adapter, image decoding). That's what the `DllOverrides` is for.

<a id="cierre-de-winecfg-desde-control-panel-fase-7-sesión-de-accesos-directos"></a>


## Winecfg closure from Control Panel (phase 7, direct access session)

<a id="qué-pasó-en-w183-1"></a>


### What happened in W183

In `run-0001.log` (`reports/wine-hardware-w183/physical/20261103T232154Z`; equal to `run-0002` and `run-0003`):

1. winecfg (guest `0x100780000`, thread `0040`) ends with `ExitProcess` and is downloaded.
2. rundll32 (another guest, thread `003c`, the one that runs `winecfg.cpl`) download `winecfg.cpl` and call `exit()` at the end of its `main`.
3. Fault in `0x100782560`, inside the winecfg already downloaded. The title ends with `0xc0000005`.

<a id="la-causa"></a>


### The cause

- `0x100782560` is `winecfg.exe+0x2560`: `do_global_dtors`, from the start of the CRT of mingw.
- When you start, winecfg records it with `_crt_atexit` in ucrtbase, and ucrtbase saves a **single atexus table for the whole process** (`MSVCRT_atexit_table`, `dlls/msvcrt/exit.c`).
- winecfg comes out with `ExitProcess`, not to go through that table, as in Windows. The entry remains, pointing to an image that is then downloaded.
- When rundll32 ends, its `exit()` runs through the whole process table, including winecfg input, and jumps into released memory.
- It's the same type of error as the W114 exception filter: something from the process that keeps an address from a guest that is no longer there.

In addition, in `ps4_guest_launch` the guest's new thread is created from the thread that calls `CreateProcess`. If that thread is from another guest (rundll32), `CreateThread` the new thread is placed in the new thread by the guest from the one who creates it and adds it to **its** list of threads. So in W179 the output of rundll32 finished the winecfg thread.

<a id="cambio-1"></a>


### Change

In `tools/build-guest-hw.py` (it applies `guest-exit-w184.patch.py`):

- **ucrtbase (`exit.c`):** each guest has its own atexus table, stored in its `struct ps4_guest`, right after the first field.
  - `atexit`, `_onexit` and `_crt_atexit`, called from a guest's thread, record on that guest's table. `exit()` from a guest only travel his board.
  - Outside the guests (explorer) everything remains the same, with the process table.
  - A guest who comes out with `ExitProcess` leaves his tickets unrun, as in Windows, and there is no table left that any other program will go through.
- **kernelbase (`ps4_guest_launch`):** while creating the new guest's thread, the calling thread is no longer marked with its guest. The new thread is just from the new guest.
- Separate compiler (copy of the building with output on the scratchpad): 23 reviews; They link ntdll, ucrtbase and kernelbase. The two warnings that come out are from previous code (W060 and W105).

<a id="prueba"></a>


### Test

1. Control panel → Configuration of Wine → OK. Repeat with Cancel.
2. Repeat from Start → Run `winecfg`, which does not pass by rundl32.
3. In both cases, the desk is still on. In the log, after `PS4 guest module … exits`, rundll32 comes out without `page fault`.

<a id="prueba-física-1"></a>


## Physical test

Report: `reports/wine-hardware-w184/physical/20261103T234342Z/`. User response: "Pale Moon go."

- **Pale Moon** opens as its own title (although it does not sail: when writing `google.com` or look at DuckDuckGo and pressing Enter is nothing, without error page or disconnection notice; see W185) (`run-0002`: `pe_machine … palemoon.exe`), without `anon mmap error`, `PWVM view … got no memory`, `c0000005` No breakpoint. The phase 9 gets to a modern browser running on the console.
- **winecfg:** Apply complete all steps, `step=refresh` included (188 ms, twice in `run-0001`, and the app follows.
- `user.reg` of the console has `AppDefaults\palemoon.exe` with `OrbisRunsAlone="Y"` and `DllOverrides` (`d3d10core`, `d3d11`).
