# W177, parte de temas: Luna y Noir, y sin estilo visual por defecto

[English](HARDWARE_W177-temas-borrador.md) | [Español](HARDWARE_W177-temas-borrador-es.md)

Borrador de la sesión lateral de temas. La sesión principal lo suma a `HARDWARE_W177.md` junto con la fase 9.

## Pedido y resultado de W175

- El usuario pidió los temas de Windows XP (Luna) y Royale Noir, lo más parecidos posible a los de Microsoft, y Aero por defecto.
- Después de probar W175 contó que Aero se sentía más lento. Por eso el valor por defecto quedó **sin estilo visual**.

## Luna y Noir

- Los `.msstyles` de Microsoft no se pueden redistribuir. Estos son propios, armados desde el `aero.msstyles` del Wine fijado (LGPL), con `tools/build-msstyles-hw.py` (nuevo).
- Por cada estilo, el builder:
  - copia las fuentes de Aero a un overlay;
  - recolorea todos los bitmaps con la paleta del estilo;
  - dibuja de nuevo, estado por estado y con los tamaños y la disposición de Aero, 32 bitmaps: botones, casillas, botones de opción, barras de desplazamiento (botones, pulgar, canal), pestañas, encabezados de lista, bordes de edición y de combo, y groupbox.
- **Luna:** botones con borde azul oscuro y cara blanca a beige, brillo naranja al pasar el mouse y borde azul en el botón por defecto. Casillas con tilde verde, botones de opción con punto verde, barras de desplazamiento azul lavanda, pestañas con borde superior naranja, barra de progreso en bloques verdes.
- **Noir:** botones negros brillantes, casillas oscuras con tilde blanca, barras de desplazamiento grafito y barra de progreso continua.
- El INI de cada estilo tiene su nombre ("Luna", "Noir") y, en `[SysMetrics]`, los colores del sistema de XP Luna y de Royale Noir. uxtheme los aplica al elegir el estilo.
  - Luna: barra de título en degradé azul, bordes azules, diálogos beige.
  - Noir: barra de título negra, diálogos gris oscuro.
- Sin `TransitionDurations`: Aero tiene 32 secciones con fundidos de 100 ms que repintan cada control varias veces por cambio de estado. Es lo más probable detrás de la lentitud.
- Se compila con los mismos comandos que el build fijado usa para `aero.msstyles` (`make -n`).
- `tools/build-wine-hardware.py` los copia a `C:\windows\resources\themes\luna\luna.msstyles` y `...\noir\noir.msstyles`, con verificación de `builder_sha256`. winecfg los lista en Integración de escritorio.

Lo que Wine no dibuja con el tema:
- La barra de título, los bordes y los botones de minimizar, maximizar y cerrar los dibuja Wine con los colores del sistema y los botones clásicos (`uxtheme/stylemap.c` solo tiene los nombres). En Luna salen la barra azul y los bordes azules de XP, pero no los botones redondeados ni la X roja.
- Lo que sí toma el estilo: las barras de desplazamiento de todas las ventanas (uxtheme se engancha con `user_api_hook`), los fondos de diálogo y los controles de los programas que piden common controls 6.0, como winecfg. Explorer usa v5 y solo toma los colores.

## Sin estilo visual por defecto

- El prefijo sellado trae en `ThemeManager` `ThemeActive=1` con Aero. Hasta W174 el archivo no existía y uxtheme lo apagaba; desde W175 un prefijo nuevo arrancaba con Aero.
- `build-wine-hardware.py` pone `ThemeActive` en 0.
- En la consola esas claves son de la consola (W175). Si Aero quedó activo, escribió sus colores claros en `Control Panel\Colors`, y apagarlo desde el registro no los restaura.
- Por eso esta build trae `user_reg_reset = [ThemeManager, Control Panel\Colors]`: esa subida los toma de la build (sin estilo, esquema oscuro) **una sola vez**. Hay que sacarlo en W178.

Para construir: `tools/build-msstyles-hw.py` (ya corrido; `out/msstyles-hw` está al día) antes de `tools/build-wine-hardware.py`.

## Prueba

1. Al arrancar: escritorio y ventanas oscuros, como antes de W175, sin estilo visual. En el registro de la subida, `user_reg.reset` con las dos claves.
2. winecfg → Integración de escritorio → la lista de temas tiene que mostrar Aero, Luna y Noir.
   - Elegir Luna → Aplicar: barra de título azul, bordes azules, diálogos beige; en winecfg, botones, casillas, pestañas y barras de desplazamiento al estilo XP.
   - Lo mismo con Noir.
3. Velocidad: con Luna y con Noir, abrir el menú Inicio, mover ventanas, desplazarse en una lista. Comparar con "(Sin tema)" y con Aero.
4. Volver a "(Sin tema)": tienen que volver los colores oscuros.

Riesgos:
- Luna y Noir siguen dibujando con bitmaps a través de uxtheme, como Aero. Sin los fundidos deberían andar mejor que Aero, pero no tan rápido como sin tema.
- Es la primera vez que estos bitmaps se ven en la consola. Puede haber detalles para ajustar: tamaños, márgenes, contraste del texto en Noir.
