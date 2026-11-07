# W204: Pale Moon como invitado se traba al pedir memoria (borrador)

[English](HARDWARE_W204-palemoon-memoria-borrador.md) | [Español](HARDWARE_W204-palemoon-memoria-borrador-es.md)

Borrador de la sesión lateral del navegador, para unir a `HARDWARE_W204.md`. Nada de esto se probó en la consola.

## Qué pasó en W203

Reporte: `reports/wine-hardware-w203/physical/20261104T134148Z/run-0001.log`. El usuario dijo: "se congeló, pero mucho después, navegando".

- **El arreglo de `poll` de W203 funciona:**
  - `PWNET poll_count n=258` (línea 3879) confirma que la tabla del servidor pasó de 256;
  - no aparece ningún `PWSERVER poll_failed`;
  - el latido de explorer queda en ~176 ms hasta el final, así que el escritorio ya no se congela.
- **Lo nuevo:** desde la línea 7780, el hilo `0110` de Pale Moon registra 100 791 veces la misma línea, hasta el final del log: `virtual:map_fixed_area mmap error Invalid argument for 0x219400000-0x219500000, unix_prot 0x3`. Es siempre el mismo 1 MB.

## Causa (deducida del código y del log)

- **`VirtualAlloc` con dirección:** fuera de las zonas reservadas de Wine (en la consola, `0x10000-0x68000000` y `0x7f000000-0x7fff0000`), la pide `map_fixed_area` → `anon_mmap_tryfixed`. En la consola es `pw_wine_anon_tryfixed` (`platform/ps4/pw_wine_platform.c`), que hace:
  - `sceKernelReserveVirtualRange` fijo, sin sobrescribir;
  - después `sceKernelMapFlexibleMemory`.
  
  Su `EINVAL` se convirtió en `STATUS_INVALID_PARAMETER`.
- **`VirtualAlloc` sin dirección:** la memoria sale de `mmap(NULL)` de libc (`anon_mmap_alloc`), y la ubicación la elige el kernel.
- **El allocator de Pale Moon:** el de la versión para Windows, mozjemalloc, quiere bloques de 1 MB alineados a 1 MB. Para eso:
  1. pide unos 2 MB sin dirección;
  2. los libera;
  3. pide 1 MB en la dirección alineada que queda adentro;
  4. si eso falla, repite desde el paso 1, sin límite. En Windows, ese fallo sólo puede venir de otro hilo que ocupó el rango.
- **Por qué no termina:** el kernel devuelve cada vez el mismo rango libre, y el pedido fijo adentro falla cada vez.

## Cambio

`platform/ps4/pw_wine_platform.c`, `pw_wine_anon_tryfixed`:
- **Cuándo actúa:** con una protección accesible, cuando el kernel rechaza con `EINVAL` la reserva o el mapeo fijo, o los ubica en otro lado.
- **Qué hace:** pide el mismo rango a `mmap` de libc como sugerencia, sin `MAP_FIXED`, como hace el camino sin dirección.
  - Sirve sólo si el kernel lo pone exactamente ahí.
  - Si lo pone en otro lado, lo libera y devuelve `EEXIST` (rango ocupado, que Wine ya maneja).
  
  Así nunca se mapea encima de otra cosa.
- **Lo que no cambia:** las reservas `PROT_NONE`.
- **Traza:** las primeras 8 veces, y después una cada 1000, se registra `PWVM tryfixed_hint` con:
  - el paso y el código del kernel;
  - el resultado de `mmap`;
  - lo que dice `sceKernelVirtualQuery` en esa dirección.

## Construcción

1. `tools/link-wine-boot.py` (compila `pw_wine_platform.c`).
2. `tools/build-wine-hardware.py`.

## Prueba física

1. Abrir `palemooncopy.exe` (como invitado) y navegar un rato largo, como en W203.
2. **Qué buscar en el log:**
   - líneas `PWVM tryfixed_hint … mapped=0x219400000` (o la dirección que sea), donde `mapped` es igual a `address`: el pedido de mozjemalloc se resolvió;
   - las líneas `map_fixed_area mmap error` ya no se repiten sin fin.
3. **Si se repite igual:** las líneas `PWVM tryfixed_hint` muestran qué hay en esa dirección (`region`, `flexible`, `direct`, `committed`) y qué devolvió `mmap`.

## No verificado

- Nada se probó en la consola.
- El cambio se compiló sólo con `clang -fsyntax-only`, con las opciones de `link-wine-boot.py`, sobre una copia.
- No se sabe por qué el kernel rechaza la reserva fija en ese rango. Que el kernel acabara de entregar ese rango con `mmap(NULL)` sale de cómo funciona Wine, no de una medición. La traza nueva lo muestra.
- Si en esa dirección hay algo que Wine no conoce, `mmap` lo ubicará en otro lado, el resultado será `EEXIST` y mozjemalloc seguirá repitiendo. En ese caso la traza dice qué ocupa el rango.
