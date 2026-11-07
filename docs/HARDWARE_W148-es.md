# W148: volcado de cuadros para el marco negro (fase 6, paso 2)

[English](HARDWARE_W148.md) | [Español](HARDWARE_W148-es.md)

APP_VER 02.47. Base W147. El dibujo no cambia.

## Qué agrega

- **Volcados:** mientras la GPU apila las ventanas, se vuelca a BMP cada cuadro de salida distinto del anterior, hasta 40 (`PW_SINK_MAX_DUMPS=40`; antes eran 8). Cada volcado deja `PWSINK dump frame=N layers=M` en el log. El costo (leer el buffer de salida para el hash, y escribir ~3,6 MB por volcado) se paga sólo hasta llegar a los 40.
- **Pilas:** el registro de pilas (`layer_stack`/`layer`) sube de 60 a 200 entradas.

Con eso cada volcado se puede cruzar con su pila: si el marco negro cae fuera de toda capa salvo el fondo, el problema está en el fondo o en el shader; si cae dentro de una capa, está en los píxeles de esa ventana.

## Prueba física

Reporte: `reports/wine-hardware-w148/physical/20261103T*`. Respuesta del usuario: "En ambos": la barra de tareas ya tiene marco negro, y también el menú Inicio, WineMine y sus menús. Quedaron 30 volcados.

**La causa, por los volcados:**

- Con sólo el fondo (`frame-000003`, `layers=1`), la columna x=600 es pasto hasta y=719.
- Cuando aparece la barra de tareas (`frame-000005`, `layers=2`, rect (0,700)-(1280,720)), las filas 696–699 son `000000` y la barra empieza en 700.
- La pila no tiene nada más que el fondo debajo de esas filas.
- El ancho del marco varía porque cada borde negro va desde el borde de la ventana hasta el múltiplo de 8 siguiente hacia afuera:

|Caso| Borde de la ventana | Negro | Siguiente múltiplo de 8 |
|---|---|---|---|
| Barra de tareas | 700 | 696–699 | 696 |
| Menú Inicio (W144) | 123 | 123–127 | 128 |
|glxgears (W145)| 307 | 308–311 | 312 |
| WineMine (W144) |75 arriba| 72–74 | 72 |
| WineMine (W144) | 148 izquierda | 144–147 | 144 |

- En la GPU de la PS4 (GFX7) un frente de onda de fragmentos son 64 píxeles, un bloque de 8×8.
- En los bloques donde hay píxeles dentro y fuera de una ventana, los de afuera salían negros.
- El shader de W144–W148 recorría las capas con `continue`, `return` y un `texelFetch` dentro de esas ramas divergentes. Ese código daba un resultado incorrecto en los píxeles que seguían iterando.
- Con una sola capa (W143) no hay divergencia, y por eso no había marco.
- La causa exacta en el compilador no está aislada: se deduce de la geometría.

Corrección en W149 (`HARDWARE_W149.md`).
