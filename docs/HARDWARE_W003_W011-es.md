# Pruebas físicas W003–W011: Wine arranca en la PS4 hasta el servidor interno

[English](HARDWARE_W003_W011.md) | [Español](HARDWARE_W003_W011-es.md)

Todas usan el mismo Title ID `ORBW00002` (APP_VER 01.02 a 01.10) y el runtime de W001 ya subido a `/data`. Cada corrida física está en `reports/wine-hardware-w0NN/physical/<ts>/`, con su log y su `report.json`.

Desde W004, por pedido del usuario, los paquetes se suben sin smoke test previo en el emulador. W003 fue el último que pasó por el emulador (`reports/wine-hardware-w003/20261031T061617Z/`, `passed`).

## Hechos de la plataforma medidos en la consola

| Llamada (app de PS4, firmware 12.52) | Resultado |
|---|---|
| `dup2(fd, 1/2)` |EPERM|
| `fcntl(fd, F_DUP2FD)` (FreeBSD 10) |EINVAL|
| `dup(fd)` sobre un archivo abierto |**EPERM**|
| `fcntl(fd, F_DUPFD)` (FreeBSD 0) |EINVAL|
| `lstat` (importación de libkernel) |**EPERM**|
| `sceKernelStat` por ruta | funciona, pero devuelve **st_ino=0 y st_dev=0** |
| `sceKernelFstat` | funciona, con ino y dev reales |
| `readlink` | la app termina en esa llamada (W002) |
| `socketpair` + `sendmsg`/`recvmsg` con `SCM_RIGHTS` | funciona: el descriptor recibido es el mismo archivo (W012) |
| `fcntl(fd, F_GETFD)` y `F_SETFD` | **EINVAL**, también sobre un descriptor recibido (W012) |
| `F_GETFL`, `F_SETFL O_NONBLOCK` y `FIONBIO` sobre un archivo | funcionan (W013) |
| `F_GETFL` sobre un socket | 2 (O_RDWR) |
| `F_SETFL O_NONBLOCK` y `FIONBIO` sobre un socket |**EACCES** (W013)|
| Primer descriptor libre | 17 (no hay fd 0–2 utilizables) |

## Qué se corrigió en cada build

|Construcción| Bloqueo en la consola | Corrección |
|---|---|---|
| W003 | preflight 95 sin detalle | Sin `readlink` directo. `pw_wine_lstat` usa `sceKernelStat` ante EPERM. Los marcadores PWBOOT de `sceKernelDebugOutText` van al log |
| W004 | `file-identity` | El preflight registra cada caso en el canal de depuración |
| W005 | ino/dev 0 por ruta | El chequeo acepta fd ≥ 0 (antes exigía ≥ 3) y registra valores |
| W006 | Wine entra a `__wine_main` y la app cae (CE-34878-0) | `pw_wine_stat` toma ino/dev de `fstat` cuando la ruta da 0/0 |
| W007 | sin marcadores después de `__wine_main` | `--wrap` de `write`, `fprintf`, `vfprintf`, `fputs` y `fwrite`: lo que va a stdout/stderr pasa al log |
| W008 | cae entre `first_teb_ready` y la conexión al servidor | Marcadores en `dbg_init` y en cada paso del servidor interno |
| W009 | cae en `init_directories` | Marcadores por bloque y manejador de señales en el launcher: SIGSEGV en `release_object(NULL)` |
| W010 | `create_fd_mapping` del NLS falla | El servidor registra status y errno y termina con un error explícito: STATUS_ACCESS_DENIED, errno 1; `dup()` da EPERM |
| W011 | el cliente recibe EINVAL de `recvmsg` al recibir un descriptor | `pw_wine_dup`: ante EPERM reabre la ruta registrada al abrir el archivo |
| W012 | igual que W011; el marcador muestra `recvmsg_failed stage=cloexec errno=22` | Marcadores por capa en `sendmsg`/`recvmsg` y sonda aislada de `SCM_RIGHTS` |
| W013 | **passed**: `result.txt` idéntico al de Windows, salida 0 | `MSG_CMSG_CLOEXEC`: ante EINVAL de `fcntl(F_SETFD)` no se marca el descriptor (no hay `exec`); sondas de `F_GETFL`/`F_SETFL`/`FIONBIO` |

Hasta W010, en la consola Wine llega a:

```
paths_ready, virtual_ready, environment_ready, first_teb_ready, debug_ready,
server_step sock_init … load_intl_file, init_directories (dispositivos, sesiones,
tipos, symlinks, eventos) → dir_intl_mapping: dup EPERM
```

## Decisiones de plataforma (documentadas, no éxitos simulados)

- **`lstat` → `stat` ante EPERM.** La app no puede leer enlaces, así que Wine no ve ninguno. Marcador: `PWBOOT lstat_eperm_served_by_stat`.
- **ino/dev desde `fstat`.** Si la ruta no se puede abrir, quedan los ceros reales.
- **`dup` por reapertura** (W011). Sólo vale para archivos y directorios abiertos por `pw_wine_open`. El descriptor nuevo tiene su propio offset y sus propios flags de estado; el offset se copia una vez. Sockets y pipes devuelven el EPERM real. Marcador: `PWBOOT dup_eperm_reopen_by_path`.
- **Stdout/stderr al log** sólo en el launcher de hardware (`--wrap`), no en Wine.
- **Close-on-exec sin efecto** (W013).
  - `pw_wine_recvmsg` con `MSG_CMSG_CLOEXEC` no falla cuando `fcntl(F_SETFD)` da EINVAL.
  - Una app de PS4 no puede hacer `exec`, y Wine corre con `WINELOADERNOEXEC=1`, así que la marca no tiene efecto.
  - Cualquier otro errno sigue siendo un error.
  - Marcador: `PWBOOT cloexec_einval_no_exec`.

## Próximo paso

- Ejecutar W012 y bajar el log con `python3 tools/fetch-hardware.py --build W012 --host 192.168.68.104`.
- Probables siguientes puntos de fricción en el mismo camino:
  - el paso de descriptores entre cliente y servidor (`SCM_RIGHTS` dentro del proceso; ver W011);
  - la memoria ejecutable para PE64 y el traductor.
## Regresiones Linux con el código de W011

- **Primera corrida** (`reports/wine-hardware-w011/regressions-25/`): falló un solo caso, el prefijo vacío. Terminó con 0xc000007b en lugar del 0xc0000135 esperado.
  - Causa: la tabla de montaje se aplicaba a todo prefijo. En un prefijo nuevo, Wine crea sus propios enlaces y su `z:` apunta a `/`, no a `../..`.
  - Corrección: `wine_boot.c` registra la tabla sólo en modo `--prepared-prefix`, que es el modo del hardware.
- **Segunda corrida** (`reports/wine-hardware-w011/regressions-25b/`): **passed**. Pasaron el texto, `explorer` y la matriz completa del incremento 24 con la del 18.
- W011 se reconstruyó con esa corrección. Está en `out/wine-hardware-w011/` y todavía no se subió.

## Resultado físico de W011

`reports/wine-hardware-w011/physical/20261031T182023Z/` (la consola pasó a 192.168.68.104).

- Aparece `PWBOOT dup_eperm_reopen_by_path`: la reapertura por ruta resolvió el mapping del NLS.
- El servidor interno completa `init_directories`, `init_threading` e `init_registry`, y crea su hilo. El canal entre el cliente y el servidor queda listo (`inprocess_channel_ready`).
- La primera recepción de un descriptor en el cliente falla: `wine client error:0: recvmsg Invalid argument`. Wine termina con `_exit(1)` y después el manejador registra señales durante la salida.
- Falta saber de dónde viene el EINVAL. Puede venir del kernel, de la conversión del encabezado o del `fcntl(F_SETFD)` con que se emula `MSG_CMSG_CLOEXEC`. W012 lo registra.

## W012

- `pw_wine_sendmsg` y `pw_wine_recvmsg` emiten `PWBOOT <llamada>_failed stage=header|control|kernel|flags|cloexec errno=…` en cada rechazo.
- El launcher prueba `SCM_RIGHTS` aislado:
  - `socketpair`, enviar un archivo y recibirlo sin flags, con `fcntl` F_GETFD/F_SETFD sobre el descriptor recibido;
  - lo mismo con `MSG_CMSG_CLOEXEC`.
- PKG `/data/pkg/orbis-win-W012-f8a2adfe0e74.pkg` (APP_VER 01.11), subido y verificado.
- Resultado (`reports/wine-hardware-w012/physical/20261031T183216Z/`):
  - `SCM_RIGHTS` funciona: se envía un archivo y se recibe como fd 20, con el mismo inodo y dispositivo.
  - `fcntl` F_GETFD y F_SETFD dan EINVAL. Por eso falla `MSG_CMSG_CLOEXEC`, tanto en la sonda como en Wine (`recvmsg_failed stage=cloexec errno=22`).

## W013

- `/data/pkg/orbis-win-W013-333f3d8fb580.pkg` (APP_VER 01.12), subido y verificado.
- Cambio: close-on-exec sin efecto ante EINVAL (ver decisiones).
- Sondas nuevas: `F_GETFL`, `F_SETFL O_NONBLOCK` y `ioctl(FIONBIO)` sobre un archivo y un socket. Wine usa `F_SETFL` para los descriptores no bloqueantes.

## Resultado físico de W013: passed

`reports/wine-hardware-w013/physical/20261031T195509Z/`, una corrida.

- Aparecen `PWBOOT cloexec_einval_no_exec` y `dup_eperm_reopen_by_path`, y el canal entre el cliente y el servidor funciona.
- Wine carga las DLL. Los `image_read_fallback` son lecturas de secciones en lugar de mapeos, por el camino ya existente.
- Ejecuta `console32-bare.exe` por WoW64 con wowprospero.
- `result.txt` = `sum=500500;thread=ok;dll=ok`. Su SHA-256 `029a3f30…a05` es idéntico a `reports/increment11-windows-reference/result.txt`.
- `process_exit method=exit status=0`.
- Observaciones sin resolver, posteriores al resultado:
  - `fixme:ntdll:create_logical_proc_info stub`.
  - Dos `err:wow:log_reset syscall 0x43 came back replaced`.
  - Tras `exit(0)`, el manejador registra tres señales 31 (trapno 22) dentro de libkernel y un `err:seh:call_seh_handlers invalid frame` durante el cierre.
- **Segunda corrida** (`reports/wine-hardware-w013/physical/20261031T195721Z/`, `run-0002.log`): **passed**.
  - `result.txt` tiene el mismo SHA-256.
  - El `result.txt` de la primera corrida, archivado por el launcher, también coincide.
  - Salida 0, con las mismas señales y los mismos `err:` en el cierre.
  - Además aparece `err:seh:NtRaiseException Exception frame is not in stack limits` después de la salida.
  - Dos de dos corridas pasaron.
- Análisis del cierre:
  - La "señal 31" es SIGSYS en la numeración del SDK (musl/Linux). El trampolín de `pw_wine_sigaction` traduce la de FreeBSD.
  - `err=0x2` es el largo de la instrucción `syscall`, que FreeBSD guarda al entrar a una syscall.
  - La primera ocurre en el hilo 0024 justo después de `process_exit method=_exit`, con `rip` dentro de libkernel.
  - Hipótesis, todavía no confirmada: una app retail recibe SIGSYS en la syscall `exit` de `_exit`. El manejador vuelve a llamar a `_exit` y el sistema termina matando la app.

## W014

- `/data/pkg/orbis-win-W014-674d897fd4ab.pkg` (APP_VER 01.13), subido y verificado. Enlaza `libSceSystemService`.
- El manejador registra además `si_code`, `rax` (el número de syscall), `rdi` y la dirección de retorno en la pila.
- `_exit`:
  - El primer llamador registra el estado y pide el cierre al sistema con `sceSystemServiceLoadExec("exit", NULL)` (marcador `system_close load_exec rc=`).
  - Si el rc es 0, espera hasta 10 s a que el sistema cierre la app.
  - Si el rc no es 0, o si pasan los 10 s (marcador `system_close_timeout`), se ejecuta el `_exit` original.
- Un SIGSYS no vuelve a llamar a `_exit`: espera ese mismo cierre.

- Resultado (`reports/wine-hardware-w014/physical/20261031T204439Z/`): **passed**.
  - `result.txt` tiene el mismo SHA-256 que el de Windows y la salida fue 0.
  - El log termina en `process_exit method=_exit status=0`.
  - No aparece el marcador `system_close load_exec rc=`, ni ninguna señal, ni los `err:seh` del cierre. La app terminó dentro de `sceSystemServiceLoadExec("exit")`, sin volver.
  - Según el usuario, la app volvió al menú de la consola sin el error CE-34878-0.
  - Como no hubo SIGSYS, el número de syscall quedó sin medir. La hipótesis sobre la syscall `exit` sigue siendo indirecta.
- Pendiente:
  - sockets no bloqueantes: `F_SETFL` y `FIONBIO` dan EACCES sobre un socket. Este EXE no lo necesitó.

## W015: primer programa GUI en la consola

- `/data/pkg/orbis-win-W015-8b373bb3ac89.pkg` (APP_VER 01.14), subido y verificado.
- Programa: `C:\orbis\gui-window64.exe`, el fixture PE64 del incremento 24, sin wowprospero.
  - Abre una ventana, la pinta y lee un píxel.
  - Escribe `result.txt`, que se compara con `reports/increment24-windows-reference/result.txt` (`painted=1;pixel=8c3c14;client=464x280`).
- Runtime: el de W014 más el cierre PE64 GUI (`out/wine-gui`), `gui-window64.exe`, `gui-text64.exe` y las fuentes Tahoma y Marlett con su registro.
  - Se prepararon igual que con `run-linux-wine.py --wine-gui`.
  - Se subieron 64 archivos nuevos o cambiados, entre ellos `system.reg` y `user.reg` con las fuentes. Los otros 429 ya estaban.
- Los cuadros que presenta Wine se guardan en `/data/orbis-win/w015/frames`.
- Resultado (`reports/wine-hardware-w015/physical/20261031T212754Z/`): **passed**.
  - `result.txt` = `painted=1;pixel=8c3c14;client=464x280`, idéntico al de Windows. Salida 0 y cierre limpio.
  - Wine presentó cinco cuadros. En el cuarto (`frame-000004.png`) se ve la ventana con 129.920 píxeles del color pintado, que es exactamente 464×280.
  - Diferencia con el emulador:
    - En la consola, el texto del título se dibuja con glifos de Marlett (símbolos), mientras que los botones de la barra salen bien.
    - En el fork pasaba al revés: título con Tahoma y botones como "0 1 r".
    - El log no tiene mensajes de fuentes porque no estaba activado `+font`.

## W016: diagnóstico de fuentes

- `/data/pkg/orbis-win-W016-5e857e989b1a.pkg` (APP_VER 01.15), subido y verificado.
- Mismo programa que W015, con `--winedebug=+font`.
- Sonda en el launcher: `open`, `fstat` y `mmap(PROT_READ, MAP_PRIVATE)` de `tahoma.ttf`, `tahomabd.ttf` y `marlett.ttf`, más los primeros 4 bytes, como hace `map_font_file` en win32u.
- Resultado (`reports/wine-hardware-w016/physical/`): **crashed**.
  - La sonda muestra que las tres fuentes se abren y se mapean bien (`magic=00000100`). El `mmap` queda descartado como causa.
  - Wine se detiene después de `paths_ready`, sin llegar a `virtual_ready`. La app queda en "STARTING WINE" y luego la consola la cierra con error, sin marcador del manejador.
  - La única diferencia con W015 es `WINEDEBUG=+font`. El primer `TRACE` de `virtual_init` lee las opciones de depuración.

## W017: dónde se cuelga `WINEDEBUG`

- `/data/pkg/orbis-win-W017-0627b3c68517.pkg` (APP_VER 01.16), subido y verificado.
- Sobrecarga:
  - marcadores `PWBOOT debug_options start|stderr_checked|app_name|parsed` en `init_options` (`debug.c`);
  - `PWBOOT virtual_step first_trace_done` en `virtual_init`.
- Mismo programa y mismo `+font` que W016.
- Limpieza remota pedida por el usuario: en `/data/pkg` se borraron los PKG W001–W016. Quedan W017, H001, H001B y dos paquetes ajenos al proyecto.
- Resultado (`reports/wine-hardware-w017/physical/20261031T214209Z/`): **crashed**, el mismo cuelgue que W016.
  - `debug_options`: `winedebug=+font`, stderr comprobado, `app_name=gui-window64.exe` y `parsed count=1`. La lectura de `WINEDEBUG` funciona.
  - El último marcador es `virtual_step first_trace_done`. El cuelgue está más adelante en `virtual_init`: límite del espacio de direcciones, writewatch, `mmap_init` o heap virtual.

## W018: separar las dos diferencias con W015

- `/data/pkg/orbis-win-W018-590c79286b38.pkg` (APP_VER 01.17), subido y verificado. Se borró el PKG de W017.
- Se quita la sonda de fuentes del launcher (`HW_FONT_MAP_PROBE` sin definir) y se mantiene `+font`.
- Marcadores en cada paso restante de `virtual_init`: `addr_space_limit=`, `writewatch_done`, `mmap_init_done` y `virtual_heap=`.
- Cómo leer el resultado:
  - Si pasa, la sonda de fuentes del launcher era la causa del cuelgue.
  - Si se cuelga, el último marcador indica en qué paso.
- Resultado (`reports/wine-hardware-w018/physical/20261031T214736Z/`): **crashed**, el mismo cuelgue sin la sonda.
  - La sonda queda descartada como causa.
  - `addr_space_limit=0x7fffffff0000`; pasan `writewatch_done` y `mmap_init_done`.
  - Wine se cuelga en `alloc_virtual_heap`, donde mapea con `MAP_FIXED` el bloque de vistas y la tabla de protección al final de un área reservada.

## W019: intentos de `alloc_virtual_heap`

- `/data/pkg/orbis-win-W019-507b1d6fe756.pkg` (APP_VER 01.18), subido y verificado. Se borró el PKG de W018.
- Marcadores nuevos:
  - `virtual_step heap_request size= limit=`;
  - `virtual_heap_try area= at= size=` y `virtual_heap_result ret= errno=` en cada intento;
  - `virtual_heap_fallback_alloc`.
- Se mantiene `+font`, para reproducir el cuelgue.
- Resultado (`reports/wine-hardware-w019/physical/20261031T215509Z/`): **crashed**.
  - `heap_request size=240000 limit=0x7fffffff0000`.
  - Primer intento: área `0x7ffffe000000-0x7fffffff0000` (la que reservó `mmap_init` con el reservador del kernel), `at=0x7fffffdb0000`.
  - No hay `virtual_heap_result`. La app termina dentro de ese `mmap(MAP_FIXED, RW)`, sin que el manejador registre ninguna señal.
  - El mismo camino funcionó en W013 y W015.

## W020: con o sin `WINEDEBUG`

- `/data/pkg/orbis-win-W020-4b6a76fa6c46.pkg` (APP_VER 01.19), subido y verificado. Se borró el PKG de W019.
- Los mismos argumentos que W015, sin `+font`, con todos los marcadores de `virtual_init` y `alloc_virtual_heap`.
- Sondas nuevas en el launcher:
  - `flexible_memory`, con `sceKernelAvailableFlexibleMemorySize`;
  - `top_region`: hasta 8 regiones de `sceKernelVirtualQuery` desde `0x7ff000000000`.
- Cómo leer el resultado:
  - Si pasa, el cuelgue depende de `WINEDEBUG`.
  - Si se cuelga en el mismo lugar, es una diferencia entre corridas, y las sondas muestran el estado de esa zona.
- Resultado (`reports/wine-hardware-w020/physical/20261031T215958Z/`): **crashed** en el mismo `virtual_heap_try`.
  - `WINEDEBUG` queda descartado. W015 pasó por una diferencia entre corridas.
  - `flexible_memory available=447741952`: no falta memoria flexible.
  - `top_region rc=0x8002000d`: `sceKernelVirtualQuery` responde EACCES en esa zona.

## W021: sin reservar la zona alta

- Decisión de plataforma (overlay, `mmap_init`): en Orbis no se reserva `0x7ffffe000000-0x7fffffff0000`. Marcador: `PWBOOT top_area_not_reserved`.
  - Wine usa sus otras áreas reservadas (`0x10000-0x68000000` y `0x7f000000-0x7fff0000`).
  - Si no hay lugar, usa la asignación libre (`anon_mmap_alloc`).
- `/data/pkg/orbis-win-W021-36fd58d86be9.pkg` (APP_VER 01.20), subido y verificado. Se borró el PKG de W020.
- Programa: `gui-window64.exe` sin `WINEDEBUG`.
- Resultado (`reports/wine-hardware-w021/physical/20261031T220443Z/`): **crashed**, más adelante que antes.
  - `top_area_not_reserved`. Ninguna área baja sirve para Win64, así que hay `virtual_heap_fallback_alloc` y el heap queda en `0x201000000`.
  - Llegan `virtual_ready`, todo el servidor, `user_shared_data_ready`, `external_prefix_ready` y `main_image_load` (base `0x140000000`).
  - La app termina sin señal antes de cargar `ntdll.dll` PE64. En W015 ese tramo pasaba.
  - En W013 la pila del hilo principal estaba en `0x7ffffe1…`, dentro de la zona que ya no se reserva.

## W022: entre la imagen principal y ntdll

- `/data/pkg/orbis-win-W022-9c09ac85d911.pkg` (APP_VER 01.21), subido y verificado. Se borró el PKG de W021.
- Marcadores `PWBOOT main_step`:
  - `load_order_ready`;
  - `thread_stack base= limit=`;
  - `keyed_event_ready`;
  - `ntdll_open` y `ntdll_mapped status= module=`.
- Resultado (`reports/wine-hardware-w022/physical/20261031T221016Z/`): **crashed**.
  - Pila principal en `0x2017b8000-0x2019b0000` y evento creado.
  - Muere dentro de `open_builtin_pe_file` de `ntdll.dll`.
  - `ntdll.dll` tiene ImageBase `0x170000000` y es reubicable (DllCharacteristics 0x160). Wine la ubica de arriba hacia abajo desde `min(user_space_limit, host_addr_space_limit) = 0x7fffffff0000`.

## W023: tope del espacio de direcciones

- Decisión de plataforma (overlay, `virtual_init`): en Orbis, `host_addr_space_limit` se recorta a `0xfc00000000`.
  - Según `address_space.h` de shadPS4, el área de mapeo de una app de PS4 termina en `0xFBFFFFFFFF`.
  - Cerca del tope de `0x7fff…` fallaron, sin señal, tanto el heap (W019/W020) como `ntdll` (W022). `sceKernelVirtualQuery` responde EACCES en esa zona.
  - El marcador `virtual_step addr_space_limit=` muestra el valor efectivo.
- Se mantiene `top_area_not_reserved`.
- `/data/pkg/orbis-win-W023-7945700f76e5.pkg` (APP_VER 01.22), subido y verificado. Se borró el PKG de W022.
- Resultado (`reports/wine-hardware-w023/physical/20261031T222107Z/`): **passed**.
  - `addr_space_limit=0xfc00000000`.
  - Heap en `0x201000000`.
  - `ntdll_mapped status=40000003 module=0xfbffd10000` (STATUS_IMAGE_NOT_AT_BASE: se reubicó por debajo del tope).
  - `result.txt` = `painted=1;pixel=8c3c14;client=464x280`, idéntico al de Windows. Salida 0.
  - Los cuadros 3 a 5 tienen los mismos hashes que en W015 (`e0fd24a7…`, `3ac7ec09…`, `2bf05020…`). La imagen es idéntica, incluido el título con glifos de Marlett.
- Segunda corrida (`reports/wine-hardware-w023/physical/20261031T222153Z/`, `run-0002.log`): **passed**.
  - Mismo `result.txt` (SHA-256 `7a4d5541…`), y también coincide el de la primera corrida, archivado.
  - `ntdll` quedó en la misma dirección, el cuadro 4 tiene el mismo hash y la salida fue 0.
  - Dos de dos corridas pasaron.

## W024: trazas de fuentes

- `/data/pkg/orbis-win-W024-a53bf2415351.pkg` (APP_VER 01.23), subido y verificado. Se borró el PKG de W023.
- Igual que W023, con `--winedebug=+font`, para ver qué fuente elige win32u para el título.
- Resultado (`reports/wine-hardware-w024/physical/20261031T223337Z/`): **passed**, con 10.157 líneas de log.
  - Marlett se carga con el parser OpenType de win32u, que abre los archivos mediante `pw_wine_*`.
  - Tahoma y Tahoma Bold tienen bitmaps embebidos. El parser las deriva a FreeType (`unsupported sfnt font: embedded bitmap data`), y FreeType falla: `Unable to load font ".../dosdevices/c:/windows/Fonts/tahoma.ttf" err = 1` (no puede abrir el recurso).
  - Causa: `builds/unix/ftsystem.c` abre la ruta con `open()` de libc. En la PS4, `dosdevices/c:` es la tabla de montaje de `pw_wine_fs`, no un enlace. En el fork el enlace existe, y por eso allí carga.
  - Al quedar Marlett como única familia TrueType cargada, el texto del título se dibuja con sus glifos.

## W025: FreeType abre por la tabla de montaje

- `platform/ps4/pw_freetype_posix.h` agrega `#define open(...) pw_wine_open(0, ...)`, junto al `fstat` que ya estaba adaptado.
- `libfreetype.a` ahora importa `pw_wine_open`. Se reconstruyeron FreeType y win32u (47 unidades, ninguna falla) y se volvió a enlazar.
- `/data/pkg/orbis-win-W025-5a801f59718f.pkg` (APP_VER 01.24), subido y verificado. Se borró el PKG de W024.
- Mantiene `+font`, para confirmar que Tahoma carga.
- Resultado (`reports/wine-hardware-w025/physical/20261031T224137Z/`): **passed**.
  - `new_ft_face` carga `tahoma.ttf` y `tahomabd.ttf`. Se agregan "Tahoma" y "Tahoma Bold" a la familia Tahoma.
  - `result.txt` idéntico al de Windows y salida 0.
  - En `frame-000014.png` el título se lee "orbisdesk GUI" en Tahoma Bold, y los botones de minimizar, maximizar y cerrar se dibujan con Marlett. Hay 129.920 píxeles del color pintado.
  - Diferencia con el fork: en el emulador los botones salen como "0 1 r". Allí no se usa Marlett, y no se investigó.
  - No se volvió a correr la matriz Linux con el cambio del adaptador de FreeType.

## W026: texto con FreeType en la consola

- `/data/pkg/orbis-win-W026-08995198fd87.pkg` (APP_VER 01.25), subido y verificado. Se borró el PKG de W025.
- Programa: `C:\orbis\gui-text64.exe`, el fixture del incremento 25, sin `WINEDEBUG`.
  - Carga Tahoma desde memoria y comprueba familia, métricas e índices de glifos.
  - Dibuja con `TextOutW` sobre una DIB y sobre la ventana, con números, acentos y eñe.
  - Escribe `text-result.txt`.
- El launcher archiva el `text-result.txt` previo (macro `HW_RESULT`).
- `fetch-hardware.py` usa `result_name` y `expected_prefix` del manifest.
  - Como en el incremento 25, se exige `passed=1;family_tahoma=1;` y salida 0.
  - La tinta de FreeType no tiene que coincidir con la de Windows (1.397 píxeles).
- Resultado (`reports/wine-hardware-w026/physical/20261031T224623Z/`): **passed**, una corrida.
  - `text-result.txt`: `passed=1;family_tahoma=1;painted=1;width=299;height=24;metric_height=24;ink=1252;window_ink=1252`.
  - La tinta es la misma que en el fork: 1.252 píxeles en la DIB y en la ventana. Windows: ancho 298 y 1.397 píxeles.
  - Salida 0.
  - En `frame-000004.png` se lee "Wine PS4: texto 0123456789 áéñ". El título "Wine PS4 - texto" está en Tahoma Bold y los botones, en Marlett.

## W027: explorer y evidencia más liviana

- `/data/pkg/orbis-win-W027-7523a490fbed.pkg` (APP_VER 01.26), subido y verificado. Se borró el PKG de W026.
- Programa: `C:\windows\explorer.exe /desktop=shell,800x600`, el caso de explorer del incremento 25, con la barra de tareas y el botón Start.
  - No hay fuente de entrada: el menú Start no se puede abrir.
  - explorer no termina solo. `fetch-hardware.py` lo clasifica como `presented` si hay cuadros de 800×600 y ningún registro de crash (`runs_until_closed`). Nunca lo clasifica como `passed`.
- Velocidad:
  - Sin `fsync` por línea en `note`, `sceKernelDebugOutText` ni la salida de Wine. Lo escrito con `write()` ya está en el kernel y sobrevive a que el proceso termine. Solo los registros de salida, crash y cierre siguen haciendo `fsync`.
  - El sink del hardware se compila con `PW_SINK_MAX_DUMPS=8`; el fork sigue en 24.
  - Con `PW_SINK_TIMING=1`, los cuadros registran `t_ms`, el tiempo de proceso.
  - `calling_wine_boot_main` y `process_exit` también registran `t_ms`.
- Resultado (`reports/wine-hardware-w027/physical/20261031T225306Z/`): **presented**.
  - El log tiene 506 líneas.
  - Tiempos de proceso: el panel del launcher aparece a 1,36 s y Wine arranca a 1,56 s. El primer cuadro del escritorio llega a 4,42 s, y el botón Start a 5,02 s (cuadro 5).
  - `frame-000005.png` muestra el escritorio 800×600 con la barra de tareas y el botón "Start" con el icono de Wine. A simple vista es igual a `reports/increment25-accepted/explorer.png` del fork.
  - Aparecen tres `err:ole` (`StdMarshalImpl_MarshalInterface`, `CoMarshalInterface`, `apartment_get_local_server_stream`, hr 0x80004002). No se investigaron.
  - No hay registro de crash. La app la cerró el usuario.
  - No hay tiempos de W026 para comparar la ganancia de quitar el `fsync` y los dumps.

## W028: control y escritorio de 1280×720

- `/data/pkg/orbis-win-W028-94ba49ee0bfa.pkg` (APP_VER 01.27), subido y verificado. Se borró el PKG de W027.
  - Se volvieron a subir dos archivos del runtime cuyo hash no coincidía en la consola. Probablemente son el registro, que Wine reescribe al salir. Quedan como en el staging.
- Escritorio: `explorer.exe /desktop=shell,1280x720` y `WINE_PS5_DESKTOP=1280x720` (variable que ya leía `ps5drv.c`). Ocupa toda la salida de video sin escalar.
- Entrada (`native/hw_pad.c`, solo para el hardware):
  - Inicialización: `sceUserServiceInitialize`, `sceUserServiceGetInitialUser`, `scePadInit` y `scePadOpen`.
  - Un hilo lee el control con `scePadReadState` cada 16 ms.
  - Mapeo:

    |Control| Wine |
    |---|---|
    | Stick izquierdo | Movimiento del puntero, con respuesta cuadrática y zona muerta de 24 |
    | X | Botón izquierdo |
    | Círculo | Botón derecho |
    |Cruceta|Flechas|
    | Triángulo |Entra|
    | Cuadrado | Esc |
    |Opciones| Tecla Windows |

  - Los eventos llegan a `ps5drv.c` por `pw_wine_next_input`.
  - Wine se despierta por un `socketpair` (`pw_wine_input_fd`).
    - El extremo de lectura tiene `SO_RCVTIMEO` de 1 ms, porque los sockets no se pueden volver no bloqueantes (W013). Así termina el bucle de `read()` con que el driver vacía el socket.
    - Si `setsockopt` falla, no hay descriptor de despertar y queda registrado.
  - Marcadores: `pad_open`, `pad_wake`, `pad_thread` y hasta 32 `pad_event`.
- Puntero:
  - `ps5drv.c` no dibuja cursor. El sink del hardware (`PW_SINK_EXTERNAL_INPUT`) dibuja una flecha de 11×17 sobre el último cuadro.
  - Cuando el puntero se mueve, el sink vuelve a mostrar ese cuadro.
  - El fork compila el sink sin esa opción y conserva el stub de entrada.
- Resultado (`reports/wine-hardware-w028/physical/20261031T230639Z/`, segunda descarga): **presented**.
  - `pad_open` dio un handle válido y funcionaron `pad_wake` (`rcvtimeo=0`) y `pad_thread rc=0`.
  - Se registró un clic con X (`type=3 code=0 down=1/0`) en `640,360`, el centro. El puntero nunca se movió del centro.
  - La primera descarga (`20261031T230607Z`) se hizo con la app todavía corriendo, sin eventos. `fetch-hardware.py` la marcó como `crashed` porque esperaba cuadros de 800×600. Ahora acepta cualquier cuadro posterior a `calling_wine_boot_main`.
- W029 (`orbisdesk-W029-6b98c73025dd.pkg`): agregó la lectura cruda del control. Se reemplazó por W030 antes de correrlo.

## W030: control, mouse y teclado USB

- `/data/pkg/orbis-win-W030-b8caa8d188c8.pkg` (APP_VER 01.29), subido y verificado. Se borró el PKG de W029.
- `native/hw_pad.c` lee tres fuentes cada 16 ms:
  - **Control**: igual que W028, sin exigir `data.connected`. Registra la lectura cruda (`pad_read`: rc, botones, sticks y los primeros 16 bytes) en las primeras cinco lecturas y luego cada ~2 s durante un minuto.
  - **Mouse USB**: `sceMouseInit`, `sceMouseOpen` en modo combinado y `sceMouseRead`, con la estructura del módulo de mouse de shadPS4. El movimiento relativo mueve el mismo puntero. Botones izquierdo, derecho y del medio.
  - **Teclado USB**: `sceKeyboardInit`, `sceKeyboardOpen` y `sceKeyboardReadState`.
    - Los códigos USB HID se traducen a teclas virtuales: letras, números, signos, F1–F12, navegación, Enter, Esc, Backspace, Tab y Caps Lock.
    - Los modificadores se interpretan como el byte de modificadores HID (Ctrl, Shift, Alt, Windows). No está comprobado en la consola.
- Mouse y teclado no se importan en el ELF:
  - Se cargan en tiempo de ejecución con `sceSysmoduleLoadModule(MOUSE)` / `sceSysmoduleLoadModuleInternal(INTERNAL_KEYBOARD)` y `sceKernelLoadStartModule`, en `/system/common/lib` o `/system/priv/lib`.
  - Las funciones se resuelven con `sceKernelDlsym`.
  - Si falta algo, la app arranca igual con el control.
  - Marcadores: `input_module`, `input_symbol`, `mouse_open`, `keyboard_open`, `input_wake`, `input_thread` y hasta 48 `input_event source=pad|mouse|keyboard`.
- Resultado (`reports/wine-hardware-w030/physical/20261031T231623Z/`): **presented**, sin entrada.
  - Según el usuario, el puntero no se movió ni con el control, ni con el mouse, ni con el teclado.
  - Control: `scePadReadState` dio `rc=0` y `connected=1` durante un minuto, y el cuaternión cambia en cada lectura. Pero los botones siempre fueron `0` y los sticks `128,128`, y no hubo ningún `input_event`.
  - Mouse: `sceSysmoduleLoadModule(MOUSE)=0`. Desde `/system/common/lib` y `/system/priv/lib`, `sceKernelLoadStartModule` da `0x80020002` (no existe), y no se resolvió ningún símbolo.
  - Teclado: `sceSysmoduleLoadModuleInternal(INTERNAL_KEYBOARD)=0x805a1000` y la misma ruta inexistente.

## W031: separar el control de los módulos USB

- `/data/pkg/orbis-win-W031-b2787855f51e.pkg` (APP_VER 01.30), subido y verificado. Se borró el PKG de W030.
- Los primeros 20 s (1.250 lecturas) solo se lee el control. Después se registra `input_usb_open_after_pad_only` y se abren el mouse y el teclado.
  - En W028, sin módulos USB, sí llegó un clic con X.
- El control registra las tres primeras lecturas y luego cada cambio de botones o de zona del stick, hasta 64. Ya no se toma una muestra cada 2 s.
- Rutas de los módulos:
  - primero `/<sceKernelGetFsSandboxRandomWord>/common/lib/` y `.../priv/lib/`;
  - después `/system/common/lib/`.
- Teclado: primero el sysmodule público `KEYBOARD` (0x0106), después el interno.
- Resultado (`reports/wine-hardware-w031/physical/20261031T232719Z/`, dos corridas): **presented**, con entrada parcial.
  - Botones del control: llegan X, Círculo, Triángulo y Cuadrado (`buttons=0x4000`, `0x2000`, `0x1000`, `0x8000`), y generan `input_event`. Los sticks valen `128,128` en todas las lecturas.
  - Mouse: `/bnvpCiZOba/common/lib/libSceMouse.sprx` carga (módulo 0x91) y `sceMouseOpen` da un handle. El puntero se mueve y hay clics en `31,711`, sobre el botón Start.
  - Teclado: el sysmodule público `KEYBOARD` carga (módulo 0x93) y `sceKeyboardOpen` da un handle. Llegan teclas (`code=72`, `66`, `74`, ...).
  - Según el usuario, el puntero se mueve pero los clics y las teclas no tienen efecto. No hay cuadros nuevos después del escritorio: solo 4 capturas, y el sink guarda hasta 8 distintas.
  - Los eventos entran en la cola de `hw_pad.c`, pero win32u no responde. Falta saber si `ps5drv.c` los saca de la cola.
- La cargar del mouse y el teclado no afectó al control: los botones ya funcionaban antes de los 20 s y siguieron después.

## W032: ¿win32u saca los eventos?

- `/data/pkg/orbis-win-W032-66d4e9b1ba06.pkg` (APP_VER 01.31), subido y verificado. Se borró el PKG de W031.
- `pw_wine_next_input` registra:
  - `input_taken` (hasta 32), con número de llamada, evento y cola restante;
  - `input_poll calls= taken=` en las primeras cuatro llamadas y luego cada 2.000.
- Con cada cambio del control se agrega `scePadRead` (`pad_read_buffered`), para comparar los sticks con los de `scePadReadState`.
- Resultado (`reports/wine-hardware-w032/physical/20261031T233207Z/`): **presented**.
  - Los eventos del control, el mouse y el teclado entran en la cola.
  - **Cero** llamadas a `pw_wine_next_input`: no aparece ningún `input_poll` ni `input_taken`.
  - `scePadRead` devuelve 0 muestras (`pad_read_buffered rc=0`), así que no sirve para comparar los sticks.
  - Causa:
    - win32u solo llama a `ProcessEvents` cuando el servidor marca la cola con `QS_DRIVER`.
    - Lo marca cuando el descriptor registrado con `set_queue_fd` tiene datos.
    - Ese handler hace `dup(unix_fd)`. Con un socket, `pw_wine_dup` devolvía el EPERM real, porque un socket no tiene ruta para reabrir.
    - `queue->fd` nunca se creaba y `register_input_fd` ignora el error.

## W033: `dup` real por SCM_RIGHTS

- Decisión de plataforma (`pw_wine_fs.c`):
  - Ante EPERM, `pw_wine_dup` envía el descriptor por un socketpair privado con SCM_RIGHTS y usa el que recibe.
  - El nuevo comparte la descripción de archivo (offset y flags de estado), como un `dup` real, y sirve también para sockets.
  - La reapertura por ruta de W011 queda como respaldo.
  - Marcador: `PWBOOT dup_eperm_scm_rights`.
- `/data/pkg/orbis-win-W033-a9f704fa8753.pkg` (APP_VER 01.32), subido y verificado. Se borró el PKG de W032.
- Resultado (`reports/wine-hardware-w033/physical/20261031T233904Z/`): **presented**.
  - Aparece `dup_eperm_scm_rights`, en el primer EPERM (el mapping del NLS).
  - Llegan 48 eventos, entre ellos clics del mouse en `30,713`, sobre Start.
  - Sigue sin haber ninguna llamada a `pw_wine_next_input`.

## W034: cada eslabón del despertar

- Marcadores nuevos, para ver dónde se corta la cadena:
  - win32u `register_input_fd`: `input_fd_register fd= to_handle=` y `input_fd_set_queue status=`.
  - Servidor `set_queue_fd`: `queue_fd source= dup= errno= fd_object=`.
  - Servidor `msg_queue_poll_event`: `queue_fd_event event=` (hasta 16).
  - `pw_wine_poll`: `poll_unsupported fd= events= net_errno= stat= mode=` cuando un descriptor no se puede registrar en `sceNetEpoll` y la llamada entera falla.
- Se reconstruyeron la parte Unix, el servidor y win32u (47 unidades, ninguna falla) y se volvió a enlazar.
- `/data/pkg/orbis-win-W034-2729a8022cc5.pkg` (APP_VER 01.33), subido y verificado. Se borró el PKG de W033.
- Resultado (`reports/wine-hardware-w034/physical/20261101T001107Z/`): **presented**.
  - Registro correcto en los tres hilos de explorer: `to_handle=0`, `queue_fd dup=69/70/91 fd_object=1` y `set_queue status=0`.
  - Hay tres `queue_fd_event event=1`, así que el servidor sí detecta el socket con datos.
  - Después aparecen `poll_unsupported fd=69 events=0 net_errno=22 mode=140666` (socket) en cada vuelta.
    - Tras el aviso, el servidor deja ese fd sin eventos (`set_fd_events(fd, 0)`).
    - `sceNetEpollControl` rechaza una máscara vacía y `pw_wine_poll` hacía fallar la llamada entera.
    - El bucle del servidor quedaba trabado desde el primer evento.

## W035: `poll` con descriptores sin eventos

- Decisión de plataforma (`pw_wine_poll`): una entrada con `events=0` se registra pidiendo solo error y cierre (8|16), que es lo único que `poll()` informaría para ella.
  - Si `sceNetEpoll` tampoco lo acepta, la entrada se omite (marcador `PWBOOT poll_idle_fd_skipped`) en lugar de fallar con todos los descriptores.
- `/data/pkg/orbis-win-W035-cff2e75119ca.pkg` (APP_VER 01.34), subido y verificado. Se borró el PKG de W034.
- Resultado (`reports/wine-hardware-w035/physical/20261101T001652Z/`): **presented**. **El menú Start se abre con la entrada de la consola.**
  - Ya no aparece `poll_unsupported`. Siguen los `queue_fd_event`, y ahora win32u saca los eventos: `input_taken` con clics (`type=3`) y movimiento (`type=2`), sin cola pendiente (`queued=0`).
  - Hay capturas nuevas después del escritorio (cuadros 6, 8, 9 y 10). En `frame-000009.png`, el menú Start está abierto sobre la barra de 1280×720, con "Run..." y "Exit desktop".
  - El escritorio ocupa los 1280×720 de la salida.
  - Las capturas no incluyen el puntero, porque el sink lo dibuja solo en el buffer de video.
  - Sticks: el registro de cambios del control solo mostraba `128,128`, pero el usuario confirmó que el stick izquierdo mueve el puntero. Las lecturas registradas coincidían con momentos de stick quieto. El stick derecho no está asignado.
  - `scePadRead` no devuelve muestras. Solo se usa `scePadReadState`.

## W036 y W037: sin espera inicial, touchpad y "Exit desktop"

- W036 (`orbisdesk-W036-9e21a3647c8e.pkg`, APP_VER 01.35): el mouse y el teclado se abren en la primera lectura de la entrada, sin los 20 s de espera de W031. Se reemplazó por W037 sin correrlo.
- W037 (`/data/pkg/orbis-win-W037-c08dff44cd23.pkg`, APP_VER 01.36), subido y verificado. Se borró el PKG de W036.
  - **Touchpad**: el primer dedo mueve el puntero en forma relativa (×0,75 por unidad). Apretar el touchpad (`ORBIS_PAD_BUTTON_TOUCH_PAD`) es el botón izquierdo.
  - **"Exit desktop"**:
    - Pide confirmación y llama a `ExitWindows`. En user32, eso lanza `wineboot.exe --end-session --shutdown` como un proceso nuevo, que no puede existir en un título de PS4.
    - Decisión de plataforma (overlay, `NtCreateUserProcess`): en Orbis, si la línea de comando contiene `wineboot.exe` y `--shutdown`, se registra `PWBOOT session_end_terminates_title` y se llama a `NtTerminateProcess(NtCurrentProcess(), 0)`.
    - El cierre continúa por la salida normal del proceso y el `sceSystemServiceLoadExec("exit")` de W014.
- Resultado (`reports/wine-hardware-w037/physical/20261101T002808Z/`): **presented**, con salida 0.
  - El control, el mouse y el teclado se abren al inicio, sin espera.
  - Aparece `PWBOOT session_end_terminates_title`, y después `process_exit method=_exit status=0 t_ms=28869`. "Exit desktop" cierra el título.
  - Las 8 capturas se agotaron antes de que se abrieran el menú y el diálogo de confirmación, así que no quedaron guardados.
  - El log no distingue un clic del touchpad de uno con X (los dos son `source=pad code=0`). El usuario confirmó que el touchpad mueve el puntero y hace clic.

## Matriz Linux con los cambios de W011–W037

- `reports/wine-hardware-w037/regressions-25/`: no corrió los casos de Wine.
  - Se cortó en una verificación previa: `Baseline runs do not match the current out/eboot.bin`.
  - `--reuse-platform reports/increment25/regressions24` apunta a corridas nativas de un `out/eboot.bin` anterior (`476105bf…`). El actual es `89d8ff99…`.
- `reports/wine-hardware-w037/regressions-25b/`, que reutiliza las corridas nativas de `reports/wine-hardware-w011/regressions-25b/regressions24`, que sí coinciden:
  - La suite del incremento 18 pasó (PE, IPC, pipes, archivos, metadatos, hilos).
  - **Regresión** en el incremento 24: `gui-window64` en el fork se cuelga después de `dispatcher_slot_ready`, sin cuadros (timeout de 95 s).
    - El emulador falla en `GpuComm` con `vk_platform.h:66 Check ... ErrorOutOfDeviceMemory` (`reports/linux-wine-runs/20261101T004441626881Z/`).
    - Con el tope de W023, `ntdll` quedaba en `0xfbffd10000`, justo debajo del final del área de usuario de shadPS4.

## W038: tope más bajo, rueda, clic derecho con dos dedos y `launch.txt`

- Tope de memoria: `host_addr_space_limit` se recorta a `0x7ffff0000`, el final del rango administrado por el kernel (`SYSTEM_MANAGED_MAX`+1 de shadPS4, redondeado a 64 KiB). Ahí ya caían el heap y las pilas en la consola.
  - Corrida aislada de `gui-window64` en el fork con ese tope (`reports/linux-wine-runs/20261101T010323961339Z/`): **passed**, con el mismo resultado que Windows y 129.920 píxeles pintados.
  - Matriz completa con el ELF de W038 (`reports/wine-hardware-w038/regressions-25/`): **passed**, sin fallas.
    - Pasan las tres corridas de texto, explorer, la suite del incremento 24 y la del
      18.

    - Se reutilizan las corridas nativas de `reports/wine-hardware-w011/regressions-25b/regressions24` (mismo `out/eboot.bin`).
- Rueda:
  - `ps5drv.c` acepta un evento tipo 4 (delta en `y`, en unidades de 120) y lo envía como `MOUSEEVENTF_WHEEL`.
  - El stick derecho genera una muesca por cada 120 unidades acumuladas (inclinar hacia arriba sube).
  - La rueda del mouse USB genera 120 por unidad. El signo del dispositivo no está comprobado.
- Touchpad: apretar con dos dedos es el botón derecho. Un toque de dos dedos de menos de 300 ms, que se mueve menos de 40 unidades y sin apretar, es un clic derecho.
- `/data/orbis-win/launch.txt`: la primera línea es la ruta Windows del EXE y cada línea siguiente, un argumento (hasta 6). Sin el archivo, se abre el escritorio de explorer a 1280×720. Marcadores: `launch_file lines=` y `launch_arg`.
- Contexto: el escritorio de Wine no tiene menú contextual. Su ventana solo atiende el doble clic, así que el clic derecho sobre el escritorio vacío no abre nada, a diferencia de Windows.
- `/data/pkg/orbis-win-W038-3d8eac4c505d.pkg` (APP_VER 01.37), subido y verificado. Se borró el PKG de W037.

## W039: menos diagnóstico de entrada

- Preparado antes de probar W038, a pedido del usuario: siempre una iteración por delante.
- Se quitan las lecturas crudas del control (`pad_read`, `pad_read_buffered`) y los contadores `input_poll` e `input_taken`.
- Quedan:
  - `pad_read_failed`, cada ~10 s, solo si la lectura falla;
  - `input_first_request`, la primera vez que win32u pide eventos;
  - las aperturas (`pad_open`, `mouse_open`, `keyboard_open`);
  - los primeros 48 `input_event`.
- El resto es igual que W038.
- `/data/pkg/orbis-win-W039-e98d98394e37.pkg` (APP_VER 01.38), subido y verificado. Se conserva el PKG de W038, que todavía no se probó.

## W038 en la consola

- Corrida en `reports/wine-hardware-w038/physical/20261101T041248Z/`, clasificada `presented`.
- Memoria:
  - `addr_space_limit=0x7ffff0000`;
  - `ntdll` quedó en `0x7ffd00000`.
  - El tope más bajo no rompe el arranque en la consola.
- El escritorio aparece a los 4,3 s y el menú Start abre.
- Entrada:
  - clics izquierdo y derecho del mouse USB;
  - teclado USB;
  - clic derecho del touchpad (`source=touchpad type=3 code=1`), tres veces.
- La rueda no se puede confirmar con este log. Los 48 `input_event` se gastaron en clics y teclas antes de cualquier evento `type=4`.
- El usuario escribió `launch.txt` en el diálogo "Run". El log tiene `err:commdlg:DllMain failed to create activation context, last error 14001` y no muestra ningún aviso de error. `launch.txt` es un archivo en `/data/orbis-win/launch.txt`, no un comando: no estaba en la consola, así que el launcher usó los argumentos por defecto.
- La app no registró salida. El usuario la cerró desde el sistema.

## W040: presupuesto de log propio para la rueda

- La rueda tiene su propio presupuesto: 16 líneas `input_event ... type=4`. Así no compite con los 48 de clics y teclas.
- El resto es igual que W039.
- `/data/pkg/orbis-win-W040-fba6f2644021.pkg` (APP_VER 01.39), subido y verificado. Se borró el PKG de W038.
- Prueba de `launch.txt`:
  - Se subió `/data/orbis-win/launch.txt` con la línea `C:\orbis\gui-text64.exe`.
  - `/data/orbis-win` lo crea la app (uid 1, modo 755) y el FTP no podía escribir ahí (550). Se le aplicó `SITE CHMOD 777` antes de subirlo.
  - Se espera `launch_file lines=1` y `launch_arg --wine-exe=C:\orbis\gui-text64.exe` en el log.

## W040 en la consola

- Corridas en `reports/wine-hardware-w040/physical/20261101T041853Z/`.
- `run-0001`, sin `launch.txt`:
  - abre el escritorio de explorer;
  - registra 48 clics del mouse y ningún evento de rueda (`type=4`), aunque la rueda ya tiene su propio presupuesto de log;
  - "Exit desktop" cierra la app con estado 0 (`session_end_terminates_title`).
- `run-0002`, con `launch.txt`:
  - `launch_file lines=1`, `launch_arg --wine-exe=C:\orbis\gui-text64.exe`;
  - `text-result.txt`: `passed=1`, `ink=1252`, igual que en W026;
  - la app sale con estado 0 a los 6,9 s.
- `launch.txt` funciona. Después de la prueba se borró de la consola, así que la próxima corrida vuelve al escritorio.
- Rueda: sin confirmar.
- `run-0003` (`reports/wine-hardware-w040/physical/20261101T042159Z/`):
  - la rueda del mouse USB llega a Wine: 16 eventos `source=mouse type=4`, con `delta=120` y `delta=-120`;
  - el stick derecho no generó eventos en esta corrida y no se sabe si se usó;
  - en el escritorio de explorer no hay nada que desplazar, así que el efecto no se ve. Para verlo hace falta un programa con lista o scroll.
- Segunda prueba, en la misma `run-0003` (`20261101T042354Z`):
  - hay 14 clics más y ningún evento de rueda del stick;
  - los 16 lugares de log de la rueda ya estaban gastados por el mouse, así que el log no permite saber si el stick derecho generó algo.

## W041: presupuesto de log de la rueda por fuente

- La rueda tiene 16 líneas de log para el mouse y 16 para el control, por separado.
- Las primeras 4 veces que el stick derecho sale de la zona muerta se registra `right_stick x= y=` con los valores crudos.
- El resto es igual que W040.
- `/data/pkg/orbis-win-W041-0737cf3db9a4.pkg` (APP_VER 01.40), subido y verificado. Se borró el PKG de W039.

## W041 en la consola

- Corridas en `reports/wine-hardware-w041/physical/20261101T042827Z/` y `20261101T043017Z/`.
- `run-0001` (solo touchpad, el stick derecho no se usó): 8 eventos del touchpad y ningún `right_stick`.
- `run-0002` (con el stick derecho):
  - `right_stick` registró valores crudos `x=161 y=27`, `x=202 y=0` y `x=208 y=0`;
  - hubo 16 eventos `source=pad type=4`: 11 con `delta=120` y 5 con `delta=-120`.
- Con esto, la rueda queda confirmada en el mouse USB (W040) y en el stick derecho (W041), en los dos sentidos.

## W042: registro crudo del stick derecho

- Registra `right_stick` cuando cualquiera de los dos ejes sale de la zona muerta (hasta 8 veces), junto con los primeros 16 bytes del reporte del control.
- Se armó cuando parecía que el stick no respondía. W041 `run-0002` mostró después que sí responde, así que no hace falta probar esta versión.
- `/data/pkg/orbis-win-W042-7ca3e3cce197.pkg` (APP_VER 01.41), subido y verificado. Se borró el PKG de W040.

## W043: compositor por orden de ventanas, presentación en un hilo y programas de Wine

- Problema reportado: al mover ventanas el video se traba, se redibuja todo (incluida la barra de tareas) y quedan partes negras.
- Causas en `ps5drv.c` y en el sink:
  - Cada flush se copiaba directo a la pantalla, sin tener en cuenta qué ventana está arriba.
  - Al mover u ocultar una ventana, su rectángulo viejo se borraba a negro, y lo que quedaba descubierto no se volvía a pintar.
  - Cada flush, por chico que fuera, hacía en el hilo de Wine un hash byte a byte del cuadro entero (3,6 MB), un borrado y un escalado con una división por píxel, y un flip.
- Cambios en `ps5drv.c` (revisiones de `tools/build-win32u-ps4.py`):
  - Cada ventana guarda una copia de su último contenido.
  - La pantalla se recompone de abajo hacia arriba con esas copias, en el orden de apilado. El orden sale de `insert_after` y `SWP_NOZORDER`, y las ventanas `WS_EX_TOPMOST` quedan encima.
  - Mover, ocultar, reordenar o destruir una ventana recompone solo los rectángulos afectados, sin pedir repintado.
- Cambios en el sink (`PW_SINK_ASYNC`, solo hardware):
  - El hilo de Wine solo marca el cuadro como pendiente; un hilo presentador lo copia y hace el flip, como mucho cada 16 ms.
  - Copia directa cuando el escritorio mide 1280×720.
  - El hash se calcula solo para los cuadros que se registran o se pueden volcar.
- Programas: `tools/stage-wine-programs.py` copia `notepad`, `regedit`, `cmd`, `winefile`, `taskmgr` y `winemine`, compilados como PE64 en el árbol de Wine fijado, a `system32` y al directorio de bibliotecas. No necesitan DLL nuevas.
- Lanzar programas desde Run o desde Start:
  - El código ya está en el launcher (`pw_hw_switch_program`, `next.txt`), pero la revisión de `process.c` que lo invoca queda para W044.
  - Se dejó afuera porque la matriz Linux corría al mismo tiempo con el ELF actual, y esa revisión lo modifica.
- `/data/pkg/orbis-win-W043-0d60b63dcd3d.pkg` (APP_VER 01.42), subido y verificado. Se borraron los PKG de W041 y W042.

## W043 en la consola

- Corrida en `reports/wine-hardware-w043/physical/20261101T045251Z/`, clasificada `presented`, con salida 0 por "Exit desktop".
- `presenter_thread started`, sin `video_out_flip_failed`. El escritorio aparece a los 4,2 s.
- El usuario movió la ventana de Run y confirmó que ya no se redibuja todo y que no quedan partes negras.
- Matriz Linux con el compositor de W043 (`reports/wine-hardware-w043/regressions-25/`): **passed**.

## W044: abrir programas, fondo, ícono de Start, íconos de menú y reloj

- Abrir programas desde Run o Start:
  - `NtCreateUserProcess` (revisión de `process.c` en `tools/prepare-wine-boot.py`) registra `PWBOOT create_process image= helper=`.
  - Salvo los procesos auxiliares de Wine (`wineboot`, `services`, `rpcss`, `svchost`, `plugplay`, `winedevice`, `conhost`, `winemenubuilder`), llama a `pw_hw_switch_program`.
  - El launcher escribe `/data/orbis-win/next.txt` (el EXE en la primera línea y los argumentos en las siguientes) y se relanza con `sceSystemServiceLoadExec("/app0/eboot.bin")`.
  - Al arrancar, `next.txt` tiene prioridad sobre `launch.txt`, se lee una sola vez y se borra. Cuando el programa termina, la app se relanza otra vez y vuelve al escritorio.
  - Todavía no se sabe si un título puede relanzarse así: el log va a mostrar `switch_program load_exec rc=`.
  - Fuera del hardware, `platform/ps4/pw_wine_platform.c` define una versión débil que registra `switch_program unavailable` y devuelve error.
  - Una referencia débil sin definir no se puede usar: `create-fself` la rechaza ("missing library for symbol").
- Explorer de hardware (`tools/build-explorer-hw.py`, 11 revisiones en un overlay, con los mismos comandos de compilación que el build fijado). Solo lo usa el paquete de la PS4: el runner Linux sigue usando el explorer fijado.
  - El botón Start muestra un ícono propio de ventana de cuatro paneles en lugar del de la clase.
  - Run y Exit muestran íconos dibujados (una ventana y un símbolo de encendido).
  - Hay un reloj (`GetTimeFormatW`, cada 1 s) en el extremo derecho de la barra, con los íconos de notificación a su izquierda.
- Hora local: el launcher lee `TIME_ZONE` y `SUMMERTIME` de la consola y le pasa a Wine `TZ=LCL±H:MM` (marcador `time_zone`).
- Fondo de pantalla: `tools/make-wallpaper.py` genera de forma determinista `orbis-hills.bmp` (cielo, nubes y colinas, sin material de terceros). Se configura con `Wallpaper` en `user.reg`.
- `DragFullWindows` pasa a `1`: arrastrar una ventana la mueve entera, en lugar de dibujar solo el contorno.
- `/data/pkg/orbis-win-W044-7710134fab9f.pkg` (APP_VER 01.43), subido y verificado. Se borró el PKG de W043.
- Pendiente para W045: carpetas en el menú Start con los programas nuevos y sus íconos.

## W044 en la consola

- Corridas en `reports/wine-hardware-w044/physical/20261101T051446Z/` (`run-0001` a `run-0012`).
- Funcionaron, según el usuario: ícono de Start, íconos de Run y Exit, reloj y arrastre de la ventana entera. El reloj toma la zona de la consola (`time_zone minutes=-180 summer=0`).
- Los 6 programas se abren desde Run. Cada uno deja `create_process`, `switch_program`, y en la corrida siguiente `switched_program` con el EXE: `notepad`, `regedit`, `cmd`, `winefile`, `winemine` y `taskmgr`.
- El fondo no se ve: el escritorio sigue negro.
  - Causa: `get_win_ptr` devuelve `WND_DESKTOP` para la ventana del escritorio, así que nunca tiene una superficie y lo que explorer pinta ahí no llega a la pantalla.
- Al cerrar `taskmgr`, la app quedó a medio cerrar: no arrancó una corrida nueva y el menú del sistema no podía cerrarla.
  - El log termina en `process_exit method=_exit status=0`.
  - En ninguna corrida quedó el marcador de la vuelta al escritorio, que se pedía desde `_exit`.

## W045: fondo desde el driver, tema oscuro, carpetas del menú Start y vuelta al escritorio

- Fondo: `ps5drv.c` carga el BMP indicado por `WINE_PS5_WALLPAPER`, que el launcher pasa con la ruta de `orbis-hills.bmp`. Lo escala a la pantalla y lo usa como capa de abajo del compositor en lugar del negro.
  - Marcadores: `wallpaper_loaded` o `wallpaper_failed`.
  - Sin la variable, como en el runner Linux, el fondo sigue negro.
- Tema oscuro: se llenan los colores del sistema en `[Control Panel\Colors]` de `user.reg`, que estaba vacía. Los fondos son oscuros (botones y barra 45,45,48; menús 38,38,40; ventanas 30,30,30), con texto 235,235,235 y selección azul 0,120,215 con texto blanco.
  - El borde del ícono de Run pasa a gris claro para que se vea sobre un menú oscuro.
- Menú Start: `tools/make-start-menu.py` genera 8 accesos directos `.lnk` (Shell Link con LinkInfo, descripción e ícono del propio EXE) en `C:\ProgramData\Microsoft\Windows\Start Menu`:
  - `Programs/Accessories`: Notepad, Comando Prompt, File Manager;
  - `Programs/Games`: Minesweeper;
  - `System Tools`: Comando Prompt, File Manager, Editor del Registro, Administrador de tareas.
- Vuelta al escritorio: se pide desde `exit()`, antes de los manejadores `atexit`, y una sola vez. El marcador `return_to_desktop` se escribe antes del pedido.
- `/data/pkg/orbis-win-W045-c2899ac36e20.pkg` (APP_VER 01.44), subido y verificado. Se borró el PKG de W044.

## W045 a W047 en la consola, y la hora

- W045 (`reports/wine-hardware-w045/physical/20261101T052806Z/`):
  - `wallpaper_loaded 1280x720 bpp=24`.
  - El menú Start sigue mostrando solo Run y Exit.
  - `cmd` se abre por el cambio de programa, pero no tiene ventana. Es un programa de consola, y en Wine la ventana de consola la da `conhost.exe`, otro proceso, que la PS4 no puede lanzar.
  - El reloj de la barra mostraba 9:11 PM con la consola en 2:30 AM.
- W046 (`reports/wine-hardware-w046/physical/20261101T053551Z/`), diagnóstico del menú:
  - `SHGetSpecialFolderLocation(CSIDL_COMMON_STARTMENU)` devuelve `0x80070002`, y las carpetas del usuario y la común quedan en NULL.
  - `CSIDL_CONTROLS` devuelve 0, pero Control Panel tampoco aparece.
  - Las carpetas existen en la consola (listado FTP).
  - Wine corre en la consola con el usuario `orbis`, mientras que el prefijo se armó con `jose`: `C:\users\orbis` no existe.
- W047, primera versión (`reports/wine-hardware-w047/physical/`):
  - `time_source`: `sceRtcGetCurrentClockLocalTime` da 02:36:08 y `time(NULL)` da 1793511368 (05:36:08 UTC). La libc y la zona (`localtime` 02:36:08) están bien.
  - Causa del reloj: el `<time.h>` del SDK trae los números de reloj de Linux, y `CLOCK_REALTIME_COARSE` (5) en el kernel de la consola es `CLOCK_UPTIME` de FreeBSD. `NtQuerySystemTime` lo prefiere si tiene resolución de 1 ms, así que Wine mostraba el tiempo desde el arranque.
  - Arreglo, para W048: `platform/ps4/pw_wine_posix.h` hace `#undef CLOCK_REALTIME_COARSE`, y Wine usa `CLOCK_REALTIME` (0), que es el mismo número en los dos sistemas. `CLOCK_MONOTONIC_RAW` (4), que Wine usa para sus contadores, es el `CLOCK_MONOTONIC` de FreeBSD.
- W047, segunda versión (`orbisdesk-W047-4a88316ed55f.pkg`): explorer agrega pruebas de `SHGetFolderPathW`, `GetFileAttributesW`, `FindFirstFileW` (la carpeta, su contenido y `C:\ProgramData`) y `SHParseDisplayName`. Se borró el PKG anterior de W047 y el de W046.
- W047, segunda versión, en la consola (`reports/wine-hardware-w047/physical/`):
  - `SHGetFolderPathW` da `C:\ProgramData\Microsoft\Windows\Start Menu` y `GetFileAttributesW` da `0x10` (directorio).
  - `FindFirstFileW` sobre la carpeta y sobre `carpeta\*` falla con el error 50 (`ERROR_NOT_SUPPORTED`). `SHParseDisplayName` da `0x80070002`.
  - Causa: `pw_wine_fchdir` y `pw_wine_openat` buscan la ruta del descriptor en la tabla que llena `pw_wine_open`. Los descriptores que llegan por SCM_RIGHTS (los handles que el wineserver en proceso pasa a cada hilo, y `pw_wine_dup` desde W033) no figuran, así que `ENOTSUP` se convierte en `STATUS_NOT_SUPPORTED`.

## W048: hora, listado de directorios y perfil `orbis`

- Hora: `#undef CLOCK_REALTIME_COARSE` en `pw_wine_posix.h` (ver arriba).
- Directorios: `directory_path` en `pw_wine_fs.c` busca primero el registro con el mismo número de descriptor, y después cualquier directorio registrado con el mismo dispositivo e inodo. En los dos casos el inodo tiene que coincidir, porque el número puede haberse reutilizado.
- Perfil: `build-wine-hardware.py` crea en `C:\users\orbis` el mismo árbol de carpetas que el perfil del host.
- Las pruebas del menú en explorer se mantienen para confirmar el arreglo.
- `/data/pkg/orbis-win-W048-3bf2c9ebfa16.pkg` (APP_VER 01.47), subido y verificado. Se borró el PKG de W047.
- Varias ventanas: dentro de un mismo programa ya funcionan, por ejemplo `taskmgr` con su diálogo Run. El compositor las apila. Varios programas a la vez siguen necesitando varios procesos.

## W048 en la consola y W049

- W048 (`reports/wine-hardware-w048/physical/`):
  - `FindFirstFileW` sobre la carpeta Start Menu (`name=Start Menu`) y sobre su contenido (`first=.`) ya funciona.
  - `FindFirstFileW(L"C:\ProgramData")` sigue fallando con el error 3, y `SHParseDisplayName` con `0x80070002`: falla buscar un nombre en la raíz de la unidad.
  - La corrida de la matriz con W048 se interrumpió a pedido del usuario. Se va a correr después de un par de iteraciones más.
- W049: explorer prueba también `CreateFileW(L"C:\\")`, `GetFileAttributesW(L"C:\\")` y `FindFirstFileW` sobre `C:\*`, `C:\windows`, `C:\ProgramData\Microsoft` y `Z:\*`. `/data/pkg/orbis-win-W049-190a9526311c.pkg` (APP_VER 01.48), subido y verificado. Se borró el PKG de W048.
- W049 en la consola (`reports/wine-hardware-w049/physical/`):
  - `CreateFileW(L"C:\\")` y `GetFileAttributesW(L"C:\\")` fallan con el error 3, y `FindFirstFileW` falla sobre `C:\*`, `C:\windows` y `Z:\*`.
  - `C:\ProgramData\Microsoft` sí funciona.
  - Causa: para la raíz de una unidad (nombre restante vacío), `lookup_unix_name` prueba un solo `fstatat(root_fd, "<prefix>/dosdevices/c:/")` y devuelve `STATUS_OBJECT_PATH_NOT_FOUND` si falla. `fstatat` no pasaba por la capa de plataforma, así que la libc de la consola no conocía la tabla de montajes. Las rutas más largas andan porque se resuelven componente por componente con funciones que sí pasan por la capa.

## W050: `fstatat` por la capa de plataforma

- `pw_wine_fstatat`:
  - las rutas absolutas o con `AT_FDCWD` pasan por la tabla de montajes, como `stat`;
  - las relativas se unen a la ruta del directorio (`directory_path`, W048).
  - `AT_SYMLINK_NOFOLLOW` se respeta; las otras banderas (`AT_NO_AUTOMOUNT`) no cambian nada.
- `pw_wine_posix.h` redirige `fstatat`. Wine se recompiló entero, porque el header se fuerza en todas las unidades.
- Reloj: el usuario confirmó que, desde W048, la hora de la barra coincide con la de la consola.
- `/data/pkg/orbis-win-W050-9edaf00b611b.pkg` (APP_VER 01.49), subido y verificado. Se borró el PKG de W049.

## W050 en la consola

- Corridas en `reports/wine-hardware-w050/physical/20261101T060132Z/`.
- Todas las pruebas de explorer pasan:
  - `C:\` se abre (`attributes=0x10`);
  - `C:\*` lista (`first=orbis`), igual que `C:\windows` y `Z:\*` (`first=apollo`);
  - `SHParseDisplayName` da `hr=0`;
  - la carpeta común del menú se resuelve y no está vacía (`empty=0`).
- `run-0001`: el Buscaminas se abre desde el menú (`create_process ... winemine.exe`, `switch_program`).
- `run-0002`: el Buscaminas sale con estado 0, queda `return_to_desktop t_ms=6409` y la app se relanza sola.
- `run-0003`: explorer otra vez. La vuelta al escritorio desde `exit()` funciona.

## W051: sin trazas del menú

- El usuario confirmó que en W050 el menú Start muestra las carpetas y los íconos.
- W051 saca de explorer las trazas de diagnóstico del menú (W046–W049).
- `/data/pkg/orbis-win-W051-1f52367bba47.pkg`, borrado al subir W052, que la incluye.
- La matriz no se corrió: el usuario pidió seguir con la multitarea.

## W052: multitarea experimental (programas huéspedes en el mismo proceso)

- Una app de PS4 no puede crear procesos. Desde W052, un programa GUI de 64 bits que se abre desde el escritorio corre como **huésped** dentro del proceso de explorer, en hilos propios, en lugar de relanzar la app.
- `tools/build-guest-hw.py` arma, solo para el paquete de la PS4, `ntdll.dll` y `kernelbase.dll` con 13 revisiones (overlay y los comandos exactos del build fijado, con `make -n -W`):
  - **ntdll** (`loader.c`):
    - un EXE cargado como módulo se reubica y resuelve sus importaciones cuando `TEB.UserReserved[2]` marca una carga de huésped (Wine, como Windows, solo lo hace con DLL);
    - `RtlExitUserProcess` llamado desde un hilo huésped termina solo ese huésped.
  - **kernelbase**:
    - `CreateProcessInternalW`: con `WINE_PS4_GUESTS` y una imagen PE de 64 bits con subsistema GUI, carga el EXE con `LoadLibraryExW` y arranca su punto de entrada en un hilo nuevo. Como "proceso" devuelve handles del propio proceso y del hilo; el resto sigue el camino normal (el relanzamiento de W044).
    - `GetModuleHandle(NULL)`, `GetModuleFileName(NULL)` y `GetCommandLineA/W` responden por el huésped cuando los llama uno de sus hilos.
    - `CreateRemoteThreadEx`: los hilos que crea un huésped heredan la marca, y se guardan para terminarlos cuando el huésped sale.
  - La marca de cada hilo es un puntero en `TEB.UserReserved[0..1]`, que Wine no usa; así no hacen falta exportaciones nuevas.
- El lanzador pasa `WINE_PS4_GUESTS=1`.
- Límites conocidos:
  - Solo programas GUI de 64 bits. Los de consola (`cmd`) y los de 32 bits siguen por el relanzamiento.
  - El `argv` de ucrt es el de explorer: se arma una sola vez al cargar la DLL. El `wmain` de Wine para programas GUI usa `GetCommandLineW`, que sí es el del huésped.
  - `exit()` de un huésped ejecuta la tabla `atexit` del proceso, compartida con explorer.
- Marcadores: `PS4 guest <exe> module <p> entry <p> thread <tid>`, `PS4 guest module <p> exits status <n>` y `PS4 guest ...: load failed`.
- `/data/pkg/orbis-win-W052-b59903b3fc10.pkg` (APP_VER 01.51), subido y verificado.

## W052 en la consola y W053

- W052 (`reports/wine-hardware-w052/physical/20261101T061638Z/`), según el usuario:
  - el Bloc de notas abre un diálogo sin textos y su ventana no tiene título;
  - mientras está abierto, el menú Start no responde;
  - al cerrarlo se cierra toda la app.
- El log no tiene ningún marcador `PS4 guest`, y todo corre en el hilo `0024` de explorer (`err:msvcrt:_invalid_parameter`, `c0000417` en un callback).
- Causa: al resolverse las importaciones del EXE huésped, `process_attach` llegó hasta `MODULE_InitDLL`, y el cargador de Wine pone `EntryPoint` también para los EXE. Así se llamó a `wmainCRTStartup` como si fuera un `DllMain`, dentro de `LoadLibraryExW` y en el hilo de explorer:
  - sin marca de huésped, `GetModuleHandle(NULL)` era explorer, por eso no había recursos y faltaban los textos;
  - `LoadLibraryExW` nunca volvió, y explorer quedó bloqueado;
  - `ExitProcess` desde ese hilo terminó el proceso entero.
- W053: `MODULE_InitDLL` no llama al punto de entrada de una imagen sin `LDR_IMAGE_IS_DLL`. El EXE principal no pasa por ahí, porque se marca como ya inicializado antes. Las devoluciones TLS se siguen llamando.
- `/data/pkg/orbis-win-W053-b31506adcf37.pkg` (APP_VER 01.52), subido y verificado. Se borró el PKG de W052.

## W053 en la consola y W054

- W053 (`reports/wine-hardware-w053/physical/`):
  - los huéspedes arrancan en hilos propios: `winemine` (`0038`), `taskmgr` (`003c`) y `notepad` (`004c`);
  - cada uno sale solo (`PS4 guest module ... exits status 0`) y explorer sigue andando;
  - el usuario confirma que el Bloc de notas y los demás programas se ven bien.
- Pendiente según el usuario:
  - con un huésped abierto, el menú Start no abre;
  - la ventana del huésped no tiene botón en la barra, así que si se minimiza no se puede recuperar.
- Causas:
  - Start: `ps5drv.c` mandaba cada evento del mouse con `hwnd` = ventana en primer plano. Con una ventana visible, el wineserver entrega el mensaje a esa ventana sin importar dónde está el puntero, así que los clics sobre la barra le llegaban al huésped. Antes no se notaba porque todas las ventanas eran del mismo hilo.
  - Barra: `add_taskbar_button` de explorer descarta las ventanas de su propio proceso.
- W054:
  - `ps5drv.c` manda los movimientos, botones y rueda del mouse sin ventana, y el servidor busca la ventana debajo del puntero, como winex11. El teclado sigue yendo a la ventana en primer plano.
  - El explorer de hardware acepta en la barra las ventanas de hilos huéspedes: lee `TEB.UserReserved` del hilo con `NtQueryInformationThread(ThreadBasicInformation)`.
- `/data/pkg/orbis-win-W054-633cbed438f5.pkg` (APP_VER 01.53), subido y verificado. Se borró el PKG de W053.

## W054 en la consola y W055

- W054: el usuario reporta que el menú Start no abre nunca.
- Causa: con `hwnd` 0, `get_hardware_input_desktop` usa el escritorio de la window station visible (`WSF_VISIBLE`), que este título no tiene, y el servidor descarta el evento sin error. Ningún clic llegaba a ninguna ventana.
- W055: cada evento de mouse lleva la ventana de primer nivel que está debajo del puntero, según la pila del compositor (`window_at`), o la ventana del escritorio si no hay ninguna. winex11 hace lo mismo con la ventana X bajo el puntero, y win32u busca después el hijo. La captura del mouse (menús abiertos) la sigue resolviendo el servidor. El teclado va a la ventana en primer plano.
- `/data/pkg/orbis-win-W055-3c82aee64ffb.pkg` (APP_VER 01.54), subido y verificado. Se borró el PKG de W054.

## W055 en la consola y W056

- W055 (`reports/wine-hardware-w055/physical/20261101T064543Z/`), según el usuario:
  - el menú Start, los botones de la barra y los huéspedes funcionan;
  - `cmd` sigue por el relanzamiento (`switch_program`) y se queda en "starting wine", porque es un programa de consola y no tiene quién dibuje la consola;
  - al arrastrar una ventana, se mueve recién al soltar.
- W056:
  - Programas de consola como huéspedes: `ps4_guest_image` también acepta `IMAGE_SUBSYSTEM_WINDOWS_CUI`. Si el proceso no tiene consola (explorer no la tiene), el lanzamiento llama a `AllocConsole`. Ese `CreateProcessW` de `conhost.exe` (un programa GUI) entra a su vez como otro huésped y dibuja la ventana de la consola. Cuando el programa de consola sale, `FreeConsole` libera la consola para que conhost termine.
  - `conhost.exe` se compila y se instala junto con los programas (`stage-wine-programs.py`).
  - Diagnóstico del arrastre en `ps5drv.c`: `PWBOOT pointer_move` (cada 50 movimientos del puntero que recibe Wine) y `PWBOOT window_move` (cada 10 movimientos de ventana que ve el compositor), con el hilo y la posición.
- Límites: hay una sola consola por proceso, así que dos programas de consola abiertos la comparten. El `argv` de ucrt de un huésped sigue siendo el de explorer.
- `/data/pkg/orbis-win-W056-7981a9fbf155.pkg` (APP_VER 01.55), subido y verificado. Se borró el PKG de W055.

## W056 en la consola, W057, W058 y W059

- W056 (`reports/wine-hardware-w056/physical/`):
  - conhost arranca como huésped, pero sale con `unknown option L"/desktop=shell,1280x720"`: su `wmain` recibe el `argv` de explorer.
  - Arrastre: hay unos 1.400 `pointer_move` y solo unos 40 `window_move` en 25 s, del hilo `0040` del Bloc de notas.
- W057: ucrtbase (`dlls/msvcrt/data.c`, en `build-guest-hw.py`) devuelve en `__p___argc`, `__p___argv` y `__p___wargv`, para cada hilo huésped, los argumentos armados con `GetCommandLineW` del huésped, una vez por huésped. Se agregan mediciones `window_move t_us` y `flush_stats`. Explorer (17 revisiones) toma el ícono de cada entrada del menú con su ruta completa (`SHGDN_FORPARSING`), porque `SHGetFileInfo` con un pidl relativo a la carpeta no daba ícono, y agrega un respaldo con `IShellLink` y `ExtractIconEx`.
- W057 en la consola (`reports/wine-hardware-w057/physical/`):
  - todas las entradas del menú reciben ícono de la lista del sistema: carpetas 2, Command Prompt 3, Notepad 4, Minesweeper 5, Registry Editor 6, Task Manager 7;
  - `flush_stats`: promedio de 5 ms y máximo de 125 ms por flush;
  - los `window_move` llegan en ráfagas cada ~15 ms, con pausas de 1 a 4 s sin movimientos mientras el puntero se sigue moviendo.
- W058: WFM, el administrador de archivos de Winlator (https://github.com/brunodev85/wfm, MIT, commit `6b18608`):
  - `tools/build-wfm.py` lo compila con mingw-w64 y las banderas de su Makefile;
  - el `libcdio.dll` precompilado del repositorio (PE32+, importa KERNEL32 y msvcrt; SHA-256 `cc9b86da…`) se instala tal cual, junto con `wfm.exe`, en `system32`;
  - "File Manager" del menú abre WFM;
  - a pedido del usuario, `winefile` sale del paquete y del menú, y se borró de la consola.
- W059 (hipótesis para las pausas del arrastre): todos los hilos registraban en el servidor copias (por SCM_RIGHTS) del mismo socket de despertar. El servidor apaga el polling de una cola después de cada evento hasta que su hilo vuelve a esperar. Si el epoll de la consola identifica el socket y no cada copia, eso silencia también a los demás hilos. Ahora `pw_wine_input_fd` da a cada hilo su propio par de sockets (`input_wake n=`), y el hilo de entrada escribe en todos.
- `/data/pkg/orbis-win-W059-995af74c9a57.pkg` (APP_VER 01.58), que incluye W058, subido y verificado.

## W059 en la consola y W060

- W059 (`reports/wine-hardware-w059/physical/`), según el usuario y el log:
  - WFM es el nuevo File Manager, pero si se cierra no vuelve a abrir: los arranques siguientes salen enseguida con estado 0.
  - `cmd` abre una consola titulada "explorer.exe" que no acepta texto: `cmd` sale al arrancar y conhost registra `read_complete failed: 0xc0000024`.
  - El arrastre sigue con pausas de 1 a 5 s, aun con un socket por hilo (`input_wake n=0..5`). Después de cada pausa la ventana salta lejos.
- Causas:
  - Arrastre: si el evento trae una ventana, el servidor busca la captura en la cola de entrada del hilo de esa ventana (`queue_hardware_message`). Mandábamos la ventana bajo el puntero, así que cuando el puntero se adelantaba, el movimiento le llegaba al escritorio y no al hilo que arrastra.
  - WFM: el EXE no se descargaba al salir, así que el segundo arranque encontraba su clase de ventana y sus variables globales de la vez anterior.
  - Consola: `AllocConsole` le pasa a conhost `--server 0x…` y después cierra ese handle, porque un proceso hijo tendría su propia copia heredada. Acá conhost quedaba con un handle cerrado.
  - Título: `AllocConsole` usa `GetModuleFileNameW(0)` del hilo que la llama, que es explorer.
- W060:
  - `window_at`: si el hilo de la ventana en primer plano tiene captura (`NtUserGetGUIThreadInfo`), el evento va a la ventana con captura.
  - Al salir, un huésped desregistra las clases de ventana de su módulo (recorre los átomos de usuario desde `0xc000` hasta 256 seguidos sin usar) y descarga el EXE con `FreeLibrary` (`PS4 guest module ... unloads, N window classes unregistered`).
  - El lanzamiento de conhost recibe un duplicado del handle de `--server`.
  - La consola toma el nombre del programa con `SetConsoleTitleW`.
  - WFM se compila desde una copia de las fuentes, en la que `WM_CLOSE` cierra sin pedir confirmación, a pedido del usuario.
- `/data/pkg/orbis-win-W060-f0a2184ef38f.pkg` (APP_VER 01.59), subido y verificado. Se borró el PKG de W059.

## W060 en la consola y W061

- W060 (`reports/wine-hardware-w060/physical/`):
  - WFM se cierra y se vuelve a abrir: al salir quedan `unloads, 5 window classes unregistered` y `regedit ... unloads, 2`.
  - `cmd` acepta texto: desde `cmd` (hilo `0048`) se lanzó `regedit`. La consola se titula "orbis", lo que está bien según el usuario.
  - `cmd` cerrado no vuelve a abrir (según el usuario). La hipótesis es que conhost sigue cargado y se reusa.
  - Arrastre: ya no hay pausas largas, pero la ventana se mueve una vez por segundo (`window_move` cada ~0,8–1,1 s), el mismo período que el reloj de la barra.
- W061: `PWBOOT input_pull` registra cada vez que un hilo saca eventos (los primeros 300): el hilo, cuántos eventos y la hora. Así se ve si los sockets de despertar despiertan a alguien o si los eventos esperan a que algún hilo se despierte por otra razón.
- `/data/pkg/orbis-win-W061-f5c916a792c7.pkg` (APP_VER 01.60), subido y verificado. Se borró el PKG de W060.

## W061 en la consola y W062

- W061 (`reports/wine-hardware-w061/physical/`):
  - `input_pull`: los hilos `002c`, `0024` y `0038` sacan eventos cada ~17 ms. La entrada llega a Wine sin demora.
  - El arrastre de la ventana de conhost (`0038`) tuvo solo 3 `window_move`, separados ~1 s, cada uno 4 ms después de un evento sacado por un hilo de explorer.
  - Consola: al cerrar su ventana, conhost sale y se descarga (`unloads, 7 window classes`), pero `cmd` (`003c`) sigue vivo. El proceso conserva la consola, y el `cmd` siguiente no llega a lanzarse: el hilo de explorer que lo lanza queda bloqueado, y con él el menú Start (según el usuario).
- W062:
  - Consola: kernelbase registra el conhost (host) y los huéspedes de consola. Si conhost sale, termina y descarga a los programas conectados (`ended with the console`). Si sale el último programa de consola, termina conhost. En los dos casos se libera la consola del proceso.
  - Diagnóstico del arrastre en `defwnd.c` (bucle de mover/redimensionar): `move_loop` registra cada mensaje recibido con su punto y hora, y `move_loop_setpos` lo que tarda cada `SetWindowPos`.
- `/data/pkg/orbis-win-W062-458326a6da3b.pkg` (APP_VER 01.61), subido y verificado. Se borró el PKG de W061.

## W062 en la consola y W063

- W062 (`reports/wine-hardware-w062/physical/`):
  - Consola: al cerrar la ventana de la consola, conhost termina `cmd` (`ended with the console`) y los dos se descargan. El segundo `cmd` abre bien y `exit` termina su conhost.
  - Según el usuario, después de `exit` la ventana de la consola queda colgada en pantalla. Conhost se terminó con `TerminateThread`: el servidor destruye sus ventanas, pero ningún hilo propio llama a `DestroyWindow` del driver, así que el compositor la sigue dibujando.
  - Arrastre: cada `SetWindowPos` tarda menos de 4 ms (`move_loop_setpos`), pero el bucle recibe un `WM_MOUSEMOVE` y enseguida (<1 ms) un `WM_LBUTTONUP`, y termina. Los `input_event` del mouse USB vienen siempre de a pares, apretar y soltar en el mismo punto o a 1 px: `hw_pad.c` genera el "soltar" en cuanto el mouse se mueve.
- W063:
  - `ps5drv.c`: al sacar eventos de entrada, como mucho cada 200 ms, quita las ventanas que ya no existen (`is_window`), libera su copia y recompone su lugar (`window_gone`).
  - `hw_pad.c` (diagnóstico): `mouse_sample` registra las muestras crudas de `sceMouseRead` (las primeras 120 lecturas con botón o con más de una muestra): orden, marca de tiempo, `connected`, botones y movimiento. Sirve para ver si los botones vienen solo en la muestra del cambio.
- `/data/pkg/orbis-win-W063-30ba07779313.pkg` (APP_VER 01.62), subido y verificado. Se borró el PKG de W062.

## W063 en la consola y W064

- W063 (`reports/wine-hardware-w063/physical/20261101T100505Z/`):
  - Botones del mouse: la hipótesis de W062 era incorrecta. `mouse_sample` muestra el botón en una sola muestra (`got=1`, `buttons=0x1`) y el soltar en la siguiente; `hw_pad.c` no inventa el "soltar". En los arrastres de este log el usuario mantuvo el botón entre 0,7 y 1 s.
  - Arrastre: mientras el botón está apretado, el bucle de movimiento (conhost, hilo `0038`) recibe solo `WM_TIMER` y `WM_SYSTIMER`. Su `pt`, que es el cursor del servidor, queda en el punto donde se apretó. Al soltar llegan un `WM_MOUSEMOVE` y el `WM_LBUTTONUP`, y la ventana salta una vez. El driver sí envía los movimientos (`pointer_move` a 676,68 durante el arrastre). La causa no está identificada.
  - `exit` en `cmd`: la app se cerró. El log termina en `ps4_guest_end ... ended with the console`, sin el `unloads` siguiente. `TerminateThread` sobre el hilo de conhost, que estaba corriendo, hace que el servidor le mande SIGQUIT con `tkill`. En la PS4 no hay `tkill` ni `thr_kill2` (`HAVE_THR_KILL2` no está definido), y `send_thread_signal` recurre a `kill()` sobre el proceso, o sea sobre todo el título. En W062 no pasó porque conhost estaba esperando en el servidor, y en ese caso no se manda señal.
  - `window_gone` no aparece: la app se cerró antes.
- W064:
  - `server/ptrace.c` (`prepare-wine-boot.py`): en la PS4, `send_thread_signal` ya no manda la señal al proceso. Registra `thread_signal unavailable thread= sig=` y devuelve error. Un hilo terminado mientras corre termina en su siguiente llamada al servidor, al encontrar cerrado su canal. La suspensión de hilos (SIGUSR1) y Ctrl+C de la consola también dependen de esto, y ahora fallan con la traza en vez de señalar a cualquier hilo.
  - `ps4_guest_end` (kernelbase): primero le manda `WM_QUIT` a los hilos del guest y espera hasta 2 s sin tener tomado el lock del guest. Conhost sale de su bucle, destruye su ventana y pasa por `ps4_guest_exit_process`, que lo descarga. Solo los hilos que no salen se terminan con `TerminateThread`. `cmd` no tiene cola de mensajes y se termina como antes. Traza: `asked to quit, wait`.
  - `ps5drv.c` (diagnóstico): `held_move` registra, para los primeros 150 movimientos con el botón izquierdo apretado, la ventana destino, la ventana en primer plano, su captura y sus flags, el resultado del envío y el cursor del servidor justo después.

## W064 en la consola y W065

- W064 en la PS4 (`reports/wine-hardware-w064/physical/20261101T143013Z/run-0001.log`):
  - `exit` en `cmd` cierra la consola y la app sigue abierta. Las dos veces que se probó, el log muestra `1 of 1 threads asked to quit, wait 0`: conhost salió de su bucle, se descargó (`unloads, 6 window classes unregistered`) y no hubo que terminar ningún hilo. No aparece `thread_signal unavailable`.
  - Arrastre: `held_move` registró 38 movimientos con el botón apretado. Todos van a la ventana capturada (`target` y `capture` iguales, `gui_flags=3`, es decir `GUI_INMOVESIZE` y captura), y el envío devuelve `STATUS_SUCCESS`. Aun así el bucle de movimiento recibe solo `WM_TIMER` con `pt` fijo, y el primer `WM_MOUSEMOVE` llega con la liberación del botón.
  - Causa: en win32u, `NtUserSendHardwareInput` no manda los movimientos al servidor sino que los acumula por hilo (`accum_mouse_motion` en `dlls/win32u/input.c`). Los envía cuando cambia la ventana destino o llega un botón o la rueda. Durante el arrastre la ventana bajo el puntero es siempre la misma, así que todos los movimientos quedaban retenidos hasta soltar. El `error=1400` del registro es un último error viejo del hilo, no del envío.
- W065:
  - `ps5drv.c` (`build-win32u-ps4.py`): los movimientos del puntero se envían con `MOUSEEVENTF_MOVE_NOCOALESCE`, que hace que win32u los mande al servidor en el momento. Es uno por muestra del mouse.
  - Se quitó el diagnóstico `held_move`.
  - Solo cambia win32u; el servidor y kernelbase son los de W064.

## W065 en la consola y W066

- W065 en la PS4 (`reports/wine-hardware-w065/physical/20261101T143854Z/`, tres corridas):
  - El arrastre de ventanas con el mouse funciona: la ventana sigue al puntero.
  - Al salir desde Inicio aparece por un momento una ventana de consola. En las tres corridas el log muestra lo mismo al salir: explorer lanza `conhost.exe` y después `wineboot.exe`, cuya carga falla (`load failed, error 1114`), y la sesión termina (`session_end_terminates_title`). `ExitWindowsEx` (user32) lanza `wineboot.exe --end-session --shutdown` con `DETACHED_PROCESS`, es decir sin consola. El lanzador de guests no miraba esos flags y le creaba una consola a todo programa de consola, así que la ventana que se ve es la consola de wineboot.
  - La falla de carga de wineboot (1114, inicialización de DLL) no se investigó todavía. No impide salir: la sesión termina igual.
- W066 (`build-guest-hw.py`, kernelbase):
  - `ps4_guest_launch` recibe los flags de `CreateProcess` y no crea consola cuando incluyen `DETACHED_PROCESS` o `CREATE_NO_WINDOW`.
  - Si la carga de un programa de consola falla después de crearle la consola, la consola se libera con `FreeConsole`, para que no quede abierta sin programa.

## W066 en la consola y W067

- W066 en la PS4 (`reports/wine-hardware-w066/physical/20261101T145558Z/run-0001.log`):
  - Al salir desde Inicio ya no se lanza `conhost.exe`. Lo único que se lanza es `wineboot.exe`, que sigue fallando al cargar (error 1114). La sesión termina normalmente.
  - `cmd` se cerró con la ventana de la consola: conhost terminó y `cmd` terminó con él.
  - File Manager (WFM) se abrió dos veces. La primera se cerró normalmente, pero el registro dice `unloads, 0 window classes unregistered`. La segunda terminó enseguida de lanzarse (`exits status 0` en la línea siguiente al lanzamiento), y al descargarse desregistró 7 clases. Lo mismo pasaba en W064. La interpretación es que a la primera instancia le quedaron ventanas, sus clases no se pudieron desregistrar, y la segunda no pudo registrarlas y salió. Las ventanas que quedaban serían las del propio hilo que llama a `ExitProcess`, que sigue vivo mientras se descarga el módulo, o las de otros hilos terminados sin esperarlos.
- W067 (`build-guest-hw.py`, kernelbase):
  - `ps4_guest_exit_process` espera hasta 2 s a que terminen los otros hilos del guest y destruye las ventanas de nivel superior y las ventanas solo de mensajes del hilo que sale, antes de descargar el módulo. Traza: `other threads ended, windows of this thread destroyed`.
  - `ps4_guest_unload` registra cada clase que no se puede desregistrar porque todavía tiene ventanas (`still has windows`) y la cuenta en `still in use`.
- W067 en la PS4 (`reports/wine-hardware-w067/physical/20261101T152905Z/run-0001.log`):
  - File Manager se abrió y se cerró cuatro veces seguidas; ninguna instancia terminó al lanzarse. Cada salida destruye 2 ventanas del hilo que sale y desregistra las 7 clases propias de WFM.
  - `cmd` se cerró tres veces: con `exit` (`1 of 1 threads asked to quit, wait 0`) y cerrando la ventana de la consola. En los dos casos la app siguió abierta.
  - El usuario confirmó que todo funcionó.
  - Queda ruido en el registro: las líneas `still has windows` son clases del sistema (`Button`, `Static`, `IME`, las de comctl32) que tienen ventanas de explorer u otros programas, no clases del guest. El recorrido de átomos intenta desregistrar toda clase con el `HINSTANCE` del guest, y Wine resuelve las clases globales sin mirar la instancia. Falta revisar si ese recorrido llega a desregistrar clases globales de otro módulo cuando no tienen ventanas.

## W068

- Causa del ruido de W067: en Wine, `UnregisterClass` encuentra una clase global (`CS_GLOBALCLASS`) con cualquier instancia (`find_class` en `server/class.c` y `dlls/win32u/class.c`). El recorrido de `ps4_guest_unload`, que llama a `UnregisterClass` con el módulo del guest para cada átomo, encontraba también las clases globales de otros módulos. Si tenían ventanas fallaba (las líneas `still has windows`). Si no tenían, las destruía. En W067 la primera descarga de WFM desregistró 13 clases y las siguientes 7, que serían las propias de WFM; las otras 6 serían clases globales ajenas (no se registraron sus nombres).
- W068 (`build-guest-hw.py`, kernelbase): antes de desregistrar, `ps4_guest_unload` consulta la clase con `GetClassInfoExW`. Una clase global se deja registrada salvo que su procedimiento de ventana esté dentro de la imagen del guest, es decir, que la haya registrado el guest. La traza suma `global kept`.
- W068 en la PS4 (`reports/wine-hardware-w068/physical/20261101T155553Z/run-0001.log`):
  - Se abrieron y cerraron `cmd` y WFM una vez cada uno. El log termina a los 29 s sin `process_exit`. No se sabe todavía si la app se colgó o se cerró desde el menú de la PS4.
  - El filtro por `CS_GLOBALCLASS` no alcanza. La descarga de `cmd`, que no registra clases, desregistró 6, y siguieron apareciendo `Button`, `Static`, `Message` e `IME` con `still has windows`. Las clases propias de user32 (`Edit`, `ListBox`, etc.) son globales sin tener `CS_GLOBALCLASS` en el estilo, así que W068 (y antes W060-W067) destruía las que no tenían ventanas. Desde ese momento, un programa que use esos controles no puede crearlos. Los 7 `global kept` de WFM serían clases globales de comctl32 (los nombres no se registraron).
- W069 (`build-guest-hw.py`, kernelbase): la prueba es el procedimiento de ventana para toda clase, sin mirar el estilo. Se desregistra solo si está dentro de la imagen del guest. Si `GetClassInfoExW` devuelve un handle de winproc (clase registrada como ANSI), se vuelve a leer con `GetClassInfoExA`. Traza: `of other modules kept`.
- W069 en la PS4 (`reports/wine-hardware-w069/physical/20261101T160626Z/run-0001.log`):
  - `cmd` se abrió y cerró dos veces, con `exit` (`asked to quit, wait 0`) y cerrando la ventana. WFM se abrió y cerró dos veces. La salida desde Inicio terminó con `process_exit status=0` a los 47,7 s.
  - Cada descarga desregistra solo las clases propias del guest: 1 para conhost, 0 para `cmd` y 1 para WFM. Las clases de otros módulos quedan registradas (11 al descargar conhost y `cmd`, 17 al descargar WFM). No hubo ningún `still has windows`.
