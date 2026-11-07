<a id="w108-renombrar-carpetas-y-borrar-árboles-desde-wfm"></a>


# W108: rename folders and delete trees from WFM

[English](HARDWARE_W108.md) | [Español](HARDWARE_W108-es.md)

APP_VER 02.07. W107 opened twice Desktop/test.txt with Notepad from Explorer and closed both guests with 0. The user reports that crear/borrar works, but does not rename folders or delete folders with subfolders. Logs: reports/wine-hardware-w107/physical/20261102T164857Z.

<a id="cambios"></a>


## Changes

pw_wine_rename expressly rejected directories with ENOTSUP. Now it solves origin and father of destination, checks the lengths of the saved routes and calls for real rename. After success, it updates the records of descriptors and cwd on both sides, including descendants and component limits. A failed operation doesn't change those records. It preserves the rejection of assembly roots. PWFS records route, return and errno. The builder compiles the adapter and exactly replaces a pw_wine_fs.o of the saved link, without modifying the base objects of the above evidence.

WFM reports errors of MoveFileW when renaming. The erasing uses real APIs Win32: lists children, closes the search handle and then recursively eliminates archivos/subcarpetas and the final directory. It does not follow any points, does not omit names by starting with point, rejects unit roots, checks lengths, attends cancellation and retains the first error. A partial elimination is not announced as a success. The user maintains the prior deletion confirmation. PWFM records the results; The dialogue shows the real failure.

This replaces the silent route SHFileOperation of erasing. The exact failure of that previous route was not identified by the logs; is not presented as a hardware-validated capacity.

<a id="construcción-y-comprobación"></a>


## Construction and verification

```sh
python3 tools/build-wfm.py
python3 tools/build-wine-hardware.py --mangohud enabled
python3 tools/upload-hardware.py --build W108 --host 192.168.68.104 --timeout 60
```

No local matrix. A timely check of the adapter in filesystem Linux passed: rename to more largo/corto with an open directory, continue openat/fchdir, correct cwd and preserve routes to failure. Evidence: build/w108-rename-check.c and build/w108-rename-check-linux.log. The first execution in DrvFS returned EACCES by moving an open directory; your log is preserved. The result of Linux to the kernel of PS4 is not extrapolated.

The fs-services diagnosis changes the historical case of rejection to a rename return. The historical reports of increments 14 - 18 are preserved and their expectation of rejection is no longer the current expectation.

In PS4, use only one user-created test folder: create padre/hijo/ grandson and a file, rename father, navigate the tree and delete it after confirming. Prove existing destination name: you must fail without overwriting content. Check Start and open a TXT/EXE to check the previous routes. Do not delete runtime fixtures or system folders during this test.

```sh
python3 tools/fetch-hardware.py --build W108 --host 192.168.68.104
```

Separate slope: the current desktop Wine only lists * .lnk. Show also files/folders will be the following improvement; It's not a filesystem ban.

Compilation completed, fuentes/manifiestos in releases. In the runtime it only changes wfm.exe compared to W107; The ELF incorporates the new FS object b9f7f2666464ac2a9f28e15e209c190289f789f11fc932f1e10e768461e70ff6. PKG SHA- 256: ec2dd685205f59c6e64c4a2b1b8f837a40670556cbd0cd2ae6df7f9715af1f02. ELF SHA- 256: 8aac41f3eaf694178c8c0d0e544ade7924ba305d63afad207eaa7f0d68961e9a.

Delivery completed with verified return reading: `/data/pkg/orbis-win-W108-ec2dd685205f.pkg`. Report: reports/wine-hardware-w108/transfers/20261102T170417Z.json. 548 verified files, 545 present and 3 uploaded; no permit failure. W107 withdrawn after verification. The user's pending physical test.
