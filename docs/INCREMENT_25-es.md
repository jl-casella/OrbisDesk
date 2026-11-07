# Incremento 25: texto con FreeType para Orbis

[English](INCREMENT_25.md) | [Español](INCREMENT_25-es.md)

## Implementación

FreeType 2.14.1 se compila como archivo estático para x86-64 Orbis desde el submódulo `b91f75bd02db43b06d634591eb286d3eb0ce3b65`, fijado por el fork `9ac99bb2445e86f525519a4041a6c85362790ad2`. No se enlaza la biblioteca Linux del host ni la import library `libSceFreeType` del SDK. Se desactivan zlib, bzip2, PNG, HarfBuzz, Brotli y los resource forks de Mac.

El overlay activa el backend real de Wine y asigna sus punteros `FT_*` a las funciones enlazadas. `FT_Init_FreeType`, la carga de fuentes y la rasterización conservan sus errores reales. Ambos enlaces del runtime siguen exigiendo que no queden símbolos sin resolver.

FreeType usa `pw_wine_fstat`, el mismo adaptador de metadatos Orbis validado para Wine. La primera prueba con el backend Unix sin adaptar invocó el stub `_fstat`, obtuvo un tamaño inválido y falló; la reproducción y su ELF permanecen en `reports/linux-wine-runs/20261031T032646761159Z/`. Otra corrida alcanzó el dibujo pero falló al buscar un resource fork de un archivo inválido: `reports/linux-wine-runs/20261031T033339521922Z/`. La configuración para Orbis desactiva ese formato opcional; la prueba de archivo inválido se mantiene.

El staging GUI verifica hashes de Tahoma regular y negrita, sus fuentes SFD y las licencias. Los instala en `windows/Fonts` de la copia privada, con avisos en `Fonts/licenses`, y configura los registros de fuentes y sustituciones. Las entradas del registro contienen rutas Windows completas: Wine carga los archivos explícitamente durante `load_registry_fonts`. Con nombres relativos, el fixture privado funcionaba pero explorer no encontraba ninguna fuente para `MS Shell Dlg`; la corrida diagnóstica quedó en `reports/linux-wine-runs/20261031T035852362753Z/`. No se agregó un resultado ficticio de enumeración ni se modificó el emulador. El paquete original del incremento 15 permanece intacto. No se lanza wineboot. Ver [atribuciones](THIRD_PARTY_FONTS-es.md).

## Fixture y criterios

`gui-text64.exe` carga desde memoria los mismos bytes de Wine Tahoma tanto en Windows como en el invitado. Comprueba familia, métricas positivas, índices de glifos y dibujo mediante `TextOutW` sobre una DIB y sobre la ventana. Incluye números, acentos y eñe. Lee toda el área cliente, incluidos los voladizos de glifos que exceden su avance, y exige el mismo número de píxeles negros que en la DIB. Guarda `text-result.txt` y exige rechazo real de un archivo ausente y otro inválido.

La referencia nativa de Windows terminó con cero y produjo:

```text
passed=1;family_tahoma=1;painted=1;width=298;height=24;metric_height=24;ink=1397;window_ink=1397
```

No se exige igualdad exacta del antialiasing entre Windows y FreeType. Las tres corridas del fork deben pasar, presentar cuadros y terminar sin stubs de importación ni violaciones de acceso. El escritorio de explorer debe presentarse y seguir vivo hasta el timeout. La lectura visual del texto se comprueba en las capturas guardadas. El verificador busca la DIB con sus glifos en todos los cuadros, evitando el cuadro negro de cierre, y exige píxeles de la etiqueta Start en explorer (no alcanza con el icono).

## Regresión detectada al validar

El control sin proveedor WoW64 descubrió que la protección de la última sección privada de wow64.dll usaba `0x1d000` bytes. Orbis exige múltiplos de `0x4000`, y rechazó esa protección con EINVAL: Wine terminó con `0xc000007b` antes de buscar el proveedor. El fallo queda registrado en `reports/increment25/regressions24/report.json` y su corrida individual.

El overlay protege ahora el tamaño redondeado de esa misma sección, `0x20000`, que mmap ya había ocupado. No amplía el rango a otro mapping ni cambia permisos del archivo de origen. La prueba enfocada corregida está en `reports/linux-wine-runs/20261031T041520955811Z/`: alcanza el error esperado de proveedor ausente, `0xc0000135`, sin stubs de importación ni timeout. Se repiten todos los casos de Wine con el nuevo ELF; las pruebas nativas se pueden reutilizar sólo si conservan el mismo ELF y emulador.

## Reproducción

Sobre la construcción completa del incremento 24, en Ubuntu 22.04/WSL:

```sh
python3 tools/build-freetype-ps4.py
python3 tools/build-wine-ps4.py --boot --all-unix
python3 tools/build-win32u-ps4.py
python3 tools/stage-wine-gui.py
python3 tools/link-wine-boot.py
```

Desde PowerShell en Windows, generar una referencia nueva (el script rechaza sobrescribir una referencia terminada):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/reference-text25.ps1
```

Después, en WSL:

```sh
python3 tools/check-increment25.py --report-dir reports/increment25-reproduccion
python3 tools/check-increment25.py --verify-only --report-dir reports/increment25-reproduccion
```

La campaña de aceptación conservada se ejecutó sin sobrescribir las anteriores:

```sh
python3 tools/check-increment25.py --report-dir reports/increment25-accepted \
  --reuse-platform reports/increment25/regressions24
python3 tools/check-increment25.py --verify-only --report-dir reports/increment25-accepted
```

`--reuse-platform` verifica los contratos nativos y la matriz del incremento 18 ya archivados, exigiendo el mismo ELF nativo y emulador. Repite todos los casos de Wine, incluidos IPC, pipes, filesystem y metadatos, con el ELF nuevo. Omitir esa opción ejecuta también los contratos nativos desde cero.

El directorio por defecto es `reports/increment25/`; ya contiene la campaña de desarrollo, por lo que los comandos anteriores eligen uno nuevo. El verificador rechaza sobrescribir un informe final. Para cada campaña se debe elegir otro directorio mediante `--report-dir`, conservando también las campañas incompletas y sus logs. Incluye pruebas de staging válido, alterado y ausente, tres corridas de texto, explorer y las regresiones completas del incremento 24 en un directorio nuevo. Archiva el ELF, FreeType, fuentes, scripts, manifiestos, logs y capturas. Las corridas individuales conservan sus runtimes completos y hashes.

## Resultado y continuación

La campaña [de aceptación](../reports/increment25-accepted/report.json) terminó con **passed**, sin fallos, y conserva 124 hashes de artefactos, además de los hashes de informes, stdout y runtimes de las cuatro corridas principales.

| Comprobación | Resultado |
|---|---|
| Staging válido / fuente alterada / fuente ausente | Los tres contratos pasan; los inválidos se rechazan antes de ejecutar Wine |
| Texto PE64 en el fork | 3/3, salida 0; DIB y ventana tienen 1.252 píxeles negros y aparecen en el cuadro presentado |
| Explorer en el fork | Start visible, 77 píxeles de etiqueta verificados; timeout esperado, sin stubs de importación ni violaciones de acceso |
| Suite del incremento 24 | passed, 19 casos; se mantienen los bloqueos esperados del oficial, el prefijo vacío, la ausencia de CPU y exceptions |
|Console32-bare mediante Wine + wowprospero| passed con el ELF corregido; resultado idéntico a Windows |

La referencia Windows conserva 1.397 píxeles de tinta; no se equipara el rasterizador nativo de Windows al de FreeType. `Wine_booted` y ejecución verificada son verdaderos en los fixtures de texto que terminan con éxito. Explorer es una sesión larga: su captura no se contabiliza como un EXE que finalizó ni como inicialización completa de todos los servicios Windows.

Las capturas revisadas son `text-1.png`, `text-2.png`, `text-3.png` y `explorer.png` del directorio de aceptación. Las campañas de desarrollo y el fallo de protección permanecen en sus directorios originales. No se agregaron parches al emulador. El oficial sigue bloqueado y la validación en PS4 real está pendiente.

El próximo hito es entrada real al driver. La GUI PE32 mediante wowprospero, el navegador de carpetas, sus clases COM y servicios siguen fuera de este incremento.

En un seguimiento puntual se incorporó Marlett de la misma revisión fijada de Wine, con su SFD y registro por ruta completa. Una corrida de `gui-text64.exe` en shadPS4 terminó con salida 0 y mostró los iconos correctos de minimizar, maximizar y cerrar. La captura está en `reports/marlett-caption/caption-fixed.png` y su informe en ese directorio. No se repitió la suite completa. La cobertura de otros alfabetos sigue pendiente.
