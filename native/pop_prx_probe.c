/* PoP Phase D.1a / P016: can the separate process host OpenOrbis code the way the title does?
 *
 * The resident loader (elfldr) only copies an ELF image and applies R_X86_64_RELATIVE: no imports, no TLS, no
 * constructors. Wine's unix side needs all three. GoldHEN plugins solve the same problem as fake-signed PRX
 * modules loaded by the system's dynamic linker (sceKernelLoadStartModule), which resolves imports, allocates
 * TLS and runs initialisers. This probe is such a PRX, built with the same OpenOrbis toolchain and static libc
 * as the title's Wine image; the payload-SDK child dlopen()s it and calls pop_prx_probe(log_fd).
 *
 * Each check is real (no stubs): a constructor flag, a __thread variable seen separately by two threads, a
 * 64 MiB heap block, a libkernel import, a file write under /data, and where a low mmap hint lands. */
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

extern uint64_t sceKernelGetProcessTime(void);   /* libkernel import, resolved by the system linker */

/* volatile + a runtime value, so the compiler cannot fold the constructor into a static initialiser */
static volatile int constructor_ran;
__attribute__((constructor)) static void pop_prx_ctor(void){ constructor_ran = (int)getpid() > 0 ? 42 : 41; }

static __thread int tls_value;
static int log_fd = -1;

static void plog(const char *fmt, ...){
    char line[512];
    va_list ap; va_start(ap, fmt);
    int n = vsnprintf(line, sizeof(line) - 1, fmt, ap);
    va_end(ap);
    if(n < 0) return;
    if(n > (int)sizeof(line) - 2) n = sizeof(line) - 2;
    line[n++] = '\n';
    if(log_fd >= 0) write(log_fd, line, (size_t)n);
}

static void *tls_thread(void *arg){
    int *seen = arg;
    seen[0] = tls_value;      /* must be 0: a fresh thread gets its own copy */
    tls_value = 7;
    seen[1] = tls_value;
    return NULL;
}

__attribute__((visibility("default"))) int pop_prx_probe(int fd);
__attribute__((visibility("default"))) int pop_prx_probe(int fd){
    /* its own append-only log: sharing the child's FILE descriptor lost these lines to the child's cached
     * stdio offset on the first hardware run (2026-11-12) */
    (void)fd;
    /* Hardware, 2026-11-12: this first open created nothing while the later identical open of prx-probe.txt
     * worked. Record the first attempt's result and retry, to tell a first-call import binding problem from
     * a path problem. */
    int first_fd = open("/data/orbisdesk/process-p014/prx-probe.jsonl", O_WRONLY | O_CREAT | O_TRUNC, 0666);
    int first_errno = first_fd < 0 ? errno : 0;
    log_fd = first_fd >= 0 ? first_fd : open("/data/orbisdesk/process-p014/prx-probe.jsonl", O_WRONLY | O_CREAT | O_TRUNC, 0666);
    int second_errno = log_fd < 0 ? errno : 0;
    if(log_fd < 0) log_fd = open("/data/orbisdesk/process-p014/prx-probe-log.txt", O_WRONLY | O_CREAT | O_TRUNC, 0666);
    plog("{\"build\":\"P016\",\"event\":\"log_open\",\"first_fd\":%d,\"first_errno\":%d,\"second_errno\":%d}", first_fd, first_errno, second_errno);
    int ok = 1;
    plog("{\"build\":\"P016\",\"event\":\"prx_entered\",\"constructor\":%d,\"pid\":%d}", constructor_ran, (int)getpid());
    ok &= constructor_ran == 42;

    tls_value = 5;
    int seen[2] = {-1, -1};
    pthread_t t;
    int prc = pthread_create(&t, NULL, tls_thread, seen);
    if(!prc) pthread_join(t, NULL);
    int tls_ok = !prc && seen[0] == 0 && seen[1] == 7 && tls_value == 5;
    plog("{\"build\":\"P016\",\"event\":\"tls\",\"pthread_rc\":%d,\"thread_initial\":%d,\"thread_after\":%d,\"main\":%d,\"ok\":%d}",
         prc, seen[0], seen[1], tls_value, tls_ok);
    ok &= tls_ok;

    size_t big = 64u << 20;
    unsigned char *volatile heap = malloc(big);   /* volatile: keep the allocation real */
    int heap_ok = heap != NULL;
    if(heap){ memset(heap, 0xa5, big); heap[big / 2] = 0x5a; heap_ok = heap[big - 1] == 0xa5 && heap[big / 2] == 0x5a; free(heap); }
    plog("{\"build\":\"P016\",\"event\":\"heap\",\"bytes\":%zu,\"ok\":%d}", big, heap_ok);
    ok &= heap_ok;

    uint64_t t0 = sceKernelGetProcessTime();
    struct timespec ts; int clock_rc = clock_gettime(CLOCK_MONOTONIC, &ts);
    plog("{\"build\":\"P016\",\"event\":\"imports\",\"process_time_us\":%llu,\"clock_rc\":%d}", (unsigned long long)t0, clock_rc);
    ok &= t0 != 0 && clock_rc == 0;

    int f = open("/data/orbisdesk/process-p014/prx-probe.txt", O_WRONLY | O_CREAT | O_TRUNC, 0666);
    int file_errno = f < 0 ? errno : 0;
    if(f >= 0){ static const char msg[] = "P016 prx wrote this\n"; if(write(f, msg, sizeof(msg) - 1) != (ssize_t)sizeof(msg) - 1) file_errno = errno; close(f); }
    plog("{\"build\":\"P016\",\"event\":\"file\",\"errno\":%d}", file_errno);
    ok &= file_errno == 0;

    void *low = mmap((void *)0x400000, 1u << 20, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    plog("{\"build\":\"P016\",\"event\":\"low_hint\",\"addr\":\"%p\",\"errno\":%d}", low, low == MAP_FAILED ? errno : 0);
    if(low != MAP_FAILED) munmap(low, 1u << 20);

    plog("{\"build\":\"P016\",\"event\":\"prx_done\",\"ok\":%d}", ok);
    if(log_fd >= 0) close(log_fd);
    return ok;
}
