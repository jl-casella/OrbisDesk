<a id="w173-compromiso-de-páginas-del-heap-mesa-residente-dll-de-winecfg-fases-6-y-7"></a>


# W173: commitment of heap pages, Mesa resident, DLL de winecfg (phases 6 and 7)

[English](HARDWARE_W173.md) | [Español](HARDWARE_W173-es.md)

APP_VER 02.72. Base W172. The result of W172 is in `docs/HARDWARE_W172.md`.

<a id="cambios"></a>


## Changes

**1. `opengl32` and `libgallium_wgl` are loaded** (`tools/build-guest-hw.py`, guest download in kernelbase:
- Before you release the module from a guest, if those two DLL are loaded, they will be fixed (`GET_MODULE_HANDLE_EX_FLAG_PIN`) and recorded `PWGUEST unload pinned`.
- The Mesa WGL keeps its own threads within `libgallium_wgl`. In W172, when they downloaded `d3d11test64.exe` they were released with it, and explorer failed within the released module.

**2. DLL from winecfg in `system32`** (`tools/build-wine-hardware.py`, program block of W043; did the direct access session):
- The closure of imports of programs of Wine (`uxtheme.dll` and `msimg32.dll`) also goes to `system32`.
- In W172 those DLL were only in the builtin folder, and winecfg did not open (`c0000135`).

**3. Heap page commitment** (`tools/build-audio-ps4.py`, `virtual.c`, `pw_commit_backing`):
- In W172 the race ended equally: `PWVM fault addr=0x1f08000c … before=0x8002000d … retry=1`, and then the same failure with `retry=0`.
- There was no `PWVM commit_backing`: by compromising, the consultation of each page had given 0, so the arrangement did not act.
- A consultation with flag 0 on an address that the kernel does not know can return to the next region. From W173 a page counts as backed only if the reported region contains it and is compromised (bit 4 of the lags).
- A reservation containing it is left to `pw_wine_memory_protect`. Any other case is mapped with flexible memory.
- Each commitment of 1 MiB or more records `PWVM commit` with pages, backed, mapped, failed and first query.

**4. Network:** `platform/ps4/pw_wine_net.c` returns to the original; W172 had come out with an ongoing version of the 8 phase. The phase 8 goes to W174 (draft: `docs/HARDWARE_W174-red-borrador.md`).

<a id="qué-se-espera"></a>


## What is expected

- `d3d11test64.exe` continues to fail in the exchange chain, but explorer does not fall when closing it.
- winecfg opens. Then follow the steps 5 and 6 of the W172 test: the program override `dxgi=builtin` has to follow when reopening the app and after the next climb.

<a id="prueba-física"></a>


## Physical test

Reporte: `reports/wine-hardware-w173/physical/20261103T193724Z/`.

- **`d3d11test64.exe`:** opened twice. The two fail in the exchange chain, as expected (for the user, "closed").
  - When downloaded: `PWGUEST unload pinned L"opengl32.dll"` and `L"libgallium_wgl.dll"`.
  - Explorer continued to work and then opened SuperMarioKart. The change 1 works.
- **winecfg:** open. There are two things missing, going to the direct access session:
  - **About:** according to the user "closes." The guest comes out with status 0 and no error in the log.
  - **Test sound:** does not sound. The audio port (`PWAUDIO open init=00000000 … failed=00000000`) is opened and `msacm32.drv` and `midimap.dll` (`c0000135` fail.
- **SuperMarioKart** (`20261103T193958Z`, "error as always, closed"):
  - `PWVM fault addr=0x1f66000c`, with the consultation failed (`0x8002000d`) before and after; The reattempt failed the same.
  - Just before, `PWVM commit base=0x1f660000 size=0x2f0000`: the consultation had given 0 with the region `0x1f660000-0x1f950000`, exactly the view.
  - The `flags` registered (`0x6f6e6101`) is misread: the bits occupy a byte and the name of the region begins immediately. The real byte is `0x01`, i.e. flexible, uncompromised memory. That's why the arrangement left the page at `pw_wine_memory_protect`.
  - The failing block is the last of a series: there were 2530 commitments of 1 MiB or more, 2304 of them of `0x2F0000`, 7,3 GiB in total throughout the race, with so many `NtFreeVirtualMemory`. The free flexible memory when starting was about 400 MB.
- **Hypothesis for W174:** Wine returns memory by mapping `PROT_NONE` above with the `mmap` libc, and that does not return the flexible memory to the kernel. The budget is running out, and the last block's commitment is left with no memory behind.
