# El menú del overlay con L3+R3 (04.31)

[English](OVERLAY_MENU.md) | [Español](OVERLAY_MENU-es.md)

Al apretar L3 y R3 juntos se abre el menú de OrbisDesk sobre el programa en curso. El programa sigue corriendo, y el mando maneja sólo el menú hasta que se cierra. Desde 04.31 el menú es un menú de acceso rápido: una barra de íconos de secciones a la izquierda y los ajustes de la sección elegida a la derecha, que se cambian ahí mismo.

El código es `native/hw_overlay.c` (`draw_panel`, `panel_input`), con el selector de perfiles en `native/hw_overlay_profiles.inc.c`. Las claves existentes siguen siendo compatibles.

## Perfiles de ejecutables (04.57)

Todas las secciones tienen un encabezado seleccionable del EXE. Subí desde el primer ítem, o desde RENDIMIENTO en la barra, y apretá X sobre el nombre. Una lista nativa desplazable muestra los últimos ejecutables iniciados, incluidos programas cerrados o fallados, y los perfiles guardados del overlay. Se excluyen File Manager (`wfm.exe`), Explorer y los ejecutables internos de servicios y del host; los nombres se deduplican sin distinguir mayúsculas. No hay explorador de archivos.

**Agregar EXE** abre un campo local con teclado en pantalla: ingresá un nombre como `hl2.exe`, no una ruta, y apretá OPTIONS o Enter. Este teclado no envía teclas a la aplicación en ejecución. Círculo vuelve a la lista; L1/R1 mueven el cursor, Cuadrado borra, L2 cambia Shift y R2 cambia los símbolos.

Al abrirse, el editor elige el programa actual del runtime, o el último nombre elegible si está al frente el escritorio. El perfil permanece fijo hasta elegir otro o reabrir el menú, aunque arranque o cierre un programa. EN EJECUCIÓN refleja el seguimiento de inicios/cierres, no una detección independiente de la ventana al frente. El historial conserva 128 nombres y su arquitectura conocida como `profile.<exe>=0|32|64` en `overlay.ini`, separados de los 64 lugares de preferencias; las preferencias guardadas también aparecen si salen del historial. Los inicios anteriores a esta función necesitan una preferencia del overlay ya guardada o agregar el nombre manualmente. No se enumeran AppDefaults que sólo existan en el registro.

FPS, generación de cuadros, estirar, cursor, tipo de control y mapeo de teclas editan el EXE elegido. Los cambios se aplican de inmediato sólo si es dueño de los ajustes actuales del runtime; otro perfil aplica en su próximo inicio sin alterar los ajustes ni la entrada en curso. El pie indica este alcance. Renderer siempre aplica al próximo inicio, mediante el puente existente de Wine AppDefaults del escritorio; un EXE conocido como de 64 bits conserva la restricción de sólo 32 bits después de reiniciar. Un pedido de renderer en curso impide cambiar de perfil hasta completarse/vencer y sobrevive al cierre del programa. Si falla el guardado de preferencias, conserva los valores anteriores en memoria y en disco. Los mapeos se guardan de forma atómica.

Estadísticas, emulación de mouse de la sesión, teclado común y Cerrar el programa siguen actuando sobre la sesión/ventana actual, independientemente del perfil elegido; el idioma sigue siendo global. Para comparar renderers de Portal, elegí/agregá `hl2.exe`, guardá GRÁFICOS → RENDERER → WINED3D + OPENGL y volvé a iniciar el juego. Esto no establece la causa del cierre.

Validación: las pruebas de host ejercitan el aislamiento del overlay real, persistencia, fallos de guardado, respuestas del renderer para un EXE cerrado durante el cierre de otro, filtrado interno, conservación de arquitectura, navegación, teclado local de nombres y mapeo inactivo. Las vistas previas en inglés/español usan las funciones nativas reales de dibujo y la compilación para PS4 pasa. La interacción física y la compatibilidad de Portal quedan pendientes de pruebas en consola.

### Inicio y recuperación del renderer (04.58)

La corrida física de la 04.57 mostró una dependencia de inicio: el consumidor del registro recién arrancaba al intentar abrir el primer programa, dejando un GET desde el escritorio en LEYENDO indefinidamente. Explorer ahora inicia un worker de registro independiente al inicializar el escritorio. Usa el protocolo nativo existente y las reglas de lectura/escritura de Wine AppDefaults; la marca nativa de pedido tomado admite un solo consumidor, incluso si también corre el cerrador anterior del juego. No hace falta abrir un juego para inicializarlo.

Todos los pedidos GET y SET tienen ahora un límite de tres segundos, incluso un GET que ningún worker haya tomado. Si falla la lectura aparece **SIN RESPUESTA; X: REINTENTAR**, en vez de un renderer predeterminado; X vuelve a leer. Los errores de lectura son visibles y un reintento exitoso permite editar. Un SET fallido conserva el aviso de error al guardar; no informa éxito. Las pruebas de host cubren timeouts con/sin consumidor, reintento, errores, un único consumidor y el parser del worker. Compilan el PE de Explorer y el overlay nativo; falta validar físicamente esta corrección.

### Intercambios del control

CONTROLES suma dos interruptores independientes, apagados por defecto y guardados para el EXE elegido: **INTERCAMBIAR STICKS** (`swapsticks.<exe>=on`) intercambia los dos ejes de los sticks izquierdo/derecho y L3/R3; **INVERTIR A/B Y X/Y** (`swapbuttons.<exe>=on`) intercambia Cruz/Círculo y Cuadrado/Triángulo. Intercambiar sticks pasa una función de mouse del stick izquierdo al stick físico derecho y viceversa, sin reescribir el perfil de teclas.

Ambos usan el mismo alcance inmediato/al próximo inicio que los demás ajustes del perfil. La entrada se transforma una sola vez, después de que el overlay y los menús nativos de Steam lean el mando físico y antes de publicar el estado del control o generar eventos de mouse/teclas. Así XInput, las rutas HID/DualSense y los perfiles de teclas/mouse comparten la misma disposición lógica. Los botones de confirmar/volver y la navegación del overlay no cambian; el teclado/mouse USB tampoco. No se agregan lecturas de configuración durante el sondeo de entrada. Las pruebas de host cubren todas las combinaciones de botones frontales/clics, direcciones de ejes, ambos interruptores juntos, persistencia, reversión ante fallos y aislamiento de perfiles inactivos; falta probar el comportamiento en consola.

## Disposición

- **Barra.** Un ícono por sección: RENDIMIENTO (rayo), GRÁFICOS (monitor), CONTROLES (mando), SISTEMA (engranaje). SALIR es el ícono de encendido al pie de la barra, en rojo. La sección elegida lleva una barra de acento a su izquierda.
- **Sección.**
  - El título de la sección, y `ORBISDESK L3+R3` a la derecha.
  - Todas las secciones muestran el encabezado seleccionable `PERFIL DE EXE` descrito arriba, con el perfil a editar y un indicador EN EJECUCIÓN/CERRADO.
  - Después vienen los ítems, cada uno en una de tres formas:
    - un interruptor: sí o no, con la perilla a la derecha y la pista en color de acento cuando está en sí;
    - un deslizador de pasos para una elección. El paso vigente se nombra en color de acento, y la perilla queda en el paso pendiente. El nombre completo del valor pendiente va a la derecha del nombre del ítem, en color de acento mientras difiere del vigente;
    - una acción, con `>` a la derecha.
- **Franja de abajo**, como en las páginas del cliente nativo de Steam (`native/steam/steam_ui.c`):
  - una línea de acento;
  - la ayuda del ítem elegido (en la barra, la del primer ítem de la sección);
  - los botones en la última línea, con la forma del cliente de Steam (`X: GUARDAR     O: VOLVER`).

Los colores son los del cliente de Steam: página `#1b2838`, franja `#171a21`, resaltado `#2a475e`, acento `#66c0f4`. El panel ocupa 540 de los 1280 píxeles de la salida.

## Secciones e ítems

| Sección | Ítem | Forma | Se guarda |
| --- | --- | --- | --- |
| RENDIMIENTO | LÍMITE FPS: no, 30, 60, auto | deslizador | por programa, `fpslimit.<exe>=` |
| | GENERAR CUADROS | interruptor | por programa, `framegen.<exe>=on` |
| | ESTADÍSTICAS: la lectura propia, o la tecla de MangoHud | interruptor, o `MANGOHUD` | no se guarda |
| GRÁFICOS | RENDERIZADO: DXVK o wined3d, Vulkan u OpenGL | deslizador | por programa de 32 bits, registro de Wine (desde el próximo arranque) |
| | ESTIRAR | interruptor | por programa, `stretch.<exe>=on` |
| CONTROLES | CONTROL: genérico, Xbox 360, Xbox One, DualSense | deslizador | por programa, `pad.<exe>=` |
| | INTERCAMBIAR STICKS | interruptor | por programa, `swapsticks.<exe>=on` |
| | INVERTIR A/B Y X/Y | interruptor | por programa, `swapbuttons.<exe>=on` |
| | MOUSE | interruptor | sólo esta sesión |
| | CURSOR: juego, siempre, oculto | deslizador | por programa, `cursor.<exe>=` |
| | MAPEO DE TECLAS (04.36) | acción: una pantalla con los botones del mando y sus teclas | por programa, `C:\orbis\padmaps\<exe>.ini` |
| | TECLADO | acción: el teclado en pantalla | no |
| SISTEMA | IDIOMA: español, inglés | deslizador | `lang=` |
| SALIR | CERRAR EL PROGRAMA (VOLVER AL ESCRITORIO para un programa que corre solo) | acción | no |

`overlay.ini`, `padtype.txt` y los valores del registro se escriben igual que antes. Los archivos existentes no necesitan cambios.

El ítem de GRÁFICOS ahora se llama RENDERIZADO, para no repetir el nombre de la sección; sus mensajes también dicen RENDERIZADO. CONFIG ahora es SISTEMA → IDIOMA.

RENDERIZADO sólo se aplica a programas de 32 bits, así que queda en gris para uno de 64:

- Muestra `SOLO 32 BITS`, sin deslizador. La línea de botones es `O: VOLVER`, y X sólo muestra el aviso `RENDERIZADO: SOLO PROGRAMAS DE 32 BITS`.
- Cómo sabe el menú de qué mundo es un programa: el lanzamiento de invitados de kernelbase avisa de cada programa por la biblioteca Unix de xinput. Un invitado de 64 bits llama por su tabla de 64 bits y uno de 32 por la de WoW64 (`tools/build-xinput-hw.py`). El overlay guarda la respuesta de los últimos 16 programas y registra `PWOVERLAY program <exe> bits=64|32`.
- Un programa del que no se sabe el mundo mantiene RENDERIZADO habilitado, como antes.

## Navegación

| Dónde | Arriba / abajo | Derecha | Izquierda | X | O |
| --- | --- | --- | --- | --- | --- |
| Barra | la sección (SALIR incluida, en ciclo) | entra a la sección | — | entra a la sección | cierra el menú |
| Sección, una elección | el ítem (en ciclo) | el valor siguiente (se detiene en el último) | el anterior (se detiene en el primero) | guarda el valor pendiente | vuelve a la barra |
| Sección, un interruptor o una acción | el ítem | — | vuelve a la barra | lo cambia, o la hace | vuelve a la barra |

- Una elección sólo se guarda con X, como antes.
- Al salir de su ítem, de la sección o del menú, el valor pendiente vuelve al vigente.
- El menú se abre en la barra, en RENDIMIENTO. Desde 04.36 lo hace siempre: 04.31 lo reabría en la última sección usada, que después de cerrar un juego casi siempre era SALIR.
- L3+R3 lo cierra desde cualquier lugar.
- El teclado y sus botones no cambian. O en el teclado sigue cerrando todo el menú.

SALIR pide dos pulsaciones: X en la barra entra a la sección, y X en CERRAR EL PROGRAMA lo cierra. La ayuda avisa que el programa no pregunta y que lo no guardado se pierde.

## MAPEO DE TECLAS (04.36)

CONTROLES → MAPEO DE TECLAS le da a cada botón y dirección de stick una tecla o un clic del mouse para el perfil de EXE elegido. Es para juegos que sólo leen el teclado y el mouse. X abre una pantalla sobre toda la salida, incluso con ese programa cerrado; primero elegí/agregá un EXE si no hay un perfil seleccionado.

**Qué edita.** El perfil de teclas del mando para ese programa, `C:\orbis\padmaps\<exe>.ini`, que `native/hw_pad.c` ya lee al arrancar el programa (W181, W213). La pantalla escribe líneas `fuente = tecla` y deja igual todas las demás: los comentarios, `stick = mouse`, `rstick = mouse` y los valores `rstick_speed` / `rstick_deadzone`.

- **Al guardar.** OPTIONS escribe el archivo de forma atómica. Si el EXE elegido es dueño de la entrada actual del runtime, el hilo del mando lo recarga en su próxima lectura (`pw_hw_pad_profile_reload`); los otros perfiles aplican en su próximo inicio.
- **Un archivo sin ninguna línea de tecla se borra.** El mando funciona entonces como sin perfil.
- **Un archivo nuevo** empieza con un comentario que nombra el programa y esta pantalla.

**La pantalla.**

- **A la izquierda:** un DualShock 4 dibujado: L1/L2/R1/R2, la cruceta, los cuatro botones de acción, SHARE, OPTIONS, el touchpad, los dos sticks y el botón PS.
  - Cada botón va en gris claro cuando tiene tecla y apagado cuando no tiene.
  - La fila elegida se ilumina en color de acento.
- **A la derecha:** la lista de todos los botones y direcciones, con su tecla a la derecha:
  - CRUZ, CÍRCULO, CUADRADO, TRIÁNGULO;
  - CRUCETA ARRIBA, ABAJO, IZQUIERDA y DERECHA;
  - L1, R1, L2, R2, L3, R3;
  - STICK IZQ. ARRIBA, ABAJO, IZQUIERDA y DERECHA;
  - STICK DER. ARRIBA, ABAJO, IZQUIERDA y DERECHA;
  - OPTIONS, CLIC DEL TOUCHPAD, SHARE.
- **La línea entre ambos.** Una línea une la fila elegida con su lugar en el dibujo, como en las páginas de mando de la configuración de los juegos de PC.
- **El valor a la derecha de una fila** es uno de estos:
  - su tecla, en color de acento mientras difiere del archivo guardado;
  - `--`, si no tiene tecla. Va en color de acento cuando se está quitando una tecla guardada;
  - `AUTO: <flecha>`, apagado, en una dirección del stick izquierdo sin tecla. Cuando un perfil tiene teclas, `hw_pad.c` le da al stick izquierdo las flechas;
  - `PUNTERO`, apagado, en un stick que `stick = mouse` o `rstick = mouse` deja como puntero o como vista con el mouse;
  - `SISTEMA`, en SHARE. El sistema se queda con ese botón: el estado del mando del SDK no tiene un bit para él, así que no se puede mapear. X sobre él sólo muestra un aviso.
- **La franja de abajo, como en el menú.** Lleva la ayuda y la línea de botones:
  - `X: ASIGNAR    CUADRADO: QUITAR    TRIÁNGULO: PREDETERMINADO    O: VOLVER`;
  - con cambios sin guardar se agrega `OPTIONS: GUARDAR`, y O dice `CANCELAR`.

**El selector de teclas.** X sobre una fila lo abre sobre la lista.

- Es un teclado de 13 columnas: ESC y F1–F12; los dígitos y BORRAR; las letras; TAB, SUPR, CTRL, ENTER, MAYÚS, INS, INICIO, ALT, ESPACIO, REPÁG, AVPÁG, FIN; y las cuatro flechas.
- Sus dos últimas filas son el mouse: CLIC IZQUIERDO, CLIC DERECHO, CLIC CENTRAL, RUEDA ARRIBA y RUEDA ABAJO.
  - Un botón del mouse queda apretado mientras se mantiene el botón del mando, y hace clic donde está la flecha. Por ejemplo, CLIC DEL TOUCHPAD = CLIC IZQUIERDO.
  - Un destino de rueda la gira un paso por pulsación.
- Son exactamente los nombres de destino que acepta `profile_vk` de `hw_pad.c`.
- Se abre en la tecla actual de la fila, que lleva un marco de acento.
- Las direcciones se mueven por las teclas. Arriba y abajo mantienen la columna.
- X le da a la fila esa tecla, CUADRADO la deja sin tecla y O cierra el selector.

| Dónde | Arriba / abajo | Izquierda / derecha | X | CUADRADO | TRIÁNGULO | OPTIONS | O |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Lista | la fila (en ciclo) | — | abre el selector | quita la tecla de la fila | el perfil predeterminado | guarda, si hubo cambios | vuelve a CONTROLES; se descartan los cambios sin guardar |
| Selector | la fila de teclas, misma columna | la tecla (en ciclo) | esa tecla | sin tecla | — | — | cierra el selector |

L3+R3 cierra todo desde cualquiera de los dos lugares, y se descartan los cambios sin guardar.

**PREDETERMINADO** carga el perfil que OrbisDesk trae para el programa, desde `C:\orbis\padmaps-default\<exe>.ini`. Si no hay ninguno, no carga ninguna tecla. Queda pendiente hasta OPTIONS.

**Las actualizaciones conservan los perfiles del usuario.**

- `tools/build-wine-hardware.py` también copia `fixtures/padmaps` a `C:\orbis\padmaps-default`, que cada actualización renueva.
- `tools/console_state.py` lista los perfiles incluidos en `padmaps` como archivos de la consola. `upload-hardware.py` y el instalador del lanzador sólo los copian si faltan, así que un perfil incluido que se editó no se reemplaza.
- Un perfil incluido que cambia en una build posterior llega a la consola con PREDETERMINADO.
- El instalador conserva como mucho 16 archivos de la consola (`HW_INSTALL_MAX_ROOTS`). `console_state.py` rechaza más.

**El lado de hw_pad.c.**

- `rstick_up`, `rstick_down`, `rstick_left` y `rstick_right` son fuentes nuevas del perfil: las direcciones del stick derecho como teclas, pasado el mismo umbral que las del izquierdo.
- Un destino también puede ser `mouse_left`, `mouse_right`, `mouse_middle`, `wheel_up` o `wheel_down`:
  - un botón del mouse baja en la flecha al apretar su primera fuente y sube al soltar la última, como las teclas desde W182;
  - un destino de rueda manda un paso al apretar.
- Las direcciones del stick derecho no valen con `rstick = mouse`. La pantalla quita esa línea, y lo mismo `stick = mouse`, cuando una dirección de ese stick recibe una tecla.
- Las reglas de W181 no cambian:
  - cuando un perfil tiene una tecla, los botones sin tecla no mandan nada;
  - el stick izquierdo manda las flechas salvo que se lo nombre o haya `stick = mouse`;
  - las teclas no van mientras un programa lee el mando por XInput (modo juego).
- La ayuda de la pantalla lo dice.

Límites:

- Una tecla por fuente. Un archivo que nombra dos veces una fuente muestra su última línea, y al guardar sólo queda ésa.
- Un archivo con más de 4 KiB de otras líneas se muestra pero no se guarda; el log lo dice.
- No se pueden mapear combinaciones (Shift+tecla), como en los perfiles de W181.

## MangoHud

Sin cambios, y lo dice la ayuda:

- ESTADÍSTICAS envía la tecla de MangoHud (Shift+F12) mientras MangoHud dibuja sobre el programa al frente, así que mostrarlo u ocultarlo funciona igual en programas de 32 y de 64 bits.
- Lo que se edita en MangoJuice vale para todo HUD: el overlay lee `MangoHud.conf` para su lectura propia y para el rectángulo de MangoHud de la generación de cuadros.

## Sin cambios

- Los avisos y su lugar.
- La lectura de estadísticas y el rectángulo de MangoHud de la generación de cuadros.
- El teclado.
- Lo que hace cada ajuste y las reglas por programa: el último programa abierto que sigue abierto, y lo que hace X sin ningún programa abierto.

## Comprobaciones

- Un arnés en el host que incluye `hw_overlay.c`, con sustitutos para las llamadas de la consola, dibuja el menú sobre un cuadro de 1280x720. También maneja `pw_hw_overlay_pad` con botones simulados y cubre cada fila de la tabla de navegación.
- 04.36: el mismo arnés comprueba:
  - que el menú se abre en RENDIMIENTO;
  - la navegación de MAPEO DE TECLAS;
  - sus archivos, a partir de copias de `fixtures/padmaps`: el perfil de SuperMarioKart editado conservando sus comentarios, `stick = mouse` quitado para vlc, un archivo nuevo con su encabezado y un archivo borrado al vaciarlo;
  - PREDETERMINADO;
  - que cada nombre de fuente y de tecla que escribe la pantalla lo aceptan `profile_sources` y `profile_vk` del propio `hw_pad.c`. Se extraen del archivo parcheado.
- También dibuja las maquetas de la pantalla.
- La prueba en consola de 04.31 (run-0263) mostró el menú funcionando. Falta la prueba en consola de MAPEO DE TECLAS.
