# W167: agrupamiento de llamadas Vulkan de 32 bits activado (fase 6)

[English](HARDWARE_W167.md) | [Español](HARDWARE_W167-es.md)

APP_VER 02.66. Base W166.

## Cambio

`native/wine_hardware.c`: en las corridas de 32 bits agrega
- `PW_VK_BATCH=1`: enciende el agrupamiento de W166;
- `PW_VK_BATCH_STATS=1`: una línea `PW_VK_BATCH` por present, con los registros encolados, los vaciados, los que viajan junto a otra llamada y las llamadas que siguen yendo solas;
- `PW_VK_BATCH_FALLBACK_PROFILE=1`: cada 300 presents, `PW_VK_FALLBACK_TOP` con las funciones que más veces fueron solas.

El arreglo de argumentos del launcher pasa de 20 a 24 lugares fijos.

Los dos diagnósticos son para esta prueba; se sacan cuando esté medido.

## Qué se espera

- `PW_VK_BATCH … enabled=1 negotiated=1`.
- **Perfil de wow64native:** en el hilo de wined3d, muchas menos llamadas Unix por segundo y menos tiempo de cambio de FS.
- **Juego:** más FPS.
- **Riesgo:** con el agrupamiento activo, un error en la reproducción puede dibujar mal o cerrar el juego. prospero-win termina el proceso ante un fallo de orden o de reproducción (`PW_VK_BATCH fatal`).

## Prueba física

Reporte: `reports/wine-hardware-w167/physical/20261103T173339Z`, `run-0002.log` (SuperMarioKart, ~150 s). Respuesta del usuario: "Más rápido, bien". No hubo `PW_VK_BATCH fatal`.

**Agrupamiento** (`PW_VK_BATCH`, present 8455):
- `enabled=1 negotiated=1`;
- 9,18 millones de registros encolados, en 1,24 millones de vaciados (~7,4 registros por vaciado);
- 98 % de los vaciados viajaron junto a otra llamada; 20.007 fueron sueltos;
- 1,53 millones de llamadas siguieron yendo solas (`fallback`), en total 1,55 millones de cruces a Unix para 8.455 cuadros.

**Perfil de wow64native, hilo de wined3d:**

| | W166 | W167 |
|---|---|---|
| Llamadas Unix por segundo | ~73.000 | ~11.600 |
| Cambio de FS | 16,4 % | 3,8 % |
|Unix| 24,7 % | 34,3 % |
|Syscalls| 34,1 % | 28,5 % |
|32 bits| 24,8 % | 33,4 % |

**FPS de la carrera** (`PWVK present fps`): 27–74. La mayoría entre 33 y 60, con tramos de 45–63 que antes no aparecían. En W165–W166 eran 27–53.

**Llamadas que más siguen yendo solas** (`PW_VK_FALLBACK_TOP`, presents 8100–8400):

| Función | Llamadas | Por cuadro |
|---|---|---|
| `vkAllocateDescriptorSets` | 55.600 | ~185 |
| `vkCreateFramebuffer` | 29.490 | ~98 |
| `vkCreateImageView` | 4.200 | ~14 |
| `vkCreateImage`, `vkBindImageMemory`, `vkGetImageMemoryRequirements` | 2.100 cada una | ~7 |

Las de imagen (y parte de los framebuffers y vistas) vienen de las copias con color key de W165: cada copia crea una imagen temporal, dos vistas y un framebuffer. Se pueden reutilizar entre copias.
