# Procesos de Windows separados (fases B–D de PoP)

[English](POP_SEPARATE_PROCESS.md) | [Español](POP_SEPARATE_PROCESS-es.md)

OrbisDesk corre todos los programas de Windows dentro de un único proceso del título de PS4. Ese modelo falla con un launcher y un juego que necesitan la misma base de imagen fija. El launcher de Prince of Persia y `POP.exe` usan los dos `0x400000`. Este documento registra cómo un programa marcado **Separate processes** en winecfg ahora corre en un segundo proceso nativo. Ese proceso ejecuta Wine como cliente del wineserver del título, con el escritorio, el registro y el espacio de nombres de objetos del título.

El sustrato de investigación (fase A, el loader de GoldHEN y su arreglo del planificador) está en [Sondas de familias de procesos](PROCESS_FAMILY_PROBES-es.md). OrbisDesk apunta a consolas con GoldHEN, así que el loader residente es un requisito declarado y no un bloqueo. Después de cada reinicio de la consola el título lo vuelve a enviar (D.7).

## Qué funciona en hardware (PS4 Pro Baikal, 12.50, arranque ROOT, del 12 al 16 de noviembre de 2026)

| Fase | Resultado | Evidencia (`reports/pop-phase-b/physical/`) |
| --- | --- | --- |
| B.1 | Un proceso lanzado por el loader se conecta al wineserver del título, se registra (versión 961) y crea `\KernelObjects\OrbisSeparateJoin` en el espacio de nombres compartido | `20261112T032514Z` |
| C | Ese proceso crea una ventana en el escritorio del título con pedidos directos al wineserver. Recibe el mouse, y el título compone sus píxeles | `20261112T085655Z` |
| D.1 | Wine corre en ese proceso. Un programa de consola PE64 enlazado en `0x400000` carga ahí sin reubicarse y sale con 42. Tres arranques seguidos del título son estables | `20261112T130124Z` |
| D.2 | La ventana de un programa GDI aparece en el escritorio. Recibe clicks, teclas y arrastre, y el escritorio sigue abierto cuando el programa termina | `20261112T132927Z` |
| D.3 | `separate_launcher.exe` corre dentro del título en `0x400000`. Llama a `CreateProcess` sobre `separate_game.exe`, marcado separado y también enlazado en `0x400000`, y el juego corre en el segundo proceso. El launcher recibe handles reales y el código de salida 44 del juego. El juego recibe 8 clicks y 11 teclas | `20261112T141146Z`, `20261112T150746Z` |
| D.4a | La sonda Vulkan del título, corrida en el proceso separado, carga `libSceGnmDriver.sprx` desde `/system/common/lib` y después la consola se detiene con *Fatal trap 9: general protection fault while in kernel mode*. El proceso separado no puede usar la GPU | `20261112T154040Z`, `20261112T154358Z`, `20261112T155318Z` |
| D.4 | Ruta inversa: `separate_inverse.exe` corre en el proceso separado en `0x400000`. Su `CreateProcess` sobre `separate_game.exe`, también en `0x400000`, se le pasa al título, y el juego corre ahí como invitado de 32 bits, con entrada y salida limpia | `20261112T194224Z` |
| D.4b | El launcher separado se queda dentro de `CreateProcess` hasta que el juego termina, como tiene que hacer el launcher de Prince of Persia por `PrinceSM`. El juego recibe el argumento del launcher (`argc` 2) por msvcrt. El título responde *started* y después *ended* | `20261112T232400Z` |
| D.5 | El propio launcher de Prince of Persia corre separado y `POP.exe` corre en el título con la GPU. El `CreateProcess` del launcher vuelve enseguida, así que pasa su control de arranque de 25 segundos, y lee el código de salida real del juego cuando el juego termina | `20261113T132532Z`, `20261113T142613Z` |
| D.6 | Sin modo de ejecución elegido, los launchers de Prince of Persia y Worms 3D arrancan como invitados, chocan con la base ocupada y pasan solos a un proceso separado. Los objetos con nombre de la copia invitada (`POP_Launcher`) se cierran, y el launcher reiniciado corre el juego | `20261113T152940Z`, `20261113T155813Z` |
| Pantalla completa | `POP.exe` (DXVK, una ventana siempre arriba) pone 800x600 y se muestra a pantalla completa, escalado a la salida | `20261113T174954Z` |
| D.7 | Un launcher separado que arranca hilos de DirectInput y XInput (Tony Hawk's American Wasteland) ya no traba el wineserver del título. Un proceso separado termina con el título, así que el inicio siguiente de OrbisDesk anda sin reiniciar la consola. Después de reiniciar la consola, el título envía el loader residente por su cuenta | `20261113T203301Z` |

Estos resultados cubren solo las configuraciones nombradas acá. No prueban compatibilidad general de aplicaciones. El proceso separado no tiene GPU propia, así que un juego que dibuja corre en el título y solo su launcher corre separado (ver *La ruta inversa* y *Límites*).

## Cómo fluye un lanzamiento

1. **kernelbase.** `CreateProcessInternalW` ve el modo de ejecución `separate` para la imagen. Su generador es `tools/build-guest-hw.py`. Escribe `/data/orbisdesk/process-p014/spawn-request` con cuatro líneas: un token, la imagen, la línea de comandos y el directorio actual. Después espera hasta 30 s a `started-<token>`, y corta enseguida ante `failed-<token>`.
2. **Vigía del título.** `native/pop_loader_spawn.h` convierte el pedido en el trabajo del hijo. Después manda `/data/orbisdesk/pop-wine-join.elf` al loader residente por el puerto 9021.
3. **Hijo del payload SDK.** `native/process_p014_child.c` adopta el uid del título y carga `pop-wine-child.prx` con `dlopen`, así el linker del sistema resuelve sus imports, el TLS y los inicializadores. Se conecta al socket puente del título y llama a `pop_wine_child_run_job`.
4. **PRX de Wine.** `native/pop_wine_child.c` pone en `WINESERVERSOCKET` el descriptor del puente y llama a `__wine_main`. Así ntdll se une al servidor del título en vez de iniciar uno. Ya unido, el proceso escribe `pid tid` bajo el token, y kernelbase abre handles reales de proceso y de hilo para quien lo llamó.
5. **Pantalla.** El driver de win32u del hijo le pasa su pila de ventanas a `native/pop_child_sink.c`, que nunca abre VideoOut. El sink manda la ventana de arriba y su handle por `surface.sock`. El título compone el cuadro en el rectángulo de la ventana. Un puntero sobre ese rectángulo se entrega a esa ventana por su handle (`pw_hw_separate_window`, `tools/build-win32u-ps4.py`).

## La ruta inversa (D.4)

La GPU es del título (D.4a). Para un launcher y un juego que necesitan los dos `0x400000`, el launcher se marca **Separate processes** y el juego queda como invitado normal.

1. El usuario abre el launcher. kernelbase lo inicia en el proceso separado, como en los pasos de arriba.
2. En el proceso separado, el `CreateProcess` del launcher llega a `pw_hw_switch_program` (`native/pop_wine_child_stubs.c`). Escribe `/data/orbisdesk/process-p014/title-launch` con la imagen, la línea de comandos, el directorio y un token.
3. El vigía de explorer (`tools/patch-explorer-open.py`) lee el archivo cada 500 ms. Manda `PW_SHELL_LAUNCH_MESSAGE` a la ventana del escritorio, que llama a `CreateProcessW` en el título. Una imagen de 32 bits pasa a ser invitada del mundo de 32 bits de explorer en su propia base.
4. Explorer crea el evento con nombre `Global\PWTitleLaunch_<token>` y escribe `title-launch-reply`: `<token> started <pid>`, o `<token> failed <error>`. Después de *started*, un hilo espera los handles de proceso y de hilo principal del invitado, escribe `<token> ended <código de salida>` y señala el evento. El handle de proceso de un invitado de 32 bits es el del título, que nunca se señala, así que el que termina es su hilo principal, y el código de salida es el de ese hilo.
5. **D.5.** En el proceso separado, `CreateProcess` vuelve enseguida (`__wrap_NtCreateUserProcess`, `native/pop_wine_child_stubs.c`). Sus handles de proceso y de hilo son ese evento con nombre, como los handles de proceso de los invitados del título son sus eventos de fin (W267). `NtQueryInformationProcess` responde `STILL_ACTIVE` y después el código de salida de la respuesta. Una espera sobre el handle termina cuando termina el juego. El launcher de Prince of Persia señala un evento después de que vuelve `CreateProcess` y lo espera 25 s; con el `CreateProcess` bloqueante de D.4b decía que no se podía iniciar el juego. Los objetos con nombre que el launcher mantiene, como `PrinceSM`, viven mientras espera. Con *failed* el `CreateProcess` del launcher falla. No se reenvían: `TerminateProcess` sobre ese handle (falla) ni los ids de proceso y de hilo (0). Frente a un título sin el evento con nombre, el proceso separado vuelve a D.4b: el hilo que llamó espera *ended* y después el proceso sale.

El protocolo está en `platform/ps4/pw_shell_open.h`.

## Cierre, reapertura y cuelgues (D.7)

- **Lecturas del servidor.** `read_request` del wineserver lee el pedido de un cliente en un bucle que termina con `EAGAIN`, así que depende de un descriptor de pedidos no bloqueante. La consola rechaza `O_NONBLOCK` en estos sockets, y los hilos de un proceso separado entregan los suyos por el puente. El launcher de Tony Hawk congeló el título con `PWSERVER stuck_s=60 ... func=thread_poll_event`. Ahora cada lectura consulta antes `poll` sin espera, y si no hay nada que leer cuenta como `EAGAIN` (`tools/build-wine-delete-server.py`).
- **Terminar con el título.** El proceso separado vigila su socket puente al servidor del título. Cuando el título se va, el socket se corta y el proceso termina (`native/pop_wine_child.c`, `P024 title_gone`). Así un launcher que quedó abierto ya no bloquea el inicio siguiente.
- **Loader después de reiniciar.** Cuando el loader residente no responde en el puerto 9021, el título envía el `elfldr.elf` incluido al BinLoader de GoldHEN en `127.0.0.1:9090`, como hace `tools/start-process-loader.py --start` desde una PC, y reintenta durante 10 s. Si el inicio igual falla, escribe `failed-<token>` y kernelbase deja de esperar (`native/pop_loader_spawn.h`, `PWSEP separate_failed_reported`). El BinLoader de GoldHEN tiene que estar activado.

### Cuelgue al arrastrar el launcher de Tony Hawk

Las corridas del 16 de noviembre expusieron dos problemas posteriores a la primera prueba de D.7. Un pedido grande de HID del título dejaba al wineserver esperando más datos aunque el pipe indicaba repetidamente que se podía leer. El título y el PRX ahora usan el escritor compartido de `platform/ps4/pw_wine_request_write.c` para los pedidos con datos, con escrituras de hasta 512 bytes. El servidor aplaza un descriptor que reporta cero bytes y sigue atendiendo a los demás. El launcher separado también creaba su diálogo sin entregar ningún cuadro completo. P031 usa el adaptador de máscaras de señales de PS4 al crear el hilo de presentación y envía los cuadros por ese hilo con un tiempo de espera en el socket. El hilo de la interfaz puede seguir actualizando el cuadro pendiente mientras el socket está ocupado.

La combinación verificada fue el PKG chico W303, versión **04.05**, con el PRX externo **P031**.

| Artefacto | SHA-256 |
| --- | --- |
| `OrbisDesk.pkg` | `d731542d774c60e456ba76d9959ab3b465fcfefa70dac3d83844f14178b10269` |
| `pop-wine-child.prx` | `a083506ffd67e92e7b66e5d25aa1597d8b3096205d17868982584a9c9ec35d7e` |

La evidencia local está en `reports/pop-phase-b/physical/20261116T155602Z/run-0149.log` y sus logs asociados. El título recibió 143 y 359 cuadros en la primera y segunda apertura, respectivamente. La segunda instancia del launcher registró 120 movimientos de ventana y salió con código 0. El título devolvió el foco al escritorio. Esta corrida cierra el cuelgue al arrastrar el launcher en esta configuración. El juego `THAW.exe` arrancó como invitado y hubo que terminar sus hilos al no salir dentro de los tres segundos posteriores al `WM_CLOSE` enviado desde el overlay. El escritorio siguió respondiendo y permitió reabrir el launcher.

## Sin una elección en winecfg (D.6)

Un invitado de 32 bits que inicia otro programa de 32 bits que necesita la base que él ocupa (error 487) recibía el aviso de reiniciar OrbisDesk con ese programa solo. Ahora, cuando ese iniciador no tiene modo de ejecución elegido, kernelbase primero escribe `AppDefaults\<exe>\OrbisExecutionMode=separate` para él, como hace **Separate processes** en winecfg. Después vuelve a iniciar al iniciador en un proceso separado y termina la copia invitada. La ventana del launcher se abre de nuevo, el usuario elige Jugar otra vez, y desde entonces el launcher abre separado. Si el inicio separado falla (por ejemplo, sin loader residente), el valor se borra y sigue el aviso. Un iniciador que sea un juego y no un launcher también se movería, y entonces no tiene GPU; en ese caso hay que ponerlo como invitado en winecfg.

Un invitado que termina ahora también cierra los mutex y eventos con nombre que su propio código creó con `CreateMutexA/W` y `CreateEventA/W`, como ya cerraba sus archivos (W206). Sin eso, el launcher de Prince of Persia reiniciado encontraba el `POP_Launcher` de la copia invitada y decía que el juego estaba corriendo. No se siguen los semáforos, las variantes `...Ex` ni `OpenMutex`/`OpenEvent`.

## Direct3D en el proceso separado

Los launchers suelen probar la tarjeta gráfica. El de Prince of Persia corre la detección de Ubisoft (`detectionapi.dll`, `directx8tests.dll`, `directx9tests.dll`). En el proceso separado, Direct3D 8/9 usan el adaptador `no3d` de wined3d: `WINE_D3D_CONFIG=renderer=no3d` y d3d8, d3d9, ddraw, dxgi, d3d10core y d3d11 builtin (`native/pop_wine_child.c`). Ese adaptador responde sin la GPU. `/data/orbisdesk/process-p014/gpu-probe` lo desactiva.

La detección ve entonces un adaptador sin formatos. El launcher de Prince of Persia lo escribe en `Hardware.ini`, y `POP.exe` se detiene con *Unable to find a display mode*. Un `Hardware.ini` con valores reales, de solo lectura, lo evita hasta que la detección pueda ver la GPU del título.

## Terminar un juego desde el overlay

Un juego terminado con Salir del overlay no suelta sus dispositivos de DirectInput. El hilo de dinput es de todo el proceso en explorer (W281). Su hook de bajo nivel y su lectura del mando cada 8 ms dejaban el control en modo juego, y el escritorio parecía congelado. El hilo ahora suelta, cada 500 ms, los dispositivos cuya ventana cooperativa ya no existe (`tools/build-dinput-hw.py`, `PWINPUT ... released`).

## El modo de pantalla de un juego

win32u guarda el último modo de pantalla que un juego puso por debajo del tamaño del escritorio (`pw_mode_set_width/height`, `tools/build-win32u-ps4.py`). La ventana visible más alta que cubre ese modo desde 0,0, con a lo sumo 64 píxeles más de marco, se muestra a pantalla completa y escalada, incluidas las ventanas siempre arriba. Para la ventana DXVK de Prince of Persia, el rectángulo del monitor que leía el driver quedaba en 1280x720 y la ventana de su launcher estaba encima del juego, así que la regla de W248 no se aplicaba (`PWSINK fullscreen on ... 800x600 of 1280x720`).

## Qué necesitó el PRX de Wine en esta consola

Cada punto se encontró en hardware. El comentario junto al código da la corrida y el motivo.

- **Carga.** El loader solo copia una imagen: sin imports, sin TLS, sin inicializadores. Por eso Wine es un PRX con firma falsa cargado con `dlopen`. `__init_libc` de musl se llama a mano, porque un PRX nunca ejecuta `crt1`.
- **Base fija.** El proceso de sistema prestado tiene su eboot en `0x400000–0x588000`. Ese código no vuelve a correr, y sus regiones se liberan antes de que arranque Wine.
- **Página compartida.** Con páginas de 16 KiB, el lugar del despachador de syscalls de ntdll (`0x7ffe1000`) comparte página del host con la vista compartida de `KUSER_SHARED_DATA`. Un segundo proceso pisaba el despachador del título, y explorer saltaba al ntdll del otro proceso. En el proceso separado esa página es privada y se refresca desde la vista compartida cada 15 ms.
- **Vida del escritorio.** El servidor cierra un escritorio cuando solo quedan los hilos de su dueño. El proceso separado se vuelve proceso de *sistema* de Wine apenas se une, así su salida deja abierto el escritorio del título.
- **Nombre del escritorio.** `ProcessParameters->Desktop` se pone en `WinSta0\shell` antes de que ntdll copie los parámetros para una imagen de 32 bits. Así todo programa cae en el escritorio del título.
- **PE32.** La CPU es `wow64native.dll` con `PW_NATIVE_SIGNALS=1`, como en el título.
- **Esperas.** Usan el `poll` del kernel en vez de un `sceNetEpoll` por llamada. Es una precaución: el título abortó al arrancar dentro de `sceNetEpollControl` después de sesiones con el hijo, hasta reiniciar. La causa no se probó.
- **Salida del proceso.** Una aserción termina el proceso con `_exit`. Wine atiende `SIGABRT`, y los hijos que fallaban una aserción quedaban colgados.

## Compilar y desplegar

```sh
python3 tools/build-wine-hardware.py --runtime-outside-package   # el título (su comando de enlace alimenta el PRX)
python3 tools/build-pop-wine-child.py                            # PRX, sonda, hijo, programas de prueba + manifiesto
python3 tools/upload-hardware.py --build W303 --host IP_CONSOLA --port 2121 --skip-runtime
python3 tools/upload-pop-separate.py --host IP_CONSOLA
```

`tools/build-guest-hw.py` y `tools/build-winecfg-hw.py` producen el kernelbase y el winecfg que el título prepara. Si esos cambian, también hay que actualizar sus copias del runtime bajo `/data/wine` y del prefijo. `/data/wine` pertenece al uid del título con modo 755. El FTP igual puede cambiar modos, así que conviene abrir un directorio solo para la subida y devolverle su modo después.

Acá importan dos comportamientos del FTP de GoldHEN. Sobrescribir un PRX en su lugar dejaba cargado el anterior, así que hay que borrarlo antes de guardar el nuevo. `RETR` de un SELF/PRX devuelve el ELF descifrado, así que se verifica por contenido y no por hash. `tools/upload-pop-separate.py` hace las dos cosas. La autoprueba del arranque corre solo si existe `/data/orbisdesk/process-p014/selftest`.

## Límites

- **Sin GPU en el proceso separado.** RADV/GNM y VideoOut son del título, y cargar el driver GNM en el segundo proceso hizo fallar al kernel (D.4a). Un programa Direct3D, OpenGL o Vulkan no puede dibujar ahí. Los programas que dibujan usan la ruta inversa: corren en el título. Direct3D 8/9 responden con el adaptador `no3d` de wined3d, así que la detección de hardware de un launcher no ve formatos.
- **OpenGL de 32 bits es opcional.** En el mundo de 32 bits de explorer, el `opengl32` builtin de Wine no tiene driver. En D.4b, `ChoosePixelFormat` devolvió 0 con error 203. Mesa i386 se usa solo si existe `C:\orbis\opengl32native.txt` (W264). Los juegos Direct3D 8/9 usan DXVK o wined3d.
- **Mundo de 32 bits tardío.** En una sesión que ya había corrido MangoJuice, un juego Unity y WFM, el primer invitado de 32 bits se detuvo con `c0000005` antes de que se revisara su imagen. La misma prueba en una sesión recién abierta funcionó (`20261112T232131Z`, después `20261112T232400Z`). Todavía no se reprodujo.
- **Una ventana, siempre arriba.** Solo se muestra la ventana de arriba del proceso separado, y se dibuja sobre todas las del título. No se manejan el orden respecto del título, varias ventanas ni las formas del cursor.
- **Cursor viejo en el hijo.** Dentro del proceso separado, `GetCursorPos` puede devolver un punto viejo. Eso afecta a menús y arrastres que maneja el propio programa.
- **Señales y suspensión.** El servidor no puede enviar señales a los hilos de un proceso separado ni suspenderlos (`pw_wine_thread_kill` solo alcanza los hilos del propio título).
- **Loader de GoldHEN.** El título envía el loader residente por el BinLoader de GoldHEN (D.7). Con el BinLoader desactivado, un inicio separado falla.

La historia de desarrollo está en los comentarios junto a cada cambio y en `native/pop_separate.h` (`P014`–`P021`).
