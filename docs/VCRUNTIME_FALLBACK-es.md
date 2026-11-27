# Las DLL del runtime de Visual C++ después de desinstalar un redistribuible (04.92)

[English](VCRUNTIME_FALLBACK.md) | [Español](VCRUNTIME_FALLBACK-es.md)

Los instaladores de juegos corren el redistribuible de Visual C++ de Microsoft (`vc_redist.x86.exe`, `vc_redist.x64.exe`) dentro de OrbisDesk con el `msiexec` de Wine. Por ejemplo, lo hace el Rockstar Games Launcher. El redistribuible reemplaza las copias de Wine de las DLL del runtime en `C:\windows\system32` y `C:\windows\syswow64` por las de Microsoft. Aparece en Agregar o quitar programas (`appwiz.cpl`) y se puede desinstalar ahí.

## Qué se rompía antes de 04.92

Desinstalar el redistribuible borraba las DLL que le pertenecían y no ponía nada en su lugar. Lo mismo pasaba con una instalación fallida que hacía rollback. Todo programa que importara esas DLL fallaba después al cargar con "DLL no encontrada".

- **Desinstalación.** El MSI de Wine borra todos los archivos de un componente que desinstala. La única excepción es una copia en disco con una versión más nueva que la del paquete (`dlls/msi/files.c`, `ACTION_RemoveFiles`). Se van el `vcruntime140.dll`, el `concrt140.dll`, el `vcomp140.dll` de Microsoft y los demás. El `msvcp140.dll` de Wine (14.50) es más nuevo que 14.44: el redistribuible nunca lo reemplazó y su desinstalación lo deja. Pero importa `vcruntime140.dll`, así que tampoco carga.
- **Rollback.** El MSI de Wine no guarda copia de los archivos que sobrescribe. El rollback de `InstallFiles` es `RemoveFiles`, corrido con el estado anterior de cada componente (`dlls/msi/action.c`, `need_rollback`). En una primera instalación ese estado es "ausente". Por eso el rollback borra las DLL que acababa de poner encima de las de Wine y no restaura nada. Windows guarda una copia y la restaura; Wine no. Cuando falla un paquete posterior de un bundle de Burn, el bundle desinstala los MSI que ya había completado, que es el caso de desinstalación de arriba. Esto pasó en la consola con el instalador del Rockstar Games Launcher, antes de que 04.80 arreglara `GetExitCodeProcess` para los invitados.
- **Sin recurso en el loader.** El loader de este Wine no recurre a `lib/wine` cuando falta una DLL en el prefijo. Lo hace solamente mientras se arma el prefijo (`dlls/ntdll/loader.c`, `find_builtin_without_file`). De todos modos, `lib/wine/<arch>-windows` no tiene el runtime de VC++.
- **Sin reparación.** El instalador del launcher copiaba los archivos del build sólo en el primer arranque de cada build. Un runtime subido por FTP no se reparaba nunca.

Evidencia, consola con GoldHEN y firmware 12.50, 2026-11-26, FTP de sólo lectura: el Rockstar Games Launcher instaló el redistribuible x86 14.44.35211. En `syswow64` estaban las copias de Microsoft de `vcruntime140`, `concrt140`, `vcomp140`, `vccorlib140`, `msvcp140_1`, `msvcp140_atomic_wait`, `msvcp140_codecvt_ids` y `mfc140*`. Sus componentes están registrados a los productos Minimum y Additional Runtime. `msvcp140.dll` y `msvcp140_2.dll` seguían siendo los de Wine. `system32` quedó igual: el paquete x64 se registró pero no instaló ningún MSI.

## La regla

Los archivos del runtime de VC++ son las familias de VC++ 2010–2022 (versiones 100 a 140) directamente en `system32` y `syswow64`: `msvcp`, `msvcr`, `vcomp`, `vcruntime`, `concrt`, `vccorlib`, `vcamp`, `atl` y `mfc` (`tools/console_state.py`, `is_vcrt_file`). El runtime de W303 tiene 45, todos builtins de Wine, 24 MB. Los redistribuibles de 2005 y 2008 instalan en WinSxS, no ahí. Quedan afuera `ucrtbase.dll` y `msvcrt.dll`: OrbisDesk los modifica, y el redistribuible no instala el UCRT en Windows 10.

Una copia es de Wine cuando lleva la firma `Wine builtin DLL` de winebuild después del encabezado DOS. Cualquier otra es de un redistribuible.

- **El builder** (`tools/build-wine-hardware.py`) se detiene si alguno no es un builtin de Wine: una copia de Microsoft distribuida por OrbisDesk nunca se actualizaría. Escribe una segunda copia de cada uno en `wine/lib/wine/vcrt-fallback/<system32|syswow64>/<nombre>`, con `wine/lib/wine/vcrt-fallback/list.txt` (`ORBISDESK-VCRT 1`, después `<sha256> <bytes> <carpeta>/<nombre>` por línea). Son archivos comunes del runtime, igual en el paquete que en un runtime subido por FTP. Ningún instalador es dueño de ellos, y Wine nunca los carga: busca los builtins en `lib/wine/<arch>-windows/<nombre>` y `lib/wine/<nombre>`. El builder también escribe las copias del prefijo como líneas `V` en `install.txt`, y `vcrt_fallback` en el manifiesto.
- **En cada arranque**, antes de que corra Wine, el launcher (`native/hw_install.h`, `hw_install_vcrt_repair`) revisa cada archivo de `list.txt`. Uno que falte en el prefijo se copia de nuevo desde `/data/wine/lib/wine/vcrt-fallback` y se verifica contra el SHA-256 de la lista. Un archivo presente nunca se toca. Esto corre tanto si el runtime vino en el paquete (primera instalación o ya al día) como si vino por FTP (`--runtime-outside-package`, "no_embedded_runtime").
- **Cuando se instala un build empaquetado nuevo**, un archivo `V` que no es de Wine se conserva: las DLL de Microsoft se quedan mientras el redistribuible esté instalado. Las copias de Wine se actualizan como siempre.
- **Las subidas por FTP** (`tools/upload-hardware.py`) conservan del mismo modo una copia del prefijo que no es de Wine. Suben las copias de respaldo como cualquier otro archivo del runtime.

Después de una desinstalación o de un rollback, las DLL vuelven en el siguiente arranque de OrbisDesk. Los programas que se abran en la misma sesión, después de desinstalar, siguen fallando hasta entonces. Una consola con un runtime anterior a esta regla no tiene `list.txt`; el log muestra `PWINSTALL vcrt no_fallback_list` y no se restaura nada.

Se eligió restaurar los archivos al arrancar en lugar de dos alternativas:

- Un recurso del loader a `lib/wine` cambiaría `ntdll` para todos los invitados. Además pondría copias cargables en `lib/wine/<arch>-windows`, que le ganarían a una copia más nueva del prefijo.
- Hacer que la desinstalación o el rollback dejen los archivos implicaría cambiar el comportamiento del MSI de Wine para todos los paquetes.

## Verificaciones

```sh
python3 tests/test_vcrt_fallback_host.py build/wine-hardware-w303/runtime
```

Esto verifica la regla de nombres, la ruta de respaldo y la firma. Compila `tests/vcrt_fallback_host_check.c` contra `native/hw_install.h` y lo corre en carpetas temporales que hacen de `/app0/runtime` y `/data`:

- un build nuevo conserva la copia de Microsoft e instala las que faltan y las más viejas;
- después de una desinstalación, vuelve la copia de Wine y otra copia de Microsoft queda intacta;
- después de un rollback que borró dos copias, vuelven las dos;
- sin runtime en el paquete, una copia faltante igual se restaura;
- una copia de respaldo dañada se rechaza por su hash, y no se escribe nada;
- sin faltantes, no se restaura nada.

Si se le pasa una carpeta de runtime, también verifica que todos sus archivos del runtime de VC++ sean builtins de Wine. Es un modelo en el host: no corre Wine, MSI ni la consola.

En la consola, con un build que traiga esta regla (empaquetado, o con su runtime subido):

1. Abrir OrbisDesk. El log del launcher muestra `PWINSTALL vcrt checked=45 present=45 restored=0`.
2. Desinstalación: quitar "Microsoft Visual C++ 2015-2022 Redistributable (x86)" en Agregar o quitar programas.
3. Cerrar OrbisDesk y volver a abrirlo. El log muestra `PWINSTALL vcrt restored syswow64/vcruntime140.dll` por cada DLL borrada. Abrir un programa de 32 bits que importe `msvcp140.dll`/`vcruntime140.dll`.
4. Reinstalar el redistribuible, o el launcher que lo trae, y verificar que se instala otra vez. En el arranque siguiente, `restored=0`.
5. Rollback: arrancar un instalador que corra `vc_redist.x86.exe` y cancelarlo después de que se copien los archivos del redistribuible, o dejar que falle un paso posterior. El log del instalador muestra el rollback. Después repetir el paso 3.
