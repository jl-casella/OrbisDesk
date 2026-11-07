<a id="w105-unidades-y-archivos-del-administrador-wfm"></a>


# W105: WFM administrator units and files

[English](HARDWARE_W105.md) | [Español](HARDWARE_W105-es.md)

APP_VER 02.04. The user reported Computer empty, without units or files. The independent calibration CPU/GPU is postponed; The metrics W104 are preserved.

<a id="cambios"></a>


## Changes

GetLogicalDrives of Wine normally lists the links of DosDevices on the server. Our title does not start mountmgr and the directory does not contain the units although the filesystem adapter already resolves C: and Z:. In mode WINE_PS4_GUESTS, kernelbase check the 26 roots DOS by GetFileAttributesW and announces only those that really exist as directories. Do not create fictitious units or return success for inaccessible roots. The overall route of Wine is kept out of that mode. PWFS records the obtained mask. It is compiled volume.o next to the previous guest patches.

WFM verifies the result of GetLogicalDriveStrings and FindFirstFile before using the data. List files without requiring FILE_ATTRIBUTE_ARCHIVE and filter directories by FILE_ATTRIBUTE_DIRECTORY. It records PWFM with the actual errors of access, listing and quantity of elements. Its MIT sources are parched in a copy; Checkout and attribution are preserved.

<a id="construcción-y-prueba-física"></a>


## Construction and physical testing

```sh
python3 tools/build-wfm.py
python3 tools/build-guest-hw.py
python3 tools/build-wine-hardware.py --mangohud enabled
python3 tools/upload-hardware.py --build W105 --host 192.168.68.104 --timeout 60
```

No local matrix, according to the current preference. In PS4: open File Manager, check Computer, enter C: and C:\orbis, return, close and reopen WFM. Check real names of carpetas/archivos and Start after closing. Z: it exposes the root that was already mounted by the adapter, its content remains subject to the actual permissions of the title. No files are modified or deleted when browsing.

After "I've already tried it," collect logs and check PWFS/PWFM and leave the guest:

```sh
python3 tools/fetch-hardware.py --build W105 --host 192.168.68.104
```

A compiled package does not credit visual correction. Build, transfer and physical result are recorded separately in reports/wine-hardware-w105.

Compilation completed. PKG SHA- 256: cb9543e2725cd77a35e48f3c2645fedd847c24c8e6380ab46edeec4c7154c6dd. ELF SHA- 256: d99dd240cdc8b7789890a23fd7f9f06d3113ecc0b58c62ddf62dba9ce039d43c. Sources and manifests archived in releases e-w105. The guest builder also reproduces ntdll and ucrtbase: its code sections match W104, only .build and .edata. Comparison in module-comparison.json.

Transfer completed with verified return reading: `/data/pkg/orbis-win-W105-cb9543e2725c.pkg`. Report: reports/wine-hardware-w105/transfers/20261102T143252Z.json. 548 verified runtime files, 539 present and 9 uploaded; no permit failure. W104 withdrawn after verification; local evidence preserved. pending of instalar/ejecutar manually and check the list in console.

<a id="resultado-físico-posterior"></a>


## Subsequent physical result

The user confirms visible drives and files. PWFS records 02000004 mask (C: and Z:). Downloaded session 20261102T145327Z. Open result.txt and vkspin64.txt causes switch_program with these documents, a new start c000007b and return to the desktop. W106 approaches the opening and keeps the list. reports/wine-hardware-w105/physical/20261102T145327Z/analysis.json. analysis
