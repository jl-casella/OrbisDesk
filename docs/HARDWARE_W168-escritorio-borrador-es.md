# W168 (borrador): accesos directos en el escritorio

[English](HARDWARE_W168-escritorio-borrador.md) | [Español](HARDWARE_W168-escritorio-borrador-es.md)

Borrador de la sesión lateral de escritorio. El número de build lo fija la sesión principal; si este cambio entra con otro, se renombra.

## Por qué no había accesos directos

Hay dos causas, y hacen falta las dos correcciones.

1. **El escritorio no recibe lo que explorer pinta.** El explorer de Wine carga los `.lnk` de las carpetas Escritorio (`FOLDERID_Desktop` y `FOLDERID_PublicDesktop`) como lanzadores y los dibuja en el `WM_PAINT` de la ventana de escritorio (`desktop.c`: `initialize_launchers`, `draw_launchers`). Corremos con `/desktop=shell,1280x720`, así que no es el escritorio "root" y los lanzadores sí se cargan (`NoDesktop` no está en el registro). Pero en ps5drv la ventana de escritorio no tiene superficie (W045: el compositor arma solo las ventanas de primer nivel sobre la capa de fondo que carga el driver desde `WINE_PS5_WALLPAPER`). Lo que explorer pinta en el escritorio, fondo e íconos, nunca llega a la pantalla.
2. **Las carpetas Escritorio están vacías.** En los prefijos de W126 a W167, `C:\users\orbis\Desktop`, `C:\users\jose\Desktop` y `C:\users\Public\Desktop` existen pero no tienen ningún `.lnk`. `tools/build-wine-hardware.py` copia los accesos de `tools/make-start-menu.py` solo al menú Inicio.

Los registros de W166 no muestran errores de esta parte (`Could not get user desktop folder` no aparece); el fondo lo carga el driver (`PWBOOT wallpaper_loaded 1280x720 bpp=24`).

## Cambio

`tools/build-explorer-hw.py`, sobre `desktop.c`:
- los lanzadores pasan a una ventana propia de primer nivel (`OrbisDesktopIcons`), con el tamaño de la grilla de íconos desde la esquina superior izquierda;
- pinta el fondo con `PaintDesktop` y encima los íconos con el `draw_launchers` de Wine;
- doble clic abre el acceso con `ShellExecuteW`, igual que el código original de Wine;
- se queda abajo de todo (`HWND_BOTTOM`, también al reordenar en `WM_WINDOWPOSCHANGING`), no toma la activación (`WS_EX_NOACTIVATE`, `MA_NOACTIVATE`) y es `WS_EX_TOOLWINDOW`;
- si cambia el contenido de las carpetas Escritorio, el vigilante de Wine la redimensiona y la repinta; sin lanzadores queda oculta;
- una línea `PWDESK launchers=… panel=… size=… per_row=… desktop=… public=…` al arrancar; si la clase o la ventana fallan, `PWDESK class error=` o `PWDESK window error=`, y los lanzadores quedan en la ventana de escritorio como antes.

`tools/build-wine-hardware.py`: copia File Manager, Notepad, Command Prompt y Solitaire (los mismos `.lnk` del menú Inicio, con su hash verificado) a `C:\users\Public\Desktop`.

Para construir hay que correr `tools/build-explorer-hw.py` antes de `tools/build-wine-hardware.py`.

Compilado en una copia aparte, sin advertencias. No probado en la consola.

## Qué se espera

- `PWDESK launchers=4` con `panel` distinto de cero.
- Cuatro íconos con su nombre arriba a la izquierda, sobre el fondo, sin un borde visible donde termina la ventana.
- Doble clic abre el programa; el ícono no tapa las ventanas abiertas ni aparece en la barra de tareas.

## Riesgos y límites

- Si `ExtractIconExW` no da un ícono grande para un acceso, Wine descarta ese lanzador sin aviso; el conteo de `PWDESK` lo muestra.
- `PaintDesktop` dibuja el bitmap centrado y sin escalar; el driver lo escala a la pantalla. Con `orbis-hills.bmp` (1280x720) y pantalla de 1280x720 coinciden; con otro tamaño habría un borde visible alrededor de los íconos.
- Si un programa manda otra ventana a `HWND_BOTTOM`, queda debajo de los íconos.
- El vigilante de carpetas usa `ReadDirectoryChangesW`; si no funciona en la consola, los accesos nuevos aparecen recién al reiniciar.
- Una capa más en la composición, del tamaño de la grilla (una fila de 4 íconos).
