# W114: CARMEN.EXE cerraba todo el escritorio

[English](HARDWARE_W114.md) | [Español](HARDWARE_W114-es.md)

APP_VER 02.13. Base W113.

## Qué pasó (W113, 20261102T194525Z, run-0001)

Primero se abrió smb.exe, que cerró bien. Después se abrió CARMEN.EXE y el título terminó con `process_exit status=0xc0000005`. En el log aparecen dos fallos encadenados:

1. **En el motor DOS.** El hilo de emulación (004c) escribe en la dirección 0 con un `memset` de 0xfa000 bytes, que es exactamente un cuadro de 640×400×4. El módulo `dosbox_pure_libretro.dll` no se había descargado al cerrar smb.exe: la segunda apertura reusó el mismo módulo, con el estado global de la primera. En W112 (run-0001) pasó la misma secuencia, smb.exe seguido de CARMEN.EXE, y el log también terminó en ese punto. CARMEN.EXE nunca se abrió como primer juego, así que que la causa sea la reutilización del motor es la hipótesis más probable, no un hecho.
2. **En explorer.** Al no manejarse la excepción, Wine llamó al filtro global de excepciones no manejadas, que seguía apuntando a `_gnu_exception_handler` del doshost.exe de smb.exe. Ese filtro lo instala el CRT de mingw, y ese doshost ya estaba descargado (0x1007C39E0, RVA 0x39e0). Se ejecutó memoria liberada y se cayó todo el proceso, es decir, explorer y todos los programas abiertos.

## Cambios

- `native/doshost_win32.c`: después de `retro_deinit`, `FreeLibrary` del motor, con `PWDOS core_unloaded freed=…` en el log. Cada juego arranca con el motor recién cargado. Antes se dejaba cargado a propósito para reusarlo, y eso es lo que falló.
- `tools/build-guest-hw.py` (kernelbase): al descargar un invitado, si el filtro de excepciones no manejadas apunta dentro de su imagen, se borra (`PWGUEST unload cleared exception filter`). Afecta a todos los programas, no sólo a los de DOS.

Entrega: `/data/pkg/orbis-win-W114-dcc5ea137af1.pkg`, con la lectura de vuelta verificada; informe reports/wine-hardware-w114/transfers/20261102T195238Z.json (553 archivos, 10 subidos). W113 retirado.

## Prueba

1. Abrir smb.exe, cerrarlo y abrir CARMEN.EXE.
2. Esperar que suene la música de la presentación (PC speaker).
3. Si CARMEN.EXE vuelve a fallar, abrirlo como primer juego después de reiniciar el título, para separar un fallo propio del juego de la reutilización del motor.

En el log hay que buscar `core_unloaded freed=1`. Si hay un fallo, tiene que aparecer `cleared exception filter` y no un salto a memoria liberada. Para el sonido, mirar `PWDOSAUDIO level` (pico mayor que 0).

## Resultado físico: 20261102T195906Z (run-0001)

- Orden usado: CARMEN.EXE primero (unos 198 s, 13880 cuadros), luego smb.exe dos veces. Los tres cerraron con 0, sin caída de explorer.
- En los tres cierres: `core_unloaded freed=1` y `unload cleared exception filter` (el filtro del CRT de doshost quedaba registrado; ahora se borra).
- Audio de CARMEN.EXE: el motor genera señal real (`nonzero=5217060`, pico de hasta
  32768) en tramos que coinciden con música y efectos, con silencios entre medio. La ruta motor → puente → `sceAudioOutOutput` entrega muestras con sonido, y el usuario confirmó «tiene sonido carmen»: el audio DOS se oye en la PS4.
- smb.exe sigue entregando silencio (`peak=0`) en las dos aperturas: es propio de ese juego o de su configuración de sonido, no de la salida.
- No se probó CARMEN.EXE después de smb.exe en la misma sesión, que era el caso que fallaba; el descargado del motor sí se ejercitó entre las tres aperturas.

## Consulta: Documents/SuperMarioKart/SuperMarioKart.exe (20261102T200017Z)

No es DOS: es un PE32 de Windows (`machine 0x14c`, subsistema GUI), de 2.043.904 bytes. Explorer lo manda por ShellExecute y kernelbase lo rechaza con `PWOPEN reject_title_replacement`: los invitados que se abren desde el escritorio tienen que ser PE64, y un PE32 sólo puede arrancar como programa inicial del título (por WoW64). No se cae nada, sólo no abre. Sus datos (`SMK/*.x`, `.wav`) indican Direct3D con mallas DirectX y sonido WAV. Aunque abriera, haría falta Direct3D, que hoy no existe (wined3d con `renderer=no3d`, sin DXVK), y audio Win32 (winmm/dsound), que no tiene driver en la PS4. Se inspeccionó sólo por FTP, sin modificar archivos.
