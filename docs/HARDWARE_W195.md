<a id="w195-señales-a-un-hilo-concreto-pthread_kill"></a>


# W195: signals to a particular thread (pthread_kill)

[English](HARDWARE_W195.md) | [Español](HARDWARE_W195-es.md)

APP_VER 02.94. Base W194. The result of W194 is in `docs/HARDWARE_W194.md`.

<a id="cambios"></a>


## Changes

- **`platform/ps4/pw_wine_threads.c`** (new, only in the final link): a keel thread id table (`pthread_getthreadid_np`, the `unix_tid` which ntdll gives the server) to `pthread_t`.
  - The threads enter by `pthread_create`, linked to `--wrap=pthread_create`. The main thread comes in by a builder.
  - They go out the destroyer of a pthread key, before they finish.
  - `pw_wine_thread_kill` look for the thread and call `pthread_kill` for libkernel with the signal number of FreeBSD.
  - It records `PWTHREAD kill` (the first 16 shipments and all failure) and `PWTHREAD table_full`.
  - The design of the table is prospero-win (`wine/ps5/pw_wine_threads.c`, LGPL).
- **`platform/ps4/pw_wine_signals.c`:** is added `pw_wine_orbis_signal`, which translates the signal number of SDK to the kernel.
- **`tools/build-wine-delete-server.py`:** check `server/ptrace.c`. `send_thread_signal` sends SIGUSR1 (suspension, context of another thread) by `pw_wine_thread_kill`. The other signals are still not sent, as in W064.
- **ntdll does not change.** Wine already blocks SIGUSR1 during each call to the server.
- **Disk space:** the packaging failed twice because C: was full. With the user's permission, `runtime/` and `app/` were deleted from `build/wine-hardware-w001` to `w180`, except W011, which it uses `tools/run-wine-hardware.py`. They were released 23 GB.

<a id="prueba-física"></a>


## Physical test

Reporte: `reports/wine-hardware-w195/physical/20261104T112911Z/`.

User response: "TLF opened ok, but with F12 I could not activate it MangoHud. The joystick moves your pointer, the keyboard goes ok and you hear tmb ok. When it was closed, everything was closed OrbisDesk. palemooncopy.exe frozen again. "

### The Lost Forest (`run-0001.log`)

- **signals:** the signals come to his thread (`PWTHREAD kill tid=112470 sig=10/30 status=0`). He's gone. `thread_signal unavailable … sig=10`.
- **Image:** the presentation chain comes out by DXVK (`PWDXGI swap chain through DXVK's dxgi`). It runs at about 76 fps at 1280 × 720 (`PWVK present fps 75.8–79.4`).
- **Audio:** is heard (`PWAUDIO … peak=1250`).
- **Keyboard:** walk.
- **Joystick:** move the pointer. It is the emulation of desktop mouse; The game doesn't get a command.
- **MangoHud does not appear with F12:** DXVK take `vkGetInstanceProcAddr` direct of `winevulkan.dll` (`Found vkGetInstanceProcAddr in winevulkan.dll`), so it does not go through the Khronos charger, which is the one that loads the MangoHud layer.
- **When you leave, you close the entire app:** Unity ends with `TerminateProcess` over your own process. The server sends SIGQUIT to all threads (`thread_signal unavailable thread=0024 sig=3`,...) and the title comes out (`process_exit method=_exit status=0`). It doesn't show up `PS4 guest module … exits`, so it didn't go through `ExitProcess`, it does end only the guest.

<a id="pale-moon-como-invitado-run-0002log"></a>


### Pale Moon as a guest (`run-0002.log`)

- Sail (start.palemoon.org, palemoon.start.me) and then the scout thread stops responding (`heartbeat_age_ms` up).
- There's no sign of thread in this run, so it's another cause.
- The log ends about 35 s later. Wine reports a critical section only stuck at 60 s, so you should wait more in the next test.

<a id="pendiente"></a>


## Pending

- W196: `TerminateProcess` of the process itself from a guest ends only to the guest.
- MangoHud with DXVK (or the HUD of DXVK).
- The command as game command (XInput over `scePad`), not as mouse.
- Pale Moon as a guest: repeat waiting at least 2 minutes.
- Windows.Gaming.Input does not see the command in `joy.cpl`: Your lists are empty. It depends on the arrival notices of devices, which do not run in this model of a process.
