/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#include <orbis/libkernel.h>
#include "pw_vm_ps4.h"
#include "pw_pthread_ps4.h"

#ifdef WITH_TRANSLATOR
#include "pw_x86_block.h"
#include "translator_runtime.h"
#endif

enum { PAGE = 0x4000 };
static const char *case_name;
static char detail[384];
int probe_process(int, char *, size_t);
int probe_wine(int, char *, size_t);
#ifdef WITH_WINE_PLATFORM
int probe_wine_platform(int, char *, size_t);
#endif

static void record(const char *event, const char *status, int code)
{
    char line[1024];
    snprintf(line, sizeof(line), "PWPS4 {\"event\":\"%s\",\"case\":\"%s\","
             "\"status\":\"%s\",\"code\":%d,\"detail\":\"%s\"}\n",
             event, case_name, status, code, detail);
    sceKernelDebugOutText(0, line);
}

static int files(void)
{
    static const char payload[] = "orbisdesk file roundtrip\n";
    char buffer[sizeof(payload)] = {0};
    int ok = 0;
    mkdir("/data/orbisdesk", 0777);
    int fd = open("/data/orbisdesk/probe.tmp", O_CREAT | O_TRUNC | O_RDWR, 0600);
    if (fd < 0) return errno ? errno : 1;
    if (write(fd, payload, sizeof(payload)) == sizeof(payload) &&
        lseek(fd, 0, SEEK_SET) == 0 && read(fd, buffer, sizeof(buffer)) == sizeof(buffer))
        ok = memcmp(buffer, payload, sizeof(buffer)) == 0;
    int rc = close(fd);
    int removed = unlink("/data/orbisdesk/probe.tmp");
    return ok && !rc && !removed ? 0 : 1;
}

static int low_memory(void)
{
    void *p = (void *)(uintptr_t)0x20000000;
    int rc = sceKernelReserveVirtualRange(&p, PAGE, 0, PAGE);
    snprintf(detail, sizeof(detail), "reserve=%d address=0x%llx", rc, (unsigned long long)(uintptr_t)p);
    if (rc) return rc;
    int ok = (uintptr_t)p >= 0x10000 && (uintptr_t)p + PAGE <= 0x100000000ULL;
    rc = sceKernelMunmap(p, PAGE);
    return ok && !rc ? 0 : 1;
}

static int reserve_collision(void)
{
    void *p = NULL;
    int rc = sceKernelMapFlexibleMemory(&p, PAGE, 3, 0);
    if (rc) return rc;
    volatile uint32_t *word = p;
    *word = 0x5a71c0de;
    void *again = p;
    /* SCE_KERNEL_MAP_FIXED | SCE_KERNEL_MAP_NO_OVERWRITE, as used by upstream Wine. */
    int collision = sceKernelReserveVirtualRange(&again, PAGE, 0x10 | 0x80, PAGE);
    int preserved = *word == 0x5a71c0de;
    snprintf(detail, sizeof(detail), "collision=%d preserved=%d", collision, preserved);
    rc = sceKernelMunmap(p, PAGE);
    return collision != 0 && preserved && !rc ? 0 : 1;
}

static int generated_code(int rwx)
{
    void *p = NULL;
    int rc = sceKernelMapFlexibleMemory(&p, PAGE, rwx ? 7 : 3, 0);
    if (rc) return rc;
    const unsigned char code[] = {0xb8, 0x2a, 0, 0, 0, 0xc3};
    memcpy(p, code, sizeof(code));
    if (!rwx) rc = sceKernelMprotect(p, PAGE, 5);
    int value = -1;
    if (!rc) value = ((int (*)(void))p)();
    snprintf(detail, sizeof(detail), "rwx=%d protect_rc=%d returned=%d", rwx, rc, value);
    int released = sceKernelMunmap(p, PAGE);
    return !rc && value == 42 && !released ? 0 : 1;
}

static pthread_key_t key;
static pthread_mutex_t mutex = PTHREAD_MUTEX_INITIALIZER;
static unsigned counter;
static unsigned destructors;
static void tls_destructor(void *value)
{
    if (value == (void *)0x1234 || value == (void *)0x5678)
        __atomic_fetch_add(&destructors, 1, __ATOMIC_RELAXED);
}
static void *worker(void *arg)
{
    if (pthread_setspecific(key, arg)) return (void *)1;
    for (unsigned i = 0; i < 1000; ++i) {
        if (pthread_mutex_lock(&mutex)) return (void *)2;
        ++counter;
        if (pthread_mutex_unlock(&mutex)) return (void *)3;
    }
    return pthread_getspecific(key) == arg ? NULL : (void *)4;
}

static int threads(int adapted)
{
    pthread_t a, b;
    void *ra = (void *)1, *rb = (void *)1;
    int rc = pthread_key_create(&key, tls_destructor);
    if (rc) return rc;
    int ca = pthread_create(&a, NULL, worker, (void *)0x1234);
    int cb = pthread_create(&b, NULL, worker, (void *)0x5678);
    int ja = ca ? ca : pthread_join(a, &ra);
    int jb = cb ? cb : pthread_join(b, &rb);
    int deleted = adapted ? pw_ps4_pthread_key_delete(key) : pthread_key_delete(key);
    snprintf(detail, sizeof(detail), "adapted=%d create=%d,%d join=%d,%d counter=%u tls=%d,%d destructors=%u delete=%d",
             adapted, ca, cb, ja, jb, counter, ra == NULL, rb == NULL, destructors, deleted);
    return !ca && !cb && !ja && !jb && !ra && !rb && counter == 2000 && destructors == 2 && !deleted ? 0 : 1;
}

/* Orbis uses the FreeBSD signal ABI, not the Linux layout in the musl headers.
 * Layout reference: DolphinPS4/probe/main.cpp and shadPS4/kernel/threads/exception.h.
 * Only the fixed general-register prefix is accessed; no FP layout is assumed. */
struct context_prefix {
    uint32_t mask[4];
    uint32_t reserved[12];
    uint64_t onstack, rdi, rsi, rdx, rcx, r8, r9, rax, rbx, rbp;
    uint64_t r10, r11, r12, r13, r14, r15;
    uint32_t trapno;
    uint16_t fs, gs;
    uint64_t addr;
    uint32_t flags;
    uint16_t es, ds;
    uint64_t err, rip, cs, rflags, rsp, ss;
};
_Static_assert(__builtin_offsetof(struct context_prefix, rip) == 224, "Orbis RIP ABI");
struct orbis_sigaction {
    void (*handler)(int, void *, void *);
    int flags;
    uint32_t mask[4];
};
extern char pw_fault_insn[], pw_fault_resume[];
extern char pw_store_insn[], pw_store_resume[];
extern uint32_t pw_fault_load(const void *p);
extern uint32_t pw_fault_store(void *p, uint32_t value);
static volatile sig_atomic_t recovered;

static void fault_handler(int sig, void *info, void *raw)
{
    (void)info;
    struct context_prefix *ctx = raw;
    if ((sig == 11 || sig == 10) && ctx->rip == (uintptr_t)pw_fault_insn) {
        ctx->rip = (uintptr_t)pw_fault_resume;
        ctx->rax = 0x5a5a;
        recovered = recovered + 1;
        return;
    }
    if ((sig == 11 || sig == 10) && ctx->rip == (uintptr_t)pw_store_insn) {
        ctx->rip = (uintptr_t)pw_store_resume;
        ctx->rax = 0x5a5a;
        recovered = recovered + 1;
        return;
    }
    _exit(97);
}

static int exceptions(void)
{
    struct orbis_sigaction action = {fault_handler, 0x40, {0}}, old_segv, old_bus;
    /* Calls the exported function using its real target ABI. */
    typedef int (*action_fn)(int, const void *, void *);
    action_fn install = (action_fn)(uintptr_t)&sigaction;
    int rc = install(11, &action, &old_segv);
    if (rc) return rc;
    rc = install(10, &action, &old_bus);
    if (rc) { install(11, &old_segv, NULL); return rc; }
    void *guard = NULL;
    rc = sceKernelReserveVirtualRange(&guard, PAGE, 0, PAGE);
    unsigned value = rc ? 0 : pw_fault_load(guard);
    if (!rc) rc = sceKernelMunmap(guard, PAGE);
    int a = install(11, &old_segv, NULL), b = install(10, &old_bus, NULL);
    snprintf(detail, sizeof(detail), "signal=%d resumed=%d value=%u rip_offset=%zu",
             rc, recovered, value, __builtin_offsetof(struct context_prefix, rip));
    return !rc && !a && !b && recovered && value == 0x5a5a ? 0 : 1;
}

static int vm_enforcement(void)
{
    struct orbis_sigaction action = {fault_handler, 0x40, {0}}, old_segv, old_bus;
    typedef int (*action_fn)(int, const void *, void *);
    action_fn install = (action_fn)(uintptr_t)&sigaction;
    if (install(11, &action, &old_segv)) return 1;
    if (install(10, &action, &old_bus)) { install(11, &old_segv, NULL); return 1; }
    void *p = NULL;
    int rc = sceKernelMapFlexibleMemory(&p, PAGE, 3, 0);
    unsigned write_fault = 0, read_fault = 0;
    if (!rc) {
        *(uint32_t *)p = 0x12345678;
        rc = sceKernelMprotect(p, PAGE, 1);
        if (!rc) write_fault = pw_fault_store(p, 0x87654321);
        if (!rc && *(uint32_t *)p != 0x12345678) rc = 1;
        if (!rc) rc = sceKernelMprotect(p, PAGE, 0);
        if (!rc) read_fault = pw_fault_load(p);
        if (!rc) rc = sceKernelMprotect(p, PAGE, 3);
        if (!rc && *(uint32_t *)p != 0x12345678) rc = 1;
        if (sceKernelMunmap(p, PAGE)) rc = 1;
    }
    int a = install(11, &old_segv, NULL), b = install(10, &old_bus, NULL);
    snprintf(detail, sizeof(detail), "protection=%d write_blocked=%d read_blocked=%d recovered=%d",
             rc, write_fault == 0x5a5a, read_fault == 0x5a5a, recovered);
    return !rc && !a && !b && write_fault == 0x5a5a && read_fault == 0x5a5a && recovered == 2 ? 0 : 1;
}

extern int sysarch(int operation, void *value);
static int segments(void)
{
    uint16_t fs, gs;
    uintptr_t fs_base = UINTPTR_MAX, gs_base = UINTPTR_MAX;
    __asm__ volatile("mov %%fs,%0; mov %%gs,%1" : "=r"(fs), "=r"(gs));
    /* Import sysarch through libkernel; an unresolved stub must not pass by
     * returning zero without writing the requested register bases. */
    int a = sysarch(128, &fs_base), b = sysarch(130, &gs_base);
    snprintf(detail, sizeof(detail), "FS=%u GS=%u fsbase=0x%llx gsbase=0x%llx get=%d,%d",
             fs, gs, (unsigned long long)fs_base, (unsigned long long)gs_base, a, b);
    return a || b || fs_base == UINTPTR_MAX || gs_base == UINTPTR_MAX ? 1 : 0;
}

static int vm_backend(void)
{
    PwVmBackend vm;
    PwVmRegion region = {0}, collision = {0};
    int rc = pw_vm_ps4_backend(&vm);
    if (rc || !pw_vm_backend_valid(&vm)) return 1;
    rc = vm.reserve_at(NULL, 0x24000000, PAGE, PAGE, &region);
    if (rc) return rc;
    rc = vm.commit(NULL, &region, 0, PAGE, PW_PROT_READ | PW_PROT_WRITE);
    if (!rc) {
        *(uint32_t *)region.write_base = 0x55aa1234;
        int refused = vm.reserve_at(NULL, 0x24000000, PAGE, PAGE, &collision);
        if (refused == PW_OK || *(uint32_t *)region.write_base != 0x55aa1234) rc = 1;
        if (refused == PW_OK) vm.release(NULL, &collision);
    }
    if (!rc) rc = vm.protect(NULL, &region, 0, PAGE, PW_PROT_READ);
    if (!rc && *(uint32_t *)region.write_base != 0x55aa1234) rc = 1;
    if (!rc) rc = vm.protect(NULL, &region, 0, PAGE, PW_PROT_READ | PW_PROT_WRITE);
    snprintf(detail, sizeof(detail), "backend=%d page_bytes=%zu", rc, vm.page_bytes);
    int released = vm.release(NULL, &region);
    return rc || released ? 1 : 0;
}

static int vm_ownership(void)
{
    PwVmBackend vm;
    PwVmRegion region = {0}, replacement = {0}, stale, forged;
    PwPs4VmStats stats;
    int ok = 0;
    if (pw_vm_ps4_backend(&vm)) return 1;
#define VM_REQUIRE(condition) do { if (!(condition)) { \
    snprintf(detail, sizeof(detail), "ownership check failed at line %d", __LINE__); goto done; \
} } while (0)
    VM_REQUIRE(vm.reserve(NULL, PAGE * 3, PAGE, &region) == PW_OK);
    stale = region;
    VM_REQUIRE(vm.protect(NULL, &region, 0, PAGE, 1) == PW_ERR_STATE);
    forged = region;
    forged.bytes += PAGE;
    VM_REQUIRE(vm.commit(NULL, &forged, 0, PAGE, 3) == PW_ERR_PRECONDITION);
    VM_REQUIRE(vm.release(NULL, &forged) == PW_ERR_PRECONDITION);
    VM_REQUIRE(vm.commit(NULL, &region, 0, PAGE, 3) == PW_OK);
    *(uint32_t *)region.write_base = 0x13579bdf;
    VM_REQUIRE(vm.commit(NULL, &region, 0, PAGE * 2, 3) == PW_ERR_STATE);
    VM_REQUIRE(*(uint32_t *)region.write_base == 0x13579bdf);
    VM_REQUIRE(vm.commit(NULL, &region, 1, PAGE, 3) == PW_ERR_PRECONDITION);
    VM_REQUIRE(vm.commit(NULL, &region, SIZE_MAX, PAGE, 3) == PW_ERR_PRECONDITION);
    VM_REQUIRE(vm.commit(NULL, &region, PAGE * 3, PAGE, 3) == PW_ERR_PRECONDITION);
    VM_REQUIRE(vm.commit(NULL, &region, PAGE, PAGE, 0x80) == PW_ERR_PRECONDITION);
    VM_REQUIRE(vm.protect(NULL, &region, 0, PAGE * 2, 1) == PW_ERR_STATE);
    VM_REQUIRE(vm.commit(NULL, &region, PAGE, PAGE, 3) == PW_OK);
    VM_REQUIRE(vm.protect(NULL, &region, 0, PAGE * 2, 1) == PW_OK);
    VM_REQUIRE(*(uint32_t *)region.write_base == 0x13579bdf);
    VM_REQUIRE(!pw_vm_ps4_stats(&stats) && stats.reservations == 1 &&
               stats.reserved_bytes == PAGE * 3 && stats.committed_bytes == PAGE * 2);
    VM_REQUIRE(vm.release(NULL, &region) == PW_OK);
    VM_REQUIRE(vm.reserve_at(NULL, (uintptr_t)stale.exec_base, PAGE, PAGE, &replacement) == PW_OK);
    VM_REQUIRE(replacement.handle != stale.handle);
    VM_REQUIRE(vm.commit(NULL, &stale, 0, PAGE, 3) == PW_ERR_PRECONDITION);
    VM_REQUIRE(vm.protect(NULL, &stale, 0, PAGE, 1) == PW_ERR_PRECONDITION);
    VM_REQUIRE(vm.release(NULL, &stale) == PW_ERR_PRECONDITION);
    VM_REQUIRE(vm.commit(NULL, &replacement, 0, PAGE, 3) == PW_OK);
    ok = 1;
done:
    if (region.handle && vm.release(NULL, &region)) ok = 0;
    if (replacement.handle && vm.release(NULL, &replacement)) ok = 0;
    if (pw_vm_ps4_stats(&stats) || stats.reservations || stats.reserved_bytes || stats.committed_bytes) ok = 0;
    if (ok) snprintf(detail, sizeof(detail), "foreign/stale/overlap refused; reuse safe; live_reservations=0");
#undef VM_REQUIRE
    return ok ? 0 : 1;
}

static void *vm_stress_worker(void *unused)
{
    (void)unused;
    PwVmBackend vm;
    if (pw_vm_ps4_backend(&vm)) return (void *)1;
    for (unsigned i = 0; i < 16; ++i) {
        PwVmRegion region = {0};
        int rc = vm.reserve(NULL, PAGE, PAGE, &region);
        if (rc) return (void *)2;
        rc = vm.commit(NULL, &region, 0, PAGE, 3);
        if (!rc) {
            *(uint32_t *)region.write_base = i;
            rc = vm.protect(NULL, &region, 0, PAGE, 1);
            if (!rc && *(uint32_t *)region.write_base != i) rc = 1;
        }
        int released = vm.release(NULL, &region);
        if (rc || released) return (void *)3;
    }
    return NULL;
}

static int vm_stress(void)
{
    pthread_t threads[4];
    unsigned created = 0;
    int ok = 1;
    for (; created < 4; ++created) {
        if (pthread_create(&threads[created], NULL, vm_stress_worker, NULL)) { ok = 0; break; }
    }
    for (unsigned i = 0; i < created; ++i) {
        void *result = (void *)1;
        if (pthread_join(threads[i], &result) || result) ok = 0;
    }
    PwPs4VmStats stats = {0};
    if (pw_vm_ps4_stats(&stats) || stats.reservations || stats.reserved_bytes || stats.committed_bytes) ok = 0;
    snprintf(detail, sizeof(detail), "threads=%u cycles=64 live_reservations=%zu committed_bytes=%zu",
             created, stats.reservations, stats.committed_bytes);
    return ok ? 0 : 1;
}

#ifdef WITH_TRANSLATOR
static int translator(int rwx)
{
    static const uint8_t guest[] = {0xb8, 7, 0, 0, 0, 0x83, 0xc0, 0x23};
    static PwX86State state;
    PwX86Block block;
    void *code = NULL;
    int rc = sceKernelMapFlexibleMemory(&code, PAGE * 4, rwx ? 7 : 3, 0);
    if (rc) return rc;
    state.eip = 0x1000;
    state.eflags = 2;
    pw_guest_fp_init(&state.fp);
    rc = pw_x86_translate(guest, sizeof(guest), state.eip, code, PAGE * 4, &block);
    if (!rc && !rwx) rc = sceKernelMprotect(code, PAGE * 4, 5);
    if (!rc) rc = pw_x86_run_block(&state, code);
    snprintf(detail, sizeof(detail), "translate_run=%d eax=%u eip=%u", rc, state.gpr[0], state.eip);
    int released = sceKernelMunmap(code, PAGE * 4);
    return !rc && !released && state.gpr[0] == 42 && state.eip == 0x1008 ? 0 : 1;
}

static int run_translation(PwX86State *state, void *code, const uint8_t *source, size_t bytes)
{
    PwX86Block block;
    int rc = pw_x86_translate(source, bytes, state->eip, code, PAGE * 4, &block);
    if (!rc && block.source_bytes != bytes) return PW_ERR_UNSUPPORTED;
    return rc ? rc : pw_x86_run_block(state, code);
}

static int translator_extended(int kind)
{
    static PwX86State state;
    PwVmBackend vm;
    PwVmRegion data = {0};
    void *code = NULL;
    int rc = pw_vm_ps4_backend(&vm);
    if (rc) return 1;
    rc = vm.reserve_at(NULL, 0x28000000, PAGE * 2, PAGE, &data);
    if (rc) return 1;
    rc = vm.commit(NULL, &data, 0, data.bytes, 3);
    if (!rc) rc = sceKernelMapFlexibleMemory(&code, PAGE * 4, 7, 0);
    if (rc) { vm.release(NULL, &data); return 1; }
    memset(&state, 0, sizeof(state));
    pw_guest_fp_init(&state.fp);
    state.eflags = 2;
    state.eip = 0x1000;
    state.stack_low = 0x28000000 + PAGE;
    state.stack_high = state.stack_low + PAGE;
    state.gpr[4] = state.stack_high - 16;
    state.memory_count = 1;
    state.memory[0] = (PwX86Memory){0x28000000, 0x28000000 + PAGE * 2, PW_X86_READ | PW_X86_WRITE};
    if (kind == 0) {
        uint32_t initial_sp = state.gpr[4];
        const uint8_t call[] = {0x6a,0xff,0x68,0x44,0x33,0x22,0x11,0xe8,0xf4,0x0f,0,0};
        rc = run_translation(&state, code, call, sizeof(call));
        uint32_t *top = (uint32_t *)(uintptr_t)state.gpr[4];
        if (!rc && (state.eip != 0x2000 || state.gpr[4] != initial_sp - 12 ||
                    top[0] != 0x100c || top[1] != 0x11223344 || top[2] != UINT32_MAX)) rc = 1;
        const uint8_t callee[] = {0xb8,42,0,0,0,0xc2,8,0};
        if (!rc) rc = run_translation(&state, code, callee, sizeof(callee));
        if (!rc && (state.gpr[0] != 42 || state.eip != 0x100c || state.gpr[4] != initial_sp)) rc = 1;
        snprintf(detail, sizeof(detail), "call_ret=%d eax=%u eip=%u stack_restored=%d",
                 rc, state.gpr[0], state.eip, state.gpr[4] == initial_sp);
    } else if (kind == 1) {
        const uint32_t inputs[] = {1,2,3,4};
        const uint32_t expected[] = {2,4,6,8};
        memcpy(data.write_base, inputs, sizeof(inputs));
        uint32_t *words = data.write_base;
        words[16] = 0x3fc00000; words[17] = 0x40100000;
        words[20] = 0x3f80;
        *(uint16_t *)((uint8_t *)data.write_base + 84) = 0x77f;
        state.gpr[0] = 0x28000000;
        state.fp.mxcsr = 0x3f80;
        state.fp.x87_control = 0x77f;
        uint32_t mxcsr_before, mxcsr_after;
        uint16_t cw_before, cw_after;
        __asm__ volatile("stmxcsr %0; fnstcw %1" : "=m"(mxcsr_before), "=m"(cw_before));
        const uint8_t fp[] = {0xd9,0x40,0x40,0xd8,0x40,0x44,0xd9,0x58,0x48,
            0xf3,0x0f,0x6f,0x00,0x66,0x0f,0xfe,0x00,0xf3,0x0f,0x7f,0x40,0x10};
        rc = run_translation(&state, code, fp, sizeof(fp));
        __asm__ volatile("stmxcsr %0; fnstcw %1" : "=m"(mxcsr_after), "=m"(cw_after));
        int host_preserved = mxcsr_before == mxcsr_after && cw_before == cw_after;
        if (!rc && (memcmp(words + 4, expected, sizeof(expected)) || words[18] != 0x40700000 ||
                    state.fp.mxcsr != 0x3f80 || state.fp.x87_control != 0x77f || !host_preserved)) rc = 1;
        snprintf(detail, sizeof(detail), "x87_sse=%d sum=0x%x sse=%x,%x,%x,%x cw=%x mxcsr=%x host_fp_preserved=%d",
                 rc, words[18], words[4], words[5], words[6], words[7], state.fp.x87_control,
                 state.fp.mxcsr, host_preserved);
    } else if (kind == 2) {
        uint8_t source[] = {0xb8,1,0,0,0};
        rc = run_translation(&state, code, source, sizeof(source));
        if (!rc && state.gpr[0] != 1) rc = 1;
        source[1] = 2;
        state.eip = 0x1000;
        if (!rc) rc = run_translation(&state, code, source, sizeof(source));
        if (!rc && (state.gpr[0] != 2 || state.eip != 0x1005)) rc = 1;
        snprintf(detail, sizeof(detail), "retranslate=%d eax=%u eip=%u", rc, state.gpr[0], state.eip);
    } else if (kind == 3) {
        state.gpr[0] = 0x28000000;
        *(uint32_t *)data.write_base = 0x3f80;
        const uint8_t load_control[] = {0x0f,0xae,0x10};
        rc = run_translation(&state, code, load_control, sizeof(load_control));
        snprintf(detail, sizeof(detail), "ldmxcsr_emitter=%d mxcsr=0x%x; emitter-only probe", rc, state.fp.mxcsr);
    } else {
        state.gpr[0] = 0x28000000;
        const uint8_t add_float[] = {0x0f,0x58,0x00};
        rc = run_translation(&state, code, add_float, sizeof(add_float));
        snprintf(detail, sizeof(detail), "addps_emitter=%d; emitter-only probe", rc);
    }
    if (sceKernelMunmap(code, PAGE * 4)) rc = 1;
    if (vm.release(NULL, &data)) rc = 1;
    return rc;
}
#endif

int main(int argc, char **argv)
{
    case_name = "invalid";
    for (int i = 0; i + 1 < argc; ++i) {
        if (!strcmp(argv[i], "--case")) case_name = argv[i + 1];
    }
    record("start", "running", 0);
    int rc = 64;
    int exit_status = 0;
    if (!strcmp(case_name, "files")) rc = files();
    else if (!strcmp(case_name, "low-memory")) rc = low_memory();
    else if (!strcmp(case_name, "reserve-collision")) rc = reserve_collision();
    else if (!strcmp(case_name, "generated-code")) rc = generated_code(0);
    else if (!strcmp(case_name, "generated-rwx")) rc = generated_code(1);
    else if (!strcmp(case_name, "threads")) rc = threads(0);
    else if (!strcmp(case_name, "threads-adapter")) rc = threads(1);
    else if (!strcmp(case_name, "exceptions")) rc = exceptions();
    else if (!strcmp(case_name, "segments")) rc = segments();
    else if (!strcmp(case_name, "vm-backend")) rc = vm_backend();
    else if (!strcmp(case_name, "vm-ownership")) rc = vm_ownership();
    else if (!strcmp(case_name, "vm-stress")) rc = vm_stress();
    else if (!strcmp(case_name, "vm-enforcement")) rc = vm_enforcement();
    else if (!strcmp(case_name, "process-exit-zero")) rc = 0;
    else if (!strcmp(case_name, "process-exit-seven")) { rc = 0; exit_status = 7; }
#ifdef WITH_TRANSLATOR
    else if (!strcmp(case_name, "translator")) rc = translator(0);
    else if (!strcmp(case_name, "translator-rwx")) rc = translator(1);
    else if (!strcmp(case_name, "translator-control")) rc = translator_extended(0);
    else if (!strcmp(case_name, "translator-fp")) rc = translator_extended(1);
    else if (!strcmp(case_name, "translator-retranslate")) rc = translator_extended(2);
    else if (!strcmp(case_name, "translator-fp-control")) rc = translator_extended(3);
    else if (!strcmp(case_name, "translator-fp-add")) rc = translator_extended(4);
    else if (!strcmp(case_name, "translator-teb")) rc = probe_translator_teb(0, detail, sizeof(detail));
    else if (!strcmp(case_name, "translator-teb-threads")) rc = probe_translator_teb(1, detail, sizeof(detail));
    else if (!strcmp(case_name, "hostexec-fp")) rc = probe_hostexec(0, detail, sizeof(detail));
    else if (!strcmp(case_name, "hostexec-cache")) rc = probe_hostexec(1, detail, sizeof(detail));
    else if (!strcmp(case_name, "dispatcher-mixed")) rc = probe_dispatcher(0, detail, sizeof(detail));
    else if (!strcmp(case_name, "dispatcher-fault")) rc = probe_dispatcher(1, detail, sizeof(detail));
    else if (!strcmp(case_name, "dispatcher-stops")) rc = probe_dispatcher(2, detail, sizeof(detail));
    else if (!strcmp(case_name, "dispatcher-owner")) rc = probe_dispatcher(3, detail, sizeof(detail));
    else if (!strcmp(case_name, "pe-preferred")) rc = probe_pe32(0, detail, sizeof(detail), &exit_status);
    else if (!strcmp(case_name, "pe-relocated")) rc = probe_pe32(1, detail, sizeof(detail), &exit_status);
    else if (!strcmp(case_name, "pe-invalid")) rc = probe_pe32(2, detail, sizeof(detail), &exit_status);
    else if (!strcmp(case_name, "pe-collision")) rc = probe_pe32(3, detail, sizeof(detail), &exit_status);
    else if (!strcmp(case_name, "pe-fourk-preferred")) rc = probe_pe32(4, detail, sizeof(detail), &exit_status);
    else if (!strcmp(case_name, "pe-fourk-relocated")) rc = probe_pe32(5, detail, sizeof(detail), &exit_status);
    else if (!strcmp(case_name, "pe-subpage")) rc = probe_pe32(6, detail, sizeof(detail), &exit_status);
    else if (!strcmp(case_name, "console-bare")) rc = probe_console(detail, sizeof(detail), &exit_status);
    else if (!strcmp(case_name, "lifecycle-host")) rc = probe_lifecycle_host(detail, sizeof(detail), &exit_status);
    else if (!strcmp(case_name, "console32")) rc = probe_console32(detail, sizeof(detail), &exit_status);
    else if (!strcmp(case_name, "pe-dll-preferred")) rc = probe_dll(0, detail, sizeof(detail), &exit_status);
    else if (!strcmp(case_name, "pe-dll-relocated")) rc = probe_dll(1, detail, sizeof(detail), &exit_status);
    else if (!strcmp(case_name, "pe-dll-missing")) rc = probe_dll(2, detail, sizeof(detail), &exit_status);
    else if (!strcmp(case_name, "pe-dll-symbol")) rc = probe_dll(3, detail, sizeof(detail), &exit_status);
    else if (!strcmp(case_name, "pe-dll-ordinal")) rc = probe_dll(4, detail, sizeof(detail), &exit_status);
    else if (!strcmp(case_name, "pe-dll-invalid")) rc = probe_dll(5, detail, sizeof(detail), &exit_status);
    else if (!strcmp(case_name, "pe-dll-dependency")) rc = probe_dll(6, detail, sizeof(detail), &exit_status);
    else if (!strcmp(case_name, "pe-init-order")) rc = probe_lifecycle(0, detail, sizeof(detail));
    else if (!strcmp(case_name, "pe-init-relocated")) rc = probe_lifecycle(1, detail, sizeof(detail));
    else if (!strcmp(case_name, "pe-init-failure")) rc = probe_lifecycle(2, detail, sizeof(detail));
    else if (!strcmp(case_name, "pe-tls-threads")) rc = probe_lifecycle(3, detail, sizeof(detail));
    else if (!strcmp(case_name, "pe-tls-invalid")) rc = probe_lifecycle(4, detail, sizeof(detail));
    else if (!strcmp(case_name, "pe-process")) rc = probe_process(0, detail, sizeof(detail));
    else if (!strcmp(case_name, "pe-process-relocated")) rc = probe_process(1, detail, sizeof(detail));
    else if (!strcmp(case_name, "pe-process-collision")) rc = probe_process(2, detail, sizeof(detail));
    else if (!strcmp(case_name, "wine-ntdll")) rc = probe_wine(0, detail, sizeof(detail));
    else if (!strcmp(case_name, "wine-kernelbase")) rc = probe_wine(1, detail, sizeof(detail));
    else if (!strcmp(case_name, "wine-kernel")) rc = probe_wine(2, detail, sizeof(detail));
#ifdef WITH_WINE_PLATFORM
    else if (!strcmp(case_name, "wine-memory")) rc = probe_wine_platform(0, detail, sizeof(detail));
    else if (!strcmp(case_name, "wine-paths")) rc = probe_wine_platform(1, detail, sizeof(detail));
    else if (!strcmp(case_name, "wine-unsupported")) rc = probe_wine_platform(2, detail, sizeof(detail));
#endif
#endif
    record("result", rc == 0 ? "passed" : (rc == PW_ERR_UNSUPPORTED ? "blocked" : "failed"), rc);
    return rc == 0 ? exit_status : 1;
}
