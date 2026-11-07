<a id="w182-reservas-grandes-y-type-libraries-para-el-navegador-fase-9-diagnóstico-de-apply-en-winecfg-íconos-de-control-panel-y-start-cuadrado-fase-7"></a>


# W182: large reserves and type libraries for the browser (phase 9), application diagnosis in winecfg, control icons Panel and square Start (phase 7)

[English](HARDWARE_W182.md) | [Español](HARDWARE_W182-es.md)

APP_VER 02.81. Base W181.

<a id="reservas-grandes-sin-memoria-navegador-fase-9"></a>


## Large no memory reserves (browser, phase 9)

`tools/build-audio-ps4.py`, `virtual.c`, `anon_mmap_alloc`, in Orbis only:
- **Before:** in W180, Pale Moon reserved 1 GiB without access (`size 0x40010000, unix_prot 0`), and the console rejected that `mmap` anonymous with `EINVAL`. Pale Moon stopped at a breakpoint (`0x80000003`) and closed the app.
- **Now:** a reserve `PROT_NONE` without fixed direction is ordered with `sceKernelReserveVirtualRange`, as is `pw_wine_anon_tryfixed` for fixed addresses. This is not the way it takes up memory, and the commitments find it the same as before.
- **If the kernel rejects it:** the `mmap` is tried as before and there is `PWVM reserve of … failed`.
- The 32 bit programs ask for memory with direction limits and follow by `map_free_area`; They don't change.

<a id="type-libraries-de-mshtml-fase-9-sesión-del-navegador"></a>


## MSHTML type libraries (phase 9, browser session)

<a id="qué-pasó-en-w180"></a>


### What happened in W180

Report: `reports/wine-hardware-w180/physical/20261103T223018Z/`. The user saw that the WebView test and the browser close the app.

- **crypt32 already loads:** the log shows `PWBOOT static_unixlib …/crypt32.so`. No line `PWCRYPT` appears. The traces come out only when root certificates or PFX are requested, and nothing asked for them before the failure.
- **`webview64`** (`run-0001.log`, line 1752 below): Gecko starts (cargan ns3, mozgue and xul) and then fails.
  1. `com_get_class_object class {33c53a50-f456-4884-b049-85fd643ecfed} not registered`. It is `CLSID_TF_InputProcessorProfiles`, of msctf (Text Services Framework). Gecko asks for text entry and, if it is not, still with IMM. The log's still after that line, so it's not the fault. It's not registered.
  2. `mshtml:load_typelib LoadRegTypeLib failed: 8002801d` (`TYPE_E_LIBNOTREGISTERED`) and `preprocess_dispex_data Could not get disp type info`. mshtml does not find its type library (`LIBID_MSHTML` 4.0) registered, and its dispatch data is empty.
  3. `c0000005` in `7FDA6EF03`, reading the address 8: mshtml uses these empty data.
  4. `call_seh_handlers invalid frame … NtRaiseException Exception frame is not in stack limits`. The exception cannot be sent and the app ends with `0xc0000005`.
- **Pale Moon** (`run-0002.log`): `map_view anon mmap error Invalid argument, size 0x40010000`. It is a reserve of 1 GB without permits that the console rejects. The main session is arranged in `virtual.c`; It's not part of this change.

<a id="cambio"></a>


### Change

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


### Console-free verification

I ran a copy of `stage-mshtml-hw.py` that he writes on the scratchpad:
- 4192 keys in total, no unsolved matter.
- No sealed value replaced; 70 values match the sealed.
- The four libraries in the two views: MSHTML 4.0 with 300 interfaces, MSXML2 3.0 with 65, SHDocVw 1.1 with 19 and with 2.0 with 3.
- For stle and SHDocVw, the name and `FLAGS` generated match those that already had the prefix sealed. This confirms that the MSFT format is correct.

<a id="construcción-orden"></a>


### Construction (order)

1. `python3 -I tools/stage-mshtml-hw.py` → `out/mshtml-hw` (new `system.reg.add`)
2. `python3 tools/build-wine-hardware.py`: no change in the building; the W177 block adds `system.reg.add` and verifies your hash.
3. `python3 -I tools/check-web-closure.py build/wine-hardware-w182/runtime`: it has to end with 0.

<a id="prueba-física"></a>


### Physical test

1. **WebView test (64 -bit) and (32 -bit):**
   - It no longer has to appear `LoadRegTypeLib failed` or `Could not get disp type info`.
   - It is expected `local complete=yes`, `title "orbis-webtest"` and `es5 "es5-ok"`.
2. **If there is an exception again:** see if it is repeated `Exception frame is not in stack limits`. If repeated, any exceptions in that thread (although Gecko or mshtml handle it) close the app, and that's a problem apart from the record.

<a id="no-verificado"></a>


### Not verified

- Nothing was tested on the console.
- No msctf (`CLSID_TF_InputProcessorProfiles`) was recorded: Gecko is still without him.
- `Exception frame is not in stack limits` in a guest thread is not explained. The frame (`7FDD05BE0`) falls outside the pile of the thread (`204BC8000` - `204DC0000`).

<a id="winecfg-control-panel-y-start-fase-7-sesión-de-accesos-directos"></a>


## winecfg, Control Panel and Start (phase 7, direct access session)

<a id="por-qué"></a>


### Why?

- In W180, winecfg was frozen by choosing a desktop integration theme and pressing Apply.
- The log in that Runs doesn't say what call he didn't come back. There are two suspicions:
  - `update_now` (repainted with `RDW_UPDATENOW`) in an endless loop, because a window of another thread continues to ask `WM_PAINT`;
  - several `broadcast_message` that deplete their timeout of 2 s, one behind the other, for each window that does not respond.
- W182 just add marks on the log to know which of the two is. It doesn't change the behavior.

<a id="cambios-de-diagnóstico"></a>


### Diagnostic changes

- `tools/build-winecfg-hw.py` (new): winecfg of Wine set with `PWCFG` marks to apply.
  - Each step of `PSN_APPLY` has `begin` and `end` with milliseconds: `settings`, `theme`, `shell_folders`, `sysparams`, `refresh`.
  - Within `theme`: `ApplyTheme` (stylish and unstyled) and `refresh_sysparams`.
  - Within `sysparams`: `SPI_SETNONCLIENTMETRICS` and `SetSysColors`.
  - It comes out `out/winecfg-hw/winecfg.exe` (sha256 `bc36725e…`), without warning.
  - `tools/build-wine-hardware.py` copies it over that of `out/wine-programs`, `lib/wine/x86_64-windows` and `system32`, just like `taskmgr-hw`. Check that the manifest comes from the current builder.
  - `winecfg.cpl` (W179) does not change: it is another program that starts `winecfg.exe`.
- `tools/build-win32u-ps4.py`, with revisions of `tools/paint-broadcast-diag-w182.patch.py`:
  - `dce.c` `update_now`: if the loop reaches 256 turns, one line per process: `PWPAINT update_now_loop hwnd child tid flags`;
  - `message.c` `broadcast_message`: measures each shipment; If a window spends all the timeout, `PWBCAST timeout msg hwnd tid elapsed_ms`, once by window and up to 32 windows.
  - Compilation: 47 units, no fault.

<a id="cambios-de-aspecto-pedidos-por-el-usuario"></a>


### Changes in appearance (user orders)

- **Icons in the control panel menu** (`tools/build-explorer-hw.py`).
  - Before, the elements of the Control Panel in the Start menu were coming out with the generic icon, because they are not files.
  - Now, if an element does not bring icon, explore it to your folder: `IShellFolder::GetUIObjectOf(IID_IExtractIconW)` and `GetIconLocation(GIL_FORSHELL)`.
    - If the location is a file, use `ExtractIconExW` with that index.
    - If it is `GIL_NOTFILENAME`, use `IExtractIconW::Extract`.
    - If everything fails, the generic icon of before remains.
  - Compilation: 44 reviews, without warning; `explorer.exe` sha256 `53d66e00…`.
- **Straight Start button on Moon and Noir** (`tools/build-msstyles-hw.py`).
  - The green button (Moon) and orange (Noir) had the right edge rounded, as in XP. Now it's straight from both sides.
  - `SizingMargins = 4, 4, 12, 12`.
  - Recompiled: Moon `e316876118aaa794`, Noir `a6a299a396a26ff5`, 35 bitmaps each drawn.
  - Preview in `out/msstyles-preview/desktop-luna.png` and `desktop-noir.png`.

<a id="prueba-en-la-consola"></a>


### Test on the console

1. winecfg → Desktop integration → choose Moon → Apply.
2. In the log:
   - the last line `PWCFG … begin` that does not have its `end` says what call does not return;
   - `PWPAINT` says which window keeps the repainted in loop;
   - `PWBCAST` says which windows are draining the 2.
   - If Apply ends well, all the marks have `end`, and the milliseconds say what step it takes.
3. Home Menu → Control panel: each item with its own icon.
4. With Moon or Noir: the Start button without the right curve.

<a id="pendiente"></a>


### Pending

- The arrangement of the freezing is left for W183, according to what these marks say.

<a id="nota-sobre-nativehw_padc"></a>


## Note on `native/hw_pad.c`

The direct access session changed `hw_pad.c` at 19: 51: 39, while it was built W182. Add a key count in the profiles: a key with two sources (cross and stick up, for example) is released only when the last one is released.
- `build-wine-hardware.py` had already compiled `hw_pad.o` at the start of the pass, about 19: 49, so **W182 is the previous `hw_pad.c`**.
- The hash of `native/hw_pad.c` in `source_hashes` of the W182 manifesto is calculated at the end and can correspond to the new file, not the compiled file.
- The arrangement enters W183.

<a id="prueba-física-1"></a>


## Physical test

Report: `reports/wine-hardware-w182/physical/20261103T230134Z/`. User response: "1 was rendered (not coves, not run es2020), 2 crash, 3 ok, 4 freeze."

- **WebView test:** page is seen; It's the first time the embedded control has worked. ES2020 does not run, as expected with Gecko 2.47. Canvas is not walking; It's about to be seen if it's for the acceleration off.
- **Pale Moon:**
  - The `mozglue.dll` of Gecko, who carried the WebView test before, is still loaded. When it starts Pale Moon, its import of `mozglue.dll` is resolved against it by name: `No implementation for mozglue.dll.?DllBlocklist_CheckStatus…`, then `unimplemented function mozglue.dll.?Now@TimeStamp…` and aborts.
  - In one process you cannot live two DLL with the same name. The reserve of 1 GiB no longer appears.
- **Panel Control icons:** well.
- **winecfg:** is frozen.
  - PWCFG markers: `settings` 0 ms, `theme` 216 ms, `shell_folders` 11 ms, `sysparams` 145 ms. Then there are seven. `open_mountmgr failed` and nothing else; never shows up `step=refresh`.
  - There was neither `PWPAINT` nor `PWBCAST`.
  - The block is between `sysparams` and the final update, in the unit part.
