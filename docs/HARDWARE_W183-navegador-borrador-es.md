# W183: Pale Moon como título aparte (fase 9, borrador)

[English](HARDWARE_W183-navegador-borrador.md) | [Español](HARDWARE_W183-navegador-borrador-es.md)

Borrador de la sesión lateral del navegador, para unir a `HARDWARE_W183.md`. Base W182. Nada de esto se probó en la consola.

## Qué pasó en W182

Reporte: `reports/wine-hardware-w182/physical/20261103T230134Z/`

1. **El WebView test renderiza** la página local. Dos filas no corren, y es lo esperado:
   - `es2020`: el control de IE ejecuta los scripts con jscript de Wine, que no tiene ES2020.
   - El canvas: el mshtml de Wine no implementa canvas (no hay `getContext` ni `HTMLCanvasElement` en `dlls/mshtml`).

   No tiene que ver con la aceleración, y no es un error de la prueba. El motor de Gecko sólo dibuja; los scripts no pasan por él.
2. **Pale Moon cierra la app** (`run-0002.log`, `run-0003.log`).
   - En las dos corridas se abrió antes el WebView test, que cargó el `mozglue.dll` de Wine Gecko. Gecko no se descarga, así que siguió cargado.
   - Al cargar `palemoon.exe`, su import `mozglue.dll` se resolvió por nombre base al módulo ya cargado. El cargador hace eso con un nombre ya cargado (`find_basename_module`), igual que Windows.
   - Faltaron exports (`No implementation for mozglue.dll.?DllBlocklist_CheckStatus…`, `?Now@TimeStamp…`, `strdup`). La primera llamada abortó (`unimplemented function mozglue.dll.?Now@TimeStamp…`) y cerró todo el título.
   - Gecko y Pale Moon comparten los nombres `mozglue`, `nss3`, `xul`, `lgpllibs`, `freebl3`, `softokn3`, `mozavcodec`, `mozavutil`, `libEGL` y `libGLESv2`. En un mismo proceso funciona sólo el que carga primero, en cualquiera de los dos órdenes.

## Cambio

Pale Moon corre solo, en un relanzamiento del título, como los programas de 32 bits.

| Archivo | Qué hace |
|---|---|
| `tools/build-guest-hw.py` (kernelbase, `process.c`) | `ps4_runs_alone(nombre)` lee `HKCU\Software\Wine\AppDefaults\<exe>` `"OrbisRunsAlone"="Y"`. Un programa de 64 bits marcado así no se carga como invitado (`PWGUEST runs_alone app=…`). En el bloque de W106 sigue el camino de los de 32 bits: un aviso para confirmar y después `NtCreateUserProcess`, que relanza el título con ese programa (`pw_hw_switch_program`). El log dice `PWOPEN runs_alone_relaunch image=… answer=…`. |
| `tools/build-wine-hardware.py` (`user.reg`) | `[Software\Wine\AppDefaults\palemoon.exe]` `"OrbisRunsAlone"="Y"`. |

El aviso dice: "Este programa se ejecuta solo: OrbisDesk se reinicia para abrirlo y al cerrarlo vuelve al escritorio. Se cerrarán los programas abiertos. ¿Continuar?"

**Sin cambios.** `pw_hw_switch_program` (`prepare-wine-boot.py`) relanza cualquier imagen que no sea un ayudante de Wine. El lanzador (`native/wine_hardware.c`) arranca la imagen sola, con WoW64 sólo si es de 32 bits, en su carpeta (`PW_PROGRAM_DIR`), y al salir vuelve al escritorio. Antes de los invitados (W043-W051), los programas de 64 bits corrían así. Los argumentos del acceso directo (`-no-remote -profile "…"`) pasan por `next.txt`, que admite hasta 6 argumentos y respeta las comillas.

**Qué cambia para el usuario:**
- Abrir Pale Moon cierra los programas abiertos.
- Mientras Pale Moon corre no hay escritorio ni barra de tareas.
- Al cerrar Pale Moon vuelve el escritorio.
- Gecko y Pale Moon ya no comparten proceso, así que el orden en que se abren deja de importar.

**Lo que se gana además:**
- Pale Moon no tiene el límite de hilos de los invitados.
- Los ganchos de mozglue en ntdll y un fallo de Pale Moon no afectan a explorer.
- Más adelante, al tener su propio proceso, Pale Moon podría usar el dxgi/D3D11 de DXVK. No se hizo en W183.

**Registro en la consola.** La fusión de `user.reg` al subir (W172) conserva los bloques AppDefaults de la consola y agrega los que sólo están en el build. Si la consola ya tiene un bloque `AppDefaults\palemoon.exe` (por ejemplo, creado desde winecfg), queda el de la consola y `OrbisRunsAlone` no llega. Después de subir, el registro de la transferencia (bloques conservados) tiene que mostrar el bloque nuevo.

## Verificación sin consola

- `build-guest-hw.py` y `build-wine-hardware.py` compilan como Python.
- Repetí las revisiones de `build-guest-hw.py` en una copia (sin `make` y sin escribir en `build/` ni en `out/`). El `process.c` revisado de kernelbase compila con el comando exacto del árbol (`compile_commands.json`) y termina con 0.
- El único aviso (`wcstoul` sin declarar) es del código de W060, que ya estaba.

## Construcción (orden)

1. `python3 tools/build-guest-hw.py` (recompila kernelbase y ntdll de invitados)
2. `python3 tools/build-wine-hardware.py`
3. `python3 -I tools/check-web-closure.py build/wine-hardware-w183/runtime`: tiene que terminar con 0.

## Prueba física

1. **WebView test (64-bit):** sigue funcionando como invitado.
2. **Pale Moon desde el menú Start** (con la copia del usuario en `C:\Program Files\Pale Moon`):
   - Tiene que aparecer el aviso.
   - Al aceptar, el título se reinicia y abre Pale Moon solo. El log tiene que mostrar `PWOPEN runs_alone_relaunch … answer=1` y, en la corrida siguiente, `switch_program image=…palemoon.exe`.
   - Se espera la página local con `es5-ok`, `es2020-ok` y `canvas-ok`.
   - Al cerrar Pale Moon, tiene que volver el escritorio.
3. **El orden inverso:** abrir Pale Moon primero, cerrarlo y después abrir el WebView test. Los dos tienen que funcionar.
4. **Si Pale Moon falla en su propio proceso:** buscar `map_view anon mmap error` (la reserva de 1 GB que la sesión principal arregla en `virtual.c`) y repetir con "Pale Moon (no JIT)".

## No verificado

- Nada se probó en la consola.
- No se probó un relanzamiento de 64 bits desde W052 (los de 32 bits sí, desde W116).
