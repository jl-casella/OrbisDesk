# OrbisDesk: nombre y compatibilidad de actualización

[English](REBRANDING_ORBISDESK.md) | [Español](REBRANDING_ORBISDESK-es.md)

Desde W283 (03.82), el proyecto se presenta como **OrbisDesk**. Nombre corto: OrbisDesk. Identificador legible para archivos/rutas: `orbisdesk`. Descripción: escritorio y aplicaciones Windows para PS4.

El cambio comprende textos del launcher y overlay, ventanas y diagnósticos propios, clases Win32 y asociaciones generadas, fuentes, scripts, documentación, sondas y cliente de Steam. Wine, WoW64, DXVK, RADV, OpenOrbis y los demás componentes conservan sus nombres técnicos y atribuciones. La figura del icono no contenía el nombre anterior y sigue siendo la ventana con silueta de consola.

## Paquetes

- Aplicación principal: título `OrbisDesk W283`, versión 03.82.
- El archivo local usa el título: `OrbisDesk-W283-03.82.pkg`.
- La transferencia usa `orbisdesk-W283-<sha256-corto>.pkg`.
- Sondas y Steam también se generan con título/archivo OrbisDesk.
- Los identificadores PS4 de actualización no cambian: ORBW00002 para la aplicación, ORBS00001 para Steam y los de las sondas existentes. Se conserva asimismo el CONTENT_ID anterior. Son identidad técnica de instalación, no el nombre mostrado. Así las nuevas versiones pueden instalarse encima de las anteriores.

El recolector continúa leyendo la ubicación original de las builds W001–W282; desde W283 utiliza `/data/orbisdesk`. La limpieza de paquetes reconoce ambos prefijos y sólo retira anteriores después de verificar por lectura de vuelta la transferencia completa. No cambia la regla de instalar/ejecutar manualmente.

## Datos

`/data/wine-prefix`, sus registros, juegos, documentos y perfiles no cambian de ubicación. El código propio usa `/data/orbisdesk` para logs y estado del lanzador. Al primer arranque importa una sola vez los archivos pequeños del directorio histórico: modo de arranque, launch, next/context y ledger de registro. Los archivos nuevos existentes tienen prioridad. Un marcador impide volver a importar una petición consumida en el siguiente arranque. No se borran los originales.

El uploader también acepta el ledger antiguo para preservar ajustes y elecciones que el usuario hizo en la consola antes de la actualización.

DOS usa `AppData\Local\OrbisDesk`. Si sólo existe la carpeta anterior, MoveFile la mueve completa antes de crear la nueva. Si falla, se informa y no se inicia el juego con una carpeta vacía que oculte los guardados originales.

## Nombres antiguos que se conservan deliberadamente

No se reescriben logs, manifiestos, hashes, paquetes archivados, commits ni series históricas de parches. Tampoco URLs y nombres de repositorios externos, identidades de instalación PS4 o constantes de migración. Esas apariciones documentan procedencia o compatibilidad; no representan la marca actual. Los comentarios de parches ya compilados se reconocen en sus dos formas, manteniendo las comprobaciones originales de hashes y binarios.

La copia de fuentes anteriores al cambio y su inventario están en `reports/rebrand-orbisdesk/20261107T105359/`. No es evidencia de una corrida física.

## Verificación

Pruebas enfocadas: reconocimiento estricto de paquetes antiguos/nuevos, selección del directorio histórico por número de build e importación de ajustes compilada en host. Se comprueba que no sobrescribe ajustes actuales, no borra originales y no repite una petición de lanzamiento consumida. Comando:

```sh
python3 tests/test_project_brand.py
```

La recompilación debe regenerar los artefactos cuyos builders/fuentes cambiaron; no se actualizan hashes de manifiestos para aparentar compilaciones inexistentes. El PKG y su SFO se revisan después. Instalación, migración en PS4 y prueba visual se registran por separado; las comprobaciones de host no las reemplazan.

## Resultado de compilación (2026-11-07)

- W283 / 03.82: `out/wine-hardware-w283/OrbisDesk-W283-03.82.pkg`. SHA256: `a3a72e1401c27fc57bf8cac1b9dcf07b280c6ca7c359fd7f7a28d21db37c3c69`. SFO verificado, 58 hashes fuente coincidentes y cierre web con `missing: 0`.
- Steam S1 / 01.05: `out/steam-probe-s1/OrbisDesk-Steam-S1-01.05.pkg`.
- Steam S2 / 01.06: `out/steam-s2/OrbisDesk-Steam-S2-01.06.pkg`. Ambos SFO y hashes verificados; no se ejecutaron pruebas Steam de red nuevas.
- Tres pruebas enfocadas aprobadas; auditoría de marca sin apariciones inesperadas en código activo. Los únicos nombres anteriores retenidos cumplen las excepciones de compatibilidad/procedencia detalladas arriba.
- Evidencia en `reports/rebrand-orbisdesk/20261107T105359/verified-release/`. La instalación y migración visual en PS4 siguen pendientes.
- El generador de icono de la sonda histórica H001B usa ahora las iniciales OD; la sonda antigua archivada no se reempaqueta como nueva evidencia.

El refresco de GUI incorporó imagehlp.dll y wkscli.dll a su cierre PE64; se retiraron sus entradas duplicadas de la lista adicional W261. Se conservan las comprobaciones de duplicados, importaciones y hashes del empaquetado.

## Entrega PS4

W283 transferida con lectura de vuelta el 2026-11-07 a `/data/pkg/orbisdesk-W283-a3a72e1401c2.pkg` (192.168.68.100:2121). 1.823 archivos runtime verificados; 83 subidos y 1.740 ya presentes. Sin fallos de chmod. Un paquete anterior eliminado sólo tras verificar PKG y runtime. Se conservaron seis bloques de configuración de consola. Instalación y ejecución manual pendientes; Steam S1/S2 permanecen locales. Evidencia: `reports/wine-hardware-w283/transfers/20261107T142853Z.json`.

## Nombre limpio desde W284

El título PS4 pasa a ser sólo `OrbisDesk` y el archivo distribuido `OrbisDesk.pkg`. La versión visible se muestra únicamente en el selector de arranque NORMAL/ROOT. Se elimina del resto de pantallas de carga y error. La versión técnica del SFO sigue aumentando (03.83 en esta entrega) para mantener las actualizaciones; W284 permanece en logs y evidencia interna. No cambia el funcionamiento de Wine.
