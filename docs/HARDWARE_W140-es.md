# W140: batería General MIDI y flechas para DirectInput (fase 5)

[English](HARDWARE_W140.md) | [Español](HARDWARE_W140-es.md)

APP_VER 02.39. Base W139.

## Batería

En W139 la música suena sin batería: dmsynth dice `Could not find instrument with patch 0x80000000` y `0x80000018`.
- El lector de MIDI de dmime (`dlls/dmime/midi.c`) convierte cada cambio de programa en un instrumento de banda con el número de programa solo, también en el canal 10.
  - El canal de percusión carga entonces un instrumento melódico.
  - Si el canal 10 no tiene cambio de programa, no carga nada.
- dmsynth toca el canal 10 como batería (patch con `F_INSTRUMENT_DRUMS`; si no lo encuentra, prueba el kit estándar). No encuentra ningún kit y descarta las notas.

Cambio en `tools/build-dmsynth-i386.py`, que ahora también compila `dmime.dll` i386 con una copia de `midi.c`:
- Los cambios de programa del canal 10 llevan `F_INSTRUMENT_DRUMS`.
- La pista de bandas recibe en tiempo 0 el valor por defecto de General MIDI para el canal 10, el kit estándar. Un cambio de programa del propio archivo en el mismo tiempo se inserta después y gana.
- Los demás objetos y recursos de dmime son los del árbol del host.

## Flechas

En W139 Enter y Back funcionan en el menú del juego, pero las flechas no.
- Las flechas del pad llegan a Wine como `VK_LEFT`/`VK_RIGHT`/etc.
- El driver (`ps5drv.c`, overlay de `tools/build-win32u-ps4.py`) manda el scan code sin la marca de tecla extendida.
- DirectInput arma el código DIK con el scan code y esa marca. Sin ella, la flecha → (`0x4d`) se lee como `DIK_NUMPAD6` en lugar de `DIK_RIGHT`. Enter no es extendida y por eso funcionaba.

Cambio: el driver pide `MAPVK_VK_TO_VSC_EX`. Si el resultado tiene prefijo `E0`, manda la tecla con `KEYEVENTF_EXTENDEDKEY`. Afecta a las flechas, Insert/Delete/Home/End/RePág/AvPág, Ctrl y Alt derechos, entre otras.

## Qué se espera

- La música del título con batería.
- En el log, sin `Could not find instrument` para 0x80000000 ni 0x80000018. Puede quedar alguno si el banco no tiene ese kit exacto: entonces dmsynth usa el estándar.
- Las flechas mueven la selección en el menú de SuperMarioKart.

## Prueba física

`reports/wine-hardware-w140/physical/20261103T072747Z`. El usuario confirma: **suena la música con batería; las flechas siguen sin responder**.

- En el log ya no hay ningún `Could not find instrument`.
- Las flechas llegan a Wine (`code=38/39/40`), pero el arreglo de flechas no tuvo efecto.
  - En la tabla de teclado de Wine (`kbdus` en `win32u/input.c`), el scan code 0x4d sin prefijo (el 6 del teclado numérico) tiene como VK base `VK_RIGHT`.
  - `MapVirtualKeyEx(VK_RIGHT, MAPVK_VK_TO_VSC_EX)` recorre la tabla desde 0, devuelve 0x4d antes de llegar a 0xe04d y nunca da el prefijo `E0`.
  - Se corrige en W141 marcando las teclas extendidas por VK.
