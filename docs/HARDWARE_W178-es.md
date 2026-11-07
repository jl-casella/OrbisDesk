# W178: sin los diagnósticos de velocidad, descriptor sets por lotes (fases 5 y 6) y mando por XInput (fases 5 y 7)

[English](HARDWARE_W178.md) | [Español](HARDWARE_W178-es.md)

APP_VER 02.77. Base W177. El resultado de W177 está en `docs/HARDWARE_W177.md`.

## Diagnósticos que se quitan

Los registros y contadores que midieron la velocidad de SuperMarioKart en W157–W167. Lo que optimizaron se queda.

- **`native/wine_hardware.c`:** los programas de 32 bits ya no reciben `PW_NATIVE_PROFILE`, `PW_QPC_TSC_HZ`, `PW_VK_BATCH_STATS` ni `PW_VK_BATCH_FALLBACK_PROFILE`.
  - Sin ellos dejan de salir `PW_NATIVE_PROFILE`, `PW_VK_BATCH`, `PW_VK_PRESENT_INTERVAL` y el perfil de llamadas que el lote no agrupa.
  - El agrupamiento de llamadas Vulkan (`PW_VK_BATCH=1`) sigue activo.
- **`native/wine_vk_runtime.c`:** sale `PWVK cpu`, el porcentaje de CPU del proceso y del hilo que presenta (W157).
  - Siguen `PWVK present fps`, una línea por segundo (W074), y el contador de F12.
- **`tools/build-wow64native-ps4.py`:** sale el conteo de llamadas al sistema por hilo (`PWSYSCALL`, W160). `Wow64SystemServiceEx` vuelve a ser el de Wine.
- **`tools/build-wined3d-hw.py`:**
  - Salen:
    - los tiempos del hilo de comandos (`PWCS`, W160);
    - el detalle de cada copia (`PWBLT`, W160);
    - los tiempos de subidas y bajadas (`PWUPLOAD` y `PWDOWNLOAD`, W162/W164);
    - los contadores de llamadas Vulkan (W165);
    - las líneas `PWCKEY` de cada copia y de cada imagen de origen.
  - La línea `PWCKEY` única del formato pasa a TRACE.
  - Siguen las optimizaciones: staging en memoria cacheada para subir y bajar, 512 MB de mapeos persistentes y las copias con color clave en la GPU.

## Descriptor sets por lotes

`tools/build-wined3d-hw.py`, `context_vk.c`:
- **Antes:** wined3d pedía un descriptor set por dibujo. En SuperMarioKart eran ~185 `vkAllocateDescriptorSets` por cuadro (W165–W167). En un programa de 32 bits cada uno es un cruce de 32 a 64 bits, y el agrupamiento de llamadas Vulkan no puede diferirlo, porque devuelve el set.
- **Ahora:** se piden de a 16 del mismo layout al pool actual.
  - Los sobrantes esperan en un caché chico, por pool y layout.
  - Cuando el pool se reinicia, se retira o se destruye, sus sobrantes se olvidan; el reinicio ya los libera.
- **Si no entra:** si el lote no cabe en el pool, se usa la asignación individual de wined3d, que retira el pool lleno como antes.

Se espera menos tiempo de CPU por cuadro en el hilo de comandos de wined3d. Se mide por FPS (F12 o MangoHud), comparando con W176/W177.

## Mando: XInput, modo juego y joy.cpl (fases 5 y 7, sesión de accesos directos)

### Punto de partida

- `native/hw_pad.c` lee el mando cada 16 ms y lo convierte en mouse y teclado:
  - stick izquierdo y touchpad: puntero; stick derecho: rueda;
  - X: clic; Círculo: clic derecho;
  - cruceta: flechas; Triángulo: Enter; Cuadrado: Escape; Options: tecla Windows.
- Ningún juego veía el mando:
  - xinput no estaba en el prefijo;
  - el xinput de Wine busca mandos por HID (winebus y hidclass bajo winedevice), que un título de PS4 no tiene.

### Cambios

- `tools/build-xinput-hw.py` (nuevo): xinput con el mando de la consola como controlador 0. Es el método del parche 0470 de prospero-win, reescrito para el Wine fijado, cuyo contexto es distinto.
  - xinput gana una librería Unix cargada por nombre (`xinput1_3`), compartida por xinput1_1, 1_2, 1_3 y 1_4 (x86_64 e i386).
  - Si responde, el controlador 0 es el mando y no arranca el hilo HID:
    - `XInputGetState(Ex)` y `XInputGetKeystroke` leen su estado;
    - `XInputSetState` y `XInputEnable` pasan la vibración;
    - `XInputGetCapabilities(Ex)` informa un mando de Xbox 360 con cable (045e:028e), que es lo que buscan los juegos;
    - `XInputGetBatteryInformation`: con cable.
  - `xinput9_1_0` reenvía a `xinput1_4` y va sin cambios. También se agrega el `hid.dll` de 64 bits, que xinput importa y el prefijo no tenía.
  - La parte Unix llama directo a `pw_wine_pad_available`, `pw_wine_pad` y `pw_wine_set_rumble`, porque el ELF es estático. Sus tablas se llaman `pw_xinput_unix_call_funcs` y `pw_xinput_unix_call_wow64_funcs`.
  - Un solo mando: los cuatro de 0471 quedan para después.
- `native/hw_pad.c`:
  - sigue siendo el único que lee el mando y guarda su último estado, con un número de paquete que cambia con cada entrada;
  - `pw_wine_pad` lo da en términos de XInput:
    - Cruz/Círculo/Cuadrado/Triángulo → A/B/X/Y; L1/R1 → LB/RB; L2/R2 → gatillos analógicos; L3/R3 → pulsar los sticks;
    - Opciones → Inicio; clic del touchpad → Atrás; cruceta → DPAD;
    - sticks de 0..255 a −32768..32767, con Y hacia arriba;
  - `pw_wine_set_rumble`: `scePadSetVibration` (motor izquierdo = grande). Si falla, `PWPAD rumble_failed rc=...`.
- **Modo juego** en `hw_pad.c`:
  - mientras algún programa haya leído el mando por XInput en el último segundo, los sticks y botones dejan de mover el puntero y de mandar clics y teclas; así un juego no recibe además clics, flechas, Enter y Escape;
  - al entrar se sueltan los botones que la emulación tenía apretados;
  - el movimiento del touchpad sigue moviendo el puntero (XInput no tiene touchpad), y su clic es el Back del juego;
  - el mouse y el teclado USB no cambian;
  - una línea `PWPAD game_mode=1` o `PWPAD game_mode=0` en cada cambio.
- `platform/ps4/pw_wine_unixlibs.c`:
  - la entrada `xinput1_3.so`;
  - definiciones débiles "sin mando" para `ntdll.so` y `bootstrap.elf`, que no llevan `hw_pad.c`: ahí xinput sigue por HID;
  - la carga por nombre acepta un nombre sin extensión (`xinput1_3` → `xinput1_3.so`), además de `<x>.drv`.
- `tools/link-wine-boot.py`: enlaza `xinput-unix.o`, con verificación de su sha256.
- `tools/stage-wine-programs.py`:
  - suma `control.exe` y `joy.cpl`;
  - la clausura saltea `xinput*`. Sin eso, `joy.cpl` traía el `xinput1_3.dll` sin parchear.
- `tools/make-start-menu.py`: "Game Controllers" en System Tools (`control.exe joy.cpl`). Los demás accesos no cambian, ni su hash.
- `tools/build-wine-hardware.py`:
  - copia xinput y `hid.dll` a las carpetas builtin y a `system32`/`syswow64`;
  - se saca el `user_reg_reset` de W177, que era de una sola vez.

Comprobado sin la consola:
- todo compila sin advertencias (`hw_pad.c` y `pw_wine_unixlibs.c` con las opciones del launcher y `-Wall`; xinput con los comandos del build fijado);
- un enlace parcial de `hw_pad.o` + `pw_wine_unixlibs.o` + `xinput-unix.o` resuelve las tres funciones a las de `hw_pad.c`.

Para construir:
1. `tools/build-xinput-hw.py`, `tools/stage-wine-programs.py` y `tools/make-start-menu.py` (los tres ya corridos);
2. `tools/link-wine-boot.py`, porque cambia el ELF;
3. la cadena de siempre.

### Prueba

1. Start → System Tools → Game Controllers → pestaña XInput:
   - el controlador 0 aparece conectado;
   - los botones, los sticks y los gatillos se mueven en el dibujo;
   - el botón de vibración hace vibrar el mando.
2. Con esa pestaña abierta: en el log, `PWPAD game_mode=1`.
   - Los sticks y botones no mueven el puntero; el touchpad sí.
   - Al cambiar de pestaña o cerrar el panel, `PWPAD game_mode=0` y el mando vuelve a ser mouse.
3. Un juego con XInput, de 32 o de 64 bits:
   - responde al mando;
   - no aparecen clics ni teclas de más;
   - si el juego vibra, vibra el mando.
4. Regresión: sin juegos abiertos el mando sigue siendo mouse y teclado como antes; mouse y teclado USB, igual.

Riesgos:
- Un programa que lea XInput sin ser un juego (`joy.cpl`) también activa el modo juego mientras lo hace. El touchpad sigue moviendo el puntero.
- Un juego que lee el mando solo de a ratos (menos de una vez por segundo) recibiría clics de la emulación entre lecturas.
- La pestaña DirectInput de `joy.cpl` no lista nada hasta W179.

## Luna y Noir

`out/msstyles-hw` se regeneró antes de esta build, con un pedido del usuario sobre W177: Luna se parecía demasiado a Aero.
- Ahora la barra de título y el borde son de color sólido: azul XP en Luna y naranja en Noir.
- La barra de tareas, el botón Start y el marco plano van en W179, con los cambios de explorer y win32u.

## Prueba física

Reporte: `reports/wine-hardware-w178/physical/20261103T214906Z/`. Respuesta del usuario: "Todo bien".

- **Mando:** `PWPAD game_mode=1` en las dos primeras partidas (el panel Game Controllers, pestaña XInput). No hubo ningún `rumble_failed`.
- **SuperMarioKart** (`run-0003`):
  - 91 segundos con FPS, mediana 54,7 (mínimo 0,6 en cargas, máximo 323,6 en menús). En W176 la mediana fue 53,3: la mejora es chica, dentro de la variación entre partidas.
  - El modo juego no se activó: SuperMarioKart no lee XInput. Para jugarlo con el mando hace falta DirectInput (W179).
