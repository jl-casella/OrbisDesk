# Programas de 32 bits como huéspedes de explorer: factibilidad

[English](investigacion-wow64-en-explorer.md) | [Español](investigacion-wow64-en-explorer-es.md)

Investigación de solo lectura (2026-11-03). No se cambió código, no se compiló y no se tocó el FTP. Referencias a Wine: `.deps/wine/source` (Wine 11.17, commit `490f6d5d`), salvo que se indique el overlay de PS4 (`.deps/wine/ps4-overlay`).

## Resumen

- **Se puede, pero es un trabajo grande y con riesgo.** Wine decide WoW64 una vez por proceso, en varias capas: ntdll Unix (`wow_peb`, `is_wow64()`), wineserver (`process->machine`), ntdll PE (`init_wow64` solo en el arranque) y wow64.dll (`process_init` lee la máquina del proceso). Ninguna pieza está pensada para activar WoW64 tarde en un proceso de 64 bits.
- **Lo que ayuda:** el backend `wow64native` no impide un arranque tardío. Las bibliotecas Unix (win32u, vulkan) ya deciden por hilo con `TEB->WowTebOffset`. El TEB de 64 bits de Wine ya trae un TEB32 preparado en cada hilo. Y el modelo de huéspedes de 64 bits ya resolvió la parte "programa dentro de otro proceso".
- **Diseño propuesto:** un único "mundo de 32 bits" por sesión. Se crea la primera vez que se abre un programa de 32 bits, sobre un EXE anfitrión de 32 bits propio, y queda vivo hasta que se cierra la app. Los programas de 32 bits son huéspedes de ese mundo, con el mismo mecanismo que los de 64 bits, compilado también para i386.
- **Estimación:** entre 15 y 25 builds, con 1 o 2 sondas al principio que pueden cortar el plan.
- **Riesgos principales:** un fallo de un juego de 32 bits tumba explorer y todos los programas abiertos. El espacio por debajo de 4 GiB pasa a ser compartido. La configuración que hoy es por proceso (señales crudas, renderer de wined3d, `WINE_PS5_FIT`) deja de poder elegirse por programa.
- **Recomendación:** primero hacer menos visible el relanzamiento, que cuesta 1 o 2 builds. El modo en proceso conviene encararlo solo si las dos sondas de la sección 8 dan bien. Un segundo proceso de PS4 con su propio Wine no es viable.

## 1. WoW64 por proceso: qué asume una sola máquina

### ntdll, lado Unix

- `wow_peb` es un global (`dlls/ntdll/unix/env.c:68`). `is_wow64()` es `!!wow_peb` (`dlls/ntdll/unix/unix_private.h:84`). Se fija solo si la imagen principal no es de 64 bits (`env.c:1851-1858`), y ahí mismo se pone `WowTebOffset` en el primer TEB.
- El TEB32 ya existe en cada hilo. `init_teb` lo llena siempre en un build de 64 bits, y solo pone `teb64->WowTebOffset` si `is_wow` (`dlls/ntdll/unix/virtual.c:4011-4031`). Lo que falta, entonces, es encender la marca por hilo, no crear estructuras nuevas.
- El primer bloque de TEB se reserva por debajo de 2 GiB (`virtual.c:4087`). Los bloques siguientes usan `user_space_wow_limit` (`virtual.c:4128`), que en un proceso de 64 bits vale 0, o sea sin límite (`virtual.c:204`; solo se fija para WoW64 en `virtual.c:5117-5123`). A partir del hilo 31, un TEB de un hilo de 32 bits podría quedar por encima de 4 GiB, donde el código de 32 bits no llega.
- El PEB32 va en `peb + page_size` (`env.c:1856`). Esa página ya está comprometida en todo proceso de 64 bits, porque el bloque del PEB se compromete entero (`virtual.c:4091-4093`).
- La DLL ntdll de 32 bits se mapea solo en el arranque: `load_wow64_ntdll(main_image_info.Machine)` (`dlls/ntdll/unix/loader.c:1876`, cuerpo en `1806-1826`).
- La pila de 64 bits y el área de CPU de un hilo WoW64 se arman en `init_thread_stack` con `main_image_info.Machine` (`dlls/ntdll/unix/thread.c:1195-1210`).
- `get_cpu_area` mira `is_wow64()` y después lee `TlsSlots[WOW64_TLS_CPURESERVED]` sin comprobar si es NULL (`thread.c:1154-1160`). Si `is_wow64()` pasa a ser verdadero en todo el proceso, cada hilo de 64 bits de explorer que entre ahí lee un NULL. Esa comprobación tiene que pasar a ser por hilo.
- Otros usos de `is_wow64()` o `wow_peb` que dejan de ser correctos en un proceso mixto:
  - `process.c:1427`: `ProcessWow64Information` devuelve `wow_peb`. wow64.dll lo necesita, pero `IsWow64Process` de un programa de 64 bits pasaría a dar TRUE.
  - `process.c:1474` y `1764`: `ProcessExecuteFlags`.
  - `virtual.c:4335`: `NtSetLdtEntries`.
  - `system.c:3809`, `server.c:459` y `621`: información del sistema.
  - `thread.c:1079-1109`: contextos al servidor con `main_image_info.Machine`.
  - `thread.c:1687`: eventos de depuración.
  - En total hay 16 usos de `main_image_info.Machine` en `dlls/ntdll/unix/*.c`.
- Selectores: `cs32_sel` y `fs32_sel` se fijan en `signal_init_process` solo si el primer hilo es WoW64 (`dlls/ntdll/unix/signal_x86_64.c:2821-2829`). En Orbis, `tools/build-signal-ps4.py` pone `cs32_sel = 0x33`, pero dentro de ese mismo `if`. El contexto inicial de 32 bits de un hilo nuevo depende de `get_cpu_area` (`signal_x86_64.c:2936-2951`), es decir, de la misma marca.

### wineserver

- La máquina se guarda por proceso: `process->machine` (`server/process.c:613` y `1272`). Se fija al mapear la primera imagen (`server/mapping.c:1680-1687`).
- `set_thread_context` y `get_thread_context` rechazan un contexto WoW cuya máquina no sea la del proceso (`server/thread.c:1918-1954`, `2198`, `2281-2282`). En un proceso AMD64, un contexto i386 por hilo da `invalid_param`. Como el servidor está en el mismo ELF (W011), el cambio es un parche más, pero hay que hacerlo.
- Mapear una DLL de 32 bits en un proceso AMD64 da `STATUS_IMAGE_MACHINE_TYPE_MISMATCH` (`mapping.c:1691-1695`). Es un estado informativo: el ntdll de 32 bits no lo trata como error (la conversión de `loader.c:2839-2842` solo existe en `_WIN64`). Riesgo bajo, a confirmar con la sonda.

### ntdll, lado PE (64 bits)

- `LdrInitializeThunk` ya decide por hilo: si `NtCurrentTeb()->WowTebOffset`, entra en `init_wow64` (`dlls/ntdll/loader.c:4498` en el arranque, `4537` en hilos posteriores).
- `init_wow64` carga wow64.dll solo si `!imports_fixup_done` (`loader.c:4340-4369`). En explorer ese indicador ya es TRUE, así que el primer hilo de 32 bits llamaría a `pWow64LdrpInitialize` con el puntero en NULL. Hace falta un indicador propio para cargar wow64.dll tarde. Además `build_wow64_main_module` registra como módulo principal la imagen de `Peb->ImageBaseAddress`, que es explorer y no un EXE de 32 bits.
- Los índices TLS reservados para wow64 (`WOW64_TLS_*`, hasta `WOW64_TLS_MAX_NUMBER`) solo se reservan si el primer hilo es WoW64 (`loader.c:4480`). En explorer, `TlsAlloc` puede haber repartido esos índices a DLL de 64 bits. Se puede resolver reservándolos al arrancar cuando hay `WINE_PS4_GUESTS`.

### wow64.dll

- `Wow64LdrpInitialize` hace `process_init` una sola vez y `thread_init` en cada hilo (`dlls/wow64/syscall.c:1486-1492`). Ese reparto sirve tal cual.
- `process_init` (`syscall.c:984-1063`) toma la máquina de `RtlWow64GetProcessMachines`, que viene del servidor. En un proceso AMD64 eso da AMD64, y `get_cpu_dll_name` termina el proceso con "unsupported machine" (`syscall.c:911-923`). Hay que fijar i386 en nuestra wow64.dll, que ya es una versión adaptada (`tools/build-wow64native-ps4.py`).
- Usa `ProcessWow64Information` para encontrar el PEB32 (`syscall.c:999`) y `SystemEmulationBasicInformation` para el límite de direcciones (`syscall.c:996-997`). Ese límite sale de `user_space_wow_limit`, que hoy vale 0 en explorer.
- Lo demás (tablas de llamadas al sistema, redirección de system32, `init_image_mapping`) solo lo usan hilos de 32 bits. No interfiere con explorer.

### kernelbase, win32u y vulkan

- `kernelbase/main.c:47` consulta `IsWow64Process` al cargar, una vez.
- win32u y vulkan ya deciden por hilo:
  - `dlls/win32u/syscall.c:176`, `class.c:1104` y `rawinput.c:474`;
  - `dlls/win32u/vulkan.c:1178`: la comprobación de mapeos por debajo de 4 GiB en 32 bits. Esto es lo que hace pensable el diseño.

**Respuesta a la pregunta 1:** no se puede encender WoW64 "a demanda" con lo que trae Wine. Hace falta separar "el proceso tiene un mundo de 32 bits" (`wow_peb` no nulo) de "este hilo es de 32 bits" (`WowTebOffset`) en ntdll Unix, en el servidor y en la entrada de ntdll PE. Las piezas que siguen a ese punto (wow64.dll, el backend, win32u) ya trabajan por hilo o se arreglan con poco.

## 2. Modelo de huéspedes y qué necesitaría uno de 32 bits

Hoy (`tools/build-guest-hw.py`):

- `ps4_guest_image` acepta solo `IMAGE_FILE_MACHINE_AMD64` (`build-guest-hw.py:205`).
- `ps4_guest_launch` (`:464`) carga el EXE con `LoadLibraryExW` usando la marca `PS4_GUEST_LOADING` (`:553`) y arranca la entrada en un hilo nuevo. El hilo lleva el huésped en `TEB.UserReserved`.
- Por huésped: línea de comandos, `GetModuleHandle(NULL)`, argv de ucrt (W057), tabla `atexit` (W184, `struct ps4_guest` en `:43-56`), fin de hilos, ventanas y clases (W060-W069), filtro de excepciones (W114).
- Un PE32, o un programa con `OrbisRunsAlone` (W183, `:453`), pasa por el diálogo y por `NtCreateUserProcess` → `pw_hw_switch_program` (`build-guest-hw.py:607-655`, `tools/prepare-wine-boot.py:616-652`, `native/wine_hardware.c:157-185`).

Un huésped de 32 bits necesitaría:

1. **Un mundo de 32 bits.** El ntdll de 32 bits tiene su propio estado de cargador: `LdrData` en el PEB32, su lock y su heap. Lo arma el primer hilo WoW64 en `LdrInitializeThunk`, que también carga kernel32, kernelbase, user32 y ucrtbase de 32 bits y el EXE de `PEB32->ImageBaseAddress`. Ese estado no se puede rehacer en el mismo proceso. Por eso el PEB32 debería apuntar a un **EXE anfitrión de 32 bits propio** (por ejemplo `orbis32host.exe`, diminuto) y no al programa.
   - Un PEB32 por huésped no tiene sentido: el ntdll de 32 bits es uno solo y su estado es global.
   - Un PEB32 compartido es lo mismo que hace explorer para los huéspedes de 64 bits.
2. **Los parches de huésped compilados para i386.** Son ntdll (`loader.c`), kernelbase (`loader.c`, `thread.c`, `process.c`) y ucrtbase (`data.c`, `exit.c`). Hoy se compilan solo para `x86_64-windows` (`build-guest-hw.py:715`). En i386 la marca en `TEB32.UserReserved` funciona igual. Las DLL de 32 bits del sistema tienen nombres separados de las de 64 bits (otro `LdrData`), así que no chocan con las de explorer como en el caso de Pale Moon (W182). Entre dos huéspedes de 32 bits sí pueden chocar.
3. **Un puente entre bitness.** El `CreateProcess` de explorer (64 bits) ve un PE32 y tiene que pedir al mundo de 32 bits que lo cargue. La forma más directa es crear un hilo WoW64 cuya entrada de 32 bits sea una exportación del anfitrión (`ps4_guest32_start`). El parámetro sería un bloque por debajo de 4 GiB con la ruta y la línea de comandos. Ese hilo hace en 32 bits lo mismo que `ps4_guest_launch`. Un hilo nuevo hereda la marca WoW64 de quien lo crea (en `NtCreateThreadEx` Unix: si el hilo que llama es WoW64, el nuevo también). El primero lo crea explorer con un indicador explícito.
4. **Los thunks de wow64 por hilo.** Salen solos: `thread_init` de wow64 corre en cada hilo de 32 bits (`syscall.c:1069-1120`).
5. **El sentido inverso, de 32 a 64 bits**, cuando un programa de 32 bits lanza uno de 64. En una primera versión se puede rechazar o mandar al relanzamiento.

## 3. Backend de CPU (wow64native)

- `BTCpuProcessInit` (`upstream/prospero-win/wine/wow64native/cpu.c:549-622`) hace lo siguiente:
  - comprueba que sus thunks están por debajo de 4 GiB (la DLL está en `0x7a400000`, `tools/build-wow64native-ps4.py:132`);
  - inicializa xstate;
  - llama a `pw_native_process_init` del lado Unix, que pide las capacidades de señales (`unix.c:175-214` y la adaptación de Orbis en `build-wow64native-ps4.py:59-77`);
  - escribe dos thunks de salto lejano y fija selectores constantes (`PW_NATIVE_CS32` y los demás). No depende del hilo principal ni de que sea el primer código del proceso. No ve diferencia entre correr al arranque o a mitad de la sesión.
- `BTCpuThreadInit` (`cpu.c:633-637`, `unix.c:216-245`) guarda el FS del host del hilo y asocia el TEB32 (exige que esté por debajo de `0xfffff000`). El estado es `__thread`, por hilo. Un hilo de 64 bits de explorer que nunca llama a `BTCpuThreadInit` no se ve afectado.
- `BTCpuThreadTerm` (con el arreglo de W170) limpia solo el hilo actual.
- **Requisito de proceso:** `PW_NATIVE_SIGNALS=1`, la entrada cruda de señales de W136 (`platform/ps4/pw_wine_signals.c`, `tools/build-signal-ps4.py`). Hoy solo se pasa a los PE32 (`native/wine_hardware.c:679-688`). Con huéspedes de 32 bits tendría que estar siempre activa, con explorer y todos los programas de 64 bits. La entrada cruda guarda el FS del host en cada hilo (`pw_host_fs`), así que en principio es neutra para los hilos de 64 bits. Pero nunca se probó con explorer.
- **Respuesta:** un `process_init` tardío es posible. También se puede hacer al arrancar explorer: cargar `wow64native.dll` y llamar a su `BTCpuProcessInit` es barato, y deja la falla a la vista desde el inicio. Lo que no se puede adelantar sin costo es la inicialización del ntdll de 32 bits (kernel32, user32 y demás de 32 bits): ocupa memoria por debajo de 4 GiB y tiempo de arranque.

## 4. Espacio de direcciones

Lo que muestran los logs:

- Wine en la PS4 está limitado a `0x7ffff0000` (32 GiB): `PWBOOT virtual_step addr_space_limit=0x7ffff0000` en todas las corridas (`.deps/wine/ps4-overlay/dlls/ntdll/unix/virtual.c:3775`).
- En explorer (`reports/wine-hardware-w186/physical/20261104T002752Z/run-0001.log`):
  - `explorer.exe` está en `0x140000000`, y las DLL de 64 bits en `0x7FDxxxxxxx`-`0x7FFxxxxxxx` (líneas `trace:loaddll`);
  - el heap de `virtual` está en `0x20095c000`;
  - los huéspedes de 64 bits se cargaron en `0x1001xxxxx`-`0x101EFxxxx` (marcas `PS4 guest ... module` en W18x).
  - Todo esto queda por encima de 4 GiB.
- Lo que sí está abajo: el ELF del título (base `0x400000`, `docs/INCREMENT_13.md`; direcciones Unix como `0x908fe0` en `PWVK lookup`), el primer bloque de TEB y el PEB (por debajo de 2 GiB, `virtual.c:4087`).
- En las 17 corridas de 32 bits de W17x y W18x (SuperMarioKart), los compromisos `PWVM commit` de 1 MiB o más van de `0x3040000` a `0x20510000`. Son unos 500 MiB usados en la zona baja, sin explorer.
- En las 55 corridas de explorer y las 8 de 64 bits solos no hay ninguna línea `PWVM commit` por debajo de 4 GiB. **No alcanza para afirmar que explorer deja libre la zona baja:** el log solo registra compromisos de 1 MiB o más, y las asignaciones chicas de 64 bits (heaps, pilas, secciones) no aparecen. Hace falta una sonda (sección 8).

Lo que cambia en un proceso mixto:

- Las asignaciones de 64 bits que no piden dirección pueden caer por debajo de 4 GiB y competir con el programa de 32 bits. Wine las aparta solo si el EXE principal tiene `HIGH_ENTROPY_VA` y `DYNAMIC_BASE`, y en ese caso hace lo contrario: libera la reserva baja (`virtual.c:5106-5116`).
- Propuesta: al arrancar explorer (con `WINE_PS4_GUESTS`), reservar una zona por debajo de 4 GiB (por ejemplo 2-3 GiB) que solo se use para asignaciones de hilos de 32 bits, para TEB de hilos WoW64 y para los mapeos ubicados de Vulkan de 32 bits (`VK_EXT_map_memory_placed`, W124). Así explorer no la ocupa. Es el mismo recurso que usa Wine con `reserve_area` para WoW64 con LAA (`virtual.c:5121`).
- La memoria física del título (memoria directa y flexible, `PWVM commit_backing`) es una sola. Un juego de 32 bits más explorer y los huéspedes abiertos se reparten el mismo presupuesto, que hoy el juego tiene para él solo.

## 5. Antecedentes

- **Windows:** un proceso es de 32 o de 64 bits. WoW64 es por proceso, y Windows solo permite sus propias DLL de 64 bits dentro de un proceso de 32 bits, nunca código de 32 bits dentro de un proceso nativo de 64 bits ([nota sobre 32 y 64 bits en un mismo proceso](https://jiangsheng.readthedocs.io/en/latest/blogs/2018/06/can-we-run-32-bit-and-64-bit-code-in-the-same-process.html)).
- **Wine, modo WoW64 nuevo:** la decisión es por proceso y depende de la imagen principal (`env.c:1851`). No hay modo mixto. Lo más parecido es ARM64EC (`is_arm64ec()`, x64 y ARM64 en un proceso), pero los dos son de 64 bits: no resuelve punteros de 32 bits ni el límite de 4 GiB.
- **prospero-win:** un juego por proceso. Elegir un juego relanza el título con `sceSystemServiceLoadExec` y cerrarlo vuelve al lanzador (`upstream/prospero-win/docs/ARCHITECTURE.md:56-60`). Es el mismo modelo que nuestro relanzamiento. Su `WINE_INTEGRATION.md:145-150` dice además que varios programas en un título compartirían el mismo sandbox.
- **Hangover/FEX:** usan `libwow64fex.dll` como CPU de WoW64 para procesos de 32 bits y ARM64EC para x86_64. La decisión también es por proceso ([Hangover](https://github.com/AndreRH/hangover)). No encontré nada que ejecute varios mundos WoW64, ni WoW64 junto a programas nativos de 64 bits, en un mismo proceso.
- **Antecedente parcial:** NTVDM y winevdm ejecutan varias tareas de 16 bits dentro de un único proceso anfitrión, con un subsistema compartido. Es la misma forma que el "mundo de 32 bits con anfitrión" propuesto aquí, aunque el mecanismo es otro.

Conclusión: no hay una implementación de referencia. El diseño sería propio.

## 6. Alternativas más simples

### 6a. Relanzamiento más disimulado (recomendada a corto plazo)

- Hoy el escritorio de explorer tarda unos 8-9 s de tiempo de proceso en mostrar sus capas (`frame_presented n=6 ... layers=1 t_ms=7984` en W186 run-0001). Antes está la prueba de Vulkan del lanzador (`vk_probe_start`/`vk_probe_end`, 0,85 s) y el cierre del sistema (`wait_for_system_close`, hasta 10 s, `native/wine_hardware.c:113-118`). El tiempo de pared del cierre y la vuelta no está en los logs.
- Mejoras posibles, todas en el lanzador y sin tocar Wine:
  - Guardar el último cuadro del escritorio en `/data/orbis-win/` al llamar a `pw_hw_switch_program`, y usarlo como fondo de la pantalla de carga (W170) en el relanzamiento y en la vuelta, en lugar del logo sobre negro.
  - Saltar la prueba de Vulkan en las corridas relanzadas.
  - Medir el tiempo de pared de un ciclo completo con marcas en el log y un reloj de pared.
- **Que los programas de 64 bits sigan vivos no es posible con este camino:** `LoadExec` termina el proceso. Lo único que se puede hacer es anotar qué huéspedes estaban abiertos (ruta y línea de comandos) y volver a abrirlos al regresar. Se pierde su estado (documentos sin guardar, por ejemplo), y el diálogo actual ya lo advierte.

### 6b. Un segundo proceso de PS4 con su propio Wine

No es viable:

- El título no puede crear procesos: `fork` y `exec` se rechazan (`docs/INCREMENT_13.md:100-103`, `docs/INCREMENT_14.md:43-46`), y W052 parte de eso (`docs/HARDWARE_W003_W011.md:1108`).
- Otro título lanzado con el lanzador del sistema sería otra aplicación instalada. La PS4 tiene una sola aplicación principal en primer plano, y abrir otra suspende o cierra la actual.
- El wineserver está dentro del proceso y pasa descriptores con `SCM_RIGHTS` dentro de él (W011). Compartirlo entre dos procesos aislados no está probado, y VideoOut pertenece a un solo proceso.
- La app no hace jailbreak (`docs/HARDWARE_W180.md:116`). Usar las capacidades de GoldHEN para eso sería una decisión aparte, y aun así quedarían las dos trabas anteriores.

Ninguna de estas afirmaciones sobre el lanzador del sistema se probó en la consola. Pero alcanzan para descartarla frente a 6a.

## 7. Diseño propuesto para el modo en proceso

Un mundo de 32 bits por sesión, creado la primera vez que se abre un PE32 y nunca destruido.

| # | Pieza | Cambio | Dónde |
|---|-------|--------|-------|
| 1 | ntdll Unix | `pw_wow64_enable()`: llena el PEB32 (lo de `env.c:1864-1900` y `build_wow64_parameters`), fija `user_space_wow_limit = limit_4g-1` y reserva la zona baja, carga `ntdll` i386 (`load_wow64_ntdll(I386)`), fija `cs32_sel = 0x33` | overlay de `env.c`, `loader.c`, `virtual.c`, `signal_x86_64.c` (vía los builders de ntdll) |
| 2 | ntdll Unix | Marca WoW64 por hilo: `init_teb` y `init_thread_stack` por indicador del hilo, `get_cpu_area` comprueba NULL, `NtCreateThreadEx` hereda la marca del hilo que llama o la toma de un indicador explícito, TEB de hilos WoW64 por debajo de 4 GiB, `ProcessWow64Information` responde según el hilo | `thread.c`, `virtual.c`, `process.c` |
| 3 | wineserver | Aceptar contexto WoW i386 por hilo en un proceso AMD64 | `server/thread.c:1918-1954`, `2198-2308` (parche del servidor estático) |
| 4 | ntdll PE 64 | `init_wow64` tardío: carga wow64.dll con su propio indicador, sin `build_wow64_main_module` del EXE de explorer; reservar los índices `WOW64_TLS_*` al arrancar | `dlls/ntdll/loader.c:4340-4369`, `4480` (en `build-guest-hw.py`) |
| 5 | wow64.dll | `current_machine = I386` fijo cuando la máquina del proceso es AMD64 | `tools/build-wow64native-ps4.py` (ya adapta `syscall.c`) |
| 6 | Anfitrión | `orbis32host.exe` (PE32): bucle mínimo, exporta `ps4_guest32_start` | programa nuevo, como los de `tools/build-*-hw.py` |
| 7 | Huéspedes i386 | Los parches de `build-guest-hw.py` también para `i386-windows` (ntdll, kernelbase, ucrtbase) | `tools/build-guest-hw.py:713-731` |
| 8 | kernelbase 64 | En `CreateProcessInternalW`, un PE32 pasa a un hilo WoW64 del anfitrión en lugar del diálogo y el relanzamiento; sin cambios para `OrbisRunsAlone` | `build-guest-hw.py:603-660` |
| 9 | Lanzador | `PW_NATIVE_SIGNALS=1` y `WINE_PS4_WOW64_CPU` siempre; renderer de wined3d por programa (registro `AppDefaults\<exe>\Direct3D`, sin la variable `WINE_D3D_CONFIG` global); `WINE_PS5_FIT` solo para el relanzamiento | `native/wine_hardware.c:609-688` |

Detalles:

- Lo que se puede hacer al arrancar explorer: la zona baja, los índices TLS, cargar `wow64native.dll` y su `BTCpuProcessInit`. Lo que conviene hacer tarde: el ntdll i386 y el anfitrión, para no gastar memoria baja ni tiempo si no se abre ningún programa de 32 bits.
- Se mantiene el relanzamiento como opción: un PE32 marcado `OrbisRunsAlone` (juegos que necesitan toda la pantalla con `WINE_PS5_FIT`, o el presupuesto de memoria entero) sigue el camino de hoy.
- Un fallo no manejado en un hilo de 32 bits llega al filtro de excepciones del mundo de 32 bits. Hay que convertirlo en la salida de ese huésped (el `ps4_guest_exit_process` de 32 bits) y no en el fin del proceso. Hoy los huéspedes de 64 bits tampoco están aislados de esto (W113/W114).

### Riesgos

- **Aislamiento:** hoy un juego de 32 bits que falla solo termina su propio relanzamiento. En proceso, un fallo en modo compatibilidad o en el backend (FS del huésped, selector, señales) termina el título completo, con explorer y lo que esté abierto. W165-W170 muestran que los fallos de este tipo existieron. Es el riesgo más grande para el usuario.
- **Señales crudas siempre activas:** `PW_NATIVE_SIGNALS=1` nunca corrió con explorer, Mesa, DXVK o Pale Moon.
- **Memoria baja y total:** ver la sección 4.
- **GPU:** el renderer Vulkan de wined3d para 32 bits pasa por winevulkan WoW64 hacia ps5drv, en el mismo proceso que el loader de Khronos y MangoHud. W127 separó justamente eso por proceso. Los mapeos ubicados de Vulkan de 32 bits compiten por la zona baja.
- **Pantalla:** `WINE_PS5_FIT` (W155) es por proceso. En el escritorio, un juego de 800x600 se vería en ventana, no escalado a pantalla completa.
- **Superficie de Wine:** se cambian ntdll Unix, el servidor y la carga de ntdll PE en puntos que hoy no tienen parches de PS4. Cada actualización de Wine hay que volver a revisarlos.
- **Contención con otras sesiones:** varias de estas piezas viven en archivos que comparten otros builds (`platform/ps4`, ntdll). Ver las notas de memoria sobre archivos compartidos.

### Estimación en builds

|Etapa|Construye| Criterio de cierre |
|-------|--------|--------------------|
| Sondas (sección 8) | 1-2 | Mapa bajo 4 GiB de explorer; explorer con `PW_NATIVE_SIGNALS=1` y `wow64native` inicializado, sin regresiones |
| Mundo de 32 bits mínimo (piezas 1-6) | 3-5 | `console32-bare.exe` o un PE32 de consola corre como hilo WoW64 dentro de explorer y termina |
| Huéspedes i386 y puente (7-8) | 3-5 | Un PE32 GUI simple (winemine o notepad de 32 bits) se abre, se cierra y se vuelve a abrir desde Start |
| GPU y sonido de 32 bits en proceso (9) | 3-6 | SuperMarioKart corre en el escritorio, con fps comparables al relanzamiento |
| Estabilidad | 3-5 | Dos PE32 a la vez, PE32 junto a Pale Moon solo o huéspedes de 64 bits, fallo de un PE32 sin tumbar explorer |
|**Total**| **13-23**, más 2 de margen | |

La cifra supone que las sondas salen bien. Si el servidor o las señales piden más de lo que se ve desde el código, la etapa 2 puede duplicarse.

## 8. Qué probar primero en la consola

Una sola build de sonda, sin cambiar el comportamiento visible:

1. **Mapa por debajo de 4 GiB con explorer.** Con el escritorio listo y después de abrir y cerrar un par de huéspedes, recorrer `NtQueryVirtualMemory` de `0x10000` a `0x100000000` y registrar cada región (base, tamaño, estado, tipo). Marca sugerida: `PWWOW lowmap`. Responde si quedan 2 GiB contiguos libres y quién ocupa la zona baja.
2. **Señales crudas con explorer.** Arrancar explorer con `PW_NATIVE_SIGNALS=1` y verificar `PWNATIVE signals raw=1` y `PWNATIVE caps=3`. Usar el escritorio, un huésped de 64 bits con OpenGL (W172/W173) y Pale Moon solo. Si hay regresiones, el diseño en proceso no sigue.
3. **Backend tardío.** Desde un hilo de explorer, cargar `wow64native.dll` y llamar a `BTCpuProcessInit`. Esperar `wow64native initialized: cs32=0033 ...`. No ejecuta código de 32 bits: solo confirma que la DLL entra en `0x7a400000` con explorer cargado y que el lado Unix acepta la inicialización.

Si las tres dan bien, recién ahí conviene encarar las piezas 1-3, que son las que tienen más incertidumbre.

## Recomendación

1. Ahora: 6a (cuadro del escritorio durante el relanzamiento, sin prueba de Vulkan en las corridas relanzadas, medir el ciclo). Son 1 o 2 builds y mejoran lo que el usuario ve.
2. Después, si se quiere avanzar: la build de sonda de la sección 8. Decidir con sus resultados.
3. El modo en proceso, si se hace, debería convivir con el relanzamiento (`OrbisRunsAlone`) y empezar por programas de 32 bits simples, no por juegos.

## 9. Resultado de la sonda B0 (W232)

El plan de trabajo está en la nota `pe32-en-explorer-plan.md` de la carpeta compartida de sesiones. B0 corrió en W232, el 2026-11-04 a las 21:50, con el log en `reports/wine-hardware-w232/physical/20261105T005111Z/run-0001.log`. Dio bien en los tres puntos:

- **Señales crudas en explorer.**
  - Las trazas: `PWNATIVE signals raw=1 syscall=0x80000087a hits=1 mxcsr=0xbfe1/0xbfe1 fsbase match` y `PWNATIVE caps=3 cs64=43 ss64=3b`.
  - Explorer siguió vivo después: hubo latido de `PWSHELL` y cuadros presentados.
  - La sonda `compat32` dio `native32=1 cs=0x43 result=0x32beef32 signal=0`.
- **Zona baja.**
  - Medido: `lowmap largest_free=0x8001f000 at=0x7ffe1000`, es decir 2 GiB contiguos libres por encima de los 2 GiB.
  - Por eso el mundo de 32 bits usa el límite de un programa *large address aware* (`0xffffffff`).
- **Backend tardío.**
  - Medido: `cpu module=0x7bfe0000 below_4g=1` y `BTCpuProcessInit status=0 cpu_flags=0x1`.
  - El log no tiene la línea literal `wow64native initialized` que esperaba el plan. Tiene, en cambio, `PWNATIVE wow64native caps=3 (no xstate in exception contexts)`, que viene del lado Unix.
  - Ese mensaje lo escribe `WINE_MESSAGE` desde el lado PE de wow64native, y en este log no aparece. Por eso las trazas nuevas del lado PE usan `ERR`, que sí llega al log (son las mismas que ya usan las líneas `PWGUEST`).

## 10. B1: el mundo de 32 bits mínimo (preparado, sin probar en consola)

Objetivo (B1-B3 del plan): que `C:\orbis\console32.exe` corra como hilo WoW64 dentro de explorer, escriba `result.txt` y termine, dos veces seguidas, y que explorer siga funcionando.

Se entrega como `wow64-b1-world.patch.py` en la carpeta compartida de sesiones. Los archivos nuevos están en `b1/`.

### Qué cambia

- **ntdll Unix (P1, `tools/build-wow64-world-ps4.py`, builder nuevo).**
  - `is_wow64()` pasa a ser por hilo cuando la imagen principal es de 64 bits: el hilo tiene TEB de 32 bits. Con imagen de 32 bits (el modo relanzado) responde igual que antes.
  - **El mundo se crea tarde, a pedido.** `NtSetInformationProcess` con la clase 1100 arma:
    - el PEB32, cuya imagen es el anfitrión;
    - el ntdll i386, con estado de retorno en lugar de `fatal_error`, y conservando la rutina Ctrl de explorer;
    - el mapa de API sets por debajo de 4 GiB;
    - el límite de direcciones de 32 bits.
  - **Hilos WoW64 desde código de 64 bits.** `NtCreateThreadEx` acepta el flag `0x01000000` para crear un hilo WoW64 desde uno de 64 bits. El TEB queda por debajo de 4 GiB, el área de CPU es i386 y el selector de código es `0x33`.
  - **Respuestas por hilo.** `ProcessWow64Information` y `get_cpu_area` responden por hilo.
  - **`TlsFree` limpia la ranura solo en los hilos de su propio mundo.** Los cargadores de 32 y de 64 bits reparten los mismos índices desde bitmaps distintos. Sin este cambio, un `TlsFree` de 64 bits borraba la ranura 1 (`WOW64_TLS_CPURESERVED`) de los hilos de 32 bits.
  - **Unidades recompiladas.** Se recompilan las 11 unidades que leen el estado WoW64: las 6 probadas y las de env, signal, system, virtual y file, tomadas de sus propios builders y verificadas por hash. El builder comprueba que ninguna otra unidad lea ese estado.
- **ntdll PE (P3, `build-guest-hw.py`).**
  - `wow64.dll` se carga con el primer hilo de 32 bits aunque el proceso ya esté iniciado.
  - Si esa carga falla, termina el hilo y no el proceso.
  - `KiUserExceptionDispatcher` solo pasa por `Wow64PrepareForException` en hilos WoW64.
- **wow64 (P4, `build-wow64native-ps4.py`).**
  - `wow64.dll`:
    - en un proceso de 64 bits emula i386 para el hilo WoW64;
    - un `NtTerminateProcess` desde código de 32 bits nunca termina explorer: "los demás" se rechaza y "yo mismo" termina solo el hilo, con traza;
    - una falla de carga termina el hilo.
  - `wow64native.dll`: si a un hilo de 32 bits le falta estado, termina ese hilo.
  - **`wow64win.dll`.** Encontré un problema que el plan no tenía: su `DllMain` reemplaza `PEB->KernelCallbackTable`. Dentro de explorer, eso habría desviado todos los callbacks de user32 de 64 bits a los thunks de WoW64 en cuanto arrancara el primer hilo de 32 bits.
    - Ahora, en un proceso de 64 bits, deja la tabla del PEB intacta y pone la suya en `TlsSlots[18]` del hilo, dentro del rango reservado de WoW64.
    - `wow64.dll` la copia en cada hilo WoW64.
    - El `KiUserCallbackDispatcher` del ntdll PE la usa solo en hilos WoW64.
- **Anfitrión (P5, `fixtures/win32/orbis32host.c`).**
  - Es `C:\windows\syswow64\orbis32host.exe`, con base `0x30000000`, y exporta `ps4_guest32_start`.
  - Para B1 carga el EXE con `DONT_RESOLVE_DLL_REFERENCES`. El ntdll i386 de serie no reubica ni resuelve un EXE cargado como módulo y llama a su entrada como `DllMain` (W052/W053 en 64 bits). Por eso el anfitrión lo reubica, resuelve sus importaciones y apunta su `ExitProcess` de kernel32 a una salida propia, que vuelve al anfitrión y descarga el programa.
  - Un EXE con TLS se rechaza con traza hasta P6.
- **Lanzador (`native/wine_hardware.c`).** Con el marcador de B0 (`C:\orbis\wow64probe.txt`), explorer recibe también `WINE_PS4_WOW64_CPU=wow64native.dll`.
- **Disparador de la prueba.** `C:\orbis\wow64world64.exe` (`fixtures/win32/wow64world.c`) es un huésped de 64 bits que crea el mundo y corre el programa dos veces. Escribe `C:\orbis\wow64world-result.txt`.

### Qué se verificó sin consola

- **Script de parche.**
  - Aplica sobre copias de los cuatro archivos compartidos.
  - Una segunda pasada responde `already applied`.
  - Los builders resultantes compilan como Python.
- **Compilación.**
  - Las 11 unidades Unix compilan, y los símbolos nuevos se resuelven entre ellas (`ld -r`).
  - El ntdll PE compila y enlaza; el desensamblado muestra los dos `cmpl $0,%gs:0x180c`.
  - `wow64.dll`, `wow64win.dll` y `wow64native.dll` compilan y enlazan.
  - El anfitrión y el disparador compilan con mingw: el anfitrión tiene la exportación y las reubicaciones.
- **Enlace completo.** El ELF de hardware enlaza con los 11 objetos nuevos. Se usó una copia de `build-wine-hardware.py` cortada después del enlace. Ninguna importación del kernel quedó definida estáticamente.

Todo se hizo en una carpeta temporal, sin tocar `build/` ni `out/`.

### Riesgos que quedan

- **Servidor (P2).** No se tocó. Si algo pide el contexto i386 de un hilo WoW64 desde otro hilo (suspender, depurar), el servidor lo trata con la máquina del proceso (AMD64). `console32.exe` no lo necesita.
- **`0x30000000` y `0x400000` libres.** Si `0x30000000` está ocupada, el disparador lo dice (`host_not_at_base`). Si `0x400000` está ocupada, el anfitrión reubica `console32.exe`, que tiene reubicaciones.
- **Rutas de explorer que siguen siendo globales.**
  - `p__wine_ctrl_routine` se conserva.
  - La rama de `wow64.dll` que termina el proceso cuando la máquina no es soportada sigue igual, pero no se alcanza con i386.
  - Una excepción no manejada en código de 32 bits todavía puede terminar el título hasta que P6 traiga el filtro de excepciones de los huéspedes.
- **Supuesto sin medir.** Ningún código de 64 bits ajeno a ntdll, wow64 y win32u corre en hilos de 32 bits, de modo que `TlsSlots[18]` no choca con una ranura de `TlsAlloc` de 64 bits.

## 11. Resultado de B1 (W233) y corrección W234 (preparada, sin probar en consola)

En W233 el mundo de 32 bits no se creó: `PWWOW world_failed status=0x4000000e host=0x30000000` (`reports/wine-hardware-w233/physical/20261105T095116Z/run-0005.log`). El primer `status=0xc0000225 host=0` es la respuesta esperada ("todavía no hay mundo; mapea el anfitrión").

- **Causa.** `0x4000000e` no es `STATUS_IMAGE_NOT_AT_BASE` (`0x40000003`) sino `STATUS_IMAGE_MACHINE_TYPE_MISMATCH`, un estado informativo. wineserver (`server/mapping.c`, `map_image_view`) lo pone después de mapear la vista cuando la máquina de la imagen no es la del proceso. Para el servidor, explorer es AMD64, así que toda imagen i386 lo recibe: el anfitrión (que `wow64world64.exe` ya aceptaba) y la ntdll de 32 bits en `pw_wow64_load_ntdll32`, que lo tomaba como fallo. Además el servidor lo pone después de `NOT_AT_BASE`, de modo que también tapa una carga fuera de la base.
- **Corrección** (`wow64-w234-ntdll32-status.patch.py`, sólo cambia `tools/build-wow64-world-ps4.py`): con cualquiera de los dos estados se llama a `virtual_relocate_module`, que no hace nada si la imagen está en su base; la ntdll de 32 bits se limita a menos de 2 GiB, como en un proceso WoW64; un fallo deja `PWWOW ntdll32 failed`.
- **El resto de las DLL de 32 bits no lo necesita.** El cargador PE de i386 (`load_native_dll`) trata ese estado como éxito y `build_module` reubica.
- **Verificado** en una copia: el parche se aplica una vez y rechaza la segunda, el constructor se analiza, y `loader.c` compila con la receta probada. Falta la prueba en consola.

## 12. Resultado de B1 (W234) y W235: abrir un PE32 lo corre dentro de explorer (preparado, sin probar en consola)

**W234.** B1 pasó: `console32.exe` corrió dos veces como hilo WoW64 de explorer, sin relanzar (`reports/wine-hardware-w234/physical/20261105T102836Z/run-0001.log`, líneas 1943-2081), con salida 0 las dos veces. El `rewritten=0` de la segunda corrida venía de la comprobación, no del programa: comparaba la hora de última escritura, y la segunda escritura (13 ms, el mismo texto) cayó en el mismo instante. W235 escribe `pending` en `result.txt` antes de cada corrida.

**W235** (`wow64-w235-world-launch.patch.py` más `w235/`) une P6, P7 y P8:

- **P7, el puente.** En el kernelbase de 64 bits, `CreateProcessInternalW` con un PE32 crea el mundo si hace falta (mapea `orbis32host.exe` en `0x30000000` y pide la clase 1100) y corre `ps4_guest32_launch` del anfitrión en un hilo WoW64. Ese hilo llama al `CreateProcessW` de 32 bits. Quien llamó recibe el primer hilo del huésped y un handle a este proceso, igual que con un huésped de 64 bits. Vale para el escritorio, el menú Inicio y WFM.
- **El relanzamiento queda como respaldo:**
  - para un PE32 con `OrbisRunsAlone` (W183);
  - para todo PE32 mientras exista `C:\orbis\pe32relaunch.txt`, que además le quita a explorer las señales crudas y wow64native;
  - cuando el mundo falla: el diálogo de siempre, pero con el error a la vista.
- **P6, huéspedes i386.** `build-guest-hw.py` compila las mismas revisiones de ntdll, kernelbase y ucrtbase también para i386 (`out/guest-hw-i386`). Para i386:
  - la comprobación de imagen acepta PE32;
  - los recorridos de pila (W207, W211) siguen la cadena de EBP;
  - un programa que no puede ser huésped vuelve al lado de 64 bits con error; nunca se relanza desde un hilo de 32 bits.
- **Dónde cargan.** Las DLL de los huéspedes i386 van a `wine/lib/wine/i386-guest`. El ntdll Unix busca ahí primero, y solo en un proceso de 64 bits. Así un programa relanzado sigue con las DLL i386 de siempre.
- **P8.**
  - Explorer recibe siempre `PW_NATIVE_SIGNALS=1` y wow64native, salvo con `pe32relaunch.txt`.
  - El entorno del mundo de 32 bits lleva `WINE_D3D_CONFIG=renderer=vulkan`, como el relanzamiento. Con el `renderer=no3d` de explorer, wined3d i386 se quedaba sin adaptador (ddraw, Direct3D 7).

**Verificado en una copia:**
- el parche se aplica una vez y rechaza la segunda;
- los tres constructores se analizan;
- las 11 unidades del ntdll Unix compilan sin advertencias nuevas;
- `orbis32host.exe` exporta `ps4_guest32_launch` y `wow64world.c` compila;
- `build-guest-hw.py` construye ntdll, kernelbase y ucrtbase para x86_64 e i386. El ntdll y el ucrtbase x86_64, que W235 no cambia, difieren del constructor anterior solo en unos 20 bytes de marcas de tiempo del encabezado PE.

**Límites conocidos de la alpha:**
- un solo directorio actual para todo el mundo de 32 bits, así que dos PE32 a la vez lo comparten;
- los programas de consola de 32 bits dependen de que `AllocConsole` arranque conhost dentro del mundo; si falla, aparece el diálogo con el error;
- un PE32 que lanza un PE64 todavía no tiene puente inverso;
- sin escalado por ventana: un juego de 640x480 queda en una ventana;
- una excepción no manejada en 32 bits termina ese hilo, no explorer (B1), pero todavía no tiene la limpieza completa de un huésped.

## 13. Resultado de W235 y W236 (preparada, sin probar en consola)

**W235** (`reports/wine-hardware-w235/physical/20261105T110320Z`):
- La primera apertura de `gui-window32.exe` dentro de explorer funcionó (run-0003).
- `console32.exe` volvió al relanzamiento: el lado de 32 bits pidió `conhost.exe`, que no puede ser huésped de 32 bits (`not_a_guest`, error 50).
- Una segunda apertura de `gui-window32.exe` terminó el título.

**Causas de la caída:**
- **(c) Procedimientos de ventana.** win32u guarda una sola tabla de procedimientos de las clases propias (botón, diálogo…). El user32 de 32 bits del mundo la sobrescribió con los suyos, y el siguiente diálogo de explorer recibió `WM_NCCREATE` en una dirección de 32 bits.
- **(g) Tabla de GDI.** gdi32 de 32 bits lee la tabla de handles de GDI y los atributos de DC con punteros de 32 bits, pero en explorer estaban por encima de 4 GiB: puntero truncado, fallo en gdi32.
- **(e) Recursión en wow64.** Ante ese fallo, wow64 se repitió 207 veces: el contexto de 32 bits tenía esp=0.

**W236** (`wow64-w236-world-fixes.patch.py` más `w236/orbis32host.c`):
- **(c)** Cada mundo guarda sus procedimientos de clases propias, y cada hilo recibe los de su mundo (`build-win32u-ps4.py`, `class.c`).
- **(g)**
  - La tabla de GDI y los atributos de DC quedan siempre por debajo de 4 GiB.
  - `zero_bits` es por hilo: lo que pide un hilo WoW64 (bits de DIB, búferes de mensajes, memoria Vulkan ubicada) queda por debajo de 4 GiB.
- **(e)** En el mundo, una excepción sin pila de 32 bits termina ese hilo, con traza, en vez de repetirse (`build-wow64native-ps4.py`).
- **(b) Segunda apertura.**
  - El lado de 32 bits ya no abre un cuadro: trae la ventana al frente o avisa que no la encontró.
  - Explorer muestra "ya está abierto".
  - Una apertura sin hilo deja de contar como fallo.
  - La espera del puente entrega los mensajes enviados al hilo de explorer, para no trabarse con un arranque de 32 bits que les envía.
- **(a) Consola.**
  - Un PE32 de consola recibe la consola desde el lado de 64 bits (conhost como huésped de 64 bits).
  - El mundo de 32 bits recibe copias de sus handles en el PEB32.
  - La consola se cierra cuando termina el primer hilo del programa, salvo que la use un programa de consola de 64 bits.

**Verificado en una copia:**
- el parche se aplica una vez y rechaza la segunda;
- `build-guest-hw.py` construye las DLL x86_64 e i386;
- las 47 unidades de win32u compilan;
- `wow64.dll`, `wow64win.dll` y `wow64native.dll` se construyen, con el guardia dentro;
- `orbis32host.c` compila.

**Límites:**
- un programa de consola de 32 bits a la vez: el PEB32 tiene una sola consola;
- si el usuario cierra la ventana de la consola, el programa de 32 bits sigue corriendo sin ella;
- el motivo de fondo de esp=0 (el contexto de 32 bits que deja la entrada cruda de señales al fallar en modo compatibilidad) sigue abierto: W236 evita la recursión pero no entrega la excepción al SEH de 32 bits.

**(d) Corrección de W235: la primera ventana de `gui-window32` nunca apareció.** La apertura devolvió OK, pero el hilo del huésped (0068) no dejó ni una línea después de crearse. En el log se ve todo hasta crear el hilo y reanudarlo; después, nada. Puede no haber arrancado o haberse quedado parado en un paso silencioso. W236 agrega una línea `PWWOW` en cada paso de un hilo nuevo de 32 bits:
1. su creación (`PWWOW thread … from=32`, ntdll Unix);
2. `ResumeThread` (`resumed previous=1`);
3. `wow64 thread_init`;
4. el cargador i386 (`loader_init: tls`, un `thread_attach <dll>` por DLL, `loader_init: attached`);
5. `start: entry`, justo antes de la entrada del programa.

La última línea que aparezca para ese hilo dice dónde se detiene. W236 suma `build-wow64-world-ps4.py` a los pasos de build.

## 14. W236 y W238: los hilos de 32 bits creados suspendidos (preparado, sin probar en consola)

**W236** (`reports/wine-hardware-w236/physical/20261105T114602Z`). La cadena no pasó por `link-wine-boot.py`, así que (c), (e) y (g) no llegaron al ELF: van en W237. Las trazas de (d) mostraron la causa de que ningún programa de 32 bits llegara a su entrada:
- Todo hilo que crea código de 32 bits (`from=32`, `flags=0x1`, suspendido) se reanuda y nunca llega a `wow64 thread_init`.
- Los del puente (`from=64`, no suspendidos) corren, y también el hilo que console32 creaba sin suspender en B1.

**Causa** (ntdll Unix, `thread.c`):
- Un hilo creado suspendido espera en `wait_suspend` antes de su primera instrucción.
- `contexts_to_server` le manda a wineserver dos contextos: el nativo y el i386 del área de CPU, rotulado con la máquina de la imagen principal, que en explorer es AMD64.
- wineserver solo acepta un segundo contexto en un proceso cuya máquina difiere de la nativa (`select`), así que la espera falla en el acto.
- `contexts_from_server` escribe entonces un contexto AMD64 sobre el área i386, y el hilo queda roto antes de empezar.
- Lo mismo pasaría con `SuspendThread` sobre un hilo de 32 bits en marcha.

**W238** (`wow64-w238-suspended-threads.patch.py`, solo `build-wow64-world-ps4.py`):
- En un proceso de 64 bits, el contexto WoW64 no se intercambia con wineserver, que no guarda ninguno para un hilo de un proceso AMD64 (P2). Va solo el nativo, como para los demás hilos de explorer, y el contexto i386 queda donde lo dejó el arranque del hilo.
- El programa relanzado no cambia.
- Costo: otro hilo no puede cambiar el contexto i386 de un hilo de 32 bits suspendido a través del servidor.

**Verificado en una copia:** se aplica una vez y las 11 unidades compilan. La cadena de build tiene que incluir `link-wine-boot.py`.

## 15. W238 y W239: la primera ventana de un PE32 (preparado, sin probar en consola)

**W238** (`reports/wine-hardware-w238/physical/20261105T121747Z`):
- `console32.exe`, abierto desde WFM, corrió entero dentro de explorer sin relanzar (`sum=500500;thread=ok;dll=ok`).
- Los hilos `from=32` llegan a su entrada.
- Todo PE32 gráfico muere en su primera ventana: ejecuta `FE9ED9E0` con `WM_NCCREATE`.

**Causas:**
- **El procedimiento.** `FE9ED9E0` es `ime_ui_window_proc` del imm32 de 64 bits (`7FE9ED9E0`) cortado a 32 bits. imm32 registra "Wine IME" como clase global. En un mismo proceso la registró primero el de 64 bits, y la ventana IME del lado de 32 bits recibió su procedimiento. Lo mismo puede pasar con cualquier clase global del lado de 64 bits.
- **La recursión.** El guardia de (e) no la atajó porque miraba el Esp del contexto, que no era 0. `call_user_exception_dispatcher` usa `TEB32->SystemReserved1[0]` cuando SegSs no es el `ss32_sel` de wow64, y en el mundo de explorer ese valor es 0.

**W239** (`wow64-w239-crossworld-procs.patch.py`):
- **win32u.**
  - Un hilo WoW64 nunca llama un procedimiento por encima de 4 GiB: el mensaje va a `default_window_proc`, con una traza por hilo.
  - `GetWindowLongPtr(GWLP_WNDPROC)` le da el handle en vez de esa dirección.
  - La ventana IME de 32 bits queda como ventana común. No hay composición IME en explorer.
- **wow64.** El guardia calcula la pila igual que el despachador, así que esa excepción termina su hilo con traza.
- **Sigue abierto:** entregar la excepción al SEH de 32 bits. Hace falta el contexto de 32 bits del fallo, que la entrada cruda de señales de wow64native no guarda.

**Verificado en una copia:** se aplica una vez, las 47 unidades de win32u compilan y `wow64.dll` lleva el guardia nuevo.

## 16. W239 y W240: las ventanas IME de 32 bits y el guardia en el despachador (preparado, sin probar en consola)

**W239** (`reports/wine-hardware-w239/physical/20261105T132122Z/run-0002.log`):
- El guardia de win32u atajó `WM_NCCREATE` de la ventana IME de 32 bits.
- El mensaje siguiente, `WM_IME_SETCONTEXT`, igual ejecutó el procedimiento de 64 bits por otro camino.
- El guardia de (e) en `Wow64PassExceptionToGuest` no actuó, aunque está en el `wow64.dll` enviado (verificado desensamblando) y `pw_wow64_world` estaba activo: el despachador, llamado justo después, calculó esp 0 igual.

**W240** (`wow64-w240-ime-and-dispatcher.patch.py`):
- **IME.** Un hilo de 32 bits del mundo de explorer no recibe ventana IME por defecto (`register_imm_window`, win32u). Así su imm32 nunca crea la ventana de interfaz IME y la clase "Wine IME" del imm32 de 64 bits no llega a ese hilo. Los hilos de 64 bits y el relanzamiento no cambian.
- **(e).** La comprobación está ahora en `call_user_exception_dispatcher`, después de su propio cálculo de esp. Termina el hilo con una línea que nombra SegSs, `ss32_sel`, el Esp del contexto y `SystemReserved1[0]`, para ver en el próximo log por qué discrepan.

**Verificado en una copia:** se aplica una vez, las 47 unidades de win32u compilan y `wow64.dll` lleva la comprobación.

## 17. W240 pasó; revisión para los juegos de 32 bits en el mundo y W242 (preparado, sin probar en consola)

**W240** (`reports/wine-hardware-w240/physical/20261105T135118Z`):
- `gui-window32`, `d3d9test32` (DXVK, 1673 cuadros en 5 s) y `ddraw7test32` (wined3d Vulkan, 2491 cuadros) corren dentro de explorer y salen con estado 0.
- No hubo ningún c0000005 en toda la corrida.

**Revisión: qué necesitan Vice City y SuperMarioKart que el mundo todavía no da.**
- **Registro (arreglado en W242).** wineserver decide la vista Wow6432Node por proceso, y explorer es AMD64: los huéspedes de 32 bits leían y escribían la vista de 64 bits. Así faltaban:
  - la configuración que Vice City y W229 guardan en Wow6432Node;
  - los registros COM hechos solo ahí: los filtros DirectShow i386, `pwmpeg1.ax` y DirectMusic.

  W242 pide la redirección con el atributo `OBJ_KEY_WOW64` del servidor (ntdll Unix, `registry.c` como unidad nueva del mundo).
- **Excepciones de 32 bits (arreglado en W242).** Desde W240 un fallo termina su hilo. Wine (`IsBadReadPtr`) y los juegos toman fallos a propósito bajo SEH. El contexto de 32 bits del fallo sí está en el área de CPU (`BTCpuResetToConsistentState`), con su Esp. El despachador lo ignoraba cuando SegSs no es `ss32_sel` y usaba `SystemReserved1[0]`, que en el mundo vale 0. Ahora usa el Esp del contexto y la excepción llega al SEH del programa.
- **Imagen en `0x400000`.** El ELF del título ocupa esa base, pero no bloquea: en el relanzamiento `gta-vc.exe` ya cargaba reubicado (`027D0000`, W208).
- **Memoria.** El mundo es *large address aware* (límite `0xffffffff`) y los 2 GiB libres contiguos están por encima de `0x80000000`. Un juego que no es LAA (Vice City, Blitz3D) puede recibir punteros por encima de 2 GiB si la zona baja no alcanza. Hay que vigilar `PWVM commit` con direcciones `>= 0x80000000` antes de un fallo.
- **Pantalla.** `WINE_PS5_FIT` es de todo el proceso y explorer no lo tiene, así que el juego queda en una ventana (sección 5, escala por ventana pendiente). La tecla F12 del contador de cuadros depende del mismo modo.
- **Vulkan.** `PW_VK_BATCH=1` (rendimiento del relanzamiento) no está en el entorno del mundo; es una línea en `env.c` si hace falta, pero en el proceso también está MangoHud y no se probó junto.
- **Audio.** `wineps4` mezcla todos los flujos en un solo puerto AudioOut: el juego comparte con explorer. Vigilar `PWAUDIO`.
- **Mando, cierre (closer32), segunda apertura y salida:** cubiertos por W213, overlay-control, W217/W236 y la salida de huésped (W184-W224 compilada para i386).

## 18. W242 y W244: Vice City en el mundo y el contexto de 32 bits en cero (preparado, sin probar en consola)

**W242** (`reports/wine-hardware-w242/physical/20261105T143753Z/run-0004.log:2224-2277`):
- Los programas de prueba de 32 bits siguen bien.
- `gta-vc.exe`, abierto desde el USB, falla al cargar: ntdll32+0x51D0B escribe `0x006DF9E0`.
- En el `ntdll.dll` i386 enviado, esa dirección cae en `fixup_imports`, en el `alloc_tls_slot` integrado: la escritura del índice TLS del programa (`*AddressOfIndex`, en el .data de VC). El directorio TLS (`0x00D60074`) está en la imagen y los datos TLS se leyeron bien, así que la página del índice no se puede escribir. Puede ser una página de 16 KiB compartida con una sección de solo lectura, o un índice fuera de la imagen.

**Por qué todos los fallos del mundo mostraban esp=0** (W235, W239, W242):
- `call_user_exception_dispatcher` pide `CONTEXT_I386_ALL`, que incluye los registros de depuración.
- `get_thread_wow64_context` entonces deja el camino del propio hilo y pregunta a wineserver, que no tiene contexto i386 para un hilo de un proceso AMD64 (P2). Falla, y el despachador sigue con un contexto en cero.
- El guardia de W239 pedía solo CONTROL y por eso veía valores reales.

**W244** (`wow64-w244-vc-image.patch.py`):
- **ntdll Unix.** En un proceso de 64 bits, los registros de depuración i386 del propio hilo salen de su copia en caché. El despachador recibe el contexto real y el despacho de W242 llega al SEH del programa.
- **ntdll i386 de los huéspedes.** Antes de escribir el índice TLS de un EXE huésped:
  - traza su base, base preferida, tamaños, alineaciones y cada sección con su protección real;
  - vuelve escribible una sección marcada escribible que el mapeo dejó de solo lectura;
  - nunca escribe un índice fuera de la imagen: lo registra.

## 19. W244 y W246: Vice City necesita su base 0x400000 (preparado, sin probar en consola)

**W244** (`reports/wine-hardware-w244/physical/20261105T150422Z/run-0002.log`):
- `gta-vc.exe` carga y llega a su entrada, pero en `00AE0000`.
- La traza de secciones muestra que no tiene `.reloc`: el cargador no puede reubicarlo (`perform_relocations` da éxito con el directorio vacío). El índice TLS quedó en `006DF9E0`, fuera de la imagen, y el código usó direcciones de la base preferida hasta fallar.
- En el relanzamiento carga en `00400000` (W225, W230), porque se mapea antes que nada. En explorer ese rango ya está tomado.

**W246** (`wow64-w246-exe-window.patch.py`):
- **(1) Ventana para EXE antiguos.** En un proceso de 64 bits, las asignaciones sin dirección buscan primero lugar por encima de `0x2000000` (áreas reservadas de Wine y, si el pedido tiene límites, el área libre) y solo usan [`0x400000`, `0x2000000`) si no hay otro. Las imágenes que piden su base preferida la siguen recibiendo. Lo que explorer ya había puesto ahí antes de conocerse la imagen principal se queda.
- **(2) Traza.** Cuando una imagen i386 no consigue su base en un proceso de 64 bits: `PWWOW image_not_at_base preferred=… occupied=…+… prot=…`.
- **(3) Huésped muerto.** Un huésped cuyos hilos terminaron todos (un fallo, un desborde de pila) se da por terminado en la apertura siguiente (`PWGUEST stale`), con su módulo descargado, y la apertura sigue. Antes se rechazaba con el error 183.
- **(4) d3d8.** Es el i386: el cargador de 32 bits nombra con `system32` los archivos de `syswow64`, está por debajo de 4 GiB, y "native" significa el d3d8 de DXVK. Nada que cambiar.

## 20. W246: Vice City juega dentro de explorer; W248 (preparado, sin probar en consola)

**W246** (`reports/wine-hardware-w246/physical/20261105T154532Z/run-0002.log`):
- `gta-vc.exe` cargó en `00400000` (la ventana reservada funcionó) y se jugó dentro de explorer, sin relanzar: DXVK d3d8, audio y controles.

**Lo que el log muestra del "congelamiento":**
- Empezó antes de Salir, con una pérdida de dispositivo GPU. Esc abrió el menú de VC, DXVK reinició el dispositivo en pantalla completa ("Device reset", "Windowed: false"), y desde la línea 8066 aparece `VK_ERROR_DEVICE_LOST` cientos de veces. Un dispositivo perdido deja la capa GPU del juego en su último cuadro.
- Para saber si es del mundo o de DXVK/RADV en PS4, hay que probar Esc y volver en modo relanzado.
- Salir sí limpió:
  - la ventana se fue;
  - se cerraron 3 archivos y se descargaron los 12 módulos propios del juego;
  - el mando salió del modo juego.
- Las banderas 0x230 de entrada cruda son solo un fixme de Wine (NOLEGACY no está implementado).
- Después, el hilo de interfaz de explorer quedó sin ventana activa ni con foco.

**Videos de inicio.** VC nunca pidió DirectShow (no cargó `quartz.dll`; en el relanzamiento carga justo después de d3d8). VC los reproduce solo si su ventana no fue desactivada durante el arranque (`startupDeactivate`). Una desactivación así no queda en el log.

**W248** (`wow64-w248-focus-trace.patch.py`):
- **win32u.** Registra cada cambio de ventana en primer plano (`PWFOCUS`, las primeras 400) para ver quién desactiva a VC al arrancar.
- **Salir del overlay.** Después de terminar un huésped, pone adelante la barra de tareas (`Shell_TrayWnd`) para que teclado y mando tengan ventana.
- **Primera ventana al frente.** Pista del usuario: en una segunda apertura, la pantalla de VC no aparecía hasta apretar el mando, y ese toque además salteaba los videos. Ni los huéspedes de 64 bits tienen un paso explícito para ponerse adelante: lo hace la activación propia de Wine al mostrar la ventana.
  - En win32u (`NtUserShowWindow`), la primera ventana de primer nivel que muestra un hilo de 32 bits del mundo pasa a primer plano, como la de un proceso que arranca en Windows.
  - Traza: `PWWOW guest32 first window … foreground … set=… tick=…`. La línea del puente lleva el mismo `tick=` para medir los ms desde el lanzamiento.
  - Las ventanas hijas (el video de VMR7) siguen a su padre; la capa GPU sigue el orden Z de la ventana en ps5drv.

## 21. W248 y W249: el COM de 32 bits encuentra sus clases (preparado, sin probar en consola)

**W248** (`reports/wine-hardware-w248/physical/20261105T164309Z/run-0001.log`):
- La ventana de VC pasa al frente al instante.
- Los videos siguen sin salir: `class {e436ebb3-…} not registered` (CLSID_FilterGraph). En SuperMarioKart pasa lo mismo con `{d2ac2881-…}` (DirectMusic).

**Causa.** La redirección a Wow6432Node de wineserver tiene tres partes:
- W242 dio la que depende del atributo `OBJ_KEY_WOW64`: la redirección dentro de una ruta.
- Las otras dos dependen de los derechos de acceso, que el servidor fuerza a `KEY_WOW64_64KEY` en un proceso que no es WoW64:
  - `get_wow6432_parent`, el Wow6432Node del padre;
  - `grab_wow6432node`, que cambia una clave abierta que tiene hijo Wow6432Node por ese hijo.
- El combase i386 abre su raíz de clases como `\Registry\Machine\Software\Classes`. En un proceso WoW64 eso queda en `Classes\Wow6432Node`; en explorer quedaba en la de 64 bits, y `CLSID\{…}` abierto relativo a ella también.

**W249** (`wow64-w249-classes-view.patch.py`, ntdll Unix `registry.c`):
- Para un hilo WoW64 de un proceso de 64 bits que no pidió la vista de 64 bits, un `NtCreateKey`/`NtOpenKeyEx` exitoso sobre una clave con hijo Wow6432Node devuelve ese hijo, como hace `grab_wow6432node`.
- Traza: `PWWOW registry 32-bit view: … -> its Wow6432Node`, las primeras 32.

## 22. W250: Gecko i386 (webview32) en el mundo (preparado, sin probar en consola)

**W248** (`reports/wine-hardware-w248/physical/20261105T170334Z/run-0004.log`, desde la línea 75775):
- El Gecko i386 está instalado y se encuentra: mshtml carga `…\gecko\2.47.4\wine-gecko-2.47.4-x86\xul.dll` (syswow64 por la redirección). No hace falta descargar nada.
- Su carga falla con `c0000017`:
  - `map_fixed_area mmap error Invalid argument` en su base `0x741f0000`, de 69 MiB, que Wine no tiene ocupada;
  - todos los demás rangos fallan igual;
  - la sesión ya mostraba `anon mmap error Invalid argument` para vistas de 0x34000.
- En Orbis, un mapeo con acceso en dirección fija, o en las áreas reservadas o libres de Wine, toma memoria flexible al instante, y esa memoria se agotó. W175 da memoria directa solo en el camino anónimo de `map_view`.

**W250** (`wow64-w250-large-views.patch.py`, ntdll Unix `virtual.c`):
- Una vista de 1 MiB o más con acceso se ubica como reserva `PROT_NONE` en todos los caminos (base fija, áreas reservadas, área libre y la ventana de W246).
- Después se respalda como en W175: memoria directa primero, si no el compromiso flexible, si no `STATUS_NO_MEMORY` con la línea `PWVM view … got no memory`.
- `C:\orbis\nodirect.txt` (W220) sigue apagando la memoria directa.

## 23. W249 y W251: SuperMarioKart dentro de explorer (preparado, sin probar en consola)

**W249** (`reports/wine-hardware-w249/physical/20261105T171535Z/run-0001.log`):
- La vista de clases funciona: DirectMusic carga y la música suena.
- SuperMarioKart se cerró antes de la carrera, y al reabrirlo quedó esperando para siempre.

**Causas:**
- **El cierre.** Un mapeo Vulkan "placed" de 64 MiB no encontró memoria flexible (`tryfixed_hint … flexible=0`), wined3d se quedó con un BO sin mapear, y el `assert` de `cs.c:3189` terminó el huésped. win32u comprometía ese rango con lectura y escritura solo como marcador, porque RADV mapea encima su alias de la memoria directa. En Orbis ese compromiso toma memoria flexible al instante, y wined3d mantiene ocho bloques de 64 MiB mapeados.
- **La espera.** El candado global de wined3d (`wined3d_cs`) quedó tomado por el hilo que salió desde adentro de una llamada d3d. El wined3d i386 queda cargado entre huéspedes, así que el siguiente esperó para siempre.

**W251** (`wow64-w251-smk-wined3d.patch.py`):
- **win32u.** El rango "placed" se compromete sin acceso (en Orbis, una reserva sin memoria) y pasa a lectura y escritura después del mapeo de RADV. También vale para los programas relanzados.
- **wined3d, mapeo.** Los dos `assert` de NOOVERWRITE pasan a un camino con traza que mapea por el hilo CS.
- **wined3d, candado.** Un hilo que termina con el candado tomado lo libera; `wined3d_mutex_lock` se lo queda si su dueño ya no existe.
- **El cierre de VC con MangoHud i386.** Un hilo de 32 bits creado justo después de iniciar DXVK lee `0xFFFFFFFF` en `0x02D8F830` sin ninguna falla de memoria antes. No veo causa del lado del mundo; queda para overlay-control.

## 24. W251 y W252: Gecko i386 y el crypt32 sin lado Unix (preparado, sin probar en consola)

**W251** (`reports/wine-hardware-w251/physical/20261105T174934Z/run-0003.log`):
- W250 funcionó: el `xul.dll` i386 de 69 MiB ya se mapea.
- Se descarga enseguida y vuelve "Failed to init Gecko".
- En el medio, el proceso de inicio del `crypt32.dll` i386 hace una llamada Unix con tabla nula (falla en `__wine_unix_call_dispatcher`) y su inicialización falla. xul.dll lo importa a través de wintrust.
- No hay `crypt32.dll` i386 en `wine/lib/wine/i386-windows`: solo la copia de syswow64 del prefijo sellado, que el cargador toma sin ruta de biblioteca Unix. Por eso la tabla estática de W180 nunca se busca. El stager lo saltaba justamente porque el prefijo ya tenía uno.

**W252** (`wow64-w252-crypt32-i386.patch.py`):
- **`stage-mshtml-hw.py`.** Pone el `crypt32.dll` i386 del árbol fijado en la carpeta de builtins (`BUILTIN_FOLDER`) aunque el prefijo tenga el suyo. También sirve a los programas relanzados. No hay que descargar nada.
- **Huésped sin ventana.** El hilo principal de webview32 nunca llegó a su salida. Ahora la siguiente apertura de un programa gráfico cuyo huésped no muestra ninguna ventana lo termina (hilos y módulo) y arranca de nuevo (`PWGUEST stale … no visible window`).
- **La muerte silenciosa de Vice City tras su primer video** (W251, `run-0001.log`):
  - El video de inicio se reprodujo dentro del mundo hasta que se abrió el overlay (`PWOVERLAY open`, línea 5052) y el video se detuvo.
  - Dos hilos nuevos de quartz cargaron todas sus DLL, el `libMangoHud.dll` i386 al final, y el log termina sin excepción de Wine ni señal.
  - En W249 VC también murió tres veces justo después de cargar el MangoHud i386. La pista es el overlay con el MangoHud de 32 bits en el proceso (W247 de overlay-control).
  - W252 agrega una línea por cada hilo de 32 bits que termina (`PWWOW guest32 thread … ends`).

## 25. W252 y W253: la salida silenciosa de Vice City (preparado, sin probar en consola)

**W252.** webview32 funciona (páginas, reapertura), y el DVD y VLC también. Vice City sigue muriendo en silencio después de los videos: terminan sus hilos de dispositivo, un hilo nuevo de 32 bits carga sus DLL, y el título desaparece sin señal ni salida.

**¿Hay manejador para cada hilo?** Sí, por proceso: los `sigaction` de Wine. Con `PW_NATIVE_SIGNALS=1`, el núcleo entra primero a `pw_native_signal_entry` (W136) en cualquier hilo.

**Lo que puede terminar el título sin una línea:**
1. **La propia entrada cruda.** Una señal en código de 32 bits (CS 0x33) que la entrada no puede atar a un hilo de Wine (pila de señal deshabilitada o ajena, sin TEB, sin base FS del anfitrión, o `sysarch` que falla) va a su etiqueta 9, que hace `exit(127)` por la llamada al sistema cruda y a propósito sin C.
2. **El sistema desde afuera.** Una falla de página o un cuelgue de la GPU (la pantalla muestra un código CE-), o pasarse del presupuesto de memoria. La muerte de VC sigue al desmontaje y la recreación de su dispositivo, y en W246 Esc ya había perdido el dispositivo.
3. **Un abort/exit del lado Unix** escribiría antes "Assertion…" o pasaría por SIGABRT, que Wine registra.

**W253** (`wow64-w253-silent-exit.patch.py`):
- La etiqueta 9 escribe primero `PWNATIVE lost signal=… cs= rip= rsp= addr= fsbase=` en el log de la corrida, con la llamada `write` cruda desde una función sin libc ni TLS, y después sale como antes.
- `native/wine_hardware.c` le pasa el descriptor del log.
- Si VC muere y esa línea no aparece, es el caso 2: hay que anotar el código de error que muestra la pantalla.

**Verificado en una copia:** se aplica una vez, `pw_wine_signals.c` compila con el compilador de la consola sin advertencias, y la función nueva no toca `%fs` ni llama a libc.

## 26. W254: trazas de la recreación del dispositivo de Vice City (preparado, sin probar en consola)

Con el MangoHud i386 apagado, VC muere igual (`reports/wine-hardware-w252/physical/20261105T184512Z/run-0008.log`): tras el video terminan sus hilos de dispositivo, un hilo nuevo carga `gta-vc.exe`, `vulkan-1` y `winevulkan`, y el título desaparece.

**W254** (`wow64-w254-vk-trace.patch.py`):
- **win32u.** Para los hilos del mundo de 32 bits, cada llamada del ciclo de vida de Vulkan deja una línea de inicio y otra de fin: instancia, dispositivo, superficie, swapchain, y las reservas de memoria de 16 MiB o más (o las que fallan). Un `PWVK32 begin …` sin su `end` es la llamada en que murió el título.
- **DXVK.** Mientras exista `C:\orbis\dxvkdebug.txt`, el anfitrión de 32 bits pone `DXVK_LOG_LEVEL=debug` y `DXVK_LOG_PATH=none`: el log de DXVK va solo al log de la corrida y nunca a archivos en la carpeta del juego.

**Verificado en una copia:** se aplica una vez, las 47 unidades de win32u compilan (sin advertencias nuevas) y el anfitrión compila.

## 27. W253 y W255: una capa GPU que sobrevive a su swapchain (preparado, sin probar en consola)

**W253** (`reports/wine-hardware-w253/physical/20261105T185751Z/run-0001.log`):
- No hay línea `PWNATIVE lost signal`, así que no fue el `exit(127)` de la entrada cruda: el sistema terminó el título.
- Los últimos envíos de RADV se completaron todos.
- El log termina cuando terminan los hilos del video: los de quartz, después el que presentaba el video (`show_frame hwnd=0x2010e path=gpu_layer`) y los de su dispositivo.

**Mecanismo probable.**
- La GPU del compositor lee la imagen de un programa Vulkan en su dirección (W152), sin copia ni referencia propia.
- La única liberación es `ps5_vulkan_forget`, desde `vkDestroySwapchainKHR`, que busca la ventana de la superficie o su ventana raíz (W229).
- Si la ventana hija del video de VMR7 se destruye antes que su swapchain, ninguna de las dos búsquedas la encuentra. La capa queda en la ventana del juego con la dirección de una imagen que Mesa libera, y la composición siguiente lee memoria GPU sin mapear: una falla de página de GPU que termina el título desde afuera.
- El dibujo del compositor es sincrónico (espera su fence), así que solo una capa olvidada puede leerse después de liberada la imagen.

**W255** (`wow64-w255-forget-layers.patch.py`, `ps5drv.c`):
- Si la ventana encontrada no muestra esa swapchain, o no se encuentra ninguna, toda ventana que todavía muestre su imagen la suelta antes de que la swapchain desaparezca.
- Cada liberación queda en el log (`PWVK forget … cleared=N`).
- Hace falta también una corrida de control en modo relanzado: si ahí muere igual, el siguiente sospechoso es el cambio de W251 a los mapeos "placed".

**Verificado en una copia:** se aplica una vez y las 47 unidades de win32u compilan sin advertencias nuevas.
- **Datos del usuario después de W253.** No apareció ningún código CE- (el título probablemente salió por sí mismo), y con la carpeta Movies de VC renombrada el juego anda dentro del mundo. El fin está en el desmontaje posterior al video.
- **Trazas de salida** (también en W255, `build-wow64-world-ps4.py`):
  - Wine termina el proceso cuando su último hilo termina (`nb_threads` llega a 0). Una cuenta que quedó baja terminaría el título justo cuando terminan los hilos del video, sin señal ni código CE-.
  - Ahora `exit_thread`/`abort_thread` registran `PWEXIT last thread …`, y `process_exit_wrapper` y `abort_process` registran `PWEXIT process_exit|abort_process …`.

## 28. W254 y W256: el segundo grafo de video de Vice City (preparado, sin probar en consola)

**Qué muestra W254** (`reports/wine-hardware-w254/physical/20261105T193720Z/run-0001.log`, con la carpeta Movies restaurada):
- El primer video (Logo.mpg) se reproduce y VC lo detiene (líneas 5489-5493, `samples=118 hr=0x80040227`).
- El VMR7 se desmonta por ddraw/wined3d: se destruyen sus swapchains (5559, 5647) y después el dispositivo 0x2d152f8 con su instancia (5684-5687).
- Ese dispositivo es de wined3d (13 extensiones, igual que los de ddraw en 2907 y 3052), no de DXVK. El dispositivo D3D8 de VC sobre DXVK (0x2d22a98, 25 extensiones, línea 4217) nunca se destruye.
- Terminan los hilos del primer grafo (5688-5691) y arranca el segundo:
  - 00cc en quartz+0x30100 = `message_thread_run` (filtergraph.c);
  - 00d0 en quartz+0x2fd70 = `io_thread` (filesource.c, el bucle del puerto de finalización del File Source).
  - W251 murió en el mismo inicio de `io_thread`.
- El final llega antes del `PWMPEG open` del segundo grafo. En el primero, ese mismo tramo (4586-4760) era la enumeración de devenum (avicap32, msdmo, mmdevapi, el audio de wineps4.drv, msacm32, midimap) y después el `sink_connect` de pwmpeg1.
- El log de DXVK no va a un archivo: con `DXVK_LOG_PATH=none` sus líneas (`info:`, `debug:`) quedan en el log de la corrida. La última es la 4461.

**Descartado con el mismo log:**
- **Reuso de TEB o de pila.** Es rutina y funcionó siempre (0x7ffa0000: 0068, 007c, 00a8). Además 00d0 ejecutó todo su `loader_init` (los THREAD_ATTACH de 18 módulos) sobre ese TEB y su pila de 32 bits antes del final.
- **Una salida de Wine o de libc.** `native/wine_hardware.c` envuelve `exit` y `_exit` y escribe antes `process_exit method=…`. Las corridas de W252 tienen esas líneas y la de W254 no. Las líneas `PWEXIT` de W255 probablemente tampoco aparezcan, porque van justo antes de esas llamadas.
- **Una señal perdida** (W253), un SIGKILL del servidor (el `process_sigkill` del overlay nunca mata a su propio proceso) o una señal `PWTHREAD` cerca del final.

**Lo que queda:** el sistema terminó el proceso. Puede ser una falla que el kernel no pudo entregar, una falla de GPU o una terminación del propio sistema. Una verificación barata y de solo lectura: listar `/user/data/sce_coredumps/` por el FTP. Un volcado a la hora de la muerte indicaría el hilo y el RIP. No se borra nada ahí.

**W256** (`wow64-w256-graph-trace.patch.py`):
- `native/wine_hardware.c`: si existe `C:\orbis\winedebug.txt`, su primera línea se agrega a `WINEDEBUG`, por ejemplo `trace+quartz,trace+devenum`. Solo se toman letras, dígitos y `+-,_`, y el log lo muestra con `PWBOOT winedebug extra=…`. Sin el archivo no cambia nada.
- `native/pwmpeg1/pwmpeg1.c`: cada paso del filtro escribe una línea con su hilo (`PWMPEG create`, `connect begin`, `connect length`, `run`, `stop`, `destroy`). La última línea del segundo grafo dice hasta dónde llegó su armado.

**Verificado en una copia:** se aplica una vez y rechaza una segunda aplicación. pwmpeg1.c compila con la receta del stager sin advertencias. El fragmento del lanzador compila sin advertencias y se probó con el archivo con contenido, vacío y ausente.

**Regresión:** SuperMarioKart, del menú a la carrera (el camino de W251), sin `winedebug.txt`. W256 no cambia cómo se crean o liberan hilos, TEB, pilas ni memoria: solo agrega líneas de log y un sufijo opcional de `WINEDEBUG`.

### 28.1 La pantalla congelada tras Salir en Vice City (W255, también en W256)

**Qué muestra W255** (`reports/wine-hardware-w255/physical/20261105T195230Z/run-0001.log`, 8420-8546):
- El cerrador terminó el invitado (TerminateThread de sus 23 hilos), así que su swapchain nunca se destruye y `ps5_vulkan_forget` no corre para ella.
- Pero `window_gone` (`purge_dead_windows`) quita de ps5drv la ventana entera, con su imagen Vulkan (`vk_pixels`) incluida.
- Desde entonces ps5drv entrega al sink la pila del escritorio. `layers=4` es la misma cuenta que tenía el escritorio antes del juego (n=256, n=320). Durante el juego era 1 porque una ventana de pantalla completa se muestra sola (W248).
- Después de la salida el escritorio sigue vivo: el foco pasa a la barra de tareas, llega la entrada, el latido del shell está bien y se presentan 64 pilas más.
- Así que el origen de la imagen congelada no aparece en este log: el lado de ps5drv se ve limpio.
- Un dato para overlay-control: el cerrador registró `exit result asked32` y no aparece un resultado final (`closed`) para el overlay.

**W256** (`tools/build-win32u-ps4.py`, `ps5drv.c`):
- `PWVK forget … reason=window_gone|destroy_window` cuando la ventana que desaparece tenía una imagen Vulkan.
- A continuación, las 3 pilas siguientes que se entregan al sink, una línea por capa (`PWSINK stack i/n pixels= rect= flags= source=`). `flags=0x1` es una imagen Vulkan leída por dirección: si aparece una después de terminado el juego, es una capa vieja. Si la pila es solo del escritorio, la imagen congelada está en el sink o en la salida de video.
- La descarga del invitado llega después de que la ventana ya no está (8437 y luego 8447), así que ahí no queda nada que olvidar.

**Verificado en una copia:** el `ps5drv.c` revisado compila con la receta del builder sin advertencias.

### 28.2 W256: Vice City desde una copia interna (sin USB)

- Con VC copiado a `C:\users\orbis\Documents\…` los dos videos se reproducen y se desmontan bien (Logo de 7 239 684 bytes y GTAtitles de 24 272 900 bytes, 81,84 s), el juego corre y Salir lo cierra.
- Todas las muertes (W251-W254) fueron con VC en `E:\PC\…` (`/mnt/usb1`, exFAT, con el jailbreak).
- Hay dos diferencias, no una:
  - el archivo estaba en el USB;
  - en W256 no había ningún disco USB montado: no hay líneas `PWDRIVE`, así que el vigilante (`usb_watch` → `pw_wine_fs_usb_refresh`, cada 2 s) no tenía discos.
- Lo que el código descarta:
  - el servidor espera con `pw_wine_poll`: no hay kqueue (`fd.o` no lo referencia);
  - ntdll no usa aio ni O_ASYNC;
  - en Wine, una lectura superpuesta de un archivo regular es un `pread` sincrónico (`virtual_locked_pread`, file.c "no async I/O on regular files"), y el `sync_read` del File Source marca el evento para no pasar por el puerto;
  - además, Logo.mpg se leyó del USB con el mismo camino en todas las corridas que murieron, y VC lee del USB sus propios archivos grandes (gta3.img) sin problema con Movies renombrada.
- Pruebas para separar las dos variables, con W256 tal cual y `C:\orbis\winedebug.txt` = `trace+quartz,trace+file`:
  1. VC desde `E:` otra vez, con Movies. Las líneas `PWMPEG connect …` y los `SyncRead` de quartz con su offset muestran la última lectura antes del final.
  2. VC desde la copia interna con el disco USB conectado.

### 28.3 Causa de la muerte de Vice City tras el video: la capa GPU vieja, corregida en W255

- En W256, VC corre desde el USB y reproduce los dos videos, dos veces seguidas (`reports/wine-hardware-w256/physical/20261105T204055Z/run-0002.log`).
- El log muestra qué cambio importó: el respaldo de W255 en `ps5_vulkan_forget` actúa al final de cada video:
  - línea 5255: `PWVK forget swapchain=0x20613ce60 hwnd=0x2010c window=0 cleared=1` (Logo);
  - línea 6253: `… hwnd=0x20112 window=0 cleared=1` (GTAtitles);
  - línea 9452: `… hwnd=0x10134 window=0 cleared=1` (Logo, segunda corrida).
- `window=0 cleared=1` es exactamente el caso descrito en W255:
  - la ventana de video hija del VMR7 ya no existía cuando se destruyó su swapchain, así que la búsqueda por ventana falló;
  - la imagen seguía siendo una capa de la ventana del juego;
  - solo el recorrido por swapchain la encontró.
- Antes de W255 esa capa quedaba apuntando a la imagen ya liberada por Mesa, y la siguiente composición leía memoria GPU sin mapear. Esa falla de GPU terminaba el título desde afuera: sin señal, sin `process_exit` y, en esta consola, sin código CE- en pantalla.
- La copia interna (W256, 20261105T203137Z) y el USB no eran la causa. La muerte dependía de la temporización de la siguiente composición después del desmontaje, por eso caía cerca del arranque del segundo grafo.
- Las trazas de W254-W256 quedan por un tiempo. `PWVK forget … window=0 cleared=1` confirma el caso cada vez que ocurre.

## 29. W257 y W258: los DLL propios de un invitado y las secciones críticas huérfanas (preparado, sin probar en consola)

**Portal** (`reports/wine-hardware-w257/physical/20261105T210849Z/run-0002.log`, desde la línea 5061):
- Portal.exe (00400000) arranca hl2.exe y lo espera, así que sigue siendo un invitado vivo con carpeta `E:\PC\Portal\`.
- El primer hl2.exe (02350000) carga `bin\tier0`, `bin\vstdlib` (04340000), launcher, engine y los demás, y sale con estado 0.
- Al descargarlo no encuentra ninguno: `own_modules module=02350000 count=0 … live=2`.
  - W209 salta todo módulo dentro de la carpeta de otro invitado vivo, por considerarlo de ese invitado.
  - `E:\PC\Portal\` es prefijo de `E:\PC\Portal\bin\`, así que los DLL de hl2 contaron como de Portal.exe y quedaron cargados con su estado.
- El segundo hl2.exe (0EFA0000) falla en el vstdlib viejo (`c0000005 at 043414C3`, `vstdlib.dll+14c3`), que todavía apunta a la imagen descargada del primero.

**W258** (`wow64-w258-guest-modules.patch.py`, `tools/build-guest-hw.py`):
- **Módulos.**
  - Al lanzar un invitado se anotan los módulos cargados en ese momento (`modules_at_launch`).
  - Al salir, un módulo dentro de la carpeta de otro invitado vivo se salta solo si ya estaba cargado cuando este invitado arrancó. Si apareció después, es propio y se va con él por el camino de W209-W211:
    - se van sus clases de ventana;
    - no hay DllMain(DETACH);
    - se descarga en rondas según sus importaciones;
    - se conserva si uno de sus hilos todavía ejecuta su código.
  - Cada uno queda en el log: `PWGUEST own … (after launch, in a live guest's folder)`.
  - Los restos que se encuentran al lanzar otro invitado se deciden como antes.
- **Secciones críticas.**
  - En el ntdll de los invitados (x86_64 e i386), cuando vence la espera (5 s, después 60 s) se revisa el hilo dueño.
  - Si ya no existe o terminó, el que espera toma la sección: `PWGUEST section … held by ended thread T (recursion R): taken over by U`.
  - Las R entradas del dueño muerto salen de `LockCount`, y el campo del dueño se limpia con un compare-exchange, así que si varios lo ven a la vez solo uno gana.
  - Un dueño vivo, o un id reusado por un hilo vivo, se espera como antes.
  - Generaliza la toma del lock de wined3d de W251. Caso: el hilo 0070 de SuperMarioKart dejó tomada la sección de vulkan-1 (79A10078).

**Verificado en una copia:** se aplica una vez y rechaza una segunda aplicación. `build-guest-hw.py` compila ntdll, kernelbase y ucrtbase para x86_64 e i386 (76 revisiones). `sync.c` y `process.c` no dan advertencias nuevas; las dos que aparecen en `process.c` (líneas 1844 y 2296) ya estaban.

## 30. W259/W260: Portal se detiene por avifil32.dll y shfolder.dll

**W259** (`reports/wine-hardware-w259/physical/20261105T221907Z/run-0004.log`, desde la línea 1841): el descargue de módulos de W258 funciona. El primer hl2.exe termina con estado 0, descarga sus DLL propias (`own=12`, `rounds=7`, `released=11 bytes=190201856`) y el segundo hl2.exe carga copias nuevas. Ahora se detiene antes:

- línea 2253, Portal.exe: `Failed to load module L"SHFOLDER.dll"; status=c0000135`;
- líneas 3198-3216, el segundo hl2.exe: `Library AVIFIL32.dll (which is needed by ...\bin\valve_avi.dll) not found`, tres veces, y luego `AppFramework : Unable to load module valve_avi.dll!`;
- línea 3299: el hl2.exe termina con estado 0 sin abrir ventana.

Ninguna de las dos DLL está en el runtime de W259: ni en syswow64 ni en system32, ni en las carpetas builtin de i386 o x86_64. Las dos ya están compiladas en el árbol de Wine fijado, para ambas arquitecturas.

**W260** (`wow64-w260-avifil32-shfolder.patch.py`, solo toca `tools/stage-wine-i386.py`, el stager de W119; no se parchea Wine):

- `avifil32` y `shfolder` se añaden a `TARGETS` (i386: syswow64 y `wine/lib/wine/i386-windows`) y a `X64_TARGETS` (x86_64: system32 y `wine/lib/wine/x86_64-windows`), con su cierre de importaciones como siempre;
- avifil32 importa msacm32, msvfw32, ole32, rpcrt4, winmm y los básicos; shfolder solo importa kernel32 (sus dos exportaciones reenvían a shell32, que está en ambas vistas);
- en x86_64 el cierre añade también msvfw32.dll, que faltaba en system32;
- el msvfw32.dll i386 sigue siendo de `stage-dshow-i386.py` (W225), que rechaza un módulo ya preparado por otro stager; para este stager cuenta como presente.

`build-wine-hardware.py` ya copia ambas listas (W119/W120) y no cambia. Tras el parche hay que volver a ejecutar `stage-wine-i386.py` y luego `stage-dshow-i386.py`, porque el segundo lee el manifiesto del primero.

**Verificado en una copia:** el parche se aplica una vez y rechaza una segunda aplicación. El stager añade, en i386, avifil32.dll y shfolder.dll; en x86_64, avifil32.dll, msvfw32.dll y shfolder.dll. No quedan importaciones sin resolver y los demás módulos conservan los mismos bytes. `stage-dshow-i386.py` sigue funcionando después, con el mismo msvfw32.dll.

### 30.1 DLL de Wine que faltan

Se compararon los módulos compilados en `.deps/wine/runtime/build/dlls/*/<arch>-windows` con el runtime de W259. La lista completa está en la carpeta de notas (`w260-missing-dlls-scan.txt`); son cientos, casi todos sin interés para juegos. Las que importan más a menudo los juegos, ausentes en **las dos** vistas salvo que se indique:

- runtimes de Visual C++: msvcp60/70/71/80/90/100/110/120/140 (y msvcp140_1, _2, _atomic_wait, _codecvt_ids), msvcr70/71/80/90/100/110/120, vcruntime140, concrt140, vcomp y vcomp90-140, msvcirt, crtdll;
- gráficos: d3d10, d3d10_1, d3d12, d3d12core, d2d1, dwrite, d3dx10_43, d3dx11_43, d3dcompiler_43, d3drm, d3dim, d3dim700, ddrawex, glu32, dxva2;
- audio: xaudio2_7/8/9 (y las demás versiones), x3daudio1_*, xapofx1_*, xactengine*;
- DirectPlay antiguo: dplay, dpnet, dpnaddr, dpnlobby, dpwsockx;
- vídeo y MCI: mciavi32, mciwave, mciseq, mcicda, mciqtz32; códecs VfW iccvid, msvidc32, msrle32, ir50_32, iyuv_32; códec ACM msgsm32.acm;
- otros: riched20, riched32, msftedit, imagehlp, lz32, wing32, ctl3d32, wintab32, mswsock, winhttp (solo falta en i386), msi, mscoree, mfplat, mf, mfreadwrite, wmvcore, wmasf, amstream, qedit, qcap, evr, msxml6, xmllite.

**d3dx9_24 a d3dx9_43 no están enlazadas en el árbol** (solo hay `.o`, en ambas arquitecturas). Antes de prepararlas hay que compilarlas (`make dlls/d3dx9_NN/<arch>-windows/d3dx9_NN.dll`).

Muchos juegos traen sus propios runtimes de C++ en su carpeta. Aun así, conviene preparar en lote los runtimes de Visual C++, xaudio2/x3daudio, d3dx10/11, d3dcompiler_43, d2d1/dwrite, riched20, imagehlp, glu32 y los códecs VfW con el mismo mecanismo, para no descubrirlos juego a juego. Algunas, como mfplat, dwrite o xaudio2, dependen de una parte Unix o de bibliotecas (GStreamer, FAudio) que hay que revisar antes, una por una.

### 30.2 W260: Portal llega a Direct3D 9 y pierde el dispositivo

`reports/wine-hardware-w260/physical/20261106T011238Z/run-0001.log`. Con avifil32 y shfolder, hl2.exe lanzado por Portal.exe crea el dispositivo D3D9 de DXVK, MangoHud i386 da métricas y se presentan 5 cuadros (640x480). Desde la línea 9057 aparece `VK_ERROR_DEVICE_LOST`, unas 18 000 veces.

No se ve nada del mundo de 32 bits:

- **Memoria asignada.** Solo una asignación es visible desde la CPU: `vkAllocateMemory 0x1000000 type=2` (línea 7264). Es la única que pasa por el mapa colocado de W126/W251; DXVK la mapea en `0x7e40000`, por debajo de 4 GiB. Las otras cuatro (16, 32, 64 y 128 MiB, `type=0`) son DEVICE_LOCAL y nunca se mapean en la CPU.
- **Ningún error de mapa.** No hay líneas `PWVK placed map … protection status` ni `placed unmap … failed`.
- **El GPU no lee el alias.** El mapa colocado es un segundo alias de las mismas páginas, solo para la CPU. El GPU sigue usando su mapeo original. El `NtProtectVirtualMemory` de W251 solo hace `mprotect` del alias de la CPU, y ese alias no tiene bits de GPU.
- **Antes de la pérdida todo iba bien.** Con esa memoria, el GPU terminó correctamente los envíos 1 a 39. El envío 40 es el que nunca termina.
- **El GPU no está colgado del todo.** Estuvo casi ocioso: `gpu_busy` de 0,1 s en un intervalo de 33 s. El compositor de explorer siguió presentando después de la pérdida (`frame_presented` n=640, luego n=704).
- **No hay diagnóstico del fallo.** `radv/amdgpu: Failed to query the last GPUVM fault (-22)`: el winsys del PS4 no da la dirección del fallo.

Conclusión: es un problema de RADV/GFX7 con un cuadro de Source, no del mundo. Si se retoma, hace falta lo que devuelve la espera de la valla en el winsys PS4 y, si se puede, la dirección del fallo.

## 31. W261: todas las DLL de Wine que faltaban

A pedido del usuario, W261 prepara de una vez todos los módulos del árbol de Wine fijado que un programa de Windows puede importar y que faltaban en ambas vistas (escaneo de 30.1). Parche: `wow64-w261-wine-dlls.patch.py` (carpeta de notas). Toca `tools/stage-wine-i386.py` (necesita W260) y `tools/build-wine-hardware.py`. Listas completas en `w261-dll-lists.txt`.

- **Se añaden:** 396 módulos i386 (110,5 MB) y 393 x86_64 (122,3 MB), sin parchear:
  - runtimes de Visual C++, Direct3D 10/12, d3dx10/11, d3dcompiler, d2d1, xaudio2/x3daudio/xact;
  - DirectPlay, MCI y los códecs VfW, Media Foundation, msxml, riched, msi, ODBC/OLE DB, red, shell y COM.
- **Sin información de depuración.** Se usa `--strip-debug`: solo se quitan las secciones `.debug_*`. El código, las RVA y la firma "Wine builtin DLL" no cambian (comprobado en los 789 módulos), así que un desplazamiento de fallo sigue correspondiendo al archivo sin quitar del árbol. Sin esto, el conjunto ocuparía unos 620 MB.
- **Una sola copia.** Van solo a syswow64 (i386) o system32 (x86_64). Ninguno tiene parte Unix, y Wine carga un builtin encontrado ahí, como ya hace con los unos 140 módulos de syswow64 del prefijo sellado. Una segunda copia en `wine/lib/wine` duplicaría el tamaño.
- **Listas completas.** Una importación que no esté en la vista ni en la lista detiene el stager, y también una de un módulo excluido. Los fallos se informan todos juntos. Los módulos de otros stagers (DXVK, Vulkan, MangoHud, HID, W225, W138, W174, W177) cuentan como parte de la vista y no se tocan.
- **Registro COM para las dos vistas.** Se genera desde los scripts WINE_REGISTRY, como en W225: 119 módulos i386 y 118 x86_64 tienen scripts, en total 7699 claves. Sin esto, `CoCreateInstance` diría "class not registered": el registro sellado solo tiene las clases de sus propios módulos, y no estaban ni xaudio2_7, ni msxml6, ni AVIFile. Detalles:
  - el registro de avifil32 (W260) también se incluye;
  - no se escribe ningún valor que ya exista en el registro sellado (28 se conservan);
  - el bloque va en system.reg antes de los de MSHTML y DirectShow, cuyas secciones posteriores conservan sus valores donde ambos registran una clave (265 casos: MSXML2.DOMDocument, typelibs de interfaces de MSHTML);
  - las bibliotecas de tipos no se registran, porque `register_typelib` ejecuta código.
- **Se excluyen, con su razón** (por nombre en el manifiesto, `w261_left_out`):
  - controladores (.sys) y applets del Panel de control;
  - módulos que necesitan servicios: Programador de tareas, Registro de eventos, WIA, tarjeta inteligente, Windows Update, BITS y HTTP.sys;
  - la impresión: spooler y CUPS;
  - módulos cuya parte Unix no está en el ELF de Orbis: dwrite, odbc32, qcap, winedmo, kerberos, msv1_0, ctapi32;
  - los que importan winegstreamer, winedmo u odbc32;
  - mscoree, que necesita Wine Mono;
  - el soporte de 16 bits;
  - la administración del sistema;
  - WinRT (`windows.*`);
  - en x86_64: DirectShow (su registro de filtros es solo i386) y DirectMusic (sus arreglos son solo i386).
- **d3dx9_24 a d3dx9_43** siguen sin estar enlazadas en el árbol.

Cambio de comportamiento a vigilar: los runtimes de Visual C++ ahora existen como builtin. Un juego que trae los suyos podría pasar a usar los de Wine, según el orden de carga.

**Verificado en una copia** (la base W260 se reconstruyó y coincide con el `builder_sha256` del manifiesto de W260):

- el parche se aplica una vez y rechaza una segunda aplicación;
- los dos archivos compilan;
- el stager termina sin problemas de importación;
- los módulos de W119/W120/W260 conservan los mismos bytes;
- ningún nombre choca con el runtime de W259.

## 32. W261/W262: excepciones x87 del juego en código de 64 bits (NFS) y OpenGL de 32 bits (Call of Duty)

### 32.1 NFS Underground 2 y Most Wanted

`reports/wine-hardware-w261/physical/20261106T033201Z`, run-0003 (speed2.exe) y run-0006 (speed.exe). Justo después del dispositivo D3D9 de DXVK, en el hilo principal 0070, aparece `c0000090 (EXCEPTION_FLT_INVALID_OPERATION) addr=0000001100C009A7`, con `mxcsr=00009fc0`. El despachador de 64 bits no puede entregarla (`Exception frame is not in stack limits`) y el hilo queda colgado.

- **Dónde.** 0x1100c009a7 es un `FWAIT` dentro de `malloc` de musl en el ELF de arranque (`wine.elf`, enlazado en 0x1100000000).
- **Por qué salta ahí.** Un `FWAIT` dispara una excepción x87 pendiente cuya máscara está desactivada. El MXCSR 0x9fc0 enmascara todas las de SSE, así que se trata del estado x87.
- **Causa.** El juego desenmascara las excepciones x87 (palabra de control) y deja una pendiente. wow64native, el backend de CPU de prospero-win, cambiaba FS en cada transición pero dejaba el estado FP vivo: el código anfitrión de 64 bits (Wine, Mesa/RADV, musl) corría con las palabras de control del juego y con su excepción pendiente. El wow64cpu de Wine hace lo mismo.

**W262** (`wow64-w262-fpu-opengl.patch.py`). Cambia las adaptaciones de `cpu.c` en `tools/build-wow64native-ps4.py` y usa el marco de 0x340 bytes de `BTCpuSimulate`, alineado a 16:

- **Al empezar `BTCpuSimulate`.** Se guardan la FCW y el MXCSR de 64 bits del hilo en 0x330 y 0x334. La imagen FXSAVE en 0x30, que ya se tomaba ahí, es el estado inicial del invitado, como antes.
- **De 32 a 64 bits** (`syscall_32to64` y `unix_call_32to64`, una vez restaurado el FS del anfitrión). `FXSAVE` del estado x87/SSE completo del invitado en 0x30, luego `FNINIT` (pila x87 vacía, sin excepciones pendientes), y se cargan la FCW y el MXCSR de 64 bits guardados.
- **De 64 a 32 bits** (`syscall_32to64_return`, que también arranca al invitado, y el regreso de `unix_call_32to64`). `FXRSTOR` desde 0x30, antes del FS del invitado. El invitado recupera exactamente lo que tenía, excepciones pendientes incluidas, como en Windows.
- **Excepciones en código de 32 bits.** No cambian: su contexto lleva el estado del invitado y la ruta `RESET_STATE` entra en `syscall_32to64` con ese estado, que se guarda igual.
- **Callbacks de usuario.** Un callback (un procedimiento de ventana llamado dentro de una syscall) arranca un `BTCpuSimulate` anidado con las palabras de control de 64 bits, no con las del juego. Al volver del callback, el estado del juego se restaura desde el marco exterior.
- **El traductor** (wowprospero) emula la FPU de 32 bits y no se ve afectado.

**Verificado en una copia:**

- el parche se aplica una vez y rechaza una segunda aplicación;
- `build-wow64native-ps4.py` compila wow64native.dll;
- en el desensamblado, tras `pw_native_restore_host_fs` vienen `fxsave64 0x30(%rsp)`, `fninit`, `fldcw` y `ldmxcsr`, y `syscall_32to64_return` empieza con `fxrstor64 0x30(%rsp)`.

<a id="322-call-of-duty-no-hay-opengl-de-32-bits"></a>


### 32.2 Call of Duty: no hay heno OpenGL de 32 bits

`run-0004` (CoDSP.exe, motor de Quake 3). El juego carga el opengl32 builtin i386 de Wine (W121, preparado para wined3d), fija un modo de pantalla, abandona y prueba el siguiente, hasta rendirse.

- **Las líneas `wglUseFontBitmaps/wglUseFontOutlines not found` no son la causa.** El opengl32 de Windows también exporta solo las variantes A y W.
- **La causa.** Las llamadas `wgl*` del opengl32 de Wine van al driver OpenGL de win32u, y ps5drv no implementa ninguno, así que no existe ningún formato de píxel.
- **La vista de 64 bits** tiene desde W076 el WGL de Mesa con Zink: un `opengl32.dll` nativo y `libgallium_wgl.dll` en system32, que dibujan mediante Vulkan.

**W262** construye lo mismo para i386:

- **Script nuevo `tools/vk-h0/build-mesa-zink-i386.sh`.** Es `build-mesa-zink.sh` con los compiladores i686 de llvm-mingw y salida en `~/vk-h0/build/mesa-zink-i386`. Esta sesión ya lo compiló: 941/941 pasos, `opengl32.dll` de 166 KB y `libgallium_wgl.dll` de 20,8 MB, PE32, con exportaciones sin decorar (`wglCreateContext`, `wglChoosePixelFormat`, …). Solo importa los api-set de ucrt, kernel32, user32 y gdi32.
- **Copia en syswow64** de ambos archivos.
- **`"opengl32"="native,builtin"`.** Así los programas de 32 bits cargan este opengl32. wined3d también lo carga, y solo importa nombres estándar `gl*`/`wgl*`. La vista de 64 bits no tiene opengl32 builtin, así que no cambia.
- **Regresión a vigilar.** SuperMarioKart (ddraw sobre wined3d) ahora carga el opengl32 de Mesa en su espacio de 32 bits.

### 32.3 Lanzador de Prince of Persia: Las arenas del tiempo

`run-0002`. El lanzador carga sus plugins de prueba ("DX Version Test", "CPU Test", …), muestra un diálogo de error y termina con estado 0. No queda en la salida de depuración ninguna cadena que explique el fallo.

- **Claves de DirectX.** El runtime de W261 no tenía `HKLM\Software\Microsoft\DirectX`, pero el `system.reg` que arma W262 ya las trae en las dos vistas (`InstalledVersion` 9 y `"Version"="4.09.00.0904"`), desde el registro de módulos de W261. El bloque de W262 se detenía al encontrarlas. El coordinador lo cambió para que omita una vista existente. No eran la causa del fallo del lanzador: la causa es base_taken (32.4).
- **`get_thread_times not implemented on this platform`.** Es un fixme de ntdll en Orbis: `GetThreadTimes` devuelve ceros. Queda pendiente si la prueba de CPU sigue fallando.
- **`MFC71ENU.DLL` y `MFC71LOC.DLL`** son DLL de recursos opcionales.

<a id="324-prince-of-persia-request-not-supported-w262b"></a>


### 32.4 Príncipe de Persia: "La conquista no apoyada" (W262b)

El texto del error que vio el usuario es "No se puede iniciar. Request not supported", es decir `STATUS_NOT_SUPPORTED`. En run-0002, líneas 4175-4183:

- el lanzador (un invitado vivo en 0x400000) inicia POP.exe;
- POP.exe también necesita 0x400000 y no tiene relocaciones;
- la carga falla con c0000018 (error 487), y el kernelbase i386 devolvía `STATUS_NOT_SUPPORTED` (`PWWOW guest32 not_a_guest image=L"POP.exe" error=487`).

Dos EXE no relocalizables con la misma base no pueden estar vivos a la vez en el único mundo de 32 bits de explorer. Es el caso típico de lanzador y juego: Prince of Persia y muchos títulos de Ubisoft y EA. Abierto a mano, POP.exe pide el lanzador.

**W262b** (`wow64-w262b-base-taken.patch.py`) reutiliza el relanzamiento existente (W043/W116):

- **`tools/build-guest-hw.py`** (kernelbase i386, `CreateProcessInternalW`). Si la carga como invitado falla con el error 487:
  - se registra `PWWOW guest32 base_taken relaunch image=… cmd=… dir=…`, con la línea de órdenes del lanzador;
  - una imagen relativa ("POP.exe") pasa a ruta completa: primero el directorio que dio el lanzador, luego la carpeta del propio invitado lanzador, luego la ruta de búsqueda;
  - sin directorio explícito, el directorio de trabajo es la carpeta del programa;
  - el diálogo de 32 bits pregunta primero, explicando el motivo;
  - después, la creación de procesos de Wine llega al gancho de `NtCreateUserProcess`.
- **`tools/build-wow64-world-ps4.py`** (`process.c` de la parte Unix de ntdll, ese gancho). Antes de `pw_hw_switch_program`, entrega a `pw_hw_switch_context` (símbolo débil) dos cosas:
  - el directorio de trabajo del lanzador;
  - las variables de entorno que el lanzador fijó o cambió respecto al entorno propio del proceso: hasta 8, solo ASCII, y sin las de Wine ni las de Windows.
- **`native/wine_hardware.c`.**
  - Escribe `/data/orbis-win/next-context.txt`, con líneas `dir=` y `env=`.
  - Registra la línea de órdenes completa (`switch_program command=`) y el contexto (`switch_context`).
  - El título relanzado le da al programa ese directorio (`PW_PROGRAM_DIR`) y esas variables (`--env=`), además de la imagen y hasta 6 argumentos, como antes.

**Verificado en una copia:**

- el parche se aplica una vez y rechaza una segunda aplicación, y los tres archivos compilan;
- `build-guest-hw.py` construye ntdll, kernelbase y ucrtbase para x86_64 e i386 (77 revisiones), y `process.c` solo muestra las dos advertencias que ya existían;
- el `process.c` de ntdll con el gancho cambiado compila con la receta de wine-boot y la cabecera del mundo, sin advertencias nuevas;
- `wine_hardware.c` compila sin advertencias con los flags de `build-wine-hardware.py`.

### 32.5 Worms 4 dejaba ocupado 0x400000; el modo de 8 bits de Age of Empires II (W262c)

**Quién ocupaba 0x400000** (`reports/wine-hardware-w261/physical/20261106T034740Z/run-0014.log`). Era el propio WORMS 4 MAYHEM.EXE (cargado en 0x400000, tamaño 0x4cd000). La línea `image_not_at_base` de la 2497 es una DLL suya que se reubica.

- **El fallo.** Worms 4 falló en la línea 2933 (`PWFAULT +619da`, lectura de NULL+0x1c; le falta OpenGL de 32 bits).
- **Por qué no terminó el invitado.** Su manejador SEH no lo trató, y su propio filtro de nivel superior (un informador de fallos) respondió `EXCEPTION_EXECUTE_HANDLER`. Así, la comprobación de invitado de W208 en `UnhandledExceptionFilter` nunca se ejecutó. El inicio de hilo de ntdll llamó directamente a `NtTerminateProcess(GetCurrentProcess())`, y wow64 (B1) lo convierte en el fin de ese hilo solamente.
- **La consecuencia.** El invitado no salió ni se descargó: siguió vivo (`live=1`) y ocupando 0x400000. launcher.exe y Age of Empires II fallaron después con el error 487.

Arreglo en `tools/build-guest-hw.py`, ntdll invitado i386 y x86_64 (`call_thread_func` de `signal_i386.c` y `RtlUserThreadStart` de `signal_x86_64.c`):

- ese `__EXCEPT` termina el invitado del hilo como lo hace `RtlExitUserProcess` (W052): sus hilos acaban y sus módulos se descargan;
- registra `PWGUEST unhandled exception … after the program's own filter: the guest ends`;
- fuera de un invitado, sigue siendo `NtTerminateProcess`.

El caso base_taken de Age of Empires II ya lo cubre W262b, que trata cualquier error 487.

**Age of Empires II en 8 bits** (run-0015). Pantalla completa a 800x600 en modo de 8 bits, con el renderizador Vulkan de wined3d:

- **La secuencia.** Un present cambió el intervalo de intercambio, y la swapchain de Vulkan se rehízo para `WINED3DFMT_P8_UINT`, formato que ninguna swapchain de Vulkan admite.
- **El crash.** `wined3d_swapchain_vk_destroy_vulkan_swapchain` no limpia lo que destruye. El blit adquirió una imagen de la swapchain ya destruida: `vkAcquireNextImageKHR` → c0000005, estado 3.
- **El fallback que ya existía.** wined3d ya presenta mediante GDI cuando no hay swapchain de Vulkan, pero su DIB no tenía tabla de colores, así que un back buffer P8 habría salido sin paleta.

Arreglo en `tools/build-wined3d-hw.py`, `swapchain.c`:

- la destrucción limpia la swapchain, la superficie, las imágenes, los semáforos y el recuento, y omite los handles nulos;
- el blit sin swapchain de Vulkan registra `PWD3D swapchain … has no Vulkan swapchain for …: GDI present` y devuelve error antes de `vkAcquireNextImageKHR`;
- el present dibuja ese cuadro, y los siguientes, mediante GDI;
- `swapchain_blit_gdi` aplica la paleta de la swapchain (la paleta primaria de ddraw);
- una swapchain que no puede crear su swapchain de Vulkan al crearse se queda, con present por GDI, en vez de hacer fallar el dispositivo.

Este es el camino de todos los juegos DirectDraw de 8 bits con el renderizador Vulkan (Age of Empires, StarCraft, Diablo, C&C). El coste es un `StretchBlt` en CPU del back buffer de 8 bits por cuadro.

**Verificado en una copia:**

- el parche se aplica una vez y rechaza una segunda aplicación;
- `build-guest-hw.py` construye las DLL invitadas de las dos arquitecturas, y `signal_i386.c` y `signal_x86_64.c` compilan sin advertencias;
- `build-wined3d-hw.py` construye wined3d.dll sin advertencias;
- W262, W262b y W262c se aplican juntos en cualquier orden.

**Worms** (W261): el caso base_taken de Worms 3D (launcher.exe → bin\Worms3D.exe) lo cubre W262b. Worms 4 es un juego OpenGL y lo cubre W262 (Zink i386), junto con Call of Duty.

## 33. Regresión de W262: todo programa de 32 bits cerraba la app (CE-34878)

`reports/wine-hardware-w262/physical/20261106T155403Z`, runs 0001-0009: cada log se corta sin señal, sin PWEXIT y sin excepción no manejada.

**La correlación.**

- Todas las ejecuciones que murieron (0001-0004 y 0006-0009) cargaron el `libgallium_wgl.dll`/`opengl32.dll` i386 de Mesa en syswow64. wined3d importa opengl32, así que `"opengl32"="native,builtin"` metía Mesa en casi todo programa de 32 bits.
- La única ejecución que sobrevivió (run-0005, el escritorio que hizo el relanzamiento) no cargó ninguno de los dos.
- Tras cargar Mesa, el hilo principal de 32 bits siguió haciendo muchas llamadas al sistema a través de las transiciones FPU nuevas de W262 (por ejemplo AoE2 en run-0009). El proceso murió al crear el siguiente hilo de 32 bits: la última línea es `PWWOW thread tid=… from=32`.

**Conclusión provisional.** Apunta a lo que hace Mesa cuando un hilo de 32 bits se adjunta (`DllMain(THREAD_ATTACH)` de su frontend WGL, o su TLS implícito: las dos versiones, i386 y x64, tienen sección `.tls`), no al cambio de FPU. La versión x64 funciona en explorer desde W076, y la i386 también murió en un proceso de 32 bits relanzado a solas (run-0006).

**Siguiente paso de diagnóstico.** `C:\orbis\winedebug.txt` con `trace+module` registra cada llamada a `THREAD_ATTACH`.

**Lo que hizo el coordinador.** Quitó la línea `"opengl32"="native,builtin"` de `build-wine-hardware.py`. Así Wine vuelve a preferir su opengl32 builtin, como en W261, y los archivos de Mesa siguen en syswow64 sin usarse. El cambio de FPU de wow64native se puede conservar.

**W263** (`wow64-w263-relaunch-args-gl.patch.py`). En run-0005 → run-0006, el lanzador de Worms 3D pasó la línea de órdenes sin comillas: `E:\PC\Worms 3D\bin\Worms3D.exe /W 1280 /H 720 /FS /REFRESH 60`. Con eso:

- `pw_hw_switch_program` tomó "3D\bin\Worms3D.exe" como primer argumento;
- su límite de 6 argumentos descartó `/REFRESH 60`.

W263 corrige `native/wine_hardware.c`:

- una línea de órdenes que empieza con la propia ruta de la imagen la salta entera, con espacios incluidos;
- el cambio de programa y el relanzamiento admiten hasta 16 argumentos;
- si la línea de opengl32 sigue en `build-wine-hardware.py`, también la quita.

**Verificado en una copia:**

- se aplica una vez y rechaza una segunda aplicación;
- `wine_hardware.c` compila sin advertencias con los flags de `build-wine-hardware.py`;
- el tokenizador, compilado en el anfitrión, da los 7 argumentos de Worms 3D y no cambia el resultado de las líneas entre comillas ni de las normales.

### 33.1 W264: OpenGL de 32 bits sin ganchos en hilos ajenos, y opcional

**Causa probable de las muertes de W262.** Está en el frontend WGL de Mesa: `stw_tls_init` de `src/gallium/frontends/wgl/stw_tls.c`, llamado desde `DllMain(PROCESS_ATTACH)`.

- Recorre *todos* los hilos del proceso (`CreateToolhelp32Snapshot`) e instala en cada uno su gancho `WH_CALLWNDPROC` (`SetWindowsHookEx(…, NULL, tid)`, con el procedimiento dentro de `libgallium_wgl.dll`).
- En el proceso de explorer eso incluye los hilos de 64 bits del propio explorer y los hilos de otros programas. En un título de 32 bits relanzado, incluye los hilos de Wine que solo son de 64 bits.
- Un procedimiento de gancho de 32 bits llamado por un hilo de 64 bits ejecuta código de 32 bits como si fuera de 64 bits, en el siguiente mensaje que ese hilo reciba.
- El Mesa de 64 bits en explorer (W076) hace lo mismo, pero solo sobre hilos de su misma arquitectura, y funciona.

**La enumeración no es necesaria.** Un hilo sin datos de gancho los obtiene la primera vez que usa WGL (`stw_tls_get_data`). Los hilos creados después los obtienen en `DLL_THREAD_ATTACH`.

**W264** (`wow64-w264-gl32-hooks.patch.py`):

1. **`tools/vk-h0/patch-mesa-wgl-hooks.py`** (nuevo, lo ejecuta `build-mesa-zink-i386.sh`). En compilaciones de 32 bits (`!_WIN64`), `stw_tls_init` omite la enumeración. La de 64 bits compila igual que antes.
2. **`native/wine_hardware.c`.** Con `C:\orbis\opengl32native.txt` presente, la ejecución recibe `WINEDLLOVERRIDES=opengl32=n,b` y registra `PWGL opengl32 native (opengl32native.txt)`. Sin el archivo se usa el opengl32 builtin de Wine, como en W263. Es un interruptor en la consola, sin recompilar, hasta comprobar que el Mesa de 32 bits es seguro para todos los programas; entonces puede pasar a ser el valor por defecto.

**Verificado en una copia:**

- el parche se aplica una vez y rechaza una segunda aplicación;
- el parche de Mesa, aplicado a una copia de `stw_tls.c` y compilado con la orden exacta de cada compilación de Mesa:
  - en i386 compila sin diagnósticos y ya no referencia `CreateToolhelp32Snapshot`;
  - en x64 compila igual, con la referencia;
- `wine_hardware.c` compila sin advertencias.

## 34. Resultados de W263 y W265: argumentos del relanzamiento; NFS Underground 2

Registros: `reports/wine-hardware-w263/physical/20261106T170812Z`. Sin Mesa i386 la app ya no se cierra, lo que confirma que la regresión de W262 venía de Mesa (sección 33).

### 34.1 El relanzamiento por base ocupada perdía o rompía los argumentos

- **Prince of Persia** (run-0004:4633): el lanzador pasa `POP.exe` como `lpApplicationName` y solo `-007` como `lpCommandLine`. Windows entrega esa línea tal cual. `pw_hw_switch_program` tomaba el primer elemento como nombre del programa y lo descartaba: `args=0`, y POP.exe terminó con estado 300 ("inicie el lanzador").
- **Worms 3D** (run-0006:6414): la línea era `E:\PC\Worms 3D\bin\Worms3D.exe /W 1280 /H 720 /FS /REFRESH 60`, sin comillas y con un espacio en la ruta. El primer elemento quedó en `E:\PC\Worms`, `3D\bin\Worms3D.exe` pasó a ser argv[1], y el límite de 6 argumentos dejó fuera `/REFRESH 60`.

El parche W263 que ya contemplaba Worms 3D no se aplicó; W265 lo reemplaza (`wow64-w265-relaunch-argv.patch.py`, en la carpeta de notas). Cambios en `native/wine_hardware.c`:

- el nombre del programa al inicio de la línea se reconoce como lo hace Windows (`switch_program_name_length`):
  - primer elemento entre comillas: es el programa si nombra la imagen (ruta completa, una cola de la ruta a partir de una `\`, o el nombre de archivo, con o sin `.exe`) o si termina en `.exe`/`.com`;
  - primer elemento sin comillas: la misma prueba;
  - sin comillas y con espacios: el prefijo más corto, terminado en un espacio, que sea la ruta de la imagen o una cola de ella, como resuelve `CreateProcess` una ruta sin comillas;
  - si nada de eso coincide (el `-007` de PoP), toda la línea son argumentos;
- los argumentos se separan con las reglas del runtime de C de Microsoft (`CommandLineToArgvW`): comillas que agrupan, 2n barras antes de una comilla dan n barras y la comilla abre o cierra, 2n+1 dan n barras y una comilla literal, y `""` dentro de comillas es una comilla. Wine reconstruye la línea a partir de ese argv y vuelve a poner comillas donde hay espacios;
- se registran `switch_program program_name=…` y una línea `switch_program arg=…` por argumento;
- hasta 16 argumentos en el cambio, en el relanzamiento (`MAX_LAUNCH_ARGS`) y en `native/wine_boot.c` (`MAX_WINE_ARGS`, antes 8), y líneas de `launch.txt`/`next.txt` de hasta 299 caracteres (antes 259).

Comprobado en una copia: el parche se aplica una vez y rechaza la segunda; `wine_hardware.c` y `wine_boot.c` compilan con las opciones del lanzador sin advertencias; el separador, extraído del archivo parcheado y compilado aparte, da:

| Imagen | Línea | Nombre reconocido | Argumentos |
|---|---|---|---|
| `…\POP.exe` | `-007` | (ninguno) | `-007` |
| `E:\PC\Worms 3D\bin\Worms3D.exe` | la misma ruta sin comillas `/W 1280 /H 720 /FS /REFRESH 60` | la ruta completa | 7: `/W` `1280` `/H` `720` `/FS` `/REFRESH` `60` |
| la misma | la ruta entre comillas `/W 1280` | la ruta entre comillas | `/W` `1280` |
| `C:\Games\a.exe` | `a -x "two words" C:\dir\ "q\"x" "a""b"` | `a` | `-x`, `two words`, `C:\dir\`, `q"x`, `a"b` |
| `C:\Games\a.exe` | `C:\PROGRA~1\a2.exe /x` | `C:\PROGRA~1\a2.exe` | `/x` |
| `C:\Games\game.exe` | `-007 C:\Games\game.exe` | (ninguno) | `-007`, `C:\Games\game.exe` |
| `C:\Games\Sub Dir\game.exe` | `Sub Dir\game.exe -w` | `Sub Dir\game.exe` | `-w` |

Pruebas en consola: PoP desde su lanzador (`arg=-007`, `launch_arg --wine-arg=-007`, sin la salida con estado 300); Worms 3D desde su lanzador con `C:\orbis\opengl32native.txt` presente (W264), ya que también usa OpenGL (en W263: `Failed to create internal global context` y un fallo de página en `0000001C`); un programa con ruta entre comillas y argumentos desde Ejecutar, y `launch.txt`.

### 34.2 Need for Speed Underground 2: el modo 1366x768 no existe

La corrección de FPU de W262 funciona en run-0003: ya no aparecen `c0000090` ni el marco inválido. El fallo nuevo (run-0003:4365, `PWFAULT … address=005D2740 access=0 target=0`, `speed2.exe+1d2740`, lectura en 0) lo precede esto (3963-3976 y de nuevo en 4319-4332):

- el juego pide a D3D9 (DXVK) un dispositivo a pantalla completa de 1366x768 A8R8G8B8;
- `NtUserChangeDisplaySettings` responde -2 (`DISP_CHANGE_BADMODE`): el controlador no ofrece ese modo;
- DXVK: `EnterFullscreenMode: Failed to change display mode` y `Failed to set initial fullscreen state`, así que `CreateDevice` falla;
- el juego no comprueba el error y usa el dispositivo nulo.

No hay DLL faltante ni comprobación de CPU, y no hay mods de pantalla ancha cargados (ni `.asi` ni `dinput8` propio). 1366x768 sale de la configuración guardada del juego, no de nuestra lista de modos. Es el mismo problema que Age of Empires II (800x600 como máximo): la lista de modos del controlador (ps5drv), que lleva overlay-control. No hay nada que cambiar en el mundo WoW64. Lo que haría falta en el controlador: aceptar a pantalla completa los tamaños habituales de 4:3, 5:4 y 16:9 (1024x768, 1280x1024, 1366x768…) y presentarlos ajustados a 1280x720, como ya hace `WINE_PS5_FIT`. Mientras tanto, elegir 1280x720 o un modo de la lista en las opciones del juego debería evitar el fallo.

<a id="35-call-of-duty-en-w264-zink-could-not-create-swapchain-trazas-w266"></a>


## 35. Llamada de Duty en W264: "Zinta: no podía crear swapchain" (trazas W266)

Registro: `reports/wine-hardware-w264/physical/20261106T172552Z/run-0001.log`, hilo 0098, con `C:\orbis\opengl32native.txt` (Mesa de 32 bits). El juego termina con estado 3.

- 28440-28443: superficie y swapchain de 1274x688 para la primera ventana, `res=0`.
- 40629: `NtUserChangeDisplaySettings` devuelve -2 (`DISP_CHANGE_BADMODE`); más tarde `PWSINK mode set 800x600 … result=0` y la ventana de pantalla completa 0x3014e.
- 43666-43709: superficie para `hwnd=0x2014e` y swapchain de 1024x700, `res=0`.
- 46726-46840: `PWVK32 begin vkCreateWin32SurfaceKHR hwnd=0` (`res=0`) y enseguida `MESA: error: zink: could not create swapchain`, sin ningún `vkCreateSwapchainKHR` entre medio.

Lectura probable, pendiente de confirmar con las trazas:

- la superficie de kopper toma la ventana del framebuffer WGL de Mesa (`stw_st.c`, `stw_st_fill_private_loader_data`: `win32->hwnd = stwfb->fb->hWnd`). Ese framebuffer no tenía ventana: `stw_framebuffer_create` recibió `hWnd` NULL, ya sea de `WindowFromDC(hdc)` en `SetPixelFormat` o en `wglMakeCurrent`, o porque se creó para un HDC sin ventana;
- win32u responde a `vkGetPhysicalDeviceSurfaceCapabilitiesKHR` con `VK_ERROR_SURFACE_LOST_KHR` de inmediato si el `hwnd` de la superficie no es una ventana (`vulkan.c`: `if (!NtUserIsWindow( surface->hwnd ))`);
- por eso `update_caps` de kopper falla antes de `kopper_CreateSwapchain`, y no aparece ningún `vkCreateSwapchainKHR`.

No son las dimensiones de la superficie (`currentExtent` o el rango mínimo y máximo) después del cambio de modo fallido: con `hwnd=0` win32u ni siquiera llega a consultarlas.

`wow64-w266-zink-surface-trace.patch.py` (carpeta de notas) solo agrega trazas, sin cambiar comportamiento:

1. Mesa, solo en la compilación de 32 bits (`#if !_WIN64`; la de 64 bits compila igual), mediante el nuevo `tools/vk-h0/patch-mesa-zink-trace.py`, que ejecuta `build-mesa-zink-i386.sh` después de `patch-mesa-wgl-hooks.py`:
   - `PWSTW framebuffer hdc= hwnd= window_from_dc= window= owner= format=` en `stw_framebuffer_create`;
   - `PWSTW kopper hwnd= window= hdc= window_from_dc=` al darle la ventana a kopper;
   - `PWZINK surface hwnd= window= res=`, `PWZINK surface support res= supported=`, `PWZINK caps res=` si falla o `PWZINK caps current= min= max= images=` cuando cambian, y `PWZINK displaytarget WxH: no surface` o `: swapchain res=` cuando falla el display target.
2. win32u (`tools/build-win32u-ps4.py`, junto a las trazas W254): `vkGetPhysicalDeviceSurfaceCapabilitiesKHR` y `…Capabilities2KHR` del mundo de 32 bits de explorer: `PWVK32 surface caps hwnd= window= res=` si falla, y `… current= min= max= images=` cuando cambian las dimensiones (por proceso, no por llamada).

Comprobado en copias:

- el parche se aplica una vez y rechaza la segunda;
- el parche de Mesa se aplica una vez y en la segunda informa que ya está aplicado;
- `zink_kopper.c`, `stw_framebuffer.c` y `stw_st.c` parcheados compilan sin errores ni advertencias con la orden exacta de las compilaciones i386 y x64;
- el `vulkan.c` de win32u, con las revisiones W266 aplicadas a una copia del overlay, compila con la receta del constructor y contiene las cadenas nuevas. Las tres advertencias que da son de código anterior (W254/W255);
- el código fuente compartido de Mesa no se modificó.

Prueba: Call of Duty con `opengl32native.txt` hasta el cambio a pantalla completa. Si la lectura es correcta, se verá lo siguiente, donde -1000000000 es `VK_ERROR_SURFACE_LOST_KHR`:

```
PWSTW framebuffer … hwnd=00000000 (y lo que dijo window_from_dc)
PWSTW kopper hwnd=00000000
PWZINK surface hwnd=00000000 window=0 res=0
PWVK32 surface caps hwnd=0 window=0 res=-1000000000
PWZINK caps res=-1000000000
PWZINK displaytarget …: swapchain res=-1000000000
```

La corrección dependerá de qué HDC usa el juego y de qué devuelve `WindowFromDC` en el mundo de 32 bits.

## 36. Resultados de W266: CoD, Portal y PoP (W267)

Registros: `reports/wine-hardware-w266/physical/20261106T182510Z`. Portal y AoE2 andan a pantalla completa y NFS Underground 2 también; CoD 1 queda en negro y PoP no arranca.

### 36.1 CoD después de Portal: el lanzador de Portal seguía vivo en 0x400000

En run-0005, CoD da `base_taken` (error 487, línea 8984). El ocupante de 0x400000 (`image_not_at_base` en 2475, `occupied=0x400000+0x3f000`) es `Portal.exe`, el lanzador de Portal:

- inicia `hl2.exe` como huésped (2474-2487) y su hilo 0070 queda esperando;
- `hl2.exe` termina y se descarga (8594-8630), pero `Portal.exe` nunca sale: no aparece su `exits status`, y en 8975 sigue `live=1`.

La causa probable: el lanzamiento de un huésped devuelve como `hProcess` un duplicado del proceso **actual**, el de explorer. Un lanzador que espera a su juego con `WaitForSingleObject(hProcess)` espera para siempre y conserva su base fija. La espera de Portal.exe no está trazada; la prueba de abajo lo confirma o lo descarta.

W267 (`tools/build-guest-hw.py`, kernelbase de los huéspedes, x86_64 e i386):

- `ps4_guest_launch` devuelve como `hProcess` un duplicado del evento de fin del huésped (`guest->ended`, W210, que se señala cuando terminó y se descargó), con acceso `SYNCHRONIZE | EVENT_QUERY_STATE`. Una espera sobre ese handle vuelve cuando el huésped termina. Se registra `PWGUEST process_handle …: the guest's end event`;
- `GetExitCodeProcess`, ante un handle que no es un proceso (`STATUS_OBJECT_TYPE_MISMATCH` o `STATUS_ACCESS_DENIED`) y coincide (`NtCompareObjects`) con uno de esos eventos (los últimos 64), responde `STILL_ACTIVE` hasta que el huésped termina y después el estado de su `exit_process` (0 si nunca lo llamó);
- `dwProcessId` sigue siendo el de explorer, y `TerminateProcess` o `GetProcessId` sobre ese handle fallan, porque es un evento.

### 36.2 CoD solo (título aparte): la DXGI de DXVK dentro del cargador de Vulkan

En run-0006 no hay ninguna línea `PWSTW` ni `PWZINK`, aunque las trazas están en la DLL de Mesa (`syswow64`) y `warn+debugstr` está activo. Mesa nunca creó un framebuffer: CoD se quedó mientras zink creaba su pantalla.

- El cargador de Khronos (`vulkan-1.dll` de syswow64, que desde la Mesa i386 se carga como `native`) carga `dxgi.dll` para ordenar los adaptadores.
- En un título de 32 bits aparte, esa `dxgi.dll` es la de DXVK (`"dxgi"="native,builtin"`, W172). DXVK arranca dentro del cargador (21416: `GetPackagesByPackageFamily`, d3dkmt, `CM_Get_DevNode`, `DXVK: v2.7.1`, otra vez el cargador). El mismo ciclo se repite 9 veces y el hilo queda en silencio.
- En el mundo de explorer (W264 run-0001:42364) la `dxgi` era la builtin de Wine (`AppDefaults\explorer.exe`, `"dxgi"="builtin"`, W190), y zink llegó a sus swapchains.

W267 (`native/wine_hardware.c`): con `C:\orbis\opengl32native.txt`, `WINEDLLOVERRIDES=opengl32=n,b;dxgi=b`, igual que en el mundo de explorer. Solo cambian las ejecuciones que optaron por la Mesa de 32 bits. Un programa D3D10/11 que se ejecute aparte con ese archivo presente recibiría la `dxgi` de Wine en lugar de la de DXVK, así que para él hay que quitar el archivo.

<a id="363-prince-of-persia-dos-exe-con-base-fija"></a>


### 36.3 Príncipe de Persia: dos EXE con base fija

Las cabeceras de `PrinceOfPersia.EXE` (el lanzador, 0x1d000) y de `POP.exe` (0x739000), leídas de la consola, tienen `IMAGE_FILE_RELOCS_STRIPPED` y ningún directorio `.reloc`. Las dos piden la base fija 0x400000, así que no pueden compartir el proceso; cargar el lanzador en otra base no es posible.

Relanzado solo (run-0008, ya con `-007`, W265), `POP.exe` busca `PrinceSM` en su carpeta (1099, como archivo, no existe) y termina con estado 300. El lanzador no escribió ningún archivo `PrinceSM` en run-0007 ni en run-0009, así que probablemente es un objeto con nombre (memoria compartida) que el lanzador vivo mantiene. Sin un segundo proceso no hay arreglo en esta ronda; W267 no cambia nada para PoP.

### 36.4 Comprobación y pruebas

Comprobado en copias:

- el parche se aplica una vez y rechaza la segunda;
- el constructor parcheado se parsea, y sus 84 revisiones (5 de W267) se aplican sobre una copia del overlay;
- `kernelbase/process.c` compila con la orden de la compilación fijada para x86_64 e i386. Sus advertencias son de código anterior: `wcstoul` sin declarar y una variable `name` sin usar;
- `wine_hardware.c` compila sin advertencias.

Pruebas en consola:

- Portal desde explorer y salir del juego: `PWGUEST process_handle … hl2.exe`, y después el `exits status` y la descarga de `Portal.exe`; luego CoD desde explorer debe arrancar en 0x400000, sin `base_taken`;
- CoD solo con `opengl32native.txt`: `launch_arg --env=WINEDLLOVERRIDES=opengl32=n,b;dxgi=b`, `dxgi.dll` builtin y las líneas PWSTW/PWZINK (W266);
- regresiones: un programa iniciado desde el escritorio, lanzadores que no esperan (Worms 3D, PoP: relanzamiento por `base_taken` como antes) y el reinicio de Pale Moon (W210).

## 37. NFS Underground 2: microcortes que se destraban con el mando (trazas W268)

Registro: `reports/wine-hardware-w266/physical/20261106T182510Z/run-0009.log`. `speed2.exe` corre en el mundo de explorer desde la línea 33058; su hilo principal es 0098 y el presentador de DXVK es 00a8. Antes corrió NFS Most Wanted (`speed.exe`, 32039).

Lo que muestra el registro:

- **En juego** `PWVK present fps` da entre 78 y 110 (35551-35943).
- **Después** baja a 15,7 (35969), 1,5 (35988), 7,3 (36049), y a 29,4, 12,8 y 12,4 hasta el final (36350). `frame_presented` de 3008 a 3072 tarda 3,2 s (156920), y de 3072 a 3136 tarda 4,0 s (160958).
- **Las muestras `PWTELEM`** salen cada 0,5 s en juego y con 1,4 a 2,6 s de separación en los cortes. Ahí hay menos CPU (`cpu_mp` de 17 a 23 mil, contra 30 a 34 mil) y casi nada de GPU (`gpu_mp` de 108 a 5387, contra 12000 a 14600). El juego espera, no calcula. Estas muestras las toma `native/telemetry.c` cuando la HUD de MangoHud las pide, una por cuadro y como mucho cada 0,5 s.
- **Solo en los cortes** el hilo 0098 ejecuta callbacks de usuario de 32 bits: retornos de `KiUserCallbackDispatcher` de wow64 vía `RtlUnwindEx` con código 80000026 (`STATUS_LONGJUMP`), entre 2 y 6 por muestra, y ninguno en los 40 s de juego anteriores. Justo entonces llegan mensajes al procedimiento de ventana del juego.
- **La entrada** no se registra después de `PWPAD game_mode=1` (34684), así que no se pueden alinear los eventos del mando o del teclado que terminan cada corte.
- **No hay** DLL faltante, fallo ni línea del watchdog del servidor (`PWSERVER stuck_s`) en ese intervalo.

La hipótesis, sin confirmar, es la del coordinador: una espera con timeout (un `Sleep`, un `MsgWaitForMultipleObjects`, o un hilo de temporizador de winmm, dsound o dinput) que el wineserver en proceso termina tarde, hasta que un evento de entrada despierta su bucle. Los timeouts del servidor son sus listas de timeouts: vencen en `get_next_timeout` y `poll()` los espera (`pw_wine_poll` en platform/ps4: `sceNetEpollWait`, con un epoll nuevo en cada llamada).

`wow64-w268-server-late-timers-trace.patch.py` (carpeta de notas) solo agrega trazas en `server/fd.c`, a través de `tools/build-wine-delete-server.py`:

- `PWSERVER late_timer n= late_ms= list=rel|abs callback=`: un temporizador del servidor que vence más de 50 ms después de su hora. `thread_timeout` es el timeout de una espera y `timer_callback` un waitable timer; la dirección se compara con los símbolos del ELF o con otras ejecuciones;
- `PWSERVER late_wake n= asked_ms= took_ms= ret= users=`: un `poll()` que vuelve más de 50 ms después del timeout que recibió. Con `ret=0` el propio timeout llegó tarde; con `ret>0` lo despertó un descriptor, después de cuando debía vencer;
- se registran las 20 primeras líneas de cada tipo y después una de cada 100.

Comprobado en una copia: el parche se aplica una vez y rechaza la segunda, y el `fd.c` del servidor resultante (comprobación de la fuente probada incluida) compila con la orden de la compilación del servidor sin diagnósticos.

Prueba: NFS Underground 2 en explorer. Jugar hasta un corte, no tocar ni el mando ni el teclado durante unos segundos y después moverlos. Lectura:

- líneas `late_timer` o `late_wake` dentro del corte, entre las líneas `PWVK present fps` que bajan: la hipótesis se confirma;
- ninguna: el corte está del lado del cliente, en una espera por un mensaje o un objeto que nadie señala, y la próxima traza va ahí.

## 38. W267: Portal y CoD; CoD sale con estado 3 después de iniciar GL (trazas W269)

Registros: `reports/wine-hardware-w267/physical/20261106T185934Z`.

El arreglo del handle de proceso (W267) funciona. En run-0003 `Portal.exe` sale y se descarga después de `hl2.exe`, y CoD arranca en explorer sin `base_taken`. El GL de 32 bits también llega (run-0002, hilo 0070):

- `PWSTW framebuffer hwnd=00020128 format=43` (20206);
- superficie con `supported=1` y caps de 1024x768 (20691);
- `vkCreateSwapchainKHR 1024x768 res=0` (20772).

Después, durante 8350 líneas, el hilo 0070 solo ejecuta callbacks de usuario de 32 bits: 1042 `RtlUnwindEx` con código 80000026 (`STATUS_LONGJUMP`), que son los retornos de `KiUserCallbackDispatcher` de wow64, es decir, mensajes a los procedimientos de ventana del programa. No se muestra ningún cuadro (no hay `PWVK show_frame`) y no hay líneas MESA, abort, MessageBox ni unhandled. Luego llegan clics del mando y Enter, el primer plano pasa de 0x2013e a la ventana GL 0x20128 (las dos del hilo 0070) y aparece `exits status 3` (29122).

Lectura probable, sin confirmar:

- el motor de CoD (Quake III), ante un error fatal (`Sys_Error`, o `Com_Error` con `ERR_FATAL`), muestra el error en su propia ventana de consola y espera en un bucle de mensajes hasta que el usuario sale;
- en esa consola, el error va a un control estático, la "caja de error", con `SetWindowText`, y el texto de la consola a un control edit;
- los 1042 callbacks son ese bucle, 0x2013e sería la consola y Enter el botón de salir. El 3 es el estado con que sale ese camino, o el `abort()` del runtime de C;
- el texto del error queda en esa ventana, no en el registro;
- una causa conocida con Mesa: los juegos del motor Quake III copian `GL_EXTENSIONS` a un buffer fijo (`glConfig.extensions_string`), y la cadena de Mesa y de zink es mucho más larga que en 2003. Para estos juegos existe `MESA_EXTENSION_MAX_YEAR`.

`wow64-w269-cod-exit-text-gl-trace.patch.py` (carpeta de notas) solo agrega trazas:

1. **win32u** (`defwnd.c`, `set_window_text`): `PWTEXT hwnd= text=` por cada texto de ventana que fija un hilo de 32 bits (`WM_SETTEXT` que llega a `DefWindowProc`: controles estáticos, diálogos, cajas de mensaje y títulos), los primeros 300. La caja de error de la consola de Quake III es uno de ellos. El buffer de la consola (`EM_REPLACESEL`) se queda en el control edit de user32 y no se traza.
2. **kernelbase de los huéspedes** (`ps4_guest_exit_process`, x86_64 e i386): `PWGUEST exit_caller n <exe>+offset at <pila>` para las primeras 12 palabras de la pila del hilo que sale que apuntan dentro de la imagen del programa. Son las direcciones de retorno del código que llamó a `exit`/`ExitProcess`, más algunos punteros a datos. Esos offsets, contrastados con el EXE leído de la consola en solo lectura, distinguen `Sys_Error`, `Com_Quit` y `abort`.
3. **Mesa de 32 bits** (`patch-mesa-zink-trace.py`, `src/mesa/main/getstring.c`): `PWGL version=... extensions_length=` la primera vez que un programa pide `GL_EXTENSIONS`, y `PWGL vendor= renderer=` una vez.

Comprobado en copias:

- el parche se aplica una vez y rechaza la segunda, y los tres scripts editados se parsean;
- el `defwnd.c` de win32u compila con la receta del constructor y contiene `PWTEXT`. Su advertencia en la línea 904 es de código anterior;
- el `process.c` de kernelbase compila para x86_64 e i386 con las 85 revisiones aplicadas. Las advertencias son anteriores (`wcstoul` y `name`);
- el script de trazas de Mesa traza `getstring.c` una vez, sin tocar los archivos ya trazados en W266, y `getstring.c` compila sin diagnósticos con las órdenes de i386 y x64;
- el código fuente compartido de Mesa no se modificó.

Prueba: CoD desde explorer, con `opengl32native.txt` como en W267, hasta que se detenga. Leer:

- las líneas `PWTEXT` antes de la salida, donde debería estar el error;
- la línea `PWGL`: un `extensions_length` muy por encima de 1024 o 4096 apunta al buffer fijo;
- los offsets de `exit_caller`.

### 38.1 Corrección de la lectura de CoD y W269 unificado

El usuario aclara: "no da error de nada, después de un rato se cierra". No apareció ningún cartel, así que la lectura de la consola de error de Quake III queda en duda. Lo que el registro sí muestra: el programa nunca presentó un cuadro y terminó por su cuenta con estado 3 (`abort()` del runtime de C, o un `exit(3)` del juego). La copia de `GL_EXTENSIONS` a un buffer fijo sigue siendo candidata, porque corrompe el estado del motor sin provocar un fallo. Las trazas de 38 siguen siendo las adecuadas.

El script de 38 queda reemplazado por `wow64-w269-cod-maxpayne.patch.py`, que incluye las mismas trazas de CoD y lo de Max Payne (38.2 y 38.3). El anterior nunca se aplicó y se quitó de la carpeta de notas.

### 38.2 Max Payne 1: su propio MSVCRT.DLL (arreglo W269)

`reports/wine-hardware-w267/physical/20261106T190602Z/run-0006.log:2292` muestra `PWGUEST clash app=MaxPayne.exe name=msvcrt.dll loaded=C:\windows\syswow64\msvcrt.dll` y después `not_a_guest` con error 1114. La carpeta del juego trae su propio `MSVCRT.DLL`, junto con MFC42, MSVCP60 y MSVCIRT.

- **Por qué choca:** la comprobación de choques (W182, el mozglue de Pale Moon contra el de Gecko) exceptúa solo las DLL cargadas desde `GetSystemDirectory`, que en el mundo de 32 bits de explorer es system32, mientras sus DLL se cargan desde syswow64.
- **Qué hace Windows:** `msvcrt.dll` es una KnownDLL (el `wine.inf` de Wine la declara así, igual que Windows). Windows siempre usa la copia del sistema, tenga lo que tenga la carpeta del programa.
- **Qué hace Wine:** el cargador resuelve una importación sin ruta con el módulo ya cargado con ese nombre (`find_dll_file` → `find_basename_module`, en `loader.c`), antes de buscar archivos.

Arreglo (`tools/build-guest-hw.py`, `ps4_guest_launch` del kernelbase de los huéspedes): una DLL cargada cuyo nombre está en las KnownDLLs de Wine no cuenta como choque. Se registra `PWGUEST clash_known name=…` y el programa se carga con la copia del sistema, como en Windows. Los demás nombres (el caso de Pale Moon) se rechazan como antes.

### 38.3 Max Payne 2: excepciones C++ antes de salir (traza W269)

Mismo registro, desde la línea 5324:

- el hilo 0074 carga `syswow64\D3D9.DLL` (DXVK) y la descarga enseguida, sin llamar a `Direct3DCreate9` (no hay ninguna línea de DXVK);
- después viene una cadena de excepciones C++ (e06d7363) lanzadas en `rlmfc.dll`, la biblioteca base de Remedy en 02E00000 (manejadores 02E1C18E, 02E1C468, 02E1C610 y 02E1D5E0), y en MSVCR71, que llega al manejador del EXE (004D43C2);
- una ventana vive unos 4 s y el programa sale con estado 0. La excepción dice el porqué y no está en el registro.

Traza (kernelbase de los huéspedes, en el manejador vectorizado de W207):

- `PWCXX n= thread= type=<primer tipo atrapable> what=<mensaje de una std::exception> throw=<módulo+offset>`;
- la cadena de EBP como `PWCXX n frame k módulo+offset`;
- se registran las 24 primeras excepciones C++ de huéspedes;
- en x86 el ThrowInfo tiene punteros y en x64 RVAs desde la base de la imagen;
- todo se lee con `NtReadVirtualMemory`, así que un puntero inválido no lee nada en lugar de fallar.

### 38.4 Comprobación de W269

En copias:

- el parche se aplica una vez y rechaza la segunda, y los tres scripts editados se parsean;
- con las 88 revisiones del constructor de huéspedes (4 de W269), `kernelbase.dll` **compila y enlaza** para x86_64 e i386, y contiene `PWCXX`, `clash_known`, `exit_caller` y `process_handle`. Las advertencias de `process.c` son de código anterior;
- el `defwnd.c` de win32u compila con la receta del constructor;
- `getstring.c` de Mesa compila sin diagnósticos para i386 y x64;
- el código fuente compartido de Mesa no se modificó.

Pruebas en consola:

- Max Payne 1 desde explorer: `clash_known name=msvcrt.dll` y `load_end error=0`, o el siguiente choque, registrado como antes, si otra de sus DLL está cargada desde otra carpeta;
- Max Payne 2: las líneas `PWCXX` antes de salir, y `PWTEXT` si crea algún diálogo;
- CoD: `PWGL`, `PWTEXT` y `exit_caller`;
- regresión: Pale Moon después de una vista web de Gecko sigue rechazado.
