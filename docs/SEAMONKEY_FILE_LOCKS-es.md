# SeaMonkey, SQLite y los bloqueos de rangos de bytes

[English](SEAMONKEY_FILE_LOCKS.md) | [Español](SEAMONKEY_FILE_LOCKS-es.md)

Estado: diagnóstico a partir del código fuente y del SDK, una corrección en el generador del servidor y una sonda, 2026-11-17. La corrección está en 04.14, donde SeaMonkey carga YouTube por completo en la consola (run-0192.log, confirmado por el usuario). La sonda no se ejecutó en la consola.

## El síntoma

En 04.12, que incluye el [cambio de descriptores](SEAMONKEY_DESCRIPTORS-es.md), SeaMonkey sigue sin terminar de cargar YouTube. Los logs de las ejecuciones (`run-0185.log`, `run-0186.log`) no muestran ningún fallo: ni `EMFILE`, ni fallos de acceso, ni líneas de memoria baja. El mismo SeaMonkey 2.53.24 x64 carga YouTube por completo en un PC con Windows. En la consola, la consola de errores de SeaMonkey muestra `NS_ERROR_STORAGE_BUSY`.

`NS_ERROR_STORAGE_BUSY` es el nombre que da mozStorage al `SQLITE_BUSY` de SQLite. En Windows, SQLite toma sus bloqueos con `LockFileEx` y devuelve `SQLITE_BUSY` cada vez que esa llamada falla, sea cual sea el error (`winLock` en `os_win.c`). YouTube depende de IndexedDB, que se guarda en SQLite. La página de búsqueda de Google no, y por eso Google carga.

## La causa

1. `LockFileEx` llega al wineserver, que anota el bloqueo en su propia lista y además toma un bloqueo Unix con `fcntl(F_SETLK)` (`set_unix_lock` en `server/fd.c`).
2. En el SDK de OpenOrbis, `F_GETLK`, `F_SETLK` y `F_SETLKW` tienen los números de FreeBSD del kernel (11, 12 y 13). Pero su `struct flock` tiene la disposición de Linux (`l_type`, `l_whence` y luego `l_start`, `l_len`, `l_pid`), y sus `F_RDLCK`/`F_WRLCK` son el 0 y el 1 de Linux. Los de FreeBSD son 1 y 3, y su estructura empieza por `l_start` y `l_len`.
3. El `fcntl` del SDK pasa el puntero al `_fcntl` de libkernel sin cambios (comprobado en el desensamblado de `fcntl.lo` en `libc.a`).
4. Así, el kernel lee el tipo de bloqueo de los bytes altos del `l_len` de Wine, que valen 0 en todos los bloqueos que toma SQLite. El 0 no es un tipo de bloqueo, y FreeBSD devuelve `EINVAL`.
5. Wine interpreta `EINVAL` como un límite de desplazamiento de 32 bits y reintenta, vuelve a recibir `EINVAL` y falla la petición con `STATUS_INVALID_PARAMETER`. Todo `LockFile`/`LockFileEx` sobre un archivo normal del título fallaba con `ERROR_INVALID_PARAMETER` (87).

Los valores de errno del SDK son los de FreeBSD, así que los demás casos de Wine (`EAGAIN`, `ENOLCK`, `EOPNOTSUPP`) ya coinciden con el kernel. Solo la estructura y los tipos de bloqueo están mal.

No es un bloqueo antiguo de una ejecución anterior. Nunca se pudo tomar ningún bloqueo, y la lista de bloqueos del servidor empieza vacía con cada título.

## La corrección

- [build-wine-delete-server.py](../tools/build-wine-delete-server.py) pasa ahora las dos llamadas a `fcntl` de `set_unix_lock` por `pw_wine_fcntl_lock`. Ese generador ya reescribe `server/fd.c`.
- `pw_wine_fcntl_lock` ([pw_wine_fs.c](../platform/ps4/pw_wine_fs.c)) copia el bloqueo a la `struct flock` y a los tipos de bloqueo propios del kernel, y traduce de vuelta la respuesta a `F_GETLK`.
- Escribe los 8 primeros fallos como `PWFS lock_failed fd=… cmd=… type=… start=… len=… errno=…`.

Los conflictos entre handles los sigue decidiendo la lista de bloqueos propia del wineserver, como en cualquier Wine. Todos los invitados están en un solo proceso, y un proceso nunca entra en conflicto con sus propios bloqueos Unix. Por eso el bloqueo Unix no añade protección aquí. Ahora simplemente funciona, en lugar de hacer fallar cada petición.

Si el sistema de archivos de la consola rechazara por completo los bloqueos Unix (`EOPNOTSUPP`, `ENOLCK`), Wine dejaría de pedirlos para ese archivo y mantendría su propia lista. Ese caso también queda en el log.

## La sonda

[lockprobe.c](../fixtures/win32/lockprobe.c) toma los bloqueos de SQLite a través de dos handles de un mismo archivo:
- el `LockFile` antiguo en el desplazamiento 0;
- los bytes pendiente, reservado y compartido a 1 GiB, con los conflictos entre las dos conexiones;
- los bytes de bloqueo del `-shm` de WAL;
- la liberación de un bloqueo al cerrar su handle.

Escribe una línea por paso, con `match` o `MISMATCH` frente al resultado de Windows, en `lockprobe-result.txt`, junto al programa.

```sh
x86_64-w64-mingw32-gcc -O2 -Wall -s -static-libgcc -o lockprobe64.exe fixtures/win32/lockprobe.c
i686-w64-mingw32-gcc -O2 -Wall -s -static-libgcc -o lockprobe32.exe fixtures/win32/lockprobe.c
```

- **Windows 11 nativo:** las dos versiones dan `mismatches=0`.
- **Lo esperado en la consola antes de la corrección:** cada paso que debería funcionar falla con `error=87`.
- **Lo esperado después de la corrección:** `mismatches=0` y ninguna línea `PWFS lock_failed` en el log de la ejecución.

## Qué se probó

- El `server/fd.c` reescrito compila con la receta registrada del servidor, y `pw_wine_fs.c` con las opciones de la receta de enlace más `-Wall`, ambos sin avisos. `pw_wine_fcntl_lock` no está en el mapa de renombrado de símbolos del servidor, así que el objeto del servidor enlaza con el de `pw_wine_fs.o`.
- La sonda se compiló para 32 y 64 bits y pasa en Windows nativo.
- **No probado:** no se compiló ningún paquete y nada se ejecutó en la consola. Hasta que la sonda se ejecute allí, no está verificado que el kernel acepte el bloqueo traducido en `/data`.

## Prueba en la consola (requiere una compilación y la aprobación del usuario)

1. Antes de la corrección, en la compilación actual: copiar `lockprobe64.exe` y `lockprobe32.exe` a `/data/orbisdesk`, ejecutar los dos desde `Z:\orbisdesk` en el gestor de archivos y recoger `lockprobe-result.txt`. Esto confirma la causa.
2. Después de la corrección: volver a ejecutar los dos y esperar `mismatches=0`. Luego abrir YouTube en SeaMonkey y buscar `NS_ERROR_STORAGE_BUSY` en su consola de errores y `PWFS lock_failed` en el log.

## En la consola: 04.14 (run-0192.log)

El log tiene 7 líneas `PWFS lock_failed … cmd=12 type=1 start=1073741824 len=1 errno=9`. `type` se imprimía con el valor del SDK, así que `type=1` es un bloqueo de escritura. El bloqueo es sobre el byte pendiente de SQLite, y el errno 9 es `EBADF`.

Esas líneas no son fallos:
- El wineserver abre `O_RDONLY` el archivo de un handle de solo lectura. Un bloqueo de escritura sobre ese archivo recibe `EBADF`, y `set_unix_lock` vuelve a pedirlo como bloqueo de lectura. Es el comportamiento normal de Wine, igual que en Linux.
- Gecko abre algunas bases de datos SQLite en solo lectura, y SQLite sigue tomando su byte pendiente con un `LockFileEx` exclusivo.
- Ningún bloqueo de lectura falló: un bloqueo de lectura rechazado habría quedado como otra línea `lock_failed`, y el log se quedó en 7 de sus 8.

Así que los bloqueos traducidos funcionan en `/data`, y el kernel admite bloqueos de rangos de bytes allí. **Resultado:** con 04.14, SeaMonkey carga YouTube por completo, según confirmó el usuario. Solo lo respaldan el log de la ejecución y el informe del usuario: la sonda no se ejecutó en la consola, y no se volvió a revisar la consola de errores en busca de `NS_ERROR_STORAGE_BUSY`.

La línea de log ya no incluye ese reintento y nombra el tipo (`read`, `write`, `unlock`). La misma ejecución llegó además a `fd_high fd=1006` sin `EMFILE`, así que 958 no era un límite fijo ([descriptores](SEAMONKEY_DESCRIPTORS-es.md)).
