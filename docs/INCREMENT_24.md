<a id="incremento-24-ui-de-wine-en-pantalla-con-win32u-y-un-driver-de-usuario-en-proceso"></a>


# increment 24: IU of Wine on-screen, with win32u and driver user in process

[English](INCREMENT_24.md) | [Español](INCREMENT_24-es.md)

**In the Linux fork of shadPS4, programs Win32 with windows run by Wine and are presented by `sceVideoOut`.** Two programs:

- a fixture of 64 bits: opens its window, paints it, checks its pixel, writes a `result.txt` identical to that of Windows native and comes out with 0, in three of three runs;
- **`explorer.exe /desktop=shell,800x600`, the Wine** desktop, which draws your task bar with the start button.

There is still no text (no sources) and no input. Hardware: pending.

| Fixture `gui-window64.exe` | `explorer.exe /desktop` |
|---|---|
| `reports/increment24/evidence/gui-window64.png` | `reports/increment24/evidence/explorer-desktop.png` |

The images are the pictures that Wine delivered to the presentation sink, stored by the sink itself within the emulator. It's not catch from the host window.

<a id="cómo-llega-una-ventana-a-la-pantalla"></a>


## How a window gets to the screen

1. **win32u para Orbis** (`tools/build-win32u-ps4.py`).
   - Collect the 47 units of the `win32u` Unix part, each with its exact Makefile recipe of Wine for Orbis.
   - Use your own overlay with two prospero-win patches (LGPL), adapted:
     - 0400: the driver of the user in process, `ps5drv.c`;
     - 0410: metrics without sources and desktop created by the server.
   - That driver reports a virtual monitor of 800 × 600, gives each window a surface of 32 bpp, composes the windows visible in a screen buffer and delivers it to `pw_wine_present()`.
   - The adaptation enables it with `__ORBIS__` and links the direct sink, because there is `dlsym` of the title.
   - The headers generated from IDL come from the host's Wine tree (`-idirafter`): they are independent of the platform.
2. **Link in the single ELF**. The objects of `win32u` are combined in one and their hidden symbols are local, as within their own `win32u.so`. Its `__wine_unix_lib_init` is recorded in the static table of Unix libs (`pw_wine_unixlibs.c`), which now also supports initialization points: they are called once per process, as the builder of a `.so`.
3. **Sink of presentation** (`platform/ps4/pw_wine_sink_ps4.c`).
   - Scale and focus each picture on one of two linear buffers of 1280 × 720 in direct memory, recorded in `sceVideoOut`, and makes `sceVideoOutSubmitFlip`.
   - It records the hash of each box and saves in `/data/frames` each box with new content (up to 24) as BMP, so that it can be verified outside the emulator.
   - `pw_wine_next_input` still has no source of events.
4. **IU closure PE64** (`tools/stage-wine-gui.py`).
   - Copies of the Wine host tree (without patches) the 52 modules that matter the fixture and `explorer.exe`, directly or transitively.
   - The Wine PCs compiled with mingw resolve their `DELAYIMPORTS` running, without the ay-import directory; For those you read the `Makefile.in`.
   - `bcrypt`, `hid` and `msacm32` are not compiled on that tree and are recorded as unsolved.
5. **Boot y runner**.
   - `--wine-exe` and `--wine-arg` choose the program within the prefix prepared.
   - `--wine-gui` copy the hash-verified closure and put the fixture in `C:\orbis`.
   - The report of each Runs brings the presented pictures, the BMP and how many pixels have the color of the fixture.

The 64 bit PE code is native to the host, so this IU does not use the translator. The programs of 32 bits continue to go through wowprospero, as in the increment 23.

<a id="correcciones-que-hicieron-falta"></a>


## Corrections required

- **Writing in image sections of file mapped** (overlay of Wine). The fork retains the policy that unwritten a file open only reading, even if the mapping is private; The increment 21 left the enlargement by `mprotect` as a proven path. Wine writes the direct relocations in its copy-on-write sections, so the relocations of `shcore.dll` failed in the only section that was mapped from the file. In `map_file_into_view`, a private mapping with writing now makes that `mprotect` explicit. If it fails, it is recorded `PWBOOT private_file_write_blocked`.
- **`getrusage` (fork 0017)** was a stub which `explorer` he invoked. In amd64, `struct rusage` has the same layout in FreeBSD and Linux, so they map `RUSAGE_SELF`, `RUSAGE_CHILDREN` and `RUSAGE_THREAD` to the host's call. An unknown destination returns EINVAL, a zero EFAULT buffer, and other ENOSYS hosts.
- **Reference of Windows of the fixture**. The fixture sets the size of the client area with `AdjustWindowRect` (464 × 280), because the edges depend on the theme. Windows 11 native `painted=1;pixel=8c3c14;client=464x280` and comes out with 0 (`reports/increment24-windows-reference/`).

<a id="resultado"></a>


## Result

|Runs|Result|
|---|---|
| `gui-window64.exe`, fork |**passed** 3 of 3: `result.txt` identical to Windows, output 0; a presented picture has exactly 464 × 280 pixels of the color of the client area|
| `gui-window64.exe`, shadPS4 oficial | blocked |
| `explorer.exe /desktop=shell,800x600`, fork |The desktop is presented with your taskbar (more than 15.000 pixels of the bar color in the last box), without stubs access violations. It runs to the runner's timeout, as it corresponds to a desk.|

`explorer.exe C:\` (folder browser) starts, loads `shell32` and `comctl32` and draws, but falls: without processes there are `rpcss` nor service manager, and the increment prefix 15 did not register the COM classes of the navigation panel because it was initialized with a minimum closure. It's a next job.

<a id="validación"></a>


## Validation

`tools/check-increment24.py` exige:

- the three runs of the fixture against the reference of Windows and the picture with the complete client area;
- the task bar in the last table of `explorer` and no stub;
- that `console32-bare.exe` by Wine (increment 23) continues to pass;
- the control without a provider WoW64;
- GS, the 7 signals, `wine-memory` (now 12 checks, with `getrusage`), `segments`, `services`, the preflight and the empty prefix;
- `exceptions` with your known detail;
- the contracts of mmap and file mapping, and the matrix of the increment 18.

It exports the evidence tables to PNG. `fork.lock.json` fix the commit `9ac99bb` with the patches 0001 to 0017.

<a id="reproducción"></a>


## Reproduction

With the tools of the increment 25, build first FreeType by `python3 tools/build-freetype-ps4.py` before `build-win32u-ps4.py`. The absence of text described above corresponds to the historical evidence of 24.

In Ubuntu 22.04/WSL, in this order:

```sh
python3 tools/build-shad-linux.py --reuse-configure --jobs 12
python3 tools/build.py --with-wine-platform
python3 tools/prepare-wine-boot.py
python3 tools/build-wine-ps4.py --boot --all-unix
python3 tools/build-wine-ps4.py --boot --server
python3 tools/build-wowprospero-ps4.py
python3 tools/build-win32u-ps4.py
python3 tools/stage-wine-gui.py
python3 tools/link-wine-boot.py
python3 tools/run-linux-wine.py --fork --prepared-prefix reports/increment15/prefix-package --wine-gui --wine-exe 'C:\orbis\gui-window64.exe'
python3 tools/run-linux-wine.py --fork --prepared-prefix reports/increment15/prefix-package --wine-gui --wine-exe 'C:\windows\explorer.exe' --wine-arg /desktop=shell,800x600
python3 tools/check-increment24.py
python3 tools/check-increment24.py --verify-only
```

<a id="qué-no-está-probado-y-próximo-hito"></a>


## What is not proven and next milestone

- **Text** Wine for Orbis is compiled without FreeType, so do not draw glyphs: no titles or labels. The next step is FreeType for Orbis and fountains in the runtime.
- **Entry**. No origin feeds `pw_wine_next_input`. The control (and keyboard and mouse where they exist) should be carried to driver, as it does prospero-win in PS5.
- **folder browser of `explorer`**. You need an initialized prefix with the complete set of DLL (COM records) and a policy for `rpcss` without separate processes.
- shadPS4 official, host Windows of the fork and hardware PS4.
