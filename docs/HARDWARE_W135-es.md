# W135: ¿corre la PS4 código de 32 bits nativo? (fase 5)

[English](HARDWARE_W135.md) | [Español](HARDWARE_W135-es.md)

APP_VER 02.34. Base W134 (fase 4b aceptada: SuperMarioKart muestra el menú).

## Probe

`native/compat32_probe.c`, llamado por el lanzador antes de Wine, una vez por build: deja un marcador antes de intentar, así que si la prueba tira el título no lo hace en cada arranque.
- Toma una página RWX debajo de 4 GiB (0x30000000).
- Hace `lretq` al selector **0x33** (código de 32 bits, GDT de amd64 de FreeBSD, el mismo que usa el `wow64native` de prospero-win en PS5).
- En modo compatibilidad ejecuta `mov dword [abs32], 0x32BEEF32` y `retf` a **0x43**, y vuelve con el `rsp` y la continuación guardados.
- Un fallo termina por `siglongjmp` y se reporta.

## Resultado físico: 20261103T034008Z

`compat32_probe native32=1 page=0x30000000 cs=0x43 cs_after=0x43 result=0x32beef32 signal=0`. El kernel de la PS4 (fw 12.52) **permite ejecutar código de 32 bits en modo compatibilidad desde la app**. El segundo arranque saltó la prueba por el marcador. Llegó al escritorio (confirmado por el usuario en la página).

Ya conocido de antes: `ucontext` de Orbis con `mc_fpstate` en +320 y `mc_fsbase` en +1152 (`platform/ps4/pw_wine_context.h`, igual que lo medido por prospero-win en PS5), y `sysarch` para las bases de segmento.

Siguiente paso si se elige: portar `wow64native`:
- `wine/wow64native/{cpu.c,unix.c}`;
- la entrada de señales de la parche 0883, que recupera la base FS del host cuando una señal llega en código de 32 bits;
- la caída al traductor si falla, como la parche 0614.
