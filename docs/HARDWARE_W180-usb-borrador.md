<a id="w180-discos-usb-como-unidades-d-a-k-fase-10-borrador"></a>


# W180: USB disks as D units: a K: (phase 10, draft)

[English](HARDWARE_W180-usb-borrador.md) | [Español](HARDWARE_W180-usb-borrador-es.md)

Eraser of the side session, to join `HARDWARE_W180.md`. It depends on the `PWUSB` probe of W179: if the app does not see `/mnt/usbN`, none of this serves and another decision is needed (see Risks). The pieces were compiled separately and not tested on the console.

<a id="resultado-de-la-sonda-de-w179"></a>


## The result of the probe of W179

`reports/wine-hardware-w179/physical/20261103T221219Z/run-0001.log`, line 125, with a connected disk before opening the app:

```
PWUSB slot=0 stat=-1 errno=2 dir=0 entries=-1 list_errno=0 first=- statfs=-1 errno=0 version=00000000 type=- rdonly=-1 from=- on=-
```

`/mnt/usb0` does not exist for the app, and neither does any of the slots 1 to 7 appear. The letters below await the second probe (W180): list `/`, `/mnt`, `/mnt/sandbox/ORBW00002_000`, `/mnt/ext0` / `ext1`, `/mnt/disc`, `/app0`, `/data`, the random word folder of the sandbox and others, with a line `PWUSB path=…` each. It does not use `getfsstat`, because it should be called a direct syscall and, if the sandbox rejects it, the app ends.

<a id="cambio-cuando-la-app-vea-los-discos"></a>


## Change (when the app sees the disks)

|File|What are you doing?|
|---|---|
| `platform/ps4/pw_wine_fs.c` / `.h` |The assembly table goes from C: / Z: to C:, Z: and `d:`.. `k:`, which point to `/mnt/usb0`.. `/mnt/usb7`. If a disk is not connected, its path gives ENOENT as any missing destination, so the letter appears and disappears with the disk: `GetLogicalDrives` 64 bit already tests the roots (W105). New functions: `pw_wine_fs_usb_slot(fd)`, which gives the slot by comparing `st_dev` to each `/mnt/usbN`, and `pw_wine_fs_usb_label`, which reads `.windows-label` from the root of the disk if the file exists.|
|`tools/build-wine-directory-ps4.py` (`file.c` of ntdll)|`FileFsDeviceInformation` marks `FILE_REMOVABLE_MEDIA` in files of a USB disk, and `GetDriveType` gives `DRIVE_REMOVABLE`. `FileFsVolumeInformation` takes the `.windows-label` label; without that file is empty, because the console does not inform the volume name. The serial number is 0.|
| `tools/build-explorer-hw.py` (`desktop.c`) |One thread compares `GetLogicalDrives` each 2. When it changes, it sends `WM_DEVICECHANGE` (`DBT_DEVICEARRIVAL` / `DBT_DEVICEREMOVECOMPLETE` with `DEV_BROADCAST_VOLUME`) to all windows and `SHChangeNotify(SHCNE_DRIVEADD/REMOVED)`, and writes a line `PWDRIVE X: arrived|removed`. In Windows and Wine it does so mountmgr, which does not run here.|
| `tools/patch-wfm-files.py` |WFM relists the current view with `WM_DEVICECHANGE` and writes `PWFM device_change refresh`. The tree on the left is only updated when you fold and deploy "Computer."|
|`native/wine_hardware.c` (main session)|`pe_machine` and `program_cwd` accept D:.. K: (`/mnt/usbN`) in addition to C:, to relaunch a 32 bit title from the disk with your folder.|
|`fixtures/win32/drivetest.c` (new) and `tools/build-wine-hardware.py`|`drivetest64.exe` and `drivetest32.exe` (`[letra]`, D: by default) write in `C:\orbis\drive-result.txt`: units and types, volume (label, series, FS), space, root list, reading the end of the larger file and a saved `D:\orbisdesk-test\save.txt` (write, reread, compare and delete).|

<a id="construcción"></a>


## Build

1. `python3 tools/build-wine-directory-ps4.py`
2. `python3 tools/build-explorer-hw.py`
3. `python3 tools/build-wfm.py` (applies `patch-wfm-files.py`)
4. `python3 tools/link-wine-boot.py`
5. `python3 tools/build-wine-hardware.py`

<a id="prueba"></a>


## Test

1. With the disk connected before opening the app, run `C:\orbis\drivetest64.exe` and `drivetest32.exe`. In `drive-result.txt` you should leave `drive D: type=removable`, the list and `write ok=1 same=1`, if the W179 probe showed that it can be written.
2. With open scans and WFM, disconnect the disk and reconnect it. The log should appear `PWDRIVE D: removed` / `arrived` and `PWFM device_change refresh`, and D: should disappear and return to WFM.
3. SuperMarioKart from the disk, without copying it: folder `SMK` copied to the root of the disk and open `D:\SMK\SuperMarioKart.exe` from WFM. It requires the change of `wine_hardware.c`.
4. A game saved on the disk, if the step 1 gave `write ok=1`.

<a id="límites-y-riesgos"></a>


## Limits and risks

- **Sandbox:** the app does not jailbreak. If `PWUSB slot=0` gives `errno=2/1/13`, the app does not see the disks. Using the SDK jailbreak of GoldHEN would be a separate decision.
- **Directory Notifications:** the in-process server does not notice directory changes (no inotify) in any unit. WFM does not show new D files: until refresh. The hot connection doesn't depend on that.
- **Disconnect with open files:** readings fail, and a game running from the disk falls.
- **Fixed letters by slot:** usb0 is D:, usb1 is E:, although D: is free.
- **32 bit programs that list units:** `GetLogicalDrives` 32 bits does not have the patch W105 and returns 0. The routes `D:\…` work the same. The patch for the kernelbase of i386 remains as an optional step.
- **exFAT/FAT32:** the names of more than 255 bytes in UTF- 8 They don't go into `d_name`. FAT32 short in 4 GiB, saves dates with resolution of 2 s and has no bit of permissions.

<a id="prueba-física"></a>


## Physical test

Pending.
