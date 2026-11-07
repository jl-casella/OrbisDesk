# W184: Pale Moon sin D3D11 (fase 9, borrador)

[English](HARDWARE_W184-navegador-borrador.md) | [Español](HARDWARE_W184-navegador-borrador-es.md)

Borrador de la sesión lateral del navegador, para unir a `HARDWARE_W184.md`. Base W183. Nada de esto se probó en la consola.

## Qué pasó en W183

Reporte: `reports/wine-hardware-w183/physical/20261103T232154Z/`. El relanzamiento funciona: run-0004 y run-0006 relanzan, y run-0005 y run-0007 corren `palemoon.exe` como título. Pale Moon se cae a los 13 s más o menos y la app vuelve al escritorio.

- **run-0005 (primer arranque del perfil):**
  - El hilo principal carga `opengl32`, el `dxgi` builtin de Wine y después el `d3d11.dll` de DXVK (W124).
  - DXVK avisa `D3D11InternalCreateDevice: Adapter is not a DXVK adapter` y crea su propio dispositivo Vulkan. Después da `DxvkMemoryAllocator: Memory allocation failed` (4096 bytes, tipos de memoria 0,2,3,5, montones de 1024 y 2048 MiB casi vacíos).
  - Fallo de acceso en `7F8941618`: `d3d11.dll` (DXVK), desplazamiento `0xe1618`.
  - Después hay un breakpoint en `7FA464E69`: `xul.dll` de Pale Moon, desplazamiento `0x734e69` (el abort de Mozilla). Termina con `0x80000003`.
- **run-0007 (segundo arranque):**
  - Pale Moon borra `d3d11layers.guard` del perfil. Es su guarda contra fallos de D3D11, que quedó del fallo anterior, así que esta vez no usa D3D11.
  - Después, `map_view anon mmap error Invalid argument, size 0x810000, unix_prot 0x3`: una reserva de 8 MB de lectura y escritura que la consola rechazó.
  - `xul.dll` lee la dirección `0x80` en `7F9FD958E` (`xul.dll`, desplazamiento `0x2a958e`) y termina con `0xc0000005`.
  - Es un problema de memoria distinto del de D3D11. Pertenece al trabajo de la sesión principal en `virtual.c` (la reserva de 1 GB de W180 era sin permisos; esta es de 8 MB con lectura y escritura).

**Por qué Pale Moon creó un dispositivo D3D11.** El `user.js` de W177-W183 pedía `layers.acceleration.disabled`. Pale Moon 35 (UXP) no tiene esa preferencia. La suya es `layers.acceleration.enabled` (los nombres están en `xul.dll`). Tampoco existe `layers.prefer-d3d9`. Pale Moon ignoró las dos y dejó la composición por GPU encendida.

## Cambio

| Archivo | Qué hace |
|---|---|
| `fixtures/browser/palemoon-user.js` | `layers.acceleration.enabled=false` en lugar de `layers.acceleration.disabled`. Saca `layers.prefer-d3d9`. Agrega `webgl.disable-angle=true` (ANGLE también usa D3D11). Siguen `gfx.direct2d.disabled`, `webgl.disabled` y `media.hardware-video-decoding.enabled=false`. Todas esas preferencias están en `xul.dll`. |
| `tools/build-wine-hardware.py` (`user.reg`, pendiente del OK de la sesión principal) | `[Software\Wine\AppDefaults\palemoon.exe\DllOverrides]` `"d3d11"=""` y `"d3d10core"=""`: si algo de Pale Moon igual pide D3D11, la carga falla limpia y no llega a DXVK. `dxgi` sigue siendo el builtin (Pale Moon lo usa para leer el adaptador). `d3d9` no se toca: `xul.dll` lo importa de forma estática. |

El `user.js` es del build, así que la subida lo reemplaza. Lo que Pale Moon escribió en el perfil (`prefs.js`, guardas) queda.

## Para después: Vulkan en un título de 64 bits relanzado

En run-0005, DXVK no pudo reservar ni 4 KB de memoria Vulkan en un proceso propio de 64 bits. Los programas de 32 bits relanzados sí usan DXVK y wined3d sobre Vulkan. No se investigó en W184. Queda anotado para cuando Pale Moon (o un juego de 64 bits) use D3D11 en su propio proceso.

## Construcción (orden)

1. `python3 tools/build-wine-hardware.py` (copia el `user.js` nuevo y, con el OK, escribe el bloque `DllOverrides`)
2. `python3 -I tools/check-web-closure.py build/wine-hardware-w184/runtime`

## Prueba física

1. **Abrir Pale Moon:**
   - En el log no tiene que aparecer `d3d11.dll` cargado por Pale Moon ni ninguna línea de DXVK (`info:  DXVK: v2.7.1`).
   - Se espera la página local con `es5-ok`, `es2020-ok` y `canvas-ok`.
2. **Si vuelve `map_view anon mmap error Invalid argument`** (como en run-0007), el fallo es de memoria y no de gráficos: queda para el arreglo de `virtual.c`.
3. **Cerrar Pale Moon:** tiene que volver el escritorio.

## No verificado

- Nada se probó en la consola.
- No está confirmado que, con la composición por GPU apagada, Pale Moon 35 no cree igual un dispositivo D3D11 para otra cosa (lectura del adaptador, decodificación de imágenes). Para eso está el `DllOverrides`.
