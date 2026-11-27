# Visual C++ runtime DLLs after a redistributable's uninstall (04.92)

[English](VCRUNTIME_FALLBACK.md) | [Español](VCRUNTIME_FALLBACK-es.md)

Game installers run Microsoft's Visual C++ redistributable (`vc_redist.x86.exe`, `vc_redist.x64.exe`) inside OrbisDesk through Wine's `msiexec`. The Rockstar Games Launcher does this, for example. The redistributable replaces Wine's copies of the runtime DLLs in `C:\windows\system32` and `C:\windows\syswow64` with Microsoft's. It shows in Add/Remove Programs (`appwiz.cpl`) and can be uninstalled there.

## What broke before 04.92

Uninstalling the redistributable deleted the DLLs it owned and put nothing back. So did a failed install that rolled back. Every program importing those DLLs then failed at load time with "DLL not found".

- **Uninstall.** Wine's MSI removes every file of a component it uninstalls. The only exception is a disk copy with a newer version than the package's (`dlls/msi/files.c`, `ACTION_RemoveFiles`). Microsoft's `vcruntime140.dll`, `concrt140.dll`, `vcomp140.dll` and the others go. Wine's `msvcp140.dll` (14.50) is newer than 14.44, so the redistributable never replaced it and its uninstall leaves it. But it imports `vcruntime140.dll`, so it fails to load too.
- **Rollback.** Wine's MSI does not back up the files it overwrites. The rollback of `InstallFiles` is `RemoveFiles`, run with each component's previous state (`dlls/msi/action.c`, `need_rollback`). For a first install that state is "absent". The rollback therefore deletes the DLLs it had just put over Wine's and restores nothing. Windows keeps a backup and restores it; Wine does not. When a later package of a Burn bundle fails, the bundle uninstalls the MSIs it already completed, which is the uninstall case above. This happened on the console with the Rockstar Games Launcher installer, before 04.80 fixed `GetExitCodeProcess` for guests.
- **No fallback in the loader.** This Wine's loader does not fall back to `lib/wine` for a DLL missing from the prefix. It does that only while the prefix is being bootstrapped (`dlls/ntdll/loader.c`, `find_builtin_without_file`). `lib/wine/<arch>-windows` holds no VC++ runtime anyway.
- **No repair.** The launcher's installer copied the build's files only on the first start of a build. A runtime uploaded over FTP was never repaired at all.

Evidence, console with GoldHEN and firmware 12.50, 2026-11-26, read-only FTP: the Rockstar Games Launcher installed the x86 redistributable 14.44.35211. `syswow64` held Microsoft's copies of `vcruntime140`, `concrt140`, `vcomp140`, `vccorlib140`, `msvcp140_1`, `msvcp140_atomic_wait`, `msvcp140_codecvt_ids` and `mfc140*`. Their components are registered to the Minimum and Additional Runtime products. `msvcp140.dll` and `msvcp140_2.dll` were still Wine's. `system32` was untouched: the x64 bundle registered but installed no MSI.

## The rule

The VC++ runtime files are the VC++ 2010–2022 families (versions 100 to 140) directly in `system32` and `syswow64`: `msvcp`, `msvcr`, `vcomp`, `vcruntime`, `concrt`, `vccorlib`, `vcamp`, `atl` and `mfc` (`tools/console_state.py`, `is_vcrt_file`). The W303 runtime has 45 of them, all Wine builtins, 24 MB. The 2005 and 2008 redistributables install into WinSxS, not there. `ucrtbase.dll` and `msvcrt.dll` are excluded: OrbisDesk revises them, and the redistributable does not install the UCRT on Windows 10.

A copy is Wine's when it carries winebuild's `Wine builtin DLL` signature after the DOS header. Anything else is a redistributable's copy.

- **The builder** (`tools/build-wine-hardware.py`) stops if one of them is not a Wine builtin: an OrbisDesk-shipped Microsoft copy would never be updated. It writes a second copy of each to `wine/lib/wine/vcrt-fallback/<system32|syswow64>/<name>`, with `wine/lib/wine/vcrt-fallback/list.txt` (`ORBISDESK-VCRT 1`, then `<sha256> <bytes> <folder>/<name>` per line). These are ordinary runtime files, in the package and in an FTP-uploaded runtime alike. No installer owns them, and Wine never loads them: its builtin search is `lib/wine/<arch>-windows/<name>` and `lib/wine/<name>`. The builder also writes the prefix copies as `V` lines in `install.txt`, and `vcrt_fallback` in the manifest.
- **On every start**, before Wine runs, the launcher (`native/hw_install.h`, `hw_install_vcrt_repair`) checks each file of `list.txt`. One missing from the prefix is copied back from `/data/wine/lib/wine/vcrt-fallback` and checked against the list's SHA-256. A present file is never touched. This runs whether the runtime came in the package (first install or up to date) or over FTP (`--runtime-outside-package`, "no_embedded_runtime").
- **When a new packaged build installs**, a `V` file that is not Wine's is kept, so Microsoft's DLLs stay while the redistributable is installed. Wine's copies are updated as before.
- **FTP uploads** (`tools/upload-hardware.py`) keep a prefix copy that is not Wine's in the same way. They upload the fallback copies like any other runtime file.

After an uninstall or a rollback, the DLLs are back on the next start of OrbisDesk. Programs started in the same session, after the uninstall, still fail until then. A console whose runtime predates this rule has no `list.txt`; the log shows `PWINSTALL vcrt no_fallback_list` and nothing is restored.

Restoring files at start was chosen over two alternatives:

- A loader fallback to `lib/wine` would change `ntdll` for every guest. It would also put loadable copies in `lib/wine/<arch>-windows`, which would win over a newer prefix copy.
- Making the uninstall or the rollback leave the files would mean changing Wine's MSI behavior for every package.

## Checks

```sh
python3 tests/test_vcrt_fallback_host.py build/wine-hardware-w303/runtime
```

This checks the name rule, the fallback path and the signature. It builds `tests/vcrt_fallback_host_check.c` against `native/hw_install.h` and runs it in temporary folders that stand in for `/app0/runtime` and `/data`:

- a new build keeps Microsoft's copy and installs the missing and older ones;
- after an uninstall, Wine's copy comes back and another Microsoft copy is untouched;
- after a rollback that deleted two copies, both come back;
- with no runtime in the package, a missing copy is still restored;
- a damaged fallback copy is refused by its hash, and nothing is written;
- with nothing missing, nothing is restored.

With a runtime folder, it also checks that every VC++ runtime file in it is a Wine builtin. It is a host model: it does not run Wine, MSI or the console.

On the console, with a build that carries this rule (packaged, or with its runtime uploaded):

1. Start OrbisDesk. The launcher log shows `PWINSTALL vcrt checked=45 present=45 restored=0`.
2. Uninstall: remove "Microsoft Visual C++ 2015-2022 Redistributable (x86)" in Add/Remove Programs.
3. Close OrbisDesk and start it again. The log shows `PWINSTALL vcrt restored syswow64/vcruntime140.dll` for each deleted DLL. Open a 32-bit program that imports `msvcp140.dll`/`vcruntime140.dll`.
4. Reinstall the redistributable, or the launcher that brings it, and check it installs again. On the next start, `restored=0`.
5. Rollback: start an installer that runs `vc_redist.x86.exe` and cancel it after the redistributable's files are copied, or let a later step fail. The installer's log shows the rollback. Then repeat step 3.
