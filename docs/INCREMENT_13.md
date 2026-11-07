<a id="incremento-13-pipes-y-conexión-completa-con-wineserver"></a>


# increment 13: pipes and complete connection with wineserver

[English](INCREMENT_13.md) | [Español](INCREMENT_13-es.md)

**Wine complete server_init_process in the fork Linux and reach server_ready.** The EXE is not yet running: the start stops after the handshake, before confirming the load of ntdll PE64. There are outstanding amounts of filesystem and process creation. It is not considered Wine initialized by completing only the connection to your server.

<a id="implementación"></a>


## Implementation

The backend Linux uses host pipe2 with real ends of reading and writing. Both are incorporated in the table of descriptors of the emulator; they retain the added shared property in the increments 11 and 12. Internally they use the existing object waiting and registration infrastructure, but they are distinguished as pipes: fstat returns FIFO and resource identity, F_GETFL returns the right access mode and the operations of the wrong end fail with EBADF.

The physical descriptors are non-blocking; RunBlocking implement the guest's waiting. This allows EOF, backpressure, poll, blocking reading and small atomic scriptures using the operating system pipe. When you double or transfer an end by SCM_RIGHTS, close the original retains the resource. The reader receives EOF when the last reference to the writing end disappears, including the outstanding references to be delivered.

The creation publishes the two descriptors only after completing both insertions. If the table is exhausted, release the partial resources and leave the flare out intact. lseek, pread and pwrite on pipes return SPIPE.

Wine later arrived at the public import writer, which was not exported from libkernel. Public imports readv/writev and the E/S vector for pipes and sockets were added. The complete vector is validated, gathered in a writing operation or distributed a reading, retaining partial results. The limit of this route is 1024 buffers and a total of INT32_MAX bytes.

<a id="validación"></a>


## Validation

`--pipe-services` is own homebrew OpenOrbis, separated from the repository of shadPS4. Check ten cases:

| Caso |Behavior proven|
|---|---|
| pipe-basic-fifo-eof |FIDO, shared identity, modes, data, poll and EOF|
| pipe-access-errors |Address, SPIPE, zero sizes, zero argument and getsockopt|
| pipe-vectors |readv/writev and rejection of an invalid vector without data consumption|
| pipe-nonblocking-backpressure |EAGAIN, filling, small writing without partial and emptied shipping|
| pipe-dup-last-writer |State sharing, independent CLOEXEC and EOF after last closure|
| pipe-scm-rights |Transfer of both ends and prior closure of the issuer|
| pipe-blocking-wakeup |One reader waits until another thread writes|
| pipe-atomic-writers |Two writers send 200 records without mixing their content|
| pipe-broken-reader |EPIPE with SIGPIPE explicitly ignored|
| pipe-allocation-rollback |Table exhaustion, intact output and recovery|

The final index `reports/increment13/report.json` retains the executions, hashes and classification. It also repeats the 15 PC controls and four file returns, hilos/TLS, PE with DLL and concurrent memory. The official emulator contrasts separately: its pipe returns zero without writing ends; the diagnosis detects these outputs intact and is blocked, without using them. Your closing timeout is kept separate from the guest's result.

The attempt of Wine reaches first_teb_ready, inprocess_channel_ready and server_ready. Then he invokes stubs as cpuset_getaffinity, _ openat, _ fstat, rfork_thread, _ dup2 and _ execve, and ends with code 1. The report keeps Wine_booted and windows_execution_verified in false. These pending calls are not counted as functional services although CommonStub return zero.

<a id="reproducción-y-evidencia"></a>


## Reproduction and evidence

```sh
python3 tools/build-shad-linux.py --reuse-configure --jobs 12
python3 tools/check-increment13.py
python3 tools/check-increment13.py --verify-only
```

The initial configuration is the increment 11. The launcher also accepts `--pipe-services` individually. Each test uses a new process and preserves ELF and data in runtime.tar.gz. The capsules `reports/increment13/emulator` and `reports/increment13/wine-boot` include binaries, adapted sources, manifests, options and fixed patches. The build Windows before remains unreconstructed.

<a id="límites-y-siguiente-trabajo"></a>


## Limits and next work

The backend of this increment is only implemented in Linux; other hosts return an explicit error. All the real PS4 tests are pending. Pipe2 has not been validated as API from the guest and the delivery of SIGPIPE to the guest has not been implemented: the host protects its own process and returns EPIPE. The proof of that error installs and restores SIG_IGN; does not show signal delivery to a handler Windows or POSIX. The limitations of epoll aliases and SCM_RIGHTS increment cycles 12 remain in force.

The next job is to identify the post-handshake routes and review the ABI of the outstanding imports before adding alases. There is also a need to provide a complete prefix prepared out of console: the current vacuum prefix can cause attempts to launch auxiliary processes. The integration of modules Unix/PE64, GS by thread and the provider WoW64 with the translator remain pending before running console32-bare.exe and check their result.

`reports/increment13/startup-symbols.txt` places the returns of the pending calls using the exact ELF, the load base 0x400000 of the log and addr2line. cpuset_getaffinity comes from sysconf; _ open de open; _ fstat de fdopendir. rfork_thread is reached from spawn_process of Wine and _ execve from preloader_exec/loader_exec/exec_wineloader. The frames of SDK they have no available source line. This identifies which ABI and which route to review; does not prove that the requested process is wineboot or provides support for fork or exec.
