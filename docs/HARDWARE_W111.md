<a id="w111-filtrar-registros-bsd-de-entradas-borradas"></a>


# W111: filter BSD records of deleted inputs

[English](HARDWARE_W111.md) | [Español](HARDWARE_W111-es.md)

APP_VER 02.10. W110 confirmed and collected in 20261102T174008Z: getdents returns CARMEN09.BMP and the previous name of a renamed folder, but stat fails with ENOENT. After the session, FTP SIZE/LIST does not find those names either; the parent folder ready only. And... The is_dir_empty server counted that residual name as content while ntdll omitted it by stat failure. It was not a closing wait or a really accessible file that WFM omitted to delete.

Evidence: reports/wine-hardware-w110/physical/20261102T174008Z/analysis.json and stat-missing-ftp.json. No files were modified by FTP during the investigation.

<a id="corrección-del-lector"></a>


## Reader's correction

The PS4 adapter copied each getdents record as an active input, without omitting d_fileno = 0. That filter is part of the semantic of readdir BSD: [FreeBSD implementation](https://github.com/freebsd/freebsd-src/blob/main/lib/libc/gen/readdir.c) and [confirmation of the criterion](https://lists.freebsd.org/archives/dev-commits-src-main/2026-February/039633.html). W110 did not print the residual record inode; its specific value in that session is not measured. W111 implements the missing contract and records skipped_unused to validate the actual case.

pw_dirent_record.h first valid header and length; a zero-inode slot is leapt along its length, without using its residual name. Also omits DT_WHT (14) as readdir BSD with DTF_HIDEW; It's not an active file. An active slot requires valid and finished name. A malformed record keeps EIO. The reader continues to an active input or the end, even between pages. It does not stat or pretend to be successful. The same correction serves ntdll and the in-process server that checks if a folder is empty. Store errno during the log of omitted slots.

The spread of W110 errors, as well as rename, textos/EXE opening, WFM and runtime PE, is preserved. Desktop remains the next job.

<a id="construcción-y-prueba"></a>


## Construction and testing

Timely check of the actual decoder: mixture of active inputs, deleted residual name, empty slot, whiteout and later valid input; rejects longitudes/nombres malformed. It happened in Linux, without touching the user's files. Source native/wine_dirent_record_check.c, result build/w111-dirent-check.log. No local matrix; actual result of PS4 pending.

```sh
gcc -Iplatform/ps4 native/wine_dirent_record_check.c -o build/w111-dirent-check
build/w111-dirent-check
python3 tools/build-wine-hardware.py --mangohud enabled
python3 tools/upload-hardware.py --build W111 --host 192.168.68.104 --timeout 60
```

It requires direct-ps4 and delete-server derivations already built and verified by hash. The builder reproduces the FS adapter that includes the decoder and explicitly replaces the object; does not modify Orbis or shadPS4.

Physical test: delete the folder that was empty; create a disposable tree, rename it, delete content and folder, and check that no old names or error 145 appear. Confirm Start and open a text later.

```sh
python3 tools/fetch-hardware.py --build W111 --host 192.168.68.104
```

Accept only with non-inode slot skips when they exist, rmdir real with rc = 0 and absence of the folder; not for a simulated response of is_dir_empty.

Compilation completed. Runtime of 548 files identical to W110; The new object FS was verified in the link. Sources, punctual and manifest test in reports/wine-hardware-w111/release-w111. PKG SHA- 256: e8585b70c409f7aca16093049940f9698ca9240f273bd37b34db7c56f859c16d. ELF SHA- 256: 060bb52333fd4b4687c3f67013003f273ff8d6fddd5cd1a4dff5904e99829f06.

Delivery completed with verified return reading: `/data/pkg/orbis-win-W111-e8585b70c409.pkg`. Report: reports/wine-hardware-w111/transfers/20261102T175415Z.json. 548 verified files, 546 present and 2 uploaded; no permit failure. W110 withdrawn after verification. The user's pending physical test.

<a id="resultado-físico-20261102t180132z"></a>


## Physical result: 20261102T180132Z

198 recorded omissions, all with inode = 0 (may include the same slot in repeated readings). is_dir_empty returns 1 and the rmdir native to the failed folder returns rc = 0. FTP later confirms that the folder no longer exists. The false 145 by deleted records is resolved in this real case.

Rename native also returns 0 by changing the folder from Documents to Where in the World is Carmen Sandiego. FTP confirms the absence of the old name and the presence of the new one with spaces. No errors of erasing are recorded. Analysis and verification FTP in reports/wine-hardware-w111/physical/20261102T180132Z/analysis.json.

Limits: no complete tree removal with active files is recorded in this session or the final output of the title. This case is missing to prove the full recursive operation; It doesn't take another building to prove it.

Subsequent user confirmation: "It erased everything correctly," after the application of crear/borrar tree with active content. This case is accepted by physical feedback. The download 20261102T180735Z did not add filesystem operations to the log; This discharge is not presented as an automatic test of the entire tree. Acceptance and sources of evidence in reports/wine-hardware-w111/physical/20261102T180735Z/acceptance.json. The arrangement is validated for the tested scenario; next priority, show files/folders and access correctly on the desktop.
