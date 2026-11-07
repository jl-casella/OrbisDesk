<a id="w136-entrada-de-señales-para-código-de-32-bits-nativo-fase-5a-paso-1"></a>


# W136: entry of signals for native 32 bit code (phase 5A, step 1)

[English](HARDWARE_W136.md) | [Español](HARDWARE_W136-es.md)

APP_VER 02.35. Base W135 (the PS4 runs 32 bit code in compatibility mode).

<a id="por-qué-este-paso-va-solo"></a>


## Why is this step going alone

The `wow64native` of prospero-win runs the 32 bit code with the base FS pointing to the 32 TEB bits. If a signal comes at that time, the libkernel signal wrapper looks for its thread by `%fs` and reads trash. So the patch 0883 records the handlers directly with the kernel and puts the base FS of the host before any C. code

This build installs that entrance **without** still run code 32 native bits: the 32 bits still in the translator (`wowprospero`). So it is only the part that changes how all the signals of the process come in..

<a id="cambios"></a>


## Changes

- `platform/ps4/pw_wine_signals.c` (adapted from the patch 0883):
  - `pw_wine_native_signals_enable`:
    - takes the instruction `syscall` of the stub `getppid` of libkernel (+ 10);
    - the test by running `getpid` / `getppid` cross;
    - with a raw SIGUSR2 record it checks that the kernel frame has the MXCSR of the thread in uc + 320 + 24 and the base FS in uc + 1152.
    - Only if everything matches, the following records go raw (`sigaction` is the call to the system 416).
  - `pw_native_signal_entry` (asm), the input that the kernel calls:
    - if it is in the Wine signal stack, read the base FS of the TEB host (0x348);
    - If the current FS is another one, put the host's and call the usual handler;
    - When returned, replace the FS input, unless the handler has sent a thread of 32 bit (CS 0x33) to 64 bit code (release of exceptions of Wine): that's still with the host, in the register and in the frame.
    - Without FS of the known host and with CS 0x33 ends the process (`exit(127)` by the same syscall), instead of running C with the FS of the guest.
- `tools/build-signal-ps4.py` (new) compiles `signal_x86_64.c` of ntdll with:
  - a field `pw_host_fs` in `amd64_thread_data` (TEB + 0x348), which each thread fills in `init_syscall_frame` with `sysarch(128)`. `pthread_teb` continues in NULL: with a value, our dispatcher would make his own call `sysarch`.
  - `PW_NATIVE_SIGNALS=1` activates the raw mode before recording the handlers. It's logged `PWNATIVE signals raw=<0|1> ...`.
  - `__wine_prospero_native_wow64_caps(1)` returns `1|2` (raw inputs, FS from the host before C). **No** returns 4: the context of Wine in Orbis does not save xstate (`XState_sig` is NULL), so exceptions lose half of the high MYs. It's logged `PWNATIVE caps=`.
- `native/wine_hardware.c`: a program PE32 is launched with `PW_NATIVE_SIGNALS=1`. Explorer and the programs of 64 bits do not change.

<a id="qué-se-espera-en-el-log-del-programa-de-32-bits"></a>


## What is expected in the log of the program of 32 bits

- `PWNATIVE signals raw=1 syscall=0x... hits=1 mxcsr=X/X fsbase=Y/Y`
- `PWNATIVE caps=3 cs64=43 ss64=...` (0x43 is the CS measured in W135)
- The program goes as in W134/W135, now with the signals for the new entry.

If `raw=0`, the detail says what failed and the process continues with the libkernel wrapper.

<a id="prueba-física-20261103t040420z"></a>


## Physical test: 20261103T040420Z

The user confirmed that gui-window32 and SuperMarioKart walked the same. In the two logs of 32 bits:

    PWNATIVE signals raw=1 syscall=0x80000087a hits=1 mxcsr=0xbfe1/0xbfe1 fsbase=0x880dad720/0x880dad720
    PWNATIVE caps=3 cs64=43 ss64=3b
    wow64: CPU wowprospero.dll from WINE_PS4_WOW64_CPU

- The `syscall` instruction of stub of `getppid` libkernel executes other calls.
- The raw record of `sigaction` works.
- The signal frame has the MXCSR in uc + 320 + 24 and the base FS in uc + 1152, as in PS5.
- The 64 bit selectors are CS 0x43 and SS 0x3b, the same ones that you use `wow64native` in PS5.
- gui-window32 ended with `process_exit status=0`.

Next step (W137): `wow64native.dll` and its Unix side, with the translator falling if it does not start.
