<a id="w228-modo-root-y-discos-usb-como-unidades"></a>


# W228: ROOT mode and USB drives as units

[English](HARDWARE_W228.md) | [Español](HARDWARE_W228-es.md)

Summary J001, W227 and W228. W228: `reports/wine-hardware-w228/physical/20261104T215518Z/` (PWJB mode = root, jailbreak rc = 0, identity setuid = 1 wineserver_lookup = 2, PWDRIVE d: and e:, relaunch with source = relax, `pe_machine path=/mnt/usb1/PC/Grand Theft Auto Vice City/gta-vc.exe machine=0x14c`).

<a id="qué-hace"></a>


## What are you doing?

- **For what:** from your sandbox, the app does not see `/mnt`, and the user's USB drives are in `/mnt/usb0`.. `/mnt/usb7`. The ROOT mode asks GoldHEN the jailbreak of its SDK before it starts Wine, and the disks appear as units of Windows.
- **Optional:** without choosing ROOT, the start is the usual (NORMAL), without jailbreak and without USB units.
- **Requirement:** GoldHEN with the command of SDK (syscall 500). Tested at the user's PS4 Pro (informed firmware 12.52). Without GoldHEN, the order fails with its code in the log and the app starts the same, without units.

<a id="cómo-se-elige"></a>


## How to choose

On the loading screen, under the logo, there are two boxes:

| | NORMAL | ROOT |
|---|---|---|
|Position|left, chosen from entry|right|
|What's up?|the app sandbox, without USB disks|GoldHEN jailbreak, USB disks like D: a K:|

- **Change:** left or right on the cruise or left stick.
- **Start:** X starts in the act. If you do not squeeze X, start with what you choose at 2,5 s, and each change gives 2,5 s more to confirm.
- **The X that opened the app does not count:** the first reading of the command only records what is already tight.
- **No control:** starts NORMAL at the act.
- **Programs that restart the title** (those of 32 bits, initiated from the desktop): the title restarts without asking and uses the mode of the first start, stored in `/data/orbis-win/boot-mode.txt`.

<a id="qué-pasa-en-root"></a>


## What's going on in ROOT

1. **Jailbreak:** before Wine (just before joining `system.reg`), the launcher calls the command 2 of SDK of GoldHEN, which keeps the original credentials in a back.
2. **Turn to the user of the app:** immediately, `setuid` to the back-up (the 1, the app). The root of the process remains the console and without prison, so `/mnt` remains visible.
   - In W227, Wine ran as a $0 and stopped at `wineserver: lstat /data/wine-prefix/.wineserver/server-…: Permission denied`.
   - `.wineserver` is the folder of Wine, in 0700 mode and of the uid 1. In this console, the 0 uid of GoldHEN does not skip the file permissions.
   - In addition, Wine running as 0 would leave in the prefix files of the 0 uid that a NORMAL boot could not use.
3. **If the `setuid` fails:** the jailbreak is undone and the app starts as NORMAL, without units, with the motive in the log.
4. **When you leave:** the jailbreak is undone with the command 3 and the back. It happens when you leave (`exit`, `_exit`), if the app falls, and before every `sceSystemServiceLoadExec` (the reboot for a program of 32 bits). If that restart fails, the jailbreak is asked again. The credentials end with the process anyway; so the closure and reboot that the app asks for comes out of the sandbox, as without ROOT.

<a id="unidades"></a>


## Units

| Ranura |Unit|
|---|---|
| `/mnt/usb0` |D:|
| `/mnt/usb1` |E:|
| … | … |
| `/mnt/usb7` |K:|

- **Fixed letters per slot:** a disk in usb1 is E: although D: is free. In W228, Vice City was in usb1 and started from `E:\PC\…`.
- **Only slots with a disk:** J001 showed that, with the jailbreak, usb0.. usb7 exist always, and the empty are folders of the same device that `/mnt`. A slot counts as a unit when its `st_dev` is different from that of `/mnt`. Without the jailbreak, `/mnt` does not exist and no letters appear.
- **No hot connection:** the letters are assembled once, when starting Wine. A connected disk then appears in the next boot. You have to connect the disk before you open the app.
- **Access as uid 1:** the app reads the disks with its own user, not as root. In W228 you could read the disk and load Vice City.
  - Writing on the disk was not tested, and depends on how the console mounted the disk.
  - Vice City saves the settings and games in My documents (C:), so you don't need to write on the disk.
- **Type and label:** nothing was added. Wine Treat the unit as a fixed disk, not removable, and the console does not inform the volume name.

<a id="programas-desde-d-a-k"></a>


## Programs from D: to K:

A program initiated from the desktop restarts the title with its route of Windows (W043, `/data/orbis-win/next.txt`). This is also worth `launch.txt`. Before, the launcher only accepted C: in two places; now `windows_unix_path()` passes D:.. K: a `/mnt/usb0`.. `/mnt/usb7`:

- `pe_machine`, which reads the PE header to choose the start of 32 bits;
- the initial program folder (`PW_PROGRAM_DIR`, W130).

<a id="líneas-del-log"></a>


## Log lines

|Line|What does it say?|
|---|---|
| `PWJB mode=normal\|root source=screen pad=… confirmed=… changes=… waited_ms=…` |the on-screen choice|
| `PWJB mode=… source=relaunch` |the mode taken from the first start|
| `PWJB jailbreak rc=… errno=… uid=… mnt_usb0=…` |the command 2 of GoldHEN|
| `PWJB identity setuid=1 rc=… errno=… uid=… euid=… wineserver_lookup=…` |the return to the user of the app; `wineserver_lookup=2` (ENOENT) means that the folder of Wine can be traveled, and 13 that not|
| `PWJB unjailbreak who=exit\|_exit\|crash\|switch_program\|identity rc=… uid=…` |the undone jailbreak|
| `PWDRIVE e: -> /mnt/usb1 dev=…` |an armed USB drive|

<a id="cómo-se-llegó"></a>


## How it got here

- **J001** (probe `ORBB00001`, `native/mnt_probe.c`, `tools/build-mnt-probe.py`): from the sandbox, `/mnt` and `/mnt/usb*` give ENOENT. With the jailbreak, uid 0 and `/mnt` list `usb0`.. `usb7`, with two disks (usb0 and usb1). After you undo it, uid 1 and ENOENT again.
- **W227:** the choice and the jailbreak worked, and the units appeared (`PWDRIVE d:` and `e:`). Wine was stopped in the server folder (previous section).
- **W228:** with the return to uid 1, ROOT reaches the desktop, the disks are seen and Vice City loads from a USB SSD.

<a id="archivos"></a>


## Files

|File|Change|
|---|---|
| `native/wine_hardware.c` |The on-screen choice (`boot_choose`, `draw_choice`), the jailbreak and its back, `setuid` to the app user, and `windows_unix_path` to `pe_machine` and the initial folder.|
| `native/hw_pad.c` |The command opens only once (`pw_hw_pad_handle`) and is shared by the choice and the input thread. The title does not matter `scePadClose`, and a second `scePadOpen` of the same user fails. The input thread starts just with Wine, so what is pressed in the choice does not reach Wine.|
| `platform/ps4/pw_wine_fs.c` |The unit table adds D:.. K: for the slots with disk.|
| `native/mnt_probe.c`, `tools/build-mnt-probe.py` |The probe J001|
| `.deps/downloads/goldhen-sdk/` |Seven SDK files of GoldHEN (MIT license, `github.com/GoldHEN/GoldHEN_Plugins_SDK`), downloaded with user permission. The pitcher does not link the SDK: he makes the same call (syscall 500 for the indirect syscall 0) in his own code.|

<a id="pendiente"></a>


## Pending

- Prove if you can write on a USB disk as uid 1.
- Hot connection: the letters do not change without reboot.
- Removable type and volume label (W180, phase plan 10).
- The 32 bit retracted programs list units with kernelbase of 32 bit, which does not have the W105 patch of `GetLogicalDrives`.
