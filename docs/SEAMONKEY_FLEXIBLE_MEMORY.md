# SeaMonkey and the flexible memory pool

[English](SEAMONKEY_FLEXIBLE_MEMORY.md) | [Español](SEAMONKEY_FLEXIBLE_MEMORY-es.md)

Status: source change and a reproduction program, 2026-11-16. Not built into a package and not tested on the console yet.

## The symptom

SeaMonkey 2.53.24 (`C:\Program Files\SeaMonkey`, bundled since W303) loads remote sites. Pages with heavy JavaScript stop part way.

## Root cause

A title has two kinds of memory. The run logs show both at boot:

```text
PWBOOT memory_info direct=4831838208 direct_free=4692967424 (rc=0) flexible_free=391118848 (rc=0)
```

The whole title, with explorer, wineserver, Mesa and every guest, has about 390 MB of **flexible** memory. It has about 4.6 GB of **direct** memory. Wine's libc heap, wineserver and Mesa can only use the flexible pool.

Since W175 and W184, Wine commits of 1 MiB or more, and new committed views of 1 MiB or more, take direct memory. Anything smaller takes flexible memory.

SeaMonkey's allocator, mozjemalloc, works like this on Windows:

1. It allocates each 1 MiB chunk committed. That view takes direct memory (W184).
2. It decommits everything after the chunk's header at once (`MALLOC_DECOMMIT`).
3. It commits runs of a few pages as it needs them. It decommits and recommits them again when it purges.

Step 2 went through `decommit_pages` → `pw_rereserve`, which gave the direct memory back. Every commit in step 3 is under 1 MiB, so it took flexible memory. Over time, the browser's whole malloc heap (DOM, strings, script source, bytecode, JIT data) moved from direct memory into the 390 MB pool. A heavy page then used the pool up.

The W224 and W225 runs show the moment it runs out. These were SeaMonkey on YouTube, logs in `reports/wine-hardware-w224/physical/20261104T204513Z/run-0001.log` and `reports/wine-hardware-w225/physical/20261104T211135Z/run-0001.log`:

```text
PWVM commit_backing page=0x267704000 flexible map=0x80020016 at=0x267704000; direct memory instead (1)
...
map_view anon mmap error Invalid argument, size 0x14000, unix_prot 0x3
try_map_free_area mmap() error Invalid argument, range 0x102100000-0x102210000, unix_prot 0x3.
PWFAULT n=1 thread=0060 address=00000007FEF42EE5 access=1 target=0    (ucrtbase.dll, from xul.dll)
```

When the pool is empty, the kernel refuses a flexible map with `EINVAL` (`0x80020016`), not `ENOMEM`. W224's fallback kept commits inside reservations working with direct memory. New small views (`map_view`), and the Unix side, had no fallback. They failed, and a `NULL` from an allocation was written to.

The W303 SeaMonkey runs under `reports/wine-hardware-w303/` show no such lines. The logs don't record which pages were opened, and none of them shows a heavy page failing. No log of the current symptom has been collected yet.

The JIT is not the cause. SpiderMonkey reserves 1 GiB `PAGE_NOACCESS` (a kernel reservation since W182), then commits 64 KiB pieces and flips them between `PAGE_READWRITE` and `PAGE_EXECUTE_READ`. That uses little memory. W215 also ruled the JIT out for Pale Moon's YouTube hang. The JIT matters here only because it also takes flexible memory. Turning it off (`javascript.options.baselinejit`, `ion`, `wasm`, `native_regexp` set to `false`, like the old "Pale Moon (no JIT)" profile) is a way to test that difference. It is not the fix.

## The change

The change is in the generator [build-audio-ps4.py](../tools/build-audio-ps4.py), which patches Wine's `virtual.c`:

- **Decommit keeps direct memory.** `decommit_pages` now calls `pw_decommit_host` for the whole host pages of a decommit:
  - Pages under a direct-memory record keep their memory.
  - The 4 KiB pages Wine has committed are zeroed first. Windows hands out a recommitted page zeroed, and mozjemalloc relies on it (W222).
  - The range is then set to `PROT_NONE`, so an access faults as on Windows.
  - Pages not under direct memory are re-reserved as before.
  - Releasing the region (`MEM_RELEASE`, `unmap_area`) still gives the memory back.
  - Log line: `PWVM decommit_host … keeps direct memory` (first 8).
- **Recommit finds it.** `pw_commit_backing` skips host pages that the kernel reports as direct memory (query flags bit 1), with one query per kernel region. A recommit of a kept page maps nothing and uses no flexible memory. For a commit of 1 MiB or more, no second block of direct memory is mapped over the kept one.
- **A reserve for the Unix side.** Below 64 MiB of free flexible memory (`PW_FLEXIBLE_RESERVE`), commits and new committed views of **any** size take direct memory. The rest of the pool stays for wineserver, libc and Mesa, which have nothing else. Log line: `PWVM flexible low: … direct memory instead` (first 8).
- **More records.** The direct-memory record table grows from 8192 to 32768 entries, because small runs now take records too.

The SeaMonkey profile ([seamonkey-user.js](../fixtures/browser/seamonkey-user.js)) is unchanged.

## Reproduction

[jitmem.c](../fixtures/win32/jitmem.c) is a 64-bit guest. [build-wine-hardware.py](../tools/build-wine-hardware.py) installs it as `C:\orbis\jitmem64.exe`. It does SeaMonkey's allocations without the browser and appends to `C:\orbis\jitmem-result.txt`:

| Step | What it does |
|---|---|
| `heap` | 384 chunks of 1 MiB the mozjemalloc way: committed, all but 16 KiB decommitted, recommitted in 16/32/64 KiB runs. Each run is checked for zeros and written. |
| `purge` | On every fourth chunk, two runs are decommitted, recommitted and checked for zeros again. |
| `views` | 256 new committed views of 80 KiB, the size W224 saw refused. |
| `jit` | 1 GiB reserved `PAGE_NOACCESS`, then 256 pieces of 64 KiB. Each piece is written `RW`, flipped to `RX`, flushed and called at both ends, flipped back to `RW` and patched, then flipped to `RX` again. |
| `release` | Everything is released with `MEM_RELEASE`. |

Arguments, all optional: number of chunks, number of JIT pieces, and another output file. A failed step records the Win32 error and the count done so far. A step that cannot run is recorded as `skipped=…`, never `ok`.

Before this change, on the console, `heap` should push about 384 MB into the flexible pool. That ends the same way as W224, with `views` failing or the title faulting. After the change, every step should be `ok`, with `PWVM decommit_host … keeps direct memory` in the run log.

## What was tested

- The patched `virtual.c` is generated from the proven input (its hash matched) and compiles with its own recipe (`orbis-cc`, `-Wall`, exit 0). Nothing was written to `build/` or `out/`.
- `jitmem.c` compiles with mingw (`-O2 -Wall`, no warnings). On native Windows 11 (reference only, not PS4 evidence), all steps are `ok`: `heap` 384, `purge` 96, `views` 256, `jit` 256 pieces, `release` 641.
- **Not tested:** no package was built and nothing ran on the console or the emulator. The emulator does not model the console's flexible-memory budget.

## Test on the console (needs a build and the user's approval)

1. Run `C:\orbis\jitmem64.exe` from WFM. Fetch `jitmem-result.txt` and the log.
2. Open SeaMonkey on the heavy page that stopped before. Scroll it, then close and reopen SeaMonkey. Check the log for `PWVM flexible low`, `decommit_host`, `anon mmap error` and `PWFAULT`.
3. If a heavy page still stops and none of those lines appear, repeat it with a profile that has the JIT off (see above). That separates a JIT problem from a rendering or network one.

## Risks

- A decommit inside direct memory no longer gives memory back until the region is released. A program that reserves a lot, commits it once and decommits it keeps it. Direct memory is 4.6 GB, and the guest's regions are released when it exits (W208/W211).
- When the pool is low, executable pages (the JIT) can get direct memory. W224's fallback already did that. Whether the console allows execution on direct memory under GoldHEN has not been tested on its own. The `jit` step tests it only if the pool is low when it runs.
