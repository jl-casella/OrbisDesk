# Incremento 10: enlace completo e intento real de arranque de Wine

[English](INCREMENT_10.md) | [Español](INCREMENT_10-es.md)

Se compiló y enlazó la parte Unix completa de ntdll y wineserver dentro del proceso PS4. Se ejecuta `__wine_main` en shadPS4 oficial para Linux, con rutas, NLS, memoria inicial y primer TEB reservados. **Wine todavía no completa su arranque y console32.exe no ha sido ejecutado por Wine.**

## Implementación

- 24 unidades nativas de ntdll, además de los dos harness diagnósticos, y 45 unidades del servidor. El enlace completo usa `--no-undefined` y conserva las tablas de servicios. Los símbolos definidos por wineserver se renombran para convivir con ntdll en el mismo ELF; los servicios externos no se sustituyen.
- Overlay privado sobre Wine `490f6d5dcbb2a5047345b8af88d114bbcaad69a8`. No se modificó el checkout original. El overlay se genera dos veces con hash idéntico. Los parches propios son 0002/0003 y se adaptan selectivamente 0101/0102/0110/0111 de prospero-win, con hashes y atribución.
- Adaptadores de directorio actual separados para cliente y servidor, resolución de rutas, ABI de señales, memoria de 16 KiB y `poll` sobre `sceNetEpoll`. Las rutas se resuelven antes de llamar al filesystem real; la operación `chdir` del emulador no se usa como garantía de cambio de ruta.
- El SDK conserva su libc original. Una biblioteca derivada omite sus miembros fallback indicados en los informes para enlazar las importaciones de kernel. Que una importación enlace no demuestra que el emulador la implemente.
- Se prepararon DLL PE64 reales ntdll, wow64, wow64win y apisetschema desde la misma revisión Wine, además de las DLL PE32 y NLS ya preservadas. Esto no integra todavía el backend de CPU de WoW64 con nuestro traductor.
- Lanzadores para Windows y Linux con proceso nuevo, límite de tiempo, ELF copiado por ejecución, hashes e informes. Se corrigió el paso de argumentos: esta revisión de shadPS4 requiere suministrar también `argv[0]` tras `--`.

## Resultado observado

El intento final está en [informe de arranque](../reports/linux-wine-runs/20261030T080525487901Z/report.json), con logs y `runtime.tar.gz` que conserva el ELF y los archivos montados.

Se alcanzaron estos puntos, después de realizar cada operación:

1. Entrada en `__wine_main`.
2. Inicialización de rutas y memoria virtual.
3. Inicialización del entorno y lectura de NLS.
4. Reserva del primer TEB. Esto aún no instala GS.
5. Creación de `dosdevices`, `drive_c` y directorios internos del servidor.

No se alcanzó `server_ready`. Durante la inicialización se invocan stubs de `fcntl`, `_fstatfs` y `dup`, seguidos de una violación de acceso. La dirección del fallo se resuelve a `pwserver_release_object`; una llamada previa a `dup` en `pwserver_dup_fd_object` recibió cero sin un descriptor duplicado válido. No se atribuye todo el fallo exclusivamente a esa llamada: el servidor ya ha usado otros resultados de stubs.

El ejecutable incluye una reproducción independiente `--services` que comprueba los efectos de las operaciones, no sólo sus retornos. Su [informe final](../reports/linux-wine-runs/20261030T080542573923Z/report.json) registra:

| Servicio | Resultado en shadPS4 oficial Linux |
|---|---|
| Archivo temporal: escritura y seek | Validado |
|Socketpair, apagado y poll/EOF mediante sceNetEpoll| Validado |
| dup con offset compartido | Bloqueado: retorna 0 sin duplicar |
| fcntl SETFD/GETFD con FD_CLOEXEC | Bloqueado: el bit no se conserva |
| fstatfs con salida escrita | Bloqueado: retorna 0 sin cambiar el buffer |
| Consulta de base GS | Bloqueado: retorna 0 sin cambiar el sentinel |

El diagnóstico termina con código invitado 92, sin violación de acceso. El cierre del emulador oficial sigue detenido hasta el límite del runner; se registra por separado del resultado del invitado. Ningún timeout se cuenta como arranque correcto.

## Por qué se usa también Linux

En Windows, KUSER_SHARED_DATA ocupa `0x7ffe0000`, dirección que necesita Wine. El intento [Windows](../reports/wine-runs/20261030T072446572Z/report.json) se bloquea en esa reserva. No se cambió la dirección requerida por Windows para aparentar compatibilidad. En WSL, shadPS4 oficial sí reserva ese rango.

Se fija el release Linux en `linux-emulator.lock.json`. Usa glibc privada extraída según `linux-runtime.lock.json`, sin reemplazar la del sistema, y Vulkan por software con lavapipe. Esto permite probar arranque; no mide rendimiento gráfico de PS4 ni valida el backend de presentación PS4. No se modificó el fork de shadPS4 durante este incremento.

<a id="reproducir"></a>


## Reproducción

Con el SDK, fuente y configuración Unix ya preparados, desde WSL:

```sh
python3 tools/build-wine-ps4.py --boot --server
python3 tools/build-wine-ps4.py --boot --all-unix
python3 tools/stage-wine-pe64.py
python3 tools/link-wine-boot.py
python3 tools/run-linux-wine.py --services --timeout 12
python3 tools/run-linux-wine.py --timeout 12
```

Los módulos PE64 deben estar previamente compilados en `.deps/wine/runtime/build`. Los runners requieren los binarios Linux y glibc indicados arriba; los archivos lock identifican las descargas, no son instaladores automáticos.

No ejecutar a la vez preparadores/builds que compartan el overlay. El build diagnóstico anterior (`tools/build.py --with-wine-platform`) sigue separado del ELF de arranque `build/wine-boot/eboot.bin`.

La [cápsula de compilación](../reports/increment10/wine-boot/evidence.json) conserva fuentes propias, overlays, parches, configuración, objetos completos, biblioteca derivada, comandos, versiones y hashes. Las ejecuciones conservan por separado su ELF y distribución real. Los algoritmos de rutas también pasan ASan, UBSan y detección de fugas en host; esto no valida el ABI de PS4.

## Trabajo imprescindible para ejecutar el EXE por Wine

La [regresión de los 58 diagnósticos anteriores](../reports/increment10-regression/report.json) mantiene 51 aprobados y 7 bloqueados, sin fallos ni timeouts. La [comparación](../reports/increment10-regression/comparison.json) verifica que el ELF diagnóstico es idéntico al del incremento 9 y conserva todos los resultados. Esto se refiere al ELF diagnóstico anterior, separado del nuevo bootstrap Wine.

1. Implementar y validar en el fork las operaciones de descriptores requeridas: duplicación con offset compartido, flags, bloqueo y consultas de filesystem. Usar la reproducción homebrew incluida y probar regresiones de filesystem.
2. Completar el canal cliente/servidor, incluidos sendmsg/recvmsg y transferencia de descriptores. Todavía no está validado SCM_RIGHTS.
3. Implementar semántica GS por hilo y validar los accesos de código PE64; devolver una variable en sysarch no basta. El adaptador de Wine rechaza una instalación de GS que no pueda verificar. Faltan validaciones de FP, flags y traps del contexto de excepciones.
4. Completar carga/inicialización PE64 y prefijo, conectar realmente WoW64 al traductor x86 y verificar salida, archivo e hilo de console32.exe.

Cada requisito sigue pendiente hasta pasar pruebas reales. Todos los resultados son de emulador; hardware PS4 continúa pendiente.
