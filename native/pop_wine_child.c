/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* PoP Phase D.1b / P017: Wine itself in the separate process.
 *
 * This file is the entry of a fake-signed PRX that contains the same Wine unix side as the title (the
 * ntdll/win32u/unixlib objects of tools/link-wine-boot.py, OpenOrbis static libc). The payload-SDK child
 * (native/process_p014_child.c) loads it with the system linker (Phase D.1a showed that resolves imports, TLS
 * and initialisers there) and calls pop_wine_child_run() with a socket already connected to the title's
 * wineserver bridge. Upstream Wine's WINESERVERSOCKET path (dlls/ntdll/unix/server.c server_init_process)
 * then uses that socket instead of starting or finding a server, so this process becomes a genuine client
 * process of the title's server: one object namespace, one registry, one window station.
 *
 * Mirrors native/wine_boot.c's prepared-prefix path, except that nothing here prepares the prefix: the title
 * already did, and it owns it. __wine_main does not return; exit() is wrapped to record the exit status. */
#include "pw_wine_platform.h"
#include "pw_wine_fs.h"
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdarg.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

extern void __wine_main(int, char **);
/* OpenOrbis libc (musl): what crt1's __libc_start_main does before main -- environ, the auxiliary vector,
 * hwcap, program name. A PRX never runs it, so libc.auxv stayed NULL and getauxval() faulted on hardware
 * (2026-11-12, klog: SIGSEGV reading 0 in __getauxval right after the main image load). This libc's
 * __init_libc sets no TLS (the system linker owns TLS), so calling it here is safe. */
extern void __init_libc(char **envp, char *pn);
static size_t pop_initial_block[] = {
    0,              /* end of an empty environment (setenv builds the real one) */
    6, 16384,       /* AT_PAGESZ: the console's page */
    0, 0            /* AT_NULL */
};
extern void __real_exit(int) __attribute__((noreturn));
extern int __real_sceKernelDebugOutText(int, const char *);

static int child_log = -1;

static void clog(const char *fmt, ...){
    char line[600];
    va_list ap; va_start(ap, fmt);
    int n = vsnprintf(line, sizeof(line) - 1, fmt, ap);
    va_end(ap);
    if(n < 0 || child_log < 0) return;
    if(n > (int)sizeof(line) - 2) n = sizeof(line) - 2;
    line[n++] = '\n';
    write(child_log, line, (size_t)n);
}

/* the D.2 display sink (native/pop_child_sink.c) logs through here */
void pop_wine_child_log(const char *line);
void pop_wine_child_log(const char *line){ clog("%s", line); }

/* Wine leaves through exit(); the status is the Windows process's exit code */
void __wrap_exit(int status) __attribute__((noreturn));
void __wrap_exit(int status){
    clog("{\"build\":\"P017\",\"event\":\"wine_exit\",\"status\":%d}", status);
    __real_exit(status);
}
/* An assertion inside Wine (hardware 2026-11-12: "exports" in load_ntdll_functions, ntdll.dll mapped at
 * 0x7fff30000): record what the mapped module's headers actually hold before aborting. The address comes
 * from the PWBOOT ntdll_mapped marker of that run; a read is attempted only after msync says it is mapped. */
#include <sys/mman.h>
void __wrap___assert_fail(const char *expr, const char *file, int line, const char *func) __attribute__((noreturn));
void __wrap___assert_fail(const char *expr, const char *file, int line, const char *func){
    clog("{\"build\":\"P017\",\"event\":\"wine_assert\",\"expr\":\"%s\",\"func\":\"%s\",\"line\":%d}", expr, func ? func : "", line);
    const unsigned char *m = (const unsigned char *)0x7fff30000ul;
    if(msync((void *)m, 16384, MS_ASYNC) == 0){
        unsigned lfanew = *(const unsigned *)(m + 0x3c);
        const unsigned char *nt = lfanew < 0x1000 ? m + lfanew : NULL;
        clog("{\"build\":\"P017\",\"event\":\"ntdll_header\",\"mz\":\"%02x%02x\",\"lfanew\":%u,\"pe\":\"%02x%02x\",\"magic\":\"%04x\",\"rva_count\":%u,\"export_rva\":%u,\"export_size\":%u}",
             m[0], m[1], lfanew, nt ? nt[0] : 0, nt ? nt[1] : 0, nt ? *(const unsigned short *)(nt + 24) : 0,
             nt ? *(const unsigned *)(nt + 24 + 108) : 0, nt ? *(const unsigned *)(nt + 24 + 112) : 0, nt ? *(const unsigned *)(nt + 24 + 116) : 0);
        char hex[3 * 64 + 1]; for(int i = 0; i < 64; i++) snprintf(hex + 3 * i, 4, "%02x ", m[i]);
        clog("{\"build\":\"P017\",\"event\":\"ntdll_first_bytes\",\"hex\":\"%s\"}", hex);
    }
    else clog("{\"build\":\"P017\",\"event\":\"ntdll_header_unmapped\",\"errno\":%d}", errno);
    /* Not abort(): Wine handles SIGABRT, and on hardware the asserting child processes were left hung (no
     * exit, no crash report: klog, 2026-11-12). End this process outright so it never lingers. */
    if(child_log >= 0) fsync(child_log);
    _exit(134);
}
/* Trace of every memory call touching ntdll.dll's view (0x7fff30000, size 0xbc000, from the PWBOOT
 * ntdll_mapped marker), with what the first two bytes of the view hold afterwards: shows which call puts the
 * "MZ" header there and which one takes it away. At most 200 lines. */
#define NTDLL_VIEW 0x7fff30000ul
#define NTDLL_VIEW_END (0x7fff30000ul + 0xbc000ul)
static unsigned trace_lines;
static int touches_ntdll(const void *addr, size_t len){
    uintptr_t a = (uintptr_t)addr; return a < NTDLL_VIEW_END && a + len > NTDLL_VIEW;
}
static void trace_call(const char *what, const void *addr, size_t len, long arg1, long arg2, long result, int err){
    if(trace_lines >= 400) return;
    trace_lines++;
    char head[8] = "--";
    if(msync((void *)NTDLL_VIEW, 16384, MS_ASYNC) == 0){
        const unsigned char *m = (const unsigned char *)NTDLL_VIEW; snprintf(head, sizeof(head), "%02x%02x", m[0], m[1]);
    }
    clog("{\"build\":\"P017\",\"event\":\"ntdll_trace\",\"call\":\"%s\",\"addr\":\"%p\",\"len\":\"%zx\",\"a1\":%ld,\"a2\":%ld,\"result\":%ld,\"errno\":%d,\"head\":\"%s\"}",
         what, addr, len, arg1, arg2, result, err, head);
}
#include <sys/stat.h>
extern int __real_fstat(int, struct stat *);
int __wrap_fstat(int fd, struct stat *st);
int __wrap_fstat(int fd, struct stat *st){
    int r = __real_fstat(fd, st), e = r ? errno : 0;
    trace_call("fstat", NULL, 0, fd, r ? -1 : (long)st->st_size, r, e);
    if(r) errno = e;
    return r;
}
extern int __real_mprotect(void *, size_t, int);
int __wrap_mprotect(void *addr, size_t len, int prot);
int __wrap_mprotect(void *addr, size_t len, int prot){
    int r = __real_mprotect(addr, len, prot), e = r ? errno : 0;
    if(touches_ntdll(addr, len)) trace_call("mprotect", addr, len, prot, 0, r, e);
    if(r) errno = e;
    return r;
}
extern int __real_munmap(void *, size_t);
int __wrap_munmap(void *addr, size_t len);
int __wrap_munmap(void *addr, size_t len){
    int r = __real_munmap(addr, len), e = r ? errno : 0;
    if(touches_ntdll(addr, len)) trace_call("munmap", addr, len, 0, 0, r, e);
    if(r) errno = e;
    return r;
}

/* Private file mappings (hardware 2026-11-12): in this process ntdll.dll's header page, mapped with mmap
 * from the file at offset 0, read back as zeros although mmap succeeded, while the same call works in the
 * title. Wine already falls back to an anonymous mapping filled with pread() when mmap of a file fails
 * (dlls/ntdll/unix/virtual.c map_file_into_view); for MAP_PRIVATE that is the same memory contents, so
 * every private file mapping here takes that path. Shared mappings keep the real mmap. */
extern void *__real_mmap(void *, size_t, int, int, int, off_t);
static unsigned long private_file_maps;
/* KUSER_SHARED_DATA (hardware 2026-11-12, D.1): Wine maps the server's USD section read-only and shared at
 * 0x7ffe0000, and on 16 KiB host pages its syscall dispatcher slot (0x7ffe1000) shares that host page, so
 * ntdll writes the slot through the shared view (signal_x86_64.c "sneak in a syscall dispatcher pointer").
 * With a second process on the same server that write replaced the title's dispatcher with this process's:
 * the desktop then called this process's __wine_syscall_dispatcher / call_user_mode_callback addresses and
 * looped on access violations. Here the host page is private: a copy of the section, refreshed from a shared
 * view every 15 ms (the server keeps the time fields current), USD's 4 KiB only, so the slot stays this
 * process's own. */
#define USD_ADDR ((void *)0x7ffe0000)
static volatile const unsigned char *usd_live;
static void *usd_refresh(void *arg){
    (void)arg;
    for(;;){
        if(__real_mprotect(USD_ADDR, 16384, PROT_READ | PROT_WRITE) == 0)
            memcpy(USD_ADDR, (const void *)usd_live, 0x1000);
        usleep(15000);
    }
    return NULL;
}
static void *map_private_usd(int fd, size_t len){
    void *live = __real_mmap(NULL, 16384, PROT_READ, MAP_SHARED, fd, 0);
    if(live == MAP_FAILED){ clog("{\"build\":\"P017\",\"event\":\"usd_live_failed\",\"errno\":%d}", errno); return MAP_FAILED; }
    void *own = __real_mmap(USD_ADDR, 16384, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON | MAP_FIXED, -1, 0);
    if(own != USD_ADDR){ clog("{\"build\":\"P017\",\"event\":\"usd_private_failed\",\"errno\":%d}", errno); return MAP_FAILED; }
    memcpy(own, live, 16384);
    usd_live = live;
    pthread_t th; int rc = pthread_create(&th, NULL, usd_refresh, NULL);
    clog("{\"build\":\"P017\",\"event\":\"usd_private\",\"live\":\"%p\",\"len\":\"%zx\",\"refresh_thread\":%d}", live, len, rc);
    return own;
}

static void *mmap_inner(void *addr, size_t len, int prot, int flags, int fd, off_t offset){
    if(addr == USD_ADDR && fd >= 0 && (flags & MAP_SHARED) && (flags & MAP_FIXED)) return map_private_usd(fd, len);
    if(fd < 0 || (flags & MAP_ANON) || !(flags & MAP_PRIVATE)) return __real_mmap(addr, len, prot, flags, fd, offset);
    void *p = __real_mmap(addr, len, PROT_READ | PROT_WRITE, flags | MAP_ANON, -1, 0);
    if(p == MAP_FAILED) return p;
    size_t done = 0;
    while(done < len){
        ssize_t r = pread(fd, (char *)p + done, len - done, offset + (off_t)done);
        if(r < 0 && errno == EINTR) continue;
        if(r <= 0) break;               /* past the end of the file: the rest stays zero, as mmap's tail */
        done += (size_t)r;
    }
    if(prot != (PROT_READ | PROT_WRITE) && mprotect(p, len, prot))
        clog("{\"build\":\"P017\",\"event\":\"private_map_mprotect\",\"prot\":%d,\"errno\":%d}", prot, errno);
    if(!private_file_maps++) clog("{\"build\":\"P017\",\"event\":\"private_file_map_first\",\"len\":%zu,\"read\":%zu}", len, done);
    return p;
}
void *__wrap_mmap(void *addr, size_t len, int prot, int flags, int fd, off_t offset);
void *__wrap_mmap(void *addr, size_t len, int prot, int flags, int fd, off_t offset){
    void *p = mmap_inner(addr, len, prot, flags, fd, offset); int e = p == MAP_FAILED ? errno : 0;
    if(fd >= 0 || touches_ntdll(addr, len) || (p != MAP_FAILED && touches_ntdll(p, len)))
        trace_call(fd >= 0 ? "mmap_file" : "mmap_anon", addr, len, prot, flags, p == MAP_FAILED ? -1 : (long)(uintptr_t)p, e);
    if(p == MAP_FAILED) errno = e;
    return p;
}

/* Hardware 2026-11-12: a file mmap works here (file_mmap_check), yet ntdll.dll's header stayed zero. Wine
 * reads a header smaller than a page with pread() straight into the image view (virtual.c map_pe_header)
 * and does not check the result; if the view is not writable in this process the read fails and leaves
 * zeros. Record such a failure, make the destination pages writable (what Wine expects there; it sets the
 * final page protections afterwards) and read again. */
extern ssize_t __real_pread(int, void *, size_t, off_t);
static unsigned long pread_retries;
ssize_t __wrap_pread(int fd, void *buf, size_t len, off_t offset);
ssize_t __wrap_pread(int fd, void *buf, size_t len, off_t offset){
    ssize_t r = __real_pread(fd, buf, len, offset);
    trace_call("pread", buf, len, (long)offset, fd, (long)r, r < 0 ? errno : 0);
    if(r >= 0 || errno != EFAULT || !len) return r;
    int first_errno = errno;
    uintptr_t page = 16384, start = (uintptr_t)buf & ~(page - 1), end = ((uintptr_t)buf + len + page - 1) & ~(page - 1);
    int mp = mprotect((void *)start, end - start, PROT_READ | PROT_WRITE), mp_errno = mp ? errno : 0;
    r = __real_pread(fd, buf, len, offset);
    if(pread_retries++ < 8)
        clog("{\"build\":\"P017\",\"event\":\"pread_retry\",\"buf\":\"%p\",\"len\":%zu,\"first_errno\":%d,\"mprotect\":%d,\"mprotect_errno\":%d,\"result\":%zd}",
             buf, len, first_errno, mp, mp_errno, r);
    return r;
}

extern int __real_mprotect(void *, size_t, int);
/* Hardware 2026-11-12 (traced): ntdll.dll's header was read into its view correctly and was zero again right
 * after, with no mmap/mprotect/munmap on it. Wine's console commit step (pw_commit_backing in ntdll's
 * virtual.c, W172/W224) maps fresh flexible memory, MAP_FIXED, over any page the kernel does not report as
 * committed; in the title (an application) written pages are reported committed, in this borrowed system
 * process ordinary memory apparently is not, so a filled page was replaced by an empty one. Here a page
 * that already lies in an accessible region (prot != 0) keeps its memory and only takes the protection;
 * a pure reservation (prot 0) still gets flexible memory as before. */
struct pop_vq { void *start, *end; long offset; int prot, type; unsigned char flags; char name[32]; };
extern int sceKernelVirtualQuery(const void *addr, int flags, void *info, size_t size);
extern int __real_sceKernelMapFlexibleMemory(void **addr, size_t len, int prot, int flags);
static unsigned long flex_kept, flex_mapped;
int __wrap_sceKernelMapFlexibleMemory(void **addr, size_t len, int prot, int flags);
int __wrap_sceKernelMapFlexibleMemory(void **addr, size_t len, int prot, int flags){
    if((flags & 0x10) && addr && *addr){
        struct pop_vq info; memset(&info, 0, sizeof(info));
        int q = sceKernelVirtualQuery(*addr, 0, &info, sizeof(info));
        int inside = !q && (char *)info.start <= (char *)*addr && (char *)*addr < (char *)info.end;
        if(inside && (info.prot & (PROT_READ | PROT_WRITE | PROT_EXEC))){
            int mp = __real_mprotect(*addr, len, prot);
            if(flex_kept++ < 6)
                clog("{\"build\":\"P017\",\"event\":\"flex_kept\",\"addr\":\"%p\",\"len\":\"%zx\",\"region\":\"%p-%p\",\"region_prot\":%d,\"type\":%d,\"flags\":%d,\"prot\":%d,\"mprotect\":%d}",
                     *addr, len, info.start, info.end, info.prot, info.type, info.flags, prot, mp);
            return 0;
        }
        if(flex_mapped++ < 6)
            clog("{\"build\":\"P017\",\"event\":\"flex_mapped\",\"addr\":\"%p\",\"len\":\"%zx\",\"query\":%d,\"inside\":%d,\"region_prot\":%d,\"flags\":%d}",
                 *addr, len, q, inside, info.prot, info.flags);
    }
    return __real_sceKernelMapFlexibleMemory(addr, len, prot, flags);
}

/* The same commit step takes direct memory for runs of 1 MiB or more (pw_direct_map, MAP_FIXED); the same
 * rule: a range whose every page already lies in an accessible region keeps its memory. */
extern int __real_sceKernelMapDirectMemory(void **addr, size_t len, int prot, int flags, long offset, size_t align);
static unsigned long direct_kept;
static int range_accessible(char *start, size_t len){
    for(char *pg = start; pg < start + len; pg += 16384){
        struct pop_vq info; memset(&info, 0, sizeof(info));
        if(sceKernelVirtualQuery(pg, 0, &info, sizeof(info)) || (char *)info.start > pg || pg >= (char *)info.end ||
           !(info.prot & (PROT_READ | PROT_WRITE | PROT_EXEC))) return 0;
    }
    return 1;
}
int __wrap_sceKernelMapDirectMemory(void **addr, size_t len, int prot, int flags, long offset, size_t align);
int __wrap_sceKernelMapDirectMemory(void **addr, size_t len, int prot, int flags, long offset, size_t align){
    if((flags & 0x10) && addr && *addr && range_accessible(*addr, len)){
        int mp = __real_mprotect(*addr, len, prot);
        if(direct_kept++ < 6)
            clog("{\"build\":\"P017\",\"event\":\"direct_kept\",\"addr\":\"%p\",\"len\":\"%zx\",\"prot\":%d,\"mprotect\":%d}", *addr, len, prot, mp);
        return 0;
    }
    return __real_sceKernelMapDirectMemory(addr, len, prot, flags, offset, align);
}

extern int __real_munmap(void *, size_t);
/* The fixed PE base (D.1, hardware 2026-11-12: the program was relocated to 0x110000). In this process
 * 0x400000 holds the eboot of the system process the loader borrows (klog: text 0x400000-0x474000, data
 * 0x478000-0x588000). Its code no longer runs: the main thread is this process's, and Wine never returns
 * to it. Its regions below 16 MiB are unmapped before Wine starts, so Wine's own reservation takes the
 * range and a program linked at 0x400000 loads there, as Prince of Persia's launcher and POP.exe need.
 * (P013 showed the process keeps running with this range overwritten.) Logged region by region. */
static void free_low_image_range(void){
    const uintptr_t lo = 0x400000, hi = 0x1000000;
    struct { uintptr_t start, end; int prot; char name[33]; } found[8]; int n = 0;
    for(uintptr_t at = lo; at < hi && n < 8; ){
        struct pop_vq info; memset(&info, 0, sizeof(info));
        if(sceKernelVirtualQuery((void *)at, 0, &info, sizeof(info))) break;
        uintptr_t s = (uintptr_t)info.start, e = (uintptr_t)info.end;
        if(s >= hi || e <= at) break;
        found[n].start = s < lo ? lo : s; found[n].end = e > hi ? hi : e; found[n].prot = info.prot;
        memcpy(found[n].name, info.name, 32); found[n].name[32] = 0; n++;
        at = e;
    }
    for(int i = 0; i < n; i++){
        int r = __real_munmap((void *)found[i].start, found[i].end - found[i].start), e = r ? errno : 0;
        clog("{\"build\":\"P017\",\"event\":\"low_range_unmap\",\"start\":\"%lx\",\"end\":\"%lx\",\"prot\":%d,\"name\":\"%s\",\"rc\":%d,\"errno\":%d}",
             (unsigned long)found[i].start, (unsigned long)found[i].end, found[i].prot, found[i].name, r, e);
    }
    if(!n) clog("{\"build\":\"P017\",\"event\":\"low_range_empty\"}");
}

/* Waits (hardware 2026-11-12): after sessions where Wine ran in this process, the title then aborted at boot
 * inside sceNetEpollControl in its wineserver's first poll (platform/ps4/pw_wine_net.c:106, crash_stack),
 * repeatably until the console restarted. platform/ps4's poll goes through a sceNetEpoll created and
 * destroyed per call; this borrowed system process does not need that path, so here poll() is the kernel's
 * own, and the network adapter is used only if the kernel refuses it. Suspected, not proven: the per-call
 * epolls of this process leave libnet state that breaks the next title. */
#include <poll.h>
extern int __real_pw_wine_poll(struct pollfd *, nfds_t, int);
static int kernel_poll_state;   /* 0 untried, 1 works, -1 refused */
int __wrap_pw_wine_poll(struct pollfd *fds, nfds_t count, int timeout);
int __wrap_pw_wine_poll(struct pollfd *fds, nfds_t count, int timeout){
    if(kernel_poll_state >= 0){
        int r = poll(fds, count, timeout);
        if(r >= 0 || errno == EINTR){
            if(!kernel_poll_state){ kernel_poll_state = 1; clog("{\"build\":\"P017\",\"event\":\"kernel_poll\",\"first_result\":%d,\"count\":%u}", r, (unsigned)count); }
            return r;
        }
        int e = errno;
        if(e == ENOSYS || e == EOPNOTSUPP || e == EPERM){
            kernel_poll_state = -1;
            clog("{\"build\":\"P017\",\"event\":\"kernel_poll_refused\",\"errno\":%d}", e);
        }
        else { errno = e; return r; }
    }
    return __real_pw_wine_poll(fds, count, timeout);
}

/* The title's desktop must outlive this process (hardware 2026-11-12, D.2: when the separate program exited,
 * the title's explorer exited too). The wineserver counts desktop users per thread and, when only the
 * desktop window owner's threads remain, posts WM_CLOSE to it after one second (server/winstation.c
 * remove_desktop_user) -- Wine's "close the virtual desktop when the last program quits". In the title every
 * program is a thread of one process, so that never happened before a second process used the desktop.
 * Wine's system processes (its services) are not desktop users: this process becomes one right after it
 * joins the server and before any thread attaches to a desktop (that happens at the first win32u use). */
extern int NtSetInformationProcess(void *handle, int info_class, void *info, unsigned int size);
static void job_report_started(void);   /* Phase D.3, below */
extern void __real_virtual_map_user_shared_data(void);
void __wrap_virtual_map_user_shared_data(void);
void __wrap_virtual_map_user_shared_data(void){
    __real_virtual_map_user_shared_data();
    void *shutdown_event = NULL;
    int status = NtSetInformationProcess((void *)~(uintptr_t)0, 1000 /* ProcessWineMakeProcessSystem */, &shutdown_event, sizeof(void *));
    clog("{\"build\":\"P018\",\"event\":\"system_process\",\"status\":\"0x%08x\",\"event_handle\":\"%p\"}", (unsigned)status, shutdown_event);
    job_report_started();
}

/* Which page protections this process may use (Wine reserves image views read/write/execute) */
static void protection_check(void){
    void *rwx = __real_mmap(NULL, 16384, PROT_READ | PROT_WRITE | PROT_EXEC, MAP_PRIVATE | MAP_ANON, -1, 0);
    int rwx_errno = rwx == MAP_FAILED ? errno : 0;
    void *rw = __real_mmap(NULL, 16384, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    int rx = rw == MAP_FAILED ? -2 : mprotect(rw, 16384, PROT_READ | PROT_EXEC), rx_errno = rx == -1 ? errno : 0;
    int rwx2 = rw == MAP_FAILED ? -2 : mprotect(rw, 16384, PROT_READ | PROT_WRITE | PROT_EXEC), rwx2_errno = rwx2 == -1 ? errno : 0;
    int writable = 0;
    if(rwx != MAP_FAILED){ volatile unsigned char *b = rwx; b[0] = 0x5a; writable = b[0] == 0x5a; }
    clog("{\"build\":\"P017\",\"event\":\"protection_check\",\"anon_rwx\":\"%p\",\"anon_rwx_errno\":%d,\"rwx_writable\":%d,"
         "\"mprotect_rx\":%d,\"mprotect_rx_errno\":%d,\"mprotect_rwx\":%d,\"mprotect_rwx_errno\":%d}",
         rwx, rwx_errno, writable, rx, rx_errno, rwx2, rwx2_errno);
    if(rwx != MAP_FAILED) munmap(rwx, 16384);
    if(rw != MAP_FAILED) munmap(rw, 16384);
}

/* What a file mapping gives in this process, logged once at entry with ntdll.dll: a plain mapping, and a
 * MAP_FIXED one over a reserved range (Wine's pattern). Uses the real mmap. */
static void file_mmap_check(void){
    int fd = open("/data/wine/lib/wine/x86_64-windows/ntdll.dll", O_RDONLY);
    if(fd < 0){ clog("{\"build\":\"P017\",\"event\":\"file_mmap_check\",\"open_errno\":%d}", errno); return; }
    unsigned char *plain = __real_mmap(NULL, 16384, PROT_READ, MAP_PRIVATE, fd, 0);
    int plain_errno = plain == MAP_FAILED ? errno : 0;
    unsigned char *res = __real_mmap(NULL, 65536, PROT_NONE, MAP_PRIVATE | MAP_ANON, -1, 0);
    unsigned char *fixed = res == MAP_FAILED ? MAP_FAILED : __real_mmap(res, 16384, PROT_READ, MAP_PRIVATE | MAP_FIXED, fd, 0);
    int fixed_errno = fixed == MAP_FAILED ? errno : 0;
    clog("{\"build\":\"P017\",\"event\":\"file_mmap_check\",\"plain\":\"%p\",\"plain_errno\":%d,\"plain_mz\":\"%02x%02x\","
         "\"reserved\":\"%p\",\"fixed\":\"%p\",\"fixed_errno\":%d,\"fixed_mz\":\"%02x%02x\",\"reserved_mz\":\"%02x%02x\"}",
         plain, plain_errno, plain != MAP_FAILED ? plain[0] : 0, plain != MAP_FAILED ? plain[1] : 0,
         res, fixed, fixed_errno, fixed != MAP_FAILED ? fixed[0] : 0, fixed != MAP_FAILED ? fixed[1] : 0,
         res != MAP_FAILED && fixed != MAP_FAILED ? res[0] : 0, res != MAP_FAILED && fixed != MAP_FAILED ? res[1] : 0);
    if(plain != MAP_FAILED) munmap(plain, 16384);
    if(res != MAP_FAILED) munmap(res, 65536);
    close(fd);
}

/* PWBOOT and platform markers: keep them in the log as well as the kernel debug output */
int __wrap_sceKernelDebugOutText(int channel, const char *text);
int __wrap_sceKernelDebugOutText(int channel, const char *text){
    if(child_log >= 0 && text) write(child_log, text, strlen(text));
    return __real_sceKernelDebugOutText(channel, text);
}

/* Phase D.3 / P019: a job from kernelbase (CreateProcess of a program set to run separately): the image, its
 * command line and current directory, and a token. The command line becomes Wine's argv after the image; the
 * current directory becomes this process's; a PE32 image gets the WoW64 CPU the title uses for 32-bit
 * programs; and once this process has joined the server it reports "pid tid" under the token, from which
 * kernelbase gives the caller real handles. */
static int job_argc;
static char *job_argv[40];
static char job_token[16];
static char job_cwd[1024];

/* Windows path -> console path, for the drives OrbisDesk mounts (platform/ps4/pw_wine_fs.c): C: is the
 * prefix's drive_c, Z: is /data, D:-K: USB drives, L: the disc. 0 when the drive is not one of those. */
static int dos_to_unix(const char *dos, char *out, size_t cap){
    if(!strncmp(dos, "\\\\?\\", 4) || !strncmp(dos, "\\??\\", 4)) dos += 4;
    if(!dos[0] || dos[1] != ':') return 0;
    char drive = (char)(dos[0] | 0x20);
    const char *root;
    char usb[16];
    if(drive == 'c') root = "/data/wine-prefix/drive_c";
    else if(drive == 'z') root = "/data";   /* Z: is /data (hardware 2026-11-12: "" sent Z:\orbisdesk to /orbisdesk) */
    else if(drive >= 'd' && drive <= 'k'){ snprintf(usb, sizeof(usb), "/mnt/usb%d", drive - 'd'); root = usb; }
    else if(drive == 'l') root = "/mnt/disc";
    else return 0;
    int n = snprintf(out, cap, "%s/%s", root, dos[2] == '\\' || dos[2] == '/' ? dos + 3 : dos + 2);
    if(n < 0 || (size_t)n >= cap) return 0;
    for(char *p = out; *p; p++) if(*p == '\\') *p = '/';
    size_t len = strlen(out);
    while(len > 1 && out[len - 1] == '/') out[--len] = 0;
    return 1;
}

/* the PE machine of an image (0 when unreadable) */
static unsigned pe_machine(const char *unix_path){
    int fd = open(unix_path, O_RDONLY);
    if(fd < 0) return 0;
    unsigned char dos[64], nt[6]; unsigned machine = 0;
    if(read(fd, dos, sizeof(dos)) == (ssize_t)sizeof(dos) && dos[0] == 'M' && dos[1] == 'Z'){
        unsigned lfanew = dos[0x3c] | dos[0x3d] << 8 | dos[0x3e] << 16 | (unsigned)dos[0x3f] << 24;
        if(lseek(fd, lfanew, SEEK_SET) == (off_t)lfanew && read(fd, nt, sizeof(nt)) == (ssize_t)sizeof(nt) &&
           nt[0] == 'P' && nt[1] == 'E') machine = nt[4] | nt[5] << 8;
    }
    close(fd);
    return machine;
}

/* split a Windows command line (CommandLineToArgvW's rules for quotes and backslashes) */
static int split_cmdline(char *s, char **argv, int max){
    int n = 0;
    while(*s && n < max){
        while(*s == ' ' || *s == '\t') s++;
        if(!*s) break;
        char *out = s; argv[n++] = s;
        int quoted = 0;
        while(*s && (quoted || (*s != ' ' && *s != '\t'))){
            int slashes = 0;
            while(*s == '\\'){ slashes++; s++; }
            if(*s == '"'){
                for(int k = 0; k < slashes / 2; k++) *out++ = '\\';
                if(slashes % 2) *out++ = *s++;
                else { quoted = !quoted; s++; }
            }
            else { for(int k = 0; k < slashes; k++) *out++ = '\\'; if(*s) *out++ = *s++; }
        }
        if(*s) s++;
        *out = 0;
    }
    return n;
}

/* called before __wine_main with the job's image: current directory and WoW64 CPU */
static void job_prepare(const char *image){
    char unix_image[1024];
    unsigned machine = dos_to_unix(image, unix_image, sizeof(unix_image)) ? pe_machine(unix_image) : 0;
    if(machine == 0x14c){ setenv("WINE_PS4_WOW64_CPU", "wow64native.dll", 1); setenv("PW_NATIVE_SIGNALS", "1", 1); }
    int cd = job_cwd[0] ? pw_wine_chdir(0, job_cwd) : -2;
    clog("{\"build\":\"P019\",\"event\":\"job_prepared\",\"machine\":\"%04x\",\"cwd\":\"%s\",\"chdir\":%d,\"argc\":%d}",
         machine, job_cwd, cd, job_argc);
}

/* after this process has joined the server (called from the USD wrapper): "pid tid" for kernelbase */
extern int NtQueryInformationThread(void *handle, int info_class, void *info, unsigned int size, unsigned int *ret);
static void job_report_started(void){
    if(!job_token[0]) return;
    unsigned char tbi[48]; memset(tbi, 0, sizeof(tbi));
    int status = NtQueryInformationThread((void *)~(uintptr_t)1 /* current thread */, 0 /* ThreadBasicInformation */, tbi, sizeof(tbi), NULL);
    unsigned long pid = *(unsigned long *)(tbi + 0x10), tid = *(unsigned long *)(tbi + 0x18);
    char path[160], tmp[170], line[48];
    snprintf(path, sizeof(path), "/data/orbisdesk/process-p014/started-%s", job_token);
    snprintf(tmp, sizeof(tmp), "%s.tmp", path);
    int n = snprintf(line, sizeof(line), "%lu %lu\n", pid, tid);
    int fd = open(tmp, O_WRONLY | O_CREAT | O_TRUNC, 0666), ok = 0;
    if(fd >= 0){ ok = write(fd, line, (size_t)n) == n; close(fd); chmod(tmp, 0666); ok = ok && !rename(tmp, path); }
    clog("{\"build\":\"P019\",\"event\":\"started_reported\",\"status\":\"0x%08x\",\"pid\":%lu,\"tid\":%lu,\"ok\":%d}", (unsigned)status, pid, tid, ok);
}

int pop_wine_child_run(int server_fd, const char *exe, const char *log_path);
__attribute__((visibility("default"))) int pop_wine_child_run_job(int server_fd, const char *token, const char *image,
                                                                  const char *cmdline, const char *cwd, const char *log_path);
__attribute__((visibility("default"))) int pop_wine_child_run_job(int server_fd, const char *token, const char *image,
                                                                  const char *cmdline, const char *cwd, const char *log_path){
    static char line[8192];
    snprintf(job_token, sizeof(job_token), "%s", token);
    snprintf(line, sizeof(line), "%s", cmdline);
    char *words[36]; int n = split_cmdline(line, words, 36);
    job_argv[0] = "/data/wine/bin/wine";
    job_argv[1] = (char *)image;
    job_argc = 2;
    for(int k = 1; k < n && job_argc < 39; k++) job_argv[job_argc++] = words[k];   /* words[0] is the program */
    job_argv[job_argc] = NULL;
    if(!dos_to_unix(cwd, job_cwd, sizeof(job_cwd))) job_cwd[0] = 0;
    return pop_wine_child_run(server_fd, image, log_path);
}

/* Phase D.3: every program run here belongs on the title's desktop (explorer /desktop=shell in WinSta0). A
 * process started outside the title has no desktop in its startup information, and win32u would then open
 * "Default". ntdll's init_peb (env.c) fills the process parameters, then calls virtual_set_large_address_space
 * and only afterwards copies the parameters for a 32-bit image (build_wow64_parameters): setting
 * ProcessParameters->Desktop here reaches both worlds. Offsets: PEB.ProcessParameters 0x20,
 * RTL_USER_PROCESS_PARAMETERS.Desktop 0xC0 (x86_64). An existing desktop name is left alone. */
extern void *peb;
extern void __real_virtual_set_large_address_space(void);
static const uint16_t title_desktop[] = {'W','i','n','S','t','a','0','\\','s','h','e','l','l',0};
void __wrap_virtual_set_large_address_space(void);
void __wrap_virtual_set_large_address_space(void){
    char *params = peb ? *(char **)((char *)peb + 0x20) : NULL;
    if(params){
        uint16_t *desktop = (uint16_t *)(params + 0xC0);
        if(!desktop[0]){
            desktop[0] = 13 * 2; desktop[1] = 14 * 2;
            *(const uint16_t **)(params + 0xC8) = title_desktop;
            clog("{\"build\":\"P019\",\"event\":\"desktop_set\",\"name\":\"WinSta0\\\\shell\"}");
        }
    }
    __real_virtual_set_large_address_space();
}

/* Phase D.4a: the title's offscreen Vulkan probe and Wine's Vulkan entry, run on a thread of their own */
static void *gpu_probe_thread(void *arg){
    extern void pw_vk_probe(void);
    extern void pw_vk_runtime_init(void);
    (void)arg;
    pw_vk_probe();
    pw_vk_runtime_init();
    return NULL;
}

/* Wine asks only for the codeset (env.c init_unix_codepage), and musl answers from the thread's locale,
 * which in this PRX is not musl's thread data: the console's names are UTF-8 */
#include <langinfo.h>
extern char *__real_nl_langinfo(nl_item item);
char *__wrap_nl_langinfo(nl_item item);
char *__wrap_nl_langinfo(nl_item item){
    if(item == CODESET) return (char *)"UTF-8";
    return __real_nl_langinfo(item);
}

/* System modules: Mesa's PS4 layer names them under the application sandbox's random directory
 * (/<word>/common/lib/...), which exists only inside an application's sandbox; this process runs from the real
 * root, where they are /system/common/lib/... (hardware 2026-11-12: libSceGnmDriver.sprx 0x80020002) */
extern int __real_sceKernelLoadStartModule(const char *path, size_t args, const void *argp, uint32_t flags, void *opt, int *res);
int __wrap_sceKernelLoadStartModule(const char *path, size_t args, const void *argp, uint32_t flags, void *opt, int *res);
int __wrap_sceKernelLoadStartModule(const char *path, size_t args, const void *argp, uint32_t flags, void *opt, int *res){
    int handle = __real_sceKernelLoadStartModule(path, args, argp, flags, opt, res);
    const char *lib = path ? strstr(path, "/common/lib/") : NULL;
    if(handle < 0 && lib && strncmp(path, "/system/", 8)){
        char system_path[256];
        snprintf(system_path, sizeof(system_path), "/system%s", lib);
        int retry = __real_sceKernelLoadStartModule(system_path, args, argp, flags, opt, res);
        clog("{\"build\":\"P020\",\"event\":\"module_retry\",\"path\":\"%s\",\"first\":\"0x%08x\",\"system\":\"0x%08x\"}",
             system_path, (unsigned)handle, (unsigned)retry);
        return retry;
    }
    return handle;
}

/* PoP D.7 (hardware 2026-11-13: after a session closed with a separate launcher open, the next start hung
 * connecting to its wineserver until the console rebooted): this process ends with the title. The bridge socket to
 * the title's wineserver hangs up when the title goes; a thread looks every 500 ms and ends the process then, as a
 * Windows process ends when its session's server does. */
static int title_server_fd = -1;
static void *title_watch(void *arg)
{
    (void)arg;
    for(;;){
        struct pollfd pfd = { title_server_fd, 0, 0 };
        int rc = poll(&pfd, 1, 500);
        if(rc > 0 && (pfd.revents & (POLLHUP | POLLERR | POLLNVAL))){
            clog("{\"build\":\"P024\",\"event\":\"title_gone\",\"revents\":%d}", pfd.revents);
            _exit(0);
        }
        if(rc < 0 && errno != EINTR) usleep(500000);
    }
    return NULL;
}

/* PoP D.7 (hardware 2026-11-14, d32 and d33: the console stopped answering, PS button and FTP included, while
 * the mouse cursor still moved; the forced restart lost this log, file and all): a thread puts the log, Wine's
 * stderr lines included, on disk every 2 seconds, so the last state before a hang survives the restart */
#include <signal.h>
#include <sys/resource.h>
/* PoP D.7 (hardware 2026-11-14, d34: the launcher, reopened, froze while its dialog was being dragged; the title's
 * wineserver then saw POLLIN with FIONREAD 0 on that thread's request pipe, and the whole child, this file's
 * heartbeat thread included, stopped). Monitor the writes of both the original header-only path and the
 * shared request writer used by the title and child for requests with data. */
extern ssize_t __real_write(int, const void *, size_t);
extern unsigned long pw_wine_request_chunks_written(void);
extern void pw_pop_surface_start(void);
static int last_write_fd;
static size_t last_write_size;
static unsigned writes_active, writes_done;

ssize_t __wrap_write(int fd, const void *buffer, size_t size);
ssize_t __wrap_write(int fd, const void *buffer, size_t size){
    if(fd <= STDERR_FILENO || fd == child_log) return __real_write(fd, buffer, size);
    __atomic_store_n(&last_write_fd, fd, __ATOMIC_RELAXED);
    __atomic_store_n(&last_write_size, size, __ATOMIC_RELAXED);
    __atomic_add_fetch(&writes_active, 1, __ATOMIC_RELAXED);
    ssize_t result = __real_write(fd, buffer, size);
    __atomic_add_fetch(&writes_done, 1, __ATOMIC_RELAXED);
    __atomic_sub_fetch(&writes_active, 1, __ATOMIC_RELAXED);
    return result;
}

static void *child_heartbeat(void *arg){
    (void)arg;
    for(unsigned beat = 1;; beat++){
        usleep(2000000);
        unsigned active = __atomic_load_n(&writes_active, __ATOMIC_RELAXED);
        /* each beat while a write has not returned; otherwise the first ones and every 30 s */
        if(beat <= 3 || beat % 15 == 0 || active)
            clog("{\"build\":\"P031\",\"event\":\"heartbeat\",\"beat\":%u,\"log_bytes\":%ld,\"request_chunks\":%lu,"
                 "\"writes_active\":%u,\"writes_done\":%u,"
                 "\"last_write_fd\":%d,\"last_write_size\":%zu}",
                 beat, (long)lseek(child_log, 0, SEEK_CUR), pw_wine_request_chunks_written(), active,
                 __atomic_load_n(&writes_done, __ATOMIC_RELAXED),
                 __atomic_load_n(&last_write_fd, __ATOMIC_RELAXED),
                 __atomic_load_n(&last_write_size, __ATOMIC_RELAXED));
        fsync(child_log);
    }
    return NULL;
}

__attribute__((visibility("default"))) int pop_wine_child_run(int server_fd, const char *exe, const char *log_path);
__attribute__((visibility("default"))) int pop_wine_child_run(int server_fd, const char *exe, const char *log_path){
    const char *prefix = "/data/wine-prefix";
    __init_libc((char **)pop_initial_block, "/data/wine/bin/wine");
    /* the title runs Wine with tracing off (native/wine_hardware.c sets pw_trace_level from its build/launch
     * arguments); the same here, so both processes take the same code paths */
    extern int pw_trace_level; pw_trace_level = 0; setenv("PW_TRACE", "0", 1);
    child_log = open(log_path, O_WRONLY | O_CREAT | O_TRUNC, 0666);
    if(child_log < 0) child_log = open(log_path, O_WRONLY | O_CREAT | O_TRUNC, 0666);  /* see native/pop_prx_probe.c: a first open failed on hardware */
    clog("{\"build\":\"P017\",\"event\":\"wine_child_entered\",\"pid\":%d,\"uid\":%d,\"server_fd\":%d,\"exe\":\"%s\"}",
         (int)getpid(), (int)getuid(), server_fd, exe);
    /* Wine's own stderr (ERR/FIXME/WARN lines) goes to the same log */
    if(child_log >= 0) dup2(child_log, 2);
    clog("{\"build\":\"P031\",\"event\":\"request_transport\",\"max_chunk\":%d}", _POSIX_PIPE_BUF);
    /* PoP D.7 (same hangs): this process yields to the system's own; the heartbeat thread starts with every
     * signal blocked, so none of Wine's signals lands on a thread Wine does not know */
    {
        errno = 0;
        int nice_rc = setpriority(PRIO_PROCESS, 0, 10);
        clog("{\"build\":\"P026\",\"event\":\"child_priority\",\"rc\":%d,\"errno\":%d}", nice_rc, nice_rc ? errno : 0);
        sigset_t all, old;
        sigfillset(&all);
        pthread_sigmask(SIG_BLOCK, &all, &old);
        pthread_t beat;
        int beat_rc = pthread_create(&beat, NULL, child_heartbeat, NULL);
        pthread_sigmask(SIG_SETMASK, &old, NULL);
        clog("{\"build\":\"P026\",\"event\":\"heartbeat_thread\",\"rc\":%d}", beat_rc);
        fsync(child_log);
    }
    /* Hardware 2026-11-12: none of this file's counted traces ever printed and Wine reported ntdll.dll mapped
     * without one memory call on it. Check that the system linker zeroed this PRX's .bss: these statics
     * must start at 0, and a sample of the .bss tail must be zero. */
    {
        extern char __pop_bss_start[], __pop_bss_end[];  /* build/pop-wine-child/link.x */
        unsigned long nonzero = 0, sampled = 0;
        if(__pop_bss_end > __pop_bss_start)
            for(char *q = __pop_bss_start; q < __pop_bss_end; q += 4096){ sampled++; if(*q) nonzero++; }
        clog("{\"build\":\"P017\",\"event\":\"bss_check\",\"trace_lines\":%u,\"pread_retries\":%lu,\"private_file_maps\":%lu,"
             "\"trace_lines_at\":\"%p\",\"bss\":\"%p\",\"end\":\"%p\",\"sampled\":%lu,\"nonzero\":%lu}",
             trace_lines, pread_retries, private_file_maps, (void *)&trace_lines, (void *)__pop_bss_start, (void *)__pop_bss_end, sampled, nonzero);
    }
    char fd_text[16]; snprintf(fd_text, sizeof(fd_text), "%d", server_fd);
    int rc = 0;
    if(pw_wine_init_paths(prefix, "/data/wine-home", "orbis")) rc = 90;
    else if(pw_wine_fs_drive_mounts(prefix)) rc = 90;
    else if(setenv("WINESERVERSOCKET", fd_text, 1) || setenv("WINE_PS4_EXTERNAL_PREFIX", "1", 1) ||
            setenv("WINEARCH", "wow64", 1) ||
            setenv("WINE_PS5_DESKTOP", "1280x720", 1) ||
            setenv("PW_SEPARATE_PROCESS", "1", 1) ||   /* D.4: programs can tell they run in the separate process */   /* the title's desktop size: win32u resizes the shared desktop window to it */
            setenv("WINE_PS4_NTDLL_DIR", "/data/wine/lib/wine/x86_64-unix", 1) ||
            setenv("WINE_PS4_NLS_DIR", "/data/wine/share/wine/nls", 1) ||
            setenv("WINE_PS4_DATA_DIR", "/data/wine/share/wine", 1) ||
            setenv("WINEDLLPATH", "/data/wine/lib/wine", 1) ||
            setenv("WINELOADERNOEXEC", "1", 1) || setenv("WINEDEBUG", "err+all,fixme-all", 1)) rc = 91;
    else if(pw_wine_chdir(0, "/data") || pw_wine_chdir(1, prefix) || pw_wine_chdir(0, "/data/orbisdesk")) rc = 92;
    clog("{\"build\":\"P017\",\"event\":\"wine_child_prepared\",\"rc\":%d,\"errno\":%d,\"pagesize\":%ld}", rc, rc ? errno : 0, sysconf(_SC_PAGESIZE));
    if(rc) return rc;
    /* PoP launcher: PrinceOfPersia.EXE's hardware detection (detectionapi.dll, directx8tests.dll,
     * directx9tests.dll) creates Direct3D 8/9 objects. This process has no GPU (D.4a: loading GNM here stopped
     * the console), and without gpu-probe it links no RADV, so DXVK's d3d9 would only fail. Wine's own d3d8/d3d9
     * answer through wined3d's no3d adapter, which uses neither Vulkan nor OpenGL; the game itself runs in the
     * title (D.4) with its usual Direct3D */
    {
        struct stat no3d;
        if(stat("/data/orbisdesk/process-p014/gpu-probe", &no3d) != 0 &&
           (setenv("WINE_D3D_CONFIG", "renderer=no3d", 1) ||
            setenv("WINEDLLOVERRIDES", "d3d8,d3d9,ddraw,dxgi,d3d10core,d3d11=b", 1))) return 95;
        clog("{\"build\":\"P022\",\"event\":\"direct3d\",\"no3d\":%d}", stat("/data/orbisdesk/process-p014/gpu-probe", &no3d) != 0);
    }
    char *fixed_argv[] = {"/data/wine/bin/wine", (char *)exe, NULL};
    char **wine_argv = job_argc ? job_argv : fixed_argv;
    int wine_argc = job_argc ? job_argc : 2;
    /* Phase D.4a (before the low range is freed: the probe loads system modules, and the module loader reads
     * the process parameters in the borrowed eboot's data at 0x478000; hardware 2026-11-12 faulted there):
     * can this process drive the GPU? The title's offscreen Vulkan probe (native/vk_probe/main.c,
     * PW_VK_IN_WINE: RADV on GNM, device, 300 frames without VideoOut), its PWVK lines in this log; then Wine's
     * Vulkan entry as in the title. Only when POP_SEP_DIR/gpu-probe exists. */
    {
        struct stat gp;
        if(stat("/data/orbisdesk/process-p014/gpu-probe", &gp) == 0){
            /* on its own thread: Mesa changes per-thread state (its locale), and in this PRX the thread pointer
             * is not musl's; hardware 2026-11-12: Wine's main thread then faulted in nl_langinfo */
            pthread_t probe_thread;
            clog("{\"build\":\"P020\",\"event\":\"gpu_probe_start\"}");
            int created = pthread_create(&probe_thread, NULL, gpu_probe_thread, NULL);
            if(!created) pthread_join(probe_thread, NULL);
            clog("{\"build\":\"P020\",\"event\":\"gpu_probe_end\",\"thread\":%d}", created);
        }
    free_low_image_range();
    file_mmap_check();
    protection_check();
    if(job_argc) job_prepare(exe);
    }
    {
        pthread_t watch;
        title_server_fd = server_fd;
        clog("{\"build\":\"P024\",\"event\":\"title_watch\",\"rc\":%d}", pthread_create(&watch, NULL, title_watch, NULL));
    }
    pw_pop_surface_start();
    clog("{\"build\":\"P017\",\"event\":\"wine_main\",\"argc\":%d}", wine_argc);
    __wine_main(wine_argc, wine_argv);
    clog("{\"build\":\"P017\",\"event\":\"wine_main_returned\"}");
    return 94;
}
