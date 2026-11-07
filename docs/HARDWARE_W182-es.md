# W182: reservas grandes y type libraries para el navegador (fase 9), diagnóstico de Apply en winecfg, íconos de Control Panel y Start cuadrado (fase 7)

[English](HARDWARE_W182.md) | [Español](HARDWARE_W182-es.md)

APP_VER 02.81. Base W181.

## Reservas grandes sin memoria (navegador, fase 9)

`tools/build-audio-ps4.py`, `virtual.c`, `anon_mmap_alloc`, sólo en Orbis:
- **Antes:** en W180, Pale Moon reservó 1 GiB sin acceso (`size 0x40010000, unix_prot 0`), y la consola rechazó ese `mmap` anónimo con `EINVAL`. Pale Moon se detuvo en un breakpoint (`0x80000003`) y cerró la app.
- **Ahora:** una reserva `PROT_NONE` sin dirección fija se pide con `sceKernelReserveVirtualRange`, igual que `pw_wine_anon_tryfixed` para direcciones fijas. Así no ocupa memoria, y los compromisos la encuentran igual que antes.
- **Si el kernel la rechaza:** se intenta el `mmap` como antes y queda `PWVM reserve of … failed`.
- Los programas de 32 bits piden memoria con límites de dirección y siguen por `map_free_area`; no cambian.

## Type libraries de MSHTML (fase 9, sesión del navegador)

### Qué pasó en W180

Reporte: `reports/wine-hardware-w180/physical/20261103T223018Z/`. El usuario vio que el WebView test y el navegador cierran la app.

- **crypt32 ya carga:** el log muestra `PWBOOT static_unixlib …/crypt32.so`. No aparece ninguna línea `PWCRYPT`. Las trazas salen sólo cuando se piden certificados raíz o PFX, y nada los pidió antes del fallo.
- **`webview64`** (`run-0001.log`, línea 1752 en adelante): Gecko arranca (cargan nss3, mozglue y xul) y después falla.
  1. `com_get_class_object class {33c53a50-f456-4884-b049-85fd643ecfed} not registered`. Es `CLSID_TF_InputProcessorProfiles`, de msctf (Text Services Framework). Gecko lo pide para la entrada de texto y, si no está, sigue con IMM. El log sigue después de esa línea, así que no es el fallo. No se registra.
  2. `mshtml:load_typelib LoadRegTypeLib failed: 8002801d` (`TYPE_E_LIBNOTREGISTERED`) y `preprocess_dispex_data Could not get disp type info`. mshtml no encuentra registrada su type library (`LIBID_MSHTML` 4.0), y sus datos de dispatch quedan vacíos.
  3. `c0000005` en `7FDA6EF03`, lectura de la dirección 8: mshtml usa esos datos vacíos.
  4. `call_seh_handlers invalid frame … NtRaiseException Exception frame is not in stack limits`. La excepción no se puede despachar y la app termina con `0xc0000005`.
- **Pale Moon** (`run-0002.log`): `map_view anon mmap error Invalid argument, size 0x40010000`. Es una reserva de 1 GB sin permisos que la consola rechaza. La sesión principal lo arregla en `virtual.c`; no es parte de este cambio.

### Cambio

`tools/stage-mshtml-hw.py` registra las type libraries como lo haría `RegisterTypeLib` (`dlls/oleaut32/typelib.c`), sin ejecutar Wine.

1. **Qué lee.** Toma el recurso `TYPELIB` 1 de cada módulo y lee el formato MSFT (`dlls/oleaut32/typelib.h`): GUID, versión, lcid, syskind y flags de la biblioteca, su nombre y su texto de ayuda. De cada tipo lee la clase, los flags, el GUID y el nombre.
2. **Qué bibliotecas.** Las cuatro que piden por `LoadRegTypeLib` los módulos que usa el control:

   | Módulo | Biblioteca | Versión | La pide |
   |---|---|---|---|
   | `mshtml.tlb` |MSHTML| 4.0 |mshtml|
   | `ieframe.dll` |SHDocVw| 1.1 |ieframe|
   | `stdole2.tlb` |stdole| 2.0 |jscript|
   | `msxml3.dll` |MSXML2| 3.0 |msxml3|

3. **Qué escribe:**
   - `TypeLib\{libid}\<versión>`, compartida por las dos vistas: el nombre (el texto de ayuda si lo hay), `0\win64` con la ruta en `system32`, `0\win32` con la ruta en `syswow64` y `FLAGS`.
   - Para cada dispinterface o interfaz oleautomation, `Interface\{iid}` en las dos vistas: nombre, `ProxyStubClsid`, `ProxyStubClsid32` (`{00020424-…}`, o `{00020420-…}` para una dispinterface que no es dual) y `TypeLib` con `Version`.
   - El formato copia el de los registros que el prefijo sellado ya tiene. Por ejemplo, stdole 2.0 sólo tiene `0\win64` y `FLAGS="0"`, sin `HELPDIR`, y las interfaces de SHDocVw tienen esas mismas cuatro entradas.
4. **Lo que ya había no se toca.** El prefijo sellado ya registraba stdole 2.0 y SHDocVw (sólo para 64 bits), pero no MSHTML ni MSXML2. Un valor que el `system.reg` sellado ya tiene no se reemplaza; por ejemplo, los proxies propios de oleaut32 para interfaces que stdole también declara.
5. **Arreglo aparte en el mismo archivo.** La comparación de `FLG_ADDREG_NOCLOBBER` con el registro sellado nunca coincidía: comparaba el nombre del valor sin comillas, y en el registro parseado está entre comillas. Ahora compara en el mismo formato.

mshtml también carga una type library privada (`mshtml.dll\1`, con `LoadTypeLibEx`, sin registro). Ese recurso existe en los dos builds.

### Verificación sin consola

Corrí una copia de `stage-mshtml-hw.py` que escribe en el scratchpad:
- 4192 claves en total, sin imports sin resolver.
- Ningún valor sellado reemplazado; 70 valores coinciden con los sellados.
- Las cuatro bibliotecas en las dos vistas: MSHTML 4.0 con 300 interfaces, MSXML2 3.0 con 65, SHDocVw 1.1 con 19 y stdole 2.0 con 3.
- Para stdole y SHDocVw, el nombre y `FLAGS` generados coinciden con los que ya tenía el prefijo sellado. Eso confirma que la lectura del formato MSFT es correcta.

### Construcción (orden)

1. `python3 -I tools/stage-mshtml-hw.py` → `out/mshtml-hw` (nuevo `system.reg.add`)
2. `python3 tools/build-wine-hardware.py`: sin cambios en el builder; el bloque de W177 agrega `system.reg.add` y verifica su hash.
3. `python3 -I tools/check-web-closure.py build/wine-hardware-w182/runtime`: tiene que terminar con 0.

### Prueba física

1. **WebView test (64-bit) y (32-bit):**
   - Ya no tiene que aparecer `LoadRegTypeLib failed` ni `Could not get disp type info`.
   - Se espera `local complete=yes`, `title "orbis-webtest"` y `es5 "es5-ok"`.
2. **Si vuelve a haber una excepción:** mirar si se repite `Exception frame is not in stack limits`. Si se repite, cualquier excepción en ese hilo (aunque Gecko o mshtml la manejen) cierra la app, y eso es un problema aparte del registro.

### No verificado

- Nada se probó en la consola.
- No se registró msctf (`CLSID_TF_InputProcessorProfiles`): Gecko sigue sin él.
- `Exception frame is not in stack limits` en un hilo de invitado no está explicado. El marco (`7FDD05BE0`) cae fuera de la pila del hilo (`204BC8000`-`204DC0000`).

## winecfg, Control Panel y Start (fase 7, sesión de accesos directos)

### Por qué

- En W180, winecfg se congeló al elegir un tema en Integración de escritorio y apretar Aplicar.
- El log de esa corrida no dice qué llamada no volvió. Hay dos sospechas:
  - `update_now` (repintado con `RDW_UPDATENOW`) en un bucle sin fin, porque una ventana de otro hilo sigue pidiendo `WM_PAINT`;
  - varios `broadcast_message` que agotan su timeout de 2 s, uno detrás de otro, por cada ventana que no responde.
- W182 solo agrega marcas en el log para saber cuál de las dos es. No cambia el comportamiento.

### Cambios de diagnóstico

- `tools/build-winecfg-hw.py` (nuevo): winecfg del Wine fijado con marcas `PWCFG` en Aplicar.
  - Cada paso de `PSN_APPLY` tiene `begin` y `end` con milisegundos: `settings`, `theme`, `shell_folders`, `sysparams`, `refresh`.
  - Dentro de `theme`: `ApplyTheme` (con estilo y sin estilo) y `refresh_sysparams`.
  - Dentro de `sysparams`: `SPI_SETNONCLIENTMETRICS` y `SetSysColors`.
  - Sale `out/winecfg-hw/winecfg.exe` (sha256 `bc36725e…`), sin advertencias.
  - `tools/build-wine-hardware.py` lo copia sobre el de `out/wine-programs`, en `lib/wine/x86_64-windows` y en `system32`, igual que `taskmgr-hw`. Comprueba que el manifest venga del builder actual.
  - `winecfg.cpl` (W179) no cambia: es otro programa que arranca `winecfg.exe`.
- `tools/build-win32u-ps4.py`, con revisiones de `tools/paint-broadcast-diag-w182.patch.py`:
  - `dce.c` `update_now`: si el bucle llega a 256 vueltas, una sola línea por proceso: `PWPAINT update_now_loop hwnd child tid flags`;
  - `message.c` `broadcast_message`: mide cada envío; si una ventana gasta todo el timeout, `PWBCAST timeout msg hwnd tid elapsed_ms`, una vez por ventana y hasta 32 ventanas.
  - Compilado: 47 unidades, ninguna falla.

### Cambios de aspecto (pedidos por el usuario)

- **Iconos en el menú Panel de control** (`tools/build-explorer-hw.py`).
  - Antes, los elementos del Panel de control en el menú Inicio salían con el icono genérico, porque no son archivos.
  - Ahora, si un elemento no trae icono, explorer se lo pide a su carpeta: `IShellFolder::GetUIObjectOf(IID_IExtractIconW)` y `GetIconLocation(GIL_FORSHELL)`.
    - Si la ubicación es un archivo, usa `ExtractIconExW` con ese índice.
    - Si es `GIL_NOTFILENAME`, usa `IExtractIconW::Extract`.
    - Si todo falla, queda el icono genérico de antes.
  - Compilado: 44 revisiones, sin advertencias; `explorer.exe` sha256 `53d66e00…`.
- **Botón Inicio recto en Luna y Noir** (`tools/build-msstyles-hw.py`).
  - El botón verde (Luna) y naranja (Noir) tenía el borde derecho redondeado, como en XP. Ahora es recto de los dos lados.
  - `SizingMargins = 4, 4, 12, 12`.
  - Recompilados: Luna `e316876118aaa794`, Noir `a6a299a396a26ff5`, 35 bitmaps dibujados cada uno.
  - Vista previa en `out/msstyles-preview/desktop-luna.png` y `desktop-noir.png`.

### Prueba en la consola

1. winecfg → Integración de escritorio → elegir Luna → Aplicar.
2. En el log:
   - la última línea `PWCFG … begin` que no tiene su `end` dice qué llamada no vuelve;
   - `PWPAINT` dice qué ventana mantiene el repintado en bucle;
   - `PWBCAST` dice qué ventanas agotan los 2 s.
   - Si Aplicar termina bien, todas las marcas tienen `end`, y los milisegundos dicen qué paso tarda.
3. Menú Inicio → Panel de control: cada elemento con su propio icono.
4. Con Luna o Noir: el botón Inicio sin la curva a la derecha.

### Pendiente

- El arreglo del congelamiento queda para W183, según lo que digan estas marcas.

## Nota sobre `native/hw_pad.c`

La sesión de accesos directos cambió `hw_pad.c` a las 19:51:39, mientras se construía W182. Agrega un conteo por tecla en los perfiles: una tecla con dos fuentes (Cruz y el stick hacia arriba, por ejemplo) se suelta recién cuando se suelta la última.
- `build-wine-hardware.py` ya había compilado `hw_pad.o` al empezar el paso, cerca de las 19:49, así que **W182 lleva el `hw_pad.c` anterior**.
- El hash de `native/hw_pad.c` en `source_hashes` del manifiesto de W182 se calcula al final y puede corresponder al archivo nuevo, no al compilado.
- El arreglo entra en W183.

## Prueba física

Reporte: `reports/wine-hardware-w182/physical/20261103T230134Z/`. Respuesta del usuario: "1 se renderizó (no canvas, not run es2020), 2 crash, 3 ok, 4 freeze".

- **WebView test:** la página se ve; es la primera vez que funciona el control embebido. ES2020 no corre, como se esperaba con Gecko 2.47. Canvas no anda; está por verse si es por la aceleración apagada.
- **Pale Moon:**
  - El `mozglue.dll` de Gecko, que cargó antes la prueba WebView, sigue cargado. Cuando arranca Pale Moon, su import de `mozglue.dll` se resuelve contra ese por nombre: `No implementation for mozglue.dll.?DllBlocklist_CheckStatus…`, después `unimplemented function mozglue.dll.?Now@TimeStamp…` y aborta.
  - En un solo proceso no pueden convivir dos DLL con el mismo nombre. La reserva de 1 GiB ya no aparece.
- **Íconos de Control Panel:** bien.
- **winecfg:** se congela.
  - Marcadores PWCFG: `settings` 0 ms, `theme` 216 ms, `shell_folders` 11 ms, `sysparams` 145 ms. Después hay siete `open_mountmgr failed` y nada más; nunca aparece `step=refresh`.
  - No hubo `PWPAINT` ni `PWBCAST`.
  - El bloqueo está entre `sysparams` y la actualización final, en la parte de unidades.
