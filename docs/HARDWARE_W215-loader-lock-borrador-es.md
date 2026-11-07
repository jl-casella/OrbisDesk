# W215: el loader lock se toma aunque un hilo que lo esperaba haya sido terminado (borrador)

[English](HARDWARE_W215-loader-lock-borrador.md) | [Español](HARDWARE_W215-loader-lock-borrador-es.md)

Borrador de la sesión lateral del navegador, para unir a `HARDWARE_W215.md`. Nada de esto se probó en la consola.

## Qué pasó en W214

Reporte: `reports/wine-hardware-w214/physical/20261104T173546Z`. El usuario dijo: "W214 no JIT pareció más fluido, pero se volvió a congelar al cargar YouTube".

- **El reinicio solo funciona** (`run-0001.log`, líneas 2233 a 2237): `own=25 remaining=0`, `parent_wait=0`, y el hijo carga.
- **El cierre normal no descarga nada** (líneas 2798 a 3234):
  - repite `waits for the loader lock, owner 0000` durante 30 s y termina en `kept: loader lock busy for 30 s`;
  - los arranques siguientes terminan con estado 1;
  - W207 y W212 ya mostraban `loader_lock=0 tries=200` en `ps4_guest_exit_process`.
- **Por qué:**
  - `ps4_guest_exit_process` termina los otros hilos del invitado teniendo el loader lock (W122). Un hilo terminado mientras esperaba el lock deja su incremento en `LockCount`.
  - `RtlTryEnterCriticalSection` sólo toma el lock si `LockCount` vale -1, así que no lo logra nunca más. Por eso se ve sin dueño y nunca libre.
  - `RtlEnterCriticalSection` sí lo toma: cada liberación señala el semáforo, y el hilo muerto nunca toma esa señal. Por eso explorer y las cargas de DLL siguen andando.
- **YouTube sin JIT** (`run-0002.log`, líneas 3287 y 4034):
  - aparece `PWHUNG … "YouTube - Pale Moon"`;
  - el hilo principal (`0060`) sigue en un bucle dentro de `mozjs.dll`, sobre memoria con `e5e5e5e5`, a los 70 s;
  - el JIT queda descartado;
  - las direcciones están lejos de cualquier exportación de `mozjs.dll`: son funciones internas.
  
  No se encontró de dónde sale la memoria liberada. Los caminos de memoria de la consola no registraron ningún fallo (`PWVM`).
- **Aparte:** en `run-0002.log`, desde la línea 5089, `libMangoHud.dll` falla bajo `libgallium_wgl.dll` en `C:\orbis\glxgears.exe`, un invitado OpenGL que no es Pale Moon, y se cae el título. Es otro error.

## Cambio

`tools/build-guest-hw.py` (kernelbase `process.c`), con `loader-lock-w215.patch.py`. Hay dos esperas del loader lock: la de `ps4_guest_exit_process` y la de la descarga de los módulos propios.
- **Lo nuevo:** en las dos, si un intento falla y el lock no tiene dueño, se toma con un `LdrLockLoaderLock` bloqueante, que en ese estado vuelve enseguida. Se registra `took the ownerless loader lock after N tries`.
- **Con dueño:** los intentos siguen como antes.

## Construcción

1. `python3 tools/build-guest-hw.py`.
2. `tools/link-wine-boot.py`.
3. `tools/build-wine-hardware.py`.

## Prueba física

1. Abrir Pale Moon, cerrarlo y volver a abrirlo dos veces.
2. **Qué buscar en el log:**
   - `exits status 0`, y después `remaining=0` en cada cierre;
   - si hizo falta, `took the ownerless loader lock`;
   - en la salida, `loader_lock=1`.

## No verificado

- Nada se probó en la consola.
- El cambio se aplicó sobre copias de los fuentes, y `process.c` pasa `-fsyntax-only` con mingw. El builder no se corrió.
- La explicación del `LockCount` sale del código de las secciones críticas de Wine, no de una medición. La traza nueva muestra cuándo pasa.
- El cuelgue y los fallos de YouTube siguen sin explicar.
