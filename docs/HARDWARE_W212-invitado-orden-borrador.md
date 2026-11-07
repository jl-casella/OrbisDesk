<a id="w212-los-módulos-de-un-invitado-se-descargan-en-orden-de-dependencias-y-sin-dllmain-borrador"></a>


# W212: the modules of a guest are downloaded in order of dependencies and without DllMain (draft)

[English](HARDWARE_W212-invitado-orden-borrador.md) | [Español](HARDWARE_W212-invitado-orden-borrador-es.md)

Eraser of the browser side session, to join `HARDWARE_W212.md`. None of this was tested on the console.

<a id="qué-pasó-en-w210"></a>


## What happened in W210

Report: `reports/wine-hardware-w210/physical/20261104T161446Z/run-0001.log` (lines 2173 to 2300) and `run-0002.log`, with the same pattern. The user said: "it is tilted when opening now Pale Moon. Nor does it open directly and freeze OrbisDesk. "

1. **First start:** Pale Moon reboot itself, and the first one usually (`ExitProcess`).
2. **The download:** with a normal output, W209 was still running `DllMain(DETACH)`. In addition, the download called `LdrUnloadDll` until each module disappeared, from the newest to the oldest.
3. **What that broke:** also reduced the references that imports from other modules had. `VCRUNTIME140.dll` had 13 references, most imports of `MSVCP140.dll` and `mozglue.dll`. It was unmapped after 3 calls (`calls=3`), with those two still loaded.
4. **The judgment:** the `DllMain` of `MSVCP140.dll` He called `VCRUNTIME140.dll` already unmapped (violation of access to `7FD8E50B0`, `VCRUNTIME140+0x50b0`). The exception handlers, who were there, failed also.
5. **The hang:** the thread that came out was left with the loader lock (`PWDUMP begin … loader_owner=0064`). Explorer stopped, and the Pale Moon restart was unable to load (`relaunch … parent_wait=258`).

<a id="cambio"></a>


## Change

`tools/build-guest-hw.py` (kernelbase `process.c`), with `guest-unload-order-w211.patch.py`:

1. **Without `DllMain(DETACH)` at any output:** no guest runs `DllMain(DETACH)` of his own modules. When a guest comes out, his other threads are over, so that code can't run as in Windows. W209 I was just skipping it for the finished guests. It is recorded `detach skipped (exit|terminated|leftovers)`.
2. **Release by rounds:** in each round, `LdrUnloadDll` once for each module that no other module of its own still matters or loads in a different way. Imports are seen in their own headers. The unit counters of Wine release the rest.
   - A module that is still loaded after 64 rounds, or that is in a import cycle, is recorded (`PWGUEST kept: … still loaded`) and is left.
   - In the end it is recorded `PWGUEST unloaded module=… own=… remaining=… rounds=…`.
3. **The memory, only if it all went away:** the memory that reserved your code is released only if all of them were downloaded. If not, the `mozglue` allocator would be left with pointers to liberated regions.

<a id="construcción"></a>


## Build

1. `python3 tools/build-guest-hw.py`.
2. `tools/link-wine-boot.py`.
3. `tools/build-wine-hardware.py`.

<a id="prueba-física"></a>


## Physical test

1. Open Pale Moon from a OrbisDesk just started.
2. Close it, open it again, make it fail and open it again.
3. **What to look for in the log:**
   - `detach skipped (exit)` at the start of the reboot;
   - `PWGUEST unloaded … remaining=0`;
   - `relaunch … parent_wait=0`;
   - a window of Pale Moon.

<a id="no-verificado"></a>


## Not verified

- Nothing was tested on the console.
- The change was applied on copies of the sources, and `process.c` passes `-fsyntax-only` with mingw. The builder didn't run.
