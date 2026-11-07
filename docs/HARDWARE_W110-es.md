# W110: entradas omitidas por la enumeración de Wine

[English](HARDWARE_W110.md) | [Español](HARDWARE_W110-es.md)

APP_VER 02.09. Los logs W109 ya muestran el bloqueo: el servidor ve koopa beach_fast.mid y CARMEN09.BMP, pero WFM no intenta DeleteFile para ellos. Sólo registra el hijo SMK y luego RemoveDirectory da 145. Los diez reintentos encuentran la misma entrada real. Por tanto, la hipótesis de cierre pendiente no explica esos intentos: hay archivos que no llegaron a la enumeración Win32.

Evidencia: reports/wine-hardware-w109/physical/20261102T172145Z/analysis.json. El primer arranque terminó con 0; el segundo seguía en el escritorio al recoger los logs. No se validó renombrado en esta sesión. No hubo borrado por FTP.

## Cambios

Se recompila únicamente el objeto Unix file de ntdll con su receta probada, desde la fuente guardada cuyo hash debe coincidir. Se sustituye exactamente uno en el enlace sin ejecutar el preparador ni cambiar objetos base.

- Una identidad sin inode no se registra ni compara como identidad de un directorio oculto (prefix/dev/proc). Es una protección ante metadatos no disponibles de PS4, sin inventar inode; no está demostrado aún que sea la causa de esta omisión concreta.
- read_directory_data_readdir distingue EOF de error, preserva el error y descarta la enumeración fallida en vez de publicar una lista parcial como éxito. WFM ya conserva el error antes de empezar a borrar hijos.
- PWDIRENUM registra entradas nativas, coincidencias de máscara, errores de stat, filtrado por identidad y entradas devueltas, además del final de lectura. El parser nativo registra un dirent inválido o fallo de getdents con sus campos.
- Se conservan WFM, apertura de documentos/EXE, rename, auditoría de servidor y reintento limitado anteriores. No se altera el escritorio en esta build.

```sh
python3 tools/build-wine-directory-ps4.py
python3 tools/build-wine-hardware.py --mangohud enabled
python3 tools/upload-hardware.py --build W110 --host 192.168.68.104 --timeout 60
```

Requiere los artefactos previos de telemetry y delete-server. Matriz local omitida. No se declara resuelto el borrado antes de la prueba en consola.

Prueba: en WFM entrar en la carpeta que falló y ver si lista sus archivos; repetir borrado de una carpeta de prueba con subcarpetas/archivos. Si sigue fallando, conservar el árbol y avisar el código. La lectura fallida puede mostrar ahora un error distinto en vez de 145; eso no se contará como éxito.

```sh
python3 tools/fetch-hardware.py --build W110 --host 192.168.68.104
```

Desktop con archivos/carpetas, icono de asociación para enlaces a textos y refresco sigue como trabajo posterior. La calibración CPU/GPU está aplazada.

Compilación completada; runtime de 548 archivos idéntico a W109 por hash. Se verificó la sustitución única del objeto file y se archivaron fuentes, manifiesto y receta en reports/wine-hardware-w110/release-w110. PKG SHA-256: 982cf9c8ac3c32e51613c5c7fec7265a7a36c55e645e8e97326cfa6a4ce61639. ELF SHA-256: fe94175937805e9ad255109c12290928c1b77c6d8f6fbe7a9fb91a598f4a8af6.

Entrega completada con lectura de vuelta verificada: `/data/pkg/orbis-win-W110-982cf9c8ac3c.pkg`. Informe: reports/wine-hardware-w110/transfers/20261102T173510Z.json. 548 archivos verificados, 546 presentes y 2 subidos; sin fallos de permisos. W109 retirado después de verificar. Prueba física pendiente del usuario.

Primer aviso posterior: el recolector W110 dio no-log en 20261102T173705Z. Se inspeccionó FTP y se encontró w109/run-0003.log nuevo. Descargado como W109 20261102T173750Z; primera línea W109 entered_launcher. Se pidió cerrar OrbisDesk, instalar el PKG W110/02.09 y ejecutar. No es evidencia de ejecución o crash de W110. PKG W110 presente en /data/pkg; no se repitió transferencia.
