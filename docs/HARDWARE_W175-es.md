# W175: memoria directa para los compromisos grandes (fase 6) y temas claro/oscuro (fase 7)

[English](HARDWARE_W175.md) | [Español](HARDWARE_W175-es.md)

APP_VER 02.74. Base W174. El resultado de W174 está en `docs/HARDWARE_W174.md`.

## Memoria directa

**El problema** (W174): el título tiene ~400 MB de memoria flexible y ~4,6 GB de memoria directa libre, y SuperMarioKart necesita más memoria flexible de la que hay.

`tools/build-audio-ps4.py`, `virtual.c` de ntdll, sólo en Orbis:
- **Compromisos grandes:** un compromiso de 1 MiB o más mapea memoria directa (`sceKernelAllocateDirectMemory` tipo WB_ONION y `sceKernelMapDirectMemory` fijo) sobre cada tramo sin comprometer.
  - Cada tramo queda anotado con su offset en una tabla de 8192 entradas.
  - Se registra `PWVM commit … direct runs=…`, con lo que el kernel reporta de la región y los totales.
- **Liberación:** `unmap_area` y el decommit (`pw_rereserve`) devuelven antes la memoria directa del rango con `sceKernelReleaseDirectMemory`, también por partes.
- **Si falla:** si la reserva o el mapeo fallan, o la tabla está llena, el compromiso sigue por memoria flexible como antes, con `PWVM direct map … failed`.

`platform/ps4/pw_wine_platform.c`, `commit_reserved`: no mapea memoria flexible sobre una región que el kernel reporta como memoria directa, aunque no la marque como comprometida.

Se espera que SuperMarioKart termine la carrera y salga sin `PWVM fault`.

## Temas claro y oscuro, y Aero (fase 7, sesión de accesos directos)

### Punto de partida

- El aspecto oscuro de OrbisDesk no es un estilo visual: son los colores del sistema que `build-wine-hardware.py` escribe en `HKCU\Control Panel\Colors` (W045).
- En winecfg, Integración de escritorio:
  - la lista de temas mostraba solo "(Sin tema)": busca estilos visuales (`.msstyles`) en `C:\windows\resources\themes`, y esa carpeta estaba vacía;
  - "Instalar tema..." acepta archivos `.theme` y aplica al momento su sección `[Control Panel\Colors]` (`do_parse_theme`, `programs/winecfg/theme.c`).
- Wine no trae un estilo visual oscuro. Su único estilo es `aero.msstyles`, claro. El selector de tema de aplicaciones claro/oscuro solo guarda `AppsUseLightTheme`, que uxtheme informa a los programas que lo consultan; no cambia los controles.

### Cambios

- `tools/build-wine-hardware.py`:
  - escribe `C:\windows\resources\themes\Orbis Oscuro.theme` (los colores actuales, del mismo diccionario `DARK`) y `Orbis Claro.theme` (los colores por defecto de Windows 10);
  - si los dos esquemas no nombran los mismos colores, la build se detiene;
  - copia `aero.msstyles` a `C:\windows\resources\themes\aero\`, como `wine.inf`. No se activa: `ThemeManager` queda como estaba.
- `tools/stage-wine-extras.py`: suma `aero.msstyles`, el del árbol fijado de x86_64, 7,2 MB. Es un solo archivo para las dos vistas, porque uxtheme lo abre como recurso.
- `tools/upload-hardware.py`: la fusión de `user.reg` (W172) ahora conserva de la consola, cada una con sus subclaves:
  - `Software\Wine\AppDefaults`;
  - `Control Panel\Colors`;
  - `Control Panel\Desktop\WindowMetrics`;
  - `Software\Microsoft\Windows\CurrentVersion\ThemeManager`;
  - `Software\Microsoft\Windows\CurrentVersion\Themes\Personalize`.
  - El registro de la subida pasa a tener `user_reg.console_blocks_kept` (por clave) y `user_reg.reset`.
- Probado sin conexión:
  - la fusión, contra el `user.reg` de W173:
    - sin cambios del usuario da el mismo archivo;
    - con el tema claro, Aero y ajustes por programa en la consola, conserva los tres, y los overrides de DLL siguen siendo los de la build;
    - una segunda subida no cambia nada;
  - los dos `.theme` tienen 31 colores cada uno, con fin de línea CRLF.

### Colores en manos de la consola

- Desde la primera instalación de W175, los colores, las métricas, el estilo visual y el tema de aplicaciones son los de la consola: una build ya no los cambia aunque cambie `DARK`.
- Si una build necesita cambiarlos (por ejemplo, un esquema oscuro corregido), pone en su manifest, solo esa vez: `manifest['user_reg_reset']=['Control Panel\\Colors']`
  - Esa subida toma esa clave de la build. Las demás, incluidos los AppDefaults, siguen viniendo de la consola. `user_reg.reset` lo registra.
  - Acepta solo claves de la lista de arriba; cualquier otra detiene la subida.
- No hace falta borrar `user.reg` con `obsolete_files`: se llevaría también los ajustes por programa.
- Sigue valiendo el límite de W172: hay que cerrar la app antes de instalar.

### Prueba

1. winecfg → Integración de escritorio → "Instalar tema..." → `C:\windows\resources\themes\Orbis Claro.theme` → Aplicar. Ventanas, menús, barra de tareas y menú Inicio tienen que verse en claro.
2. Lo mismo con `Orbis Oscuro.theme`: vuelve al aspecto actual.
3. Lista de temas: tiene que aparecer "Aero".
   - Elegirlo, con el esquema claro, y ver cómo se dibujan botones, casillas y barras de desplazamiento.
   - Mirar si se nota más lento, por ejemplo al abrir el menú Inicio o al mover ventanas.
   - Volver a "(Sin tema)".
4. Dejar el tema claro, cerrar la app e instalar la build siguiente: tiene que seguir en claro, con `user_reg.console_blocks_kept` en el registro de la subida.

Riesgos:
- Aero dibuja los controles con bitmaps a través de uxtheme, en la CPU. Puede ser más lento, y se ve mezclado con el esquema oscuro.
- Algunos dibujos propios de explorer (el glifo de Inicio y los de Run y Exit) se pensaron sobre fondo oscuro; en claro hay que ver si se distinguen.

## Prueba física

Reporte: `reports/wine-hardware-w175/physical/20261103T202505Z/`. Respuesta: "Otro problema"; según el usuario, SuperMarioKart "se cerró antes, después de seleccionar personaje en el menú".

- **Memoria directa:** funciona, sin ningún `PWVM fault` ni `PWVM direct map … failed`.
  - El kernel reporta las regiones como `flags=0x12` (memoria directa, comprometida).
  - Por partida hubo unas 20 reservas, 14 liberaciones y 6 entradas vivas, unos 62 MB.
- **Nuevo fallo**, en las tres partidas a los 75–85 s, al cargar la pista:
  - `d3dxof_parsing:parse_template_members_list Array cannot be used to specify variable array size`;
  - después, `c0000005` en `0x1006BB3A`, dentro del juego, y el juego sale con status 0.
  - El error aparece sólo en W175, justo después de un compromiso directo de 2,4 MB (`base=0x8910000 size=0x260000`).
  - La memoria directa no viene en cero, y Windows entrega en cero la memoria comprometida. El parser de `.x` leyó restos de memoria. Se corrige en W176.
- **Temas:** el usuario le pidió cambios a la sesión de accesos directos.
