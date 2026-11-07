# Mando para juegos después de W195: análisis (borrador, sin cambios de código)

[English](HARDWARE_mando-juegos-analisis.md) | [Español](HARDWARE_mando-juegos-analisis-es.md)

## Lo que ya existe (W178, W179, W181)

- `tools/build-xinput-hw.py`: xinput (1_1 a 1_4, x86_64 e i386) con el mando de la consola como controlador 0, por `pw_wine_pad` de `native/hw_pad.c`. Método de prospero-win 0470.
- `tools/build-dinput-hw.py`: DirectInput y DirectInput8 con un dispositivo propio (`joystick_pad.c`) que lee XInput 0.
- Modo juego en `native/hw_pad.c`: mientras algún programa lea el mando por XInput (último segundo), los sticks y botones dejan de mover el puntero y de mandar teclas (`PWPAD game_mode=1`). Ya responde a "cómo lo recibe un juego sin que lo reciba el escritorio".
- En W178 se vio `PWPAD game_mode=1` con el panel Game Controllers. Por lo tanto XInput y el modo juego funcionan en hardware.

## Por qué The Lost Forest no ve el mando (W195)

En `reports/wine-hardware-w195/physical/20261104T112911Z/run-0001.log`:
- El juego (hilo 0040) carga `xinput1_3.dll` pero no `dinput8.dll` ni `hid.dll`.
- No hay ninguna línea `PWPAD game_mode`. Nunca llamó a `XInputGetState`.

Se revisó `UnityPlayer.dll` (Unity 2020.3.3f1, input clásico; el juego no trae el Input System nuevo) desensamblándolo con `llvm-objdump`:
- Unity descubre mandos sólo por HID, por dos caminos:
  - **SetupDi** sobre la interfaz HID (`HidD_GetHidGuid`, `SetupDiGetClassDevsA`, `SetupDiEnumDeviceInterfaces`). Los paths que contienen `IG_` o `ig_` se **saltean** (0x1805137aa).
  - **Raw input** (`GetRawInputDeviceList`, `GetRawInputDeviceInfoW` con `RIDI_DEVICEINFO` y `RIDI_DEVICENAME`). Para un nombre con `IG_` (0x18051b747), busca el primer slot 0–3 donde `XInputGetState` responde (0x180ead470) y lo asocia al dispositivo.
- Después, con o sin `IG_`, abre el nombre con `CreateFileW(GENERIC_READ, FILE_SHARE_READ|WRITE, OPEN_EXISTING, FILE_FLAG_OVERLAPPED)` (0x18051b7ba). Si falla, registra el error y descarta el dispositivo.
- Llama a `HidD_GetPreparsedData`, `HidD_GetProductString`, `HidP_GetCaps`, `HidP_GetButtonCaps`, `HidP_GetValueCaps` y `HidP_MaxDataListLength` sobre ese handle.
- Lanza un `ReadFile` overlapped. Acepta éxito o `ERROR_IO_PENDING`.

Conclusión: para Unity hace falta un dispositivo HID de verdad, listado por raw input, con `IG_` en el nombre, que se pueda abrir y que responda las IOCTL de HID. XInput ya está bien; lo que falta es que Unity llegue a usarlo. Es lo mismo que hace Wine en Linux: winebus agrega `&IG_00` a los mandos XInput. En Orbis no hay winebus, hidclass ni winedevice (el mismo límite que `\\.\Nsi` en W174).

SDL2 (modo raw input o HIDAPI), el camino HID de dinput y Windows.Gaming.Input necesitan lo mismo. WGI además necesita los avisos PnP de llegada (plugplay), que no existen en el modelo de un proceso.

## Opciones

| | Qué | Toca | Tamaño | Riesgo |
|---|---|---|---|---|
| A | Emular del lado del cliente, como `nsi.dll` en W174: una entrada sintética en la lista de raw input de win32u; `hid.dll` contesta `HidD_*` para ese nombre; y algo abrible con lecturas pendientes (por ejemplo un named pipe con `IG_` en el nombre) | win32u, hid.dll y, si el pipe no alcanza, ntdll | Mediano | Frágil: imita lo que Unity hace hoy, no un dispositivo |
| B | Correr el stack HID de Wine dentro del proceso: un hilo con el bucle de `ntoskrnl.exe` (`wine_ntoskrnl_main_loop`), `hidclass.sys` y `winebus.sys` con un backend nuevo (Unix side) que lee `pw_wine_pad` y publica un mando Xbox 360 con `IG_00` | launcher (arranque del hilo), winebus (backend nuevo), registro de servicios y staging | Grande | Hay que probar primero que el device manager del wineserver en proceso y el PnP de ntoskrnl funcionen sin winedevice ni plugplay |
| C | Un dispositivo HID mínimo propio: un hilo que habla el protocolo de device manager del servidor y contesta sólo las IOCTL que usan `hid.dll` y win32u, con claves `DeviceClasses` en el registro | DLL nueva y registro | Mediano-grande | Hay que generar los datos preparsed sin hidclass |

Recomendación: B, empezando por una sonda chica que cree un device manager y un dispositivo dentro del proceso y lo abra con `CreateFile`. Si la sonda falla, A. Es lo único que deja funcionando a Unity, SDL, el HID de dinput y raw input como en Linux. El XInput y el modo juego actuales se quedan como están.

Windows.Gaming.Input (`joy.cpl`): no es barato con ninguna opción. Depende de los avisos PnP; queda para después de B.
