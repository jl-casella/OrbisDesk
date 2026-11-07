# Escritorio W284 en el fork Linux de shadPS4

[English](SHAD_W284_DESKTOP.md) | [Español](SHAD_W284_DESKTOP-es.md)

Fecha: 2026-11-07. Resultado: escritorio de OrbisDesk W284 (03.83) confirmado visualmente en WSLg; el ELF W284 conserva su hash original. No se modificó ni transfirió el paquete PS4 en esta iteración. Las fuentes W286 que se están editando en paralelo no forman parte de esta validación.

## Correcciones generales del fork

- ET_SCE_EXEC usa las direcciones enlazadas, con sesgo de reubicación cero. La reserva, el trampolín, las búsquedas por dirección y el tamaño de imagen se calculan sobre la extensión real de los segmentos, sin incluir el hueco anterior al primer PT_LOAD. ET_SCE_DYNEXEC conserva su ruta anterior.
- sigsetjmp/siglongjmp y las variantes setjmp/longjmp guardan/restauran registros, control de FPU y máscaras según el ABI FreeBSD. Las entradas se enlazan sin un wrapper C que introduzca un marco adicional en el contexto guardado.
- Cada hilo invitado tiene una pila alternativa del anfitrión para señales.
- getppid ofrece un punto de entrada de syscall libkernel. Se despachan PID, PPID, sigaction, write y exit a los servicios del emulador. Las llamadas desconocidas devuelven ENOSYS, con el indicador de acarreo correspondiente.
- Los contextos traducen selectores CS Linux 0x33/0x23 a PS4 0x43/0x33 y viceversa. El CS 0x43 está observado también en la corrida física W284 archivada.

Las funciones de salto usan como referencia el layout de [FreeBSD amd64 sigsetjmp](https://github.com/freebsd/freebsd-src/blob/releng/9.3/lib/libc/amd64/gen/sigsetjmp.S) y conservan su atribución/licencia en el archivo nuevo.

## Validación y límites

La reproducción OpenOrbis `native/shad_platform_check.c`, construida con `python3 tools/build-shad-platform-check.py`, confirmó seis resultados: fixed_pointers, longjmp_zero, saved_mask, signal_recovery, raw_syscalls y signal_cs. Entrega ELF/SELF: `build/shad-platform-check/app/eboot.bin`. Su prueba física se mantiene pendiente; es una reproducción independiente de Wine para compartir. El diagnóstico enlaza -lkernel antes de -lc para no mezclar sigsetjmp importado con siglongjmp estático de musl: sus buffers no son intercambiables.

La corrida de Wine confirmó servidor, ntdll PE64, entrada a inicialización Windows, prueba raw de señales, presentación y monitor activo de Explorer. La captura `reports/shad-w284-desktop/desktop.jpg` muestra fondo, File Manager y barra Start. El intento de clic adicional se detuvo porque Computer Use detectó entrada del usuario; no se reintentó ni se da por aprobado ese clic.

RADV sobre GNM no inicia en este fork: la imagen usa la ruta real de copia CPU. No se valida Vulkan/Direct3D ni ejecución nativa PE32. El marcador de una prueba nativa previa realmente intentada permanece: el launcher informa native32=0, skipped y errno=17. No se escribió un resultado aprobado ni se simuló capacidad. Una copia totalmente nueva que vuelva a ejecutar la prueba nativa sigue requiriendo investigar selectores y el enlace de saltos del SDK; no se afirma arranque limpio sin esa limitación. No se agregó pe32relaunch.txt ni se modificó el EXE.

## Reproducción

En Ubuntu-22.04, desde la raíz del workspace:

```sh
python3 tools/build-shad-linux.py --reuse-configure --jobs 12
python3 tools/build-shad-platform-check.py
python3 tools/run-orbisdesk-shad.py --build W284
```

El último comando reutiliza la copia privada de desarrollo registrada en `build/orbisdesk-shad-visible.json`. --fresh crea otra copia desde el runtime original y vuelve a exponer la limitación de la prueba nativa descrita arriba. No escribe en el runtime de la build ni en la consola. Se limita coredump_filter sólo en el proceso hijo para evitar volcados enormes de los espacios reservados.

El parche de trabajo está en `patches/shadPS4/pending/0018-fixed-executable-and-kernel-signals.patch`. Se aplica sobre el commit 9ac99bb2445e86f525519a4041a6c85362790ad2 con git apply. No se alteró fork.lock.json para aparentar un commit nuevo: el manifiesto de compilación registra explícitamente source_dirty y el SHA256 del diff completo.

Evidencia, manifiestos y logs: `reports/shad-w284-desktop/`. La captura tiene el manifiesto de la ejecución que la produjo; el cierre final de formato y tamaño se compila aparte y conserva su propio manifiesto.

Durante esta tarea se retiraron sólo dos volcados temporales WSL de los PID 393499 y 395815, generados por los intentos fallidos iniciales (unos 34 GB). Se conservaron los paquetes, logs y el runtime W283. Los dos OELF intermedios de W284 retirados previamente son regenerables; el ELF y el paquete se conservaron.

## Cierre final

La compilación final conserva el diff SHA256 `d37d54454bc340c54e15c2a867c76c5fcca58a3eee860c81d0b1ed72fff4e30f` y el binario SHA256 `95fedb2030bb9ce9212eb0a8c0780b795bcdb38879246795775134e21e4dd0fa`. Las seis comprobaciones OpenOrbis se repitieron sobre ese binario y aprobaron. El launcher verificó ambos hashes antes del último arranque. La captura final `reports/shad-w284-desktop/desktop-final.jpg` confirma nuevamente el escritorio; `run-0010.log` conserva raw=1, monitor GUI activo y ningún registro W284 crash. La ventana quedó abierta (PID 408085 en esta sesión; no es identificador persistente).
