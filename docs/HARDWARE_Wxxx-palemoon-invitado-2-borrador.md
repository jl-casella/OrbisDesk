<a id="wxxx-pale-moon-como-invitado-segunda-ronda-de-diagnóstico-borrador"></a>


# Wxxx: Pale Moon as guest, second round of diagnosis (draft)

[English](HARDWARE_Wxxx-palemoon-invitado-2-borrador.md) | [Español](HARDWARE_Wxxx-palemoon-invitado-2-borrador-es.md)

Eraser of the browser side session. Follow `HARDWARE_Wxxx-palemoon-invitado-borrador.md` (W198). The main session assigns the number. None of this was tested on the console.

<a id="qué-mostró-w199"></a>


## What did he show W199

Report: `reports/wine-hardware-w199/physical/20261104T123309Z/run-0001.log`. `palemooncopy.exe` opens in the line 4581.

- **The diagnostic lines of W198:**
  - `PWDUMP begin age_ms=8233 loader_owner=0198 loader_count=0` (line 5886) is the last line of a thread of Wine.
  - There is no line `PWLOCK`.
- **After:** only the composer writes (`PWSINK show_stats`) and RADV (`radv/ps4: submit 4000`). The screen is still composed; what stopped is the threads of Windows.
- **The lock loader:** has it the `0198` thread of Pale Moon. `LockCount` in 0 means that no one else is waiting for it, so the scout interface thread (`0024`) is not stuck in the lock loader.
- **Where the tilt was stuck:** after `begin`, the next step is `CreateToolhelp32Snapshot`. That call needs the wineserver: `OpenProcess`, `ReadProcessMemory` and `NtQuerySystemInformation`. He didn't come back.
- **Why the observer did not show it:** the calls he makes on each turn (`GetGUIThreadInfo`, `GetForegroundWindow`) read the shared memory of win32u (`get_shared_input`) and they don't ask the server for anything. That's why their lines didn't say if the server kept responding.
- **W198:** their spins did end, but with `PWDUMP modules unavailable error=5`. `OpenProcess` of the process itself returned denied access. Without modules, each battery was cut into the 0 frame.

**Hypothesis, unconfirmed:** the wineserver, which in OrbisDesk is a thread of the same title, was stopped. That explains:
- that any thread that asks for something will remain waiting (the interface thread to explore in your next call, all of Pale Moon, the tilt);
- the warning of 60 s in a critical section does not appear;
- that the composer, who does not use the server, keep walking.

**Disloaded:**
- **The W195 suspension signals:** W192, which had no thread signals, were frozen as well.
- **A blocker socket:** the sockets are non-blockers with `SO_NBIO` from the phase 8.

You don't know what's stopping the server.

<a id="cambio-diagnóstico-segunda-ronda"></a>


## Change (diagnosis, second round)

`diag-freeze-2.patch.py` changes `tools/build-wine-delete-server.py` and `tools/build-explorer-hw.py`, with changes of W198 already applied. It only adds traces: nothing recovers the hang, shortens a wait, or jumps a lock.

- **server (`PWSERVER`):** a peeled thread inside the server (`server/fd.c`) reports a step from the main loop that carries more than 5 s. One step is:
  - an event of a fd (the orders of the threads arrive like this);
  - a timer.
  
  For each of them records the type, function, fd Unix and event. If it is an order, also the customer thread and order number (`enum request` of `include/wine/server_protocol.h`).
  - Repeat the notice at the 20 s and every 60 s.
  - It records `PWSERVER resumed` when the step is over.
  - Write with `write(2)` from a buffer in the stack, without the stdio lock.
  - When you start it records `PWSERVER watch rc=0`.
- **explorer (`PWDUMP`):** no longer uses toolhelp for modules. For each address, take the image of its own headers (`VirtualQuery` and the export name), without the loader lock. Before the first call to the server records `PWDUMP step=thread_list`.

<a id="construcción"></a>


## Build

1. `tools/build-wine-delete-server.py` and `tools/build-explorer-hw.py` already have the changes (applied with `diag-freeze-2.patch.py`).
2. Run those two builders and then `tools/link-wine-boot.py` and `tools/build-wine-hardware.py`.

<a id="prueba-física"></a>


## Physical test

1. When you start, the log has to show `PWSERVER watch rc=0`.
2. Open `palemooncopy.exe` and sail until it freezes. Wait 2 minutes.
3. **What to look for in the log:**
   - `PWSERVER stuck_s=… kind=… func=… unix_fd=… client=… req=…`: what does the server do;
   - `PWDUMP step=thread_list`: if the tilt reached its first call to the server.
4. **The name of the function of `func`:** `wine.elf` retains the symbols of the server, also the static (in W200: `thread_poll_event`, `sock_poll_event`, `pwserver_main_loop`). The line also brings `watch=`, the direction of the watch itself (`pw_server_watch`). To place `func` in `llvm-nm-14 wine.elf`, the difference between the two directions is used, in case the ELF was loaded into another base.

<a id="no-verificado"></a>


## Not verified

- Nothing was tested on the console.
- The two changes were compiled only with `-fsyntax-only`, with the recipe of each builder, on copies. The builders didn't run.
- If the server stops out of one step (for example, within `kevent`), the monitor does not notice anything. In that case, the lack of `PWSERVER stuck` lines is also a data.
