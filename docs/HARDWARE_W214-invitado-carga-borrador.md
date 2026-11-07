<a id="w214-el-exe-de-un-invitado-encuentra-sus-dll-y-su-descarga-espera-al-loader-borrador"></a>


# W214: The EXE of a guest finds his DLL and its download awaits the loader (draft)

[English](HARDWARE_W214-invitado-carga-borrador.md) | [Español](HARDWARE_W214-invitado-carga-borrador-es.md)

Eraser of the browser side session, to join `HARDWARE_W214.md`. None of this was tested on the console.

<a id="qué-pasó-en-w212"></a>


## What happened in W212

Report: `reports/wine-hardware-w212/physical/20261104T170942Z` (`run-0001.log` and `run-0002.log`). The user said, "YouTube came to load but it froze in connection. I wanted to close it down from the Task Manager, but it doesn't appear in Applications. I restarted OrbisDesk, opened it, closed it, and I couldn't open it again. "

**What works:** the first start start output (`detach skipped (exit)`, `own=25 remaining=0 rounds=5`, `parent_wait=0`).

1. **The Pale Moon reboot does not load** (`run-0002.log`, lines 2030 a 2044): "Library mozglue.dll (which is needed by... palemoon.exe) not found," and also missing `VCRUNTIME140`.
   - A guest's EXE was loaded with `LoadLibraryExW( ruta, 0, 0 )`. This is only the case in the process image directory (the scout directory) and in the current directory.
   - From a direct access it worked because `ShellExecute` of Wine puts the direct access folder as the current directory while it starts the program.
   - The W210 auxiliary thread starts with the scout directory.
2. **After a normal closure nothing** (`run-0002.log`, line 2993 is unloaded: `kept: loader lock busy for 2 s`. The same is true of the remains when they start, and the following starts end with a state 1. Another thread had the loader lock more than the 2 of the attempt; on the console, loading one DLL is slow.
3. **YouTube hangs** (`run-0001.log`, lines 4048 and 4626):
   - It appears `PWHUNG … MozillaWindowClass "YouTube - Pale Moon"`
   - The main thread (`0098`) is not blocked. It is in `mozjs.dll`, 20 frames in, with the same frames at 70 s, `rip` within the same function and `r9 = e5e5e5e5` (the filling of the released memory).
   - It is the same engine corruption of JavaScript from the previous failures, seen as a loop.
   - **Hypothesis, unconfirmed:** the JIT. The SpiderMonkey interruption and the Pale Moon hanging monitor suspend the main thread and read or change its context from another thread, which in the console passes through the signals of W195.
   - **Proof that separates it:** open YouTube with direct access "Pale Moon (no JIT)."

<a id="cambio"></a>


## Change

`tools/build-guest-hw.py` (kernelbase `process.c`), with `guest-load-w214.patch.py`:
1. **DLL from the EXE folder:** the EXE of a given guest with route is loaded with `LOAD_WITH_ALTERED_SEARCH_PATH`. Your imports are first sought in your own folder, as for the image of a process. That's also true after a guest called `SetDefaultDllDirectories`, which Wine combines with the EXE folder.
2. **The waiting for the loader lock:**
   - The download on exit waits until 30 s and records the lock owner every 5 s (`waits for the loader lock, owner …`).
   - The passing of remains when you start continues with 2.
   - When you start you no longer expect to download another guest (`leftovers skipped: another unload runs`), because it runs on the scout thread.

<a id="construcción"></a>


## Build

1. `python3 tools/build-guest-hw.py`.
2. `tools/link-wine-boot.py`.
3. `tools/build-wine-hardware.py`.

<a id="prueba-física"></a>


## Physical test

1. Start OrbisDesk and open Pale Moon. It restarts only once, and the window has to appear.
2. Close it and open it again twice.
3. Open YouTube with "Pale Moon (not JIT)."
4. **What to look for in the log:**
   - `relaunch … parent_wait=0`, and then `Loaded … mozglue.dll` from the Pale Moon folder;
   - at each closure, `remaining=0` (if there was a wait, `waits for the loader lock, owner …`).

<a id="no-verificado"></a>


## Not verified

- Nothing was tested on the console.
- The change was applied on copies of the sources, and `process.c` passes `-fsyntax-only` with mingw. The builder didn't run.
- It is not known what thread the loader lock had in W212; The new trace says so.
