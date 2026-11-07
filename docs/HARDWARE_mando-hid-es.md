# Mando como gamepad HID (stack HID de Wine dentro del proceso)

[English](HARDWARE_mando-hid.md) | [Español](HARDWARE_mando-hid-es.md)

Estado: compilado y enlazado en parcial sin la consola. Falta empaquetarlo y la prueba física. El análisis previo está en `docs/HARDWARE_mando-juegos-analisis.md`.

## Problema

- The Lost Forest (Unity 2020.3, input clásico) no ve el mando aunque XInput funciona desde W178.
- Unity descubre mandos sólo por HID:
  - toma la lista de raw input;
  - si un nombre contiene `IG_`, lo asocia a un slot de XInput;
  - después lo abre (`CreateFileW`) y pide sus datos HID.
- En Orbis no había ningún dispositivo HID: winebus, hidclass y winedevice no corren en un proceso único sin administrador de servicios.

## Diseño

Se corre el stack HID de Wine dentro del proceso, como lo haría winedevice.exe. Lo único que se cambia de Wine es `ntoskrnl.exe`.

| Pieza | Qué hace |
|---|---|
| `native/pwhidhost.c` → `pwhidhost.dll` | Explorer la carga al terminar de armar el escritorio. Un hilo hace lo mismo que `ServiceMain` de winedevice: corre `wine_ntoskrnl_main_loop` (el bucle de IRP) y, cuando el administrador PnP está listo, llama a `ZwLoadDriver` de winebus. Antes crea la clave de servicio `xinput` (winexinput.sys) si falta. El prefix se armó en un host sin mando XInput, así que no la tiene, y setupapi no puede crearla sin SCM. |
| `ntoskrnl.exe` (overlay, `tools/build-hidstack-hw.py`) | 3 revisiones. (1) `open_driver`: sin administrador de servicios, acepta el driver desde su clave de registro, con el mismo control de tipo (driver de kernel). (2) `set_service_status` no hace nada sin handle de servicio. (3) El bucle de IRP marca el evento `PwNtoskrnlPnpReady` después de `pnp_manager_start`. |
| `winebus.sys`, `winehid.sys`, `winexinput.sys`, `hidclass.sys`, `hidparse.sys` | Del build fijado, sin cambios. |
| `native/winebus_orbis.c` | Unix side de winebus. Se compila en lugar de `bus_sdl.c`, así el lado PE de winebus llama a sus `sdl_bus_*` sin cambios. Crea un único dispositivo: un mando de Xbox 360 con cable (045e:028e), con el layout de `hid_device_add_gamepad` (el de un controller mapeado de SDL) y vibración (`hid_device_add_haptics`). Lee el estado cada 8 ms con `pw_wine_pad_peek` y manda un reporte sólo cuando cambia. La vibración va a `pw_wine_set_rumble`. Los efectos de force feedback físicos devuelven `STATUS_NOT_SUPPORTED` con una línea `PWHID no force feedback`. |
| `native/hw_pad.c` | `pw_wine_pad_peek`: el mismo estado que `pw_wine_pad`, pero sin contar como lectura de XInput. Si contara, el modo juego quedaría siempre activo, porque el bus lee aunque nadie juegue. |
| `platform/ps4/pw_wine_unixlibs.c` | Entrada `winebus.so` y un `pw_wine_pad_peek` débil ("sin mando") para los ELF sin `hw_pad.c`. |

Cadena esperada, la misma que en Linux:
1. winebus publica el mando con `is_gamepad`, así que su ID compatible incluye `WINEBUS\WINE_COMP_XINPUT`.
2. `winexinput.sys` crea dos hijos: `&IG_00` (el que ven los juegos) y `&XI_00` (el de uso interno de Wine).
3. Cada hijo se instala con `winehid.sys` + `hidclass.sys`.
4. Queda una interfaz HID que win32u lista en raw input. win32u refresca la lista cada 2 s y hidclass manda `WM_INPUT_DEVICE_CHANGE`.
5. Unity encuentra `IG_`, usa XInput slot 0 (el xinput de W178) y eso enciende el modo juego de `hw_pad.c` (`PWPAD game_mode=1`).

Además:
- winebus crea su mouse y teclado virtuales (845E:0001/0002), como en Linux. Aparecen en la lista de raw input y no generan entrada.
- **DirectInput** (`tools/build-dinput-hw.py`): `joystick_hid.c` saltea el gamepad HID de winebus (045e:028e con path `&IG_`/`&XI_`). El mando ya aparece como `joystick_pad.c` y no se lista dos veces.

## Archivos

- Nuevos:
  - `tools/build-hidstack-hw.py`
  - `native/winebus_orbis.c`
  - `native/pwhidhost.c`
  - `out/hidstack-hw/`, ya construido
- Editados:
  - `native/hw_pad.c` (`pw_wine_pad_peek`)
  - `platform/ps4/pw_wine_unixlibs.c` (entrada `winebus.so`)
  - `tools/link-wine-boot.py` (enlaza `winebus-unix.o`, con verificación de sha256)
  - `tools/build-explorer-hw.py` (revisión en `desktop.c`: `LoadLibraryW(L"pwhidhost.dll")`; si falla, `PWHID pwhidhost.dll not loaded`)
  - `tools/build-dinput-hw.py` (revisión en `joystick_hid.c`)
  - `tools/build-wine-hardware.py`: un bloque después del de dinput. Comprueba el builder y las fuentes, y copia los módulos a la carpeta builtin y al prefix (drivers en `system32\drivers`, `ntoskrnl.exe` en `system32`) y `pwhidhost.dll` a `system32`.
- Ya regenerados: `out/explorer-hw` (49 revisiones) y `out/dinput-hw` (4 revisiones).

Comprobado sin la consola:
- todo compila sin advertencias;
- el objeto Unix exporta sólo `pw_winebus_unix_call_funcs`;
- un enlace parcial de `hw_pad.o` + `pw_wine_unixlibs.o` + `winebus-unix.o` + `xinput-unix.o` resuelve `pw_wine_pad_peek`, `pw_wine_pad`, `pw_wine_pad_available` y `pw_wine_set_rumble` a `hw_pad.c` (`build/hidstack-hw/check.py`).

## Construcción (orden)

1. `python3 tools/build-hidstack-hw.py` (ya corrido; repetirlo si cambian `native/winebus_orbis.c` o `native/pwhidhost.c`)
2. `python3 tools/build-explorer-hw.py` (ya corrido)
3. `python3 tools/build-dinput-hw.py` (ya corrido)
4. `python3 tools/link-wine-boot.py` (cambia el ELF: `winebus-unix.o` y `pw_wine_unixlibs.c`)
5. `python3 tools/build-wine-hardware.py` (compila `hw_pad.c` y copia el stack)

## Qué mirar en el log

En orden, si todo anda:
- `PWHID xinput_service created` (o `present`)
- `PWHID irp_loop start` y `PWHID irp loop running, ready event set`
- `PWHID driver ...\winebus from its service key (no service manager)`, y lo mismo para `winehid` y `xinput`
- `PWHID pad bus init vid=045e pid=028e`
- `PWHID winebus load status=0`
- `PWHID pad device started`
- con un juego que use el mando: `PWPAD game_mode=1`

Fallos posibles y su línea:
- `PWHID pwhidhost.dll not loaded`
- `PWHID ntoskrnl load error=`
- `PWHID pnp_ready wait=` (el bucle no arrancó)
- `PWHID driver ... no service manager; key error`
- `failed to create driver`
- `PWHID winebus load status=` distinto de 0
- `Failed to send event` (WARN de ntoskrnl): el aviso a plugplay por RPC, que no existe. Se espera y no impide nada.

## Prueba

1. Arranque normal: el escritorio aparece igual que antes, y sin juego el mando sigue siendo mouse y teclado.
2. Controladores del juego:
   - la pestaña XInput sigue andando;
   - la pestaña DirectInput lista **un** solo "Controller (XBOX 360 For Windows)".
3. El bosque perdido:
   - el mando mueve al personaje;
   - aparece `PWPAD game_mode=1` y el puntero no se mueve.
   - Si no anda, traer por FTP `C:\users\orbis\AppData\LocalLow\<empresa>\The Lost Forest\Player.log`: Unity escribe ahí "Joystick connected" o el error al abrir el dispositivo.
4. SuperMarioKart (DirectInput) sigue igual que en W179.

## W198: resultado y corrección

Reporte: `reports/wine-hardware-w198/physical/20261104T121658Z/` (`run-0001` a `run-0004`).
- El host arrancó bien: `PWHID xinput_service`, `irp_loop start`, `ready event set`.
- Después: `PWHID winebus load status=0xc0000001`. El escritorio se trabó al abrir programas. W199 dejó de copiar `pwhidhost.dll`.

Dos causas, las dos en `ntoskrnl.exe`:

1. **Relocación doble de los invitados (el congelamiento).**
   - `ntoskrnl` registra con `LdrRegisterDllNotification` un callback que reubica cualquier **ejecutable** cargado fuera de su base: en winedevice el loader no lo hace, y ahí sólo se cargan drivers.
   - En Orbis los programas son invitados del mismo proceso, y el loader de invitados ya los reubica. `wfm.exe` cargó en `0x100110000`, su base es `0x140000000`, y quedó reubicado dos veces.
   - Por eso los punteros "truncados": `0x14023E040 − 2×0x3FEF0000 ≈ 0xC023E040`.
   - En `run-0002`, explorer (hilo 0024) falló leyendo `0xC023E040` dentro de un callback de usuario y quedó en un bucle de `c0000258`. En `run-0001` lo mismo le pasó a `rundll32`, con un salto a `0xC0221B30`.
   - **Corrección:** el callback vuelve enseguida si la imagen no es de subsistema nativo. Así sólo toca los drivers, y tampoco cambia la cookie de seguridad de los invitados.
2. **`winebus` no cargó (`0xc0000001`).**
   - Mi camino sin SCM sólo se tomaba si `OpenSCManagerW` devolvía NULL. En este runtime devuelve un handle no nulo después de `RPC_S_SERVER_UNAVAILABLE`, y `OpenServiceW` falla con `NDRCContextBinding invalid handle` (`run-0002`, líneas 906-978).
   - **Corrección:** `open_driver` lee siempre la clave de servicio del registro y no consulta al administrador de servicios.

El manejador vectorizado de `instr.c` no es causa: sólo emula instrucciones privilegiadas y lecturas de `0xfffff78000000000`. En el bucle aparece llamado en cada excepción, pero devuelve "seguir buscando".

La versión corregida se compiló en una copia aparte (`build/hidstack-hw-next/`), sin tocar `out/hidstack-hw`, mientras se construía W199.

Para volver a activarlo:
1. pasar las dos revisiones a `tools/build-hidstack-hw.py` y correrlo;
2. volver a copiar `pwhidhost.dll` en `tools/build-wine-hardware.py` y sacarla de `obsolete_files`;
3. correr `link-wine-boot.py` (no cambia: el objeto Unix es el mismo) y `build-wine-hardware.py`.

En la prueba, además de lo de arriba: abrir File Manager, winecfg y Task Manager y confirmar que abren como en W197.

## W200: resultado

Reporte: `reports/wine-hardware-w200/physical/20261104T124304Z/`. Respuesta del usuario: File Manager, winecfg y Task Manager abren. joy.cpl no lista el mando. The Lost Forest se colgó al abrir.

El stack arranca bien:
- winebus, winehid y xinput cargan desde su clave de servicio;
- `winebus load status=0`;
- `pad device started`, `pad connected=1`;
- `PWPAD game_mode` alterna.

1. **Ráfaga de excepciones en `run-0001`: no es del stack HID.**
   - La pestaña Windows.Gaming.Input de joy.cpl llama a `RoGetActivationFactory("Windows.Gaming.Input.RawGameController")`. Falla porque `windows.gaming.input.dll` no está en el runtime.
   - Después `update_wgi_devices` usa el factory nulo: AV leyendo `0x3` en joy.cpl+0x9122.
   - Eso pasa dentro de un callback de ventana, y sigue el bucle de `c0000258`.
   - W178 tiene el mismo AV y unos 496 000 `c0000258`.
   - El manejador vectorizado de ntoskrnl aparece en cada traza porque ahora corre primero, pero devuelve "seguir buscando".
2. **joy.cpl, listas "connected" vacías.**
   - La primera página agrega un dispositivo DirectInput sólo si responde `DIPROP_GUIDANDPATH`, y lo pone en "XInput devices" si su path contiene `&ig_`.
   - `joystick_pad.c` (W179) nunca implementó esa propiedad, así que el mando no aparecía ahí ni antes de W200.
   - El dispositivo HID `&ig_`, que la habría llenado, lo saltea el filtro de dinput.
   - Arreglo propuesto: `joystick_pad.c` responde `DIPROP_GUIDANDPATH` con el path HID `&ig_` de winexinput.
3. **El bosque perdido se cuelga.**
   - Unity carga xinput y lo consulta (`game_mode=1`), crea el swap chain (`PWDXGI`) y no llega a crear el presenter de DXVK, cosa que en W195 sí venía después.
   - A partir de ahí tampoco escribe el monitor de explorer (hilo 0030). Sólo sigue el hilo nativo de audio (`PWAUDIO`, `peak=0`).
   - Parece un bloqueo del lado de Wine/servidor en el camino de raw input o HID de Unity. Con el log actual no se puede saber qué pedido quedó colgado.
   - Para W202 se proponen tres diagnósticos:
     - una línea por IRP despachado (`PWHID irp`, y `done` con su duración);
     - un contador de reportes del mando;
     - un archivo `C:\orbis\nohid.txt` que apaga el stack sin reconstruir, para comparar The Lost Forest con y sin él.

## W202: cambios

- **`joystick_pad.c`** (`tools/build-dinput-hw.py`): responde `DIPROP_GUIDANDPATH` con el path de la interfaz HID presente que contiene `vid_045e&pid_028e` y `&ig_` (`CM_Get_Device_Interface_ListW`). joy.cpl lista entonces el mando en "XInput devices". Sin el stack HID devuelve `DIERR_UNSUPPORTED`, como antes.
- **Filtro de dinput** (`joystick_hid.c`): ahora saltea sólo `&IG_`.
  - El hijo `&XI_` de winexinput no se registra como interfaz HID: hidclass le da `GUID_DEVINTERFACE_WINEXINPUT`. Por eso no aparece en `EnumDevices`.
  - Windows.Gaming.Input lo abre por path a través de dinput, y el filtro anterior también le cerraba ese camino.
- **Traza de pedidos** (overlay de `ntoskrnl.c`): `PWHID irp n= type= code= client=` antes de cada pedido despachado y `PWHID irp done ... status= ms=` después.
  - Se registran los primeros 400 y, después, sólo los que tardan más de 100 ms.
  - Valores de `type`: 1 create, 2 close, 3 read, 4 write, 5 flush, 6 ioctl, 7 volume, 8 free, 9 cancel. `client` es el hilo que lo pidió.
  - Un pedido que nunca vuelve aparece con su línea de inicio y sin `done`.
- **Contador de reportes** (`native/winebus_orbis.c`): `PWHID report n= queued= len=`, los primeros 10 y después cada 500.
- **Interruptor** (`native/pwhidhost.c`): si existe `C:\orbis\nohid.txt`, el host registra `PWHID disabled by C:\orbis\nohid.txt` y no carga ntoskrnl ni ningún driver.

Construcción para W202:
1. `build-hidstack-hw.py` y `build-dinput-hw.py` (los dos ya corridos)
2. `link-wine-boot.py` (cambió `winebus-unix.o`)
3. `build-wine-hardware.py`

Prueba sugerida:
1. The Lost Forest con el stack, igual que en W200. Si se cuelga, buscar en el log el último `PWHID irp` sin su `done` y su `client`.
2. The Lost Forest con `C:\orbis\nohid.txt` creado (por FTP): sirve para ver si el cuelgue viene del stack.
3. joy.cpl, primera página: el mando debería aparecer en "XInput devices". La pestaña Windows.Gaming.Input sigue rompiéndose, ver abajo.

### Pestaña Windows.Gaming.Input de joy.cpl (pendiente de decisión)

La falla es vieja (W178): `windows.gaming.input.dll` no está y joy.cpl no controla el factory nulo. Hay dos arreglos posibles:
- **Guarda en joy.cpl:** un overlay de `dlls/joy.cpl/wginput.c` con `if (!statics) return;` después de cada `RoGetActivationFactory`. Son tres sitios: `update_wgi_devices`, `check_gamepad_interface` y `check_racing_wheel_interface`. Se compila con los comandos del build fijado y se copia en lugar de `joy.cpl`. Es chico: la pestaña queda vacía, sin la falla ni el bucle.
- **Instalar Windows.Gaming.Input:**
  - La DLL está en el build fijado, y sus imports (combase, user32, dinput8, setupapi, hid) ya están en el runtime.
  - Pero el prefix no tiene ninguna clave `ActivatableClassId` de `Windows.Gaming.Input.*`, así que habría que registrarlas (claves de registro en el prefix) además de copiar la DLL.
  - Con el stack HID, la pestaña vería el mando (por `&XI_`), y también los juegos que usan WGI.
  - Es más trabajo y no está probado.

## W203–W205: el mando llega a Unity, pero Unity no lee más

- **W203:** el cuelgue de The Lost Forest era el límite de 256 fds del `poll` del servidor en proceso (lo arregló la sesión fase9). El juego arranca.
- **W204:** Unity recibe valores de XInput (`PWPAD xinput lx=…` cambia con el stick), pero el personaje no se mueve y `Player.log` no tiene "Joystick connected". La única lectura HID de Unity (irp n=24) queda pendiente.
- **W205** (trazas en winebus, winexinput y hidclass): el camino del reporte funciona de punta a punta. En la línea 4247 el primer reporte completa la lectura de Unity (`hc queued … hid … client reads completed 1`). Después Unity no vuelve a leer: no hay otro irp `type=3` hasta que el juego cierra (línea 4711).

Causa (servidor de Wine y UnityPlayer):
- El input clásico de Unity tiene un hilo propio (UnityPlayer `0x1805154d0`). Espera los eventos de las lecturas con `WaitForMultipleObjects`, llama a `GetOverlappedResult(…, FALSE)`, procesa el reporte y vuelve a llamar a `ReadFile`.
- La primera lectura la lanza el hilo principal de Unity. Quedó pendiente en hidclass. Wine termina una lectura pendiente de dispositivo con un APC de sistema (`APC_ASYNC_IO`, `server/async.c`) en el hilo que la pidió, y recién después señala el evento del `OVERLAPPED`.
- El hilo principal de Unity espera en llamadas nativas (DXVK/Vulkan), no en esperas de Wine, así que el APC no corre. El evento no se señala, el hilo de entrada espera para siempre, y Unity nunca da el mando por conectado.
- Las lecturas de dispositivo empiezan con estado desconocido (`async_set_unknown_status`, `server/device.c`): el hilo que lee espera dentro de Wine hasta que el driver responde. Si el driver completa la lectura en ese mismo despacho, el APC corre en esa espera.

<a id="w206-arreglo"></a>


## W206:

`tools/build-hidstack-hw.py`, overlay de `hidclass.sys/device.c`:
- hidclass guarda el último reporte de cada dispositivo;
- una cola de cliente nueva empieza con ese reporte (`PWHID hc open pdo …: queue starts with the last report`).

Así, la primera lectura de Unity se completa en el despacho mismo. Las siguientes las pide su hilo de entrada, que espera en `WaitForMultipleObjects`, donde sus APC sí corren. El reporte extra es el estado actual del mando. Las trazas de W205 siguen.

Construcción: `build-hidstack-hw.py` (ya corrido) y `build-wine-hardware.py`. No hace falta enlazar: el objeto Unix no cambió.

Prueba: abrir The Lost Forest y mover el stick izquierdo. Debería mover el personaje. En el log debería haber más de un irp `type=3`, con el `client` del hilo de entrada de Unity.

Queda abierto: el mismo problema afectaría cualquier lectura asíncrona que un hilo deje pendiente sin volver a esperar dentro de Wine. No se investigó por qué el SIGUSR1 de W195 no hace correr el APC en ese hilo.

## W206–W211: el mando llega a Unity, pero el InputManager no responde

- **W206:** la primera lectura de Unity se completa en el despacho, como se buscaba, pero el juego no cambia.
  - UnityPlayer no lee por HID un dispositivo emparejado con XInput: su actualización por dispositivo (`0x18051eab0`) llama a `XInputGetState` y nada más.
  - Por eso falta la segunda lectura: es lo esperado. El arreglo de W206 queda (no molesta), pero no era la causa.
  - "Joystick connected" sólo se escribe cuando quien llama pasa un indicador de log, cosa que no pasa al arranque. Que falte no prueba nada.
- **W208** (traza `PWXI`): la actualización de Unity (`UnityPlayer.dll+0x51ef65`) llama a `XInputGetState` unas 65 veces por segundo, sin error, y recibe el stick moviéndose. En `0x18051ef40` normaliza los sticks, gatillos, botones y cruceta y los guarda en el objeto de joystick del dispositivo, que está registrado como índice 0 ("joystick 1").
- **W209:** el mando no mueve tampoco el menú (respuesta del usuario). El InputManager de Unity no usa ese joystick. Con el desensamblado no se pudo establecer por qué.
- **W211** (experimento): con `C:\orbis\padhid-generic.txt` presente, winebus publica el mando como gamepad HID genérico.
  - Usa VID 1209 y PID 5057 (pid.codes), `is_gamepad` en FALSE y el nombre "OrbisDesk Gamepad".
  - No hay winexinput ni `&IG_`, así que Unity toma su camino de joystick HID: SetupDi y lecturas desde su hilo de entrada.
  - XInput sigue igual para los juegos que lo usan.
  - En dinput, `joystick_hid.c` saltea 1209:5057 y `joystick_pad.c` devuelve su path, así que joy.cpl lo lista en "DInput devices".
  - El log dados `PWHID pad bus init vid=… pid=… mode=xinput|generic-hid`.
  - Sin el archivo, todo queda como en W208.

## W211: resultado y decisión (W213)

- **Resultado de W211** (`reports/wine-hardware-w211/physical/20261104T164421Z/run-0001.log`):
  - `mode=generic-hid` y no hay `&IG_`.
  - Unity abrió el dispositivo genérico y lo leyó desde su hilo principal (`0064`): 310 lecturas, 17 con un reporte entregado. No llamó a XInput.
  - Por eso el modo juego nunca se activó, y la emulación de teclado y mouse de `hw_pad.c` siguió activa en el juego: `input_event source=pad` con flechas (códigos 39 y 40), clics y rueda.
  - Lo que el usuario vio funcionar (moverse con la cruceta, el menú con puntero y Enter) es esa emulación, **no el joystick de Unity**.
- **El juego lee sobre todo el teclado:** su `Assembly-CSharp.dll` llama a `Input.GetKey`/`GetKeyDown` con A, D, ←, → (moverse), W, S, ↑ (trepar), Space (saltar) y Escape.
- **Sigue sin resolverse** el camino de joystick real de Unity 2020 (input clásico), en los dos modos:
  - con `&IG_`/XInput, Unity recibe el mando pero su InputManager no lo usa;
  - como HID genérico, Unity lo lee, pero el stick no movió al personaje.

**W213: HID genérico por defecto.**
- `native/winebus_orbis.c` publica el mando como gamepad HID genérico (1209:5057, "OrbisDesk Gamepad").
- `C:\orbis\padhid-xinput.txt` vuelve al mando de Xbox 360 de W198–W208.
- El motivo: en modo XInput, Unity consulta XInput en cada cuadro. Eso activa el modo juego, que apaga la emulación, y como Unity tampoco usa el mando, el mando no hace nada. En modo genérico la emulación queda disponible.
- Los juegos XInput (`xinput1_3` da el mando como controlador 0) y DirectInput (`joystick_pad.c`) se comportan igual en los dos modos.
- `padhid-generic.txt` ya no se usa.
- **Riesgo, sin probar:** SDL2 y el Input System nuevo de Unity leen XInput y también los dispositivos HID. Sin `&IG_` no pueden emparejarlos, así que pueden listar dos mandos: XInput 0 y un joystick HID genérico 1209:5057. Hay que probarlo con un juego SDL2.

**Perfil de teclas para The Lost Forest:** `fixtures/padmaps/The Lost Forest.exe.ini`.
- Cruceta y stick izquierdo mandan las flechas, Cruz manda Space (saltar), Triángulo y Options mandan Enter. Escape queda sin asignar.
- `build-wine-hardware.py` ya copia todos los `.ini` a `C:\orbis\padmaps`.
- **Hoy no se carga:** `pw_hw_pad_profile` sólo corre cuando un programa arranca por relanzamiento o es de 32 bits (`native/wine_hardware.c`), y The Lost Forest corre como invitado de 64 bits dentro de explorer.
- Hace falta un puente:
  - `kernelbase` (`ps4_guest_launch`, en `tools/build-guest-hw.py`) avisa al lado nativo cuando un invitado carga y cuando termina;
  - `hw_pad.c` tiene que poder cambiar y borrar el perfil con el hilo del mando corriendo.
- Mientras tanto, la emulación del escritorio ya permite moverse con la cruceta (flechas) y usar el menú.

**W213: puente de perfiles para invitados.**
- `tools/build-guest-hw.py` (kernelbase `process.c`):
  - cuando un invitado termina de cargar, avisa al lado nativo con la ruta del programa;
  - cuando termina, avisa de nuevo para borrar.
  - Lo hace por la biblioteca Unix de xinput (llamada 3, `unix_pad_profile`). La carga por nombre se hace directo con `NtQueryVirtualMemory(MemoryWineLoadUnixLibByName)` y la llamada con el `__wine_unix_call_dispatcher` que exporta ntdll, porque kernelbase no enlaza winecrt0.
- `tools/build-xinput-hw.py`: la llamada `pad_profile`, que pasa a `pw_wine_pad_profile`. `platform/ps4/pw_wine_unixlibs.c` tiene la versión débil "sin mando".
- `native/hw_pad.c`: `pw_wine_pad_profile` sólo deja un pedido. El hilo del mando lo aplica al empezar cada lectura, así el perfil nunca cambia en medio de `poll_controller`.
  - Al cargar, el perfil se cambia sólo si existe `padmaps\<exe>.ini`. Si no, queda el activo: The Lost Forest arranca `UnityCrashHandler64.exe` como otro invitado, y ese arranque no le borra el perfil.
  - Al terminar un invitado, se borra sólo si el perfil activo es el suyo.
  - Al cambiar, se sueltan las teclas que tenían apretadas el perfil y la emulación.
- Log:
  - `PWPAD profile=The Lost Forest.exe keys=…`
  - `PWPAD guest profile=<exe> none, keeps …`
  - `PWPAD guest profile=<exe> cleared`
  - si no encuentra la biblioteca: `PWPAD no pad library for guest profiles`

Construcción de W213: `build-guest-hw.py`, `link-wine-boot.py` (cambian `xinput-unix.o` y `winebus-unix.o`, además de `hw_pad.c` y `pw_wine_unixlibs.c`) y `build-wine-hardware.py`. `out/hidstack-hw` y `out/xinput-hw` ya están reconstruidos.

## Resultado W213

Reporte: `reports/wine-hardware-w213/physical/20261104T171948Z/run-0001.log`. Respuesta del usuario: "W213 sí, todo OK". En The Lost Forest el mando mueve al personaje y salta, a través del perfil de teclas.

En el log:
- `PWHID pad bus init vid=1209 pid=5057 mode=generic-hid`
- `PWPAD profile=The Lost Forest.exe keys=11 stick=keys`
- `PWPAD guest profile=UnityCrashHandler64.exe none, keeps The Lost Forest.exe`
- durante el juego, eventos `source=profile`: flechas y Space
- al salir, `PWPAD guest profile=The Lost Forest.exe cleared`

Las trazas `PWHID` y `PWXI` siguieron activas en W213.

**W214: sin trazas de diagnóstico** (a pedido del usuario).
- Se sacan:
  - la traza por pedido de ntoskrnl (W202);
  - las de winebus, winexinput y hidclass (W205);
  - el contador de reportes de `winebus_orbis.c`;
  - `PWPAD xinput` una vez por segundo (W204);
  - `PWXI` (W208), que además hacía dos `GetModuleHandleExW` en cada llamada a XInput.
- winexinput.sys y el lado PE de winebus.sys vuelven a ser los del build fijado, sin overlay. hidclass mantiene sólo el arreglo de W206.
- Quedan las líneas que se escriben una sola vez o en cada cambio de estado: carga de drivers, `PWHID irp loop running`, `pad bus init`, `pad device started`, `PWPAD game_mode` y `PWPAD profile`.
- Construcción: `build-hidstack-hw.py` y `build-xinput-hw.py` (los dos ya corridos), `link-wine-boot.py` (cambió `winebus-unix.o`) y `build-wine-hardware.py` (`hw_pad.c`).

Queda abierto:
- el camino de joystick real de Unity 2020, en los dos modos;
- el posible mando doble en juegos SDL2 con HID genérico, sin probar;
- la pestaña Windows.Gaming.Input de joy.cpl, en espera.

## Riesgos

- Es la primera vez que corre `ntoskrnl.exe` dentro del proceso del título. Su `DllMain` instala un manejador vectorizado de excepciones (`instr.c`) que emula instrucciones privilegiadas de drivers. Para cualquier otra excepción devuelve "seguir buscando", pero se ejecuta antes que los manejadores de los juegos (Mono usa violaciones de acceso).
- Que el device manager del wineserver en proceso entregue los IRP a un hilo del mismo proceso no se probó antes.
- La instalación de los hijos usa setupapi con los INF del prefix. Sin SCM, `SetupInstallServicesFromInfSection` falla, pero su resultado se ignora y el valor `Service` se escribe igual (`dlls/setupapi/devinst.c`). La clave de servicio la crea `pwhidhost.dll`.
- Un juego que lea el mando sólo por HID (sin XInput) no enciende el modo juego. El mando seguiría moviendo además el puntero. Unity y SDL usan XInput para los dispositivos `IG_`.
- Windows.Gaming.Input sigue sin ver el mando: necesita los avisos PnP de plugplay, que no existen en el modelo de un proceso.
