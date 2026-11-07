# W179, partes de la sesión de configuración de Wine: DirectInput del mando y aspecto XP de Luna y Noir

[English](HARDWARE_W179-borrador.md) | [Español](HARDWARE_W179-borrador-es.md)

Borrador. La sesión principal lo suma a `HARDWARE_W179.md`, junto con el arreglo de bcrypt del navegador.

## 1. DirectInput con el mando de la PS4 (fase 7)

- El DirectInput de Wine encuentra joysticks solo por HID (`dlls/dinput/joystick_hid.c`), que un título de PS4 no tiene: ningún juego DirectInput veía un mando, y la pestaña DirectInput de `joy.cpl` estaba vacía.
- `tools/build-dinput-hw.py` (nuevo) compila dinput y dinput8 (x86_64 e i386) con un dispositivo nuevo, `joystick_pad.c`. Es código propio, no de prospero-win.
  - Muestra el controlador XInput 0 (el mando, desde W178) como un gamepad con la disposición del driver de Xbox 360 de Windows:
    - X/Y: stick izquierdo; Rx/Ry: stick derecho; Z: los dos gatillos juntos;
    - 10 botones: A B X Y LB RB Back Start LS RS;
    - la cruceta como POV.
  - Se presenta como "Controller (XBOX 360 For Windows)", VID/PID 045e:028e.
  - Lee XInput cada 8 ms en el hilo de entrada de dinput (un temporizador como `read_event`), y también en `Poll()`.
  - Los ejes respetan el rango, la zona muerta y la saturación que pone el programa, con el mismo cálculo que `scale_axis_value` de `joystick_hid.c`.
  - Sin force feedback: el mando vibra por XInput.
- `dinput.c`: el mando aparece primero entre los controladores de juego (`EnumDevices`) y se crea por su GUID de instancia o de producto.
- Leer el mando por DirectInput lee XInput, así que activa el modo juego de `hw_pad.c` igual que un juego XInput.
- `tools/build-wine-hardware.py` copia los cuatro DLL a las carpetas builtin y a `system32`/`syswow64`. El dinput de 64 bits no estaba en el prefijo.
- Sin advertencias al compilar. Los imports de los cuatro DLL ya están en el prefijo.

## 2. Luna y Noir más parecidos a XP y a Royale Noir

Pedido del usuario después de probar W177: Luna se parecía demasiado a Aero. Quería el borde y la barra de título plenos en azul XP, la barra de tareas azul y el botón Start verde; en Noir lo mismo, pero naranja.

- `tools/build-msstyles-hw.py` (ya en W178):
  - **Luna:** título y borde plenos azul XP (0,84,227), y gris azulado (122,150,223) en las ventanas inactivas.
  - **Noir:** título y borde naranja (232,112,24), y gris oscuro en las inactivas.
  - Tres piezas nuevas con clases del shell de XP:
    - `[Taskbar.BackgroundBottom]`: azul XP / negro brillante;
    - `[Start::Button.Pushbutton]`: verde / naranja, cuadrado a la izquierda y redondeado a la derecha;
    - `[TaskBand::Toolbar.Button]`: los botones de las ventanas, con la activa más oscura.
- `tools/build-explorer-hw.py` (`tools/taskbar-theme-w179.patch.py`):
  - explorer carga uxtheme en tiempo de ejecución y abre "Taskbar" en la ventana de la barra;
  - si el estilo la tiene, dibuja desde el estilo el fondo, el botón Start (`SetWindowTheme "Start"`, clase Button) y los botones de las ventanas (`SetWindowTheme "TaskBand"`, clase Toolbar);
  - el texto va en el color del estilo: "start" en negrita e itálica, y el reloj sobre el color de la barra;
  - con `WM_THEMECHANGED` (elegir otro estilo en winecfg) recarga;
  - con Aero o sin estilo queda el dibujo clásico.
- `tools/build-win32u-ps4.py` (`tools/flat-frame-w179.patch.py`), en el pintado del borde de ventana (`defwnd.c`):
  - si el color de borde del estilo es distinto de la cara de botón, todo el borde, incluidos los bordes 3D, se dibuja pleno en ese color;
  - con el esquema oscuro de siempre (borde igual a la cara) no cambia nada.

Lo que Wine no dibuja con el estilo: los botones de minimizar, maximizar y cerrar siguen siendo los clásicos, sin la X roja de XP.

Comprobado sin la consola: el explorer modificado compila y enlaza sin advertencias, y `defwnd.c` modificado compila sin advertencias con la receta de win32u.

## Prueba

1. Game Controllers → pestaña DirectInput: aparece "Controller (XBOX 360 For Windows)", y sus ejes, botones y POV se mueven.
2. Un juego DirectInput (por ejemplo, uno de 32 bits que pide joystick) responde al mando, sin clics de la emulación.
3. winecfg → Luna:
   - borde y título plenos en azul;
   - barra de tareas azul, Start verde, botones de ventana azules (el activo más oscuro), reloj en blanco.
4. Lo mismo con Noir: naranja y negro.
5. "(Sin tema)" y Aero: barra de tareas y bordes como antes.

Riesgos:
- Enumerar dispositivos DirectInput lee XInput, así que activa el modo juego durante un segundo aunque el programa no use el mando.
- El dispositivo de dinput es código nuevo: un juego con un formato de datos poco común puede mostrar algo raro en los ejes; el log de `dinput` lo diría.
- Los botones de la barra de tareas con estilo se dibujan con el ícono pequeño de la clase de la ventana. Una ventana que solo tiene un ícono puesto con `WM_SETICON` aparece sin ícono, porque leerlo pediría un mensaje a su hilo.
