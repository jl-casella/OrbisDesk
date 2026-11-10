# Evidencia y bloqueos

[English](STATUS.md) | [Español](STATUS-es.md)

## Estado actual, 2026-11-10

La base del producto es **W303 / 04.02**, con el runtime integrado en `OrbisDesk.pkg` y validación de instalaciones limpias en consola registrada en el commit `208803d`. La construcción completa del producto en GitHub ya pasa. CI asigna la versión SFO del candidato por separado de la predeterminada local.

Usar el [estado actual](CURRENT_STATE-es.md) para retomar y [builds y releases](RELEASES-es.md) para el flujo verificado de cachés/precompilados, instalación y comprobaciones de candidatos. Instalación, comportamiento del escritorio/aplicaciones y publicación son aceptaciones distintas; usar el SHA, manifiestos y logs del candidato exacto.

## Evidencia histórica hasta W284

En la retoma W284, el paquete local era **OrbisDesk.pkg**, W284 / 03.83, con instalación y prueba visual pendientes. Ver [W284](HARDWARE_W284-es.md). Las entradas siguientes conservan el estado informado en cada fecha histórica.


**Entrega W283 completada:** `/data/pkg/orbisdesk-W283-a3a72e1401c2.pkg`, FTP 192.168.68.100:2121. PKG y 1.823 archivos runtime verificados por lectura (83 subidos, 1.740 ya presentes); un paquete anterior retirado tras verificar. Sin fallos de permisos. Ajustes de consola conservados. Instalación y prueba física pendientes. Evidencia: `reports/wine-hardware-w283/transfers/20261107T142853Z.json`.

Marca actual: **OrbisDesk**, W283 / 03.82. Paquete compilado y verificado; instalación y prueba física pendientes. Ver [retoma actual](CURRENT_STATE-es.md) y [cambio de nombre](REBRANDING_ORBISDESK-es.md). Las entradas siguientes son históricas.

Retoma actualizada al 2026-11-03: **W188 (02.87)** está subida y verificada; su prueba física sigue pendiente en la evidencia local. Consultar primero [CURRENT_STATE](CURRENT_STATE-es.md) y [W188](HARDWARE_W188-es.md). El contenido W112 e inferior que sigue es histórico y no define la próxima build.

Estado actualizado al 2026-11-02: consultar [CURRENT_STATE](CURRENT_STATE-es.md). W105 lista unidades/archivos y W106 abre EXE sin reiniciar, según el usuario. W107 ya abrió textos con Notepad. Prioridad elegida: soporte DOS. [W112](HARDWARE_W112-es.md) integra DOSBox Pure PE64, frontend GDI y AudioOut; compilación finalizada, compatibilidad y audio en PS4 pendientes. Corrección anterior: [W111](HARDWARE_W111-es.md), registros de entradas borradas: W110 enumera nombres con stat ENOENT, también inexistentes por FTP. El filtro BSD de inode cero ya se validó en PS4: rmdir 0, carpeta ausente y rename con espacios confirmado. El usuario también confirmó borrado completo del árbol con contenido activo; aceptación física registrada por feedback explícito, sin atribuir nuevos borrados al log. Siguiente prioridad elegida: DOS; escritorio aplazado. Después: desktop con archivos/carpetas además de *.lnk. Calibración CPU/GPU aplazada. W096 ya ejecutó tres aplicaciones gráficas juntas en PS4 y las cerró con 0; Start dejó de abrir después. W099 completa cierres y recargas, pero tras otro ciclo hay un acceso inválido en malloc nativo. W100 añade un bloqueo común al asignador del SDK, pero la prueba física también termina con CE-34878-0. W101 completó dos ciclos sin cargar MangoHud y salida final 0. W102 reactiva la capa con muestreo en el frame y completó dos ciclos con la capa cargada: seis cierres 0, Start operativo y salida final 0 (63455 ms). Evidencia en `reports/wine-hardware-w102/physical/20261102T131731Z/acceptance.json`. W103 registró tres cierres 0 y GPU variable sin pérdidas; CPU quedó fija en 16,666 % y se rechazó. [W104](HARDWARE_W104-es.md) sustituye su fuente por getrusage y retira «app» de las etiquetas CPU/GPU. Conserva el muestreo en el frame. En PS4: 90 muestras, CPU 6,917–32,801 %, GPU 0,08–9,5 %, sin errores ni pérdidas GPU y tres cierres 0. El defecto de CPU fija se resuelve en esta sesión; calibración independiente y dos ciclos completos no acreditados. El detalle de las iteraciones recientes está en [HARDWARE_G001](HARDWARE_G001-es.md) y [HARDWARE_W003_W011](HARDWARE_W003_W011-es.md). Las campañas anteriores que siguen conservan sus resultados y bloqueos históricos.

Pista de hardware: [H001](HARDWARE_H001-es.md) ejecutado en la PS4 Pro Baikal del usuario (firmware informado 12.52, GoldHEN). Pasan VideoOut, log, roundtrip en `/data`, protección R/RW, reserva bajo 4 GiB y TLS/hilos. Leer `/app0/sce_sys/param.sfo` devuelve ENOENT (2); no demuestra un fallo general de APP0. H001B, versión 01.01, usa un asset propio para esa comprobación y registra el SFO por separado como metadata opcional. H001B también pasó en la consola, incluida la lectura de APP0 (`reports/hardware-h001b/physical/20261031T051942Z/`).

[W001](HARDWARE_W001-es.md), el primer arranque de Wine en la consola (`console32-bare.exe` mediante wowprospero), está subido con su runtime: 430 archivos y 294 MB en `/data`, todos verificados por lectura de vuelta. En la consola quedó `blocked` antes de arrancar Wine: `readlink` devuelve ENOSYS (78) y `dup2` devuelve -1. Los enlaces `dosdevices` del prefijo no existen en el hardware.

Con W002–W013 ([W002](HARDWARE_W002-es.md), [W003–W013](HARDWARE_W003_W011-es.md)), **`console32-bare.exe` corre en la PS4 real mediante Wine y wowprospero.** W013 dejó un `result.txt` idéntico al de Windows (`sum=500500;thread=ok;dll=ok`, mismo SHA-256) y salió con 0.
- Evidencia: `reports/wine-hardware-w013/physical/20261031T195509Z/`.
- Corridas: dos, ambas `passed` con el mismo hash. La segunda está en `reports/wine-hardware-w013/physical/20261031T195721Z/`.
- Fue posible gracias a decisiones de plataforma documentadas para lo que una app retail no puede hacer:
  - sin enlaces simbólicos;
  - `lstat` con EPERM;
  - `dup` con EPERM;
  - `fcntl` con EINVAL.
- W013 terminaba con SIGSYS en el `_exit` de libkernel. W014 cierra la app con `sceSystemServiceLoadExec("exit")`. Su log termina limpio, sin señales ni `err:seh`, y según el usuario la app vuelve al menú sin el error CE-34878-0 (`reports/wine-hardware-w014/physical/20261031T204439Z/`, `passed`).
- **GUI en la consola** ([detalle](HARDWARE_W003_W011-es.md)): `gui-window64.exe` (PE64) abre su ventana, la pinta y lee un píxel. Su `result.txt` es idéntico al de Windows.
  - W023: dos de dos corridas. W025: con texto correcto.
  - Para eso hicieron falta tres decisiones de plataforma sobre memoria:
    - no reservar la zona `0x7ffffe000000-0x7fffffff0000`;
    - dejar que el kernel elija el heap virtual;
    - recortar `host_addr_space_limit` a `0xfc00000000`.
  - El adaptador de FreeType ahora abre los archivos mediante la tabla de montaje. Desde W025 el título se dibuja en Tahoma Bold y los botones, con Marlett.
- Pendiente:
  - entrada (control);
  - El texto ya funciona: `gui-text64.exe` pasó en W026, con la misma tinta que en el fork.
  - explorer muestra en la consola el escritorio de 1280×720 con la barra de tareas, en unos 5 s.
  - Desde W035 el menú Start se abre con el mouse USB o con los botones del control. El teclado USB también llega a Wine.
  - Para eso hizo falta:
    - `native/hw_pad.c`;
    - un `dup` real por SCM_RIGHTS;
    - que `pw_wine_poll` acepte descriptores sin eventos.
  - Funcionan el stick izquierdo, el touchpad y los botones del control (W037, confirmado por el usuario). El stick derecho no está asignado.
  - "Exit desktop" cierra el título con salida 0.
  - sockets no bloqueantes (EACCES);
  - La matriz Linux pasa con el ELF de W038 (`reports/wine-hardware-w038/regressions-25/`). Antes falló con el tope de memoria de W023, que shadPS4 no soporta; W038 lo baja a `0x7ffff0000`.

Estado más reciente: [incremento 25](INCREMENT_25-es.md). FreeType 2.14.1 está enlazado para Orbis, con Tahoma de la revisión fijada de Wine y registro explícito en el prefijo privado. El fixture de texto PE64 pasa tres de tres corridas: 1.252 píxeles de tinta tanto en la DIB como en la ventana, y verificación del cuadro presentado. Explorer muestra Start (77 píxeles de etiqueta comprobados). Se corrigió la protección de secciones finales privadas de DLL para redondear al rango de 16 KiB ya mapeado. La campaña de aceptación y las regresiones pasan; evidencia en `reports/increment25-accepted/`. No se agregaron parches al emulador. Entrada, GUI PE32 y hardware: pendientes; el oficial sigue bloqueado.

Seguimiento puntual: se empaqueta y registra también Marlett de Wine. Una corrida del fixture gráfico en el fork confirma los iconos de minimizar, maximizar y cerrar; salida 0. Captura e informe en `reports/marlett-caption/`. No se repitió la suite completa.

Estado del incremento 24: [incremento 24](INCREMENT_24-es.md). En el fork Linux, Wine presenta ventanas por `sceVideoOut` con `win32u` y un driver de usuario en proceso. Un fixture GUI de 64 bits da el mismo resultado que Windows en tres de tres corridas, y `explorer.exe /desktop` muestra el escritorio con su barra de tareas. Sin texto (no hay FreeType) ni entrada. El oficial sigue bloqueado. Hardware: pendiente.

Estado del incremento 23: [incremento 23](INCREMENT_23-es.md). En el fork Linux, console32-bare.exe corre mediante Wine con el traductor como proveedor WoW64 (`--wow64-cpu wowprospero`): `result.txt` idéntico a Windows, salida 0, tres de tres corridas y sin stubs. El oficial sigue bloqueado; console32.exe con CRT mediante Wine queda pendiente. Hardware: pendiente.

Estado del incremento 22: [incremento 22](INCREMENT_22-es.md). En el fork Linux pasan GS por hilo (`--gs-services`), los contextos de señal (`--signal-services`) y `segments`. Wine ejecuta el ntdll PE64, crea el heap y carga `wow64.dll`; termina con `0xc0000135` porque falta el proveedor de CPU WoW64. El EXE todavía no se ejecuta mediante Wine. `exceptions` falla igual en el fork y en el oficial Linux (diferencia del host). Hardware: pendiente.

Estado del incremento 21: [incremento 21](INCREMENT_21-es.md). Pasan los mappings privados de archivos y las denegaciones de protección en el fork Linux. Wine alcanza ntdll_pe64_ready, entering_windows_initialization y dispatcher_slot_ready. Se adapta el slot de syscalls a páginas de 16 KiB. El siguiente bloqueo es instalar y verificar GS mediante sysarch: salida 93 limpia, sin aserción ni timeout. El EXE todavía no se ejecuta mediante Wine. Hardware: pendiente.

Estado del incremento 20: [incremento 20](INCREMENT_20-es.md). El fork devuelve EINVAL para offsets inválidos de mmap; Wine toma el fallback y mapea el EXE PE32. Se adapta la política de imágenes reubicadas de prospero-win y se fuerza WoW64. La carga de ntdll PE64 encuentra una aserción de mprotect, reproducida por separado. La inicialización Windows y la ejecución del EXE mediante Wine siguen pendientes. Hardware: pendiente.

Estado del incremento 19: [incremento 19](INCREMENT_19-es.md). Pasan las doce pruebas del prefijo externo en el fork Linux. Wine consume ese prefijo sin lanzar wineboot, pero la carga del EXE se bloquea en una aserción de mmap con offset no alineado. No se completó la carga de ntdll PE64 ni se ejecutó el EXE mediante Wine. Se conservan las regresiones del incremento 18. Hardware: pendiente.

Estado del incremento 18: [incremento 18](INCREMENT_18-es.md). console32.exe, con el CRT de mingw, corre sin Wine en el fork Linux sobre un kernel32 y un msvcrt mínimos propios, con la misma salida que en Windows. En el oficial queda bloqueado por el emulador. Hardware: pendiente.

Estado del incremento 17: [incremento 17](INCREMENT_17-es.md). lifecycle-host.exe carga y descarga DLL desde disco sin Wine en el fork Linux y sale con 42, como en Windows. En el oficial queda bloqueado por el emulador. Hardware: pendiente.

Estado del incremento 16: [incremento 16](INCREMENT_16-es.md). console32-bare.exe corre sin Wine en el fork Linux, con el loader PE32 propio y un kernel32 mínimo; su salida es igual a la de Windows. En el oficial queda bloqueado por el emulador. Hardware: pendiente.

Estado del incremento 15: [incremento 15](INCREMENT_15-es.md). Pasan identidad de archivos y symlinks en el fork. Un prefijo externo inicializado y verificado con Wine nativo queda empaquetado; la ejecución del EXE mediante Wine en shadPS4 sigue pendiente.

Estado del incremento 14: [incremento 14](INCREMENT_14-es.md). Pasan los adaptadores de directorios PS4; se confirma y rechaza el intento de lanzar wineboot.

Estado del incremento 13: [incremento 13](INCREMENT_13-es.md). Funcionan pipes en Linux; Wine completa server_init_process. La ejecución del EXE sigue bloqueada después del handshake por imports pendientes, con GS, prefijo y WoW64 todavía por resolver.

Estado del incremento 12: [incremento 12](INCREMENT_12-es.md). SCM_RIGHTS ya se prueba con archivos y sockets en el fork Linux. El siguiente bloqueo de arranque es pipe; los resultados anteriores se conservan como historial.

Estado del incremento 11: [incremento 11](INCREMENT_11-es.md). El fork Linux verifica dup, flags por descriptor y mensajes con varios buffers. El arranque completo sigue bloqueado en la transferencia `SCM_RIGHTS`; GS y el proveedor WoW64 también siguen pendientes. La matriz siguiente conserva resultados históricos.

Este documento describe la referencia inicial. Para el trabajo posterior y las matrices ampliadas, consultar [Incremento 1](INCREMENT_01-es.md) e [Incremento 2: TEB y hostexec](INCREMENT_02-es.md) e [Incremento 3: dispatcher común](INCREMENT_03-es.md) e [Incremento 4: primer PE32](INCREMENT_04-es.md) e [Incremento 5: secciones de 4 KiB](INCREMENT_05-es.md) e [Incremento 6: DLL e IAT](INCREMENT_06-es.md) e [Incremento 7: inicialización y TLS](INCREMENT_07-es.md) e [Incremento 8: proceso y bring-up de Wine](INCREMENT_08-es.md) e [Incremento 9: memoria y archivos Wine Unix](INCREMENT_09-es.md) e [Incremento 10: enlace completo y arranque parcial](INCREMENT_10-es.md).

## Entorno

Pruebas realizadas el 29 de octubre de 2026 en Windows y Ubuntu 22.04 bajo WSL. OpenOrbis v0.5.4; Clang/LLD 14; MinGW i686. El binario oficial de shadPS4 v0.20.0 reporta el commit `529ceb32f5546b820588f194b903cc39d08015fe`. El checkout de referencia de su fuente `main` tiene otra revisión, registrada separadamente en `sources.lock.json`. No deben confundirse.

## Matriz

| Prueba | Resultado del invitado en shadPS4 oficial |
|---|---|
| `files` | Lectura, escritura, seek, cierre y borrado correctos |
| `low-memory` | Reserva en `0x20000000`, bajo 4 GiB |
| `reserve-collision` | La segunda reserva es rechazada y conserva el contenido |
| `vm-backend` | Reserva exacta, commit, colisión, RW→R→RW y liberación correctos |
| `generated-code` | Bloqueo al cambiar RW→RX, antes de ejecutar |
| `generated-rwx` | Código generado retorna 42 |
| `threads` | Bloqueado por llamada real al stub POSIX `pthread_key_delete` |
| `threads-adapter` | Dos hilos, 2000 incrementos, TLS independiente y dos destructores; borrado con ScePthread |
| `exceptions` | SIGSEGV recuperado; RIP en offset 224; retorna `0x5a5a` |
| `segments` | Bloqueado por stub de `sysarch`; outputs quedan intactos |
| `translator` |Bloqueo RW→RX|
| `translator-rwx` | Traductor upstream real ejecuta `mov eax,7; add eax,35` |

Todas las pruebas que llegan a `return 0` muestran además la limitación del cierre del emulador. La aprobación anterior corresponde al comportamiento medido por cada prueba, no a un cierre limpio ni al funcionamiento global de Wine.

## Bloqueos concretos

### FS/GS para Wine

Reproducción: `./tools/run-probes.ps1 -Cases segments`.

El import `sysarch` (`b7uXQmnfB2s`) se resuelve a CommonStub. Las operaciones AMD64_GET_FSBASE y AMD64_GET_GSBASE retornan cero sin modificar los valores de salida `UINTPTR_MAX`. El runner detecta la invocación y la clasifica como bloqueada. No se ejecuta un syscall del host para intentar eludirlo.

Esto impide validar la ruta de TEB/GS que usa el port PS5. Requiere trabajo de emulación por hilo, preservando el GS usado por Windows y la traducción de TLS de shadPS4. Una función que sólo guarde una variable con el nuevo GS no establece la semántica de acceso a memoria de las instrucciones PE64.

Estado posterior, separado por emulador (incremento 22):

- **Fork Linux**: resuelto. El TCB del invitado deja de usar la base GS (parche 0011) y `sysarch` sirve GET_FSBASE, GET_GSBASE y SET_GSBASE (parche 0012). `segments` y `--gs-services` pasan, con lecturas reales `gs:`, aislamiento entre hilos y TLS nativo preservado.
- **shadPS4 oficial**: sigue bloqueado por el stub.
- **Host Windows**: sin cambios ni validación; GS es el TEB del propio proceso.

### Cambios de protección ejecutable en Windows

Reproducción: `./tools/run-probes.ps1 -Cases generated-code,generated-rwx`.

La misma clase de asignación flexible permite ejecución si se crea con RWX. Si se crea con RW y luego se pide RX, el emulador aborta en `AddressSpace::Protect`, con el error de Windows «The parameter is incorrect». Es una reproducción independiente de Wine. No demuestra que PS4 real tenga este fallo.

RWX permite probar el DBT; no resuelve automáticamente los cambios de protección de imágenes y memoria que necesitará Wine. No se sustituyó mprotect por un éxito simulado ni se agregó una excepción para este título al emulador.

### TLS y cierre

`pthread_key_delete` no está registrado para el import de libkernel usado por OpenOrbis, aunque la API `scePthreadKeyDelete` sí está disponible. El adaptador PS4 llama a esta última y normaliza su código de error; conserva la prueba POSIX original como reproducción del problema.

El `exit(0)` del invitado llega a una aserción de `process.cpp` en el emulador. El informe conserva el código real del proceso anfitrión y lo etiqueta `guest-zero-exit-traps-in-emulator`; no lo presenta como cierre limpio.

## Estado de los hitos de la referencia inicial (histórico)

1. Diagnóstico: implementado y ejecutado; quedan bloqueos de plataforma reproducibles.
2. Wine Unix, servidor y módulos: pendiente; integración bloqueada por la frontera FS/GS.
3. PE32 completo: fixtures compilados; EXE todavía no ejecutado sobre el runtime PS4.
4. GDI, mando y audio: fixture GDI compilado; adaptadores de presentación aún pendientes.
5. Vulkan/DXVK: referencias fijadas; no construido ni probado.

Las pruebas de enteros del DBT no cubren x87/SSE, automodificación de código, llamadas Win32, carga de DLL ni WoW64. El backend inicial usa memoria flexible: faltan contabilidad y memoria directa para cargas grandes. No hay validación en hardware ni afirmaciones de rendimiento o compatibilidad con juegos.
