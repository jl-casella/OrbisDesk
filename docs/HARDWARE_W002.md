<a id="prueba-física-w002-prefijo-sin-enlaces-simbólicos"></a>


# Physical test W002: prefix without symbolic links

[English](HARDWARE_W002.md) | [Español](HARDWARE_W002-es.md)

W002 replace W001: same Title ID `ORBW00002`, APP_VER 01.01, same runtime at `/data`. The sources of W001 are in `reports/wine-hardware-w001/release-w001/` and were verified against the hashes of his manifest.

<a id="qué-mostró-w001"></a>


## What did he show W001

W001 stopped on the console before starting Wine, with `readlink` in ENOSYS and `dup2` in - 1 (see [HARDWARE_W001.md](HARDWARE_W001.md)). The investigation found two different causes.

1. **Order of libraries in the hardware builder.**
   - The ELF of Wine tested (`build/wine-boot/bootstrap.elf`) matters `lstat` and `readlink` of libkernel.
   - `build-wine-hardware.py` inserted `-L<sdk>/lib` before `build/wine-boot/lib`. With that, `-lc` would solve at `libc.a` of SDK, whose `readlink` and `lstat` are direct syscalls FreeBSD.
   - Neither the fork nor, according to the log, the console is served by them from an app.
   - The builder now retains the proven order. It also fails if any import of the ELF tested is static in the ELF hardware.
2. **The unit links.**
   - Even with the right imports, an app has no proven way of creating the links `dosdevices/c:` and `z:`: the fork does not implement `symlink`, and in hardware it is not proven either.
   - `platform/ps4/pw_wine_fs.c` now has a fixed assembly table:
     - `<prefix>/dosdevices/c:` → `<prefix>/drive_c`;
     - `<prefix>/dosdevices/z:` → the parent directory of the prefix, as the `../..` of the increment package 15.
   - Every route through those tickets is rewritten before you reach the kernel. `pw_wine_readlink` reports the text of the link, and `pw_wine_realpath` uses it.
   - `native/wine_boot.c` records the table after `pw_wine_init_paths`.
   - If fate does not exist, it fails with the real error of that destiny.
   - The preflight reads the links and the identity of the file using that table.

## Launcher

- It records in the log the result and errno of `dup2`. If `dup2` does not work, try `fcntl(F_DUP2FD)` with the value FreeBSD (10), because `fcntl` is the import of libkernel. Neither one closes descriptors before they succeed, and the redirection only counts if a probe written by fd 2 makes the log grow.
- Before calling Wine, record five probes:
  - `lstat` and `stat` of `drive_c`;
  - `readlink` of a directory, which must give EINVAL;
  - the assembly table;
  - `C:\orbis\console32.exe` resolution.
- A previous `result.txt` is archived with `sceKernelRename`.

<a id="smoke-test-en-el-fork"></a>


## Smoke test in the fork

`reports/wine-hardware-w002/20261031T060734Z/`: **passed**.

- `console32-bare.exe` runs by Wine and wowprospero inside the packaged launcher.
- `result.txt` is identical to Windows and the output is 0.
- The 12 preflight cases pass.
- No stub after handing over the control to Wine.
- In the fork, `dup2` is a stub and `fcntl(F_DUP2FD)` returns EOPNOTSUPP (45), so the output of Wine It's not redirected in the emulator. That doesn't affect the outcome.

<a id="estado"></a>


## Status

PKG in `/data/pkg/orbis-win-W002-b19780829b4a.pkg`, verified by reading it back. The 430 runtime files were already on the console with the right hash. Registration: `reports/wine-hardware-w002/transfers/20261031T060926Z.json`.

<a id="resultado-físico"></a>


## Physical result

The user ran it twice and the app was closed with error. The logs `run-0001.log` and `run-0002.log` are in `reports/wine-hardware-w002/physical/20261031T061129Z/` and are identical:

```
W002 stderr_redirect method=dup2 out=-1 errno=1 err=-1 errno=1 verified=0
W002 stderr_redirect method=f_dup2fd out=-1 errno=22 err=-1 errno=22 verified=0
W002 sysmodule_net rc=0x00000000
W002 probe libc_lstat rc=-1 errno=1 dir=0
W002 probe kernel_stat rc=0 errno=0 dir=1
```

What those logs show:
- In the console, `dup2` on the fd 1/2 returns EPERM and `fcntl(F_DUP2FD)` returns EINVAL.
- `lstat` returns **EPERM** and `sceKernelStat` works.
- The process ends in the next probe, the only one that calls `readlink` directly. The log does not say how it ends: the app does not record anything else.
- Wine It wasn't called..

`fetch-hardware.py` He classified it as `no-log`. That classification looks for markers with `rc=`, And these records use another format. The real state is a fall in the probe of `readlink`. W003 correct the launcher and the platform (see [HARDWARE_W003_W011.md](HARDWARE_W003_W011.md)).
