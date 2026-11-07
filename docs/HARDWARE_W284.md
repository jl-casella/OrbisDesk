<a id="orbisdesk-paquete-con-nombre-limpio-w284"></a>


# OrbisDesk: package with a clean name (W284)

[English](HARDWARE_W284.md) | [Español](HARDWARE_W284-es.md)

Change of presentation over W283. The title of PS4 is `OrbisDesk`, without building suffix, and the distributed file is `OrbisDesk.pkg`.

The visible version `03.83 (W284)` appears only on the initial screen of choice NORMAL/ROOT. The version foot of the back load and the error screen is removed. The logs keep their internal identification and remain in `/data/orbisdesk/w284`. It does not change programme implementation or mode options.

The identity ORBW00002 and its Content ID are maintained. APP_VER/VERSION of the SFO are 03.83 to allow the existing installation to be updated; They're not part of the title. The technical version does not restart to 01.00.

<a id="validación"></a>


## Validation

Finalized Compilation: `out/wine-hardware-w284/OrbisDesk.pkg`. Right SFO: TITLE = OrbisDesk, APP_VER = 03.83 and previously preserved identity. 58 matching source hashes. Location of the proven version in the drawing code. SHA256 of the package: `bc57f0268524449e916aef601445c83e0e8b3cc5e220e20c887b78609c70e1cb`. Evidence: `reports/wine-hardware-w284/release-w284/verification.json`. Visual test and installation in PS4 pending. Delivery FTP completed: `/data/pkg/OrbisDesk.pkg` in 192.168.68.100:2121. PKG and 1.823 runtime files (1 uploaded, 1.822 present) were verified, with no permit failure; a previous package removed after verification. Console settings were preserved. Evidence: `reports/wine-hardware-w284/transfers/20261107T144147Z.json`.

Runtime comparison: same 1.823 files, no deleted entries; only regenerated `winecfg.cpl` during the usual build (no change source). The functional matrix of Wine for this presentation change is not repeated.

<a id="prueba-física-recogida-2026-11-07"></a>


## Physical test collected (2026-11-07)

The user installed and tested the new delivery. Evidence downloaded from 192.168.68.100:2121 in `reports/wine-hardware-w284/physical/20261107T153807Z/`. Log `run-0001.log`: W284 confirmed, root mode, image presentation up to `t_ms=684982` and posterior pointer movements. No record `W284 crash`, no unhandled exception or final output code. Classification: `presented`; does not amount to an approval of all the compatibility of games.

The capture `screen.png` shows ORBISDESK in the selector NORMAL/ROOT and the VISION foot 03.83 W284. The absence of version on the other screens was found in code; This capture is only for the selector. An exception of syscall during the tilted thread diagnosis returns to your handler and the session continues; is not classified as fatal closure.
