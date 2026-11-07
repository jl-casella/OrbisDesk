# W203: el escritorio se congela con Pale Moon como invitado (borrador)

[English](HARDWARE_W203-palemoon-invitado-borrador.md) | [Español](HARDWARE_W203-palemoon-invitado-borrador-es.md)

Borrador de la sesión lateral del navegador, para unir a `HARDWARE_W203.md`. Sigue a los dos borradores de diagnóstico (`HARDWARE_Wxxx-palemoon-invitado-borrador.md`, `…-2-borrador.md`). Nada de esto se probó en la consola.

## Qué mostró W201

Reporte: `reports/wine-hardware-w201/physical/20261104T125351Z/run-0001.log`

- **El vigía del servidor arrancó** (`PWSERVER watch rc=0`, línea 422), y nunca registró un paso de más de 5 s.
- **Cuándo se congeló:** esta vez al arrancar Pale Moon, después de cargar `freebl3.dll` y `nssckbi.dll`.
- **El volcado de explorer:**
  - registró `PWDUMP begin … loader_owner=0000` (nadie tenía el loader lock);
  - después registró `PWDUMP step=thread_list`;
  - no volvió de esa primera llamada al servidor.
- **Lo que sigue andando:** sólo el compositor y RADV.

**Conclusión:** el servidor no estaba trabado en un pedido; no leía los pedidos nuevos.

## Causa (deducida del código)

- **Cómo espera el servidor:** el bucle principal del wineserver (`server/fd.c`, `main_loop`) espera con `poll( pollfd, nb_users, timeout )` sobre toda su tabla de descriptores. `epoll` no está disponible en la consola, y `poll` es `pw_wine_poll` (`platform/ps4/pw_wine_posix.h`). Los comentarios de W034 y W176 en `pw_wine_net.c` ya muestran que el servidor pasa por ahí.
- **El límite:** hasta W201, `pw_wine_poll` rechazaba más de 256 descriptores con `EINVAL`.
- **Qué cuenta `nb_users`:** los lugares de la tabla del servidor:
  - uno por hilo de Windows (su tubería de pedidos);
  - los sockets, tuberías y archivos que el servidor espera.
- **Qué pasa con Pale Moon como invitado:** agrega decenas de hilos al proceso de explorer, y más sockets al navegar. Al pasar de 256:
  - cada `poll()` falla;
  - `main_loop` no mira el error y vuelve a llamar, así que ya no lee ningún pedido;
  - cada hilo se detiene en su próxima llamada al servidor;
  - los temporizadores del servidor siguen corriendo, así que ningún paso dura 5 s (W201 no registró ningún `PWSERVER stuck`).
- **Por qué solo no pasa:** como título aparte, Pale Moon tiene su propia tabla, más chica.

Encaja con:
- la falta de aviso de sección crítica;
- el compositor, que sigue andando porque no usa el servidor;
- el momento del cuelgue: al arrancar o al navegar, según cuántos hilos y sockets haya.

Lo que no está medido es el tamaño de la tabla en el momento del cuelgue. Este cambio lo registra.

## Cambio

- **`platform/ps4/pw_wine_net.c`:** `pw_wine_poll` acepta hasta 4096 descriptores. Pasados 256, los eventos van en memoria del heap en lugar de la pila.
  - Cada máximo nuevo pasado 256 se registra una vez cada 64 (`PWNET poll_count n=…`).
  - Más de 4096 sigue siendo `EINVAL`, con un aviso (`PWNET poll_count_unsupported`).
- **`tools/build-wine-delete-server.py` (`server/fd.c`):** sólo trazas; el bucle no cambia.
  - Al entrar al bucle de `poll`, `PWSERVER poll_loop epoll_fd=…` muestra qué espera usa.
  - Un `poll()` que falla se registra (`PWSERVER poll_failed n=… errno=… users=… active=…`): los 5 primeros y después uno cada 100 000.

## Construcción

1. `python3 tools/build-wine-delete-server.py`.
2. `tools/link-wine-boot.py`, que compila `pw_wine_net.c`.
3. `tools/build-wine-hardware.py`.

## Prueba física

1. Al arrancar, el log tiene que mostrar `PWSERVER poll_loop epoll_fd=-1`.
2. Abrir `palemooncopy.exe` (como invitado) y navegar a dos o tres sitios. Esperar 2 minutos.
3. **Qué buscar en el log:**
   - `PWNET poll_count n=…`: confirma que la tabla pasó de 256;
   - ninguna línea `PWSERVER poll_failed`;
   - el latido de explorer (`heartbeat_age_ms`) en ~230.
4. Si se congela igual, las líneas `PWSERVER` y `PWDUMP` de las rondas anteriores siguen en el build.

## No verificado

- Nada se probó en la consola.
- Los cambios se compilaron sólo con `-fsyntax-only`, sobre copias: `pw_wine_net.c` con las opciones de `link-wine-boot.py` y `server/fd.c` con la receta del servidor.
- No se sabe si `sceNetEpoll` acepta más de 256 descriptores en una misma espera. Si no los acepta, `pw_wine_poll` devuelve el error de libSceNet, y `PWSERVER poll_failed` lo muestra con su `errno`.
- Una tabla de miles de descriptores hace más lento cada `poll()`: crea y destruye un epoll de libSceNet por llamada, y revisa duplicados en tiempo cuadrático. No se midió.
