<a id="w193-y-w194-un-juego-unity-con-direct3d-11-the-lost-forest"></a>

# W193 and W194: a Unity game using Direct3D 11 (The Lost Forest)

[English](HARDWARE_W194.md) | [Español](HARDWARE_W194-es.md)

W193: APP_VER 02.92, base W192. W194: APP_VER 02.93, base W193. The result of W192 is in `docs/HARDWARE_W192.md`.

<a id="el-juego"></a>


## The game

**The Lost Forest** (elifyener, MIT license): a 2D platforms made with Unity 2020.3 .3f1.
- It came down with user's permission from itch.io: `WindowsBuild.zip`, 25 525 677 bytes, SHA- 256 `37c7b937282efa9c526a6fd6b7fc01d808a6079391efc6e1ad849673270b081b`.
- It's in `.deps/games/lostforest/`. Don't pack.
- The exe and `UnityPlayer.dll` are x86 - 64.
- It was copied by FTP to `C:\users\orbis\Documents\TheLostForest` (165 files).

<a id="cambios"></a>


## Changes

- **W193, `tools/build-wine-hardware.py`:** `winhttp.dll` and `avrt.dll`, from the Wine host tree and without review, they go to `lib/wine/x86_64-windows` and `system32`. `UnityPlayer.dll` imports winhttp, and Unity loads avrt for its audio threads.
- **W194:** is added `jsproxy.dll`, which matters winhttp. Now the complete import closure of the game against the runtime of W193 was calculated, and it was the only one missing.

<a id="pruebas-físicas"></a>


## Physical evidence

**W192:** `UnityPlayer.dll` does not load (`Library WINHTTP.dll … not found`).

**W193:** `WINHTTP.dll` does not load (`Library jsproxy.dll … not found`).

**W194:** report `reports/wine-hardware-w194/physical/20261104T104654Z/`. User response: "Falla."
- **What I walked:**
  - the game loads as a guest within the explorer, with `PWGUEST load_end … error=0`;
  - Mono load (`mono-2.0-bdwgc.dll`);
  - DXVK creates the device with `Using feature level D3D_FEATURE_LEVEL_11_1`;
  - the audio output (`PWAUDIO level` is opened, without sound: peak = 0).
- **What fails:** does not create any presentation chain (there is no `PWDXGI`) and the window is not shown.
  - Since shortly after loading, the server has asked to stop the thread `004c` with SIGUSR1: `PWBOOT thread_signal unavailable thread=004c sig=10`, about 17 800 times.
  - Since W186, when the signal cannot be sent, the context order fails, but the order is repeated without end.
  - Monkey stops the threads (SuspendThread and GetThreadContext) for your garbage collector and for your own thread control. Without the signal, it doesn't make it, and the boot doesn't go forward.
- **The second opening of the game:** the user opened it a second time. That second instance in the same process started the Unity fault manager (`UnityCrashHandler64.exe`).

<a id="causa-y-lo-que-haría-falta"></a>


## Cause and what it would take

The console doesn't have `tkill` or `thr_kill2` (W064). Instead `pthread_kill` of libkernel does send a signal to a particular thread: `pw_wine_signals.c` already uses it for the own thread.

For GetThreadContext of another thread to work within the process it is necessary:
- a native TID record at `pthread_t`, updated when creating and finishing threads;
- that the server sends SIGUSR1 with `pthread_kill`;
- differ the suspension while the thread has locks on the Unix side of Wine.


It is also likely to be the cause of Pale Moon freezing the desk when running as a guest (W192, `palemooncopy.exe`): W184/W185 already showed that your hanging monitor uses contexts of other threads. It's not checked.

<a id="pendiente"></a>


## Pending

- The thread suspension with `pthread_kill` (above).
- Then again The Lost Forest: menu, input, sound and back to the desktop.
