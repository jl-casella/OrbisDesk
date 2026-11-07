<a id="w215-el-loader-lock-se-toma-aunque-un-hilo-que-lo-esperaba-haya-sido-terminado-borrador"></a>


# W215: the loader lock is taken even if a thread that expected it has been finished (draft)

[English](HARDWARE_W215-loader-lock-borrador.md) | [Español](HARDWARE_W215-loader-lock-borrador-es.md)

Eraser of the browser side session, to join `HARDWARE_W215.md`. None of this was tested on the console.

<a id="qué-pasó-en-w214"></a>


## What happened in W214

Report: `reports/wine-hardware-w214/physical/20261104T173546Z`. The user said, "W214 no JIT seemed more fluid, but it was refrozen when loading YouTube."

- **The restart only works.** (`run-0001.log`, lines 2233 a 2237): `own=25 remaining=0`, `parent_wait=0`, and the child carries.
- **The normal closure does not download anything** (lines 2798 to 3234):
  - repeats `waits for the loader lock, owner 0000` for 30 s and ends in `kept: loader lock busy for 30 s`;
  - the following start-ups end with a state 1;
  - W207 and W212 already showed `loader_lock=0 tries=200` in `ps4_guest_exit_process`.
- **Why?:**
  - `ps4_guest_exit_process` ends the other threads of the guest with the loader lock (W122). A finished thread while waiting for the lock leaves its increment in `LockCount`.
  - `RtlTryEnterCriticalSection` just take the lock if `LockCount` okay - 1, so you never get it again. That's why he looks unowned and never free.
  - `RtlEnterCriticalSection` if it takes it: each release points to the light, and the dead thread never takes that sign. That's why you explore and DLL loads continue to walk.
- **YouTube without JIT** (`run-0002.log`, lines 3287 and 4034):
  - `PWHUNG … "YouTube - Pale Moon"` appears;
  - the main thread (`0060`) remains in a loop within `mozjs.dll`, over memory with `e5e5e5e5`, at 70 s;
  - the JIT is discarded;
  - addresses are far from any `mozjs.dll` export: they are internal functions.
  
  It was not found where the memory was released from. The memory paths of the console did not record any failure (`PWVM`).
- **Apart:** in `run-0002.log`, from the line 5089, `libMangoHud.dll` low failure `libgallium_wgl.dll` in `C:\orbis\glxgears.exe`, a guest OpenGL which is not Pale Moon, And the title falls. It's another mistake..

<a id="cambio"></a>


## Change

`tools/build-guest-hw.py` (kernelbase `process.c`), with `loader-lock-w215.patch.py`. There are two waiting for the lock loader: the `ps4_guest_exit_process` loader and the discharge of the own modules.
- **The new thing:** in both, if an attempt fails and the lock has no owner, it is taken with a `LdrLockLoaderLock` blocker, which in that state returns immediately. It is recorded `took the ownerless loader lock after N tries`.
- **With owner:** attempts continue as before.

<a id="construcción"></a>


## Build

1. `python3 tools/build-guest-hw.py`.
2. `tools/link-wine-boot.py`.
3. `tools/build-wine-hardware.py`.

<a id="prueba-física"></a>


## Physical test

1. Open Pale Moon, close it and reopen it twice.
2. **What to look for in the log:**
   - `exits status 0`, and then `remaining=0` at each closure;
   - if necessary, `took the ownerless loader lock`;
   - at the exit, `loader_lock=1`.

<a id="no-verificado"></a>


## Not verified

- Nothing was tested on the console.
- The change was applied on copies of the sources, and `process.c` passes `-fsyntax-only` with mingw. The builder didn't run.
- The explanation of `LockCount` comes from the code of the critical sections of Wine, not from a measurement. The new trace shows when it happens.
- The hanging and the failures of YouTube remain unexplained.
