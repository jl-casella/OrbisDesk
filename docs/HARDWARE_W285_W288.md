# W285–W288: guest audio streams, GPU log folder, GRAPHICS menu and MangoHud on wined3d

[English](HARDWARE_W285_W288.md) | [Español](HARDWARE_W285_W288-es.md)

Four builds over W284 (2026-11-07). Each keeps the previous one. Package: `OrbisDesk.pkg`, ORBW00002.

| Build | APP_VER | Change | Physical result |
|---|---|---|---|
| W285 | 03.84 | A guest's audio streams leave the mixer when it unloads | Tested: NFS U2 closed from the overlay, no stale stream |
| W286 | 03.85 | RADV's GPU logs go to `/data/orbisdesk/gpu` | Not tested on its own |
| W287 | 03.86 | GRAPHICS overlay entry; MangoHud on wined3d games | Tested: MangoHud attaches to SuperMarioKart; the saved renderer was not applied |
| W288 | 03.87 | wined3d reads the program's renderer at every `wined3d_create` | Uploaded; not tested yet |

## W285: audio streams of a guest that ends

W284 evidence (`reports/wine-hardware-w284/physical/20261107T153841Z/run-0001.log`):
- Need for Speed Underground 2 was closed from the overlay.
- Its mmdevapi stream stayed in the console audio driver's mixer, `playing=1` with nothing held, until OrbisDesk ended.
- Each stream closed that way would have left one more behind.

Change:
- `tools/build-audio-ps4.py` (wineps4 driver):
  - Each stream records the guest of the creating thread: `TEB.UserReserved[0]`, read from the 32-bit TEB for WoW64 calls.
  - One more Unix call follows mmdevapi's 37 calls. It moves a guest's streams out of the mixer to an orphan list.
  - Orphans are not freed. mmdevapi's session list, shared by every guest of the process, still holds the dead guest's clients and their handles. A later release frees an orphan. A handle in neither list is refused with `E_HANDLE`.
- `tools/build-guest-hw.py`: `ps4_guest_unload` calls the driver through `NtQueryVirtualMemory(MemoryWineLoadUnixLibByName)` and ntdll's `__wine_unix_call_dispatcher`. Kernelbase does not link winecrt0.

Log lines: `PWAUDIO stream ... owner=... wow=1`, `PWAUDIO stream ... orphaned`, `PWAUDIO guest ...: N streams out of the mixer`.

Physical test (`reports/wine-hardware-w285/physical/20261107T163224Z/`):
- NFS U2, closed from the overlay, stopped and released its own stream that time, so the orphan path was not needed.
- The owner was recorded (`owner=0x23d3d50 wow=1`), and the mixer reported no stream after the close.
- The orphan path itself is still unobserved on hardware.

Transfer: `reports/wine-hardware-w285/transfers/20261107T162644Z.json`. Package SHA-256 `0c359ea9dff24a2f90f49f8809bb629092e3555aeab587799f4271e942317ed4`.

## W286: GPU log folder

The old state folder `/data/orbis-win` was removed from the console after the W283 migration: 2,457 files and 538 directories. Directories created by the title are mode 755 and owned by the title's user, so FTP needs `SITE CHMOD 777` before deleting inside them.

RADV's winsys (`~/vk-h0/src/mesa-crema/src/amd/common/ac_ps4_drm.c`) still wrote `radv-ps4.log`, GPU hang and fault reports and the flight recorder under `/data/orbis-win/gpu`. Its `mkdir` does not create parents, so without the old folder those files were silently not written.

`tools/build-telemetry-ps4.py` now rewrites the 17 paths to `/data/orbisdesk/gpu` before building `libamd_common.a`. It refuses to continue if any old path remains or fewer than 12 new ones are found. Only the `mesa-wine` build uses that source tree.

The only remaining `/data/orbis-win` string in the ELF is the migration source (`PW_LEGACY_STATE_ROOT`).

Transfer: `reports/wine-hardware-w286/transfers/20261107T165854Z.json`. Package SHA-256 `f9d2889a5a99486165f4759495d628b9aa71dbeeb561d46f67f5336f894bacd4`.

## W287: GRAPHICS overlay entry and MangoHud on wined3d

Both changes were staged as patches by a separate session and integrated here.

**GRAPHICS (GRAFICOS)**, under STRETCH in the control overlay, per 32-bit program:
- Choices: DXVK + Vulkan, DXVK + OpenGL, wined3d + Vulkan, wined3d + OpenGL.
  - First half: Direct3D 8/9 through DXVK or Wine's own d3d8/d3d9.
  - Second half: wined3d's renderer.
- X asks kernelbase's closer to write `HKCU\Software\Wine\AppDefaults\<exe>\Direct3D\renderer` and `...\DllOverrides\d3d8`/`d3d9`, then read them back.
- The menu states that the choice applies from the program's next start.
- `syswow64\pw-wined3d\` holds Wine's i386 d3d8.dll and d3d9.dll. The guests' i386 ntdll loads them for a guest whose own AppDefaults says `builtin`. Load order in explorer's world otherwise comes from explorer.exe's key.

Limits:
- 32-bit programs only.
- A relaunched title has no closer.
- Two games with different d3d9 loaded at once share one module name.

**MangoHud on wined3d:**
- Since W259, wined3d took `vkGetInstanceProcAddr` from winevulkan.dll, so the implicit MangoHud layer never entered SuperMarioKart's instance. W284's `in_front=1` was only the overlay's estimate.
- W287 builds the i386 Vulkan loader from a copy whose `loader_windows.c` creates no DXGI factory (`tools/vk-h0/patch-vulkan-loader-i386-nodxgi.py`). That factory was the W257 recursion through Wine's dxgi.
- wined3d tries `vulkan-1.dll` first again.

Physical test (`reports/wine-hardware-w287/physical/20261107T215435Z/`):
- MangoHud attaches to SuperMarioKart: `PWD3D vulkan library=vulkan-1.dll`, then `PWHUD i386 vkCreateInstance`, `vkCreateDevice` and `vkCreateSwapchainKHR 800x600`.
- GRAPHICS saved `dxvk-gl` for `SuperMarioKart.exe` and read it back on the next start, but that start still used Vulkan.
  - wined3d was loaded once (`Using the Vulkan renderer`) and stayed loaded in the 32-bit world after the first run.
  - It reads its renderer only in `wined3d_dll_init`.

Transfer: `reports/wine-hardware-w287/transfers/20261107T173710Z.json`. Package SHA-256 `ac4a6d9f85f470e967a2f2d4a1f500be8d9559a79c985e7ad75f4b52444dc2ea`.

## W288: renderer per program at each wined3d object

`tools/build-wined3d-hw.py`, `wined3d_main.c`: `wined3d_create` calls `pw_program_renderer()`. That function takes the renderer from:
1. the program's `AppDefaults\<exe>\Direct3D\renderer` (`vulkan`, `gl` or `no3d`);
2. otherwise the world's `WINE_D3D_CONFIG`;
3. otherwise the value chosen when the DLL loaded.

`GetModuleFileNameW(NULL)` names the guest. Log: `PWD3D renderer=gl for L"SuperMarioKart.exe" from the program (was vulkan)`.

OpenGL for wined3d in explorer's 32-bit world (Wine's builtin opengl32, Mesa WGL/Zink) has not run on the console yet. A failure there is expected to show as a wined3d adapter error, not a silent fallback.

## Related

- Steam S2 01.06 and S3 01.07 passed on the console: [STEAM_S2](STEAM_S2.md), [STEAM_S3](STEAM_S3.md).
- The local build folders `build/wine-hardware-w001` to `w279` were removed to free disk space. Packages under `out/` and evidence under `reports/` were kept.
