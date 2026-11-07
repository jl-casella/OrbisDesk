<a id="investigación-gta-vice-city-pe32-y-la-base-0x400000"></a>


# Research: GTA Vice City (PE32) and base 0x400000

[English](investigacion-gta-vc-base-0x400000.md) | [Español](investigacion-gta-vc-base-0x400000-es.md)

Analyzed run: W208, `reports/wine-hardware-w208/physical/20261104T153132Z/run-0003.log`. EXE: a copy of the user on the console, read by FTP only reading to a temporary directory outside the repository. Nothing was packed and the file was not changed.

<a id="resumen"></a>


## Summary

- `gta-vc.exe` has no relocation directory. It can only be executed in `0x400000`.
- Wine mapped it in `0x027D0000` and remained unrelegated. The first access to an absolute address of the EXE failed: the writing of the index TLS in `0x006DF9E0`.
- `0x400000` is occupied by the title's own ELF, which the kernel of the PS4 loads on that base. This is not GTA specific: it affects any fixed base EXE, and most games of 32 old bits are.
- To load it in `0x400000` you have to get the eboot out of that area. That you can depend on the kernel, and you have to try it on a console before you touch the build of Wine.

<a id="1-por-qué-0x400000-no-está-libre"></a>


## 1. Why `0x400000` is not free

- The eboot is a ELF PIE of OpenOrbis (`tools/link-wine-boot.py:93`, `-pie` with `link.x`. Its first segment begins in the direction 0 (`link.x`, `.text`). `create-fself` marks it `ET_SCE_EXEC_ASLR` (`PS4 ELF Specification.md:11`), and the kernel chooses the base. In the logs that base is `0x400000` (`docs/INCREMENT_13.md:98`).
- `build/wine-boot/bootstrap.elf` (the last local build, perhaps not the exact one of W208) has `PT_LOAD` segments from 0 to `0xc5c050`. In memory that's `0x400000` - `0x105c050`, about 12,4 MB.
- GTA VC needs `0x400000` - `0xa14000` (`SizeOfImage` `0x614000`). That range is all inside the eboot.
- A fact that confirms it: in the increment 20, with a smaller eboot, Wine placed a PE32 in `0xed0000` and recorded that the preferred base was not free (`docs/INCREMENT_20.md:37`). Now Wine places it above (`0x27d0000`, line 452 of the log).
- `console32.exe` and the fixtures work because they are linked in `0x30000000` with relocations (`tools/build.py:79-102`; `docs/INCREMENT_16.md:51`).

<a id="2-el-exe-tiene-relocaciones-utilizables"></a>


## 2. Does the EXE have usable relocations?

No. Read PE header data from the console file (3 088 896 bytes):

|Field|Value|
|---|---|
| Machine | `0x14c` |
| Characteristics |`0x10e`: EXECUTABLE, LINE_NUMS_STRIPPED, LOCAL_SYMS_STRIPPED, 32BIT. **No** has `RELOCS_STRIPPED` (`0x1`).|
| ImageBase / SizeOfImage | `0x400000` / `0x614000` |
| Entry point |RVA `0x267c40`, within `.text`|
| DataDirectory[BASERELOC] |**0 / 0**: no relocations table|
|Sections| 14: `.text`, `.rdata`, `.exc`, `.asrc`, `.data`, `.CRT`, `/0`, `.idata`, `.tls`, `_rwdseg`, `_rwcseg`, `.bss`, `.edata`, `.rsrc` |
| TLS | StartAddressOfRawData `0x6f4000`, **AddressOfIndex `0x6df9e0`**, AddressOfCallBacks `0x6df9e4` |
| Imports | advapi32, ddraw, dinput8, kernel32, user32, winmm, wsock32, d3d8, mss32, ole32 |

- There are no typical sections of SafeDisc, and the `.nfo` of the folder indicates a 1.1 version without CD. No packaging signals were found. The problem is not protection: it is that the EXE has no relocation.
- Wine does not reject the EXE. In `virtual_relocate_module` (`.deps/wine/ps4-overlay/dlls/ntdll/unix/virtual.c:4072-4081`) only fails if `RELOCS_STRIPPED` is on. If the directory is empty, return `STATUS_SUCCESS` without touching anything. Wine upstream does the same (`.deps/wine/source/.../virtual.c:3970`).
- The log failure matches that:
  - `info[1]=006DF9E0` is exactly `AddressOfIndex` from TLS.
  - `edi=02a50074` is `0x27d0000 + 0x280074`, the directory TLS inside the mapped image.
  - The missing code is in the ntdll of 32 bit (`eip=7bf71c7b`), just after loading kernel32. That is compatible with the initialization TLS of the charger, although I did not symbolize the address.
- Even if that writing was avoided, the rest of the code uses absolute directions of `0x400000` - `0xa14000`. Reconstructing hand relocations is unreliable and would mean modifying the user's EXE. I rule it out.

<a id="3-qué-haría-falta-para-cargarlo-en-0x400000"></a>


## 3. What would it take to load it in `0x400000`

<a id="descartado"></a>


### Disloaded

- **Relocate the EXE**: it has no relocations table (section 2).
- **segment base other than zero in support of 32 bit**: all 32 bit code of Wine and the thunks wow64 assume flat memory.
- **Change the layout within Wine**: the range is occupied by the process PS4 itself, not Wine.

<a id="camino-real-sacar-el-eboot-de-la-zona-baja"></a>


### Real road: get the eboot out of the lower area

You have to make the title code not in `0x400000`. In order of cost:

- **A. PIE with `--image-base` high.** Link to `ld.lld -pie --image-base=0x1000000000` (or similar) and see where the kernel puts it:
  - in `0x400000 + vaddr`: the lower area is free;
  - again in `0x400000`: the kernel ignores the vaddr.
- **B. `ET_SCE_EXEC` (0xFE00, without ASLR) with high vaddr.** `create-fself` does not have an option for the type (`-ptype` is something else). We should park `e_type` before we generate SELF. That the kernel accepts a vaddr other than `0x400000` is not verified.
- **C. Stub boy plus module.** A minimum eboot that loads the boot from Wine as PRX (which the kernel places above) and then tries `munmap` of their own pages on `0x400000`. It's the most invasive. I don't know if the kernel allows the eboot to be mapped..

The fate of the eboot should be left out of the 4 GB low and of what it reserves Wine (`addr_space_limit=0x7ffff0000`, line 395). You should also avoid the GPU radv (`0x40_0000_0000` +) windows. A candidate range is `0x10_0000_0000` - `0x3f_ffff_ffff`; The probe has to confirm it.

<a id="4-propuesta-para-el-coordinador"></a>


## 4. Proposal for the coordinator

1. **eboot base wave (1 - 2 builds, without Wine).** A separate test eboot, without touching `link-wine-boot.py` or the current boot, which:
   - record `&__text_start` (variant A, and B if the A does not move anything);
   - try `mmap(0x400000, 0x614000, MAP_FIXED|MAP_ANON)` and register the rc;
   - print `PWBASE text=0x... low_map rc=... errno=...` and come back.

   If the two variants give `0x400000`, the C would remain, or accept that the fixed base EXE does not run in this design.
2. **Clean failure instead of crash (1 build, optional, independent)** Today the user sees 4,7 loading and return to the desktop without explanation. Two possible places:
   - In `native/wine_hardware.c`, next to `pe_machine`: read `ImageBase` and the relocations directory. If the base falls into the eboot and there are no relocations, record `pe_fixed_base` and not throw.
   - In the overlay (`virtual.c:4081`): if it is the main EXE, `delta != 0` and there are no relocations, return `STATUS_CONFLICTING_ADDRESSES`. Risk: an EXE without relocations that does not use absolute addresses would stop loading. It's rare, but it changes the behavior over Wine.

   I didn't touch either of you. The relaunch dialogue is in `tools/build-guest-hw.py`, which is now edited9.
3. **If the probe releases the low area (2 - 4 builds):** relink the boot with the new base and check `main_image_load ... base=0x400000` in the log. Just there are GTA's own problems:
   - `d3d8.dll` local in the game folder, ddraw and dinput8;
   - `Mss32.dll` (Miles) and wsock32.

   There's no serious estimate of that part yet.

<a id="sonda-b001-pkg-aparte-orbb00001"></a>


## B001 sound (PKG apart, ORBB00001)

- Source: `native/pwbase_probe.c`. Build: `tools/build-pwbase-probe.py`. These are new files; no shared tool (`orbis_package.py` is only imported) was modified.
- Package `IV0000-ORBB00001_00-ORBISWINPWBASE01`, title "OrbisDesk base probe B001." It is installed next to OrbisDesk (ORBW00002) without replacing it. Not included Wine.
- Variant A (`eboot.bin`): PIE `ET_SCE_EXEC_ASLR`, first segment linked to `0x1000000000`.
- Variant B (`/app0/pwbase_b.bin`): the same code linked to `0x1100000000`, with `e_type` `ET_SCE_EXEC`.
  - `create-fself` has no choice for the type, and `make_fself.py` of the SDK only works in Python 2.
  - Therefore the build changes `e_type` in the copy of the heading ELF of the SELF and recalculates the OHRM SHA- 256 (offset `0x380`). Check both before writing.
  - The segment digests do not cover the header. That the kernel accepts the SELF so modified is just part of what is proven.
- A runs and then throws B only once with `sceSystemServiceLoadExec`. Mark it with `/data/orbis-win/probe-base-b.tried`; to repeat B you have to delete that file.
- Each variant adds these lines to `/data/orbis-win/probe-base.txt`:
  - `PWBASE X start`: linked direction, `__text_start`, `main`, one data and the stack.
  - `text_delta`: difference between the actual direction and the linked direction.
  - The kernel map below 4 GB (`lowmap`.
  - `low_hint`: a `mmap` in `0x400000` without `MAP_FIXED`.
  - `low_map`: `MAP_FIXED` of `0x400000` / `0x614000`, only if the kernel does not report anything in that range; If the writing works, try a writing in `0x6df9e0`.
  - If the text or something else is in the range, it records `skipped` with the reason instead of stepping on it.
- Local test in a temporary directory: the two variants were compiled and linked, and the first `PT_LOAD` was in the requested direction. `create-fself` accepted both and the patch of B changed exactly 33 bytes. The packaging and the console were not tested.

How to read the result:

|Result|Meaning|
|---|---|
|A `text` Ο `0x1000000000`|the kernel respects the vaddr of the EIP; reach `--image-base`|
|A `text` = `0x400000` + `text_delta` = `-0xfffc00000`|the kernel ignores the vaddr; look B|
|B `start` with `text` Ο `0x1100000000`|`ET_SCE_EXEC` in the upper direction works|
|without lines of B and `b_load_exec rc≠0`|LoadExec or the SELF modified rejected|
| `low_map addr=0x400000 write_ok=1` |the area of GTA can be mapped with that layout|

<a id="resultado-de-b001"></a>


### B001 result

The user installed and opened B001. In `/data/orbis-win/` neither `probe-base.txt` nor `probe-base-b.tried` appeared.

- **Writing in `/data` is not the problem.** H001B use the same pay (`0x3800000000000011`, does not make any special steps and writes `/data/orbis-win/hw01` with `mkdir` and `open` (`native/hardware_boot.c:137-143`). B001 does exactly that in the first line of `main`.
- **The most likely is that the eboot of B001 I never would. `main`.** That eboot is variant A: PIE with the vaddr in `0x1000000000`. There are two possible explanations: the kernel rejected the burden, or the process died before `main` (replacements or crt).
- The user confirmed that B001 shows "error when opening." The system rejected the eboot before `main`, with the first `PT_LOAD` in `0x1000000000`. We don't have the error code yet.

<a id="sonda-b002-orbb00002"></a>

## Probe B002 (ORBB00002)

Same files: `native/pwbase_probe.c` and `tools/build-pwbase-probe.py`, rewritten.

- **The eboot is no longer the variant.** `eboot.bin` is a driver linked to 0, just like all the eboot that work.
  - Search the base line.
  - Launch each stage (`/app0/pwbase_<n>.bin`) with `sceSystemServiceLoadExec`.
  - Before launching a stage the mark pending in `/data/orbis-win/probe-base.state`. The stage erases the mark, measures and reproduces the driver.
  - If you open the driver find a stage still pending, record `stage_did_not_start` and follow the next one.
- **Etapas:**

  | Etapa |Linking to|Type|What for?|
  |---|---|---|---|
  | `z` | 0 | ASLR |control: if LoadExec from another file works|
  | `a2` | `0x10000000` | ASLR |if a vaddr other than zero load|
  | `a` | `0x1000000000` | ASLR |the variant of B001|
  | `b` | `0x1100000000` | `ET_SCE_EXEC` |type without ASLR in high direction|

- **Data for option C**, at the first opening of driver:
  - `modules`: name and segments of each loaded module (this ELF, libkernel, `libc.prx` of `/app0/sce_module`). It shows where the kernel places an application PRX, and if it is left out of the 4 GB low.
  - `self_unmap`: `munmap` and `MAP_FIXED` of a page that belongs only to an arrangement of the eboot itself. It shows if an eboot can release its own range.
  - An own PRX loaded with `sceKernelLoadStartModule` is left for B003, if these data justify it.
- **Departures:**
  - the log `/data/orbis-win/probe-base.txt`, with support in `/download0/probe-base.txt` if `/data` does not open;
  - `sceKernelDebugOutText`;
  - one notification of the system by stage (`PWBASE <etapa> text=0x… low_ok|occupied|…`) and one notification at the end (`PWBASE done`). The user can read them even if there is no log.
- **What does the user do:** open "OrbisDesk base probe B002." If the app is closed before `PWBASE done` notification, open it again, up to 4 times. To repeat everything from scratch, delete `/data/orbis-win/probe-base.state`.
- **Local test:** the script ran complete in a temporary directory, unpacked. The five pieces compile without warnings, each `PT_LOAD` is in the direction requested and `create-fself` accepts all. Neither the packaging nor the console are proven.

<a id="resultado-de-b002"></a>


### B002 result

"It also closed when it opened." Neither `probe-base.txt` nor `probe-base.state` appeared, and the back in `/download0` cannot be read by FTP. The driver is linked to 0, so the high direction does not explain this failure.

- It was compared. B002 with the packages that do start (H001B, G001, W211):
  - same `create-fself` and pay, same `sce_module`, `right.sprx` and `param.sfo` (`orbis_package.py`;
  - the icon is the same as W211;
  - no one does jailbreak or escape from the sandbox before using `/data`.
- The concrete difference is in the imports. The driver matters `sceKernelSendNotificationRequest` and `sceKernelGetModuleInfo`, which does not matter any eboot that has run here (compared to `llvm-nm` against W211 and H001B). An import that the system does not solve prevents you from starting before `main`. It's the most likely cause, but it's not proven.
- B001 only had already proven imports, so their rejection does point to the high direction.

<a id="sonda-b003-orbb00003"></a>

## Probe B003 (ORBB00003)

- **No new imports.** Notices and `sceKernelGetModuleInfo` were removed. The modules are seen on the full map of `sceKernelVirtualQuery`, which brings names. The build fails if any ELF matters something that does not matter the newest `wine.elf` or `hardware.elf` of H001B.
- **The first opening is just control.** Create `/data/orbis-win/probe-base.control`, write `PWBASE driver control …` in `probe-base.txt`, wait 5 s and close with LoadExec `exit`.
- **From the second opening:** base line (full map, `low_map`, `self_unmap`) and stages `z`, `a2`, `a` and `b`, with the slope mark as in B002.
- **What does the user do:**
  1. Open the app once and wait for it to close alone (about 5 s). Check for FTP that exists `probe-base.txt`.
  2. If it exists, open it again, up to 5 times if any stage closes it, until the log says `PWBASE driver done`.

  To repeat everything, delete `probe-base.control` and `probe-base.state`.
- **Local test:** the script ran complete in a temporary directory, unpacked. The five pieces have 23 imports each, all already tested.

<a id="resultado-de-b003"></a>


### B003 result

"It's closed too." Even the control of the first opening didn't write anything. So the import hypothesis doesn't reach, or it's not the cause.

Comparison with the packages that did correct:

- `param.sfo`: the same fields as W212 and H001B. APP_TYPE 1, ATTRIBUTE 0, CATEGORY `gd` and SYSTEM_VER 0 come from `orbis_package.py`. They change only title, IDs and version.
- `pkg.gp4`: the same `app_type="full"`, the same `sce_module/libc.prx`, `libSceFios2.prx` and `sce_sys/about/right.sprx`.
- fself: the same `create-fself --paid 0x3800000000000011`, without authinfo, as W212 and H001B.
- H001B ran in the console the 31/10 with this same toolchain (SDK libc, `link.x` unchanged) and wrote in `/data` (`reports/hardware-h001b/physical/20261031T051942Z`). A boy eboot from the SDK can work.
- The following is different: the probe code, the ORBB title and the `.bin` extra in `/app0`.

<a id="sonda-b004-controles-con-título-fijo"></a>


## Sonda B004: fixed-title controls

New user rules:

- A single title and content ID for all probes: `ORBB00001` / `IV0000-ORBB00001_00-ORBISWINPWBASE01`. Each one is installed above the previous one.
- A single package name: `/data/pkg/orbis-win-pwbase-probe.pkg`.
- As the same title is only reinstated with a larger version, each way has its own.

|Command|Version| eboot |
|---|---|---|
| `--control h001b` | 01.04 |`build/hardware-h001b/app/eboot.bin` no change, plus `hardware-marker.txt`|
| `--control w212` | 01.05 |`build/wine-hardware-w212/app/eboot.bin` unchanged|
|without option| 01.06 |the stage probe of B003|

Proposed order:

1. **h001b.** If you show your screen PASS/FAIL and write `/data/orbis-win/hw01/report-*` under ORBB00001, the title and package are fine, and the failure is in ELF of the probe (code or link).
2. **w212, only if h001b is closed.** Yeah. W212 running under ORBB00001, the problem is something of H001B which is no longer working today. If it also closes, it's the title or the package. Warning: the eboot of W212 Start Wine complete with `/data/wine-prefix` and writes in `/data/orbis-win/w212`, just like OrbisDesk.
3. **The probe, when a control works.**

In the local test the three modes were built in a temporary directory, with the versions of the table. They didn't pack.

<a id="resultado-de-b004-control-h001b"></a>


### B004 result (h001b control)

The H001B eboot, unchanged, opened under ORBB00001 and showed "all green." The title, package and charger work, so B001 - B003 failed by their own ELF.

The structural difference between those ELF and that of H001B are the required libraries (DT_NEEDED):

- H001B: `libkernel` and `libSceVideoOut`.
- B001 - B003: `libkernel` and `libSceSystemService`, which was what I needed LoadExec.
- The Wine eboot also requires `libSceSystemService`, but along with VideoOut, Sysmodule and others. I don't know what combination the system requires.

In addition, none of the B00x opened VideoOut.

<a id="sonda-b005-orbb00001-versión-0107"></a>


## Sonda B005 (ORBB00001, version 01.07)

- **Each ELF is constructed as H001B** (`tools/build-hardware-boot.py`:
  - the same lags, with `-Werror`;
  - the `sink.c` that ran in H001B (`build/hardware-h001b/sink.c`), changing only the frame folder to `/data/orbis-win/pwbase-frames`;
  - link to `-lc -lkernel -lSceVideoOut`.

  The required libraries are identical to H001B; was verified with `llvm-readelf`.
- **LoadExec is sought in running time.** It is charged `libSceSystemService.sprx` with `sceKernelLoadStartModule` from the directory with the random word of the sandbox, as `native/hw_pad.c` load libScePad (W030), and the function is obtained with `sceKernelDlsym`. If that fails, the app does not close itself: it shows "close the app from the PS4 menu."
- **Display:** each important line appears with the source of H001B. So the user sees the result even if the log fails.
- The first opening control and the stages `z`, `a2`, `a` and `b` remain the same as in B003. The test of proven imports is also maintained.
- Local test: the five pieces compete with `-Werror`, each `PT_LOAD` remains in their direction and `create-fself` accepts them. He didn't pack.

<a id="resultado-de-b005"></a>


### B005 result

"It ended in error." There was nothing left on the console of B005: neither `probe-base.control`, nor `probe-base.txt`, nor the folder `pwbase-frames`. The h001b control did leave `hw01/report-0006.jsonl` and `roundtrip-0006.bin` (4/11). So B005 died before the first line of `main`, even with the link recipe of H001B.

Which shared all the probes that failed and did not have the control that worked:

- **Extra SELF files in `/app0`** (`pwbase_*.bin`: in B001, B002, B003 and B005. The h001b control had none.
- **`own_page`**, an arrangement of 32 KiB aligned to 16 KiB in `.bss`: in B002 to B005. Enlarge the last RW segment (memsz `0x14714` against `0x4310` in H001B).

<a id="sonda-b006-bisección-desde-h001b-orbb00001"></a>


## Sonda B006: bisection from H001B (ORBB00001)

`tools/build-pwbase-probe.py --step N`. Each step has a larger version than the previous one:

| Paso |Version|Contents|
|---|---|---|
| 1 | 01.08 |Only the driver with `PWBASE_CONTROL_ONLY`: create the log, draw the screen and open as H001B. No LoadExec, no stages, no `own_page`, no other files.|
| 2 | 01.09 |The same `eboot.bin` step 1, plus the four `pwbase_*.bin` in `/app0`, which are never thrown. Try if your presence only breaks the boot.|
| 3 | 01.10 |The driver and the complete stages, without `own_page` (`PWBASE_NO_SELF_UNMAP`).|
| 4 | 01.11 |The complete probe, equal to B005.|

- Step 1 in console: should show "PWBASE PROBE DRIVER" and line `control_only ok`, and write `/data/orbis-win/probe-base.txt`. It closes from the PS4 menu.
- If the pass 1 fails, the cause is in the probe boot code, which is already almost that of H001B. They should be compared line by line.
- If the 1 step works and the 2 fails, the cause is the extra files in `/app0`, and the stages would have to live elsewhere.
- Local test: the four steps were built in a temporary directory. The driver of the pass 1 has a layout of segments almost equal to H001B and the same libraries required (`libkernel` and `libSceVideoOut`).

<a id="resultado-de-b006-paso-1"></a>


### B006 pass 1 result

"B006 ok." `/data/orbis-win/probe-base.txt` contains

```
PWBASE control_only log_fd=14 text=0x400000
PWBASE control_only ok: close the app from the PS4 menu
```

In addition there are three frames in `/data/orbis-win/pwbase-frames/`. The probe start works, and `text=0x400000` confirms the base of the eboot in a console. Follow the step 2, with the same `eboot.bin` plus the `pwbase_*.bin` in `/app0`. As its log is identical, success is recognized by two new lines at the end of `probe-base.txt`.

<a id="resultado-de-b006-pasos-2-y-3"></a>


### Results of B006 steps 2 and 3

- **Step 2:** opened. The extra `.bin` in `/app0` does not prevent the start.
- **Paso 3** (`reports/pwbase-probe-b006/probe-base-2.txt`):
  - The LoadExec sought in running time works: `dlsym=0` and the function in `0x8007e8ea0`. With it the title is closed alone and it launches other SELF.
  - The stage `z` (linked to 0) ran by LoadExec, as a new process (pid 1104), with the text in `0x400000`.
  - The stage `a2` (linked to `0x10000000`, type ASLR) did not write any lines and the user saw an error. Along with B001 (`0x1000000000` as eboot, "error when opening"), the conclusion is: **with the type that generates OpenOrbis (`ET_SCE_EXEC_ASLR`), an executable whose first segment is not in 0 does not run, and the one running is in `0x400000`.** The stage `a` uses the same type; The expected thing is that it fails the same.
  - The stage `b` (`ET_SCE_EXEC` is missing, without ASLR, in `0x1100000000`). It's the last way to move the eboot without option C.
- **Process map** (`sceKernelVirtualQuery`, up to `0x7ef000000`:
  - below 4 GB is only the eboot (`0x400000` - `0x420000` for the probe);
  - the rest starts at `0x200000000` (ScePackageInfo, direct memory, etc.);
  - The main pile is about `0x7eedfc000`.

  For option C, that means that the only obstacle under 4 GB would be the same stub.

<a id="resultado-de-b006-etapas-a-y-b-reportspwbase-probe-b006probe-base-4txt"></a>


### Results of B006 stages `a` and `b` (`reports/pwbase-probe-b006/probe-base-4.txt`)

- `a2` and `a` (ASLR type with vaddr other than 0) did not start.
- **`b` did start.** It's `ET_SCE_EXEC` linked to `0x1100000000`:
  - `text=0x1100000000`, `text_delta=0x0`;
  - the executable occupies `0x1100000000` - `0x110001c000`;
  - **there's nothing left below 4 GB**;
  - `low_map addr=0x400000 errno=0 write_ok=1`.
- Conclusion: with a high bound eboot `ET_SCE_EXEC`, the kernel loads it in its link direction and leaves the GTA range free. No need for option C.

<a id="plan-mover-el-eboot-de-orbisdesk"></a>


## Plan: move the OrbisDesk eboot

<a id="qué-suponía-la-base-0x400000-revisado"></a>


### What the base `0x400000` meant (revised)

|Piece|Status|
|---|---|
| Wine `mmap_init` (`ps4-overlay/.../virtual.c:767`) |Book `0x10000` - `0x68000000` and share the reservation around the occupied. Without the eboot, Wine is left with `0x400000` and the PE32 can be loaded into its base. No change.|
| `addr_space_limit=0x7ffff0000` (`virtual.c:3775`) |The eboot in `0x1100000000` is above the limit, outside Windows space, as a `.so` in Linux. No change.|
| Windows GPU of radv (`0x4000000000`, `0x4400000000`, `0x4600000000`…) |Do not overlap with `0x1100000000` - `0x11023ca5d0`.|
|System map (probes B006)|System areas in `0x200000000` - `0x201000000`, stack in `0x7eedf0000` - `0x7ef000000`, `libSceSystemService` in `0x8007e8ea0`. `0x1100000000` is free, tested by `b`.|
|Thunks of wow64native (`cpu.c:595-605`)|The distant jumps 32 → 64 go to `syscall_32to64` and `unix_call_32to64`, within `wow64native.dll` (below 4 GB), not to the eboot.|
|Truncated pointer to 32 bit in our code|`compat32_probe.c:47`, `pw_pe32_lifecycle.c:257` and `pw_k32_ps4.c:473` are data assigned under 4 GB, not addresses of the eboot.|
|Symbols tools|No subtraction `0x400000` (INCREMENT_13 did so by hand). With the moving eboot, the log addresses match those of the ELF.|
|`__dso_handle` of ld|Lld defines it in the heading ELF, which is worth 0 with the base 0 and is left in 0 when moving the image. Mesa the reference to `R_X86_64_PC32` and the link fails. The script defines it hidden at the beginning of the new image; It has to be just an address of the image (`__cxa_atexit`).|
|Symbols in 0 after moving|Only `native_cookie`, which is TLS: the value is an offset within the TLS block, as before.|

What cannot be verified without running: any heuristics of Wine or of the system that depends on the eboot code being below 4 GB. I didn't find any.

<a id="paso-1-sonda-b007-con-el-eboot-real-lista-para-construir"></a>


### Step 1: probe B007 with the real eboot (ready to build)

New tool: `tools/build-wine-highbase-probe.py`. Use the new `tools/orbis_self.py` and do not touch any shared files.

1. Read `link_command` of `out/wine-hardware-wNNN/manifest.json` (the newest, or `--build`). Repeat the link without change and require an identical `wine.elf` byte to byte. This is how it checks that WNNN's inputs remain; If it fails, first we have to rebuild WNNN.
2. It links back to the same `link.x`, adding `. = BASE; HIDDEN(__dso_handle = .);`. Check that every `PT_LOAD` moved exactly `BASE` and that the imports did not change.
3. `create-fself` with the same lags as `build-wine-hardware.py`, and then `ET_SCE_EXEC` (`orbis_self.set_exec_type`).
4. Pack as ORBB00001 version 01.12 and upload it as `/data/pkg/orbis-win-pwbase-probe.pkg`.

Local test with W215: the replay gave identical, the image was left in `0x1100000000` - `0x11023ca5d0` and `create-fself` accepted the result. It was not packed or executed.

What to look at in console:

- The desk starts as W215. The log goes to `/data/orbis-win/w215/` (the same directory as W215), with the current prefix and runtime of `/data`.
- When opening `gta-vc.exe`, the relaunch uses this same eboot. It is expected `main_image_load status=0 … base=0x400000`, instead of `40000003 … base=0x27d0000`, and that the AV will no longer appear in `0x006DF9E0`. What you miss after that is the game (d3d8, ddraw, dinput8, Mss32).

<a id="paso-2-integrar-en-el-título-real-archivos-compartidos-lo-decide-el-coordinador"></a>


### Step 2: integrate into the real title (shared files; the coordinator decides)

In `tools/build-wine-hardware.py`, about ten lines:

- Where you copy `link.x` (lines 88 - 93), put `. = 0x1100000000;` and `HIDDEN(__dso_handle = .);`.
- After `create-fself` (lines 161 - 163), call `orbis_self.set_exec_type`.
- Record `eboot_base` in the manifest.

`tools/link-wine-boot.py` no changes are needed: your `bootstrap.elf` does not pack, and `build-wine-hardware.py` replaces the `--script` command that you reuse.

<a id="riesgos"></a>


### Risks

- The SELF of B007 is modified after `create-fself`. B006 `b` showed that a SELF modified boy thus loads; with 30 MB should be the same, but it is not tested.
- If something in Wine or in the system libraries uses eboot addresses as 32 bit values, it will just fail in B007. This was not found in the review.

<a id="resultado-de-b007-w215-con-el-eboot-en-0x1100000000"></a>


## Results of B007 (W215 with the eboot in `0x1100000000`)

`reports/wine-hardware-w215/physical/20261104T182301Z`:

- The desk starts (run- 0001 and run- 0003).
- In run- 0002, `gta-vc.exe` load in its base: `main_image_load status=00000000 machine=014c base=0x400000` and `Loaded …gta-vc.exe at 00400000`. The TLS failure in `0x006DF9E0` disappeared. **Move the eboot solved the problem of the base.**
- Before the new failure load without errors:
  - the importance of the game: Advapi32, ddraw, dinput8, winmm and ole32, such as building; wsock32 is omitted because it is not used;
  - the local `d3d8.dll` of the game, in `0x10000000`, and `Mss32.dll`, in `0x21100000`;
  - later, `d3d9.dll` and `d3d8.dll` natives of `system32`.

  The missing ACM codecs (`l3codeca.acm`, `msgsm32.acm`) do not stop anything.

<a id="la-falla-nueva-getdiskfreespacea-devuelve-0-bytes-por-sector"></a>


### The new failure: `GetDiskFreeSpaceA` returns 0 bytes per sector

- The AV is in `0x58060C`, writing in `0xFFFFFFFC`.
- The function is a matching malloc of the game (`0x5805F0`):

  ```
  eax=size; ebx=align; malloc(size+align)          ; 0x6618C0
  edx=(ptr+align) & ~(align-1); [edx-4]=ptr        ; 0x58060C
  ```

  With `ebx=0` the mask is worth 0, `edx` worth 0 and writes in `-4`. The records of the failure match: `ebx=ecx=edx=0` and `eax=0x1893FD0`, which is the correct malloc.
- The only call that passes a variable alignment is in `0x408767`, in the initialization of the CD streaming ("Using no buffet rolling for streaming" and "cdvd_stream" chains):

  ```
  0x408710 call [0x6F2310]  ; GetDiskFreeSpaceA(NULL, &spc, &BytesPerSector, &free, &total)
  0x408716 cmp  BytesPerSector, 2048 ; si <= 2048: FILE_FLAG_NO_BUFFERING
  0x408767 call aligned_malloc(2048, BytesPerSector)
  ```

  In the run `BytesPerSector` it's worth 0. The game took the "no buffered" branch (0 ≤ 2048), does not check the return of `GetDiskFreeSpaceA`, and the local variable was left in 0.
- **Why is it worth it? 0 in Wine/PS4:**
  - `GetDiskFreeSpaceA` → `NtQueryVolumeInformationFile(FileFsFullSizeInformation)` → `get_full_size_info` (`ps4-overlay/dlls/ntdll/unix/file.c:2223`).
  - In `__ORBIS__` (no `linux`) the branch `fstatvfs` (`file.c:2241-2243` is compiled.
  - The eboot does not matter any statfs function: `fstatvfs` comes statically linked from the libc of SDK (`statvfs.lo`, in `build/wine-boot/lib/libc.a` and in the libc of SDK, that makes the syscall straight. This same libc has already failed with `lstat` and `readlink` in hardware (note in `build-wine-hardware.py`).
  - If `fstatvfs` fails, the query returns error, `GetDiskFreeSpaceA` returns FALSE and does not fill out.
  - The libkernel of the PS4 does export `_fstatfs` (stub of OpenOrbis), with the `struct statfs` of FreeBSD.
  - It is not measured in a console: the log does not trace the volume consultation. It's the most likely explanation, and the next build confirms it.

<a id="siguiente-paso-propuesto-para-la-próxima-w"></a>


### Next proposed step (for the next W)

`tools/build-wine-directory-ps4.py` already patches `file.c` with `replace()`. An additional `replace` would be added, which does not invent values:

- In `get_full_size_info`, low `#ifdef __ORBIS__`, call `_fstatfs` libkernel with a buffer of `struct statfs` of FreeBSD 9:
  - `f_bsize` in `0x10`, `f_blocks` in `0x20`, `f_bfree` in `0x28`, `f_bavail` in `0x30`;
  - `f_fstypename` in `0x118`;
  - 0x1D8 bytes in total; more is reserved.

  If `_fstatfs` fails, return the error as today.
- Record once `PWFS statfs rc=… errno=… bsize=… blocks=… bfree=… bavail=… fstype=…`. The name of the file system confirms that the layout is correct.
- With real values, `BytesPerSector` comes out 512 (or 2048 if `bsize==2048`) and the branch of the game works.

Risk: `_fstatfs` is a new import for the eboot of Wine. Comparing B005 (failed) with B006 step 3 (opened), the only difference was `own_page`, the arrangement of 32 KiB aligned to 16 KiB in `.bss`. A new import was not what broke the boot; We still have to check it out in the building.

After this, the expected is to reach Direct3D: the local `d3d8.dll` wrapper plus d3d9/d3d8 native `system32`, the Miles audio and the streaming of `.img` with `FILE_FLAG_NO_BUFFERING` / `OVERLAPPED`.

<a id="integración-del-eboot-alto-en-el-título-real-concreto"></a>


### Integration of the high eboot into the real title (concrete)

In `tools/build-wine-hardware.py` (shared), with the `tools/orbis_self.py` new:

```python
# línea 7
from orbis_self import set_exec_type
EBOOT_BASE=0x1100000000   # B006 stage b, B007: ET_SCE_EXEC loads here; 0x400000 stays free for PE32 images
# después de la línea 92 (antes de link_script.write_text(text))
if not text.startswith('SECTIONS\n{'):raise SystemExit('unexpected SDK link.x start')
text='SECTIONS\n{\n\t. = 0x%x;\n\tHIDDEN(__dso_handle = .);\n'%EBOOT_BASE+text[len('SECTIONS\n{'):]
# después de create-fself (líneas 161-163)
(work/'wine.exec.oelf').write_bytes(set_exec_type(work/'wine.oelf',app/'eboot.bin'))
# en el manifest (línea 757)
'eboot_base':hex(EBOOT_BASE),
```

- It's about ten lines.
- `tools/build-wine-highbase-probe.py` stop serving once integrated, because the `link.x` saved already brings the base.
- If at any time you would like to return to `0x400000`, just remove the two lines from the script and call to `set_exec_type`.

<a id="aplicado-para-w217-aprobado-por-el-usuario"></a>


## Implemented for W217 (user approved)

|File|Change| sha256 |
|---|---|---|
| `tools/build-wine-hardware.py` |`EBOOT_BASE=0x1100000000`, `. = base` and `HIDDEN(__dso_handle = .)` in the `link.x` copied, `set_exec_type` after `create-fself`, `eboot_base` in the manifest| `d8f989fc…3f116e` |
| `tools/build-wine-directory-ps4.py` |`replace` in `get_full_size_info`: in `__ORBIS__` use `_fstatfs` of libkernel, record `PWFS statfs` once and returns the error as if it fails| `4c0f41e8…081085f68` |
| `tools/orbis_self.py` |new, no change from B007| `30921262…3e4b7966` |

Unconstructed checked in `build/`:

- the `file.c` patching compiles without warnings in a temporary directory and `file.o` matters `_fstatfs`;
- the three scripts parsean.

The number of building (W216 → W217, version 03.16) is updated by the coordinator.

Order of build:

1. `tools/build-wine-directory-ps4.py`. `build-wine-hardware.py` only value the object's hash against its report, not what version of the script generated it: if it does not run first, W217 comes out with the old `file.o` without making a mistake.
2. `tools/build-wine-hardware.py`, and the usual rise.

What to look at:

- `out/wine-hardware-w217/manifest.json`: `"eboot_base": "0x1100000000"`.
- Desktop: runs like W216. The code addresses of the eboot in the log are now in `0x11…`; For example, `PWVK lookup … unchecked 0x11…` instead of `0x90dee0`.
- `gta-vc.exe`:
  - `main_image_load status=00000000 machine=014c base=0x400000`;
  - `Loaded …gta-vc.exe at 00400000`;
  - `PWFS statfs rc=0 bsize=… blocks=… bfree=… bavail=… fstype=…`. A legible `fstype` (e.g. `ufs` or `exfatfs`) confirms the layout;
  - AV should not be repeated in `0x58060C`.
- If `PWFS statfs rc=-1 errno=N` appears, libkernel also rejects `_fstatfs` and the cause is measured.

<a id="resultado-de-w217"></a>


## W217 result

`reports/wine-hardware-w217/physical/20261104T190832Z/run-0002.log`:

- `gta-vc.exe` load in `0x400000` (line 554). The moved eboot works in the real title: desktop and game.
- Line 1199: **`PWFS statfs rc=-1 errno=1`**. The new path runs, but `_fstatfs` of libkernel returns EPERM. The sandbox denies it, just like `lstat` (`probe libc_lstat rc=-1 errno=1`, which today is resolved with `stat`).
- Without sizes, `GetDiskFreeSpaceA` continues to fail, `BytesPerSector` remains in 0 and the AV is repeated in `0x58060C` (line 3544).

The cause was measured: the system does not allow the app to consult the volume with `fstatfs`.

<a id="siguiente-paso-propuesto-w218"></a>


### Next proposed step (W218)

The system libraries export, according to stubs of OpenOrbis:

- `libkernel_sys`, that the eboot already links: `statfs(path)`, `fstatfs` and `getfsstat`.
- `libSceShellCoreUtil`: `sceShellCoreUtilGetFreeSizeOfUserPartition`, the free space of the user partition, where it is `/data`.
- `libSceAppContent`: `…GetAvailableSpaceKb` for download and temporary data. They do not apply to `/data`.

All units of Wine are under `/data`: C: is `/data/wine-prefix/drive_c` and Z: is `/data`. In `get_full_size_info` (`__ORBIS__`) I propose to test in order and record a line `PWFS` by attempt, only the first time:

1. `_fstatfs(fd)`, as today (EPERM).
2. `statfs("/data")` of `libkernel_sys`, with the same layout of FreeBSD 9.
3. `getfsstat(buf, size, MNT_NOWAIT)`, looking for assembly with `f_mntonname` equal to `/data` or the longest prefix of the route.
4. If everything fails, **is decided by the user**:
   - (a) Return success with the geometry that Wine you always use (512 bytes by sector, 8 sectors per unit; `file.c:2261-2262` does not measure it except with `bsize==2048`) and the counters in 0. Registered `PWFS geometry_only`. GTA only uses `BytesPerSector`, but an installer who reviews the free space would see 0.
   - (b) Return the error as today. GTA is still falling.

   The option (a) does not invent free space; if you respond successfully without volume data.

Size: one `replace` more in `tools/build-wine-directory-ps4.py`, shared. The steps 1 to 3 do not invent anything, and the step 4 is a decision. With the log of W218 it is known which of the three queries allows the sandbox.

<a id="aplicado-para-w218-el-usuario-eligió-la-opción-a"></a>


### Implemented for W218 (the user chose the option a)

`tools/build-wine-directory-ps4.py` (sha256 `f3586b20…382fa8e8`) replaces the block of W217. In `get_full_size_info`, low `__ORBIS__`:

1. Test `_fstatfs(fd)` of libkernel. If it fails, record `PWFS statfs rc=-1 errno=N` once.
2. Test `getfsstat(buf, 64×0x1d8, MNT_NOWAIT)`, that of `libkernel_sys`. The libc of SDK defines `statfs` and `fstatfs` with raw syscalls, but `getfsstat` no, so the link takes it from `libkernel_sys.so`, that the eboot already requires. Choose the assembly with the longest `f_mntonname` containing `/data/wine-prefix`. It records `PWFS getfsstat rc=… errno=… mount=… fstype=…`.
3. With one of the two: `PWFS statfs bsize=… blocks=… bfree=… bavail=… fstype=…` and real values.
4. Without any: `PWFS geometry_only bytes_per_sector=512 sectors_per_unit=8 counts=0`. Returns success with the geometry that Wine reports for any disk and counters in 0. It is not declared free space.

Verified in a temporary directory:

- el `file.c` compila sin warnings;
- the complete link of W217, with that `file.o` and `--no-undefined`, ends well: `_fstatfs` and `getfsstat` they are as imports, and `libkernel_sys.so` is already among the required libraries.

`tools/build-wine-hardware.py` did not change (`d8f989fc…3f116e`). Steps: raise the number to W218, `build-wine-directory-ps4.py`, `link-wine-boot.py`, `build-wine-hardware.py` and raise it.

What to look at in the GTA Runs:

- one of the `PWFS` lines above;
- the AV in `0x58060C` no longer appears;
- the next failure, which should be after the initialization of the CD stream.

<a id="resultado-de-w218-y-cambio-para-w219"></a>


### W218 result and change for W219

- In `reports/wine-hardware-w218/physical/20261104T192945Z/run-0002.log`, the last line is `PWFS statfs rc=-1 errno=1` (line 1199). There is no line of `getfsstat`, no exception, no `process_exit`.
- The user saw "pkg error and closed." The system closed the title within `getfsstat`: that syscall does not return error, it kills the process.
- W219: `tools/build-wine-directory-ps4.py` (sha256 `6f713395…7d59c47c8`) remove `getfsstat`. After `_fstatfs` fails, it passes directly to `PWFS geometry_only bytes_per_sector=512 sectors_per_unit=8 counts=0`.
- It compiles without warnings in a temporary directory. The only new import against W216 is `_fstatfs`, which in W217 and W218 returned with EPERM without closing the process.

<a id="resultado-de-w219-necesita-al-menos-directx-81"></a>


## W219 result: "needs at least DirectX 8.1"

The disk no longer stops the game. Now the game shows its own notice that it is necessary DirectX 8.1.

- **How the game checks.** Do not look at the record: the exe does not contain `Software\Microsoft\DirectX`. Use the `GetDXVersion` function of the SDK examples of DirectX 8.1. The chains, in `0x2d3f6c` - `0x2d4038`, follow that order:
  1. load `DDRAW.DLL` and call `DirectDrawCreateEx`;
  2. load `D3D8.DLL` (if there is, the version is 8.0);
  3. `dpnhpast.dll` load (if there is, the version is 8.1).

  The corresponding error message is "Couldn't LoadLibrary dpnhpast.dll."
- **What's going on in W219** (`run-0002.log`, lines 1560-1569): Look. `dpnhpast.dll` in the game folder, in `syswow64` and `windows`, and ends with `Failed to load module L"dpnhpast.dll"; status=c0000135`. The game is left in 8.0 and shows the notice.
- **Registration:** is fine in both views. `Software\Microsoft\DirectX` and `Software\Wow6432Node\Microsoft\DirectX` have `Version="4.09.00.0904"` and `InstalledVersion` 9, that come from `wine.inf`. There's no need to change it.
- **The DLL exists but is not packed.** Wine compiles the unpatches for the two architectures: `.deps/wine/runtime/build/dlls/dpnhpast/{i386,x86_64}-windows/dpnhpast.dll`, "Wine builtin DLL, "with imports of kernel32, ntdll and ucrtbase. No list of modules includes it.

<a id="fix-propuesto-para-w221-una-línea"></a>


### Proposed fix for W221 (one line)

In `tools/stage-wine-extras.py`, add `dpnhpast` to `MODULES`:

```python
MODULES=(('comctl32_v6','comctl32_v6.dll'),('imaadp32.acm','imaadp32.acm'),('msadp32.acm','msadp32.acm'),
         ('msg711.acm','msg711.acm'),('msacm32.drv','msacm32.drv'),('midimap','midimap.dll'),
         ('dpnhpast','dpnhpast.dll'))
```

and a line in the docstring: "dpnhpast.dll: DirectPlay NAT helper; DirectX 8.1 checks (DX SDK GetDXVersion, GTA Vice City) load it by name. "

`build-wine-hardware.py` already install each module of `out/wine-extras` in `wine/lib/wine/<arch>-windows/` and `system32` / `syswow64` (lines 388 - 392). No changes are needed, but it requires the extras manifest to come from the current manager.

Steps:

1. `tools/stage-wine-extras.py`;
2. `tools/build-wine-hardware.py`, plus the usual steps (directory, link) if they changed their entries.

Implemented (coordinator's request): `tools/stage-wine-extras.py` sha256 `951827e4…a4bd4ea9`, with `dpnhpast` for i386 and x86_64. Both DLL are already compiled in the host tree (128 001 and 135 907 bytes, 2/11).

What to look at: `Loaded L"C:\\windows\\system32\\dpnhpast.dll" … builtin`, without the notice of DirectX. The following should be the creation of the D3D8 device through the `d3d8.dll` local.

<a id="resultado-de-w221-falla-en-vkcreateswapchainkhr"></a>


## W221 result: failure in `vkCreateSwapchainKHR`

`reports/wine-hardware-w221/physical/20261104T200201Z/run-0002.log`:

- `dpnhpast` load (line 1569) and the notice of DirectX disappears.
- The game creates the device with **DXVK 2.7.1 (x86)**, The `d3d8` / `d3d9` native of `system32` (lines 2127 - 2129).
- RADV fails in `ip=0x110048bd44`, reading the direction 0, and the process ends with status 3.

The analysis:

- With the symbols of `build/wine-hardware-w221/wine.elf` (sha `bc8745b7…`), that direction is in **`wsi_configure_image`** (Mesa `wsi_common.c`). With `VK_SWAPCHAIN_CREATE_MUTABLE_FORMAT_BIT_KHR` (`testb $4`, and the image receives `flags |= 0x508`), Mesa travel `pNext` looking for `VkImageFormatListCreateInfo` (`sType 1000147000`), which the specification requires with that flag. The chain ended without finding it and the reading of `NULL` failed.
- **The cause is in Wine.** In `win32u_vkCreateSwapchainKHR` (`dlls/win32u/vulkan.c:1858-1865`, if the image size (640 × 480) differs from the customer rectangle of the window and there are the maintenance1 extensions, Wine does `create_info_host.pNext = &scaling;`. That **replaces** the customer chain instead of extending it: the DXVK mutable flag remains and your list of formats is lost.
- It is not a problem of WoW64 or of our WSI: the conversion from 32 to 64 bits does not intervene.

<a id="fix-preparado-para-w223"></a>


### Fix prepared for W223

It is in the shared notes, not applied because W222 is compiling: `side-session-notes/…/swapchain-pnext-w223.patch.py` (sha256 `36875696…c6070668`). Add a `revise` to `tools/build-win32u-ps4.py`:

```c
        scaling.pNext = create_info_host.pNext;
        create_info_host.pNext = &scaling;
```

- It was tested on a copy of `build-win32u-ps4.py`: it is applied and the result is parsea. The context (`create_info_host.pNext = &scaling;`) appears only once in the `vulkan.c` set.
- Steps: apply the script to `tools/build-win32u-ps4.py`, run `tools/build-win32u-ps4.py`, then `link-wine-boot.py` and `build-wine-hardware.py`.
- What to look at: it should not be repeated `vkCreateSwapchainKHR Exception 0xc0000005`. DXVK should present the swapchain of 640 × 480, climbed to the window by `VkSwapchainPresentScalingCreateInfoEXT`.

Secondary: `quartz` does not have the FilterGraph (lines 2639 - 2721), so the intro videos probably fail. The game usually goes on without them.

<a id="w223-vice-city-juega-faltan-los-videos-de-intro"></a>


## W223: Vice City plays. Intro videos are missing

The fix of `pNext` solved the swapchain and the game goes with the control. What's left is the videos.

<a id="qué-falta-medido"></a>


### What's missing (measured)

- **Video format.** I read the headers by FTP, only reading: `movies/Logo.mpg` (7,2 MB) and `movies/GTAtitles.mpg` (24 MB are **MPEG- 1 system stream** (pack `0x21`, without MPEG- 2 extension). The video is MPEG- 1 from 640 × 480 to 25 fps (rate code 3). The audio is **MPEG- 1 Layer II** (`fffda400`: 192 kbps, 48 kHz, stereo). Streams are `0xe0`, `0xc0` and pating `0xbe`.
- **DirectShow of 32 bit is not there.** It's missing `quartz`, `devenum`, `msdmo`, `avicap32` and `msvfw32` in `syswow64`, in `wine/lib/wine/i386-windows` and in the sealed prefix. It is also not recorded in `system.reg`: hence the `class {e436ebb3-…} not registered` (FilterGraph) of W221, lines 2639 - 2721. The prefix does have `comctl32`, `msacm32`, `oleaut32`, `rpcrt4`, `version` and `winmm`.
- **The host tree of Wine does have them, without patches.** `.deps/wine/runtime/build/dlls/{quartz,devenum,msdmo,avicap32,msvfw32,amstream}/i386-windows`, and `libs/strmbase/i386-windows/libstrmbase.a`.
  - `avicap32` has a v4l capture unixlib, but its `DllMain` ignores the result of `__wine_init_unix_call` and charges equal.
  - `quartz` imports `msvfw32` and loads `ddraw` in deferred. `devenum` matters `avicap32`, `msdmo` and `msvfw32`.
- **No MPEG decoder-1.** In the Wine fixed, the MPEG splitter-1 and MPEG video and audio decoders (`CLSID_MPEG1Splitter`, `CLSID_CMpegVideoCodec`, `CLSID_CMpegAudioCodec`) exist only in `winegstreamer`, that needs GStreamer (`UNIX_LIBS = $(GSTREAMER_LIBS)`). In PS4 No GStreamer. Even if everything is installed DirectShow, `RenderFile("movies\\Logo.mpg")` can't find who decodify.
- **Registration.** We need more than COM's CLSID.:
  - * check-bytes * of "Media Type," which are in the script `WINE_REGISTRY` of `quartz` (`dlls/quartz/quartz.rgs`, already with the entry MPEG- 1 `000001ba…` to File Source (Async.). It can be read as it does `stage-mshtml-hw.py`;
  - The `FilterData` (REGFILTER2) that the `DllRegisterServer` of `quartz` writes with `IFilterMapper2_RegisterFilter` (`main.c:520-560`. Without them, the graph does not find the video renderer or that of DirectSound when it is built.

<a id="plan-propuesto-sin-éxito-simulado"></a>


### Proposed plan (without simulated success)

1. **`tools/stage-dshow-i386.py` (new).**
   - Unpatch copy of the i386 versions of `quartz`, `devenum`, `msdmo`, `avicap32` and `msvfw32` from the host tree.
   - Genera `system.reg.add` for Wow6432Node with:
     - the COM classes, from the resources `WINE_REGISTRY` of each module;
     - * Check-bytes * of "Media Type" of `quartz.rgs`;
     - The `FilterData` of the `quartz` filters, serialized in Python as it does `filtermapper.c`.
   - It does not record the filters that only exist in `winegstreamer`: there is no one who believes them, and to register them would be to announce something that is not there.
2. **A filter DirectShow own, `pwmpeg1` (new PE i386)**
   - It has its own CLSID and accepts `MEDIATYPE_Stream/MEDIASUBTYPE_MPEG1System` from File Source (Async.).
   - It displays two outputs: video RGB32 with `VIDEOINFOHEADER` and PCM audio of 16 stereo bits. It puts timstamps on both.
   - It really decodes, with **pl_mpeg** (phoboslab/pl_mpeg, MIT license, a single header), which covers just what videos use: system stream, video MPEG- 1 and MP2 audio.
   - It is compiled with `libstrmbase.a` of the host tree. It records traces `PWMPEG open/stream/first_frame/eos/error`.
   - If the file is not MPEG- 1 (e.g. MPEG- 2, or AVI with another codec), it rejects the connection to a trace and `RenderFile` fails as in a Windows without the codec.
3. **`tools/build-wine-hardware.py` (shared).** A few lines, following the MSHTML pattern: install the modules and add `system.reg.add` to `system.reg`.

<a id="riesgos-1"></a>


### Risks

- The `quartz` Renderer Video draws with GDI in a child window of the game, which presents with DXVK and Vulkan. How that is mixed in our composer (`ps5drv`) is not proven.
- pl_mpeg is a new dependence: you have to set a commit at `.deps/downloads`, with your LICENSE.
- Size: The filter is about 800 - 1200 lines, plus the generator of `FilterData`. They are expected 2 to 4 build, because the graph of DirectShow usually presents details one by one.

<a id="aplicado-para-w225-plan-aprobado-por-el-usuario"></a>


### Implemented for W225 (user-approved plan)

|File|What is it| sha256 |
|---|---|---|
| `.deps/downloads/pl_mpeg-c871f2be/pl_mpeg.h` |pl_mpeg in the commit `c871f2be022ece7ef4f64230b4fb8e1fb9eb6023` (2025-12-30, MIT according to the leader himself| `3a8cb30c…5fc2c9` |
| `.deps/downloads/pl_mpeg-c871f2be/LICENSE` |Provenance and license note (the repository does not have a separate LICENSE file)| `f75ebcfb…16e837` |
| `native/pwmpeg1/pwmpeg1.c`, `.spec` |the filter DirectShow (new)| `b5b62f7d…1d480`, `669471a1…1e62b` |
| `tools/stage-dshow-i386.py` |new manager: modules, filter and registration| `613e5caf…7b8ea` |
| `tools/build-wine-hardware.py` |install `out/dshow-i386` and add your `system.reg.add`| `4b3495f1…7d85e` |

**Filter `pwmpeg1.ax`** (CLSID `{D1ABD1FB-1295-47E2-A8FC-65868F9C0C90}`):

- Entry: `MEDIATYPE_Stream/MPEG1System`, read from the File Source by `IAsyncReader`.
- In the connection it opens the stream with pl_mpeg and records `PWMPEG open size=… video=… WxH fps=… audio=… rate=… duration=…`. If you do not find MPEG- 1 headers, record `PWMPEG reject …` and return `VFW_E_TYPE_NOT_ACCEPTED`.
- Departures: video RGB32 bottom-up and stereo PCM s16 audio. Each has its own thread and instance of pl_mpeg, with timstamps from the PTS.
- Record `PWMPEG <video|audio> first_sample`, `eos samples=N` or `stopped`.
- It's a native DLL (not built) that matters only kernel32, ntdll, ole32 and ucrtbase.

**Modules.** Copy without patches `quartz`, `devenum`, `msdmo`, `avicap32` and `msvfw32` (i386). The rest of your import closure is already in the view of 32 bits.

**Record** (263 keys, all in the view of 32 bits):

- the scripts `WINE_REGISTRY` of `quartz` and `devenum`. They include `CLSID_FilterGraph` and the "Media Type" check-bytes, which are written in `Classes` and `Classes\Wow6432Node`;
- 9 categories of `devenum`;
- 6 filters of `quartz`, with `FilterData` serialized as it does `filtermapper.c`;
- `pwmpeg1` with merit `MERIT_NORMAL`.

Filters of `winegstreamer` are not recorded. I read back the `FilterData` as it does `FM2_ReadFilterData`: Video Renderer, File Source and `pwmpeg1` come out with the pins and types expected.

**Verified without `build/` or `out/`:** the manager ran complete in a temporary directory (compiles and links the filter without warnings) and the parsean scripts. It wasn't tested on a console.

**Steps for W225:**

1. `python3 tools/stage-dshow-i386.py`. You need the toolchain of WSL of `build-dmsynth-i386.py`.
2. `tools/build-wine-hardware.py`, which refuses to follow if the manifest is not the current manager. Then I'll take her up.

**What to look at in the GTA Runs:**

- which no longer appears `class {e436ebb3-…} not registered`;
- load of `quartz.dll`, `devenum.dll` and `pwmpeg1.ax`;
- `PWMPEG open … video=1 640x480 fps=25.000 audio=1 rate=48000`;
- `first_sample` video and audio;
- at the end of each video, `eos`.

**Risks:**

- The graph first chooses `CLSID_VideoRendererDefault` (VMR7 in Wine, which uses ddraw). How it looks on the DXVK window of the game is not proven.
- If the game uses `IMediaSeeking` or `IMediaPosition`, the filter does not implement them: the call fails, but does not simulate anything.

<a id="resultado-de-w225-el-registro-no-llegó-al-prefijo-vivo"></a>


### W225 result: the record did not reach the live prefix

- In `reports/wine-hardware-w225/physical/20261104T211135Z/run-0003.log` it follows `class {e436ebb3-…} not registered`, and there are no lines `PWMPEG`. The `system.reg` of the console (1 423 302 bytes) does not have any of the keys of DirectShow.
- **Why it didn't come.** `wine-prefix/system.reg` is a runtime file, and the rise replaces it whole when it changes: so they came before GeckoPath, the audio classes of W121 and DirectMusic. But W225 run- 0001 started at 21: 03: 53 UTC (`libc=1793826233`), while the rise was still in progress (21: 00: 45 - 21: 04: 29; the PKG goes up first). That Wine loaded the old record into memory and his server kept it on top of the uploaded file. The live `system.reg` was last written at 21: 09: 41 (run- 0003, with 252 keys less than the building.
- **Fix prepared for W226 (without touching shared files).** It is the script `side-session-notes/…/system-reg-merge-w226.patch.py` (sha256 `4a2773ce…92ed2171`):
  - `build-wine-hardware.py` further writes `wine-prefix/system.reg.build`, the build record in a file that Wine never rewrites. It goes up like any other runtime file.
  - `wine_hardware.c`, before you start Wine, add to `system.reg` the `system.reg.build` blocks that have values and whose key is missing. He writes to a temporary and then renews it. It doesn't touch the keys the console already has. It does so once by building (mark `HW_DIR/system-reg-merged.txt`), because Wine does not restore the parent keys without values or those of devices that it relists. It records `Wnnn system_reg_merge live_keys=… build_keys=… added=… rc=…` or `already_done`.
  - Tested on copies: the patched launcher competes with the real lags and without warnings. The function, run in native with the `system.reg` live and the W225, adds 266 keys (264 of DirectShow, And in the second run he returns `already_done`.

<a id="resultado-de-w227-el-audio-de-los-videos-suena-la-imagen-no-se-ve"></a>


### W227 result: the audio of the videos sounds, the image is not seen

`reports/wine-hardware-w227/physical/20261104T214244Z/run-0005.log`:

- `system_reg_merge already_done`; `quartz`, `devenum` and `pwmpeg1` load; `PWMPEG open … 640x480 fps=25.000 audio=1 rate=48000 duration=39.40`.
- Video and audio give `first_sample hr=0`. The `stopped …` are because the user jumped the videos.

Analysis:

- **The renderer.** The graph chose VMR7 (`image_presenter_StartPresenting`). Your presenter (`dlls/quartz/vmr7_presenter.c`) open ddrag in `DDSCL_NORMAL` without a window, create the primary and put a clip with the video window. ddraw created a hidden window (`ddraw_attach_d3d_device … created hidden window 0001004C`).
- **The bug of Wine.** When you put the clipper, ddraw points your swapchain to the window of the clipper (`SetClipper` → `wined3d_swapchain_set_window`, `dlls/ddraw/surface.c:4784-4796`). But the Vulkan swapchain of wined3d preserves the `VkSurface` it created for the first window: it only redoes it before `OUT_OF_DATE` / `SUBOPTIMAL` (`dlls/wined3d/swapchain.c:931`, `1283-1290`). Each picture was presented to the hidden window: `PWVK show_frame … hwnd=0x1004c` to 25 fps.
- **The composer.** The video window is `WS_CHILD` of the game (`put_Owner`). `ps5_vulkan_frame` only accept top-level windows (`find_window`), and a daughter's image falls to a copy GDI inside her. The game window, whose client is a surface Vulkan of DXVK, didn't bring anything on screen during the videos.: `layers=1`, Just the bottom. That's why the user saw the desk..

**Fix prepared for W229** (W228 was used for another change): `side-session-notes/…/video-window-w229.patch.py` (sha256 `2a9287c0…74dae86a7`).

1. `tools/build-wined3d-hw.py`, which now also reproduces `swapchain.c`: before each present Vulkan, if the swapchain window changed since the swapchain Vulkan was created, it is recited for the new window. It records `PWD3D swapchain_window from … to …`. The window of each swapchain is stored in a table within `swapchain.c`, so `wined3d_private.h` does not change.
2. `tools/build-win32u-ps4.py` (`ps5drv.c`): `ps5_vulkan_frame` takes the image of a daughter window as a layer of his top-level (`GA_ROOT`), over the daughter's area, and `ps5_vulkan_forget` He takes it the same.

Tested on copies: wined3d compiles and links without warnings, and 47 objects of win32u compiles (3 warnings of `vulkan.c` they were already in the current building). It wasn't tested on a console.

Steps: apply the script to the root, run `build-wined3d-hw.py` and `build-win32u-ps4.py`, after the usual (`stage-dshow-i386.py`, guess, `link-wine-boot.py`, `build-wine-hardware.py`) and go up. It is appropriate to wait until the climb is finished before opening the title (W225).

What to look at:

- `PWD3D swapchain_window from 0001004C to <ventana de video>`;
- `PWVK show_frame … hwnd=<ventana de video> … path=gpu_layer`;
- more layers while the video lasts.

Risk: if during the videos the game window is not between the visible top-level that follows `ps5drv`, the image returns to the copy GDI as today. The log would show it because it would not appear `path=gpu_layer` for the video window.

<a id="w229-el-merge-de-systemreg-rompió-los-accesos-directos-error-mío-y-su-arreglo"></a>


### W229: the `system.reg` merge broke the direct access (my error) and its arrangement

- **Symbol.** Direct access to the Start menu and items of the control panel stopped opening: ShellExecute passed `.lnk` or `.cpl` a CreateProcess (`PWOPEN reject_title_replacement`).
- **Cause.** `merge_system_reg` measured each file with `fstat`, and in PS4 The `struct stat` of the libc of the SDK does not match that of the kernel. I read about 3 KB from each record:
  - W227 and W228: `live_keys=30 build_keys=29 bytes=2944`, without writing anything because there were no differences.
  - W229 run- 0001: those first bytes differed, so he "added" 20 blocks and wrote a `system.reg` of 5 KB (`live_keys=33 build_keys=29 added=20 bytes=5064`) The runs 0001 and 0002 started Wine with that record, without the associations `lnkfile` / `cplfile`.
- **Current state.** The rise of W229 was still in progress (finished 22: 06: 24 UTC; run- 0001 started 22: 04: 49) and put the `system.reg` again. All right. The living today has the same hash as the building (`18a6562a…`). The W229 mark already exists, so W229 does not do the merge again: there is no need to repair anything on the console. Open W229 again should show the direct accesses working.
- **Other changes of W229.** The changes of `joy.cpl` (`build-joycpl-hw.py`) just copy the DLL and do not touch the register. The `user.reg` living differs from the build only by the normal fusion of the rise.
- **Fix prepared for W230:** `side-session-notes/…/system-reg-merge-fix-w230.patch.py` (sha256 `d8e1a48e…3f968a3a`, only `native/wine_hardware.c`:
  1. `read_whole` read until the end of the unused file `fstat`;
  2. the key table takes place for the keys of the two files (with a living boy and a large build was filled and the search did not end; I found it when I tried);
  3. don't write anything unless both files look complete: at least 256 KiB, end in line jump and at least 1000 keys each. If not, record `implausible …`, do not write and do not leave the mark.

  Proof: the launcher competes with the real flags without warnings. In native, a live truncated gives `implausible` unwritten; with complete files add 266 keys; The second run gives `already_done`.

<a id="w230-el-arreglo-de-w229-no-se-activó-y-por-qué"></a>


### W230: the arrangement of W229 was not activated, and why

- W230 run- 0003: does not appear `PWD3D swapchain_window`, and the pictures continue to go to the hidden window `0001004C`. The `wined3d.dll` i386 of W230 does have the change (the chain appears in `wine/lib/wine/i386-windows` and `syswow64`).
- **Cause.** The presence of wined3d begins with `wined3d_swapchain_set_window(swapchain, dst_window_override)` (`dlls/wined3d/cs.c:682`, And a zero override means "the device window." Our W128 (`tools/build-ddraw-hw.py`), which shows the primary in window with the back buffer and a present, presented with null override. So, each present returned the hidden window and undone the video window VMR7 had put with the clipper. The check of W229 never saw a window change. In Wine upstream that doesn't happen, because there the primary is copied to the front buffer without present.
- **Fix for W232:** `side-session-notes/…/ddraw-present-window-w232.patch.py` (sha256 `bc2d1fae…6488ef637`). It is a line in `build-ddraw-hw.py`: the present name `ddraw->swapchain_window`, which is the window of the clipper when there is one and the usual one if not. Proof: it applies to a copy and ddraw compiles and links.
- Steps: apply the script, run `tools/build-ddraw-hw.py` and then the usual. The changes of W229 in wined3d and win32u are still necessary: they recreate the swapchain for the video window and show it over the game window.
- What to look at: `PWD3D swapchain_window from 0001004C to <ventana de video>`, and `PWVK show_frame … hwnd=<ventana de video> … path=gpu_layer`.

<a id="qué-no-se-hizo"></a>


## What wasn't done

- No file of `tools/`, `native/`, `platform/` or `fixtures/` was edited.
- No building was run in `build/` or `out/`, and nothing was up. The probe was only compiled and linked into a temporary directory, to verify the script.
- The EXE was read with FTP only reading from `192.168.68.104:2121` and is only in the temporary directory of this session.
