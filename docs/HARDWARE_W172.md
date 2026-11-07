<a id="w172-compromiso-de-páginas-invisibles-al-kernel-fase-6-direct3d-1011-en-32-bits-con-el-dxgi-de-dxvk-y-winecfg-fase-7"></a>


# W172: commitment of invisible pages to the kernel (phase 6), Direct3D 10/11 in 32 bits with the dxgi of DXVK, and winecfg (phase 7)

[English](HARDWARE_W172.md) | [Español](HARDWARE_W172-es.md)

APP_VER 02.71. Base W171. The result of W171 is in `docs/HARDWARE_W171.md`. The phase 7 was prepared by the direct access session.

<a id="fallo-del-heap-de-supermariokart"></a>


## Heap failure of SuperMarioKart

- `tools/build-audio-ps4.py`, `virtual.c` of ntdll, `set_protection`:
  - by compromising pages that Wine has no compromise, each one is consulted with `sceKernelVirtualQuery`;
  - if the kernel does not report it (W171: `0x8002000d`), it is mapped with a flexible memory fixed on it before `mprotect`;
  - if that mapping fails, the page is unmapped and remapped;
  - Those pages have no data, so mapping them on top of them doesn't lose anything.
- Each case remains as `PWVM commit_backing`: the first 32 and all that fail.
- The diagnosis `PWVM fault` and the single reattempt of W171 are maintained.
- It is expected that SuperMarioKart will finish the race and leave without `PWVM fault`.

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

<a id="prueba-física"></a>


## Physical test

Report: `reports/wine-hardware-w172/physical/20261103T191612Z/`. User response: "Another problem"; winecfg "made a mistake." The race of SuperMarioKart has not yet been tested.

- **`d3d11test32.exe`:** works.
  - DXVK creates the device with `D3D_FEATURE_LEVEL_11_0` (maximum 11 _ 1) and `dxgi.dll` is charged as native.
  - The window presents pictures by the layer of GPU (`path=gpu_layer`), and the process comes out with `status=0x00000000` at 12,6.
- **`d3d11test64.exe`:** fails as expected.
  - The `dxgi` of Wine rejects the device of DXVK (`This is not the device we're looking for`), and `D3D11CreateDevice` does not create the exchange chain.
  - When you download the guest, you also download `opengl32.dll` and `libgallium_wgl.dll`, which the `wined3d` GL adapter had loaded. Then explore fails in `0x7FC3F4460`, within `libgallium_wgl` already released, and the app reboot.
- **winecfg:** does not open: `Library uxtheme.dll (which is needed by winecfg.exe) not found`. `uxtheme.dll` and `msimg32.dll` were left only in `wine/lib/wine/x86_64-windows`, without a copy in `system32` of the prefix.
- **SuperMarioKart** (second batch, `20261103T192014Z`, "ended as always with access violation"):
  - `PWVM fault addr=0x1f08000c` with the failed consultation (`0x8002000d`) before and after; The reattempt failed the same.
  - There was no `PWVM commit_backing`, so the arrangement did not act.
  - The process comes out with `status=0x00000000`.
- **Network (untested):** the link of W172 compiled a `platform/ps4/pw_wine_net.c` that session of the phase 8 I had already edited.
  - `sendmsg` / `recvmsg` accept `msg_name`, and the hors `MSG_*` are translated from SDK to the kernel.
  - `EAGAIN` is no longer drawn, and `pw_wine_socket_nonblock` is defined but not used.
  - W173 return to the original file.
- **Up:** the fusion of `user.reg` gave `source=merged` and the uploaded file is equal to that of the build.

<a id="prueba-propuesta-fase-7"></a>


## Proposed test (phase 7)

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
