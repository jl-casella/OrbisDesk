<a id="primera-prueba-física-h001"></a>


# First physical test: H001

[English](HARDWARE_H001.md) | [Español](HARDWARE_H001-es.md)

User-indicated destination: PS4 Pro Baikal, firmware 12.52, GoldHEN, FTP `192.168.68.107:2121`. The server responded as GoldHEN FTP v2. 2 and allowed anonymous access to `/data/pkg`. This verifies the connection, not the compatibility of the runtime on hardware.

The package **OrbisDesk Hardware Check H001**, Title ID `ORBW00001`, is a native OpenOrbis application independent of Wine. It is installed with Package Installer and opened from the PS4 menu. It's not sent to the BinLoader as payload.

The screen shows the results of:

- opening of the log and reading of the heading of `/app0/sce_sys/param.sfo`;
- writing, seeking and reading a file of its own in `/data/orbis-win/hw01`;
- memory mapping, protection calls R/RW, data conservation and release;
- reserve under 4 GiB and release;
- thread, mutex, join and isolation of a native variable TLS.

It does not test execution JIT, signals GS of Wine or an EXE of Windows. The protection test checks the calls and the reading; does not cause an illegal writing to check for bug recovery in this first version.

When it's over, it's still visible. The user can send a capture by PSPlay and close the application from the PS4 menu. The incremental log `report-0001.jsonl`, etc. are left in `/data/orbis-win/hw01/`, along with the Roundtrip files and BMP tables. A new name is reserved per execution to avoid overwriting previous reports. Each stage is recorded before it is executed.

<a id="construcción-y-comprobación-local"></a>


## Local construction and verification

```sh
python3 tools/build-hardware-boot.py
python3 tools/run-hardware-boot.py
```

The builder uses the existing SDK; in WSL resolves the cryptographic packaging with PkgTool of Windows and the .NET runtime installed by roll-forward, without installing OpenSSL old or changing the system settings. `pkg_validate` check the PKG. The smoke test runs the ELF for 15 seconds in the fork and retains results and capture in `reports/hardware-h001/`.

The first smoke test passed without stubs import. The physical test remains **pending and feedback**. Manifest of the package in `out/hardware-h001/manifest.json`; the transfer records include the hash of the file read back by FTP.

<a id="entrega-inicial"></a>


## Initial delivery

It was increased `/data/pkg/orbis-win-H001-a8997e445b54.pkg` (6.619.136 bytes) and verified by reading back by FTP, SHA- 256 `a8997e445b5441eb3528755200225f7129e74a3f81ad95f6629fe6efe7ffb069`. The eboot of the final package matches the one that passed the smoke test. Transfer registered in `reports/hardware-h001/transfers/20261031T050227Z.json`. Manual installation and physical execution pending from the user.

<a id="resultado-físico-h001-y-actualización-h001b"></a>


## Physical result H001 and update H001B

The user ran H001 in his PS4 Pro and sent a photo. The log JSONL and the picture generated in the console were also recovered: evidence in `reports/hardware-h001/physical/20261031T051043Z/`. They pass screen, log, roundtrip in `/data`, protection R/RW, low reserve and TLS/threads. The reading of the SFO returns ENOENT (2). The initial review of the package and its sources are stored in `reports/hardware-h001/release-h001/`.

The files had been created with 0600 mode: FTP could be listed but not downloaded. Only the mode of our two diagnostic files was changed to 0644 by CHMOD SITE, and they could be recovered without altering their content.

H001B test a normal file included in the package, `/app0/hardware-marker.txt`, with verifiable content. It retains the original reading of the SFO as an optional observation, without turning its absence into a correct reading result. In addition, create the roundtrip logs and files in 0644 mode and apply fchmod to allow its recovery by FTP.

The current builders generate H001B in `build/hardware-h001b` and `out/hardware-h001b`. `run-hardware-boot.py` uses H001B by default and allows `--build H001` for the previous binary. The dot test of H001B passed without stubs import. The complete Wine suite was not executed.

Update: same Title ID `ORBW00001`, APP_VER 01.01, title **OrbisDesk Hardware Check H001B**. Up with verified back reading at `/data/pkg/orbis-win-H001B-0d1e49cc1c38.pkg`. Transfer in `reports/hardware-h001b/transfers/20261031T051457Z.json`. It has to be closed H001 before installing it; the reading of the asset in hardware is still pending feedback.
