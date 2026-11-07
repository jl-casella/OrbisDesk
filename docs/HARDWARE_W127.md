<a id="w127-directdraw-y-direct3d-7-con-wined3d-sobre-vulkan-fase-4b"></a>


# W127: DirectDraw and Direct3D 7 with wined3d over Vulkan (phase 4b)

[English](HARDWARE_W127.md) | [Español](HARDWARE_W127-es.md)

APP_VER 02.26. Base W126 (phase 4 accepted: D3D9 with DXVK in 32 and 64 bits).

<a id="enfoque"></a>

## Approach

- The wined3d of our Wine fixed has a renderer Vulkan with an emulated function fixed-function in HLSL (`dlls/wined3d/ffp_hlsl.c`, `d3d_info->ffp_hlsl = true` in `adapter_vk.c`). It is what you need ddraw and D3D7 (Blitz3D), and it does not depend on OpenGL, which in the PS4 has no context.
- Your presentation uses the same route as DXVK: vulkan- 1 → winevulkan → WSI headless → window.
- The renderer is chosen by process:
  - The 32 bit programs, which are relaunched alone, receive `WINE_D3D_CONFIG=renderer=vulkan` (`native/wine_hardware.c`).
  - The 64 bit desk retains `renderer=no3d`: dxgi only lists for the Khronos loader and MangoHud (W087).
- DXVK continues to attend d3d8/d3d9/d3d10core/d3d11. wined3d just draw ddraw (DX1- 7).

## Fixture

`fixtures/win32/ddraw7test.c` → `C:\orbis\ddraw7test32.exe`:
- `DirectDrawCreateEx`, normal cooperative, primary with clipper, off-screen 3D surface, `IDirect3D7::CreateDevice(IID_IDirect3DHALDevice)`;
- then ~ 5 s of Clear with changing color, a triangle XYZRHW ¥124; DIFFUSE and a Blt to the primary;
- `ddraw7-result.txt` save the HRESULT of each step, the pictures and the ms.

<a id="entrega"></a>

## Delivery

`/data/pkg/orbis-win-W127-c0d3ae3d3672.pkg`, with the check-back reading. W126 withdrawn.

<a id="prueba"></a>


## Test

1. `C:\orbis\ddraw7test32.exe`: The triangle is expected on a changing background.
2. `SuperMarioKart.exe`: whatever you show (menu, error, nothing).

Risks:
- The HLSL → SPIR-V (vkd3d-shader) compilation runs under the 32 bit translator and can take or fail.
- The paths of ddraw that the render Vulkan of wined3d still does not implement.

<a id="resultado-físico-20261103t003912z"></a>


## Physical result: 20261103T003912Z

- **ddraw7test32.exe**:
  - All steps return 0 (create, cook, primary, clipper, target, d3d7, device, clear, draw and blit), but give **55 pictures in 5 s** and the window is blank (confirmed by the user).
  - Log: `wined3d_texture_vk_load_texture Unimplemented load from WINED3D_LOCATION_DRAWABLE`, `vk_blitter_blit Failed to load the destination sub-resource`. There was no `show_frame`.
  - The D3D7 device and the FFP in HLSL work. What's wrong is to show the primary.
- **SuperMarioKart.exe**: opens, fails for the same reason and Blitz shows "access violation" (exception C + + `e06d7363`). It comes out with 0.
- Cause: in window mode (`DDSCL_NORMAL`), `ddraw_surface_update_frontbuffer` copies the primary to * front buffer * of the swapchain. In OpenGL that's the window; in the renderer Vulkan of wined3d that front buffer cannot be read or written (`DRAWABLE`).

# W128 (02.27)

- `tools/build-ddraw-hw.py` (new, same method as taskmgr/explorer) compiles a `ddraw.dll` i386 with `surface.c` revised. If `WINE_D3D_CONFIG` order `renderer=vulkan`, the primary without flip update:
  - copy the visible part of the rectangle (intersection with the client area of the swapchain window, in screen coordinates) to **back buffer**;
  - it presents it with `wined3d_swapchain_present`, with the rectangle origin in screen coordinates and the destination in customer coordinates.
  - The failures are as if `PWDDRAW … failed`.
- Replace the i386 ddraw in syswow64 and `lib/wine/i386-windows`.
- The full-screen flip (`swap_interval > 0`) does not change: it already used the back buffer.

Delivery: `/data/pkg/orbis-win-W128-f41bc03a1d20.pkg`, with the check-back reading. W127 withdrawn.

<a id="resultado-físico-w128-20261103t005338z"></a>


## Physical result W128: 20261103T005338Z

- **ddraw7test32.exe: DirectDraw 7 / Direct3D 7 works.**
  - The triangle is seen, confirmed by the user.
  - `ddraw7-result.txt`: all steps in 0, **1208 tables in 5000 ms (~ 240 FPS)**; the log reports ~ 290 presentations per second and the output is 0.
  - The path is wined3d (renderer Vulkan, FPP in HLSL) → back buffer → present.
- **SuperMarioKart.exe**:
  - Open your window: a first box of 400 × 300 and then the mode of 800 × 600 (`show_frame n=1/n=2`).
  - Then `guest exception 0xc0000005 at eip 0x10027948 … address 0x4 write 0`, a reading of NULL + 4 in the code of the game itself. Blitz reports it as access violation.
  - Hypothesis: the relaunched process does not start in the game folder. The EXE and its arguments are passed but not the directory, so the relative loads (`SMK\*.x`, `.png`) fail and return NULL.

# W129 (02.28)

`native/wine_hardware.c`: a program that starts alone (relaunch or `launch.txt`) makes `chdir` the folder of your EXE before starting Wine, which takes the current directory of the process from there, as it would Explorer. Log: `program_cwd dir=… rc=…`. Delivery: `/data/pkg/orbis-win-W129-87ebc14d997c.pkg`, with the check-back reading; W128 withdrawn.

<a id="resultado-físico-w129-20261103t005957z"></a>


## Physical result W129: 20261103T005957Z

`program_cwd … rc=-1 errno=1`: the kernel denies `chdir` the title (EPERM). The game continued to start out of your folder and the failure is repeated equally (`eip 0x10027948 … address 0x4`). The directory hypothesis still couldn't be tested.

# W130 (02.29)

- It was first tried to redirect `getcwd` with `--wrap` in the link, but `create-fself` rejects it (`missing library for symbol (getcwd)`), so it was discarded.
- `tools/build-env-ps4.py` (new) reproduces the `env.c` tested ntdll, verified by hash, with a single change: `get_initial_directory` uses `PW_PROGRAM_DIR` (Unix route) before the cwd Unix. Log: `PWBOOT initial_directory …`.
- The pitcher passes `--env=PW_PROGRAM_DIR=<carpeta del EXE>` to the programs that start alone (`program_cwd … via=PW_PROGRAM_DIR`). `build-wine-hardware.py` replaces `env.o`.

Delivery: `/data/pkg/orbis-win-W130-d7994349f00c.pkg`, with the check-back reading. W129 withdrawn.

<a id="resultado-físico-w130-20261103t014428z"></a>


## Physical result W130: 20261103T014428Z

- `PWBOOT initial_directory /data/wine-prefix/drive_c/users/orbis/Documents/SuperMarioKart`: the game already starts in your folder. Even so the failure is the same (`eip 0x10027948 … address 0x4`), so the directory was not the cause.
- Disassembled from EXE (temporary copy in WSL `/tmp`, deleted later; the game was not changed):
  - `0x10027948` is the Blitz function that draws an image.
  - The neighboring chains are `Image does not exist` (0x1011454c) and `Image frame out of range` (0x10114530.
  - With the image pointer in 0 (`edi=0`) it jumps directly to `mov 0x4(%edi)`.
  - I mean, a `LoadImage` returned 0 and the game tried to draw it.
- The 241 files of `SMK` are on the console. Hypothesis: the creation of the ddrag surface for the already decoded image, or the opening of the file, fails.

# W131 (02.30)

- The PE32 runs use `WINEDEBUG=warn+module,trace+seh,trace+loaddll,warn+debugstr, trace+ddraw,trace+file,warn+d3d,warn+vulkan`, to see each call to ddrag and each file opening. It takes off the trace of Vulkan of W117.
- Before compiling, the C: disk was filled (0 MB free). With the user's permission, only the `runtime/` folders of `build/wine-hardware-w001`... `w125` (45,9 GB were deleted, reclamation). W126 - W131, reports, logs and packages are preserved.
- Delivery: `/data/pkg/orbis-win-W131-5328384a488f.pkg`, with the check-back reading. W130 withdrawn.

<a id="resultado-físico-w131-20261103t023957z"></a>


## Physical result W131: 20261103T023957Z

- SuperMarioKart.exe: `CreateFileW L"smk/splash800x600.png"` → `…/SuperMarioKart/SMK/ splash800x600.png` (search without distinguishing capital works) and returns handle. Open the file twice and fail in `0x10027948`.
- Between the two openings there is neither `NtReadFile` nor `NtQueryInformationFile`. The image is most likely to be read by section (`NtCreateSection` / `NtMapViewOfSection`), which the channel `file` does not trace. In the PS4 data file mapping passes by `map_file_into_view`.
- Before the game: plugins of FreeImage (`*.fip`, `plugins\*.fip`), none, which is normal.

# W132 (02.31)

The runs PE32 add `trace+virtual,trace+section`. Delivery: `/data/pkg/orbis-win-W132-d4d3b4712798.pkg`, with the check-back reading (only the ELF changed). W131 withdrawn.

<a id="w132w133-causa-raíz-de-supermariokart"></a>


## W132 - W133: root cause of SuperMarioKart

- W132 (`trace+virtual`): between the two openings of the PNG there is no section or reading mapping.
- W133 brought `fileio32.exe` (`fixtures/win32/fileio_test.c`), which opens the same PNG with the same graph (`smk\`). The result (`fileio-result.txt`, run 20261103T03xx):
  - CreateFile, GetFileSize (438750), ReadFile (`89504e47`, PNG), MapViewOfFile, fopen, free, `_open` and `_read` work.
  - **`GetFileType=0 error=50`**: FILE_TYPE_UNKNOWN with ERROR_NOT_SUPPORTED.
- `get_device_info` (ntdll/unix/file.c) returned `STATUS_NOT_SUPPORTED` in ORBIS for all descriptors. The MSVC C runtime that you use Blitz3D classifies the handle with `GetFileType` when you open; with "unknown" closes it and gives the opening for failure. So there are two openings without readings, `LoadImage` returns 0 and the drawing function reads NULL + 4. The running of mingw (`fopen` in filio32) does not make that check.

# W134 (02.33)

`tools/build-wine-directory-ps4.py` (the `file.o` that is already recombinated) implements `get_device_info` in ORBIS since `fstat`:
- file or directory → `FILE_DEVICE_DISK_FILE_SYSTEM`;
- FIFO o socket → `FILE_DEVICE_NAMED_PIPE`;
- character device → `FILE_DEVICE_UNKNOWN`;
- `Characteristics` = 0, without making up removable, remote or just reading flags.

It affects all programs, also those of 64 bits. Delivery: `/data/pkg/orbis-win-W134-cf64b54dcb8a.pkg`, with the check-back reading; W133 withdrawn.

<a id="resultado-físico-w134-20261103t032832z--supermariokart-corre"></a>


## Physical result W134: 20261103T032832Z - SuperMarioKart runs

- `fileio32.exe`: **`GetFileType=1`** (FILE_TYPE_DISK. The rest, just like before.
- **SuperMarioKart.exe no longer falls**:
  - Load the presentation image, open the audio and present 800 × 600 to **~ 12 FPS** (`PWVK present fps 11.4–12.0`) for several minutes. There's no `raise_guest_exception`. The Runs was still alive when the log was collected (54443 lines).
  - The audio is zero (`PWAUDIO level … peak=0`). The music of the game is `.mid` files, and in the PS4 there is no MIDI synthesizer (winmm has no MIDI device). The effects `.wav` by FMOD did not yet appear in this section.
- The user needs to confirm the visible (menu, controls). The performance (12 FPS) is limited by the 32 bit translator, wined3d in the CPU and presentation by CPU (phases 5 and 6).
- The watchman (`tools/watch-hardware-run.py`) did not detect these runs: each past aborted with 550 of FTP in a log that was being written. Now jump that file on that pass; was tested with the filio32 Runs.

**Phase 4b accepted.** The user confirmed that SuperMarioKart.exe (Blitz3D, DirectDraw 7 / Direct3D 7, 32 bits) shows your menu on the PS4 with W134. pending: MIDI music (no synthesizer), confirm controls, speed (~12 FPS).
