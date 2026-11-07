<a id="w116-programas-de-32-bits-fase-1-del-plan-pe32"></a>


# W116: 32 bit programs (phase 1 of the plan PE32)

[English](HARDWARE_W116.md) | [Español](HARDWARE_W116-es.md)

APP_VER 02.15. Base W115, which brings Solitaire and Spider to Start → Games.

<a id="objetivo"></a>


## Objective

That a PE32 (i386) can be opened from the desktop. It is the first step for SuperMarioKart.exe and for games of 32 bits in general (Direct3D and audio go in subsequent phases).

<a id="cambios"></a>


## Changes

- **kernelbase** (`tools/build-guest-hw.py`, `CreateProcessInternalW`):
  - An EXE with `Machine == I386` stops receiving `reject_title_replacement`.
  - Explorer shows a dialogue: OrbisDesk reinitiates and runs the program alone, and the open programs are closed.
  - If the user accepts, follow `NtCreateUserProcess`, which renews the title with that program (`pw_hw_switch_program`). If it cancels, it is returned `STATUS_CANCELLED`.
  - Log: `PWOPEN pe32_relaunch image=… answer=…`.
- **launcher** (`native/wine_hardware.c`):
  - `pe_machine()` read the PE header of the EXE that is to be run (only unit C:).
  - If it's 0x14c, it happens `--wow64-cpu=wowprospero.dll`. That option was lost in W015; without it wow64 seeks `wow64cpu.dll`, which the prefix does not bring.
  - Log: `pe_machine path=… machine=…` and `calling_wine_boot_main cpu=wowprospero`.
- **fixture**: `C:\orbis\gui-window32.exe`, which is `fixtures/win32/gui_window.c` compiled with `i686-w64-mingw32-gcc`. Paint the window in a color, at the 2 s write `C:\orbis\result.txt` and close.

It does not change what runs in PE64; The guests are still the same.

<a id="entrega"></a>

## Delivery

`/data/pkg/orbis-win-W116-3d23071b5e56.pkg`, with the check-back reading; reports/wine-hardware-w116/transfers/20261102T202916Z.json report (564 files, 9 uploaded). W115 withdrawn.

<a id="prueba"></a>


## Test

1. In File Manager open `C:\orbis\gui-window32.exe`, accept dialogue and wait for relaunch. A blue window has to appear about 2 s; Then it closes and the desk returns.
2. Open `Documents\SuperMarioKart\SuperMarioKart.exe`. It is expected to fail for lack of Direct3D, and what matters is where it fails.

```sh
python3 tools/fetch-hardware.py --build W116 --host 192.168.68.104
```

In the log you have to look:
- `pe32_relaunch` and `switch_program`;
- in the next run, `cpu=wowprospero` and `wow64: CPU`;
- `result.txt` with `painted=1;pixel=8c3c14`;
- `return_to_desktop`.

Risks:
- A PE32 GUI never ran in the PS4. He only ran `console32-bare` in W013/W014.
- The 32 bit or x87/SSE low wowprospero SEH was also not tested on hardware.

<a id="resultado-físico-20261102t203507z"></a>


## Physical result: 20261102T203507Z

- **run- 0001** (desk): `PWOPEN pe32_relaunch image=C:\orbis\gui-window32.exe answer=1`, then `switch_program`. Dialogue and relaunch work.
- **run- 0002** (the 32 bit program alone):
  - `pe_machine machine=0x14c`, `cpu=wowprospero` and `wow64: CPU wowprospero.dll from WINE_PS4_WOW64_CPU`.
  - Load ntdll of syshow64, wow64, wow64win, kernel32, user32, gdi32, imm32 and msvcrt of 32 bits. He's the first. PE32 GUI that goes so far in the PS4.
  - After win32u initializes Vulkan (RADV up to `ac_query_gpu_info = 0`, a system call of win32u Jump to the address 0 (`handle_syscall_fault code=c0000005 addr=0 ip=0`) and return with c0000005.
  - On the 64 bit desk, that same point ends at `wgl:internal_context_create Failed to create internal thread context`, without failing.
  - The log ends at `NtGdiCreateBitmap planes = 0`: there is no window, there is result.txt and there is no return to the desk.
- SuperMarioKart.exe does not appear in these logs.

It is still not known what call it is: the trail does not say what function was left in NULL. W117 (02.16) only adds traces for runs PE32 (`trace+wgl,trace+vulkan,trace+wow`) and nothing else changes. It's up at `/data/pkg/orbis-win-W117-540833c24102.pkg`, with the check-back reading. The gui-window32.exe test must be repeated.

<a id="w117--w118-la-llamada-nula"></a>


## W117 → W118: the null call

W117 (20261102T204218Z, run- 0002) left the missing trace:

- `Instance proc vkGetPhysicalDeviceProperties2 not found`. The Vulkan instance of win32u is 1.0: only the `…2KHR` functions of `VK_KHR_get_physical_device_properties2` are resolved.
- RADV announces `VK_EXT_map_memory_placed` and `VK_KHR_map_memory2`. In WoW64 (`zero_bits != 0`), `init_physical_device` (`dlls/win32u/vulkan.c:516`) calls `instance->p_vkGetPhysicalDeviceProperties2`, without KHR, which is NULL. In 64 bits that branch does not run, so the desk does not fail.

W118 (02.17), in `tools/build-win32u-ps4.py`, use `p_vkGetPhysicalDeviceProperties2KHR` on that branch. It is a bug of Wine upstream that appears with WoW64 over an instance 1.0. It was rebuilt win32u (47 units), relinked the ELF (without indefinite symbols) and packed. Delivery: `/data/pkg/orbis-win-W118-6eb3e742dc83.pkg`, with the check-back reading; W117 withdrawn. The PE32 traces of W117 are maintained.

Test: repeat gui-window32.exe. If it happens, blue window about 2 s, `C:\orbis\result.txt` and `return_to_desktop`.

<a id="resultado-físico-w118-20261102t204952z--fase-1-aceptada"></a>


## Physical result W118: 20261102T204952Z - phase 1 accepted

- run- 0001: `pe32_relaunch answer=1` → `switch_program`.
- run- 0002: `cpu=wowprospero`, `wow64: CPU wowprospero.dll`, visible blue window (confirmed by the user), `process_exit status=0`, `return_to_desktop`.
- `C:\orbis\result.txt` (read by FTP): `painted=1;pixel=8c3c14;client=464x280`, the same color and reading as the reference PE64.
- run- 0003: the desk returns normally.

It is the first Windows GUI program of 32 bits running in PS4, with the prospero-win translator. It does not measure performance or SEH test, x87/SSE or code that is modified.

<a id="lo-que-necesita-supermariokartexe-inspección-de-importaciones"></a>


## What you need SuperMarioKart.exe (import inspection)

It was copied to / tmp of WSL only to read the import table and then it was deleted; the game on the console was not changed.

- It is a game Blitz3D (`Blitz Runtime Class`, `Unable to run Blitz Basic module`).
- Importa KERNEL32, USER32, GDI32, ADVAPI32, SHELL32, ole32, WSOCK32, WINMM, MSACM32, DDRAW (`DirectDrawCreateEx`), DINPUT (`DirectInputCreateEx`), d3dxof y DPLAYX.
- The audio is FMOD over DirectSound, loaded in running time.
- Blitz3D use **DirectDraw 7 / Direct3D 7**. DXVK does not cover D3D7 (only d3d8 forward), so for this game the phase 4 has to be wined3d, not DXVK. The options are the renderer Vulkan of wined3d over winevulkan i386, or that of OpenGL over Zink i386.
- DLL i386 missing to start it: ddrag, wined3d, dinput, d3dxof, dplayx, wsock32, dsound and mmdevapi (plus the driver audio of the 3 phase).
