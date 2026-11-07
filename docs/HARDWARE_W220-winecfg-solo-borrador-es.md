# W220: casilla "Run alone" en la pestaña Applications de winecfg (borrador)

[English](HARDWARE_W220-winecfg-solo-borrador.md) | [Español](HARDWARE_W220-winecfg-solo-borrador-es.md)

Borrador de la sesión de configuración de Wine, para unir a `HARDWARE_W220.md`. Nada de esto se probó en la consola.

## Qué pasó en W217

Reporte: `reports/wine-hardware-w217/physical/20261104T192336Z/run-0004.log`

- El usuario agregó `C:\Program Files\SeaMonkey\seamonkey.exe` en la pestaña Applications de winecfg para que corriera solo.
- SeaMonkey arrancó como invitado (línea 1939), sin `runs_alone`.
- El `user.reg` de la consola no tiene la clave `AppDefaults\seamonkey.exe`.

## Causa

- winecfg no tenía ningún control para `OrbisRunsAlone`. Ese valor lo lee `ps4_runs_alone` (kernelbase, `tools/build-guest-hw.py`), y el `winecfg.exe` de W217 no contiene ese nombre.
- **"Add application" no escribe nada:** en Wine (`programs/winecfg/appdefaults.c`, `on_add_app_click`) sólo agrega una fila a la lista. La clave `AppDefaults\<programa>` aparece recién cuando se cambia algún valor con ese programa elegido.
- **No se perdió nada al guardar:** AppDefaults es de la consola en cada subida, y el servidor guarda el registro cada 5 s (W190).

## Cambio

`tools/build-winecfg-hw.py`, con `winecfg-runs-alone-w220.patch.py`. El builder ahora revisa `appdefaults.c` además de `theme.c`: `make -n` con los dos y tres comandos.

- **La casilla:**
  - dados "Alanca solo (el título se reinicia con este programa)" y va debajo de Windows versión;
  - se crea con la pestaña. La lista queda una fila más corta, y lo de abajo sube una fila. Los recursos del diálogo no cambian;
  - sólo se habilita con un programa elegido, no con Default Settings, y muestra el valor que ya tiene;
  - marcada pone `OrbisRunsAlone="Y"`; desmarcada lo borra. Pasa por la lista de cambios de winecfg, así que se escribe con Apply u OK.
- **"Add application":** habilita Apply, y Apply crea `AppDefaults\<programa>` aunque no se cambie nada más. Si el programa se quita antes de aplicar, la clave se borra igual.
- **Apply en esta pestaña:** crea las claves de los programas agregados, aplica los cambios y termina con `RegFlushKey(HKEY_CURRENT_USER)`, como W190 en el tema.

## Construcción

1. `python3 tools/build-winecfg-hw.py`. Debe dar 8 revisiones y 0 advertencias. `build-wine-hardware.py` exige que el manifest corresponda al builder actual.
2. `tools/build-wine-hardware.py`.

## Prueba física

1. En winecfg, pestaña Applications: "Add application…", elegir `seamonkey.exe`, marcar "Run alone" y apretar OK.
2. Abrir SeaMonkey. El log debe mostrar `PWGUEST runs_alone app=…seamonkey.exe` y el título reinicia con SeaMonkey.
3. **Persistencia:** bajar el `user.reg` de la consola. Debe tener `[Software\\Wine\\AppDefaults\\seamonkey.exe]` con `"OrbisRunsAlone"="Y"`, y seguir ahí después de la próxima subida.
4. **Desmarcar:** desmarcar la casilla y aplicar. El valor desaparece, y SeaMonkey vuelve a arrancar como invitado.

## No verificado

- Nada se probó en la consola.
- El builder corrió sobre una copia (8 revisiones, 0 advertencias, `winecfg.exe` armado), sin tocar `build/` ni `out/`.
- El lugar de la casilla se calculó con las medidas del diálogo, sin verla en pantalla.
