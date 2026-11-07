<a id="w203-el-escritorio-se-congela-con-pale-moon-como-invitado-borrador"></a>


# W203: the desktop is frozen with Pale Moon as guest (draft)

[English](HARDWARE_W203-palemoon-invitado-borrador.md) | [Español](HARDWARE_W203-palemoon-invitado-borrador-es.md)

Eraser of the browser side session, to join `HARDWARE_W203.md`. Follow the two diagnostic drafts (`HARDWARE_Wxxx-palemoon-invitado-borrador.md`, `…-2-borrador.md`). None of this was tested on the console.

<a id="qué-mostró-w201"></a>


## What did he show W201

Reporte: `reports/wine-hardware-w201/physical/20261104T125351Z/run-0001.log`.

- **The server's vigil started** (`PWSERVER watch rc=0`, line 422), and never recorded a step of more than 5 s.
- **When it froze:** This time when you start Pale Moon, after loading `freebl3.dll` and `nssckbi.dll`.
- **The scout overturn:**
  - registered `PWDUMP begin … loader_owner=0000` (No one had the loader lock.);
  - then recorded `PWDUMP step=thread_list`;
  - He didn't come back from that first call to the server.
- **What's still going:** only the composer and RADV.

**Conclusion:** the server was not stuck in an order; I didn't read the new orders.

<a id="causa-deducida-del-código"></a>


## Case (deduced from code)

- **How does the server expect:** the main loop of wineserver (`server/fd.c`, `main_loop` wait with `poll( pollfd, nb_users, timeout )` above all its table of descriptors. `epoll` is not available on the console, and `poll` is `pw_wine_poll` (`platform/ps4/pw_wine_posix.h`). The comments of W034 and W176 in `pw_wine_net.c` already show that the server passes through.
- **The limit:** up W201, `pw_wine_poll` rejected more than 256 descriptors with `EINVAL`.
- **What counts `nb_users`:** the places on the server table:
  - one by thread of Windows (your order pipe);
  - the sockets, pipes and files that the server expects.
- **What about Pale Moon as guest:** adds dozens of threads to the scanning process, and more sockets when sailing. As you go from 256:
  - every `poll()` fails;
  - `main_loop` does not look at the error and call again, so no longer reads any order;
  - each thread stops at its next call to the server;
  - server timers continue to run, so no hard steps 5 s (W201 did not record any `PWSERVER stuck`).
- **Why don't you just pass:** as a separate title, Pale Moon has its own board, smaller.

Fits with:
- the lack of critical section notice;
- the composer, who continues to walk because he does not use the server;
- the time of the hanging: when starting or sailing, according to how many threads and sockets there are.

What is not measured is the size of the table at the time of the hanging. This change records it.

<a id="cambio"></a>


## Change

- **`platform/ps4/pw_wine_net.c`:** `pw_wine_poll` accepts until 4096 descriptors. After 256, events go in memory of the heap instead of the stack.
  - Each new maximum past 256 is recorded once every 64 (`PWNET poll_count n=…`).
  - More than 4096 is still `EINVAL`, with a warning (`PWNET poll_count_unsupported`).
- **`tools/build-wine-delete-server.py` (`server/fd.c`):** only trace; The loop doesn't change.
  - When you enter the loop of `poll`, `PWSERVER poll_loop epoll_fd=…` shows what you expect to use.
  - A failed `poll()` is recorded (`PWSERVER poll_failed n=… errno=… users=… active=…`): the first 5 and then one each 100 000.

<a id="construcción"></a>


## Build

1. `python3 tools/build-wine-delete-server.py`.
2. `tools/link-wine-boot.py`, which compiles `pw_wine_net.c`.
3. `tools/build-wine-hardware.py`.

<a id="prueba-física"></a>


## Physical test

1. When you start, the log has to show `PWSERVER poll_loop epoll_fd=-1`.
2. Open `palemooncopy.exe` (as a guest) and navigate to two or three sites. Wait 2 minutes.
3. **What to look for in the log:**
   - `PWNET poll_count n=…`: confirms that the table has passed from 256;
   - no line `PWSERVER poll_failed`;
   - the rate of explorer (`heartbeat_age_ms`) in ~ 230.
4. If it freezes the same, the lines `PWSERVER` and `PWDUMP` of the previous rounds remain in the build.

<a id="no-verificado"></a>


## Not verified

- Nothing was tested on the console.
- The changes were compiled only with `-fsyntax-only`, on copies: `pw_wine_net.c` with the options `link-wine-boot.py` and `server/fd.c` with the server recipe.
- It is not known whether `sceNetEpoll` accepts more than 256 descriptors in the same wait. If you do not accept them, `pw_wine_poll` returns the error of libSceNet, and `PWSERVER poll_failed` shows it with your `errno`.
- A table of thousands of descriptors slows every `poll()`: creates and destroys an epoll of libSceNet per call, and reviews duplicates in quadratic time. He didn't measure himself.
