# W151: sin los logs viejos del menú Inicio

[English](HARDWARE_W151.md) | [Español](HARDWARE_W151-es.md)

APP_VER 02.50. Base W150. El dibujo no cambia.

## Cambio

Se sacan diagnósticos de incrementos anteriores que escribían en cada apertura del menú Inicio. Quedaron de cuando el menú no mostraba carpetas ni íconos, o de cuando explorer se colgaba:

- `tools/build-wine-directory-ps4.py` (W110): sin las líneas por archivo (`native_entry`, `returned`, `matched`, `cached`) ni `read_end` en lecturas sin error. Los errores (`read_failed`, `stat_failed`, `ignored`) siguen.
- `native/wine_hardware.c` (W092): `WINEDEBUG` pasa de `trace+module` a `warn+module`. Sigue mostrando la DLL que falla al iniciar, que era su propósito, sin una línea por recurso.
- `tools/build-explorer-hw.py`:
  - sin el log de íconos del menú (W057);
  - sin una línea por marca de progreso, clic en la barra de tareas o notificación de ventana (W097).
  - El observador de explorer sigue y cada 2 s informa la última marca.
- `tools/build-win32u-ps4.py` y `native/hw_pad.c`: sin `input_pull` (W061) ni `mouse_sample` (W063).

## Prueba física

Reporte: `reports/wine-hardware-w151/physical/*`. Respuesta del usuario: "Más rápido".

- El log bajó de 5.613 líneas (W150) a 988 en una corrida parecida: 0 `PWDIRENUM` y 0 `trace:module`.
- `show_stats path=layers` sin cambios (0,54 ms promedio después del arranque).
- Al no haber marcas, no queda una medición en milisegundos de la apertura del menú. El resultado es la respuesta del usuario.
