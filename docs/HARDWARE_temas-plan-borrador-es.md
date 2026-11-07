# Temas claro y oscuro en winecfg (plan, borrador)

[English](HARDWARE_temas-plan-borrador.md) | [Español](HARDWARE_temas-plan-borrador-es.md)

Pedido del usuario: que la parte de temas de winecfg (Integración de escritorio) funcione, con un tema claro y uno oscuro como el actual.

## Cómo funciona hoy

- El aspecto oscuro no es un estilo visual: son los colores del sistema que `build-wine-hardware.py` escribe en `HKCU\Control Panel\Colors` (W045, diccionario `DARK`).
- winecfg tiene dos mecanismos:
  - **Combo de temas:** lista los `.msstyles` de `C:\windows\resources\themes\*`. El prefijo no tiene ninguno, así que solo muestra "(Sin tema)".
  - **"Instalar tema..." con un archivo `.theme`:** lee su sección `[Control Panel\Colors]` y aplica esos colores al momento (`do_parse_theme` en `programs/winecfg/theme.c`). Ese es el mecanismo que sirve para claro y oscuro.
- Wine no tiene un estilo visual oscuro. Su único `.msstyles` es `aero.msstyles`, claro, con un solo color ("Blue"). El selector "tema de aplicaciones claro/oscuro" solo guarda `AppsUseLightTheme`, que `uxtheme` informa a los programas que lo consultan (`ShouldAppsUseDarkMode`); no cambia los controles de Wine.

## Plan

1. **Dos temas de colores** en `C:\windows\resources\themes\`:
   - `Orbis Oscuro.theme`: los colores actuales, generados del mismo diccionario `DARK` de `build-wine-hardware.py`, así no hay dos copias que mantener;
   - `Orbis Claro.theme`: los colores por defecto de Windows 10 (fondos blancos y gris claro, texto negro, selección azul).
   - Uso: winecfg → Integración de escritorio → "Instalar tema..." → elegir uno. Se aplica al instante.
2. **Que la elección sobreviva a las builds.** Hoy `upload-hardware.py` conserva de la consola solo `AppDefaults`, así que la siguiente subida volvería a poner el tema oscuro. Se suman a la lista de claves que vienen de la consola:
   - `Control Panel\Colors`;
   - `Control Panel\Desktop\WindowMetrics` (tamaños y fuentes de esa misma pestaña);
   - `Software\Microsoft\Windows\CurrentVersion\ThemeManager`;
   - `Software\Microsoft\Windows\CurrentVersion\Themes\Personalize`.
   - Consecuencia: una vez instalada, una build ya no puede cambiar esos colores por su cuenta.
3. **Opcional: `aero.msstyles`** en `resources\themes\aero` (compilado en el árbol fijado, x86_64), para que el combo de temas muestre "Aero".
   - Es un estilo visual claro: dibuja los controles con bitmaps a través de uxtheme.
   - Con los colores oscuros se ve mezclado, y dibujar con bitmaps en la CPU del Jaguar puede ser más lento.
   - Viene desactivado; solo se activa si el usuario lo elige.

## Archivos

| Archivo | Cambio |
|---|---|
| `tools/build-wine-hardware.py` | escribe los dos `.theme` (DARK y un nuevo LIGHT) |
| `tools/upload-hardware.py` | más claves conservadas en la fusión de `user.reg` |
| `tools/stage-wine-extras.py` | (si va el punto 3) `aero.msstyles` y su copia a `resources\themes\aero` |

## Prueba

1. winecfg → Integración de escritorio → "Instalar tema..." → `Orbis Claro.theme`: ventanas, menús, barra de tareas y menú Inicio en claro.
2. Lo mismo con `Orbis Oscuro.theme`: vuelve a quedar como ahora.
3. Elegir el claro, cerrar la app, instalar la build siguiente: tiene que seguir en claro.
4. (Si va Aero) elegir Aero en el combo y ver cómo se dibujan los controles y si se nota más lento.
