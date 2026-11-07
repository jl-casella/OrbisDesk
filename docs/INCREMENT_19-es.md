# Incremento 19: consumir el prefijo externo en shadPS4

[English](INCREMENT_19.md) | [Español](INCREMENT_19-es.md)

**El prefijo real del incremento 15 ya se monta y verifica dentro del fork Linux. Wine lo consume sin lanzar wineboot. El EXE todavía no se ejecuta mediante Wine.** El arranque encuentra un bloqueo anterior a la carga completa de ntdll PE64: el emulador afirma que falló un mmap de archivo con offset `0xc00` y no retorna el error al invitado. No se modificó el fork: sigue en `bf96b33`.

## Consumidor del paquete y política de arranque

El launcher admite `--prepared-prefix <directorio>` y `--prefix-preflight`. El segundo requiere el primero y termina después de las comprobaciones nativas, sin entrar en Wine. No se combina esta modalidad con los diagnósticos anteriores. En este incremento sólo admite el console32-bare.exe empaquetado y verifica que su hash coincida con la fixture local. Wine recibe `C:\orbis\console32.exe`.

El consumidor contrasta la revisión de Wine con el runtime compilado, el hash del archivo tar y cada entrada declarada. Rechaza entradas adicionales, duplicadas, padres que no sean directorios, rutas que escapen del destino, enlaces externos, registros ausentes, cabeceras PE inválidas y arquitecturas incorrectas. Las únicas entradas simbólicas admitidas son `c: -> ../drive_c` y `z: -> ../..`. La extracción usa una copia privada del archivo verificado, escribe los archivos antes de crear los enlaces y conserva intacto el paquete original.

El bootstrap borra la política heredada, inicializa las rutas y ejecuta el preflight. Sólo si pasa y se solicitó el arranque preparado habilita `WINE_PS4_EXTERNAL_PREFIX=1`. El overlay Orbis omite entonces la llamada automática a run_wineboot y registra `external_prefix_ready`. Esto consume una inicialización real realizada por Wine nativo en el incremento 15; no crea eventos falsos ni simula procesos. Los demás intentos de crear procesos siguen rechazándose. El cwd del cliente pasa a la carpeta física del EXE.

## Pruebas y criterios de aceptación

Pasan doce comprobaciones OpenOrbis en el fork:

- Cabecera de los tres registros de Wine.
- Destinos de los enlaces c: y z:, y resolución completa de una ruta por cada unidad.
- Identidad entre stat por la ruta DOS y fstat del archivo abierto.
- EXE PE32; ntdll, kernel32 y kernelbase PE32; seis módulos PE64, incluidos wow64 y wow64win.
- Ausencia del proveedor wow64cpu.dll del host.

El preflight sale con 0 y no entra en __wine_main. La comparación con el emulador oficial queda bloqueada: readlink invoca un CommonStub y no se valida el prefijo; el invitado sale con 95 y el cierre del emulador agota el timeout. No se contabiliza como aprobado en el oficial.

También pasan el paquete válido y ocho rechazos en el host: hash del tar incorrecto, archivo alterado, registro eliminado, enlace externo, ruta con escape, arquitectura incorrecta, revisión distinta y entrada duplicada. Las variantes de arquitectura, ruta y enlace actualizan sus hashes para comprobar esas validaciones más allá de la comprobación criptográfica. No se escribe en el destino antes de rechazarlas.

Se repite la matriz del incremento 18, guardándola en `reports/increment19/regressions-18/` mediante la nueva opción `--report-dir`. Conserva los resultados de consola, lifecycle, los veinte casos PE y las pruebas de archivos, hilos, memoria, IPC, pipes, directorios y metadatos. Los diagnósticos services y GS mantienen los bloqueos del incremento 15. El prefijo vacío conserva el rechazo de wineboot y STATUS_DLL_NOT_FOUND.

## Siguiente bloqueo real

Con el prefijo preparado se alcanzan `prefix_preflight_passed`, `server_ready` y `external_prefix_ready`. Wine resuelve la ruta DOS y abre console32.exe. Después intenta mapear una sección privada de 4 KiB, con offset de archivo `0xc00`. El fork propaga ese offset al mmap del host, que falla con EINVAL; `address_space.cpp` lo trata como una aserción fatal. No retorna al invitado y la ejecución termina por timeout. No se alcanza `ntdll_pe64_ready` ni `entering_windows_initialization`. No hay invocaciones de CommonStub en este intento preparado, aunque existen otros logs de funciones incompletas.

Wine ya contempla `EINVAL` por offset no alineado en `map_file_into_view` de virtual.c y dispone de un fallback de lectura. Ese fallback no puede ejecutarse mientras el emulador aborte antes de devolver el error. No se probó todavía que retornar EINVAL resuelva los demás requisitos de mapeo de imágenes.

`native/wine_mmap_repro.c` reproduce el problema sin Wine ni traductor: abre un archivo y solicita `sceKernelMmap(NULL, 0x1000, 3, 2, fd, 0xc00, &out)`. El resultado esperado del diagnóstico es EINVAL, conservando el parámetro de salida. Tanto el fork como el oficial reproducen la aserción y el timeout, sin retornar al programa. Se guardan por separado ambas ejecuciones. Este programa sirve también como prueba de hardware futura; no se ejecutó en consola.

## Reproducción

Desde Ubuntu 22.04/WSL, en la raíz del workspace:

```sh
python3 tools/build-wine-ps4.py --boot --all-unix
python3 tools/build-wine-ps4.py --boot --server
python3 tools/link-wine-boot.py
python3 tools/run-linux-wine.py --fork --prepared-prefix reports/increment15/prefix-package --prefix-preflight
python3 tools/run-linux-wine.py --prepared-prefix reports/increment15/prefix-package --prefix-preflight
python3 tools/run-linux-wine.py --fork --prepared-prefix reports/increment15/prefix-package
python3 tools/reproduce-wine-mmap.py
python3 tools/check-increment19.py
python3 tools/check-increment19.py --verify-only
```

check-increment19 comprueba la matriz y el bloqueo registrado; un resultado distinto requiere investigarse, no actualizar automáticamente la expectativa. `--collect-existing` reúne las ejecuciones ya realizadas a partir de sus logs en build, evitando repetirlas. El índice está en `reports/increment19/report.json`; los informes individuales y sus runtime.tar.gz permanecen en linux-wine-runs. Las cápsulas Wine y del emulador quedan bajo `reports/increment19/`. El manifiesto del paquete sigue declarando `ps4_runtime_ready: false`.

## Ruta siguiente hasta ejecutar mediante Wine

1. Corregir el contrato general de error de mmap en un parche separado del fork, validándolo primero con la reproducción OpenOrbis. Repetir Wine para comprobar el fallback de lectura y revisar la interacción entre páginas PE de 4 KiB y páginas Orbis de 16 KiB. El criterio es cargar de verdad las imágenes, no solamente cambiar el código de error.
2. Completar y verificar la carga de ntdll PE64. Si aparece otro bloqueo de plataforma, conservar la reproducción y resolverlo antes de avanzar.
3. Resolver GS por hilo: lecturas reales gs:, aislamiento entre hilos, preservación del TLS nativo y restauración de la base original. La prueba --gs-services debe pasar; almacenar sólo una variable no basta.
4. Investigar dispatcher-mixed en Linux antes de reutilizar esa frontera. Integrar el contrato BTCpu* con contextos I386_CONTEXT, TEB32, llamadas Unix y de sistema, callbacks, excepciones e invalidación del código traducido. Wine debe gestionar sus módulos reales; kernel32/msvcrt sintéticos no sirven como evidencia de esta integración.
5. Ejecutar console32-bare.exe y luego console32.exe mediante Wine. Exigir archivo idéntico a Windows, hilo completado y salida 0, sin atajos de los módulos propios. Sólo entonces marcar la ejecución Windows mediante Wine como verificada.

GDI, entrada, audio y Vulkan siguen después. Hardware PS4: pendiente.
