# W116: programas de 32 bits (fase 1 del plan PE32)

[English](HARDWARE_W116.md) | [Español](HARDWARE_W116-es.md)

APP_VER 02.15. Base W115, que trae Solitaire y Spider en Start → Games.

## Objetivo

Que un PE32 (i386) se pueda abrir desde el escritorio. Es el primer paso para SuperMarioKart.exe y para juegos de 32 bits en general (Direct3D y audio van en fases siguientes).

## Cambios

- **kernelbase** (`tools/build-guest-hw.py`, `CreateProcessInternalW`):
  - Un EXE con `Machine == I386` deja de recibir `reject_title_replacement`.
  - Explorer muestra un diálogo: OrbisDesk se reinicia y ejecuta el programa solo, y los programas abiertos se cierran.
  - Si el usuario acepta, sigue a `NtCreateUserProcess`, que relanza el título con ese programa (`pw_hw_switch_program`). Si cancela, se devuelve `STATUS_CANCELLED`.
  - Log: `PWOPEN pe32_relaunch image=… answer=…`.
- **launcher** (`native/wine_hardware.c`):
  - `pe_machine()` lee la cabecera PE del EXE que se va a ejecutar (sólo unidad C:).
  - Si es 0x14c, pasa `--wow64-cpu=wowprospero.dll`. Esa opción se perdió en W015; sin ella wow64 busca `wow64cpu.dll`, que el prefix no trae.
  - Log: `pe_machine path=… machine=…` y `calling_wine_boot_main cpu=wowprospero`.
- **fixture**: `C:\orbis\gui-window32.exe`, que es `fixtures/win32/gui_window.c` compilado con `i686-w64-mingw32-gcc`. Pinta la ventana de un color, a los 2 s escribe `C:\orbis\result.txt` y se cierra.

No cambia lo que corre en PE64; los invitados siguen igual.

## Entrega

`/data/pkg/orbis-win-W116-3d23071b5e56.pkg`, con la lectura de vuelta verificada; informe reports/wine-hardware-w116/transfers/20261102T202916Z.json (564 archivos, 9 subidos). W115 retirado.

## Prueba

1. En File Manager abrir `C:\orbis\gui-window32.exe`, aceptar el diálogo y esperar al relanzamiento. Tiene que aparecer una ventana azul unos 2 s; después se cierra y vuelve el escritorio.
2. Abrir `Documents\SuperMarioKart\SuperMarioKart.exe`. Se espera que falle por falta de Direct3D, y lo que importa es dónde falla.

```sh
python3 tools/fetch-hardware.py --build W116 --host 192.168.68.104
```

En el log hay que buscar:
- `pe32_relaunch` y `switch_program`;
- en el run siguiente, `cpu=wowprospero` y `wow64: CPU`;
- `result.txt` con `painted=1;pixel=8c3c14`;
- `return_to_desktop`.

Riesgos:
- Un PE32 GUI nunca corrió en la PS4. Sólo corrió `console32-bare` en W013/W014.
- Tampoco se probó en hardware la SEH de 32 bits ni x87/SSE bajo wowprospero.

## Resultado físico: 20261102T203507Z

- **run-0001** (escritorio): `PWOPEN pe32_relaunch image=C:\orbis\gui-window32.exe answer=1`, luego `switch_program`. El diálogo y el relanzamiento funcionan.
- **run-0002** (el programa de 32 bits solo):
  - `pe_machine machine=0x14c`, `cpu=wowprospero` y `wow64: CPU wowprospero.dll from WINE_PS4_WOW64_CPU`.
  - Cargan ntdll de syswow64, wow64, wow64win, kernel32, user32, gdi32, imm32 y msvcrt de 32 bits. Es el primer PE32 GUI que llega tan lejos en la PS4.
  - Después de que win32u inicializa Vulkan (RADV hasta `ac_query_gpu_info = 0`), una llamada al sistema de win32u salta a la dirección 0 (`handle_syscall_fault code=c0000005 addr=0 ip=0`) y vuelve con c0000005.
  - En el escritorio de 64 bits, ese mismo punto termina en `wgl:internal_context_create Failed to create internal thread context`, sin fallar.
  - El log termina en `NtGdiCreateBitmap planes = 0`: no hay ventana, no hay result.txt y no hay vuelta al escritorio.
- SuperMarioKart.exe no figura en estos logs.

Todavía no se sabe qué llamada es: el rastro no dice qué función quedó en NULL. W117 (02.16) sólo agrega trazas para runs PE32 (`trace+wgl,trace+vulkan,trace+wow`) y nada más cambia. Está subida en `/data/pkg/orbis-win-W117-540833c24102.pkg`, con la lectura de vuelta verificada. Hay que repetir la prueba de gui-window32.exe.

## W117 → W118: la llamada nula

W117 (20261102T204218Z, run-0002) dejó la traza que faltaba:

- `Instance proc vkGetPhysicalDeviceProperties2 not found`. La instancia Vulkan propia de win32u es 1.0: sólo se resuelven las funciones `…2KHR` de `VK_KHR_get_physical_device_properties2`.
- RADV anuncia `VK_EXT_map_memory_placed` y `VK_KHR_map_memory2`. En WoW64 (`zero_bits != 0`), `init_physical_device` (`dlls/win32u/vulkan.c:516`) llama a `instance->p_vkGetPhysicalDeviceProperties2`, sin KHR, que es NULL. En 64 bits esa rama no se ejecuta, por eso el escritorio no falla.

W118 (02.17), en `tools/build-win32u-ps4.py`, usa `p_vkGetPhysicalDeviceProperties2KHR` en esa rama. Es un bug de Wine upstream que aparece con WoW64 sobre una instancia 1.0. Se recompiló win32u (47 unidades), se reenlazó el ELF (sin símbolos indefinidos) y se empaquetó. Entrega: `/data/pkg/orbis-win-W118-6eb3e742dc83.pkg`, con la lectura de vuelta verificada; W117 retirado. Las trazas PE32 de W117 se mantienen.

Prueba: repetir gui-window32.exe. Si pasa, ventana azul unos 2 s, `C:\orbis\result.txt` y `return_to_desktop`.

## Resultado físico W118: 20261102T204952Z — fase 1 aceptada

- run-0001: `pe32_relaunch answer=1` → `switch_program`.
- run-0002: `cpu=wowprospero`, `wow64: CPU wowprospero.dll`, ventana azul visible (confirmado por el usuario), `process_exit status=0`, `return_to_desktop`.
- `C:\orbis\result.txt` (leído por FTP): `painted=1;pixel=8c3c14;client=464x280`, el mismo color y la misma lectura que la referencia PE64.
- run-0003: el escritorio vuelve con normalidad.

Es el primer programa Windows GUI de 32 bits que corre en la PS4, con el traductor de prospero-win. No mide rendimiento ni prueba SEH, x87/SSE o código que se modifica.

## Lo que necesita SuperMarioKart.exe (inspección de importaciones)

Se copió a /tmp de WSL sólo para leer la tabla de importaciones y después se borró; el juego en la consola no se modificó.

- Es un juego Blitz3D (`Blitz Runtime Class`, `Unable to run Blitz Basic module`).
- Importa KERNEL32, USER32, GDI32, ADVAPI32, SHELL32, ole32, WSOCK32, WINMM, MSACM32, DDRAW (`DirectDrawCreateEx`), DINPUT (`DirectInputCreateEx`), d3dxof y DPLAYX.
- El audio es FMOD sobre DirectSound, cargado en tiempo de ejecución.
- Blitz3D usa **DirectDraw 7 / Direct3D 7**. DXVK no cubre D3D7 (sólo d3d8 en adelante), así que para este juego la fase 4 tiene que ser wined3d, no DXVK. Las opciones son el renderer Vulkan de wined3d sobre winevulkan i386, o el de OpenGL sobre un Zink i386.
- DLL i386 que faltan para arrancarlo: ddraw, wined3d, dinput, d3dxof, dplayx, wsock32, dsound y mmdevapi (más el driver de audio de la fase 3).
