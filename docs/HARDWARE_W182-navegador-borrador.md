<a id="w182-registro-de-type-libraries-fase-9-borrador"></a>


# W182: record of type libraries (phase 9, draft)

[English](HARDWARE_W182-navegador-borrador.md) | [Español](HARDWARE_W182-navegador-borrador-es.md)

Eraser of the browser side session, to join `HARDWARE_W182.md`. Base W180. None of this was tested on the console.

<a id="qué-pasó-en-w180"></a>


## What happened in W180

Report: `reports/wine-hardware-w180/physical/20261103T223018Z/`. The user saw that the WebView test and the browser close the app.

- **crypt32 already loads:** the log shows `PWBOOT static_unixlib …/crypt32.so`. No line `PWCRYPT` appears. The traces come out only when root certificates or PFX are requested, and nothing asked for them before the failure.
- **`webview64`** (`run-0001.log`, line 1752 below): Gecko starts (cargan ns3, mozgue and xul) and then fails.
  1. `com_get_class_object class {33c53a50-f456-4884-b049-85fd643ecfed} not registered`. It is `CLSID_TF_InputProcessorProfiles`, of msctf (Text Services Framework). Gecko asks for text entry and, if it is not, still with IMM. The log's still after that line, so it's not the fault. It's not registered.
  2. `mshtml:load_typelib LoadRegTypeLib failed: 8002801d` (`TYPE_E_LIBNOTREGISTERED`) and `preprocess_dispex_data Could not get disp type info`. mshtml does not find its type library (`LIBID_MSHTML` 4.0) registered, and its dispatch data is empty.
  3. `c0000005` in `7FDA6EF03`, reading the address 8: mshtml uses these empty data.
  4. `call_seh_handlers invalid frame … NtRaiseException Exception frame is not in stack limits`. The exception cannot be sent and the app ends with `0xc0000005`.
- **Pale Moon** (`run-0002.log`): `map_view anon mmap error Invalid argument, size 0x40010000`. It is a reserve of 1 GB without permits that the console rejects. The main session is arranged in `virtual.c`; It's not part of this change.

<a id="cambio"></a>


## Change

`tools/stage-mshtml-hw.py` records the type libraries as it would `RegisterTypeLib` (`dlls/oleaut32/typelib.c`), without running Wine.

1. **What does it read.** Take the resource `TYPELIB` 1 from each module and read the MSFT format (`dlls/oleaut32/typelib.h`): GUID, version, lcid, syskind and lags of the library, its name and its help text. From each type he reads the class, the lags, the GUID and the name.
2. **What libraries.** The four that ask for `LoadRegTypeLib` the modules that use the control:

   |Module|Library|Version|He's asking for it.|
   |---|---|---|---|
   | `mshtml.tlb` | MSHTML | 4.0 | mshtml |
   | `ieframe.dll` | SHDocVw | 1.1 | ieframe |
   | `stdole2.tlb` | stdole | 2.0 | jscript |
   | `msxml3.dll` | MSXML2 | 3.0 | msxml3 |

3. **What does he write?:**
   - `TypeLib\{libid}\<versión>`, shared by both views: the name (the help text if there is), `0\win64` with the route in `system32`, `0\win32` with the route in `syswow64` and `FLAGS`.
   - For each dispensing or oleautomation interface, `Interface\{iid}` in the two views: name, `ProxyStubClsid`, `ProxyStubClsid32` (`{00020424-…}`, or `{00020420-…}` for a dispestiface that is not dual) and `TypeLib` with `Version`.
   - The format copies the records that the sealed prefix already has. For example, stle 2.0 only has `0\win64` and `FLAGS="0"`, without `HELPDIR`, and SHDocVw interfaces have those same four entries.
4. **What was already untouched.** The sealed prefix already recorded stle 2.0 and SHDocVw (only for 64 bits), but not MSHTML or MSXML2. A value that the `system.reg` sealed already has is not replaced; For example, the own oleaut32 proxies for interfaces that it also declares.
5. **Set aside in the same file.** The comparison of `FLG_ADDREG_NOCLOBBER` with the sealed record never matched: it compared the name of the value without quotes, and in the parsed record is between quotes. Now compare in the same format.

mshtml also loads a private type library (`mshtml.dll\1`, with `LoadTypeLibEx`, without registration). This remedy exists in both buildings.

<a id="verificación-sin-consola"></a>


## Console-free verification

I ran a copy of `stage-mshtml-hw.py` that he writes on the scratchpad:
- 4192 keys in total, no unsolved matter.
- No sealed value replaced; 70 values match the sealed.
- The four libraries in the two views: MSHTML 4.0 with 300 interfaces, MSXML2 3.0 with 65, SHDocVw 1.1 with 19 and with 2.0 with 3.
- For stle and SHDocVw, the name and `FLAGS` generated match those that already had the prefix sealed. This confirms that the MSFT format is correct.

<a id="construcción-orden"></a>


## Construction (order)

1. `python3 -I tools/stage-mshtml-hw.py` → `out/mshtml-hw` (new `system.reg.add`)
2. `python3 tools/build-wine-hardware.py`: no change in the building; the W177 block adds `system.reg.add` and verifies your hash.
3. `python3 -I tools/check-web-closure.py build/wine-hardware-w182/runtime`: it has to end with 0.

<a id="prueba-física"></a>


## Physical test

1. **WebView test (64 -bit) and (32 -bit):**
   - It no longer has to appear `LoadRegTypeLib failed` or `Could not get disp type info`.
   - It is expected `local complete=yes`, `title "orbis-webtest"` and `es5 "es5-ok"`.
2. **If there is an exception again:** see if it is repeated `Exception frame is not in stack limits`. If repeated, any exceptions in that thread (although Gecko or mshtml handle it) close the app, and that's a problem apart from the record.

<a id="no-verificado"></a>


## Not verified

- Nothing was tested on the console.
- No msctf (`CLSID_TF_InputProcessorProfiles`) was recorded: Gecko is still without him.
- `Exception frame is not in stack limits` in a guest thread is not explained. The frame (`7FDD05BE0`) falls outside the pile of the thread (`204BC8000` - `204DC0000`).
