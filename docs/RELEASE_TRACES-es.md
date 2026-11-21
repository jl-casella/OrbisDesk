# Trazas en release: un solo interruptor para el alpha-1

[English](RELEASE_TRACES.md) | [Español](RELEASE_TRACES-es.md)

**Estado:** el interruptor corrió en la consola en la W299 (`W299 trace level=0 source=build release=1`). La segunda ronda (revisión del log de la W299) corrió en la W300: el log de release bajó de 403 KB a 217 KB. La tercera ronda (W300: volcados de cuelgue) está en las fuentes, todavía no en una build W. Las líneas propias del alpha 2 siguen el interruptor desde la 04.37 (ver [Líneas del alpha 2](#líneas-del-alpha-2)); todavía no corrieron en la consola.

El alpha-1 se construye para velocidad. Las trazas de diagnóstico vienen apagadas, y un solo interruptor las vuelve a encender sin recompilar. Los marcadores de build, los errores reales, los crashes y las salidas se loguean siempre. Apagar las trazas nunca convierte un fallo en un éxito silencioso.

## El interruptor

El header es [pw_trace.h](../platform/ps4/pw_trace.h). El launcher de hardware, [wine_hardware.c](../native/wine_hardware.c), decide una sola vez, antes de arrancar Wine:

| Dónde | Valor | Trazas |
|---|---|---|
| Build | `ORBIS_RELEASE=1` (por defecto) | apagadas |
| Build | `-DORBIS_RELEASE=0` | encendidas |
| Corrida: `/data/orbisdesk/trace.txt` | presente y vacío, o `1` | encendidas (manda sobre la build) |
| Corrida: `/data/orbisdesk/trace.txt` | `0` | apagadas (manda sobre la build) |

El log de corrida registra la decisión: `Wnnn trace level=N source=build|trace.txt release=N`.

El launcher le pasa la respuesta a cada capa:

- **Lado nativo** (launcher, sink, pad, adaptadores de plataforma): `pw_trace_on()`, que lee `pw_trace_level`. La variable está definida en [pw_wine_platform.c](../platform/ps4/pw_wine_platform.c).
- **Lado Unix de Wine** (ntdll, win32u, wineserver, driver de audio), todo en el mismo ELF: `pw_trace_enabled()`.
- **Winsys de RADV** (Mesa, mismo ELF): el `pw_trace_level` débil, mediante [patch-crema-traces.py](../tools/vk-h0/patch-crema-traces.py).
- **Lado Windows** (explorer, kernelbase, wow64, la ntdll i386, el host del mundo de 32 bits): la variable `PW_TRACE=0|1`.

Lo que enlace estos objetos sin el launcher de hardware conserva todas las trazas, como antes del interruptor. Eso incluye los diagnósticos del fork y del host, y `wine_boot.c` solo. Un `PW_TRACE` sin definir también cuenta como encendido.

El título aparte de Steam S4 ([build-steam-s4.py](../tools/build-steam-s4.py)) no enlaza código de plataforma de OrbisDesk, y el loader de la consola rechaza un import que ningún eboot provee, aunque sea débil. Su build le pasa `-DPW_TRACE_DEFINE_LEVEL` a la única fuente que incluye `pw_trace.h`, que entonces define el nivel ella misma, con trazas encendidas.

`C:\orbis\winedebug.txt` sigue sumando canales de depuración de Wine en los dos modos. `C:\orbis\dxvkdebug.txt` sigue encendiendo el log de depuración de DXVK para el mundo de 32 bits.

## Qué cambia sin trazas

- **Wine.** `WINEDEBUG=fixme-all,warn+module`: los errores de Wine, más las DLL que no cargan o no inicializan. Con trazas vuelven los canales de antes: `trace+seh`, `trace+loaddll`, `warn+debugstr` y los canales extra de los programas de 32 bits.
- **DXVK.** `DXVK_LOG_PATH=none`, nivel `error`; `warn` con trazas. Sin definir, DXVK escribía `<exe>_d3d9.log` y archivos parecidos en la carpeta del propio juego.
- **Salida de video.** Sin volcados BMP de cuadros, y sin líneas ni tiempos periódicos de cuadros. Las primeras 8 líneas `PWBOOT frame_presented` quedan: [fetch-hardware.py](../tools/fetch-hardware.py) las usa para clasificar una corrida como `presented`.
- **Programas de 32 bits.**
  - wow64 ya no lee el reloj alrededor de cada llamada al sistema. Esa medición solo existía para las líneas de esperas de W272.
  - La línea por DLL de cada hilo nuevo solo se compila con `-DORBIS_RELEASE=0`.
- **Líneas que se repiten durante la sesión, ahora solo con trazas:**
  - presents por segundo, muestras de telemetría
  - movimientos del puntero, estadísticas de flush de ventanas, reportes de esperas lentas
  - timers atrasados del servidor
  - listados de directorio por entrada
  - borrados y renombres exitosos, resoluciones de nombres exitosas
  - el reloj del shell de explorer, los reportes del mezclador y del nivel de audio
  - los primeros eventos de entrada
  - las sondas de plataforma del launcher
  - la lectura de una imagen PE en lugar de mapearla (`PWBOOT image_read_fallback`) cuando se leyó entera, y una DLL ubicada lejos de la base del servidor (`image_map_addr_unavailable`)
  - las líneas de hilos del mundo de 32 bits (`PWWOW ... thread_init`, `loader_init`, `ends`) y las de inicio y fin de Vulkan de los programas de 32 bits (`PWVK32`); una llamada de Vulkan que falla se sigue logueando
  - las líneas `system_module` por DLL de un invitado (quedan el resumen `system_modules` y `system_unloaded`), y las palabras de pila `exit_caller` de un invitado que sale con estado 0
  - RADV: las líneas de arranque de cada dispositivo, los primeros 40 envíos y uno de cada 1000, las líneas detalladas de mapeo y sus puntos de traza de arranque; un chequeo o paso que falla, un envío rechazado, los cuelgues y los fallos de GPU se siguen logueando
- **Con tope de frecuencia, pero siempre logueados:**
  - el present por GDI de wined3d (swapchains de 8 bits): los primeros 4, después uno de cada 1000;
  - un puerto de audio que falla: los primeros 8, después uno de cada 1000.
- **Solo cuando cambia.** `GetLogicalDrives` (`PWFS logical_drives`) loguea su primera respuesta y cada cambio, no cada llamada.
- **Volcados de cuelgue.** Un `PWHUNG` o un shell detenido deja una línea, y el volcado completo de hilos pasa a ser una sola línea de resumen, `PWDUMP skipped age_ms=N threads=N loader_owner=N`. El volcado completo vuelve con trazas, o a pedido con `C:\orbis\dumpnow.txt`. En la W300, cuatro volcados completos de 37 hilos fueron el 70% del log, de un juego que estaba cargando, no colgado.
- **Una sola vez.** RADV escribía cada línea a stderr y a la salida de depuración de la consola, y el launcher loguea las dos; ahora escribe solo a stderr.

## Líneas del alpha 2

El alpha 2 (04.23–04.36) sumó líneas de log para la caché de shaders, la generación de cuadros, FPS LIMIT, el overlay, la liberación de memoria de los invitados, SeaMonkey y el fondo del escritorio. Desde la 04.37 siguen el mismo interruptor. Para verlas en una corrida, creá `/data/orbisdesk/trace.txt` (vacío, o con `1`) antes de iniciar OrbisDesk. Con `0` o sin el archivo, el comportamiento es el de release. No hace falta recompilar.

Hay tres marcadores opcionales anteriores que siguen aparte: `/data/orbisdesk/framegen.txt` (las líneas de tiempos de la generación de cuadros), `C:\orbis\nativeprofile.txt` (el perfil por hilo de wow64native) y `C:\orbis\vkbatch32.off`. No dependen del interruptor.

**Solo con trazas desde la 04.37:**

- **Caché de shaders y tiempo de cuadro.** `PWPERF` (la línea de ventana de 5 s y `slow_compile`). Sin trazas no se mide nada: el sink vuelve antes de sus contadores.
- **FPS LIMIT.** El reporte de 5 s `PWFPS limit=… presents=…`, `PWFPS vblank count trusted|not trusted` y `PWFPS auto cap`.
- **Generación de cuadros.** El reporte de 10 s `PWFG display pairs=…`, `PWFG display on|off`, `PWFG shown_rate`, `PWFG gpu_us` (cada 120 cuadros generados), las sondas de arranque (`PWFG probe …`, `PWFG buffers`), `PWFG target sc=` y las primeras líneas de copia.
- **Overlay.** `PWOVERLAY open|close|keyboard|stats=`, las líneas de la tecla de MangoHud, `PWOVERLAY mangohud|desktop in_front` (nativo y kernelbase), `PWOVERLAY program … bits`, `PWOVERLAY hud:` (el resumen de MangoHud.conf), `PWOVERLAY keymap program=`, `PWOVERLAY render set … requested`, `PWOVERLAY exit taken by the closer`, y `PWOVERLAY control wait` cuando el mando quedó listo.
- **Liberación de memoria de los invitados** (kernelbase y win32u). `PWGUEST heap_usage`, `heap_large`, `heap_small`, `heap_unowned`, las listas `kept bytes … from`, `heaps … claimed`, `heap … kept: held by`, `PWGUEST vulkan module=… devices=`, `PWGUEST gl module=… result=`, `PWVK guest_memory`, `PWVK guest_release`, `PWVK guest_teardown … ms=` y `PWAUDIO guest …: N streams out of the mixer`.
- **Detalle del ciclo de vida de los invitados.** `PWGUEST thread_new`, `thread_starts`, `ended: thread`, `class … unregistered`, `ilonly entry`, `mangohud excluded`.
- **Ventanas y gráficos.** `PWVK size`, `PWVK layer`, `PWRECT`, `PWSINK monitor`, `PWSINK fullscreen off|not|image`, `PWINPUT warp`, y `PWGL viewport` y `PWSTW size` de Mesa WGL (las dos aparecen en el log como `MESA: error:`).
- **Fondo del escritorio.** `PWDESK wallpaper menu`, `PWDESK background open|apply`; `render` y `browse` solo cuando salen bien.
- **Video.** `PWAVI open` y la descripción de cada stream, `first_sample`, `eos`, y `stopped` cuando terminó limpio.
- **Plataforma y lado Unix de Wine.** `PWFS descriptor_growth`, los cambios de `PWMEM direct_free source=`, `PWIPC request_chunked`, `PWSERVER request_deferred`, `PWLOAD shared_section_private` después de una copia completa, y las líneas `device … gave back N bytes` de RADV.

**Lo que queda en release, y por qué:**

- Toda línea que reporta un fallo, un rechazo o algo que se conserva. Por ejemplo: `PWFG failed …`, `PWFG off for this run`, `PWFG generator off for this run`, `PWOVERLAY … not saved`, `… refused`, `config line ignored`, `PWGUEST … release failed`, `heaps not recorded`, `kept: … more than listed`, `PWVK guest_teardown … kept`, `PWAVI stream … not offered|unreadable`, `PWAVI reject`, `PWFS lock_failed`, `PWDESK background apply … error|refused`, y `ended with submissions unfinished` de RADV. Son lo que necesita un reporte de campo, y no cuestan nada mientras nada falla.
- **Los ajustes que cambió el usuario, una vez por cambio.** `PWOVERLAY framegen=`, `fpslimit=`, `control type=`, `control pad.…=`, `render … program=`, `keymap saved`, `PWFG mode=`, `PWFPS limit=… cap=` y `PWPAD profile=… reload`. Un reporte de crash necesita saber qué estaba encendido.
- **El camino de salida.** `PWOVERLAY exit requested|title|result`, y las líneas de "nadie contestó". Son raras, y son las últimas líneas antes de que se cierre un título.
- **Un mando que no quedó listo.** `PWOVERLAY control wait … ready=0`.
- **El estado de arranque, una sola vez.** `PWFG config`, `PWFG ready`, `PWFG no present hook`, `PWTELEM framegen query`, `PWHID dualsense unavailable`, `PWNET kernel_poll`, `PWBOOT memory_info`, `PWINSTALL plan`, `PWCACHE radv disk_cache=` y `address32_hi`. `PWCACHE` queda porque su parche de Mesa conserva su marca sobre un árbol de fuentes ya existente; es una línea por dispositivo.
- **Anomalías raras.** `PWGUEST leftover thread`, `own_modules … kept`, `PWWOW tls_slot`, `PWSINK mode kept|restore`, `PWFONT`, `PWWOW win32u`, `PWCRT`, `PWTOP` y las líneas `fault` de los invitados.
- **Separación de procesos y lanzamiento.** `PWSEP …`, `PWOPEN …`, `PWLAUNCH`: una línea por decisión de lanzamiento, necesaria cuando un juego no arranca.
- **Red, HID y DirectInput.** `PWNSI` (un aviso por corrida y una línea por cada cambio de red de la consola), `PWHID winebus unlink again ignored` y `PWINPUT device … gone: released`. Cada una es rara y señala un evento real.

Tres cosas no cambian: `PW_NATIVE_PROFILE` sigue siendo opcional mediante `nativeprofile.txt`; `PW_VK_BATCH` enciende el batching y no es una traza; y la cadena de depuración `PWHUD` de MangoHud solo aparece con el canal `warn+debugstr` de Wine.

## Siempre se loguea

- los marcadores `Wnnn` del launcher
- los hitos `PWBOOT` que leen la pantalla de carga y las herramientas de evidencia (`server_ready`, `static_unixlib ...win32u.so`, `gpu_layers=`, `frame_presented`)
- los registros de crash y de salida, `PWNATIVE lost signal`, `PWFAULT`
- los reportes de cuelgue (`PWHUNG`, el resumen `PWDUMP`, `PWLOCK`, `PWSERVER stuck`)
- toda línea de fallo

## Lo que todavía no cubre

- **El cliente de Steam.** Baja su log al almacenamiento después de cada línea, salvo la de progreso de instalación sin trazas (W299).
- **El HUD de MangoHud.** Se muestra por defecto. Con `MANGOHUD=0` la capa ni se cargaría, y el interruptor STATISTICS del overlay no podría mostrarlo.
- **`C:\orbis\dxvkdebug.txt`.** Una copia que quedó en la consola encendió el log de depuración de DXVK en la W299; es un override manual y se borró de la consola.
- **Un juego a pantalla completa que no bombea mensajes.** Mientras carga o pasa un video, Wine reporta su ventana como colgada y `PWHUNG` lo registra. Una mejora posible es no reportarlo mientras el programa sigue presentando cuadros de Vulkan. El lado nativo ya cuenta los presents. No se hace para el alpha-1.
- **Los errores `validate_state_table` de wined3d.** Son reportes de consistencia de upstream al crear el dispositivo; quedan como están.

Quedan anotados como trabajo siguiente.
