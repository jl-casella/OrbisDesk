<a id="w179-navegador-con-bcrypt-fase-9-directinput-y-aspecto-xp-en-lunanoir-fase-7-sonda-usb-fase-10-e-íconos"></a>


# W179: browser with bcrypt (phase 9), DirectInput and XP appearance in Luna/Noir (phase 7), USB probe (phase 10) and icons

[English](HARDWARE_W179.md) | [Español](HARDWARE_W179-es.md)

APP_VER 02.78. Base W178.

<a id="íconos-de-programs--internet"></a>


## Program icons → Internet

The new access of W177 had no icon. The copy of Pale Moon is from the user and may not be, and `iexplore.exe` and the test programs do not bring an icon resource.

`tools/make-icons.py` draw three more icons, just like those of Graphics Tools (16, 32 and 48 px), and `tools/make-start-menu.py` it assigns them:
- `palemoon.ico`, a clear growing moon on a dark blue disk: Pale Moon and Pale Moon (no JIT);
- `web.ico`, a blue balloon with meridians and parallels: it is drawn, but without access to use it, because the one of the Internet Explorer is removed (see below);
- `webview.ico`, a window with the balloon inside: WebView test (64 -bit) and (32 -bit).

The four above icons are identical (same hash). To build: `tools/make-icons.py` and `tools/make-start-menu.py` before `tools/build-wine-hardware.py`.

<a id="sonda-de-discos-usb-fase-10-sesión-de-red"></a>


## USB disk sound (phase 10, network session)

`platform/ps4/pw_wine_fs.c`, `usb_probe`, is called once at the end of `pw_wine_fs_drive_mounts`. Before giving letters to USB disks you have to know if the app, which runs on the sandbox (W030), sees `/mnt/usb0..7` and if you can write there.

- **What does it record?:** a line `PWUSB slot=N stat=… errno=… dir=… entries=… list_errno=… first=… statfs=… version=… type=… rdonly=… from=… on=…` by slot.
  - `slot=0` always comes out; the other slots, only if they exist.
- **How to read:**
  - `stat=0 dir=1 entries>=0`: the app sees the disk.
  - `stat=-1 errno=2`: does not exist for the app (sandbox, or no disk).
  - `errno=1` or `13`: permission denied.
  - `version=20030518`: confirms the format of `statfs` that is read.
  - `type=`: the file system (`exfatfs` or `msdosfs`).
  - `rdonly=1`: only for reading.
- **Writing test**, only if at the root of the disk there is `orbisdesk-write.txt`:
  - if it could be written, it is `write_test open=0 errno=0 written=46`, and the file ends with "orbisdesk W179: write test from the console";
  - If the file does not exist, it comes out `write_test=skipped`.
- **What's the touch of the disk:** nothing more. Just list the root and read the file system type.

The unit letters, the hot connection and the execution from the disk go in W180, as the probe says.

<a id="wine-configuration-en-control-panel-ícono-de-game-controllers"></a>


## Wine Configuration in Control Panel; Game Controllers icon

At the request of the user:
- **Wine Configuration** from System Tools to submenu **Panel Control** Start menu.
  - That submenu lists the shell's Control Panel folder, which only shows apps (`*.cpl` in `system32`), and winecfg is a program. This is why an applet of 64 bit, `fixtures/win32/winecfgcpl.c` is added with the winecfg icon (`winecfgcpl.rc`, `programs/winecfg/winecfg.ico`).
  - When opening it, it starts `C:\windows\system32\winecfg.exe`; If you can't, show the error code.
  - It compiles it. `tools/build-wine-hardware.py` how `system32\winecfg.cpl`.
  - The old System Tools access comes out with `obsolete_files`.
- **Game Controllers** (System Tools) uses the `joy.cpl` icon. `tools/make-start-menu.py` accepts a fifth field with the icon.
  - Compared to the previous output, only those two accesses change: one comes out and the other changes the icon.

<a id="sin-acceso-a-internet-explorer"></a>


## No Internet access Explorer

The "Internet Explorer" is removed from Programs → Internet (`tools/make-start-menu.py`).
- `iexplore.exe` records your class as a local COM server. That needs marshaling of the class factory and rpcss, and neither of them exists in a single-process title. In W177 he ended up with 1 code without showing anything.
- The embedded control, which covers MSHTML for other programs, continues with the WebView tests.

<a id="navegador-bcrypt-y-clausura-de-gecko-fase-9-sesión-del-navegador"></a>


## Browser: bcrypt and Gecko closing (phase 9, browser session)

<a id="qué-pasó-en-w177"></a>


### What happened in W177

Report: `reports/wine-hardware-w177/physical/20261103T211906Z/`. Fixture result: `build/w177-webview-result.txt`.

1. **`webview64.exe`:** `ole`, `create` and `activate` gave `0x00000000`. The three navigations (`local`, `remote`, `back`) were in `ready_state=1` not completed in 30 s.
   - Cause (`run-0001.log`, line 1386 onwards): `xul.dll` of Wine Gecko did not load. It matters `wintrust.dll`, which matters `crypt32.dll`, which matters `bcrypt.dll` (it matters also `ncrypt.dll`). `bcrypt.dll` is not in the prefix in either view.
   - After: `mshtml:create_document_object Failed to init Gecko, returning CLASS_E_CLASSNOTAVAILABLE`.
   - The import review of W177 looked at a single level: `wintrust` was, but not what `wintrust` needed.
2. **Internet Explorer** (`run-0002.log`, lines 1060 - 1103: It starts as a guest, but `IEWinMain` records `CLSID_InternetExplorer` as a local server (`CLSCTX_SERVER`).
   - That's why ole32 has to serialize the class factory. It fails because there is no proxy/stub of `IServiceProvider` (`Failed to create ifstub, hr 0x80004002`), and it would also need rpcss (`start_rpcss Failed to open service manager`).
   - Neither exists in the model of a process. `iexplore` ends with state 1.
   - Explorer shows the same serialization error when starting (line 844), and that was already happening before phase 9.
3. **Pale Moon:** was not on the console (there is `Program Files/Pale Moon` in `ftp-list.txt`). With the fate of the missing direct access, the shell passed the `.lnk` same to `CreateProcess`, which rejects it (`PWOPEN reject_title_replacement`). No on-screen messages.
   - Pale Moon also matters `wintrust` and `crypt32`: with the installed copy it would have failed as well as Gecko.

<a id="cambio"></a>


### Change

|File|What are you doing?|
|---|---|
|`tools/build-bcrypt-x64.py` (new)|Compile `bcrypt.dll` of 64 bits, which the Wine tree of the host never linked. The `libsymcrypt.a` x86_64 of that tree has objects of an old build with clang, and clang before 19 disables the code by platform (`SYMCRYPT_IGNORE_PLATFORM`). That's why `cpuid.o` was empty and the link failed (`SymCryptDetectCpuFeaturesByCpuid`). The builder runs the exact commands of `compile_commands.json` with the Makefile compiler (`x86_64-w64-mingw32-gcc`), with output in `build/bcrypt-x64`, and then the file and link rules of the Makefile. He doesn't write on the host tree or change code. The crypt cryptography is SymCrypt (PE code), so it doesn't depend on a Unix side.|
| `tools/stage-mshtml-hw.py` |Add `bcrypt` in the two views (the 64 bit one leaves the new build). It also adds the DLL that `xul.dll` and `mozglue.dll` load in deferred: `psapi`, `winspool.drv`, `rasapi32`, `rasdlg` and `dbghelp`. One of those missing makes an exception on his first call. By closing it also enters `compstui` (from winspool). `winspool.drv` without Unix side equal load (your `DllMain` returns TRUE) and your printing calls fail.|
|`tools/check-web-closure.py` (new)|Walk all the imports, transitatively, on the built runtime. Search in the order of the charger: program folder, `system32` / `syswow64` and build folder. It covers Wine Gecko (both), mshtml/ieframe/jscript/iexplore (both views), fixtures and, optionally, a program folder such as the copy of Pale Moon. Deferred imports go separately. With `--staged` add the manager's output to each view, to review an arrangement before the build. Finish with 1 if there's anything missing.|

| `tools/build-wine-hardware.py` |One line: `tools/build-bcrypt-x64.py` in `source_hashes`. The W177 block already copies everything that lists `out/mshtml-hw/manifest.json`.|
| `tools/make-start-menu.py` |Without direct access "Internet Explorer" (see below). It changes the main session.|

<a id="verificación-sin-consola"></a>


### Console-free verification

- `build-bcrypt-x64.py` He ran and left. `out/bcrypt-x64`: 126 objects, 4,5 minutes. The `bcrypt.dll` is PE32+ of 2,9 MB, It matters only Advapi32, kernel32, ntdll and ucrtbase, and exports 56 functions `BCrypt*`.
- `stage-mshtml-hw.py` already ran and left `out/mshtml-hw`: 17 modules of 64 bits and 18 of 32 bits, no unsolved matter. The same 1770 registration keys, no sealed values replaced.
- `check-web-closure.py --staged out/mshtml-hw/x86_64-windows out/mshtml-hw/i386-windows build/wine-hardware-w178/runtime <Pale Moon 35.0.3>`: zero missing imports and zero missing deferred imports. Cover Gecko x86_64 (54 modules), Gecko x86 (55), mshtml in both views (29 and 29), fixtures (38) and Pale Moon (134.
- About W177 without the arrangement, the same check gives `bcrypt.dll` missing in all three cases, which is the error that the console gave.

<a id="construcción-orden"></a>


### Construction (order)

1. `python3 tools/build-bcrypt-x64.py` → `out/bcrypt-x64` repeat it only if the builder changes)
2. `python3 -I tools/stage-mshtml-hw.py` → `out/mshtml-hw`
3. `python3 tools/build-wine-hardware.py`
4. `python3 -I tools/check-web-closure.py build/wine-hardware-w179/runtime`: it has to end with 0.

Gecko doesn't change, so `stage-wine-gecko.py` you don't need to.

<a id="internet-explorer-no-soportado"></a>


### Internet Explorer: not supported

`iexplore.exe` cannot work in the model of a process and its direct access is from the Start menu.

- **Cause:** `IEWinMain` (`dlls/ieframe/iexplore.c` records `CLSID_InternetExplorer` with `CLSCTX_SERVER`, which includes local server (other process). For this, it is a way to increase the class factory, and it needs the proxy/stub of `IServiceProvider` and then rpcss, the service of the Wine PRC. There are neither of them here: there are no separate processes or service managers.
- **Results in W177:** `Failed to create ifstub, hr 0x80004002`, `failed to register CLSID_InternetExplorer: 80004002`, `start_rpcss Failed to open service manager`, and the program ends with state 1.
- **What continues to work:** IE control embedded in a program (WebView test). It creates the class in process and does not go through `IEWinMain`.
- **No attempt was made:** change `ieframe` to record only in process. It would replace the `ieframe.dll` that also uses the embedded control.
- `iexplore.exe` is still installed, because the associations of `mshtml.inf` (`.gif`, `.jpg`, `.htm`...) They name him. Open one of those double-click files fails as does the direct access.

<a id="prueba-física"></a>


### Physical test

1. **WebView test (64 -bit) and (32 -bit):** is expected `local complete=yes`, `title "orbis-webtest"`, `es5 "es5-ok"` and the visible page. With network: `remote complete=yes` with title.
2. **Pale Moon:** before, copy the `palemoon` folder from `.7z` a `wine-prefix/drive_c/Program Files/Pale Moon/`. Then follow the steps of `HARDWARE_W177.md`.
3. **In the log:** it does not have to appear `Library bcrypt.dll … not found` or `Failed to init Gecko`.

Without the copy of Pale Moon on the console, its direct access does nothing visible: the shell passes the `.lnk` to `CreateProcess`, which rejects it (`PWOPEN reject_title_replacement`).

<a id="no-verificado"></a>


### Not verified

- No W179 was tested on the console.
- It was not tested if Gecko's code calls for bcrypt functions that need more than SymCrypt.
- `make -n -B` (used to read the symcrypt commands) regenerated `config.status`, the Makefiles and `compile_commands.json` of the host tree with the same configuration arguments, and stepped `config.log`. Make redo the makfiles even if it is used `-n`. The lines that were compared to the Makefile (CC, symcrypt, bcrypt, FFMPEG) remained the same, and `include/config.h` did not change.

<a id="directinput-y-aspecto-xp-fase-7-sesión-de-accesos-directos"></a>


## DirectInput and look XP (phase 7, session of direct accesses)

<a id="1-directinput-con-el-mando-de-la-ps4-fase-7"></a>


### 1. DirectInput with the control of PS4 (phase 7)

- The DirectInput of Wine finds joysticks only by HID (`dlls/dinput/joystick_hid.c`), which a title of PS4 has no game DirectInput I saw a command, and the DirectInput tab of `joy.cpl` was empty.
- `tools/build-dinput-hw.py` (new) compiles dinput and dinput8 (x86_64 and i386) with a new device, `joystick_pad.c`. It's own code, not prospero-win.
  - Shows the XInput 0 driver (the control, from W178) as a gamepad with the provision of driver Xbox 360 of Windows:
    - X/Y: left stick; Rx/Ry: right stick; Z: the two triggers together;
    - 10 buttons: A B X AND LB RB Back Start LS RS;
    - the cruise as POV.
  - It is presented as "Controller (XBOX 360 For Windows)," VID/PID 045e: 028e.
  - Read XInput every 8 ms in the input thread of dinput (a timer like `read_event`), and also in `Poll()`.
  - The axles respect the range, the dead area and the saturation that the program sets, with the same calculation as `scale_axis_value` of `joystick_hid.c`.
  - No force feedback: the command vibrates by XInput.
- `dinput.c`: the control first appears among the game drivers (`EnumDevices`) and is created by your instance or product GUID.
- Read the command by DirectInput reads XInput, so activate the game mode of `hw_pad.c` just like a XInput game.
- `tools/build-wine-hardware.py` copy the four DLL folders to build and to `system32` / `syswow64`. The dinput of 64 bits was not in the prefix.
- No warning when compiling. The imports of the four DLL are already in the prefix.

<a id="2-luna-y-noir-más-parecidos-a-xp-y-a-royale-noir"></a>


### 2. Moon and Noir more like XP and Royale Noir

User's request after testing W177: Moon looked too much like Aero. He wanted the full edge and title bar in blue XP, the blue task bar and the green Start button; in Noir the same, but orange.

- `tools/build-msstyles-hw.py` (already in W178):
  - **Moon:** full title and edge blue XP (0,84,227), and blue grey (122,150,223) in inactive windows.
  - **Noir:** title and orange edge (232,112,24), and dark grey in the inactive.
  - Three new pieces with XP shell classes:
    - `[Taskbar.BackgroundBottom]`: blue XP / black bright;
    - `[Start::Button.Pushbutton]`: green / orange, square to the left and rounded to the right;
    - `[TaskBand::Toolbar.Button]`: the buttons in the windows, with the darkest active.
- `tools/build-explorer-hw.py` (`tools/taskbar-theme-w179.patch.py`):
  - Explore uxtheme load in running time and open "Taskbar" in the bar window;
  - if the style has it, draw from the style the background, the Start button (`SetWindowTheme "Start"`, Button class) and the window buttons (`SetWindowTheme "TaskBand"`, Toolbar class);
  - the text goes in the color of the style: "start" in bold and italic, and the watch on the color of the bar;
  - with `WM_THEMECHANGED` (choose another style in winecfg) recharge;
  - with Aero or without style the classic drawing is left.
- `tools/build-win32u-ps4.py` (`tools/flat-frame-w179.patch.py`), on the window edge (`defwnd.c` paint:
  - if the edge color of the style is different from the button face, the whole edge, including the 3D edges, is drawn in full in that color;
  - with the usual dark scheme (edge equal to face) does not change anything.

What Wine does not draw with the style: the buttons to minimize, maximize and close remain the classic, without the red X of XP.

Check without the console: the modified explorer compiles and links without warnings, and `defwnd.c` modified compiles without warnings with the recipe of win32u.

<a id="prueba"></a>


### Test

1. Game Controllers → tab DirectInput: "Controller (XBOX 360 For Windows appears," and its axes, buttons and POV move.
2. A game DirectInput (for example, one of 32 bits that requests joystick) responds to the command, without clicks of the emulation.
3. winecfg → Moon:
   - full edge and title in blue;
   - blue task bar, green start, blue window buttons (the darkest asset), blank watch.
4. The same with Noir: orange and black.
5. "(No theme)" and Aero: taskbar and edges as before.

Risks:
- List DirectInput devices reads XInput, so it activates the game mode for a second even if the program does not use the command.
- The dinput device is new code: a game with a rare data format can show something rare on the axes; The log of `dinput` would say so.
- The buttons of the stylish task bar are drawn with the small icon of the window class. A window that only has an icon set with `WM_SETICON` appears without an icon, because reading it would ask for a message to its thread.

<a id="prueba-física-1"></a>


## Physical test

Report: `reports/wine-hardware-w179/physical/20261103T221219Z/`. The user tested with a USB drive connected and with his copy of Pale Moon.

- **DirectInput:** Game Controllers' DirectInput tab shows the control.
- **Browser:** `bcrypt` worked, because `xul.dll` now load. The following block is `crypt32`:
  - `load_builtin_unixlib failed to load .../x86_64-unix/crypt32.so: Dynamic loading not supported`;
  - then a Unix call without a table (`c0000005`, reading 0x8);
  - `Initialization of crypt32.dll failed`, and xul is downloaded.
  - WebView test 64 is blank (`Failed to init Gecko`) and Pale Moon says "Could not load XPCOM." It's going to W180: the Crypt32 Unix side as a static library.
- **Wine Configuration:** the applet starts `winecfg.exe` as a guest from `rundll32`. When `rundll32` ends, its output also ends the winecfg thread before it draws. In W180 the applet is waiting for that thread.
- **USB:** `PWUSB slot=0 stat=-1 errno=2` in both games, and no other slot. `/mnt/usb0` does not exist for the app: it can be the sandbox, or the console rides the disk elsewhere. W180 adds a wider probe of `/mnt`.
- **SuperMarioKart with the control** (`20261103T221722Z/run-0003`: it didn't work; In the run the left stick moved the cursor.
  - The game loads `DINPUT.dll`, and when creating DirectInput it loads `xinput1_4` (`joystick_pad`). `PWPAD game_mode=1` in the line 2218 and `game_mode=0` in the 2825, about a second later.
  - The enumeration read the command once and then no one read it anymore. The game does not acquire or consult the joystick: you can use only the keyboard, read the command by another API (`joyGetPosEx` winmm) or ask that it be chosen in your options.
  - He's going to the direct access session for W181.
