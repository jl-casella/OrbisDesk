<a id="w180-unix-side-de-crypt32-fase-9-borrador"></a>


# W180: Crypt32 Unix side (phase 9, draft)

[English](HARDWARE_W180-navegador-borrador.md) | [Español](HARDWARE_W180-navegador-borrador-es.md)

Eraser of the browser side session, to join `HARDWARE_W180.md`. Base W179. None of this was tested on the console.

<a id="qué-pasó-en-w179"></a>


## What happened in W179

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


## Change

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


## Construction (order)

1. `python3 tools/build-unixlibs-ps4.py` → `build/unixlibs-ps4` (adds `crypt32.o` to the report)
2. `python3 tools/link-wine-boot.py`: links all the report libraries and compiles `pw_wine_unixlibs.c`
3. the steps of the ELF hardware using the main session
4. `python3 tools/build-wine-hardware.py`
5. `python3 -I tools/check-web-closure.py build/wine-hardware-w180/runtime`: it has to end with 0. Check the imports of the PE, not the Unix sides.

`pw_crypt32_unix.c` only compiles `build-unixlibs-ps4.py`: `link-wine-boot.py` compiles a fixed list of `platform/ps4` files.

<a id="verificación-sin-consola"></a>


## Console-free verification

I only compiled crypt32 with a copy of `build-unixlibs-ps4.py` that you write on the scratchpad (WSL, `orbis-cc`):
- The two units compete without warning.
- The combined object defines `pw_crypt32_unix_call_funcs` and `pw_crypt32_unix_call_wow64_funcs` as global.
- Unix file routines (`open`, `opendir`, `readdir`, `fstat`) are redirected to those of `platform/ps4` (`pw_wine_open`...), as in the other libraries.

He didn't link the ELF.

<a id="prueba-física"></a>


## Physical test

1. **WebView test (64 -bit) and (32 -bit):** is expected `local complete=yes`, `title "orbis-webtest"` and `es5 "es5-ok"`.
2. **Pale Moon:** opens the local page and then real sites (see `HARDWARE_W177.md`).
3. **In the log:**
   - does not have to appear `crypt32.so … Dynamic loading not supported`, `Initialization of "crypt32.dll" failed` or `Failed to init Gecko`;
   - is expected `PWCRYPT x64 root_certs=none`, and `wow64` in the 32 bit.

<a id="no-verificado"></a>


## Not verified

- Nothing was tested on the console.
- There may be another block after crypt32 (another Unix side, memory, threads). To find it, `check-web-closure.py` only covers imports of PE.
