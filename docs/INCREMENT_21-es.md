# Incremento 21: mappings privados y protección de ntdll

[English](INCREMENT_21.md) | [Español](INCREMENT_21-es.md)

**Se corrige el bloqueo de mprotect del incremento 20 en el fork Linux. Wine completa la carga y reubicación de ntdll PE64 y alcanza la fase de inicialización Windows. El EXE todavía no se ejecuta mediante Wine.** Se adapta también el slot de syscalls a páginas grandes. El bloqueo siguiente es instalar y verificar GS; la ejecución final termina limpiamente con 93, sin aserción ni timeout.

## Corrección del emulador

El parche 0010 propaga MAP_PRIVATE hasta el mmap del host Linux. Antes, la ruta de archivos usaba siempre MAP_SHARED. Un archivo abierto sólo lectura podía mapearse para lectura, pero el intento posterior de habilitar escritura durante las relocaciones terminaba en una aserción por EACCES. Ahora el mapping privado usa copy-on-write real del kernel Linux: su memoria puede modificarse sin cambiar el archivo original. Los mappings compartidos conservan su comportamiento compartido.

La región virtual registra si puede habilitar escritura. Este límite se obtiene al crear el mapping y no consultando un descriptor que podría haberse cerrado o reutilizado. Una petición sobre un mapping compartido de archivo sólo lectura devuelve EACCES antes de cambiar protecciones. Se comprueba toda la petición antes de aplicarla, evitando cambios parciales si otra región del rango la prohíbe. Regiones con límites distintos no se fusionan.

También se conserva el tipo de región antes de dividir o fusionar sus nodos, para no consultar una referencia invalidada después de MergeAdjacent. El límite superior del rango se calcula evitando el overflow de addr + size.

La selección copy-on-write nueva se habilita para archivos del host en Linux. Se conserva la política previa que reduce los permisos iniciales de mappings de archivos sólo lectura; la ampliación probada es mediante sceKernelMprotect. Los backends virtuales que ya poblaban copias anónimas mantienen esa ruta previa. Windows, macOS, los backends virtuales y PS4 real no se consideran validados por estas pruebas de archivos montados en Linux. No se agrega ningún export Orbis ni una excepción específica para Wine o para un juego.

## Prueba OpenOrbis

`native/wine_file_mapping_probe.c` usa exclusivamente llamadas de archivos y memoria de OpenOrbis. Comprueba diez escenarios:

- Ampliar a lectura/escritura un mapping privado de archivo abierto sólo lectura.
- Escribir en esa copia conservando el archivo original.
- Escribir en un mapping privado de archivo abierto lectura/escritura.
- Aislamiento entre dos vistas privadas del mismo archivo.
- Mapping privado válido después de cerrar y reutilizar su descriptor.
- EACCES en una vista compartida sólo lectura, incluso si su descriptor se reutiliza para abrir el archivo con lectura/escritura.
- Denegación atómica sobre un rango mixto de regiones privadas y compartidas, conservando las protecciones originales de ambas.
- Escritura compartida visible tanto desde el archivo como desde otra vista compartida.
- Páginas privadas ya modificadas conservan sus datos al cambiar el archivo por una vista compartida.
- Vista compartida con permiso de escritura conserva su capacidad de protección después de cerrar y reutilizar el descriptor para lectura.

En el fork pasan los diez casos, sin stubs ni timeout. En el oficial, el mismo ELF reproduce la aserción de protección en la primera ampliación privada y queda bloqueado. La prueba queda disponible para ejecución futura en hardware.

## Avance real de Wine y siguiente bloqueo

Se mantiene el prefijo externo, WINEARCH=wow64, el servidor dentro del proceso y la política de imágenes reubicadas del incremento 20. No se reemplazan las DLL de Wine por los módulos sintéticos de los incrementos 16 a 18.

El intento preparado alcanza `ntdll_pe64_ready`, después de cargar, reubicar y resolver las funciones de ntdll PE64. Después carga ntdll PE32 y apisetschema y alcanza `entering_windows_initialization`. Se comprueba que los archivos de ntdll PE64 y PE32 conservan los hashes originales en el archivo de ejecución, incluso después de las modificaciones en memoria que realiza el cargador.

La primera corrida se detenía después en anon_mmap_fixed: pedía una página de 4096 bytes en `0x7ffe1000` sobre un host de páginas de 16384. La traza incorporada registra esos parámetros en `anon_alignment_blocker`, sin modificar la petición. Esa dirección es el slot del dispatcher x64, situado dentro de la misma página anfitriona que KUSER_SHARED_DATA. No corresponde a una nueva asignación de pila.

Se adapta el parche LGPL de prospero-win `0530-ntdll-syscall-dispatcher-slot-in-large-host-page.patch`, conservando original, atribuciones y hashes en el manifiesto. Su requisito de una sección de datos del usuario de al menos una página anfitriona ya estaba cubierto por el parche 0102. Se usa la vista compartida existente: protección RW de los 16 KiB, escritura del puntero en el slot y restauración de protección R. La adaptación Orbis comprueba los dos resultados de protección con el adaptador verificado, lee el puntero de vuelta y sólo entonces registra `dispatcher_slot_ready`. Cualquier fallo termina con error explícito, sin simular el estado listo ni reemplazar el contenido de la página por un mapping anónimo.

La corrida final verifica el slot en `0x7ffe1000`, con página anfitriona de 16384 bytes. Ya no aparece la aserción de mprotect ni la de alineación. A continuación, sysarch sigue entrando en CommonStub: no instala ni devuelve una base GS real. El adaptador detecta la falta de instalación/verificación y termina con código 93 (`0x5d`). No hay timeout ni violación de acceso en este intento final. El informe mantiene `invoked_stubs: ["sysarch"]`; no se contabiliza como Wine funcional. Las corridas previas con la aserción se conservan como exploratorias.

## Validación y artefactos

Se repiten los seis casos del contrato de offsets de mmap, las doce comprobaciones del prefijo y la matriz de 31 ejecuciones del incremento 18. Se mantienen sus resultados esperados, incluyendo el bloqueo del emulador oficial. Los diagnósticos services y GS y el arranque con prefijo vacío conservan los resultados anteriores. Después de la última adaptación del overlay se repiten con el ELF definitivo el preflight, services, GS, el prefijo vacío e IPC, pipes, filesystem y metadata; estos cuatro últimos se contrastan también con la matriz anterior del mismo fork. La validación negativa del consumidor del prefijo se conserva del incremento 19; sus herramientas y el paquete se contrastan por hash y no se modificaron.

El índice principal es `reports/increment21/report.json`. Las corridas exploratorias se conservan aparte y no sustituyen las pruebas del binario final fijado. Los informes individuales conservan logs, configuración y runtime.tar.gz. Las cápsulas Wine y del emulador están bajo `reports/increment21/`, con hashes verificados. Wine_booted y windows_execution_verified permanecen en false; el prefijo sigue declarando ps4_runtime_ready: false.

## Reproducción

En Ubuntu 22.04/WSL, con las revisiones y parches fijados:

```sh
python3 tools/build-shad-linux.py --reuse-configure --jobs 12
python3 tools/build-wine-ps4.py --boot --all-unix
python3 tools/build-wine-ps4.py --boot --server
python3 tools/link-wine-boot.py
python3 tools/check-wine-file-mapping21.py --official
python3 tools/run-linux-wine.py --fork --prepared-prefix reports/increment15/prefix-package
python3 tools/check-increment21.py
python3 tools/check-increment21.py --verify-only
```

`--collect-existing` reúne las ejecuciones guardadas en build/increment21-*.log. El verificador exige los marcadores reales de ntdll y del slot, el contrato de archivos y el bloqueo limpio de GS registrado. Si cambia, hay que investigarlo.

## Prioridades siguientes

1. Implementar y validar GS por hilo con accesos reales gs:, aislamiento entre hilos, TLS nativo preservado y restauración de la base. El diagnóstico --gs-services y el intento real de Wine deben superar este bloqueo.
2. Investigar dispatcher-mixed en Linux y conectar el contrato BTCpu* con el traductor, contextos de Wine, llamadas Unix, callbacks, excepciones e invalidación de código.
3. Ejecutar console32-bare.exe y después console32.exe mediante Wine, exigiendo archivo idéntico a Windows, hilo completado y salida 0.

Hardware PS4: pendiente.
