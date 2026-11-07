# W181, parte del mando: perfiles de teclas para juegos que solo usan teclado

[English](HARDWARE_W181-teclas-plan-borrador.md) | [Español](HARDWARE_W181-teclas-plan-borrador-es.md)

Borrador de la sesión de configuración de Wine. La sesión principal lo suma a `HARDWARE_W181.md`.

## Qué pasó en W179 con SuperMarioKart

- En `run-0003.log` (`reports/wine-hardware-w179/physical/20261103T221722Z`):
  - SMK carga `DINPUT.dll` (línea 915) y, a través del dispositivo de W179, `xinput1_4` (2216);
  - `PWPAD game_mode=1` (2218) y, un segundo después, `game_mode=0` (2825), sin volver a activarse.
- SMK es un juego Blitz3D que **solo usa teclado**. Su `Read me.txt` (leído de la consola por FTP, sin modificar nada) dice:
  - flechas: acelerar, reversa y doblar;
  - espacio: usar objeto;
  - Enter: elegir en el menú;
  - Esc: cierra el juego sin avisar.
- Blitz3D enumera joysticks al arrancar: esa es la única lectura de XInput. Después el juego no vuelve a leer el mando.
- Sin modo juego, el mando seguía siendo mouse: el stick movía el cursor, y **cuadrado mandaba Escape**, que en SMK cierra el juego.

## Cambios

- `native/hw_pad.c`: perfiles de teclas por programa (`pw_hw_pad_profile`).
  - **Dónde están:** `C:\orbis\padmaps\<exe>.ini`, con líneas `fuente = tecla`; `#` o `;` empiezan un comentario.
  - **Fuentes:** `cross`, `circle`, `square`, `triangle`, `l1`, `r1`, `l2`, `r2`, `l3`, `r3`, `options`, `touchpad`, `up`, `down`, `left`, `right` (cruceta), y `stick_up`, `stick_down`, `stick_left`, `stick_right` (stick izquierdo, digital pasado un umbral).
  - **Teclas:** `up`, `down`, `left`, `right`, `space`, `enter`, `escape`, `tab`, `backspace`, `shift`, `ctrl`, `alt`, `home`, `end`, `pageup`, `pagedown`, `insert`, `delete`, `a`–`z`, `0`–`9`, `f1`–`f12`.
  - Una línea que no se entiende queda en el log como `PWPAD profile_line_ignored`.
  - Con perfil:
    - los botones que el perfil nombra mandan esas teclas, y los demás no hacen nada;
    - el stick izquierdo manda las flechas (o las teclas de `stick_*`), salvo con `stick = mouse`;
    - el stick derecho no hace scroll;
    - el touchpad sigue siendo el puntero, con su clic, salvo que el perfil nombre `touchpad`.
  - El modo juego de XInput sigue primero: si el programa lee XInput, el perfil no manda teclas, y al entrar se sueltan las que estaban apretadas.
  - Sin perfil, la emulación de siempre.
  - Log: `PWPAD profile=<exe> keys=N stick=keys|mouse`, o `PWPAD profile=<exe> none errno=...`.
- `native/wine_hardware.c`: cuando el launcher relanza un programa (`switched`) o corre uno de 32 bits, le pasa su ruta a `pw_hw_pad_profile`.
- `fixtures/padmaps/SuperMarioKart.exe.ini` (nuevo), que `tools/build-wine-hardware.py` copia a `C:\orbis\padmaps`:
  - cruz ↑ (acelerar), cuadrado ↓ (reversa);
  - círculo y R1: espacio (objeto);
  - cruceta y stick: flechas;
  - Options y triángulo: Enter;
  - Esc sin asignar.
- Un perfil se puede escribir o cambiar con Notepad y se lee al arrancar el programa.

Comprobado sin la consola:
- `hw_pad.c` y `wine_hardware.c` compilan sin advertencias con las opciones del launcher y `-Wall`;
- un enlace parcial resuelve `pw_hw_pad_profile`;
- el lector de perfiles, probado aparte, carga del `.ini` de SMK 14 teclas (10 botones y las 4 flechas del stick) y da `none` para explorer.

## Prueba

1. SuperMarioKart: en el log, `PWPAD profile=SuperMarioKart.exe keys=14 stick=keys`.
   - En los menús: stick y cruceta mueven, Options o triángulo eligen.
   - En carrera: cruz acelera, cuadrado reversa, stick o cruceta doblan, círculo o R1 usan el objeto.
   - El cursor no se mueve con el stick; el touchpad sí lo mueve.
   - Cuadrado ya no cierra el juego.
2. Al volver al escritorio: el mando es mouse otra vez (explorer no tiene perfil).
3. Un juego XInput sin perfil se comporta como en W178.

Riesgos:
- El mapeo de SMK es una propuesta; si el usuario prefiere otro, se cambia solo el `.ini`.
- Un juego que necesite Esc (por ejemplo, para la pausa) tiene que tenerlo en su perfil; en SMK quedó sin asignar a propósito.
