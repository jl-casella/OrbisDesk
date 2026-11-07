# W137: código de 32 bits nativo (fase 5A, paso 2)

[English](HARDWARE_W137.md) | [Español](HARDWARE_W137-es.md)

APP_VER 02.36. Base W136: la entrada de señales cruda anda en la PS4 (`caps=3`).

## Cambios

- `tools/build-wow64native-ps4.py` (nuevo) arma el `wow64native` de prospero-win:
  - **`wow64native.dll`** (PE, base 0x7a400000). Los thunks 32→64 tienen que quedar debajo de 4 GiB.
  - **Lado Unix:** `unix.c` compilado para Orbis, enlazado en el ELF y registrado como `wow64native.so` en `platform/ps4/pw_wine_unixlibs.c`.
    - Pregunta a ntdll `__wine_prospero_native_wow64_caps(1)` y exige los bits 1 y 2.
    - En PS5 exige también el 4. Acá no se exige porque ntdll en Orbis no guarda xstate en el contexto de señal. Lo deja logueado: `PWNATIVE wow64native caps=3 (no xstate in exception contexts)`.
    - Consecuencia: una excepción en código de 32 bits no lleva la mitad alta de los YMM.
  - **`wow64.dll`:** `WINE_PS4_WOW64_CPU` acepta `wow64native.dll` o `wowprospero.dll` (parche 0611). Si `BTCpuProcessInit` de wow64native falla, carga `wowprospero.dll` y el programa sigue en el traductor (parche 0614): `wow64native.dll did not start (...); using wowprospero.dll`.
- `tools/build-signal-ps4.py`: el contexto inicial de 32 bits lleva CS 0x33 (`cs32_sel`), como en la rama FreeBSD de Wine. En Orbis era 0, cosa que sólo toleraba el traductor.
- `native/wine_hardware.c`: un PE32 se lanza con `--wow64-cpu=wow64native.dll` (en el log, `cpu=wow64native`).

## Qué se espera

- Si arranca nativo:
  - `wow64: CPU wow64native.dll from WINE_PS4_WOW64_CPU`;
  - `wow64native initialized: cs32=0033 ss32=003b cs64=0043 avx=...`.
- Si no, la línea de caída al traductor, y el programa anda como en W136.
- Lo que hay que mirar: que gui-window32 abra y cierre, y los FPS del menú de SuperMarioKart. En el traductor eran unos 12.

## Prueba física: 20261103T041814Z

El usuario confirmó que los dos programas arrancaron. En el log de cada uno:

    wow64: CPU wow64native.dll from WINE_PS4_WOW64_CPU
    PWNATIVE wow64native caps=3 (no xstate in exception contexts)
    wow64native initialized: cs32=0033 ss32=003b cs64=0043 avx=1

**El código de 32 bits corre nativo en la PS4.**
- gui-window32 terminó con `process_exit status=0`.
- SuperMarioKart llegó al menú. Hubo excepciones de Wine resueltas (`RtlUnwindEx ... cs=0043`), es decir, el camino de excepciones desde código nativo anduvo.

### FPS

El menú de SuperMarioKart hace los mismos FPS que en el traductor:
- W134 (traductor): 11,4–12,0.
- W137 (nativo): 11,5–12,0.

Así que la CPU de 32 bits no era el límite. La curva es plana en 12, lo que apunta a la presentación (ddraw → wined3d Vulkan → copia a CPU → GDI → sink) o a un ritmo fijo del juego, no al cálculo. El log de ddraw/file/virtual de los PE32 es de unas 500 líneas por segundo: no alcanza para explicar el tope, pero conviene sacarlo al medir.
