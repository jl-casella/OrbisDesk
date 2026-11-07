<a id="w119-dll-de-32-bits-fase-2-del-plan-pe32"></a>


# W119: DLL from 32 bits (phase 2 of the plan PE32)

[English](HARDWARE_W119.md) | [Español](HARDWARE_W119-es.md)

APP_VER 02.18. Base W118 (phase 1 accepted: gui-window32.exe runs by WoW64 and wowprospero).

<a id="cambios"></a>


## Changes

- The missing i386 DLL (s): ddraw, wined3d, dinput, d3dxof, dplayx, wsock32, mswsock, hid, dsound, mmdevapi, dxgi, winevulkan, vulkan- 1 were compiled on the host tree set (`.deps/wine/runtime/build`, opengl32, d3d8 and d3d9. The `make` of these objectives also compiled other parts of the tree (by dependencies) and stopped after the 16 were ready.
- `tools/stage-wine-i386.py` (new)
  - takes those DLL plus its import closure, without which they are already in the sealed prefix sysmow64;
  - He leaves `out/wine-i386/` with his manifest. They are 15 modules, without unsolved imports.
- `tools/build-wine-hardware.py` copies them with `copy_verified` to `C:\windows\syswow64` and `wine/lib/wine/i386-windows`.

What **does not** include: the native part of wined3d (`wined3d.so`) or the opening part of 32 bits. wined3d load but has no drawing to do; That's phase 4b.

<a id="entrega"></a>

## Delivery

`/data/pkg/orbis-win-W119-ba78ebe15b9b.pkg`, with the check-back reading (594 files, 32 uploaded). W118 withdrawn. It weighs 442 MB because the i386 DLL kept their debugging information; W120 it's all over them.

<a id="prueba-pendiente"></a>


## Pending test

Open `Documents\SuperMarioKart\SuperMarioKart.exe`, accept dialogue and wait. The expected thing is for you to load your DLL (ddrag, dinput, dplayx, d3dxof, wsock32) and fail to create the surface of Direct3D 7. You have to bring the log with fetch-hardware.py --build W119.

<a id="resultado-físico-20261102t215549z"></a>


## Physical result: 20261102T215549Z

- run- 0001: `pe32_relaunch` → `switch_program` of SuperMarioKart.exe.
- run- 0002: `cpu=wowprospero`.
  - Load the 32 bit DLL, including the new ones.
  - `ws2_32.dll`, imported through wsock32, returns FALSE in its `DllMain`. `loader_init` abort with c0000142, `process_exit status=0xc0000142` and return to the desk. No window of the game.
- Cause: the ws2_32 i386 was loaded from `C:\windows\syswow64`. ntdll associates the Unix part of a DLL builtin only when it was found in `wine/lib/wine/i386-windows`, so there was no `static_unixlib …/ws2_32.so` and `__wine_init_unix_call` failed. In 64 bit does not pass, because those DLL are in `x86_64-windows`.
- It also appears `find_forwarded_export … cryptbase.SystemFunction036` (advapi32); It's not what cuts the execution.

Correction in W120: `tools/stage-wine-i386.py` adds `ws2_32` to your objectives, so it is also left in `wine/lib/wine/i386-windows`.
