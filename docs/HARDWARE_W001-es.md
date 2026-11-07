# Prueba física W001: Wine en la PS4

[English](HARDWARE_W001.md) | [Español](HARDWARE_W001-es.md)

W001 es el primer intento de arrancar Wine en hardware. Antes pasaron H001 y H001B, que probaron la plataforma básica sin Wine (ver [HARDWARE_H001.md](HARDWARE_H001-es.md)).

- Sumese: **OrbisDesk Wine W001**, Título ID `ORBW00002`.
- Consola destino: la PS4 Pro de H001.
- El launcher (`native/wine_hardware.c`) se enlaza con los mismos objetos de Wine que pasaron `console32-bare.exe` mediante wowprospero en el incremento 23. `tools/build-wine-hardware.py` lo verifica contra los hashes de `build/wine-boot/link-report.json`.
- En la consola, el launcher hace en orden:
  1. abre `/data/orbis-win/w001/run-NNNN.log`;
  2. intenta redirigir stdout y stderr a ese log;
  3. crea los enlaces `dosdevices/c:` y `z:`;
  4. si hay un `result.txt` previo, lo archiva;
  5. llama a `pw_wine_boot_main --prepared-prefix --wow64-cpu=wowprospero.dll`.

  En pantalla queda la etapa alcanzada.

El runtime no viaja dentro del PKG: son 430 archivos y 294 MB. Se copian por FTP a `/data`:
- `wine-prefix`, sellado del incremento 15;
- `wine-home`;
- `wine/lib/wine/{i386,x86_64}-windows`;
- `wine/share/wine/nls`.

Cada archivo se verifica leyéndolo de vuelta. El ejecutable `console32.exe` queda en `drive_c/orbis`.

## Cambios del launcher tras el smoke test

- **El marcador ahora sale de un efecto medido, no del valor que devuelve `dup2`.**
  - En el fork, `dup2` es un stub que devuelve 0 sin redirigir nada. El primer smoke test terminó con un log vacío.
  - Ahora el launcher escribe una sonda por fd 2 y comprueba que el log creció. El resultado queda en `W001 stderr_redirect ... verified=0|1`.
  - Los marcadores del launcher se escriben directo al log, sin depender de la redirección.
- **Los enlaces de unidad no se pueden probar en el emulador.**
  - La libc del SDK implementa `readlink` y `symlink` como syscalls FreeBSD directas (57 y 58). El stub de libkernel no los exporta.
  - El fork no atiende syscalls directas y devuelve ENOSYS (78).
  - `tools/run-wine-hardware.py` clasifica de forma explícita como `emulator-limit` la corrida que se detiene exactamente en `W001 drive_c rc=78` con sólo el stub `_dup2`. Esa clasificación no es un `passed`.
  - Lo que queda después de los enlaces sólo se prueba en la consola.

Prueba de humo: `reports/wine-hardware-w001/20261031T054609Z/` (`emulator-limit`).

## Herramientas

```sh
python3 tools/build-wine-hardware.py
python3 tools/run-wine-hardware.py              # smoke en el fork
python3 tools/upload-hardware.py --build W001   # PKG + runtime, lectura de vuelta por hash
python3 tools/fetch-hardware.py --build W001    # log, cuadros y result.txt de la consola
```

Restricciones de `upload-hardware.py`:
- no borra nada remoto y salta los archivos cuyo hash remoto ya coincide;
- aplica `SITE CHMOD` 777/666 a `wine-prefix` y `wine-home`, para que Wine pueda escribir el registro, y 644 al resto.

`fetch-hardware.py` guarda la evidencia en `reports/wine-hardware-w001/physical/<ts>/` y clasifica la corrida así:
- `passed`: `result.txt` idéntico a la referencia de Windows y salida 0;
- `blocked`: hay código de salida, pero no se cumple lo anterior;
- `crashed`: hay marcadores, pero no hay salida.

## Estado

El PKG está en `/data/pkg/orbis-win-W001-255931edb0ce.pkg` (7.340.032 bytes).

Subida del runtime: 430 archivos y 293.681.470 bytes, todos verificados leyéndolos de vuelta. Sin fallos de `chmod`.

- El primer intento se cortó por un timeout del control de FTP.
- El uploader ahora reconecta y reintenta cada paso. La segunda pasada encontró 320 archivos ya correctos y subió 110.
- Registro: `reports/wine-hardware-w001/transfers/20261031T055154Z.json`.

## Resultado físico

**Resultado: `blocked`.** El usuario instaló W001 y lo ejecutó cinco veces, de `run-0001.log` a `run-0005.log`. Las cinco dan lo mismo:

```
W001 stderr_redirect dup2_out=-1 dup2_err=-1 verified=0
W001 sysmodule_net rc=0x00000000
W001 drive_c rc=78
```

Evidencia: `reports/wine-hardware-w001/physical/20261031T055531Z/`. Hay una primera recolección, que clasificaba esto como `crashed`, en `20261031T055338Z/`. Wine no llegó a arrancar.

**Qué se sabe:**
- En la consola, `readlink`, que la libc del SDK emite como syscall FreeBSD directa, devuelve **ENOSYS**, igual que en el fork. Lo más probable es que `symlink` corra la misma suerte, pero no se llegó a llamarla, porque el launcher se detiene en `readlink`.
- Una app de PS4 no puede consultar enlaces simbólicos por esa vía, y probablemente tampoco crearlos.
- `dup2` devuelve -1, y esta versión no registró el errno.

**Consecuencia.** El diseño del prefijo supone enlaces simbólicos:
- `dosdevices/c:` y `z:`;
- el preflight del incremento 19, que hace `readlink` de ambos;
- la resolución de rutas de `pw_wine_fs.c`, que sigue enlaces con `readlink`.

Esa suposición no vale en la consola. El siguiente paso es un prefijo sin enlaces del sistema de archivos. No hay afirmación de que Wine arranque en hardware.

Lo que más probablemente aparezca primero en consola es la memoria ejecutable: código PE64 mapeado de archivo y el arena del traductor de wowprospero. H001 no probó JIT ni `PROT_EXEC`. Si el log se detiene ahí, el paso siguiente es una sonda aislada H002.
