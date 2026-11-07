# MangoHud en juegos Direct3D por DXVK (borrador para la próxima W)

[English](HARDWARE_W197-mangohud-dxvk-borrador.md) | [Español](HARDWARE_W197-mangohud-dxvk-borrador-es.md)

Borrador de la sesión de configuración de Wine. La sesión principal lo suma al documento de la W en que entre (aquí "W197").

## Qué pasó en W195

- The Lost Forest (Unity, x64, Direct3D 11 por DXVK 2.7.1) corre, pero F12 no muestra MangoHud.
- En `run-0001.log` (`reports/wine-hardware-w195/physical/20261104T112911Z`), las tres veces que DXVK arranca dice `Vulkan: Found vkGetInstanceProcAddr in winevulkan.dll`.
- MangoHud es una capa implícita de Vulkan. La carga el loader de Khronos (`system32\vulkan-1.dll`, W086) cuando `MANGOHUD=1`, y el lanzador ya lo pone (`launch_arg --env=MANGOHUD=1`). Llamando a winevulkan directamente, DXVK no pasa por el loader y la capa no se carga.

## La causa

- DXVK 2.7.1 busca `vkGetInstanceProcAddr` en una lista fija: primero `winevulkan.dll` y después `vulkan-1.dll` (`src/vulkan/vulkan_loader.cpp`). Usa la primera que carga.
- No hay variable de entorno ni opción de `dxvk.conf` que cambie ese orden. Las cadenas de los DLL solo tienen `DXVK_HUD`, `DXVK_CONFIG`, `DXVK_WSI_DRIVER` y similares; ninguna elige el loader.
- Deshabilitar `winevulkan` por DllOverrides no sirve: el loader de Khronos carga el mismo `winevulkan.dll` como driver.

## Opciones

- **MangoHud por el loader (elegida).** En los DLL x64 de DXVK que cargan Vulkan (`d3d9`, `d3d11`, `dxgi`), el primer nombre pasa de `winevulkan.dll` a `vulkan-1.dll`: mismo largo, relleno con ceros. Cada DLL tiene una sola vez la pareja `winevulkan.dll\0vulkan-1.dll\0`, y el stager lo comprueba. Así un juego Direct3D de 64 bits va por el loader, como vkcube, y MangoHud se carga con la misma configuración (`%APPDATA%\MangoHud\MangoHud.conf`) y la misma tecla F12.
- **HUD propio de DXVK (descartada).** `DXVK_HUD` o `dxvk.hud` en `dxvk.conf` muestran FPS y tiempos de cuadro, pero DXVK 2.7.1 no tiene tecla para mostrarlo u ocultarlo: queda fijo desde que arranca el juego. Además no usa la configuración de MangoHud que ya tiene el usuario.
- **Compilar DXVK desde el código con el orden cambiado.** Da el mismo resultado, pero hace falta descargar el código y armar mingw, meson y glslang. El cambio de bytes es más chico y se comprueba en cada build.

Los DLL x32 quedan como vienen: un programa de 32 bits no tiene el loader de Khronos (W116).

## Cambio

- `tools/stage-dxvk.py` (lo aplica `dxvk-loader-w197.patch.py`, en la carpeta de notas):
  - `LOADER` y `LOADER_DLLS`: el reemplazo, solo en `x64/d3d9.dll`, `x64/d3d11.dll` y `x64/dxgi.dll`;
  - si la pareja de nombres no aparece exactamente una vez, el stager se detiene;
  - el manifest guarda, por archivo, `release_sha256` (el del release) y `patched`.
- `dxvk_dxgi.dll` es una copia de `x64/dxgi.dll` (W192), así que también va por el loader.
- `tools/build-wine-hardware.py` no cambia: toma los archivos del manifest de DXVK y comprueba el sha del stager.
- Probado sobre una copia del stager, con salida en el scratchpad: se cambian 3 DLL; el tamaño de cada uno es el mismo; no queda `winevulkan` en ellos; los otros 7 tienen el mismo sha que el release.

## Efectos a mirar

- Todo programa de 64 bits que use el d3d9 o el d3d11 de DXVK carga MangoHud, y el HUD se ve desde el inicio (la configuración no trae `no_display`). F12 lo oculta.
- El loader agrega una llamada más por función de Vulkan. Con el HUD visible, MangoHud dibuja en cada `vkQueuePresentKHR`. Comparar los FPS de The Lost Forest con W195 (unos 76).

## Prueba

1. The Lost Forest: el log dice `Vulkan: Found vkGetInstanceProcAddr in vulkan-1.dll`, y MangoHud aparece arriba a la izquierda.
2. F12 lo oculta y lo vuelve a mostrar.
3. FPS parecidos a W195.
4. vkcube con MangoHud sigue igual.
