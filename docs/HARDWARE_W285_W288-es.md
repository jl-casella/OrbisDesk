# W285–W288: streams de audio de invitados, carpeta de logs de GPU, menú GRÁFICOS y MangoHud en wined3d

[English](HARDWARE_W285_W288.md) | [Español](HARDWARE_W285_W288-es.md)

Cuatro builds sobre W284 (2026-11-07). Cada una mantiene la anterior. Paquete: `OrbisDesk.pkg`, ORBW00002.

| Build | APP_VER | Cambio | Resultado físico |
|---|---|---|---|
| W285 | 03.84 | Los streams de audio de un invitado salen del mezclador al descargarse | Probada: NFS U2 cerrado desde el overlay, sin stream colgado |
| W286 | 03.85 | Los logs de GPU de RADV van a `/data/orbisdesk/gpu` | Sin prueba propia |
| W287 | 03.86 | Entrada GRÁFICOS en el overlay; MangoHud en juegos con wined3d | Probada: MangoHud se engancha a SuperMarioKart; el renderer guardado no se aplicó |
| W288 | 03.87 | wined3d lee el renderer del programa en cada `wined3d_create` | Subida; sin probar todavía |

## W285: streams de audio de un invitado que termina

Evidencia de W284 (`reports/wine-hardware-w284/physical/20261107T153841Z/run-0001.log`):
- Need for Speed Underground 2 se cerró desde el overlay.
- Su stream de mmdevapi quedó en el mezclador del driver de audio de la consola, con `playing=1` y nada retenido, hasta que terminó OrbisDesk.
- Cada stream cerrado así habría dejado otro más.

Cambio:
- `tools/build-audio-ps4.py` (driver wineps4):
  - Cada stream registra el invitado del hilo que lo crea: `TEB.UserReserved[0]`, leído del TEB de 32 bits en las llamadas WoW64.
  - Se agrega una llamada Unix después de las 37 de mmdevapi. Saca los streams de un invitado del mezclador y los pasa a una lista de huérfanos.
  - Los huérfanos no se liberan. La lista de sesiones de mmdevapi, compartida por todos los invitados del proceso, sigue teniendo los clientes del invitado muerto y sus handles. Un release posterior libera el huérfano. Un handle que no está en ninguna lista se rechaza con `E_HANDLE`.
- `tools/build-guest-hw.py`: `ps4_guest_unload` llama al driver con `NtQueryVirtualMemory(MemoryWineLoadUnixLibByName)` y el `__wine_unix_call_dispatcher` de ntdll. Kernelbase no enlaza winecrt0.

Líneas de log: `PWAUDIO stream ... owner=... wow=1`, `PWAUDIO stream ... orphaned`, `PWAUDIO guest ...: N streams out of the mixer`.

Prueba física (`reports/wine-hardware-w285/physical/20261107T163224Z/`):
- NFS U2, cerrado desde el overlay, esa vez paró y liberó su propio stream, así que no hizo falta el camino de huérfanos.
- El dueño quedó registrado (`owner=0x23d3d50 wow=1`) y el mezclador no informó ningún stream después del cierre.
- El camino de huérfanos en sí todavía no se observó en el hardware.

Transferencia: `reports/wine-hardware-w285/transfers/20261107T162644Z.json`. SHA-256 del paquete `0c359ea9dff24a2f90f49f8809bb629092e3555aeab587799f4271e942317ed4`.

## W286: carpeta de logs de GPU

La carpeta de estado anterior, `/data/orbis-win`, se borró de la consola después de la migración de W283: 2.457 archivos y 538 carpetas. Las carpetas que crea el título tienen modo 755 y son del usuario del título, así que el FTP necesita `SITE CHMOD 777` antes de borrar adentro.

El winsys de RADV (`~/vk-h0/src/mesa-crema/src/amd/common/ac_ps4_drm.c`) todavía escribía `radv-ps4.log`, los reportes de cuelgue y falla de GPU y el flight recorder en `/data/orbis-win/gpu`. Su `mkdir` no crea las carpetas padre, así que sin la carpeta vieja esos archivos dejaban de escribirse sin aviso.

`tools/build-telemetry-ps4.py` ahora cambia las 17 rutas a `/data/orbisdesk/gpu` antes de compilar `libamd_common.a`. Se niega a seguir si queda alguna ruta vieja o si encuentra menos de 12 nuevas. Ese árbol de fuentes lo usa sólo la build `mesa-wine`.

La única cadena `/data/orbis-win` que queda en el ELF es el origen de la migración (`PW_LEGACY_STATE_ROOT`).

Transferencia: `reports/wine-hardware-w286/transfers/20261107T165854Z.json`. SHA-256 del paquete `f9d2889a5a99486165f4759495d628b9aa71dbeeb561d46f67f5336f894bacd4`.

## W287: entrada GRÁFICOS del overlay y MangoHud en wined3d

Los dos cambios los preparó como parches otra sesión y se integraron acá.

**GRÁFICOS (GRAFICOS)**, debajo de ESTIRAR en el overlay de control, por programa de 32 bits:
- Opciones: DXVK + Vulkan, DXVK + OpenGL, wined3d + Vulkan, wined3d + OpenGL.
  - Primera mitad: Direct3D 8/9 por DXVK o por los d3d8/d3d9 propios de Wine.
  - Segunda mitad: el renderer de wined3d.
- X le pide al closer de kernelbase que escriba `HKCU\Software\Wine\AppDefaults\<exe>\Direct3D\renderer` y `...\DllOverrides\d3d8`/`d3d9`, y que los lea de vuelta.
- El menú avisa que la elección se aplica desde el próximo arranque del programa.
- `syswow64\pw-wined3d\` tiene los d3d8.dll y d3d9.dll i386 de Wine. El ntdll i386 de los invitados los carga para un invitado cuyo propio AppDefaults dice `builtin`. Si no, el orden de carga en el mundo de explorer sale de la clave de explorer.exe.

Límites:
- Sólo programas de 32 bits.
- Un título relanzado no tiene closer.
- Dos juegos con d3d9 distintos cargados a la vez comparten un mismo nombre de módulo.

**MangoHud en wined3d:**
- Desde W259, wined3d tomaba `vkGetInstanceProcAddr` de winevulkan.dll, así que la capa implícita de MangoHud nunca entraba en la instancia de SuperMarioKart. El `in_front=1` de W284 era sólo una estimación del overlay.
- W287 compila el loader de Vulkan i386 desde una copia cuyo `loader_windows.c` no crea fábrica DXGI (`tools/vk-h0/patch-vulkan-loader-i386-nodxgi.py`). Esa fábrica era la recursión de W257 a través del dxgi de Wine.
- wined3d vuelve a probar primero `vulkan-1.dll`.

Prueba física (`reports/wine-hardware-w287/physical/20261107T215435Z/`):
- MangoHud se engancha a SuperMarioKart: `PWD3D vulkan library=vulkan-1.dll`, después `PWHUD i386 vkCreateInstance`, `vkCreateDevice` y `vkCreateSwapchainKHR 800x600`.
- GRÁFICOS guardó `dxvk-gl` para `SuperMarioKart.exe` y lo leyó de vuelta en el arranque siguiente, pero ese arranque siguió usando Vulkan.
  - wined3d se cargó una vez (`Using the Vulkan renderer`) y quedó cargado en el mundo de 32 bits después de la primera corrida.
  - Sólo lee su renderer en `wined3d_dll_init`.

Transferencia: `reports/wine-hardware-w287/transfers/20261107T173710Z.json`. SHA-256 del paquete `ac4a6d9f85f470e967a2f2d4a1f500be8d9559a79c985e7ad75f4b52444dc2ea`.

## W288: renderer por programa en cada objeto wined3d

`tools/build-wined3d-hw.py`, `wined3d_main.c`: `wined3d_create` llama a `pw_program_renderer()`. Esa función toma el renderer de:
1. el `AppDefaults\<exe>\Direct3D\renderer` del programa (`vulkan`, `gl` o `no3d`);
2. si no hay, el `WINE_D3D_CONFIG` del mundo;
3. si tampoco, el valor elegido cuando se cargó la DLL.

`GetModuleFileNameW(NULL)` da el nombre del invitado. Log: `PWD3D renderer=gl for L"SuperMarioKart.exe" from the program (was vulkan)`.

OpenGL para wined3d en el mundo de 32 bits de explorer (el opengl32 propio de Wine, Mesa WGL/Zink) todavía no corrió en la consola. Si falla, se espera que aparezca como error del adaptador de wined3d, no como un cambio silencioso a otro renderer.

## Relacionado

- Steam S2 01.06 y S3 01.07 pasaron en la consola: [STEAM_S2](STEAM_S2-es.md), [STEAM_S3](STEAM_S3-es.md).
- Se borraron las carpetas locales `build/wine-hardware-w001` a `w279` para liberar disco. Se conservaron los paquetes de `out/` y la evidencia de `reports/`.
