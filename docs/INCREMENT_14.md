<a id="incremento-14-directorios-ps4-y-diagnóstico-de-wineboot"></a>


# increment 14: directories PS4 and diagnosis of wineboot

[English](INCREMENT_14.md) | [Español](INCREMENT_14-es.md)

**Wine conserves server_ready and no longer invokes the CommonStub observed in the increment 13. The EXE is not yet running.** The new trace confirms that the requested auxiliary process is `C:\windows\system32\wineboot.exe`, machine
8664. It is explicitly rejected with STATUS_NOT_SUPPORTED within the initial scope of a single process.

The attempt then ends with STATUS_DLL_NOT_FOUND (0xc0000135), when solving `/data/console32.exe` in the empty development prefix. There are no units DOS prepared there. The runner retains the full guest code, `-1073741515`; the host code 53 corresponds to its eight-bit low. Wine_booted and windows_execution_verified are still in false.

<a id="adaptación-del-runtime"></a>


## Runtime adaptation

This increment modifies the runtime PS4, the overlay of Wine, the tests and the launcher. Keep the emulator in the f42070cabeb048cb0247711d7f30ad6f115ceba6 review.

The libc of the SDK entered _ fstat from fdopendir. The port now provides opendir/fdopendir/readdir/closedir/rewinddir/dirfd own over sceKernelGetdents and the conversion of existing stat. The Orbis structure, its registration size, and the name finished in zero are validated, and an input of SDK is produced. Each stream retains its descriptor, buffer and position; the closure releases the property and the associated records. No alias _ fstat is added to the SDK buffer that writes an incompatible structure.

Openat resolves AT_FDCWD against the cwd of the client or server module. For a registered directory descriptor, use your route and keep the record when duplicated. Absolute routes ignore dirfd. The records are synchronized with open/close/dup to prevent the reuse of an old route after closing. Implementation is a route-based subset: a directory received by mechanisms that do not record its route returns ENOTSUP. The directories rename is rejected, and external changes of its routes are not validated. The port table supports 256 directory records and returns EMFILE when it is exhausted. It does not amount to implementing complete openat within the kernel.

The CPU quantity query still lacks a verified adapter. It is returned - 1/ENOTSUP; Wine use your existing fallback of CPU. The result shows no affinity or topology of PS4. The other sysconf consultations are delegated to SDK; The page size of 16384 bytes is verified.

spawn_process records ImagePathName and returns STATUS_NOT_SUPPORTED before touching stdin/stdout or running fork. The reexec route also has explicit rejection for Orbis, although it is not reached in the final attempt. The actual test exercises wineboot rejection and checks the c00000bb error it receives Wine.

The helpers are now explicitly compiled with - D__ORBIS__, in addition to the target FreeBSD of PS4. This selects the native directories adapter. The flags are recorded in link-report.json; the original SDK remains intact.

<a id="validación"></a>


## Validation

Eleven tests are passed OpenOrbis in `--fs-services`:

- Relative opening in namespaces cliente/servidor and absolute route with invalid dirfd.
- Directory Dup and operation after closing the original descriptor.
- Route, descriptor and type errors, keeping the file after fdopendir failure.
- explicit rejection of dirfd without registered route.
- Enumeration of 40 long names, crossing the buffer of 4096 bytes.
- Rewind and second complete enumeration.
- Close the stream and reuse the descriptor with another directory.
- EOF of empty directory, accepting the point and point-point entries.
- Rejection of directory renaming.
- CPU error contract and page size, plus preparation of fixtures.

Negative controls validate errors; They don't count as supported capabilities. The complete suite also retains four platform regressions, fifteen IPC controls and ten pipes. The GS test and the mixed service suite keep their blockages known. Everything corresponds to the low fork Linux WSL; hardware and other hosts are still pending.

The same ELF was executed in shadPS4 official: ten controls of the filesystem suite pass and the duplication is blocked, with calls to stubs dup/fcntl. The guest ends with 92 And the emulator's closure is the timeout. These data are kept separate from the complete execution of eleven controls in the fork.

`tools/check-wine-fs.py` compiles and runs route algorithms in Linux with ASan, UBSan and leakage detection. The instrumented binary does not use PIE. Your report records commands, source hashes and binary and output code. This test uses the real host filesystem for algorithms; the structure of Orbis is checked separately in the homebrew.

<a id="reproducción-y-evidencia"></a>


## Reproduction and evidence

```sh
python3 tools/build-wine-ps4.py --boot --all-unix
python3 tools/build-wine-ps4.py --boot --server
python3 tools/link-wine-boot.py
python3 tools/check-wine-fs.py
python3 tools/check-increment14.py
python3 tools/check-increment14.py --verify-only
```

`reports/increment14/report.json` indexes the executions and their hashes. `reports/increment14/host-fs` retains the instrumented test. The capsules wine -boot and emulator of the same increment keep binaries and fixed sources; the verifier contrasts the exact ELF of the runtime.tar.gz. files. The above results are retained in their own increments.

<a id="próximo-hito"></a>


## Next milestone

Prepare and verify an off-console prefix, with DOS units, modules and proper registration. Validation should include links and file identity: the current backend still has limitations of lstat/readlink and dev/ino.

The first process of Wine calls run_wineboot even with a directory structure present. The port needs an explicit policy to consume an external prefix validated in its single process mode. Create only the folders does not initialize the prefix. Then there is a load of ntdll PE64, GS by thread and the integration of the provider WoW64 with the translator, before checking the result of console32-bare.exe.
