# W192: Direct3D 11 de 64 bits dentro de explorer

[English](HARDWARE_W192.md) | [Español](HARDWARE_W192-es.md)

APP_VER 02.91. Base W191. El resultado de W191 está en `docs/HARDWARE_W191.md`.

## Cambios

- **`tools/build-dxgi-hw.py`** (nuevo): es el `dxgi.dll` de 64 bits de Wine con una revisión en `factory.c`. El método es el mismo que el de `build-ddraw-hw.py`: overlay, y la receta de `make -n` sólo para la unidad revisada.
  - En `CreateSwapChainForHwnd`, un dispositivo que no es de wined3d ni una cola D3D12 ya no termina en "This is not the device we're looking for". El factory carga `dxvk_dxgi.dll`, crea un factory de DXVK (`CreateDXGIFactory2`) y le pide la cadena de presentación.
  - DXVK 2.x ya no ofrece la interfaz que usaba el factory de Wine (`IWineDXGISwapChainFactory`). Es el `53cb4ff0…` desconocido del log de W189.
  - Las fallas se registran con `PWDXGI … failed`. El primer éxito deja una línea `PWDXGI swap chain through DXVK's dxgi`.
- **`tools/build-wine-hardware.py`:**
  - el `dxgi` de Wine de `lib/wine/x86_64-windows` es ahora este;
  - el `dxgi.dll` x64 de DXVK también se copia como `system32\dxvk_dxgi.dll`, con otro nombre, para que pueda convivir en el mismo proceso con el de Wine.
- **`tools/build-guest-hw.py`:** se saca la detección de W191 (un programa que importa Direct3D 10/11 o DXGI ya no se relanza solo). `OrbisRunsAlone="Y"` sigue funcionando para quien lo tenga.

## Prueba física

Reporte: `reports/wine-hardware-w192/physical/20261104T041659Z/`. Respuesta del usuario: "Todo ok".

- **La copia `d3d11test64d3d11test64.exe`, sin marca:**
  - carga como invitado dentro de explorer (`PWGUEST load_begin`), sin relanzar;
  - la cadena de presentación sale por DXVK (`PWDXGI swap chain through DXVK's dxgi for window 00000000000100E6`, `Presenter: Actual swapchain properties`);
  - sale con estado 0, y el escritorio sigue respondiendo.
- **Pale Moon:** se relanza por su marca (`OrbisRunsAlone`, W183) y navega.

## Pendiente

- **Las marcas que quedan:**
  - `d3d11test64.exe` conserva la de W190 en el registro de la consola. La subida conserva los bloques `AppDefaults` de la consola, así que se relanza aunque ya no haga falta. Se borra desde winecfg (la pestaña de aplicaciones) o con `user_reg_reset`.
  - Pale Moon sigue corriendo solo, pero por otra razón: sus DLL tienen los mismos nombres que las de Wine Gecko.
- **No probado:**
  - pantalla completa (`SetFullscreenState`) de un invitado con DXVK;
  - Direct3D 10;
  - varios invitados con Direct3D 11 a la vez;
  - un juego real.
