<a id="w103-porcentajes-nativos-para-mangohud"></a>


# W103: native percentages for MangoHud

[English](HARDWARE_W103.md) | [Español](HARDWARE_W103-es.md)

APP_VER 02.02. W102 retains the physical reference of stability: two cycles, six closures 0, operational start and final output 0. W103 adds metrics; their accuracy and availability are pending implementation in a console.

<a id="qué-se-mide"></a>


## What is measured

- **CPU app**: difference from the clock CPU from the process (clock_gettime, clock FreeBSD 15) divided by time and quantity of CPU available in the initial affinity of the title. It includes OrbisDesk and its guests, not the overall use of PS4. If the clock or affinity is not available, show N/A.
- **GPU app**: binding of the GFX working intervals measured with GPU timstamps of Crema, between all the devices of the title and in order of dispatch. Divide work by the interval between GPU completed samples. It does not measure occupation of shakers or activity of other titles or of the system.
- Show every 500 ms. The first interval and the invalid counters show N/A. A loss of events invalidated that sample; it does not become an invented percentage. Percentages per core are not published.

Sampling is kept in the frame of W102, without new statistical threads. The GPU telemetry ring has limited capacity and records losses instead of blocking shipments. The provider records PWTELEM with raw values, statements and losses; MangoHud records PWHAD native_metrics.

Private consultation NtQuerySystemInformation 0x50573454 uses a versioned structure of 80 bytes. Standard classes of CPU of Windows are not modified. tools/build-telemetry-ps4.py recombine only system.o from the proven source, with the original recipe, and reconstruct the Mesa AMD file. The link replaces that object and adds native/telemetry.c. The previous draft of CPU of prepare-wine-boot.py is not executed.

The patches of Crema and MangoHud are applied on the compilation copies; Checkouts upstream are preserved. Manifesto and reports include source hashes, objects, AMD file, DLL, ELF and PKG. Evidence archived in reports/wine-hardware-w103/release-w103 and build-report.json.

<a id="construcción-y-validación-física"></a>


## Construction and physical validation

From WSL Ubuntu - 22.04 at the root of the project:

```sh
python3 tools/build-telemetry-ps4.py
bash tools/vk-h0/build-mangohud.sh
python3 tools/build-wine-hardware.py --mangohud enabled
python3 tools/upload-hardware.py --build W103 --host 192.168.68.104 --timeout 60
```

Compilation and liaison completed; local matrix omitted at user's request. PKG SHA- 256: 913c7e7df41bb6af6540e0f8997839e18e368db2a2356a0ab94134d2ba94a429. ELF SHA- 256: fac0deea9426fb36a583ac163ee8b35cd2ad229266481ca22d1fae856d3a86e4.

After installing, observe CPU app/GPU app with one application and with all three. Repeat two cycles of open/close glxgears, vkcube and vkspin, closing vkcube first, and return to Start. Check for load changes and tell if N/A persists. Upon receiving "I've already tried it," download the logs and check states, deltas, losses and closures before declaring the validated percentages:

```sh
python3 tools/fetch-hardware.py --build W103 --host 192.168.68.104
```

Transfer completed with verified return reading: `/data/pkg/orbis-win-W103-913c7e7df41b.pkg`. Report: `reports/wine-hardware-w103/transfers/20261102T135850Z.json`. Runtime: 548 files, 545 present and 3 uploaded, No permission failures. W102 removed from /data/pkg after verification. Local evidence preserved.

Transfer and physical result are recorded separately; compiling does not prove that the CPU watch or the GPU counter are valid on this console.

<a id="primera-sesión-física-20261102t140357z"></a>


## First physical session: 20261102T140357Z

74 samples were collected. The three applications were opened and closed with code 0. No crash marker; the desk continued to present pictures. The log does not record the final output of the title nor does it allow to credit two cycles or the Start response. Analysis: physical/20261102T140357Z/analysis.json within reports/wine-hardware-w103.

GPU ranged from 0,356 to 8,909%, with zero events lost. There is evidence of response to the load, without independent calibration. CPU is rejected ****: the valid samples give 16,666% and the alleged watch CPU It is almost the same as the time that has passed. A functional percentage is not considered. W104 replace that source with getrusage (RUSAGE_SELF), user + kernel, and remove "app" from the labels at the user's request.
