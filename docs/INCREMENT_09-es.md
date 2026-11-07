# Incremento 9: memoria, rutas y archivos del lado Unix de Wine

[English](INCREMENT_09.md) | [Español](INCREMENT_09-es.md)

Se compilan cinco unidades Unix de Wine adaptadas a PS4 y se ejecutan funciones reales de ese código dentro del ELF de diagnóstico. **No se ha arrancado Wine completo ni ejecutado console32.exe con Wine.**

## Validación

| Entorno |Pasan| Bloqueados |Fallan|Tiempos de salida|
|---|---:|---:|---:|---:|
| Fork c6de833f6bec304b6f08c37520428ba2ed147a1a | 51 | 7 | 0 | 0 |
| Oficial v0.20.0, mismo ELF y doce fixtures | 23 | 34 | 1 | 0 |

[Fork](../reports/increment9-fork-final/report.json), [oficial](../reports/increment9-official-final/report.json), [comparación](../reports/increment9-fork-final/comparison.json) y [regresión](../reports/increment9-fork-final/regression.json). Se conservan los 55 resultados anteriores. Los tres diagnósticos nuevos pasan en el fork, sin invocar stubs. En el oficial pasan rutas/archivos y rechazo de funciones fuera de alcance; memoria se bloquea al ejecutar la página RX. La falla oficial sigue siendo vm-enforcement. Su cierre del proceso también conserva el problema conocido del incremento 1.

El fork no recibió cambios en este incremento. Hardware PS4: pendiente.

## Cambio de plataforma

`pw_wine_platform` usa las mismas primitivas kernel que el backend PS4 probado: reserva exacta sin reemplazo, mapeo flexible, protección y liberación. Los mapeos son propiedad de Wine y no entran en el registro de imágenes PE/JIT. Se exigen dirección y tamaño alineados a 16 KiB; otros flags o protecciones inválidas se rechazan. PROT_NONE queda reservado sin consumir memoria flexible.

Orbis puede devolver ENOMEM cuando la dirección está ocupada. Wine necesita EEXIST para continuar buscando otra dirección. El puente convierte ese error solamente si sceKernelVirtualQuery demuestra un solapamiento; si no, conserva el error original. No se confunde agotamiento de memoria con una colisión.

La función real anon_mmap_tryfixed de Wine llama a ese puente. Wine virtual.c usa también protección/liberación PS4 y la ruta de host pages de 16 KiB, siguiendo la adaptación de prospero-win 0510. El allocator Windows completo aún no se ha ejercitado: sigue requiriendo el arranque y las otras unidades de ntdll.

Para las rutas se exigen HOME y WINEPREFIX absolutos, existentes, y un USER explícito. No se consulta una base de usuarios Unix ni se inventa un directorio home. El harness ejecuta set_home_dir y set_config_dir del loader de Wine con esos valores. La prueba usa directorios vacíos de ensayo: **no es un prefijo Wine inicializado**, y no ejecuta wineboot ni prepara registros de Windows.

## Dos incompatibilidades del SDK corregidas

El struct stat público del SDK tiene mode_t de 32 bits. La estructura del kernel usa mode/nlink de 16 bits y tiene st_size en offset 72, con tamaño total 120. Escribir el resultado del kernel directamente en el struct del SDK desplazaba el tamaño y otros campos. El puente recibe el formato kernel y convierte cada campo a la estructura pública; stat/fstat/lstat de Wine file.c pasan por él. Se comprueban tamaño y offsets del formato kernel al compilar. El layout se contrastó con el ABI de shadPS4, sin copiar su implementación de filesystem.

Además, lstat.lo de libc llama a fstatat.lo, que devuelve incondicionalmente ENOSYS. El SDK ya incluye una importación lstat de libkernel. La compilación genera una copia privada de libc.a y elimina únicamente lstat.lo para resolver esa llamada mediante la importación real. El SDK original permanece intacto. Los hashes original/derivado y los desensamblados acompañan la evidencia.

Se comprobó lstat sobre un archivo ordinario. No se validaron enlaces simbólicos: en la revisión fijada del emulador, posix_lstat delega en posix_stat. No se afirma semántica no-follow ni funcionamiento de dosdevices de un prefijo completo.

## Pruebas nuevas

- **wine-memory:** siete comprobaciones. Reserva exacta, colisión preservando datos, RW→RX y ejecución nativa con resultado 42, retorno a RW y liberación, reserva PROT_NONE, rechazo de entradas inválidas y solapamiento que empieza en una zona libre y alcanza una reserva posterior. Se llama a la función modificada de Wine, no a una copia de su implementación.
- **wine-paths:** diez comprobaciones. Validación de rutas y usuario, funciones reales de inicialización de directorios de Wine, escritura/lectura/seek, rename, stat/fstat/lstat y preservación de salidas ante ENOENT/EBADF, además del rechazo ENOTDIR. El archivo resultante se conserva entre los logs.
- **wine-unsupported:** verifica STATUS_NOT_SUPPORTED (0xc00000bb) y buffers sin cambios para CD-ROM y características de dispositivos. Esto es una prueba de rechazo correcto; ninguna de esas dos capacidades se declara funcional.

No se ejecutan NtCreateFile/NtReadFile/NtWriteFile completos: necesitan el servidor y el resto de ntdll. Las operaciones de archivo de la prueba usan libc/libkernel y el puente ABI; las funciones de rutas proceden del Wine real.

## Fuentes y compilación

Wine permanece en `490f6d5dcbb2a5047345b8af88d114bbcaad69a8`, sin modificaciones. `tools/prepare-wine-ps4.py` genera un overlay de cinco archivos y el parche `patches/wine/0001-ps4-memory-paths-files-cdrom.patch`. Se verificó su aplicación exacta con git apply --check y que la fuente original sigue limpia. Las adaptaciones de fstab y host pages se basan en los parches 0100/0510 de prospero-win, LGPL-2.1-or-later, con sus atribuciones conservadas.

Compilan virtual.c, file.c, env.c, loader.c y cdrom.c. Dos harness incluyen las unidades completas de memoria y loader. Para el ELF de prueba se reducen objetos con ld -r --gc-sections, conservando sólo las funciones probadas y sus dependencias. Esto evita que el KEEP de OpenOrbis arrastre las tablas Unix todavía no portadas. Los objetos completos también se conservan. No se ignoran símbolos sin resolver ni se proporcionan servicios simulados para enlazar.

El snapshot guarda 56 entradas de compilación, las versiones de herramientas, los comandos, objetos completos y reducidos, libc derivada y el ELF exacto. Ver [cápsula de evidencia](../reports/increment9-fork-final/wine-platform/evidence.json). Las tres DLL PE32 y sus NLS son las del incremento 8; no se reconstruyeron ni se modificó la limitación del parser experimental que las rechaza.

En WSL, después de configurar el diagnóstico Unix del incremento 8:

```sh
python3 tools/build.py --with-wine-platform
python3 tools/build-wine-ps4.py --diagnose-remaining
```

El segundo comando devuelve error: las cinco unidades restantes que examina siguen bloqueadas. Sus comandos y errores actuales quedan en `build/wine-ps4/remaining-report.json` y los logs por unidad.

```powershell
./tools/run-probes.ps1 -IncludeWine -IncludeWinePlatform
./tools/run-probes.ps1 -IncludeWine -IncludeWinePlatform -Emulator build/shadPS4-win/shadps4.exe -EmulatorKind fork -EmulatorCommit c6de833f6bec304b6f08c37520428ba2ed147a1a -BuildManifest build/shadPS4-win/build-manifest.json
```

## Lo que sigue bloqueado

- signal_x86_64.c: machine/segments.h; contexto de señales y FS/GS pendiente.
- thread.c: sys/thr.h y operaciones de hilo FreeBSD por adaptar.
- sync.c: sys/event.h; sincronización/eventos PS4 pendiente.
- socket.c: FIONREAD y SIOCATMARK, sin sustituirlos por números no verificados.
- system.c: sysctl, información de CPU y cabeceras de dispositivos FreeBSD.

Todavía faltan enlace/carga de ntdll.so PS4, servidor dentro del proceso, prefijo inicializado y WoW64↔Unix. Las consultas de dispositivos y la semántica de enlaces del prefijo también requieren trabajo. El siguiente bloque es sincronización/hilos y contexto de señales, manteniendo estas pruebas como regresión antes de intentar el arranque completo de Wine.
