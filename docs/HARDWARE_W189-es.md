# W189: limpieza de diagnósticos y Direct3D 11 de 64 bits

[English](HARDWARE_W189.md) | [Español](HARDWARE_W189-es.md)

APP_VER 02.88. Base W188. El resultado de W188 está en `docs/HARDWARE_W188.md` (Pale Moon navega).

## Limpieza de diagnósticos temporales

| Archivo | Qué se sacó | Quién |
| --- | --- | --- |
| `tools/build-winecfg-hw.py` | Las marcas `PWCFG` de Aplicar, temas y `SetWindowPos` (W182/W183). Los arreglos quedan, entre ellos el `SetWindowPos` asíncrono de W183. | sesión de accesos directos |
| `tools/build-win32u-ps4.py` | `PWPAINT update_now_loop` y `PWBCAST timeout` (W182). | sesión de accesos directos |
| `platform/ps4/pw_wine_fs.c` | La sonda `PWUSB` del sandbox (W180) y su llamada. La tabla de montajes sigue con C: y Z:. | sesión de red |
| `fixtures/browser/palemoon-user.js` | Las preferencias `logging.*` del log de red. Quedan las de red y keep-alive apagado. | sesión del navegador |

## Direct3D 11 en programas de 64 bits

### Qué pasaba

En W183 (`reports/wine-hardware-w183/physical/20261103T232154Z/run-0005.log`), Pale Moon relanzado como título de 64 bits:
- DXVK 2.7.1 crea su propio dispositivo Vulkan ("Adapter is not a DXVK adapter").
- La primera reserva falla: `DxvkMemoryAllocator: Memory allocation failed`, 4096 bytes, con los montones de 1024 y 2048 MiB casi vacíos.
- Después viene un `c0000005`. `d3d11test64.exe` también se cerraba.

### Causa probable (leída en el código, no confirmada en la consola)

- **Las líneas que faltan no son la falla.** No aparecen líneas `radv/ps4: va`/`bo` del segundo dispositivo porque el log detallado del winsys tiene un cupo de 64 líneas para todo el proceso (`ac_ps4_drm.c`, `ps4_verbose_left`), y la sonda de arranque lo gasta. Las fallas reales del winsys se loguean siempre, y no hay ninguna.
- **Qué falla en realidad:** en 64 bits, win32u ofrece `VK_KHR_external_memory_win32` y DXVK lo activa. Una reserva compartida (por ejemplo una textura `MISC_SHARED`; la prueba de texturas compartidas de Gecko crea una de 32×32 BGRA, 4096 bytes) pasa por `vkGetMemoryFdKHR`. En la consola, `ac_drm_bo_export` devuelve `-ENOSYS` porque no hay dma-buf. win32u libera la memoria y devuelve `VK_ERROR_OUT_OF_HOST_MEMORY` (su aviso no sale, porque el registro de 64 bits no tiene `warn+vulkan`).
- **Por qué 32 bits anda:** los títulos de 32 bits usan wined3d sobre Vulkan (`renderer=vulkan`), que no pide memoria compartida.
- Que la reserva de 4096 bytes sea justo una compartida se deduce; no se ve en el log.

### Cambio

`tools/build-win32u-ps4.py` (W189): en `__ORBIS__`, win32u deja de ofrecer `VK_KHR_external_memory_win32`, `VK_KHR_external_semaphore_win32` y `VK_KHR_win32_keyed_mutex`. Sin ellas, DXVK rechaza los recursos compartidos con un código de error en lugar de que falle una reserva normal, y el programa puede seguir sin compartir.

### No cubierto

- Exportar e importar memoria de verdad dentro del proceso (`ac_ps4_drm.c`). Hace falta sólo si un programa necesita recursos compartidos para funcionar.
- `d3d11test64.exe` puede tener otra causa.

## Prueba física

Reporte: `reports/wine-hardware-w189/physical/20261104T030929Z/`. Respuesta del usuario: "1. Se cerró, 2. Cambia tema ok, pero al volver a abrir la app siempre inicia con luna. 3. Asumámoslo ok".

### d3d11test64: la memoria se arregló, falla un paso después

En `run-0001.log`, `d3d11test64.exe` corre como invitado dentro de explorer:
- DXVK ya no ve la extensión (`khrExternalMemoryWin32 : 0`, "External memory features not supported").
- Crea el dispositivo con nivel 11_0, y la reserva de memoria ya no falla.
- Después falla la cadena de presentación: `err:dxgi:dxgi_factory_CreateSwapChainForHwnd This is not the device we're looking for.` y `D3D11CreateDevice: Failed to create swap chain`. El programa sale con estado 0.

**Causa:** el `d3d11.dll` es el de DXVK, pero el `dxgi.dll` es el builtin de Wine. Desde W124, el `dxgi` de 64 bits de DXVK no se instala porque explorer (el cargador de Khronos, MangoHud y el adaptador de Gecko) usa el de Wine. El `dxgi` de Wine sólo acepta dispositivos de wined3d. Un invitado comparte el proceso de explorer y el `dxgi` que ya está cargado, así que no puede usar otro.

### Tema

El cambio de tema se aplica, pero al reabrir la app vuelve Luna. Lo está revisando la sesión de accesos directos (todavía sin causa).

### Otras pruebas

- winecfg: cambiar tema, Aplicar y OK funcionan sin las marcas `PWCFG`.
- SMK: el usuario no lo probó a fondo ("asumámoslo ok").

## Para W190

- `system32\dxgi.dll` pasa a ser el de DXVK. El de Wine queda en `lib/wine/x86_64-windows`.
- `HKCU\Software\Wine\AppDefaults\explorer.exe\DllOverrides` `"dxgi"="builtin"`: explorer y todos sus invitados siguen con el de Wine, porque Wine toma las AppDefaults por el nombre del proceso (`set_load_order_app_name`).
- `AppDefaults\d3d11test64.exe` `"OrbisRunsAlone"="Y"`: la prueba corre sola, relanzando el título, y ahí carga el `dxgi` de DXVK.
- **Pale Moon** corre solo y ahora va a cargar el `dxgi` de DXVK para consultar el adaptador. Su bloque `DllOverrides` de la consola se conserva entero en la subida, así que agregarle un valor `dxgi` desde la build no llegaría. Hay que comprobar que siga navegando.
- **Límite:** un programa de 64 bits con Direct3D 11 sólo va a funcionar si corre solo. Como invitado dentro de explorer, sigue fallando la cadena de presentación.
