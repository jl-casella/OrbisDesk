<a id="incremento-25-texto-con-freetype-para-orbis"></a>


# increment 25: text with FreeType for Orbis

[English](INCREMENT_25.md) | [Español](INCREMENT_25-es.md)

<a id="implementación"></a>


## Implementation

FreeType 2.14.1 is compiled as a static file for x86 - 64 Orbis from the submodule `b91f75bd02db43b06d634591eb286d3eb0ce3b65`, fixed by the fork `9ac99bb2445e86f525519a4041a6c85362790ad2`. The host's library Linux and the `libSceFreeType` import library SDK are not linked. Zlib, bzip2, PNG, HarfBuzz, Brotli and Mac resource forks are disabled.

The overlay activates the actual backend of Wine and assigns its points `FT_*` to the linked functions. `FT_Init_FreeType`, the source load and the rastering keep their real errors. Both runtime links continue to demand that there are no unsolved symbols.

FreeType uses `pw_wine_fstat`, the same Orbis metadata adapter validated for Wine. The first test with the unadapted backend Unix invoked the stub `_fstat`, obtained an invalid size and failed; the reproduction and its ELF remain in `reports/linux-wine-runs/20261031T032646761159Z/`. Another Runs reached the drawing but failed to search for a fork resource of an invalid file: `reports/linux-wine-runs/20261031T033339521922Z/`. The Orbis configuration disables that optional format; the invalid file test is maintained.

The GUI staging verifies regular and bold Tahoma hashes, its SFD sources and licenses. It installs them in `windows/Fonts` of the private copy, with notices in `Fonts/licenses`, and sets the source and replacement records. The log entries contain complete Windows routes: Wine explicitly load the files for `load_registry_fonts`. With relative names, the private fixture worked but explorer found no source for `MS Shell Dlg`; The diagnostic Runs was left in `reports/linux-wine-runs/20261031T035852362753Z/`. A fictional listing result was not added and the emulator was not modified. The original package of the increment 15 remains intact. You don't throw wineboot. See [attributions](THIRD_PARTY_FONTS.md).

<a id="fixture-y-criterios"></a>


## Fixture and criteria

`gui-text64.exe` load from memory the same bytes of Wine Tahoma both in Windows and in the guest. Check family, positive metrics, glyphs and drawing by `TextOutW` on a DIB and on the window. It includes numbers, accents and peas. Read the entire client area, including the glyphs that exceed their advance, and demand the same number of black pixels as in the DIB. Save `text-result.txt` and demand real rejection of an absent and other invalid file.

The native reference of Windows ended with zero and produced:

```text
passed=1;family_tahoma=1;painted=1;width=298;height=24;metric_height=24;ink=1397;window_ink=1397
```

No exact equality of the antialiasing is required between Windows and FreeType. The three fork runs must pass, present pictures and end without stubs import or access violations. The scout desk must be presented and still alive until the timeout. The visual reading of the text is checked in the stored catches. The verifier looks for the DIB with its glyphs in all the pictures, avoiding the black closing box, and requires pixels of the Start label in explorer (it does not reach the icon).

<a id="regresión-detectada-al-validar"></a>


## Discount detected when validating

The control without a provider WoW64 found that the protection of the last private section of wow64.dll used `0x1d000` bytes. Orbis demands multiple `0x4000`, and rejected that protection with EINVAL: Wine ended with `0xc000007b` before looking for the provider. The failure is recorded in `reports/increment25/regressions24/report.json` and its individual Runs.

The overlay now protects the rounded size of the same section, `0x20000`, which mmap had already occupied. It does not extend the range to another mapping or change the source file permissions. The corrected focused test is in `reports/linux-wine-runs/20261031T041520955811Z/`: it reaches the expected error of absent provider `0xc0000135`, without stubs import or timeout. All cases of Wine with the new ELF are repeated; native tests can be reused only if they retain the same ELF and emulator.

<a id="reproducción"></a>


## Reproduction

On the complete construction of the increment 24, in Ubuntu 22.04/WSL:

```sh
python3 tools/build-freetype-ps4.py
python3 tools/build-wine-ps4.py --boot --all-unix
python3 tools/build-win32u-ps4.py
python3 tools/stage-wine-gui.py
python3 tools/link-wine-boot.py
```

From PowerShell in Windows, generate a new reference (the script refuses to overwrite a finished reference):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/reference-text25.ps1
```

Then in WSL:

```sh
python3 tools/check-increment25.py --report-dir reports/increment25-reproduccion
python3 tools/check-increment25.py --verify-only --report-dir reports/increment25-reproduccion
```

The preserved acceptance campaign was run without overwriting the above:

```sh
python3 tools/check-increment25.py --report-dir reports/increment25-accepted \
  --reuse-platform reports/increment25/regressions24
python3 tools/check-increment25.py --verify-only --report-dir reports/increment25-accepted
```

`--reuse-platform` verifies the native contracts and the matrix of the increment 18 already archived, demanding the same ELF native and emulator. Repeat all cases of Wine, including CPI, pipes, filesystem and metadata, with the ELF new. Allowing this option also runs native contracts from scratch.

The default directory is `reports/increment25/`; already contains the development campaign, so the previous commands choose a new one. The verifier refuses to overwrite a final report. For each campaign you must choose another directory by `--report-dir`, also preserving incomplete campaigns and their logs. It includes valid, altered and absent staging tests, three text runs, explorer and the complete increment returns 24 in a new directory. File the ELF, FreeType, sources, scripts, manifests, logs and catches. The individual creams keep their full runtimes and hashes.

<a id="resultado-y-continuación"></a>


## Outcome and continuation

The campaign [acceptance](../reports/increment25-accepted/report.json) ended with **passed**, without flaw, and it conserves 124 hashes of artifacts, in addition to the hashes of reports, stdout and runtimes of the four main runs.

|Verification|Result|
|---|---|
|Staging valid / altered source / absent source|All three contracts are passed; the invalids are rejected before executing Wine|
|Text PE64 in the fork|3/3, output 0; DIB and window have 1.252 black pixels and appear in the table presented|
|Explorer in the fork|visible start, 77 verified label pixels; expected timeout, without stubs import or access violations|
|Suite of increment 24|passed, 19 cases; the expected blocks of the official emulator, the empty prefix, the absence of CPU and exceptions are maintained|
| Console32-bare mediante Wine + wowprospero |passed with the ELF corrected; identical result to Windows|

The reference Windows conserves 1.397 ink pixels; the native rasterizer of Windows is not equated to the native rasterizer of FreeType. `Wine_booted` and verified execution are true in text fixtures that end successfully. Explorer is a long session: its capture is not counted as an EXE that ended or as a complete initialization of all services Windows.

The revised catches are `text-1.png`, `text-2.png`, `text-3.png` and `explorer.png` in the acceptance directory. The development campaigns and the protection failure remain in their original directories. No patches were added to the emulator. The official emulator is still blocked and the validation in PS4 real is pending.

The next milestone is real entry to driver. The GUI PE32 by wowprospero, the folder browser, its COM classes and services remain out of this increment.

In a timely follow-up, Marlett was incorporated into the same fixed review of Wine, with his SFD and full-track registration. A Runs of `gui-text64.exe` in shadPS4 ended with 0 output and showed the right icons to minimize, maximize and close. The capture is in `reports/marlett-caption/caption-fixed.png` and your report in that directory. The full suite was not repeated. The coverage of other alphabet remains pending.
