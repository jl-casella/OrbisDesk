# W179: arreglos del navegador y webviews (fase 9, borrador)

[English](HARDWARE_W179-navegador-borrador.md) | [Español](HARDWARE_W179-navegador-borrador-es.md)

Borrador de la sesión lateral del navegador, para unir a `HARDWARE_W179.md`. Base W177 (`docs/HARDWARE_W177.md`). Nada de esto se probó en la consola.

## Qué pasó en W177

Reporte: `reports/wine-hardware-w177/physical/20261103T211906Z/`. Resultado del fixture: `build/w177-webview-result.txt`.

1. **`webview64.exe`:** `ole`, `create` y `activate` dieron `0x00000000`. Las tres navegaciones (`local`, `remote`, `back`) quedaron en `ready_state=1` sin completarse en 30 s.
   - Causa (`run-0001.log`, línea 1386 en adelante): `xul.dll` de Wine Gecko no cargó. Importa `wintrust.dll`, que importa `crypt32.dll`, que importa `bcrypt.dll` (también lo importa `ncrypt.dll`). `bcrypt.dll` no está en el prefijo en ninguna de las dos vistas.
   - Después: `mshtml:create_document_object Failed to init Gecko, returning CLASS_E_CLASSNOTAVAILABLE`.
   - La revisión de imports de W177 miraba un solo nivel: `wintrust` estaba, pero no lo que `wintrust` necesita.
2. **Internet Explorer** (`run-0002.log`, líneas 1060-1103): arranca como invitado, pero `IEWinMain` registra `CLSID_InternetExplorer` como servidor local (`CLSCTX_SERVER`).
   - Para eso ole32 tiene que serializar la fábrica de clases. Falla porque no hay proxy/stub de `IServiceProvider` (`Failed to create ifstub, hr 0x80004002`), y además necesitaría rpcss (`start_rpcss Failed to open service manager`).
   - Ninguno de los dos existe en el modelo de un proceso. `iexplore` termina con estado 1.
   - Explorer muestra el mismo error de serialización al arrancar (línea 844), y eso ya pasaba antes de la fase 9.
3. **Pale Moon:** no estaba en la consola (no hay `Program Files/Pale Moon` en `ftp-list.txt`). Con el destino del acceso directo ausente, el shell le pasó el `.lnk` mismo a `CreateProcess`, que lo rechaza (`PWOPEN reject_title_replacement`). No aparece ningún mensaje en pantalla.
   - Pale Moon también importa `wintrust` y `crypt32`: con la copia instalada habría fallado igual que Gecko.

## Cambio

| Archivo | Qué hace |
|---|---|
| `tools/build-bcrypt-x64.py` (nuevo) | Compila `bcrypt.dll` de 64 bits, que el árbol de Wine del host nunca enlazó. El `libsymcrypt.a` x86_64 de ese árbol tiene objetos de un build viejo con clang, y clang anterior a 19 desactiva el código por plataforma (`SYMCRYPT_IGNORE_PLATFORM`). Por eso `cpuid.o` quedó vacío y el enlace fallaba (`SymCryptDetectCpuFeaturesByCpuid`). El builder corre los comandos exactos de `compile_commands.json` con el compilador del Makefile (`x86_64-w64-mingw32-gcc`), con salida en `build/bcrypt-x64`, y después las reglas de archivo y enlace del Makefile. No escribe en el árbol del host ni cambia código. La criptografía de bcrypt es SymCrypt (código PE), así que no depende de un Unix side. |
| `tools/stage-mshtml-hw.py` | Agrega `bcrypt` en las dos vistas (el de 64 bits sale del builder nuevo). También agrega las DLL que `xul.dll` y `mozglue.dll` cargan en diferido: `psapi`, `winspool.drv`, `rasapi32`, `rasdlg` y `dbghelp`. Una de esas que falte lanza una excepción en su primera llamada. Por clausura entra también `compstui` (de winspool). `winspool.drv` sin Unix side carga igual (su `DllMain` devuelve TRUE) y sus llamadas de impresión fallan. |
| `tools/check-web-closure.py` (nuevo) | Recorre todos los imports, transitivamente, en el runtime construido. Busca en el orden del cargador: carpeta del programa, `system32`/`syswow64` y carpeta builtin. Cubre Wine Gecko (las dos), mshtml/ieframe/jscript/iexplore (las dos vistas), los fixtures y, opcionalmente, una carpeta de programa como la copia de Pale Moon. Los imports diferidos van aparte. Con `--staged` suma la salida del stager a cada vista, para revisar un arreglo antes del build. Termina con 1 si falta algo. |

| `tools/build-wine-hardware.py` | Una línea: `tools/build-bcrypt-x64.py` en `source_hashes`. El bloque de W177 ya copia todo lo que lista `out/mshtml-hw/manifest.json`. |
| `tools/make-start-menu.py` | Sin el acceso directo "Internet Explorer" (ver abajo). Lo cambia la sesión principal. |

## Verificación sin consola

- `build-bcrypt-x64.py` ya corrió y dejó `out/bcrypt-x64`: 126 objetos, unos 4,5 minutos. El `bcrypt.dll` es PE32+ de 2,9 MB, importa sólo advapi32, kernel32, ntdll y ucrtbase, y exporta 56 funciones `BCrypt*`.
- `stage-mshtml-hw.py` ya corrió y dejó `out/mshtml-hw`: 17 módulos de 64 bits y 18 de 32 bits, sin imports sin resolver. Las mismas 1770 claves de registro, sin valores sellados reemplazados.
- `check-web-closure.py --staged out/mshtml-hw/x86_64-windows out/mshtml-hw/i386-windows build/wine-hardware-w178/runtime <Pale Moon 35.0.3>`: cero imports faltantes y cero diferidos faltantes. Cubre Gecko x86_64 (54 módulos), Gecko x86 (55), mshtml en las dos vistas (29 y 29), los fixtures (38) y Pale Moon (134).
- Sobre W177 sin el arreglo, el mismo chequeo da `bcrypt.dll` faltante en los tres casos, que es el error que dio la consola.

## Construcción (orden)

1. `python3 tools/build-bcrypt-x64.py` → `out/bcrypt-x64` (hecho; repetirlo sólo si cambia el builder)
2. `python3 -I tools/stage-mshtml-hw.py` → `out/mshtml-hw` (hecho)
3. `python3 tools/build-wine-hardware.py`
4. `python3 -I tools/check-web-closure.py build/wine-hardware-w179/runtime`: tiene que terminar con 0.

Gecko no cambia, así que `stage-wine-gecko.py` no hace falta.

## Internet Explorer: no soportado

`iexplore.exe` no puede funcionar en el modelo de un proceso y su acceso directo sale del menú Start.

- **Causa:** `IEWinMain` (`dlls/ieframe/iexplore.c`) registra `CLSID_InternetExplorer` con `CLSCTX_SERVER`, que incluye servidor local (otro proceso). Para eso ole32 serializa la fábrica de clases, y necesita el proxy/stub de `IServiceProvider` y después rpcss, el servicio de RPC de Wine. Acá no hay ninguno de los dos: no hay procesos aparte ni administrador de servicios.
- **Resultado en W177:** `Failed to create ifstub, hr 0x80004002`, `failed to register CLSID_InternetExplorer: 80004002`, `start_rpcss Failed to open service manager`, y el programa termina con estado 1.
- **Lo que sigue funcionando:** el control de IE embebido en un programa (WebView test). Crea la clase en proceso y no pasa por `IEWinMain`.
- **No se intentó:** cambiar `ieframe` para que registre sólo en proceso. Reemplazaría el `ieframe.dll` que también usa el control embebido.
- `iexplore.exe` sigue instalado, porque las asociaciones de `mshtml.inf` (`.gif`, `.jpg`, `.htm`…) lo nombran. Abrir uno de esos archivos con doble clic falla igual que el acceso directo.

## Prueba física

1. **WebView test (64-bit) y (32-bit):** se espera `local complete=yes`, `title "orbis-webtest"`, `es5 "es5-ok"` y la página visible. Con red: `remote complete=yes` con título.
2. **Pale Moon:** antes, copiar la carpeta `palemoon` del `.7z` a `wine-prefix/drive_c/Program Files/Pale Moon/`. Después seguir los pasos de `HARDWARE_W177.md`.
3. **En el log:** no tiene que aparecer `Library bcrypt.dll … not found` ni `Failed to init Gecko`.

Sin la copia de Pale Moon en la consola, su acceso directo no hace nada visible: el shell le pasa el `.lnk` a `CreateProcess`, que lo rechaza (`PWOPEN reject_title_replacement`).

## No verificado

- Nada de W179 se probó en la consola.
- No se probó si el código de Gecko llama a funciones de bcrypt que necesiten algo más que SymCrypt.
- `make -n -B` (usado para leer los comandos de symcrypt) regeneró `config.status`, los Makefiles y `compile_commands.json` del árbol del host con los mismos argumentos de configure, y pisó `config.log`. Make rehace los makefiles aunque se use `-n`. Las líneas que se compararon del Makefile (CC, symcrypt, bcrypt, FFMPEG) quedaron iguales, y `include/config.h` no cambió.
