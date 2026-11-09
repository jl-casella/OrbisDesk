# Índice de documentación

[English](INDEX.md) | [Español](INDEX-es.md)

Índice de toda la documentación pública. Empezar por la guía para IA y el estado actual. Los documentos históricos y borradores conservan su contexto; un enlace no implica validación actual. Las notas privadas, dependencias descargadas y evidencia ignorada no se indexan.

Regenerar ambos idiomas: `python3 tools/build-doc-index.py`.

## Entrada y políticas

- [AGENTS-es.md](../AGENTS-es.md) — OrbisDesk: guía para desarrollo asistido por IA
- [README-es.md](../README-es.md) — OrbisDesk
- [THIRD_PARTY-es.md](../THIRD_PARTY-es.md) — Licencias y procedencia
- [CURRENT_STATE-es.md](CURRENT_STATE-es.md) — Punto de retoma: OrbisDesk W288 (03.87), 2026-11-07
- [DOCUMENTATION_POLICY-es.md](DOCUMENTATION_POLICY-es.md) — Política de documentación
- [REBRANDING_ORBISDESK-es.md](REBRANDING_ORBISDESK-es.md) — OrbisDesk: nombre y compatibilidad de actualización
- [REPOSITORY_LAYOUT-es.md](REPOSITORY_LAYOUT-es.md) — Contenido del repositorio y reconstrucción de dependencias
- [STATUS-es.md](STATUS-es.md) — Evidencia y bloqueos

## Arquitectura y ejecución de invitados

- [investigacion-gta-vc-base-0x400000-es.md](investigacion-gta-vc-base-0x400000-es.md) — Investigación: GTA Vice City (PE32) y la base 0x400000
- [investigacion-wow64-en-explorer-es.md](investigacion-wow64-en-explorer-es.md) — Programas de 32 bits como huéspedes de explorer: factibilidad

## Emulador y validación del escritorio

- [SHAD_W284_DESKTOP-es.md](SHAD_W284_DESKTOP-es.md) — Escritorio W284 en el fork Linux de shadPS4
- [TASKBAR_CENTER_FIX-es.md](TASKBAR_CENTER_FIX-es.md) — Fondo de barra y pruebas de Start en shadPS4

## Cliente Steam nativo, juegos y atribuciones

- [GAMES-es.md](GAMES-es.md) — W114: juegos en Start → Programs → Games
- [STEAM_HOSTED-es.md](STEAM_HOSTED-es.md) — El cliente de Steam dentro de OrbisDesk
- [STEAM_S1-es.md](STEAM_S1-es.md) — S1: HTTPS nativo para el cliente de Steam (ORBS00001)
- [STEAM_S2-es.md](STEAM_S2-es.md) — S2: descarga anónima de un depot de Steam
- [STEAM_S3-es.md](STEAM_S3-es.md) — S3: login del usuario por QR y biblioteca
- [STEAM_S4-es.md](STEAM_S4-es.md) — S4: instalar un juego de la biblioteca
- [STEAM_S5-es.md](STEAM_S5-es.md) — S5: lanzar desde el Explorer de OrbisDesk un juego instalado (en curso)
- [THIRD_PARTY_FONTS-es.md](THIRD_PARTY_FONTS-es.md) — FreeType y fuentes del runtime

## Incrementos de plataforma y Wine (históricos)

- [INCREMENT_01-es.md](INCREMENT_01-es.md) — Incremento 1: memoria administrada y fork reproducible
- [INCREMENT_02-es.md](INCREMENT_02-es.md) — Incremento 2: TEB de 32 bits y ejecución hostexec
- [INCREMENT_03-es.md](INCREMENT_03-es.md) — Incremento 3: dispatcher común de CPU
- [INCREMENT_04-es.md](INCREMENT_04-es.md) — Incremento 4: primer PE32 sin importaciones
- [INCREMENT_05-es.md](INCREMENT_05-es.md) — Incremento 5: secciones PE de 4 KiB sobre páginas PS4 de 16 KiB
- [INCREMENT_06-es.md](INCREMENT_06-es.md) — Incremento 6: DLL PE32 e importaciones reales por IAT
- [INCREMENT_07-es.md](INCREMENT_07-es.md) — Incremento 7: inicialización de DLL y TLS por hilo
- [INCREMENT_08-es.md](INCREMENT_08-es.md) — Incremento 8: proceso PE32 y primer bring-up de Wine
- [INCREMENT_09-es.md](INCREMENT_09-es.md) — Incremento 9: memoria, rutas y archivos del lado Unix de Wine
- [INCREMENT_10-es.md](INCREMENT_10-es.md) — Incremento 10: enlace completo e intento real de arranque de Wine
- [INCREMENT_11-es.md](INCREMENT_11-es.md) — Incremento 11: descriptores e IPC de Wine
- [INCREMENT_12-es.md](INCREMENT_12-es.md) — Incremento 12: transferencia de archivos y sockets
- [INCREMENT_13-es.md](INCREMENT_13-es.md) — Incremento 13: pipes y conexión completa con wineserver
- [INCREMENT_14-es.md](INCREMENT_14-es.md) — Incremento 14: directorios PS4 y diagnóstico de wineboot
- [INCREMENT_15-es.md](INCREMENT_15-es.md) — Incremento 15: identidad de archivos, symlinks y prefijo externo
- [INCREMENT_16-es.md](INCREMENT_16-es.md) — Incremento 16: console32-bare.exe sin Wine
- [INCREMENT_17-es.md](INCREMENT_17-es.md) — Incremento 17: carga de DLL desde disco sin Wine
- [INCREMENT_18-es.md](INCREMENT_18-es.md) — Incremento 18: console32.exe con el CRT de mingw, sin Wine
- [INCREMENT_19-es.md](INCREMENT_19-es.md) — Incremento 19: consumir el prefijo externo en shadPS4
- [INCREMENT_20-es.md](INCREMENT_20-es.md) — Incremento 20: mmap, fallback de Wine e imagen principal reubicada
- [INCREMENT_21-es.md](INCREMENT_21-es.md) — Incremento 21: mappings privados y protección de ntdll
- [INCREMENT_22-es.md](INCREMENT_22-es.md) — Incremento 22: GS por hilo, contextos de señal y arranque de Windows hasta WoW64
- [INCREMENT_23-es.md](INCREMENT_23-es.md) — Incremento 23: console32-bare.exe mediante Wine, con el traductor como CPU WoW64
- [INCREMENT_24-es.md](INCREMENT_24-es.md) — Incremento 24: UI de Wine en pantalla, con win32u y un driver de usuario en proceso
- [INCREMENT_25-es.md](INCREMENT_25-es.md) — Incremento 25: texto con FreeType para Orbis

## Builds físicas y evidencia por subsistema

- [HARDWARE_G001-es.md](HARDWARE_G001-es.md) — G001: Vulkan (RADV sobre GNM) en la PS4, hito H0
- [HARDWARE_H001-es.md](HARDWARE_H001-es.md) — Primera prueba física: H001
- [HARDWARE_W001-es.md](HARDWARE_W001-es.md) — Prueba física W001: Wine en la PS4
- [HARDWARE_W002-es.md](HARDWARE_W002-es.md) — Prueba física W002: prefijo sin enlaces simbólicos
- [HARDWARE_W003_W011-es.md](HARDWARE_W003_W011-es.md) — Pruebas físicas W003–W011: Wine arranca en la PS4 hasta el servidor interno
- [HARDWARE_W096-es.md](HARDWARE_W096-es.md) — W096: MangoHud compartido entre invitados
- [HARDWARE_W097-es.md](HARDWARE_W097-es.md) — W097: diagnóstico de Start después de cerrar invitados gráficos
- [HARDWARE_W098-es.md](HARDWARE_W098-es.md) — W098: carga de gráficos después de cerrar invitados
- [HARDWARE_W099-es.md](HARDWARE_W099-es.md) — W099: cierre de MangoHud sin retener el bloqueo compartido
- [HARDWARE_W100-es.md](HARDWARE_W100-es.md) — W100: exclusión mutua para el asignador nativo del SDK
- [HARDWARE_W101-es.md](HARDWARE_W101-es.md) — W101: comparación de cierre sin cargar MangoHud
- [HARDWARE_W102-es.md](HARDWARE_W102-es.md) — W102: MangoHud reactivado con muestreo en el frame
- [HARDWARE_W103-es.md](HARDWARE_W103-es.md) — W103: porcentajes nativos para MangoHud
- [HARDWARE_W104-es.md](HARDWARE_W104-es.md) — W104: etiquetas CPU/GPU y fuente CPU corregida
- [HARDWARE_W105-es.md](HARDWARE_W105-es.md) — W105: unidades y archivos del administrador WFM
- [HARDWARE_W106-es.md](HARDWARE_W106-es.md) — W106: abrir archivos desde WFM sin reemplazar el escritorio
- [HARDWARE_W107-es.md](HARDWARE_W107-es.md) — W107: asociaciones de texto visibles para HKCR
- [HARDWARE_W108-es.md](HARDWARE_W108-es.md) — W108: renombrar carpetas y borrar árboles desde WFM
- [HARDWARE_W109-es.md](HARDWARE_W109-es.md) — W109: borrado pendiente y diagnóstico del error 145
- [HARDWARE_W110-es.md](HARDWARE_W110-es.md) — W110: entradas omitidas por la enumeración de Wine
- [HARDWARE_W111-es.md](HARDWARE_W111-es.md) — W111: filtrar registros BSD de entradas borradas
- [HARDWARE_W112-es.md](HARDWARE_W112-es.md) — W112: primer runtime DOS dentro de Wine
- [HARDWARE_W112_TASKMGR-es.md](HARDWARE_W112_TASKMGR-es.md) — W112: Administrador de tareas (Performance, Processes y End task)
- [HARDWARE_W113-es.md](HARDWARE_W113-es.md) — W113: diagnóstico de audio DOS (smb.exe sin sonido)
- [HARDWARE_W114-es.md](HARDWARE_W114-es.md) — W114: CARMEN.EXE cerraba todo el escritorio
- [HARDWARE_W116-es.md](HARDWARE_W116-es.md) — W116: programas de 32 bits (fase 1 del plan PE32)
- [HARDWARE_W119-es.md](HARDWARE_W119-es.md) — W119: DLL de 32 bits (fase 2 del plan PE32)
- [HARDWARE_W120-es.md](HARDWARE_W120-es.md) — W120: audio de Windows (fase 3 del plan PE32)
- [HARDWARE_W124-es.md](HARDWARE_W124-es.md) — W124: Direct3D 8–11 con DXVK (fase 4 del plan PE32)
- [HARDWARE_W127-es.md](HARDWARE_W127-es.md) — W127: DirectDraw y Direct3D 7 con wined3d sobre Vulkan (fase 4b)
- [HARDWARE_W135-es.md](HARDWARE_W135-es.md) — W135: ¿corre la PS4 código de 32 bits nativo? (fase 5)
- [HARDWARE_W136-es.md](HARDWARE_W136-es.md) — W136: entrada de señales para código de 32 bits nativo (fase 5A, paso 1)
- [HARDWARE_W137-es.md](HARDWARE_W137-es.md) — W137: código de 32 bits nativo (fase 5A, paso 2)
- [HARDWARE_W138-es.md](HARDWARE_W138-es.md) — W138: música MIDI por DirectMusic (fase 5)
- [HARDWARE_W139-es.md](HARDWARE_W139-es.md) — W139: instrumentos de DirectMusic con GUID_Download (fase 5)
- [HARDWARE_W140-es.md](HARDWARE_W140-es.md) — W140: batería General MIDI y flechas para DirectInput (fase 5)
- [HARDWARE_W141-es.md](HARDWARE_W141-es.md) — W141: flechas como teclas extendidas, por VK (fase 5)
- [HARDWARE_W142-es.md](HARDWARE_W142-es.md) — W142: salida a pantalla por GPU (fase 6, paso 1)
- [HARDWARE_W143-es.md](HARDWARE_W143-es.md) — W143: salida a pantalla por GPU, orden de arranque corregido (fase 6, paso 1)
- [HARDWARE_W144-es.md](HARDWARE_W144-es.md) — W144: la GPU apila las ventanas (fase 6, paso 2)
- [HARDWARE_W145-es.md](HARDWARE_W145-es.md) — W145: capas en GPU sin marco negro (fase 6, paso 2)
- [HARDWARE_W146-es.md](HARDWARE_W146-es.md) — W146: forma de las ventanas como transparencia, con diagnóstico (fase 6, paso 2)
- [HARDWARE_W147-es.md](HARDWARE_W147-es.md) — W147: diagnóstico de la pila de capas (fase 6, paso 2)
- [HARDWARE_W148-es.md](HARDWARE_W148-es.md) — W148: volcado de cuadros para el marco negro (fase 6, paso 2)
- [HARDWARE_W149-es.md](HARDWARE_W149-es.md) — W149: shader de capas sin divergencia (fase 6, paso 2)
- [HARDWARE_W150-es.md](HARDWARE_W150-es.md) — W150: sin los diagnósticos del marco negro (fase 6, paso 2)
- [HARDWARE_W151-es.md](HARDWARE_W151-es.md) — W151: sin los logs viejos del menú Inicio
- [HARDWARE_W152-es.md](HARDWARE_W152-es.md) — W152: cuadros Vulkan como capa de la GPU (fase 6, pasos 2 y 3)
- [HARDWARE_W153-es.md](HARDWARE_W153-es.md) — W153: lectura de imágenes sin FLAT, con chequeo previo (fase 6, pasos 2 y 3)
- [HARDWARE_W154-es.md](HARDWARE_W154-es.md) — W154: la imagen Vulkan sigue a su ventana al moverla (fase 6)
- [HARDWARE_W155-es.md](HARDWARE_W155-es.md) — W155: programas de 32 bits sin trazas y a pantalla completa (fase 6)
- [HARDWARE_W156-es.md](HARDWARE_W156-es.md) — W156: la imagen Vulkan en el área cliente real, con su proporción (fase 6)
- [HARDWARE_W157-es.md](HARDWARE_W157-es.md) — W157: medición de CPU por cuadro (fase 6)
- [HARDWARE_W158-es.md](HARDWARE_W158-es.md) — W158: dlopen sin estado por hilo de musl (cuelgues después de varios programas)
- [HARDWARE_W159-es.md](HARDWARE_W159-es.md) — W159: perfil de wow64native en programas de 32 bits (fase 6)
- [HARDWARE_W160-es.md](HARDWARE_W160-es.md) — W160: tiempo por operación de wined3d y syscalls por hilo (fase 6)
- [HARDWARE_W161-es.md](HARDWARE_W161-es.md) — W161: qué son las copias 2D de SuperMarioKart (fase 6)
- [HARDWARE_W162-es.md](HARDWARE_W162-es.md) — W162: staging de subidas en memoria con caché (fase 6)
- [HARDWARE_W163-es.md](HARDWARE_W163-es.md) — W163: wined3d de 32 bits deja mapeados sus bloques de memoria (fase 6)
- [HARDWARE_W164-es.md](HARDWARE_W164-es.md) — W164: staging de bajadas en memoria con caché (fase 6)
- [HARDWARE_W165-es.md](HARDWARE_W165-es.md) — W165: sprites con color key en la GPU, contador de FPS con F12 y tiempo de las llamadas Vulkan (fase 6)
- [HARDWARE_W166-es.md](HARDWARE_W166-es.md) — W166: llamadas Vulkan de 32 bits en lotes (fase 6)
- [HARDWARE_W167-es.md](HARDWARE_W167-es.md) — W167: agrupamiento de llamadas Vulkan de 32 bits activado (fase 6)
- [HARDWARE_W168-es.md](HARDWARE_W168-es.md) — W168: excepciones de 32 bits sin perder FS, sprites sin objetos por copia y acceso directo en el escritorio (fase 6)
- [HARDWARE_W169-es.md](HARDWARE_W169-es.md) — W169: FS al reanudar, mapeos ubicados al liberar y acceso directo en el escritorio del usuario (fase 6)
- [HARDWARE_W170-es.md](HARDWARE_W170-es.md) — W170: salida de hilo con NULL, diagnóstico del fallo del heap, escritorio sin duplicado y apariencia (fase 6)
- [HARDWARE_W171-es.md](HARDWARE_W171-es.md) — W171: estado de la página en el fallo del heap (fase 6)
- [HARDWARE_W172-es.md](HARDWARE_W172-es.md) — W172: compromiso de páginas invisibles al kernel (fase 6), Direct3D 10/11 en 32 bits con el dxgi de DXVK, y winecfg (fase 7)
- [HARDWARE_W173-es.md](HARDWARE_W173-es.md) — W173: compromiso de páginas del heap, Mesa residente, DLL de winecfg (fases 6 y 7)
- [HARDWARE_W174-es.md](HARDWARE_W174-es.md) — W174: memoria flexible devuelta al liberar (fase 6), winecfg completo (fase 7) y red para programas Windows (fase 8)
- [HARDWARE_W175-es.md](HARDWARE_W175-es.md) — W175: memoria directa para los compromisos grandes (fase 6) y temas claro/oscuro (fase 7)
- [HARDWARE_W176-es.md](HARDWARE_W176-es.md) — W176: memoria directa en cero (fase 6) y arreglos de red (fase 8)
- [HARDWARE_W177-es.md](HARDWARE_W177-es.md) — W177: limpieza de los diagnósticos de la carrera (fase 6), temas Luna y Noir (fase 7) y navegador (fase 9)
- [HARDWARE_W178-es.md](HARDWARE_W178-es.md) — W178: sin los diagnósticos de velocidad, descriptor sets por lotes (fases 5 y 6) y mando por XInput (fases 5 y 7)
- [HARDWARE_W179-es.md](HARDWARE_W179-es.md) — W179: navegador con bcrypt (fase 9), DirectInput y aspecto XP en Luna/Noir (fase 7), sonda USB (fase 10) e íconos
- [HARDWARE_W180-es.md](HARDWARE_W180-es.md) — W180: Unix side de crypt32 (fase 9), applet de winecfg que espera y segunda sonda USB (fase 10)
- [HARDWARE_W181-es.md](HARDWARE_W181-es.md) — W181: perfiles de teclas del mando para juegos que sólo usan teclado (fase 5)
- [HARDWARE_W182-es.md](HARDWARE_W182-es.md) — W182: reservas grandes y type libraries para el navegador (fase 9), diagnóstico de Apply en winecfg, íconos de Control Panel y Start cuadrado (fase 7)
- [HARDWARE_W183-es.md](HARDWARE_W183-es.md) — W183: Pale Moon en su propio proceso (fase 9), Apply de winecfg sin bloqueo y teclas del mando con varias fuentes (fases 5 y 7)
- [HARDWARE_W184-es.md](HARDWARE_W184-es.md) — W184: memoria para vistas grandes y perfil de Pale Moon (fase 9), salida de invitados sin atexit ajenos (fase 7)
- [HARDWARE_W185-es.md](HARDWARE_W185-es.md) — W185: Pale Moon siempre en línea, sin proxy del sistema ni IPv6, con registro de red (fase 9)
- [HARDWARE_W186-es.md](HARDWARE_W186-es.md) — W186: pedidos de contexto de otro hilo sin señal (Pale Moon, fase 9)
- [HARDWARE_W187-es.md](HARDWARE_W187-es.md) — W187: registro de red de Pale Moon (fase 9)
- [HARDWARE_W188-es.md](HARDWARE_W188-es.md) — W188: números de opciones de socket del kernel (fases 8 y 9)
- [HARDWARE_W189-es.md](HARDWARE_W189-es.md) — W189: limpieza de diagnósticos y Direct3D 11 de 64 bits
- [HARDWARE_W190-es.md](HARDWARE_W190-es.md) — W190: Direct3D 11 de 64 bits con el dxgi de DXVK y el registro guardado a tiempo
- [HARDWARE_W191-es.md](HARDWARE_W191-es.md) — W191: Direct3D 11 detectado al abrir y aleatoriedad del kernel
- [HARDWARE_W192-es.md](HARDWARE_W192-es.md) — W192: Direct3D 11 de 64 bits dentro de explorer
- [HARDWARE_W194-es.md](HARDWARE_W194-es.md) — W193 y W194: un juego Unity con Direct3D 11 (The Lost Forest)
- [HARDWARE_W195-es.md](HARDWARE_W195-es.md) — W195: señales a un hilo concreto (pthread_kill)
- [HARDWARE_W197-es.md](HARDWARE_W197-es.md) — W196 y W197: cerrar un juego Unity sin cerrar la app
- [HARDWARE_W228-es.md](HARDWARE_W228-es.md) — W228: modo ROOT y discos USB como unidades
- [HARDWARE_W284-es.md](HARDWARE_W284-es.md) — OrbisDesk: paquete con nombre limpio (W284)
- [HARDWARE_W285_W288-es.md](HARDWARE_W285_W288-es.md) — W285–W288: streams de audio de invitados, carpeta de logs de GPU, menú GRÁFICOS y MangoHud en wined3d
- [HARDWARE_mando-hid-es.md](HARDWARE_mando-hid-es.md) — Mando como gamepad HID (stack HID de Wine dentro del proceso)
- [HARDWARE_mando-juegos-analisis-es.md](HARDWARE_mando-juegos-analisis-es.md) — Mando para juegos después de W195: análisis (borrador, sin cambios de código)

## Borradores y planes (no son evidencia de aceptación)

- [CI_PLAN-es.md](CI_PLAN-es.md) — Plan de CI: checks rápidos de PR, piloto manual de matriz y distribuciones
- [HARDWARE_W168-escritorio-borrador-es.md](HARDWARE_W168-escritorio-borrador-es.md) — W168 (borrador): accesos directos en el escritorio
- [HARDWARE_W172-fase7-borrador-es.md](HARDWARE_W172-fase7-borrador-es.md) — W172: Direct3D 10/11 en 32 bits con el dxgi de DXVK, y winecfg (fase 7)
- [HARDWARE_W174-red-borrador-es.md](HARDWARE_W174-red-borrador-es.md) — W174: red para programas Windows (fase 8, borrador)
- [HARDWARE_W175-borrador-es.md](HARDWARE_W175-borrador-es.md) — W175: temas claro y oscuro, y Aero, en winecfg (fase 7)
- [HARDWARE_W176-red-borrador-es.md](HARDWARE_W176-red-borrador-es.md) — W176: red, arreglos tras W174 (fase 8, borrador)
- [HARDWARE_W177-navegador-borrador-es.md](HARDWARE_W177-navegador-borrador-es.md) — W177: navegador y webviews (fase 9, borrador)
- [HARDWARE_W177-temas-borrador-es.md](HARDWARE_W177-temas-borrador-es.md) — W177, parte de temas: Luna y Noir, y sin estilo visual por defecto
- [HARDWARE_W178-mando-borrador-es.md](HARDWARE_W178-mando-borrador-es.md) — W178, parte del mando: XInput con el mando de la PS4, modo juego y joy.cpl (fase 7)
- [HARDWARE_W179-borrador-es.md](HARDWARE_W179-borrador-es.md) — W179, partes de la sesión de configuración de Wine: DirectInput del mando y aspecto XP de Luna y Noir
- [HARDWARE_W179-navegador-borrador-es.md](HARDWARE_W179-navegador-borrador-es.md) — W179: arreglos del navegador y webviews (fase 9, borrador)
- [HARDWARE_W180-navegador-borrador-es.md](HARDWARE_W180-navegador-borrador-es.md) — W180: Unix side de crypt32 (fase 9, borrador)
- [HARDWARE_W180-usb-borrador-es.md](HARDWARE_W180-usb-borrador-es.md) — W180: discos USB como unidades D: a K: (fase 10, borrador)
- [HARDWARE_W181-teclas-plan-borrador-es.md](HARDWARE_W181-teclas-plan-borrador-es.md) — W181, parte del mando: perfiles de teclas para juegos que solo usan teclado
- [HARDWARE_W182-navegador-borrador-es.md](HARDWARE_W182-navegador-borrador-es.md) — W182: registro de type libraries (fase 9, borrador)
- [HARDWARE_W182-winecfg-borrador-es.md](HARDWARE_W182-winecfg-borrador-es.md) — W182, parte de winecfg y del aspecto: diagnóstico del congelamiento al aplicar un tema, iconos del Panel de control y botón Inicio recto
- [HARDWARE_W183-navegador-borrador-es.md](HARDWARE_W183-navegador-borrador-es.md) — W183: Pale Moon como título aparte (fase 9, borrador)
- [HARDWARE_W183-winecfg-borrador-es.md](HARDWARE_W183-winecfg-borrador-es.md) — W183, parte de winecfg: Aplicar un tema ya no se congela
- [HARDWARE_W184-navegador-borrador-es.md](HARDWARE_W184-navegador-borrador-es.md) — W184: Pale Moon sin D3D11 (fase 9, borrador)
- [HARDWARE_W184-winecfg-borrador-es.md](HARDWARE_W184-winecfg-borrador-es.md) — W184, parte de winecfg: Aceptar o Cancelar ya no cierran todo
- [HARDWARE_W185-navegador-borrador-es.md](HARDWARE_W185-navegador-borrador-es.md) — W185: red de Pale Moon (fase 9, borrador)
- [HARDWARE_W187-navegador-borrador-es.md](HARDWARE_W187-navegador-borrador-es.md) — W187: log de red de Pale Moon (fase 9, borrador)
- [HARDWARE_W188-navegador-borrador-es.md](HARDWARE_W188-navegador-borrador-es.md) — W188: keepalive de TCP en Pale Moon (fase 9, borrador)
- [HARDWARE_W190-winecfg-borrador-es.md](HARDWARE_W190-winecfg-borrador-es.md) — W190, parte de winecfg: el tema elegido se mantiene al reiniciar
- [HARDWARE_W197-mangohud-dxvk-borrador-es.md](HARDWARE_W197-mangohud-dxvk-borrador-es.md) — MangoHud en juegos Direct3D por DXVK (borrador para la próxima W)
- [HARDWARE_W203-palemoon-invitado-borrador-es.md](HARDWARE_W203-palemoon-invitado-borrador-es.md) — W203: el escritorio se congela con Pale Moon como invitado (borrador)
- [HARDWARE_W204-palemoon-memoria-borrador-es.md](HARDWARE_W204-palemoon-memoria-borrador-es.md) — W204: Pale Moon como invitado se traba al pedir memoria (borrador)
- [HARDWARE_W205-palemoon-pestana-borrador-es.md](HARDWARE_W205-palemoon-pestana-borrador-es.md) — W205: Pale Moon como invitado se traba al abrir una segunda pestaña (borrador)
- [HARDWARE_W207-palemoon-invitado-borrador-es.md](HARDWARE_W207-palemoon-invitado-borrador-es.md) — W207: Pale Moon como invitado — archivos al terminar, traza del fallo, sin relanzar (borrador)
- [HARDWARE_W208-invitado-descarga-borrador-es.md](HARDWARE_W208-invitado-descarga-borrador-es.md) — W208: un invitado descarga sus DLL y libera su memoria al terminar (borrador)
- [HARDWARE_W209-invitado-salida-borrador-es.md](HARDWARE_W209-invitado-salida-borrador-es.md) — W209: la salida por fallo de un invitado termina y el siguiente arranque limpia lo que quedó (borrador)
- [HARDWARE_W210-invitado-reinicio-borrador-es.md](HARDWARE_W210-invitado-reinicio-borrador-es.md) — W210: un invitado que se reinicia a sí mismo arranca de nuevo cuando ya terminó (borrador)
- [HARDWARE_W212-invitado-orden-borrador-es.md](HARDWARE_W212-invitado-orden-borrador-es.md) — W212: los módulos de un invitado se descargan en orden de dependencias y sin DllMain (borrador)
- [HARDWARE_W214-invitado-carga-borrador-es.md](HARDWARE_W214-invitado-carga-borrador-es.md) — W214: el EXE de un invitado encuentra sus DLL y su descarga espera al loader (borrador)
- [HARDWARE_W215-loader-lock-borrador-es.md](HARDWARE_W215-loader-lock-borrador-es.md) — W215: el loader lock se toma aunque un hilo que lo esperaba haya sido terminado (borrador)
- [HARDWARE_W216-invitado-terminado-borrador-es.md](HARDWARE_W216-invitado-terminado-borrador-es.md) — W216: el último hilo de un invitado terminado sale sin DLL_THREAD_DETACH (borrador)
- [HARDWARE_W220-winecfg-solo-borrador-es.md](HARDWARE_W220-winecfg-solo-borrador-es.md) — W220: casilla "Run alone" en la pestaña Applications de winecfg (borrador)
- [HARDWARE_Wxxx-navegador-borrador-es.md](HARDWARE_Wxxx-navegador-borrador-es.md) — Wxxx: Pale Moon sin log de red (fase 9, borrador)
- [HARDWARE_Wxxx-palemoon-invitado-2-borrador-es.md](HARDWARE_Wxxx-palemoon-invitado-2-borrador-es.md) — Wxxx: Pale Moon como invitado, segunda ronda de diagnóstico (borrador)
- [HARDWARE_Wxxx-palemoon-invitado-borrador-es.md](HARDWARE_Wxxx-palemoon-invitado-borrador-es.md) — Wxxx: Pale Moon como invitado congela el escritorio (diagnóstico, borrador)
- [HARDWARE_fase7-mando-plan-borrador-es.md](HARDWARE_fase7-mando-plan-borrador-es.md) — Fase 7, resto: mando de la PS4 por XInput y DirectInput, y joy.cpl (plan, borrador)
- [HARDWARE_fase7-plan-borrador-es.md](HARDWARE_fase7-plan-borrador-es.md) — Fase 7 del plan PE32: dxgi de DXVK por programa y winecfg (plan, borrador)
- [HARDWARE_temas-plan-borrador-es.md](HARDWARE_temas-plan-borrador-es.md) — Temas claro y oscuro en winecfg (plan, borrador)

## Otras notas públicas

- [CI-es.md](CI-es.md) — Ejecutar CI y medir la matriz de plataforma
- [RELEASES-es.md](RELEASES-es.md) — Construcción del producto, releases y rama de desarrollo
- [RELEASE_LICENSES-es.md](RELEASE_LICENSES-es.md) — Licencias del release (alpha-1)
- [RELEASE_TRACES-es.md](RELEASE_TRACES-es.md) — Trazas en release: un solo interruptor para el alpha-1
