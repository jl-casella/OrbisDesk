# Incremento 11: descriptores e IPC de Wine

[English](INCREMENT_11.md) | [Español](INCREMENT_11-es.md)

**Wine todavía no ejecuta el EXE.** Su ntdll Unix completo y el servidor en proceso alcanzan la preparación de rutas, memoria, entorno y primer TEB. La conexión al servidor se detiene ahora con un error explícito: falta transferir descriptores mediante `SCM_RIGHTS`. No se sustituye esa operación por éxito.

## Implementación

El fork Linux de shadPS4 incorpora dos parches generales adicionales sobre los tres anteriores, fijados en `fork.lock.json` y reproducibles con `tests/fork-patches.ps1`:

- `dup` comparte la descripción de archivo y su posición. Cerrar un descriptor conserva el archivo mientras otro descriptor lo use.
- `F_GETFD`/`F_SETFD` conservan `FD_CLOEXEC` por descriptor; duplicar lo limpia. `F_GETFL`/`F_SETFL` permiten las operaciones implementadas, incluida la selección de sockets no bloqueantes. Las variantes pendientes se rechazan.
- Se exportan `sendmsg` y `recvmsg` desde libkernel; se corrige el retorno firmado de 64 bits. Funcionan varios buffers sin datos auxiliares.
- `sendmsg` rechaza datos auxiliares con `EOPNOTSUPP` antes de enviar el mensaje. Esta protección evita perder silenciosamente un descriptor; **no implementa `SCM_RIGHTS`**. `fstatfs` también devuelve un error explícito.

El adaptador PS4 de Wine convierte la cabecera de mensaje de 56 bytes del SDK a la de 48 bytes usada por el kernel emulado. Incluye conversión de cabeceras de control y manejo de errores, cuya transferencia real sigue pendiente de prueba. La semántica de este ABI en hardware continúa pendiente.

El bootstrap comprueba el fallo de conexión antes de seguir con `recvmsg`. Los diagnósticos `--services`, `--ipc-services` y `--gs-services` ejecutan las operaciones reales sin requerir que Wine arranque.

## Validación y límites

La suite de servicios verifica escritura y seek, posición compartida tras dup, flags independientes, supervivencia al cierre, CLOEXEC y EOF con poll. La suite IPC verifica mensajes con dos buffers, lectura no bloqueante y rechazo de datos auxiliares sin enviar parcialmente el mensaje. La transferencia de archivos permanece bloqueada. GS se detiene al detectar el stub de `sysarch`, antes de probar accesos `gs:`; no cuenta como soporte de GS.

El nuevo ejecutable de referencia `console32-bare.exe` sólo importa kernel32 y se enlaza sin CRT. En Windows real calcula `500500`, usa un hilo, resuelve una función de una DLL y escribe `sum=500500;thread=ok;dll=ok`. El informe está en `reports/increment11-windows-reference`. **Esa comprobación no es ejecución bajo Wine ni bajo PS4.**

El build Linux usa Clang 19, libc++ y su biblioteca experimental para `std::jthread`. Se detectó una regresión al terminar hilos: LLVM libunwind interpretaba el registro de frames con un ABI diferente del GNU esperado por el emulador. Las pruebas aisladas pasaron al anteponer libgcc_s. El toolchain fija ese orden de enlace; las regresiones finales y sus hashes se registran en `reports/increment11/report.json`. No requiere `LD_PRELOAD` en las ejecuciones finales. El binario Windows anterior no se reconstruye en este incremento. Cuatro archivos de libpng usan finales de línea LF para compilar en WSL; el registro de normalización verifica que coinciden con los blobs fijados en Git. El estado del submódulo puede marcarlos como modificados por esa conversión.

El intento de preparar un prefijo con Wine nativo Linux continúa incompleto: wineboot espera durante instalación de componentes. Sus archivos parciales no se consideran un prefijo PS4 listo. La caché opcional de fuentes se verificó, pero no se activó en el build final.

## Reproducción

Desde Ubuntu 22.04 de WSL, en la raíz del workspace:

```sh
python3 tools/build-shad-linux.py --jobs 12
python3 tools/run-linux-wine.py --fork --baseline --case threads-adapter --timeout 15
python3 tools/run-linux-wine.py --fork --baseline --case vm-stress --timeout 20
python3 tools/run-linux-wine.py --fork --services --timeout 15
python3 tools/run-linux-wine.py --fork --ipc-services --timeout 15
python3 tools/run-linux-wine.py --fork --gs-services --timeout 15
python3 tools/run-linux-wine.py --fork --exe out/console32-bare.exe --timeout 20
```

Cada ejecución conserva ELF, entradas y logs en su archivo `runtime.tar.gz`. `reports/increment11/wine-boot` conserva el build completo y fuentes adaptadas; su verificador comprueba hashes y coincidencia con los ELF ejecutados. El índice de este incremento distingue las pruebas oficiales y del fork. Todo sigue pendiente de hardware PS4.

## Siguiente trabajo necesario para ejecutar el EXE con Wine

1. Implementar transferencia de descriptores en sockets locales con propiedad, cierre y posición compartida correctos; ampliar la reproducción para truncado, varios descriptores y concurrencia. Repetir el handshake real de wineserver.
2. Resolver GS por hilo con accesos de memoria reales y comprobar que no rompe TLS nativo. Un getter/setter que sólo guarda un número no basta.
3. Completar el prefijo fuera de consola, cargar ntdll PE64 y las DLL Unix necesarias, e integrar el proveedor WoW64 con el traductor de prospero-win.
4. Ejecutar el fixture y comprobar archivo de resultado, hilo, DLL y código de salida. Sólo entonces contar el primer EXE ejecutado mediante Wine.

Son requisitos identificados; el arranque puede revelar otros. Los cambios del emulador no implican que deban modificarse los servicios de una PS4 real.
