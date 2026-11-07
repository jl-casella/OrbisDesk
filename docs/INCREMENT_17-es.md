# Incremento 17: carga de DLL desde disco sin Wine

[English](INCREMENT_17.md) | [Español](INCREMENT_17-es.md)

**lifecycle-host.exe se ejecuta completo en el fork Linux de shadPS4 sin Wine.** Carga `lifecycle.dll` desde `/data` y corre su `DllMain` y su callback TLS. Crea un hilo que recibe DLL_THREAD_ATTACH/DETACH y descarga la DLL con DLL_PROCESS_DETACH. Comprueba que `lifecycle-fail.dll` falle con `ERROR_DLL_INIT_FAILED` y sale con 42, igual que en Windows nativo. Sigue siendo un kernel32 mínimo, no Windows. Hardware: pendiente.

## Referencia de Windows

`reports/increment17-windows-reference/report.json` registra la ejecución nativa en este host (Windows 11 Pro 10.0.26200): `lifecycle-host.exe` desde un directorio con las tres DLL sale con 42. El informe guarda el hash de los cuatro binarios. Los runners comparan esos hashes con los archivos copiados a `/data` antes de dar por válida una corrida. El EXE verifica por sí mismo el orden de los ocho eventos de `lifecycle.dll` (0x11, 0x21, 0x12, 0x22, 0x13, 0x23, 0x10, 0x20), y sólo así devuelve 42.

## Lifecycle dinámico

`platform/ps4/pw_pe32_lifecycle.c` dejaba fija la lista de imágenes al crearse. Ahora:

- Cada región de hilo reserva un bloque TLS para cada una de las `PW_PE32_MAX_MODULES` ranuras: `(2+8)` páginas de 16 KiB. Así, un módulo cargado después recibe un bloque en todos los hilos vivos sin mover el TEB.
- El lifecycle lleva un registro de hilos vivos. Por eso un `PwPe32Thread` debe mantener su dirección entre create y destroy.
- `pw_pe32_lifecycle_load` asigna la ranura libre como índice TLS, instala el bloque con su plantilla en cada hilo y ejecuta PROCESS_ATTACH en el hilo llamador. Si `DllMain` devuelve FALSE, ejecuta PROCESS_DETACH, libera la ranura y devuelve `PW_PE32_INIT_FAILED`.
- `pw_pe32_lifecycle_unload` ejecuta PROCESS_DETACH y libera la ranura. Ninguna de las dos funciones desmapea la imagen.
- `pw_pe32_lifecycle_set_runner` reemplaza la ejecución acotada de las notificaciones. El kernel32 la usa para que el código de `DllMain` pueda llamar a sus funciones.

Los cinco casos del incremento 7 (`pe-init-*`, `pe-tls-*`) siguen pasando sin cambios.

## kernel32

`platform/ps4/pw_k32_ps4.c` pasa de 13 a 15 exports:

- **`LoadLibraryA`:** si la DLL no está cargada, lee `/data/<nombre>.dll` (nombre plano en minúsculas) y la carga con `pw_pe32_load` en su base preferida. Si la base está ocupada, la reubica en `0x34000000`, `0x35000000`… Después la enlaza contra los módulos cargados con `pw_pe32_link` y llama a `pw_pe32_lifecycle_load`.
- **`FreeLibrary`:** si el contador llega a cero, llama a `pw_pe32_lifecycle_unload` y desmapea la DLL. kernel32 y el EXE siguen fijados.
- **`GetCurrentProcess`:** devuelve el pseudo-handle `0xffffffff`.
- **`TerminateProcess`:** sólo acepta ese pseudo-handle y sale como `ExitProcess`. Con cualquier otro handle rechaza la llamada.

La lista de módulos es dinámica. Cada hilo reconstruye la parte de módulos de su tabla de regiones cuando cambia un contador de generación. Lo hace antes de su siguiente paso, siempre en su propio hilo, así que nunca se modifica el estado de otra CPU. La vista de fuente recorre la lista bajo el mutex del proceso.

Límites conocidos, también registrados en el informe:

- Una DLL sólo puede importar de módulos sin imports propios: es la regla de `pw_pe32_link` (hoy, kernel32).
- `LoadLibraryA`, `FreeLibrary` y `CreateThread` desde una notificación de DLL se rechazan con `refused`. El lifecycle no es reentrante, a diferencia del loader lock de Windows.
- Descargar una DLL no invalida los bloques ya traducidos de su rango. Si otro hilo sigue ejecutándola, o si se carga otro código en la misma dirección, el resultado queda indefinido.
- Al salir, las DLL que siguen cargadas reciben PROCESS_DETACH también con `TerminateProcess`. En Windows, `TerminateProcess` no las notifica.

## Resultados

| Entorno, mismo ELF |ciclo de vida anfitrión| Motivo |
|---|---|---|
|Presión Linux `bf96b33`|**passed**| Salida 42, como Windows; 12 notificaciones (8 de `lifecycle.dll`, 4 de la DLL rechazada); sin stubs ni rechazos |
|shadPS4 oficial Linux v0.20.0|bloqueado| El invitado pasa; `process.cpp:312 exit: Unreachable code!` y timeout, como en el incremento 16 |
|shadPS4 oficial Windows v0.20.0|bloqueado| `address_space.cpp:603 Protect: Unreachable code!` al publicar el primer bloque RX |

`console-bare` del incremento 16 sigue pasando, ahora con 15 exports. `check-increment17.py` repite en el fork los cinco casos del incremento 7 y las ocho regresiones del incremento 15: files, threads-adapter, pe-dll-relocated, vm-stress, ipc, pipes, filesystem y metadata. No se agregó ningún parche al emulador.

## Reproducción y evidencia

```sh
python3 tools/build.py --with-wine-platform
python3 tools/run-linux-wine.py --fork --baseline --case lifecycle-host
python3 tools/check-increment17.py
python3 tools/check-increment17.py --verify-only
```

```powershell
./tools/run-probes.ps1 -Cases lifecycle-host -TimeoutSeconds 25
```

`reports/increment17/report.json` indexa las corridas, la traza `PWK32` y el detalle del caso. El informe oficial de Windows está en `reports/runs/20261030T203956399Z/`. Hardware: pendiente.

## Próximo hito

Pasar a `console32.exe`, que usa el CRT de mingw. Importa 26 funciones de `msvcrt.dll` y además critical sections, `TlsGetValue`, `VirtualProtect`, `VirtualQuery`, `GetModuleHandleA`, `GetStartupInfoA`, `Sleep` y `SetUnhandledExceptionFilter`. Requiere un msvcrt mínimo o permitir que una DLL importe de otra con imports. La pista Wine sigue en paralelo.
