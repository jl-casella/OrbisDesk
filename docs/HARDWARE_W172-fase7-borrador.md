<a id="w172-direct3d-1011-en-32-bits-con-el-dxgi-de-dxvk-y-winecfg-fase-7"></a>


# W172: Direct3D 10/11 in 32 bits with the dxgi of DXVK, and winecfg (phase 7)

[English](HARDWARE_W172-fase7-borrador.md) | [Español](HARDWARE_W172-fase7-borrador-es.md)

APP_VER (complete main session). Base W171.

<a id="punto-de-partida"></a>


## Point of departure

- W124 installed d3d8, d3d9, d3d10core and d3d11 of DXVK 2.7.1, but not its `dxgi.dll`.
- The 64 bit desk uses `dxgi` build Wine: the Khronos loader verifies drivers with a factory DXGI and MangoHud asks for GPU (W087). The 64 bit programs run as guests within that process (W052), and a process cannot have two `dxgi.dll`.
- The `d3d11` of DXVK needs the `dxgi` of DXVK. That's why D3D10/11 didn't work.

<a id="cambios"></a>


## Changes

- `tools/build-wine-hardware.py`:
  - `dxgi.dll` 32 bit DXVK goes `syswow64`; `system32` is still with Wine;
  - override `"dxgi"="native,builtin"` in `user.reg`.
    - In 32 bits, each program runs in its own process (W116), with `vulkan-1` building of Wine and without Khronos loader, and finds `dxgi` of DXVK.
    - In 64 bits, `system32\dxgi.dll` is that of Wine, which carries the building signature and therefore it is still charged as building (`dlls/ntdll/loader.c`).
  - It compiles `fixtures/win32/d3d11test.c` as `C:\orbis\d3d11test32.exe` and `C:\orbis\d3d11test64.exe`.
- `fixtures/win32/d3d11test.c` (new)
  - window, `D3D11CreateDeviceAndSwapChain` and ~ 5 s of `ClearRenderTargetView` with a changing color;
  - `d3d11-result.txt` record the HRESULT of each step, the level of features, the adapter DXGI, the loaded `dxgi.dll` route, the tables and the ms;
  - does not use shakers: it is a minimum case, like `d3d9test`.
- `tools/stage-wine-programs.py`: adds `winecfg.exe` (PE64). Its import closure amounts to `uxtheme.dll` and `msimg32.dll`.
- `tools/make-start-menu.py`: "Wine Configuration" in System Tools.
- `tools/upload-hardware.py`: `user.reg` fuses when you go up.
  - Wine rewrite the record in the console: in W108 - W112 `user.reg` and `system.reg` They were always as `uploaded`. That's why a common climb erased what was stored with winecfg.
  - Now the `user.reg` of the console is down. The `HKCU\Software\Wine\AppDefaults` blocks (what winecfg keeps per program) come out of the console; everything else, from the building.
  - The result is raised and checked with your hash. The search of the rise has `user_reg` with the origin, the preserved blocks and the three hashes.
  - If there is no `user.reg` on the console, or it does not start with `WINE REGISTRY Version 2`, the build is raised as it is and recorded.
  - Tested without connection against `user.reg` of W167:
    - fused with itself gives the same file;
    - retains the blocks by program of the console;
    - the global overrides are still those of the build;
    - A second climb doesn't change anything.

To build: `tools/stage-wine-programs.py` and `tools/make-start-menu.py` before `tools/build-wine-hardware.py`.

<a id="límites"></a>


## Limits

- D3D10/11 in 64 bits is still not working: a guest shares the `dxgi` of Wine on the desktop. `d3d11test64.exe` is to confirm it, not to make it happen. It requires those programs to be relegated like those of 32 bits; is as a separate step (risk: the Khronos loader loads `dxgi` and, with that of DXVK, can be reentered into `vkCreateInstance`).
- Only winecfg program settings are retained. The "Default settings" are set up by the building.
- You have to close the app before installing a build. If it is open during the upload, Wine rewrite `user.reg` within 30 s and step on the merged file.
- `uxtheme.dll` now exists in the prefix. Explorer tried to load it and failed (`c0000135`); Now he's carrying it. Without an installed theme, the look should remain the classic.
- `joy.cpl` is left for after xinput (phase 5).

<a id="prueba"></a>


## Test

1. `C:\orbis\d3d11test32.exe`: the window is expected with the background that changes color for ~ 5. Then read:
   - `d3d11-result.txt`: `device=00000000`, `dxgi=` in `syswow64` and the amount of pictures;
   - the log of DXVK next to the exe;
   - in the run log, `trace+loaddll` with `dxgi.dll` loaded as `native`.
2. 32 bit regression:
   - `d3d9test32.exe`;
   - `ddraw7test32.exe`;
   - SuperMarioKart (wined3d/ddraw does not use `dxgi`, but the override is global).
3. 64 bit regression: `vkcube` or `vkspin64` with MangoHud. The desk has to continue to load the `dxgi` building (`trace+loaddll`).
4. `d3d11test64.exe` (guest): It is expected to fail at `device=`. We have to write down the code.
5. Start → System Tools → Wine Configuration:
   - to go through the eyelashes; if any fails, note which and the log;
   - in Applications, add `d3d11test32.exe`, and in Libraries put `dxgi` = builtin;
   - close the app and open it again: the adjustment has to follow, and `d3d11test32.exe` has to fail with `dxgi` of Wine. This proves that the programme adjustment is applied.
6. In the next rise, `user_reg.source=merged` and `app_default_blocks_kept` greater than 1.

Risks:
- That some 32 bit that works today use the `dxgi` of Wine without us knowing; the regression of the 2 point covers it in part.
- The audio and graphic tabs of winecfg consult devices and can fail on the console.
