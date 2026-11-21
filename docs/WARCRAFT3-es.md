# Warcraft III 1.07: las importaciones estáticas de Storm y los videos AVI de introducción

[English](WARCRAFT3.md) | [Español](WARCRAFT3-es.md)

Estado: dos correcciones, ambas confirmadas en la consola, 2026-11-17. El juego arranca, reproduce su video de introducción con sonido, llega a su menú y termina con estado 0 en 04.15 (`run-0205.log`). Se ejecutó la copia propia del usuario de Warcraft III 1.07 desde una unidad USB (`E:\PC\Warcraft III`). Es un juego en una consola, no una afirmación de compatibilidad para otros juegos o versiones de Blizzard.

## 1. "Warcraft III was unable to initialize"

Hasta 04.12 el juego se detenía enseguida con "unable to initialize". No faltaba ningún archivo y nada fallaba.

**Causa (nuestra, el cargador de invitados).** El `DllMain` de Storm.dll mira `lpReserved` en `DLL_PROCESS_ATTACH`:
- Windows pasa un `lpReserved` no nulo a las DLL que un proceso importa estáticamente, y NULL a una DLL cargada con `LoadLibrary`.
- Con NULL, Storm supone que la cargó otro programa y construye su tabla de descifrado MPQ con otra semilla. Entonces cada tabla hash de los archivos del juego se descifra como basura, y cada búsqueda de archivo dentro de ellos falla sin leer nada.
- `war3.exe` importa Storm estáticamente. OrbisDesk inicia un EXE invitado con `LoadLibraryExW`, así que las importaciones estáticas del EXE invitado se adjuntaban con NULL, como si se cargaran con `LoadLibrary`.

Dos sondas pequeñas lo mostraron en la consola (04.12): una DLL que registra su `lpReserved` recibió NULL como importación estática, y un programa que importa estáticamente el Storm.dll del juego encontró ilegible la tabla hash de cada archivo, byte a byte igual que con `LoadLibrary` en el Wine del host.

**Corrección.** [build-guest-hw.py](../tools/build-guest-hw.py) agrega una revisión al cargador `ntdll` de invitados. Cuando se carga una imagen invitada y el módulo es el propio EXE invitado, `process_attach` recibe un puntero a un `CONTEXT` estático en lugar de NULL, como hace `loader_init` de Wine para un proceso. Las DLL que un `DllMain` carga mientras tanto siguen recibiendo NULL. Se aplica a las dos compilaciones de `ntdll` para invitados (64 bits e i386). Desde 04.13 el juego se inicializa.

## 2. Los videos de introducción

En 04.13 el juego se caía justo después de inicializarse: `PWFAULT` en Game.dll, el diálogo "FATAL ERROR" de Storm, y luego terminaba todo el título.

**Causa (nuestra, una capacidad de DirectShow que faltaba).**
- Los videos de `Movies\*.mpq` son archivos AVI: video en el DivX de Blizzard ("BLZ0") y audio en MP3.
- Game.dll los reproduce con DirectShow. En Windows el grafo es File Source → AVI Splitter → el `blizzard.ax` propio del juego ("DivX for Blizzard Decoder Filter", que `war3.exe` registra en cada arranque) → Video Renderer, y el flujo MP3 va a un decodificador MP3 y al renderizador de DirectSound.
- El DirectShow de 32 bits de la consola (`stage-dshow-i386.py`, W225) no tenía separador AVI. El separador AVI de Wine es parte de winegstreamer, y la consola no tiene GStreamer. Por eso fallaba `IGraphBuilder::RenderFile`.
- Game.dll ignora ese fallo, inicia de todos modos el temporizador del video y desreferencia el grafo NULL en el primer tic. Es un error del propio juego, pero solo aparece cuando `RenderFile` falla, y en Windows no falla.

**Corrección: un separador AVI para invitados de 32 bits.**
- [pwavi.c](../native/pwmpeg1/pwavi.c) agrega "PW AVI Splitter" como segundo filtro en `pwmpeg1.ax`. Como el AVI Splitter de Windows, solo separa; los decodificadores que siguen en el grafo decodifican.
  - Lee las cabeceras AVI (`hdrl`, `strh`/`strf`) y el índice `idx1`, o recorre la lista `movi` cuando no hay índice.
  - Cada flujo de video o audio recibe un pin de salida con el formato propio del flujo: `VIDEOINFOHEADER` con el FOURCC como subtipo, o `WAVEFORMATEX` con la etiqueta de formato como subtipo.
  - Cada pin tiene su propio hilo de entrega. Los tiempos de las muestras salen de `dwScale`/`dwRate` del flujo, y los fotogramas clave de las marcas del índice.
  - Cada pin informa la duración del flujo mediante `IMediaSeeking`. Sin eso, el grafo de filtros de Wine mantiene su posición en 0, y Game.dll lee esa posición en cada tic del temporizador. No ofrece búsqueda (seeking).
  - Un archivo que no puede analizar se rechaza (`PWAVI reject` en el registro), y `RenderFile` falla como antes.
- [pwmpeg1.c](../native/pwmpeg1/pwmpeg1.c) entrega los dos filtros. El decodificador MPEG-1 no cambia.
- [stage-dshow-i386.py](../tools/stage-dshow-i386.py) compila `pwavi.c` dentro de `pwmpeg1.ax` y registra el separador en la vista de 32 bits, con un mérito apenas superior al "AVI Splitter" de winegstreamer (que sigue registrado en el prefijo base, pero no puede cargarse en la consola).

No se simula nada: el video lo decodifica el propio `blizzard.ax` del juego, y el MP3 los decodificadores PE de Wine, que no tienen parte Unix.

En el Wine del host, `RenderFile` tuvo éxito con el mismo video, el video se decodificó en tiempo real hasta su último fotograma (3260), y la posición del grafo llegó a la duración del video (135,47 s).

## 3. En la consola: 04.15 (`run-0205.log`)

Evidencia: `reports/wine-hardware-w303/physical/20261117T171642Z/` (local, no está en Git).

- El primer arranque de 04.15 todavía se caía. La consola fusiona las claves nuevas del `system.reg` de la build en el prefijo solo una vez por ID de build (marcador `/data/orbisdesk/w303/system-reg-merged.txt`). Esa fusión ya se había hecho para W303 con una versión anterior, así que el registro del separador no estaba. Tras borrar ese marcador, el siguiente arranque fusionó 110 claves (`system_reg_merge … added=110 … rc=0x00000000`).
- En ese arranque:
  - `PWAVI open size=103433e streams=2 indexed=1`: se analizaron los dos flujos, video `BLZ0` y audio MP3 (etiqueta de formato `0x55`).
  - Los dos flujos entregaron muestras (`first_sample hr=0`). La introducción se reprodujo con imagen y sonido hasta que se detuvo: 2137 muestras de video y 1723 de audio, unos 89 s de los 135 s del video. La ventana del video se presentó a unos 24 fotogramas por segundo, la velocidad del video.
  - Luego el juego fijó 1024x768 y dibujó su menú con d3d8 (wined3d, renderizador OpenGL).
  - Sin `PWFAULT` ni "FATAL ERROR". `war3.exe` terminó con estado 0.
- El mismo registro tiene cinco arranques posteriores de `war3.exe`, cada uno terminado con estado 0. No reproducen video de introducción.

### La línea "MPEG Layer-3 Decoder"

El registro contiene:

```
err:winediag:mpeg_layer3_decoder_create GStreamer doesn't support MP3 audio decoding, please install appropriate plugins.
err:quartz:autoplug Failed to create filter for L"MPEG Layer-3 Decoder", hr 0xd0000005.
```

Aquí es inofensiva:
- "MPEG Layer-3 Decoder" (`l3codecx.ax`) es el filtro MP3 de mayor mérito del prefijo. En Wine es una fachada de winegstreamer, que no puede funcionar sin GStreamer, así que crearlo falla. El fallo se devuelve como código de error (`0xd0000005` es `HRESULT_FROM_NT(STATUS_ACCESS_VIOLATION)`), no como una falla en el juego: no hay `PWFAULT` y el juego siguió.
- Luego quartz probó el siguiente filtro MP3. El registro muestra que se cargan `qasf.dll` (el envoltorio DMO) y `mp3dmod.dll` (el DMO decodificador MP3 de Wine, código PE con su propio mpg123) justo después, y luego arranca el flujo de audio. `l3codeca.acm` nunca se cargó, así que no se usó el camino del ACM Wrapper.
- El costo es un intento fallido por video: winegstreamer, mfplat, propsys y rtworkq se cargan en el juego sin uso. Quitar la entrada solo cambiaría la línea del registro y esa carga, así que se dejó como está.

## Límites

- El separador no maneja archivos OpenDML (AVI más grandes que su primer segmento RIFF), cambios de paleta ni búsqueda. Ofrece hasta 4 flujos, y solo de video y audio.
- No se confirmó en la consola un video reproducido hasta el final sin saltarlo, ni que el juego avance solo después. En el host, la salida de audio se detenía a los 32 s aproximadamente por la propia salida de sonido del host, así que tampoco pudo comprobarse allí.
- Solo se llegó al menú principal. No se probaron las cinemáticas de la campaña ni el juego en sí.
- La fusión del registro una vez por ID de build afecta a cualquier versión que agregue claves de registro sin un ID de build nuevo: una consola que ya ejecutó una versión anterior de ese ID de build no recibe las claves nuevas hasta que se quite el marcador. Una instalación limpia no se ve afectada.
- Sin corregir: una falla dentro del filtro de excepciones de nivel superior del propio invitado (como en 04.13, donde la segunda falla de Game.dll ocurrió dentro del diálogo de error de Storm) termina todo el título, no solo ese invitado. La excepción de segunda oportunidad sin manejar llega al `NtRaiseException` de la parte Unix de Wine, que termina el proceso; las salidas por invitado agregadas en W208 y W262 no cubren ese camino.
