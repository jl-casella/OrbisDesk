<a id="w100-exclusión-mutua-para-el-asignador-nativo-del-sdk"></a>


# W100: mutual exclusion for the native allocator of SDK

[English](HARDWARE_W100.md) | [Español](HARDWARE_W100-es.md)

W099 complete overlay closures and allows reopening of applications. After another cycle, Start is blocked with a native invalid access in malloc + 0x5ea. The PC was symbolized using the actual load base confirmed by a log symbol. Evidence: `reports/wine-hardware-w099/physical/20261102T120118Z/analysis.md`.

<a id="cambio"></a>


## Change

`native/native_heap.c` protects malloc, calloc, realloc, free, memalign, __ memalign, aligned_alloc and posix_memalign by --wrap at the link. The mutex is an atomic owner of libkernel identity (scePthreadSelf), with recursive depth for calls between family functions. The waiting uses sceKernelUsleep; does not require pthread of musl or assign memory to obtain the lock. errno are preserved, results, alignment and actual behavior of the assignment. Invalid pointers are not ignored.

The musl linked condition your locks to your internal thread counter, but the port creates threads through libkernel. It is not written on that private counter or other routes of pthread/TLS of musl are enabled. The admin's entries are serialized from the link, also for the native builders who use them. `PWHEAP serialized_sdk_allocator entries=8` records activation and start meters; does not amount to a stress test or hardware validation.

The compilation / link and presence of the eight wrappers were verified. No local matrix is run on the basis of the user's indication. Unix, DLL PE and runtime objects are identical to W099; The closing arrangement of MangoHud and its traces remain. CPU/GPU percentages are still postponed. The disappearance of the physical failure must still be verified; the invalid pointer could also have another origin.

APP_VER 01.99, title ORBW00002. The following APP_VER shall be 02.00, not 01.100.

<a id="construcción-y-prueba"></a>


## Construction and testing

```sh
python3 tools/build-wine-hardware.py
python3 tools/upload-hardware.py --build W100 --host 192.168.68.104
```

The uploader verifies PKG and runtime before removing the previous PKG Wine from the console. It keeps local logs and copies. Close the app before installing.

Repeat two cycles: open vkcube, glxgears and vkspin, close vkcube first, close the others, return to Start and reopen the apps. If it is blocked, leave it for about 15 seconds and warn; If there is crash, indicate the code. When you finish, press "I've already tried it" to download:

```sh
python3 tools/fetch-hardware.py --build W100 --host 192.168.68.104
```

<a id="entrega-completada"></a>


## Delivery completed

After a FTP lock and the reactivation of the server by the user in. 104, the delivery ended with a verified return reading: `/data/pkg/orbis-win-W100-e388c48da7a5.pkg`, SHA- 256 `e388c48da7a5b8972b7d1d7f472d8c4d5451238ebe1b47763f1f2d121ef056b1`. Report: `reports/wine-hardware-w100/transfers/20261102T122627Z.json`. Runtime 548 files, 546 present and two uploaded records; is identical to the runtime generated for W099. The PKG W099 was deleted with a response FTP 250 and there were no permissions or cleaning errors. Locally preserved logos and packages. W100 is still pending physical execution.

Later result: tested and with CE-34878-0 when closing programs. PWHEAP is active and the three guests record 0 closure, but the log is cut on return to Start, without exception captured. The heap failure and the closure of apps are not considered to be solved. It is continued with [W101](HARDWARE_W101.md), comparison without loading MangoHud; see `reports/wine-hardware-w100/physical/20261102T122841Z/analysis.md`.
