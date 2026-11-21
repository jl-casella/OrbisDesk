# Diálogo de fondo de escritorio: tus propias imágenes como fondo (borrador)

[English](DESKTOP_BACKGROUND.md) | [Español](DESKTOP_BACKGROUND-es.md)

Borrador. Nada de esto se probó en la consola.

## Pedido

Usuario:
- poner como fondo de escritorio sus propias imágenes, no sólo los fondos incluidos;
- elegirlas en un diálogo como el Fondo de escritorio de Windows, que se abre desde el menú de clic derecho del escritorio;
- los fondos incluidos pasan del menú de clic derecho a ese diálogo, y **Browse…** elige cualquier imagen con el diálogo de abrir archivo.

## Qué ofrece Wine

Wine no tiene nada que cambie el fondo:
- `desk.cpl` es sólo la página de configuración de pantalla (resolución);
- la pestaña Desktop Integration de winecfg tiene temas, colores y fuentes, pero no fondo;
- shell32 no tiene Propiedades de pantalla.

Así que el diálogo es propio de OrbisDesk. Se arma en memoria en el código del escritorio de explorer, como el diálogo de renombrar del menú del escritorio.

## Cambio

`tools/build-explorer-hw.py`, con `desktop-background-dialog.patch.py` (carpeta de notas). Agrega 4 revisiones a `desktop.c`, sobre el menú del escritorio y el bloque Wallpaper anterior.

- **Menú:** el clic derecho en el escritorio vacío ya no tiene el submenú **Wallpaper**. En su lugar tiene **Desktop background…**.
- **Diálogo:**
  - **Picture:** los fondos incluidos (los BMP de `C:\windows`: Aurora, Dusk, Hills, Meadow) y, al final, "My picture: *archivo*" cuando hay una;
  - una **vista previa** de toda la pantalla;
  - **Position:** Fill (cubre la pantalla y recorta), Fit (imagen entera con bandas negras), Stretch o Center (sin escalar);
  - **Browse…:** el diálogo estándar de abrir archivo, para BMP, JPEG, PNG, GIF y TIFF. comdlg32 se carga en tiempo de ejecución, así que el enlace de explorer no cambia;
  - una línea de estado con el tamaño de la imagen, o el motivo por el que no se puede usar;
  - **OK**, **Cancel** y **Apply**.
- **Imágenes:**
  - las imágenes se decodifican con WIC (`windowscodecs`, creado con `CoCreateInstance`). Sus GUID se definen localmente, porque explorer no enlaza libuuid;
  - la imagen se dibuja en un lienzo del tamaño de la pantalla según Position;
  - la capa de fondo de la consola (ps5drv) sólo lee BMP de 24/32 bits. Por eso, cualquier imagen que no sea un BMP incluido del tamaño de la pantalla se escribe como BMP de 24 bits en `%APPDATA%\OrbisDesk\wallpaper-1.bmp` o `wallpaper-2.bmp`. Los dos nombres se alternan porque la capa de fondo sólo recarga cuando cambia la ruta. Después el BMP se pone como siempre (`SPI_SETDESKWALLPAPER`), que también actualiza la pantalla en el momento;
  - un fondo incluido se pone tal cual, como hacía el menú anterior.
- **Memoria:**
  - las imágenes de más de 16 megapíxeles se rechazan antes de decodificarlas. Una foto típica de 16 megapíxeles entra;
  - el escalador de WIC de Wine es por vecino más cercano. Una imagen grande se escala a lo sumo al doble del tamaño de la pantalla y se promedia de a 2×2, que se ve mejor y usa unos 15 MB, más la copia propia del decodificador (hasta 64 MB para 16 megapíxeles) mientras el diálogo dibuja;
  - el BMP convertido pesa 2,7 MB a 1280×720.
- **Persistencia:**
  - `HKCU\Software\OrbisDesk\Desktop` guarda la elección:
    - `Wallpaper` es el BMP que se puso, como antes;
    - `Source` es la imagen elegida;
    - `Style` es la posición: 0 Fill, 1 Fit, 2 Stretch, 3 Center;
  - esa clave es de la consola (`tools/console_state.py`), así que las actualizaciones y el instalador del primer arranque la conservan;
  - el BMP convertido queda en el perfil del usuario, que ninguna actualización borra; las actualizaciones sólo borran los archivos que listan como obsoletos;
  - al arrancar, la restauración que ya tiene explorer vuelve a poner la elección cuando una actualización restableció `Control Panel\Desktop` al valor por defecto.
  - El `user.reg` y el `system.reg` del build no cambian.
- **Log:** `PWDESK background open|render|browse|apply …`. Las líneas `render` incluyen el tamaño de origen, el HRESULT y el tiempo que tardó.

## Construcción

1. Aplicar en el checkout principal: `python3 desktop-background-dialog.patch.py tools/build-explorer-hw.py`. No se aplica si ya está aplicado, si falta el bloque Wallpaper de W292 o si su ancla no es única.
2. `python3 tools/build-explorer-hw.py`, y después el paquete (`build-wine-hardware.py`, que controla el manifest de explorer).

No hace falta correr ningún otro builder: win32u ya cambia la capa de fondo en ejecución, y windowscodecs y comdlg32 ya están en el runtime.

Prueba en copia, sobre el builder con sha `2b70355e…` (checkout principal, `feat/wine-mono`): 86 revisiones, `desktop.c` compila sin advertencias, y `explorer.exe` enlaza (sha `3c924afc…`).

## Prueba física

1. Clic derecho en el escritorio vacío: está **Desktop background…**, y ya no está el submenú **Wallpaper**.
2. Abrirlo. La lista muestra Aurora, Dusk, Hills y Meadow, con el actual seleccionado y en la vista previa. Log: `PWDESK background open`.
3. Seleccionar Dusk, y después **Apply**. El fondo cambia en el momento. Log: `PWDESK background apply … target=C:\windows\orbis-dusk.bmp`.
4. **Browse…**, y elegir un JPEG o PNG, por ejemplo de Documents o de un disco USB. Aparece "My picture: …" y la vista previa la muestra. Probar cada Position; la vista previa acompaña.
5. **OK**. El fondo es tu imagen. Log: `PWDESK background apply … target=…\AppData\Roaming\OrbisDesk\wallpaper-1.bmp`.
6. Aplicar otra imagen: el destino pasa a `wallpaper-2.bmp`, y la pantalla cambia otra vez.
7. Reiniciar OrbisDesk: tu imagen sigue. Después de la próxima actualización también sigue. Log: `PWDESK wallpaper start … restored=1`.
8. Elegir una imagen de más de 16 megapíxeles: la línea de estado la rechaza, y el fondo no cambia.
9. El diálogo funciona con el puntero y con teclas: Tab, las flechas, Enter y Escape.

## No verificado

- Nada se probó en la consola.
- Cuánto tarda en decodificarse un JPEG grande en la PS4. La línea `render` del log lo registra.
- Cómo se ve y se comporta el diálogo de abrir archivo de Wine con el puntero del mando y el teclado en pantalla.
- GIF y TIFF usan los decodificadores de WIC tal como vienen. De un GIF animado sólo se usa el primer cuadro.
- Si se borra la imagen original o se saca su disco USB, el fondo sigue, porque es una copia. El diálogo entonces lista la copia convertida como "My picture".
