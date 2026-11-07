<a id="incremento-11-descriptores-e-ipc-de-wine"></a>


# increment 11: descriptors and CPI of Wine

[English](INCREMENT_11.md) | [Español](INCREMENT_11-es.md)

**Wine still does not run the EXE.** Your ntdll complete Unix and the server in process reach the preparation of routes, memory, environment and first TEB. The connection to the server is now stopped with an explicit error: it is missing to transfer descriptors by `SCM_RIGHTS`. This operation is not replaced by success.

<a id="implementación"></a>


## Implementation

The Linux fork of shadPS4 incorporates two additional general patches on the three above, set at `fork.lock.json` and reproducible with `tests/fork-patches.ps1`:

- `dup` shares the file description and its position. Close a descriptor keeps the file while another descriptor uses it.
- `F_GETFD` / `F_SETFD` keep `FD_CLOEXEC` per descriptor; double the clean. `F_GETFL` / `F_SETFL` allow the operations implemented, including the selection of non-blocking sockets. The outstanding variants are rejected.
- They are exported `sendmsg` and `recvmsg` from libkernel; The signed return of 64 bits is corrected. Several buffers operate without auxiliary data.
- `sendmsg` rejects auxiliary data with `EOPNOTSUPP` before sending the message. This protection avoids the silent loss of a descriptor; **does not implement `SCM_RIGHTS`**. `fstatfs` also returns an explicit error.

The PS4 adapter of Wine converts the message header from 56 bytes from SDK to 48 bytes used by the emulated kernel. It includes conversion of control headers and error management, the actual transfer of which is still pending. The semantics of this ABI in hardware is still pending.

The bootstrap checks the connection failure before following with `recvmsg`. The diagnoses `--services`, `--ipc-services` and `--gs-services` run the actual operations without requiring Wine to start.

<a id="validación-y-límites"></a>


## Validation and limits

The service suite verifies writing and seek, shared position after dup, independent lags, closure survival, CLOEXEC and EOF with poll. The IPC suite verifies messages with two buffers, non-blocking reading and rejection of auxiliary data without partially sending the message. The file transfer remains blocked. GS stops when detecting stub of `sysarch`, before testing for `gs:` accesses; does not count as support of GS.

The new reference executable `console32-bare.exe` It just matters. kernel32 and it is linked without CRT. In Windows real calculates `500500`, use a thread, solve a function of a DLL and write `sum=500500;thread=ok;dll=ok`. The report is in `reports/increment11-windows-reference`. **That check is not low execution. Wine or low PS4.**

The build Linux uses Clang 19, libc + + and its experimental library for `std::jthread`. A regression was detected when finishing threads: LLVM libunwind interpreted the frames record with a ABI different from the GNU expected by the emulator. The isolated tests passed to the top libgcc_s. The toolchain sets that link order; the final regressions and their hashes are recorded in `reports/increment11/report.json`. It does not require `LD_PRELOAD` in the final executions. The previous binary Windows is not reconstructed in this increment. Four libpng files use LF line endings to compile in WSL; the standardisation record verifies that they match the blobs set in Git. The submodule status can mark them as modified by that conversion.

The attempt to prepare a prefix with Wine native Linux remains incomplete: wineboot waits during installation of components. Your partial files are not considered a ready PS4 prefix. The optional source cache was verified, but not activated in the final build.

<a id="reproducción"></a>


## Reproduction

From Ubuntu 22.04 of WSL, at the root of the workspace:

```sh
python3 tools/build-shad-linux.py --jobs 12
python3 tools/run-linux-wine.py --fork --baseline --case threads-adapter --timeout 15
python3 tools/run-linux-wine.py --fork --baseline --case vm-stress --timeout 20
python3 tools/run-linux-wine.py --fork --services --timeout 15
python3 tools/run-linux-wine.py --fork --ipc-services --timeout 15
python3 tools/run-linux-wine.py --fork --gs-services --timeout 15
python3 tools/run-linux-wine.py --fork --exe out/console32-bare.exe --timeout 20
```

Each execution keeps ELF, entries and logs in your `runtime.tar.gz` file. `reports/increment11/wine-boot` retains the complete build and adapted sources; your verifier checks hashes and matches the ELF executed. The index of this increment distinguishes the official and fork tests. Everything is still up for hardware PS4.

<a id="siguiente-trabajo-necesario-para-ejecutar-el-exe-con-wine"></a>


## Next job needed to run the EXE with Wine

1. Implement the transfer of descriptors in local sockets with correct ownership, closure and shared position; extend the reproduction for truncate, several descriptors and concurrence. Repeat the actual handshake of wineserver.
2. Solve GS by thread with real memory accesses and check that it does not break TLS native. A getter/setter that only keeps a number is not enough.
3. Complete the off-of-console prefix, load ntdll PE64 and the necessary DLL Unix, and integrate the provider WoW64 with the prospero-win translator.
4. Run the fixture and check result file, thread, DLL and output code. Only then to count the first EXE executed by Wine.

These are identified requirements; the boot can reveal others. The changes in the emulator do not imply that the services of a real PS4 should be changed.
