# W150: sin los diagnósticos del marco negro (fase 6, paso 2)

[English](HARDWARE_W150.md) | [Español](HARDWARE_W150-es.md)

APP_VER 02.49. Base W149. El dibujo no cambia.

## Cambio

W149 arregló el marco negro. Se sacan los diagnósticos de W146–W148, que hacían lenta la primera apertura del menú Inicio:

- `tools/build-win32u-ps4.py`: sin el log `flush_shape` (W146) ni el registro de pilas `layer_stack`/`layer` (W147–W148). `apply_shape` sigue: las formas de ventana son transparencia en el camino por GPU.
- `platform/ps4/pw_wine_sink_ps4.c`: con capas, el buffer de salida se vuelca sólo en los cuadros que van al log (los 8 primeros y uno de cada 64), como en W144–W147.
- `tools/build-wine-hardware.py`: `PW_SINK_MAX_DUMPS` vuelve de 40 a 8.

## Qué se espera

- La primera apertura del menú Inicio tan rápida como las siguientes.
- Sin marco negro, como en W149.

## Prueba física

Reporte: `reports/wine-hardware-w150/physical/20261103T131357Z`. Respuesta del usuario: "Sigue lento".

- Hubo sólo 5 volcados y ningún log de pilas: lo que se sacó no era la causa principal.
- En el log, cada apertura del menú Inicio escribe cientos de líneas de diagnósticos viejos (5.613 líneas en una corrida de ~40 s):
  - enumeración de carpetas `PWDIRENUM`, de W110: 2.420 líneas;
  - `trace+module` en `WINEDEBUG`, de W092: 1.308 líneas, una por cada búsqueda de recurso (los íconos del menú);
  - marcas de explorer `PWSHELL`, de W097, e íconos del menú `startmenu icon`, de W057;
  - mouse e input (`mouse_sample`, `input_pull`), de W061/W063.
- Con las marcas de explorer, la primera apertura del menú tarda ~1 s desde el clic: 0,3 s antes de llenarlo y 0,7 s llenándolo. Las siguientes tardan ~0,5 s. El primer submenú tarda otros 0,8 s.

Esos logs se sacan en W151 (`HARDWARE_W151.md`).
