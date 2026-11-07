<a id="mando-como-gamepad-hid-stack-hid-de-wine-dentro-del-proceso"></a>


# Command as a HID gamepad (Wine HID stack within the process)

[English](HARDWARE_mando-hid.md) | [Español](HARDWARE_mando-hid-es.md)

Status: compiled and partially linked without the console. It's still packing and physical evidence. The previous analysis is in `docs/HARDWARE_mando-juegos-analisis.md`.

<a id="problema"></a>


## Problem

- The Lost Forest (Unity 2020.3, classic input) does not see the command even though XInput has been working since W178.
- Unity discovers controls only by HID:
  - takes the raw input list;
  - if a name contains `IG_`, it is associated with a XInput slot;
  - then open it (`CreateFileW`) and ask for your HID data.
- In Orbis there was no HID device: winebus, hidclass and winedevice do not run in a single process without service manager.

<a id="diseño"></a>


## Design

It runs the HID stack of Wine within the process, as it would winedevice.exe. The only thing that's changed from Wine is `ntoskrnl.exe`.

|Piece|What are you doing?|
|---|---|
| `native/pwhidhost.c` → `pwhidhost.dll` |Explorer the load when the desk is finished. A thread does the same thing as `ServiceMain` of winedevice: it runs `wine_ntoskrnl_main_loop` (the IRP loop) and, when the administrator PnP is ready, calls `ZwLoadDriver` of winebus. Before you create the service key `xinput` (winexinput.sys) if you are missing. The prefix was set up in a host without XInput, so it doesn't have it, and Setudaddy can't create it without SCM.|
| `ntoskrnl.exe` (overlay, `tools/build-hidstack-hw.py`) |3 revisions. (1) `open_driver`: without service manager, accept the driver from your registration key, with the same type control (driver of kernel). (2) `set_service_status` does nothing without service handle. (3) The IRP loop marks the event `PwNtoskrnlPnpReady` after `pnp_manager_start`.|
| `winebus.sys`, `winehid.sys`, `winexinput.sys`, `hidclass.sys`, `hidparse.sys` |Of the fixed build, no change.|
| `native/winebus_orbis.c` |Unix side of winebus. It is compiled instead of `bus_sdl.c`, so the PE side of winebus calls its `sdl_bus_*` unchanged. It creates a single device: a Xbox control 360 with cable (045e: 028e), with the layout of `hid_device_add_gamepad` (that of a mapped control of SDL) and vibration (`hid_device_add_haptics`). Read the state every 8 ms with `pw_wine_pad_peek` and send a report only when it changes. The vibration is going to `pw_wine_set_rumble`. The physical force feedback effects return `STATUS_NOT_SUPPORTED` with a line `PWHID no force feedback`.|
| `native/hw_pad.c` |`pw_wine_pad_peek`: the same state as `pw_wine_pad`, but not counted as reading XInput. If I counted, the game mode would always be active, because the bus reads even if no one plays.|
| `platform/ps4/pw_wine_unixlibs.c` |Input `winebus.so` and a `pw_wine_pad_peek` weak ("no control") for ELF without `hw_pad.c`.|

Expected chain, same as in Linux:
1. winebus publishes the command with `is_gamepad`, so your compatible ID includes `WINEBUS\WINE_COMP_XINPUT`.
2. `winexinput.sys` creates two children: `&IG_00` (the one who sees the games) and `&XI_00` (the one with internal use of Wine).
3. Each child is installed with `winehid.sys` + `hidclass.sys`.
4. There is a HID interface that win32u is ready in raw input. win32u refresh the list every 2 and hidclass commands `WM_INPUT_DEVICE_CHANGE`.
5. Unity finds `IG_`, uses XInput slot 0 (the xinput of W178) and that turns on the game mode of `hw_pad.c` (`PWPAD game_mode=1`.

In addition:
- winebus creates its mouse and virtual keyboard (845E: 0001/0002), as in Linux. They appear on the raw input list and do not generate input.
- **DirectInput** (`tools/build-dinput-hw.py`): `joystick_hid.c` Sauté the HID gamepad of winebus (045e: 028e with path `&IG_` / `&XI_`). The command already appears as `joystick_pad.c` and is not ready twice.

<a id="archivos"></a>


## Files

- New:
  - `tools/build-hidstack-hw.py`
  - `native/winebus_orbis.c`
  - `native/pwhidhost.c`
  - `out/hidstack-hw/`, already built
- Edited:
  - `native/hw_pad.c` (`pw_wine_pad_peek`)
  - `platform/ps4/pw_wine_unixlibs.c` (input `winebus.so`)
  - `tools/link-wine-boot.py` (link `winebus-unix.o` with sha256 verification)
  - `tools/build-explorer-hw.py` (revision in `desktop.c`: `LoadLibraryW(L"pwhidhost.dll")`; if it fails, `PWHID pwhidhost.dll not loaded`)
  - `tools/build-dinput-hw.py` (revision in `joystick_hid.c`)
  - `tools/build-wine-hardware.py`: a block after dinput. Check the builder and the sources, and copy the modules to the builtin folder and to the prefix (drivers in `system32\drivers`, `ntoskrnl.exe` in `system32`) and `pwhidhost.dll` a `system32`.
- Already regenerated: `out/explorer-hw` (49 reviews) and `out/dinput-hw` (4 reviews).

Check without the console:
- everything compiles without warning;
- the Unix object exports only `pw_winebus_unix_call_funcs`;
- a partial link of `hw_pad.o` + `pw_wine_unixlibs.o` + `winebus-unix.o` + `xinput-unix.o` resolves `pw_wine_pad_peek`, `pw_wine_pad`, `pw_wine_pad_available` and `pw_wine_set_rumble` to `hw_pad.c` (`build/hidstack-hw/check.py`).

<a id="construcción-orden"></a>


## Construction (order)

1. `python3 tools/build-hidstack-hw.py` (already running; repeat if they change `native/winebus_orbis.c` or `native/pwhidhost.c`)
2. `python3 tools/build-explorer-hw.py` (already running)
3. `python3 tools/build-dinput-hw.py` (already running)
4. `python3 tools/link-wine-boot.py` (changes ELF: `winebus-unix.o` and `pw_wine_unixlibs.c`)
5. `python3 tools/build-wine-hardware.py` (compile `hw_pad.c` and copy the stack)

<a id="qué-mirar-en-el-log"></a>


## What to look at in the log

In order, if everything goes:
- `PWHID xinput_service created` (or `present`)
- `PWHID irp_loop start` and `PWHID irp loop running, ready event set`
- `PWHID driver ...\winebus from its service key (no service manager)`, and the same for `winehid` and `xinput`
- `PWHID pad bus init vid=045e pid=028e`
- `PWHID winebus load status=0`
- `PWHID pad device started`
- with a game using the command: `PWPAD game_mode=1`

Possible failures and their line:
- `PWHID pwhidhost.dll not loaded`
- `PWHID ntoskrnl load error=`
- `PWHID pnp_ready wait=` (the loop did not start)
- `PWHID driver ... no service manager; key error`
- `failed to create driver`
- `PWHID winebus load status=` other than 0
- `Failed to send event` (Ntoskrnl's WRNA): the notice to plugplay by RPC, which does not exist. It is expected and does not prevent anything.

<a id="prueba"></a>


## Test

1. Start normal: the desktop appears as before, and without a game the control remains mouse and keyboard.
2. Game Controllers:
   - the XInput tab is still on the move;
   - The DirectInput tab lists **a** only "Controller (XBOX 360 For Windows)."
3. The Lost Forest:
   - the control moves the character;
   - It appears `PWPAD game_mode=1` and the pointer does not move.
   - If you don't go, bring by FTP `C:\users\orbis\AppData\LocalLow\<empresa>\The Lost Forest\Player.log`: Unity writes there "Joystick connected" or error when opening the device.
4. SuperMarioKart (DirectInput) remains the same as in W179.

<a id="w198-resultado-y-corrección"></a>


## W198: result and correction

Reporte: `reports/wine-hardware-w198/physical/20261104T121658Z/` (`run-0001` a `run-0004`).
- The host started well: `PWHID xinput_service`, `irp_loop start`, `ready event set`.
- After: `PWHID winebus load status=0xc0000001`. The desk was jammed when it opened programs. W199 stopped copying `pwhidhost.dll`.

Two causes, both in `ntoskrnl.exe`:

1. **Double relocation of guests (freezing).**
   - `ntoskrnl` records with `LdrRegisterDllNotification` a callback relocating any **executable** loaded outside its base: in winefold the loader does not, and there they only load drivers.
   - In Orbis the programs are guest from the same process, and the guest loader already replaces them. `wfm.exe` loaded in `0x100110000`, its base is `0x140000000`, and it was relocated twice.
   - That's why the "truncated" pointers: `0x14023E040 − 2×0x3FEF0000 ≈ 0xC023E040`.
   - In `run-0002`, explorer (thread 0024) failed reading `0xC023E040` within a callback user and was left in a loop of `c0000258`. In `run-0001` the same thing happened to `rundll32`, with a jump to `0xC0221B30`.
   - **Correction:** the callback returns immediately if the image is not of native subsystem. So it only touches the drivers, and it doesn't change the guests' safety cookie either.
2. **`winebus` He didn't load. (`0xc0000001`).**
   - My way without SCM was only taken if `OpenSCManagerW` returned NULL. In this runtime, he returns a non-zero handle after `RPC_S_SERVER_UNAVAILABLE`, and `OpenServiceW` fails with `NDRCContextBinding invalid handle` (`run-0002`, lines 906 - 978.
   - **Correction:** `open_driver` always read the service key of the registry and do not consult the service manager.

The vectorized handle of `instr.c` is not cause: it emits only privileged instructions and readings of `0xfffff78000000000`. In the loop it appears called in each exception, but returns "keep looking."

The corrected version was compiled in a separate copy (`build/hidstack-hw-next/`), without touching `out/hidstack-hw`, while it was built W199.

To reactivate it:
1. pass the two reviews to `tools/build-hidstack-hw.py` and run it;
2. recopy `pwhidhost.dll` in `tools/build-wine-hardware.py` and remove it from `obsolete_files`;
3. run `link-wine-boot.py` (does not change: the Unix object is the same) and `build-wine-hardware.py`.

In the test, in addition to the above: open File Manager, winecfg and Task Manager and confirm that they open as in W197.

<a id="w200-resultado"></a>


## W200: result

Report: `reports/wine-hardware-w200/physical/20261104T124304Z/`. User response: File Manager, winecfg and Task Manager open. Jewel.cpl doesn't get the command ready. The Lost Forest hung up when it opened.

Stack starts well:
- winebus, winehid and xinput load from their service key;
- `winebus load status=0`;
- `pad device started`, `pad connected=1`;
- `PWPAD game_mode` alternates.

1. **Exemptions rate in `run-0001`: not HID stack.**
   - The tab Windows. Gaming.Input of joy.cpl calls `RoGetActivationFactory("Windows.Gaming.Input.RawGameController")`. It fails because `windows.gaming.input.dll` is not in the runtime.
   - Then `update_wgi_devices` use the null factory: AV reading `0x3` in joy.cpl + 0x9122.
   - That happens within a callback window, and follows the loop of `c0000258`.
   - W178 has the same AV and about 496 000 `c0000258`.
   - The vectorized ntoskrnl handler appears on each track because now he runs first, but returns "keep looking."
2. **joy.cpl, empty "connected" lists.**
   - The first page adds a device DirectInput only if it responds `DIPROP_GUIDANDPATH`, and puts it in "XInput devices" if your path contains `&ig_`.
   - `joystick_pad.c` (W179) never implemented that property, so the command did not appear there or before W200.
   - The HID device `&ig_`, which would have filled it, is skipped by the dinput filter.
   - Proposed arrangement: `joystick_pad.c` responds `DIPROP_GUIDANDPATH` with winexinput's HID path `&ig_`.
3. **The Lost Forest se cuelga.**
   - Unity loads xinput and consults it (`game_mode=1`), creates the swap chain (`PWDXGI`) and does not create the presenter of DXVK, which in W195 did come later.
   - From there he also does not write the scout monitor (thread 0030). Only follow the native audio thread (`PWAUDIO`, `peak=0`).
   - It looks like a block on the side of Wine/servidor on the Unity Raw Input or HID road. With the current log you cannot know which order was hung.
   - For W202 three diagnoses are proposed:
     - a line by IRP dispatched (`PWHID irp`, and `done` with its duration);
     - a command reporting counter;
     - a `C:\orbis\nohid.txt` file that turns off the stack without rebuilding, to compare The Lost Forest with and without it.

<a id="w202-cambios"></a>


## W202: changes

- **`joystick_pad.c`** (`tools/build-dinput-hw.py`): responds `DIPROP_GUIDANDPATH` with the path of the present HID interface containing `vid_045e&pid_028e` and `&ig_` (`CM_Get_Device_Interface_ListW`). joy.cpl then lists the command in "XInput devices." Without the HID stack returns `DIERR_UNSUPPORTED`, as before.
- **Filter of dinput** (`joystick_hid.c`: now it's only `&IG_`.
  - The winexinput child `&XI_` is not recorded as HID interface: hidclass gives him `GUID_DEVINTERFACE_WINEXINPUT`. That's why it doesn't appear in `EnumDevices`.
  - Windows. Gaming.Input opens it by path through dinput, and the previous filter also closed that way.
- **Trg of orders** (overlay of `ntoskrnl.c`): `PWHID irp n= type= code= client=` before each order sent and `PWHID irp done ... status= ms=` after.
  - The first 400 and then only those that take more than 100 ms are recorded.
  - `type` values: 1 create, 2 close, 3 read, 4 write, 5 flush, 6 ioctl, 7 volume, 8 free, 9 Cancel. `client` is the thread that asked for it.
  - An order that never comes back appears with its starting line and without `done`.
- **Report counter** (`native/winebus_orbis.c`): `PWHID report n= queued= len=`, the first 10 and then every 500.
- **Switch** (`native/pwhidhost.c`): if there is `C:\orbis\nohid.txt`, the host records `PWHID disabled by C:\orbis\nohid.txt` and does not load ntoskrnl or any driver.

Construction for W202:
1. `build-hidstack-hw.py` and `build-dinput-hw.py` (both already running)
2. `link-wine-boot.py` (changed `winebus-unix.o`)
3. `build-wine-hardware.py`

Suggested test:
1. The Lost Forest with the stack, just like in W200. If you hang up, look in the log the last `PWHID irp` without your `done` and your `client`.
2. The Lost Forest with `C:\orbis\nohid.txt` created (by FTP): it serves to see if the hang comes from the stack.
3. joy.cpl, first page: the command should appear in "XInput devices." The tab Windows. Gaming.Input continues to break, see below.

<a id="pestaña-windowsgaminginput-de-joycpl-pendiente-de-decisión"></a>


### Pestana Windows. Gaming.Input de joy.cpl (decision-making)

The failure is old (W178): `windows.gaming.input.dll` is not there and joy.cpl does not control the null factory. There are two possible arrangements:
- **Save in joy.cpl:** a overlay of `dlls/joy.cpl/wginput.c` with `if (!statics) return;` after every `RoGetActivationFactory`. These are three sites: `update_wgi_devices`, `check_gamepad_interface` and `check_racing_wheel_interface`. It is compiled with the fixed build commands and copied instead of `joy.cpl`. He's a boy: the tab is empty, without the fault or the loop.
- **Instalar Windows.Gaming.Input:**
  - The DLL is on the build-up set, and its imports (base, user32, dinput8, setupapi, hid) are already on the runtime.
  - But the prefix does not have any `ActivatableClassId` of `Windows.Gaming.Input.*`, so you would have to register them (registration keys in the prefix) as well as copy the DLL.
  - With the HID stack, the tab would see the control (by `&XI_`), and also the games that WGI uses.
  - It's more work and it's not proven.

<a id="w203w205-el-mando-llega-a-unity-pero-unity-no-lee-más"></a>


## W203 - W205: the command reaches Unity, but Unity does not read anymore

- **W203:** The Lost Forest's hang was the limit of 256 fds of `poll` of the server in process (fixed by the fase9 session). The game starts.
- **W204:** Unity receives XInput values (`PWPAD xinput lx=…` changes with the stick), but the character does not move and `Player.log` He doesn't have "Joystick connected." The only HID reading of Unity (irp n = 24) is pending.
- **W205** (traces in winebus, winexinput and hidclass): the report path works from point to point. In the line 4247 the first report completes the reading of Unity (`hc queued … hid … client reads completed 1`). Then Unity does not read again: there is no other irp `type=3` until the game closes (line 4711).

Cause (server of Wine and UnityPlayer):
- The classic Unity input has its own thread (UnityPlayer `0x1805154d0`). Wait for the reading events with `WaitForMultipleObjects`, call `GetOverlappedResult(…, FALSE)`, process the report and call back to `ReadFile`.
- The first reading is released by the main thread of Unity. It was left in hydclass. Wine ends a pending reading of a device with a system APC (`APC_ASYNC_IO`, `server/async.c`) on the thread that requested it, and just after that it points to the event of `OVERLAPPED`.
- The main thread of Unity is waiting for native calls (DXVK/Vulkan), not for Wine, so the APC is not running. The event is not pointed out, the input thread waits forever, and Unity never gives the command by connected.
- The device readings begin with unknown state (`async_set_unknown_status`, `server/device.c`): the thread you read awaits within Wine until the driver responds. If the driver completes the reading in that same office, the APC runs on that wait.

<a id="w206-arreglo"></a>

## W206: fix

`tools/build-hidstack-hw.py`, overlay of `hidclass.sys/device.c`:
- hidclass keeps the last report on each device;
- a new client tail starts with that report (`PWHID hc open pdo …: queue starts with the last report`).

Thus, the first reading of Unity is completed in the office itself. The following are asked for their input thread, which awaits at `WaitForMultipleObjects`, where their APCs do run. The extra report is the current state of command. The traces of W205 follow.

Construction: `build-hidstack-hw.py` (already running) and `build-wine-hardware.py`. No need to link: the Unix object did not change.

Try: open The Lost Forest and move the left stick. I should move the character. In the log there should be more than one irp `type=3`, with the `client` of Unity's input thread.

It is open: the same problem would affect any asynchronous reading that a thread leaves pending without waiting again within Wine. It was not investigated why the W195 SIGUSR1 does not run the APC on that thread.

<a id="w206w211-el-mando-llega-a-unity-pero-el-inputmanager-no-responde"></a>


## W206 - W211: the command reaches Unity, but the InputManager does not respond

- **W206:** Unity's first reading is completed in the office, as was sought, but the game does not change.
  - UnityPlayer does not read by HID a device paired with XInput: its device update (`0x18051eab0`) calls `XInputGetState` and nothing else.
  - That is why the second reading is missing: it is what is expected. The arrangement of W206 is left (not upset), but it was not the cause.
  - "Joystick connected" is only written when the caller passes a log indicator, which does not happen to the boot. It doesn't prove anything to be missing.
- **W208** (trace `PWXI`): the Unity update (`UnityPlayer.dll+0x51ef65` calls `XInputGetState` about 65 times per second, without error, and gets the stick moving. In `0x18051ef40` it normalizes the sticks, triggers, buttons and cruises and keeps them in the device's joystick object, which is recorded as 0 index ("joystick 1").
- **W209:** the control does not move the menu either (user response). Unity's InputManager doesn't use that joystick. The disassembly could not establish why.
- **W211** (experiment): with `C:\orbis\padhid-generic.txt` present, winebus publishes the command as generic gamepad HID.
  - Use VID 1209 and PID 5057 (pid.codes), `is_gamepad` in FALSE and the name "OrbisDesk Gamepad."
  - There is no winexput or `&IG_`, so Unity takes its HID joystick path: SetupDi and readings from its input thread.
  - XInput is still the same for the games that use it.
  - In dinput, `joystick_hid.c` saltates 1209: 5057 and `joystick_pad.c` return your path, so joy.cpl lists it in "DInput devices."
  - El log dice `PWHID pad bus init vid=… pid=… mode=xinput|generic-hid`.
  - Without the file, everything is as in W208.

<a id="w211-resultado-y-decisión-w213"></a>


## W211: result and decision (W213)

- **Results of W211** (`reports/wine-hardware-w211/physical/20261104T164421Z/run-0001.log`:
  - `mode=generic-hid` and there is `&IG_`.
  - Unity opened the generic device and read it from its main thread (`0064`): 310 readings, 17 with a report delivered. He didn't call XInput.
  - So the game mode was never activated, and the `hw_pad.c` keyboard and mouse emulation remained active in the game: `input_event source=pad` with arrows (39 and 40 codes), clicks and wheel.
  - What the user saw work (move with the cross, the pointer menu and Enter) is that emulation, **not the Unity joystick**.
- **The game reads above all the keyboard:** its `Assembly-CSharp.dll` calls `Input.GetKey` / `GetKeyDown` with A, D, ←, → (move), W, S, ↑ (climb), Space (jump) and Escape.
- **Still unresolved** the real joystick path of Unity 2020 (classic input), in both modes:
  - with `&IG_` / XInput, Unity receives the command but its InputManager does not use it;
  - As generic HID, Unity reads it, but the stick did not move the character.

**W213: Generic HID by default.**
- `native/winebus_orbis.c` publishes the command as generic gamepad HID (1209: 5057, "OrbisDesk Gamepad").
- `C:\orbis\padhid-xinput.txt` back to Xbox 360 of W198 - W208.
- The reason: in XInput mode, Unity consults XInput in each table. That activates the game mode, which turns off the emulation, and since Unity doesn't use the command either, the command does nothing. In generic mode the emulation is available.
- The XInput (`xinput1_3` games give the command as a driver 0) and DirectInput (`joystick_pad.c` games behave the same in both modes.
- `padhid-generic.txt` is no longer used.
- **Risk, untested:** SDL2 and Unity's new Input System read XInput and also HID devices. Without `&IG_` they can't match them, so they can list two controls: XInput 0 and a generic HID joystick 1209: 5057. You have to try it with a game SDL2.

**Key profile for The Lost Forest:** `fixtures/padmaps/The Lost Forest.exe.ini`
- Cross and left stick send the arrows, cross send Space (jump), Triangle and Options send Enter. Escape is not assigned.
- `build-wine-hardware.py` already copies all `.ini` to `C:\orbis\padmaps`.
- **Today it is not loaded:** `pw_hw_pad_profile` only runs when a program starts by relaunching or is 32 bit (`native/wine_hardware.c`), and The Lost Forest runs as a guest of 64 bits within explorer.
- A bridge is needed:
  - `kernelbase` (`ps4_guest_launch`, in `tools/build-guest-hw.py`) warns the native side when a guest loads and when it ends;
  - `hw_pad.c` must be able to change and delete the profile with the steering thread running.
- In the meantime, the emulation of the desktop already allows to move with the cross (arrows) and use the menu.

**W213: guest profile bridge.**
- `tools/build-guest-hw.py` (kernelbase `process.c`):
  - when a guest is finished loading, tell the native side of the program route;
  - When it's over, let me know again to delete.
  - It does so by the Unix library of xinput (called 3, `unix_pad_profile`). The load per name is made directly with `NtQueryVirtualMemory(MemoryWineLoadUnixLibByName)` and the call with `__wine_unix_call_dispatcher` that exports ntdll, because kernelbase does not link winecrt0.
- `tools/build-xinput-hw.py`: the call `pad_profile`, which passes to `pw_wine_pad_profile`. `platform/ps4/pw_wine_unixlibs.c` has the weak version "without command."
- `native/hw_pad.c`: `pw_wine_pad_profile` leaves only one order. The thread of the command applies it at the beginning of each reading, so the profile never changes in the middle of `poll_controller`.
  - When charged, the profile is changed only if there is `padmaps\<exe>.ini`. If not, the asset remains: The Lost Forest starts `UnityCrashHandler64.exe` as another guest, and that boot does not remove the profile.
  - When a guest is finished, it is deleted only if the active profile is yours.
  - When changing, the keys that had tight profile and emulation are released.
- Log:
  - `PWPAD profile=The Lost Forest.exe keys=…`
  - `PWPAD guest profile=<exe> none, keeps …`
  - `PWPAD guest profile=<exe> cleared`
  - if you do not find the library: `PWPAD no pad library for guest profiles`

Construction of W213: `build-guest-hw.py`, `link-wine-boot.py` (change `xinput-unix.o` and `winebus-unix.o`, in addition to `hw_pad.c` and `pw_wine_unixlibs.c`) and `build-wine-hardware.py`. `out/hidstack-hw` and `out/xinput-hw` are already rebuilt.

<a id="resultado-w213"></a>


## Result W213

Report: `reports/wine-hardware-w213/physical/20261104T171948Z/run-0001.log`. User response: "W213 yes, all OK." In The Lost Forest the control moves the character and jumps, through the key profile.

In the log:
- `PWHID pad bus init vid=1209 pid=5057 mode=generic-hid`
- `PWPAD profile=The Lost Forest.exe keys=11 stick=keys`
- `PWPAD guest profile=UnityCrashHandler64.exe none, keeps The Lost Forest.exe`
- during the game, events `source=profile`: arrows and space
- on its way out, `PWPAD guest profile=The Lost Forest.exe cleared`

The traces `PWHID` and `PWXI` remained active in W213.

**W214: no diagnostic traces** (at the user's request).
- Se sacan:
  - the trace on request of ntoskrnl (W202);
  - Winebus, winexinput and hydclass (W205);
  - the reporting counter of `winebus_orbis.c`;
  - `PWPAD xinput` once per second (W204);
  - `PWXI` (W208), which also made two `GetModuleHandleExW` in each call to XInput.
- winexinput.sys and the PE side of winebus.sys are back to the fixed build, without overlay. hidclass maintains only the arrangement of W206.
- The lines that are written only once or in each state change remain: load of drivers, `PWHID irp loop running`, `pad bus init`, `pad device started`, `PWPAD game_mode` and `PWPAD profile`.
- Construction: `build-hidstack-hw.py` and `build-xinput-hw.py` (the two already running), `link-wine-boot.py` (changed `winebus-unix.o`) and `build-wine-hardware.py` (`hw_pad.c`).

It is open:
- the actual joystick path of Unity 2020, in both ways;
- the possible double control in games SDL2 with generic HID, untested;
- the tab Windows. Gaming.Input of joy.cpl, on hold.

<a id="riesgos"></a>


## Risks

- It's the first time he's run `ntoskrnl.exe` into the title process. Its `DllMain` installs a vector-based exception (`instr.c`) handler that emits privileged instructions of drivers. For any other exception it returns "keep looking," but it runs before the game drivers (Monkey uses access violations).
- That the device manager of the wineserver in process delivers the IRP to a thread of the same process was not tested before.
- The installation of the children uses setupi with the INF of the prefix. Without SCM, `SetupInstallServicesFromInfSection` fails, but its result is ignored and the value `Service` is written equally (`dlls/setupapi/devinst.c`). The service key is created by `pwhidhost.dll`.
- A game that reads the command only by HID (without XInput) does not turn on the game mode. The command would continue to move the pointer. Unity and SDL use XInput for `IG_` devices.
- Windows.Gaming.Input still does not see the command: it needs the warnings PnP of plugplay, which do not exist in the model of a process.
