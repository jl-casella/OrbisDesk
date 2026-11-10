# W290: el escritorio sigue los cambios de la carpeta Desktop, y los íconos tienen menú de clic derecho (borrador)

[English](HARDWARE_W290-escritorio-borrador.md) | [Español](HARDWARE_W290-escritorio-borrador-es.md)

Borrador para unir a las notas de W290. Nada de esto se probó en la consola.

## Reporte

Usuario, después de W289: si en WFM se renombra, borra o agrega un acceso directo en `C:\users\orbis\Desktop`, el escritorio no cambia hasta reiniciar OrbisDesk.

## Causa

- explorer lee los `.lnk` de Desktop una vez al arrancar (`add_folder`). Después, su hilo `watch_desktop_folders` espera con `ReadDirectoryChangesW` en las dos carpetas Desktop. El builder de W168 dejó ese hilo; sólo pasó los íconos a una ventana propia.
- **El wineserver de la PS4 nunca completa ese pedido.** En `server/change.c` un cambio de carpeta sólo se avisa con inotify o dnotify:
  - Wine se configura `--without-inotify` (`tools/probe-wine-unix.py`);
  - el kernel de la PS4 no tiene dnotify (`F_NOTIFY`/`F_SETSIG`);
  - `change.c` no tiene camino con kqueue (kqueue sólo se usa para esperar en `fd.c`).

  El pedido queda en cola (`STATUS_PENDING`) y el hilo espera para siempre, sin escribir nada en el log. El doc de W168 ya advertía ese riesgo.
- No depende de WFM. No se ve ningún cambio, tampoco los accesos de Desktop que escribe el cliente nativo de Steam fuera de Wine.
- Los listados de la carpeta sí están al día: ntdll guarda un listado por handle, y cada `FindFirstFileW` abre un handle nuevo.

## Cambio

`tools/build-explorer-hw.py`, con `desktop-refresh-menu.patch.py` (carpeta de notas). Agrega 9 revisiones a `desktop.c`, antes del bloque W179.

- **Sondeo:**
  - un hilo compara cada 2 s una firma de los `*.lnk` de las dos carpetas Desktop (nombre, tamaño y última escritura);
  - si cambia, le pide a la ventana de íconos que recargue;
  - escribe `PWDESK poll every 2000 ms` una vez, y `PWDESK poll change files=N` en cada cambio.
- **Recarga en el hilo de la ventana:**
  - la lista se rearma en el hilo de la ventana de íconos (`PWDESK reload reason=poll|menu|notify launchers=A->B files=N`);
  - Wine original cambiaba la lista desde el hilo vigilante mientras la ventana la pintaba. Un aviso, en un Wine que sí los da, ahora también sólo pide la recarga;
  - `process_changes` y `remove_launcher` ya no hacen falta, y se sacan.
- **Menú de clic derecho sobre un ícono** (círculo, apretar o tocar el touchpad con dos dedos, o el botón derecho de un mouse):
  - **Open**;
  - **Open file location:** WFM se abre en esa carpeta (`wfm.exe "<carpeta>"`; WFM navega a su primer argumento);
  - **Rename:** un diálogo chico armado en memoria, así que los recursos no cambian. La extensión se conserva, y un nombre con `\ / : * ? " < > |` se rechaza;
  - **Delete:** pregunta antes, con No por defecto. Borra sólo el acceso directo, con `DeleteFileW`, porque acá no hay Papelera;
  - **Properties:** un cuadro de mensaje con destino, argumentos y carpeta de inicio, leídos del `.lnk`.
  - Los errores aparecen en un cuadro de mensaje y en el log (`PWDESK rename|delete … error=N`).
- **Escritorio vacío:** el clic derecho en el escritorio vacío, dentro o fuera de la ventana de íconos, ofrece **Refresh** y **Open Desktop folder**.
- **No incluido:** "New shortcut" (necesita elegir un destino) y mover íconos arrastrando.

## Construcción

1. Aplicar: `python3 desktop-refresh-menu.patch.py tools/build-explorer-hw.py`. No se aplica si el ancla W179 no es única o si el parche ya está aplicado.
2. `python3 tools/build-explorer-hw.py`, y después el paquete (`build-wine-hardware.py` controla el manifest de explorer).

Prueba en copia, sobre el builder con sha `33c325c6…`, que incluye el ítem de Steam de W289 en Start:
- 66 revisiones;
- `desktop.c` compila sin advertencias, y `explorer.exe` enlaza.

## Prueba física

1. **Renombrar:** con OrbisDesk abierto, renombrar en WFM un acceso de Desktop. En unos 2 s el ícono muestra el nombre nuevo. Log: `PWDESK poll change` y `PWDESK reload reason=poll`.
2. **Borrar y agregar:** borrar un acceso en WFM, y después copiar un `.lnk` a Desktop. Cada cambio aparece sin reiniciar.
3. **Steam:** abrir el cliente de Steam, instalar o agregar algo que cree un acceso en Desktop, y volver. El ícono aparece.
4. **Menú del ícono:** círculo sobre un ícono, y probar:
   - Properties muestra el destino;
   - Rename a "Prueba" cambia el nombre (para escribir hace falta teclado);
   - Delete y No lo deja; Delete y Yes lo borra;
   - Open file location abre WFM en Desktop.
5. **Escritorio vacío:** círculo en el escritorio vacío. Refresh, y Open Desktop folder.
6. **Cerrar el menú:** con el menú abierto, hacer clic fuera o apretar cuadrado. Se cierra, y la barra de tareas y Start siguen respondiendo.

## No verificado

- Nada se probó en la consola ni en el runner de Linux.
- Si un clic fuera del menú lo cierra, porque la ventana de íconos no toma activación; cuadrado (Escape) debería cerrarlo.
- Dónde aparecen en pantalla el diálogo de renombrar y los cuadros de mensaje.
- Si el sistema de archivos de la PS4 actualiza la última escritura de un `.lnk` reescrito en el lugar. Renombrar, borrar o agregar cambia el nombre o la cantidad de archivos, así que eso se detecta igual.
