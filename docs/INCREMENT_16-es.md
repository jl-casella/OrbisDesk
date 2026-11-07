# Incremento 16: console32-bare.exe sin Wine

[English](INCREMENT_16.md) | [Español](INCREMENT_16-es.md)

**console32-bare.exe se ejecuta completo en el fork Linux de shadPS4 con el loader PE32 propio y un kernel32 mínimo, sin Wine.** Escribe `result.txt` con el mismo contenido que la referencia de Windows y sale con 0. No es Windows ni Wine: es un subconjunto acotado de kernel32 sobre los adaptadores PS4. Hardware: pendiente.

## kernel32 sintético

`platform/ps4/pw_k32_ps4.c` registra una imagen `kernel32.dll` en la lista explícita de módulos que usa `pw_pe32_link` (`pw_pe32_tables.c`). No tiene cabeceras PE: es una página de sólo lectura con trece ranuras de 16 bytes llenas de `HLT`, una por export. La vista de fuente del traductor devuelve `PW_ERR_NOT_FOUND` en esa página, así que ningún bloque se traduce allí. Cuando el EIP llega a una ranura, el bucle de ejecución sale al host y atiende la llamada con `pw_guest_call` (stdcall), la misma frontera de `pw_guest_call`/`pw_guest_callback` que usa el lifecycle del incremento 7. `pw_guest_call_finish` comprueba que EBX, EBP, ESI y EDI no cambien, desapila los argumentos y vuelve a la dirección de retorno.

| Función | Adaptador |
|---|---|
| CreateFileA, WriteFile, CloseHandle | `open`/`write`/`close` bajo `/data/orbis-win/console-bare`, como la prueba `files` |
| CreateThread | pthread del host con su propio `PwPs4Cpu`, pila de 64 KiB y TEB de `pw_pe32_thread_create` |
| WaitForSingleObject, GetExitCodeThread | condición del proceso; `pthread_cond_timedwait` para plazos finitos |
| LoadLibraryA, GetProcAddress, FreeLibrary | módulos ya cargados y sus exports (`PwPe32Info.exports`) |
| GetCurrentProcessId | `getpid` |
| GetLastError, SetLastError | `LastErrorValue` en TEB+0x34 del hilo |
| ExitProcess | detiene todos los hilos invitados y entrega el código al ELF |

El hilo principal se crea con `pw_pe32_lifecycle_create` + `pw_pe32_process_attach`, y cada hilo nuevo con `pw_pe32_thread_create` + `pw_pe32_thread_attach`. Cada uno tiene su TEB y su bloque TLS. El hilo nuevo hereda la tabla de regiones del creador (menos su TEB); así puede escribir en la pila del hilo principal, como hace el EXE.

Los argumentos que el kernel32 no sirve fallan con un error Win32 y una línea `PWK32` con `refused`. Ejemplos: rutas no planas, `SECURITY_ATTRIBUTES`, plantillas, atributos distintos de `FILE_ATTRIBUTE_NORMAL`, E/S solapada, `CREATE_SUSPENDED`, pilas de más de 64 KiB y DLL que no están precargadas. Nunca se devuelve un éxito simulado; el contador `refused` del detalle los suma.

Límites conocidos:

- `LoadLibraryA` sólo resuelve módulos ya cargados (`kernel32.dll` y el EXE). Cargar una DLL desde disco devuelve `ERROR_MOD_NOT_FOUND`. Ambos módulos quedan fijados durante el proceso, así que `FreeLibrary` sólo mueve el contador.
- Los modos de compartición de `CreateFileA` se aceptan, pero no se aplican.
- No hay PEB, SEH, heap ni handles de consola. Una falla de un hilo termina el proceso con `0xc0000005` y una línea `fault`.
- `ExitProcess` en otro hilo detiene a los demás en su siguiente llamada a kernel32. Si un hilo está sólo en código invitado, se detiene al agotar el presupuesto de pasos.
- El EXE se carga reubicado en `0x30000000` (base preferida `0x400000`, 14 relocaciones HIGHLOW). Tiene `DYNAMIC_BASE`, igual que lo trataría el ASLR de Windows.

## Caso console-bare

`native/pe32_probe.c` agrega `probe_console`, que se ejecuta con `--case console-bare`. El runner copia `console32-bare.exe` y la referencia `reports/increment11-windows-reference/result.txt` a `/data`. Antes, comprueba que el EXE tenga el hash de esa referencia (`83bd9d59…`). La prueba exige:

- salida por `ExitProcess` con código 0;
- `result.txt` idéntico byte a byte a la referencia;
- un hilo creado y ninguna falla de hilo;
- ningún rechazo y ningún handle sin cerrar;
- conteo exacto de llamadas por función;
- ninguna reserva de memoria viva al final.

El conteo es CloseHandle ×2; CreateFileA, CreateThread, WaitForSingleObject, GetExitCodeThread, LoadLibraryA, GetProcAddress, FreeLibrary, WriteFile y ExitProcess ×1. `GetCurrentProcessId` sólo se resuelve; no se llama. `run-linux-wine.py` y `run-probes.ps1` comparan además el archivo desde el host. `tools/build.py` compila `pw_k32_ps4.c` y genera `console32-bare.exe` con `tools/build-console-bare.py`. El binario es reproducible: el hash sigue igual.

## Resultados

| Entorno, mismo ELF |consola-bare| Motivo |
|---|---|---|
|Presión Linux `bf96b33`|**passed**| `result.txt` igual a Windows, salida 0, sin stubs |
|shadPS4 oficial Linux v0.20.0|bloqueado| El invitado pasa y el archivo coincide; el emulador cae en `process.cpp:312 exit: Unreachable code!` al salir con 0 y agota el timeout. `files` hace lo mismo |
|shadPS4 oficial Windows v0.20.0|bloqueado| El primer `sceKernelMprotect` RW→RX del JIT llega a `address_space.cpp:603 Protect: Unreachable code!`, como los casos del traductor desde el incremento 2 |

Detalle en el fork: `steps=23` cuenta pasos del dispatcher, no instrucciones. GCC pliega la suma 1..1000 a la constante `0x7a314`, así que el hilo sólo la escribe en la pila del hilo principal. El cálculo del EXE no ejercita un bucle traducido; sí lo hacen los incrementos 3–7.

`check-increment16.py` repite las regresiones del incremento 15 en el fork. Pasan files, threads-adapter, pe-dll-relocated, vm-stress, ipc, pipes, filesystem y metadata. No se agregó ningún parche al emulador.

## Reproducción y evidencia

```sh
python3 tools/build.py --with-wine-platform
python3 tools/run-linux-wine.py --fork --baseline --case console-bare
python3 tools/check-increment16.py
python3 tools/check-increment16.py --verify-only
```

En PowerShell, con el binario oficial de Windows:

```powershell
./tools/run-probes.ps1 -Cases console-bare,files -TimeoutSeconds 25
```

`reports/increment16/report.json` indexa las corridas: fork y oficial Linux por separado, más las ocho regresiones. Incluye también la traza `PWK32` y los hashes del ELF y del emulador. El informe oficial de Windows queda en `reports/runs/20261030T202259693Z/`. Hardware: pendiente.

## Próximo hito

Ampliar el kernel32 mínimo sólo con lo que pida el siguiente EXE real: heap, consola, `GetModuleHandle` y carga de DLL desde disco con el lifecycle del incremento 7. La pista Wine sigue en paralelo: montar el prefijo del incremento 15 y definir su política de arranque.
