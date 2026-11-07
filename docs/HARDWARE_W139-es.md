# W139: instrumentos de DirectMusic con GUID_Download (fase 5)

[English](HARDWARE_W139.md) | [Español](HARDWARE_W139-es.md)

APP_VER 02.38. Base W138.

## Problema

En W138 la cadena DirectMusic de SuperMarioKart arranca, pero no suena (ver `HARDWARE_W138.md`).
- El juego (Blitz3D, DirectX 7) pide cargar los instrumentos de la canción en el sintetizador con `IDirectMusicSegment::SetParam(GUID_Download, performance)`.
- En `dlls/dmband/bandtrack.c` del Wine fijado esa orden es sólo un `FIXME`. Ningún instrumento llega a dmsynth, y cada nota da `Could not find instrument`.

## Cambio

`tools/build-dmsynth-i386.py` ahora también compila `dmband.dll` i386:
- Usa una copia de `bandtrack.c` en la que `GUID_Download` toma la misma rama que `GUID_DownloadToAudioPath`, la orden equivalente de DirectX 8.
  - Ambas reciben una performance o un audio path y llaman a `IDirectMusicBand_Download` por cada banda de la pista.
  - El builder exige encontrar la rama original una sola vez.
- Los demás objetos y recursos de dmband son los del árbol del host.
- `tools/build-wine-hardware.py` copia esta dmband encima de la que viene en `out/wine-i386`.

## Qué se espera

- Que se oiga la música del título.
- En el log: ningún `GUID_Download not handled yet`, casi ningún `Could not find instrument` y `PWAUDIO level` con pico alto mientras suena la música.
- Puede quedar algún `Could not find instrument` si el banco no tiene un kit de batería pedido. En ese caso dmsynth usa el kit estándar.

## Prueba física

`reports/wine-hardware-w139/physical/20261103T071201Z`. El usuario confirma: **suena la música**. Las flechas del menú no parecen responder.

En el log (`run-0002.log`):
- No aparece `GUID_Download not handled yet`.
- `PWAUDIO level` llega a pico 32767.
- Los avisos `Could not find instrument` quedaron sólo para los patches 0x80000000 y 0x80000018, que son kits de batería. La batería no suena.
- Las flechas llegan a Wine como teclas (`input_event source=pad type=1 code=39`, `VK_RIGHT`).

Las dos cosas se corrigen en W140 (ver `HARDWARE_W140.md`).
