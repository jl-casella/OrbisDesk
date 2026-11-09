# W292: elegir el fondo de escritorio, con tres fondos más (borrador)

[English](HARDWARE_W292-fondos-borrador.md) | [Español](HARDWARE_W292-fondos-borrador-es.md)

Borrador para unir a las notas de W292. Nada de esto se probó en la consola.

## Pedido

Usuario: poder cambiar el fondo de escritorio, con 2 o 3 fondos más incluidos además de `orbis-hills.bmp`.

## Cómo llegaba el fondo a la pantalla

- El launcher pasa `WINE_PS5_WALLPAPER=/data/wine-prefix/drive_c/windows/orbis-hills.bmp` (`native/wine_hardware.c`).
- ps5drv (`tools/build-win32u-ps4.py`, W045/W144) lee ese BMP una vez, al instalarse el driver. Lo dibuja como su propia capa de abajo, debajo de todas las ventanas: en este driver la ventana del escritorio no tiene superficie.
- La ventana de íconos de explorer pinta el fondo debajo de los íconos con `PaintDesktop`, desde el bitmap de user32. user32 carga ese bitmap de `HKCU\Control Panel\Desktop\Wallpaper`, que el build pone en `orbis-hills.bmp`.
- `update_desktop_wallpaper` de win32u corre en cada `SPI_SETDESKWALLPAPER`, también en el de explorer al arrancar. Sólo descartaba la ruta guardada. Así, el cambio de un programa llegaba al bitmap de user32 pero no a la capa de ps5drv, y la pantalla seguía con la imagen del arranque.

## Cambio: el fondo cambia en el momento

El cambio se aplica en el momento, sin reiniciar. El launcher no cambia: su variable de entorno sigue siendo la imagen del arranque, que se ve hasta que arranca explorer.

1. **win32u** (`wallpaper-live-win32u.patch.py` → `tools/build-win32u-ps4.py`, 3 revisiones):
   - `update_desktop_wallpaper` lee `Wallpaper` del registro y se lo pasa a la nueva `ps5_set_wallpaper`;
   - ps5drv convierte la ruta DOS con `ntdll_get_unix_file_name` y carga el BMP en una capa nueva. Con `screen_lock`, cambia la capa, libera la vieja y vuelve a presentar el stack. La composición por CPU también redibuja toda la pantalla;
   - si la ruta es la misma, no hace nada. Un archivo que no carga deja el fondo actual, y un valor vacío es negro;
   - log: `PWBOOT wallpaper_set <ruta> unix=<ruta>`.
   - explorer llama a `SPI_SETDESKWALLPAPER` al arrancar, así que la elección del registro reemplaza la imagen del arranque apenas corre explorer. El launcher no necesita leer el registro.
2. **explorer** (`desktop-wallpaper.patch.py` → `tools/build-explorer-hw.py`, 5 revisiones; necesita el bloque de escritorio de W290):
   - el clic derecho en el escritorio vacío muestra **Wallpaper**, un submenú con los `*.bmp` de `C:\windows`, ordenados y con el actual marcado. `orbis-dusk.bmp` aparece como "Dusk";
   - elegir uno llama a `SPI_SETDESKWALLPAPER` con `SPIF_UPDATEINIFILE`. Eso actualiza `HKCU\Control Panel\Desktop\Wallpaper`, el bitmap de user32 y la capa de ps5drv, y se repinta la ventana de íconos;
   - **cambio de otro programa:** explorer recibe `WM_SETTINGCHANGE` del fondo. Copia el valor nuevo y repinta los íconos;
   - log: `PWDESK wallpaper menu|set|changed|start …`.
3. **Que sobreviva a las subidas:**
   - `Control Panel\Desktop` es del build: cada subida lo reemplaza y vuelve a poner `orbis-hills.bmp`;
   - explorer guarda una copia de la elección en `HKCU\Software\OrbisDesk\Desktop\Wallpaper`, y `tools/upload-hardware.py` ahora toma `Software\OrbisDesk` como de la consola (`wallpaper-package-upload.patch.py`);
   - al arrancar, si Control Panel tiene el valor por defecto pero la copia nombra otro archivo que existe, explorer restaura la copia. Si no, copia el valor actual, así que un cambio hecho con regedit también se conserva. Si regedit pone justo `orbis-hills.bmp` mientras la copia tiene otro archivo, en el arranque siguiente gana la copia.
4. **Fondos:**
   - `make-wallpaper-set.py` (carpeta de notas; para `tools/`) dibuja `orbis-dusk.bmp`, `orbis-aurora.bmp` y `orbis-meadow.bmp`;
   - cada uno es un paisaje procedural de 1280×720 con semilla fija, en Python puro, y los tres tardan unos 20 s. No se descarga ni se copia nada, así que no hay atribución a terceros;
   - salida: `out/wallpaper-set/` con un manifest de hashes;
   - `build-wine-hardware.py` los copia, con control de hash, al lado de `orbis-hills.bmp` en `C:\windows`. El fondo por defecto no cambia.

| Archivo | sha256 |
| --- | --- |
| `orbis-dusk.bmp` (atardecer, colinas en capas) | `c52e12f7…` |
| `orbis-aurora.bmp` (noche, aurora, lago) | `5fda4043…` |
| `orbis-meadow.bmp` (campos a la mañana) | `f8e4c4e7…` |

## Construcción

1. `python3 make-wallpaper-set.py .`, desde la raíz del repositorio, o desde `tools/` una vez copiado ahí.
2. Aplicar:
   - `wallpaper-live-win32u.patch.py tools/build-win32u-ps4.py`;
   - `desktop-wallpaper.patch.py tools/build-explorer-hw.py`;
   - `wallpaper-package-upload.patch.py .` (cambia `build-wine-hardware.py` y `upload-hardware.py`).
3. Correr `build-win32u-ps4.py`, `build-explorer-hw.py`, `link-wine-boot.py` (win32u va en el ELF de arranque), y después `build-wine-hardware.py`.

## Prueba física

1. Clic derecho en el escritorio vacío, y después **Wallpaper**: aparecen Aurora, Dusk, Hills y Meadow, con Hills marcado.
2. Elegir Dusk. La pantalla cambia en el momento, debajo de las ventanas y de los íconos. Log: `PWDESK wallpaper set` y `PWBOOT wallpaper_set`.
3. Abrir una ventana y moverla sobre el escritorio: no se ve nada del fondo viejo.
4. Reiniciar OrbisDesk: sigue Dusk. Se espera ver un momento las colinas al arrancar, antes de que arranque explorer.
5. Después de la próxima subida, sigue Dusk. Log: `PWDESK wallpaper start … restored=1`.
6. Volver a elegir Hills y reiniciar: queda Hills.

## No verificado

- Nada se probó en la consola ni en el runner de Linux.
- Si liberar la capa vieja mientras presenta el camino de GPU produce un parpadeo. El sink marca el último stack como viejo al liberar, y el stack nuevo sigue enseguida, como al redimensionar una ventana.
- Cada capa de fondo es un buffer de pantalla completa en el pool de la GPU (unos 3,7 MB a 1280×720). Se guarda una sola a la vez.
- Los programas que guardan su propia copia del fondo la conservan hasta repintar.
