# Wxxx: Pale Moon como invitado, segunda ronda de diagnóstico (borrador)

[English](HARDWARE_Wxxx-palemoon-invitado-2-borrador.md) | [Español](HARDWARE_Wxxx-palemoon-invitado-2-borrador-es.md)

Borrador de la sesión lateral del navegador. Sigue a `HARDWARE_Wxxx-palemoon-invitado-borrador.md` (W198). La sesión principal asigna el número. Nada de esto se probó en la consola.

## Qué mostró W199

Reporte: `reports/wine-hardware-w199/physical/20261104T123309Z/run-0001.log`. `palemooncopy.exe` abre en la línea 4581.

- **Las líneas de diagnóstico de W198:**
  - `PWDUMP begin age_ms=8233 loader_owner=0198 loader_count=0` (línea 5886) es la última línea de un hilo de Wine.
  - No hay ninguna línea `PWLOCK`.
- **Después:** sólo escriben el compositor (`PWSINK show_stats`) y RADV (`radv/ps4: submit 4000`). La pantalla se sigue componiendo; lo que se detuvo son los hilos de Windows.
- **El loader lock:** lo tiene el hilo `0198` de Pale Moon. `LockCount` en 0 quiere decir que nadie más lo espera, así que el hilo de interfaz de explorer (`0024`) no está trabado en el loader lock.
- **Dónde se trabó el volcado:** después de `begin`, el paso siguiente es `CreateToolhelp32Snapshot`. Esa llamada necesita el wineserver: `OpenProcess`, `ReadProcessMemory` y `NtQuerySystemInformation`. No volvió.
- **Por qué el observador no lo mostraba:** las llamadas que hace en cada vuelta (`GetGUIThreadInfo`, `GetForegroundWindow`) leen la memoria compartida de win32u (`get_shared_input`) y no le piden nada al servidor. Por eso sus líneas no decían si el servidor seguía respondiendo.
- **W198:** sus volcados sí terminaron, pero con `PWDUMP modules unavailable error=5`. `OpenProcess` del propio proceso devolvió acceso denegado. Sin módulos, cada pila se cortó en el marco 0.

**Hipótesis, sin confirmar:** el wineserver, que en OrbisDesk es un hilo del mismo título, quedó detenido. Eso explica:
- que todo hilo que le pide algo se quede esperando (el hilo de interfaz de explorer en su próxima llamada, todos los de Pale Moon, el volcado);
- que no aparezca el aviso de 60 s de una sección crítica;
- que el compositor, que no usa el servidor, siga andando.

**Descartado:**
- **Las señales de suspensión de W195:** W192, que no tenía señales a hilos, se congeló igual.
- **Un socket bloqueante:** los sockets son no bloqueantes con `SO_NBIO` desde la fase 8.

No se sabe qué detiene al servidor.

## Cambio (diagnóstico, segunda ronda)

`diag-freeze-2.patch.py` cambia `tools/build-wine-delete-server.py` y `tools/build-explorer-hw.py`, con los cambios de W198 ya aplicados. Sólo agrega trazas: nada recupera el cuelgue, acorta una espera ni se salta un lock.

- **servidor (`PWSERVER`):** un hilo vigía dentro del servidor (`server/fd.c`) informa un paso del bucle principal que lleva más de 5 s. Un paso es:
  - un evento de un fd (los pedidos de los hilos llegan así);
  - un temporizador.
  
  Para cada uno registra el tipo, la función, el fd Unix y el evento. Si es un pedido, también el hilo cliente y el número de pedido (`enum request` de `include/wine/server_protocol.h`).
  - Repite el aviso a los 20 s y cada 60 s.
  - Registra `PWSERVER resumed` cuando el paso termina.
  - Escribe con `write(2)` desde un búfer en la pila, sin el lock de stdio.
  - Al arrancar registra `PWSERVER watch rc=0`.
- **explorer (`PWDUMP`):** ya no usa toolhelp para los módulos. Para cada dirección, saca la imagen de sus propios encabezados (`VirtualQuery` y el nombre de exportación), sin el loader lock. Antes de la primera llamada al servidor registra `PWDUMP step=thread_list`.

## Construcción

1. `tools/build-wine-delete-server.py` y `tools/build-explorer-hw.py` ya tienen los cambios (aplicados con `diag-freeze-2.patch.py`).
2. Correr esos dos builders y después `tools/link-wine-boot.py` y `tools/build-wine-hardware.py`.

## Prueba física

1. Al arrancar, el log tiene que mostrar `PWSERVER watch rc=0`.
2. Abrir `palemooncopy.exe` y navegar hasta que se congele. Esperar 2 minutos.
3. **Qué buscar en el log:**
   - `PWSERVER stuck_s=… kind=… func=… unix_fd=… client=… req=…`: qué hace el servidor;
   - `PWDUMP step=thread_list`: si el volcado llegó a su primera llamada al servidor.
4. **El nombre de la función de `func`:** `wine.elf` conserva los símbolos del servidor, también los estáticos (en W200: `thread_poll_event`, `sock_poll_event`, `pwserver_main_loop`). La línea también trae `watch=`, la dirección del propio vigía (`pw_server_watch`). Para ubicar `func` en `llvm-nm-14 wine.elf`, se usa la diferencia entre las dos direcciones, por si el ELF se cargó en otra base.

## No verificado

- Nada se probó en la consola.
- Los dos cambios se compilaron sólo con `-fsyntax-only`, con la receta de cada builder, sobre copias. Los builders no se corrieron.
- Si el servidor se detiene fuera de un paso (por ejemplo, dentro de `kevent`), el vigía no avisa nada. En ese caso, la falta de líneas `PWSERVER stuck` también es un dato.
