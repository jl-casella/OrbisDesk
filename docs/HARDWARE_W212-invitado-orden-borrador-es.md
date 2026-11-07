# W212: los módulos de un invitado se descargan en orden de dependencias y sin DllMain (borrador)

[English](HARDWARE_W212-invitado-orden-borrador.md) | [Español](HARDWARE_W212-invitado-orden-borrador-es.md)

Borrador de la sesión lateral del navegador, para unir a `HARDWARE_W212.md`. Nada de esto se probó en la consola.

## Qué pasó en W210

Reporte: `reports/wine-hardware-w210/physical/20261104T161446Z/run-0001.log` (líneas 2173 a 2300) y `run-0002.log`, con el mismo patrón. El usuario dijo: "se tilda al abrir ahora Pale Moon. Ni abre directamente y congela OrbisDesk."

1. **Primer arranque:** Pale Moon se reinicia a sí mismo, y el primero sale normalmente (`ExitProcess`).
2. **La descarga:** con una salida normal, W209 todavía corría `DllMain(DETACH)`. Además, la descarga llamaba a `LdrUnloadDll` hasta que cada módulo desaparecía, del más nuevo al más viejo.
3. **Lo que eso rompió:** también se bajaron las referencias que tenían las importaciones de otros módulos. `VCRUNTIME140.dll` tenía 13 referencias, la mayoría de las importaciones de `MSVCP140.dll` y `mozglue.dll`. Se desmapeó después de 3 llamadas (`calls=3`), con esos dos todavía cargados.
4. **El fallo:** el `DllMain` de `MSVCP140.dll` llamó a `VCRUNTIME140.dll` ya desmapeada (violación de acceso en `7FD8E50B0`, `VCRUNTIME140+0x50b0`). Los manejadores de excepción, que estaban ahí, fallaron también.
5. **El cuelgue:** el hilo que salía se quedó con el loader lock (`PWDUMP begin … loader_owner=0064`). Explorer se detuvo, y el Pale Moon reiniciado no pudo cargar (`relaunch … parent_wait=258`).

## Cambio

`tools/build-guest-hw.py` (kernelbase `process.c`), con `guest-unload-order-w211.patch.py`:

1. **Sin `DllMain(DETACH)` en ninguna salida:** ningún invitado corre el `DllMain(DETACH)` de sus módulos propios. Cuando un invitado sale, sus otros hilos ya terminaron, así que ese código no puede correr como en Windows. W209 sólo lo salteaba para los invitados terminados. Se registra `detach skipped (exit|terminated|leftovers)`.
2. **Descarga por rondas:** en cada ronda, `LdrUnloadDll` una vez para cada módulo que ningún otro módulo propio todavía cargado importa ni carga de forma diferida. Las importaciones se ven en sus propios encabezados. Los contadores de dependencias de Wine liberan el resto.
   - Un módulo que sigue cargado después de 64 rondas, o que está en un ciclo de importaciones, se registra (`PWGUEST kept: … still loaded`) y queda.
   - Al final se registra `PWGUEST unloaded module=… own=… remaining=… rounds=…`.
3. **La memoria, sólo si se fue todo:** la memoria que reservó su código se libera sólo si se descargaron todos. Si no, el allocator de `mozglue` quedaría con punteros a regiones liberadas.

## Construcción

1. `python3 tools/build-guest-hw.py`.
2. `tools/link-wine-boot.py`.
3. `tools/build-wine-hardware.py`.

## Prueba física

1. Abrir Pale Moon desde un OrbisDesk recién arrancado.
2. Cerrarlo, volver a abrirlo, hacer que falle y volver a abrirlo.
3. **Qué buscar en el log:**
   - `detach skipped (exit)` en la salida del reinicio;
   - `PWGUEST unloaded … remaining=0`;
   - `relaunch … parent_wait=0`;
   - una ventana de Pale Moon.

## No verificado

- Nada se probó en la consola.
- El cambio se aplicó sobre copias de los fuentes, y `process.c` pasa `-fsyntax-only` con mingw. El builder no se corrió.
