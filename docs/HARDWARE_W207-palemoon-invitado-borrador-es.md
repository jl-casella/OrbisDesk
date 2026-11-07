# W207: Pale Moon como invitado — archivos al terminar, traza del fallo, sin relanzar (borrador)

[English](HARDWARE_W207-palemoon-invitado-borrador.md) | [Español](HARDWARE_W207-palemoon-invitado-borrador-es.md)

Borrador de la sesión lateral del navegador, para unir a `HARDWARE_W207.md`. Nada de esto se probó en la consola.

Tres cambios:
1. Un invitado cierra sus archivos al terminar.
2. Una traza del fallo de mozglue de W205.
3. El `user.reg` del build deja de traer `AppDefaults\palemoon.exe`.

La decisión del usuario es que Pale Moon corra siempre como invitado, sin reiniciar el título ("quiero que siempre corra sin reiniciar"). Por eso no se compara con Pale Moon corriendo solo.

# 1. Un invitado cierra sus archivos al terminar

## Qué pasó en W205

Reporte: `reports/wine-hardware-w205/physical/20261104T143053Z/run-0002.log`, líneas 2818 a 2840.

- Pale Moon, como invitado, terminó (por un fallo, línea 2558). Después no se podía volver a abrir hasta reiniciar OrbisDesk.
- El segundo arranque:
  - carga `palemoon.exe`;
  - intenta cargar `Rstrtmgr.dll` (`c0000135`);
  - termina enseguida con estado 0, sin mostrar nada.
- **Qué indica `Rstrtmgr.dll`:** Pale Moon usa el Restart Manager para buscar a quién tiene tomado su perfil. Llega ahí cuando no puede abrir `<perfil>\parent.lock`, porque lo abrió sin compartir (`CreateFileW`, compartir 0, `FILE_FLAG_DELETE_ON_CLOSE`) y nadie lo cerró.
- **Lo que hace hoy `ps4_guest_exit_process`** (`tools/build-guest-hw.py`):
  - termina los hilos del invitado;
  - destruye sus ventanas;
  - descarga su módulo.
  
  No cierra ningún handle. El proceso sigue vivo, así que nada los cierra, como sí pasaría al terminar un proceso de verdad. Esto vale para cualquier invitado, no sólo para Pale Moon.

## Cambio

`tools/build-guest-hw.py`, en kernelbase:
- **`file.c`, `CreateFileW`:** un archivo que se abre desde un hilo del invitado, con código del propio programa, queda anotado en el invitado junto con su índice de archivo. Cuenta como código del programa:
  - un llamador fuera del directorio de Windows;
  - o el runtime de C (`ucrtbase`, `msvcrt`).
  
  Las DLL de Wine pueden quedarse con un archivo que abrieron desde un hilo del invitado durante todo el título, así que esas no se anotan.
- **`process.c`, `CloseHandle`:** un handle que cierra un hilo del invitado sale de la lista.
- **`process.c`, `ps4_guest_unload`:** se cierra cada handle anotado que todavía apunta al mismo archivo (mismo índice), y se registra `PWGUEST files module=… closed=… stale=…`. Esto pasa:
  - al salir el invitado;
  - cuando falla y termina con `TerminateProcess`;
  - cuando se termina junto con su consola.
  
  Un handle que el programa cerró por otro camino (`NtClose`) y que después se reusó para otro archivo no se toca.

**No cubre:**
- archivos abiertos directamente con `NtCreateFile` o por las DLL de Wine;
- otros handles: eventos, mutex, sockets, secciones.

## Construcción

1. `python3 tools/build-guest-hw.py`.
2. `tools/link-wine-boot.py`.
3. `tools/build-wine-hardware.py`.

## Prueba física

1. Abrir Pale Moon (como invitado) y cerrarlo.
2. Volver a abrirlo sin reiniciar OrbisDesk.
3. **Qué buscar en el log:**
   - al cerrarlo, `PWGUEST files module=… closed=…` con `closed` mayor que 0;
   - que el segundo arranque abra la ventana y no cargue `Rstrtmgr.dll`.
4. Repetir con un cierre por fallo, si se puede reproducir (W205: segunda pestaña y navegación).

## No verificado

- Nada se probó en la consola.
- El cambio se compiló sólo con `-fsyntax-only` (mingw, con las definiciones de kernelbase), sobre una copia de los fuentes con todas las revisiones del builder.
- Que `parent.lock` sea el handle que bloquea sale del código de Pale Moon y de la carga de `Rstrtmgr.dll`, no de una medición.

# 2. Traza del fallo de mozglue (diagnóstico)

## Qué pasó en W205

Reporte: `reports/wine-hardware-w205/physical/20261104T142955Z/run-0002.log`, línea 2536.

- **El fallo:** el hilo `0064` de Pale Moon falla en `mozglue.dll+0x10EEA`.
- **Los registros:** `rcx` y `rsi` valen `0xe5e5e5e5e5e5e5e5`, y `rbx` vale `e5e5e5e5e5e00000`. Es el relleno que mozjemalloc pone en la memoria liberada, enmascarado a la dirección de un bloque. Su allocator recibió un puntero leído de memoria ya liberada: un uso después de liberar (use-after-free).
- **Dónde está el error:** en el código que llama al allocator. El log no lo muestra: la traza de Wine trae sólo los registros, y después el manejador de Pale Moon lo termina (`TerminateProcess` 253).
- **Antes del fallo:** el mismo hilo llama dos veces a `NtGdiRemoveFontMemResourceEx`, que en Wine es un stub: devuelve `TRUE` y deja las fuentes registradas.
  - Pale Moon libera la fuente sin mirar ese resultado, así que el stub no explica un uso después de liberar en el mismo momento.
  - Wine copia los datos de la fuente al agregarla, así que tampoco se queda con la memoria de Pale Moon.
  
  Por ahora es sólo una marca de cuándo pasa: el cierre de una página o pestaña.

## Cambio

`tools/build-guest-hw.py` (kernelbase, `process.c`), con `guest-fault-trace-w207.patch.py`:
- **Qué instala:** con el primer invitado, un manejador vectorizado, el primero de la cadena.
- **Qué registra:** para las primeras 8 violaciones de acceso de hilos invitados del título, `PWFAULT`, antes de que corran los manejadores del programa. Registra:
  - la dirección, la lectura o escritura y el destino;
  - los marcos (módulo+desplazamiento), desenrollados desde el contexto del fallo dentro de la pila del propio hilo.
  
  Los nombres de módulo salen de `LdrFindEntryForAddress`, que no toma ningún lock. Un marco de JIT, sin módulo, corta el recorrido.
- **No cambia el comportamiento:** devuelve `EXCEPTION_CONTINUE_SEARCH`, así que los manejadores del programa corren igual.

## Prueba física

1. Repetir lo de W205: abrir una segunda pestaña y navegar hasta que Pale Moon se cierre.
2. **Qué buscar en el log:** las líneas `PWFAULT n=1 …`. El marco 0 tiene que ser `mozglue.dll+10eea`. Los siguientes muestran quién le pasó el puntero liberado al allocator, en general desplazamientos dentro de `xul.dll`.
3. Con esos desplazamientos se busca la función en `xul.dll` de Pale Moon 35.0.3. Pale Moon no trae símbolos: se identifica por desensamblado y por las importaciones cercanas.

# 3. `user.reg` sin `AppDefaults\palemoon.exe`

`tools/build-wine-hardware.py`, con `palemoon-userreg-w207.patch.py`, saca los dos bloques:
- **`OrbisRunsAlone="Y"` (W183):** haría que Pale Moon relanzara el título otra vez.
- **Sus `DllOverrides` (W184: `d3d10core`, `d3d11`):** nunca se aplican a un invitado, que corre con los `AppDefaults` de `explorer.exe` (Wine toma el nombre del ejecutable del proceso).

Si el merge del upload vuelve a agregar bloques que la consola ya no tiene es tema de la sesión desktop-shortcuts.

# Construcción (las tres partes)

1. `python3 tools/build-guest-hw.py`.
2. `tools/link-wine-boot.py`.
3. `tools/build-wine-hardware.py`.

# No verificado (las tres partes)

- Nada se probó en la consola.
- Los tres scripts se aplicaron juntos sobre copias de los builders:
  - las revisiones de kernelbase se aplican sobre los fuentes;
  - `file.c` y `process.c` pasan `-fsyntax-only` con mingw y las definiciones de kernelbase.
  
  Los builders no se corrieron.
