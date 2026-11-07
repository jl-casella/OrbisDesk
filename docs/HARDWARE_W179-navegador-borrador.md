<a id="w179-arreglos-del-navegador-y-webviews-fase-9-borrador"></a>


# W179: browser and webviews arrangements (phase 9, draft)

[English](HARDWARE_W179-navegador-borrador.md) | [Español](HARDWARE_W179-navegador-borrador-es.md)

Eraser of the browser side session, to join `HARDWARE_W179.md`. Base W177 (`docs/HARDWARE_W177.md`). None of this was tested on the console.

<a id="qué-pasó-en-w177"></a>


## What happened in W177

Report: `reports/wine-hardware-w177/physical/20261103T211906Z/`. Fixture result: `build/w177-webview-result.txt`.

1. **`webview64.exe`:** `ole`, `create` and `activate` gave `0x00000000`. The three navigations (`local`, `remote`, `back`) were in `ready_state=1` not completed in 30 s.
   - Cause (`run-0001.log`, line 1386 onwards): `xul.dll` of Wine Gecko did not load. It matters `wintrust.dll`, which matters `crypt32.dll`, which matters `bcrypt.dll` (it matters also `ncrypt.dll`). `bcrypt.dll` is not in the prefix in either view.
   - After: `mshtml:create_document_object Failed to init Gecko, returning CLASS_E_CLASSNOTAVAILABLE`.
   - The import review of W177 looked at a single level: `wintrust` was, but not what `wintrust` needed.
2. **Internet Explorer** (`run-0002.log`, lines 1060 - 1103: It starts as a guest, but `IEWinMain` records `CLSID_InternetExplorer` as a local server (`CLSCTX_SERVER`).
   - That's why ole32 has to serialize the class factory. It fails because there is no proxy/stub of `IServiceProvider` (`Failed to create ifstub, hr 0x80004002`), and it would also need rpcss (`start_rpcss Failed to open service manager`).
   - Neither exists in the model of a process. `iexplore` ends with state 1.
   - Explorer shows the same serialization error when starting (line 844), and that was already happening before phase 9.
3. **Pale Moon:** was not on the console (there is `Program Files/Pale Moon` in `ftp-list.txt`). With the fate of the missing direct access, the shell passed the `.lnk` same to `CreateProcess`, which rejects it (`PWOPEN reject_title_replacement`). No on-screen messages.
   - Pale Moon also matters `wintrust` and `crypt32`: with the installed copy it would have failed as well as Gecko.

<a id="cambio"></a>


## Change

|File|What are you doing?|
|---|---|
|`tools/build-bcrypt-x64.py` (new)|Compile `bcrypt.dll` of 64 bits, which the Wine tree of the host never linked. The `libsymcrypt.a` x86_64 of that tree has objects of an old build with clang, and clang before 19 disables the code by platform (`SYMCRYPT_IGNORE_PLATFORM`). That's why `cpuid.o` was empty and the link failed (`SymCryptDetectCpuFeaturesByCpuid`). The builder runs the exact commands of `compile_commands.json` with the Makefile compiler (`x86_64-w64-mingw32-gcc`), with output in `build/bcrypt-x64`, and then the file and link rules of the Makefile. He doesn't write on the host tree or change code. The crypt cryptography is SymCrypt (PE code), so it doesn't depend on a Unix side.|
| `tools/stage-mshtml-hw.py` |Add `bcrypt` in the two views (the 64 bit one leaves the new build). It also adds the DLL that `xul.dll` and `mozglue.dll` load in deferred: `psapi`, `winspool.drv`, `rasapi32`, `rasdlg` and `dbghelp`. One of those missing makes an exception on his first call. By closing it also enters `compstui` (from winspool). `winspool.drv` without Unix side equal load (your `DllMain` returns TRUE) and your printing calls fail.|
|`tools/check-web-closure.py` (new)|Walk all the imports, transitatively, on the built runtime. Search in the order of the charger: program folder, `system32` / `syswow64` and build folder. It covers Wine Gecko (both), mshtml/ieframe/jscript/iexplore (both views), fixtures and, optionally, a program folder such as the copy of Pale Moon. Deferred imports go separately. With `--staged` add the manager's output to each view, to review an arrangement before the build. Finish with 1 if there's anything missing.|

| `tools/build-wine-hardware.py` |One line: `tools/build-bcrypt-x64.py` in `source_hashes`. The W177 block already copies everything that lists `out/mshtml-hw/manifest.json`.|
| `tools/make-start-menu.py` |Without direct access "Internet Explorer" (see below). It changes the main session.|

<a id="verificación-sin-consola"></a>


## Console-free verification

- `build-bcrypt-x64.py` He ran and left. `out/bcrypt-x64`: 126 objects, 4,5 minutes. The `bcrypt.dll` is PE32+ of 2,9 MB, It matters only Advapi32, kernel32, ntdll and ucrtbase, and exports 56 functions `BCrypt*`.
- `stage-mshtml-hw.py` already ran and left `out/mshtml-hw`: 17 modules of 64 bits and 18 of 32 bits, no unsolved matter. The same 1770 registration keys, no sealed values replaced.
- `check-web-closure.py --staged out/mshtml-hw/x86_64-windows out/mshtml-hw/i386-windows build/wine-hardware-w178/runtime <Pale Moon 35.0.3>`: zero missing imports and zero missing deferred imports. Cover Gecko x86_64 (54 modules), Gecko x86 (55), mshtml in both views (29 and 29), fixtures (38) and Pale Moon (134.
- About W177 without the arrangement, the same check gives `bcrypt.dll` missing in all three cases, which is the error that the console gave.

<a id="construcción-orden"></a>


## Construction (order)

1. `python3 tools/build-bcrypt-x64.py` → `out/bcrypt-x64` repeat it only if the builder changes)
2. `python3 -I tools/stage-mshtml-hw.py` → `out/mshtml-hw`
3. `python3 tools/build-wine-hardware.py`
4. `python3 -I tools/check-web-closure.py build/wine-hardware-w179/runtime`: it has to end with 0.

Gecko doesn't change, so `stage-wine-gecko.py` you don't need to.

<a id="internet-explorer-no-soportado"></a>


## Internet Explorer: not supported

`iexplore.exe` cannot work in the model of a process and its direct access is from the Start menu.

- **Cause:** `IEWinMain` (`dlls/ieframe/iexplore.c` records `CLSID_InternetExplorer` with `CLSCTX_SERVER`, which includes local server (other process). For this, it is a way to increase the class factory, and it needs the proxy/stub of `IServiceProvider` and then rpcss, the service of the Wine PRC. There are neither of them here: there are no separate processes or service managers.
- **Results in W177:** `Failed to create ifstub, hr 0x80004002`, `failed to register CLSID_InternetExplorer: 80004002`, `start_rpcss Failed to open service manager`, and the program ends with state 1.
- **What continues to work:** IE control embedded in a program (WebView test). It creates the class in process and does not go through `IEWinMain`.
- **No attempt was made:** change `ieframe` to record only in process. It would replace the `ieframe.dll` that also uses the embedded control.
- `iexplore.exe` is still installed, because the associations of `mshtml.inf` (`.gif`, `.jpg`, `.htm`...) They name him. Open one of those double-click files fails as does the direct access.

<a id="prueba-física"></a>


## Physical test

1. **WebView test (64 -bit) and (32 -bit):** is expected `local complete=yes`, `title "orbis-webtest"`, `es5 "es5-ok"` and the visible page. With network: `remote complete=yes` with title.
2. **Pale Moon:** before, copy the `palemoon` folder from `.7z` a `wine-prefix/drive_c/Program Files/Pale Moon/`. Then follow the steps of `HARDWARE_W177.md`.
3. **In the log:** it does not have to appear `Library bcrypt.dll … not found` or `Failed to init Gecko`.

Without the copy of Pale Moon on the console, its direct access does nothing visible: the shell passes the `.lnk` to `CreateProcess`, which rejects it (`PWOPEN reject_title_replacement`).

<a id="no-verificado"></a>


## Not verified

- No W179 was tested on the console.
- It was not tested if Gecko's code calls for bcrypt functions that need more than SymCrypt.
- `make -n -B` (used to read the symcrypt commands) regenerated `config.status`, the Makefiles and `compile_commands.json` of the host tree with the same configuration arguments, and stepped `config.log`. Make redo the makfiles even if it is used `-n`. The lines that were compared to the Makefile (CC, symcrypt, bcrypt, FFMPEG) remained the same, and `include/config.h` did not change.
