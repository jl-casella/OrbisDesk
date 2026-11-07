# W127: DirectDraw y Direct3D 7 con wined3d sobre Vulkan (fase 4b)

[English](HARDWARE_W127.md) | [Español](HARDWARE_W127-es.md)

APP_VER 02.26. Base W126 (fase 4 aceptada: D3D9 con DXVK en 32 y 64 bits).

## Enfoque

- El wined3d de nuestro Wine fijado tiene renderer Vulkan con fixed-function emulado en HLSL (`dlls/wined3d/ffp_hlsl.c`, `d3d_info->ffp_hlsl = true` en `adapter_vk.c`). Es lo que necesitan ddraw y D3D7 (Blitz3D), y no depende de OpenGL, que en la PS4 no tiene contexto.
- Su presentación usa la misma ruta que DXVK: vulkan-1 → winevulkan → WSI headless → ventana.
- El renderer se elige por proceso:
  - Los programas de 32 bits, que se relanzan solos, reciben `WINE_D3D_CONFIG=renderer=vulkan` (`native/wine_hardware.c`).
  - El escritorio de 64 bits conserva `renderer=no3d`: dxgi sólo enumera para el loader de Khronos y MangoHud (W087).
- DXVK sigue atendiendo d3d8/d3d9/d3d10core/d3d11. wined3d sólo dibuja ddraw (DX1–7).

<a id="fixture"></a>


## Fijación

`fixtures/win32/ddraw7test.c` → `C:\orbis\ddraw7test32.exe`:
- `DirectDrawCreateEx`, cooperativo normal, primaria con clipper, superficie 3D fuera de pantalla, `IDirect3D7::CreateDevice(IID_IDirect3DHALDevice)`;
- después ~5 s de Clear con color que cambia, un triángulo XYZRHW|DIFFUSE y un Blt a la primaria;
- `ddraw7-result.txt` guarda el HRESULT de cada paso, los cuadros y los ms.

## Entrega

`/data/pkg/orbis-win-W127-c0d3ae3d3672.pkg`, con la lectura de vuelta verificada. W126 retirado.

## Prueba

1. `C:\orbis\ddraw7test32.exe`: se espera el triángulo sobre fondo cambiante.
2. `SuperMarioKart.exe`: lo que muestre (menú, error, nada).

Riesgos:
- La compilación HLSL → SPIR-V (vkd3d-shader) corre bajo el traductor de 32 bits y puede tardar o fallar.
- Los caminos de ddraw que el renderer Vulkan de wined3d todavía no implementa.

## Resultado físico: 20261103T003912Z

- **ddraw7test32.exe**:
  - Todos los pasos devuelven 0 (create, coop, primary, clipper, target, d3d7, device, clear, draw y blit), pero da **55 cuadros en 5 s** y la ventana queda en blanco (confirmado por el usuario).
  - Log: `wined3d_texture_vk_load_texture Unimplemented load from WINED3D_LOCATION_DRAWABLE`, `vk_blitter_blit Failed to load the destination sub-resource`. No hubo ningún `show_frame`.
  - El dispositivo D3D7 y el FFP en HLSL funcionan. Lo que falla es mostrar la primaria.
- **SuperMarioKart.exe**: abre, falla por el mismo motivo y Blitz muestra «access violation» (excepción C++ `e06d7363`). Sale con 0.
- Causa: en modo ventana (`DDSCL_NORMAL`), `ddraw_surface_update_frontbuffer` copia la primaria al *front buffer* del swapchain. En OpenGL eso es la ventana; en el renderer Vulkan de wined3d ese front buffer no se puede ni leer ni escribir (`DRAWABLE`).

# W128 (02.27)

- `tools/build-ddraw-hw.py` (nuevo, mismo método que taskmgr/explorer) compila un `ddraw.dll` i386 con `surface.c` revisado. Si `WINE_D3D_CONFIG` pide `renderer=vulkan`, la actualización de la primaria sin flip:
  - copia la parte visible del rectángulo (intersección con el área cliente de la ventana del swapchain, en coordenadas de pantalla) al **back buffer**;
  - la presenta con `wined3d_swapchain_present`, con el rectángulo origen en coordenadas de pantalla y el destino en coordenadas de cliente.
  - Los fallos quedan como `PWDDRAW … failed`.
- Reemplaza el ddraw i386 en syswow64 y en `lib/wine/i386-windows`.
- El flip a pantalla completa (`swap_interval > 0`) no cambia: ya usaba el back buffer.

Entrega: `/data/pkg/orbis-win-W128-f41bc03a1d20.pkg`, con la lectura de vuelta verificada. W127 retirado.

## Resultado físico W128: 20261103T005338Z

- **ddraw7test32.exe: DirectDraw 7 / Direct3D 7 funciona.**
  - Se ve el triángulo, confirmado por el usuario.
  - `ddraw7-result.txt`: todos los pasos en 0, **1208 cuadros en 5000 ms (~240 FPS)**; el log reporta ~290 presentaciones por segundo y la salida es 0.
  - El camino es wined3d (renderer Vulkan, FFP en HLSL) → back buffer → present.
- **SuperMarioKart.exe**:
  - Abre su ventana: un primer cuadro de 400×300 y después el modo de 800×600 (`show_frame n=1/n=2`).
  - Luego `guest exception 0xc0000005 at eip 0x10027948 … address 0x4 write 0`, una lectura de NULL+4 en el código del propio juego. Blitz lo informa como «access violation».
  - Hipótesis: el proceso relanzado no arranca en la carpeta del juego. Se pasa el EXE y sus argumentos pero no el directorio, así que las cargas relativas (`SMK\*.x`, `.png`) fallan y devuelven NULL.

# W129 (02.28)

`native/wine_hardware.c`: un programa que arranca solo (relanzamiento o `launch.txt`) hace `chdir` a la carpeta de su EXE antes de iniciar Wine, que toma de ahí el directorio actual del proceso, como haría Explorer. Log: `program_cwd dir=… rc=…`. Entrega: `/data/pkg/orbis-win-W129-87ebc14d997c.pkg`, con la lectura de vuelta verificada; W128 retirado.

## Resultado físico W129: 20261103T005957Z

`program_cwd … rc=-1 errno=1`: el kernel niega `chdir` al título (EPERM). El juego siguió arrancando fuera de su carpeta y el fallo se repite igual (`eip 0x10027948 … address 0x4`). La hipótesis del directorio todavía no se pudo probar.

# W130 (02.29)

- Se intentó primero redirigir `getcwd` con `--wrap` en el enlace, pero `create-fself` lo rechaza (`missing library for symbol (getcwd)`), así que se descartó.
- `tools/build-env-ps4.py` (nuevo) recompila el `env.c` probado de ntdll, verificado por hash, con un solo cambio: `get_initial_directory` usa `PW_PROGRAM_DIR` (ruta Unix) antes que el cwd Unix. Log: `PWBOOT initial_directory …`.
- El lanzador pasa `--env=PW_PROGRAM_DIR=<carpeta del EXE>` a los programas que arrancan solos (`program_cwd … via=PW_PROGRAM_DIR`). `build-wine-hardware.py` sustituye `env.o`.

Entrega: `/data/pkg/orbis-win-W130-d7994349f00c.pkg`, con la lectura de vuelta verificada. W129 retirado.

## Resultado físico W130: 20261103T014428Z

- `PWBOOT initial_directory /data/wine-prefix/drive_c/users/orbis/Documents/SuperMarioKart`: el juego ya arranca en su carpeta. Aun así el fallo es el mismo (`eip 0x10027948 … address 0x4`), así que el directorio no era la causa.
- Desensamblado del EXE (copia temporal en WSL `/tmp`, borrada después; el juego no se modificó):
  - `0x10027948` es la función de Blitz que dibuja una imagen.
  - Las cadenas vecinas son `Image does not exist` (0x1011454c) e `Image frame out of range` (0x10114530).
  - Con el puntero de imagen en 0 (`edi=0`) salta directo a `mov 0x4(%edi)`.
  - Es decir, un `LoadImage` devolvió 0 y el juego intentó dibujarlo.
- Los 241 archivos de `SMK` están en la consola. Hipótesis: falla la creación de la superficie de ddraw para la imagen ya decodificada, o la apertura del archivo.

# W131 (02.30)

- Los runs PE32 usan `WINEDEBUG=warn+module,trace+seh,trace+loaddll,warn+debugstr, trace+ddraw,trace+file,warn+d3d,warn+vulkan`, para ver cada llamada a ddraw y cada apertura de archivo. Se quita el trace de Vulkan de W117.
- Antes de compilar, el disco C: se llenó (0 MB libres). Con autorización del usuario se borraron sólo las carpetas `runtime/` de `build/wine-hardware-w001` … `w125` (45,9 GB, copias que se regeneran). Se conservan W126–W131, reports, logs y paquetes.
- Entrega: `/data/pkg/orbis-win-W131-5328384a488f.pkg`, con la lectura de vuelta verificada. W130 retirado.

## Resultado físico W131: 20261103T023957Z

- SuperMarioKart.exe: `CreateFileW L"smk/splash800x600.png"` → `…/SuperMarioKart/SMK/ splash800x600.png` (la búsqueda sin distinguir mayúsculas funciona) y devuelve handle. Abre el archivo dos veces y falla en `0x10027948`.
- Entre las dos aperturas no hay ningún `NtReadFile` ni `NtQueryInformationFile`. Lo más probable es que la imagen se lea por sección (`NtCreateSection`/`NtMapViewOfSection`), que el canal `file` no traza. En la PS4 los mapeos de archivos de datos pasan por `map_file_into_view`.
- Antes del juego: plugins de FreeImage (`*.fip`, `plugins\*.fip`), ninguno, lo cual es normal.

# W132 (02.31)

Los runs PE32 suman `trace+virtual,trace+section`. Entrega: `/data/pkg/orbis-win-W132-d4d3b4712798.pkg`, con la lectura de vuelta verificada (sólo cambió el ELF). W131 retirado.

## W132–W133: causa raíz de SuperMarioKart

- W132 (`trace+virtual`): entre las dos aperturas del PNG no hay mapeo de sección ni lectura.
- W133 trajo `fileio32.exe` (`fixtures/win32/fileio_test.c`), que abre el mismo PNG con la misma grafía (`smk\`). El resultado (`fileio-result.txt`, run de 20261103T03xx):
  - CreateFile, GetFileSize (438750), ReadFile (`89504e47`, PNG), MapViewOfFile, fopen, fread, `_open` y `_read` funcionan.
  - **`GetFileType=0 error=50`**: FILE_TYPE_UNKNOWN con ERROR_NOT_SUPPORTED.
- `get_device_info` (ntdll/unix/file.c) devolvía `STATUS_NOT_SUPPORTED` en ORBIS para todo descriptor. El runtime de C de MSVC que usa Blitz3D clasifica el handle con `GetFileType` al abrir; con «desconocido» lo cierra y da la apertura por fallida. Por eso hay dos aperturas sin lecturas, `LoadImage` devuelve 0 y la función de dibujo lee NULL+4. El runtime de mingw (`fopen` en fileio32) no hace esa comprobación.

# W134 (02.33)

`tools/build-wine-directory-ps4.py` (el `file.o` que ya se recompila) implementa `get_device_info` en ORBIS desde `fstat`:
- archivo o directorio → `FILE_DEVICE_DISK_FILE_SYSTEM`;
- FIFO o socket → `FILE_DEVICE_NAMED_PIPE`;
- dispositivo de caracteres → `FILE_DEVICE_UNKNOWN`;
- `Characteristics` = 0, sin inventar banderas de extraíble, remoto ni sólo lectura.

Afecta a todos los programas, también los de 64 bits. Entrega: `/data/pkg/orbis-win-W134-cf64b54dcb8a.pkg`, con la lectura de vuelta verificada; W133 retirado.

## Resultado físico W134: 20261103T032832Z — SuperMarioKart corre

- `fileio32.exe`: **`GetFileType=1`** (FILE_TYPE_DISK). Lo demás, igual que antes.
- **SuperMarioKart.exe ya no se cae**:
  - Carga la imagen de presentación, abre el audio y presenta a 800×600 a **~12 FPS** estables (`PWVK present fps 11.4–12.0`) por varios minutos. No hay `raise_guest_exception`. La corrida seguía viva cuando se recogió el log (54443 líneas).
  - El audio sale en cero (`PWAUDIO level … peak=0`). La música del juego son archivos `.mid`, y en la PS4 no hay sintetizador MIDI (winmm no tiene dispositivo MIDI). Los efectos `.wav` por FMOD no aparecieron todavía en este tramo.
- Falta que el usuario confirme lo visible (menú, controles). El rendimiento (12 FPS) está limitado por el traductor de 32 bits, wined3d en la CPU y la presentación por la CPU (fases 5 y 6).
- El vigilante (`tools/watch-hardware-run.py`) no detectó estas corridas: cada pasada abortaba con un 550 del FTP en un log que se estaba escribiendo. Ahora salta ese archivo en esa pasada; se probó con la corrida de fileio32.

**Fase 4b aceptada.** El usuario confirmó que SuperMarioKart.exe (Blitz3D, DirectDraw 7 / Direct3D 7, 32 bits) muestra su menú en la PS4 con W134. Pendiente: música MIDI (no hay sintetizador), confirmar controles, velocidad (~12 FPS).
