<a id="w107-asociaciones-de-texto-visibles-para-hkcr"></a>


# W107: text associations visible to HKCR

[English](HARDWARE_W107.md) | [Español](HARDWARE_W107-es.md)

APP_VER 02.06. W106 opens EXE from WFM correctly, confirmed by the user and by PWOPEN in thread 0024 (Explorer). vkspin64.exe, gui-window64.exe and gui-text64.exe were launched as guests; the two texts tried failed and the guard prevented the title from being replaced. Evidence: reports/wine-hardware-w106/physical/20261102T151517Z/analysis.json.

The cause is the location of the registry: W106 put the associations in HKCU\ Software\ Classes, but the fixed revision of Wine opens HKCR directly in\ Registry\ Machine\ Software\ Classes. There is no fusion with the user classes in this implementation. shell32 search there for extension, ProgID and command.

W107 adds the absent associations to system.reg (HKLM\ Software\ Classes), retaining existing associations as .ini - > inifile - > Notepad. The command remains Notepad PE64 with the argument between quotes. Do not change WFM, Explorer, DLL or guest mechanism that already opens EXE. It does not add a fictional editor or treat error as a success. The guard against rebeginnings and error for EXE are maintained not compatible as concurrent guests.

```sh
python3 tools/build-wine-hardware.py --mangohud enabled
python3 tools/upload-hardware.py --build W107 --host 192.168.68.104 --timeout 60
```

Close OrbisDesk during the transfer and before installing so that the previous session does not save old records on the updated runtime. No local matrix. In PS4, open two .txt from WFM (e.g. result.txt and text-progress.txt), check that Notepad shows its content and close it; check WFM, an EXE PE64 and Start later. Do not save changes in fixtures.

```sh
python3 tools/fetch-hardware.py --build W107 --host 192.168.68.104
```

Validation: load of notepad.exe from Explorer with the correct document, user-confirmed visual opening and absence of switch_program for text. Compilation, delivery and physical acceptance are separate states.

Compilation completed. The comparison with W106 confirms only system.reg and user.reg different in the runtime; WFM, Explorer and DLL match by hash. .txt - > OrbisDesk .Text - > actual command of Notepad and the existing .ini - > infile association were verified. Local matrix omitted, physical test pending. Fuentes/manifiesto in reports/wine-hardware-w107/release-w107. PKG SHA- 256: df1d1deadc9a4d9401a7c11e2f41f055a0898e53290c2e951db8fdd694aa140d. ELF SHA- 256: 02dc4e424d06e5c4ee5b84b5ea6c441b851e049822fb1849109c14657cde386e.

Delivery completed with verified return reading: `/data/pkg/orbis-win-W107-df1d1deadc9a.pkg`. Report: reports/wine-hardware-w107/transfers/20261102T164351Z.json. 548 verified files, 546 present and 2 uploaded, no permit failure. W106 withdrawn after verification. The user's pending physical test.
