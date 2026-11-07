<a id="incremento-12-transferencia-de-archivos-y-sockets"></a>


# increment 12: file transfer and sockets

[English](INCREMENT_12.md) | [Español](INCREMENT_12-es.md)

**It was implemented and tested SCM_RIGHTS in the fork Linux. Wine does not yet run the EXE:** the following observed block is `pipe`, necessary for server channels and threads. GS, the prefix and the provider WoW64 are still pending.

<a id="cambio"></a>


## Change

The sockets created with `socketpair(AF_UNIX, SOCK_STREAM)` keep references to the files and sockets sent as auxiliary data. The receiver installs own descriptors that share the original resource. Close the issuing descriptor before receiving no longer destroys the pending resource.

The rights are associated with the byte flow positions and are published together with the shipments actually accepted by the host socket. Uncontrolled readings rule out references; the readings with little space report truncated and release the remaining references. MSG_PEEK keeps the message and creates new descriptors for each reception. The EOF is maintained and the waiting on the real sockets of the backend; transport is not replaced by responses prepared for Wine.

The same shared property allows `dup` sockets. The non-blocking mode is shared; FD_CLOEXEC is still specific to each descriptor. Network objects that are not sockets, such as epoll, do not duplicate by this route.

Malformed controls and invalid descriptors are rejected before shipment. The supported controls are SOL_SOCKET/SCM_RIGHTS, with up to 253 descriptors per call. Direct and indirect cycles between socket pairs are explicitly rejected: there is still no collector of outstanding duty cycles. This limitation does not amount to complete support of Unix sockets of a kernel. It does not extend SCM_RIGHTS to sockets per pathname, datagrams or P2P. OOB and the PEEK/WAITALL combination are rejected in these local pairs. To record two aliases of the same socket in the same epoll is pending.

The Wine adapter translates MSG_CTRUNC from the kernel to the value of SDK, which is different, and allows MSG_PEEK. FD_CLOEXEC when received it is applied by fcntl, as before: no atumicity is demonstrated between reception and a concurrent exec. The multiple Windows process remains outside the initial range.

<a id="evidencia"></a>


## Evidence

The `reports/increment12/report.json` index records the final executions, their hashes and the blockades. 15 IPC checks and four platform regressions pass. The homebrew OpenOrbis `--ipc-services` checks:

- Messages with several buffers and non-blocking reading.
- Shared file position and CLOEXEC upon receipt.
- Two descriptors in a message, with the issuer closing before receiving.
- Partial truncate and lack of space for control.
- Separation between ordinary bytes and a message with rights.
- Unload with read and duplicate for MSG_PEEK.
- Transfer of a socket that continues to work after closing the original.
- Socket dup with shared mode and flags per descriptor.
- Invalid descriptor rejection without sending the byte of the message.
- Rejection of direct and indirect cycles.
- Two competing emitters and correspondence between byte and received file.
- Reuse of the descriptor numbers after closing the received ones.

Rejection checks validate errors, not implemented capabilities. The re-use of descriptor numbers is not an exhaustive measurement of host leaks. Platform tests are repeated for files, hilos/TLS, PE with DLL and concurrent memory. Everything corresponds to the low fork Linux WSL; the compatibility of these changes in Windows and PS4 is still pending.

Wine reaches the process of sending the channel and then requires pipe. The marker `inprocess_channel_ready` only indicates that the channel was sent; doesn't mean that the handshake or `server_init_process` is over. The previous stub pipe returned zero without creating its ends; Now return EOPNOTSUPP and keep the output. `--services` keeps the capacity `pipe-basic` locked and your error contract checked separate. There is no stub success to count the boot as functional.

The final attempt ends with code 0: the client receives EOF from the server and Wine calls abort_thread (0) in wine_server_receive_fd. The report remains `Wine_booted: false` and `windows_execution_verified: false`. The regression test verifies the closure before `server_ready` and the server error; does not accept that zero as a result of the EXE.

<a id="reproducción"></a>


## Reproduction

```sh
python3 tools/build-shad-linux.py --reuse-configure --jobs 12
python3 tools/check-increment12.py
python3 tools/check-increment12.py --verify-only
```

The first command requires the Linux configuration documented in the increment
11. Each execution uses a new process and retains its ELF and exact data in runtime.tar.gz. The capsules `reports/increment12/emulator` and `reports/increment12/wine-boot` keep the binaries, adapted sources, patches and construction options. The index does not change the evidence of previous increments.

The arrangement of the control and the truncate flask are contrasted with [sys/socket.h of FreeBSD 9](https://raw.githubusercontent.com/freebsd/freebsd-src/releng/9.0/sys/sys/socket.h) and the SDK OpenOrbis set. This does not replace the validation of ABI in PS4.

<a id="próximo-bloqueo"></a>


## Next block

Implement pipe with one-way reading and writing, EOF, non-blocking mode, poll and transfer of its ends, keeping the references shared. Try it with homebrew before repeating the Wine handshake. Then, solve the blocks that appear to reach GS and WoW64.
