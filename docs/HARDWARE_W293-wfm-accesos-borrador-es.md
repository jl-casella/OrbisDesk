# W293: los accesos directos en WFM muestran su propio ícono, con la flecha (borrador)

[English](HARDWARE_W293-wfm-accesos-borrador.md) | [Español](HARDWARE_W293-wfm-accesos-borrador-es.md)

Borrador para unir a las notas de W293. Nada de esto se probó en la consola.

## Reporte

Usuario, después de W292: en la carpeta Desktop de File Manager, los accesos que no son File Manager, Open Steam Client y Portal 2 aparecen sin su ícono, aunque son accesos directos y el escritorio los muestra con él.

## Causa

- WFM le pide a shell32 el ícono de cada archivo (`SHGetFileInfo` con `SHGFI_SYSICONINDEX`, `getFileInfo` de `file_utils.h`).
- Para un `.lnk`, shell32 de Wine (`dlls/shell32/folders.c`, `IExtractIconW_fnGetIconLocation`, la rama `lnkfile`) toma sólo el **IconLocation** del acceso. Si no tiene, devuelve el ícono genérico de archivo y nunca mira el destino.
- Los tres que se veían bien tienen IconLocation:
  - `File Manager.lnk` y `Open Steam Client.lnk` los escribe `tools/build-steam-hosted.py`;
  - el acceso de Portal 2 lo escribe el cliente de Steam (`native/steam/steam_shortcut.cpp`, `kHasIconLocation`).
- Los accesos hechos sólo con un destino, como `IShellLink::SetPath` (así lo hace el propio "Create shortcut" de WFM), no tienen.
- El escritorio de explorer usa el ícono del destino cuando falta (`extract_icon` de `desktop.c`), por eso ahí se veían bien.
- Además, shell32 agrega la flecha de acceso directo sólo a los íconos grandes. En las vistas de lista y detalles ningún acceso tenía la flecha.

## Cambio

`tools/build-wfm.py`, con `wfm-shortcut-icons.patch.py` (carpeta de notas). Agrega 2 revisiones a `content_view.c`, en el `LVN_GETDISPINFO` de la lista. Para un archivo `.lnk`:
- el IconLocation si el acceso tiene uno (shell32 lo resuelve desde el `.lnk`);
- si no, el ícono del destino, si el destino existe;
- si no, el ícono del propio `.lnk`.

Siempre pide con `SHGFI_LINKOVERLAY`, así que la flecha aparece en todas las vistas. Abrir un acceso no cambia. Log, una vez por ítem: `PWFM shortcut_icon source=lnk|target|target-missing|unread path=… target=… icon=N`.

Un destino en un disco USB no existe en modo NORMAL, así que el acceso queda con el ícono genérico y la flecha: `source=target-missing`. El escritorio directamente no muestra esos accesos, porque explorer descarta un launcher cuyo ícono no puede sacar. Eso explica los 5 launchers en NORMAL contra 9 en ROOT del log de W292.

Por qué no se arregla shell32: shell32 no lo compila el proyecto (sale del build fijado de Wine), y el cambio en WFM queda acotado. Arreglar el caso de respaldo en shell32 también arreglaría los diálogos de archivos y otros programas; queda como posible tarea siguiente.

## Corrección después de W293 en la consola

- En la consola, WFM seguía mostrando los íconos genéricos, y el log no tenía ninguna línea `PWFM shortcut_icon` (`reports/wine-hardware-w293/physical/manual-20261108T052636Z/run-0001.log`). WFM había listado Desktop normalmente (`PWFM children path=Desktop count=9`).
- Causa: `getFileExtension` de WFM devuelve la extensión sin el punto, así que el chequeo de W293 `hasFileExtension(path, L".lnk")` nunca coincidía, y el código nuevo nunca corría. Ahora el chequeo es `L"lnk"`.
- Cada ítem de la lista en una carpeta Desktop, la del usuario o la pública, ahora también deja `PWFM desktop_item_icon path=… type=… view=… icon=N` en el log, sea cual sea su tipo o la vista.
- En un builder que ya tiene la versión de W293, el script reemplaza ese bloque.

## Construcción

1. Aplicar: `python3 wfm-shortcut-icons.patch.py tools/build-wfm.py`.
2. `python3 tools/build-wfm.py`, y después el paquete (`build-wine-hardware.py` controla el manifest de WFM).

Prueba en copia, sobre el builder con sha `a4b4589b…` (con la versión de W293, que el script reemplazó): WFM compila (`wfm.exe` sha `4e7cffa6…`, en lugar del `38103c3a…` de W293). La única advertencia (`pwfmDeleteTree` sin usar) está en `pwfm_operations.h`, que `content_view.c` ya incluía; no la causa este cambio.

## Prueba física

1. En WFM, abrir `C:\users\orbis\Desktop`. Todos los accesos muestran el ícono de su programa con la flecha de acceso directo, tanto en la vista de lista como en la de íconos grandes. Log: `PWFM shortcut_icon source=target` para SuperMarioKart y The Lost Forest, y `source=lnk` para File Manager, Steam y Portal 2.
2. Doble clic en un acceso: el programa se abre como antes.
3. En NORMAL, los accesos a programas en un disco USB muestran el ícono genérico con la flecha (`source=target-missing`). En ROOT muestran el ícono del programa.

## No verificado

- El build corregido no se probó en la consola. El build de W293 directamente no ejecutaba el cambio.
- Que Wine dibuje la flecha sobre el ícono de un destino cuando se pide con `SHGFI_LINKOVERLAY`. `SIC_GetIconIndex` la compone para `GIL_FORSHORTCUT`, que este flag activa.
- El árbol de la izquierda sólo lista carpetas, así que no cambia.
