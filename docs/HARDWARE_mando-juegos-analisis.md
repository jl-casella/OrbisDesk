<a id="mando-para-juegos-después-de-w195-análisis-borrador-sin-cambios-de-código"></a>


# Command for games after W195: analysis (draft, no code changes)

[English](HARDWARE_mando-juegos-analisis.md) | [Español](HARDWARE_mando-juegos-analisis-es.md)

<a id="lo-que-ya-existe-w178-w179-w181"></a>


## What already exists (W178, W179, W181)

- `tools/build-xinput-hw.py`: xinput (1 _ 1 to 1 _ 4, x86_64 and i386) with the console control as the 0 controller, by `pw_wine_pad` of `native/hw_pad.c`. Method of prospero-win 0470.
- `tools/build-dinput-hw.py`: DirectInput and DirectInput8 with a device (`joystick_pad.c`) that reads XInput 0.
- Mode game in `native/hw_pad.c`: while some program reads the command by XInput (last second), the sticks and buttons stop moving the pointer and sending keys (`PWPAD game_mode=1`). He's already responding to "how a game gets it without the desk getting it."
- In W178 it was seen `PWPAD game_mode=1` with the Game Controllers panel. So XInput and the game mode work on hardware.

<a id="por-qué-the-lost-forest-no-ve-el-mando-w195"></a>


## Why The Lost Forest does not see the command (W195)

In `reports/wine-hardware-w195/physical/20261104T112911Z/run-0001.log`:
- The game (thread 0040) loads `xinput1_3.dll` but not `dinput8.dll` or `hid.dll`.
- There is no line `PWPAD game_mode`. He never called `XInputGetState`.

It was revised `UnityPlayer.dll` (Unity 2020.3 .3f1, classic input; the game does not bring the new Input System) disassembling it with `llvm-objdump`:
- Unity discovers controls only by HID, by two ways:
  - **SetupDi** over the HID interface (`HidD_GetHidGuid`, `SetupDiGetClassDevsA`, `SetupDiEnumDeviceInterfaces`). The skates containing `IG_` or `ig_` are **leapt** (0x1805137aa).
  - **Raw input** (`GetRawInputDeviceList`, `GetRawInputDeviceInfoW` with `RIDI_DEVICEINFO` and `RIDI_DEVICENAME`). For a name with `IG_` (0x18051b747), look for the first slot 0 - 3 where `XInputGetState` It responds (0x180ead470) and associates it to the device.
- Then, with or without `IG_`, open the name with `CreateFileW(GENERIC_READ, FILE_SHARE_READ|WRITE, OPEN_EXISTING, FILE_FLAG_OVERLAPPED)` (0x18051b7ba). If it fails, record the error and discard the device.
- Call `HidD_GetPreparsedData`, `HidD_GetProductString`, `HidP_GetCaps`, `HidP_GetButtonCaps`, `HidP_GetValueCaps` and `HidP_MaxDataListLength` on that handle.
- It's a `ReadFile` overlapped. Accept success or `ERROR_IO_PENDING`.

Conclusion: For Unity a real HID device, listed by raw input, with `IG_` in the name, is needed that can be opened and that responds to HID IOCTL. XInput is good enough; What's missing is that Unity gets to use it. It is the same thing that does Wine in Linux: winebus adds `&IG_00` to the XInput controls. In Orbis there is no winebus, hidclass or winedevice (the same limit as `\\.\Nsi` in W174).

SDL2 (Raw input or HIDAPI mode), the HID path of dinput and Windows. Gaming.Input need the same. WGI also needs the PnP arrival notices (plugplay), which do not exist in the model of a process.

<a id="opciones"></a>


## Options

| |What?|Touch|Size|Risk|
|---|---|---|---|---|
|A|Emulate on the client's side, as `nsi.dll` in W174: a synthetic input into the win32u raw input list; `hid.dll` answers `HidD_*` for that name; and something open with pending readings (e.g. a named pipe with `IG_` in the name)|win32u, hid.dll and, if the pipe does not reach, ntdll|Medium|Fragile: imitates what Unity does today, not a device|
|B|Run the HID stack of Wine within the process: a thread with the loop of `ntoskrnl.exe` (`wine_ntoskrnl_main_loop`), `hidclass.sys` and `winebus.sys` with a new backend (Unix side) reading `pw_wine_pad` and publishing an Xbox 360 command with `IG_00`|launcher (thread start), winebus (new backend), service log and staging|Great.|It must first be proved that the device manager of the wineserver in process and the PnP of ntoskrnl work without winedevice or plugplay|
|C|A minimum HID device of its own: a thread that speaks the server's device manager protocol and answers only the IOCTL that use `hid.dll` and win32u, with keys `DeviceClasses` in the record|New DLL and registration|Medium-large|We have to generate the data prepared without hydclass.|

Recommendation: B, starting with a girl probe that creates a device manager and a device within the process and opens it with `CreateFile`. If the probe fails, A. It's the only thing that lets Unity, SDL, the HID of dinput and raw input as in Linux. The XInput and the current game mode stay as they are.

Windows. Gaming.Input (`joy.cpl`): it is not cheap with any option. It depends on the warnings PnP; is left for after B.
