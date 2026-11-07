# W111: filtrar registros BSD de entradas borradas

[English](HARDWARE_W111.md) | [Español](HARDWARE_W111-es.md)

APP_VER 02.10. W110 confirmado y recogido en 20261102T174008Z: getdents devuelve CARMEN09.BMP y el nombre anterior de una carpeta renombrada, pero stat falla con ENOENT. Después de la sesión, FTP SIZE/LIST tampoco encuentra esos nombres; la carpeta padre lista sólo . y ... El servidor is_dir_empty contaba ese nombre residual como contenido mientras ntdll lo omitía por fallo de stat. No era una espera de cierre ni un archivo realmente accesible que WFM omitiera borrar.

Evidencia: reports/wine-hardware-w110/physical/20261102T174008Z/analysis.json y stat-missing-ftp.json. No se modificaron archivos por FTP durante la investigación.

## Corrección del lector

El adaptador de PS4 copiaba cada registro de getdents como entrada activa, sin omitir d_fileno=0. Ese filtro forma parte de la semántica de readdir BSD: [implementación de FreeBSD](https://github.com/freebsd/freebsd-src/blob/main/lib/libc/gen/readdir.c) y [confirmación del criterio](https://lists.freebsd.org/archives/dev-commits-src-main/2026-February/039633.html). W110 no imprimía el inode del registro residual; su valor concreto en esa sesión no se da por medido. W111 implementa el contrato que faltaba y registra skipped_unused para validar el caso real.

pw_dirent_record.h valida primero cabecera y longitud; un slot con inode cero se salta avanzando por su longitud, sin usar su nombre residual. También omite DT_WHT (14) como readdir BSD con DTF_HIDEW; no es un archivo activo. Un slot activo requiere nombre válido y terminado. Un registro malformado mantiene EIO. El lector continúa hasta una entrada activa o el final, incluso entre páginas. No hace stat ni finge éxito de borrado. La misma corrección sirve a ntdll y al servidor in-process que comprueba si una carpeta está vacía. Conserva errno durante el log de slots omitidos.

Se conserva la propagación de errores W110, así como rename, apertura de textos/EXE, WFM y runtime PE. Desktop permanece como siguiente trabajo.

## Construcción y prueba

Comprobación puntual del decodificador real: mezcla de entradas activas, nombre residual borrado, slot vacío, whiteout y entrada válida posterior; rechaza longitudes/nombres malformados. Pasó en Linux, sin tocar archivos del usuario. Fuente native/wine_dirent_record_check.c, resultado build/w111-dirent-check.log. Sin matriz local; resultado real de PS4 pendiente.

```sh
gcc -Iplatform/ps4 native/wine_dirent_record_check.c -o build/w111-dirent-check
build/w111-dirent-check
python3 tools/build-wine-hardware.py --mangohud enabled
python3 tools/upload-hardware.py --build W111 --host 192.168.68.104 --timeout 60
```

Requiere las derivaciones directory-ps4 y delete-server ya construidas y verificadas por hash. El builder recompila el adaptador FS que incluye el decodificador y sustituye el objeto explícitamente; no modifica Orbis ni shadPS4.

Prueba física: borrar la carpeta que quedó vacía; crear un árbol descartable, renombrarlo, borrar contenido y carpeta, y revisar que no aparezcan nombres viejos ni error 145. Confirmar Start y apertura de un texto después.

```sh
python3 tools/fetch-hardware.py --build W111 --host 192.168.68.104
```

Aceptar sólo con skips de slots sin inode cuando existan, rmdir real con rc=0 y ausencia de la carpeta; no por una respuesta simulada de is_dir_empty.

Compilación completada. Runtime de 548 archivos idéntico a W110; se verificó el objeto FS nuevo en el enlace. Fuentes, prueba puntual y manifiesto en reports/wine-hardware-w111/release-w111. PKG SHA-256: e8585b70c409f7aca16093049940f9698ca9240f273bd37b34db7c56f859c16d. ELF SHA-256: 060bb52333fd4b4687c3f67013003f273ff8d6fddd5cd1a4dff5904e99829f06.

Entrega completada con lectura de vuelta verificada: `/data/pkg/orbis-win-W111-e8585b70c409.pkg`. Informe: reports/wine-hardware-w111/transfers/20261102T175415Z.json. 548 archivos verificados, 546 presentes y 2 subidos; sin fallos de permisos. W110 retirado después de verificar. Prueba física pendiente del usuario.

## Resultado físico: 20261102T180132Z

198 omisiones registradas, todas con inode=0 (pueden incluir la misma ranura en lecturas repetidas). is_dir_empty devuelve 1 y el rmdir nativo de la carpeta que fallaba devuelve rc=0. FTP posterior confirma que la carpeta ya no existe. El falso 145 por registros borrados queda resuelto en este caso real.

Rename nativo también devuelve 0 al cambiar la carpeta de Documents a Where in the World is Carmen Sandiego. FTP confirma ausencia del nombre viejo y presencia del nuevo con espacios. No se registran errores de borrado. Análisis y comprobaciones FTP en reports/wine-hardware-w111/physical/20261102T180132Z/analysis.json.

Límites: no se registra una eliminación de árbol completo con archivos activos en esta sesión ni la salida final del título. Falta ese caso para acreditar la operación recursiva completa; no hace falta otra build para probarlo.

Confirmación posterior del usuario: «Borró todo correctamente», después de la solicitud de crear/borrar árbol con contenido activo. Se acepta ese caso por feedback físico. La descarga 20261102T180735Z no agregó operaciones de filesystem al log; no se presenta esa descarga como prueba automática del árbol completo. Aceptación y fuentes de evidencia en reports/wine-hardware-w111/physical/20261102T180735Z/acceptance.json. El arreglo queda validado para el escenario probado; siguiente prioridad, mostrar archivos/carpetas y accesos correctamente en el escritorio.
