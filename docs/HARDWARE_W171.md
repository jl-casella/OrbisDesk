<a id="w171-estado-de-la-página-en-el-fallo-del-heap-fase-6"></a>


# W171: page status in heap failure (phase 6)

[English](HARDWARE_W171.md) | [Español](HARDWARE_W171-es.md)

APP_VER 02.70. Base W170. The result of W170 is in `docs/HARDWARE_W170.md`.

<a id="cambio"></a>


## Change

`tools/build-audio-ps4.py`, `virtual.c` of ntdll, `virtual_handle_fault`:
- When you fail to access a page that Wine has access, `PWVM fault` adds what the kernel says of the page before and after you re-apply the protection: range, protection, type and lags of `sceKernelVirtualQuery` (bit 4: compromised).
- If you re-apply the protection returned 0, the instruction is executed once again. If the page continues to fail, the second failure comes to the program as before and is recorded with `retry=0`.

<a id="qué-se-espera"></a>


## What is expected

- Let the log say if the page was compromised and with what protection, to correct `pw_wine_memory_protect` or the map of Wine.
- If the reattempt is enough, SuperMarioKart continues after the race, and the log shows `retry=1` without a second failure on that page.

The phase 7 (DXVK of 32 bits and winecfg) of the direct access session goes to W172.

<a id="prueba-física"></a>


## Physical test

Report: `reports/wine-hardware-w171/physical/20261103T190203Z/`. User's response: "It closed on departure." Output `status=0x00000000`.

```
PWVM fault addr=0x1f66000c err=1 vprot=0x23 view=0x1f660000 size=0x2f0000 protect=0x3 reprotect=0 errno=0
  before=0x8002000d 0-0 prot=0 type=0 flags=0 after=0x8002000d 0-0 prot=0 type=0 flags=0 retry=1
(segundo fallo en la misma página, retry=0)
```

- `sceKernelVirtualQuery` fails with `0x8002000d` (EACCES) before and after: the kernel does not report the page, although Wine has it compromised and `mprotect` returns 0. The reattempt fails the same.
- `pw_wine_memory_protect` (`platform/ps4/pw_wine_platform.c`) only the pages that the consultation reports as uncompromised with flexible memory. If the consultation fails, it does nothing and returns 0.
- The pages thus come out of `anon_mmap_fixed` with `PROT_NONE` of Wine, i.e. the `mmap` of libc: the decommit, and the release into a reserved area. It's an inference of the code; It's not measured.
- The rise of W171 used for the first time the fusion of `user.reg` of phase 7: `source=merged`, a block AppDefaults conserved, and the uploaded file is equal to the build.
