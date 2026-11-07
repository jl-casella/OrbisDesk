<a id="w097-diagnóstico-de-start-después-de-cerrar-invitados-gráficos"></a>


# W097: diagnosis of Start after closing graphic guests

[English](HARDWARE_W097.md) | [Español](HARDWARE_W097-es.md)

W096 allowed the user to run vkspin, vkcube and glxgears together, but Start stopped opening after closing. The three guests left with 0 and continued to arrive in the mouse. There is not enough evidence to distinguish a shell lock from an input delivery problem.

Evidence: `reports/wine-hardware-w096/physical/20261102T103537Z/analysis.md`.

W097 conserves MangoHud and Wine W096 Unix. Change to add an independent observer and progress marks, and kernelbase to record the result of waiting for auxiliary threads. **It does not declare the failure** solved. The pending change in percentages CPU/GPU is not incorporated and local matrix is not executed, as per the current user's indication.

<a id="interpretación-de-las-trazas"></a>


## Interpretation of the tracks

`PWSHELL monitor` reports the antiquity of the heart beat of the shell's royal thread clock, the GUI state and the windows activas/de foco/captura/men u. It does not try to restart the desktop or simulate a response. The observer does not use SendMessage.

Stages of `PWSHELL stage`:

| Etapa |Point|
| --- | --- |
| 20 |The driver returned from a bar click|
| 30 |Window creation / destruction notification entered|
| 31 / 32 |Before / after destroying the button of a closed window|
| 33 / 34 |Before / after you clean icons from that window|
| 35 / 36 |Before / after synchronizing bar buttons|
| 100 / 101 |Before / after destroying the previous menu|
| 102 / 103 |Before / after listing Start and loading your icons|
| 104 |Special Control Panel Folder Settings|
| 105 / 106 |Entry / return of TrackPopupMenuEx|

A 105 stage with active heart beat can simply be an open menu. `other_threads_wait=258` indicates timeout; 0, completion of all expected threads. A timeout maintains its previous behavior: W097 only records it.

<a id="construcción-y-prueba-física"></a>


## Construction and physical testing

From the workspace in Ubuntu - 22.04:

```sh
python3 tools/build-explorer-hw.py
python3 tools/build-guest-hw.py
python3 tools/build-wine-hardware.py
python3 tools/upload-hardware.py --build W097 --host 192.168.68.104
```

APP_VER 01.96, title ORBW00002. Close OrbisDesk before installing. Open the three applications, close them and press the Start button center. If it fails, leave it like this for a few 15 seconds so that the observer will register the state and notify. You don't need to wait a minute or interpret the watch in plain sight.

Readily verified up by reading: `/data/pkg/orbis-win-W097-0641ae78ebb8.pkg`, SHA- 256 `0641ae78ebb8ef0bebd0f8fa17e86b283aa738be45c644793da786823740b567`. Report: `reports/wine-hardware-w097/transfers/20261102T104911Z.json`. Runtime: 548 files, 537 present, 11 uploaded, no permissions failure.

While preparing this delivery, the user specified that when closing vkcube also glxgears and vkspin stopped and stopped opening Start. This symptom extends research to the shared closure and its blockages, not just to the menu. A second download W096, `physical/20261102T104940Z`, has the same two logs unchanged; does not provide an additional session with that reproduction. In W097 you have to close **vkcube first, leaving the other two windows open**, and leave some 15 seconds if they freeze. Start's status is checked later.

```sh
python3 tools/fetch-hardware.py --build W097 --host 192.168.68.104
```

<a id="resultado-recibido"></a>


## Outcome received

Logs in `reports/wine-hardware-w097/physical/20261102T105238Z/`. In the second session the three applications close with 0 and their string waits also return 0. Start opens and returns when selecting another input. The log is cut when recharge glxgears, before creating the new thread; does not record a derogation or a final exit of the title. The user reports crash from the app. It is continued in [W098](HARDWARE_W098.md) with traces of the load of modules.
