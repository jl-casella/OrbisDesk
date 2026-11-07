# W147: diagnóstico de la pila de capas (fase 6, paso 2)

[English](HARDWARE_W147.md) | [Español](HARDWARE_W147-es.md)

APP_VER 02.46. Base W146. El dibujo no cambia.

## Por qué

Con capas por GPU cada ventana tiene alrededor un marco negro de 3–5 píxeles. W146 mostró que ese marco no está dentro de la ventana: es otra capa más grande que la ventana (`HARDWARE_W146.md`).

## Qué agrega

En `present_screen`, para cada pila que cambia (cantidad de capas o rectángulos), hasta 60 veces:

```
PWBOOT layer_stack n=… count=… windows=…
PWBOOT layer n=… i=… hwnd=… rect=(l,t)-(r,b) stride=… px=<0,0>,<2,2>,<0,mitad>
```

`hwnd=0` es el fondo de pantalla. Con eso se ve qué ventana de `ps5drv` produce el rectángulo grande y negro: hwnd, tamaño y contenido.

## Prueba física

Reporte: `reports/wine-hardware-w147/physical/20261103T112424Z`. El usuario abrió el menú Inicio con submenús y WineMine.

- **La pila no tiene capas de más.** Hay 11 pilas registradas: fondo (`hwnd=0`), barra de tareas `0x10038` y cada menú o ventana con su rectángulo exacto. Por ejemplo, el menú Inicio `0xc0060` es (0,586)-(123,700) y WineMine `0x30064` es (0,0)-(160,226). No aparece ninguna capa más grande que una ventana.
- **El único cuadro volcado con una ventana no tiene marco** (`frame-000064.bmp`): WineMine en (0,0) termina en `19191c`, `0a0a0a` y sigue directo el fondo.
- **Faltan cuadros:** en hardware los volcados son 8; cinco se gastan en el arranque y los demás sólo salen en los cuadros 64, 128… Así que no hay ningún cuadro con un menú abierto para compararlo con su pila.

**Conclusión:** el marco no es una capa extra y no está siempre. En W144 y W145 aparecía en ventanas que se habían movido (WineMine en x=144, glxgears) y en menús. Hay que capturar el cuadro justo cuando aparece (W148).
