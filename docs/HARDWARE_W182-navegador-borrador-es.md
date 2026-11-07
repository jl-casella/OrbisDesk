# W182: registro de type libraries (fase 9, borrador)

[English](HARDWARE_W182-navegador-borrador.md) | [Español](HARDWARE_W182-navegador-borrador-es.md)

Borrador de la sesión lateral del navegador, para unir a `HARDWARE_W182.md`. Base W180. Nada de esto se probó en la consola.

## Qué pasó en W180

Reporte: `reports/wine-hardware-w180/physical/20261103T223018Z/`. El usuario vio que el WebView test y el navegador cierran la app.

- **crypt32 ya carga:** el log muestra `PWBOOT static_unixlib …/crypt32.so`. No aparece ninguna línea `PWCRYPT`. Las trazas salen sólo cuando se piden certificados raíz o PFX, y nada los pidió antes del fallo.
- **`webview64`** (`run-0001.log`, línea 1752 en adelante): Gecko arranca (cargan nss3, mozglue y xul) y después falla.
  1. `com_get_class_object class {33c53a50-f456-4884-b049-85fd643ecfed} not registered`. Es `CLSID_TF_InputProcessorProfiles`, de msctf (Text Services Framework). Gecko lo pide para la entrada de texto y, si no está, sigue con IMM. El log sigue después de esa línea, así que no es el fallo. No se registra.
  2. `mshtml:load_typelib LoadRegTypeLib failed: 8002801d` (`TYPE_E_LIBNOTREGISTERED`) y `preprocess_dispex_data Could not get disp type info`. mshtml no encuentra registrada su type library (`LIBID_MSHTML` 4.0), y sus datos de dispatch quedan vacíos.
  3. `c0000005` en `7FDA6EF03`, lectura de la dirección 8: mshtml usa esos datos vacíos.
  4. `call_seh_handlers invalid frame … NtRaiseException Exception frame is not in stack limits`. La excepción no se puede despachar y la app termina con `0xc0000005`.
- **Pale Moon** (`run-0002.log`): `map_view anon mmap error Invalid argument, size 0x40010000`. Es una reserva de 1 GB sin permisos que la consola rechaza. La sesión principal lo arregla en `virtual.c`; no es parte de este cambio.

## Cambio

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

## Verificación sin consola

Corrí una copia de `stage-mshtml-hw.py` que escribe en el scratchpad:
- 4192 claves en total, sin imports sin resolver.
- Ningún valor sellado reemplazado; 70 valores coinciden con los sellados.
- Las cuatro bibliotecas en las dos vistas: MSHTML 4.0 con 300 interfaces, MSXML2 3.0 con 65, SHDocVw 1.1 con 19 y stdole 2.0 con 3.
- Para stdole y SHDocVw, el nombre y `FLAGS` generados coinciden con los que ya tenía el prefijo sellado. Eso confirma que la lectura del formato MSFT es correcta.

## Construcción (orden)

1. `python3 -I tools/stage-mshtml-hw.py` → `out/mshtml-hw` (nuevo `system.reg.add`)
2. `python3 tools/build-wine-hardware.py`: sin cambios en el builder; el bloque de W177 agrega `system.reg.add` y verifica su hash.
3. `python3 -I tools/check-web-closure.py build/wine-hardware-w182/runtime`: tiene que terminar con 0.

## Prueba física

1. **WebView test (64-bit) y (32-bit):**
   - Ya no tiene que aparecer `LoadRegTypeLib failed` ni `Could not get disp type info`.
   - Se espera `local complete=yes`, `title "orbis-webtest"` y `es5 "es5-ok"`.
2. **Si vuelve a haber una excepción:** mirar si se repite `Exception frame is not in stack limits`. Si se repite, cualquier excepción en ese hilo (aunque Gecko o mshtml la manejen) cierra la app, y eso es un problema aparte del registro.

## No verificado

- Nada se probó en la consola.
- No se registró msctf (`CLSID_TF_InputProcessorProfiles`): Gecko sigue sin él.
- `Exception frame is not in stack limits` en un hilo de invitado no está explicado. El marco (`7FDD05BE0`) cae fuera de la pila del hilo (`204BC8000`-`204DC0000`).
