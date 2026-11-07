# Prueba física W002: prefijo sin enlaces simbólicos

[English](HARDWARE_W002.md) | [Español](HARDWARE_W002-es.md)

W002 reemplaza a W001: mismo Title ID `ORBW00002`, APP_VER 01.01, mismo runtime en `/data`. Las fuentes de W001 están en `reports/wine-hardware-w001/release-w001/` y se verificaron contra los hashes de su manifest.

## Qué mostró W001

W001 se detuvo en la consola antes de arrancar Wine, con `readlink` en ENOSYS y `dup2` en -1 (ver [HARDWARE_W001.md](HARDWARE_W001-es.md)). La investigación encontró dos causas distintas.

1. **Orden de bibliotecas en el builder de hardware.**
   - El ELF de Wine probado (`build/wine-boot/bootstrap.elf`) importa `lstat` y `readlink` de libkernel.
   - `build-wine-hardware.py` insertaba `-L<sdk>/lib` delante de `build/wine-boot/lib`. Con eso, `-lc` resolvía a la `libc.a` del SDK, cuyo `readlink` y `lstat` son syscalls FreeBSD directas.
   - Ni el fork ni, según el log, la consola las atienden desde una app.
   - El builder conserva ahora el orden probado. Además falla si alguna importación del ELF probado queda como definición estática en el ELF de hardware.
2. **Los enlaces de unidad.**
   - Aun con las importaciones correctas, una app no tiene forma probada de crear los enlaces `dosdevices/c:` y `z:`: el fork no implementa `symlink`, y en hardware tampoco está demostrado.
   - `platform/ps4/pw_wine_fs.c` tiene ahora una tabla de montaje fija:
     - `<prefix>/dosdevices/c:` → `<prefix>/drive_c`;
     - `<prefix>/dosdevices/z:` → el directorio padre del prefijo, como el `../..` del paquete del incremento 15.
   - Toda ruta que pasa por esas entradas se reescribe antes de llegar al kernel. `pw_wine_readlink` informa el texto del enlace, y `pw_wine_realpath` lo usa.
   - `native/wine_boot.c` registra la tabla después de `pw_wine_init_paths`.
   - Si el destino no existe, falla con el error real de ese destino.
   - El preflight lee los enlaces y la identidad del archivo mediante esa tabla.

<a id="launcher"></a>


## Lanzador

- Registra en el log el resultado y el errno de `dup2`. Si `dup2` no funciona, prueba `fcntl(F_DUP2FD)` con el valor de FreeBSD (10), porque `fcntl` es la importación de libkernel. Ninguno de los dos cierra descriptores antes de tener éxito, y la redirección sólo cuenta si una sonda escrita por fd 2 hace crecer el log.
- Antes de llamar a Wine registra cinco sondas:
  - `lstat` y `stat` de `drive_c`;
  - `readlink` de un directorio, que debe dar EINVAL;
  - la tabla de montaje;
  - la resolución de `C:\orbis\console32.exe`.
- Un `result.txt` previo se archiva con `sceKernelRename`.

## Smoke test en el fork

`reports/wine-hardware-w002/20261031T060734Z/`: **pasó**.

- `console32-bare.exe` corre mediante Wine y wowprospero dentro del launcher empaquetado.
- `result.txt` es idéntico al de Windows y la salida es 0.
- Los 12 casos del preflight pasan.
- Ningún stub después de entregar el control a Wine.
- En el fork, `dup2` es un stub y `fcntl(F_DUP2FD)` devuelve EOPNOTSUPP (45), así que la salida de Wine no se redirige en el emulador. Eso no afecta el resultado.

## Estado

PKG en `/data/pkg/orbis-win-W002-b19780829b4a.pkg`, verificado leyéndolo de vuelta. Los 430 archivos del runtime ya estaban en la consola con el hash correcto. Registro: `reports/wine-hardware-w002/transfers/20261031T060926Z.json`.

## Resultado físico

El usuario lo corrió dos veces y la app se cerró con error. Los logs `run-0001.log` y `run-0002.log` están en `reports/wine-hardware-w002/physical/20261031T061129Z/` y son idénticos:

```
W002 stderr_redirect method=dup2 out=-1 errno=1 err=-1 errno=1 verified=0
W002 stderr_redirect method=f_dup2fd out=-1 errno=22 err=-1 errno=22 verified=0
W002 sysmodule_net rc=0x00000000
W002 probe libc_lstat rc=-1 errno=1 dir=0
W002 probe kernel_stat rc=0 errno=0 dir=1
```

Lo que muestran esos logs:
- En la consola, `dup2` sobre los fd 1/2 devuelve EPERM y `fcntl(F_DUP2FD)` devuelve EINVAL.
- `lstat` devuelve **EPERM** y `sceKernelStat` funciona.
- El proceso termina en la sonda siguiente, la única que llama a `readlink` directamente. El log no dice cómo termina: la app no llega a registrar nada más.
- Wine no se llamó.

`fetch-hardware.py` lo clasificó como `no-log`. Esa clasificación busca marcadores con `rc=`, y estos registros usan otro formato. El estado real es una caída en la sonda de `readlink`. W003 corrige el launcher y la plataforma (ver [HARDWARE_W003_W011.md](HARDWARE_W003_W011-es.md)).
