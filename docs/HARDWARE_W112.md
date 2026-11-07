<a id="w112-primer-runtime-dos-dentro-de-wine"></a>


# W112: first runtime DOS within Wine

[English](HARDWARE_W112.md) | [Español](HARDWARE_W112-es.md)

APP_VER 02.11. User-chosen priority: games DOS. W111 retains the acceptance of recursive renamed and erased; desktop and absolute calibration of CPU/GPU are still postponed.

Documents/smb.exe was identified as MZ MS-DOS/PKLITE, not PE Windows. SHA256 e58adb73373c214a0f4ae1f98fb7dde655095c338cb4121db3bd4abde6049db3. The game is not part of the distribution and is not modified by FTP.

<a id="implementación"></a>


## Implementation

DOSBox Pure of https://codeberg.org/schelling/dosbox-pure.git, revision ba6dcaee84aa2c22d709c3dfdacb7aca5ebc3042, fixed at dos.lock.json. Number PE64 with CPU normal interpreted (DISABLE_DYNAREC = 1), 4720 cycles. It is housed by means of doshost.exe, an own libretor front executed as a guest PE64 of the existing Explorer. XRGB8888 video by GDI, without Vulkan. It does not add instructions to the translator WoW64 or changes to the emulator.

WFM retains its broker WM_COPYDATA: Explorer classifies .exe MZ and .com, preserving PE and formats Windows NE/LE/LX. For DOS open doshost.exe with the route as an argument between quotes, on the opening thread of Explorer. FindWindow and a mutex prevent two simultaneous DOS hosts. EXE Windows and text associations continue to be ShellExecute usual.

The front receives keyboard and control events already translated by Wine: flechas/D-pad, Enter/tri angle, Escape/cuadrado, click izquierdo/cruz = Space, click derecho/c circle = Ctrl. It does not implement mouse DOS or configuration interface. One window DOS at a time; performance and compatibility of pending games.

stereo PCM reaches a native bridge AudioOut by a private class NtQuerySystemInformation 0x50444155, ABI of 48 bytes. Token by opening, size validation/tasa/bloques And mutex. Actual output from 256 frames a 48 kHz, with sample-and-hold conversion from the core rate. Do not create another worker audio. The errors are recorded and the window indicates "without audio" if it fails; delivering samples to the bridge does not show that the console emits audible sound.

The kernel keeps its overlay of saved in C:\users\orbis\AppData\Local\OrbisDesk\DOS. Persistence pending to be checked. When the window is closed it is called retro_unload_game (core shutdown) and retro_deinit before closing AudioOut. The DLL remains loaded; The callbacks are replaced at the next opening. Cierre/reapertura require physical proof.

GPL- 2.0 -or-later license: license and corresponding source of the kernel, front, audio bridge and recipe travel in system32 along with the runtime: DOSBox-Pure-LICENSE.txt, DOS-runtime-README.txt and DOS -runtime-source.tar.gz.

<a id="construcción-reproducible-en-wsl"></a>


## Reproducible construction in WSL

```sh
python3 tools/build-dos-runtime.py
python3 tools/build-explorer-hw.py
python3 tools/build-telemetry-ps4.py
python3 tools/build-wine-hardware.py
python3 tools/upload-hardware.py --build W112 --host 192.168.68.104 --timeout 60
```

The recipe uses the existing lvm-mingw in ~ / vk-h0/llvm-mingw for the static core and mingw GCC for the front. It includes <new> explicitly for std:: nothrow with libc + +. --reuse-core allows to rematch only the front if they match revision, recipe and hash of the previously compiled core.

The patch's idempotency guard GPU was also corrected: it was looking for a comment of a line but inserted a multi-line. The exact source tested was restored and the library GPU was verified with the same SHA256 of W111: a27136aa640b4e8da90b0ce6af9fd7bd34e6ef16f67c41a790b28e3eaf276849.

<a id="evidencia-y-aceptación"></a>


## Evidence and acceptance

Core, front, Explorer, Unix system, bridge AudioOut and ELF/PKG. No local matrix at user's preference. This does not apply DOS. Manifesto: out/wine-dos/manifest.json and out/wine-hardware-w112/manifest.json. Articles and recipes archived in reports/wine-hardware-w112/release-w112.

Install W112, open Documents/smb.exe from WFM and observe image, teclado/mando and audio. Close the window, check Start/WFM and reopen the game. If you fail, keep the fault: the logs PWDOS/PWDOSAUDIO separate dispatch, DLL loading, init/load, first frame, real audio and shutdown. A frame hash does not confirm playability; an opening log of AudioOut does not confirm audibility. Compatibility DOS validated in PS4: slope.
