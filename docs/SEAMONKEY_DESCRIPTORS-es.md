# SeaMonkey y los descriptores de archivo del título

[English](SEAMONKEY_DESCRIPTORS.md) | [Español](SEAMONKEY_DESCRIPTORS-es.md)

Estado: 04.25 (cinco descriptores por hilo) se ejecutó en la consola en run-0234 sin ningún `EMFILE`; todavía no se conoce el margen. 04.26 solo cambia una línea de log y no está compilado. 2026-11-18.

## Run-0234: la primera ejecución con cinco descriptores por hilo (04.26)

Run-0234 es 04.25 con OpenGL activado, en `reports/wine-hardware-w303/physical/20261118T215511Z/`. SeaMonkey se arrancó, se usó, se cerró y se volvió a arrancar.

**El primer arranque no tuvo ningún `EMFILE`, y salió con estado 0.**
- Se presentaron fotogramas de la GPU (`PWVK show_frame … path=gpu_layer`). No hubo `PWTHREAD request_socket off`, así que cada hilo nuevo usó el par de sockets.
- El punto más alto fue `descriptor_growth fd=818 open=819 files=260 pipes=288 sockets=240`. Las tuberías crecieron desde 32 al arrancar, unas tres por hilo, y los sockets unos dos, como se esperaba.
- Con `open=819` el título estaba por encima del fallo de run-0224 (798) y cerca del de run-0229 (837), sin fallar. Así que el límite no es el recuento total del título.
- Los dos fallos tenían muchos más extremos de tubería: 435 en run-0224 y 498 en run-0229. Run-0234 se quedó en 288. Esto encaja con un límite que cuente tuberías, por ejemplo la memoria de tuberías del kernel, pero los contadores de la consola no se pueden leer (`kern.*` responde `ENOENT`), así que no está demostrado.

**El segundo arranque tampoco tuvo ningún `EMFILE`.** Terminó en la excepción de C++ de MangoHud, no por descriptores ([composición por GPU](SEAMONKEY_GPU-es.md)).

**Lo que queda:**
- Una ejecución sin fallo no muestra el margen. Mirar `pipes=` en cada ejecución con composición por GPU y YouTube, y `descriptor_kinds` si vuelve el `EMFILE`.
- Si vuelve con muchas tuberías otra vez, el siguiente paso es la tubería de espera. También podría ser un par de sockets, y entonces no quedaría ningún extremo de tubería por hilo. Eso cambia el mismo código de Wine que 04.25 y necesita su propia prueba en la consola.

**Este cambio (no compilado):** [pw_wine_fs.c](../platform/ps4/pw_wine_fs.c): `descriptor_growth` estima los hilos como las tuberías entre tres, no entre siete. Ya no imprime los contadores `kern.*` en cada máximo nuevo, porque todos los nombres respondieron `ENOENT`. La línea `PWFS kernel_files` del primer `EMFILE` se mantiene. El archivo compila para la consola con `-Wall` y sin avisos.

## Run-0229: la ejecución con trazas, y cinco descriptores por hilo (04.25)

Run-0229 es 04.24 con OpenGL activado, en `reports/wine-hardware-w303/physical/20261118T203415Z/` (run-0228 es la parte anterior del mismo arranque del título). La configuración de PES 2014 y `pes2014.exe` se ejecutaron antes que SeaMonkey, así que no es una ejecución solo de SeaMonkey.

**Lo que muestran las trazas:**
- El primer `EMFILE` llegó con `open=837`, en la carpeta `safebrowsing/google4` de Safe Browsing. Lo que más creció fueron las tuberías: de 42 al arrancar a 449 (`descriptor_growth fd=792`) y después 498. Los archivos crecieron de 39 a 303.
- Un momento después una apertura funcionó con `fd=869` y `open=870`. Más tarde otras aperturas volvieron a fallar (las carpetas del escritorio de explorer, `xulstore.json`). Así que el límite no es un recuento de los descriptores propios del título. Se mueve con otra cosa.
- Todos los nombres `kern.*` respondieron `ENOENT` con `sysctlbyname`, así que los contadores de la consola no se pueden leer desde el título.
- SeaMonkey arrancó 126 hilos y tuvo como mucho 54 vivos a la vez (`thread_new … live=`). Por creador: 96 por NSPR (`nss3.dll+1060f9`, el inicio de todo hilo de Gecko), 14 por Mesa (`libgallium_wgl.dll+de8d7`), 6 por `xul.dll+33d6c60`, 5 hilos de estilo Chromium (`xul.dll+8e8f8a`), y uno cada uno por SeaMonkey, MangoHud y otros dos puntos de `xul.dll`.
- En todo el título había unos 71 hilos vivos (tuberías entre siete), 497 descriptores.

**El cambio (no compilado):** un hilo creado por `NtCreateThreadEx` usa un par de sockets Unix para sus peticiones y sus respuestas, en lugar de dos tuberías. Necesita cinco descriptores en lugar de siete. Con 71 hilos son unos 140 descriptores menos. La ejecución se habría quedado por debajo de `open=700`.
- [prepare-wine-boot.py](../tools/prepare-wine-boot.py), `thread.c` de ntdll: `NtCreateThreadEx` crea un par de sockets y hace no bloqueante el extremo del servidor con `pw_wine_socket_nonblock`, que prueba `fcntl` y después `SO_NBIO`. Si falla alguno de los dos pasos, registra `PWTHREAD request_socket off`, crea tuberías como antes y no vuelve a probar el par de sockets. La salida de un hilo cierra ese único descriptor una sola vez.
- `server.c` de ntdll: `init_thread_pipe` ve el socket, crea solo la tubería de espera y envía `reply_fd` -2.
- [build-wine-delete-server.py](../tools/build-wine-delete-server.py), `thread.c` del servidor: `new_thread` acepta un socket que `fcntl` rechaza, con la misma alternativa que los demás sockets del servidor. `init_thread` interpreta -2 como "responder por el descriptor de peticiones" y comparte ese descriptor entre los dos.
- `request.c` del servidor: los dos puntos que alternan entre esperar una petición (`POLLIN`) y terminar una respuesta (`POLLOUT`) ya no fijan los eventos del segundo descriptor después de los del primero cuando los dos son uno. Si no, el servidor dejaría de escuchar al hilo.
- El primer hilo de un proceso, creado por el servidor, conserva sus tuberías. La tubería de espera no cambia: un hilo conserva su extremo de escritura para devolver un aviso que tomó una espera anidada.
- [build-guest-hw.py](../tools/build-guest-hw.py): `thread_new … by=` también mira más allá de `nss3.dll`, así que nombra el código de Gecko que arrancó cada hilo NSPR.
- Las cuatro unidades de Wine (`thread.c` y `server.c` de ntdll, `request.c` y `thread.c` del servidor) compilan con las recetas de la consola de `build/wine-boot/report.json` y `build/wine-server/report.json`. No hay avisos nuevos. Los tres de `server.c` de ntdll son los mismos sin este cambio.

**Riesgos que comprobar en la consola:**
- Las respuestas mayores que el búfer del socket se escriben por partes. El servidor ya las termina con `POLLOUT`, el camino que usaba una tubería llena.
- La línea `PWNET nonblock` aparece una vez, si `fcntl` se rechazó y se usó `SO_NBIO`.
- Si aparece `PWTHREAD request_socket off`, el título funcionó con tuberías, como antes.

**Siguiente ejecución en la consola, con este cambio compilado:** OpenGL activado, SeaMonkey sin nada antes, y después YouTube. En `descriptor_growth`, `pipes` debería crecer unos tres por hilo y `sockets` unos dos. Buscar `PWTHREAD request_socket off` y cualquier bloqueo justo después de que un programa arranque un hilo. Ejecutar también un juego de 32 bits y uno de 64 bits, porque cambian los hilos de todos los programas.

## Run-0224: la composición por GPU llega al límite al arrancar (04.22)

Run-0224 es 04.22 con OpenGL activado en el `user.js` de la consola, después de que PES 2014 se ejecutara y saliera en la misma sesión. Está en `reports/wine-hardware-w303/physical/20261118T191237Z/`. SeaMonkey presentó fotogramas de la GPU (`PWVK show_frame … path=gpu_layer`). Unos 10 s después de arrancar, el título se quedó sin descriptores:

```text
PWFS descriptors open=798 highest=797 maxfilesperproc=-1 errno=2 maxfiles=-1 errno=2
PWFS descriptor_kinds files=295 folders=11 pipes=435 sockets=35 other=20 unknown=2 nofile=13952/13952 errno=0
```

Después Gecko se detuvo en un punto de ruptura (`0x80000003`) en su hilo principal, en `xul.dll`. Es una parada del tipo `MOZ_CRASH` después de que fallara una apertura, no el fallo anterior de la GPU.

**Las tuberías son las de los hilos de Wine, no una fuga de GL.**
- Con el servidor dentro del proceso, cada hilo de Wine tiene siete extremos de tubería: sus tuberías de petición, respuesta y espera (`dlls/ntdll/unix/server.c` `init_thread_pipe`, `thread.c` `NtCreateThreadEx`). El hilo guarda cuatro (el extremo de escritura de la petición, el de lectura de la respuesta y los dos de la espera) y el servidor guarda tres. Esto corrige los seis de "Por qué se llena la tabla", más abajo.
- 435 extremos de tubería son unos 62 hilos vivos en el título: los de explorer y los de SeaMonkey.
- Al salir, el invitado de SeaMonkey tenía 89 hilos en su lista. 80 de ellos empiezan en `_beginthreadex` de ucrtbase, que usan tanto los hilos NSPR de Gecko como las colas de Mesa. Así que la dirección de inicio no dice quién los creó.
- La composición por GPU añade a SeaMonkey los hilos de Mesa. Zink arranca un hilo de envío y cuatro de compilación por pantalla, y uno más por cada contexto GL con hilo propio (`zink_screen.c`, `u_threaded_context.c`; la caché de shaders está desactivada en esta compilación, así que `disk$` y `zcq` no arrancan). Son unos 7 hilos y 49 descriptores. Por eso la composición por GPU llega al límite al arrancar, mientras que Basic llegaba más tarde, en YouTube.

**El límite no es el de la tabla de descriptores, y el título no puede subirlo.**
- `RLIMIT_NOFILE` ya es 13952.
- El título se ha quedado sin descriptores en 958 (run-0180), 1035 (run-0212), 798 (run-0224) y, con VLC, con 459 abiertos y el más alto en 642 (`manual-20261109T221515Z/run-0004.log`). Un recuento por proceso de las entradas de la tabla fallaría siempre en el mismo número, y VLC no habría fallado con entradas libres por debajo de 642.
- Así que el kernel cuenta otra cosa. Puede ser el total de archivos abiertos de la consola en todos los procesos, si el kernel de Sony devuelve `EMFILE` donde `falloc` de FreeBSD devuelve `ENFILE`. Los MIB numéricos de `sysctl` respondieron `ENOENT`, así que todavía no se ha leído.

**Este cambio (no compilado):**
- [pw_wine_fs.c](../platform/ps4/pw_wine_fs.c): en el primer `EMFILE`, una línea `PWFS kernel_files` con `kern.openfiles`, `kern.maxfiles`, `kern.maxfilesperproc`, `kern.maxusers`, los contadores de sockets y la memoria de tuberías, leídos por nombre con `sysctlbyname` de libkernel. Un nombre rechazado imprime `-1/<errno>`.
- En cada `PWFS fd_high`, una línea `PWFS descriptor_growth` con los mismos tipos que `descriptor_kinds`, los hilos estimados (tuberías entre siete) y los contadores del kernel. Muestra qué tipo crece hacia el límite y si `kern.openfiles` crece con el título.
- [build-guest-hw.py](../tools/build-guest-hw.py): `PWGUEST thread_new module=… id=… made=… live=… by=módulo+desplazamiento start=módulo+desplazamiento` para cada hilo invitado, los 256 primeros del título. `by` es el primer llamador fuera de kernelbase, kernel32, ntdll y las bibliotecas de C, así que distingue `xul.dll` de `libgallium_wgl.dll` y `nss3.dll`. `live` cuenta los hilos del invitado que no han terminado.
- `pw_wine_fs.c` compila para la consola con las opciones de la receta de enlace y `-Wall`, sin avisos; `sysctlbyname` se resuelve a la exportación de libkernel. La unidad de hilos de kernelbase compila para x86_64 e i386 con la receta del builder y `-Wall`, sin avisos.

**Lo que no se cambió, y por qué:**
- Menos descriptores por hilo requiere un cambio del protocolo de Wine. El hilo conserva el extremo de escritura de su tubería de espera solo para devolver un aviso que tomó una espera anidada (un gestor de señal durante una espera). Un hilo que lo guardara en memoria se quedaría bloqueado en su `read` reanudado. Eso requiere una petición nueva al servidor o una espera que no pierda avisos, y una prueba en la consola.
- Desactivar el contexto con hilo propio de Mesa (`GALLIUM_THREAD=0`) quitaría solo uno o dos hilos, y haría más lento todo programa GL.

**Siguiente ejecución en la consola, con este cambio compilado:** OpenGL activado. Arrancar SeaMonkey solo, sin PES antes, esperar 30 s y abrir YouTube. Enviar el log. Si `kern.openfiles` está cerca de `kern.maxfiles` en el fallo, el límite es el de la consola, y el arreglo es usar menos descriptores. Si los contadores se rechazan o están lejos, `thread_new` dice los hilos de qué módulo hay que reducir.

## El síntoma

En la versión 04.11 de la aplicación, que ya incluye el [cambio de memoria flexible](SEAMONKEY_FLEXIBLE_MEMORY-es.md), SeaMonkey carga Google por completo. YouTube sigue quedándose a medias.

## Qué muestra el log

La ejecución es `reports/wine-hardware-w303/physical/20261117T105502Z/run-0180.log`, una sola sesión de SeaMonkey en YouTube.

**Esta vez la memoria no es el límite.** Al arrancar, `flexible_free` es de 389 MB y `direct_free` de 4,69 GB. El log no tiene ninguna línea `PWVM flexible low`, `anon mmap error` ni `PWFAULT`. Las líneas `PWVM decommit_host … keeps direct memory` muestran que el cambio de memoria flexible funciona. `seamonkey.exe` termina con estado 0.

**El título se queda sin descriptores de archivo.** Todos los descriptores del wineserver y de cada invitado comparten una sola tabla, porque el servidor corre dentro del título. Las líneas `PWFS fd_high` muestran cómo crece la tabla mientras YouTube se reproduce: 343 cuando SeaMonkey abre su perfil, y después 474, 609, 675, 854 y 922. Entonces:

```text
PWFS open_failed errno=24 n=1 path=.../Profiles/orbis/cache2
PWFS descriptors open=958 highest=957 maxfilesperproc=-1 errno=2 maxfiles=-1 errno=2
00bc:err:winediag:NtCreateFile Too many open files, ulimit -n probably needs to be increased
PWFS open_failed errno=24 n=2 path=.../Profiles/orbis/cache2/doomed
...  (se registran 16 y después el log deja de contar)
```

`errno=24` es `EMFILE`. La caché de disco de SeaMonkey ya no podía abrir sus archivos. Cualquier otra apertura en el título fallaba igual, tanto sockets como archivos. Eso es una página que deja de cargar sin un fallo.

El fallo no se limitó a SeaMonkey. Justo después, el sondeo del escritorio de explorer, que se hace cada 2 segundos, no pudo listar la carpeta del escritorio:

```text
003c:err:explorer:orbis_poll_desktop_folders PWDESK poll change files=0
0024:err:explorer:orbis_reload_launchers PWDESK reload reason=poll launchers=23->0 files=0
```

Los iconos volvieron en el sondeo siguiente, cuando ya se habían liberado descriptores.

**El tope de hilos es otro problema, y llegó después.** Las 13 líneas `PWGUEST thread_overflow … count=256` aparecen después de los fallos `EMFILE`. La cuenta no es el número de hilos vivos. La lista del invitado (`struct ps4_guest`, [build-guest-hw.py](../tools/build-guest-hw.py)) registra cada hilo que crea SeaMonkey y nunca quita los que terminaron, así que cuenta todos los hilos iniciados desde el arranque. Un hilo pasado de 256 sigue corriendo. Solo no se termina con el invitado al salir, y aquí el invitado salió con normalidad. Por eso este tope no detiene una página.

Las 37 líneas `PWGUEST shared_thread … WINMM.dll+1cb50` son el hilo de `PlaySound` de winmm (`proc_PlaySound` en el `winmm.dll` compilado). Cada llamada a `PlaySound` inicia uno, y termina por sí solo. Se cuentan como hilos de todo el proceso porque la regla de W281 incluye cualquier hilo que empiece en winmm, no solo el del temporizador. No son la causa.

## Por qué se llena la tabla

Con el wineserver dentro del proceso, los dos extremos de cada tubería y de cada socket de Wine están en la única tabla del título:

- **Un hilo vivo ocupa seis descriptores.** Wine da a cada hilo una tubería de petición, una de respuesta y una de espera, y el servidor y el hilo guardan cada uno un extremo de cada tubería.
- **Un handle de archivo o de socket abierto ocupa dos en cuanto se usa.** El servidor guarda su descriptor. El cliente recibe una copia por `SCM_RIGHTS` y la guarda en su caché de descriptores.
- **Cada imagen mapeada guarda uno** en el lado del servidor.

Gecko con YouTube usa muchos hilos: decodificación multimedia, el hilo de sockets, DNS, decodificación de imágenes, ayudantes de JavaScript y workers. Además, en Gecko 60 mantiene abiertos hasta 128 archivos de la caché de disco, y muchos sockets. Junto con explorer y sus servicios, llega fácilmente a 958.

Todavía no se sabe si 958 es un límite fijo del kernel. Un título no puede leer los sysctl `maxfilesperproc` y `maxfiles` (`errno=2`). Una ejecución anterior de VLC (`reports/wine-hardware-w303/physical/manual-20261109T221515Z/run-0004.log`) dio `EMFILE` con `open=459 highest=642`, algo que un simple recuento por proceso no haría. Así que el límite puede contar algo distinto de las entradas de la tabla que ve `fcntl`.

## El cambio

- **Perfil** ([seamonkey-user.js](../fixtures/browser/seamonkey-user.js)):
  - `browser.cache.disk.enable` pasa a `false`, así que SeaMonkey no usa archivos de caché de disco. Sus aperturas eran las que fallaban.
  - `browser.cache.memory.capacity` pasa de 32 MB a 64 MB en su lugar. Desde el cambio de memoria flexible, el heap de malloc de SeaMonkey usa memoria directa.
  - `network.http.max-connections` pasa de 900 a 64.
- **Log** ([pw_wine_fs.c](../platform/ps4/pw_wine_fs.c)): el informe del primer `EMFILE` añade una línea que separa los descriptores abiertos por tipo y lee el límite del kernel:

  ```text
  PWFS descriptor_kinds files=… folders=… pipes=… sockets=… other=… unknown=… nofile=<blando>/<duro> errno=…
  ```

  `pipes` dividido entre seis es más o menos el número de hilos vivos. `nofile` es `RLIMIT_NOFILE`, leído con el `getrlimit` de libkernel. libkernel usa los números de recurso de FreeBSD, así que el código pasa 8; el `RLIMIT_NOFILE` de la cabecera del SDK (7) es el número de Linux.

Ninguno de los dos cambios oculta el fallo. Si la tabla se sigue llenando, aparecen las líneas `PWFS open_failed` y `descriptor_kinds`.

## Qué se probó

- `pw_wine_fs.c` compila con las opciones de la receta de enlace (`clang --target=x86_64-pc-freebsd12-elf -D__ORBIS__ -fPIC -O2`, más `-Wall`) sin avisos. `getrlimit` se resuelve con la exportación de libkernel, no con la libc del SDK. No se escribió nada en `build/` ni en `out/`.
- **No probado:** no se compiló ningún paquete y nada se ejecutó en la consola. Los nombres de las preferencias son los de Gecko 60. No se comprobó si SeaMonkey 2.53.24 las aplica.

## Prueba en la consola (requiere una compilación y la aprobación del usuario)

1. Abrir YouTube en SeaMonkey, reproducir un vídeo durante un minuto y desplazarse por la página.
2. Buscar en el log `PWFS open_failed`, `descriptor_kinds`, `Too many open files` y `PWDESK poll change files=0`.
3. Si la tabla se sigue llenando, la línea `descriptor_kinds` dice adónde van los descriptores. Si son sobre todo `pipes`, son hilos vivos; si son sobre todo `sockets`, son conexiones; y si son sobre todo `files`, son handles de archivo.

## Pasos siguientes posibles, según esa línea

- **Límite blando de `nofile` por debajo del duro:** subir el límite blando al arrancar. El cambio de Wine en `tools/prepare-wine-boot.py` omite `set_max_limit( RLIMIT_NOFILE )` en la consola, así que nadie lo ha probado. Con GoldHEN quizá también se pueda subir el límite duro.
- **Sobre todo tuberías:** dar a cada hilo menos descriptores con el servidor dentro del proceso, o hacer que Gecko inicie menos hilos.
- **Sobre todo archivos o sockets:** con el servidor dentro del proceso, dejar de guardar en el cliente su propia copia del descriptor de un handle. Los dos lados comparten una tabla, así que la copia es lo que duplica la cuenta. Cerrar el descriptor del servidor mientras el cliente lo usa es la carrera que la copia evita, así que hay que hacerlo con cuidado.
- **Lista de hilos:** quitar de `struct ps4_guest` los hilos terminados cuando se llena. El código que copia la lista y la usa fuera del bloqueo (`ps4_guest_end`, `ps4_overlay_close_guest`) no debe ver un handle cerrado que se haya reutilizado para otro objeto.
