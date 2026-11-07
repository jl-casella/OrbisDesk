# W172: Direct3D 10/11 en 32 bits con el dxgi de DXVK, y winecfg (fase 7)

[English](HARDWARE_W172-fase7-borrador.md) | [Español](HARDWARE_W172-fase7-borrador-es.md)

APP_VER (completa la sesión principal). Base W171.

## Punto de partida

- W124 instaló d3d8, d3d9, d3d10core y d3d11 de DXVK 2.7.1, pero no su `dxgi.dll`.
- El escritorio de 64 bits usa el `dxgi` builtin de Wine: el loader de Khronos verifica los drivers con una fábrica DXGI y MangoHud le pide la GPU (W087). Los programas de 64 bits corren como invitados dentro de ese proceso (W052), y un proceso no puede tener dos `dxgi.dll`.
- El `d3d11` de DXVK necesita el `dxgi` de DXVK. Por eso D3D10/11 no funcionaba.

## Cambios

- `tools/build-wine-hardware.py`:
  - el `dxgi.dll` de 32 bits de DXVK va a `syswow64`; `system32` sigue con el de Wine;
  - override `"dxgi"="native,builtin"` en `user.reg`.
    - En 32 bits, cada programa corre en su propio proceso (W116), con el `vulkan-1` builtin de Wine y sin loader de Khronos, y encuentra el `dxgi` de DXVK.
    - En 64 bits, `system32\dxgi.dll` es el de Wine, que lleva la firma de builtin y por eso se sigue cargando como builtin (`dlls/ntdll/loader.c`).
  - compila `fixtures/win32/d3d11test.c` como `C:\orbis\d3d11test32.exe` y `C:\orbis\d3d11test64.exe`.
- `fixtures/win32/d3d11test.c` (nuevo):
  - ventana, `D3D11CreateDeviceAndSwapChain` y ~5 s de `ClearRenderTargetView` con un color que cambia;
  - `d3d11-result.txt` anota el HRESULT de cada paso, el nivel de features, el adaptador DXGI, la ruta del `dxgi.dll` cargado, los cuadros y los ms;
  - no usa shaders: es un caso mínimo, como `d3d9test`.
- `tools/stage-wine-programs.py`: agrega `winecfg.exe` (PE64). Su cierre de imports suma `uxtheme.dll` y `msimg32.dll`.
- `tools/make-start-menu.py`: "Wine Configuration" en System Tools.
- `tools/upload-hardware.py`: `user.reg` se fusiona al subir.
  - Wine reescribe el registro en la consola: en W108–W112 `user.reg` y `system.reg` figuraban siempre como `uploaded`. Por eso una subida común borraba lo que se guardara con winecfg.
  - Ahora se baja el `user.reg` de la consola. Los bloques de `HKCU\Software\Wine\AppDefaults` (lo que winecfg guarda por programa) salen de la consola; todo lo demás, de la build.
  - Se sube el resultado y se verifica con su hash. El registro de la subida tiene `user_reg` con el origen, los bloques conservados y los tres hashes.
  - Si en la consola no hay `user.reg`, o no empieza con `WINE REGISTRY Version 2`, se sube el de la build tal cual y se anota.
  - Probado sin conexión contra el `user.reg` de W167:
    - fusionado con sí mismo da el mismo archivo;
    - conserva los bloques por programa de la consola;
    - los overrides globales siguen siendo los de la build;
    - una segunda subida no cambia nada.

Para construir: `tools/stage-wine-programs.py` y `tools/make-start-menu.py` antes de `tools/build-wine-hardware.py`.

## Límites

- D3D10/11 en 64 bits sigue sin funcionar: un invitado comparte el `dxgi` de Wine del escritorio. `d3d11test64.exe` está para confirmarlo, no para que pase. Requiere que esos programas se relancen como los de 32 bits; queda como paso aparte (riesgo: el loader de Khronos carga `dxgi` y, con el de DXVK, puede volver a entrar en `vkCreateInstance`).
- Solo se conservan los ajustes por programa de winecfg. Los globales ("Default settings") los pone la build.
- Hay que cerrar la app antes de instalar una build. Si está abierta durante la subida, Wine vuelve a escribir `user.reg` dentro de los 30 s y pisa el archivo fusionado.
- `uxtheme.dll` ahora existe en el prefijo. Explorer lo intentaba cargar y fallaba (`c0000135`); ahora lo carga. Sin un tema instalado, el aspecto debería seguir siendo el clásico.
- `joy.cpl` queda para después de xinput (fase 5).

## Prueba

1. `C:\orbis\d3d11test32.exe`: se espera la ventana con el fondo que cambia de color durante ~5 s. Después hay que leer:
   - `d3d11-result.txt`: `device=00000000`, `dxgi=` en `syswow64` y la cantidad de cuadros;
   - el log de DXVK junto al exe;
   - en el run log, `trace+loaddll` con `dxgi.dll` cargado como `native`.
2. Regresión de 32 bits:
   - `d3d9test32.exe`;
   - `ddraw7test32.exe`;
   - SuperMarioKart (wined3d/ddraw no usa `dxgi`, pero el override es global).
3. Regresión de 64 bits: `vkcube` o `vkspin64` con MangoHud. El escritorio tiene que seguir cargando el `dxgi` builtin (`trace+loaddll`).
4. `d3d11test64.exe` (invitado): se espera que falle en `device=`. Hay que anotar el código.
5. Inicio → Herramientas del sistema → Wine Configuración:
   - recorrer las pestañas; si alguna falla, anotar cuál y el log;
   - en Aplicaciones, agregar `d3d11test32.exe`, y en Bibliotecas poner `dxgi` = builtin;
   - cerrar la app y volver a abrirla: el ajuste tiene que seguir, y `d3d11test32.exe` tiene que fallar con el `dxgi` de Wine. Eso prueba que el ajuste por programa se aplica.
6. En la próxima subida, `user_reg.source=merged` y `app_default_blocks_kept` mayor que 1.

Riesgos:
- Que algo de 32 bits que hoy funciona use el `dxgi` de Wine sin que lo sepamos; la regresión del punto 2 lo cubre en parte.
- Las pestañas de audio y gráficos de winecfg consultan dispositivos y pueden fallar en la consola.
