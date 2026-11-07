# W124: Direct3D 8–11 con DXVK (fase 4 del plan PE32)

[English](HARDWARE_W124.md) | [Español](HARDWARE_W124-es.md)

APP_VER 02.23. Base W123 (fase 3 aceptada: audio de Windows en 32 y 64 bits).

## Elección

- La GPU expone **Vulkan 1.3** (`PWVK GPU: AMD Liverpool (PS4) (RADV BONAIRE), API 1.3.335`) y las extensiones que DXVK 2.x aprovecha: robustness2, descriptor_buffer, graphics_pipeline_library, extended_dynamic_state 1/2/3, maintenance5/6, transform_feedback y map_memory_placed. Se tomaron del log de W117.
- **DXVK 2.7.1** (`https://github.com/doitsujin/dxvk`, licencia zlib), el release mingw oficial sin modificar, fijado por SHA-256 `d85ce7c79f57ecd765aaa1b9e7007cb875e6fde9f6d331df799bce73d513ce87`.
  - Es la última de la línea 2.x. La 3.x usa un compilador de shaders nuevo que, según sus notas de versión, compila más en la CPU, y el Jaguar de la PS4 es el recurso más limitado.
  - prospero-win usa 2.6.2, de la misma línea.

## Cambios

- `tools/stage-dxvk.py`: verifica el archivo y extrae `out/dxvk/{x64,x32}` con su manifest.
- `tools/build-wine-hardware.py`:
  - d3d8, d3d9, d3d10core y d3d11 de DXVK van a `system32` (x64) y a `syswow64` (x32).
  - Overrides `native,builtin` en `user.reg`.
  - `vulkan-1` pasa de `native` a `native,builtin`: los programas de 32 bits no tienen vulkan-1 nativo (el de syswow64 es el builtin de Wine) y `native` solo lo rechazaría. Los de 64 bits siguen con el loader de Khronos.
  - **No** se instala el `dxgi.dll` de DXVK: el builtin de Wine sigue siendo el que usan el loader de Khronos y MangoHud (W087). D3D10/11 necesitan el dxgi de DXVK por programa; eso queda para la fase 7 (winecfg).
- Fixture `fixtures/win32/d3d9test.c`, en `C:\orbis\d3d9test64.exe` y `d3d9test32.exe`:
  - ventana, Direct3D9 HAL y ~5 s de cuadros (clear de color cambiante más un triángulo);
  - resultado en `C:\orbis\d3d9-result.txt`: adaptador, HRESULT de cada paso, cuadros y ms;
  - DXVK escribe además su log junto al exe (`d3d9test64_d3d9.log`).

## Entrega

`/data/pkg/orbis-win-W124-f3bdc91ecf00.pkg`, con la lectura de vuelta verificada (613 archivos). W123 retirado.

## Prueba

1. `C:\orbis\d3d9test64.exe` (invitado): ¿se ve la ventana con el triángulo sobre fondo que cambia?
2. `C:\orbis\d3d9test32.exe` (relanzamiento, WoW64): lo mismo.

Después hay que leer `d3d9-result.txt`, los logs de DXVK junto a cada exe y el run log (fetch-hardware.py --build W124).

Riesgos:
- Que DXVK rechace el dispositivo por alguna feature que falte en GFX7; su log lo dice.
- Los mapeos de memoria por debajo de 4 GiB en 32 bits (`VK_EXT_map_memory_placed`, que RADV anuncia pero nuestro winsys nunca probó).
- La presentación pasa por la copia a CPU de siempre.

## Resultado físico: 20261103T000821Z

**64 bits (d3d9test64.exe, invitado)**: DXVK 2.7.1 funciona en la PS4 hasta el primer cuadro.
- `Found device: PS5 (radv 26.0.8)`. Crea el dispositivo con robustness2, descriptor_buffer, graphics_pipeline_library, extended_dynamic_state3, maintenance5–7, transform_feedback, geometry y tessellation.
- Swapchain `B8G8R8A8_UNORM`, FIFO, 632×453, 5 imágenes. Los submits a la GPU completan (`radv/ps4: submit 1..4 … GPU completed`).
- `PWVK show_frame n=1`: el primer cuadro se dibujó en la ventana.
- Después el hilo presentador de DXVK llama `vkWaitForPresentKHR`. El WSI headless de RADV no lo implementa, así que salta a la dirección 0 (`handle_syscall_fault … ip=0`, `Exception 0xc0000005 in Unix call`) y DXVK termina con status 3.

**32 bits (d3d9test32.exe, WoW64)**:
- DXVK x86 llega a crear el dispositivo (36 extensiones).
- `win32u_vkMapMemory2KHR vkMapMemory2EXT failed: -5` y `Failed to map Vulkan memory: VK_ERROR_MEMORY_MAP_FAILED`. `CreateDevice` devuelve `D3DERR_NOTAVAILABLE` (8876086a).
- Causa: en la rama `__PS4__` de `radv_amdgpu_winsys_bo_map` (Mesa de Crema), un mapeo ubicado (`use_fixed_addr`, `VK_EXT_map_memory_placed`) devuelve NULL. Sin mapeos por debajo de 4 GiB, ninguna memoria visible por CPU funciona para un proceso de 32 bits.

# W125 (02.24)

`tools/build-win32u-ps4.py`: `init_physical_device` deja de ofrecer `VK_KHR_present_id`, `present_id2`, `present_wait` y `present_wait2`, porque el WSI headless no implementa la espera. DXVK vuelve a su ritmo sin ellas.

Entrega: `/data/pkg/orbis-win-W125-49f75d9ba11e.pkg`, con la lectura de vuelta verificada. W124 retirado.

Prueba: d3d9test64.exe. Se espera el triángulo sobre fondo cambiante ~5 s y `d3d9-result.txt` con `frames>0`.

**Pendiente para 32 bits**: implementar el mapeo ubicado en el winsys de GNM.
- Mapear de nuevo la memoria directa del BO en la dirección que elige Wine (`sceKernelMapDirectMemory` con `MAP_FIXED`, alineación de 16 KiB) y reportar esa alineación en `minPlacedMemoryMapAlignment`.
- Al desmapear, devolver la reserva a Wine.
- Requiere recompilar Mesa (`tools/vk-h0/build-mesa.sh`, `VARIANT=wine`).

## Resultado físico W125: 20261103T001804Z — Direct3D 9 de 64 bits aceptado

- `d3d9-result.txt`: `adapter=00000000:PS5;device=00000000;clear=0;draw=0;present=0; frames=1204;ms=5003`. Son **~240 cuadros por segundo** con un triángulo y un clear por cuadro, en una ventana de 632×453.
- Log: `PWVK present fps 170.6 → 251.8 → 276.3`, copia a la ventana por GDI en ~1,2–1,6 ms por cuadro, sin `Exception`. Salida del invitado con 0 (`loader_lock=1`, `other_threads_wait=0 count=5`) y escritorio intacto.
- DXVK 2.7.1 x64 sobre winevulkan → RADV (GFX7) → GNM funciona en la PS4.
- Límites: la presentación sigue pasando por la CPU (fase 6) y la prueba es mínima. No dice nada de shaders reales, texturas ni rendimiento de un juego.

# W126 (en preparación): mapeos ubicados para 32 bits

`tools/vk-h0/patch-mesa-placed.py`, llamado desde `build-mesa.sh` (`VARIANT=wine`):
- `ac_ps4_bo_cpu_map_fixed` (en `ac_ps4_drm.c`) mapea otra vez la memoria directa del BO, sólo para la CPU, en la dirección que reservó Wine (`sceKernelMapDirectMemory` con `MAP_FIXED`, longitud redondeada a 16 KiB). La GPU conserva su mapeo y ambos comparten las mismas páginas físicas.
- La rama `__PS4__` de `radv_amdgpu_winsys_bo_map` lo usa cuando `use_fixed_addr`, en vez de devolver NULL.
- `minPlacedMemoryMapAlignment` pasa a 16 KiB en PS4 (antes, la página del sistema). Wine reserva con granularidad de 64 KiB, así que el redondeo queda dentro de su reserva.

Compilado: Mesa recompilado (el primer intento falló por `-Wmissing-prototypes`; se agregó el prototipo) y la telemetría GPU reconstruida sobre la nueva `libamd_common`. El ELF contiene `placed map of bo`. Entrega W126 (02.25): `/data/pkg/orbis-win-W126-662aff853a70.pkg`, con la lectura de vuelta verificada; W125 retirado.

Prueba: d3d9test32.exe (relanzamiento, WoW64). Se espera el mismo triángulo y `d3d9-result.txt` con `frames>0`; d3d9test64.exe como regresión.

## Resultado físico W126: 20261103T003114Z — Direct3D 9 de 32 bits aceptado

- **d3d9test32.exe** (relanzamiento, wowprospero):
  - `Using placed map with alignment 16384` y mapeos ubicados en 0x3080000, 0x3790000, 0x3b90000 y 0x4b90000, todos por debajo de 4 GiB, sin `vkMapMemory2EXT failed`.
  - `d3d9-result.txt`: todos los pasos en 0, **1290 cuadros en 5000 ms (~258 FPS)**; el log reporta ~295 presentaciones por segundo.
  - `process_exit status=0` y vuelta al escritorio.
- **d3d9test64.exe** (regresión): ~250 FPS y salida 0.
- **Fase 4 (D3D9 con DXVK) aceptada en 32 y 64 bits.** Es un caso mínimo: no prueba shaders reales, texturas, juegos ni rendimiento con carga. D3D10/11 no se probaron y necesitan el dxgi de DXVK por programa (fase 7). D3D8 va por el mismo d3d9 de DXVK y tampoco se probó.
