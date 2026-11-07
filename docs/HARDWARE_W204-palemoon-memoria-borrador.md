<a id="w204-pale-moon-como-invitado-se-traba-al-pedir-memoria-borrador"></a>


# W204: Pale Moon as a guest it is stuck when asking for memory (draft)

[English](HARDWARE_W204-palemoon-memoria-borrador.md) | [Español](HARDWARE_W204-palemoon-memoria-borrador-es.md)

Eraser of the browser side session, to join `HARDWARE_W204.md`. None of this was tested on the console.

<a id="qué-pasó-en-w203"></a>


## What happened in W203

Report: `reports/wine-hardware-w203/physical/20261104T134148Z/run-0001.log`. The user said, "It was frozen, but much later, sailing."

- **The `poll` arrangement of W203 works:**
  - `PWNET poll_count n=258` (line 3879) confirms that the server table has passed from 256;
  - no `PWSERVER poll_failed` appears;
  - The scout beat is in ~ 176 ms until the end, so the desk is no longer frozen.
- **The new:** from the line 7780, the `0110` thread of Pale Moon records 100 791 times the same line, until the end of the log: `virtual:map_fixed_area mmap error Invalid argument for 0x219400000-0x219500000, unix_prot 0x3`. It's always the same 1 MB.

<a id="causa-deducida-del-código-y-del-log"></a>


## Case (deduced from code and log)

- **`VirtualAlloc` with direction:** outside the reserved areas of Wine (on the console, `0x10000-0x68000000` and `0x7f000000-0x7fff0000`), the order `map_fixed_area` → `anon_mmap_tryfixed`. In the console it is `pw_wine_anon_tryfixed` (`platform/ps4/pw_wine_platform.c`), which makes:
  - `sceKernelReserveVirtualRange` fixed, not overwritten;
  - then `sceKernelMapFlexibleMemory`.
  
  His `EINVAL` became `STATUS_INVALID_PARAMETER`.
- **`VirtualAlloc` without direction:** memory comes out of `mmap(NULL)` libc (`anon_mmap_alloc`), And the location is chosen by the kernel.
- **The Pale Moon allocator:** the version for Windows, mozjemalloc, wants blocks of 1 MB aligned to 1 MB. For that:
  1. order some 2 MB without address;
  2. He frees them;
  3. order 1 MB in the aligned direction inside;
  4. If that fails, repeat from the pass 1, without limit. In Windows, that failure can only come from another thread that occupied the range.
- **Why does not end:** the kernel returns each time the same free range, and the fixed order inside fails each time.

<a id="cambio"></a>


## Change

`platform/ps4/pw_wine_platform.c`, `pw_wine_anon_tryfixed`:
- **When it acts:** with an accessible protection, when the kernel rejects with `EINVAL` the reserve or the fixed mapping, or places them elsewhere.
- **What are you doing?:** requests the same range to `mmap` of libc as a suggestion, without `MAP_FIXED`, how it does the road without direction.
  - It only serves if the kernel puts it right there.
  - If you put it elsewhere, you release it and return it `EEXIST` (occupied range, which Wine already handles).
  
  That way he never maddles over anything else.
- **What does not change:** the reserves `PROT_NONE`.
- **Trace:** the first 8 times, and then one each 1000, is recorded `PWVM tryfixed_hint` with:
  - the step and code of the kernel;
  - the result of `mmap`;
  - what it says `sceKernelVirtualQuery` in that direction.

<a id="construcción"></a>


## Build

1. `tools/link-wine-boot.py` (compila `pw_wine_platform.c`).
2. `tools/build-wine-hardware.py`.

<a id="prueba-física"></a>


## Physical test

1. Open `palemooncopy.exe` (as a guest) and navigate for a long time, as in W203.
2. **What to look for in the log:**
   - lines `PWVM tryfixed_hint … mapped=0x219400000` (or any address), where `mapped` is equal to `address`: the order of mozjemalloc was resolved;
   - the lines `map_fixed_area mmap error` are no longer repeated without end.
3. **If repeated as follows:** the lines `PWVM tryfixed_hint` show what is in that direction (`region`, `flexible`, `direct`, `committed`) and what returned `mmap`.

<a id="no-verificado"></a>


## Not verified

- Nothing was tested on the console.
- The change was compiled only with `clang -fsyntax-only`, with the options of `link-wine-boot.py`, on a copy.
- It is not known why the kernel rejects the fixed reserve in that range. That the kernel just delivered that range with `mmap(NULL)` comes from how it works Wine, not from a measurement. The new trace shows it.
- If in that direction there is something that Wine you do not know, `mmap` will place it elsewhere, the result will be `EEXIST` and mozjemalloc will continue to repeat. In that case, the trace says what the rank is.
