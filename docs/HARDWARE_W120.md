<a id="w120-audio-de-windows-fase-3-del-plan-pe32"></a>


# W120: Windows audio (phase 3 of the plan PE32)

[English](HARDWARE_W120.md) | [Español](HARDWARE_W120-es.md)

APP_VER 02.19. Base W119. Built and verified locally; **not yet up**: wait for it to be tested W119, because both share the runtime of `/data`.

<a id="diseño"></a>


## Design

- **Driver**:
  - It is the `wineps5` of prospero-win (`upstream/prospero-win/wine/wineps5/unix.c` with `src/pw_audio_mix.c`, LGPL- 2.1 -or-later), renamed `wineps4`.
  - Minimum changes, in `tools/build-audio-ps4.py`: the sink is linked instead of looking for `dlsym`, and the device is called `PS4`.
  - Operation: an endpoint of reproduction, mix at 48 kHz in blocks of 256 frames and port as a watch.
  - It has tables WoW64, so it serves programs of 32 and 64 bits.
- **Native Sink** (`platform/ps4/pw_wine_audio.c`):
  - Open your own port AudioOut MAIN (stereo S16, 48 kHz, explicit volume 0 dB), other than that of DOS.
  - The failures are recorded (`PWAUDIO open … failed=`) and returned.
  - Each ~ 5 s records `PWAUDIO level grains/nonzero/peak`, as in W113.
- **Name load**:
  - mmdevapi asks `wineps4.drv` with `MemoryWineLoadUnixLibByName`, which in ntdll used `dlopen`, impossible in ELF Static.
  - The `virtual.c` tested (your hash is verified) is rewarded with a single addition: first look in the static table (`pw_wine_static_unixlib_by_name`, in `platform/ps4/pw_wine_unixlibs.c`). Log: `PWBOOT static_unixlib_by_name`.
  - Unload it does nothing: the module is a marker.
- **Record**: `HKCU\Software\Wine\Drivers\Audio = "ps4"` in the `user.reg` of the prefix. He does the same work as the 0120 patch of prospero-win, without touching the server.
- **DLL x64**: mmdevapi, dsound and msacm32 (`tools/stage-wine-i386.py`, `modules_x64`). The i386 were already coming in W119.
- **Size**: From W120 it also takes the cleansing information from the i386 DLL. The modules go from 507 to 183 MiB and the runtime from 442 to 303 MB.

## Fixtures

`C:\orbis\sound64.exe` (guest) and `C:\orbis\sound32.exe` (relaunch): tone of 440 Hz for 2 s by `waveOut`. Each step is left in `C:\orbis\sound-result.txt` (devices, open, prepare, write, done).

<a id="construcción"></a>


## Build

```sh
python3 tools/stage-wine-i386.py
python3 tools/build-audio-ps4.py
python3 tools/link-wine-boot.py
python3 tools/build-wine-hardware.py --mangohud enabled
```

The link has no indefinite symbols. The ELF contains `PWAUDIO level` and `static_unixlib_by_name`, and `user.reg` has `"Audio"="ps4"`.

<a id="prueba-cuando-se-suba"></a>


## Test (when uploaded)

1. sound64.exe: the tone is heard, `sound-result.txt` ends in `done=1` and in the log appear `static_unixlib_by_name wineps4.drv`, `PWAUDIO open … port>=0` and `PWAUDIO level` with peak > 0.
2. sound32.exe: same thing, by WoW64.
3. Solitaire or the sound of the system, if you use them.

<a id="entrega"></a>

## Delivery

It also includes the ws2_32 correction of 32 bits that came out of the W119 test. `/data/pkg/orbis-win-W120-024d30e0d1c7.pkg`, with the check-back reading (603 files, 105 uploaded). W119 withdrawn.

Prueba:
1. `C:\orbis\sound64.exe`: Can you hear the tone?
2. `C:\orbis\sound32.exe`: same thing, by WoW64.
3. SuperMarioKart.exe: It is expected to pass ws2_32 and advance to Direct3D 7.

<a id="resultado-físico-20261102t220327z"></a>


## Physical result: 20261102T220327Z

The user did not hear any sound, either in 32 or in 64 bits.

- **sound64.exe** (he ran twice as a guest) and **sound32.exe** (relaunch, `cpu=wowprospero`) end with 0. `sound-result.txt` says `devices=0;open=6`, that is `MMSYSERR_NODRIVER`.
- The cause is in the log: `ole:com_get_class_object class {bcde0395-e52f-467c-8e3d-c4579291692e} not registered`. That class is `MMDeviceEnumerator`, and the sealed prefix was armed when mmdevapi did not exist. winmm never gets to load the driver: there is no `static_unixlib_by_name` or `PWAUDIO`. The driver and the sink did not come to be tested.
- **SuperMarioKart.exe**: passes ws2_32, which has already been corrected. Now it cuts `"opengl32.dll" failed to initialize`: the opengl32 i386, which wined3d matters through ddrag, did not have its Unix (`opengl32.so` part). Finish with c0000142 and return to the desk.

# W121 (02.20)

- `system.reg` records the COM classes of mmdevapi (MMDeviceEnumerator) and dsound (DirectSound, DirectSound8, BufferConfig, Capture, Capture8 and FullDuplex) in `Classes\CLSID` and `Classes\Wow6432Node\CLSID`, as your `DllRegisterServer` would do. The prefix had no input in Wow6432Node\ CLSID.
- `tools/build-unixlibs-ps4.py` compiles the Unix part of opengl32 (`unix_thunks.c` and `unix_wgl.c`, without patches) and `pw_wine_unixlibs.c` records it as `opengl32.so` with tables WoW64. The link is without indefinite symbols. Your WGL calls go to win32u, which in PS4 still does not create GL contexts. The expected thing is that wined3d will fail later, already in the creation of the D3D device (phase 4b).

Delivery: `/data/pkg/orbis-win-W121-69a6fea6d6c3.pkg`, with the check-back reading. W120 withdrawn.

<a id="resultado-físico-w121-20261102t230543z"></a>


## Physical result W121: 20261102T230543Z

- **sound64.exe sounds** (confirmed by the user). It's the first audio of Windows in PS4:
  - `sound-result.txt`: `devices=1;open=0;prepare=0;write=0;done=1`;
  - in the log, `static_unixlib_by_name L"wineps4.drv" wow=0` and `PWAUDIO open init=0 port=536870919`.
- **When the interface is finished, it hangs..** `ps4_guest_exit_process` finish the other two threads of the guest. One of them (0048, the winmm wavelength) was inside `LdrUnloadDll` with the loader lock taken. Die with the lock, and then `RtlpWaitForCriticalSection … loader_section wait timed out in thread 0040, blocked by 0048`: from there no charge or download from DLL can go ahead, nor that of explorer.
- sound32.exe and SuperMarioKart.exe were not tested by the hanging.

# W122 (02.21)

`tools/build-guest-hw.py`, `ps4_guest_exit_process`:
- Before finishing the other guest's threads, take the loader lock (`LdrLockLoaderLock` in an attempt mode, up to 2 s) and release it when those threads are finished. So no one dies inside the loader.
- Log: `loader_lock=1 tries=N`. If you don't get it in 2 s, you record it with `loader_lock=0` and follow it as before.
- The change affects all programs that close with their own threads, not just those of audio.

Delivery: `/data/pkg/orbis-win-W122-bf7dd5d39621.pkg`, with the check-back reading. W121 withdrawn.

<a id="resultado-físico-w122-20261102t231348z"></a>


## Physical result W122: 20261102T231348Z

- **sound64.exe**: the user heard the tone; `done=1`. On leaving: `loader_lock=1 tries=0`, `other_threads_wait=0 count=2`, and the desk continued to respond. The hang of W121 was solved.
- **sound32.exe** (relaunch with wowprospero):
  - `static_unixlib_by_name L"wineps4.drv" wow=1` and `PWAUDIO open … port=536870919`: the driver load in WoW64.
  - Then `wine: Unimplemented function advapi32.dll.SystemFunction036`. The process ends with status 1 and returns to the desktop. The user didn't hear the tone.
- **SuperMarioKart.exe**: passes ws2_32 and opengl32, load wined3d and open the audio (FMOD → dsound → mmdevapi → `PWAUDIO open`). At the 9 s he dies in the same function. Before there is a C + + exception that the game handles. It still didn't reach Direct3D.
- Cause: Advapi32 resends `SystemFunction036` (RtlGenRandom) to `cryptbase.dll`, which was not in the sealed sysmow64 (`find_forwarded_export … cryptbase.SystemFunction036`).

# W123 (02.22)

`tools/stage-wine-i386.py` adds `cryptbase` i386, without part Unix, to syswow64 and `lib/wine/i386-windows`. Delivery: `/data/pkg/orbis-win-W123-33a385d0516e.pkg`, with the check-back reading. W122 withdrawn.

<a id="resultado-físico-w123-20261102t232033z"></a>


## Physical result W123: 20261102T232033Z

- **sound32.exe**: WoW64 + `PWAUDIO open … port=536870919` and `process_exit status=0` (before I was done with 1). He's gone. `Unimplemented function`. The sink records the level each ~5 s and hard tone 2 s, so log doesn't say if it sounded: user confirmation is missing.
- **SuperMarioKart.exe**:
  - Run 6,6 s and open the audio (dsound → mmdevapi → `PWAUDIO open`).
  - It launches an exception C + + (`e06d7363`) from the Blitz runtime. Then close alone and clean: `process_exit method=exit status=0`, with all DLL_PROCESS_DETACH, and return to the desk.
  - There is no `Unimplemented` or failure of ntdll. It is the way Blitz reports an error of his runtime (what the dialogue shows is missing). The most likely is that it does not achieve graphic mode Direct3D 7: wined3d has no GL (`wgl:internal_context_create Failed` context. That's phase 4b.

**Phase 3 accepted.** The user confirmed that he heard the tone of sound32.exe (32 bits, WoW64) in addition sound64.exe. The audio of Windows (winmm → mmdevapi → wineps4 → AudioOut) works on 32 and 64 bits in the PS4. The latency was not measured, several sources at the same time or DirectSound direct (SuperMarioKart opens dsound but ends before playing).
