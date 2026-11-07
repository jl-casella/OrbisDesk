<a id="w135-corre-la-ps4-código-de-32-bits-nativo-fase-5"></a>


# W135: does the PS4 code of 32 native bits run? (phase 5)

[English](HARDWARE_W135.md) | [Español](HARDWARE_W135-es.md)

APP_VER 02.34. Base W134 (accepted phase 4b: SuperMarioKart shows the menu).

## Probe

`native/compat32_probe.c`, called by the pitcher before Wine, once per build: leaves a marker before trying, so if the test pulls the title it doesn't do it on each boot.
- Take a RWX page under 4 GiB (0x30000000).
- It does `lretq` to the selector **0x33** (code 32 bits, GDT of amd64 of FreeBSD, the same as the `wow64native` of prospero-win in PS5).
- In compatibility mode it runs `mov dword [abs32], 0x32BEEF32` and `retf` to **0x43**, and returns with the `rsp` and the continuation saved.
- A failure ends by `siglongjmp` and is reported.

<a id="resultado-físico-20261103t034008z"></a>


## Physical result: 20261103T034008Z

`compat32_probe native32=1 page=0x30000000 cs=0x43 cs_after=0x43 result=0x32beef32 signal=0`. The PS4 kernel (fw 12.52) **allows you to run 32 bit code in compatibility mode from the** app. The second start jumped the test by the marker. He arrived at the desktop (confirmed by the user on the page).

Already known from before: `ucontext` Orbis with `mc_fpstate` in + 320 and `mc_fsbase` in + 1152 (`platform/ps4/pw_wine_context.h`, as measured by prospero-win in PS5), and `sysarch` for the segment bases.

Next step if chosen: carry `wow64native`:
- `wine/wow64native/{cpu.c,unix.c}`;
- the entry of signals from the patch 0883, which recovers the base FS of the host when a signal comes in code of 32 bits;
- the fall to the translator if it fails, such as the patch 0614.
