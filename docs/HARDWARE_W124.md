<a id="w124-direct3d-811-con-dxvk-fase-4-del-plan-pe32"></a>


# W124: Direct3D 8 - 11 with DXVK (plan phase 4 PE32)

[English](HARDWARE_W124.md) | [Español](HARDWARE_W124-es.md)

APP_VER 02.23. Base W123 (phase 3 accepted: audio Windows in 32 and 64 (g) The Commission shall take the necessary measures to ensure that the measures are implemented.

<a id="elección"></a>


## Election

- The GPU exposes **Vulkan 1.3** (`PWVK GPU: AMD Liverpool (PS4) (RADV BONAIRE), API 1.3.335`) and the extensions that DXVK 2 .x takes advantage of: robusts2, descriptor_buffer, graphics_pipeline_library, extended_dynamic_state 1/2/3, maintenance5/6, transform_feedback and map_memory_placed. They were taken from the log of W117.
- **DXVK 2.7.1** (`https://github.com/doitsujin/dxvk` zlib license), the official release mingw unchanged, set by SHA- 256 `d85ce7c79f57ecd765aaa1b9e7007cb875e6fde9f6d331df799bce73d513ce87`.
  - It's the last of the line 2. The 3 .x uses a new shaker compiler that, according to its version notes, compiles more in the CPU, and the Jaguar of the PS4 is the most limited resource.
  - prospero-win use 2.6.2, from the same line.

<a id="cambios"></a>


## Changes

- `tools/stage-dxvk.py`: verify the file and extract `out/dxvk/{x64,x32}` with your manifest.
- `tools/build-wine-hardware.py`:
  - d3d8, d3d9, d3d10core and d3d11 of DXVK go to `system32` (x64) and `syswow64` (x32).
  - Overrides `native,builtin` in `user.reg`.
  - `vulkan-1` passes from `native` to `native,builtin`: the 32 bit programs have no vulkan- 1 native (the one of syswow64 is the building of Wine) and `native` would only reject it. The 64 bits are still with the Khronos loader.
  - **No** is installed `dxgi.dll` of DXVK: the building of Wine It is still the one that uses the Khronos loader and MangoHud (W087). D3D10/11 need the dxgi of DXVK per program; that's left for phase 7 (winecfg).
- Fixture `fixtures/win32/d3d9test.c`, in `C:\orbis\d3d9test64.exe` and `d3d9test32.exe`:
  - window, Direct3D9 HAL and ~ 5 s of frames (clear of changing color plus a triangle);
  - result in `C:\orbis\d3d9-result.txt`: adapter, HRESULT of each step, tables and ms;
  - DXVK also writes your log next to the exe (`d3d9test64_d3d9.log`).

<a id="entrega"></a>

## Delivery

`/data/pkg/orbis-win-W124-f3bdc91ecf00.pkg`, with the check-back reading (613 files). W123 withdrawn.

<a id="prueba"></a>


## Test

1. `C:\orbis\d3d9test64.exe` (guest): Can you see the window with the triangle on the background that changes?
2. `C:\orbis\d3d9test32.exe` (relaunch, WoW64): same thing.

Then read `d3d9-result.txt`, the logs of DXVK next to each exe and the run log (fetch-hardware.py --build W124).

Risks:
- That DXVK rejects the device for some missing feature in GFX7; Your log says so.
- The memory mapping below 4 GiB in 32 bits (`VK_EXT_map_memory_placed`, that RADV but our winsys never proved).
- The presentation goes through the copy to CPU the usual.

<a id="resultado-físico-20261103t000821z"></a>


## Physical result: 20261103T000821Z

**64 bits (d3d9test64.exe, guest)**: DXVK 2.7.1 works in PS4 until the first picture.
- `Found device: PS5 (radv 26.0.8)`. Create the device with robusts2, descriptor_buffer, graphics_pipeline_library, extended_dynamic_state3, maintenance5- 7, transform_feedback, geometry and tessellation.
- Swapchain `B8G8R8A8_UNORM`, FIFO, 632 × 453, 5 images. Submitts to GPU complete (`radv/ps4: submit 1..4 … GPU completed`).
- `PWVK show_frame n=1`: The first picture was drawn in the window.
- Then the DXVK presenter thread calls `vkWaitForPresentKHR`. The WSI headless of RADV does not implement it, so jump to the direction 0 (`handle_syscall_fault … ip=0`, `Exception 0xc0000005 in Unix call`) and DXVK ends with status 3.

**32 bits (d3d9test32.exe, WoW64)**:
- DXVK x86 comes to create the device (36 extensions).
- `win32u_vkMapMemory2KHR vkMapMemory2EXT failed: -5` and `Failed to map Vulkan memory: VK_ERROR_MEMORY_MAP_FAILED`. `CreateDevice` returns `D3DERR_NOTAVAILABLE` (8876086a).
- Cause: in the branch `__PS4__` of `radv_amdgpu_winsys_bo_map` (Mesa of Crema), a mapping located (`use_fixed_addr`, `VK_EXT_map_memory_placed`) returns NULL. Without mapping below 4 GiB, no memory visible by CPU works for a process of 32 bits.

# W125 (02.24)

`tools/build-win32u-ps4.py`: `init_physical_device` stop offering `VK_KHR_present_id`, `present_id2`, `present_wait` and `present_wait2`, because the WSI headless does not implement the waiting. DXVK back to your pace without them.

Delivery: `/data/pkg/orbis-win-W125-49f75d9ba11e.pkg`, with the check-back reading. W124 withdrawn.

Test: d3d9test64.exe. The triangle is expected on a changing background ~ 5 s and `d3d9-result.txt` with `frames>0`.

**pending for 32 bits**: implement the mapping located in the GNM winsys.
- Mapping back the direct memory of the BO in the direction you choose Wine (`sceKernelMapDirectMemory` with `MAP_FIXED`, alignment of 16 KiB) and report that alignment in `minPlacedMemoryMapAlignment`.
- When you unmap, return the reservation to Wine.
- It requires recombinant Mesa (`tools/vk-h0/build-mesa.sh`, `VARIANT=wine`).

<a id="resultado-físico-w125-20261103t001804z--direct3d-9-de-64-bits-aceptado"></a>


## Physical result W125: 20261103T001804Z - Direct3D 9 of 64 bits accepted

- `d3d9-result.txt`: `adapter=00000000:PS5;device=00000000;clear=0;draw=0;present=0; frames=1204;ms=5003`. They are **~ 240 paintings per second** with a triangle and a clear per picture, in a window of 632 × 453.
- Log: `PWVK present fps 170.6 → 251.8 → 276.3`, copy to the window by GDI in ~ 1,2 - 1,6 ms per picture, without `Exception`. Departure of the guest with 0 (`loader_lock=1`, `other_threads_wait=0 count=5`) and desktop intact.
- DXVK 2.7.1 x64 over winevulkan → RADV (GFX7) → GNM works in PS4.
- Limits: the presentation continues to pass through the CPU (phase 6) and the test is minimal. It doesn't say anything about real shakers, textures, or performance of a game.

<a id="w126-en-preparación-mapeos-ubicados-para-32-bits"></a>


# W126 (in preparation): maps located for 32 bits

`tools/vk-h0/patch-mesa-placed.py`, called from `build-mesa.sh` (`VARIANT=wine`):
- `ac_ps4_bo_cpu_map_fixed` (in `ac_ps4_drm.c`) remap the direct memory of the BO, only for CPU, in the direction it reserved Wine (`sceKernelMapDirectMemory` with `MAP_FIXED`, rounded length at 16 KiB. The GPU retains its mapping and both share the same physical pages.
- The `__PS4__` branch of `radv_amdgpu_winsys_bo_map` uses it when `use_fixed_addr`, instead of returning NULL.
- `minPlacedMemoryMapAlignment` passes to 16 KiB in PS4 (before, the system page). Wine reserve with granularity of 64 KiB, so the rounding is within your reservation.

Compilation: Mesa rebuilt (the first attempt failed by `-Wmissing-prototypes`; The prototype was added) and the telemetry GPU was rebuilt on the new `libamd_common`. The ELF contains `placed map of bo`. Delivery W126 (02.25): `/data/pkg/orbis-win-W126-662aff853a70.pkg`, with the check-back reading; W125 withdrawn.

Test: d3d9test32.exe (relaunch, WoW64). The same triangle and `d3d9-result.txt` with `frames>0` is expected; d3d9test64.exe as regression.

<a id="resultado-físico-w126-20261103t003114z--direct3d-9-de-32-bits-aceptado"></a>


## Physical result W126: 20261103T003114Z - Direct3D 9 32 bit accepted

- **d3d9test32.exe** (relaunch, wowprospero):
  - `Using placed map with alignment 16384` and maps located in 0x3080000, 0x3790000, 0x3b90000 and 0x4b90000, all below 4 GiB, without `vkMapMemory2EXT failed`.
  - `d3d9-result.txt`: all steps in 0, **1290 tables in 5000 ms (~ 258 FPS)**; the log reports ~ 295 presentations per second.
  - `process_exit status=0` and back to the desk.
- **d3d9test64.exe** (regression): ~250 FPS and output 0.
- **Phase 4 (D3D9 with DXVK) accepted in 32 And 64 bits.** It's a minimum case: it doesn't test real shakers, textures, games, or performance with load. D3D10/11 were not tested and need the dxgi of DXVK per program (phase 7). D3D8 goes by the same d3d9 of DXVK and it was not tested either.
