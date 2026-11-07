<a id="w106-abrir-archivos-desde-wfm-sin-reemplazar-el-escritorio"></a>


# W106: open files from WFM without replacing the desktop

[English](HARDWARE_W106.md) | [Español](HARDWARE_W106-es.md)

APP_VER 02.05. The user confirmed the list of W105, but opening documents restarts the app. Logs: reports/wine-hardware-w105/physical/20261102T145327Z. In run- 0001 and run- 0003, result.txt and vkspin64.txt they reach switch_program as executable images. The following starts fail with c000007b and return to the desk. It is a replacement of the title by a document, not a proven crash by exception. The analysis is left at analysis.json of that session.

<a id="cambios"></a>


## Changes

WFM sends route and directory to the desktop window with WM_COPYDATA. Explorer checks the same process, size and chain termination emitter; copy the data to your heap and publish an application on your own thread. Solve open by ShellExecuteExW NOASYNC, following the shell route you use Start. The application does not keep memory or execute a worker of the WFM guest. A shipping or opening failure is shown as error. PWOPEN records tail, result and threat ID. Both binaries record the hash of the common protocol; The packer rejects versions that do not match.

The prefix records real associations for. txt/.log/.ini/.cfg/.conf/.json/. md/.csv/.xml with Notepad PE64 and file argument between quotes. A document such as PE is not run or a satisfactory opening is simulated.

In mode PS4, kernelbase blocks the old title replacement route if there is no compatible guest or its load failed (STATUS_NOT_SUPPORTED). It returns a normal failure of creation. The supported EXE PE64 are opened in guest threads; PE32 is not implemented as a concurrent guest and fails without reboot. The initial start PE32 of the launcher is independent and retains its route. The explicit treatment of wineboot to leave is maintained. It does not change Orbis or shadPS4.

Listing W105 and metrics CPU/GPU W104 are maintained. Calibration postponed.

```sh
python3 tools/build-wfm.py
python3 tools/build-explorer-hw.py
python3 tools/build-guest-hw.py
python3 tools/build-wine-hardware.py --mangohud enabled
python3 tools/upload-hardware.py --build W106 --host 192.168.68.104 --timeout 60
```

No local matrix. PS4 test: open C:\orbis\result.txt from WFM and check content in Notepad; close Notepad and continue to navigate on WFM. Repeat with another text and try vkspin64.exe/vkcube.exe from WFM by keeping your windows and Explorer open. A non-compatible EXE and a non-associated file must return error without restarting the desktop. Close WFM and try Start. Do not modify existing documents during this test.

```sh
python3 tools/fetch-hardware.py --build W106 --host 192.168.68.104
```

Check PWOPEN and guest loads from the Explorer thread, absence of switch_program by documents and visible content informed by the user. Construction, delivery and execution are documented separately; to compile the actual routing of ShellExecute on the console alone.

Compilation completed; sources and manifests archived in releases e-w106. PKG SHA- 256: 02a9368dc02f976ae4a6c87f9f6fb98da18b8e4ea99923b7168c6a7c38e148ad. ELF SHA- 256: 5deac57a1dc22ee346a5d8117b997edf10b8a3d68b89ed8459ca0956d44f5264. Close OrbisDesk before installing to prevent the previous session from keeping your record of new associations. The associations are included in user.reg and are verified along with the rest of the runtime in the transfer.

Delivery completed with verified return reading: `/data/pkg/orbis-win-W106-02a9368dc02f.pkg`. Report: reports/wine-hardware-w106/transfers/20261102T150943Z.json. 548 verified files, 536 present and 12 uploaded; no permit failure. W105 withdrawn after verification. The user's pending physical test.

<a id="prueba-física-20261102t151517z"></a>


## Physical test: 20261102T151517Z

The user confirms correct EXE and failed texts. PWOPEN in thread 0024 confirms vkspin64.exe, gui-window64.exe and gui-text64.exe open. Two texts are rejected without switch_program; does not load Notepad. The guard keeps the desk. The association was left in HKCU Classes but HKCR established Machine Classes consultation. W107 fix the location. Evidence and analysis: reports/wine-hardware-w106/physical/20261102T151517Z/analysis.json.
