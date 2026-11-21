# Sondas de familias de procesos para launchers de base fija

[English](PROCESS_FAMILY_PROBES.md) | [Español](PROCESS_FAMILY_PROBES-es.md)

Estas sondas reproducen el contrato de procesos que necesitan launchers cuyo hijo debe ejecutarse mientras el padre sigue vivo. No implementan un backend de procesos separados ni cambian el lanzador actual de huéspedes. La primera investigación usó dev `a17f5eb` y el ELF local W303 sin modificar.

**Estado actual, 2026-11-11:** P007 ya verifica un auxiliar freestanding con base fija y transferencia bidireccional de descriptores en hardware físico 12.50. El siguiente requisito es el arranque SELF OpenOrbis de P009/P010, no repetir las pistas mmap de P005. El producto principal sigue en W303. Ver el plan actualizado al final de esta guía.

**Actualización, 2026-11-12:** las fases B–D (un proceso separado que ejecuta Wine como cliente del wineserver del título, con ventanas, entrada y handles reales de `CreateProcess`) están en [Procesos de Windows separados](POP_SEPARATE_PROCESS-es.md).

## Reproducción Win32 propia

[process_family.c](../fixtures/win32/process_family.c) produce dos ejecutables PE32 con base preferida `0x400000`, `IMAGE_FILE_RELOCS_STRIPPED` y sin directorio de relocaciones. El builder verifica esas propiedades. Sólo importan kernel32 y no usan arranque CRT.

El padre crea una memoria compartida con nombre nuevo, publica PID y base de imagen, y crea al hijo suspendido. Después de reanudarlo, incrementa un heartbeat mientras espera un código de salida verificado. El hijo abre el mapping, comprueba que su PID sea distinto, abre el handle de proceso del padre y exige que éste siga vivo e incremente el heartbeat. Ambos registran sus bases reales. La evidencia exitosa incluye `family_verified`, `child_verified`, salida 0 del padre y 42 del hijo.

Esto prueba creación real de procesos, creación suspendida/reanudación, herencia de entorno, memoria con nombre, avance concurrente del padre, identidad de procesos y espera/salida. Es un contrato sintético inspirado en el [hallazgo del launcher de base fija](investigacion-wow64-en-explorer-es.md#363-prince-of-persia-dos-exe-con-base-fija), no una recreación del protocolo desconocido `PrinceSM`. También se construye un padre relocalizable en `0x24000000`, `family-control.exe`, para distinguir conflictos de base fija de otras limitaciones de procesos.

## Inventario de exports nativos

[process_capabilities.c](../native/process_capabilities.c) lista módulos cargados y busca en sus exports varios nombres relacionados con procesos. Escribe `/data/process-capabilities.jsonl` y no invoca ninguna función descubierta. No intenta `fork`, `rfork`, inyección de payloads, cambios de privilegios ni reemplazo de aplicación.

El descubrimiento es deliberadamente limitado: ausencia en la lista de módulos cargados no demuestra ausencia en el kernel PS4, bibliotecas no cargadas o la tabla HLE separada del emulador. Encontrar un símbolo tampoco demostraría que funcione. `discovery_only=true` y `native_child_started=false` no deben reportarse como creación nativa exitosa.

## Compilar y ejecutar

Usar el entorno WSL/OpenOrbis y MinGW ya configurado, descrito en [AGENTS](../AGENTS-es.md). Las salidas están aisladas en `build/process-probes` y `out/process-probes`; no se reconstruye el runtime del producto.

```sh
python3 tools/build-process-probes.py
python3 tools/run-process-probes.py --target host-wine --timeout 120
python3 tools/run-process-probes.py --target shad-capabilities --timeout 15
python3 tools/run-process-probes.py --target shad-family --build W303 --timeout 45
```

`host-wine` usa la build Linux de Wine fijada, un prefijo privado nuevo y su propio wineserver. La inicialización puede superar 45 segundos; la referencia exitosa registrada tardó unos 86 segundos, incluyendo inicialización. No es un benchmark de rendimiento. Con Python nativo de Windows se puede ejecutar `--target windows`; políticas/comportamiento de carga locales pueden rechazar independientemente una imagen no relocalizable.

`shad-family` verifica eboot del producto y binario del fork con sus manifiestos, copia el runtime existente a `/var/tmp/orbisdesk-process-*`, agrega los fixtures y selecciona al padre por `orbisdesk/launch.txt` de esa copia. También fija un `XDG_DATA_HOME` privado y enlaza el directorio de datos predeterminado del emulador a la misma copia, para que un reinicio que pierda los montajes CLI no salga hacia el perfil habitual. La preparación es separada de la ejecución acotada del emulador y puede tardar varios minutos en un workspace montado desde Windows. Nunca cambia datos de consola ni runtime fuente. Los procesos Linux lanzados tienen volcados de memoria deshabilitados.

Para repetir de forma acotada con los mismos datos privados:

```sh
python3 tools/run-process-probes.py --target shad-family --build W303 --timeout 45 \
  --resume-from reports/process-probes/REPLACE_WITH_RUN/report.json
```

La reanudación verifica identidades de fixtures, ELF del producto, emulador y ubicación privada. Archiva registros anteriores de fixtures antes de repetir. Una sonda real fallida de primer arranque puede dejar su marcador de una vez por build y afectar el arranque posterior; hay que distinguir esas condiciones. No inventar un marcador native32 exitoso. No se pueden reanudar temporales ausentes. Se usa `/var/tmp` porque este WSL puede limpiar `/tmp` al finalizar su sesión.

Agregar `--control` para correr el padre relocalizable. Cada invocación crea informes separados con hashes, comando, manifiestos de emulador/producto cuando corresponde, timeout/salida y JSONL padre/hijo. `status`, `family_contract_passed` y descubrimiento de capacidades son resultados separados. El inventario completo sale correctamente como diagnóstico mientras su estado de familia sigue bloqueado. Una referencia host exitosa nunca es aceptación nativa PS4. Pasar sólo el contrato de procesos tampoco demuestra que arranque un juego.

## Observaciones iniciales

La evidencia está en `reports/process-probes/` (local, ignorado):

| Ejecución | Observación |
| --- | --- |
| `20261111T024546910018Z` | El prefijo Wine host nuevo superó 45 segundos antes del fixture; se conserva como timeout. |
| `20261111T025026571221Z` | Referencia Wine host aprobada: padre PID 32, hijo PID 320, ambos en `0x400000`; memoria compartida, avance del padre y salidas esperadas verificados. |
| `20261111T024546910069Z` | Inventario de exports en el fork completado, un módulo cargado y sin coincidencias de los nombres buscados. No se inició un proceso nativo. |
| `20261111T024619495646Z` | W303 nuevo en el fork agotó el tiempo antes del fixture, en su sonda native32 tras mapear `0x30000000`. Sin registros padre/hijo. |
| `20261111T025247883640Z` | Mismo timeout inicial native32 con datos privados persistentes, acotado a 15 segundos. |
| `20261111T025535571801Z` | Reutilizar el marcador de ese intento real permitió llegar al padre fijo en `0x400000`. Su log termina en `create_child_attempt`; el producto llama `switch_program`/LoadExec para el hijo. El relanzamiento del emulador pierde montajes CLI y vuelve a sus datos locales habituales; después aborta con mensaje de stack smashing (salida 127). Ese intento anterior no mantuvo aislamiento tras reiniciar: tocó archivos de arranque del perfil local predeterminado, no datos PS4 ni runtime fuente del producto. |
| `20261111T025859128715Z` | Repetición con perfil XDG privado conservó aislamiento, pero agotó tiempo antes del launcher; sin registros padre/hijo y con log del perfil nuevo vacío. No invalida el comportamiento LoadExec observado antes. |
| `windows-20261111T0247354026543Z` y `windows-control-20261111T0249160656069Z` | Windows nativo rechazó la imagen fija con error 623. El padre relocalizable arrancó y registró error 623 al crear su hijo fijo; esto no invalida el contrato aprobado por separado en Wine. |

En el fork, `sceSystemServiceLaunchApp` es un stub que devuelve éxito, `sceSystemServiceLoadExec` reinicia el título y el dispatcher de syscalls crudas no implementa spawn. Además `Emulator::Restart` omite montajes personalizados al reconstruir su línea de comandos. Ninguna es una ruta validada de segundo proceso. No convertir un resultado de stub ni dos instancias del emulador lanzadas a mano en soporte multiproceso PS4.

Siguiente paso: conservar por separado cualquier resultado adicional de bootstrap y después demostrar un loader/transporte real de procesos auxiliares PS4 antes de conectar una opción por programa en Wine. Hasta demostrar ese requisito, la ruta original de huéspedes compartidos queda igual y el launcher de base fija sigue sin resolver en PS4.

## P001: comprobación de requisitos instalable en consola física

Compilar con `python3 tools/build-process-hardware-probe.py`. El paquete independiente es `out/process-hardware-p001/OrbisDesk-Process-Check-P001.pkg`, título **OrbisDesk Process Check P001**, ID `ORBP00001`, versión `01.00`. No reemplaza OrbisDesk (`ORBW00002`) ni los títulos de sondas anteriores. El builder valida el PKG y registra hashes de ejecutable/paquete/fuentes en `out/process-hardware-p001/manifest.json`.

P001 usa el sink de presentación por CPU y el adaptador ABI de mensajes Orbis existentes. Comprueba un archivo temporal mapeado en dos direcciones distintas con `MAP_SHARED`, visibilidad bidireccional entre esos mappings y un descriptor real transferido por socket Unix local con `SCM_RIGHTS`. El receptor debe poder usar el descriptor recibido. También inventaría exports de módulos cargados. Los mensajes son no bloqueantes y no se invoca ningún export de creación de procesos. No incorpora cambios de privilegios, ejecución Wine, relanzamiento del título, listener externo ni payload de kernel.

La pantalla dice expresamente **SECOND PROCESS: NOT TESTED** y marca los resultados IPC como **LOCAL**. Son requisitos útiles, no prueba de mappings/IPC entre procesos ni de creación de procesos. Cada ejecución crea `/data/orbisdesk/process-p001/run-NNNN/report.jsonl` y elimina sólo su archivo temporal propio. La pantalla queda abierta para una foto; después cerrar la app desde el menú PS4.

La validación en el fork `reports/process-hardware-p001/20261111T031337036221Z/report.json` completó en unos 1,9 segundos: mappings coherentes, envío/recepción del descriptor y E/S del receptor aprobados, inventario de exports completado. No se encontraron los exports de creación buscados en los módulos cargados. El ejecutor detuvo el diagnóstico persistente después de completarse; salida -9 significa esa detención deliberada, no un crash de la app. La prueba en consola física sigue pendiente.

El 2026-11-11 la consola estaba apagada. El paquete está listo; **no se intentó transferencia FTP**. Su entrega preparada está en `out/process-hardware-p001/ftp-handoff.json`. Cuando el usuario confirme consola/FTP encendidos y dirección actual, subir únicamente este diagnóstico a `/data/pkg/OrbisDesk-Process-Check-P001.pkg`. No borrar ni reemplazar el `OrbisDesk.pkg` principal. El usuario instala/abre el diagnóstico, envía foto del resultado y lo cierra; después descargar su JSONL nuevo por FTP.

### Resultado físico P001, 2026-11-11

La transferencia posterior a `192.168.68.106:2121` completó y la descarga FTP de verificación coincidió con SHA-256 del paquete `694e2182c953109dfbb29b791375781d8f68e1561f59b6c29e630779b64a402a`. El usuario confirmó la prueba; la evidencia descargada es `reports/process-hardware-p001/physical/20261111T124733314388Z/run-0001/report.jsonl`, SHA-256 `6e8d2e4db40c281457eabac42611eae908a4445218fbeac54777c0423d8eb73b`.

- Aprobaron ambos mappings compartidos, coherencia y liberación. Sigue siendo una prueba de backing compartido dentro de un proceso, no aceptación entre procesos.
- Aprobaron creación de socketpair y envío del descriptor. La recepción devolvió -1 con errno 45 y el diagnóstico completó con un requisito fallido. No marcar P001 completo como aprobado. El informe no identifica si el fallo vino del kernel o de la validación del adaptador.
- El inventario encontró `execve` en `libkernel.sprx` (handle 8193) y **`posix_spawn` en `libSceLibcInternal.sprx` (handle 2)**. No se llamó a ninguna. Es un hallazgo físico ausente en el inventario del fork y un candidato concreto para investigar; un nombre exportado no prueba creación de procesos utilizable.

Para la siguiente sonda de descriptores, comparar P001 con la ruta `scm_duplicate` ya usada en hardware de `platform/ps4/pw_wine_fs.c`: usa flags 0 y buffer de recepción doble de `CMSG_SPACE(sizeof(int))`, mientras P001 usa `MSG_DONTWAIT` y buffer simple. Registrar la etapa de fallo adaptador/kernel y comparar ambas variables por separado antes de atribuir una limitación general a la transferencia de descriptores. Por separado, establecer ABI y comportamiento del `posix_spawn` del sistema antes de un intento acotado padre/hijo nativo. Todavía no se verificó un segundo proceso físico.

## P002: variantes de recepción e intento de hijo nativo

Compilar con `python3 tools/build-process-hardware-probe.py --build P002`. P002 usa el mismo título de diagnóstico `ORBP00001`, versión `01.01`, y empaqueta `/app0/process-child.bin` junto al padre. Actualiza P001, no OrbisDesk. Paquete y manifiestos quedan en `out/process-hardware-p002/`.

Cinco socketpairs nuevos aíslan el fallo de recepción. Los casos 0–3 conservan los flags de envío de P001; sus flags/capacidades de recepción son `(0,24)`, `(0,256)`, `(MSG_DONTWAIT,24)` y `(MSG_DONTWAIT,256)` con este SDK. El caso 4 usa flags 0 en envío/recepción y capacidad 256 como control semejante a producción. El builder instrumenta una copia privada generada de `pw_wine_net.c` para registrar etapa de fallo, flags del mensaje devuelto y longitud del control. El adaptador de producción queda igual. Un worker IPC mantiene la pantalla activa; una llamada pendiente a los 15 segundos se reporta sin cancelar un hilo dentro de una syscall ni avanzar al spawn.

La revisión ABI comparó `spawn.h` de OpenOrbis con la [cabecera oficial de FreeBSD 9.1](https://github.com/freebsd/freebsd-src/blob/releng/9.1/include/spawn.h) y su [implementación](https://github.com/freebsd/freebsd-src/blob/releng/9.1/lib/libc/gen/posix_spawn.c). Coincide la interfaz de seis argumentos, pero difieren los objetos auxiliares: FreeBSD usa tipos puntero opacos y el SDK declara estructuras inline. P002 resuelve el export del sistema y pasa **NULL en acciones de archivo y atributos**, más un entorno vacío explícito. Eso evita esos layouts; no demuestra comportamiento idéntico de la implementación Sony. Registra por separado retorno y errno. No intenta syscalls crudas fork/rfork ni cambios de privilegios.

La prueba nativa exige exports `posix_spawn` y `waitpid`. Un worker separado llama primero a spawn con imagen inexistente como control negativo y después pide el hijo empaquetado. El padre publica estado compartido respaldado por archivo con su PID y avanza un heartbeat atómico. El hijo registra PID/PPID reales, mapea ese estado, rechaza PID padre/hijo iguales y exige que el padre siga avanzando. Después termina con código 42. El padre compara el PID devuelto con el estado compartido y exige recoger salida 42 antes de mostrar **NATIVE CHILD: PASS**.

El hijo espera avance durante unos tres segundos como máximo después de entrar a su sonda. El padre consulta salida durante unos cinco segundos; su UI espera unos 15 segundos como máximo al worker completo. Una API spawn trabada queda como pendiente: no se cancela el worker por la fuerza y no se puede garantizar que la llamada respete un deadline de espacio de usuario. Cerrar un diagnóstico pendiente desde el menú PS4. Fallos de arranque o salida temprana del hijo siguen siendo fallos aunque la API haya devuelto éxito.

Ambos procesos también piden un mapping anónimo RW con dirección `0x400000` como **sugerencia**, sin MAP_FIXED. Escriben marcas diferentes. Sólo si ambos mappings caen realmente ahí se comprueba aislamiento de esa dirección; en otro caso la subprueba es inconclusa. No reemplaza la prueba aparte de EXE PE32 fijos ni sobrescribe mappings existentes.

Los logs quedan en `/data/orbisdesk/process-p002/run-NNNN/report.jsonl`, con `child.jsonl` y `state.bin` si la rama nativa llega a crearlos. El hijo no abre servicios gráficos/audio. Wine, los juegos y el runtime OrbisDesk quedan intactos. Una opción posterior por proceso todavía necesita bootstrap, semántica de wineserver común e integración de gráficos/entrada/audio; pasar una sonda nativa no haría compatible PoP.

Ejecutar `python3 tools/run-process-hardware-probe.py --build P002` para la comprobación corta del fork. El fork actual permite validar casos IPC y la rama de exports ausentes, no la llamada spawn del sistema real. El ejecutor detiene el panel persistente tras `panel_ready` y registra esa detención separada del fin del diagnóstico. Los resultados físicos deben venir de los logs nuevos de la consola.

El paquete final pasó la comprobación del fork `reports/process-hardware-p002/20261111T130258266381Z/report.json`: completaron los cinco casos IPC locales y se omitió el arranque nativo por exports ausentes. El 2026-11-11 se subió a `192.168.68.106:2121` como `/data/pkg/OrbisDesk-Process-Check-P002.pkg`; la descarga FTP completa coincidió con SHA-256 `a70d9e6cc5179df6d50461a8d1335bddb38dc14c927f952fe428f2f6fa46c2e9`. Se retiró el P001 anterior únicamente de esa carpeta remota de paquetes después de verificar su hash; su evidencia local se conserva. La ejecución física P002 queda pendiente del feedback del usuario.

### P002 física: causa IPC aislada y cierre al llamar a spawn

La prueba posterior produjo `reports/process-hardware-p002/physical/20261111T130746161012Z/run-0001/report.jsonl`, SHA-256 `70e6594719c29ecccc251bbcb7cf35723bce645cb8417d18cbdd53fd50013882`. Los casos 0, 1 y 4 aprobaron recepción y E/S del receptor. Los casos 2 y 3 fallaron en **validación de flags del adaptador**, no en `kernel_recvmsg`: ambos devolvieron flags `128` (`0x80`) y longitud de control 24 antes de que el adaptador generase errno 45. El tamaño del buffer no explica este fallo. La consola reflejó el bit de operación `MSG_DONTWAIT` solicitado en los flags de salida.

El adaptador de producción ahora excluye ese bit reflejado de la validación de eventos **sólo si se pidió recepción no bloqueante**. Los bits no solicitados o desconocidos siguen fallando. `python3 tools/test-wine-recvmsg-flags.py` ejecuta una regresión host enfocada contra código de producción con respuestas sintéticas de kernel: el comportamiento anterior reconstruido falla en el primer caso no bloqueante; el arreglo lo acepta, conserva flags conocidos de truncamiento y sigue rechazando flags inesperados/desborde de control y preservando EAGAIN. Es evidencia unitaria, no aceptación física del código cambiado.

La rama nativa encontró ambos exports y creó su worker, pero el último registro de spawn es `negative_spawn_enter`. No hay retorno, petición del hijo real, log del hijo ni panel completado. El usuario confirmó IPC 2/3 rojos seguidos por **cierre de la app**. No se capturó señal exacta ni dirección de fallo. No describirlo como error devuelto por spawn, creación exitosa ni timeout demostrado. No se pudo recuperar `state.bin` por FTP; eso no demuestra que nunca se creara. Se postergan más llamadas directas hasta inspeccionar la función.

## P003: validar el arreglo de flags e inspeccionar sin llamar a spawn

Compilar con `python3 tools/build-process-hardware-probe.py --build P003`; versión `01.02`, mismo título de diagnóstico. Los cinco casos IPC usan el adaptador de producción corregido. P003 **no llama a `posix_spawn`**, no empaqueta el helper hijo, no hace fork/rfork crudo ni cambia privilegios. Muestra **SPAWN: NOT CALLED** por separado del resultado de guardar código.

Si se encuentra el export `posix_spawn`, consulta los segmentos de ese módulo y comprueba que su dirección esté dentro de un segmento legible. Escribe hasta 512 bytes, limitados por el final del segmento, en `posix-spawn-HANDLE.bin`, con metadatos de dirección/offset en `report.jsonl`. No cambia permisos de memoria; si falta información, la captura queda como no disponible. Lee una porción pequeña de una función cargada, no el módulo de firmware completo. Las capturas son evidencia local de investigación ignorada por Git y no deben comitearse ni distribuirse como fuentes del proyecto.

Los logs quedan en `/data/orbisdesk/process-p003/run-NNNN/`. La siguiente revisión debe desensamblar esa entrada y establecer por qué terminó la llamada P002 antes de otro intento de creación nativa. Aprobar los cinco casos IPC validaría el arreglo localmente en PS4, no IPC entre procesos, integración Wine ni compatibilidad de PoP.

P003 completó la comprobación del fork `reports/process-hardware-p003/20261111T131656645434Z/report.json`. El paquete subido a `.106:2121` el 2026-11-11 se verificó por descarga completa, SHA-256 `6b5eb31878d8dbb01271310f02f144269c6e7b49550a0561cb6bd5c1a3555cc7`. Se retiró el paquete remoto P002 después de comprobar su hash archivado. La validación física P003 queda pendiente; este cambio en el fuente del adaptador no reconstruyó ni reemplazó el paquete principal OrbisDesk.

### P003 física: arreglo IPC local validado

Evidencia: `reports/process-hardware-p003/physical/20261111T132421573148Z/`. Los cinco casos aprobaron recepción y E/S del descriptor, incluidos los dos no bloqueantes que fallaban. SHA-256 del informe: `62bdef6e72cffacc15c5cb685341fd319a1d3220f56451c3f522fe4c601a35c4`. Esto valida el arreglo del adaptador para estas transferencias locales PS4; IPC entre procesos sigue sin probarse.

Se guardaron 512 bytes de la entrada del módulo 2, SHA-256 `e9c7fe177c06966340f3283eb2905f1f2dbaeb7e8e7043efe7fcab00581ef452`. El desensamblado y análisis quedan con la evidencia ignorada. El wrapper pasa seis argumentos a un helper local. Éste distingue retorno -1/cero/positivo de una llamada sin resolver; el camino de retorno cero termina llamando a otro destino con argumento 127, seguido de UD2. Coincide con la forma de spawn mediante vfork/exec de FreeBSD. No identifica los destinos importados reales ni demuestra qué camino ejecutó P002. La causa del cierre sigue sin probarse y esa inferencia sola no justifica otra llamada a spawn.

## P004: inspeccionar destinos sin ejecutarlos

La versión `01.03` actualiza el mismo diagnóstico. Compilar usando la carpeta de la corrida P003:

```sh
python3 tools/build-process-hardware-probe.py --build P004 \
  --inspection-source reports/process-hardware-p003/physical/20261111T132421573148Z/run-0001
python3 tools/run-process-hardware-probe.py --build P004
```

El builder desensambla la referencia y registra destinos de llamadas directas fuera de la ventana capturada y anteriores al primer UD2, hasta ocho. Esta referencia produce siete: thunks de llamadas importadas y dos helpers cercanos. La cabecera generada contiene sólo offsets relativos y una huella, no código del firmware. El manifiesto registra SHA-256 de referencia y offsets; un entorno nuevo necesita su propia captura de consola coincidente para reconstruir esta sonda.

Al ejecutar, P004 comprueba los 512 bytes vivos con esa identidad FNV-64 antes de usar el plan. Es una comprobación de consistencia, no autorización criptográfica. Referencias diferentes/no legibles se omiten. Cada destino debe caer dentro de un segmento legible de módulo antes de guardar 32 bytes. Sólo se usa un stub de salto indirecto reconocido `FF 25` para ubicar un slot GOT; éste también debe ser legible antes de leer el puntero. El destino apuntado debe pertenecer a un segmento legible de algún módulo cargado antes de guardar 64 bytes. P004 también registra direcciones de exports relacionados disponibles, como `vfork`, `execve`, `_exit` y `__error`, para compararlos offline. No llama a esos exports.

Los logs agregan `call_inspection` y `related_export`; las capturas son `call-N-stub.bin` y, si el destino se resuelve y es legible, `call-N-target.bin`. Destinos ausentes o sin resolver no se consideran identificados exitosamente. Como en P003, estas capturas pequeñas son evidencia local ignorada. No se lanzan el hijo nativo ni Wine. El objetivo es identificar la primera llamada interna y la ruta de error/salida antes de decidir si corresponde otro intento de proceso nativo.

P004 completó la comprobación del fork `reports/process-hardware-p004/20261111T133256904423Z/report.json`. El 2026-11-11 se subió a `.106:2121` y la descarga completa coincidió con SHA-256 `4b1be9181c9e5cb2d29148086558199e6e9a4249a4f948e18023b1ae3f54d7f1`; se retiró el P003 remoto sólo después de verificar su hash.

### P004 física: destino inválido en la primera llamada indirecta

La consola completó las cinco pruebas IPC locales, coincidió con la huella de entrada P003 y llegó a `panel_ready` sin llamar a spawn. La evidencia está archivada en `reports/process-hardware-p004/physical/20261111T134733398802Z/`; el SHA-256 del reporte es `5b6c1b5344e7110d49e113c1fe1f7bfae7ed8740ad37587ccf029e2dcf926ed6`. El análisis offline verificó cada archivo descargado contra el manifiesto de descarga y guardó los desensamblados y `analysis.json` junto a la evidencia.

La primera llamada del helper llega a un thunk de salto indirecto `FF 25` en `0x8000906a8`, cuyo slot GOT en `0x8001c81d8` contiene **`0xeffffffe0000005f`**. Es una dirección x86-64 no canónica, no una función invocable ni un destino legible de un módulo cargado. El inspector correctamente no la desreferenció. Otros slots capturados coinciden con los exports de libkernel `__error`, `execve`/`_execve` y `_exit`; dos destinos cercanos son helpers locales. No se establecieron el nombre del primer import ni el origen del valor inválido. Su posición se parece a la llamada vfork de FreeBSD, pero esa semejanza no identifica el import.

Esto explica de forma estática y sólida que P002 se cerrara antes de `negative_spawn_return`: alcanzar el mismo salto produciría un fallo. P004 no es una traza de ejecución de P002 y no se capturaron dirección de fallo ni registros de P002, por lo que la excepción histórica precisa sigue sin verificarse. No hay evidencia de creación de un hijo ni de que se alcanzara la salida 127 del lado hijo que se había considerado como hipótesis.

**Próximo requisito:** establecer un mecanismo de creación de procesos soportado en PS4 y sus requisitos de arranque antes de otra prueba de creación. El export `posix_spawn` no es utilizable por esta ruta capturada en el entorno de título probado. No reparar su GOT adivinando direcciones, sustituirlo por fork/rfork crudo ni declarar disponible el soporte de procesos nativos. El modo por programa con procesos separados y la coexistencia del launcher/juego PoP siguen bloqueados; el modo actual de proceso compartido no cambia. La corrección IPC local validada es útil por separado, pero no demuestra IPC entre procesos ni una recompilación del paquete principal de OrbisDesk.

## P005: observador y auxiliar externo freestanding

P005 (`01.04`, mismo título de diagnóstico) prepara el primer experimento de coexistencia con cargador externo. No arranca el cargador, invoca spawn retail, hace fork del título ni ejecuta Wine. Compilar y comprobar la rama de cargador ausente:

```sh
python3 tools/build-process-hardware-probe.py --build P005
python3 tools/run-process-hardware-probe.py --build P005 --timeout 20
python3 tools/test-process-loader-helper.py
```

El observador OpenOrbis se conecta únicamente al puerto loopback 9021. Si existe un cargador compatible, envía el `process-helper.elf` empaquetado y registra su salida en `loader-stream.log`. Un fallo de conexión sigue siendo **LOADER UNAVAILABLE**, nunca creación exitosa de procesos. Enviar el ELF es solicitar un lanzamiento, no prueba de READY. El título continúa su latido mientras trabaja el hilo de red. Su interfaz acotada puede terminar aunque el trabajador no haya vuelto; cerrar el título sigue siendo la recuperación final.

El [auxiliar](../native/process_loader_helper.c) es un PIE freestanding separado sin imports pendientes, objetos de inicio SDK, inicialización que parchee kernel, gráficos ni audio. Su entrada realinea la pila y usa un wrapper explícito pequeño de syscalls Orbis para archivos, memoria, identidad, espera y salida en usuario. Nunca llama a syscalls de creación de procesos ni kexec. Las [estructuras del protocolo](../native/process_loader_protocol.h) comprueban tamaños al compilar. La solicitud selecciona un directorio nuevo y token aleatorio; el token rechaza sesiones viejas, pero no autentica frente a código local privilegiado.

El auxiliar mapea el estado de esa corrida, valida token e identidad del observador, registra PID/PPID reales y exige tanto avance del observador como que éste reconozca su PID distinto. El observador exige por separado avance del auxiliar. Un **COEXISTENCE HANDSHAKE** aprobado requiere ese intercambio bidireccional y finalización autorreportada 42. El título no simula recolectar el hijo de un cargador externo: mantiene explícito **NATIVE EXIT STATUS: NOT REAPED BY TITLE**. Otro supervisor deberá demostrar por separado desaparición nativa y código de salida real.

Cada lado solicita además `0x400000` como pista mmap no destructiva, sin MAP_FIXED. El aislamiento sólo pasa si ambos obtienen realmente esa dirección y conservan marcadores distintos; de lo contrario es inconcluso. No son todavía dos EXE Windows en sus bases fijas. El experimento comienza a probar mappings entre procesos, pero no valida SCM_RIGHTS entre procesos ni conexión al servidor Wine.

La evidencia queda en `/data/orbisdesk/process-p005/run-NNNN/`: `report.jsonl`, `state.bin` y, si se alcanzan, `helper.jsonl` y `loader-stream.log`. `request.bin` en el directorio padre identifica la corrida actual. Los archivos/directorios permiten acceso a otra identidad auxiliar y no contienen datos del producto/usuario. No usar esos permisos amplios de diagnóstico como predeterminados del producto.

### Artefacto del cargador externo y límite de despliegue

[build-process-loader.py](../tools/build-process-loader.py) compila un artefacto de investigación GPL-3.0-or-later separado usando [archivos fijados](../tools/process-loader.lock.json). No lo ejecuta ni despliega. El SDK binario es **v0.9**, commit del tag fuente `1a85cb5a8ea12dc2dcfbcc878700d0d097245de7`; no es el HEAD más nuevo estudiado antes. El kernel fuente de esa release también contiene los casos 12.50 y 12.52 en una misma rama. Su arranque y el bootstrap del cargador realizan inicialización privilegiada y cambios de kernel/sesión; ni Root ni disponibilidad FTP establecen sus requisitos.

```sh
python3 tools/build-process-loader.py --fetch
# Transfiere, verifica descarga FTP completa y retira sólo PKGs viejos de diagnóstico con hash coincidente.
# Nunca envía un payload a BinLoader ni arranca el cargador.
python3 tools/transfer-process-probe.py --build P005 --host PS4_IP --include-loader
```

Los artefactos son `out/process-loader/{elfldr.bin,elfldr.elf,socksrv.elf,manifest.json,upstream-source.tar.gz}`. El comando FTP ahora deja el paquete en `/data/pkg/`, el bootstrap ELF en `/data/payloads/OrbisDesk-elfldr-P005.elf` y las fuentes del cargador junto a los archivos de diagnóstico P005. La transferencia BIN anterior es histórica: GoldHEN rechazó ese BIN sin cabecera, como se demuestra más abajo. No reemplaza el PKG principal de OrbisDesk. Establecer la build GoldHEN real y el arranque compatible antes de ejecutar ese payload separado. Arrancarlo es una acción distinta de instalar P005. Con el cargador activo, abrir P005, esperar aproximadamente hasta 15 segundos el panel final, fotografiarlo y cerrar desde el menú PS4. Una corrida sin cargador sólo verifica la rama de cargador ausente.

### Evidencia local enfocada

La corrida del fork `reports/process-hardware-p005/20261111T143905267179Z/report.json` llegó al panel final en 2.523 segundos, registrando conexión rechazada (`-61`), ningún PID auxiliar y ninguna aprobación de coexistencia. El runner detuvo deliberadamente el panel persistente (salida -9). No ejecutó el cargador externo ni estableció soporte de procesos nativos.

La referencia Linux compila el auxiliar real con un adaptador de números de syscall sólo para anfitrión. Verifica latidos bidireccionales con otro PID nativo y salida observada 42, más rechazo de token viejo con salida 83. Detectó y corrigió alineación de pila e índices del lector de resultados antes de desplegar. El reporte es `build/process-loader-helper-reference/report.json`; la evidencia temporal queda en `/var/tmp/orbisdesk-p005-reference-*`. Son comprobaciones anfitrionas, no aceptación física PS4. No hace falta la matriz completa del producto para este incremento aislado. El arranque físico del cargador y la coexistencia P005 quedan pendientes.

### Transferencia P005 y primer intento de arranque

El 2026-11-11 la descarga FTP completa verificó SHA-256 del paquete P005 `5dffddf47b31f37435db84a8e8b9f2af66824ab4850505513bec86d9c933e359` y del bootstrap BIN `f917c03a4d11844892b22cdd27833705a9c291c4d00e94da24525f1da197d57d`. La transferencia está en `reports/process-hardware-p005/ftp-20261111T144434955398Z/transfer.json`; se retiró el PKG P004 tras comprobar su hash, conservando evidencia local y paquete del producto.

[start-process-loader.py](../tools/start-process-loader.py) envía primero un magic desconocido de cuatro bytes al puerto 9021 y comprueba el rechazo del servicio auditado, sin solicitar ejecutar payloads. Con `--start`, si no se puede conectar, verifica el hash local y envía el artefacto seleccionado una vez a GoldHEN 9090. **ELF es ahora el predeterminado**, por el rechazo de formato diagnosticado abajo; BIN queda sólo como opción explícita de reproducción histórica. No reemplaza un servicio ya identificado ni sobrescribe otro endpoint que responda sin identificarse. Este comando ejecuta un bootstrap privilegiado; es distinto del FTP que sólo transfiere:

```sh
python3 tools/start-process-loader.py --host PS4_IP --firmware 12.50 --start
```

El primer intento, `reports/process-hardware-p005/loader-20261111T144600293992Z/report.json`, envió correctamente 263.540 bytes a 9090. El 9021 agotó su tiempo antes y después; el servicio **no fue identificado remotamente**. Esto no establece si el bootstrap falló, quedó pendiente o produjo un servicio inaccesible por red. La comprobación FTP posterior respondió, por lo que la consola seguía accesible. El usuario informó GoldHEN `2.4`, sin sufijo beta. No repetir automáticamente el bootstrap. La próxima ejecución P005 del usuario comprobará por loopback si hay servicio local accesible; todavía no se verificó ningún auxiliar nativo en hardware.

### Corrección de la versión de la consola

El 2026-11-11 el usuario corrigió el firmware: su PS4 Pro Baikal usa **12.50**, no 12.52. Las corridas P001–P004 y el intento inicial de arranque del cargador se atribuyen a esa consola 12.50; los reportes previos no verificaban la versión automáticamente. El reporte original del bootstrap conserva el valor informado 12.52 y no se sobrescribe: la corrección queda como evidencia adicional. El bootstrap y el SDK agrupan 12.50/12.52 en la misma rama; P005 no contiene una selección fija 12.52 ni requiere recompilarse por este dato. Esto no convierte el intento de arranque en exitoso: el cargador sigue sin identificarse y la coexistencia física continúa pendiente. El comando de arranque ahora exige `--firmware` explícito con `--start`; es metadata del operador, no detección automática.

### P005 física: observador completado, cargador ausente localmente

El usuario ejecutó P005 en esa consola 12.50. La corrida archivada es `reports/process-hardware-p005/physical/20261111T145120101532Z/run-0001/`, con hashes y firmware corregido informado por el operador en `fetch.json` en el directorio padre. El observador registró PID 116, conexión local rechazada (`loader_unavailable: -61`), ningún PID ni avance auxiliar, y `panel_ready`. Sólo estaban `report.jsonl` y `state.bin`; la solicitud nunca llegó a transferir el ELF. Coexistencia, salida nativa y aislamiento de dirección baja siguen sin verificar.

Esto confirma la rama de cargador ausente en hardware real y descarta un problema exclusivamente de acceso remoto para esta corrida: el título tampoco pudo alcanzar el servicio loopback. No establece por qué el bootstrap anterior no produjo un listener accesible. Investigar sus etapas de entrada/CRT/kexec/permisos antes de otro intento. No repetir P005 esperando ejecución auxiliar sin resolver ese requisito ni interpretar esto como un fallo de Wine o PoP.

## P006: formato de arranque GoldHEN corregido y cargador residente verificado

El bootstrap inicial y un BIN instrumentado no produjeron traza de archivo. Una sonda P007 separada de 392 bytes sólo hacía E/S de archivos y volvía; tampoco dejó marca. Esas ausencias no establecían un fallo de ABI, permisos ni runtime. La revisión automática rechazó un cambio propuesto de permisos remotos y no se aplicó. La captura klog de sólo lectura estableció la causa real: GoldHEN recibió los tres BIN (263.540, 267.844 y 392 bytes) y registró explícitamente **`invalid payload format... skipping.`** Nunca alcanzaron sus entradas. No describirlo como un crash de kexec/CRT.

La corrección es enviar **`elfldr.elf` directamente**, en lugar de este wrapper BIN upstream sin cabecera. Es un resultado observado para estos artefactos y esta sesión GoldHEN; no afirma que GoldHEN rechace cualquier BIN. El lanzador ahora usa ELF por defecto y registra formato y hash reales. Nunca sondea 9090 con una conexión vacía; la identificación usa sólo el protocolo residente 9021.

P006 agrega además traza por etapas al CRT y cargador fijados, mediante [process_loader_stage.h](../native/process_loader_stage.h), [el builder instrumentado](../tools/build-process-loader-trace.py) y los parches generados de [SDK](../patches/process-loader/0001-sdk_source-bootstrap-trace.patch)/[cargador](../patches/process-loader/0001-elfldr-bootstrap-trace.patch). No reemplaza el CRT compartido ni el runtime del producto. La cabecera registra sin inicialización libc ni escrituras adicionales de kernel; el bootstrap subyacente conserva sus operaciones privilegiadas auditadas. Commits/hashes siguen fijados en [el lock](../tools/process-loader.lock.json).

```sh
python3 tools/build-process-loader.py --fetch
python3 tools/build-process-loader-trace.py --fetch
python3 tools/transfer-process-probe.py --build P005 --host PS4_IP --include-loader \
  --loader-dir out/process-loader-p006
python3 tools/start-process-loader.py --host PS4_IP --firmware 12.50 \
  --artifact-dir out/process-loader-p006 --payload-format elf --start
```

En la PS4 física, GoldHEN aceptó el ELF, seleccionó `ScePartyDaemon` PID 47 y registró lanzamiento exitoso. Las etapas klog/kernel/enlazador dinámico/parches del SDK devolvieron 0. El bootstrap creó el servicio separado PID **120**, devolvió ese PID y llegó a **`service_listening: 9021`**. La identificación recibió el rechazo esperado de `elfldr.elf`. El valor de firmware registrado por el SDK `0x12508001` selecciona su rama 12.50 y coincide independientemente con la corrección del usuario.

Evidencia:

- `reports/process-loader-p006/klog-20261111T150446824106Z/`: rechazos de formato originales.
- `reports/process-loader-p006/elf-attempt-20261111T150618910025Z/`: klog capturado durante el envío ELF exitoso.
- `reports/process-loader-p006/loader-20261111T150619007851Z/report.json`: identificación positiva; SHA-256 ELF `84c26c87891b18302fbcb5184bbe3f0d2c3d6bd784233fe0993e0cd41eae0c5c`.
- `reports/process-loader-p006/trace-20261111T150716558679Z/`: traza descargada SHA-256 `7ebbe982de1a1f8d363564fc043ccd681dd58d3738a5921310971923caf6d4c4`.

Esto valida arranque y creación del servicio residente en hardware físico 12.50. **No** valida todavía el intercambio título/auxiliar, dos mappings independientes en base fija, supervisión de salida nativa ni Wine/PoP. Ahora se puede repetir P005 **sin reinstalar**, con el cargador activo. Un reinicio de consola puede eliminar este requisito de sesión. La traza está en `/data/orbisdesk/process-loader-p006.jsonl`; las fuentes/parches GPL acompañan el ELF transferible en `loader-source-bundle.tar.gz`. No se afirma restauración completa del estado de consola.

## Repetición P005 física: coexistencia nativa e intercambio de estado aprobados

Con el cargador activo, el usuario repitió el paquete P005 sin cambios. La evidencia es `reports/process-hardware-p005/physical/20261111T152515872916Z/run-0002/`; `analysis.json` en el directorio padre verifica los hashes de todos los archivos descargados y cruza logs del observador, logs del auxiliar, salida socket y campos binarios de memoria compartida. SHA-256 del reporte `0c2eaa7db8959a61ce39588e6ee5b280743746dc4e707708482532244c10667e`; SHA-256 del reporte auxiliar `b4ce81d492e1343560309afbc6b10d7ae5f00c1dd5136f4f2b06164d65456ec2`.

| Observación | Resultado físico 12.50 |
| --- | --- |
| PID del título observador | 123 |
| PID auxiliar / PID de su padre nativo | 124 / 120 (cargador residente) |
| Latidos observador / auxiliar | 18 / 11 |
| Observador reconoció otro PID / auxiliar observó avance del observador | Ambos 1 |
| Finalización auxiliar | 42 autorreportado; no recolectado por el título |
| JSONL auxiliar frente a salida socket del cargador | Idénticos byte a byte |
| Intercambio de coexistencia / panel final | Aprobado / alcanzado |
| Pista mmap solicitada | `0x400000`, sin MAP_FIXED |
| Mappings reales observador / auxiliar | `0x41c000` / `0x588000` |

Esto demuestra físicamente que un auxiliar nativo creado independientemente y el título siguen activos simultáneamente e intercambian estado en ambas direcciones por un mapping de archivo compartido. El título no se reinició ni actuó como padre nativo del auxiliar. No es simplemente otro hilo dentro del título. La corrida original run-0001 sigue archivada como caso de cargador ausente.

**Requisitos pendientes:** el aislamiento en base fija es inconcluso porque ninguno obtuvo la pista solicitada; no marcarlo aprobado ni inferir qué imagen ocupa ese rango sin inventario de módulos/mappings. Siguen sin verificar la supervisión de código de salida/desaparición nativa, limpieza repetida y SCM_RIGHTS entre procesos. No se establecieron auxiliar Wine, contrato de objetos de proceso Windows ni resultado PoP. Inspeccionar la disposición de imágenes/mappings nativos y demostrar mappings simultáneos independientes en la base fija PE32 antes de integrar Wine. No sobrescribir mappings existentes con MAP_FIXED como sustituto de esa investigación.

## Revisión posterior: P007 aprobado, sigue el arranque P009/P010

El trabajo posterior extiende [el builder de diagnóstico](../tools/build-process-hardware-probe.py) con P007/P009 y [el del cargador externo](../tools/build-process-loader-trace.py) con P010. Estos resultados reemplazan las evaluaciones pendientes anteriores sólo donde existe evidencia; las corridas previas siguen archivadas.

**P007 verificado:** `reports/process-hardware-p007/physical/20261111T164219043252Z/run-0002/`. Se volvieron a comprobar todos los hashes descargados contra el manifiesto. El título mantuvo su mapping nativo en `0x400000`; el auxiliar PID 135 (padre nativo 120) identificó y desmapeó tres regiones ejecutables del bootstrap en su propio proceso, mapeó **16 MiB en `0x400000`** y conservó su marcador. Ambos lados verificaron contenidos de descriptores recibidos por AF_UNIX/SCM_RIGHTS y pasó la coexistencia. Es un resultado freestanding: no se estableció que su rutina de desmapeo sea segura para un runtime OpenOrbis/Wine ya inicializado con libc/TLS/referencias globales. EOF y finalización 42 no son un código de salida nativo recolectado; siguen sin verificar dos auxiliares Wine externos con la misma base PE preferida.

**Estado P009/P010:** P009 es un fake SELF OpenOrbis enlazado en `0x1100000000`, con dependencias nativas parecidas a Wine y pruebas previstas de hilo, heap de 64 MiB, base fija y adaptador de red de producción. Una corrida física anterior terminó en Sysmodule cargando `/app0/sce_module/libSceFios2.prx`, antes de `child_entered`. Las notas de implementación registran rechazos ENOEXEC para variantes System/NPDRM. El [parche sandbox](../patches/process-loader/0002-elfldr-orbisdesk-sandbox-root.patch) de P010 agrega una ruta opcional que adopta rootdir/jaildir/prison del título antes del exec SELF. Siguen pendientes la compatibilidad de `/app0` y la inicialización de módulos.

Artefactos y observaciones actuales:

- P009 **01.11**, SHA-256 del paquete `b0765eed7287d0396013ce4b29acc9bbd7bba672ff9f10ecbb4badd995a81e03`; transferencia verificada `reports/process-hardware-p009/ftp-20261111T183323923852Z/transfer.json`.
- SHA-256 del ELF P010 `1e4964e8a0aba6ef32315440d52aa19d8c550cf88b6765acc1c21649d6938987`; arranque identificado en `reports/process-loader-p010/loader-20261111T183316445826Z/report.json`.
- Última descarga P009 `20261111T184918946303Z`: run-0009 llegó al cargador sin PID hijo; run-0010 recibió conexión local rechazada. La comprobación posterior de sólo lectura `reports/process-loader-p010/loader-20261111T185030669844Z/report.json` tampoco encontró cargador accesible. No explica su desaparición ni demuestra que el parche sandbox la causara.
- Varias revisiones P009 usan el mismo marcador textual. El orden de transferencias no identifica por sí solo la revisión instalada de cada corrida histórica; correlacionar candidato real y klog en la próxima aceptación.

Orden revisado:

1. Establecer y registrar un servicio P010 estable para el candidato exacto; investigar su terminación antes de repetir otro lanzamiento y conservar klog.
2. Alcanzar la entrada propia del hijo P009 con `/app0` y módulos correctos; pasar después hilo/heap, base fija, estado compartido y descriptores en hardware.
3. Verificar dos auxiliares simultáneos con contenidos independientes en la base fija, limpieza repetida y supervisión de salida nativa. No repetir la campaña freestanding aprobada como primer bloqueo.
4. Integrar una familia Wine sin interfaz con un servidor/espacio de objetos común; ejecutar el fixture PE32 padre/hijo de base fija antes de gráficos y PoP.
5. Continuar el selector independientemente. Automático/Dentro del escritorio/Exclusivo pueden funcionar ahora; Procesos separados debe seguir visiblemente no disponible hasta aprobar la integración Wine.

La referencia anfitriona de 14 casos de política de registro pasó (`reports/execution-modes/20261111T162625766752Z/report.json`) y sus hashes coinciden con la política actual. Winecfg coincide con su builder y entradas de interfaz. El manifiesto i386 de invitados ya no coincide con el builder actual: recompilar sus DLL consumidoras antes de empaquetar el selector. Esto no representa una nueva build del producto ni aceptación del selector en hardware.
