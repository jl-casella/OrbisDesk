# W141: flechas como teclas extendidas, por VK (fase 5)

[English](HARDWARE_W141.md) | [Español](HARDWARE_W141-es.md)

APP_VER 02.40. Base W140.

## Problema

En W140 el driver pedía `MapVirtualKeyEx(..., MAPVK_VK_TO_VSC_EX)` y marcaba la tecla como extendida si el resultado tenía prefijo `E0`. Para las flechas eso no pasa nunca, porque en la tabla `kbdus` de Wine el scan code 0x4d sin prefijo también corresponde a `VK_RIGHT`, y es el primero que encuentra. DirectInput recibía entonces el 6 del teclado numérico en vez de la flecha.

## Cambio

En `ps5drv.c` (overlay de `tools/build-win32u-ps4.py`) el driver manda con `KEYEVENTF_EXTENDEDKEY` las teclas que un teclado de PC envía con prefijo `E0`:
- las flechas;
- Insert/Delete/Home/End/RePág/AvPág;
- Ctrl y Alt derechos;
- `/` del teclado numérico, las teclas Windows y Menú.

El scan code sigue siendo el de `MAPVK_VK_TO_VSC`.

El log de los programas de 32 bits suma `trace+dinput`, para ver qué código DIK recibe DirectInput por cada tecla.

## Qué se espera

- Las flechas mueven la selección del menú de SuperMarioKart.
- En el log, `dinput_keyboard_hook` con `vkCode 0x27` y la tecla `cd` (`DIK_RIGHT`) en `setting key`.

## Prueba física

`reports/wine-hardware-w141/physical/20261103T074002Z`. El usuario confirma: **las flechas mueven la selección del menú**.

Con `trace+dinput` se ve que el juego crea un dispositivo de teclado de DirectInput (formato de 256 bytes, `DISCL_EXCLUSIVE | DISCL_FOREGROUND`, buffer de 32), pero nunca lo adquiere. No hay `Acquire`, ni lecturas de estado, ni eventos del hook. Las teclas le llegan por los mensajes de ventana. El arreglo funciona porque el juego arma el código de tecla con el scan code y el bit de tecla extendida del `lParam` de `WM_KEYDOWN`, que también dependen de `KEYEVENTF_EXTENDEDKEY`. Las notas de W140 que hablan de DirectInput describen el mecanismo de Wine, pero el juego no pasa por ahí.

## Estado de SuperMarioKart (fase 5)

- Arranca con CPU de 32 bits nativa (W137).
- Música MIDI con batería (W139/W140).
- Efectos de sonido.
- Enter, Back y flechas en el menú (W141).
- Pendiente: ~12 FPS (presentación o límite del juego) y xinput para mandos.
