# W179: navegador con bcrypt (fase 9), DirectInput y aspecto XP en Luna/Noir (fase 7), sonda USB (fase 10) e íconos

[English](HARDWARE_W179.md) | [Español](HARDWARE_W179-es.md)

APP_VER 02.78. Base W178.

## Íconos de Programs → Internet

Los accesos nuevos de W177 no tenían ícono. La copia de Pale Moon es del usuario y puede no estar, y `iexplore.exe` y los programas de prueba no traen recurso de ícono.

`tools/make-icons.py` dibuja tres íconos más, igual que los de Graphics Tools (16, 32 y 48 px), y `tools/make-start-menu.py` los asigna:
- `palemoon.ico`, una luna creciente clara sobre un disco azul oscuro: Pale Moon y Pale Moon (no JIT);
- `web.ico`, un globo azul con meridianos y paralelos: queda dibujado, pero sin acceso que lo use, porque el de Internet Explorer se quita (ver abajo);
- `webview.ico`, una ventana con el globo adentro: WebView test (64-bit) y (32-bit).

Los cuatro íconos anteriores salen idénticos (mismo hash). Para construir: `tools/make-icons.py` y `tools/make-start-menu.py` antes de `tools/build-wine-hardware.py`.

## Sonda de discos USB (fase 10, sesión de red)

`platform/ps4/pw_wine_fs.c`, `usb_probe`, se llama una vez al final de `pw_wine_fs_drive_mounts`. Antes de dar letras a los discos USB hay que saber si la app, que corre en el sandbox (W030), ve `/mnt/usb0..7` y si puede escribir ahí.

- **Qué registra:** una línea `PWUSB slot=N stat=… errno=… dir=… entries=… list_errno=… first=… statfs=… version=… type=… rdonly=… from=… on=…` por slot.
  - `slot=0` sale siempre; los demás slots, sólo si existen.
- **Cómo se lee:**
  - `stat=0 dir=1 entries>=0`: la app ve el disco.
  - `stat=-1 errno=2`: no existe para la app (sandbox, o no hay disco).
  - `errno=1` o `13`: permiso denegado.
  - `version=20030518`: confirma el formato de `statfs` que se lee.
  - `type=`: el sistema de archivos (`exfatfs` o `msdosfs`).
  - `rdonly=1`: montado sólo para lectura.
- **Prueba de escritura**, sólo si en la raíz del disco existe `orbisdesk-write.txt`:
  - si se pudo escribir, queda `write_test open=0 errno=0 written=46`, y el archivo termina con "orbisdesk W179: write test from the console";
  - si el archivo no existe, sale `write_test=skipped`.
- **Qué toca del disco:** nada más. Sólo lista la raíz y lee el tipo de sistema de archivos.

Las letras de unidad, la conexión en caliente y la ejecución desde el disco van en W180, según lo que diga la sonda.

## Wine Configuration en Control Panel; ícono de Game Controllers

A pedido del usuario:
- **Wine Configuration** pasa de System Tools al submenú **Control Panel** del menú Start.
  - Ese submenú lista la carpeta Control Panel del shell, que sólo muestra applets (`*.cpl` en `system32`), y winecfg es un programa. Por eso se agrega un applet de 64 bits, `fixtures/win32/winecfgcpl.c`, con el ícono de winecfg (`winecfgcpl.rc`, de `programs/winecfg/winecfg.ico`).
  - Al abrirlo arranca `C:\windows\system32\winecfg.exe`; si no puede, muestra el código de error.
  - Lo compila `tools/build-wine-hardware.py` como `system32\winecfg.cpl`.
  - El acceso viejo de System Tools sale con `obsolete_files`.
- **Game Controllers** (System Tools) usa el ícono de `joy.cpl`. `tools/make-start-menu.py` acepta un quinto campo con el ícono.
  - Comparado con la salida anterior, sólo cambian esos dos accesos: uno sale y el otro cambia de ícono.

## Sin acceso a Internet Explorer

Se quita "Internet Explorer" de Programs → Internet (`tools/make-start-menu.py`).
- `iexplore.exe` registra su clase como servidor COM local. Eso necesita marshaling de la class factory y rpcss, y ninguno de los dos existe en un título de un solo proceso. En W177 terminaba con código 1 sin mostrar nada.
- El control embebido, que cubre MSHTML para otros programas, sigue con las pruebas WebView.

## Navegador: bcrypt y clausura de Gecko (fase 9, sesión del navegador)

### Qué pasó en W177

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

### Cambio

| Archivo | Qué hace |
|---|---|
| `tools/build-bcrypt-x64.py` (nuevo) | Compila `bcrypt.dll` de 64 bits, que el árbol de Wine del host nunca enlazó. El `libsymcrypt.a` x86_64 de ese árbol tiene objetos de un build viejo con clang, y clang anterior a 19 desactiva el código por plataforma (`SYMCRYPT_IGNORE_PLATFORM`). Por eso `cpuid.o` quedó vacío y el enlace fallaba (`SymCryptDetectCpuFeaturesByCpuid`). El builder corre los comandos exactos de `compile_commands.json` con el compilador del Makefile (`x86_64-w64-mingw32-gcc`), con salida en `build/bcrypt-x64`, y después las reglas de archivo y enlace del Makefile. No escribe en el árbol del host ni cambia código. La criptografía de bcrypt es SymCrypt (código PE), así que no depende de un Unix side. |
| `tools/stage-mshtml-hw.py` | Agrega `bcrypt` en las dos vistas (el de 64 bits sale del builder nuevo). También agrega las DLL que `xul.dll` y `mozglue.dll` cargan en diferido: `psapi`, `winspool.drv`, `rasapi32`, `rasdlg` y `dbghelp`. Una de esas que falte lanza una excepción en su primera llamada. Por clausura entra también `compstui` (de winspool). `winspool.drv` sin Unix side carga igual (su `DllMain` devuelve TRUE) y sus llamadas de impresión fallan. |
| `tools/check-web-closure.py` (nuevo) | Recorre todos los imports, transitivamente, en el runtime construido. Busca en el orden del cargador: carpeta del programa, `system32`/`syswow64` y carpeta builtin. Cubre Wine Gecko (las dos), mshtml/ieframe/jscript/iexplore (las dos vistas), los fixtures y, opcionalmente, una carpeta de programa como la copia de Pale Moon. Los imports diferidos van aparte. Con `--staged` suma la salida del stager a cada vista, para revisar un arreglo antes del build. Termina con 1 si falta algo. |

| `tools/build-wine-hardware.py` | Una línea: `tools/build-bcrypt-x64.py` en `source_hashes`. El bloque de W177 ya copia todo lo que lista `out/mshtml-hw/manifest.json`. |
| `tools/make-start-menu.py` | Sin el acceso directo "Internet Explorer" (ver abajo). Lo cambia la sesión principal. |

### Verificación sin consola

- `build-bcrypt-x64.py` ya corrió y dejó `out/bcrypt-x64`: 126 objetos, unos 4,5 minutos. El `bcrypt.dll` es PE32+ de 2,9 MB, importa sólo advapi32, kernel32, ntdll y ucrtbase, y exporta 56 funciones `BCrypt*`.
- `stage-mshtml-hw.py` ya corrió y dejó `out/mshtml-hw`: 17 módulos de 64 bits y 18 de 32 bits, sin imports sin resolver. Las mismas 1770 claves de registro, sin valores sellados reemplazados.
- `check-web-closure.py --staged out/mshtml-hw/x86_64-windows out/mshtml-hw/i386-windows build/wine-hardware-w178/runtime <Pale Moon 35.0.3>`: cero imports faltantes y cero diferidos faltantes. Cubre Gecko x86_64 (54 módulos), Gecko x86 (55), mshtml en las dos vistas (29 y 29), los fixtures (38) y Pale Moon (134).
- Sobre W177 sin el arreglo, el mismo chequeo da `bcrypt.dll` faltante en los tres casos, que es el error que dio la consola.

### Construcción (orden)

1. `python3 tools/build-bcrypt-x64.py` → `out/bcrypt-x64` (hecho; repetirlo sólo si cambia el builder)
2. `python3 -I tools/stage-mshtml-hw.py` → `out/mshtml-hw` (hecho)
3. `python3 tools/build-wine-hardware.py`
4. `python3 -I tools/check-web-closure.py build/wine-hardware-w179/runtime`: tiene que terminar con 0.

Gecko no cambia, así que `stage-wine-gecko.py` no hace falta.

### Internet Explorer: no soportado

`iexplore.exe` no puede funcionar en el modelo de un proceso y su acceso directo sale del menú Start.

- **Causa:** `IEWinMain` (`dlls/ieframe/iexplore.c`) registra `CLSID_InternetExplorer` con `CLSCTX_SERVER`, que incluye servidor local (otro proceso). Para eso ole32 serializa la fábrica de clases, y necesita el proxy/stub de `IServiceProvider` y después rpcss, el servicio de RPC de Wine. Acá no hay ninguno de los dos: no hay procesos aparte ni administrador de servicios.
- **Resultado en W177:** `Failed to create ifstub, hr 0x80004002`, `failed to register CLSID_InternetExplorer: 80004002`, `start_rpcss Failed to open service manager`, y el programa termina con estado 1.
- **Lo que sigue funcionando:** el control de IE embebido en un programa (WebView test). Crea la clase en proceso y no pasa por `IEWinMain`.
- **No se intentó:** cambiar `ieframe` para que registre sólo en proceso. Reemplazaría el `ieframe.dll` que también usa el control embebido.
- `iexplore.exe` sigue instalado, porque las asociaciones de `mshtml.inf` (`.gif`, `.jpg`, `.htm`…) lo nombran. Abrir uno de esos archivos con doble clic falla igual que el acceso directo.

### Prueba física

1. **WebView test (64-bit) y (32-bit):** se espera `local complete=yes`, `title "orbis-webtest"`, `es5 "es5-ok"` y la página visible. Con red: `remote complete=yes` con título.
2. **Pale Moon:** antes, copiar la carpeta `palemoon` del `.7z` a `wine-prefix/drive_c/Program Files/Pale Moon/`. Después seguir los pasos de `HARDWARE_W177.md`.
3. **En el log:** no tiene que aparecer `Library bcrypt.dll … not found` ni `Failed to init Gecko`.

Sin la copia de Pale Moon en la consola, su acceso directo no hace nada visible: el shell le pasa el `.lnk` a `CreateProcess`, que lo rechaza (`PWOPEN reject_title_replacement`).

### No verificado

- Nada de W179 se probó en la consola.
- No se probó si el código de Gecko llama a funciones de bcrypt que necesiten algo más que SymCrypt.
- `make -n -B` (usado para leer los comandos de symcrypt) regeneró `config.status`, los Makefiles y `compile_commands.json` del árbol del host con los mismos argumentos de configure, y pisó `config.log`. Make rehace los makefiles aunque se use `-n`. Las líneas que se compararon del Makefile (CC, symcrypt, bcrypt, FFMPEG) quedaron iguales, y `include/config.h` no cambió.

## DirectInput y aspecto XP (fase 7, sesión de accesos directos)

### 1. DirectInput con el mando de la PS4 (fase 7)

- El DirectInput de Wine encuentra joysticks solo por HID (`dlls/dinput/joystick_hid.c`), que un título de PS4 no tiene: ningún juego DirectInput veía un mando, y la pestaña DirectInput de `joy.cpl` estaba vacía.
- `tools/build-dinput-hw.py` (nuevo) compila dinput y dinput8 (x86_64 e i386) con un dispositivo nuevo, `joystick_pad.c`. Es código propio, no de prospero-win.
  - Muestra el controlador XInput 0 (el mando, desde W178) como un gamepad con la disposición del driver de Xbox 360 de Windows:
    - X/Y: stick izquierdo; Rx/Ry: stick derecho; Z: los dos gatillos juntos;
    - 10 botones: A B X Y LB RB Back Start LS RS;
    - la cruceta como POV.
  - Se presenta como "Controller (XBOX 360 For Windows)", VID/PID 045e:028e.
  - Lee XInput cada 8 ms en el hilo de entrada de dinput (un temporizador como `read_event`), y también en `Poll()`.
  - Los ejes respetan el rango, la zona muerta y la saturación que pone el programa, con el mismo cálculo que `scale_axis_value` de `joystick_hid.c`.
  - Sin force feedback: el mando vibra por XInput.
- `dinput.c`: el mando aparece primero entre los controladores de juego (`EnumDevices`) y se crea por su GUID de instancia o de producto.
- Leer el mando por DirectInput lee XInput, así que activa el modo juego de `hw_pad.c` igual que un juego XInput.
- `tools/build-wine-hardware.py` copia los cuatro DLL a las carpetas builtin y a `system32`/`syswow64`. El dinput de 64 bits no estaba en el prefijo.
- Sin advertencias al compilar. Los imports de los cuatro DLL ya están en el prefijo.

### 2. Luna y Noir más parecidos a XP y a Royale Noir

Pedido del usuario después de probar W177: Luna se parecía demasiado a Aero. Quería el borde y la barra de título plenos en azul XP, la barra de tareas azul y el botón Start verde; en Noir lo mismo, pero naranja.

- `tools/build-msstyles-hw.py` (ya en W178):
  - **Luna:** título y borde plenos azul XP (0,84,227), y gris azulado (122,150,223) en las ventanas inactivas.
  - **Noir:** título y borde naranja (232,112,24), y gris oscuro en las inactivas.
  - Tres piezas nuevas con clases del shell de XP:
    - `[Taskbar.BackgroundBottom]`: azul XP / negro brillante;
    - `[Start::Button.Pushbutton]`: verde / naranja, cuadrado a la izquierda y redondeado a la derecha;
    - `[TaskBand::Toolbar.Button]`: los botones de las ventanas, con la activa más oscura.
- `tools/build-explorer-hw.py` (`tools/taskbar-theme-w179.patch.py`):
  - explorer carga uxtheme en tiempo de ejecución y abre "Taskbar" en la ventana de la barra;
  - si el estilo la tiene, dibuja desde el estilo el fondo, el botón Start (`SetWindowTheme "Start"`, clase Button) y los botones de las ventanas (`SetWindowTheme "TaskBand"`, clase Toolbar);
  - el texto va en el color del estilo: "start" en negrita e itálica, y el reloj sobre el color de la barra;
  - con `WM_THEMECHANGED` (elegir otro estilo en winecfg) recarga;
  - con Aero o sin estilo queda el dibujo clásico.
- `tools/build-win32u-ps4.py` (`tools/flat-frame-w179.patch.py`), en el pintado del borde de ventana (`defwnd.c`):
  - si el color de borde del estilo es distinto de la cara de botón, todo el borde, incluidos los bordes 3D, se dibuja pleno en ese color;
  - con el esquema oscuro de siempre (borde igual a la cara) no cambia nada.

Lo que Wine no dibuja con el estilo: los botones de minimizar, maximizar y cerrar siguen siendo los clásicos, sin la X roja de XP.

Comprobado sin la consola: el explorer modificado compila y enlaza sin advertencias, y `defwnd.c` modificado compila sin advertencias con la receta de win32u.

### Prueba

1. Game Controllers → pestaña DirectInput: aparece "Controller (XBOX 360 For Windows)", y sus ejes, botones y POV se mueven.
2. Un juego DirectInput (por ejemplo, uno de 32 bits que pide joystick) responde al mando, sin clics de la emulación.
3. winecfg → Luna:
   - borde y título plenos en azul;
   - barra de tareas azul, Start verde, botones de ventana azules (el activo más oscuro), reloj en blanco.
4. Lo mismo con Noir: naranja y negro.
5. "(Sin tema)" y Aero: barra de tareas y bordes como antes.

Riesgos:
- Enumerar dispositivos DirectInput lee XInput, así que activa el modo juego durante un segundo aunque el programa no use el mando.
- El dispositivo de dinput es código nuevo: un juego con un formato de datos poco común puede mostrar algo raro en los ejes; el log de `dinput` lo diría.
- Los botones de la barra de tareas con estilo se dibujan con el ícono pequeño de la clase de la ventana. Una ventana que solo tiene un ícono puesto con `WM_SETICON` aparece sin ícono, porque leerlo pediría un mensaje a su hilo.

## Prueba física

Reporte: `reports/wine-hardware-w179/physical/20261103T221219Z/`. El usuario probó con un disco USB conectado y con su copia de Pale Moon.

- **DirectInput:** la pestaña DirectInput de Game Controllers muestra el mando.
- **Navegador:** `bcrypt` funcionó, porque `xul.dll` ahora carga. El siguiente bloqueo es `crypt32`:
  - `load_builtin_unixlib failed to load .../x86_64-unix/crypt32.so: Dynamic loading not supported`;
  - después, una llamada Unix sin tabla (`c0000005`, lectura de 0x8);
  - `Initialization of crypt32.dll failed`, y xul se descarga.
  - WebView test 64 queda en blanco (`Failed to init Gecko`) y Pale Moon dice "Could not load XPCOM". Va a W180: el Unix side de crypt32 como biblioteca estática.
- **Wine Configuration:** el applet arranca `winecfg.exe` como invitado desde `rundll32`. Cuando `rundll32` termina, su salida termina también el hilo de winecfg antes de que dibuje. En W180 el applet espera ese hilo.
- **USB:** `PWUSB slot=0 stat=-1 errno=2` en las dos partidas, y ningún otro slot. `/mnt/usb0` no existe para la app: puede ser el sandbox, o la consola monta el disco en otro lugar. W180 suma una sonda más amplia de `/mnt`.
- **SuperMarioKart con el mando** (`20261103T221722Z/run-0003`): no funcionó; en carrera el stick izquierdo movía el cursor.
  - El juego carga `DINPUT.dll`, y al crear DirectInput se carga `xinput1_4` (`joystick_pad`). `PWPAD game_mode=1` en la línea 2218 y `game_mode=0` en la 2825, cerca de un segundo después.
  - La enumeración leyó el mando una vez y después nadie lo leyó más. El juego no adquiere ni consulta el joystick: puede usar sólo el teclado, leer el mando por otra API (`joyGetPosEx` de winmm) o pedir que se elija en sus opciones.
  - Va a la sesión de accesos directos para W181.
