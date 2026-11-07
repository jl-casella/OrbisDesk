# W168: excepciones de 32 bits sin perder FS, sprites sin objetos por copia y acceso directo en el escritorio (fase 6)

[English](HARDWARE_W168.md) | [Español](HARDWARE_W168-es.md)

APP_VER 02.67. Base W167.

## 1. Cierre de SuperMarioKart: FS nulo al volver de una excepción

**Problema.** Casi todas las partidas de SuperMarioKart desde W153 terminan con `EXCEPTION_ACCESS_VIOLATION` y salida `0xc000000d`:
- el acceso falla en `0x7BF4C041` (ntdll de 32 bits, `RtlNtStatusToDosError`, instrucción `mov %fs:0x18,%edx`), leyendo la dirección `0x18`;
- justo antes, el juego (Blitz3D) lanza y atrapa una excepción de C++ (`e06d7363`) al cambiar la música.

El contexto de la excepción tiene `fs=0000`, mientras que los contextos tomados durante la ejecución normal tienen `fs=0013` y `gs=001b`.

**Causa:**
- En FreeBSD, el kernel de la PS4, todo hilo de usuario corre con su selector de FS de usuario (`_ufssel`, `0x13`); la base la pone `sysarch` en el MSR.
- `wow64native` (`cpu.c`) arma los contextos de 32 bits con `SegFs = fs32_sel`, y en el camino de vuelta con `RESET_STATE` (`NtContinue`, al reanudar después de una excepción) carga `context->SegFs` en FS antes de poner la base.
- `fs32_sel` sale de `fs32_selector`, que `unix.c` deja en 0. Un selector nulo no sirve para acceder a memoria en modo de compatibilidad, y la siguiente lectura del TEB falla.
- La entrada normal al código de 32 bits no carga FS, y por eso sólo fallaba después de una excepción.

**Cambio.** `tools/build-wow64native-ps4.py` (adaptación de `unix.c`): en Orbis, `fs32_selector` es el selector de FS del hilo que inicializa, leído con `mov %fs`, que corre con el FS del sistema. El log deja `PWNATIVE fs32_selector=…`; se espera `0x13`.

Sirve para cualquier programa de 32 bits que reanude después de una excepción.

**Otro fallo, no resuelto.** En la partida larga de W167 hubo además otro acceso inválido, una sola vez:
- en `heap_allocate_large` (ntdll de 32 bits, `heap.c:1015`), escribiendo en `0x1F1A000C`, al terminar la carrera;
- el bloque grande recién reservado no estaba mapeado.

Sigue sin causa conocida.

## 2. Copias con color key: objetos reutilizados

W167 (`PW_VK_FALLBACK_TOP`) mostró que cada copia con color key de W165 crea y libera una imagen, dos vistas y un framebuffer: ~7 imágenes, ~14 vistas y ~98 framebuffers por cuadro.

`tools/build-wined3d-hw.py`, `texture_vk.c`:
- **Imagen temporal:** una sola, que crece hasta el rectángulo más grande que llegó, con su vista y un set de descriptores de un pool propio (64 sets). El rectángulo se copia en su esquina y el shader lee sólo esa parte (`src.zw`).
- **Barrera:** antes de copiar el siguiente sprite, una barrera espera a que el dibujo anterior haya leído la imagen (`SHADER_READ_ONLY` → `TRANSFER_DST`).
- **Destino:** la vista y el framebuffer se reutilizan mientras no cambien el command buffer ni la imagen. Dentro de un command buffer la imagen no se puede destruir.
- **Log:** `PWCKEY source image n` cuando la imagen crece. `PWCKEY blit` (las primeras tres y una de cada 5.000) cuenta los framebuffers creados.

## 3. Accesos directos en el escritorio

Investigado y preparado por la sesión lateral de escritorio.

### Por qué no había accesos directos


Hay dos causas, y hacen falta las dos correcciones.

1. **El escritorio no recibe lo que explorer pinta.** El explorer de Wine carga los `.lnk` de las carpetas Escritorio (`FOLDERID_Desktop` y `FOLDERID_PublicDesktop`) como lanzadores y los dibuja en el `WM_PAINT` de la ventana de escritorio (`desktop.c`: `initialize_launchers`, `draw_launchers`). Corremos con `/desktop=shell,1280x720`, así que no es el escritorio "root" y los lanzadores sí se cargan (`NoDesktop` no está en el registro). Pero en ps5drv la ventana de escritorio no tiene superficie (W045: el compositor arma solo las ventanas de primer nivel sobre la capa de fondo que carga el driver desde `WINE_PS5_WALLPAPER`). Lo que explorer pinta en el escritorio, fondo e íconos, nunca llega a la pantalla.
2. **Las carpetas Escritorio están vacías.** En los prefijos de W126 a W167, `C:\users\orbis\Desktop`, `C:\users\jose\Desktop` y `C:\users\Public\Desktop` existen pero no tienen ningún `.lnk`. `tools/build-wine-hardware.py` copia los accesos de `tools/make-start-menu.py` solo al menú Inicio.

Los registros de W166 no muestran errores de esta parte (`Could not get user desktop folder` no aparece); el fondo lo carga el driver (`PWBOOT wallpaper_loaded 1280x720 bpp=24`).

### Cambio

`tools/build-explorer-hw.py`, sobre `desktop.c`:
- los lanzadores pasan a una ventana propia de primer nivel (`OrbisDesktopIcons`), con el tamaño de la grilla de íconos desde la esquina superior izquierda;
- pinta el fondo con `PaintDesktop` y encima los íconos con el `draw_launchers` de Wine;
- doble clic abre el acceso con `ShellExecuteW`, igual que el código original de Wine;
- se queda abajo de todo (`HWND_BOTTOM`, también al reordenar en `WM_WINDOWPOSCHANGING`), no toma la activación (`WS_EX_NOACTIVATE`, `MA_NOACTIVATE`) y es `WS_EX_TOOLWINDOW`;
- si cambia el contenido de las carpetas Escritorio, el vigilante de Wine la redimensiona y la repinta; sin lanzadores queda oculta;
- una línea `PWDESK launchers=… panel=… size=… per_row=… desktop=… public=…` al arrancar; si la clase o la ventana fallan, `PWDESK class error=` o `PWDESK window error=`, y los lanzadores quedan en la ventana de escritorio como antes.

`tools/build-wine-hardware.py`: copia el acceso a File Manager (el mismo `.lnk` del menú Inicio, con su hash verificado) a `C:\users\Public\Desktop`. La sesión lateral había puesto cuatro (File Manager, Notepad, Command Prompt, Solitaire); el usuario pidió sólo File Manager.

Para construir hay que correr `tools/build-explorer-hw.py` antes de `tools/build-wine-hardware.py`.

Compilado en una copia aparte, sin advertencias. No probado en la consola.

### Qué se espera

- `PWDESK launchers=1` con `panel` distinto de cero.
- Un ícono con su nombre arriba a la izquierda, sobre el fondo, sin un borde visible donde termina la ventana.
- Doble clic abre el programa; el ícono no tapa las ventanas abiertas ni aparece en la barra de tareas.

### Riesgos y límites

- Si `ExtractIconExW` no da un ícono grande para un acceso, Wine descarta ese lanzador sin aviso; el conteo de `PWDESK` lo muestra.
- `PaintDesktop` dibuja el bitmap centrado y sin escalar; el driver lo escala a la pantalla. Con `orbis-hills.bmp` (1280x720) y pantalla de 1280x720 coinciden; con otro tamaño habría un borde visible alrededor de los íconos.
- Si un programa manda otra ventana a `HWND_BOTTOM`, queda debajo de los íconos.
- El vigilante de carpetas usa `ReadDirectoryChangesW`; si no funciona en la consola, los accesos nuevos aparecen recién al reiniciar.
- Una capa más en la composición, del tamaño de la grilla (un ícono).

## Prueba física

Pendiente.
