# W208: un invitado descarga sus DLL y libera su memoria al terminar (borrador)

[English](HARDWARE_W208-invitado-descarga-borrador.md) | [Español](HARDWARE_W208-invitado-descarga-borrador-es.md)

Borrador de la sesión lateral del navegador, para unir a `HARDWARE_W208.md`. Nada de esto se probó en la consola.

## Qué pasó en W207

Reporte: `reports/wine-hardware-w207/physical/20261104T145559Z/run-0001.log`. El usuario dijo: "no abre la 2da vez".

- **Lo que ya funciona:** el cierre de archivos de W207. Al terminar aparece `PWGUEST files … closed=1` y ya no se carga `Rstrtmgr.dll`.
- **El segundo arranque** (líneas 2779 a 2800) termina enseguida con estado 1. Los dos intentos siguientes dan lo mismo.
- **La causa:** `ps4_guest_unload` sólo descarga el EXE del invitado.
  - `xul.dll`, que `palemoon.exe` carga con `LoadLibrary`, y las DLL que trae (`mozglue`, `nss3`, …) siguen cargadas con su estado de la primera vez.
  - El segundo arranque las encuentra ya inicializadas: no vuelve a aparecer `Loaded … xul.dll`.
- **Qué era "23 of other modules kept":** se refiere a clases de ventana, no a DLL.
- **La memoria:** la memoria disponible de `load_begin` baja de 4974739456 a 4747493376, unos 227 MB por cada vez que se abre Pale Moon. Son los bloques del allocator de `mozglue`, que nadie libera.

## Cambio

`tools/build-guest-hw.py`, con `guest-unload-w208.patch.py`. Al terminar el invitado, después de su EXE:

1. **Sus módulos propios:** los cargados desde que empezó, fuera del directorio de Windows y no fijados. Se anotan los que había al arrancar y se registra `PWGUEST own <nombre> base=… size=… refcount=…`.
2. **Hilos en su código:** se buscan otros hilos del proceso cuya dirección de inicio, o alguno de sus primeros 32 marcos, esté en ese código. Cada uno se registra (`PWGUEST kept: thread … in …`). Si hay alguno, no se descarga nada.
3. **Clases de ventana:** se quitan las clases cuyo procedimiento está en esos módulos, con la misma prueba que W068 usa para el EXE. Si una todavía tiene ventanas, no se descarga nada (`PWGUEST kept: class …`).
4. **Filtro de excepciones:** si apunta a ellos, se borra.
5. **La descarga:** `LdrUnloadDll` hasta que cada módulo desaparece, del más nuevo al más viejo. `DllMain(DETACH)` corre como siempre. Se registra `PWGUEST unloaded … gone=1`.
6. **En ntdll (`free_modref`), para cualquier imagen que se desmapea:** se quitan los manejadores vectorizados cuyo código está en ella y se liberan sus slots FLS (`PWGUEST unmap … handlers=… fls=…`).
7. **La memoria:** las regiones que su código reservó con `VirtualAlloc` (`kernelbase` `memory.c`, anotadas como los archivos de W207) se liberan (`PWGUEST memory … released=… bytes=…`).

**El interruptor:** si existe `C:\orbis\noguestunload.txt`, todo se registra pero no se quita, descarga ni libera nada. Sirve para volver atrás sin un build nuevo si la descarga detiene el escritorio.

**No cubre:**
- temporizadores o trabajos del thread pool que todavía no corrieron, con código en esos módulos;
- hooks globales;
- objetos COM registrados.

Si alguno de esos quedara, fallaría cuando se ejecute.

## Una excepción no manejada en un invitado termina sólo el invitado

**W207, segunda corrida** (`reports/wine-hardware-w207/physical/20261104T145950Z/run-0002.log`, líneas 2353 a 2407): el usuario dijo "abrí 2da tab y navegué a YouTube y se cerró OrbisDesk".

- **El fallo:** el mismo de W205 en `mozglue.dll+0x10EEA`.
- **La pila** (`PWFAULT`): `mozjs.dll` (5 marcos) y después `xul.dll`. El motor de JavaScript le pasó al allocator un puntero ya liberado.
- **Lo que pasó después:**
  1. Esta vez ningún manejador de Pale Moon lo atrapó: el `_XcptFilter` de `palemoon.exe` devolvió "seguir buscando".
  2. Wine intentó `winedbg` ("Unhandled page fault … starting debugger").
  3. ntdll terminó todo el proceso con `NtTerminateProcess` (`process_exit status=0xc0000005`). Esa llamada no pasa por el `TerminateProcess` del invitado (W196).
- **Por qué en W205 no pasó:** en W205, un manejador de `xul.dll` atrapó el mismo fallo y llamó a `TerminateProcess`, así que sólo terminó el invitado.

**Cambio:** `tools/build-guest-hw.py` (`kernelbase` `debug.c`, `UnhandledExceptionFilter`), con `guest-unhandled-w208.patch.py`.
- Primero el programa usa su propio filtro de excepciones, como antes.
- Después, en vez de buscar el depurador, un hilo invitado termina su invitado: `TerminateProcess` del propio proceso, que maneja `ps4_guest_exit_process`, con el código de la excepción como estado.
- Se registra `PWGUEST unhandled exception … the guest ends`.
- Los hilos de explorer no cambian.

## Construcción

1. `python3 tools/build-guest-hw.py`.
2. `tools/link-wine-boot.py`.
3. `tools/build-wine-hardware.py`.

## Prueba física

1. Abrir Pale Moon (como invitado), navegar un poco y cerrarlo.
2. Volver a abrirlo sin reiniciar. Repetir dos o tres veces.
3. **Qué buscar en el log:**
   - `PWGUEST own_modules … count=…` y las líneas `PWGUEST own` (los módulos de Pale Moon);
   - `classes=…` y `threads=0`;
   - `PWGUEST unloaded xul.dll … gone=1`;
   - `PWGUEST unmap … handlers=…`;
   - `PWGUEST memory … bytes=…`, del orden de 200 MB;
   - que el `available=` de cada `load_begin` vuelva a un valor parecido al primero.
4. **Si el escritorio se cuelga o falla al cerrar Pale Moon:** crear `C:\orbis\noguestunload.txt` por FTP y repetir. El log va a decir qué habría descargado y qué se lo impidió.
5. **Si cuelga o falla dentro de `DllMain(DETACH)`:** W209 descarga sin `DllMain`.

## No verificado

- Nada se probó en la consola.
- Las revisiones se aplicaron sobre copias de los fuentes, y `kernelbase` (`file.c`, `memory.c`, `process.c`) y `ntdll` (`exception.c`, `loader.c`) pasan `-fsyntax-only` con mingw y las definiciones de cada módulo. El builder no se corrió.
- No se sabe si el `DllMain(DETACH)` de `xul.dll` y `mozglue.dll` funciona después de que sus hilos fueron terminados.
