<a id="w209-la-salida-por-fallo-de-un-invitado-termina-y-el-siguiente-arranque-limpia-lo-que-quedó-borrador"></a>


# W209: a guest's failure output ends and the next boot cleans what was left (draft)

[English](HARDWARE_W209-invitado-salida-borrador.md) | [Español](HARDWARE_W209-invitado-salida-borrador-es.md)

Eraser of the browser side session, to join `HARDWARE_W209.md`. None of this was tested on the console.

<a id="qué-pasó-en-w208"></a>


## What happened in W208

Report: `reports/wine-hardware-w208/physical/20261104T152601Z/run-0001.log`. The user said, "it closed only Pale Moon this time."

- **The safety net of W208 works.** In the line 7106 appears `PWGUEST unhandled exception c0000005 … the guest ends`, And the desk goes on.
- **But the output does not end:**
  - ends the other 42 threads (line 7113) and does not record anything else;
  - by destroying the windows of the failed thread, `DestroyWindow` sent `WM_DESTROY` to the window procedure of Pale Moon, in `xul.dll` (`WTSUnRegisterSessionNotification`, TaskbarList);
  - that code, with its other threads finished, never came back.
  
  Nothing was unloaded.
- **The next start** (line 7216) found `xul.dll` and the rest already loaded. W208 only the modules loaded from the guest's boot were counted as its own, so it had none (`own_modules … count=0`).
- **The Lost Forest:** the threads of `UnityCrashHandler64.exe`, another guest still alive, stop the discharge (`kept (threads in their code)`, lines 5331 a 5334). It's what I expected.

<a id="cambio"></a>


## Change

`tools/build-guest-hw.py`, with `guest-exit-w209.patch.py`:

1. **Windows without the program code:** each guest window, and his daughters, passes to `DefWindowProc` before destroying it. This is not called the program code, as when Windows destroys the windows of a process that ended.
2. **Without `DllMain` after `TerminateProcess`:** a guest who ends up with `TerminateProcess` It's marked. That includes his own. `TerminateProcess`, the failure and the unhandled exception of W208. Your modules are downloaded without `DllMain(DETACH)`, that Windows does not call when a process is over; `ExitProcess` He keeps calling him. Registered `PWGUEST own_modules … detach skipped (terminated)`.
3. **Which modules are specific to the guest:** those that meet the three conditions:
   - are outside the Windows directory;
   - were not in the process before their first guest;
   - They're not in the folder of another guest who keeps running.
   
   There's a list of live guests. If a guest ends up without downloading them, they are left for the next one.
4. **Cleaning when starting:** before loading a guest, the modules that left guests already finished are downloaded, also without `DllMain` (`PWGUEST own_modules … leftovers=1`). If a thread is still in that code, they stay.

`C:\orbis\noguestunload.txt` still leaves everything alone in traces.

<a id="construcción"></a>


## Build

1. `python3 tools/build-guest-hw.py`.
2. `tools/link-wine-boot.py`.
3. `tools/build-wine-hardware.py`.

<a id="prueba-física"></a>


## Physical test

1. Open Pale Moon, go to YouTube with a second tab until it closes.
2. Open it again without reboot.
3. Close it normally and open it again.
4. **What to look for in the log:**
   - after failure:
     - `other threads ended, N windows of this thread destroyed`;
     - `own_modules … terminated=1`;
     - `detach skipped (terminated)`;
     - `PWGUEST unloaded xul.dll … gone=1`;
     - `PWGUEST memory … bytes=…`;
   - in each `load_begin`, a `available=` similar to the previous one;
   - if there was anything left from an earlier exit, `own_modules … leftovers=1` when you started.

<a id="no-verificado"></a>


## Not verified

- Nothing was tested on the console.
- The revisions were applied on copies of the sources, and `kernelbase` (`process.c`, `debug.c`, `memory.c`, `file.c`) passes `-fsyntax-only` with mingw. The builder didn't run.
- A guest whose departure is stuck remains on the living list, and its modules are not cleaned until reboot.
- Global hooks, threat pool timers and COM objects of the downloaded modules are not removed.
