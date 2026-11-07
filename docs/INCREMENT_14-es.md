# Incremento 14: directorios PS4 y diagnóstico de wineboot

[English](INCREMENT_14.md) | [Español](INCREMENT_14-es.md)

**Wine conserva server_ready y ya no invoca los CommonStub observados en el incremento 13. El EXE todavía no se ejecuta.** La nueva traza confirma que el proceso auxiliar solicitado es `C:\windows\system32\wineboot.exe`, máquina
8664. Se rechaza explícitamente con STATUS_NOT_SUPPORTED dentro del alcance inicial de un único proceso.

El intento termina después con STATUS_DLL_NOT_FOUND (0xc0000135), al resolver `/data/console32.exe` en el prefijo de desarrollo vacío. No existen unidades DOS preparadas allí. El runner conserva el código completo del invitado, `-1073741515`; el código 53 del host corresponde a sus ocho bits bajos. Wine_booted y windows_execution_verified siguen en false.

## Adaptación del runtime

Este incremento modifica el runtime PS4, el overlay de Wine, las pruebas y el launcher. Mantiene el emulador en la revisión f42070cabeb048cb0247711d7f30ad6f115ceba6.

La libc del SDK entraba a _fstat desde fdopendir. El port ahora proporciona opendir/fdopendir/readdir/closedir/rewinddir/dirfd propios sobre sceKernelGetdents y la conversión de stat existente. Se valida la estructura Orbis, su tamaño de registro y el nombre terminado en cero, y se produce una entrada del SDK. Cada stream conserva su descriptor, buffer y posición; el cierre libera la propiedad y los registros asociados. No se añade un alias _fstat que escriba una estructura incompatible en el buffer del SDK.

openat resuelve AT_FDCWD contra el cwd del módulo cliente o servidor. Para un descriptor de directorio registrado, usa su ruta y conserva el registro al duplicarlo. Las rutas absolutas ignoran dirfd. Los registros se sincronizan con open/close/dup para impedir reutilizar una ruta antigua después del cierre. La implementación es un subconjunto basado en rutas: un directorio recibido por mecanismos que no registran su ruta devuelve ENOTSUP. La renombración de directorios se rechaza, y cambios externos de sus rutas no están validados. La tabla del port admite 256 registros de directorio y devuelve EMFILE al agotarse. No equivale a implementar openat completo dentro del kernel.

La consulta de cantidad de CPU aún carece de un adaptador verificado. Se devuelve -1/ENOTSUP; Wine usa su fallback existente de una CPU. El resultado no demuestra afinidad ni topología de PS4. Las demás consultas sysconf se delegan al SDK; se verifica el tamaño de página de 16384 bytes.

spawn_process registra ImagePathName y devuelve STATUS_NOT_SUPPORTED antes de tocar stdin/stdout o ejecutar fork. La ruta de reexec también tiene rechazo explícito para Orbis, aunque no se alcanza en el intento final. La prueba real ejercita el rechazo de wineboot y comprueba el error c00000bb que recibe Wine.

Los helpers se compilan ahora explícitamente con -D__ORBIS__, además del target FreeBSD de PS4. Esto selecciona el adaptador nativo de directorios. Los flags quedan registrados en link-report.json; el SDK original permanece intacto.

## Validación

Pasan once comprobaciones OpenOrbis en `--fs-services`:

- Apertura relativa en namespaces cliente/servidor y ruta absoluta con dirfd inválido.
- Dup de directorio y funcionamiento después de cerrar el descriptor original.
- Errores de ruta, descriptor y tipo, conservando el archivo tras fallar fdopendir.
- Rechazo explícito de dirfd sin ruta registrada.
- Enumeración de 40 nombres largos, cruzando el buffer de 4096 bytes.
- Rewind y segunda enumeración completa.
- Cierre del stream y reutilización del descriptor con otro directorio.
- EOF de directorio vacío, aceptando las entradas punto y punto-punto.
- Rechazo de renombración de directorio.
- Contrato de error de CPU y tamaño de página, más la preparación de fixtures.

Los controles negativos validan errores; no cuentan como capacidades soportadas. La suite completa también conserva cuatro regresiones de plataforma, quince controles IPC y diez de pipes. La prueba GS y la suite mixta de servicios mantienen sus bloqueos conocidos. Todo corresponde al fork Linux bajo WSL; hardware y otros hosts siguen pendientes.

El mismo ELF se ejecutó en shadPS4 oficial: diez controles de la suite filesystem pasan y la duplicación queda bloqueada, con llamadas a los stubs dup/fcntl. El invitado termina con 92 y el cierre del emulador agota el timeout. Estos datos se conservan separados de la ejecución completa de once controles en el fork.

`tools/check-wine-fs.py` compila y ejecuta los algoritmos de rutas en Linux con ASan, UBSan y detección de fugas. El binario instrumentado no usa PIE. Su informe registra comandos, hashes de fuentes y binario y código de salida. Esta prueba usa el filesystem real del host para los algoritmos; la estructura de Orbis se comprueba por separado en el homebrew.

## Reproducción y evidencia

```sh
python3 tools/build-wine-ps4.py --boot --all-unix
python3 tools/build-wine-ps4.py --boot --server
python3 tools/link-wine-boot.py
python3 tools/check-wine-fs.py
python3 tools/check-increment14.py
python3 tools/check-increment14.py --verify-only
```

`reports/increment14/report.json` indexa las ejecuciones y sus hashes. `reports/increment14/host-fs` conserva la prueba instrumentada. Las cápsulas wine-boot y emulator del mismo incremento guardan binarios y fuentes fijadas; el verificador contrasta los ELF exactos de los archivos runtime.tar.gz. Los resultados anteriores se conservan en sus propios incrementos.

## Próximo hito

Preparar y verificar un prefijo fuera de consola, con unidades DOS, módulos y registro adecuados. Su validación debe incluir enlaces e identidad de archivos: el backend actual aún tiene limitaciones de lstat/readlink y de dev/ino.

El primer proceso de Wine llama a run_wineboot incluso con una estructura de directorios presente. El port necesita una política explícita para consumir un prefijo externo validado en su modo de un único proceso. Crear sólo las carpetas no inicializa el prefijo. Después quedan carga de ntdll PE64, GS por hilo y la integración del proveedor WoW64 con el traductor, antes de comprobar el resultado de console32-bare.exe.
