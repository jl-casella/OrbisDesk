# W292: íconos del escritorio en columnas, con File Manager y Steam primero (borrador)

[English](HARDWARE_W292-escritorio-columnas-borrador.md) | [Español](HARDWARE_W292-escritorio-columnas-borrador-es.md)

Borrador para unir a las notas de W292. Nada de esto se probó en la consola.

## Pedido

Usuario:
- los accesos del escritorio tienen que llenar columnas de arriba hacia abajo, y empezar una columna nueva a la derecha cuando se llena el alto sobre la barra de tareas;
- "File Manager" va siempre primero, "Open Steam Client" segundo, y el resto en orden alfabético.

Antes de este cambio, la ventana de íconos de W168 llenaba filas de izquierda a derecha, en el orden de la carpeta.

## Cambio

`tools/build-explorer-hw.py`, con `desktop-columns-order.patch.py` (carpeta de notas). Necesita el bloque de escritorio de W290 ([refresco y menú del escritorio](HARDWARE_W290-escritorio-borrador-es.md)) y agrega 4 revisiones a `desktop.c`.

- **Columnas:**
  - la posición de un ícono ahora es su columna (índice ÷ íconos por columna) y su fila (el resto). `get_icon_rect`, `get_title_rect` y `launcher_from_point` usan la misma cuenta, así que el dibujo, el doble clic y el menú de clic derecho coinciden;
  - íconos por columna = el alto sobre la barra de tareas ÷ la celda de un ícono. Ese alto es el borde superior de `Shell_TrayWnd` si está visible (en 1280×720, 720 menos la barra); si no, el área de trabajo; si no, el alto de la pantalla;
  - la ventana `OrbisDesktopIcons` toma el tamaño columnas × filas. El alto se recalcula en cada ubicación: al arrancar, y en cada recarga por sondeo, menú o aviso.
- **Orden:**
  - `File Manager.lnk` primero y `Open Steam Client.lnk` segundo si existen; después el resto por nombre, sin distinguir mayúsculas. Si dos tienen el mismo nombre (Desktop del usuario y público), decide la ruta;
  - la lista se ordena en `place_desktop_icons`, que corre después de cada carga y recarga. El orden se mantiene después del sondeo de 2 s, de renombrar o de borrar. Un acceso borrado simplemente no aparece.
- **Log:** una línea por ubicación: `PWDESK order count=N columns=C per_column=R: File Manager | Open Steam Client | ...`, o `PWDESK order count=0`.

## Construcción

1. Aplicar: `python3 desktop-columns-order.patch.py tools/build-explorer-hw.py`. No se aplica si ya está aplicado, si falta el bloque de W290 o si el ancla W179 no es única.
2. `python3 tools/build-explorer-hw.py`, y después el paquete (`build-wine-hardware.py` controla el manifest de explorer).

Prueba en copia, sobre el builder con sha `b4647688…`:
- 70 revisiones;
- `desktop.c` compila sin advertencias, y `explorer.exe` enlaza (sha `ed9f3baa…`).

## Prueba física

1. **Disposición:** con más accesos de los que entran en una columna, bajan por el borde izquierdo y siguen en una segunda columna. Ninguno queda tapado por la barra de tareas.
2. **Orden:** File Manager arriba a la izquierda, Open Steam Client debajo, y después el resto en orden alfabético. Log: `PWDESK order`.
3. **Renombrar:** renombrar un acceso desde el menú o WFM para que cambie de lugar en el alfabeto. En unos 2 s pasa a su lugar nuevo, y File Manager y Steam siguen primero.
4. **Borrar:** borrar Open Steam Client. Los demás suben un lugar. Al restaurarlo, vuelve a ser el segundo.
5. **Selección:** en la segunda columna, el doble clic abre el programa correcto, y el menú de clic derecho nombra el acceso correcto (Properties).

## No verificado

- Nada se probó en la consola ni en el runner de Linux.
- El alto de la barra de tareas en la consola: la cantidad por columna sale del rectángulo de `Shell_TrayWnd`, leído al ubicar los íconos. Si la barra cambia de tamaño después (por ejemplo, al cambiar el tema), los íconos se acomodan en la próxima recarga, no en el momento.
- Con más íconos de los que entran en pantalla, las columnas de más se salen por el borde derecho, como antes las filas.
