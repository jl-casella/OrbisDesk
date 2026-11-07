# Incremento 22: GS por hilo, contextos de señal y arranque de Windows hasta WoW64

[English](INCREMENT_22.md) | [Español](INCREMENT_22-es.md)

**En el fork Linux, Wine ya instala su GS, maneja sus fallos de página y ejecuta el ntdll PE de 64 bits: crea el heap del proceso y carga `wow64.dll`. El arranque se detiene limpio con `STATUS_DLL_NOT_FOUND` (`0xc0000135`) porque falta el proveedor de CPU WoW64 (`wow64cpu.dll`). El EXE todavía no se ejecuta mediante Wine.** Hardware: pendiente.

El incremento 21 se detenía con la salida 93: `sysarch` no instalaba GS. Al resolverlo aparecieron, uno detrás de otro, otros cuatro bloqueos. Cada uno tiene su prueba y su corrección.

## 1. GS libre para el invitado (parches 0011 y 0012 del fork)

En Linux, shadPS4 guardaba el TCB del invitado en la base GS del hilo (`tls.cpp`, `arch_prctl(ARCH_SET_GS)`) y reescribía las lecturas `fs:` del TCB como lecturas `gs:` (`cpu_patches.cpp`). Si un invitado instalaba su propio GS (Wine instala el TEB), todo acceso TLS parcheado del ELF pasaba a leer el TEB. Implementar `sysarch` sobre ese diseño habría roto el TLS nativo.

- **0011**: el puntero al TCB pasa a un `thread_local` del host, con un offset fijo respecto del thread pointer de FS. Las lecturas, comparaciones y XOR del TCB se generan con la misma forma que en Windows, mediante un trampolín: cargar el puntero desde `fs:[offset]` y, si hace falta, el campo. En Linux el parcheo AOT emite esos trampolines y, si no hay espacio, la ejecución falla con una aserción explícita en lugar de dejar una lectura sin parchear. Cada hilo comprueba que el offset sea el mismo. GS queda libre, como en la consola, donde el TLS va por FS.
- **0012**: `sysarch` (`b7uXQmnfB2s`). `AMD64_GET_FSBASE` devuelve el TCB; `AMD64_GET_GSBASE` y `AMD64_SET_GSBASE` usan la base GS del hilo del host. `AMD64_SET_FSBASE` y las operaciones desconocidas devuelven EINVAL; en otros hosts, ENOSYS. Si falla, no se modifica el parámetro de salida.

Es un cambio del emulador para cualquier título en Linux, no una excepción para Wine. En el host Windows GS es el TEB del propio proceso; no se modificó ni se valida allí.

`native/wine_gs_probe.c` (`--gs-services`) agrega el caso `gs-fsbase-contract` (FSBASE igual al TCB visto por `fs:0`, SET_FSBASE rechazado sin tocar la salida) al caso existente: lecturas reales `gs:0`/`gs:8` en el hilo principal y en dos hilos, `__thread` nativo preservado y restauración de la base. Pasa en el fork; en el oficial sigue bloqueado por el stub de `sysarch`. `segments`, bloqueado desde la referencia inicial por el mismo stub, también pasa en el fork.

## 2. Contexto completo en los handlers de señal (parche 0013 del fork)

Con GS instalado, Wine registraba `segv_handler Got unexpected trap 0`. El fork reenviaba los fallos al handler del invitado con un `ucontext` Orbis incompleto:

- sin `mc_trapno`, `mc_err`, `rflags` ni estado FPU, y sin bases FS/GS;
- con `si_addr` igual al RIP en lugar de la dirección del fallo.

Wine en Orbis se compila con las definiciones FreeBSD: clasifica el fallo por el código `T_*` y por el código de error. Con `trapno` 0, un fallo de página no pasaba por `virtual_handle_fault` (páginas de guarda, crecimiento de pila) y se convertía en instrucción ilegal.

**0013** traduce el vector de Linux al código `T_*` de FreeBSD, copia el código de error, `RFLAGS`, `CS`, el área FXSAVE (`mc_fpformat` XMM) y las bases FS/GS, y al volver del handler escribe `RFLAGS` y el estado FPU en el contexto del host. Para SIGSEGV y SIGBUS, `si_addr` conserva la dirección del fallo.

## 3. Traducción de señales en la plataforma propia

La misma prueba mostró un defecto nuestro, no del emulador. Los headers del SDK toman números de señal, `SA_*` y `SIG_*` del `bits/signal.h` de musl (Linux), pero `sigaction` y `sigprocmask` de libkernel implementan el ABI FreeBSD. `platform/ps4/pw_wine_signals.c` pasaba esos valores sin traducir:

- `SA_SIGINFO` de musl (4) es `SA_RESETHAND` en FreeBSD: el handler de Wine se perdía después del primer fallo, sin `SA_ONSTACK` ni `SA_RESTART`;
- `SIG_UNBLOCK` de musl (1) es `SIG_BLOCK` en FreeBSD: desbloquear bloqueaba;
- SIGBUS, SIGUSR1, SIGUSR2, SIGSYS y otras tienen otros números.

Ahora se traducen señales (incluidas las de tiempo real), flags, máscaras y la operación; un valor sin equivalente devuelve EINVAL. El handler se instala detrás de un trampolín que le entrega el número de señal de musl. El `siginfo_t` del SDK ya tiene el layout FreeBSD.

`native/wine_signal_probe.c` (`--signal-services`) comprueba en el fork:

|Caso| Qué exige |
|---|---|
| `signal-read-page-fault` | `T_PAGEFLT`, bit de escritura apagado, dirección del fallo, `RFLAGS`, FSBASE y GSBASE |
| `signal-write-page-fault` | `T_PAGEFLT` con bit de escritura y reanudación de la escritura |
| `signal-fpu-state-read` | formato XMM y MXCSR del hilo (bits de control) |
| `signal-fpu-state-write` | un MXCSR editado en el handler queda activo al volver |
| `signal-mask-translation` | bloquear y desbloquear SIGUSR1 y SIGBUS por la máscara del hilo |

En el fork pasan los cinco. En el oficial no pasa.

## 4. Imágenes de 64 bits reubicadas a una dirección inexistente

El wineserver asigna a las DLL de 64 bits una base dinámica entre `0x600000000000` y `0x700000000000`. En el fork Linux el espacio de usuario termina en `0x54FFFFFFFFFF`, así que `map_image_view` mapeaba ntdll en otra dirección (`0x7fc70000`), pero `map_image_into_view` lo reubicaba igual hacia `0x6fffffd00000`. Sus punteros absolutos apuntaban a memoria inexistente.

La revisión del overlay (`tools/prepare-wine-boot.py`, parche `0003-ps4-static-server-and-paths.patch`) usa como base de reubicación la dirección donde realmente quedó la vista y lo registra como `PWBOOT image_map_addr_unavailable`. La política de rangos del servidor no se cambió.

## 5. KUSER_SHARED_DATA sin inicializar

Sin wineboot, `RtlCreateHeap` devolvía nulo y Wine reportaba `unsafe_heap_from_handle Invalid handle 0`. `virtual_init_user_shared_data`, que entre otras cosas pone `SystemCall = 1`, sólo se llama desde `run_wineboot`, y la política del prefijo externo (incremento 19) lo salteaba entero. Con el servidor dentro del proceso, cada ejecución crea un USD nuevo. Sin ese bit, el stub de syscall del ntdll PE ejecutaba la instrucción `syscall` contra Linux en lugar de saltar al dispatcher de Wine: `NtAllocateVirtualMemory` (id 0x18) terminaba como `sched_yield`, que devuelve 0 sin memoria.

La rama del prefijo externo inicializa ahora esa parte del USD y lo registra (`PWBOOT user_shared_data_ready system_call=1`). La parte que llena `wineboot.exe` del lado PE (características del procesador, versión) sigue sin hacerse.

## Resultado de Wine

Con el prefijo preparado, en el fork:

- alcanza `user_shared_data_ready`, `external_prefix_ready`, `ntdll_pe64_ready`, `entering_windows_initialization` y `dispatcher_slot_ready`;
- ntdll PE64 queda reubicado a su base real; el heap del proceso se crea;
- carga `wow64.dll` (`build_module Loaded ... wow64.dll`);
- termina con `wow:load_64bit_module failed to load dll c0000135`, salida `0xc0000135`, sin timeout, stubs ni violaciones de acceso.

La DLL que falta es la de `get_cpu_dll_name()`, el proveedor de CPU WoW64. El paquete del prefijo no incluye `wow64cpu.dll` desde el incremento 19, a propósito: en PS4 ese proveedor tiene que ser el traductor. `Wine_booted` y `windows_execution_verified` siguen en false.

## Hallazgo aparte: exceptions en Linux

`exceptions` falla en el fork Linux con `signal=0 resumed=0 value=0`: la lectura de una región reservada con `sceKernelReserveVirtualRange` no falla. El oficial Linux da la misma línea, así que es una diferencia del host Linux y no una regresión. La prueba se había validado sólo en Windows. Queda registrada junto a `dispatcher-mixed`.

## Validación

`tools/check-increment22.py` repite y exige:

- GS y señales: `passed` en el fork; `blocked` o no aprobado en el oficial;
- `segments` aprobado; `exceptions` con el mismo detalle en fork y oficial;
- `services` igual al histórico salvo `gs-query-output`, que pasa de blocked a passed (`fstatfs-output` sigue bloqueado);
- el preflight de doce comprobaciones; el prefijo vacío con su rechazo de wineboot y `0xc0000135`;
- el contrato de file mapping (10 casos, con comparación oficial) y el de mmap (6 casos), guardados en `reports/increment22/`;
- la matriz del incremento 18 en `reports/increment22/regressions-18`;
- el arranque de Wine descrito arriba, la ausencia de los bloqueos anteriores (`GS base could not be installed`, `unexpected trap`, heap nulo, aserción de mprotect) y los hashes intactos de ntdll PE64 y PE32 en el paquete de ejecución.

Las corridas se hacen sin `--winedebug`, opción de diagnóstico agregada al runner. `--report-dir` se agregó a `check-wine-file-mapping21.py` y `check-wine-mmap21.py` para no sobrescribir la evidencia del incremento 21.

## Reproducción

En Ubuntu 22.04/WSL:

```sh
python3 tools/build-shad-linux.py --reuse-configure --jobs 12
python3 tools/prepare-wine-boot.py
python3 tools/build-wine-ps4.py --boot --all-unix
python3 tools/build-wine-ps4.py --boot --server
python3 tools/link-wine-boot.py
python3 tools/run-linux-wine.py --fork --gs-services
python3 tools/run-linux-wine.py --fork --signal-services
python3 tools/run-linux-wine.py --fork --prepared-prefix reports/increment15/prefix-package
python3 tools/check-increment22.py
python3 tools/check-increment22.py --verify-only
```

`fork.lock.json` fija el commit `f1dcef5` y los parches 0001 a 0013.

## Próximo hito

1. **Proveedor WoW64 sobre el traductor**: un `wow64cpu.dll` (`BTCpu*`) que use `pw_cpu_ps4`, partiendo de `upstream/prospero-win/wine/wow64native/`. Hay que cubrir `I386_CONTEXT`, TEB32, llamadas de sistema y Unix, callbacks, excepciones e invalidación de código. Antes conviene resolver `dispatcher-mixed` en Linux.
2. Completar la parte PE del USD que llena `wineboot.exe`, si el arranque la necesita.
3. `console32-bare.exe` y después `console32.exe` mediante Wine, con `result.txt` idéntico a Windows y salida 0.
