<a id="w180-unix-side-de-crypt32-fase-9-applet-de-winecfg-que-espera-y-segunda-sonda-usb-fase-10"></a>


# W180: Crypt32 Unix side (phase 9), waiting winecfg applet and second USB probe (phase 10)

[English](HARDWARE_W180.md) | [Español](HARDWARE_W180-es.md)

APP_VER 02.79. Base W179. The result of W179 is in `docs/HARDWARE_W179.md`.

<a id="applet-de-wine-configuration"></a>


## Wine Configuration applet

`fixtures/win32/winecfgcpl.c`:
- After starting `winecfg.exe`, the applet awaits its main thread (`pi.hThread`).
- In W179 the applet ran at `rundll32`, and the departure of that guest also finished the winecfg thread before he drew.
- Waiting for the thread is also correct in Windows. The handle of the process is no good here, because the one of a guest is the one of the console.

<a id="crypt32-fase-9-sesión-del-navegador"></a>


## crypt32 (phase 9, browser session)

<a id="qué-pasó-en-w179"></a>


### What happened in W179

Reporte: `reports/wine-hardware-w179/physical/20261103T221219Z/`.

- **bcrypt worked:** `xul.dll` already loads its imports.
- **The next block is crypt.32:**
  - `failed to load "/data/wine/lib/wine/x86_64-unix/crypt32.so": Dynamic loading not supported`
  - `Initialization of "crypt32.dll" failed`
  - xul is downloaded and mshtml da `Failed to init Gecko`.
  - It passes in `webview64` (`run-0001.log`, line 2436 and in Pale Moon (`run-0002.log`, line 1946 onwards), which shows "Coud not load XPCOM."
- **Access failure** (`handle_syscall_fault c0000005`, `ip=0x448636`, address reading 8) It's from the crypt32 itself. When `DLL_PROCESS_ATTACH` fails, the charger calls `DLL_PROCESS_DETACH`, and there crypt32 makes the call Unix `process_detach` (index 1) without table.
- **netapi32:** `netapi32.so` also does not load, but netapi32 checks that you have Unix side before each call (`samba_init`) and answers as a local team. That log line is not a mistake.

<a id="cambio"></a>


### Change

|File|What are you doing?|
|---|---|
| `tools/build-unixlibs-ps4.py` |New library `crypt32`: `dlls/crypt32/unixlib.c` unchanged, with your Orbis Makefile recipe, and `platform/ps4/pw_crypt32_unix.c` with the same recipe. The Wine tables are renamed when compiling `pw_crypt32_wine_unix_call_funcs` and `pw_crypt32_wine_unix_call_wow64_funcs`.|
|`platform/ps4/pw_crypt32_unix.c` (new)|The tables that are recorded (`pw_crypt32_unix_call_funcs`, `pw_crypt32_unix_call_wow64_funcs`). They call those of Wine input per input and add traces `PWCRYPT`.|
| `platform/ps4/pw_wine_unixlibs.c` |`crypt32.so` input, with x64 table and wow64 table for 32 bit programs.|

Behavior on the console:

- **Without GnuTLS:** the `config.h` of Orbis does not define `SONAME_LIBGNUTLS`. So `unixlib.c` uses the functions without GnuTLS of Wine: open, import and export PFX stores and return keys `STATUS_DLL_NOT_FOUND`. Every time there is the line `PWCRYPT <x64|wow64> <función> unsupported: no GnuTLS on the console`.
  - It affects `PFXImportCertStore` and the PFX export. Neither Gecko nor Pale Moon use them to sail.
- **root certificates:** Wine search for them on fixed routes (`/etc/ssl/certs/ca-certificates.crt`, `/etc/ssl/certs`, `/etc/pki/tls/certs/ca-bundle.crt` and others), which the console does not have. The enumeration ends empty, and the first time is `PWCRYPT <vista> root_certs=none`. The crypt32 root warehouse retains the same Microsoft roots as it brings `rootstore.c`.
  - **Pale Moon** valid TLS with its own NSS (`nssckbi.dll` store, So you don't need the one in the system.
  - **MSHTML** does not have TLS on the console (schannel does not have Unix side), so I would not use it either.
  - A certificate warehouse of the console was not sought.

<a id="construcción-orden"></a>


### Construction (order)

1. `python3 tools/build-unixlibs-ps4.py` → `build/unixlibs-ps4` (adds `crypt32.o` to the report)
2. `python3 tools/link-wine-boot.py`: links all the report libraries and compiles `pw_wine_unixlibs.c`
3. the steps of the ELF hardware using the main session
4. `python3 tools/build-wine-hardware.py`
5. `python3 -I tools/check-web-closure.py build/wine-hardware-w180/runtime`: it has to end with 0. Check the imports of the PE, not the Unix sides.

`pw_crypt32_unix.c` only compiles `build-unixlibs-ps4.py`: `link-wine-boot.py` compiles a fixed list of `platform/ps4` files.

<a id="verificación-sin-consola"></a>


### Console-free verification

I only compiled crypt32 with a copy of `build-unixlibs-ps4.py` that you write on the scratchpad (WSL, `orbis-cc`):
- The two units compete without warning.
- The combined object defines `pw_crypt32_unix_call_funcs` and `pw_crypt32_unix_call_wow64_funcs` as global.
- Unix file routines (`open`, `opendir`, `readdir`, `fstat`) are redirected to those of `platform/ps4` (`pw_wine_open`...), as in the other libraries.

He didn't link the ELF.

<a id="prueba-física"></a>


### Physical test

1. **WebView test (64 -bit) and (32 -bit):** is expected `local complete=yes`, `title "orbis-webtest"` and `es5 "es5-ok"`.
2. **Pale Moon:** opens the local page and then real sites (see `HARDWARE_W177.md`).
3. **In the log:**
   - does not have to appear `crypt32.so … Dynamic loading not supported`, `Initialization of "crypt32.dll" failed` or `Failed to init Gecko`;
   - is expected `PWCRYPT x64 root_certs=none`, and `wow64` in the 32 bit.

<a id="no-verificado"></a>


### Not verified

- Nothing was tested on the console.
- There may be another block after crypt32 (another Unix side, memory, threads). To find it, `check-web-closure.py` only covers imports of PE.

<a id="segunda-sonda-usb-fase-10-sesión-de-red"></a>


## Second USB probe (phase 10, network session)

<a id="resultado-de-la-sonda-de-w179"></a>


### The result of the probe of W179

`reports/wine-hardware-w179/physical/20261103T221219Z/run-0001.log`, line 125, with a connected disk before opening the app:

```
PWUSB slot=0 stat=-1 errno=2 dir=0 entries=-1 list_errno=0 first=- statfs=-1 errno=0 version=00000000 type=- rdonly=-1 from=- on=-
```

`/mnt/usb0` does not exist for the app, and neither does any of the slots 1 to 7 appear. The letters below await the second probe (W180): list `/`, `/mnt`, `/mnt/sandbox/ORBW00002_000`, `/mnt/ext0` / `ext1`, `/mnt/disc`, `/app0`, `/data`, the random word folder of the sandbox and others, with a line `PWUSB path=…` each. It does not use `getfsstat`, because it should be called a direct syscall and, if the sandbox rejects it, the app ends.

<a id="cambio-cuando-la-app-vea-los-discos"></a>


### Change (when the app sees the disks)

|File|What are you doing?|
|---|---|
| `platform/ps4/pw_wine_fs.c` / `.h` |The assembly table goes from C: / Z: to C:, Z: and `d:`.. `k:`, which point to `/mnt/usb0`.. `/mnt/usb7`. If a disk is not connected, its path gives ENOENT as any missing destination, so the letter appears and disappears with the disk: `GetLogicalDrives` 64 bit already tests the roots (W105). New functions: `pw_wine_fs_usb_slot(fd)`, which gives the slot by comparing `st_dev` to each `/mnt/usbN`, and `pw_wine_fs_usb_label`, which reads `.windows-label` from the root of the disk if the file exists.|
|`tools/build-wine-directory-ps4.py` (`file.c` of ntdll)|`FileFsDeviceInformation` marks `FILE_REMOVABLE_MEDIA` in files of a USB disk, and `GetDriveType` gives `DRIVE_REMOVABLE`. `FileFsVolumeInformation` takes the `.windows-label` label; without that file is empty, because the console does not inform the volume name. The serial number is 0.|
| `tools/build-explorer-hw.py` (`desktop.c`) |One thread compares `GetLogicalDrives` each 2. When it changes, it sends `WM_DEVICECHANGE` (`DBT_DEVICEARRIVAL` / `DBT_DEVICEREMOVECOMPLETE` with `DEV_BROADCAST_VOLUME`) to all windows and `SHChangeNotify(SHCNE_DRIVEADD/REMOVED)`, and writes a line `PWDRIVE X: arrived|removed`. In Windows and Wine it does so mountmgr, which does not run here.|
| `tools/patch-wfm-files.py` |WFM relists the current view with `WM_DEVICECHANGE` and writes `PWFM device_change refresh`. The tree on the left is only updated when you fold and deploy "Computer."|
|`native/wine_hardware.c` (main session)|`pe_machine` and `program_cwd` accept D:.. K: (`/mnt/usbN`) in addition to C:, to relaunch a 32 bit title from the disk with your folder.|
|`fixtures/win32/drivetest.c` (new) and `tools/build-wine-hardware.py`|`drivetest64.exe` and `drivetest32.exe` (`[letra]`, D: by default) write in `C:\orbis\drive-result.txt`: units and types, volume (label, series, FS), space, root list, reading the end of the larger file and a saved `D:\orbisdesk-test\save.txt` (write, reread, compare and delete).|

<a id="construcción"></a>


### Build

1. `python3 tools/build-wine-directory-ps4.py`
2. `python3 tools/build-explorer-hw.py`
3. `python3 tools/build-wfm.py` (applies `patch-wfm-files.py`)
4. `python3 tools/link-wine-boot.py`
5. `python3 tools/build-wine-hardware.py`

<a id="prueba"></a>


### Test

1. With the disk connected before opening the app, run `C:\orbis\drivetest64.exe` and `drivetest32.exe`. In `drive-result.txt` you should leave `drive D: type=removable`, the list and `write ok=1 same=1`, if the W179 probe showed that it can be written.
2. With open scans and WFM, disconnect the disk and reconnect it. The log should appear `PWDRIVE D: removed` / `arrived` and `PWFM device_change refresh`, and D: should disappear and return to WFM.
3. SuperMarioKart from the disk, without copying it: folder `SMK` copied to the root of the disk and open `D:\SMK\SuperMarioKart.exe` from WFM. It requires the change of `wine_hardware.c`.
4. A game saved on the disk, if the step 1 gave `write ok=1`.

<a id="límites-y-riesgos"></a>


### Limits and risks

- **Sandbox:** the app does not jailbreak. If `PWUSB slot=0` gives `errno=2/1/13`, the app does not see the disks. Using the SDK jailbreak of GoldHEN would be a separate decision.
- **Directory Notifications:** the in-process server does not notice directory changes (no inotify) in any unit. WFM does not show new D files: until refresh. The hot connection doesn't depend on that.
- **Disconnect with open files:** readings fail, and a game running from the disk falls.
- **Fixed letters by slot:** usb0 is D:, usb1 is E:, although D: is free.
- **32 bit programs that list units:** `GetLogicalDrives` 32 bits does not have the patch W105 and returns 0. The routes `D:\…` work the same. The patch for the kernelbase of i386 remains as an optional step.
- **exFAT/FAT32:** the names of more than 255 bytes in UTF- 8 They don't go into `d_name`. FAT32 short in 4 GiB, saves dates with resolution of 2 s and has no bit of permissions.

<a id="prueba-física-1"></a>


## Physical test

Pending.
