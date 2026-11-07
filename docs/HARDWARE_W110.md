<a id="w110-entradas-omitidas-por-la-enumeración-de-wine"></a>


# W110: entries omitted by the listing of Wine

[English](HARDWARE_W110.md) | [Español](HARDWARE_W110-es.md)

APP_VER 02.09. The logs W109 already show the lock: the server sees koopa beach_fast .mid and CARMEN09.BMP, but WFM does not try DeleteFile for them. Just search the SMK child and then RemoveDirectory give 145. The ten reattempts find the same real entrance. Therefore, the pending closing hypothesis does not explain these attempts: there are files that did not reach the listing Win32.

Evidence: reports/wine-hardware-w109/physical/20261102T172145Z/analysis.json. The first start ended with 0; The second one was still on the desk when he picked up the logs. It was not validated renamed in this session. There was no erased by FTP.

<a id="cambios"></a>


## Changes

Only the Unix file object of ntdll is recombined with its proven recipe, from the saved source whose hash should match. The link is exactly one replaced without running the prepper or changing base objects.

- An identity without inode is not recorded or compared as an identity of a hidden directory (prefix/dev/proc). It is a protection against unavailable metadata of PS4, without inventing inode; It is not yet demonstrated that it is the cause of this particular omission.
- read_directory_data_readdir distinguishes EOF from error, preserves error and discards failed listing rather than publishing a partial list as success. WFM already retains the error before starting to erase children.
- PWDIRENUM records native entries, mask coincidences, stat errors, identity filtered and returned entries, in addition to the end of reading. The native parser records an invalid dirent or failure of getdents with its fields.
- WFM, documentos/EXE opening, rename, server audit and previous limited reattempt are preserved. Don't alter the desk in this building.

```sh
python3 tools/build-wine-directory-ps4.py
python3 tools/build-wine-hardware.py --mangohud enabled
python3 tools/upload-hardware.py --build W110 --host 192.168.68.104 --timeout 60
```

It requires the previous telemetry and spelling-server artifacts. Local matrix omitted. The deletion is not declared to be resolved before the test in a console.

Test: in WFM enter the failed folder and see if you list your files; repeat deleted from a test folder with subcarpetas/archivos. If you continue to fail, keep the tree and notify the code. Failed reading can now show a different error instead of 145; That will not be counted as a success.

```sh
python3 tools/fetch-hardware.py --build W110 --host 192.168.68.104
```

Desktop with files/folders, association icon for text links and refreshment follows as later work. The calibration CPU/GPU is postponed.

Compilation completed; runtime of 548 files identical to W109 per hash. The single replacement of the file object was verified and sources, manifest and recipe were archived in reports/wine-hardware-w110/release-w110. PKG SHA- 256: 982cf9c8ac3c32e51613c5c7fec7265a7a36c55e645e8e97326cfa6a4ce61639. ELF SHA- 256: fe94175937805e9ad255109c12290928c1b77c6d8f6fbe7a9fb91a598f4a8af6.

Delivery completed with verified return reading: `/data/pkg/orbis-win-W110-982cf9c8ac3c.pkg`. Report: reports/wine-hardware-w110/transfers/20261102T173510Z.json. 548 verified files, 546 present and 2 uploaded; no permit failure. W109 withdrawn after verification. The user's pending physical test.

First later notice: the collector W110 gave no-log in 20261102T173705Z. It was inspected FTP and found w109/run-0003.log new. Disloaded as W109 20261102T173750Z; The first line W109 entered_launcher. It was ordered to close OrbisDesk, install the PKG W110/02.09 and run. It's not evidence of execution or crash of W110. PKG W110 present in /data/pkg; no transfer was repeated.
