<a id="w191-direct3d-11-detectado-al-abrir-y-aleatoriedad-del-kernel"></a>


# W191: Direct3D 11 detected when opening and randomizing the kernel

[English](HARDWARE_W191.md) | [Español](HARDWARE_W191-es.md)

APP_VER 02.90. Base W190. The result of W190 is in `docs/HARDWARE_W190.md`.

<a id="cambios"></a>


## Changes

- **Detection of Direct3D 10/11** (`tools/build-guest-hw.py` kernelbase): a program of 64 bits that matters `d3d11.dll`, `dxgi.dll` or `d3d10*.dll` He runs by himself, without a hand mark. It counts both direct and deferred imports. With `"OrbisRunsAlone"="N"` still as guest. Among the programs that bring the build, only `d3d11test64.exe` matters those DLL.
- **Alloy** (`tools/build-telemetry-ps4.py`, ntdll `system.c`:
  - `get_random` first use `sysctl kern.arandom` (CTL_KERN 1, KERN_ARND 37), and if it fails `/dev/urandom`.
  - If both fail, the consultation (`SystemInterruptInformation`, through which they pass `RtlGenRandom` and `BCryptGenRandom`) returns `STATUS_UNSUCCESSFUL` with a line `PWRANDOM unavailable`, instead of returning the buffer without changing.

<a id="prueba-física"></a>


## Physical test

Report: `reports/wine-hardware-w191/physical/20261104T040443Z/`. User response: "1. Okay, 2. Okay. "

- **Detection:**
  - An unmarked copy of the test (`d3d11test64d3d11test64.exe`) gives `PWGUEST runs_alone … reason=dxgi_import`, renews and DXVK creates the presentation chain.
  - The original continues to enter by its W190 mark.
- **Alloy:** each process records `PWRANDOM source=kern.arandom` (six runs). `/dev/urandom` it was not necessary and it is not known if the sandbox lets it open.
- **Pale Moon:** open `https://example.com`.

<a id="después"></a>


## After

In W192 the detection is taken: the `dxgi` of Wine is created to create the presentation chain of a device DXVK with the `dxgi` of DXVK, so Direct3D 11 should walk inside of explorer, without relaunching.
