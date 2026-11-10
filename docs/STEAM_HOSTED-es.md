# El cliente de Steam dentro de OrbisDesk

[English](STEAM_HOSTED.md) | [Español](STEAM_HOSTED-es.md)

El cliente de Steam de [S1–S5](STEAM_S5-es.md) era un título aparte (ORBS00001). Este cambio lo pone dentro del título de OrbisDesk (ORBW00002), como pidió el usuario: **"Open Steam Client"** en el menú Inicio, justo arriba de "Exit desktop", y un acceso con el mismo nombre en el Escritorio. Cualquiera de los dos pasa la pantalla a la UI de Steam, y al salir del cliente se vuelve al mismo escritorio en marcha. La UI está en inglés. Con esto, el paquete de OrbisDesk pasa a ser GPL-3.0-or-later (decisión del usuario).

**Estado:** el objeto, sus archivos y los parches para los archivos compartidos de OrbisDesk están armados y comprobados en la PC: compila con la toolchain del título, un enlace de prueba pasa y las páginas de 1280x720 se dibujan bien. **No está integrado ni corrió en la consola.** El título aparte ORBS00001 sigue compilando (`tools/build-steam-s4.py`) hasta que pase el integrado.

## Cómo encaja en el título

| Parte | Dónde | Qué hace |
|---|---|---|
| Pantalla | `native/steam/steam_ui.c`, `STEAM_UI_HOSTED` | Sin VideoOut propio. El sink llama a `pw_hw_steam_draw(target, pitch, 1280, 720)` en cada cuadro, justo antes del overlay de control; mientras el cliente está abierto, dibuja su página sobre todo el cuadro. Cada página nueva le pide un cuadro al sink (`pw_hw_cursor_moved`). |
| Control | el mismo archivo | `native/hw_pad.c` llama a `pw_hw_steam_pad(&data)` en cada lectura, junto al gancho del overlay. Mientras el cliente está abierto toma X, O, triángulo, arriba y abajo, y el escritorio lee el control en neutro. Al cerrar, retiene el control hasta que se sueltan todos los botones. |
| Apertura | `native/steam/steam_client.cpp`, `pw_hw_steam_open()` | Arranca el cliente en un hilo propio (pila de 2 MB) y devuelve `opened`, o `busy` si ya está abierto. Cuando el cliente termina, cierra su pantalla y vuelve el escritorio. |
| Pedido | `native/steam/orbis_steam_open.c` → `C:\orbis\steam-open.exe` | Un invitado de 64 bits que manda `<steam-open>` por el mismo canal que usa el cerrador del overlay de kernelbase: la biblioteca Unix de xinput1_3, llamada 3. `native/hw_pad.c` responde en el mismo buffer. |
| Menú Inicio | `tools/build-explorer-hw.py` | `MENU_ID_STEAM` entre el separador y "Exit desktop", con su propio ícono. Abre `C:\orbis\steam-open.exe`. |
| Escritorio | `C:\users\orbis\Desktop\Open Steam Client.lnk` | El mismo programa auxiliar, escrito en el formato de `tools/make-start-menu.py`. El explorer de Wine descarta un acceso del Escritorio sin ícono (`programs/explorer/desktop.c`, `add_launcher`), y el programa auxiliar de W289 no tenía, así que el acceso no aparecía. Desde la recompilación de SH1 del 2026-11-08 el programa lleva un recurso de ícono: el disco azul con centro blanco del glifo del menú Inicio, que el builder dibuja a 16, 32 y 48 píxeles y enlaza con `windres`. |
| Archivos | `C:\orbis\steam\` | `cacert.pem`, las DLL de gbe_fork (`gbe-x86-steam_api.dll`, `gbe-x64-steam_api64.dll`), su texto LGPL-3.0 y `gbe-SOURCE.txt`. |
| Datos | `/data/orbisdesk/steam`, `/data/orbisdesk/steam-games` | Los mismos que el título aparte: sesión guardada, biblioteca, juegos. El log sigue siendo `/data/orbisdesk/steam-client.txt`, con líneas `PWSTEAM client hosted …`. |

**Dentro del título el cliente no puede usar lo mismo que en ORBS00001,** así que el build cambia cuatro cosas:
- **C++:** se compila con clang-19 contra la libc++ 21 de `~/vk-h0/sysroot` y su overlay de libc (`libc-overlay-wine`), la misma libc++ que enlaza el ELF de hardware. La libc++ 11 del SDK, que usa el título aparte, tiene otra ABI. `__PS4__` mantiene a esa libc++ fuera de sus caminos de FreeBSD, como cuando se compiló (`upstream/DolphinPS4/toolchain/env.sh`).
- **Sockets:** Wine envuelve `setsockopt` y traduce él mismo los números de opción TCP de Linux (`platform/ps4/pw_wine_sockopt.c`). Con `STEAM_UI_HOSTED`, `native/steam/orbis/orbis_net_fix.h` deja `TCP_KEEPIDLE`/`INTVL`/`CNT` con los números de Linux, para que no se traduzcan dos veces, y curl se recompila así.
- **Relojes:** sólo a los objetos de Steam se les renombran `clock_gettime`/`clock_getres`, a los `pw_steam_*` de `orbis_clock.c` (`objcopy --redefine-sym`). Un `--wrap` global tocaría también las llamadas de Wine y de Mesa, que ya usan los números de FreeBSD.
- **Red:** Wine ya llamó a `sceNetInit`, y una segunda llamada da error. El parche de Playden `0003-shared-net-init.patch` le pregunta al anfitrión, y dentro del título la respuesta es "ya está andando".

**Símbolos:** el objeto (`build/steam-hosted/steam_client_hosted.o`, 4,2 MB sin DWARF) tiene cuatro símbolos globales fuertes, `pw_hw_steam_open`, `_draw`, `_pad` y `_active`; los demás símbolos fuertes quedan locales, así que no puede chocar con Wine, Mesa ni zlib. Los símbolos débiles quedan débiles y globales: son las copias COMDAT de funciones inline y de plantillas, compiladas con los mismos headers de libc++ 21 que la libc++ del título, y el enlace se queda con una copia de cada una. El primer build también los dejaba locales, y el enlace de W289 falló: la copia local del objeto ganaba cada grupo COMDAT, la de libc++-vk.a se descartaba, y los propios objetos de libc++ apuntaban a una sección descartada (`R_X86_64_PC32 out of range`, 340 errores). Ahora el builder falla si algún símbolo débil es un nombre de C, salvo los dos que clang emite en todo objeto C++ (`DW.ref.__gxx_personality_v0`, `__clang_call_terminate`). El builder comprueba que cada símbolo que necesita esté definido o importado por el `wine.elf` más reciente, o lo provean las bibliotecas estáticas del título (su libc, libm, libc++, libc++abi y compiler-rt). Los únicos imports nuevos son `sceNetRecv` y `sceNetResolverAbort`, que S2 ya probó en la consola, más `pw_hw_root_mode` (débil: el cliente enlaza aunque no esté).

## Modo ROOT y espacio libre

`pw_hw_root_mode()` (parche preparado para `native/wine_hardware.c`) devuelve si está activo el jailbreak de GoldHEN, y el cliente lo registra. El espacio libre se mide igual en los dos modos (`fstatfs`, `statfs`, `getfsstat`; ver [STEAM_S4-es.md](STEAM_S4-es.md)). En modo NORMAL el sandbox niega los tres (S4 01.12). **Todavía no se sabe si funcionan en modo ROOT.** W228 vuelve con `setuid` al uid de la app justo después del jailbreak, pero sigue fuera de la prisión; la corrida en la consola lo va a decir. Si el espacio sigue sin poder medirse, queda "COULD NOT BE MEASURED" con "install anyway".

## Compilación

```sh
python3 tools/build-steam-deps.py --target ps4      # una vez
python3 tools/build-steam-hosted.py
```

Salidas, en `build/steam-hosted/`:
- `steam_client_hosted.o`;
- `prefix/` (archivos para `drive_c`);
- `manifest.json` (hashes, el `wine.elf` contra el que se comprobó, imports nuevos).

`joined.o` conserva el DWARF para leer direcciones de un crash.

## Parches para los archivos compartidos de OrbisDesk

Están preparados para la sesión de builds, que los integra y compila. Se aplican con `git apply --check` sobre el árbol actual:
- `steam-hosted-native.patch`:
  - `native/hw_pad.c`: el pedido `<steam-open>` y `pw_hw_steam_pad` junto al overlay;
  - `platform/ps4/pw_wine_sink_ps4.c`: `pw_hw_steam_draw` antes del overlay;
  - `native/wine_hardware.c`: `pw_hw_root_mode`.
- `steam-hosted-tools.patch`:
  - `tools/build-wine-hardware.py`: el objeto en el enlace y los archivos del prefijo;
  - `tools/build-explorer-hw.py`: el ítem del menú Inicio.

## Pruebas en la PC (2026-11-07)

- `tools/build-steam-hosted.py` compila todo con la toolchain del título, y el chequeo de símbolos pasa contra `build/wine-hardware-w288/wine.elf`.
- **Enlace de prueba:** el objeto, con un `pw_hw_cursor_moved` vacío y las bibliotecas del título (crt1, libc++-vk, libc++abi-vk, libc, libm, libunwind, libkernel, libSceNet, compiler-rt), enlaza con `--no-undefined` y el `link.x` de W289 (base `0x1100000000`), forzando la entrada de los objetos de locale, thread y system_error de libc++. La primera prueba usaba el `link.x` del SDK, cuya base 0 ocultaba el error de W289; con el script de W289 el error se reprodujo, y con el objeto corregido pasa.
- **Páginas:** el renderizador integrado dibujó la biblioteca y el QR en un cuadro de 1280x720 con un pitch de 1344 píxeles. Las dos se leen bien, y el QR ocupa dos tercios del alto.
- **No se probó** (sólo en la consola): el hilo integrado, los ganchos del sink y del control, el pedido del programa auxiliar, el ítem del menú Inicio, y la convivencia del cliente con los invitados en marcha (memoria, hilos, el lock compartido de malloc).

## Primera corrida en la consola (W289, según la sesión de builds)

- Menú Inicio → "Open Steam Client" abrió el cliente integrado, y al salir volvió al escritorio.
- El acceso del Escritorio no aparecía, porque el programa auxiliar no tenía ícono (ver la tabla). El arreglo espera al próximo build de hardware.
- La corrida de Portal 2 usó el `steam_api.dll` propio del juego: ningún log tiene una línea `emu enable`, porque el emulador no se activó con triángulo en la página del juego. Todavía no es una prueba del interruptor de gbe_fork.

## W291: el interruptor del emulador

El usuario apretó triángulo en la página de Portal 2 y el interruptor "no funcionó" (`reports/wine-hardware-w291/physical/manual-20261108T033824Z/`, `run-0002.log` y `steam-client.txt`). El log del cliente se corta en `PWSTEAM emu enable dll=x86 interfaces=30`: el interruptor nunca registró `done`, un fallo ni `ok=`. El título siguió andando, y su log termina unos 15 s después, cuando el usuario lo cerró.

Qué muestra la evidencia, y qué no:
- **No es un crash ni una espera en otro hilo:** el hilo del cliente seguía dentro de `EnableEmulator` después de su primera DLL. Esa línea salía una vez por DLL, al final de sus pasos (copia, interfaces, archivos de ajustes). Lo que seguía es una segunda `steam_api*.dll` del juego, o la escritura de la marca.
- **Sin aviso:** la página del juego quedó en pantalla, sin cambios, durante todo el interruptor.
- **Un paso lento:** `steam_interfaces.txt` salía de 37 búsquedas con `std::regex` sobre la DLL del juego. En la PC, con libc++ (la del título), tardan 20 s con el `steam_api.dll` de 9 MB de gbe_fork; la búsqueda del literal tarda 18 ms, con la misma salida. La PS4 es más lenta que la PC. Cuánto tardó en la consola, y cuántas DLL de la API de Steam tiene Portal 2, no está en el log. Las trazas nuevas van a mostrar las dos cosas.

El cambio, en el objeto integrado (y en el código del título aparte):
- `SteamInterfaces` busca cada literal y lee los dígitos que lo siguen, en el mismo orden y con la misma regla de SteamClient017. Da lo mismo que la regex vieja con las DLL x86 y x64 de gbe_fork y con 3000 entradas al azar armadas con pedazos de los patrones.
- La página pasa a "TURNING ON THE EMULATOR..." o "RESTORING THE ORIGINAL STEAM API..." apenas se aprieta triángulo.
- Cada paso queda en el log con los milisegundos desde que se apretó: `start dlls=N`, después por DLL `dll=i/N step=read arch= game_bytes= emulator_bytes=`, `copied` (o `already_emulator`), `interfaces lines=` y `settings`, después `done dlls= entries=`, y al final `emu enable ok=` y `emu page back`. Las DLL van numeradas, sin nombre, porque una ruta puede nombrar el juego.

## Pestañas de la biblioteca

La lista de la biblioteca tiene tres pestañas: **ALL**, **INSTALLED** y **NOT INSTALLED**. Una línea bajo el título las muestra con la cantidad de juegos de cada una, y la activa se dibuja en el color de acento (azul). En W292 iba entre corchetes, pero la fuente no tiene corchetes y se veían como espacios. R1 pasa a la siguiente y L1 a la anterior. El usuario pidió R1 y R2, pero R2 es un gatillo, así que el par es L1/R1. L2 y R2 hacen lo mismo (su pulsación digital), así que sirve cualquiera de los dos pares. Al cambiar de pestaña se mantiene el juego elegido si la nueva lo lista, y las listas se leen de nuevo en cada página, así que una instalación terminada pasa su juego de pestaña. Log: `PWSTEAM library tab=N games=M`. En el build para la PC, `l` y `r` por stdin.

## Idioma del contenido

Muchos juegos guardan los archivos de cada idioma en depots propios. Hasta ahora toda instalación elegía inglés: los cuatro rechazos `language` de las líneas `PWSTEAM plan depots=…` son esos depots. **Cuadrado** en la página de un juego instalado abre **LANGUAGE**. Lista los idiomas que traen los depots propios del juego (`SelectionResult::languages` de Playden), con el instalado marcado. X sobre uno vuelve a planear la instalación en ese idioma, con `SelectDepots` de Playden, y muestra la página de instalación de siempre con `LANGUAGE: SPANISH (INSTALLED NOW: ENGLISH)`. X ahí corre la instalación:
- se bajan los depots del idioma nuevo;
- todo archivo que ya está con el SHA-1 correcto se conserva, como en cualquier verificación;
- los archivos que tienen los dos idiomas se reemplazan por los del nuevo.

Los archivos que sólo tenían los depots del idioma viejo quedan en la carpeta, y la página lo avisa. El `language` del registro pasa al nuevo sólo cuando todo pasó. Desde entonces, X ("verify and update") planea en el idioma del registro, no en inglés. Una instalación pausada o fallida no tiene registro (`RunInstall` lo borra al empezar), así que `.orbisdesk-language.txt`, en la carpeta del juego, guarda el idioma que se está instalando, y la próxima instalación sigue en ese idioma. Un juego con menos de dos idiomas avisa que Steam no tiene paquetes de idioma para él, y que sus idiomas, si los tiene, se eligen dentro del juego.

**Qué lee el juego:**
- **La API de Steam, a través de gbe_fork:** gbe_fork responde tanto `SteamApps()->GetCurrentGameLanguage()` como `SteamUtils()->GetSteamUILanguage()` con el `language=` de `steam_settings/configs.user.ini`, junto a su DLL (`dll/steam_apps.cpp`, `dll/steam_utils.cpp`, `dll/settings_parser.cpp` de release-2026_09_27). Con el emulador activo, una instalación primero devuelve las DLL del juego y al final vuelve a activar el emulador, con el idioma recién instalado. Con el `steam_api.dll` propio del juego, el idioma lo da Steam, que no corre dentro de OrbisDesk.
- **Juegos con motor Source:** su idioma de interfaz sale de `-language <nombre>` en la línea de comandos; sin eso, siguen el idioma de la interfaz de Steam. Según reportes de la comunidad, `-language` funciona en Half-Life 2, Portal y Portal 2. El acceso de un juego instalado en otro idioma que inglés recibe `-language <nombre>` cuando su ejecutable tiene `bin/engine.dll` al lado y la entrada de arranque de Steam no elige uno. El audio sigue el idioma del contenido del juego, que es `GetCurrentGameLanguage`.
- **El registro:** el cliente no escribe `HKCU\Software\Valve\Steam\Language`. El registro es del `wineserver` mientras el título corre: lo tiene en memoria y lo vuelve a guardar en `user.reg`, así que una escritura nativa en ese archivo se perdería o quedaría pisada. No se sabe si Portal 2 lee esa clave. Si `-language` y gbe_fork no alcanzan, el paso siguiente es un lanzador que fije la clave desde dentro de Wine antes de arrancar el juego.
- Otros juegos pueden tomar el idioma de un ajuste propio. Para esos no se configura nada.

**W292 en la consola:**
- El interruptor de Triángulo tardó 922 ms, y la restauración funcionó.
- Las pestañas funcionaron.
- Se instaló español: 686 MB bajados, 3706 archivos verificados.
- Con el emulador activo, Portal 2 cargó el `steam_api.dll` de gbe_fork pero siguió en inglés.
- Hay dos causas posibles, y las dos quedan cubiertas:
  - **Un `configs.user.ini` que quedó de antes.** El interruptor interrumpido de W291 había escrito archivos en `bin/steam_settings/` y se cortó antes de su registro. Cada interruptor posterior los tomó como archivos del juego y no los tocó, así que pudo quedar `language=english`. Los números de W292 encajan: 2 DLL y 5 entradas en el registro, o sea 3 archivos y ninguna carpeta. Ahora el interruptor fija `language=` en un `configs.user.ini` que ya existe, y conserva todas sus otras líneas. Registra `step=language file=new|existing state=same|updated language=…`. Se probaron siete formas de `configs.user.ini` en la PC, incluidas líneas CRLF y una sección que falta.
  - **Source toma su idioma de interfaz de la línea de comandos:** el argumento `-language` de arriba.
- El acceso recibe sus argumentos cuando termina una instalación o una verificación. Para el Portal 2 instalado en W292, eso es X en su página (no baja nada) o elegir de nuevo el idioma.

**El idioma de Steam** (cuadrado en la lista de la biblioteca) es el idioma que piden las instalaciones nuevas, como el ajuste propio de Steam. Se guarda en `/data/orbisdesk/steam/steam-language.txt`, es inglés hasta que se cambia, y se muestra en el título de la biblioteca. Un juego que no lo trae se instala en inglés, o si no en su primer idioma, y la página de instalación avisa que no está disponible. Un juego instalado conserva su idioma: cuadrado en su página lo cambia. La lista son los códigos de idioma de la API de Steam.

**Los nombres de idioma en pantalla** son el nombre propio de cada idioma, como lo da la lista de idiomas de Steam: ESPAÑOL - ESPAÑA, ESPAÑOL - LATINOAMÉRICA, FRANÇAIS, PORTUGUÊS - BRASIL, ČEŠTINA, ROMÂNĂ, TÜRKÇE, etcétera. `steam_ui.c` dibuja UTF-8:
- una letra de Latin-1 con signo, o Ă, Č o Š, es la mayúscula de `hw_text.h` con un signo de dos filas encima, dentro del interlineado (una línea son 10 filas, una letra 7); la cedilla va abajo;
- las minúsculas se dibujan como mayúsculas;
- cualquier otro carácter no ASCII no ocupa lugar.

La barra de selección ahora también cubre los signos. Los idiomas cuya escritura la fuente no tiene conservan su nombre en inglés: ruso, búlgaro, griego, ucraniano, árabe, tailandés, vietnamita, japonés, coreano y los dos chinos. Los logs conservan los códigos de Steam. Los nombres de juego con letras acentuadas ahora también las muestran. La lista de idiomas se dibujó en la PC en un cuadro de 1280x720 con un pitch de 1344 píxeles.

Líneas del log:
- `PWSTEAM language page carried=N installed=…`
- `PWSTEAM language chosen=… installed=…`
- `PWSTEAM plan … language=… asked=… carried=N`
- `PWSTEAM plan resume_language=…`
- `PWSTEAM plan steam_language=…`
- `PWSTEAM steam_language set=… saved=…`
- `PWSTEAM install start … language=… installed_language=…`
- `PWSTEAM shortcut … language_args=…`
- `PWSTEAM emu enable dll=i step=language …`

Los nombres de idioma son los de Steam, y no son datos de la cuenta. Si Steam no tiene el idioma elegido para esta cuenta, no se instala nada y la página lo avisa (`language unavailable`).

## Desinstalar

Pedido el 2026-11-08. La sesión de builds había borrado `steam-games/19680` (Alice: Madness Returns, SteamStub, unos 8,9 GB) por FTP porque el cliente no tenía cómo hacerlo. Ahora **OPTIONS** en la página de un juego instalado abre una página UNINSTALL.

- **Confirmación:** la página muestra el tamaño y la carpeta, y un aviso en ámbar. Dice que se borran la carpeta y los accesos directos del juego, y que el paso no se puede deshacer: el juego hay que bajarlo de nuevo. También dice que las partidas guardadas en la carpeta del juego se van con él. X desinstala; O conserva el juego.
- **Orden del borrado:** primero se borra todo lo que hay en `steam-games/<app>`, después el registro `.orbisdesk-install.json` y al final la carpeta. Si un borrado se corta a medias, el registro sigue ahí. El juego sigue figurando como instalado, su página se sigue abriendo y OPTIONS puede volver a intentarlo.
- **Nunca sigue enlaces:** cada entrada se abre con `O_DIRECTORY | O_NOFOLLOW`. Una carpeta se vacía y se borra, y cualquier otra cosa, un enlace simbólico incluido, se desvincula. No se toca nada fuera de la carpeta del juego. No se usa `stat()`, porque el `struct stat` del SDK no es el del kernel.
- **Accesos directos:** se borran sólo después de que la carpeta ya no está. El cliente borra el `.lnk` que hizo `WriteGameShortcuts` en el Escritorio y en Inicio → Programs → Steam, pero sólo si su destino está dentro de `Z:\orbisdesk\steam-games\<app>\`. Un `.lnk` del mismo nombre que apunta a otro lado es del usuario y se queda.
- **Página de resultado:** muestra cuántos archivos y carpetas se borraron y el estado de cada acceso directo. Si falla, dice cuántos elementos no se pudieron borrar, junto con la primera ruta y su errno. Esa ruta va sólo en pantalla, nunca en el log, porque los nombres de archivo de un juego pueden nombrarlo.
- **Log:**
  - `PWSTEAM uninstall page app=N`, después `canceled` o `confirmed bytes=`
  - `PWSTEAM uninstall remove start record=1`
  - `PWSTEAM uninstall remove ok= files= folders= failures= errno=`
  - `PWSTEAM uninstall done ok= ms= shortcuts_prefix= desktop=removed|absent|not_ours|unreadable|failed|kept start=… shortcut_errno=`
- **Prueba en la PC** (WSL, contra los objetos del S4 host; pasan todos los chequeos):
  - se borra un árbol con carpetas anidadas y un enlace a una carpeta fuera del juego, y la carpeta de afuera queda intacta;
  - una carpeta que no se puede vaciar (modo 555) falla con errno 13 y conserva el registro, y un segundo intento, después de arreglar el modo, borra todo;
  - se borra el `.lnk` de este juego, se conserva uno del mismo nombre que apunta a otro lado, y un segundo borrado informa `absent`.

Una descarga pausada o fallida (una carpeta sin registro) sigue sin poder borrarse. El juego figura como no instalado, así que su página no se abre.

## Pie fijo

El usuario pidió que la ayuda de los botones y el estado queden abajo de la pantalla, como en Crema, para que no se muevan cuando la lista cambia de largo (al cambiar de pestaña con L1/R1, por ejemplo).

- **Marca del pie:** una línea de la página que empieza con `STEAM_UI_FOOTER` (byte 0x02) abre el pie. Esa línea y todas las que siguen van en una franja oscura con una raya azul arriba.
- **Franja fija:** la franja mide cuatro líneas de texto en todas las páginas, así que empieza a la misma altura en todas (y=548 de 720 en el título). Sólo un pie de más de cuatro líneas la agranda.
- **Cuerpo:** el texto de arriba se corta donde empieza la franja, y una línea que no entra entera no se dibuja. La línea de botones de todas las páginas pasó al pie.
- **Biblioteca:** el pie lleva "GAME n OF m" y el idioma de Steam, después (en el título) "CLOSE RUNNING GAMES BEFORE INSTALLING." y después los botones. El título queda en "STEAM LIBRARY". La lista sigue con 11 filas. Cada fila se corta a una sola línea: un nombre de más de 36 caracteres queda en 33 más "...", así que un nombre largo ya no salta de línea ni empuja las filas. Arriba y abajo no tienen ayuda.
- **Listas de idiomas:** las listas quedan en 9 filas. Así entran bajo el encabezado del idioma de Steam a 1280x720. "n OF m" va en el pie.
- **Avisos:** `STEAM_UI_WARN` (byte 0x03) dibuja una línea en ámbar. Se usa para SteamStub, para el aviso de desinstalar, para un borrado que falló, para "no shortcut" y para el espacio libre sin medir.
- **SteamStub:** al usuario se le pasó la línea "HAS STEAMSTUB DRM" de Alice en W293. Ahora SteamStub va en la primera línea bajo el nombre del juego, en ámbar, en la página del juego y en el resultado de la instalación. Si es la razón por la que no se hizo acceso directo, la línea del acceso directo lo dice (`skipped=steamstub` en el log). Cualquier otra razón también se muestra.
- **Acento:** `STEAM_UI_ACCENT` (byte 0x04) pasa las letras al color de acento y de vuelta. Lo usa la pestaña activa de la biblioteca.
- **Redacción:** la fuente no tiene coma ni apóstrofo, así que los textos nuevos los evitan. "NEW LANGUAGE'S FILES" ahora dice "FILES OF THE NEW LANGUAGE".
- **Dibujos en la PC a 1280x720 y 1920x1080:** la biblioteca en ALL con 11 filas y en INSTALLED con 2, la página de Alice con SteamStub y la confirmación de desinstalar. La franja empieza en el mismo lugar en todos.

## Confirmación para cerrar sesión

El usuario cerró sesión sin querer al tocar triángulo, y pidió una confirmación como la de desinstalar (2026-11-08).

- **Dónde:** triángulo en la biblioteca, y triángulo en la página "COULD NOT LOAD THE LIBRARY".
- **Qué muestra:** una página "SIGN OUT". Su línea ámbar dice que se borra de la consola la sesión guardada y que para volver a usarlo hay que iniciar sesión de nuevo con la app de Steam. También dice que los juegos instalados y sus accesos directos quedan.
- **Botones:** el pie dice "X: SIGN OUT     O: STAY SIGNED IN". Sólo X borra la sesión. O vuelve a la biblioteca, o sale desde la página de error, y la sesión queda.
- **Log:** `PWSTEAM sign_out page`, después `PWSTEAM sign_out confirmed` o `PWSTEAM sign_out canceled`. Después de confirmar, `PWSTEAM signed_out=1` como antes.
- **Objeto del título:** `996b4549fb97fc183589531343d52f335978c4ead8f7a8bb3be43d9da637c9f8`, verificado contra el `wine.elf` de W297 sin imports nuevos. También enlaza de prueba con el `link.x` de W297. Todavía no corrió en la consola.

## SteamStub antes de la descarga

En W293, Alice: Madness Returns (8,9 GB) y BioShock se bajaron enteros antes de que la revisión posterior a la instalación encontrara la sección `.bind` de SteamStub. Después el usuario tuvo que desinstalarlos. Ahora una instalación nueva o retomada revisa primero (2026-11-08):

- **Qué se baja:** las llaves y los manifests de los depots, como los baja la instalación, y después sólo los chunks que tienen los encabezados y la tabla de secciones de cada ejecutable listado. Por lo general es el primer chunk, hasta 1 MB por ejecutable. Se revisan como mucho cuatro ejecutables distintos de las entradas de lanzamiento de Steam. No se escribe nada en el disco.
- **Qué cuenta como SteamStub:** igual que al hacer el acceso directo, que todo ejecutable que se lee como PE tenga `.bind`. Una tabla de secciones que no se puede leer lo deja sin saber, nunca como "sin SteamStub".
- **Con SteamStub:** una página "STEAMSTUB DRM" con una línea ámbar y el tamaño que ocuparía la instalación completa. El pie dice "O: DO NOT INSTALL     OPTIONS: INSTALL ANYWAY". O vuelve a la biblioteca sin haber escrito nada. OPTIONS sigue a la página de instalación de siempre, que entonces lleva una línea ámbar de SteamStub.
- **Sin SteamStub:** la página de instalación de siempre. La instalación reusa las llaves, los servidores y los manifests de la revisión, y escribe sus chunks en su lugar una vez que los archivos tienen su tamaño. Los workers los encuentran ahí (su SHA-1 coincide) y no los bajan de nuevo.
- **Cuando no puede correr** (sin llaves, sin servidores, un chunk que no se pudo bajar): la página de instalación lo dice en una línea ámbar, y la instalación revisa el ejecutable al final como antes.
- **No se revisa:** un juego instalado que se verifica, se actualiza o cambia de idioma. Su registro ya dice si tiene SteamStub.
- **Sólo detección.** Nada de esto quita SteamStub ni lo esquiva.
- **Log:** `PWSTEAM precheck entry=N pe= arch= steamstub= chunks=`, después `PWSTEAM precheck app= exe= pe= steamstub=0|1 fetched= ms=`, `PWSTEAM precheck answer=back|install_anyway`, y en la instalación `PWSTEAM install from_precheck=1` y `PWSTEAM install prefetched=N of=M`.
- **Prueba en la PC:** imágenes PE cortadas en chunks dan la misma máquina y el mismo `.bind` que la imagen entera. Sólo se piden los chunks que tienen los encabezados y la tabla (2 de 4096 en una imagen de 1 MB con chunks de 256 bytes). Se lee una tabla que cruza el borde entre dos chunks. Un chunk que no se puede bajar se lee como "no es PE", no como "sin SteamStub". El `notepad.exe` de Windows (x64 y x86) y `cmd.exe` se leen igual por chunks que enteros.
- **Falta comprobar en la consola:** Alice (19680) y BioShock (7670) tienen que dar `steamstub=1` sin la descarga completa, y Portal (400) tiene que dar `steamstub=0`.

## Nombre del dispositivo

Steam Guard mostraba los inicios de sesión del cliente como "Playden (PS5)". El parche de Playden `0004-device-name-steamdesk.patch` cambia todos los nombres que se le mandan a Steam:
- el nombre del dispositivo en el inicio de sesión por QR y por contraseña (`device_friendly_name`) es "SteamDesk (PS4)";
- el nombre de la máquina en el logon del CM, y el del lote de Steam Cloud (que este cliente no usa), es "SteamDesk";
- el `User-Agent` de HTTP es "SteamDesk/1.0".

El id de la máquina no cambia, así que una sesión guardada sigue andando. Para una sesión hecha antes de este cambio, Steam puede seguir mostrando el nombre viejo hasta el próximo inicio de sesión.

## Para aceptarlo en la consola

1. Menú Inicio → "Open Steam Client" muestra la UI en inglés.
2. La biblioteca, una instalación y el interruptor de gbe_fork funcionan.
3. En modo ROOT, el plan muestra un espacio libre medido.
4. O en la biblioteca vuelve al mismo escritorio, con sus ventanas como estaban.
