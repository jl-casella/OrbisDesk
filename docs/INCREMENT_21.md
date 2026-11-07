<a id="incremento-21-mappings-privados-y-protección-de-ntdll"></a>


# increment 21: private mappings and ntdll protection

[English](INCREMENT_21.md) | [Español](INCREMENT_21-es.md)

**fix to mprotect of the increment 20 in the fork Linux. Wine completes the load and relocation of ntdll PE64 and reaches the initialization phase Windows. The EXE is not yet run by Wine.** The syscall slot is also adapted to large pages. The next block is to install and verify GS; the final execution ends clean with 93, without assertion or timeout.

<a id="corrección-del-emulador"></a>


## emulator correction

The patch 0010 spreads MAP_PRIVATE to mmap of the host Linux. Before, the file route always used MAP_SHARED. An open file only reading could be mapped for reading, but the later attempt to enable writing during replacements ended up in an EACCES statement. Now the private mapping uses real kernel copy-on-write Linux: your memory can be modified without changing the original file. Shared mappings retain their shared behavior.

The virtual region records if it can enable writing. This limit is obtained when creating the mapping and not by consulting a descriptor that could have been closed or reused. A request on a shared file mapping only reading returns EACCES before changing protections. The whole request is checked before it is applied, avoiding partial changes if another region of the range prohibits it. Regions with different limits are not merged.

The type of region is also preserved before dividing or merging its nodes, so as not to consult an invalidated reference after MergeAdjacent. The upper limit of the range is calculated by avoiding addr + size overflow.

The new copy-on-write selection is enabled for host files in Linux. The previous policy that reduces the initial permission of file mappings is retained only reading; The proven extension is by sceKernelMprotect. The virtual backends that already populated anonymous copies maintain that previous route. Windows, macOS, virtual and PS4 real backends are not considered validated by these file tests mounted in Linux. No export Orbis or a specific exception for Wine or for a game is added.

<a id="prueba-openorbis"></a>

## OpenOrbis test

`native/wine_file_mapping_probe.c` uses only file calls and memory of OpenOrbis. Check ten scenarios:

- Extend to read/write a private open file mapping only reading.
- Write on that copy by keeping the original file.
- Write on a private open file mapping read/write.
- Isolation between two private views of the same file.
- Valid private mapping after closing and reusing your descriptor.
- EACCES in a shared view only reading, even if your descriptor is reused to open the file with read/write.
- Atomic denial over a mixed range of private and shared regions, preserving the original protections of both.
- Shared writing visible from both the file and from another shared view.
- Private pages already modified keep your data by changing the file for a shared view.
- Shared view with writing permission retains your protection capacity after closing and reusing the descriptor for reading.

In the fork, the ten cases pass, without stubs or timeout. In the official emulator, the same ELF reproduces the protection statement in the first private extension and is blocked. The test is available for future hardware execution.

<a id="avance-real-de-wine-y-siguiente-bloqueo"></a>


## Real progress of Wine and next block

The external prefix, WINEARCH = wow64, the server within the process and the relocated image policy of the increment 20 is maintained. The DLL from Wine is not replaced by the synthetic modules of the 16 to 18 increments.

The prepared attempt reaches `ntdll_pe64_ready`, after loading, relocating and solving the functions of ntdll PE64. Then load ntdll PE32 and apisetschema and reach `entering_windows_initialization`. It is verified that the files of ntdll PE64 and PE32 keep the original hashes in the running file, even after the memory modifications made by the charger.

The first run was then stopped in anon_mmap_fixed: he asked for a page of 4096 bytes in `0x7ffe1000` on a host of pages of 16384. The built-in trace records those parameters in `anon_alignment_blocker`, without changing the request. That address is the dispatcher slot x64, located within the same host page as KUSER_SHARED_DATA. It does not correspond to a new stack allocation.

The LGPL patch of prospero-win `0530-ntdll-syscall-dispatcher-slot-in-large-host-page.patch` is adapted, with original, permissions and hashes in the manifesto. Your requirement for a user data section of at least one host page was already covered by the 0102 patch. Existing shared view is used: RW protection of 16 KiB, pointer writing on the slot and restoration of protection R. The Orbis adaptation checks the two protection results with the checked adapter, reads the pointer back and only then records `dispatcher_slot_ready`. Any failure ends with explicit error, without simulating the ready status or replacing the content of the page with an anonymous mapping.

The final run verifies the slot in `0x7ffe1000`, with a host page of 16384 bytes. The statement of mprotect and the alignment one no longer appear. Then sysarch continues to enter CommonStub: it does not install or return a real GS base. The adapter detects the lack of installation / verification and ends with code 93 (`0x5d`). There is no timeout or access violation in this final attempt. The report maintains `invoked_stubs: ["sysarch"]`; is not counted as Wine functional. The preruns with the assertion are preserved as exploratory.

<a id="validación-y-artefactos"></a>


## Validation and artifacts

The six cases of the offset contract of mmap, the 12 prefix and matrix checks of 31 of the increment 18. Their expected results, including the blocking of the official emulator, are maintained. Diagnostics services and GS and the start with empty prefix keep the above results. After the last adaptation of the overlay are repeated with ELF the preflight, services, GS, the empty prefix and CPI, pipes, filesystem and metadata; these last four are also contrasted with the previous matrix of the same fork. The negative consumer validation of the prefix is kept from the increment 19; their tools and the package are contrasted by hash and were not modified.

The main index is `reports/increment21/report.json`. Exploratory runs are kept separately and do not replace the tests of the fixed final binary. The individual reports retain logs, configuration and runtime.tar.gz. The capsules Wine and the emulator are low `reports/increment21/`, with verified hashes. Wine_booted and windows_execution_verified remain in false; the prefix continues to declare ps4_runtime_ready: false.

<a id="reproducción"></a>


## Reproduction

In Ubuntu 22.04/WSL, with the checks and patches fixed:

```sh
python3 tools/build-shad-linux.py --reuse-configure --jobs 12
python3 tools/build-wine-ps4.py --boot --all-unix
python3 tools/build-wine-ps4.py --boot --server
python3 tools/link-wine-boot.py
python3 tools/check-wine-file-mapping21.py --official
python3 tools/run-linux-wine.py --fork --prepared-prefix reports/increment15/prefix-package
python3 tools/check-increment21.py
python3 tools/check-increment21.py --verify-only
```

`--collect-existing` brings together the executions stored in build/increment21- * .log. The verifier requires the actual markers of ntdll and of the slot, the file contract and the clean lock of GS recorded. If it changes, we have to look into it.

<a id="prioridades-siguientes"></a>


## Next priorities

1. To implement and validate GS by thread with actual gs:, thread-to-thread insulation, TLS native preserved and restoration of the base. The --gs-services diagnosis and the real attempt of Wine must overcome this block.
2. Investigate dispatcher-mixed in Linux and connect the contract BTCpu * with the translator, contexts Wine, called Unix, callbacks, exceptions and code invalidation.
3. Run console32-bare.exe and then console32.exe by Wine, requiring file identical to Windows, completed thread and output 0.

Hardware PS4: pendiente.
