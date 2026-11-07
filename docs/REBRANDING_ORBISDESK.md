<a id="orbisdesk-nombre-y-compatibilidad-de-actualización"></a>


# OrbisDesk: name and update compatibility

[English](REBRANDING_ORBISDESK.md) | [Español](REBRANDING_ORBISDESK-es.md)

Since W283 (03.82), the project is presented as **OrbisDesk**. Short name: OrbisDesk. Legible identifier for archivos/rutas: `orbisdesk`. Description: desktop and applications Windows for PS4.

The change includes texts from the launcher and overlay, own windows and diagnoses, classes Win32 and generated associations, sources, scripts, documentation, probes and client of Steam. Wine, WoW64, DXVK, RADV, OpenOrbis and the other components retain their technical names and powers. The icon figure did not contain the previous name and remains the window with console silhouette.

<a id="paquetes"></a>


## Packages

- Main application: title `OrbisDesk W283`, version 03.82.
- The local file uses the title: `OrbisDesk-W283-03.82.pkg`.
- The transfer uses `orbisdesk-W283-<sha256-corto>.pkg`.
- Songs and Steam are also generated with title / file OrbisDesk.
- The update identifiers PS4 do not change: ORBW00002 for the application, ORBS00001 for Steam and those of existing probes. The previous CONTENT_ID is also preserved. They are technical identity of installation, not the name shown. So the new versions can be installed above the above.

The collector continues to read the original location of the buildings W001 - W282; since W283 uses `/data/orbisdesk`. The package cleaning recognizes both prefixes and only takes off previous ones after checking the complete transfer by reading back. It does not change the instalar/ejecutar rule manually.

<a id="datos"></a>


## Data

`/data/wine-prefix`, your records, games, documents and profiles do not change location. The own code uses `/data/orbisdesk` for logs and launcher status. At first start it matters only once the small files in the historical directory: boot mode, launch, next/context and log ledger. Existing new files have priority. A marker prevents a reimport of a request consumed in the next boot. The originals are not deleted.

The uploader also accepts the old ledger to preserve settings and choices that the user made on the console before the update.

DOS use `AppData\Local\OrbisDesk`. If there is only the previous folder, MoveFile the complete move before creating the new one. If it fails, the game is reported and does not start with an empty folder that hides the original saved.

<a id="nombres-antiguos-que-se-conservan-deliberadamente"></a>


## Old names that are deliberately preserved

Do not rewrite logs, manifests, hashes, archived packages, comms or historical series of patches. Neither URLs and external repository names, installation identities PS4 or migration constants. These apparitions document provenance or compatibility; they do not represent the current brand. The comments of already compiled patches are recognized in both forms, maintaining the original checks of hashes and binaries.

The copy of pre-change sources and their inventory are in `reports/rebrand-orbisdesk/20261107T105359/`. It's not evidence of a physical Runs.

<a id="verificación"></a>


## Verification

Focus tests: strict recognition of packages antiguos/nuevos, selection of the historical directory by number of build and import of settings compiled in host. It is found that it does not overwrite current settings, does not delete original and does not repeat a used launch request. Command:

```sh
python3 tests/test_project_brand.py
```

The recombination must regenerate the artifacts whose builders/fuentes changed; no hashes of manifests are updated to appear non-existing compilations. The PKG and its SFO are then reviewed. Installation, migration in PS4 and visual testing are recorded separately; The host checks do not replace them.

<a id="resultado-de-compilación-2026-11-07"></a>


## Compilation result (2026-11-07)

- W283 / 03.82: `out/wine-hardware-w283/OrbisDesk-W283-03.82.pkg`. SHA256: `a3a72e1401c27fc57bf8cac1b9dcf07b280c6ca7c359fd7f7a28d21db37c3c69`. UFO verified, 58 hashes matching source and web closure with `missing: 0`.
- Steam S1 / 01.05: `out/steam-probe-s1/OrbisDesk-Steam-S1-01.05.pkg`.
- Steam S2 / 01.06: `out/steam-s2/OrbisDesk-Steam-S2-01.06.pkg`. Both SFO and hashs verified; no evidence was carried out Steam new network.
- Three approved focused tests; brand audit without unexpected active-code appearances. The only previous names retained meet the exceptions of compatibilidad/procedencia detailed above.
- Evidence in `reports/rebrand-orbisdesk/20261107T105359/verified-release/`. Installation and visual migration in PS4 are still pending.
- The icon generator of the historical probe H001B now uses the initial OD; the old archived probe is not repackaged as new evidence.

The GUI soda incorporated imagehlp.dll and wkscli.dll to its closure PE64; their duplicate entries were removed from the additional list W261. The checks of duplicates, imports and hashes of the packaging are retained.

<a id="entrega-ps4"></a>


## Delivery PS4

W283 transferred with reading back 2026-11-07 to `/data/pkg/orbisdesk-W283-a3a72e1401c2.pkg` (192.168.68.100:2121). 1.823 verified runtime files; 83 up and 1.740 already present. No chmod flaw. An earlier package removed only after checking PKG and runtime. Six console configuration blocks were retained. Uncompleted manual installation and execution; Steam S1/S2 remain local. Evidence: `reports/wine-hardware-w283/transfers/20261107T142853Z.json`.

<a id="nombre-limpio-desde-w284"></a>


## Clean name from W284

The title PS4 becomes only `OrbisDesk` and the file distributed `OrbisDesk.pkg`. The visible version is shown only on the start selector NORMAL/ROOT. It is removed from the other load and error screens. The technical version of the SFO continues to increase (03.83 in this delivery) to maintain the updates; W284 remains in internal logs and evidence. It does not change the function of Wine.
