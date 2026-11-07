# Incremento 15: identidad de archivos, symlinks y prefijo externo

[English](INCREMENT_15.md) | [Español](INCREMENT_15-es.md)

**Existe un prefijo de Wine inicializado por wineboot y verificado con console32-bare.exe, pero sólo con Wine nativo en Linux (WSL). El EXE todavía no se ejecuta mediante Wine dentro de shadPS4.** La ejecución PS4 sigue usando el prefijo vacío y termina con STATUS_DLL_NOT_FOUND, igual que en el incremento 14.

## Adaptación del emulador

El parche `0008` del fork (commit `bf96b33d43c3ebbe842486b42944203d7892fb00`) conserva la identidad de los archivos del host. Así, stat y fstat del mismo archivo, y de dos enlaces duros, devuelven igual `st_dev`/`st_ino`, y archivos distintos se distinguen. También expone lstat y readlink para symlinks, con límites de buffer y errores de enlace roto. Los descriptores abiertos sobreviven al renombrado de su archivo o directorio. El backend de Wine deja de excluir `readlink.lo` del SDK y usa estas rutas. No se inventa semántica de lstat: sigue rigiendo la regla del incremento 9.

## Validación en shadPS4

Pasan nueve comprobaciones OpenOrbis en `--metadata-services` en el fork Linux:

- Identidad de archivo y de enlace duro; diferencia entre archivos distintos.
- Coincidencia entre stat y fstat.
- lstat y stat sobre un symlink a archivo.
- readlink con buffer exacto y truncado, sin escribir fuera del límite.
- Symlink colgante, y errores de readlink sobre un archivo común y una ruta inexistente.
- Identidad de directorios.
- Renombrado de un archivo y de un directorio con descriptores abiertos.

La misma ELF en shadPS4 oficial bloquea las nueve pruebas, invoca el stub `readlink`, termina con 92 y el cierre agota el timeout. Ese resultado se guarda aparte. `check-increment15.py` repite además las regresiones: files, threads-adapter, pe-dll-relocated, vm-stress, ipc, pipes, filesystem y metadata pasan; services, gs y wine mantienen sus bloqueos esperados.

## Prefijo externo (Wine nativo en el host)

`tools/build-host-wine-closure.py` compila en el host las DLL PE i386/x86_64 necesarias para `wineboot --init`, siguiendo imports y `DELAYIMPORTS`. La configuración es `--enable-archs=i386,x86_64 --without-x --without-freetype`. `tools/build-host-wine-unix.py` agrega las bibliotecas Unix y los datos NLS/winmd.

Los cuatro primeros intentos de `tools/prepare-host-prefix.py` fallaron. Faltaban módulos de la clausura, y el último abortó porque wineboot llamó a `wininet.dll.InternetOpenW`, una carga diferida sin compilar. Con la clausura completa (119 módulos), dos corridas consecutivas pasan:

- `wineboot --init` sale con 0 y wineserver se cierra limpio antes y después.
- `console32-bare.exe` escribe `sum=500500;thread=ok;dll=ok\r\n` y sale con 0.
- Los tres archivos de registro existen y no hay errores de copia de setupapi.

Los hashes del registro cambian entre corridas porque los `.reg` incluyen marcas de tiempo, así que el prefijo no es reproducible byte a byte. Siguen faltando el driver gráfico (explorer y COM registran errores sin ventana) y unas 30 DLL que `wine.inf` intenta registrar (mshtml, urlmon, windowscodecs, quartz…). Para el EXE de consola no son necesarias; para GDI sí lo serán.

`tools/package-wine-prefix.py` empaqueta la primera corrida para un preflight posterior en `/data/wine-prefix`. Reubica `c:` y `z:` como enlaces relativos, omite `com1..8` y excluye `wow64cpu.dll`, porque el proveedor de CPU del host no es el traductor PS4. Copia el EXE a `C:\orbis\console32.exe`. El manifiesto registra las 497 entradas con su hash, y declara `ps4_runtime_ready: false`.

## Reproducción y evidencia

```sh
python3 tools/build-host-wine-closure.py
python3 tools/build-host-wine-unix.py
python3 tools/prepare-host-prefix.py
python3 tools/package-wine-prefix.py reports/increment15/prefix-producer/<corrida> reports/increment15/prefix-package
python3 tools/check-increment15.py
python3 tools/check-increment15.py --verify-only
```

`reports/increment15/report.json` indexa las ejecuciones, el emulador y la sección `host_prefix`. El verificador contrasta el hash del informe productor y del archivo empaquetado. Las corridas del productor están en `reports/increment15/prefix-producer/` (cuatro bloqueadas y dos aprobadas). La cápsula del emulador está en `reports/increment15/emulator-capsule/`. Hardware: pendiente.

## Próximo hito

Pista Wine: montar el prefijo empaquetado en la ejecución PS4 y definir una política de arranque que lo consuma sin lanzar wineboot en el modo de un único proceso. Después siguen ntdll PE64, GS por hilo y el proveedor WoW64 con el traductor.

En paralelo, el incremento 16 abre un hito intermedio: ejecutar console32-bare.exe con el loader PE32 propio y un kernel32 mínimo, sin Wine.
