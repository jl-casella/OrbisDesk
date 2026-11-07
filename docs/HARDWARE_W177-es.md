# W177: limpieza de los diagnósticos de la carrera (fase 6), temas Luna y Noir (fase 7) y navegador (fase 9)

[English](HARDWARE_W177.md) | [Español](HARDWARE_W177-es.md)

APP_VER 02.76. Base W176. El resultado de W176 está en `docs/HARDWARE_W176.md`.

## Limpieza de los diagnósticos de memoria

El fallo de fin de carrera de SuperMarioKart quedó resuelto en W176. Se quitan los registros que se agregaron para encontrarlo (W170–W175), a pedido del usuario:

- **`tools/build-audio-ps4.py` (`virtual.c`):**
  - Sale el diagnóstico `PWVM fault` de `virtual_handle_fault` (W170/W171), con la consulta al kernel antes y después y el reintento único.
  - Salen los resúmenes `PWVM commit …` de cada compromiso de 1 MiB o más, con `flexible_free` y los totales de memoria directa, y sus contadores.
  - Sale la línea `commit_backing` de las 32 primeras páginas.
- **`tools/build-win32u-ps4.py` (`vulkan.c`):** salen `PWVK placed map` y `PWVK placed free` (W170). El desmapeo del alias vuelve a registrar sólo si falla, como en W169.

Quedan como trazas de error, porque sólo aparecen cuando algo falla:
- `PWVM direct map … failed` y `PWVM direct release … failed`;
- `PWVM commit_backing` cuando el mapeo de una página falla;
- `PWVM rereserve … falling back`;
- `PWVK placed unmap … failed`.

Los arreglos siguen igual: memoria directa en cero para los compromisos grandes, devolución al liberar, re-reserva, chequeo de región en el compromiso, guarda en `commit_reserved`, `TerminateThread(NULL)` y Mesa residente.

## Navegador y webviews (fase 9, sesión del navegador)

Depende de la fase 8 sólo para las páginas remotas. Desde W176 funcionan DNS, TCP, HTTP, UDP y los adaptadores en 64 y 32 bits. La página local y el control embebido se pueden probar sin red.

### Qué había (leído en el código y en el prefijo de W173)

1. **MSHTML no estaba instalado.** `mshtml`, `jscript`, `msxml3` e `iexplore` están compilados en `.deps/wine/runtime/build` (x86_64 e i386), pero no están ni en `system32` ni en `syswow64`. `ieframe`, `shdocvw`, `urlmon` y `wininet` sí están.
2. **Registro incompleto.** En `system.reg`, el control WebBrowser (`{8856F961-…}`, ieframe) está registrado sólo para 64 bits. mshtml y jscript no están registrados en ninguna de las dos vistas. Un programa de 32 bits busca las clases en `Classes\Wow6432Node\CLSID` y no encontraba ninguna de estas.
3. **Wine Gecko.** Wine 11.17 pide Gecko 2.47.4 (`dlls/appwiz.cpl/addons.c`). mshtml busca primero `HKLM\Software\Wine\MSHTML\2.47.4` `GeckoPath` (`dlls/mshtml/nsembed.c`, `find_wine_gecko_reg`). Si no lo encuentra, ejecuta `control.exe appwiz.cpl install_gecko` con `CreateProcess`, y eso no funciona en un título de un solo proceso.
4. **No hay TLS de Windows.** `SONAME_LIBGNUTLS` no está definido en el `config.h` de Orbis. schannel y bcrypt no tienen Unix side. Por eso MSHTML, wininet e `iexplore` no pueden abrir HTTPS. Pale Moon trae su propio TLS (NSS), así que no le afecta.
5. **Invitados de 64 bits.** El invitado comparte el dxgi builtin con explorer (fase 7), así que un navegador de 64 bits no puede usar D3D11 de DXVK. Además, `struct ps4_guest` guarda 64 hilos (`tools/build-guest-hw.py`). Si el programa crea más, los hilos de sobra no se registran y siguen corriendo después de que el invitado termina.

### Navegador elegido: Pale Moon 35.0.3 x64, sin incluirlo en el paquete

- Motor Goanna (UXP), de un proceso. Firefox actual y Chromium son multiproceso.
- La licencia de redistribución de Pale Moon (palemoon.org/redist.shtml) pide permiso previo de Moonchild Productions para incluirlo en un paquete más grande. También prohíbe cambiar sus archivos y sus preferencias por defecto. Por eso no va en el pkg. El usuario pone su copia en `C:\Program Files\Pale Moon\` (en la consola, `drive_c/Program Files/Pale Moon/` dentro del prefijo).
- Los accesos directos pasan un perfil propio con `-no-remote -profile …`. Las preferencias van en el `user.js` de ese perfil (`fixtures/browser/`) y no tocan Pale Moon.
- Hay dos perfiles:
  - `orbis`: sin aceleración. No usa D3D11, Direct2D, WebGL ni decodificación de video por GPU. Tampoco nada que abra otro proceso: plugins, plugin-container de GMP ni el actualizador. La memoria y la caché quedan acotadas.
  - `orbis-nojit`: el mismo perfil con el JIT de JavaScript apagado. Sirve para descartar que un fallo venga del JIT, que escribe código en memoria ejecutable.
- Revisión de imports, sin consola: `palemoon-35.0.3.win64.7z` (SHA-256 `745ba383…dbb65b`), todos los PE contra el `system32` de W173 y la carpeta builtin.
  - Faltan `usp10.dll`, `wsock32.dll` y `wtsapi32.dll`. Las tres están compiladas en el árbol fijado y ahora las instala `stage-mshtml-hw.py`.
  - `xul.dll` importa `d3d9.dll` de forma estática. Carga el d3d9 de DXVK, pero con la aceleración apagada no lo usa para componer.
- K-Meleon 76.5.5 (GPL/MPL) quedó como alternativa. Es sólo de 32 bits, así que correría como título relanzado, y es la única forma de tener D3D11 por DXVK. No se descargó.

### Webviews

- **MSHTML (IE de Wine) con Wine Gecko 2.47.4**, para 64 y 32 bits. Cubre los programas viejos que embeben el control de IE.
  - Gecko va donde lo pondría su `.msi`: `C:\windows\system32\gecko\2.47.4\wine-gecko-2.47.4-x86_64` y `syswow64\…\wine-gecko-2.47.4-x86`.
  - `GeckoPath` va en las dos vistas del registro. Un programa de 32 bits ve `syswow64` como `system32`.
  - Gecko ocupa unos 108 MB (x86_64) y 109 MB (x86) en el prefijo.
- **Sin HTTPS en MSHTML** (punto 4 de arriba). Sólo `file:`, `about:`, `res:` y `http:`.
- **Type libraries sin registrar** (`mshtml.tlb`, la de ieframe). Un programa que pida la type library a oleaut32 (scripts, VB6, marshaling entre apartments) recibe `TYPE_E_LIBNOTREGISTERED`. El control embebido desde C/C++ en el mismo hilo no la necesita.
- **WebView2 (Edge/Chromium): no soportado.** Abre procesos separados (browser, renderer, GPU) y aquí no hay procesos Windows aparte. No se instala nada para WebView2. Un programa que lo requiera falla al crear el entorno (`CreateCoreWebView2Environment`), con el error del cargador de WebView2.

### Cambio

| Archivo | Qué hace |
|---|---|
| `tools/stage-wine-gecko.py` (nuevo) | Verifica los dos tarballs por SHA-256, los extrae con chequeo de rutas (sólo archivos regulares dentro de `wine-gecko-2.47.4-<arch>/`) y comprueba que `VERSION` diga `Wine Gecko 2.47.4`. Escribe `out/wine-gecko/` con un manifiesto (hash de cada archivo y `builder_sha256`). |
| `tools/stage-mshtml-hw.py` (nuevo) | Copia mshtml, jscript, msxml3, mshtml.tlb, iexplore, usp10, wsock32, wtsapi32 y netapi32 (en 32 bits, también msimg32 y uxtheme, que importa Gecko x86), cada uno con su clausura de imports, salvo lo que ya está en el prefijo o en otro stager. Genera el registro COM como lo haría `DllRegisterServer`, sin ejecutar Wine: los scripts `WINE_REGISTRY` de los recursos de cada DLL (leídos como `dlls/atl/registrar.c`) y `mshtml.inf` (`RegInstall`, con los CLSID de `mshtml_classes.idl`, `mshtml.idl` y `mshtml_private.h`). En 32 bits, `CLSID` e `Interface` van a `Classes\Wow6432Node` y `HKLM\Software` a `Software\Wow6432Node`. No repite valores que el `system.reg` sellado ya tiene. |
| `fixtures/win32/webview.c` (nuevo) | `webview64.exe` y `webview32.exe`. Ver abajo. |
| `fixtures/web/index.html` (nuevo) | Página local de prueba: un script ES5 (`#es5`), uno ES2020 (`#es2020`), canvas, grid, flex, user agent y tiempo de los scripts. Los dos scripts van separados: un error de sintaxis en el ES2020 no frena el ES5. |
| `fixtures/browser/palemoon-user.js`, `palemoon-nojit-user.js` (nuevos) | Los dos perfiles de Pale Moon. |
| `tools/make-start-menu.py` | Carpeta `Programs/Internet`: Pale Moon, Pale Moon (no JIT), Internet Explorer (abre la página local), WebView test (64-bit) y WebView test (32-bit). |
| `tools/build-guest-hw.py` | `struct ps4_guest` guarda 256 hilos en lugar de 64. Si se llena, deja `PWGUEST thread_overflow module=… count=…`. |
| `tools/build-wine-hardware.py` | Instala MSHTML y Gecko, agrega `GeckoPath` y `system.reg.add`, compila los dos fixtures, copia la página a `C:\orbis\webtest` y crea los dos perfiles en `C:\users\orbis\AppData\Roaming\Moonchild Productions\Pale Moon\Profiles\`. |
| `THIRD_PARTY.md` | Wine Gecko (MPL-2.0, sin modificar) y por qué Pale Moon no va incluido. |

Los cambios en los tres builders compartidos están aplicados (W177 go). No hay cambios en `platform/ps4` ni en el ELF.

<a id="fixture-webview64exe--webview32exe"></a>


### Fijación `webview64.exe` / `webview32.exe`

Es un contenedor OLE mínimo (client site, in-place site y frame de una ventana) con el control WebBrowser adentro. Cada paso agrega una línea a `C:\orbis\webview-result.txt` con su HRESULT:

|Paso| Qué prueba |
|---|---|
| `ole` | `OleInitialize` |
| `create` | `CoCreateInstance(CLSID_WebBrowser)`: el registro de la clase en la vista que corresponde |
| `activate` | `SetClientSite` y `DoVerb(OLEIVERB_INPLACEACTIVATE)` en la ventana |
| `local` | `Navigate2` a `C:\orbis\webtest\index.html` y mensajes hasta `READYSTATE_COMPLETE` (30 s como máximo), con estado y milisegundos |
| `title` | Título del documento. Se espera `orbis-webtest`; queda vacío si Gecko no cargó |
| `es5` | Texto de `#es5`. Se espera `es5-ok` si jscript corrió |
| `es2020` | Texto de `#es2020`. Se espera `not run`: jscript no tiene ES2020 |
| `remote` | La misma navegación al argumento 1 (`http://example.com/` por defecto; `-` lo saltea). Necesita red |

Un paso que no puede correr porque falló uno anterior queda como `skipped=…`, nunca como ok. La ventana queda abierta con la página hasta cerrarla. Compilado con mingw (`-O2 -Wall`, 64 y 32 bits): sin avisos. No se ejecutó.

### Construcción (orden)

1. `python3 -I tools/stage-wine-gecko.py` → `out/wine-gecko`
2. `python3 -I tools/stage-mshtml-hw.py` → `out/mshtml-hw`. Lee los manifiestos de `out/wine-pe64`, `wine-gui`, `wine-programs`, `wine-extras`, `wine-i386` y `dmsynth-i386`, así que va después de sus stagers.
3. `python3 tools/make-start-menu.py`
4. `python3 tools/build-guest-hw.py` (límite de hilos; recompila ntdll y kernelbase de invitados)
5. `python3 tools/build-wine-hardware.py`

No hace falta `link-wine-boot.py` ni `build-unixlibs-ps4.py`. La primera subida de W177 tarda más que las anteriores: Wine Gecko suma unos 217 MB.

Prueba en copia (escribiendo en el scratchpad): `stage-mshtml-hw.py` dio 10 módulos de 64 bits y 11 de 32 bits, sin imports sin resolver, 1770 claves y ningún valor sellado reemplazado. El control WebBrowser de 32 bits queda en `ieframe.dll`, como el de 64 bits que dejó wineboot. `make-start-menu.py` dio 20 accesos directos (antes 15). Los cuatro builders tocados compilan como Python; el C nuevo de `build-guest-hw.py` no se compiló (eso lo hace el propio builder).

### Qué buscar en el log

- `Could not find Wine Gecko. HTML rendering will be disabled.`: `GeckoPath` no se leyó o la carpeta no tiene el `VERSION` esperado.
- `Gecko can only be used from one thread.`: dos hilos usan MSHTML. Pasa si dos invitados de 64 bits usan el control a la vez, porque comparten el proceso.
- `PWGUEST thread_overflow`: el invitado pasó de 256 hilos (punto 5).
- `c0000135` al abrir Pale Moon: falta una DLL. La revisión de imports no encontró ninguna, pero `xul.dll` carga otras en tiempo de ejecución (`LoadLibrary`).

### No verificado / riesgos

- **Nada se probó en la consola** ni en una Wine de host.
- **`xul.dll` duplicado:** el `xul.dll` de Pale Moon y el de Gecko tienen el mismo nombre. Si un invitado usa MSHTML y Pale Moon está abierto, los dos estarían en el mismo proceso. No está claro qué hace el cargador de Wine con dos módulos del mismo nombre cargados por ruta completa.
- **mozglue engancha `LdrLoadDll`** (lista de bloqueo de DLL) en el ntdll del proceso, que es el de explorer. Si eso falla o queda enganchado después de cerrar el navegador, afecta a explorer.
- **Memoria:** la consola reporta unos 447 MB de memoria flexible para todo el título. Una página pesada puede no entrar.
- **Hilos:** en W177 el límite por invitado sube de 64 a 256. Si aun así se llena, queda `PWGUEST thread_overflow` en el log y ese hilo sigue corriendo después de que el invitado termina.
- **JIT:** SpiderMonkey cambia la protección de páginas ejecutables todo el tiempo. Si hay fallos en código generado, el perfil `orbis-nojit` sirve para separarlos.
- **Perfiles y subidas:** `upload-hardware.py` sube sólo los archivos del build. En cada perfil, eso es sólo `user.js`, que pertenece al build y se reemplaza en cada subida. Lo que escribe Pale Moon (`prefs.js`, historial, marcadores) no está en el build y se conserva. Una preferencia que se quiera mantener va en `prefs.js` (desde `about:config`), no en `user.js`.
- **Sin aceleración en 64 bits** mientras los invitados compartan el dxgi de explorer.

### Prueba física

Pendiente. Orden propuesto:

1. **Sin red:** WebView test (64-bit) y (32-bit). Se espera `create`/`activate` en 0, `local` completo, `title` = `orbis-webtest`, `es5` = `es5-ok`, y la página visible en la ventana. Después, Internet Explorer desde el menú: abre la página local.
2. **Con red** (W176: DNS, TCP, HTTP, UDP y adaptadores en 64 y 32 bits): el paso `remote` de los dos fixtures (`http://example.com/`).
3. **Pale Moon** (con la copia del usuario en `C:\Program Files\Pale Moon`): abrir con el perfil `orbis`, ver la página local (se espera `es5-ok`, `es2020-ok` y `canvas-ok`) y cerrar. Volver a abrir para comprobar que explorer sigue bien después de cerrarlo. Después, sitios reales (HTML5, JS moderno, TLS 1.3) con el tiempo de carga de cada uno. Si se cae, repetir con `orbis-nojit`.

## Temas Luna y Noir, sin estilo por defecto (fase 7, sesión de accesos directos)

### Pedido y resultado de W175

- El usuario pidió los temas de Windows XP (Luna) y Royale Noir, lo más parecidos posible a los de Microsoft, y Aero por defecto.
- Después de probar W175 contó que Aero se sentía más lento. Por eso el valor por defecto quedó **sin estilo visual**.

### Luna y Noir

- Los `.msstyles` de Microsoft no se pueden redistribuir. Estos son propios, armados desde el `aero.msstyles` del Wine fijado (LGPL), con `tools/build-msstyles-hw.py` (nuevo).
- Por cada estilo, el builder:
  - copia las fuentes de Aero a un overlay;
  - recolorea todos los bitmaps con la paleta del estilo;
  - dibuja de nuevo, estado por estado y con los tamaños y la disposición de Aero, 32 bitmaps: botones, casillas, botones de opción, barras de desplazamiento (botones, pulgar, canal), pestañas, encabezados de lista, bordes de edición y de combo, y groupbox.
- **Luna:** botones con borde azul oscuro y cara blanca a beige, brillo naranja al pasar el mouse y borde azul en el botón por defecto. Casillas con tilde verde, botones de opción con punto verde, barras de desplazamiento azul lavanda, pestañas con borde superior naranja, barra de progreso en bloques verdes.
- **Noir:** botones negros brillantes, casillas oscuras con tilde blanca, barras de desplazamiento grafito y barra de progreso continua.
- El INI de cada estilo tiene su nombre ("Luna", "Noir") y, en `[SysMetrics]`, los colores del sistema de XP Luna y de Royale Noir. uxtheme los aplica al elegir el estilo.
  - Luna: barra de título en degradé azul, bordes azules, diálogos beige.
  - Noir: barra de título negra, diálogos gris oscuro.
- Sin `TransitionDurations`: Aero tiene 32 secciones con fundidos de 100 ms que repintan cada control varias veces por cambio de estado. Es lo más probable detrás de la lentitud.
- Se compila con los mismos comandos que el build fijado usa para `aero.msstyles` (`make -n`).
- `tools/build-wine-hardware.py` los copia a `C:\windows\resources\themes\luna\luna.msstyles` y `...\noir\noir.msstyles`, con verificación de `builder_sha256`. winecfg los lista en Integración de escritorio.

Lo que Wine no dibuja con el tema:
- La barra de título, los bordes y los botones de minimizar, maximizar y cerrar los dibuja Wine con los colores del sistema y los botones clásicos (`uxtheme/stylemap.c` solo tiene los nombres). En Luna salen la barra azul y los bordes azules de XP, pero no los botones redondeados ni la X roja.
- Lo que sí toma el estilo: las barras de desplazamiento de todas las ventanas (uxtheme se engancha con `user_api_hook`), los fondos de diálogo y los controles de los programas que piden common controls 6.0, como winecfg. Explorer usa v5 y solo toma los colores.

### Sin estilo visual por defecto

- El prefijo sellado trae en `ThemeManager` `ThemeActive=1` con Aero. Hasta W174 el archivo no existía y uxtheme lo apagaba; desde W175 un prefijo nuevo arrancaba con Aero.
- `build-wine-hardware.py` pone `ThemeActive` en 0.
- En la consola esas claves son de la consola (W175). Si Aero quedó activo, escribió sus colores claros en `Control Panel\Colors`, y apagarlo desde el registro no los restaura.
- Por eso esta build trae `user_reg_reset = [ThemeManager, Control Panel\Colors]`: esa subida los toma de la build (sin estilo, esquema oscuro) **una sola vez**. Hay que sacarlo en W178.

Para construir: `tools/build-msstyles-hw.py` (ya corrido; `out/msstyles-hw` está al día) antes de `tools/build-wine-hardware.py`.

### Prueba

1. Al arrancar: escritorio y ventanas oscuros, como antes de W175, sin estilo visual. En el registro de la subida, `user_reg.reset` con las dos claves.
2. winecfg → Integración de escritorio → la lista de temas tiene que mostrar Aero, Luna y Noir.
   - Elegir Luna → Aplicar: barra de título azul, bordes azules, diálogos beige; en winecfg, botones, casillas, pestañas y barras de desplazamiento al estilo XP.
   - Lo mismo con Noir.
3. Velocidad: con Luna y con Noir, abrir el menú Inicio, mover ventanas, desplazarse en una lista. Comparar con "(Sin tema)" y con Aero.
4. Volver a "(Sin tema)": tienen que volver los colores oscuros.

Riesgos:
- Luna y Noir siguen dibujando con bitmaps a través de uxtheme, como Aero. Sin los fundidos deberían andar mejor que Aero, pero no tan rápido como sin tema.
- Es la primera vez que estos bitmaps se ven en la consola. Puede haber detalles para ajustar: tamaños, márgenes, contraste del texto en Noir.

## Prueba física

Reporte: `reports/wine-hardware-w177/physical/20261103T211906Z/`. Respuesta del usuario: "Navegador falla". `webview-result.txt` está copiado en `build/w177-webview-result.txt`.

- **webview64:**
  - `ole`, `create` y `activate` dan `0x00000000`, es decir que el control se crea y se activa.
  - Las tres navegaciones (local, remota y back) quedan en `ready_state=1 complete=no` a los 30 s.
- **Causa:** `xul.dll` de Gecko no carga. Le falta `bcrypt.dll`, que necesitan `ncrypt.dll` y `crypt32.dll`; `WINTRUST.dll` necesita `crypt32`, y xul necesita `WINTRUST`.
  - El árbol host sólo tiene `bcrypt.dll` de i386; no hay de x86_64.
  - mshtml registra `Failed to init Gecko, returning CLASS_E_CLASSNOTAVAILABLE`.
- **Internet Explorer:** arranca como invitado (el `error=1813` es un `GetLastError` viejo). Después falla al crear un stub de marshaling (`0x80004002`) y no tiene Gecko con qué dibujar.
- Pale Moon, los temas y SuperMarioKart no se reportaron.
- El arreglo de `bcrypt` (y la revisión de la clausura de Gecko) va a la sesión del navegador, para W178.
