# Fase 7, resto: mando de la PS4 por XInput y DirectInput, y joy.cpl (plan, borrador)

[English](HARDWARE_fase7-mando-plan-borrador.md) | [Español](HARDWARE_fase7-mando-plan-borrador-es.md)

## Punto de partida

- `native/hw_pad.c` es el único que lee el mando: `scePadReadState` cada 16 ms en un hilo, y todo se convierte en mouse y teclado.
  - Stick izquierdo y touchpad: puntero. Stick derecho: rueda.
  - X: clic izquierdo. Círculo, o dos dedos en el touchpad: clic derecho.
  - Cruceta: flechas. Triángulo: Enter. Cuadrado: Escape. Options: tecla Windows.
- En el prefijo no están xinput (1_1, 1_2, 1_3, 1_4, 9_1_0), `joy.cpl` ni `control.exe`. Están compilados en el árbol fijado, x86_64 e i386.
- El xinput de Wine busca mandos por HID (winebus/hidclass, con winedevice), que en un título no existe. El DirectInput de Wine encuentra joysticks solo por HID (`dinput/joystick_hid.c`). El `hid.dll` de 64 bits ni siquiera está en el prefijo.
- prospero-win resolvió XInput con 0470/0471:
  - xinput gana una librería Unix (`xinput1_3.so`, cargada por nombre) que lee el estado del mando que guarda el título y le pasa la vibración;
  - con título, el controlador 0 es el del título y no arranca el hilo HID;
  - `XInputGetCapabilities` informa un mando de Xbox 360 con cable (045e:028e).
- `joy.cpl` tiene una pestaña XInput propia (`dlls/joy.cpl/xinput.c`: `XInputGetCapabilities`, `XInputGetStateEx` y `XInputSetState` para probar la vibración) y una pestaña DirectInput (`EnumDevices DI8DEVCLASS_GAMECTRL`).

## Diseño

1. **Un solo lector del mando.** `hw_pad.c` sigue siendo el único que llama a `scePadReadState`. Guarda el último estado con un número de paquete y exporta:
   - `pw_wine_pad(state)`: el estado en términos de `XINPUT_GAMEPAD`.
     - Cruz/Círculo/Cuadrado/Triángulo → A/B/X/Y.
     - L1/R1 → LB/RB; L2/R2 → gatillos analógicos; L3/R3 → pulsar los sticks.
     - Options → Start; touchpad pulsado → Back (Share lo toma el sistema).
     - Cruceta → DPAD. Sticks de 0..255 a −32768..32767, con Y invertido como en XInput.
   - `pw_wine_set_rumble(left, right)`: `scePadSetVibration`.
2. **XInput.**
   - Builder nuevo `tools/build-xinput-hw.py`: overlay de `dlls/xinput1_3` con 0470/0471 adaptados.
     - La parte Unix llama a `pw_wine_pad` y `pw_wine_set_rumble` directamente (todo es un ELF estático: no hay `dlsym`).
     - Compila los PE de xinput1_1, 1_2, 1_3 y 1_4 (los cuatro salen de esa fuente) en x86_64 e i386; xinput9_1_0 se revisa aparte.
     - Compila el objeto Unix con `__wine_unix_call_funcs` renombrado.
   - Un solo mando (el usuario inicial). 0471 (cuatro mandos) queda para después: hoy `hw_pad.c` abre solo el del usuario inicial.
   - La parte Unix entra en la tabla de `platform/ps4/pw_wine_unixlibs.c` como `xinput1_3.so`.
     - `pw_wine_static_unixlib_by_name` hoy solo acepta nombres `.drv`; tiene que aceptar también un nombre sin extensión (`xinput1_3` → `xinput1_3.so`), porque así lo carga 0470.
3. **Quién recibe el mando (el riesgo principal).** Sin cambios, un juego que lee XInput recibiría el mando **y** además clics, flechas, Enter y Escape de la emulación.
   - **Modo juego:** mientras algún programa haya leído XInput en el último segundo, `hw_pad.c` deja de convertir en mouse y teclado los sticks y los botones. El juego recibe solo XInput.
   - Al cerrar el juego, o cuando deja de leer XInput, vuelve la emulación sola, en menos de un segundo.
   - El **movimiento del touchpad** sigue moviendo el puntero también en modo juego: XInput no tiene touchpad. Sirve para no quedar sin puntero, por ejemplo en la pestaña XInput de `joy.cpl`, que lee el mando mientras está visible. El clic del touchpad pasa a ser Back.
   - El mouse y el teclado USB no cambian.
   - Una línea de log al entrar y al salir del modo juego (`PWPAD game_mode=1/0 reader=...`).
4. **DirectInput.** Sin HID, Wine no ve joysticks. Va un dispositivo propio en dinput (`joystick_pad.c` en un overlay de `dlls/dinput`, x86_64 e i386, mismo método que los otros builders):
   - un gamepad con ejes X/Y (stick izquierdo), Rx/Ry (stick derecho), Z (gatillos), 10 botones y un POV (cruceta);
   - lee con `XInputGetStateEx(0)` del xinput de arriba, así que comparte el modo juego;
   - se enumera como `DI8DEVTYPE_GAMEPAD` junto a los HID (que siguen sin aparecer).
   - Es lo más grande del plan: el modelo es `dinput/mouse.c`, con los objetos y el formato de datos de un joystick. Puede ir en la build siguiente si W178 se alarga.
5. **joy.cpl.**
   - `control.exe` y `joy.cpl` (x86_64) en `system32` y la carpeta builtin.
   - "Game Controllers" en Start → System Tools: `control.exe joy.cpl`.
   - Prueba: la pestaña XInput muestra el mando 0 con sus botones, sticks y gatillos, y el botón de vibración hace vibrar el mando; la pestaña DirectInput lista "Orbis Pad".

## Archivos

| Archivo | Cambio | Compartido |
|---|---|---|
| `tools/build-xinput-hw.py` | nuevo: PE xinput x2 arquitecturas, objeto Unix | no |
| `tools/build-dinput-hw.py` | nuevo: dinput con `joystick_pad.c`, x2 arquitecturas | no |
| `native/hw_pad.c` | estado compartido, `pw_wine_pad`, `pw_wine_set_rumble`, modo juego | sí |
| `platform/ps4/pw_wine_unixlibs.c` | entrada `xinput1_3.so`; por nombre sin `.drv` | sí |
| `tools/link-wine-boot.py` | enlazar el objeto Unix de xinput | sí |
| `tools/stage-wine-programs.py` | `control` y el módulo `joy.cpl` | sí |
| `tools/make-start-menu.py` |"Controladores de juegos"| sí |
| `tools/build-wine-hardware.py` | copiar xinput, dinput, `joy.cpl`; sacar el `user_reg_reset` de W177 | sí |

Orden: `build-xinput-hw.py`, `build-dinput-hw.py`, `stage-wine-programs.py`, `make-start-menu.py`, después la cadena (con `link-wine-boot.py`, porque cambia el ELF).

## Riesgos

- **Doble entrada** (punto 3). El modo juego se activa por lectura de XInput. Un juego que solo usa DirectInput también lo activa, porque el dispositivo de dinput lee XInput.
  - Un programa que lea XInput sin ser un juego (`joy.cpl`) también lo activa mientras lo hace. El touchpad sigue moviendo el puntero.
- **Juegos que leen el mando una vez al arrancar y después no:** la emulación vuelve al segundo y el juego recibiría clics si vuelve a leer más tarde. Es poco común; queda registrado en el log.
- **Vibración:** `scePadSetVibration` necesita el handle de `hw_pad.c`. Si falla, se registra el código y no se oculta.
- **xinput9_1_0** tiene su propio `main.c`: hay que ver si reenvía a xinput1_3 o si hay que parchearlo también.
- **WoW64:** la tabla Unix de 32 bits es la misma (los parámetros no llevan punteros, igual que en 0470).
- **El dinput propio es código nuevo, no de prospero-win:** es lo que más prueba necesita.
