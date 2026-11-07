# W190: Direct3D 11 de 64 bits con el dxgi de DXVK y el registro guardado a tiempo

[English](HARDWARE_W190.md) | [Español](HARDWARE_W190-es.md)

APP_VER 02.89. Base W189. El resultado de W189 está en `docs/HARDWARE_W189.md`.

## Cambios

### dxgi de DXVK para títulos de 64 bits que corren solos

`tools/build-wine-hardware.py`:
- `system32\dxgi.dll` pasa a ser el de DXVK (x64). El builtin de Wine queda en `lib/wine/x86_64-windows`.
- Se agrega `HKCU\Software\Wine\AppDefaults\explorer.exe\DllOverrides` con `"dxgi"="builtin"`. Explorer y todos sus invitados de 64 bits comparten un proceso, y Wine toma las AppDefaults por el nombre de ese proceso (`set_load_order_app_name`). Así siguen usando el `dxgi` de Wine: el cargador de Khronos, MangoHud y Gecko.
- `AppDefaults\d3d11test64.exe` lleva `"OrbisRunsAlone"="Y"`: la prueba relanza el título y corre sola.
- Pale Moon, que también corre solo, ahora carga el `dxgi` de DXVK. Su bloque `DllOverrides` de la consola se conserva entero en la subida, así que no se le pudo agregar una excepción.

### Registro guardado al aplicar (sesión de accesos directos)

El detalle está en `docs/HARDWARE_W190-winecfg-borrador.md`:
- **El problema:** el servidor guardaba el registro cada 30 s y nunca al salir, porque el título se mata.
- **El cambio:**
  - `server/registry.c`: guardado cada 5 s, y `RegFlushKey` escribe a disco (`tools/build-wine-delete-server.py`);
  - Aplicar de winecfg termina con `RegFlushKey(HKEY_CURRENT_USER)`.

## Prueba física

Reporte: `reports/wine-hardware-w190/physical/20261104T033417Z/`. Respuesta del usuario: "2. Ok, 1, Ok, 3. Ok".

- **d3d11test64:**
  - `run-0002` relanza (`switch_program image=C:\orbis\d3d11test64.exe`).
  - `run-0003` corre la prueba como título: carga `system32\dxgi.dll` como nativo, y DXVK crea la cadena de presentación (`Presenter: Actual swapchain properties`).
  - Se presentan cuadros (`frame_presented n=1920` a los 12,7 s). Sale con estado 0 (`process_exit … status=0x00000000`) y vuelve al escritorio (`return_to_desktop`).
  - Es el primer programa de 64 bits con Direct3D 11 que funciona.
- **Tema:** Noir sigue al reabrir la app, aunque se cerró enseguida después de Aceptar.
- **Pale Moon:** se relanza (`run-0004` → `run-0005`) y el usuario confirma que navega con el `dxgi` de DXVK.

## Límites

- Un programa de 64 bits con Direct3D 11 funciona sólo si corre solo (`OrbisRunsAlone`). Como invitado dentro de explorer sigue con el `dxgi` de Wine, y la cadena de presentación falla.
- Por ahora hay que marcar cada programa a mano en el registro. No hay detección automática.
- No se midió el rendimiento de d3d11test64.
