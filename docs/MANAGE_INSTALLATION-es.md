# Administrar la instalación

[English](MANAGE_INSTALLATION.md) | [Español](MANAGE_INSTALLATION-es.md)

Estado: agregado el 2026-11-20. Las páginas se dibujaron en la PC con el mismo código de dibujo del launcher. Todavía no se compiló ni se probó en la consola.

## Por qué

Para empezar de cero había que borrar los datos de OrbisDesk por FTP. El servidor FTP de la consola no podía borrar unos 2100 de los archivos que crean Wine y el instalador hasta cambiarles los permisos uno por uno. El propio título sí puede borrarlos cuando corre como root, así que ahora la pantalla de carga lo ofrece.

## Qué ve el usuario

Mientras la pantalla de carga muestra su barra, una rueda abajo a la derecha dice `OPTIONS: MANAGE INSTALLATION`. El launcher lee el mando desde su primera pantalla hasta que arranca Wine. Después de OPTIONS el texto dice `OPENING MANAGE INSTALLATION`, y el menú se abre en el siguiente punto de control: justo después del jailbreak (como root, antes de que algo abra el prefijo) o justo antes de que arranque Wine. Nada se borra mientras Wine corre.

| Opción | Qué borra | Después |
| --- | --- | --- |
| REINSTALL DATA | `/data/orbisdesk`, `/data/wine-prefix`, `/data/wine-home` y `/data/wine`, salvo lo que se conserva (abajo) | El título se reinicia. Su instalador no encuentra registro de instalación e instala el runtime del paquete, como en un primer arranque. |
| DELETE DATA - KEEP GAMES AND SAVES | Lo mismo | El título se cierra |
| DELETE EVERYTHING | Las cuatro carpetas enteras, juegos de Steam y partidas incluidos | El título se cierra |
| BACK | Nada | El arranque sigue |

Las dos primeras conservan: los juegos de Steam (`/data/orbisdesk/steam-games`), la sesión de Steam (`/data/orbisdesk/steam` y sus archivos `steam-*.txt`), `Documents`, `Saved Games` y `Desktop` del usuario, y los accesos directos de Steam del menú Start.

Cada opción que borra muestra primero una página con lo que borra y lo que conserva, y `IT CANNOT BE UNDONE`. Como en las páginas de desinstalar y cerrar sesión del cliente de Steam, sólo X sigue y O vuelve. Mientras borra, la página cuenta los archivos. Un archivo que no puede borrar se cuenta en pantalla y queda en el log como `PWMANAGE unlink_failed` (los primeros 32).

El menú no se ofrece en un reinicio que abre un programa desde el escritorio (W043), para que el OPTIONS de un juego no lo abra.

## Dónde está

- [hw_manage.h](../native/hw_manage.h): la rueda, las páginas, la lectura del mando, el borrado y el menú.
- [wine_hardware.c](../native/wine_hardware.c): el aviso en la pantalla de carga, la lectura desde la primera pantalla y los dos puntos de control.
- Las líneas del log empiezan con `PWMANAGE` (`watch`, `requested`, `menu at=`, `delete choice=`, `delete done files= failed= ms=`, `relaunch`, `back`).

## Límites

- El menú sólo se puede abrir antes de que arranque Wine. En un arranque sin nada que instalar son unos pocos segundos.
- Sin GoldHEN el jailbreak falla y el título corre en el sandbox. Entonces sólo puede borrar lo que el sandbox permite.
- La tipografía de la pantalla de carga tiene letras, dígitos y `: - . / %`, así que las páginas no usan comas ni paréntesis.

## Cómo probarlo en la consola

1. Abrir OrbisDesk y apretar OPTIONS mientras está la barra. Se tiene que abrir el menú, y BACK tiene que seguir hasta el escritorio.
2. Elegir REINSTALL DATA y confirmar con X. El título se tiene que reiniciar, instalar y llegar al escritorio. Los juegos de Steam, las partidas y la sesión de Steam tienen que seguir ahí.
3. Elegir DELETE EVERYTHING, apretar O en su página (no se borra nada) y después elegirlo de nuevo con X. El título se tiene que cerrar, y por FTP las cuatro carpetas ya no tienen que estar.
