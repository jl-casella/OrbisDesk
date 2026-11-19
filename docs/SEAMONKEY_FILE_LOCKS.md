# SeaMonkey, SQLite and byte-range file locks

[English](SEAMONKEY_FILE_LOCKS.md) | [Español](SEAMONKEY_FILE_LOCKS-es.md)

Status: diagnosis from the source and the SDK, a fix in the server generator, and a probe, 2026-11-17. The fix is in 04.14, where SeaMonkey loads YouTube completely on the console (run-0192.log, confirmed by the user). The probe was not run on the console.

## The symptom

On 04.12, which includes the [descriptor change](SEAMONKEY_DESCRIPTORS.md), SeaMonkey still does not finish loading YouTube. The run logs (`run-0185.log`, `run-0186.log`) show no failure: no `EMFILE`, no fault and no low-memory line. The same SeaMonkey 2.53.24 x64 loads YouTube fully on a Windows PC. On the console, SeaMonkey's error console shows `NS_ERROR_STORAGE_BUSY`.

`NS_ERROR_STORAGE_BUSY` is mozStorage's name for SQLite's `SQLITE_BUSY`. On Windows, SQLite takes its locks with `LockFileEx`, and it returns `SQLITE_BUSY` whenever that call fails, whatever the error (`winLock` in `os_win.c`). YouTube depends on IndexedDB, which is stored in SQLite. Google's search page does not, which is why Google loads.

## The cause

1. `LockFileEx` reaches wineserver, which records the lock in its own list and then also takes a Unix lock with `fcntl(F_SETLK)` (`set_unix_lock` in `server/fd.c`).
2. In the OpenOrbis SDK, `F_GETLK`, `F_SETLK` and `F_SETLKW` have the kernel's FreeBSD numbers (11, 12 and 13). But its `struct flock` has Linux's layout (`l_type`, `l_whence`, then `l_start`, `l_len`, `l_pid`), and its `F_RDLCK`/`F_WRLCK` are Linux's 0 and 1. FreeBSD's are 1 and 3, and its struct starts with `l_start` and `l_len`.
3. The SDK's `fcntl` passes the pointer to libkernel's `_fcntl` unchanged (checked in the disassembly of `fcntl.lo` in `libc.a`).
4. So the kernel reads the lock type from the high bytes of Wine's `l_len`, which is 0 for every lock SQLite takes. Type 0 is not a lock type, and FreeBSD returns `EINVAL`.
5. Wine treats `EINVAL` as a 32-bit offset limit and retries, gets `EINVAL` again, and fails the request with `STATUS_INVALID_PARAMETER`. Every `LockFile`/`LockFileEx` on a regular file in the title failed with `ERROR_INVALID_PARAMETER` (87).

The SDK's errno values are FreeBSD's, so Wine's other cases (`EAGAIN`, `ENOLCK`, `EOPNOTSUPP`) already match the kernel. Only the struct and the lock types are wrong.

This is not a stale lock from an earlier run. No lock could ever be taken, and the server's lock list starts empty with each title.

## The fix

- [build-wine-delete-server.py](../tools/build-wine-delete-server.py) now routes the two `fcntl` calls in `set_unix_lock` through `pw_wine_fcntl_lock`. It already rewrites `server/fd.c`.
- `pw_wine_fcntl_lock` ([pw_wine_fs.c](../platform/ps4/pw_wine_fs.c)) copies the lock into the kernel's own `struct flock` and lock types, and translates the answer to `F_GETLK` back.
- It writes the first 8 failures as `PWFS lock_failed fd=… cmd=… type=… start=… len=… errno=…`.

Conflicts between handles are still decided by wineserver's own lock list, as on any Wine. Every guest is in one process, and a process never conflicts with its own Unix locks. So the Unix lock adds no protection here. It now just succeeds instead of failing every request.

If the console's file system refused Unix locks altogether (`EOPNOTSUPP`, `ENOLCK`), Wine would stop asking for them on that file and keep its own list. That case is logged too.

## The probe

[lockprobe.c](../fixtures/win32/lockprobe.c) takes SQLite's locks through two handles of one file:
- the old `LockFile` at offset 0;
- the pending, reserved and shared bytes at 1 GiB, with the conflicts between the two connections;
- the WAL `-shm` lock bytes;
- the release of a lock when its handle is closed.

It writes one line per step, with `match` or `MISMATCH` against Windows' result, to `lockprobe-result.txt` next to the program.

```sh
x86_64-w64-mingw32-gcc -O2 -Wall -s -static-libgcc -o lockprobe64.exe fixtures/win32/lockprobe.c
i686-w64-mingw32-gcc -O2 -Wall -s -static-libgcc -o lockprobe32.exe fixtures/win32/lockprobe.c
```

- **Native Windows 11:** both builds give `mismatches=0`.
- **Expected on the console before the fix:** every step that should succeed fails with `error=87`.
- **Expected after the fix:** `mismatches=0`, and no `PWFS lock_failed` line in the run log.

## What was tested

- The rewritten `server/fd.c` compiles with the server's recorded recipe, and `pw_wine_fs.c` with the link recipe's flags plus `-Wall`, both with no warnings. `pw_wine_fcntl_lock` is not in the server's symbol-renaming map, so the server object links to the one in `pw_wine_fs.o`.
- The probe was built for 32 and 64 bit and passes on native Windows.
- **Not tested:** no package was built and nothing ran on the console. The kernel's acceptance of the translated lock on `/data` is unverified until the probe runs there.

## Console test (needs a build and the user's approval)

1. Before the fix, on the current build: copy `lockprobe64.exe` and `lockprobe32.exe` to `/data/orbisdesk`, run both from `Z:\orbisdesk` in the file manager, and fetch `lockprobe-result.txt`. This confirms the cause.
2. After the fix: run both again and expect `mismatches=0`. Then open YouTube in SeaMonkey, and look for `NS_ERROR_STORAGE_BUSY` in its error console and `PWFS lock_failed` in the log.

## On the console: 04.14 (run-0192.log)

The log has 7 `PWFS lock_failed … cmd=12 type=1 start=1073741824 len=1 errno=9` lines. `type` was printed as the SDK's value, so `type=1` is a write lock. The lock is on SQLite's pending byte, and errno 9 is `EBADF`.

These lines are not failures:
- wineserver opens a read-only handle's file `O_RDONLY`. A write lock on such a file gets `EBADF`, and `set_unix_lock` asks again for a read lock. This is stock Wine behavior, the same on Linux.
- Gecko opens some SQLite databases read-only, and SQLite still takes its pending byte with an exclusive `LockFileEx`.
- No read lock failed: a refused read lock would have been logged as another `lock_failed` line, and the log stopped at 7 of its 8.

So the translated locks work on `/data`, and the kernel supports byte-range locks there. **Result:** with 04.14, SeaMonkey loads YouTube completely, as the user confirmed. Only the run log and the user's report back this up: the probe was not run on the console, and the error console was not checked again for `NS_ERROR_STORAGE_BUSY`.

The log line now leaves out this retry and names the type (`read`, `write`, `unlock`). The same run also reached `fd_high fd=1006` without `EMFILE`, so 958 was not a fixed limit ([descriptors](SEAMONKEY_DESCRIPTORS.md)).
