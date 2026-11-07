# W120: audio de Windows (fase 3 del plan PE32)

[English](HARDWARE_W120.md) | [Español](HARDWARE_W120-es.md)

APP_VER 02.19. Base W119. Compilada y verificada localmente; **todavía no subida**: espera a que se pruebe W119, porque las dos comparten el runtime de `/data`.

## Diseño

- **Driver**:
  - Es el `wineps5` de prospero-win (`upstream/prospero-win/wine/wineps5/unix.c` con `src/pw_audio_mix.c`, LGPL-2.1-or-later), renombrado `wineps4`.
  - Cambios mínimos, en `tools/build-audio-ps4.py`: el sink está enlazado en lugar de buscarse con `dlsym`, y el dispositivo se llama `PS4`.
  - Funcionamiento: un endpoint de reproducción, mezcla a 48 kHz en bloques de 256 cuadros y el puerto como reloj.
  - Tiene tablas WoW64, así que sirve a programas de 32 y 64 bits.
- **Sink nativo** (`platform/ps4/pw_wine_audio.c`):
  - Abre su propio puerto AudioOut MAIN (S16 estéreo, 48 kHz, volumen 0 dB explícito), distinto del de DOS.
  - Los fallos se registran (`PWAUDIO open … failed=`) y se devuelven.
  - Cada ~5 s registra `PWAUDIO level grains/nonzero/peak`, como en W113.
- **Carga por nombre**:
  - mmdevapi pide `wineps4.drv` con `MemoryWineLoadUnixLibByName`, que en ntdll usaba `dlopen`, imposible en el ELF estático.
  - El `virtual.c` probado (se verifica su hash) se recompila con una sola adición: buscar primero en la tabla estática (`pw_wine_static_unixlib_by_name`, en `platform/ps4/pw_wine_unixlibs.c`). Log: `PWBOOT static_unixlib_by_name`.
  - Descargarlo no hace nada: el módulo es un marcador.
- **Registro**: `HKCU\Software\Wine\Drivers\Audio = "ps4"` en el `user.reg` del prefix. Hace el mismo trabajo que el parche 0120 de prospero-win, sin tocar el servidor.
- **DLL x64**: mmdevapi, dsound y msacm32 (`tools/stage-wine-i386.py`, `modules_x64`). Las i386 ya venían en W119.
- **Tamaño**: a partir de W120 también se quita la información de depuración de las DLL i386. Los módulos pasan de 507 a 183 MiB y el runtime de 442 a 303 MB.

<a id="fixtures"></a>


## Arreglos

`C:\orbis\sound64.exe` (invitado) y `C:\orbis\sound32.exe` (relanzamiento): tono de 440 Hz durante 2 s por `waveOut`. Cada paso queda en `C:\orbis\sound-result.txt` (devices, open, prepare, write, done).

## Construcción

```sh
python3 tools/stage-wine-i386.py
python3 tools/build-audio-ps4.py
python3 tools/link-wine-boot.py
python3 tools/build-wine-hardware.py --mangohud enabled
```

El enlace no tiene símbolos indefinidos. El ELF contiene `PWAUDIO level` y `static_unixlib_by_name`, y `user.reg` tiene `"Audio"="ps4"`.

## Prueba (cuando se suba)

1. sound64.exe: se oye el tono, `sound-result.txt` termina en `done=1` y en el log aparecen `static_unixlib_by_name wineps4.drv`, `PWAUDIO open … port>=0` y `PWAUDIO level` con peak > 0.
2. sound32.exe: lo mismo, por WoW64.
3. Solitaire o el sonido del sistema, si los usa.

## Entrega

Incluye además la corrección de ws2_32 de 32 bits que salió de la prueba de W119. `/data/pkg/orbis-win-W120-024d30e0d1c7.pkg`, con la lectura de vuelta verificada (603 archivos, 105 subidos). W119 retirado.

Prueba:
1. `C:\orbis\sound64.exe`: ¿se oye el tono?
2. `C:\orbis\sound32.exe`: lo mismo, por WoW64.
3. SuperMarioKart.exe: se espera que pase ws2_32 y avance hasta Direct3D 7.

## Resultado físico: 20261102T220327Z

El usuario no oyó ningún sonido, ni en 32 ni en 64 bits.

- **sound64.exe** (corrió dos veces como invitado) y **sound32.exe** (relanzamiento, `cpu=wowprospero`) terminan con 0. `sound-result.txt` dice `devices=0;open=6`, o sea `MMSYSERR_NODRIVER`.
- La causa está en el log: `ole:com_get_class_object class {bcde0395-e52f-467c-8e3d-c4579291692e} not registered`. Esa clase es `MMDeviceEnumerator`, y el prefix sellado se armó cuando mmdevapi no existía. winmm nunca llega a cargar el driver: no hay `static_unixlib_by_name` ni `PWAUDIO`. El driver y el sink no llegaron a probarse.
- **SuperMarioKart.exe**: pasa ws2_32, que ya quedó corregido. Ahora corta `"opengl32.dll" failed to initialize`: la opengl32 i386, que wined3d importa a través de ddraw, no tenía su parte Unix (`opengl32.so`). Termina con c0000142 y vuelve al escritorio.

# W121 (02.20)

- `system.reg` registra las clases COM de mmdevapi (MMDeviceEnumerator) y de dsound (DirectSound, DirectSound8, BufferConfig, Capture, Capture8 y FullDuplex) en `Classes\CLSID` y en `Classes\Wow6432Node\CLSID`, como haría su `DllRegisterServer`. El prefix no tenía ninguna entrada en Wow6432Node\CLSID.
- `tools/build-unixlibs-ps4.py` compila la parte Unix de opengl32 (`unix_thunks.c` y `unix_wgl.c`, sin parches) y `pw_wine_unixlibs.c` la registra como `opengl32.so` con tablas WoW64. El enlace queda sin símbolos indefinidos. Sus llamadas WGL van a win32u, que en la PS4 todavía no crea contextos GL. Lo esperable es que wined3d falle después, ya en la creación del dispositivo D3D (fase 4b).

Entrega: `/data/pkg/orbis-win-W121-69a6fea6d6c3.pkg`, con la lectura de vuelta verificada. W120 retirado.

## Resultado físico W121: 20261102T230543Z

- **sound64.exe suena** (confirmado por el usuario). Es el primer audio de Windows en la PS4:
  - `sound-result.txt`: `devices=1;open=0;prepare=0;write=0;done=1`;
  - en el log, `static_unixlib_by_name L"wineps4.drv" wow=0` y `PWAUDIO open init=0 port=536870919`.
- **Al terminar se cuelga la interfaz.** `ps4_guest_exit_process` termina los otros dos hilos del invitado. Uno de ellos (0048, el hilo de onda de winmm) estaba dentro de `LdrUnloadDll` con el lock del loader tomado. Muere con el lock, y después `RtlpWaitForCriticalSection … loader_section wait timed out in thread 0040, blocked by 0048`: desde ahí ninguna carga ni descarga de DLL puede avanzar, ni la de explorer.
- sound32.exe y SuperMarioKart.exe no se llegaron a probar por el cuelgue.

# W122 (02.21)

`tools/build-guest-hw.py`, `ps4_guest_exit_process`:
- Antes de terminar los otros hilos del invitado, toma el lock del loader (`LdrLockLoaderLock` en modo intento, hasta 2 s) y lo suelta cuando esos hilos terminaron. Así ninguno muere dentro del loader.
- Log: `loader_lock=1 tries=N`. Si no lo consigue en 2 s, lo registra con `loader_lock=0` y sigue como antes.
- El cambio afecta a todos los programas que cierran con hilos propios, no sólo a los de audio.

Entrega: `/data/pkg/orbis-win-W122-bf7dd5d39621.pkg`, con la lectura de vuelta verificada. W121 retirado.

## Resultado físico W122: 20261102T231348Z

- **sound64.exe**: el usuario oyó el tono; `done=1`. Al salir: `loader_lock=1 tries=0`, `other_threads_wait=0 count=2`, y el escritorio siguió respondiendo. El cuelgue de W121 quedó resuelto.
- **sound32.exe** (relanzamiento con wowprospero):
  - `static_unixlib_by_name L"wineps4.drv" wow=1` y `PWAUDIO open … port=536870919`: el driver carga en WoW64.
  - Después `wine: Unimplemented function advapi32.dll.SystemFunction036`. El proceso termina con status 1 y vuelve al escritorio. El usuario no oyó el tono.
- **SuperMarioKart.exe**: pasa ws2_32 y opengl32, carga wined3d y abre el audio (FMOD → dsound → mmdevapi → `PWAUDIO open`). A los 9 s muere en la misma función. Antes hay una excepción C++ que el juego maneja. Todavía no llegó a Direct3D.
- Causa: advapi32 reenvía `SystemFunction036` (RtlGenRandom) a `cryptbase.dll`, que no estaba en el syswow64 sellado (`find_forwarded_export … cryptbase.SystemFunction036`).

# W123 (02.22)

`tools/stage-wine-i386.py` agrega `cryptbase` i386, sin parte Unix, a syswow64 y a `lib/wine/i386-windows`. Entrega: `/data/pkg/orbis-win-W123-33a385d0516e.pkg`, con la lectura de vuelta verificada. W122 retirado.

## Resultado físico W123: 20261102T232033Z

- **sound32.exe**: WoW64 + `PWAUDIO open … port=536870919` y `process_exit status=0` (antes terminaba con 1). Ya no aparece `Unimplemented function`. El sink registra el nivel cada ~5 s y el tono dura 2 s, así que el log no dice si sonó: falta la confirmación del usuario.
- **SuperMarioKart.exe**:
  - Corre 6,6 s y abre el audio (dsound → mmdevapi → `PWAUDIO open`).
  - Lanza una excepción C++ (`e06d7363`) desde el runtime de Blitz. Después cierra solo y limpio: `process_exit method=exit status=0`, con todos los DLL_PROCESS_DETACH, y vuelve al escritorio.
  - No hay `Unimplemented` ni fallo de ntdll. Es la forma en que Blitz informa un error de su runtime (falta lo que muestre el diálogo). Lo más probable es que no consiga modo gráfico Direct3D 7: wined3d no tiene contexto GL (`wgl:internal_context_create Failed`). Eso es la fase 4b.

**Fase 3 aceptada.** El usuario confirmó que oyó el tono de sound32.exe (32 bits, WoW64) además del de sound64.exe. El audio de Windows (winmm → mmdevapi → wineps4 → AudioOut) funciona en 32 y 64 bits en la PS4. No se midieron la latencia, varias fuentes a la vez ni DirectSound directo (SuperMarioKart abre dsound pero termina antes de reproducir).
