<a id="w109-borrado-pendiente-y-diagnóstico-del-error-145"></a>


# W109: pending deletion and diagnosis of error 145

[English](HARDWARE_W109.md) | [Español](HARDWARE_W109-es.md)

APP_VER 02.08. The user confirmed that the 145 appeared when deleting folders with subfolders. W108 ended with 0 code, without a recorded crash. PWFM Unicode messages were not captured; The exact entry that blocked the operation is not yet known. LIST of FTP was archived, without changing content: Documents/Test was empty after the session. This is compatible with a delayed elimination, but does not demonstrate its cause.

Evidence W108: reports/wine-hardware-w108/physical/20261102T170507Z, including desktop-tree-after-error.json, remaining-tree-roots.json and remaining-directory-entries.json. No folders were deleted from the PS4 by FTP.

<a id="cambios"></a>


## Changes

- WFM retries only RemoveDirectory real before ERROR_DIR_NOT_EMPTY, maximum 10 expect 50 ms in worker. It does not redelete content that appears concurrently. Backup cancellation and fails if the folder does not disappear. No success is simulated and no mistakes are omitted.
- PWFM converts its Unicode messages to UTF- 8 by OutputDebugStringA, captured in the Wine channel, preserving GetLastError. It records each child, DeleteFile, retry and result, in addition to the existing dialogue.
- The native adapter records unlink/rmdir with route, return and errno.
- The server's fd object uses the proven recipe to record the first entry that blocks is_dir_empty and its result. It spreads errors of rewind/ readdir rather than treating them as empty. It does not change the base objects: it is compiled in build/delete-server-ps4, it reproduces the original units after checking their hashes and applies the same namespace. The combined object inprocess.o is exactly replaced by the binding; The originals are intact.

W108 rename and asociaciones/aperturas of W107/W106 are preserved. It is not claimed that the 145 is fixed until the test is repeated in a console.

```sh
python3 tools/build-wine-delete-server.py
python3 tools/build-wfm.py
python3 tools/build-wine-hardware.py --mangohud enabled
python3 tools/upload-hardware.py --build W109 --host 192.168.68.104 --timeout 60
```

No local matrix. In PS4: create a test folder with hijo/nieto and a file; Rename father, check navigation and delete confirming. If you fail, keep the folder for inspection and warn. Check Start at the end.

```sh
python3 tools/fetch-hardware.py --build W109 --host 192.168.68.104
```

<a id="consulta-de-desktop-siguiente-iteración"></a>


## Desktop consultation, next iteration

The user created test.lnk to test.txt and does not appear either. It was verified by FTP that both exist in Desktop. In addition to listing only * .lnk, the Explorer code discards a launcher if extract_icon does not get icon. Try to remove it from the .lnk or from the destination; a .txt does not contain PE icons. The following iteration should give an association / generic icon, expand files/folders and verify the directory's refreshment. Not to assume that the only failure is the notification of changes. This building keeps that job apart.

Compilation completed. The 45 server base objects were verified by hash before recombinating; the set of global symbols of the final object matches the original. In runtime it only changes wfm.exe. Sources, manifests and derivative server object documented in releases build-report.json. PKG SHA-256: 9968f1da041b182e5f541bf195204b4fd72148d2cda241a20e913000138fce45. ELF SHA-256: 0fcb12e585fb123ee46c172768559d6d2134dffd824ce8fdd1720745bd9c131c.

Delivery completed with verified return reading: `/data/pkg/orbis-win-W109-9968f1da041b.pkg`. Report: reports/wine-hardware-w109/transfers/20261102T172053Z.json. 548 verified files, 545 present and 3 uploaded; no permit failure. W108 withdrawn after verification. The user's pending physical test.
