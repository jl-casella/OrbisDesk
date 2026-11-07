# Incremento 12: transferencia de archivos y sockets

[English](INCREMENT_12.md) | [Español](INCREMENT_12-es.md)

**Se implementó y probó SCM_RIGHTS en el fork Linux. Wine todavía no ejecuta el EXE:** el siguiente bloqueo observado es `pipe`, necesario para los canales del servidor y los hilos. GS, el prefijo y el proveedor WoW64 siguen pendientes.

## Cambio

Los sockets creados con `socketpair(AF_UNIX, SOCK_STREAM)` conservan referencias a los archivos y sockets enviados como datos auxiliares. El receptor instala descriptores propios que comparten el recurso original. Cerrar el descriptor emisor antes de recibir ya no destruye el recurso pendiente.

Los derechos se asocian a posiciones del flujo de bytes y se publican junto con los envíos efectivamente aceptados por el socket anfitrión. Las lecturas sin control descartan las referencias; las lecturas con poco espacio informan truncado y liberan las referencias restantes. MSG_PEEK conserva el mensaje y crea descriptores nuevos para cada recepción. Se mantiene el EOF y la espera sobre los sockets reales del backend; no se sustituye el transporte por respuestas preparadas para Wine.

La misma propiedad compartida permite `dup` de sockets. El modo no bloqueante se comparte; FD_CLOEXEC sigue siendo propio de cada descriptor. Los objetos de red que no son sockets, como epoll, no se duplican mediante esta ruta.

Los controles malformados y los descriptores inválidos se rechazan antes del envío. Los controles soportados son SOL_SOCKET/SCM_RIGHTS, con hasta 253 descriptores por llamada. Se rechazan explícitamente los ciclos directos e indirectos entre pares de sockets: todavía no hay recolector de ciclos de derechos pendientes. Esta limitación no equivale a soporte completo de sockets Unix de un kernel. Tampoco se amplía SCM_RIGHTS a sockets por pathname, datagramas ni P2P. Se rechazan OOB y la combinación PEEK/WAITALL en estos pares locales. Registrar dos alias del mismo socket en un mismo epoll queda pendiente.

El adaptador de Wine traduce MSG_CTRUNC del kernel al valor del SDK, que es distinto, y permite MSG_PEEK. FD_CLOEXEC al recibir se aplica mediante fcntl, como antes: no se demuestra atomicidad entre recepción y un exec concurrente. El proceso Windows múltiple sigue fuera del alcance inicial.

## Evidencia

El índice `reports/increment12/report.json` registra las ejecuciones finales, sus hashes y los bloqueos. Pasan 15 comprobaciones IPC y cuatro regresiones de plataforma. El homebrew OpenOrbis `--ipc-services` comprueba:

- Mensajes con varios buffers y lectura no bloqueante.
- Posición de archivo compartida y CLOEXEC al recibir.
- Dos descriptores en un mensaje, con cierre del emisor antes de recibir.
- Truncado parcial y ausencia de espacio para control.
- Separación entre bytes ordinarios y un mensaje con derechos.
- Descarte con read y duplicación durante MSG_PEEK.
- Transferencia de un socket que sigue funcionando tras cerrar el original.
- Dup de sockets con modo compartido y flags por descriptor.
- Rechazo de descriptor inválido sin enviar el byte del mensaje.
- Rechazo de ciclos directos e indirectos.
- Dos emisores concurrentes y correspondencia entre byte y archivo recibido.
- Reutilización de los números de descriptor después de cerrar los recibidos.

Las comprobaciones de rechazo validan errores, no capacidades implementadas. La reutilización de números de descriptor no es una medición exhaustiva de fugas del host. Las pruebas de plataforma se repiten para archivos, hilos/TLS, PE con DLL y memoria concurrente. Todo corresponde al fork Linux bajo WSL; la compatibilidad de estos cambios en Windows y PS4 real sigue pendiente.

Wine alcanza el envío del canal en proceso y luego requiere pipe. El marcador `inprocess_channel_ready` sólo indica que se envió ese canal; no significa que el handshake o `server_init_process` hayan terminado. El stub anterior de pipe devolvía cero sin crear sus extremos; ahora devuelve EOPNOTSUPP y conserva la salida. `--services` mantiene separadas la capacidad `pipe-basic` bloqueada y la verificación de su contrato de error. No hay stub de éxito que permita contar el arranque como funcional.

El intento final termina con código 0: el cliente recibe EOF del servidor y Wine llama a abort_thread(0) en wine_server_receive_fd. El informe conserva `Wine_booted: false` y `windows_execution_verified: false`. La prueba de regresión verifica el cierre antes de `server_ready` y el error del servidor; no acepta ese cero como resultado del EXE.

## Reproducción

```sh
python3 tools/build-shad-linux.py --reuse-configure --jobs 12
python3 tools/check-increment12.py
python3 tools/check-increment12.py --verify-only
```

El primer comando requiere la configuración Linux documentada en el incremento
11. Cada ejecución usa un proceso nuevo y conserva su ELF y datos exactos en runtime.tar.gz. Las cápsulas `reports/increment12/emulator` y `reports/increment12/wine-boot` conservan los binarios, fuentes adaptadas, parches y opciones de construcción. El índice no modifica las evidencias de incrementos anteriores.

La disposición del control y el flag de truncado se contrastan con [sys/socket.h de FreeBSD 9](https://raw.githubusercontent.com/freebsd/freebsd-src/releng/9.0/sys/sys/socket.h) y con el SDK OpenOrbis fijado. Esto no reemplaza la validación del ABI en PS4.

## Próximo bloqueo

Implementar pipe con lectura y escritura unidireccionales, EOF, modo no bloqueante, poll y transferencia de sus extremos, manteniendo las referencias compartidas. Probarlo con homebrew antes de repetir el handshake de Wine. Después, resolver los bloqueos que aparezcan hasta llegar a GS y WoW64.
