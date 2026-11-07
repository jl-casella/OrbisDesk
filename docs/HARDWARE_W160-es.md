# W160: tiempo por operación de wined3d y syscalls por hilo (fase 6)

[English](HARDWARE_W160.md) | [Español](HARDWARE_W160-es.md)

APP_VER 02.59. Base W159.

## Para qué

W159 mostró que en SuperMarioKart:
- el hilo de command stream de wined3d pasa el 74 % del tiempo en código de 32 bits;
- el hilo del juego pasa el 80 % en unas 59.000 syscalls por segundo.

Faltan dos datos:
- **En wined3d:** el 74 % incluye el tiempo que el hilo gira sin trabajo (`YieldProcessor` hasta `WINED3D_CS_SPIN_COUNT`, 2000 vueltas) antes de dormir. Si ese giro pesa, el límite no es wined3d sino quien le da trabajo.
- **En el juego:** qué syscall hace tantas veces.

## Cambio

- **`tools/build-wined3d-hw.py` (nuevo):**
  - arma el `wined3d.dll` de 32 bits con `cs.c` revisado, por el mismo método que `build-ddraw-hw.py`;
  - `tools/build-wine-hardware.py` lo pone sobre el staged;
  - el hilo de command stream informa cada 2³² ticks del TSC (~2,7 s):
    - `PWCS window kticks wall=… exec=… spin=… wait=… waits=…`: tiempo total, ejecutando operaciones, girando con la cola vacía, y dormido esperando trabajo;
    - `PWCS ops count/kticks: …`: las ocho operaciones más costosas, con cantidad y tiempo, en miles de ticks.
- **`tools/build-wow64native-ps4.py`:**
  - `Wow64SystemServiceEx` cuenta cada syscall y sus ticks, por hilo (los primeros ocho);
  - cada ~2,7 s, `PWSYSCALL tid=… total=… count/kticks: …` con las seis más frecuentes de cada hilo;
  - las de ntdll van por nombre y las de win32u como `w32:<id>`, que se traduce con la lista de syscalls de win32u.
- **`native/wine_hardware.c`:** pasa `PW_QPC_TSC_HZ` con `sceKernelGetTscFrequency()` en las corridas de 32 bits, para que el perfilador de wow64native use la frecuencia real (en W159 midió 22 GHz).

## Prueba física

Reporte: `reports/wine-hardware-w160/physical/20261103T151524Z`, `run-0002.log` (SuperMarioKart, ~80 s). Respuesta del usuario: "Anduvo igual". ~16 fps.

**Reloj:** `tsc_hz=1594020272` (sceKernelGetTscFrequency).

**Hilo de command stream de wined3d (`PWCS`, ventanas de 2³² ticks ≈ 2,7 s):**
- **Reparto del tiempo:** ejecuta operaciones el 88–91 %; gira con la cola vacía menos del 1 %; duerme 7–10 %. No está esperando trabajo: está ocupado de verdad.

| Operación | Por ventana | Miles de ticks | % del hilo | Cada una |
|---|---|---|---|---|
| `BLT_SUB_RESOURCE` | 279–308 | 2,75–3,1 millones | 64–71 % | ~6,2 ms |
| `DRAW` | 9.100–10.500 | 610.000–680.000 | ~15 % | ~2,7 µs |
| `UPDATE_SUB_RESOURCE` | 12.600–14.300 | ~140.000 | ~3 % | ~6 µs |
| `PRESENT` | 40–44 | ~65.000 | ~1,5 % | ~1 ms |

- Con ~40 cuadros por ventana son unas 7 copias 2D por cuadro, ~44 ms de los ~64 ms del cuadro.

**Syscalls (`PWSYSCALL`):**
- **Hilo del juego (0024):** ~147.000 por ventana, ~54.000 por segundo; 99 % son `NtDelayExecution` (`Sleep` cortos), ~65 % de su tiempo. Espera a wined3d durmiendo de a poco; no es trabajo.
- **Otros hilos:** casi sólo `NtWaitForSingleObject` y `NtDelayExecution`, es decir, esperas.

**Conclusión:**
- El cuello son las copias 2D (`Blt` de DirectDraw): cada una cuesta ~6 ms en el hilo de wined3d.
- El blitter de Vulkan de wined3d (`vk_blitter_blit_supported`, `texture_vk.c`) sólo acepta copias simples (`COLOR_BLIT`/`RAW_BLIT`) entre recursos con acceso de GPU. Las que tienen color key o alpha test, o superficies en memoria de sistema, caen al blitter de CPU: baja la imagen de la GPU, copia y la vuelve a subir.
- Es lo más probable, pero no está confirmado: W161 registra qué son esas copias.
