<a id="w137-código-de-32-bits-nativo-fase-5a-paso-2"></a>


# W137: native 32 bit code (phase 5A, step 2)

[English](HARDWARE_W137.md) | [Español](HARDWARE_W137-es.md)

APP_VER 02.36. Base W136: the raw signal input is on the PS4 (`caps=3`).

<a id="cambios"></a>


## Changes

- `tools/build-wow64native-ps4.py` (new) weapon the `wow64native` of prospero-win:
  - **`wow64native.dll`** (PE, base 0x7a400000) The thunks 32 → 64 must be below 4 GiB.
  - **Unix side:** `unix.c` compiled for Orbis, linked to ELF and recorded as `wow64native.so` in `platform/ps4/pw_wine_unixlibs.c`.
    - Ask ntdll `__wine_prospero_native_wow64_caps(1)` and demand the bits 1 and 2.
    - In PS5 it also requires 4. Here is not required because ntdll in Orbis does not keep xstate in the context of signal. It leaves it logged: `PWNATIVE wow64native caps=3 (no xstate in exception contexts)`.
    - Consequence: an exception in code of 32 bits does not carry the high half of the YMM.
  - **`wow64.dll`:** `WINE_PS4_WOW64_CPU` accepts `wow64native.dll` or `wowprospero.dll` (patch 0611). If `BTCpuProcessInit` of wow64native fails, load `wowprospero.dll` and the program is still in the translator (patch 0614): `wow64native.dll did not start (...); using wowprospero.dll`.
- `tools/build-signal-ps4.py`: the initial context of 32 bits carries CS 0x33 (`cs32_sel`), as in the branch FreeBSD of Wine. In Orbis it was 0, which only the translator tolerated.
- `native/wine_hardware.c`: a PE32 is launched with `--wow64-cpu=wow64native.dll` (in the log, `cpu=wow64native`).

<a id="qué-se-espera"></a>


## What is expected

- If you start native:
  - `wow64: CPU wow64native.dll from WINE_PS4_WOW64_CPU`;
  - `wow64native initialized: cs32=0033 ss32=003b cs64=0043 avx=...`.
- If not, the line of fall to the translator, and the program goes as in W136.
- What you have to look at: that guide-window32 opens and closes, and the FPS of the SuperMarioKart menu. In the translator they were about 12.

<a id="prueba-física-20261103t041814z"></a>


## Physical test: 20261103T041814Z

The user confirmed that the two programs started. In each log:

    wow64: CPU wow64native.dll from WINE_PS4_WOW64_CPU
    PWNATIVE wow64native caps=3 (no xstate in exception contexts)
    wow64native initialized: cs32=0033 ss32=003b cs64=0043 avx=1

**The 32 bit code runs native in PS4.**
- gui-window32 ended with `process_exit status=0`.
- SuperMarioKart reached the menu. There were exceptions of Wine resolved (`RtlUnwindEx ... cs=0043`), that is, the path of exceptions from native code walked.

### FPS

The SuperMarioKart menu makes the same FPS as in the translator:
- W134 (traductor): 11,4–12,0.
- W137 (native): 11,5 - 12,0

So the CPU of 32 bits was not the limit. The curve is flat at 12, which points to the presentation (ddraw → wined3d Vulkan → copy to CPU → GDI → sink) or at a fixed rate of the game, not at the calculation. The log of ddraw/file/virtual of PE32 is about 500 lines per second: it is not enough to explain the cap, but it should be removed when measuring.
