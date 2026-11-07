# W113: diagnóstico de audio DOS (smb.exe sin sonido)

[English](HARDWARE_W113.md) | [Español](HARDWARE_W113-es.md)

APP_VER 02.12. Base W112 (Task Manager aceptado, DOS incluido).

## Lo que muestran los logs de W112 (20261102T193318Z)

smb.exe abre por la ruta DOS (`PWDOS dispatch`), el core DOSBox Pure corre y la salida de audio de la PS4 se abre sin errores:

- `PWDOSAUDIO init rc=0`, luego `open source_rate=44100 port=536870919 status=0`.
- El core pide 48000 Hz: el host cierra y reabre (`init rc=8026000e`, ya inicializado, aceptado) y `open source_rate=48000 ... status=0`.
- Al cerrar: `close blocks=15318` (run-0001) y `blocks=11137` (run-0002), sin errores. Son unos 80 y 60 s de audio entregados a `sceAudioOutOutput` en bloques de 256 cuadros.

O sea, el audio sí llega al puerto y el puerto lo acepta. Con estos logs no se puede distinguir entre: (a) el core entrega silencio (el juego no usa un dispositivo emulado activo, o lo usa con volumen 0), o (b) la PS4 no reproduce ese puerto (volumen del puerto, usuario, ruta de salida).

## Cambio (sólo ELF, native/dos_audio.c)

- Tras `sceAudioOutOpen`, `sceAudioOutSetVolume` a 0 dB (32768) en L y R, con rc en el log (`PWDOSAUDIO volume`). Si falla, se cierra el puerto y se devuelve el error; el host muestra «sin audio». No se asume el volumen por defecto del puerto.
- Nivel de la señal que manda el core: cada 938 bloques (~5 s) `PWDOSAUDIO level` con cuadros recibidos, muestras distintas de cero y pico; al cerrar, los totales.

doshost.exe, el core y el runtime PE no cambian (553 archivos, 2 subidos: registro).

## Entrega

`/data/pkg/orbis-win-W113-20ce4e1f2972.pkg`, lectura de vuelta verificada; informe reports/wine-hardware-w113/transfers/20261102T193930Z.json. W112 retirado.

## Prueba

Abrir Documents/smb.exe, jugar unos 20 s, cerrar. Decir si se oyó algo.

```sh
python3 tools/fetch-hardware.py --build W113 --host 192.168.68.104
```

- `volume rc=0` y se oye: era el volumen del puerto.
- `peak=0` / `nonzero=0`: el core entrega silencio; siguiente paso, revisar qué dispositivo de sonido usa el juego (PC speaker, Sound Blaster, AdLib) y la configuración del core.
- `peak>0`, `volume rc=0` y no se oye: el problema está en la salida de la PS4.

## Resultado físico: 20261102T194242Z

- `PWDOSAUDIO volume ... rc=0` en las dos aperturas: el volumen del puerto quedó en 0 dB.
- El core corrió a tiempo real (2046 cuadros a 70,087 Hz, 1.401.243 cuadros de audio a 48 kHz, unos 29 s) y entregó **sólo silencio**: `nonzero=0 peak=0` en cada intervalo y al cerrar. Cierre de doshost con 0.
- Conclusión: con smb.exe no hay sonido porque el emulador DOS no genera nada, no porque se pierda en la salida de la PS4. Que la PS4 reproduzca audio todavía no está probado: hace falta una fuente que sí genere señal.
- smb.exe está empaquetado dos veces (PKLITE y LZEXE); no se puede saber por sus cadenas qué dispositivo de sonido usa. Siguiente prueba: CARMEN.EXE (Where in the World is Carmen Sandiego), que usa PC speaker en la presentación. Si da `peak>0`, la ruta de audio funciona y el silencio es propio de smb.exe o de su configuración.
