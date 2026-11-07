# W205: Pale Moon como invitado se traba al abrir una segunda pestaña (borrador)

[English](HARDWARE_W205-palemoon-pestana-borrador.md) | [Español](HARDWARE_W205-palemoon-pestana-borrador-es.md)

Borrador de la sesión lateral del navegador, para unir a `HARDWARE_W205.md`. Nada de esto se probó en la consola.

## Qué mostró W204

Reporte: `reports/wine-hardware-w204/physical/20261104T135801Z/run-0001.log`. El usuario dijo: "se congeló al abrir una segunda tab".

- **El arreglo de memoria de W204:**
  - no hay ninguna línea `map_fixed_area mmap error`;
  - tampoco hay líneas `PWVM tryfixed_hint`, así que el camino nuevo no hizo falta en esta corrida.
- **El escritorio sigue vivo hasta el final:**
  - el latido de explorer queda en ~216 ms y se siguen presentando cuadros;
  - no hay `PWSERVER`, `PWLOCK` ni `PWDUMP`.
  
  Se traba sólo Pale Moon (hilo principal `0110`, línea 5170).
- **Dos ventanas nuevas:** el hilo `0110` crea dos ventanas de primer nivel, con la misma secuencia (`WTSRegisterSessionNotification`, un `tmpmap` del servidor, `DwmExtendFrameIntoClientArea`):
  - `0x30166` en la línea 6675: después Pale Moon sigue, con decenas de resoluciones de nombres;
  - `0x7012A` en la línea 6879: después ningún hilo de Pale Moon registra nada más.
- **Direct3D 11 sigue activo en Pale Moon** (líneas 5981 a 6400):
  - `VK_KHR_EXTERNAL_MEMORY_WIN32 not supported`;
  - `D3D11DXGIKeyedMutex::AcquireSync: Not supported`;
  - no aparece ningún `PWVK show_frame`;
  - después de `0x7012A` no hay líneas nuevas de DXVK.
  
  La preferencia `layers.acceleration.enabled` sigue en `true` en el perfil por defecto que usa `palemooncopy.exe`.
- **Por qué no hay volcado:** `PWDUMP` sólo corre cuando se detiene el hilo de explorer, así que no corrió.

No se sabe en qué espera el hilo `0110`.

## Prueba sin construir nada (W204)

Como en W197:
1. En `palemooncopy.exe`, ir a `about:config` y poner `layers.acceleration.enabled` en `false`.
2. Reiniciar Pale Moon.
3. Abrir una segunda pestaña.

**Qué buscar en el log:** que no haya líneas de DXVK (`D3D11InternalCreateDevice`).

**Cómo leer el resultado:** si así no se traba, la causa está en el compositor Direct3D 11 de Pale Moon dentro del proceso de explorer. Como título aparte, Pale Moon corre con la aceleración apagada y `d3d11` deshabilitado.

## Cambio (diagnóstico)

`tools/build-explorer-hw.py`, con `hung-window-w205.patch.py`:
- **Qué revisa:** cada 2 s, el observador de explorer busca una ventana visible de primer nivel de otro hilo (no el de explorer) que Wine considera colgada. `IsHungAppWindow` la marca así después de 5 s sin leer mensajes.
- **Cuándo actúa:** cuando lleva 8 s así, y otra vez a los 70 s.
- **Qué registra:** `PWHUNG` con:
  - la ventana, su hilo y cuántas ventanas colgadas hay;
  - la clase;
  - el título, leído con `InternalGetWindowText`, que no manda mensajes.
  
  Después corre el mismo volcado de hilos (`PWDUMP`) que ya existe.
- **Sólo lectura:** no se le manda nada a la ventana colgada y no se recupera nada.

## Construcción

1. `python3 tools/build-explorer-hw.py`.
2. `tools/link-wine-boot.py`.
3. `tools/build-wine-hardware.py`.

## Prueba física

1. Abrir `palemooncopy.exe` y abrir una segunda pestaña.
2. Esperar 2 minutos.
3. **Qué buscar en el log:**
   - `PWHUNG hwnd=… tid=… class=… title=…`;
   - las dos tandas `PWDUMP`. El hilo de `PWHUNG` y sus marcos muestran en qué llamada de Wine está esperando (`win32u`, `ntdll`, `user32`, …), y los otros hilos de Pale Moon, qué hacen.

## No verificado

- Nada se probó en la consola.
- El cambio se compiló sólo con `-fsyntax-only` (mingw), sobre una copia del overlay actual.
- Los marcos dentro de `xul.dll` salen como desplazamientos (`xul.dll+…`); Pale Moon no trae símbolos.
- Si el hilo colgado no responde a `GetThreadContext`, el volcado se detiene en ese hilo.
