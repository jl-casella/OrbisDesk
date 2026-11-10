# W290: las fuentes del sistema conservan su tamaño al cambiar el estilo visual (borrador)

[English](HARDWARE_W290-fuentes-tema-borrador.md) | [Español](HARDWARE_W290-fuentes-tema-borrador-es.md)

Borrador para unir a las notas de W290. Nada de esto se probó en la consola.

## Reporte

Usuario: al cambiar el tema, las letras se ven más chicas hasta el próximo reinicio de la app.

## Causa

1. **El estilo pasa puntos como píxeles.** Al elegir un estilo en winecfg, `ApplyTheme` de uxtheme lee las fuentes del INI del estilo. Aero, y Luna y Noir (armados a partir de Aero por `tools/build-msstyles-hw.py`), definen:
   - `MenuFont`, `StatusFont`, `MsgBoxFont` e `IconTitleFont` = Tahoma 8;
   - `CaptionFont` = Tahoma 10 bold.

   `parse_handle_nonclient_font` (`dlls/uxtheme/msstyles.c`) pasa el tamaño en puntos a `SPI_SETNONCLIENTMETRICS` sin convertir, como `lfHeight` positivo.
2. **win32u lo guarda como píxeles.** `set_font_entry` (`dlls/win32u/sysparams.c`) guarda la altura positiva tal cual, y `get_font_entry` la escala como alto en píxeles. Queda una celda de 8 píxeles en vez de 8 puntos, que son 11 píxeles a 96 dpi: letra más chica en menús, barra de tareas, títulos, cuadros de mensaje y nombres de íconos.
3. **Reiniciar lo deshace.** uxtheme pone las fuentes sin `SPIF_UPDATEINIFILE`, así que van sólo a la clave volátil (`save_entry`), que se borra al reiniciar. Además, cuando una fuente se carga del registro, `load_entry` ya lee una altura positiva como puntos. Por eso, después de reiniciar, el tamaño vuelve a estar bien.

## Cambio

`tools/build-win32u-ps4.py`, con `theme-font-size.patch.py` (carpeta de notas). Una revisión de `sysparams.c`: `set_font_entry` toma una altura positiva como puntos (`-muldiv(h, 96, 72)`), igual que `load_entry`. Las alturas negativas pasan por `map_from_system_dpi` como antes.

- **Por qué en win32u y no en uxtheme:**
  - win32u leía el mismo valor guardado de dos maneras: una altura positiva era píxeles al ponerla y puntos al cargarla en el arranque siguiente. Ahora las dos la leen como puntos;
  - uxtheme no tiene builder propio; sus copias PE64 y PE32 salen directo del build fijado;
  - el lado Unix de win32u es compartido por los dos mundos, así que esta sola revisión los cubre.
- **Efecto secundario:** un programa que ponga una fuente del sistema con alto de celda positivo en píxeles ahora la recibe como puntos, un tercio más grande. Windows guarda ese valor como píxeles. En OrbisDesk nada lo hace, salvo uxtheme.

## Construcción

1. Aplicar: `python3 theme-font-size.patch.py tools/build-win32u-ps4.py`.
2. `python3 tools/build-win32u-ps4.py`, después `tools/link-wine-boot.py` (win32u va en el ELF de arranque), y después `tools/build-wine-hardware.py`.

Prueba en copia, sobre el builder con sha `d1c972fa…`:
- compilan las 47 unidades de win32u;
- `sysparams.c` sin advertencias.

## Prueba física

1. Mirar el tamaño de las letras en Start, el reloj de la barra, el título de una ventana y el nombre de un ícono del escritorio.
2. En winecfg, Desktop Integration: cambiar a Luna, después Noir, después Aero, con Apply cada vez. Las letras mantienen el tamaño del paso 1.
3. Reiniciar OrbisDesk. El tamaño es el mismo que antes del reinicio.
4. Abrir un programa (WFM, Notepad) después del cambio. Sus menús y cuadros de mensaje tienen el tamaño normal.

## No verificado

- Nada se probó en la consola.
- El análisis sale del código fijado: uxtheme, win32u y el INI de Aero. No se midió la altura de las fuentes en pantalla.
- Los programas que guardan una fuente ya creada (`HFONT`) y no la rehacen con `WM_SETTINGCHANGE` la conservan. Esto sólo afecta a programas abiertos durante el cambio.
