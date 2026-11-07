# W159: perfil de wow64native en programas de 32 bits (fase 6)

[English](HARDWARE_W159.md) | [Español](HARDWARE_W159-es.md)

APP_VER 02.58. Base W158, que no se probó por separado: incluye su arreglo de `dlopen`.

## Para qué

En W157, el hilo de command stream de wined3d de SuperMarioKart estaba al 90–97 % de un núcleo, con 39–63 ms de CPU por cuadro. Hace falta saber cuánto de eso es código de 32 bits (wined3d) y cuánto el lado de 64 bits: las llamadas a Vulkan de winevulkan y RADV, y los syscalls.

## Cambio

`native/wine_hardware.c` agrega `PW_NATIVE_PROFILE=1` en las corridas PE32. Es el perfilador que ya trae `wow64native` (prospero-win):
- cada 2 s, por hilo, escribe `PW_NATIVE_PROFILE version=2 tid=… tsc=… tsc_hz=… unix_calls=… syscall_calls=… unix_host_ticks=… syscall_host_ticks=… other_host_ticks=…`;
- al arrancar y una vez por minuto, `PW_NATIVE_PROFILE cpu_clock_mhz=…`.

`upstream/prospero-win/tools/native_profile_split.py` reparte el tiempo de cada hilo en:
- `unix%`: lado de 64 bits dentro de llamadas Unix (Vulkan y el driver);
- `syscall%`: syscalls, incluida la espera en ellos;
- `other%`;
- `fs%`: cambio del registro FS en cada transición;
- `guest%`: código de 32 bits, más el tiempo sin CPU.

También da las llamadas por segundo.

El costo: un `rdtsc` y unos contadores por transición, y una línea por hilo cada 2 s.

## Qué se espera

- **Si en el hilo de wined3d domina `guest%`:** el costo es wined3d. La salida es otra traducción de Direct3D 7, como dgVoodoo2 y DXVK.
- **Si domina `unix%`, con muchas llamadas por segundo:** el costo es el paso a 64 bits de cada llamada a Vulkan o el driver. Se puede agrupar o abaratar.
- **Si domina `syscall%`:** el tiempo se va en esperas o sincronización.

## Prueba física

Reporte: `reports/wine-hardware-w159/physical/20261103T145658Z`. Respuesta del usuario: "Todo anduvo".

**Secuencia de W155 (`run-0001.log`):** notepad, WFM, un juego DOS, glxgears, WFM. Sin `handle_syscall_fault` ni cierre. Es una sola prueba, y la falla anterior era intermitente.

**SuperMarioKart (`run-0002.log`):**
- Unos 15 fps, con el hilo que presenta al 87 % (`PWVK cpu`).
- La frecuencia del TSC que informa el perfilador está mal (`tsc_hz=22072826350`): calibra contra `CLOCK_MONOTONIC`, y en la PS4 los identificadores de reloj del SDK no coinciden con los del kernel. Los porcentajes, que son cocientes de `rdtsc`, valen. Las tasas por segundo de `native_profile_split.py` salen infladas unas 14 veces.
- Con el TSC real (~1,59 GHz: 31,1·10⁹ ticks en 304 cuadros a ~15,5 fps), entre el segundo y el último informe de cada hilo:

| Hilo |32 bits (`guest`)|Unix|Syscalls| Cambio de FS | Llamadas |
|---|---|---|---|---|---|
|0048, stream de mando de wined3d| 74 % | 14,6 % | 6,4 % | 4,9 % | ~1.395 Unix por cuadro (~6,7 µs cada una) |
| 0024, hilo del juego | 7,3 % | 0,2 % | 79,6 % | 12,9 % | ~58.800 syscalls por segundo (~13,5 µs cada uno) |

**Lectura:**
- En el hilo de wined3d, por cada cuadro de ~64 ms:
  - ~41 ms de CPU son código de 32 bits de wined3d: el 74 % de `guest`, descontado el ~13 % que el hilo no estuvo en CPU;
  - ~9 ms son llamadas a Vulkan por el lado Unix;
  - ~3 ms son cambios de FS.
- El paso a 64 bits no es lo principal: lo que pesa es el trabajo propio de wined3d, unos 0,8 ms por cada una de las ~50 llamadas de dibujo del cuadro, que es mucho.
- El hilo del juego pasa casi todo su tiempo entrando y saliendo de syscalls, unas 58.800 por segundo. Parece una espera activa (sobre wined3d o sobre un reloj), pero no se sabe qué syscall es.

**Siguiente:** muestrear en qué funciones de wined3d está el hilo de 32 bits, y contar qué syscalls hace el hilo del juego.
