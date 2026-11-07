# Incremento 23: console32-bare.exe mediante Wine, con el traductor como CPU WoW64

[English](INCREMENT_23.md) | [Español](INCREMENT_23-es.md)

**En el fork Linux de shadPS4, `console32-bare.exe` se ejecuta mediante Wine.** Wine carga sus módulos reales (ntdll de 64 y 32 bits, `kernelbase.dll` y `kernel32.dll`) y ejecuta el código de 32 bits con el traductor IA-32 de prospero-win como proveedor de CPU WoW64. El programa:

- crea su hilo;
- carga su DLL;
- escribe `C:\orbis\result.txt`, idéntico byte a byte al de Windows nativo;
- venta con 0.

Pasa en tres corridas seguidas. En shadPS4 oficial sigue bloqueado. Hardware: pendiente.

No se usan los módulos sintéticos de los incrementos 16 a 18: todo pasa por Wine.

## Proveedor WoW64: wowprospero para PS4

El incremento 22 terminaba con `0xc0000135` porque faltaba el proveedor de CPU WoW64. Se adapta `wowprospero` de prospero-win (LGPL-2.1-or-later), el backend `BTCpu*` que ejecuta el código i386 con el traductor. `tools/build-wowprospero-ps4.py` construye tres piezas y registra el hash original y el adaptado de cada fuente:

- **Parte Unix**: `unix.c` y el DBT (`pw_x86_engine`, `block`, `cache`, `hostexec`, `reencode`, `x87`, `guest_fp`, `vm`) compilados para Orbis. La única adaptación de `unix.c` es leer RIP y RSP del contexto de señal con el layout FreeBSD que usa Orbis (el mismo de PS5). Se enlazan dentro del ELF de Wine. No hay `dlopen`: ntdll encuentra la tabla `__wine_unix_call_funcs` del módulo por el nombre de su `.so`, en `platform/ps4/pw_wine_unixlibs.c` (`PWBOOT static_unixlib`).
- **`wowprospero.dll`** (PE de 64 bits), enlazado como lo hace prospero-win, contra el árbol de Wine del host fijado.
- **`wow64.dll`** con la selección del proveedor por entorno, adaptada del parche 0611 de prospero-win: `WINE_PS4_WOW64_CPU` sólo acepta `wowprospero.dll`. Si no puede cargarlo, usa la elección del prefijo.

El runner lo activa con `--wow64-cpu wowprospero`. Copia los dos PE verificados por hash y, después de verificar el paquete del prefijo, instala `wowprospero.dll` en `system32` del prefijo extraído, como prospero-win lo instala en PS5. Fuera del bootstrap, Wine sólo carga un builtin a través de un archivo de `system32`. El paquete del prefijo no cambia, y sigue sin incluir el `wow64cpu.dll` de hardware del host.

## Bloqueos resueltos en el camino

Cada uno se resolvió con una prueba y una corrección explícita.

1. **Pila alternativa de señales inexistente (fork 0014)**. Todo hilo empezaba con `sigaltstack` en cero y sin `SS_DISABLE`. Desde el incremento 22, los handlers de Wine llegan con `SA_ONSTACK`, así que el fork saltaba a una pila en la dirección 0 y el emulador caía con SIGSEGV. Ahora los hilos empiezan con `SS_DISABLE`, como en FreeBSD.
2. **`stack_t` sin traducir (plataforma)**. Wine instala su pila de señales con el `stack_t` del SDK: layout de Linux y `SS_DISABLE=2`. libkernel espera el de FreeBSD: `ss_size` antes de `ss_flags` y `SS_DISABLE=4`. `pw_wine_sigaltstack` lo traduce.
3. **SS en el contexto de señal (fork 0015)**. Wine compara el SS guardado con su selector de datos para reconocer código de 16 bits. Con SS en 0 trataba el fallo como de 16 bits y leía un TEB de WoW64 nulo. Ahora se informan SS (del contexto de Linux si el kernel lo guarda; si no, el actual), DS y ES.
4. **Reservas sin memoria (plataforma)**. Wine reserva con `PROT_NONE` y luego hace el commit cambiando la protección. En Orbis, y en el PS4 real, una reserva no tiene memoria y el kernel ignora la protección sobre ella. El arena de código del traductor quedaba vacío y el primer bloque fallaba al ejecutarse. `pw_wine_memory_protect` mapea memoria flexible fija sobre las partes todavía no comprometidas, igual que `pw_wine_anon_tryfixed` con las vistas nuevas.
5. **`madvise` stub (fork 0016)**. El `free` de la libc del título llama a `madvise` con `MADV_DONTNEED`. En FreeBSD esos consejos (hasta `MADV_CORE`) sólo orientan al pager y conservan el contenido. El fork valida rango y consejo y devuelve éxito sin pedirle nada al host, cuyo `MADV_DONTNEED` borraría páginas anónimas. `MADV_PROTECT` devuelve EPERM; un consejo desconocido, EINVAL. Antes la corrida tenía este stub invocado y por eso no contaba como aprobada.

Para diagnosticar se agregaron al runner `--winedebug` y `--wineenv`. Sólo sirven para diagnóstico, quedan registrados en el informe, y el verificador rechaza cualquier corrida que los use. Los volcados de las caídas los produjo el `core_pattern` de WSL (`/wsl-capture-crash`, en `%LOCALAPPDATA%\Temp\wsl-crashes`). De ahí salieron los registros y la señal de cada caída.

## Pruebas

- `--signal-services` pasa de 5 a 7 casos: `SA_ONSTACK` sin pila alternativa (con `SS_DISABLE` informado) y una pila instalada con el `stack_t` del SDK, en la que debe correr el handler. El caso de lectura exige además que CS, SS y DS coincidan con los del hilo.
- `wine-memory` pasa de 7 a 10 comprobaciones:
  - una reserva comprometida por protección ejecuta código;
  - `MADV_DONTNEED` conserva el contenido;
  - un consejo inválido devuelve EINVAL.
- El intento con prefijo preparado compara ahora `result.txt` con `reports/increment11-windows-reference/` (contenido, hash del EXE y salida). `Wine_booted` y `windows_execution_verified` sólo pasan a true si todo coincide, el proceso sale con 0, no hay timeout ni violaciones de acceso y no se invocó ningún stub.

| Entorno | console32-bare.exe mediante Wine |
|---|---|
| Fork Linux, `--wow64-cpu wowprospero` | **passed**, 3 de 3: `result.txt` idéntico, salida 0, sin stubs |
| Fork Linux sin proveedor | `0xc0000135` (`load_64bit_module`), como en el incremento 22 |
|shadPS4 oficial Linux v0.20.0| blocked: `readlink` es stub en el preflight del prefijo y vence el timeout |

## Validación

`tools/check-increment23.py` exigencia:

- las tres corridas aprobadas contra la referencia de Windows;
- los hashes de los PE preparados (ntdll de 64 y 32 bits, `wow64.dll`, `wowprospero.dll`);
- que ningún `wow64cpu.dll` entre en el paquete de ejecución;
- que no reaparezcan los bloqueos anteriores;
- el control sin proveedor y la comparación oficial;
- GS, señales, `wine-memory`, `segments`, `services`, el preflight y el prefijo vacío;
- `exceptions` con la misma línea en fork y oficial;
- los contratos de mmap y file mapping, y la matriz del incremento 18.

Todo queda en `reports/increment23/`. `fork.lock.json` fija el commit `7b9f902` con los parches 0001 a 0016.

## Reproducción

En Ubuntu 22.04/WSL, en este orden: `build.py` regenera el overlay sin boot, así que `prepare-wine-boot.py` va después.

```sh
python3 tools/build-shad-linux.py --reuse-configure --jobs 12
python3 tools/build.py --with-wine-platform
python3 tools/prepare-wine-boot.py
python3 tools/build-wine-ps4.py --boot --all-unix
python3 tools/build-wine-ps4.py --boot --server
python3 tools/build-wowprospero-ps4.py
python3 tools/link-wine-boot.py
python3 tools/run-linux-wine.py --fork --prepared-prefix reports/increment15/prefix-package --wow64-cpu wowprospero
python3 tools/check-increment23.py
python3 tools/check-increment23.py --verify-only
```

## Qué no está probado

- `console32.exe` (con el CRT de mingw) mediante Wine. El paquete del prefijo sólo trae `console32-bare.exe`.
- shadPS4 oficial, el host Windows del fork y el hardware PS4.
- Excepciones del invitado de 32 bits (SEH) y escrituras sobre código traducido. Este programa no las ejercita.
- Gráficos, entrada y audio.

## Próximo hito

1. `console32.exe` mediante Wine, con un paquete de prefijo que lo incluya y el mismo contrato de Windows.
2. Excepciones de 32 bits y código automodificable bajo wowprospero, con pruebas propias.
3. Investigar `dispatcher-mixed` y `exceptions` en Linux, y el bloqueo del oficial.
