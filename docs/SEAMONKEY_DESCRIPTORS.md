# SeaMonkey and the title's file descriptors

[English](SEAMONKEY_DESCRIPTORS.md) | [Español](SEAMONKEY_DESCRIPTORS-es.md)

Status: 04.25 (five descriptors a thread) ran on the console in run-0234 with no `EMFILE`; the margin is not known yet. 04.26 only changes a log line and is not built. 2026-11-18.

## Run-0234: the first run with five descriptors a thread (04.26)

Run-0234 is 04.25 with OpenGL on, in `reports/wine-hardware-w303/physical/20261118T215511Z/`. SeaMonkey was started, used, closed and started again.

**The first start had no `EMFILE`, and it exited with status 0.**
- GPU frames were presented (`PWVK show_frame … path=gpu_layer`). There was no `PWTHREAD request_socket off`, so every new thread used the socket pair.
- The highest point was `descriptor_growth fd=818 open=819 files=260 pipes=288 sockets=240`. Pipes grew from 32 at start, about three per thread, and sockets about two, as expected.
- At `open=819` the title was above run-0224's failure (798) and close to run-0229's (837), without failing. So the limit is not the title's total count.
- The two failures had many more pipe ends: 435 in run-0224 and 498 in run-0229. Run-0234 stayed at 288. This fits a limit that counts pipes, for example the kernel's pipe memory, but the console's counters cannot be read (`kern.*` answers `ENOENT`), so it is not proven.

**The second start had no `EMFILE` either.** It ended in MangoHud's C++ exception, not in descriptors ([GPU compositing](SEAMONKEY_GPU.md)).

**What is left:**
- One run with no failure does not show the margin. Look at `pipes=` in every run with GPU compositing and YouTube, and at `descriptor_kinds` if `EMFILE` comes back.
- If it comes back with pipes high again, the next step is the wait pipe. It could also be a socket pair, which would leave no pipe ends per thread. That changes the same Wine code as 04.25 and needs its own console test.

**This change (not built):** [pw_wine_fs.c](../platform/ps4/pw_wine_fs.c): `descriptor_growth` estimates threads as pipes divided by three, not seven. It no longer prints the `kern.*` counters at each new high, since every name answered `ENOENT`. The `PWFS kernel_files` line at the first `EMFILE` stays. The file compiles for the console target with `-Wall` and no warnings.

## Run-0229: the traced run, and five descriptors a thread (04.25)

Run-0229 is 04.24 with OpenGL on, in `reports/wine-hardware-w303/physical/20261118T203415Z/` (run-0228 is the earlier part of the same title start). PES 2014's settings and `pes2014.exe` ran before SeaMonkey, so it is not a SeaMonkey-only run.

**What the traces show:**
- The first `EMFILE` came at `open=837`, on Safe Browsing's `safebrowsing/google4` folder. Pipes grew the most: from 42 at boot to 449 (`descriptor_growth fd=792`), then 498. Files grew from 39 to 303.
- A moment later an open succeeded at `fd=869` with `open=870`. Later opens failed again (explorer's desktop folders, `xulstore.json`). So the limit is not a count of the title's own descriptors. It moves with something else.
- Every `kern.*` name answered `ENOENT` through `sysctlbyname`, so the console's counters cannot be read from the title.
- SeaMonkey started 126 threads and had at most 54 alive at once (`thread_new … live=`). By creator: 96 through NSPR (`nss3.dll+1060f9`, the start of every Gecko thread), 14 by Mesa (`libgallium_wgl.dll+de8d7`), 6 by `xul.dll+33d6c60`, 5 Chromium-style threads (`xul.dll+8e8f8a`), and one each by SeaMonkey, MangoHud and two other `xul.dll` sites.
- About 71 threads were alive in the whole title (pipes divided by seven), 497 descriptors.

**The change (not built):** a thread made by `NtCreateThreadEx` uses one Unix socket pair for its requests and its replies, instead of two pipes. It needs five descriptors instead of seven. At 71 threads, that is about 140 descriptors fewer. The run would have stayed below `open=700`.
- [prepare-wine-boot.py](../tools/prepare-wine-boot.py), ntdll's `thread.c`: `NtCreateThreadEx` makes a socket pair and makes the server's end non-blocking with `pw_wine_socket_nonblock`, which tries `fcntl`, then `SO_NBIO`. If either step fails, it logs `PWTHREAD request_socket off`, makes pipes as before, and does not try the socket pair again. A thread's exit closes that one descriptor once.
- ntdll's `server.c`: `init_thread_pipe` sees the socket, makes only the wait pipe, and sends `reply_fd` -2.
- [build-wine-delete-server.py](../tools/build-wine-delete-server.py), the server's `thread.c`: `new_thread` accepts a socket that `fcntl` refuses, with the same fallback as the server's other sockets. `init_thread` takes -2 as "reply on the request descriptor" and shares that descriptor between the two.
- The server's `request.c`: the two places that switch between waiting for a request (`POLLIN`) and finishing a reply (`POLLOUT`) no longer set the second descriptor's events after the first's when both are one. Otherwise the server would stop listening to the thread.
- A process's first thread, made by the server, keeps its pipes. The wait pipe is unchanged: a thread keeps its write end to put back a wake-up that a nested wait took.
- [build-guest-hw.py](../tools/build-guest-hw.py): `thread_new … by=` also looks past `nss3.dll`, so it names the Gecko code that started each NSPR thread.
- The four Wine units (ntdll `thread.c` and `server.c`, the server's `request.c` and `thread.c`) compile with the console recipes from `build/wine-boot/report.json` and `build/wine-server/report.json`. There are no new warnings. The three in ntdll's `server.c` are the same without this change.

**Risks to check on the console:**
- Replies larger than the socket's buffer are written in parts. The server already finishes them on `POLLOUT`, the path a full pipe used.
- The `PWNET nonblock` line appears once, if `fcntl` was refused and `SO_NBIO` was used.
- If `PWTHREAD request_socket off` appears, the title ran with pipes, as before.

**Next console run, with this change built:** OpenGL on, SeaMonkey with nothing before it, then YouTube. In `descriptor_growth`, `pipes` should grow by about three per thread and `sockets` by about two. Look for `PWTHREAD request_socket off` and for any hang right after a program starts a thread. Also run one 32-bit game and one 64-bit game, since every program's threads change.

## Run-0224: GPU compositing reaches the limit at start (04.22)

Run-0224 is 04.22 with OpenGL on in the console's `user.js`, after PES 2014 had run and exited in the same session. It is in `reports/wine-hardware-w303/physical/20261118T191237Z/`. SeaMonkey presented GPU frames (`PWVK show_frame … path=gpu_layer`). About 10 s after it started, the title ran out of descriptors:

```text
PWFS descriptors open=798 highest=797 maxfilesperproc=-1 errno=2 maxfiles=-1 errno=2
PWFS descriptor_kinds files=295 folders=11 pipes=435 sockets=35 other=20 unknown=2 nofile=13952/13952 errno=0
```

Gecko then stopped on a breakpoint (`0x80000003`) on its main thread, in `xul.dll`. That is a `MOZ_CRASH`-style stop after an open failed, not the earlier GPU crash.

**The pipes are Wine's thread pipes, not a GL leak.**
- With the in-process server, each Wine thread holds seven pipe ends: its request, reply and wait pipes (`dlls/ntdll/unix/server.c` `init_thread_pipe`, `thread.c` `NtCreateThreadEx`). The thread keeps four (request write end, reply read end, both wait ends) and the server keeps three. This corrects the six in "Why the table fills" below.
- 435 pipe ends are about 62 live threads in the title: explorer's and SeaMonkey's.
- At its exit, SeaMonkey's guest listed 89 threads. 80 of them start in ucrtbase's `_beginthreadex`, which Gecko's NSPR threads and Mesa's queues both use. So the start address does not say who made them.
- GPU compositing adds Mesa's threads to SeaMonkey. Zink starts one flush thread and four compile threads per screen, and one more thread for each threaded GL context (`zink_screen.c`, `u_threaded_context.c`; the shader cache is off in this build, so `disk$` and `zcq` are not started). That is about 7 threads and 49 descriptors. This is why GPU compositing reaches the limit at start, while Basic reached it later, on YouTube.

**The limit is not the descriptor table's, and the title cannot raise it.**
- `RLIMIT_NOFILE` is already 13952.
- The title has run out at 958 (run-0180), 1035 (run-0212), 798 (run-0224) and, for VLC, 459 open with the highest at 642 (`manual-20261109T221515Z/run-0004.log`). A per-process count of table entries would fail at one number, and VLC would not have failed with free entries below 642.
- So the kernel counts something else. It may be the console's open files across all processes, if Sony's kernel reports `EMFILE` where FreeBSD's `falloc` reports `ENFILE`. The numeric `sysctl` MIBs answered `ENOENT`, so this has not been read yet.

**This change (not built):**
- [pw_wine_fs.c](../platform/ps4/pw_wine_fs.c): at the first `EMFILE`, a `PWFS kernel_files` line with `kern.openfiles`, `kern.maxfiles`, `kern.maxfilesperproc`, `kern.maxusers`, the socket counters and the pipe memory, read by name with libkernel's `sysctlbyname`. A refused name prints `-1/<errno>`.
- At each `PWFS fd_high`, a `PWFS descriptor_growth` line with the same kinds as `descriptor_kinds`, the estimated threads (pipes divided by seven), and the kernel counters. This shows which kind grows towards the limit and whether `kern.openfiles` grows with the title.
- [build-guest-hw.py](../tools/build-guest-hw.py): `PWGUEST thread_new module=… id=… made=… live=… by=module+offset start=module+offset` for each guest thread, the first 256 of the title. `by` is the first caller outside kernelbase, kernel32, ntdll and the C runtimes, so it tells `xul.dll` from `libgallium_wgl.dll` and `nss3.dll`. `live` counts the guest's threads that have not ended.
- `pw_wine_fs.c` compiles for the console target with the link recipe's flags and `-Wall`, without warnings; `sysctlbyname` resolves to libkernel's export. The kernelbase thread unit compiles for x86_64 and i386 with the builder's recipe and `-Wall`, without warnings.

**Not changed, and why:**
- Fewer descriptors per thread needs a Wine protocol change. The thread keeps its wait pipe's write end only to put back a wake-up that a nested wait (a signal handler during a wait) took. A thread that put it aside in memory instead would stay blocked in its restarted `read`. That needs a server request or a lost-wakeup-safe wait, and a console test.
- Turning off Mesa's threaded context (`GALLIUM_THREAD=0`) would remove only one or two threads, and it would slow every GL program.

**Next console run, with this change built:** OpenGL on. Start SeaMonkey alone, without PES first, wait 30 s, then open YouTube. Send the log. If `kern.openfiles` is near `kern.maxfiles` at the failure, the limit is the console's, and the fix is fewer descriptors. If the counters are refused or far apart, `thread_new` says which module's threads to cut.

## The symptom

On app version 04.11, with the [flexible memory change](SEAMONKEY_FLEXIBLE_MEMORY.md) included, SeaMonkey loads Google completely. YouTube still stops part way.

## What the log shows

The run is `reports/wine-hardware-w303/physical/20261117T105502Z/run-0180.log`, a single SeaMonkey session on YouTube.

**Memory is not the limit this time.** At boot `flexible_free` is 389 MB and `direct_free` 4.69 GB. The log has no `PWVM flexible low` line, no `anon mmap error` and no `PWFAULT`. The `PWVM decommit_host … keeps direct memory` lines show the flexible-memory change working. `seamonkey.exe` exits with status 0.

**The title runs out of file descriptors.** All the wineserver's and every guest's descriptors share one table, because the server runs inside the title. The `PWFS fd_high` lines show the table growing while YouTube plays: 343 when SeaMonkey opens its profile, then 474, 609, 675, 854 and 922. Then:

```text
PWFS open_failed errno=24 n=1 path=.../Profiles/orbis/cache2
PWFS descriptors open=958 highest=957 maxfilesperproc=-1 errno=2 maxfiles=-1 errno=2
00bc:err:winediag:NtCreateFile Too many open files, ulimit -n probably needs to be increased
PWFS open_failed errno=24 n=2 path=.../Profiles/orbis/cache2/doomed
...  (16 logged, then the log stops counting)
```

`errno=24` is `EMFILE`. SeaMonkey's disk cache could no longer open its files. Every other open in the title failed in the same way, sockets and files alike. That is a page that stops loading with no crash.

The failure was not limited to SeaMonkey. Right after it, explorer's 2-second desktop poll could not list the desktop folder:

```text
003c:err:explorer:orbis_poll_desktop_folders PWDESK poll change files=0
0024:err:explorer:orbis_reload_launchers PWDESK reload reason=poll launchers=23->0 files=0
```

The icons came back on the next poll, once descriptors had been freed.

**The thread cap is a separate issue, and it came later.** The 13 `PWGUEST thread_overflow … count=256` lines appear after the `EMFILE` failures. The count is not the number of live threads. The guest's list (`struct ps4_guest`, [build-guest-hw.py](../tools/build-guest-hw.py)) records each thread SeaMonkey creates and never removes ended ones, so it counts every thread started since launch. A thread past 256 still runs. It only isn't ended with the guest at exit, and here the guest exited normally. So this cap does not stall a page.

The 37 `PWGUEST shared_thread … WINMM.dll+1cb50` lines are winmm's `PlaySound` thread (`proc_PlaySound` in the built `winmm.dll`). Each `PlaySound` call starts one, and it ends on its own. They are counted as process-wide threads because W281's rule takes in every winmm thread start, not only the timer thread. They are not the cause.

## Why the table fills

With the in-process wineserver, both ends of each Wine pipe and socket live in the title's one table:

- **A live thread takes six descriptors.** Wine gives each thread a request, a reply and a wait pipe, and the server and the thread each keep one end of every pipe.
- **An open file or socket handle takes two once it is used.** The server keeps its descriptor. The client gets a copy over `SCM_RIGHTS` and keeps it in its descriptor cache.
- **Each mapped image keeps one** on the server side.

Gecko on YouTube runs many threads: media decoding, the socket thread, DNS, image decoding, JavaScript helpers and workers. It also keeps up to 128 disk-cache files open in Gecko 60, and many sockets. Together with explorer and its services, that easily reaches 958.

It is not yet known whether 958 is a fixed kernel limit. The `maxfilesperproc` and `maxfiles` sysctls are not readable from a title (`errno=2`). An earlier VLC run (`reports/wine-hardware-w303/physical/manual-20261109T221515Z/run-0004.log`) reported `EMFILE` at `open=459 highest=642`, which a plain per-process count would not do. So the limit may count something other than the table entries that `fcntl` sees.

## The change

- **Profile** ([seamonkey-user.js](../fixtures/browser/seamonkey-user.js)):
  - `browser.cache.disk.enable` is `false`, so SeaMonkey uses no disk-cache files. Their opens were the ones that failed.
  - `browser.cache.memory.capacity` goes from 32 MB to 64 MB in its place. Since the flexible-memory change, SeaMonkey's malloc heap uses direct memory.
  - `network.http.max-connections` goes from 900 to 64.
- **Log** ([pw_wine_fs.c](../platform/ps4/pw_wine_fs.c)): the report at the first `EMFILE` gains a line that splits the open descriptors by kind and reads the kernel's limit:

  ```text
  PWFS descriptor_kinds files=… folders=… pipes=… sockets=… other=… unknown=… nofile=<soft>/<hard> errno=…
  ```

  `pipes` divided by six is roughly the number of live threads. `nofile` is `RLIMIT_NOFILE` read through libkernel's `getrlimit`. libkernel uses FreeBSD's resource numbers, so the code passes 8; the SDK header's `RLIMIT_NOFILE` (7) is Linux's number.

Neither change hides the failure. If the table still fills, the `PWFS open_failed` and `descriptor_kinds` lines appear.

## What was tested

- `pw_wine_fs.c` compiles with the link recipe's flags (`clang --target=x86_64-pc-freebsd12-elf -D__ORBIS__ -fPIC -O2`, plus `-Wall`) with no warnings. `getrlimit` resolves to libkernel's export, not to the SDK's libc. Nothing was written to `build/` or `out/`.
- **Not tested:** no package was built and nothing ran on the console. The preference names are Gecko 60's. Whether SeaMonkey 2.53.24 applies them was not checked.

## Test on the console (needs a build and the user's approval)

1. Open YouTube in SeaMonkey, play a video for a minute and scroll the page.
2. In the log, look for `PWFS open_failed`, `descriptor_kinds`, `Too many open files` and `PWDESK poll change files=0`.
3. If the table still fills, the `descriptor_kinds` line says where the descriptors go. Mostly `pipes` means live threads, mostly `sockets` means connections, and mostly `files` means file handles.

## Possible next steps, depending on that line

- **`nofile` soft limit below the hard limit:** raise the soft limit at boot. The Wine change in `tools/prepare-wine-boot.py` skips `set_max_limit( RLIMIT_NOFILE )` on the console, so nobody has tried this. Under GoldHEN it may also be possible to raise the hard limit.
- **Mostly pipes:** give each thread fewer descriptors under the in-process server, or make Gecko start fewer threads.
- **Mostly files or sockets:** in the in-process server, stop the client from keeping its own copy of a handle's descriptor. Both sides share one table, so the copy is what doubles the count. Closing the server's descriptor while the client uses it is the race that the copy prevents, so this needs care.
- **Thread list:** prune ended threads from `struct ps4_guest` when it fills. Code that copies the list and uses it outside the lock (`ps4_guest_end`, `ps4_overlay_close_guest`) must not see a closed handle reused for another object.
