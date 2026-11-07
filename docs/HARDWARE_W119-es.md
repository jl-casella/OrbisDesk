# W119: DLL de 32 bits (fase 2 del plan PE32)

[English](HARDWARE_W119.md) | [Español](HARDWARE_W119-es.md)

APP_VER 02.18. Base W118 (fase 1 aceptada: gui-window32.exe corre por WoW64 y wowprospero).

## Cambios

- Se compilaron en el árbol host fijado (`.deps/wine/runtime/build`) las DLL i386 que faltaban: ddraw, wined3d, dinput, d3dxof, dplayx, wsock32, mswsock, hid, dsound, mmdevapi, dxgi, winevulkan, vulkan-1, opengl32, d3d8 y d3d9. El `make` de esos objetivos compiló además otras partes del árbol (por dependencias) y se detuvo una vez listos los 16.
- `tools/stage-wine-i386.py` (nuevo):
  - toma esas DLL más su cierre de importaciones, sin las que ya están en el syswow64 del prefix sellado;
  - deja `out/wine-i386/` con su manifest. Son 15 módulos, sin importaciones sin resolver.
- `tools/build-wine-hardware.py` los copia con `copy_verified` a `C:\windows\syswow64` y `wine/lib/wine/i386-windows`.

Lo que **no** incluye: la parte nativa de wined3d (`wined3d.so`) ni la de opengl32 de 32 bits. wined3d carga pero no tiene con qué dibujar; eso es la fase 4b.

## Entrega

`/data/pkg/orbis-win-W119-ba78ebe15b9b.pkg`, con la lectura de vuelta verificada (594 archivos, 32 subidos). W118 retirado. Pesa 442 MB porque las DLL i386 conservaban su información de depuración; W120 las achica.

## Prueba pendiente

Abrir `Documents\SuperMarioKart\SuperMarioKart.exe`, aceptar el diálogo y esperar. Lo esperable es que cargue sus DLL (ddraw, dinput, dplayx, d3dxof, wsock32) y falle al crear la superficie de Direct3D 7. Hay que traer el log con fetch-hardware.py --build W119.

## Resultado físico: 20261102T215549Z

- run-0001: `pe32_relaunch` → `switch_program` de SuperMarioKart.exe.
- run-0002: `cpu=wowprospero`.
  - Cargan las DLL de 32 bits, incluidas las nuevas.
  - `ws2_32.dll`, importada a través de wsock32, devuelve FALSE en su `DllMain`. `loader_init` aborta con c0000142, `process_exit status=0xc0000142` y vuelta al escritorio. No hay ventana del juego.
- Causa: la ws2_32 i386 se cargó desde `C:\windows\syswow64`. ntdll asocia la parte Unix de una DLL builtin sólo cuando la encuentra en `wine/lib/wine/i386-windows`, así que no hubo `static_unixlib …/ws2_32.so` y `__wine_init_unix_call` falló. En 64 bits no pasa, porque esas DLL están en `x86_64-windows`.
- También aparece `find_forwarded_export … cryptbase.SystemFunction036` (advapi32); no es lo que corta la ejecución.

Corrección en W120: `tools/stage-wine-i386.py` agrega `ws2_32` a sus objetivos, así queda también en `wine/lib/wine/i386-windows`.
