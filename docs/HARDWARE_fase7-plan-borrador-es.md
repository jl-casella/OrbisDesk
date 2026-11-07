# Fase 7 del plan PE32: dxgi de DXVK por programa y winecfg (plan, borrador)

[English](HARDWARE_fase7-plan-borrador.md) | [Español](HARDWARE_fase7-plan-borrador-es.md)

Borrador de la sesión lateral. Todavía no hay build. El número lo asigna la sesión principal.

## Punto de partida

- W124 instaló d3d8, d3d9, d3d10core y d3d11 de DXVK 2.7.1 en `system32` y `syswow64`, pero **no** su `dxgi.dll`. El `dxgi` builtin de Wine sigue siendo el del escritorio de 64 bits: el loader de Khronos verifica los drivers del registro con una fábrica DXGI, y MangoHud le pide la GPU (W087, con `renderer=no3d`).
- El `d3d11` de DXVK necesita el `dxgi` de DXVK. Por eso hoy D3D10/11 no funcionan, y W124 lo dejó para la fase 7 ("por programa, winecfg").
- `winecfg.exe` no está en el prefijo. Está compilado en el árbol fijado de Wine para x86_64 e i386.

## Restricción que define el plan

- **64 bits:** los programas de 64 bits corren como invitados dentro del proceso de explorer (W052). Ese proceso ya tiene cargado el `dxgi` builtin, y Wine no tiene dos módulos `dxgi.dll` en un mismo proceso. Un programa D3D11 de 64 bits no puede usar el `dxgi` de DXVK como invitado.
- **32 bits:** cada programa relanza la app y corre en su propio proceso (W116, WoW64). Ahí `vulkan-1` es el builtin de Wine, sin loader de Khronos y sin la verificación por DXGI: es la combinación estándar Wine + DXVK.

## Paso 1: D3D10/11 en 32 bits

- `tools/build-wine-hardware.py`:
  - el `dxgi.dll` x32 de DXVK va a `syswow64`;
  - `system32` sigue con el `dxgi` de Wine;
  - override `"dxgi"="native,builtin"` en `user.reg`. En 64 bits encuentra el builtin de Wine en `system32` y lo usa; en 32 bits usa el de DXVK. El log lo confirma con `trace+loaddll`, que ya está activo.
- Fixture nuevo `fixtures/win32/d3d11test.c` → `C:\orbis\d3d11test32.exe`:
  - ventana, `D3D11CreateDeviceAndSwapChain`, descripción del adaptador DXGI y nivel de features;
  - ~5 s de `ClearRenderTargetView` con un color que cambia;
  - `d3d11-result.txt` con el HRESULT de cada paso, los cuadros y los ms.
  - Es un caso mínimo, igual que `d3d9test`: no prueba shaders.
- Prueba en la consola:
  - `d3d11test32.exe`;
  - regresión: `d3d9test32.exe`, `ddraw7test32.exe` y SuperMarioKart (wined3d/ddraw no usa `dxgi`, pero hay que comprobarlo).

<a id="paso-2-winecfg"></a>


## Paso 2: vinocfg

- `tools/stage-wine-programs.py`: agrega `winecfg` (x86_64) con su cierre de imports, igual que regedit.
- `tools/make-start-menu.py`: entrada "Wine Configuration" en System Tools.
- Uso:
  - pestaña Aplicaciones → agregar el exe;
  - pestaña Bibliotecas → por ejemplo `dxgi` = builtin, para un programa de 32 bits que deba usar el `d3d11` de Wine en lugar de DXVK.
  - Queda en `HKCU\Software\Wine\AppDefaults\<exe>\DllOverrides`, que el loader lee en el proceso propio de cada programa de 32 bits.
- **Que la build no borre lo que guarda winecfg.**
  - `user.reg` está en `runtime_files`, y `upload-hardware.py` lo sube cada vez que el hash de la consola es distinto.
  - En W108–W112, `system.reg` y `user.reg` figuran siempre como `uploaded` y `userdef.reg` como `present`: Wine reescribe el registro en la consola (el wineserver guarda cada 30 s).
  - Hoy cada subida pisaría los overrides del usuario.
  - Se eligió **fusionar al subir** en lugar de escribir el archivo solo la primera vez. Si se escribiera una sola vez, los cambios de registro de las builds siguientes (por ejemplo, el override de `dxgi` de este paso) no llegarían nunca a la consola.
  - Cómo funciona: `upload-hardware.py` baja el `user.reg` de la consola. Los bloques cuya clave empieza con `Software\\Wine\\AppDefaults` salen de la consola; todo lo demás, del `user.reg` de la build. Un bloque de AppDefaults que solo tiene la build se agrega.
  - Sube el resultado y lo verifica con su propio hash. En el registro de la subida quedan los dos hashes y cuántos bloques se conservaron.
  - Si en la consola no hay `user.reg`, o no empieza con `WINE REGISTRY Version 2`, sube el de la build tal cual y lo anota. El preflight del arranque (`native/wine_prefix_probe.c`) solo mira esa cabecera.
  - El bucle general de `runtime_files` saltea `user.reg`, para que no lo vuelva a subir con el hash de la build después de la fusión.
  - Límite: se conservan solo los ajustes por programa. Los globales de winecfg (la entrada "Default settings") siguen siendo de la build.
  - Límite: hay que cerrar la app antes de instalar. Si está abierta durante la subida, Wine vuelve a escribir `user.reg` dentro de los 30 s siguientes y pisa el archivo fusionado con lo que tiene en memoria. Eso pierde los cambios de registro de la build, no los del usuario.
- Prueba: abrir winecfg como invitado, recorrer las pestañas y guardar un override. Las pestañas de audio y gráficos consultan dispositivos; si alguna falla, se registra y se informa, sin ocultarlo.

## Paso 3 (después, aparte): D3D10/11 en 64 bits

- Requiere que el programa no corra como invitado. La idea es que `ps4_guest_launch` (`tools/build-guest-hw.py`) mire `AppDefaults\<exe>\DllOverrides\dxgi` y, si es native, use el relanzamiento como con los de 32 bits.
- Riesgo abierto: en ese proceso propio de 64 bits sigue el loader de Khronos, que carga `dxgi` para verificar drivers. Con el `dxgi` de DXVK eso puede volver a entrar en `vkCreateInstance` desde DXVK. Hay que probarlo con un `d3d11test64.exe` antes de darlo por bueno.

## Archivos

| Archivo |Paso| Comparte con la sesión principal |
|---|---|---|
| `tools/build-wine-hardware.py` | 1 | sí (bloque DXVK, overrides, fixtures) |
| `fixtures/win32/d3d11test.c` | 1 | no (nuevo) |
| `tools/stage-wine-programs.py` | 2 | no se verifica por hash; hay que re-correrlo |
| `tools/make-start-menu.py` | 2 | sí (la salida la copia build-wine-hardware) |
| `tools/upload-hardware.py` | 2 | sí (fusión de `user.reg`) |
| `tools/build-guest-hw.py` | 3 | sí |

`joy.cpl`, que también es parte de la fase 7, queda para después de xinput (fase 5).
