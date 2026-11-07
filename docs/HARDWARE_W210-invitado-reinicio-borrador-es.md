# W210: un invitado que se reinicia a sí mismo arranca de nuevo cuando ya terminó (borrador)

[English](HARDWARE_W210-invitado-reinicio-borrador.md) | [Español](HARDWARE_W210-invitado-reinicio-borrador-es.md)

Borrador de la sesión lateral del navegador, para unir a `HARDWARE_W210.md`. Nada de esto se probó en la consola.

## Qué pasó en W209

Reporte: `reports/wine-hardware-w209/physical/20261104T155634Z/run-0001.log`

- **La salida por fallo de W209 funciona:**
  - "36 otros hilos terminados, 7 ventanas de este hilo destruido";
  - `terminated=1` y `detach skipped`;
  - 28 módulos `gone=1`;
  - se liberan 1,2 GB (`memory … released=119 bytes=1201668096`).
- **Pale Moon arranca otra vez** (línea 2850, hilo `00f8`):
  1. Reconstruye su caché de arranque (`PWDELETE … startupCache`).
  2. Se reinicia a sí mismo: llama a `CreateProcess` con `palemoon.exe` y termina con estado 0 (línea 3303). Así es el reinicio de Mozilla, que no espera al hijo.
- **Por qué el hijo falla:**
  1. Como invitado, el hijo se cargó en ese mismo momento, con el primero todavía corriendo. Recibió su `palemoon.exe`, `xul.dll` y el resto ya inicializados (`load_end … module=0000000100DD0000 error=126`).
  2. La salida del primero los conservó, con razón: el hijo es un invitado vivo de la misma carpeta (`count=0 … live=1`).
  3. El hijo encontró XPCOM inicializado y terminó con estado 1 (línea 3319).

## Cambio

`tools/build-guest-hw.py` (kernelbase `process.c`), con `guest-relaunch-w210.patch.py`:
- **Cuándo actúa:** cuando un hilo de un invitado arranca el mismo programa del invitado (la misma ruta).
- **Qué hace:**
  - `CreateProcess` vuelve enseguida.
  - Un hilo auxiliar, que no es del invitado, espera a que ese invitado termine y se descargue (como máximo 15 s). Para eso hay un evento que se marca al final de `ps4_guest_unload`.
  - Después arranca el programa como un invitado nuevo, que lo carga desde cero.
- **Qué registra:** `PWGUEST relaunch_later …` y `PWGUEST relaunch … parent_wait=0`.
- **Si el invitado sigue corriendo a los 15 s:** el programa arranca igual, como antes (`parent_wait=258`).

## Construcción

1. `python3 tools/build-guest-hw.py`.
2. `tools/link-wine-boot.py`.
3. `tools/build-wine-hardware.py`.

## Prueba física

1. Repetir lo de W209: hacer que Pale Moon falle, volver a abrirlo, cerrarlo y abrirlo otra vez.
2. **Qué buscar en el log:**
   - si se reinicia, `PWGUEST relaunch_later app=…palemoon.exe` y, poco después, `PWGUEST relaunch … parent_wait=0`;
   - después, un `load_begin` nuevo con `Loaded … xul.dll` otra vez;
   - una ventana de Pale Moon, sin `exits status 1`.

## No verificado

- Nada se probó en la consola.
- El cambio se aplicó sobre copias de los fuentes, y `process.c` pasa `-fsyntax-only` con mingw. El builder no se corrió.
- Las variables de entorno que Mozilla pone para su hijo quedan en el proceso, que es compartido. Mozilla las borra al arrancar.
