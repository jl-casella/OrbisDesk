# W169: FS al reanudar, mapeos ubicados al liberar y acceso directo en el escritorio del usuario (fase 6)

[English](HARDWARE_W169.md) | [Español](HARDWARE_W169-es.md)

APP_VER 02.68. Base W168.

## Prueba de W168

Reporte: `reports/wine-hardware-w168/physical/*`. Respuesta del usuario: "Se cerró igual".

- **Escritorio:** `PWDESK launchers=1`, con un ícono.
- **Sprites:** una sola imagen de origen (`PWCKEY source image 1: 832x640`); 1.420 framebuffers en 5.000 copias (antes, uno por copia).
- **`PWNATIVE fs32_selector=0x13`**, pero el arreglo no alcanzó:
  - el contexto de la excepción sigue con `fs=0000`;
  - después volvió el fallo en `fs:0x18`.
  - El contexto que llega a `NtRaiseException`/`NtContinue` lo captura el propio código de 32 bits (`RtlCaptureContext`), no `wow64native`, y el camino `RESET_STATE` de `cpu.c` carga su `SegFs` tal cual.
- **Lo que cerró la carrera esta vez** fue el otro fallo:
  - `heap_allocate_large` escribe en `0x1F66000C` al terminar la carrera, cuando el juego libera recursos y copia archivos.
  - Antes había pasado una vez, en W167.

## Cambios

**1. FS al reanudar** (`tools/build-wow64native-ps4.py`, adaptación de `cpu.c`): el `iretq` de `RESET_STATE` carga `fs32_sel` (`0x13`) en lugar de `context->SegFs`. El FS del código de 32 bits nunca es otro: su base es el TEB, que `pw_native_restore_guest_fs` pone enseguida.

**2. Liberar un mapeo ubicado** (`tools/build-win32u-ps4.py`, `vulkan.c`, `win32u_vkFreeMemory`):
- En los programas de 32 bits, la memoria Vulkan mapeada se ve en una dirección que Wine reserva. RADV la mapea ahí con un alias de su memoria directa (`tools/vk-h0/patch-mesa-placed.py`), y su unmap deja el alias para que Wine lo libere.
- Wine libera con `MEM_RELEASE` y vuelve a mapear su reserva encima. Si eso no reemplaza el alias, o si al liberar la memoria directa quedó un hueco, Wine cree que el rango está reservado y no lo está. El bloque grande que el heap pone después ahí falla al escribirse.
- **Cambio:** en Orbis se hace `munmap` del alias (redondeado a 16 KiB) antes de `NtFreeVirtualMemory`. Si falla, queda `PWVK placed unmap … failed`.
- Es la causa más probable según el código y el momento del fallo, pero no está confirmada.

**3. Acceso directo en el escritorio del usuario** (`tools/build-wine-hardware.py`):
- El acceso a File Manager pasa de `C:\users\Public\Desktop` a `C:\users\orbis\Desktop`.
- El usuario vio que el "Desktop" de WFM, que abre esa carpeta, estaba vacío; lo que ponía ahí no aparecía y el acceso a File Manager tampoco estaba.
- Explorer lee las dos carpetas, así que el ícono sigue igual en pantalla, y lo que el usuario agregue desde WFM también se ve.

## Qué se espera

- Carreras completas sin `EXCEPTION_ACCESS_VIOLATION` ni salida `0xc000000d`.
- En WFM, el "Desktop" muestra el acceso a File Manager. Un `.lnk` copiado ahí aparece en el escritorio.

## Prueba física

Reporte: `reports/wine-hardware-w169/physical/20261103T182143Z/`. Respuesta del usuario: "Se cerró igual". El proceso sale con `0xc000000d` a los 178 s.

**Escritorio:** `PWDESK launchers=2`. File Manager aparece dos veces porque la consola conserva `/data/wine-prefix` entre builds y la subida sólo agrega archivos: el acceso de W168 en `C:\users\Public\Desktop` sigue ahí junto al de W169 en `C:\users\orbis\Desktop`. En la carpeta Desktop de WFM aparece una sola vez, como se esperaba.

**Carrera, en orden:**
1. `heap_allocate_large` (ntdll i386, `+0x55a64`) falla al escribir la cabecera de un bloque que `allocate_region` acaba de devolver (`0x1F950000`). Es el mismo fallo de W167 (`0x1F1A0000`) y W168 (`0x1F660000`), siempre en el heap `0x2F0000`. No hubo `PWVK placed unmap … failed`.
2. Los manejadores del juego lo atrapan y lanzan una excepción C++.
3. El juego llama a `TerminateThread(NULL)` y después falla `RtlNtStatusToDosError` leyendo `fs:0x18` con `eax=c0000008`.

**Por qué falla el FS** (paso 3; el cambio 1 no alcanzó porque el problema no es el selector):
- `NtTerminateThread(0)` no es el hilo actual: Wine devuelve `STATUS_INVALID_HANDLE` y el hilo sigue.
- Pero `BTCpuThreadTerm` de `wow64native` tomaba NULL como el hilo actual y borraba antes su estado, incluida la base de FS del código de 32 bits. El retorno siguiente de una llamada al sistema puso base 0, y el código de error de kernelbase leyó `fs:0x18`.
- La evidencia: en los cinco fallos `fs:0x18` de W165 a W169, la línea anterior es el `PW_NATIVE_PROFILE` final de ese hilo, que imprime `thread_term` antes de borrar el estado.
- La excepción C++ y este fallo aparecen en todos los logs del juego desde W160, también al salir sin carrera. El fallo del heap aparece recién desde W167, la primera build con `PW_VK_BATCH=1`. Por eso el cierre en la carrera viene del heap, y el FS convierte cualquier salida en un cierre con error.

El cambio 2 (unmap del alias antes de liberar) no cambió el fallo del heap. Su causa sigue sin identificarse.
