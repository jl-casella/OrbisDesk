# Compatibilidad al iniciar guests: candidata 04.59

[English](GUEST_COMPATIBILITY.md) | [Español](GUEST_COMPATIBILITY-es.md)

Esta candidata conserva los cambios de rendimiento, perfiles de renderer y controles de la 04.58. Agrega fixes de versión de Windows por guest y presión de descriptores, además de correcciones en APIs usadas por juegos e instaladores hijos. Falta validar en hardware.

## Half-Life

La corrida física run-0013 en la PS4 Pro Baikal, firmware **12.50**, llegó a hl.exe y a _wassert de UCRT. El cuadro “Wine C++ Runtime Library” indicaba **g_pFileSystem, launcher.cpp:439**. Era una aserción, no un error por falta del runtime.

La FileSystem_Stdio.dll de GoldSrc instalada tiene SizeOfImage=0x10000 en el PE. La corrida registró una filesystem_stdio.dll de 0x5e000, consistente con la DLL de Source usada por juegos anteriores. Wine usaba el EXE anfitrión del mundo como directorio de aplicación, mientras que SetDllDirectory es compartido.

LdrGetDllPath ahora toma el directorio del EXE del guest que llama como directorio de aplicación. Las búsquedas explícitas APPLICATION_DIR y DEFAULT_DIRS también lo usan. Las rutas alteradas, las búsquedas limitadas al sistema y el proceso raíz conservan sus reglas. La ruta se copia bajo el lock del loader. Esto no crea espacios de nombres aislados para DLL.

## Versión de Windows por EXE

Wine Configuration → Applications ya ofrece el selector. Ahora kernelbase lee HKCU\Software\Wine\AppDefaults\<exe>\Version para el guest real y aplica las restricciones de su manifiesto/PE, en lugar de la respuesta que Explorer guardó para el proceso. GetVersionExA y GetVersion delegan en GetVersionExW.

El mapeo importado cubre desde XP hasta Windows 11. Esto no cambia todas las APIs de versión de Wine/NT. Se siguen aplicando los límites de compatibilidad de Windows según el manifiesto.

El resultado se inicializa una sola vez por guest, incluidas las llamadas concurrentes. Las consultas repetidas no vuelven a abrir el registro ni a recorrer los recursos. Hay que reiniciar esa aplicación para aplicar otra versión; un nuevo guest recibe una caché independiente.

## Descriptores de archivo altos

Un descriptor recién recibido, cacheable y de archivo regular o directorio, cuyo número sea **512 o superior**, usa la ruta needs_close existente en Wine en vez de quedar en la caché del cliente. Quien llama cierra la copia temporal después de usarla; el handle del servidor sigue válido y las operaciones siguientes pueden pedir otra copia.

Los descriptores menores y los de otros tipos conservan su política. Esto no expulsa entradas ya cacheadas ni aumenta el límite del kernel. PWFS fd_cache off registra el primer uso. La preparación de boot y el builder del mundo comparten una transformación con verificación de contexto; el título y el helper de proceso separado consumen el objeto recompilado.

## Hijos de instaladores

El [fallo reportado de WiX Burn](https://github.com/jl-casella/OrbisDesk/issues/64) involucra un relanzamiento en clean room y handles de archivo heredados. El prefijo ya contiene runtimes de VC++.

La candidata corrige estos problemas de APIs del proceso compartido:

- Los helpers WinMain narrow/wide de UCRT analizan los argumentos de cada guest sin leer ni sobrescribir el puntero que cacheó el proceso raíz.
- Durante la carga de un hijo, las consultas de argumentos y módulo usadas por los inicializadores de DLL seleccionan al hijo en carga, en lugar del padre.
- DuplicateHandle reconoce los eventos de finalización registrados de guests como referencias a la tabla de handles del anfitrión compartido. Hace la duplicación real y conserva acceso, herencia, flags de cierre del origen y errores; los eventos arbitrarios siguen siendo handles de proceso inválidos.
- GetProcessId reconoce esos handles registrados e informa el PID compartido que ya devuelve CreateProcess. TerminateProcess distingue el evento de finalización del guest actual del handle de otro guest, para que el PID compartido no convierta un pedido de terminar al hijo en la terminación del padre.

PWBURN startup comprueba la identidad de los argumentos del hijo; PWBURN inherited comprueba la validez real de los handles de archivo attached/self antes de entrar. Estos diagnósticos no imprimen líneas de comandos completas. No se reemplaza ningún instalador por un stub exitoso ni se inventan valores del registro que indiquen prerrequisitos instalados.

Estos fixes no implementan el ejecutor de scripts de instalación que falta en Steam nativo ([issue 63](https://github.com/jl-casella/OrbisDesk/issues/63)), aislamiento completo de procesos o virtualización general de handles heredados. Burn, la instalación MSI y GTA IV todavía necesitan validación completa en consola.

## Validación

La prueba de anfitrión tests/test_guest_launch_compat_host.py aplica las transformaciones canónicas a las fuentes fijadas de Wine y ejecuta las funciones resultantes bajo AddressSanitizer/UndefinedBehaviorSanitizer con modelos de sus interfaces. Cubre umbral y tipos de descriptores, argumentos WinMain de raíz/padre/hijo, comillas, identidad del hijo en carga, argumentos y errores de la duplicación real, modos de búsqueda de DLL y selección de versión/manifiesto por EXE. La compilación PE32/PE64 comprueba por separado el ABI real de Wine.

También comprueba la reutilización de la caché de versión y el reintento si falla su inicialización, las consultas de PID y la protección para no confundir el handle de proceso del hijo con el proceso propio del padre.

Después de instalar la candidata y el runtime correspondiente, probar Half-Life primero tras reiniciar OrbisDesk y luego después de cerrar otro juego Source. Para GTA IV, seleccionar Windows 10 para el EXE de launcher correspondiente en Wine Configuration y volver a probar el instalador real del prerrequisito. Revisar juntos PWGUEST version, PWFS, PWBURN, logs del instalador y salidas de los guests. Las pruebas de anfitrión y la compilación no constituyen aceptación en PS4.

## 04.60: presentación de píxeles empaquetados

El usuario llegó a Half-Life en la 04.59, pero informó colores verde/magenta, presentación en ventana y un escritorio colgado después de salir. La corrida física run-0026 informó VK_FORMAT_A4R4G4B4_UNORM_PACK16 (1000340000): una fila de 640 píxeles tenía 1.280 bytes. El puente de presentación la interpretó como píxeles de 32 bits, envió un stride de 320 píxeles y disparó el fallback global de la composición por GPU. GDI también interpretaba esos píxeles empaquetados como BGRA de 32 bits. El cierre del propio Half-Life terminó con estado 0; no quedó demostrada la respuesta del escritorio en pantalla.

La 04.60 convierte los cuadros empaquetados 4444, 565 y 5551 soportados a BGRA en memoria persistente, legible por la GPU y propiedad de la ventana. La memoria se reutiliza entre cuadros, se redimensiona con seguridad y se libera al olvidar la swapchain o destruir/depurar la ventana. El compositor espera a que la GPU termine antes de retornar; la conversión/reutilización y la liberación quedan bajo su lock de pantalla. Se mantienen los metadatos de capa de imagen y el ajuste a pantalla completa. Los cuadros BGRA/RGBA existentes de 32 bits conservan su ruta sin copia.

El formato, las dimensiones, el stride y la aritmética de tamaños se comprueban antes de publicar el estado de la capa. Una entrada desconocida o inválida no puede enviar una capa inválida y desactivar el compositor del escritorio. El fallback GDI usa la misma conversión, con filas compactas de 32 bits y un buffer temporal consumido antes de liberarlo. PWPIXELS layer informa formato/stride de origen y conversión; PWPIXELS rejected diagnostica entradas inválidas con límite de mensajes. Esto no extiende la generación de fotogramas a fuentes empaquetadas de 16 bits.

La prueba tests/test_present_pixels_host.py ejecuta el conversor y las entradas del driver preparado bajo ASan/UBSan: vectores de colores primarios/alfa, filas con padding y desalineadas, propiedad del buffer persistente, fallo de asignación, cambio de tamaño, notificaciones de swapchains anteriores, búsqueda de ventana hija, rechazo sin fallback global, ruta de 32 bits conservada y ciclos de cierre/reapertura. También comprueba la liberación en las rutas de destrucción de ventana. La compilación nativa y estas pruebas no constituyen aceptación en PS4. Colores, pantalla completa, salida y respuesta del escritorio todavía requieren una nueva prueba física; no se afirma haber corregido un deadlock independiente del escritorio.

## 04.61: límite de copias de descriptores retenidas por el cliente

En la prueba de 04.60 el usuario llegó al juego en Half-Life. run-0029 registra la conversión nueva de píxeles empaquetados sin fallback de composición GPU; no registra un ciclo de cierre/reapertura normal. GTA IV en run-0031 renderizó mediante DXVK pero registró EMFILE al abrir carpetas del mapa/interiores, seguido de 200 lecturas fallidas al obtener el descriptor. Había 664 descriptores visibles en el primer fallo: 271 archivos regulares, 205 extremos de pipes y 155 sockets; RLIMIT_NOFILE informó 13.952. No está establecido qué recurso exacto del kernel provoca EMFILE. Las esperas posteriores del loader lock ocurrieron tras terminar el juego a la fuerza y cerrar WFM, no antes del bloqueo de carga.

El umbral numérico de fd de 04.59 no limita suficientemente las copias del cliente. 04.61 limita a 64 las copias retenidas de archivos regulares/directorios por cliente nativo, bajo el mutex de caché de Wine. Las copias adicionales usan el contrato existente needs_close y las cierra la operación que las adquirió; se conserva el handle del servidor y sus reglas de posición, compartición y acceso. No se expulsa una copia de caché que otro hilo pueda estar usando. El cierre normal de handle o la duplicación con cierre de origen libera el cupo; sockets y otros tipos conservan su política, y sigue vigente la regla >=512.

Los errores transitorios de recursos de descriptores/memoria ya no se guardan como entradas negativas permanentes. PWFS fd_cache budget marca el primer desvío por cupo; PWFS fd_lookup_failed registra como máximo 16 fallos de recursos con estado y cantidad de copias retenidas. Los informes nativos de EMFILE siguen visibles. Las operaciones sin caché requieren más solicitudes al servidor; deben medirse ese costo y el margen recuperado en consola.

tests/test_fd_budget_host.py ejecuta las funciones preparadas de caché y adquisición de Wine bajo ASan/UBSan. Un límite real de host de 256 descriptores reproduce el agotamiento sin límite de caché; la ruta limitada atiende 160 archivos simultáneos del servidor, conserva el uso concurrente de descriptores prestados, reintenta fallos transitorios y libera todos los cupos durante ciclos repetidos. Es evidencia de host. La carga de GTA IV, el margen físico de descriptores y el cierre quedan pendientes de validación en consola. El error de ruta del launcher, los errores de IPC/navegador de Social Club y el fallo pendiente de inicialización de Riched20 en el redistribuible son problemas separados sin resolver; esta candidata no afirma corregirlos.

## Seguimiento tras la prueba de 04.61

El usuario informó que GTA IV siguió en el bucle de carga. run-0034 registró otra vez EMFILE en rutas del mapa/interiores con 658 descriptores visibles, seguido de 185 lecturas fallidas al obtener el descriptor. No apareció el marcador de desvío por cupo, por lo que no se demostró una reducción de presión con la política de 64 copias. La dirección del trampoline Vulkan coincide con el binario archivado de 04.61 y difiere de 04.60; los archivos SFO/SELF instalados no estaban disponibles por FTP. Es una correlación, no un hash leído del binario instalado.

En el primer EMFILE/ENFILE, el seguimiento agrega PWFS pressure (registros del adaptador agrupados por origen cliente/servidor, duplicados, rutas de juegos y archivos IPC), PWFS cache_snapshot (copias retenidas actuales/máximas y desvíos por cupo) y PWFS kernel_open_control. El origen del adaptador no representa propiedad exclusiva: SCM_RIGHTS comparte descripciones de archivo abierto y no todos los descriptores recibidos tienen registro del adaptador. El control del kernel abre la ruta fallida sólo para lectura con flags nativos 0 y cierra únicamente ese descriptor nuevo. No reintenta la operación solicitada, nunca repite flags de creación/truncado y no cambia el error que recibe el juego. El snapshot usa valores atómicos sin tomar el mutex del cliente mientras el servidor puede estar atendiendo a ese cliente. Se conservan los informes de tipos de descriptor y RLIMIT. Los fallos posteriores no repiten el escaneo completo ni la apertura de control.

En run-0032 Half-Life tenía frame gen activado, pero registró PWFG skipped image para su fuente empaquetada de 16 bits: pitch 2560 para 1280 píxeles. La conversión de colores ocurría después en el driver, tras el hook de captura del generador. El seguimiento difiere la captura de fuentes empaquetadas hasta que el driver produce su capa BGRA existente, propiedad de la ventana. La captura y el planificador de pantalla usan ese mismo puntero; no hay una segunda conversión ni se cuenta dos veces la presentación de origen. Se conserva la captura directa de 32 bits. El proceso hijo publica sus capas convertidas mediante el puente existente y no ejecuta un segundo generador. La publicación de FPS de salida sigue exigiendo fotogramas generados realmente mostrados; FPS VK continúa contando presentaciones reales del juego.

Las pruebas de host cubren el puente de fotogramas convertidos, callbacks anteriores, casos desactivado/sin límite/shadow, fallos de captura, captura de 32 bits conservada, límites del diagnóstico del primer fallo, errno original y control del kernel sólo de lectura. Las regresiones de archivos comparan con el fuente archivado de 04.61 usando ASan/UBSan; se actualizó la expectativa antigua ENOTSUP de renombrado de directorio al contrato de renombrado/directorio abierto que ya estaba implementado. La compilación nativa es independiente de la aceptación física. El diagnóstico de recursos de GTA IV y los fotogramas generados/mostrados de Half-Life requieren otra corrida en consola.

## 04.93: paquetes de Burn iniciados desde el Package Cache

Desinstalar o reparar un paquete de WiX Burn desde Agregar o quitar programas fallaba. Los redistribuibles de VC++, por ejemplo, terminaban con el estado 0x80070006 (E_HANDLE) o 1460 y no mostraban ninguna interfaz (04.92, run-0249 y run-0250 de 20261126T203327Z).

Desde otra carpeta, Burn se copia a `%TEMP%\{guid}\.cr\` y arranca esa copia como su hijo de sala limpia. Desde `C:\ProgramData\Package Cache` arranca el hijo desde su propia imagen. En este título una imagen es un solo módulo, así que W210 arrancaba ese hijo recién cuando terminaba el padre. Pero el padre espera a su hijo. A los 15 segundos (`PWGUEST relaunch ... parent_wait=258`), W252 terminaba al padre porque no tenía ninguna ventana visible. Al terminarlo se cerraban sus archivos, incluido el archivo `-burn.filehandle.self` que el hijo había heredado (`PWGUEST files ... closed=2`). `PWBURN inherited kind=1` mostraba entonces el handle cerrado (`valid=0 error=6`) o con su valor reusado por un objeto no heredable (`flags=0`), y el hijo fallaba al leer su propio paquete. Los inicios desde otras carpetas, como el del Rockstar Games Launcher, nunca pasaban por acá: su hijo corría desde `.cr` en otra base y conservaba `flags=0x1`.

Ahora, un invitado que arranca su propia imagen con un parámetro `-burn.` en la línea de comandos recibe una copia privada de esa imagen en `%TEMP%\OrbisDesk-burn-<hilo>-<tick>\`, como la que Burn hace de sí mismo en otras carpetas. La copia se carga como otro módulo junto al padre, que sigue corriendo, y los handles heredados del padre siguen abiertos. Un hilo espera a que termine el invitado de la copia y después la borra (`PWBURN own_image`, `PWBURN copy_removed`). Si no se puede hacer la copia, el inicio sigue como antes. Los demás programas que se reinician a sí mismos siguen usando W210.

El cambio se verificó generando el overlay de invitados y compilando kernelbase para x86_64 e i386. Falta la prueba en la consola: desinstalar y reparar el redistribuible x86 desde Agregar o quitar programas. El log debería mostrar `PWBURN own_image`, después `PWBURN inherited kind=1 valid=1 flags=0x1`, ningún `relaunch_later`, y la interfaz propia de Burn.
