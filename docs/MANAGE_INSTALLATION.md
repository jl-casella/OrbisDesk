# Manage installation

[English](MANAGE_INSTALLATION.md) | [Español](MANAGE_INSTALLATION-es.md)

Status: added on 2026-11-20. The pages were drawn on the PC with the launcher's own drawing code. Not yet built or run on the console.

## Why

To start over, OrbisDesk's data had to be deleted over FTP. The console's FTP server could not delete about 2100 of the files Wine and the installer made until their permissions were changed one by one. The title itself can delete them once it runs as root, so the loading screen now offers that.

## What the user sees

While the loading screen shows its bar, a gear at the bottom right says `OPTIONS: MANAGE INSTALLATION`. The launcher reads the pad from its first screen until Wine starts. After OPTIONS the label reads `OPENING MANAGE INSTALLATION`, and the menu opens at the next checkpoint: right after the jailbreak (as root, before anything opens the prefix), or just before Wine starts. Nothing is deleted while Wine runs.

| Choice | What it deletes | Then |
| --- | --- | --- |
| REINSTALL DATA | `/data/orbisdesk`, `/data/wine-prefix`, `/data/wine-home` and `/data/wine`, except what is kept (below) | The title relaunches. Its installer finds no install record and installs the package's runtime, as on a first start. |
| DELETE DATA - KEEP GAMES AND SAVES | The same | The title closes |
| DELETE EVERYTHING | The four folders as they are, Steam games and saves included | The title closes |
| BACK | Nothing | The start goes on |

Kept by the first two: the Steam games (`/data/orbisdesk/steam-games`), the Steam sign-in (`/data/orbisdesk/steam` and its `steam-*.txt` files), the user's `Documents`, `Saved Games` and `Desktop`, and the Steam shortcuts in the Start menu.

Each deleting choice first shows a page with what it deletes and keeps, and `IT CANNOT BE UNDONE`. As on the Steam client's uninstall and sign-out pages, only X goes on and O goes back. While it deletes, the page counts the files. A file it cannot delete is counted on screen and logged as `PWMANAGE unlink_failed` (the first 32).

The menu is not offered in a relaunch that runs a program from the desktop (W043), so a game's OPTIONS press does not open it.

## Where it is

- [hw_manage.h](../native/hw_manage.h): the gear, the pages, the pad watch, the deletion and the menu.
- [wine_hardware.c](../native/wine_hardware.c): the hint on the loading screen, the watch at the first screen, and the two checkpoints.
- Log lines start with `PWMANAGE` (`watch`, `requested`, `menu at=`, `delete choice=`, `delete done files= failed= ms=`, `relaunch`, `back`).

## Limits

- The menu can only be opened before Wine starts. On a start with nothing to install, that is a few seconds.
- Without GoldHEN the jailbreak fails and the title runs in the sandbox. It can then delete only what the sandbox may.
- The lettering of the loading screen has letters, digits and `: - . / %`, so the pages use no commas or brackets.

## How to check on the console

1. Start OrbisDesk and press OPTIONS while the bar is up. The menu should open and BACK should go on to the desktop.
2. Choose REINSTALL DATA and confirm with X. The title should relaunch, install, and reach the desktop. Steam games, saves and the Steam sign-in should still be there.
3. Choose DELETE EVERYTHING, press O on its page (nothing deleted), then choose it again with X. The title should close, and the four folders should be gone over FTP.
