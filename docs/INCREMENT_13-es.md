# Incremento 13: pipes y conexión completa con wineserver

[English](INCREMENT_13.md) | [Español](INCREMENT_13-es.md)

**Wine completa server_init_process en el fork Linux y alcanza server_ready.** El EXE todavía no se ejecuta: el arranque se detiene después del handshake, antes de confirmar la carga de ntdll PE64. Se observan imports pendientes del filesystem y de creación de procesos. No se considera Wine inicializado por completar sólo la conexión con su servidor.

## Implementación

El backend Linux utiliza pipe2 del host con extremos reales de lectura y escritura. Ambos se incorporan a la tabla de descriptores del emulador; conservan la propiedad compartida añadida en los incrementos 11 y 12. Internamente usan la infraestructura de espera y registro de objetos existente, pero se distinguen como pipes: fstat devuelve FIFO e identidad del recurso, F_GETFL devuelve el modo de acceso correcto y las operaciones del extremo equivocado fallan con EBADF.

Los descriptores físicos son no bloqueantes; RunBlocking implementa las esperas del invitado. Esto permite EOF, backpressure, poll, lectura bloqueante y escrituras pequeñas atómicas usando el pipe del sistema operativo. Al duplicar o transferir un extremo mediante SCM_RIGHTS, cerrar el original conserva el recurso. El lector recibe EOF cuando desaparece la última referencia al extremo de escritura, incluidas las referencias pendientes de entrega.

La creación publica los dos descriptores sólo después de completar ambas inserciones. Si se agota la tabla, libera los recursos parciales y deja intacta la salida del llamador. lseek, pread y pwrite sobre pipes devuelven ESPIPE.

Wine llegó después al import público writev, que no estaba exportado desde libkernel. Se añadieron los imports públicos readv/writev y la E/S vectorial para pipes y sockets. Se valida el vector completo, se reúne en una operación de escritura o se distribuye una lectura, conservando resultados parciales. El límite de esta ruta es 1024 buffers y un total de INT32_MAX bytes.

## Validación

`--pipe-services` es homebrew OpenOrbis propio, separado del repositorio de shadPS4. Comprueba diez casos:

|Caso| Comportamiento comprobado |
|---|---|
|tubo-básico-fifo-eof| FIFO, identidad compartida, modos, datos, poll y EOF |
|terroristas del acceso a los tubos| Dirección, ESPIPE, tamaños cero, argumento nulo y getsockopt |
|pipas-vectores| readv/writev y rechazo de un vector inválido sin consumir datos |
|presión de retroalimentación de tuberías| EAGAIN, llenado, escritura pequeña sin envío parcial y vaciado |
|pipe-dup-last-writer| Estado compartido, CLOEXEC independiente y EOF tras el último cierre |
|pipa-scm-derecha| Transferencia de ambos extremos y cierre previo del emisor |
|depilación-desperto| Un lector espera hasta que otro hilo escribe |
|pipe-atomic-writers| Dos escritores envían 200 registros sin mezclar su contenido |
|tubo-rojo-reader| EPIPE con SIGPIPE ignorado explícitamente |
|pipe-allocation-rollback| Agotamiento de la tabla, salida intacta y recuperación |

El índice final `reports/increment13/report.json` conserva las ejecuciones, hashes y clasificación. También repite los 15 controles de IPC y cuatro regresiones de archivos, hilos/TLS, PE con DLL y memoria concurrente. El emulador oficial se contrasta por separado: su pipe devuelve cero sin escribir extremos; el diagnóstico detecta esas salidas intactas y queda bloqueado, sin usarlas. Su timeout de cierre se conserva separado del resultado del invitado.

El intento de Wine alcanza first_teb_ready, inprocess_channel_ready y server_ready. Después invoca stubs como cpuset_getaffinity, _openat, _fstat, rfork_thread, _dup2 y _execve, y termina con código 1. El informe mantiene Wine_booted y windows_execution_verified en false. Estas llamadas pendientes no se cuentan como servicios funcionales aunque CommonStub devuelva cero.

## Reproducción y evidencia

```sh
python3 tools/build-shad-linux.py --reuse-configure --jobs 12
python3 tools/check-increment13.py
python3 tools/check-increment13.py --verify-only
```

La configuración inicial es la del incremento 11. El launcher también acepta `--pipe-services` individualmente. Cada prueba usa un proceso nuevo y conserva ELF y datos en runtime.tar.gz. Las cápsulas `reports/increment13/emulator` y `reports/increment13/wine-boot` incluyen binarios, fuentes adaptadas, manifests, opciones y parches fijados. El build Windows anterior queda sin reconstruir.

## Límites y siguiente trabajo

El backend de pipes de este incremento sólo está implementado en Linux; otros hosts devuelven un error explícito. Todas las pruebas de PS4 real están pendientes. No se ha validado pipe2 como API del invitado ni se ha implementado la entrega de SIGPIPE al invitado: el host protege su propio proceso y devuelve EPIPE. La prueba de ese error instala y restaura SIG_IGN; no demuestra entrega de señales a un handler Windows o POSIX. Las limitaciones de alias en epoll y de ciclos de SCM_RIGHTS del incremento 12 siguen vigentes.

El próximo trabajo es identificar las rutas posteriores al handshake y revisar el ABI de los imports pendientes antes de añadir aliases. También falta proporcionar un prefijo completo preparado fuera de consola: el prefijo vacío actual puede provocar intentos de lanzar procesos auxiliares. La integración de módulos Unix/PE64, GS por hilo y el proveedor WoW64 con el traductor siguen pendientes antes de ejecutar console32-bare.exe y comprobar su resultado.

`reports/increment13/startup-symbols.txt` ubica los retornos de las llamadas pendientes usando el ELF exacto, la base de carga 0x400000 del log y addr2line. cpuset_getaffinity viene de sysconf; _openat de openat; _fstat de fdopendir. rfork_thread se alcanza desde spawn_process de Wine y _execve desde preloader_exec/loader_exec/exec_wineloader. Los frames del SDK no tienen línea de fuente disponible. Esto identifica qué ABI y qué ruta revisar; no prueba que el proceso solicitado sea wineboot ni aporta soporte para fork o exec.
