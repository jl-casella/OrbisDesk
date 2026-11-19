# Wine Mono: .NET programs

[English](WINE_MONO.md) | [Español](WINE_MONO-es.md)

## Why

PES 2014's `settings.exe` is an IL-only .NET program. Started from the desktop and alone, it stopped with `mscoree.dll not found, IL-only binary "settings.exe" cannot be loaded` (run-0121, run-0163). OrbisDesk shipped neither Wine's `mscoree.dll` nor a .NET runtime: both were in the list of modules left out (`tools/stage-wine-i386.py`, "needs Wine Mono, not staged").

## What the build adds

- [stage-wine-mono.py](../tools/stage-wine-mono.py) unpacks Wine Mono 11.3.0, the version the pinned Wine asks for (`dlls/mscoree/mscoree_private.h`). The archive is the upstream `wine-mono-11.3.0-x86.tar.xz`, pinned by SHA-256 in [product-assets.lock.json](../product-assets.lock.json); the digest matches the GitHub release asset. Despite its name it holds both runtimes, `bin/libmono-2.0-x86.dll` and `bin/libmono-2.0-x86_64.dll`, and the class libraries.
- The console's file system has no symbolic links, so the 156 links in `lib/mono` become copies of their targets. `support/` is left out: it holds the `.msi` helpers that Wine's `appwiz.cpl` runs when it creates a prefix, which this sealed prefix does not do.
- [build-wine-hardware.py](../tools/build-wine-hardware.py) copies the tree to `C:\windows\mono\mono-2.0`, the first place `mscoree` looks (`get_mono_path_local`), and Wine Mono's `COPYING` to `C:\windows\mono\licenses`. That adds about 275 MB to the runtime.
- `mscoree.dll` and `mscorwks.dll` are staged in both views, `system32` and `syswow64`.

## First hardware run (app version 04.09, run-0172)

`settings.exe` now found `mscoree.dll`, then faulted at its first instruction (`c0000005` at `0x1359e0`). An IL-only EXE's header entry is a jump through an import table that the loader never binds for such an image: Wine's `fixup_imports_ilonly` puts `mscoree`'s `_CorExeMain` in the loader entry instead. OrbisDesk's guest launcher called the header entry. It now takes the loader entry for an image with a .NET header and logs `PWGUEST ilonly entry` ([build-guest-hw.py](../tools/build-guest-hw.py)). Not yet checked on the console.

## Second hardware run (app version 04.20, run-0221)

Mono now starts: `PWGUEST ilonly entry 005359FE -> 7B72C150`, then `mscorlib`, `System.Windows.Forms` and the program's `Settings_b.dll` load, and WinForms creates its parking window. Two problems remained, one in `settings.exe` and one in the game, `pes2014.exe`.

### settings.exe: "Error creating window handle"

The program ended with `System.ComponentModel.Win32Exception: Error creating window handle` from `TextBoxBase.CreateHandle` in `Settings.Online..ctor`, right after two `PWFAULT ... address=FF665060 access=0`, each followed by `dispatch_user_callback ignoring exception c0000005`.

- Wine Mono's WinForms is Microsoft's. A `TextBox` is a superclass of `Edit`: WinForms takes the proc of `Edit` from `GetClassInfo` and passes it the messages it does not handle, with `CallWindowProc`.
- With visual styles, `Edit` is comctl32 v6's global class `6.0.2600.2982!Edit`. In the title's single process, explorer's 64-bit side had already registered it, with the proc of the 64-bit comctl32. The 32-bit comctl32 v6 registers it again when the class is looked up (`RegisterClassNameW`), and the server refuses: there is one class per name in a process.
- W239 gives a 32-bit thread the handle of such a proc instead of its address. `CallWindowProc` with that handle asks win32u for the procs (`NtUserCallWindowProc`); wow64win copies them into 32-bit fields (`win_proc_params_64to32`), so the 64-bit `0x7FF665060` arrived as `FF665060`, and user32 called it. The fault inside `WM_NCCREATE` made `CreateWindowEx` fail. W239 only covered the path where win32u calls the proc itself.

The fix is in [build-win32u-ps4.py](../tools/build-win32u-ps4.py):

1. When a 32-bit thread registers a global class that the 64-bit side registered with a 64-bit proc, the server still refuses it, but win32u keeps the 32-bit proc beside the 64-bit one. The 32-bit world's threads get it, as W236 does for user32's builtin classes. Log: `PWWOW win32u: global class L"6.0.2600.2982!Edit" is the 64-bit side's (proc .../...); 32-bit threads get .../...`.
2. A proc that is still 64-bit (a class only the 64-bit side has, such as W239's `Wine IME`) is never handed to 32-bit code through `CallWindowProc` or `DispatchMessage`: the thread gets its own `DefWindowProc`, the same default W239 gives in the other path. Log: `PWWOW win32u: 32-bit thread ... is 64-bit; its DefWindowProc instead`.

Window extra bytes stay those of the 64-bit registration, which are never fewer than the 32-bit control needs (comctl32's `Edit`: 8 bytes against 6).

`mscoree:LoadLibraryShim error reading registry key for installroot` is not fatal: without the `.NETFramework` `InstallRoot` key, the `.msi` key this prefix lacks, `LoadLibraryShim` loads the DLL by its bare name, and `fusion.dll` loaded on the next line.

### pes2014.exe: the image did not fit the legacy EXE window

`PWWOW image_not_at_base preferred=0x400000 size=0x2050000 status=0xc0000018 occupied=0x23f0000+0xc3000 prot=0x800021`, then the `base_taken` message box.

- The game has no relocations, so it needs exactly `[0x400000, 0x2450000)`. W246 keeps placement-free allocations of the title out of `[0x400000, 0x2000000)`, 32 MiB, which was enough for Vice City but not for this image.
- The occupant is not left over from `settings.exe`. It is a read-only file view (`SEC_FILE`, `0x800000`) of 195 pages, the size of `locale.nls` (794,914 bytes), next to the 32-bit world's process heap at `023D0000`. The 32-bit world maps both when it starts, just above `0x2000000`, and keeps them while the title runs. The view was already there in run-0169, run-0171 and run-0178, where PES 2014 was the first 32-bit program of the title. Every PES 2014 start in the world in the W303 logs (run-0100 to run-0221) and in W261's run-0011 failed the same way; most name this view, two an allocation at `0x2200000`, in the same range.
- The heaps that `settings.exe` left (`02B10000`, held by `mscoree.dll`) are above the game's range and played no part.

The fix is in [build-wow64-world-ps4.py](../tools/build-wow64-world-ps4.py): the window is now `[0x400000, 0x8000000)`, 124 MiB of image, still below the usual DLL base `0x10000000`. The world's heap and its `locale.nls` view then land above it. The relaunch through `base_taken` stays for an image that still finds its base taken.

### Console test (after 04.21 is built and uploaded)

1. From the desktop, open `E:\PC\PES 2014\settings.exe`. Expected: the settings window with its tabs and text boxes. In the log: `PWWOW win32u: global class ...Edit... 32-bit threads get`, and no `PWFAULT` at `FFxxxxxx` and no `Error creating window handle`.
2. Change a setting, save, close `settings.exe`.
3. Without restarting OrbisDesk, open `E:\PC\PES 2014\pes2014.exe`. Expected: no `image_not_at_base preferred=0x400000 size=0x2050000` line and no message box about the same memory address; the game loads in the desktop's 32-bit world (`PWGUEST load_end app=...pes2014.exe module=00400000 error=0`). What the game does after its own startup checks is not part of this fix.
4. Close the game and open `settings.exe` again, to check a second start after a guest's end.
5. Fetch the logs with `tools/fetch-hardware.py`.

## Third hardware run (app version 04.22, run-0224)

`settings.exe` opened its window, with its tabs, and closed with exit code 0. The log shows the 04.21 fix at work for `Edit`, `Button`, `Static` and `tooltips_class32`.

### settings.exe: symbols instead of text

The title bar, the tab names and the resolution list (`(1280x720) 16:9`) were readable. Every group label, radio button, check box and the `OK` and `Cancel` buttons showed symbols instead of letters. The texts themselves were right: `PWTEXT` shows `Quality`, `High`, `Screen Mode`, `XInput`, `OK` and `Cancel`.

- The readable texts are drawn by native controls (the tab control, the combo box) with the handle from `Font.ToHfont`. Its character set is the one of the font GDI+ actually picked, ANSI for Tahoma.
- The broken texts are the ones WinForms draws itself (labels, group boxes, buttons, radio buttons and check boxes in the standard style). WinForms builds its own `LOGFONT` for them with the `Font`'s `GdiCharSet`. The program was made on Japanese Windows: one label is in Japanese, and the designer gives such a form's fonts charset 128 (Shift-JIS).
- No font in the runtime covers that charset: it has Tahoma, Tahoma Bold and Marlett, and no fontconfig. Wine's font mapper then drops the charset filter and takes the first family in name order, Marlett. Marlett is a symbol-only font (its code page range is only the symbol bit), so each letter became one of its window glyphs.

The fix is in [build-win32u-ps4.py](../tools/build-win32u-ps4.py) (`font.c`): in that fallback without a charset filter, a face whose only code page is the symbol one is skipped unless the request asks for `SYMBOL_CHARSET`. Windows' mapper does not give a symbol font to text either. A request that names Marlett still gets it. If only symbol fonts exist, they are still used. Log, at most eight times: `PWFONT L"..." charset 128: no font has its charset; not the symbol font L"Marlett"`.

The Japanese label stays boxes: the runtime has no Japanese font. Latin text in such a program now uses Tahoma.

### pes2014.exe

`pes2014.exe` now loads at `0x400000` in the desktop's 32-bit world. It then shows its own message: the game copy needs a `rld.dll` that is not in its folder (`c0000135`). That file belongs to the user's copy of the game, not to OrbisDesk, and OrbisDesk does nothing about it.

### Console test (after 04.24 is built and uploaded)

1. Open `E:\PC\PES 2014\settings.exe`. Expected: group labels, radio buttons, check boxes and the `OK` and `Cancel` buttons in readable Latin letters. The Japanese label may stay boxes. In the log: `PWFONT ... charset 128: no font has its charset; not the symbol font L"Marlett"`.
2. Check the things that use Marlett on purpose: a window's close, minimize and maximize buttons, a scroll bar's arrows and a check mark in a menu still show their symbols.
3. Change a setting, press `OK`, open `settings.exe` again and check that the setting was kept.
4. Fetch the logs with `tools/fetch-hardware.py`.

## Limits

- The fake .NET Framework files and registry keys that the `.msi` installs are absent. A program that checks the registry for an installed .NET Framework version before it starts may still refuse to run.
- `settings.exe` ran from start to end on the console in run-0224 (exit code 0). Saving a setting has not been checked yet.
- The runtime has no font for Japanese, Chinese or Korean. Text in those scripts shows as boxes.
- A 64-bit thread that uses a global class registered first by the 32-bit world (the reverse of the case above) is not handled.
