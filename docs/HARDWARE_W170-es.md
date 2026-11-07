# W170: salida de hilo con NULL, diagnóstico del fallo del heap, escritorio sin duplicado y apariencia (fase 6)

[English](HARDWARE_W170.md) | [Español](HARDWARE_W170-es.md)

APP_VER 02.69. Base W169. El resultado de W169 está en `docs/HARDWARE_W169.md`.

## Cambios

**1. `TerminateThread(NULL)` ya no borra el estado del hilo** (`tools/build-wow64native-ps4.py`, adaptación de `cpu.c`):
- `BTCpuThreadTerm` sólo borra el estado si el handle es el pseudo-handle del hilo actual, o un handle real cuyo `ClientId` es el del hilo actual.
- Con NULL no hace nada. `NtTerminateThread(0)` falla con `STATUS_INVALID_HANDLE` y el hilo sigue en código de 32 bits con su FS intacto.
- Afecta toda salida de SuperMarioKart. No arregla el fallo del heap, que es lo que dispara la salida al final de la carrera.

**2. Diagnóstico del fallo del heap** (sólo logs, el resultado no cambia):
- `tools/build-audio-ps4.py`, `virtual.c` de ntdll, `virtual_handle_fault`: cuando un acceso falla en una página que Wine tiene como accesible, registra `PWVM fault`. La línea incluye la dirección, la vista que la contiene (base, tamaño, protección) y el resultado de volver a aplicar la protección que Wine ya tiene registrada. `ENOMEM` indica que la página no está mapeada en el host.
- `tools/build-win32u-ps4.py`, `vulkan.c`: `PWVK placed map` y `PWVK placed free` con cada rango de los mapeos ubicados, para ver si la dirección del fallo fue antes memoria Vulkan.

**3. Archivos obsoletos del prefijo** (`tools/build-wine-hardware.py`, `tools/upload-hardware.py`):
- El manifiesto lista `obsolete_files`. La subida los borra por FTP después de subir el runtime: sólo rutas bajo `wine-prefix/` que la build no instala, y si ya no están, no es error.
- Primera entrada: `C:\users\Public\Desktop\File Manager.lnk` de W168, que duplicaba el ícono en el escritorio.

**4. Apariencia**, preparada en la sesión de accesos directos y aprobada por el usuario:
- Ícono del PKG: una ventana con forma de PS4 (`out/app-icon/icon0.png`, `tools/orbis_package.py`).
- Botón Start: el mismo ícono dibujado con GDI, en lugar del ícono de clase (`tools/build-explorer-hw.py`).
- Fondo de escritorio: foto de dominio público CC0 convertida a 1280x720 (`out/wallpaper-cc0/`, crédito en `THIRD_PARTY.md`).
- Pantalla de carga: negra, con el logo y una barra de progreso que avanza con las marcas de arranque (`native/wine_hardware.c`, glifo `%` en `native/hw_text.h`).

## Qué se espera

- Un solo ícono de File Manager en el escritorio.
- Al salir de SuperMarioKart desde el menú, ningún fallo `fs:0x18` ni salida `0xc000000d`.
- Al final de la carrera puede repetirse el fallo del heap. Si pasa, el log tiene `PWVM fault` con la vista y el estado de la página, para decidir la corrección.

## Prueba física

Reporte: `reports/wine-hardware-w170/physical/20261103T184320Z/`. Respuesta del usuario: "Se cerró al salir".

- **Escritorio:** `PWDESK launchers=1`. La subida borró el acceso viejo (`obsolete_deleted 1`).
- **Salida:** el proceso sale con `status=0x00000000`, sin fallo `fs:0x18`; el cambio 1 funcionó. Lo que el usuario vio como cierre es la salida del juego después de su manejo de la excepción.
- **El fallo del heap** pasó otra vez, ahora al salir desde el menú, en la misma dirección que W169: `PWVM fault addr=0x1f95000c err=1 vprot=0x23 view=0x1f950000 size=0x2f0000 protect=0x3 reprotect=0 errno=0`.
  - La vista es del heap (3 MB), Wine la tiene comprometida y de lectura/escritura, y volver a aplicar esa protección devuelve 0.
  - No hay mapeos Vulkan ubicados cerca: los 56 `PWVK placed map` están entre `0x10240000` y `0x1ABD0000`.
- **Hipótesis:** en Orbis una reserva `PROT_NONE` no tiene memoria detrás y el kernel ignora cambios de protección sobre ella. `pw_wine_memory_protect` compromete con memoria flexible sólo lo que `sceKernelVirtualQuery` reporta como no comprometido. Si una página queda en un estado que el kernel reporta como comprometido pero sin la protección pedida, `mprotect` devuelve 0 sin efecto. W171 lo comprueba.
