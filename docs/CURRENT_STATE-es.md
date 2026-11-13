# Punto de retoma: OrbisDesk W303 y build alojada del producto, 2026-11-10

[English](CURRENT_STATE.md) | [Español](CURRENT_STATE-es.md)

La base actual del producto es **W303**, cuya versión SFO local predeterminada es **04.02**. El commit `208803d` registra validación de instalaciones limpias en consola. La construcción completa del producto en GitHub ya pasa; la base `dev` revisada es `aa43870`. Un candidato de CI tiene su propia versión SFO asignada y SHA, y necesita su propia evidencia de aceptación del runtime.

- **Instalación:** `OrbisDesk.pkg` lleva el runtime. El instalador del primer arranque corre después de elegir NORMAL/ROOT y antes del jailbreak ROOT, mientras `/app0/runtime` sigue accesible. Verifica los archivos copiados y preserva el estado del usuario. Ver [instalación y releases](RELEASES-es.md#instalación-en-el-primer-arranque).
- **Builds:** la receta alojada limpia incluye el árbol anfitrión completo de Wine y su prefijo verificado, adaptadores PS4, Steam integrado, gráficos, zlib y recursos fijados. Gráficos y Wine pueden venir de cachés Actions verificadas o assets precompilados fijados de releases; cambiar etapas PS4 posteriores no invalida esos bloques. Ver [builds y releases](RELEASES-es.md).
- **Runtime:** W303 restaura perfiles/carpetas Public, programas de 32 bits, NLS/metadatos y registro del prefijo completo, conserva las métricas de ventanas W302 y reaplica las exclusiones de módulos de consola. Incluye SeaMonkey, suprime la pregunta inicial de privacidad de VLC y aplica la [política de trazas](RELEASE_TRACES-es.md).
- **Steam:** el cliente nativo está integrado en el título y en la receta del producto. Su aceptación de login/descargas/juegos es distinta de la aceptación de instalación y escritorio; seguir [Steam integrado](STEAM_HOSTED-es.md) y su evidencia enlazada.
- **Siguiente aceptación:** usar el paquete, manifiesto, SHA y logs del candidato CI exacto para comprobar instalación, escritorio y aplicaciones. Una build exitosa o un acierto de caché no demuestra ejecución de ese candidato en consola o emulador.

<a id="punto-de-retoma-orbisdesk-w288-0387-2026-11-07"></a>

# Retoma anterior: OrbisDesk W288 (03.87), 2026-11-07

En esa retoma, W288 / 03.87 era la última build subida y todavía no se había probado en consola. Las entradas siguientes conservan la evidencia y comprobaciones pendientes de esa fecha. Detalle: [HARDWARE_W285_W288](HARDWARE_W285_W288-es.md).

- **W285:** los streams de audio de un invitado salen del mezclador cuando se descarga (lista de huérfanos, sin liberarlos). Probada con NFS U2 cerrado desde el overlay; en esa corrida el juego liberó su propio stream.
- **W286:** los logs de GPU de RADV van a `/data/orbisdesk/gpu`. Se borró de la consola la carpeta vieja `/data/orbis-win`.
- **W287:** entrada GRÁFICOS en el overlay, por programa de 32 bits: DXVK o wined3d para D3D8/9, Vulkan u OpenGL para wined3d. MangoHud ahora se engancha a los juegos con wined3d (SuperMarioKart, confirmado en el log). El renderer guardado no se aplicó, porque wined3d quedó cargado entre corridas.
- **W288:** wined3d lee el renderer del programa en cada `wined3d_create`. Próxima comprobación: SuperMarioKart con `gl` guardado debería loguear `PWD3D renderer=gl ... from the program`.
- **Antes, el mismo 2026-11-07 (W273–W282, sin documentos propios):**
  - línea de comandos y nombre de módulo por invitado durante la carga;
  - arreglo de la espera de mensajes con timeout cero (Quake 3, NFS U2);
  - afinidad de CPU real con `scePthreadSetaffinity` (6 núcleos del título); los cambios de afinidad del proceso se rechazan;
  - NFS U2 fijado a un núcleo, sólo para los hilos que arrancan en su EXE;
  - trazas de fallas x87 y frames de 32 bits en los volcados de cuelgue;
  - los hilos únicos de winmm/dinput ya no pertenecen a un invitado;
  - winmm saca un timer cuyo callback ya no está mapeado o falla (NFS U2 vuelve a tener música en el segundo arranque);
  - wmvcore informa que falta winegstreamer en vez de cerrar el juego (GTA San Andreas).
- **Steam:** S2 01.06 (descarga anónima de un depot, 8/8 archivos verificados) y S3 01.07 (login por QR, sesión guardada, biblioteca de 36 juegos) pasaron en la consola. Falta comprobar que S3 reabra sin QR. Ver [STEAM_S3](STEAM_S3-es.md).
- **Juegos que el usuario informó funcionando ese día:** Quake 3, Max Payne 1 y 2, NFS Underground 2 (con música en el segundo arranque), NFS Most Wanted, GTA San Andreas, Worms 4, Call of Duty (carga un nivel). SuperMarioKart corre; se están comprobando su MangoHud y la elección de renderer.

# Punto de retoma anterior: OrbisDesk, paquete limpio W284 (03.83), 2026-11-07

Prueba física W284 descargada: modo root, imagen e interfaz activas durante unos 11 minutos, sin cierre fatal registrado. Captura del selector confirma OrbisDesk y versión 03.83 W284. Evidencia: `reports/wine-hardware-w284/physical/20261107T153807Z/`. Clasificación `presented`, sin código de salida; no es validación general de juegos.

Compilada y verificada localmente: `out/wine-hardware-w284/OrbisDesk.pkg`. Título visible PS4: **OrbisDesk**. Versión visible sólo en el selector NORMAL/ROOT; SFO interno 03.83 para actualizar ORBW00002. Sin cambios de lógica de ejecución. 58 hashes fuente y SHA256 del paquete comprobados. Selector visual confirmado en captura. Entrega FTP completada: `/data/pkg/OrbisDesk.pkg`, 192.168.68.100:2121. PKG y 1.823 archivos runtime verificados por lectura de vuelta; un paquete anterior retirado tras verificar. Ajustes preservados; instalación y arranque físico confirmados en la evidencia posterior. Evidencia: `reports/wine-hardware-w284/transfers/20261107T144147Z.json`. Ver [W284](HARDWARE_W284-es.md). Las entradas siguientes son históricas.

# Historia previa: OrbisDesk W283 (03.82), 2026-11-07


**Entrega W283 completada:** `/data/pkg/orbisdesk-W283-a3a72e1401c2.pkg`, FTP 192.168.68.100:2121. PKG y 1.823 archivos runtime verificados por lectura (83 subidos, 1.740 ya presentes); un paquete anterior retirado tras verificar. Sin fallos de permisos. Ajustes de consola conservados. Instalación y prueba física pendientes. Evidencia: `reports/wine-hardware-w283/transfers/20261107T142853Z.json`.

El nombre actual es **OrbisDesk**. El cambio abarca código propio, interfaz, documentación, clases y asociaciones Win32, títulos y nombres de paquetes, sondas y cliente de Steam. Detalles y excepciones: [REBRANDING_ORBISDESK](REBRANDING_ORBISDESK-es.md).

- W283 conserva ORBW00002 y su Content ID para actualizar la instalación existente.
- Estado/logs nuevos en `/data/orbisdesk`; importación única de ajustes anteriores. Prefijo, documentos y juegos siguen en sus ubicaciones originales.
- Steam S1 01.05 y S2 01.06 recompilados como OrbisDesk, sin prueba física nueva.
- Tres comprobaciones enfocadas de migración/rutas/paquetes aprobadas en host.
- Paquete principal compilado y verificado: `out/wine-hardware-w283/OrbisDesk-W283-03.82.pkg`. SFO correcto, 58 hashes fuente coincidentes y cierre web sin importaciones faltantes. Instalación y validación visual pendientes; no interpretar el cambio de marca como nueva compatibilidad de juegos.
- Los logs, paquetes y hashes históricos mantienen sus nombres originales.

# Historia previa: 2026-11-07, W281 (03.80) subida / prueba pendiente

## Último código auditado: W281

Esta retoma leyó código, manifiestos y evidencia local. No compiló, ejecutó, transfirió ni modificó código. El estado W260/W261 que sigue queda como historia.

- W281 / 03.80, ORBW00002: paquete local y 56 archivos fuente del manifiesto comprobados por SHA256, sin diferencias. 91 revisiones en el builder de huéspedes para x86_64/i386 y cierre web sin importaciones faltantes.
- PKG /data/pkg/orbis-win-W281-90e022053bab.pkg. Transferencia verificada en reports/wine-hardware-w281/transfers/20261107T130350Z.json: 1825 archivos runtime, destino actual **192.168.68.100:2121**; W280 retirado tras verificar. No usar automáticamente la IP histórica .104. No hay carpeta physical de W281 todavía.
- Última evidencia localizada en esta retoma: W279, reports/wine-hardware-w279/physical/20261107T124705Z/. No equivale a una aceptación global: el recolector marca presented, sin salida final.

## Cambios posteriores a W260/W261

- **Huéspedes/procesos:** handles de proceso con evento de fin y GetExitCodeProcess por huésped (W267); KnownDLLs no cuentan como choques (W269); GetModuleHandle(NULL), GetModuleFileName(NULL) y línea de comandos responden por huésped también durante la carga/DllMain (W273/W274). El primer hilo usa la reserva de pila del EXE (W271).
- **Relanzamiento como fallback:** hereda carpeta/entorno del lanzador (W262) y analiza la línea Windows, con hasta 16 argumentos (W265). Esto importa cuando un segundo EXE necesita una base fija ocupada por el primer invitado.
- **OpenGL i386:** Mesa WGL/Zink preparada en syswow64 y ajustes de inicialización con dxgi; diagnóstico de CoD y de extensiones GL. No dar compatibilidad general de esos juegos por probada sólo por compilar la ruta.
- **CPU/afinidad (W275–W279):** pw_wine_thread_setaffinity usa scePthreadSetaffinity y el registro TID/pthread_t; system.c informa CPUs permitidas. W279 registra processors=6, title_cores=3f y speed2.exe en máscara 0x20. Cambios de afinidad de todo el proceso se rechazan con ACCESS_DENIED para no fijar Explorer y servidor al núcleo que pide un huésped. No es implementación de RR ni de ntsync.
- **W281, aún pendiente de probar:** los hilos singleton de winmm/dinput/dinput8 no pertenecen al huésped que los creó; así el cierre no elimina el temporizador compartido y deja la segunda apertura sin música. La afinidad del huésped de un núcleo se aplica sólo si la entrada del hilo cae en su EXE, no a hilos de DXVK ni de otras DLL. NFS U2 es el caso que motivó ambas correcciones.
- **Multimedia W280:** wmvcore i386/x86_64 devuelve error real y lector NULL cuando falta winegstreamer, en lugar de terminar mediante la excepción del delay-load. Motivado por GTA San Andreas; no implementa GStreamer ni reproducción WMV.

Código clave: tools/build-guest-hw.py, build-wine-delete-server.py, build-telemetry-ps4.py, build-wmvcore-hw.py; platform/ps4/pw_wine_threads.c; native/wine_hardware.c. El mundo PE32 continúa en el mismo proceso de Explorer, con relanzamiento alternativo; no apareció arquitectura de auxiliares nativos.

## Nueva pista separada: cliente nativo de Steam

- ORBS00001, independiente de Wine/ORBW00002. Backend de Playden fijado en fb74dbfd6bb96fc19a96afc1f48a4e40a885216b, con Mbed TLS/curl/zstd/LZMA. Ver docs/STEAM_S1.md, STEAM_S2.md y native/steam/.
- S1 comprueba entropía, CA, HTTPS y rechazos de certificados. Host pasó; primera PS4 falló al leer CA; 01.01 cambia a lectura hasta EOF. No se encontró aquí evidencia de aceptación completa de esa versión.
- S2 host sí completa login anónimo, manifiesto y descarga de depot 1004/app 1007: 8 archivos, 69 chunks, 67863136 bytes, todos verificados por SHA1. No es login de una cuenta ni el cliente Steam Windows ejecutándose dentro de Wine.
- S2 PS4 01.03 falla en HttpClient de Playden; curl solo sí consigue TLS 1.3/HTTP200. El fallo se rastreó a opciones curl desactivadas que Playden necesita. 01.04 ya está empaquetada con la configuración corregida y diagnóstico de opciones; su aceptación física no consta en los documentos revisados. No anunciar descarga completa en PS4 hasta el resultado final verificado.

Próximo punto de lectura: resultado físico W281 (audio/reapertura de NFS U2, rendimiento/afinidad), y resultado S2 01.04 en su pista independiente. Los textos «sin probar» de documentos antiguos pueden tener resultados posteriores: leer las secciones cronológicas nuevas y comprobar manifests/logs antes de actuar.

## Historia conservada: W260 probado / W261 en preparación

## Retoma más reciente: W260–W261

Este bloque sustituye el estado W188 y los pendientes históricos conservados debajo. Auditoría de archivos locales; esta retoma no compiló ni transfirió nada.

- **Última build con manifiesto, transferencia y evidencia física localizada:** W260 / 03.59. Paquete /data/pkg/orbis-win-W260-791ed8ceb53a.pkg, transferencia reports/wine-hardware-w260/transfers/20261106T004811Z.json con lectura verificada. Pruebas físicas: 20261106T011238Z y 20261106T021646Z. Son fechas UTC: aún 5/11 por la noche en Argentina. El recolector dice presented, no aceptación completa.
- **Código/build en preparación:** W261 / 03.60. Existe un PKG en out, pero al revisar no estaba out/wine-hardware-w261/manifest.json ni un informe de transferencia. build/w261-final.sh sigue la cadena de staging, enlace, paquete y cierre web; el enlace registra linked-unvalidated sin símbolos pendientes. No anunciar W261 terminada, subida ni probada sin esas comprobaciones.

## Arquitectura: lo que ya dejó de ser hipotético

- **Mundo PE32 dentro de Explorer implementado.** Las sondas pasaron; W234 ejecutó console32 dos veces sin relanzar. W235 incorporó orbis32host y el puente de CreateProcess; los huéspedes i386 tienen sus DLL separadas del modo relanzado.
- **GUI y gráficos PE32 en el mundo:** W240 corrió gui-window32, d3d9test32 DXVK (1673 cuadros/5 s) y ddraw7test32 wined3d Vulkan (2491 cuadros), todos salida 0.
- Se resolvieron callbacks por arquitectura, TLS, creación suspendida, cruces de procedimientos de ventana/IME, registro WOW64/COM y despacho SEH. No son ya tareas pendientes iniciales del plan. Relanzamiento y OrbisRunsAlone siguen como alternativas; el marcador pe32relaunch permite volver al camino anterior.
- **Vice City:** W246 lo ejecutó y se jugó dentro de Explorer con d3d8 DXVK, sonido y controles. W256 reprodujo desde USB ambos videos dos veces. W255 corrige capas GPU retenidas tras destruir una swapchain cuya ventana hija ya no existe; W256 recupera el foco tras salir. No inferir compatibilidad total: se registró DEVICE_LOST al recrear el dispositivo con Esc en W246.
- **Señales a hilos:** W195 implementó registro TID/pthread_t y SIGUSR1 dirigido; sus logs muestran entrega correcta. La frase histórica «no hay señales dirigidas» ya no describe todas las capacidades actuales. No implica soporte completo de contextos remotos i386 ni señales de terminación: otras siguen restringidas.
- **Cierres de huéspedes:** TerminateProcess propio y FLS por imagen (W196/W197), descarga de DLL propias, orden de dependencias, hilos y locks huérfanos tuvieron nuevas iteraciones. W259 acredita descarga de módulos de hl2 y carga nueva en la siguiente apertura, resolviendo una colisión con la carpeta del padre Portal.
- Esto conserva un único proceso compartido: no es aislamiento nativo.

## USB, navegador y multimedia

- **USB ya funciona en modo ROOT:** W228 permite elegir NORMAL/ROOT al arrancar. GoldHEN quita el sandbox y después se vuelve al uid de la app; el modo se conserva en relanzamientos y se restaura al salir. D:–K: corresponden a usb0–usb7 montados, detectados al arranque. Vice City se leyó desde E:. No dar por probadas escritura ni conexión en caliente. Ver HARDWARE_W228.md.
- Pale Moon ya navega desde W188. Hay nuevas iteraciones sobre su uso como huésped y cierre/reapertura; no reinstalar W188 para resolver la antigua red.
- DirectShow/COM i386 y reproducción de video se ampliaron; la investigación registra webview32 con páginas y reapertura, DVD y VLC funcionando en W252. No implica soporte de todos los formatos, DRM o Media Foundation.

## Bloqueo inmediato y W261

- **Portal en W260:** hl2 alcanza DXVK/D3D9 y presenta cinco cuadros. Después VK_ERROR_DEVICE_LOST; el compositor de Explorer sigue presentando. La evidencia apunta a investigar RADV/GFX7, no demuestra que falle la activación del mundo WoW64. Falta el diagnóstico de la valla/GPUVM para atribuir la causa exacta.
- W260 añadió avifil32/shfolder, que antes impedían llegar a esa etapa.
- W261 prepara 396 módulos i386 y 393 x86_64 adicionales con cierre de imports, debug retirado y registro COM generado: 7699 claves de 119/118 módulos. Es una ampliación de disponibilidad, no ejecución validada de todas esas APIs. Hay exclusiones explícitas por servicios/backend Unix/Mono/WinRT, entre otras; d3dx9_24–43 siguen sin enlazarse. El archivo w261-final.sh incluye además las opciones de cursor por programa y el bloqueo de estadísticas sobre el escritorio.

Referencia de trabajo actual: investigacion-wow64-en-explorer.md, secciones 9–31. Sus primeros apartados son el plan histórico; los encabezados «preparado» de secciones intermedias deben leerse junto con los resultados de la siguiente.

Próximo: verificar cierre de W261 y su transferencia antes de pedir prueba; continuar Portal por evidencia GPU. No reconstruir ni detener procesos ajenos durante una retoma. Preferencias: iteraciones enfocadas en PS4 física, preservar evidencia y feedback con botón; sin matriz local extensa.

## Historia conservada: retoma W188 (02.87)

## Retoma auditada del workspace

Las notas W113–W188 avanzaron sin actualizar este índice. Este bloque sustituye las indicaciones de «actual», «siguiente» y «pendiente» de la historia W112 e inferior que se conserva más abajo. No reinstalar ni reconstruir W112.

- Última build: W188, APP_VER 02.87, ORBW00002. PKG local comprobado por SHA256: 5c42debd84403324f8510d194dac3e4fc635fef12ce5023e90c258f1c3a32e61.
- Subida verificada a 192.168.68.104:2121: /data/pkg/orbis-win-W188-5c42debd8440.pkg. reports/wine-hardware-w188/transfers/20261104T004515Z.json: readback_verified=true, 861 archivos runtime, 695120406 bytes; W187 eliminado después de verificar. La fecha UTC del informe equivale al 3 de noviembre por la noche en Argentina.
- W188 y W187 no tienen evidencia física descargada en sus directorios locales. No confundir transferencia con instalación o ejecución. Última prueba física documentada: W186, reports/wine-hardware-w186/physical/20261104T002752Z/.

## Capacidades recuperadas y sus límites

- DOSBox Pure ya ejecutó DOS en PS4: CARMEN con audio audible y cierres 0 (W114). smb.exe genera silencio en el núcleo; no es prueba de fallo de AudioOut.
- Windows PE32 arranca mediante relanzamiento del título. W137 añadió ejecución x86 nativa en modo compatibilidad (wow64native), con camino de señales/excepciones. No afirmar que PE32 ya convive como huésped dentro de Explorer PE64.
- Audio Windows 32/64 aceptado (W120 y siguientes); D3D9 mínimo con DXVK aceptado en ambos (W126). DDraw/D3D7 con wined3d/Vulkan llega a SuperMarioKart (W134). No generalizar esas pruebas a todos los juegos ni dar D3D10/11 por validado.
- Presentación y composición por capas GPU; varias mejoras de staging, mapas y agrupamiento Vulkan. SuperMarioKart completó una carrera y salió 0 en W176; W178 registró mediana 54,7 FPS en su sesión, con variación según escena. W181 confirmó el juego con mando mediante perfil de teclas.
- WFM: listado, EXE/textos, rename y borrado recursivo aceptados en iteraciones anteriores. Temas Luna/Noir, Start e iconos se trabajaron después. winecfg Apply completó dos veces en W184; ese cambio también separa atexit de invitados.
- Red básica aceptada W176 en 32/64: DNS, TCP, HTTP 200, no bloqueante, loopback, adaptadores y consulta DNS por UDP. Eso no acredita HTTPS de navegador.
- USB: W181 aún ve /mnt inexistente para la app, errno=2. No hay acceso a discos USB acreditado; las letras propuestas no eliminan el sandbox.
- WebView Gecko muestra página local (W182), con limitaciones de JS/canvas. Pale Moon 35 corre como título independiente para evitar DLL homónimas de Gecko. W186 muestra página local completa: es5-ok, es2020-ok, canvas-ok. Su arreglo de GetThreadContext fallido elimina el bloqueo observado; sitios remotos siguen en blanco o con error. No afirmar navegación remota funcional.

## Trabajo inmediato

1. Obtener resultado físico de W188 antes de otra build. Corrige traducción de opciones TCP/IP/IPv6 del SDK Linux al kernel FreeBSD mediante wrappers en platform/ps4/pw_wine_sockopt.c. Conserva logging de Pale Moon y desactiva keepalive en su perfil. Ver docs/HARDWARE_W188.md: causa inferida del código, todavía pendiente de validación física.
2. Revisar HTTP/HTTPS y palemoon-net.log-main.* junto con PWNET: distinguir conexión, TLS y respuesta HTTP. Sigue pendiente verificar la fuente aleatoria de ntdll (getrandom ENOSYS y fallback /dev/urandom no acreditado).
3. La investigación docs/investigacion-wow64-en-explorer.md propone primero disimular/medir el relanzamiento y después sondas de mapa bajo 4 GiB, señales y BTCpuProcessInit tardío. Mundo PE32 dentro de Explorer: no implementado; estimación del documento 15–25 builds, condicionada a las sondas.

Preferencias persistentes: pruebas enfocadas en PS4 real, sin matriz local; preservar evidencia; retirar PKGs anteriores sólo tras subida verificada; usuario instala/ejecuta y avisa con botón. Calibración absoluta CPU/GPU aplazada. Esta retoma fue de lectura local y documentación: no se compiló ni se tocó FTP.

## Historia previa conservada (índice antiguo W112)

## Task Manager en W112 (a81c9325bbaf, aceptado: «Todo anda»)

Performance en 0 y Processes vacío: la clase 8 (ProcessorPerformance) devolvía NOT_SUPPORTED en ORBIS y taskmgr abandonaba cada refresco. End task dejaba la fila porque la pasada de borrado sólo corría si se enumeraba otra ventana. Arreglos en system.o de telemetría y out/taskmgr-hw. W112 (02.11) se reconstruyó con DOS ya sincronizado y se subió: /data/pkg/orbis-win-W112-a81c9325bbaf.pkg, informe transfers/20261102T192004Z.json. El PKG W112 previo (b6809b7be979) se borró por FTP: su ELF no tenía el arreglo y el runtime de /data ya es el nuevo. Detalle: [HARDWARE_W112_TASKMGR](HARDWARE_W112_TASKMGR-es.md).

## Última consulta: Documents/smb.exe

El usuario confirmó «Borró todo correctamente» y luego precisó que falló abrir Documents/smb.exe. Se descargó sólo ese EXE para identificarlo, sin ejecutarlo ni modificar la consola. Reporte: reports/smb-exe-inspection/report.json. Es MZ MS-DOS con marcador PKLITE, e_lfanew=0 y sin cabecera PE, 66055 bytes; SHA e58adb73373c214a0f4ae1f98fb7dde655095c338cb4121db3bd4abde6049db3. W111 20261102T181347Z registra reject_title_replacement para ese archivo. Necesita un runtime DOS aparte; no es un fallo demostrado de PE32/WoW64. Wine upstream también delega DOS en DOSBox (programs/winevdm/winevdm.c). El usuario eligió añadir soporte para juegos DOS. W112 (02.11) ya compila DOSBox Pure PE64 interpretado, doshost.exe GDI, puente nativo AudioOut y routing de MZ/.com desde el broker de Explorer. Ver HARDWARE_W112.md. PKG SHA b6809b7be979be7e1a6b638a08fbdfbace2c5351fea7c56fb84cc471d06f2c01. ELF SHA 985ee531e5e49707b4de6086cb07b565239613714c075609d61aa6bed76a72f8. 553 archivos runtime; fuente DOS y receta incluidas, sin juegos. Transferencia W112 iniciada a 192.168.68.104:2121; verificar informe antes de anunciar subida completada. No se ha ejecutado DOS en PS4 todavía. Próximo: instalar, abrir Documents/smb.exe, comprobar imagen/controles/audio, cerrar, comprobar Start/WFM y reabrir. Recoger logs PWDOS/PWDOSAUDIO. W111 conserva su aceptación de renombrado, falso 145 y árbol borrado. El parche GPU tenía guard no idempotente: corregido y fuente/biblioteca restauradas a los hashes exactos de W111. No se cambiaron los porcentajes.

## Iteración actual: W111

W110 real recogida: 20261102T174008Z. Native_entry CARMEN09.BMP pero stat ENOENT; FTP posterior confirma nombre inexistente y padre vacío. También enumera un nombre anterior de carpeta renombrada que ya no existe. El servidor cuenta esas entradas residuales como contenido y falla 145. Guard de identidad W110 no explica este caso; no se atribuye a cierre pendiente.

W111 (02.10) corrige el contrato BSD readdir: omite registros con inode cero y whiteouts validando primero longitud; continúa hasta una entrada activa/EOF. Mantiene errores reales y no simula vacío. El inode de esos registros no se imprimió en W110: la siguiente prueba registra skipped_unused para confirmarlo. Comprobación puntual del decodificador pasó (activos/borrados/malformados). Paquete compilado y subido con lectura de vuelta verificada: /data/pkg/orbis-win-W111-e8585b70c409.pkg. Informe: reports/wine-hardware-w111/transfers/20261102T175415Z.json. 548 archivos verificados (546 presentes, 2 subidos), sin fallos de permisos. W110 retirado después de verificar. Sólo ELF, runtime PE idéntico por hash. Ver [HARDWARE_W111](HARDWARE_W111-es.md). Resultado físico: Prueba real recogida en 20261102T180132Z: 198 omisiones de slots inode=0, rmdir nativo rc=0 y carpeta ausente por FTP. Rename con espacios rc=0, nombre viejo ausente y nuevo presente por FTP. Sin errores de borrado. El falso 145 queda validado como corregido en este caso; el renombrado real también. Falta una prueba de árbol completo con archivos activos y salida final del título. No se requiere nueva build para esa comprobación. Nueva recolección 20261102T180735Z tras otro «Ya la probé»: mismo run-0001, sin nuevas operaciones de filesystem respecto de 180132Z. Se pidió al usuario el resultado observado (éxito/error/no completado), sin pedir otra reinstalación. El usuario confirmó explícitamente «Borró todo correctamente». Se acepta la prueba recursiva por feedback de hardware, sin atribuirla a operaciones nuevas del log. Aceptación: reports/wine-hardware-w111/physical/20261102T180735Z/acceptance.json. W111 queda como referencia para rename, falso 145 y borrado del árbol probado. No quedan más pruebas solicitadas para este arreglo. Siguiente prioridad: escritorio con archivos/carpetas, iconos de enlaces a texto y refresco. Tras «Ya la probé», recoger W111 y verificar rmdir real y carpeta ausente.

## Referencia anterior: W110

W109 probado y recogido: 20261102T172145Z, dos logs. El servidor registra koopa beach_fast.mid y CARMEN09.BMP como entradas bloqueantes. WFM no registra DeleteFile para ellos; sólo enumera SMK y luego falla RemoveDirectory 145. Los reintentos no cambian ese resultado. La hipótesis de cierre pendiente no explica estos casos. El problema está en archivos omitidos por el listado Win32.

W110 (02.09) recompila el objeto Unix file de ntdll con receta/hash probados: identidades sin inode no ocultan entradas; errores de readdir no se convierten en éxito parcial; PWDIRENUM audita nativo/máscara/stat/filtro/resultado. La causa exacta de omisión aún no se atribuye al inode: requiere logs de esta build. Paquete compilado y subido con lectura de vuelta verificada: /data/pkg/orbis-win-W110-982cf9c8ac3c.pkg. Informe: reports/wine-hardware-w110/transfers/20261102T173510Z.json. 548 archivos verificados (546 presentes, 2 subidos), sin fallos de permisos. W109 retirado después de verificar. Sólo ELF cambia, WFM/componentes PE coinciden por hash con W109. Prueba física pendiente. El primer aviso de prueba se investigó en 20261102T173705Z: W110 no tiene directorio/logs. FTP muestra nuevo w109/run-0003.log, descargado como sesión W109 20261102T173750Z; comienza W109 entered_launcher. No contar como prueba de W110 ni inferir crash previo al main. Se pidió cerrar, instalar 02.09 y probar W110. No se volvió a subir ni recompilar. Ver [HARDWARE_W110](HARDWARE_W110-es.md). Sin matriz local, sin cambios de emulador.

## Referencia anterior: W109

W108 falló con 145 al borrar con subcarpetas (confirmado por el usuario). Sesión 20261102T170507Z descargada, título termina con 0. PWFM Unicode no se capturó. FTP posterior: Documents/Test vacío; causa pendiente, posiblemente eliminación diferida. No hubo borrado por FTP.

W109 (02.08) compilada y subida con lectura de vuelta verificada: /data/pkg/orbis-win-W109-9968f1da041b.pkg. Informe: reports/wine-hardware-w109/transfers/20261102T172053Z.json. 548 archivos verificados (545 presentes, 3 subidos), sin fallos de permisos. W108 retirado después de verificar. Prueba física pendiente. Reintento de RemoveDirectory real hasta 500ms ante 145; conserva error/cancelación, no borra contenido concurrente. Corrige canal de logs WFM, registra unlink/rmdir y añade auditoría is_dir_empty del servidor mediante un único objeto recompilado con receta/hash probados. Sin matriz local. Detalle: [HARDWARE_W109](HARDWARE_W109-es.md). Tras probar, recoger W109 y revisar PWFM/PWDELETE para identificar la entrada bloqueante o confirmar borrado real.

Desktop siguiente: test.lnk existe por FTP pero no aparece. Explorer también descarta accesos si no obtiene icono del link/destino (.txt sin icono PE). Añadir fallback de icono y archivos/carpetas, y verificar refresco; no atribuir todo a notificaciones. No mezclar esta mejora con la iteración de borrado.

## Referencia anterior: W108

W107 abrió Desktop/test.txt dos veces con Notepad y cerró con 0; sesión 20261102T164857Z descargada. El usuario informa fallos al renombrar carpetas y borrar árboles. W108 (02.07) habilita rename real con reparación de rutas de descriptores/cwd y sustituye el borrado silencioso de WFM por recorrido Win32 que cierra Find antes de recursión, no sigue reparse points y reporta errores. El builder recompila y sustituye explícitamente el objeto FS; base intacta. Comprobación puntual de rename en Linux pasó; primera ejecución DrvFS EACCES conservada. Paquete compilado y subido con lectura de vuelta verificada: /data/pkg/orbis-win-W108-ec2dd685205f.pkg. Informe: reports/wine-hardware-w108/transfers/20261102T170417Z.json. 548 archivos verificados (545 presentes, 3 subidos), sin fallos de permisos. W107 retirado después de verificar. Prueba PS4 pendiente. Sin matriz local. Detalle: [HARDWARE_W108](HARDWARE_W108-es.md).

Siguiente mejora acordada como consulta: desktop actual sólo muestra *.lnk; archivos/carpetas reales requieren ampliar la enumeración/presentación de Explorer. Terminar primero esta iteración; calibración CPU/GPU sigue aplazada.

## Referencia anterior: W107

W106 abre EXE correctamente según el usuario; logs 20261102T151517Z confirman PWOPEN abierto=1 en hilo 0024 e invitados PE64. Textos fallan sin reinicio. Causa: asociaciones en HKCU Classes, pero HKCR de Wine fijado consulta HKLM Classes sin fusión. W107 (02.06) mueve asociaciones a system.reg; no recompila WFM, Explorer ni DLL. Paquete compilado; comparación de hashes confirma sólo los dos registros distintos en el runtime. Transferencia verificada: /data/pkg/orbis-win-W107-df1d1deadc9a.pkg. Informe: reports/wine-hardware-w107/transfers/20261102T164351Z.json. 548 archivos verificados (546 presentes, 2 subidos), sin fallos de permisos. W106 retirado después de verificar. Prueba física pendiente. Detalle: [HARDWARE_W107](HARDWARE_W107-es.md). Tras «Ya la probé», recoger W107 y comprobar Notepad con argumento del texto, contenido visible, WFM/EXE y Start.

## Referencia anterior: W106

El usuario confirmó que W105 lista unidades y archivos. Abrir result.txt o vkspin64.txt reinicia el título: los logs de la sesión 20261102T145327Z muestran switch_program con el documento, luego c000007b y vuelta al escritorio.

W106 (02.05), compilada y subida con lectura de vuelta verificada: /data/pkg/orbis-win-W106-02a9368dc02f.pkg. Informe: reports/wine-hardware-w106/transfers/20261102T150943Z.json. 548 archivos verificados (536 presentes, 12 subidos), sin fallos de permisos. W105 retirado después de verificar. Prueba física pendiente. WFM envía la apertura al hilo del escritorio de Explorer mediante una copia validada/encolada; allí ShellExecuteEx resuelve la asociación. El prefijo asocia textos a Notepad. Kernelbase impide que un documento o un invitado fallido/no compatible reemplace el título. EXE PE64 compatibles abren hilos; PE32 concurrente devuelve error sin reiniciar. El arranque inicial PE32 y wineboot para salir son rutas aparte. Sin cambios al emulador. Mantiene listado W105 y métricas W104; calibración CPU/GPU aplazada. Detalle y prueba física: [HARDWARE_W106](HARDWARE_W106-es.md). Al recibir «Ya la probé», fetch-hardware.py --build W106 --host 192.168.68.104. Verificar texto visible en Notepad, WFM vivo, cierre y reapertura, Start, PWOPEN en hilo Explorer y ausencia de switch_program por documentos.

## Referencia anterior: W105

El usuario aplaza la calibración CPU/GPU y prioriza File Manager: Computer no muestra unidades. W105 (02.04) adapta GetLogicalDrives en kernelbase para enumerar raíces DOS realmente accesibles cuando WINE_PS4_GUESTS está activo; no depende del directorio de dispositivos que llenaría mountmgr. WFM verifica los handles/resultados de enumeración y lista archivos sin exigir ARCHIVE. Logs PWFS/PWFM permiten identificar acceso denegado o enumeración fallida.

WFM, DLL de invitados y paquete compilados y subidos con lectura verificada: /data/pkg/orbis-win-W105-cb9543e2725c.pkg. Informe de transferencia: reports/wine-hardware-w105/transfers/20261102T143252Z.json. 548 archivos verificados (539 presentes, 9 subidos), sin fallos de permisos. W104 retirado de /data/pkg después de verificar. Validación física pendiente. Mantiene las métricas y etiquetas CPU/GPU de W104. Detalle: [HARDWARE_W105](HARDWARE_W105-es.md). Tras probar, usar fetch-hardware.py --build W105 --host 192.168.68.104. Revisar Computer, C:, C:\orbis, cerrar/reabrir WFM y Start. No marcar funcional sólo por el arranque del escritorio.

## Referencia anterior: W104

W103 fue ejecutada y sus logs descargados en reports/wine-hardware-w103/physical/20261102T140357Z. Tres aperturas y tres cierres 0, sin marcador de crash; escritorio presentando cuadros. No consta salida final ni dos ciclos completos. GPU: 0,356–8,909 %, pérdidas 0. CPU rechazada: 16,666 % constante, reloj importado avanzando como tiempo real.

W104 (02.03) cambia CPU a getrusage(RUSAGE_SELF), usuario + kernel, y muestra las etiquetas CPU y GPU sin «app», a pedido del usuario. Mantiene Crema GPU y el muestreo en el frame. Compilada y subida con lectura de vuelta verificada; pendiente de prueba física. PKG: /data/pkg/orbis-win-W104-33b552761826.pkg. Informe: reports/wine-hardware-w104/transfers/20261102T141256Z.json. 548 archivos verificados (545 presentes, 3 subidos), sin fallos de permisos. W103 retirado de /data/pkg después de verificar. PKG SHA-256: 33b5527618262a29db545d5e108d9e96c63170f513336adf04d4a8315139e87f. Prueba física recogida: reports/wine-hardware-w104/physical/20261102T141838Z. 90 muestras: CPU 6,917–32,801 %, GPU 0,08–9,5 %, sin errores ni pérdidas GPU. CPU fija en 16,666 % resuelta en esta sesión; ambas métricas responden a carga. Tres aperturas y tres cierres 0, sin marcador de crash. No consta salida final ni dos ciclos; exactitud absoluta sin calibración independiente. Detalle: [HARDWARE_W104](HARDWARE_W104-es.md).

## Entrega anterior: W103

W103, APP_VER 02.02, compilada y subida con lectura de vuelta verificada: `/data/pkg/orbis-win-W103-913c7e7df41b.pkg`. Informe: `reports/wine-hardware-w103/transfers/20261102T135850Z.json`. 548 archivos verificados: 545 presentes y 3 subidos; sin fallos de permisos. W102 retirado de /data/pkg después de verificar. Evidencias locales conservadas.

MangoHud muestra CPU app (reloj CPU del proceso / tiempo / afinidad inicial) y GPU app (unión de intervalos GPU reales de Crema entre dispositivos GFX). Warmup, reloj no soportado o pérdida de contadores muestran N/A. Sigue el muestreo en el frame de W102, sin nuevos trabajadores de estadísticas. Consulta privada versionada; no se fabrican tiempos globales ni por núcleo. Sólo system.o de Wine Unix se sustituye por una compilación con la consulta; no se ejecutó el borrador CPU de prepare-wine-boot.py.

La primera prueba física rechazó CPU y registró GPU sin pérdidas (ver arriba). W102 sigue como referencia aceptada de dos ciclos. La próxima prueba es W104; al recibir «Ya la probé», usar fetch-hardware.py --build W104 --host 192.168.68.104 y revisar PWTELEM/PWHUD, deltas, pérdidas y cierres. Detalle y comandos: [HARDWARE_W103](HARDWARE_W103-es.md).

## Referencia física anterior: W102

W102, APP_VER 02.01, compilada y subida con lectura de vuelta verificada a la PS4 en 192.168.68.104:2121. Instalada y probada: dos ciclos con la capa cargada, seis aperturas y seis cierres 0, Start operativo y salida final 0 a los 63455 ms. Aceptación: `reports/wine-hardware-w102/physical/20261102T131731Z/acceptance.json`.

- PKG: `/data/pkg/orbis-win-W102-09be7a07d5eb.pkg`.
- SHA-256: `09be7a07d5eb38aa1b348d0821c949edefb5fd821f18c9fabca0cac0dbbed42c`.
- Informe: `reports/wine-hardware-w102/transfers/20261102T130927Z.json`
- Runtime: 548 archivos, 544 presentes y 4 subidos, sin fallos de permisos.
- W101 fue retirado de /data/pkg después de verificar. Copias locales y logs conservados.

[Detalle W102](HARDWARE_W102-es.md). W101 validó el control sin capa; W102 completó el mismo escenario con MangoHud cargado. No se afirma estabilidad general ni validación de sesiones largas, logging opcional o exactitud de porcentajes.

## Evidencia que condujo a W102

W096 permitió tres apps gráficas juntas pero aparecieron fallos después del cierre. W098 registró CE-34878-0 al cerrar vkcube, con el log cortado durante DLL_THREAD_DETACH de user32 en un worker. W099 quitó joins del bloqueo compartido y permitió cierres y recargas, pero tras otro ciclo hubo un acceso inválido en malloc nativo. W100 añadió exclusión mutua al asignador del SDK: se activó, pero no eliminó el CE-34878-0.

W101 desactivó la carga de MangoHud y completó dos ciclos: seis arranques y seis cierres 0 de glxgears/vkcube/vkspin, Start operativo y salida final 0 a 83829 ms. Se verificaron hud=0 y ausencia de PROCESS_ATTACH de libMangoHud. Logs: `reports/wine-hardware-w101/physical/20261102T125705Z/`, con analysis.md. Esto acota la ruta implicada, sin probar una causa exacta ni compatibilidad general.

## Cambio W102

MangoHud vuelve a estar enabled (ImplicitLayers DWORD 0). El muestreo hardware y las métricas FPS se ejecutan en el frame protegido, sin trabajadores que retengan parámetros de instancia. Se desactiva el observador del archivo: guardar y reiniciar OrbisDesk para aplicar configuración. PWHUD registra sampling=frame, fps_metrics=frame y config_watcher=disabled.

La adaptación evita esos servicios persistentes de la capa en el modelo de invitados dentro de un proceso. No cambia la política general de herencia de hilos de Wine. F2/logging y otros servicios opcionales no quedan validados. Puede cambiar el coste del frame; no se han corregido ni validado porcentajes CPU/GPU. Wine Unix, DLL de Wine, driver y heap W100 se conservan.

Fuentes: `tools/vk-h0/patch-mangohud-frame-sampling.py` sobre la copia WSL en `~/vk-h0/src/mangohud-win`. El checkout upstream se conserva. El registro de build de MangoHud y el manifiesto verifican hashes de DLL y fuentes compiladas.

## Entorno y preferencias vigentes

PS4 Pro Baikal, firmware informado 12.52, GoldHEN. Última IP .104; .107 era anterior. Usar siempre --host explícito. WSL Ubuntu-22.04 para compilar.

El usuario instala/ejecuta manualmente; no se usa BinLoader para lanzar estas apps. Omitir matriz local: compilar y verificar artefactos/transferencia y seguir con la prueba real. No marcar funcional por respuestas simuladas ni por capturas iniciales. El estado automático presented del recolector no equivale a passed.

Después de una subida completa verificada, retirar los PKG Wine anteriores de /data/pkg, conservando evidencias y paquetes locales. El uploader restringe los nombres/versiones y registra resultados. --timeout es 60 s por defecto; si FTP se detiene, reconectar o pedir reactivación sin declarar la entrega terminada.

Avisar que la nueva build está subida y presentar un botón Ya la probé mediante request_user_input_async. Al recibirlo, descargar logs y analizarlos. No iniciar la siguiente prueba física antes de avisar que terminó la entrega.

## Prioridad que originó W103

Los dos ciclos de W102 ya se recogieron y aceptaron para el escenario acotado. La siguiente prioridad indicada por el usuario es retomar los porcentajes CPU/GPU, ahora que el fallo de cierre no se reproduce en esa prueba. Mantener W102 como referencia de estabilidad. Para recopilar una nueva sesión de W102:

```sh
python3 tools/fetch-hardware.py --build W102 --host 192.168.68.104
```

Se comprobaron carga de la capa, política frame, seis cierres, reaperturas, Start y salida final. No sustituye una prueba prolongada. W103 usa APP_VER 02.02.

El borrador de tiempos CPU en tools/prepare-wine-boot.py NO se ha incorporado a estas builds; revisar su semántica y límites antes de incorporarlo, sin ejecutar ese preparador por rutina ni mezclarlo accidentalmente con otra corrección.

## Base funcional anterior y límites

W013 ejecutó PE32 bare mediante Wine/wowprospero en PS4 con resultado idéntico a Windows; W014 corrigió la salida al menú. Hay escritorio, mando/USB y aplicaciones PE64, Vulkan/RADV y OpenGL/Zink en hardware. [Wine](HARDWARE_W003_W011-es.md), [gráficos](HARDWARE_G001-es.md). Los invitados comparten proceso; no son procesos Windows independientes. Presentación Vulkan con copia a CPU/GDI. Geometry shaders generales, Direct3D/DXVK, juegos comerciales y rendimiento siguen pendientes. El cierre con la capa pasó el escenario descrito; sigue la precisión de telemetría antes de ampliar alcance.

## Validación adicional del emulador: escritorio W284

El fork Linux ya presenta el escritorio de W284 en WSLg. Correcciones generales al cargador ET_SCE_EXEC, saltos y señales libkernel; seis comprobaciones OpenOrbis aprobadas en emulador. Imagen por copia CPU; PE32 nativo y RADV/GNM siguen pendientes. Ver [evidencia y reproducción](SHAD_W284_DESKTOP-es.md). Esta comprobación usa el ELF W284 conservado y no clasifica las fuentes W286 concurrentes como validadas.
