# W214: el EXE de un invitado encuentra sus DLL y su descarga espera al loader (borrador)

[English](HARDWARE_W214-invitado-carga-borrador.md) | [Español](HARDWARE_W214-invitado-carga-borrador-es.md)

Borrador de la sesión lateral del navegador, para unir a `HARDWARE_W214.md`. Nada de esto se probó en la consola.

## Qué pasó en W212

Reporte: `reports/wine-hardware-w212/physical/20261104T170942Z` (`run-0001.log` y `run-0002.log`). El usuario dijo: "YouTube llegó a cargar pero se freezó en connecting. Lo quise cerrar del Task Manager pero no aparece en Applications. Reinicié OrbisDesk, lo abrí, cerré, y no pude volver a abrir."

**Lo que funciona:** la salida del reinicio del primer arranque (`detach skipped (exit)`, `own=25 remaining=0 rounds=5`, `parent_wait=0`).

1. **El Pale Moon reiniciado no carga** (`run-0002.log`, líneas 2030 a 2044): "Library mozglue.dll (which is needed by …palemoon.exe) not found", y también falta `VCRUNTIME140`.
   - El EXE de un invitado se cargaba con `LoadLibraryExW( ruta, 0, 0 )`. Así sólo se busca en el directorio de la imagen del proceso (el de explorer) y en el directorio actual.
   - Desde un acceso directo funcionaba porque `ShellExecute` de Wine pone como directorio actual la carpeta del acceso directo mientras arranca el programa.
   - El hilo auxiliar de W210 arranca con el directorio de explorer.
2. **Después de un cierre normal no se descarga nada** (`run-0002.log`, línea 2993): `kept: loader lock busy for 2 s`. Lo mismo pasa con los restos al arrancar, y los siguientes arranques terminan con estado 1. Otro hilo tenía el loader lock más de los 2 s del intento; en la consola, cargar una DLL es lento.
3. **YouTube se cuelga** (`run-0001.log`, líneas 4048 y 4626):
   - Aparece `PWHUNG … MozillaWindowClass "YouTube - Pale Moon"`.
   - El hilo principal (`0098`) no está bloqueado. Está en `mozjs.dll`, 20 marcos adentro, con los mismos marcos a los 70 s, `rip` dentro de una misma función y `r9 = e5e5e5e5` (el relleno de la memoria liberada).
   - Es la misma corrupción del motor de JavaScript de los fallos anteriores, vista como un bucle.
   - **Hipótesis, sin confirmar:** el JIT. La interrupción de SpiderMonkey y el monitor de cuelgues de Pale Moon suspenden el hilo principal y leen o cambian su contexto desde otro hilo, que en la consola pasa por las señales de W195.
   - **Prueba que lo separa:** abrir YouTube con el acceso directo "Pale Moon (no JIT)".

## Cambio

`tools/build-guest-hw.py` (kernelbase `process.c`), con `guest-load-w214.patch.py`:
1. **Las DLL desde la carpeta del EXE:** el EXE de un invitado dado con ruta se carga con `LOAD_WITH_ALTERED_SEARCH_PATH`. Sus importaciones se buscan primero en su propia carpeta, como para la imagen de un proceso. Eso vale también después de que un invitado llamó a `SetDefaultDllDirectories`, que Wine combina con la carpeta del EXE.
2. **La espera por el loader lock:**
   - La descarga al salir espera hasta 30 s y registra el dueño del lock cada 5 s (`waits for the loader lock, owner …`).
   - La pasada de restos al arrancar sigue con 2 s.
   - Al arrancar ya no espera la descarga de otro invitado (`leftovers skipped: another unload runs`), porque corre en el hilo de explorer.

## Construcción

1. `python3 tools/build-guest-hw.py`.
2. `tools/link-wine-boot.py`.
3. `tools/build-wine-hardware.py`.

## Prueba física

1. Arrancar OrbisDesk y abrir Pale Moon. Se reinicia solo una vez, y tiene que aparecer la ventana.
2. Cerrarlo y volver a abrirlo dos veces.
3. Abrir YouTube con "Pale Moon (no JIT)".
4. **Qué buscar en el log:**
   - `relaunch … parent_wait=0`, y después `Loaded … mozglue.dll` desde la carpeta de Pale Moon;
   - en cada cierre, `remaining=0` (si hubo espera, `waits for the loader lock, owner …`).

## No verificado

- Nada se probó en la consola.
- El cambio se aplicó sobre copias de los fuentes, y `process.c` pasa `-fsyntax-only` con mingw. El builder no se corrió.
- No se sabe qué hilo tenía el loader lock en W212; la traza nueva lo dice.
