# Investigación: GTA Vice City (PE32) y la base 0x400000

[English](investigacion-gta-vc-base-0x400000.md) | [Español](investigacion-gta-vc-base-0x400000-es.md)

Corrida analizada: W208, `reports/wine-hardware-w208/physical/20261104T153132Z/run-0003.log`. EXE: copia del usuario en la consola, leída por FTP sólo lectura a un directorio temporal fuera del repositorio. No se empaquetó nada ni se modificó el archivo.

## Resumen

- `gta-vc.exe` no tiene directorio de relocaciones. Sólo puede ejecutarse en `0x400000`.
- Wine lo mapeó en `0x027D0000` y siguió sin relocarlo. El primer acceso a una dirección absoluta del EXE falló: la escritura del índice TLS en `0x006DF9E0`.
- `0x400000` está ocupada por el propio ELF del título (eboot), que el kernel de la PS4 carga en esa base. Esto no es específico de GTA: afecta a cualquier EXE de base fija, y la mayoría de los juegos de 32 bits antiguos lo son.
- Para cargarlo en `0x400000` hay que sacar el eboot de esa zona. Que se pueda depende del kernel, y hay que probarlo en consola antes de tocar el build de Wine.

## 1. Por qué `0x400000` no está libre

- El eboot es un ELF PIE de OpenOrbis (`tools/link-wine-boot.py:93`, `-pie` con `link.x`). Su primer segmento empieza en la dirección 0 (`link.x`, `.text`). `create-fself` lo marca `ET_SCE_EXEC_ASLR` (`PS4 ELF Specification.md:11`), y el kernel elige la base. En los logs esa base es `0x400000` (`docs/INCREMENT_13.md:98`).
- `build/wine-boot/bootstrap.elf` (el último build local, quizá no el exacto de W208) tiene segmentos `PT_LOAD` de 0 a `0xc5c050`. En memoria eso es `0x400000`–`0x105c050`, unos 12,4 MB.
- GTA VC necesita `0x400000`–`0xa14000` (`SizeOfImage` `0x614000`). Ese rango queda entero dentro del eboot.
- Un dato que lo confirma: en el incremento 20, con un eboot más chico, Wine ubicó un PE32 en `0xed0000` y registró que la base preferida no estaba libre (`docs/INCREMENT_20.md:37`). Ahora Wine lo ubica más arriba (`0x27d0000`, línea 452 del log).
- `console32.exe` y los fixtures funcionan porque se enlazan en `0x30000000` con relocaciones (`tools/build.py:79-102`; `docs/INCREMENT_16.md:51`).

## 2. ¿El EXE tiene relocaciones utilizables?

No. Datos del encabezado PE leídos del archivo de la consola (3 088 896 bytes):

| Campo | Valor |
|---|---|
|Máquina| `0x14c` |
|Características| `0x10e`: EXECUTABLE, LINE_NUMS_STRIPPED, LOCAL_SYMS_STRIPPED, 32BIT. **No** tiene `RELOCS_STRIPPED` (`0x1`). |
| ImageBase / SizeOfImage | `0x400000` / `0x614000` |
|Punto de entrada| RVA `0x267c40`, dentro de `.text` |
|DataDirectory[BASERELOC]| **0 / 0**: no hay tabla de relocaciones |
| Secciones | 14: `.text`, `.rdata`, `.exc`, `.asrc`, `.data`, `.CRT`, `/0`, `.idata`, `.tls`, `_rwdseg`, `_rwcseg`, `.bss`, `.edata`, `.rsrc` |
| TLS | StartAddressOfRawData `0x6f4000`, **AddressOfIndex `0x6df9e0`**, AddressOfCallBacks `0x6df9e4` |
|Importaciones| advapi32, ddraw, dinput8, kernel32, user32, winmm, wsock32, d3d8, mss32, ole32 |

- No hay secciones típicas de SafeDisc, y el `.nfo` de la carpeta indica una versión 1.1 sin CD. No se encontraron señales de empaquetado. El problema no es la protección: es que el EXE no tiene relocaciones.
- Wine no rechaza el EXE. En `virtual_relocate_module` (`.deps/wine/ps4-overlay/dlls/ntdll/unix/virtual.c:4072-4081`) sólo falla si `RELOCS_STRIPPED` está puesto. Si el directorio está vacío devuelve `STATUS_SUCCESS` sin tocar nada. Wine upstream hace lo mismo (`.deps/wine/source/.../virtual.c:3970`).
- La falla del log coincide con eso:
  - `info[1]=006DF9E0` es exactamente `AddressOfIndex` del TLS.
  - `edi=02a50074` es `0x27d0000 + 0x280074`, el directorio TLS dentro de la imagen mapeada.
  - El código que falla está en el ntdll de 32 bits (`eip=7bf71c7b`), justo después de cargar kernel32. Eso es compatible con la inicialización TLS del cargador, aunque no simbolicé la dirección.
- Aunque esa escritura se evitara, el resto del código usa direcciones absolutas de `0x400000`–`0xa14000`. Reconstruir relocaciones a mano no es fiable y significaría modificar el EXE del usuario. Lo descarto.

## 3. Qué haría falta para cargarlo en `0x400000`

### Descartado

- **Relocar el EXE**: no tiene tabla de relocaciones (sección 2).
- **Base de segmento distinta de cero en compatibilidad de 32 bits**: todo el código de 32 bits de Wine y los thunks wow64 asumen memoria plana.
- **Cambiar el layout dentro de Wine**: el rango lo ocupa el proceso PS4 mismo, no Wine.

### Camino real: sacar el eboot de la zona baja

Hay que lograr que el código del título no quede en `0x400000`. En orden de costo:

- **A. PIE con `--image-base` alto.** Enlazar con `ld.lld -pie --image-base=0x1000000000` (o similar) y ver dónde lo pone el kernel:
  - en `0x400000 + vaddr`: la zona baja queda libre;
  - otra vez en `0x400000`: el kernel ignora el vaddr.
- **B. `ET_SCE_EXEC` (0xFE00, sin ASLR) con vaddr alto.** `create-fself` no tiene una opción para el tipo (`-ptype` es otra cosa). Habría que parchear `e_type` antes de generar el SELF. Que el kernel acepte un vaddr distinto de `0x400000` no está verificado.
- **C. Stub chico más módulo.** Un eboot mínimo que carga el boot de Wine como PRX (que el kernel ubica arriba) y después intenta `munmap` de sus propias páginas en `0x400000`. Es el más invasivo. No sé si el kernel permite desmapear el eboot.

El destino del eboot debe quedar fuera de los 4 GB bajos y de lo que reserva Wine (`addr_space_limit=0x7ffff0000`, línea 395). Debe evitar también las ventanas GPU de radv (`0x40_0000_0000`+). Un rango candidato es `0x10_0000_0000`–`0x3f_ffff_ffff`; la sonda lo tiene que confirmar.

## 4. Propuesta para el coordinador

1. **Sonda de base del eboot (1–2 builds, sin Wine).** Un eboot de prueba aparte, sin tocar `link-wine-boot.py` ni el boot actual, que:
   - registre `&__text_start` (variante A, y la B si la A no mueve nada);
   - intente `mmap(0x400000, 0x614000, MAP_FIXED|MAP_ANON)` y registre el rc;
   - imprima `PWBASE text=0x... low_map rc=... errno=...` y vuelva.

   Si las dos variantes dan `0x400000`, quedaría la C, o aceptar que los EXE de base fija no corren en este diseño.
2. **Fallo limpio en vez de crash (1 build, opcional, independiente).** Hoy el usuario ve 4,7 s de carga y vuelta al escritorio sin explicación. Dos lugares posibles:
   - En `native/wine_hardware.c`, junto a `pe_machine`: leer `ImageBase` y el directorio de relocaciones. Si la base cae dentro del eboot y no hay relocaciones, registrar `pe_fixed_base` y no lanzar.
   - En el overlay (`virtual.c:4081`): si es el EXE principal, `delta != 0` y no hay relocaciones, devolver `STATUS_CONFLICTING_ADDRESSES`. Riesgo: un EXE sin relocaciones que no use direcciones absolutas dejaría de cargar. Es raro, pero cambia el comportamiento respecto de Wine.

   No toqué ninguno de los dos. El diálogo de relanzado está en `tools/build-guest-hw.py`, que hoy edita fase9.
3. **Si la sonda libera la zona baja (2–4 builds):** reenlazar el boot con la base nueva y comprobar `main_image_load ... base=0x400000` en el log. Recién ahí aparecen los problemas propios de GTA:
   - `d3d8.dll` local en la carpeta del juego, ddraw y dinput8;
   - `Mss32.dll` (Miles) y wsock32.

   No hay una estimación seria de esa parte todavía.

## Sonda B001 (PKG aparte, ORBB00001)

- Fuente: `native/pwbase_probe.c`. Build: `tools/build-pwbase-probe.py`. Son archivos nuevos; no se modificó ninguna herramienta compartida (`orbis_package.py` sólo se importa).
- Paquete `IV0000-ORBB00001_00-ORBISWINPWBASE01`, título "OrbisDesk base probe B001". Se instala junto a OrbisDesk (ORBW00002) sin reemplazarlo. No incluye Wine.
- Variante A (`eboot.bin`): PIE `ET_SCE_EXEC_ASLR`, primer segmento enlazado en `0x1000000000`.
- Variante B (`/app0/pwbase_b.bin`): el mismo código enlazado en `0x1100000000`, con `e_type` `ET_SCE_EXEC`.
  - `create-fself` no tiene opción para el tipo, y `make_fself.py` del SDK sólo funciona en Python 2.
  - Por eso el build cambia `e_type` en la copia del encabezado ELF del SELF y recalcula el SHA-256 del OELF (offset `0x380`). Verifica las dos cosas antes de escribir.
  - Los digests de segmentos no cubren el encabezado. Que el kernel acepte el SELF así modificado es justamente parte de lo que se prueba.
- A ejecuta y luego lanza B una sola vez con `sceSystemServiceLoadExec`. Lo marca con `/data/orbis-win/probe-base-b.tried`; para repetir B hay que borrar ese archivo.
- Cada variante agrega estas líneas a `/data/orbis-win/probe-base.txt`:
  - `PWBASE X start`: dirección enlazada, `__text_start`, `main`, un dato y la pila.
  - `text_delta`: diferencia entre la dirección real y la enlazada.
  - El mapa del kernel por debajo de 4 GB (`lowmap`).
  - `low_hint`: un `mmap` en `0x400000` sin `MAP_FIXED`.
  - `low_map`: `MAP_FIXED` de `0x400000`/`0x614000`, sólo si el kernel no informa nada en ese rango; si la escritura funciona, prueba una escritura en `0x6df9e0`.
  - Si el texto o algo más está en el rango, registra `skipped` con el motivo en vez de pisarlo.
- Prueba local en un directorio temporal: se compilaron y enlazaron las dos variantes, y el primer `PT_LOAD` quedó en la dirección pedida. `create-fself` aceptó las dos y el parche de B cambió exactamente 33 bytes. No se probaron el empaquetado ni la consola.

Cómo leer el resultado:

| Resultado | Significado |
|---|---|
| A `text` ≈ `0x1000000000` | el kernel respeta el vaddr del PIE; alcanza con `--image-base` |
| A `text` = `0x400000` + `text_delta` = `-0xfffc00000` | el kernel ignora el vaddr; mirar B |
| B `start` con `text` ≈ `0x1100000000` | `ET_SCE_EXEC` en dirección alta funciona |
| sin líneas de B y `b_load_exec rc≠0` | LoadExec o el SELF modificado rechazado |
| `low_map addr=0x400000 write_ok=1` | la zona de GTA se puede mapear con ese layout |

### Resultado de B001

El usuario instaló y abrió B001. En `/data/orbis-win/` no aparecieron ni `probe-base.txt` ni `probe-base-b.tried`.

- **Escribir en `/data` no es el problema.** H001B usa el mismo paid (`0x3800000000000011`), no hace ningún paso especial y escribe `/data/orbis-win/hw01` con `mkdir` y `open` (`native/hardware_boot.c:137-143`). B001 hace exactamente eso en la primera línea de `main`.
- **Lo más probable es que el eboot de B001 nunca llegara a `main`.** Ese eboot es la variante A: PIE con el vaddr en `0x1000000000`. Hay dos explicaciones posibles: el kernel rechazó la carga, o el proceso murió antes de `main` (relocaciones o crt).
- El usuario confirmó que B001 muestra "error al abrir". El sistema rechazó el eboot antes de `main`, con el primer `PT_LOAD` en `0x1000000000`. Todavía no tenemos el código de error.

## Sonda B002 (ORBB00002)

Mismos archivos: `native/pwbase_probe.c` y `tools/build-pwbase-probe.py`, reescritos.

- **El eboot ya no es la variante.** `eboot.bin` es un driver enlazado en 0, igual que todos los eboot que funcionan.
  - Registra la línea base.
  - Lanza cada etapa (`/app0/pwbase_<n>.bin`) con `sceSystemServiceLoadExec`.
  - Antes de lanzar una etapa la marca pendiente en `/data/orbis-win/probe-base.state`. La etapa borra la marca, mide y relanza el driver.
  - Si al abrirse el driver encuentra una etapa todavía pendiente, registra `stage_did_not_start` y sigue con la siguiente.
- **Etapas:**

  |Etapa| Enlazada en | Tipo | Para qué |
  |---|---|---|---|
  | `z` | 0 |ASLR| control: si LoadExec de otro archivo funciona |
  | `a2` | `0x10000000` |ASLR| si un vaddr distinto de cero carga |
  | `a` | `0x1000000000` |ASLR| la variante de B001 |
  | `b` | `0x1100000000` | `ET_SCE_EXEC` | tipo sin ASLR en dirección alta |

- **Datos para la opción C**, en la primera apertura del driver:
  - `modules`: nombre y segmentos de cada módulo cargado (este ELF, libkernel, `libc.prx` de `/app0/sce_module`). Muestra dónde ubica el kernel un PRX de la aplicación, y si queda fuera de los 4 GB bajos.
  - `self_unmap`: `munmap` y `MAP_FIXED` de una página que pertenece sólo a un arreglo del propio eboot. Muestra si un eboot puede liberar su propio rango.
  - Un PRX propio cargado con `sceKernelLoadStartModule` queda para B003, si estos datos lo justifican.
- **Salidas:**
  - el log `/data/orbis-win/probe-base.txt`, con respaldo en `/download0/probe-base.txt` si `/data` no abre;
  - `sceKernelDebugOutText`;
  - una notificación del sistema por etapa (`PWBASE <etapa> text=0x… low_ok|occupied|…`) y otra al final (`PWBASE done`). El usuario puede leerlas aunque no haya log.
- **Qué hace el usuario:** abrir "OrbisDesk base probe B002". Si la app se cierra antes de la notificación `PWBASE done`, abrirla de nuevo, hasta 4 veces. Para repetir todo desde cero, borrar `/data/orbis-win/probe-base.state`.
- **Prueba local:** el script corrió completo en un directorio temporal, sin empaquetar. Las cinco piezas compilan sin warnings, cada `PT_LOAD` queda en la dirección pedida y `create-fself` acepta todas. Ni el empaquetado ni la consola están probados.

### Resultado de B002

"También se cerró al abrir". No aparecieron ni `probe-base.txt` ni `probe-base.state`, y el respaldo en `/download0` no se puede leer por FTP. El driver está enlazado en 0, así que la dirección alta no explica esta falla.

- Se comparó B002 con los paquetes que sí arrancan (H001B, G001, W211):
  - mismo `create-fself` y paid, mismos `sce_module`, `right.sprx` y `param.sfo` (`orbis_package.py`);
  - el ícono es el mismo de W211;
  - nadie hace jailbreak ni escape del sandbox antes de usar `/data`.
- La diferencia concreta está en los imports. El driver importa `sceKernelSendNotificationRequest` y `sceKernelGetModuleInfo`, que no importa ningún eboot que haya corrido aquí (comparado con `llvm-nm` contra W211 y H001B). Un import que el sistema no resuelve impide arrancar antes de `main`. Es la causa más probable, pero no está demostrada.
- B001 sólo tenía imports ya probados, así que su rechazo sí apunta a la dirección alta.

## Sonda B003 (ORBB00003)

- **Sin imports nuevos.** Se quitaron las notificaciones y `sceKernelGetModuleInfo`. Los módulos se ven en el mapa completo de `sceKernelVirtualQuery`, que trae nombres. El build falla si algún ELF importa algo que no importen el `wine.elf` más nuevo o el `hardware.elf` de H001B.
- **La primera apertura es sólo el control.** Crea `/data/orbis-win/probe-base.control`, escribe `PWBASE driver control …` en `probe-base.txt`, espera 5 s y cierra con LoadExec `exit`.
- **Desde la segunda apertura:** línea base (mapa completo, `low_map`, `self_unmap`) y las etapas `z`, `a2`, `a` y `b`, con la marca de pendiente igual que en B002.
- **Qué hace el usuario:**
  1. Abrir la app una vez y esperar a que se cierre sola (unos 5 s). Revisar por FTP que exista `probe-base.txt`.
  2. Si existe, abrirla de nuevo, hasta 5 veces si alguna etapa la cierra, hasta que el log diga `PWBASE driver done`.

  Para repetir todo, borrar `probe-base.control` y `probe-base.state`.
- **Prueba local:** el script corrió completo en un directorio temporal, sin empaquetar. Las cinco piezas tienen 23 imports cada una, todos ya probados.

### Resultado de B003

"Se cerró también". Ni siquiera el control de la primera apertura escribió nada. Así que la hipótesis de los imports no alcanza, o no es la causa.

Comparación con los paquetes que sí corrieron:

- `param.sfo`: los mismos campos que W212 y H001B. APP_TYPE 1, ATTRIBUTE 0, CATEGORY `gd` y SYSTEM_VER 0 vienen de `orbis_package.py`. Cambian sólo título, IDs y versión.
- `pkg.gp4`: el mismo `app_type="full"`, los mismos `sce_module/libc.prx`, `libSceFios2.prx` y `sce_sys/about/right.sprx`.
- fself: el mismo `create-fself --paid 0x3800000000000011`, sin authinfo, como W212 y H001B.
- H001B corrió en consola el 31/10 con este mismo toolchain (libc del SDK, `link.x` sin cambios) y escribió en `/data` (`reports/hardware-h001b/physical/20261031T051942Z`). Un eboot chico del SDK puede funcionar.
- Lo que sigue distinto: el código del probe, el título ORBB y los `.bin` extra en `/app0`.

## Sonda B004: controles con título fijo

Reglas nuevas del usuario:

- Un solo título y content ID para todas las sondas: `ORBB00001` / `IV0000-ORBB00001_00-ORBISWINPWBASE01`. Cada una se instala encima de la anterior.
- Un solo nombre de paquete: `/data/pkg/orbis-win-pwbase-probe.pkg`.
- Como el mismo título sólo se reinstala con una versión mayor, cada modo tiene la suya.

| Comando | Versión |eboot|
|---|---|---|
| `--control h001b` | 01.04 | `build/hardware-h001b/app/eboot.bin` sin cambios, más `hardware-marker.txt` |
| `--control w212` | 01.05 | `build/wine-hardware-w212/app/eboot.bin` sin cambios |
| sin opción | 01.06 | la sonda de etapas de B003 |

Orden propuesto:

1. **h001b.** Si muestra su pantalla PASS/FAIL y escribe `/data/orbis-win/hw01/report-*` bajo ORBB00001, el título y el paquete están bien, y la falla está en el ELF de la sonda (código o enlace).
2. **w212, sólo si h001b se cierra.** Si W212 corre bajo ORBB00001, el problema es algo de H001B que hoy ya no funciona. Si también se cierra, es el título o el paquete. Advertencia: el eboot de W212 arranca Wine completo con `/data/wine-prefix` y escribe en `/data/orbis-win/w212`, igual que OrbisDesk.
3. **La sonda, cuando un control funcione.**

En la prueba local los tres modos se construyeron en un directorio temporal, con las versiones de la tabla. No se empaquetaron.

### Resultado de B004 (control h001b)

El eboot de H001B, sin cambios, abrió bajo ORBB00001 y mostró "todo verde". El título, el paquete y el cargador funcionan, así que B001–B003 fallaron por su propio ELF.

La diferencia estructural que queda entre esos ELF y el de H001B son las bibliotecas requeridas (DT_NEEDED):

- H001B: `libkernel` y `libSceVideoOut`.
- B001–B003: `libkernel` y `libSceSystemService`, que era lo que necesitaba LoadExec.
- El eboot de Wine también requiere `libSceSystemService`, pero junto con VideoOut, Sysmodule y otras. No sé qué combinación exige el sistema.

Además, ninguno de los B00x abría VideoOut.

## Sonda B005 (ORBB00001, versión 01.07)

- **Cada ELF se construye como H001B** (`tools/build-hardware-boot.py`):
  - las mismas flags, con `-Werror`;
  - el `sink.c` que corrió en H001B (`build/hardware-h001b/sink.c`), cambiando sólo la carpeta de frames a `/data/orbis-win/pwbase-frames`;
  - enlace con `-lc -lkernel -lSceVideoOut`.

  Las bibliotecas requeridas quedan idénticas a H001B; se verificó con `llvm-readelf`.
- **LoadExec se busca en tiempo de ejecución.** Se carga `libSceSystemService.sprx` con `sceKernelLoadStartModule` desde el directorio con la palabra aleatoria del sandbox, como `native/hw_pad.c` carga libScePad (W030), y la función se obtiene con `sceKernelDlsym`. Si eso falla, la app no se cierra sola: muestra "close the app from the PS4 menu".
- **Pantalla:** cada línea importante aparece con la fuente de H001B. Así el usuario ve el resultado aunque falle el log.
- El control de primera apertura y las etapas `z`, `a2`, `a` y `b` siguen igual que en B003. El chequeo de imports probados también se mantiene.
- Prueba local: las cinco piezas compilan con `-Werror`, cada `PT_LOAD` queda en su dirección y `create-fself` las acepta. No se empaquetó.

### Resultado de B005

"Terminó en error". En la consola no quedó nada de B005: ni `probe-base.control`, ni `probe-base.txt`, ni la carpeta `pwbase-frames`. El control h001b sí dejó `hw01/report-0006.jsonl` y `roundtrip-0006.bin` (4/11). Por lo tanto B005 murió antes de la primera línea de `main`, aun con la receta de enlace de H001B.

Lo que comparten todas las sondas que fallaron y no tenía el control que funcionó:

- **Archivos SELF extra en `/app0`** (`pwbase_*.bin`): en B001, B002, B003 y B005. El control h001b no tenía ninguno.
- **`own_page`**, un arreglo de 32 KiB alineado a 16 KiB en `.bss`: en B002 a B005. Agranda el último segmento RW (memsz `0x14714` contra `0x4310` en H001B).

## Sonda B006: bisección desde H001B (ORBB00001)

`tools/build-pwbase-probe.py --step N`. Cada paso tiene una versión mayor que el anterior:

|Paso| Versión | Contenido |
|---|---|---|
| 1 | 01.08 | Sólo el driver con `PWBASE_CONTROL_ONLY`: crea el log, dibuja la pantalla y queda abierto como H001B. Sin LoadExec, sin etapas, sin `own_page`, sin otros archivos. |
| 2 | 01.09 | El mismo `eboot.bin` del paso 1, más los cuatro `pwbase_*.bin` en `/app0`, que nunca se lanzan. Prueba si su sola presencia rompe el arranque. |
| 3 | 01.10 | El driver y las etapas completos, sin `own_page` (`PWBASE_NO_SELF_UNMAP`). |
| 4 | 01.11 | La sonda completa, igual a B005. |

- Paso 1 en consola: debería mostrar "PWBASE PROBE DRIVER" y la línea `control_only ok`, y escribir `/data/orbis-win/probe-base.txt`. Se cierra desde el menú de la PS4.
- Si el paso 1 falla, la causa está en el código de arranque de la sonda, que ya es casi el de H001B. Habría que compararlos línea por línea.
- Si el paso 1 funciona y el 2 falla, la causa son los archivos extra en `/app0`, y las etapas tendrían que vivir en otro lugar.
- Prueba local: los cuatro pasos se construyeron en un directorio temporal. El driver del paso 1 tiene un layout de segmentos casi igual al de H001B y las mismas bibliotecas requeridas (`libkernel` y `libSceVideoOut`).

### Resultado de B006 paso 1

"B006 ok". `/data/orbis-win/probe-base.txt` contiene:

```
PWBASE control_only log_fd=14 text=0x400000
PWBASE control_only ok: close the app from the PS4 menu
```

Además hay tres frames en `/data/orbis-win/pwbase-frames/`. El arranque de la sonda funciona, y `text=0x400000` confirma la base del eboot en consola. Sigue el paso 2, con el mismo `eboot.bin` más los `pwbase_*.bin` en `/app0`. Como su log es idéntico, el éxito se reconoce por dos líneas nuevas al final de `probe-base.txt`.

### Resultado de B006 pasos 2 y 3

- **Paso 2:** abrió. Los `.bin` extra en `/app0` no impiden el arranque.
- **Paso 3** (`reports/pwbase-probe-b006/probe-base-2.txt`):
  - El LoadExec buscado en tiempo de ejecución funciona: `dlsym=0` y la función en `0x8007e8ea0`. Con él el título se cierra solo y lanza otros SELF.
  - La etapa `z` (enlazada en 0) corrió por LoadExec, como un proceso nuevo (pid 1104), con el texto en `0x400000`.
  - La etapa `a2` (enlazada en `0x10000000`, tipo ASLR) no escribió ninguna línea y el usuario vio un error. Junto con B001 (`0x1000000000` como eboot, "error al abrir"), la conclusión es: **con el tipo que genera OpenOrbis (`ET_SCE_EXEC_ASLR`), un ejecutable cuyo primer segmento no está en 0 no corre, y el que corre queda en `0x400000`.** La etapa `a` usa el mismo tipo; lo esperable es que falle igual.
  - Falta la etapa `b` (`ET_SCE_EXEC`, sin ASLR, en `0x1100000000`). Es la última forma de mover el eboot sin la opción C.
- **Mapa del proceso** (`sceKernelVirtualQuery`, hasta `0x7ef000000`):
  - debajo de 4 GB sólo está el eboot (`0x400000`–`0x420000` para la sonda);
  - lo demás empieza en `0x200000000` (ScePackageInfo, memoria directa, etc.);
  - la pila principal está cerca de `0x7eedfc000`.

  Para la opción C, eso significa que el único obstáculo bajo 4 GB sería el propio stub.

### Resultado de B006 etapas `a` y `b` (`reports/pwbase-probe-b006/probe-base-4.txt`)

- `a2` y `a` (tipo ASLR con vaddr distinto de 0) no arrancaron.
- **`b` sí arrancó.** Es `ET_SCE_EXEC` enlazada en `0x1100000000`:
  - `text=0x1100000000`, `text_delta=0x0`;
  - el ejecutable ocupa `0x1100000000`–`0x110001c000`;
  - **no queda nada por debajo de 4 GB**;
  - `low_map addr=0x400000 errno=0 write_ok=1`.
- Conclusión: con un eboot `ET_SCE_EXEC` enlazado alto, el kernel lo carga en su dirección de enlace y deja libre el rango de GTA. No hace falta la opción C.

## Plan: mover el eboot de OrbisDesk

### Qué suponía la base `0x400000` (revisado)

| Pieza | Estado |
|---|---|
| Wine `mmap_init` (`ps4-overlay/.../virtual.c:767`) | Reserva `0x10000`–`0x68000000` y parte la reserva alrededor de lo ocupado. Sin el eboot, Wine se queda con `0x400000` y el PE32 puede cargarse en su base. Sin cambios. |
| `addr_space_limit=0x7ffff0000` (`virtual.c:3775`) | El eboot en `0x1100000000` queda arriba del límite, fuera del espacio Windows, como un `.so` en Linux. Sin cambios. |
| Ventanas GPU de radv (`0x4000000000`, `0x4400000000`, `0x4600000000`…) | No se solapan con `0x1100000000`–`0x11023ca5d0`. |
| Mapa del sistema (sondas B006) | Áreas del sistema en `0x200000000`–`0x201000000`, pila en `0x7eedf0000`–`0x7ef000000`, `libSceSystemService` en `0x8007e8ea0`. `0x1100000000` está libre, comprobado por `b`. |
| Thunks de wow64native (`cpu.c:595-605`) | Los saltos lejanos 32→64 van a `syscall_32to64` y `unix_call_32to64`, dentro de `wow64native.dll` (debajo de 4 GB), no al eboot. |
| Truncados de punteros a 32 bits en nuestro código | `compat32_probe.c:47`, `pw_pe32_lifecycle.c:257` y `pw_k32_ps4.c:473` son datos asignados debajo de 4 GB, no direcciones del eboot. |
| Herramientas de símbolos | Ninguna resta `0x400000` (INCREMENT_13 lo hizo a mano). Con el eboot movido, las direcciones del log coinciden con las del ELF. |
| `__dso_handle` de lld | Lld lo define en el encabezado ELF, que vale 0 con base 0 y queda en 0 al mover la imagen. Mesa lo referencia con `R_X86_64_PC32` y el enlace falla. El script lo define oculto al comienzo de la imagen nueva; sólo tiene que ser una dirección propia de la imagen (`__cxa_atexit`). |
| Símbolos en 0 tras mover | Sólo `native_cookie`, que es TLS: el valor es un offset dentro del bloque TLS, igual que antes. |

Lo que no se puede verificar sin ejecutar: cualquier heurística de Wine o del sistema que dependa de que el código del eboot esté por debajo de 4 GB. No encontré ninguna.

### Paso 1: sonda B007 con el eboot real (lista para construir)

Herramienta nueva: `tools/build-wine-highbase-probe.py`. Usa el nuevo `tools/orbis_self.py` y no toca ningún archivo compartido.

1. Lee `link_command` de `out/wine-hardware-wNNN/manifest.json` (el más nuevo, o `--build`). Repite el enlace sin cambios y exige un `wine.elf` idéntico byte a byte. Así comprueba que los insumos siguen siendo los de WNNN; si falla, primero hay que reconstruir WNNN.
2. Enlaza de nuevo con el mismo `link.x`, agregando `. = BASE; HIDDEN(__dso_handle = .);`. Comprueba que cada `PT_LOAD` se movió exactamente `BASE` y que los imports no cambiaron.
3. `create-fself` con las mismas flags que `build-wine-hardware.py`, y después `ET_SCE_EXEC` (`orbis_self.set_exec_type`).
4. Empaqueta como ORBB00001 versión 01.12 y lo sube como `/data/pkg/orbis-win-pwbase-probe.pkg`.

Prueba local con W215: el replay dio idéntico, la imagen quedó en `0x1100000000`–`0x11023ca5d0` y `create-fself` aceptó el resultado. No se empaquetó ni se ejecutó.

Qué mirar en consola:

- El escritorio arranca como W215. El log va a `/data/orbis-win/w215/` (el mismo directorio que W215), con el prefijo y runtime actuales de `/data`.
- Al abrir `gta-vc.exe`, el relanzado usa este mismo eboot. Se espera `main_image_load status=0 … base=0x400000`, en vez de `40000003 … base=0x27d0000`, y que ya no aparezca el AV en `0x006DF9E0`. Lo que falle después es del juego (d3d8, ddraw, dinput8, Mss32).

### Paso 2: integrar en el título real (archivos compartidos; lo decide el coordinador)

En `tools/build-wine-hardware.py`, unas diez líneas:

- Donde copia `link.x` (líneas 88-93), anteponer `. = 0x1100000000;` y `HIDDEN(__dso_handle = .);`.
- Después de `create-fself` (líneas 161-163), llamar a `orbis_self.set_exec_type`.
- Registrar `eboot_base` en el manifest.

`tools/link-wine-boot.py` no necesita cambios: su `bootstrap.elf` no se empaqueta, y `build-wine-hardware.py` reemplaza el `--script` del comando que reutiliza.

### Riesgos

- El SELF de B007 se modifica después de `create-fself`. B006 `b` mostró que un SELF chico modificado así carga; con 30 MB debería ser igual, pero no está probado.
- Si algo en Wine o en las bibliotecas del sistema usa direcciones del eboot como valores de 32 bits, va a fallar recién en B007. Esto no se encontró en la revisión.

## Resultado de B007 (W215 con el eboot en `0x1100000000`)

`reports/wine-hardware-w215/physical/20261104T182301Z`:

- El escritorio arranca (run-0001 y run-0003).
- En run-0002, `gta-vc.exe` carga en su base: `main_image_load status=00000000 machine=014c base=0x400000` y `Loaded …gta-vc.exe at 00400000`. La falla del TLS en `0x006DF9E0` desapareció. **Mover el eboot resolvió el problema de la base.**
- Antes de la falla nueva cargan sin errores:
  - los imports del juego: advapi32, ddraw, dinput8, winmm y ole32, como builtin; wsock32 se omite por no usarse;
  - el `d3d8.dll` local del juego, en `0x10000000`, y `Mss32.dll`, en `0x21100000`;
  - más tarde, `d3d9.dll` y `d3d8.dll` nativos de `system32`.

  Los códecs ACM que faltan (`l3codeca.acm`, `msgsm32.acm`) no detienen nada.

### La falla nueva: `GetDiskFreeSpaceA` devuelve 0 bytes por sector

- La AV es en `0x58060C`, escribiendo en `0xFFFFFFFC`.
- La función es un malloc alineado del juego (`0x5805F0`):

  ```
  eax=size; ebx=align; malloc(size+align)          ; 0x6618C0
  edx=(ptr+align) & ~(align-1); [edx-4]=ptr        ; 0x58060C
  ```

  Con `ebx=0` la máscara vale 0, `edx` vale 0 y escribe en `-4`. Los registros de la falla coinciden: `ebx=ecx=edx=0` y `eax=0x1893FD0`, que es el malloc correcto.
- La única llamada que pasa una alineación variable está en `0x408767`, en la inicialización del streaming de CD (cadenas "Using no buffered loading for streaming" y "cdvd_stream"):

  ```
  0x408710 call [0x6F2310]  ; GetDiskFreeSpaceA(NULL, &spc, &BytesPerSector, &free, &total)
  0x408716 cmp  BytesPerSector, 2048 ; si <= 2048: FILE_FLAG_NO_BUFFERING
  0x408767 call aligned_malloc(2048, BytesPerSector)
  ```

  En la corrida `BytesPerSector` vale 0. El juego tomó la rama "no buffered" (0 ≤ 2048), no revisa el retorno de `GetDiskFreeSpaceA`, y la variable local quedó en 0.
- **Por qué vale 0 en Wine/PS4:**
  - `GetDiskFreeSpaceA` → `NtQueryVolumeInformationFile(FileFsFullSizeInformation)` → `get_full_size_info` (`ps4-overlay/dlls/ntdll/unix/file.c:2223`).
  - En `__ORBIS__` (no `linux`) se compila la rama `fstatvfs` (`file.c:2241-2243`).
  - El eboot no importa ninguna función statfs: `fstatvfs` viene enlazada estáticamente de la libc del SDK (`statvfs.lo`, en `build/wine-boot/lib/libc.a` y en la del SDK), que hace la syscall directa. Esta misma libc ya falló así con `lstat` y `readlink` en hardware (nota en `build-wine-hardware.py`).
  - Si `fstatvfs` falla, la consulta devuelve error, `GetDiskFreeSpaceA` devuelve FALSE y no llena las salidas.
  - El libkernel de la PS4 sí exporta `_fstatfs` (stub de OpenOrbis), con la `struct statfs` de FreeBSD.
  - No está medido en consola: el log no traza la consulta de volumen. Es la explicación más probable, y la siguiente build la confirma.

### Siguiente paso propuesto (para la próxima W)

`tools/build-wine-directory-ps4.py` ya parchea `file.c` con `replace()`. Se agregaría un `replace` más, que no inventa valores:

- En `get_full_size_info`, bajo `#ifdef __ORBIS__`, llamar a `_fstatfs` de libkernel con un buffer de la `struct statfs` de FreeBSD 9:
  - `f_bsize` en `0x10`, `f_blocks` en `0x20`, `f_bfree` en `0x28`, `f_bavail` en `0x30`;
  - `f_fstypename` en `0x118`;
  - 0x1D8 bytes en total; se reserva más.

  Si `_fstatfs` falla, devolver el error como hoy.
- Registrar una vez `PWFS statfs rc=… errno=… bsize=… blocks=… bfree=… bavail=… fstype=…`. El nombre del sistema de archivos confirma que el layout es correcto.
- Con valores reales, `BytesPerSector` sale 512 (o 2048 si `bsize==2048`) y la rama del juego funciona.

Riesgo: `_fstatfs` es un import nuevo para el eboot de Wine. Comparando B005 (falló) con B006 paso 3 (abrió), la única diferencia era `own_page`, el arreglo de 32 KiB alineado a 16 KiB en `.bss`. Un import nuevo no fue lo que rompió el arranque; aun así hay que comprobarlo en la build.

Después de esto, lo esperable es llegar a Direct3D: el wrapper `d3d8.dll` local más d3d9/d3d8 nativos de `system32`, el audio de Miles y el streaming de `.img` con `FILE_FLAG_NO_BUFFERING`/`OVERLAPPED`.

### Integración del eboot alto en el título real (concreto)

En `tools/build-wine-hardware.py` (compartido), con el `tools/orbis_self.py` nuevo:

```python
# línea 7
from orbis_self import set_exec_type
EBOOT_BASE=0x1100000000   # B006 stage b, B007: ET_SCE_EXEC loads here; 0x400000 stays free for PE32 images
# después de la línea 92 (antes de link_script.write_text(text))
if not text.startswith('SECTIONS\n{'):raise SystemExit('unexpected SDK link.x start')
text='SECTIONS\n{\n\t. = 0x%x;\n\tHIDDEN(__dso_handle = .);\n'%EBOOT_BASE+text[len('SECTIONS\n{'):]
# después de create-fself (líneas 161-163)
(work/'wine.exec.oelf').write_bytes(set_exec_type(work/'wine.oelf',app/'eboot.bin'))
# en el manifest (línea 757)
'eboot_base':hex(EBOOT_BASE),
```

- Son unas diez líneas.
- `tools/build-wine-highbase-probe.py` deja de servir una vez integrado, porque el `link.x` guardado ya trae la base.
- Si en algún momento se quisiera volver a `0x400000`, basta con quitar las dos líneas del script y la llamada a `set_exec_type`.

## Aplicado para W217 (aprobado por el usuario)

| Archivo | Cambio |sha256|
|---|---|---|
| `tools/build-wine-hardware.py` | `EBOOT_BASE=0x1100000000`, `. = base` y `HIDDEN(__dso_handle = .)` en el `link.x` copiado, `set_exec_type` después de `create-fself`, `eboot_base` en el manifest | `d8f989fc…3f116e` |
| `tools/build-wine-directory-ps4.py` | `replace` en `get_full_size_info`: en `__ORBIS__` usa `_fstatfs` de libkernel, registra `PWFS statfs` una vez y devuelve el error tal cual si falla | `4c0f41e8…081085f68` |
| `tools/orbis_self.py` | nuevo, sin cambios desde B007 | `30921262…3e4b7966` |

Verificado sin construir en `build/`:

- el `file.c` parcheado compila sin warnings en un directorio temporal y `file.o` importa `_fstatfs`;
- los tres scripts parsean.

El número de build (W216 → W217, versión 03.16) lo actualiza el coordinador.

Orden de build:

1. `tools/build-wine-directory-ps4.py`. `build-wine-hardware.py` sólo valida el hash del objeto contra su report, no qué versión del script lo generó: si no se corre primero, W217 sale con el `file.o` viejo sin dar error.
2. `tools/build-wine-hardware.py`, y la subida habitual.

Qué mirar:

- `out/wine-hardware-w217/manifest.json`: `"eboot_base": "0x1100000000"`.
- Escritorio: corre como W216. Las direcciones de código del eboot en el log quedan ahora en `0x11…`; por ejemplo, `PWVK lookup … unchecked 0x11…` en vez de `0x90dee0`.
- Corrida de `gta-vc.exe`:
  - `main_image_load status=00000000 machine=014c base=0x400000`;
  - `Loaded …gta-vc.exe at 00400000`;
  - `PWFS statfs rc=0 bsize=… blocks=… bfree=… bavail=… fstype=…`. Un `fstype` legible (por ejemplo `ufs` o `exfatfs`) confirma el layout;
  - no debe repetirse la AV en `0x58060C`.
- Si aparece `PWFS statfs rc=-1 errno=N`, libkernel también rechaza `_fstatfs` y la causa queda medida.

## Resultado de W217

`reports/wine-hardware-w217/physical/20261104T190832Z/run-0002.log`:

- `gta-vc.exe` carga en `0x400000` (línea 554). El eboot movido funciona en el título real: escritorio y juego.
- Línea 1199: **`PWFS statfs rc=-1 errno=1`**. El camino nuevo se ejecuta, pero `_fstatfs` de libkernel devuelve EPERM. El sandbox lo niega, igual que `lstat` (`probe libc_lstat rc=-1 errno=1`, que hoy se resuelve con `stat`).
- Sin tamaños, `GetDiskFreeSpaceA` sigue fallando, `BytesPerSector` queda en 0 y se repite la AV en `0x58060C` (línea 3544).

La causa quedó medida: el sistema no deja a la app consultar el volumen con `fstatfs`.

### Siguiente paso propuesto (W218)

Las bibliotecas del sistema exportan, según los stubs de OpenOrbis:

- `libkernel_sys`, que el eboot ya enlaza: `statfs(path)`, `fstatfs` y `getfsstat`.
- `libSceShellCoreUtil`: `sceShellCoreUtilGetFreeSizeOfUserPartition`, el espacio libre de la partición de usuario, donde está `/data`.
- `libSceAppContent`: `…GetAvailableSpaceKb` para datos de descarga y temporales. No aplican a `/data`.

Todas las unidades de Wine están bajo `/data`: C: es `/data/wine-prefix/drive_c` y Z: es `/data`. En `get_full_size_info` (`__ORBIS__`) propongo probar en orden y registrar una línea `PWFS` por intento, sólo la primera vez:

1. `_fstatfs(fd)`, como hoy (EPERM).
2. `statfs("/data")` de `libkernel_sys`, con el mismo layout de FreeBSD 9.
3. `getfsstat(buf, size, MNT_NOWAIT)`, buscando el montaje con `f_mntonname` igual a `/data` o al prefijo más largo de la ruta.
4. Si todo falla, **lo decide el usuario**:
   - (a) Devolver éxito con la geometría que Wine ya usa siempre (512 bytes por sector, 8 sectores por unidad; `file.c:2261-2262` no la mide salvo con `bsize==2048`) y los contadores en 0. Se registra `PWFS geometry_only`. GTA sólo usa `BytesPerSector`, pero un instalador que revise el espacio libre vería 0.
   - (b) Devolver el error como hoy. GTA sigue cayendo.

   La opción (a) no inventa espacio libre; sí responde con éxito sin datos del volumen.

Tamaño: un `replace` más en `tools/build-wine-directory-ps4.py`, compartido. Los pasos 1 a 3 no inventan nada, y el paso 4 es una decisión. Con el log de W218 se sabe cuál de las tres consultas permite el sandbox.

### Aplicado para W218 (el usuario eligió la opción a)

`tools/build-wine-directory-ps4.py` (sha256 `f3586b20…382fa8e8`) reemplaza el bloque de W217. En `get_full_size_info`, bajo `__ORBIS__`:

1. Prueba `_fstatfs(fd)` de libkernel. Si falla, registra `PWFS statfs rc=-1 errno=N` una vez.
2. Prueba `getfsstat(buf, 64×0x1d8, MNT_NOWAIT)`, la de `libkernel_sys`. La libc del SDK define `statfs` y `fstatfs` con syscalls crudas, pero `getfsstat` no, así que el enlace la toma de `libkernel_sys.so`, que el eboot ya requiere. Elige el montaje con el `f_mntonname` más largo que contenga `/data/wine-prefix`. Registra `PWFS getfsstat rc=… errno=… mount=… fstype=…`.
3. Con una de las dos: `PWFS statfs bsize=… blocks=… bfree=… bavail=… fstype=…` y valores reales.
4. Sin ninguna: `PWFS geometry_only bytes_per_sector=512 sectors_per_unit=8 counts=0`. Devuelve éxito con la geometría que Wine reporta para cualquier disco y contadores en 0. No se declara espacio libre.

Verificado en un directorio temporal:

- El `file.c` compila sin warnings;
- el enlace completo de W217, con ese `file.o` y `--no-undefined`, termina bien: `_fstatfs` y `getfsstat` quedan como imports, y `libkernel_sys.so` ya está entre las bibliotecas requeridas.

`tools/build-wine-hardware.py` no cambió (`d8f989fc…3f116e`). Pasos: subir el número a W218, `build-wine-directory-ps4.py`, `link-wine-boot.py`, `build-wine-hardware.py` y la subida.

Qué mirar en la corrida de GTA:

- una de las líneas `PWFS` de arriba;
- que la AV en `0x58060C` ya no aparezca;
- la falla siguiente, que debería estar después de la inicialización del stream de CD.

### Resultado de W218 y cambio para W219

- En `reports/wine-hardware-w218/physical/20261104T192945Z/run-0002.log`, la última línea es `PWFS statfs rc=-1 errno=1` (línea 1199). No hay línea de `getfsstat`, ni excepción, ni `process_exit`.
- El usuario vio "error de la pkg y se cerró". El sistema cerró el título dentro de `getfsstat`: esa syscall no devuelve error, mata el proceso.
- W219: `tools/build-wine-directory-ps4.py` (sha256 `6f713395…7d59c47c8`) quita `getfsstat`. Después de que `_fstatfs` falla, pasa directo a `PWFS geometry_only bytes_per_sector=512 sectors_per_unit=8 counts=0`.
- Compila sin warnings en un directorio temporal. El único import nuevo frente a W216 es `_fstatfs`, que en W217 y W218 volvió con EPERM sin cerrar el proceso.

## Resultado de W219: "necesita al menos DirectX 8.1"

El disco ya no frena al juego. Ahora el juego muestra su propio aviso de que hace falta DirectX 8.1.

- **Cómo lo comprueba el juego.** No mira el registro: el exe no contiene `Software\Microsoft\DirectX`. Usa la función `GetDXVersion` de los ejemplos del SDK de DirectX 8.1. Las cadenas, en `0x2d3f6c`–`0x2d4038`, siguen ese orden:
  1. carga `DDRAW.DLL` y llama a `DirectDrawCreateEx`;
  2. carga `D3D8.DLL` (si existe, la versión es 8.0);
  3. carga `dpnhpast.dll` (si existe, la versión es 8.1).

  El mensaje de error correspondiente es "Couldn't LoadLibrary dpnhpast.dll".
- **Qué pasa en W219** (`run-0002.log`, líneas 1560-1569): busca `dpnhpast.dll` en la carpeta del juego, en `syswow64` y en `windows`, y termina con `Failed to load module L"dpnhpast.dll"; status=c0000135`. El juego queda en 8.0 y muestra el aviso.
- **Registro:** está bien en las dos vistas. `Software\Microsoft\DirectX` y `Software\Wow6432Node\Microsoft\DirectX` tienen `Version="4.09.00.0904"` e `InstalledVersion` 9, que vienen de `wine.inf`. No hace falta cambiarlo.
- **La DLL existe pero no se empaqueta.** Wine la compila sin parches para las dos arquitecturas: `.deps/wine/runtime/build/dlls/dpnhpast/{i386,x86_64}-windows/dpnhpast.dll`, "Wine builtin DLL", con imports de kernel32, ntdll y ucrtbase. Ninguna lista de módulos la incluye.

### Fix propuesto para W221 (una línea)

En `tools/stage-wine-extras.py`, agregar `dpnhpast` a `MODULES`:

```python
MODULES=(('comctl32_v6','comctl32_v6.dll'),('imaadp32.acm','imaadp32.acm'),('msadp32.acm','msadp32.acm'),
         ('msg711.acm','msg711.acm'),('msacm32.drv','msacm32.drv'),('midimap','midimap.dll'),
         ('dpnhpast','dpnhpast.dll'))
```

y una línea en el docstring: "dpnhpast.dll: DirectPlay NAT helper; DirectX 8.1 checks (DX SDK GetDXVersion, GTA Vice City) load it by name".

`build-wine-hardware.py` ya instala cada módulo de `out/wine-extras` en `wine/lib/wine/<arch>-windows/` y en `system32`/`syswow64` (líneas 388-392). No necesita cambios, pero exige que el manifest de extras venga del stager actual.

Pasos:

1. `tools/stage-wine-extras.py`;
2. `tools/build-wine-hardware.py`, más los pasos de siempre (directory, link) si cambiaron sus entradas.

Aplicado (pedido del coordinador): `tools/stage-wine-extras.py` sha256 `951827e4…a4bd4ea9`, con `dpnhpast` para i386 y x86_64. Ambas DLL ya están compiladas en el árbol host (128 001 y 135 907 bytes, 2/11).

Qué mirar: `Loaded L"C:\\windows\\system32\\dpnhpast.dll" … builtin`, sin el aviso de DirectX. Lo siguiente debería ser la creación del dispositivo D3D8 a través del `d3d8.dll` local.

## Resultado de W221: falla en `vkCreateSwapchainKHR`

`reports/wine-hardware-w221/physical/20261104T200201Z/run-0002.log`:

- `dpnhpast` carga (línea 1569) y el aviso de DirectX desaparece.
- El juego crea el dispositivo con **DXVK 2.7.1 (x86)**, los `d3d8`/`d3d9` nativos de `system32` (líneas 2127-2129).
- RADV falla en `ip=0x110048bd44`, leyendo la dirección 0, y el proceso termina con status 3.

El análisis:

- Con los símbolos de `build/wine-hardware-w221/wine.elf` (sha `bc8745b7…`), esa dirección está en **`wsi_configure_image`** (Mesa `wsi_common.c`). Con `VK_SWAPCHAIN_CREATE_MUTABLE_FORMAT_BIT_KHR` (`testb $4`, y la imagen recibe `flags |= 0x508`), Mesa recorre `pNext` buscando `VkImageFormatListCreateInfo` (`sType 1000147000`), que la especificación exige con ese flag. La cadena terminó sin encontrarla y la lectura de `NULL` falló.
- **La causa está en Wine.** En `win32u_vkCreateSwapchainKHR` (`dlls/win32u/vulkan.c:1858-1865`), si el tamaño de la imagen (640×480) difiere del rectángulo cliente de la ventana y existen las extensiones maintenance1, Wine hace `create_info_host.pNext = &scaling;`. Eso **reemplaza** la cadena del cliente en vez de extenderla: el flag mutable de DXVK queda y su lista de formatos se pierde.
- No es un problema de WoW64 ni de nuestro WSI: la conversión de 32 a 64 bits no interviene.

### Fix preparado para W223

Está en las notas compartidas, sin aplicar porque W222 está compilando: `side-session-notes/…/swapchain-pnext-w223.patch.py` (sha256 `36875696…c6070668`). Agrega un `revise` a `tools/build-win32u-ps4.py`:

```c
        scaling.pNext = create_info_host.pNext;
        create_info_host.pNext = &scaling;
```

- Se probó sobre una copia de `build-win32u-ps4.py`: se aplica y el resultado parsea. El contexto (`create_info_host.pNext = &scaling;`) aparece una sola vez en el `vulkan.c` fijado.
- Pasos: aplicar el script a `tools/build-win32u-ps4.py`, correr `tools/build-win32u-ps4.py`, después `link-wine-boot.py` y `build-wine-hardware.py`.
- Qué mirar: no debe repetirse `vkCreateSwapchainKHR Exception 0xc0000005`. DXVK debería presentar el swapchain de 640×480, escalado a la ventana por el `VkSwapchainPresentScalingCreateInfoEXT`.

Secundario: `quartz` no tiene registrado el FilterGraph (líneas 2639-2721), así que los videos de intro probablemente fallen. El juego suele seguir sin ellos.

## W223: Vice City juega. Faltan los videos de intro

El fix de `pNext` resolvió el swapchain y el juego anda con el mando. Lo que queda son los videos.

### Qué falta (medido)

- **Formato de los videos.** Leí las cabeceras por FTP, sólo lectura: `movies/Logo.mpg` (7,2 MB) y `movies/GTAtitles.mpg` (24 MB) son **MPEG-1 system stream** (pack `0x21`, sin extensión MPEG-2). El video es MPEG-1 de 640×480 a 25 fps (rate code 3). El audio es **MPEG-1 Layer II** (`fffda400`: 192 kbps, 48 kHz, estéreo). Los streams son `0xe0`, `0xc0` y padding `0xbe`.
- **DirectShow de 32 bits no está.** Faltan `quartz`, `devenum`, `msdmo`, `avicap32` y `msvfw32` en `syswow64`, en `wine/lib/wine/i386-windows` y en el prefijo sellado. Tampoco está registrado en `system.reg`: de ahí el `class {e436ebb3-…} not registered` (FilterGraph) de W221, líneas 2639-2721. El prefijo sí tiene `comctl32`, `msacm32`, `oleaut32`, `rpcrt4`, `version` y `winmm`.
- **El árbol host de Wine sí los tiene, sin parches.** `.deps/wine/runtime/build/dlls/{quartz,devenum,msdmo,avicap32,msvfw32,amstream}/i386-windows`, y `libs/strmbase/i386-windows/libstrmbase.a`.
  - `avicap32` tiene una unixlib de captura v4l, pero su `DllMain` ignora el resultado de `__wine_init_unix_call` y carga igual.
  - `quartz` importa `msvfw32` y carga `ddraw` en diferido. `devenum` importa `avicap32`, `msdmo` y `msvfw32`.
- **No hay decodificador MPEG-1.** En el Wine fijado, el splitter MPEG-1 y los decodificadores MPEG de video y audio (`CLSID_MPEG1Splitter`, `CLSID_CMpegVideoCodec`, `CLSID_CMpegAudioCodec`) existen sólo en `winegstreamer`, que necesita GStreamer (`UNIX_LIBS = $(GSTREAMER_LIBS)`). En PS4 no hay GStreamer. Aunque se instale todo DirectShow, `RenderFile("movies\\Logo.mpg")` no encuentra quién decodifique.
- **Registro.** Hace falta algo más que los CLSID de COM:
  - las *check-bytes* de "Media Type", que están en el script `WINE_REGISTRY` de `quartz` (`dlls/quartz/quartz.rgs`, ya con la entrada MPEG-1 `000001ba…` hacia File Source (Async.)). Se puede leer como lo hace `stage-mshtml-hw.py`;
  - los `FilterData` (REGFILTER2) que el `DllRegisterServer` de `quartz` escribe con `IFilterMapper2_RegisterFilter` (`main.c:520-560`). Sin ellos, el grafo no encuentra el renderer de video ni el de DirectSound al construirse.

### Plan propuesto (sin éxito simulado)

1. **`tools/stage-dshow-i386.py` (nuevo).**
   - Copia sin parches las versiones i386 de `quartz`, `devenum`, `msdmo`, `avicap32` y `msvfw32` desde el árbol host.
   - Genera `system.reg.add` para Wow6432Node con:
     - las clases COM, desde los recursos `WINE_REGISTRY` de cada módulo;
     - las *check-bytes* de "Media Type" de `quartz.rgs`;
     - los `FilterData` de los filtros de `quartz`, serializados en Python como lo hace `filtermapper.c`.
   - No registra los filtros que sólo existen en `winegstreamer`: no hay quien los cree, y registrarlos sería anunciar algo que no está.
2. **Un filtro DirectShow propio, `pwmpeg1` (PE i386, nuevo).**
   - Tiene su propio CLSID y acepta `MEDIATYPE_Stream/MEDIASUBTYPE_MPEG1System` de File Source (Async.).
   - Expone dos salidas: video RGB32 con `VIDEOINFOHEADER` y audio PCM de 16 bits estéreo. Pone timestamps en ambas.
   - Decodifica de verdad, con **pl_mpeg** (phoboslab/pl_mpeg, licencia MIT, un solo header), que cubre justo lo que usan los videos: system stream, video MPEG-1 y audio MP2.
   - Se compila con `libstrmbase.a` del árbol host. Registra trazas `PWMPEG open/stream/first_frame/eos/error`.
   - Si el archivo no es MPEG-1 (por ejemplo MPEG-2, o AVI con otro códec), rechaza la conexión con una traza y `RenderFile` falla como en un Windows sin el códec.
3. **`tools/build-wine-hardware.py` (compartido).** Unas líneas, siguiendo el patrón de MSHTML: instalar los módulos y agregar `system.reg.add` a `system.reg`.

### Riesgos

- El Video Renderer de `quartz` dibuja con GDI en una ventana hija de la del juego, que presenta con DXVK y Vulkan. Cómo se mezcla eso en nuestro compositor (`ps5drv`) no está probado.
- pl_mpeg es una dependencia nueva: hay que fijar un commit en `.deps/downloads`, con su LICENSE.
- Tamaño: el filtro son unas 800-1200 líneas, más el generador de `FilterData`. Se esperan 2 a 4 builds, porque el grafo de DirectShow suele exponer detalles uno por uno.

### Aplicado para W225 (plan aprobado por el usuario)

| Archivo | Qué es |sha256|
|---|---|---|
| `.deps/downloads/pl_mpeg-c871f2be/pl_mpeg.h` | pl_mpeg en el commit `c871f2be022ece7ef4f64230b4fb8e1fb9eb6023` (2025-12-30), MIT según el propio header | `3a8cb30c…5fc2c9` |
| `.deps/downloads/pl_mpeg-c871f2be/LICENSE` | nota de procedencia y licencia (el repositorio no tiene un archivo LICENSE aparte) | `f75ebcfb…16e837` |
| `native/pwmpeg1/pwmpeg1.c`, `.spec` | el filtro DirectShow (nuevo) | `b5b62f7d…1d480`, `669471a1…1e62b` |
| `tools/stage-dshow-i386.py` | stager nuevo: módulos, filtro y registro | `613e5caf…7b8ea` |
| `tools/build-wine-hardware.py` | instala `out/dshow-i386` y agrega su `system.reg.add` | `4b3495f1…7d85e` |

**Filtro `pwmpeg1.ax`** (CLSID `{D1ABD1FB-1295-47E2-A8FC-65868F9C0C90}`):

- Entrada: `MEDIATYPE_Stream/MPEG1System`, leída del File Source por `IAsyncReader`.
- En la conexión abre el stream con pl_mpeg y registra `PWMPEG open size=… video=… WxH fps=… audio=… rate=… duration=…`. Si no encuentra cabeceras MPEG-1, registra `PWMPEG reject …` y devuelve `VFW_E_TYPE_NOT_ACCEPTED`.
- Salidas: video RGB32 bottom-up y audio PCM s16 estéreo. Cada una tiene su hilo y su instancia de pl_mpeg, con timestamps desde el PTS.
- Registra `PWMPEG <video|audio> first_sample`, `eos samples=N` o `stopped`.
- Es una DLL nativa (no builtin) que importa sólo kernel32, ntdll, ole32 y ucrtbase.

**Módulos.** Copia sin parches `quartz`, `devenum`, `msdmo`, `avicap32` y `msvfw32` (i386). El resto de su cierre de imports ya está en la vista de 32 bits.

**Registro** (263 claves, todo en la vista de 32 bits):

- los scripts `WINE_REGISTRY` de `quartz` y `devenum`. Incluyen `CLSID_FilterGraph` y las check-bytes de "Media Type", que se escriben en `Classes` y en `Classes\Wow6432Node`;
- las 9 categorías de `devenum`;
- los 6 filtros propios de `quartz`, con `FilterData` serializado como lo hace `filtermapper.c`;
- `pwmpeg1` con mérito `MERIT_NORMAL`.

No se registran los filtros de `winegstreamer`. Leí de vuelta los `FilterData` como lo hace `FM2_ReadFilterData`: Video Renderer, File Source y `pwmpeg1` salen con los pins y tipos esperados.

**Verificado sin `build/` ni `out/`:** el stager corrió completo en un directorio temporal (compila y enlaza el filtro sin warnings) y los scripts parsean. No se probó en consola.

**Pasos para W225:**

1. `python3 tools/stage-dshow-i386.py`. Necesita el toolchain de WSL de `build-dmsynth-i386.py`.
2. `tools/build-wine-hardware.py`, que se niega a seguir si el manifest no es del stager actual. Después, la subida.

**Qué mirar en la corrida de GTA:**

- que ya no aparezca `class {e436ebb3-…} not registered`;
- carga de `quartz.dll`, `devenum.dll` y `pwmpeg1.ax`;
- `PWMPEG open … video=1 640x480 fps=25.000 audio=1 rate=48000`;
- `first_sample` de video y de audio;
- al terminar cada video, `eos`.

**Riesgos:**

- El grafo elige primero `CLSID_VideoRendererDefault` (VMR7 en Wine, que usa ddraw). Cómo se ve sobre la ventana DXVK del juego no está probado.
- Si el juego usa `IMediaSeeking` o `IMediaPosition`, el filtro no las implementa: la llamada falla, pero no simula nada.

### Resultado de W225: el registro no llegó al prefijo vivo

- En `reports/wine-hardware-w225/physical/20261104T211135Z/run-0003.log` sigue `class {e436ebb3-…} not registered`, y no hay líneas `PWMPEG`. El `system.reg` de la consola (1 423 302 bytes) no tiene ninguna de las claves de DirectShow.
- **Por qué no llegó.** `wine-prefix/system.reg` sí es un archivo de runtime, y la subida lo reemplaza entero cuando cambia: así llegaron antes GeckoPath, las clases de audio de W121 y DirectMusic. Pero W225 run-0001 arrancó a las 21:03:53 UTC (`libc=1793826233`), mientras la subida seguía en curso (21:00:45–21:04:29; el PKG sube primero). Ese Wine cargó el registro viejo en memoria y su servidor lo guardó encima del archivo subido. El `system.reg` vivo se escribió por última vez a las 21:09:41 (run-0003), con 252 claves menos que el del build.
- **Fix preparado para W226 (sin tocar archivos compartidos).** Es el script `side-session-notes/…/system-reg-merge-w226.patch.py` (sha256 `4a2773ce…92ed2171`):
  - `build-wine-hardware.py` escribe además `wine-prefix/system.reg.build`, el registro del build en un archivo que Wine nunca reescribe. Se sube como cualquier otro archivo de runtime.
  - `wine_hardware.c`, antes de que arranque Wine, agrega a `system.reg` los bloques de `system.reg.build` que tienen valores y cuya clave falta. Escribe a un temporal y después lo renombra. No toca las claves que la consola ya tiene. Lo hace una vez por build (marca `HW_DIR/system-reg-merged.txt`), porque Wine no vuelve a guardar las claves padre sin valores ni las de dispositivos que vuelve a enumerar. Registra `Wnnn system_reg_merge live_keys=… build_keys=… added=… rc=…` o `already_done`.
  - Probado sobre copias: el launcher parcheado compila con las flags reales y sin warnings. La función, corrida en nativo con el `system.reg` vivo y el de W225, agrega 266 claves (264 de DirectShow), y en la segunda corrida devuelve `already_done`.

### Resultado de W227: el audio de los videos suena, la imagen no se ve

`reports/wine-hardware-w227/physical/20261104T214244Z/run-0005.log`:

- `system_reg_merge already_done`; `quartz`, `devenum` y `pwmpeg1` cargan; `PWMPEG open … 640x480 fps=25.000 audio=1 rate=48000 duration=39.40`.
- Video y audio dan `first_sample hr=0`. Los `stopped …` son porque el usuario saltó los videos.

Análisis:

- **El renderer.** El grafo eligió VMR7 (`image_presenter_StartPresenting`). Su presenter (`dlls/quartz/vmr7_presenter.c`) abre ddraw en `DDSCL_NORMAL` sin ventana, crea la primaria y le pone un clipper con la ventana de video. ddraw creó una ventana oculta (`ddraw_attach_d3d_device … created hidden window 0001004C`).
- **El bug de Wine.** Al poner el clipper, ddraw apunta su swapchain a la ventana del clipper (`SetClipper` → `wined3d_swapchain_set_window`, `dlls/ddraw/surface.c:4784-4796`). Pero el swapchain Vulkan de wined3d conserva el `VkSurface` que creó para la primera ventana: sólo lo rehace ante `OUT_OF_DATE`/`SUBOPTIMAL` (`dlls/wined3d/swapchain.c:931`, `1283-1290`). Cada cuadro se presentó a la ventana oculta: `PWVK show_frame … hwnd=0x1004c` a 25 fps.
- **El compositor.** La ventana de video es `WS_CHILD` de la del juego (`put_Owner`). `ps5_vulkan_frame` sólo acepta ventanas top-level (`find_window`), y la imagen de una hija cae a una copia GDI dentro de ella. La ventana del juego, cuyo cliente es una superficie Vulkan de DXVK, no aportaba nada en pantalla durante los videos: `layers=1`, sólo el fondo. Por eso el usuario veía el escritorio.

**Fix preparado para W229** (W228 se usó para otro cambio): `side-session-notes/…/video-window-w229.patch.py` (sha256 `2a9287c0…74dae86a7`).

1. `tools/build-wined3d-hw.py`, que ahora recompila también `swapchain.c`: antes de cada present Vulkan, si la ventana del swapchain cambió desde que se creó el swapchain Vulkan, se recrea para la ventana nueva. Registra `PWD3D swapchain_window from … to …`. La ventana de cada swapchain se guarda en una tabla dentro de `swapchain.c`, así que `wined3d_private.h` no cambia.
2. `tools/build-win32u-ps4.py` (`ps5drv.c`): `ps5_vulkan_frame` toma la imagen de una ventana hija como capa de su top-level (`GA_ROOT`), sobre el área de la hija, y `ps5_vulkan_forget` la quita igual.

Probado sobre copias: wined3d compila y enlaza sin warnings, y los 47 objetos de win32u compilan (los 3 warnings de `vulkan.c` ya estaban en el build actual). No se probó en consola.

Pasos: aplicar el script a la raíz, correr `build-wined3d-hw.py` y `build-win32u-ps4.py`, después lo de siempre (`stage-dshow-i386.py`, guest, `link-wine-boot.py`, `build-wine-hardware.py`) y subir. Conviene esperar a que termine la subida antes de abrir el título (W225).

Qué mirar:

- `PWD3D swapchain_window from 0001004C to <ventana de video>`;
- `PWVK show_frame … hwnd=<ventana de video> … path=gpu_layer`;
- más capas mientras dura el video.

Riesgo: si durante los videos la ventana del juego no está entre las top-level visibles que sigue `ps5drv`, la imagen vuelve a la copia GDI como hoy. El log lo mostraría porque no aparecería `path=gpu_layer` para la ventana de video.

### W229: el merge de `system.reg` rompió los accesos directos (error mío) y su arreglo

- **Síntoma.** Los accesos directos del menú Inicio y los ítems del panel de control dejaron de abrir: ShellExecute pasaba el `.lnk` o el `.cpl` a CreateProcess (`PWOPEN reject_title_replacement`).
- **Causa.** `merge_system_reg` medía cada archivo con `fstat`, y en PS4 la `struct stat` de la libc del SDK no coincide con la del kernel. Leía unos 3 KB de cada registro:
  - W227 y W228: `live_keys=30 build_keys=29 bytes=2944`, sin escribir nada porque no había diferencias.
  - W229 run-0001: esos primeros bytes diferían, así que "agregó" 20 bloques y escribió un `system.reg` de 5 KB (`live_keys=33 build_keys=29 added=20 bytes=5064`). Las corridas 0001 y 0002 arrancaron Wine con ese registro, sin las asociaciones `lnkfile`/`cplfile`.
- **Estado actual.** La subida de W229 todavía estaba en curso (terminó 22:06:24 UTC; run-0001 arrancó 22:04:49) y volvió a poner el `system.reg` completo. El vivo tiene hoy el mismo hash que el del build (`18a6562a…`). La marca de W229 ya existe, así que W229 no vuelve a hacer el merge: no hace falta reparar nada en la consola. Abrir W229 de nuevo debería mostrar los accesos directos funcionando.
- **Otros cambios de W229.** El de `joy.cpl` (`build-joycpl-hw.py`) sólo copia la DLL y no toca el registro. El `user.reg` vivo difiere del build sólo por la fusión normal de la subida.
- **Fix preparado para W230:** `side-session-notes/…/system-reg-merge-fix-w230.patch.py` (sha256 `d8e1a48e…3f968a3a`), sólo `native/wine_hardware.c`:
  1. `read_whole` lee hasta el final del archivo sin usar `fstat`;
  2. la tabla de claves tiene lugar para las claves de los dos archivos (con un vivo chico y un build grande se llenaba y la búsqueda no terminaba; lo encontré al probar);
  3. no escribe nada salvo que ambos archivos parezcan completos: al menos 256 KiB, final en salto de línea y al menos 1000 claves cada uno. Si no, registra `implausible …`, no escribe y no deja la marca.

  Probado: el launcher compila con las flags reales sin warnings. En nativo, un vivo truncado da `implausible` sin escribir; con archivos completos agrega 266 claves; la segunda corrida da `already_done`.

### W230: el arreglo de W229 no se activó, y por qué

- W230 run-0003: no aparece `PWD3D swapchain_window`, y los cuadros siguen yendo a la ventana oculta `0001004C`. El `wined3d.dll` i386 de W230 sí tiene el cambio (la cadena aparece en `wine/lib/wine/i386-windows` y en `syswow64`).
- **Causa.** El present de wined3d empieza con `wined3d_swapchain_set_window(swapchain, dst_window_override)` (`dlls/wined3d/cs.c:682`), y un override nulo quiere decir "la ventana del dispositivo". Nuestro W128 (`tools/build-ddraw-hw.py`), que muestra la primaria en ventana con el back buffer y un present, presentaba con override nulo. Así, cada present devolvía la ventana oculta y deshacía la ventana de video que VMR7 había puesto con el clipper. El chequeo de W229 nunca veía un cambio de ventana. En Wine upstream eso no pasa, porque ahí la primaria se copia al front buffer sin present.
- **Fix para W232:** `side-session-notes/…/ddraw-present-window-w232.patch.py` (sha256 `bc2d1fae…6488ef637`). Es una línea en `build-ddraw-hw.py`: el present nombra `ddraw->swapchain_window`, que es la ventana del clipper cuando hay una y la de siempre si no. Probado: se aplica a una copia y ddraw compila y enlaza.
- Pasos: aplicar el script, correr `tools/build-ddraw-hw.py` y después lo de siempre. Los cambios de W229 en wined3d y win32u siguen siendo necesarios: recrean el swapchain para la ventana de video y la muestran sobre la ventana del juego.
- Qué mirar: `PWD3D swapchain_window from 0001004C to <ventana de video>`, y `PWVK show_frame … hwnd=<ventana de video> … path=gpu_layer`.

## Qué no se hizo

- No se editó ningún archivo de `tools/`, `native/`, `platform/` ni `fixtures/`.
- No se ejecutó ningún build en `build/` ni `out/`, y no se subió nada. La sonda sólo se compiló y enlazó en un directorio temporal, para verificar el script.
- El EXE se leyó con FTP sólo lectura desde `192.168.68.104:2121` y está únicamente en el directorio temporal de esta sesión.
