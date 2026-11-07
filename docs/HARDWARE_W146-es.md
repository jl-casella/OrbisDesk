# W146: forma de las ventanas como transparencia, con diagnóstico (fase 6, paso 2)

[English](HARDWARE_W146.md) | [Español](HARDWARE_W146-es.md)

APP_VER 02.45. Base W145.

## Problema

Con las capas por GPU (W144/W145) las ventanas y los menús tienen un marco de 4 píxeles negros (`0x000000`). Esos píxeles llegan en el flush valiendo cero, así que no es memoria sin pintar (`HARDWARE_W145.md`).

## Cambio

- **Forma de la ventana (`ps5drv.c`, `apply_shape`):**
  - Wine pasa en cada flush la forma de la ventana: un bitmap de 1 bit por píxel de la superficie, encendido donde la ventana se ve. Sale de la región de la ventana, del color clave o del alfa (`set_surface_shape` en `dce.c`).
  - Mientras la GPU apila las ventanas, los píxeles fuera de esa forma pasan a `PS5_UNPAINTED`, y el shader muestra lo que hay debajo.
  - `compose_rect` sigue ignorando la forma, como siempre.
- **Diagnóstico (`PWBOOT flush_shape`):** se registran los primeros 80 flushes que tocan el borde izquierdo de una ventana, con:
  - el rectángulo visible, el de la superficie y el sucio;
  - si hay forma y si cambió;
  - los valores crudos, con alfa, de los píxeles 0, 1, 3, 4 y 5 del borde izquierdo, a media altura;
  - el valor que quedó en la columna 2.

## Qué se espera

- **Si el margen está fuera de la forma:** el marco negro desaparece y el log muestra `shape=1`.
- **Si no hay forma (`shape=0`):** los valores del borde dicen qué pinta Wine ahí, y el paso siguiente sale de esos valores.

## Prueba física

Reporte: `reports/wine-hardware-w146/physical/20261103T111131Z`. Respuesta del usuario: "Sigue el marco".

Lo que muestran los 34 `flush_shape` registrados (barra de tareas, menú Inicio y submenús, ventana Computer, un diálogo):
- **Forma:** en todos, `shape=0`. Ninguna ventana tiene región, color clave ni alfa, así que `apply_shape` no hace nada.
- **Borde izquierdo:** el píxel 0 de cada ventana es `46464a` (ButtonLight) y el 1 es `5a5a5f` (ButtonHilight), el borde 3D estándar. El borde negro no está dentro de la ventana.
- **Rectángulos:** el rectángulo de la superficie empieza siempre en (0,0) del rectángulo visible.

**Conclusión:**
- Los 3–5 píxeles negros que rodean cada ventana están **fuera** de su rectángulo.
- Los dibuja otra capa de la pila, aproximadamente 4 píxeles más grande por lado y en color 0. El color `Background` del tema también es negro.
- Todavía no se sabe qué capa es. W147 registra la pila completa (`HARDWARE_W147.md`).
