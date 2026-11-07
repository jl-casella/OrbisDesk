<a id="w104-etiquetas-cpugpu-y-fuente-cpu-corregida"></a>


# W104: CPU/GPU labels and corrected source CPU

[English](HARDWARE_W104.md) | [Español](HARDWARE_W104-es.md)

APP_VER 02.03. At the user's request, the visible labels remain CPU and GPU, without "app." They continue to measure the title OrbisDesk with their guests; they do not represent the overall consumption of the console.

The W103 test left CPU fixed at 16,666%: the imported clock with ID 15 advanced almost as the time passed. That metric was rejected. W104 uses getrusage (RUSAGE_SELF), adding process usertime and kernel, and retains the normalization for past time and initial affinity. An inconsistent error or interval shows N/A. The availability and values of this new source should be checked in PS4.

GPU retains the GFX timstamps of Crema and the sample in the frame of W102. In W103 values of 0,356 to 8,909% were observed, with no lost events. No statistical threads or life cycle changes are added.

```sh
bash tools/vk-h0/build-mangohud.sh
python3 tools/build-wine-hardware.py --mangohud enabled
python3 tools/upload-hardware.py --build W104 --host 192.168.68.104 --timeout 60
```

The private consultation object of W103, already verified by hash, is reused; the native provider and MangoHud is retracted. The Unix Printer or a local matrix is not run, according to the current preference.

In console: observe CPU/GPU with one and three applications, repeat open/close all three and return to Start. After "I already tried it," download and check the logs:

```sh
python3 tools/fetch-hardware.py --build W104 --host 192.168.68.104
```

Check that CPU is no longer fixed, check errores/rangos and raw deltas, losses GPU and guest exits. The absence of crash alone does not value the percentages. Construction, transfer and physical testing are documented separately in reports/wine-hardware-w104.

Compilation completed. PKG SHA- 256: 33b5527618262a29db545d5e108d9e96c63170f513336adf04d4a8315139e87f. ELF SHA- 256: a9571e8eeeaf797e96b18eba9c0819143fb319861608b1de7aa3c721a366c09d. Building and manifesto sources archived in releases. A subsequent metadata adjustment describes the getrusage source and the labels; It doesn't change binaries. The original script is archived with its compilation hash.

Transfer verified by return reading: `/data/pkg/orbis-win-W104-33b552761826.pkg`. Report: reports/wine-hardware-w104/transfers/20261102T141256Z.json. 548 verified runtime files, 545 present and 3 uploaded; no permit failure. W103 withdrawn after verification. Physical evidence pending.

<a id="resultado-físico-20261102t141838z"></a>


## Physical result: 20261102T141838Z

Logs downloaded and analyzed in reports/wine-hardware-w104/physical/20261102T141838Z/analysis.json. 90 samples: CPU between 6,917 and 32,801 %, GPU between 0,08 and 9,5%. CPU accumulated monotonic, no samples with errors and no losses GPU. With three apps are observed CPU around 28 - 31% and GPU around 8 - 9 %; when closing applications they descend, reaching CPU to approximately 7 - 9% and GPU to 0,8 - 0,9 % before the last closure. The observed defect of CPU fixed at 16,666% is resolved. There is no independent calibration of absolute accuracy.

Three openings and three closures with code 0, no crash marker. The desktop thread records activity after closing, but the log does not credit two cycles or final output of the title. The automatic state presented does not become an acceptance of overall stability.
