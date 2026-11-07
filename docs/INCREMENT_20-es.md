# Incremento 20: mmap, fallback de Wine e imagen principal reubicada

[English](INCREMENT_20.md) | [Español](INCREMENT_20-es.md)

**El fork ya devuelve EINVAL para offsets de archivo inválidos. Wine lee de verdad las secciones del EXE con su fallback y continúa hacia ntdll PE64.** La inicialización de ntdll todavía no termina: el siguiente bloqueo es una aserción del emulador al habilitar escritura para su reubicación. El EXE no se ejecutó mediante Wine.

## Corrección del fork

El parche 0009, commit `bcae5f261c86a79cf7b8ac8ef2bf3f7a9fb2a8c4`, valida el offset de archivo en posix_mmap antes de llamar a MemoryManager::MapFile. Los offsets negativos o no alineados a la granularidad Orbis de 16 KiB devuelven EINVAL. sceKernelMmap conserva el parámetro de salida cuando falla. La validación ocurre antes de modificar el mapa de memoria; no se cambia el comportamiento de mappings anónimos ni se añade una excepción para Wine o para un programa concreto.

La reproducción OpenOrbis ampliada pasa seis comprobaciones en el fork:

- Rechazo de offset `0xc00`, negativo y de 4 KiB no alineado a 16 KiB.
- Mapeo válido con offset de 16 KiB y lectura del patrón esperado del archivo.
- Rechazo del offset inválido con MAP_FIXED, sin cambiar el parámetro de salida.
- Conservación del contenido de la memoria existente después de esa petición fallida.

El mismo ELF en el oficial reproduce la aserción del incremento 19 en la primera petición. El contrato de offsets de la prueba sigue pendiente de validación en hardware. Los nueve parches reproducen el árbol fijado del fork.

## Carga real del EXE en Wine

Se agrega una traza al fallback existente de virtual.c que registra offset, bytes solicitados, bytes leídos y errno, sin modificar su resultado. En la corrida final se leen las cuatro secciones del EXE desde offsets `0x400`, `0x800`, `0xa00` y `0xc00`, con 1024, 512, 512 y 512 bytes respectivamente, sin errores. El nuevo EINVAL permite que se ejecute esa lectura en lugar de abortar el emulador.

La traza del cargador informa `STATUS_IMAGE_NOT_AT_BASE` (`0x40000003`), máquina I386 (`0x014c`), imagen en `0xed0000`. La base preferida `0x400000` no está libre. Ese estado informativo hacía que la ruta inicial intentara start.exe, que no está disponible y requeriría otro proceso.

Se adapta el parche de prospero-win `wine/patches/0130-ntdll-ps5-report-main-exe-load-failure.patch`: acepta únicamente STATUS_IMAGE_NOT_AT_BASE como imagen mapeada y deja la reubicación al cargador PE de Wine. Los demás errores se informan y terminan el proceso en lugar de probar start.exe. No se afirma que las relocaciones del EXE ya se hayan ejecutado. El bootstrap preparado establece además `WINEARCH=wow64`, para conservar el host x86-64 al cargar PE32. El prefijo vacío mantiene su comportamiento anterior.

El parche original es LGPL-2.1-or-later, como Wine y prospero-win. Se conservan sus atribuciones, el archivo adaptado y los hashes original/adaptado en boot-manifest.json, dentro de `prospero_patches`. La fuente original de Wine se mantiene intacta; los cambios se producen en el overlay Orbis.

## Nuevo bloqueo: protección del mapeo de ntdll

Wine abre `/data/wine/lib/wine/x86_64-windows/ntdll.dll` y lee sus secciones. La corrida final registra dieciséis fallbacks de lectura entre el EXE y ntdll, con los bytes solicitados efectivamente copiados. Después, load_ntdll llama a virtual_relocate_module porque la DLL tampoco está en su base preferida.

Al cambiar protecciones a lectura/escritura, el emulador cae en `address_space.cpp:815 Protect`, con `mprotect failed: Permission denied`. La ruta de archivo del host usa MAP_SHARED y no propaga la distinción privada del mapping hasta AddressSpace::MapFile. Esto requiere revisar tanto el contrato de error como la semántica de mappings privados y sus permisos. No se cambia en este incremento la política de permisos de archivos de Orbis.

La reproducción independiente `native/wine_file_protect_repro.c` abre un archivo sólo lectura, lo mapea con MAP_PRIVATE y PROT_READ, y solicita PROT_READ|PROT_WRITE. Tanto el fork como el oficial reproducen la misma aserción, sin Wine ni traductor. La prueba también comprueba que una escritura privada no altere el archivo si alguna plataforma permite completar la operación; ese camino aún no se validó.

El intento de Wine termina por timeout de esta aserción, sin CommonStub invocados. No se alcanzan `ntdll_pe64_ready` ni `entering_windows_initialization`. Wine_booted y windows_execution_verified permanecen en false.

## Validación y evidencia

Se repiten las 31 ejecuciones de la matriz del incremento 18 con el fork final, incluyendo la comparación con el oficial, y se conservan sus resultados esperados. Las pruebas de consola, lifecycle, veinte casos PE, memoria, archivos, hilos, IPC, pipes, directorios y metadatos del fork siguen pasando. El preflight de doce comprobaciones del prefijo también pasa con el ELF final. Services y GS conservan sus bloqueos documentados; el arranque con prefijo vacío conserva el rechazo de wineboot y el estado `0xc0000135`.

`reports/increment20/report.json` reúne los informes y distingue las pruebas aprobadas del bloqueo de Wine. Los paquetes de runtime individuales conservan el ELF exacto, el prefijo y los logs. Se mantienen las corridas exploratorias y la matriz anterior a la adaptación 0130; las utilizadas por el verificador corresponden al binario final. La cápsula del emulador registra un árbol limpio y su SHA256. El paquete de prefijo del incremento 15 no se modifica y mantiene `ps4_runtime_ready: false`.

## Reproducción

Desde Ubuntu 22.04/WSL, después de aplicar los parches fijados del fork:

```sh
python3 tools/build-shad-linux.py --reuse-configure --jobs 12
python3 tools/build-wine-ps4.py --boot --all-unix
python3 tools/build-wine-ps4.py --boot --server
python3 tools/link-wine-boot.py
python3 tools/check-wine-mmap20.py --official
python3 tools/run-linux-wine.py --fork --prepared-prefix reports/increment15/prefix-package
python3 tools/reproduce-wine-file-protect.py
python3 tools/check-increment20.py
python3 tools/check-increment20.py --verify-only
```

check-increment20 comprueba el contrato de mmap, el fallback real y el bloqueo de protección registrado. `--collect-existing` reúne los logs ya ejecutados bajo build/increment20-*.log. Un cambio del bloqueo requiere investigarlo y actualizar la reproducción, no asumir que la siguiente etapa funciona.

## Prioridades siguientes

1. Resolver la protección de mappings de archivo: comparar MAP_PRIVATE/MAP_SHARED, archivos abiertos sólo lectura y lectura/escritura, preservación del archivo tras escrituras privadas y devolución de errores sin abortar el emulador. Mantener una prueba OpenOrbis y separar lo validado en el fork de hardware.
2. Repetir la carga y reubicación de ntdll PE64 hasta alcanzar su marcador real de finalización. No basta con que todas sus secciones hayan sido leídas.
3. Validar GS por hilo con accesos reales gs:, aislamiento, TLS nativo y restauración.
4. Investigar dispatcher-mixed en Linux e integrar BTCpu* con contextos, llamadas, callbacks, excepciones e invalidación de traducciones.
5. Ejecutar console32-bare.exe y console32.exe mediante las DLL reales de Wine, con resultado idéntico a Windows, hilo completado y salida 0.

Hardware PS4, gráficos, entrada y audio continúan pendientes.
