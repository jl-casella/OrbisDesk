/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "pw_pe32.h"
#include "pw_cpu_ps4.h"
#include "pw_k32_ps4.h"
#include "pw_vm_ps4.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#include <orbis/libkernel.h>

static uint32_t read32(const uint8_t *p)
{
    uint32_t value; memcpy(&value, p, 4); return value;
}
static void write32(uint8_t *p, uint32_t value) { memcpy(p, &value, 4); }

static int rejection_tests(uint8_t *file, size_t bytes, unsigned *tested)
{
    PwPe32Info info;
    int rc = pw_pe32_inspect(file, bytes, &info);
    if (rc) return rc;
    uint32_t pe = read32(file + 0x3c), opt = pe + 24;
    uint32_t table = opt + (uint32_t)(file[pe + 20] | file[pe + 21] << 8);
    uint32_t reloc_raw = 0, imports_raw = 0;
    for (unsigned i = 0; i < info.section_count; ++i) {
        PwPe32Section *s = &info.sections[i];
        if (info.reloc_rva >= s->rva && info.reloc_rva < s->rva + s->raw_bytes)
            reloc_raw = s->raw_offset + info.reloc_rva - s->rva;
        uint32_t rva = read32(file + opt + 104);
        if (rva >= s->rva && rva < s->rva + s->raw_bytes) imports_raw = s->raw_offset + rva - s->rva;
    }
    if (!reloc_raw || !imports_raw || info.section_count < 2) return 1;
    struct Mutation { uint32_t offset, value; int expected; } cases[] = {
        {0,0,PW_ERR_NOT_PE}, {0x3c,UINT32_MAX,PW_ERR_TRUNCATED},
        {opt + 16,0,PW_ERR_MALFORMED}, {opt + 56,0xffffc000,PW_ERR_MALFORMED},
        {table + 40 + 12,info.sections[0].rva,PW_ERR_MALFORMED},
        {table + 20,0xfffffe00,PW_ERR_TRUNCATED},
        {reloc_raw + 4,7,PW_ERR_MALFORMED},
        {reloc_raw,0xfffff000,PW_ERR_MALFORMED},
        {imports_raw,1,PW_ERR_MALFORMED},
        {opt + 32,0x800,PW_ERR_UNSUPPORTED},
        {table + 36,0xe0000020,PW_ERR_UNSUPPORTED}
    };
    for (unsigned i = 0; i < sizeof(cases) / sizeof(cases[0]); ++i) {
        uint32_t saved = read32(file + cases[i].offset);
        write32(file + cases[i].offset, cases[i].value);
        PwPe32Info output, before;
        memset(&output, 0xa5, sizeof(output)); before = output;
        rc = pw_pe32_inspect(file, bytes, &output);
        write32(file + cases[i].offset, saved);
        if (rc != cases[i].expected || memcmp(&output, &before, sizeof(output))) return 1;
        (*tested)++;
    }
    if (pw_pe32_inspect(file, 63, &info) != PW_ERR_TRUNCATED) return 1;
    (*tested)++;
    return 0;
}

static int store_source(void *opaque, uint32_t pc, const uint8_t **source, size_t *bytes)
{
    (void)opaque;
    static const uint8_t store[] = {0x0f,0xae,0x18}; /* STMXCSR [eax] */
    static const uint8_t direct[] = {0x89,0x08}; /* MOV [eax], ecx */
    if (pc == 0x1000) { *source = store; *bytes = sizeof(store); }
    else if (pc == 0x2000) { *source = direct; *bytes = sizeof(direct); }
    else return PW_ERR_NOT_FOUND;
    return PW_OK;
}

static int subpage_checks(PwVmBackend *vm, PwPe32Image *image, unsigned *tested, PwPs4CpuStats *stats)
{
    uint32_t data = 0, crossing = 0;
    for (unsigned i = 0; i < image->info.section_count; ++i) {
        const PwPe32Section *s = &image->info.sections[i];
        if (!(s->protection & PW_PROT_WRITE)) continue;
        for (unsigned j = 0; j < image->info.section_count; ++j) {
            const PwPe32Section *next = &image->info.sections[j];
            if (s->rva + s->mapped_bytes == next->rva && !(next->protection & PW_PROT_WRITE)) {
                data = image->base + s->rva + 0x100;
                crossing = image->base + next->rva - 2;
                break;
            }
        }
        if (data) break;
    }
    if (!data || !(image->page_permissions[image->info.entry_rva / PW_PE32_PAGE] & PW_PROT_WRITE)) return 1;
    PwPs4Cpu *cpu = NULL;
    int rc = pw_cpu_ps4_create(&cpu, vm, store_source, NULL);
    if (rc) return rc;
    PwX86State *state = pw_cpu_ps4_state(cpu);
    rc = pw_pe32_bind(image, state);
    uint32_t targets[] = {image->entry, crossing};
    for (unsigned i = 0; !rc && i < 2; ++i) {
        uint32_t before = read32((const uint8_t *)(uintptr_t)targets[i]);
        state->eip = 0x1000; state->gpr[0] = targets[i];
        int refused = pw_cpu_ps4_step(cpu);
        if (refused != PW_ERR_VM || state->eip != 0x1000 || !state->fault_write || state->fault_width != 4 ||
            read32((const uint8_t *)(uintptr_t)targets[i]) != before) rc = 1;
        else (*tested)++;
    }
    for (unsigned i = 0; !rc && i < 2; ++i) {
        uint32_t before = read32((const uint8_t *)(uintptr_t)targets[i]);
        state->eip = 0x2000; state->gpr[0] = targets[i]; state->gpr[1] = 0xbad;
        int refused = pw_cpu_ps4_step(cpu);
        if (refused != PW_ERR_VM || state->eip != 0x2000 ||
            read32((const uint8_t *)(uintptr_t)targets[i]) != before) rc = 1;
        else (*tested)++;
    }
    if (!rc) {
        state->eip = 0x1000; state->gpr[0] = data;
        rc = pw_cpu_ps4_step(cpu);
        if (!rc && (state->eip != 0x1003 || read32((const uint8_t *)(uintptr_t)data) != state->fp.mxcsr)) rc = 1;
        if (!rc) (*tested)++;
    }
    if (!rc) {
        const uint8_t *source; size_t bytes;
        if (pw_pe32_source(image, data, &source, &bytes) != PW_ERR_NOT_FOUND) rc = 1;
        else (*tested)++;
    }
    if (pw_cpu_ps4_stats(cpu, stats)) rc = 1;
    if (!rc && (stats->host_attempts != 3 || stats->host_steps != 1 || stats->host_compiles != 1)) rc = 1;
    if (pw_cpu_ps4_destroy(cpu)) rc = 1;
    return rc;
}

int probe_pe32(int kind, char *detail, size_t capacity, int *exit_status)
{
    FILE *stream = fopen(kind >= 4 ? "/data/minimal4k32.exe" : "/data/minimal32.exe", "rb");
    if (!stream) { snprintf(detail, capacity, "cannot open minimal32.exe"); return 1; }
    int rc = fseek(stream, 0, SEEK_END);
    long length = ftell(stream);
    if (length <= 0 || length > PW_PE32_MAX_FILE) rc = 1;
    if (!rc) rc = fseek(stream, 0, SEEK_SET);
    uint8_t *file = !rc ? malloc((size_t)length) : NULL;
    if (!file) rc = 1;
    if (!rc && fread(file, 1, (size_t)length, stream) != (size_t)length) rc = 1;
    if (fclose(stream)) rc = 1;
    PwVmBackend vm;
    PwPe32Image image = {0};
    PwVmRegion stack = {0}, collision = {0};
    PwPs4Cpu *cpu = NULL;
    unsigned tested = 0;
    uint32_t returned = 0, base = 0, relocations = 0;
    unsigned shared = 0, widened = 0;
    PwPs4CpuStats stats = {0};
    if (!rc) rc = pw_vm_ps4_backend(&vm);
    if (!rc && kind == 2) rc = rejection_tests(file, (size_t)length, &tested);
    if (!rc && kind == 3) {
        PwPe32Info info;
        rc = pw_pe32_inspect(file, (size_t)length, &info);
        if (!rc) rc = vm.reserve_at(NULL, info.preferred, info.image_bytes, PW_PE32_PAGE, &collision);
        if (!rc) rc = vm.commit(NULL, &collision, 0, PW_PE32_PAGE, 3);
        if (!rc) {
            *(uint32_t *)collision.write_base = 0xfeed1234;
            int refused = pw_pe32_load(&vm, file, (size_t)length, 0, &image);
            if (refused != PW_ERR_VM || image.region.handle || *(uint32_t *)collision.write_base != 0xfeed1234) rc = 1;
            else tested = 1;
        }
    }
    if (!rc && (kind < 2 || kind >= 4)) {
        int relocated = kind == 1 || kind == 5;
        rc = pw_pe32_load(&vm, file, (size_t)length, relocated ? 0x34000000 : 0, &image);
        if (!rc) {
            base = image.base; relocations = image.relocations_applied;
            shared = image.shared_pages; widened = image.widened_pages;
            if ((relocated && (base == image.info.preferred || relocations != image.info.relocation_count || !relocations)) ||
                (!relocated && (base != image.info.preferred || relocations))) rc = 1;
            if (kind >= 4 && (!shared || !widened || image.info.section_alignment != 0x1000)) rc = 1;
            for (unsigned p = 0; p < image.page_count; ++p)
                if (image.page_permissions[p] & PW_PROT_EXEC) rc = 1;
        }
        if (!rc && kind == 6) rc = subpage_checks(&vm, &image, &tested, &stats);
    }
    if (!rc && (kind < 2 || kind == 4 || kind == 5)) {
        if (!rc) rc = vm.reserve_at(NULL, 0x38000000, PW_PE32_PAGE, PW_PE32_PAGE, &stack);
        if (!rc) rc = vm.commit(NULL, &stack, 0, stack.bytes, 3);
        if (!rc) rc = pw_cpu_ps4_create(&cpu, &vm, pw_pe32_source, &image);
        if (!rc) {
            PwX86State *state = pw_cpu_ps4_state(cpu);
            state->stack_low = 0x38000000; state->stack_high = 0x38004000;
            state->gpr[4] = state->stack_high - 4;
            *(uint32_t *)(uintptr_t)state->gpr[4] = 0x0badf00d;
            state->memory[state->memory_count++] = (PwX86Memory){state->stack_low, state->stack_high, 3};
            rc = pw_pe32_bind(&image, state);
            if (!rc) rc = pw_cpu_ps4_run(cpu, 0x0badf00d, 32);
            returned = state->gpr[0];
            if (!rc && (returned != 42 || state->gpr[4] != state->stack_high)) rc = 1;
            if (!rc) rc = pw_cpu_ps4_stats(cpu, &stats);
            if (!rc) *exit_status = (int)returned;
        }
    }
    if (cpu && pw_cpu_ps4_destroy(cpu)) rc = 1;
    if (stack.handle && vm.release(NULL, &stack)) rc = 1;
    if (collision.handle && vm.release(NULL, &collision)) rc = 1;
    if (image.region.handle && pw_pe32_unload(&image)) rc = 1;
    free(file);
    PwPs4VmStats memory = {0};
    if (pw_vm_ps4_stats(&memory) || memory.reservations || memory.committed_bytes) rc = 1;
    snprintf(detail, capacity, "kind=%d rc=%d base=0x%x entry_return=%u highlow_applied=%u checks=%u shared=%u widened=%u blocks=%llu host=%llu live=%zu",
             kind, rc, base, returned, relocations, tested, shared, widened, (unsigned long long)stats.translated_blocks,
             (unsigned long long)stats.host_steps, memory.reservations);
    return rc;
}

static void console_trace(void *opaque, const char *line)
{
    (void)opaque;
    char buffer[400];
    snprintf(buffer, sizeof(buffer), "%s\n", line);
    sceKernelDebugOutText(0, buffer);
}
static uint8_t *read_all(const char *path, size_t limit, size_t *size)
{
    FILE *stream = fopen(path, "rb");
    if (!stream) return NULL;
    int rc = fseek(stream, 0, SEEK_END);
    long length = ftell(stream);
    if (length < 0 || (size_t)length > limit) rc = 1;
    if (!rc) rc = fseek(stream, 0, SEEK_SET);
    uint8_t *data = !rc ? malloc((size_t)length + 1) : NULL;
    if (data && fread(data, 1, (size_t)length, stream) != (size_t)length) { free(data); data = NULL; }
    if (fclose(stream)) { free(data); data = NULL; }
    if (data) *size = (size_t)length;
    return data;
}
/* Loads /data/<name> at 0x30000000 and runs it on pw_k32_ps4 without Wine. */
static int run_exe(const char *name, const char *directory, PwK32Stats *stats, uint32_t *base, uint32_t *relocations)
{
    char path[96];
    snprintf(path, sizeof(path), "/data/%s", name);
    size_t bytes = 0;
    uint8_t *file = read_all(path, PW_PE32_MAX_FILE, &bytes);
    PwVmBackend vm;
    PwPe32Image image = {0};
    PwK32Process *process = NULL;
    int rc = file ? pw_vm_ps4_backend(&vm) : 1;
    if (!rc) rc = pw_pe32_load(&vm, file, bytes, 0x30000000, &image);
    free(file);
    if (!rc) rc = pw_k32_ps4_create(&process, &vm, 0x31000000, directory, "/data", console_trace, NULL);
    int run = !rc ? pw_k32_ps4_run(process, &image, name, 0x38000000, 0x3a000000, 1u << 20) : 0;
    if (process && pw_k32_ps4_stats(process, stats)) rc = 1;
    if (!rc) rc = run;
    *base = image.base; *relocations = image.relocations_applied;
    if (process && pw_k32_ps4_destroy(process)) rc = 1;
    if (image.region.handle && pw_pe32_unload(&image)) rc = 1;
    return rc;
}
typedef struct Expected { const char *name; unsigned count; } Expected;
/* Exact kernel32 call counts: the listed functions, and zero for every other. */
static int calls_match(const PwK32Stats *stats, const Expected *expected, unsigned count)
{
    for (unsigned i = 0; i < PW_K32_EXPORTS; ++i) {
        unsigned want = 0;
        for (unsigned j = 0; j < count; ++j) if (!strcmp(expected[j].name, pw_k32_ps4_export_name(i))) want = expected[j].count;
        if (stats->calls[i] != want) return 0;
    }
    return 1;
}
static unsigned total(const unsigned *calls, unsigned count)
{
    unsigned sum = 0;
    for (unsigned i = 0; i < count; ++i) sum += calls[i];
    return sum;
}

/* console32-bare.exe through the PE32 loader and pw_k32_ps4, without Wine.
 * The expected file is the Windows reference copied by the runner. */
int probe_console(char *detail, size_t capacity, int *exit_status)
{
    /* GetCurrentProcessId is only resolved, never called. */
    static const Expected expected[] = {{"CloseHandle", 2}, {"CreateFileA", 1}, {"CreateThread", 1}, {"ExitProcess", 1},
        {"FreeLibrary", 1}, {"GetExitCodeThread", 1}, {"GetProcAddress", 1}, {"LoadLibraryA", 1},
        {"WaitForSingleObject", 1}, {"WriteFile", 1}};
    size_t reference_bytes = 0, produced_bytes = 0;
    uint8_t *reference = read_all("/data/console-bare-reference.txt", 4096, &reference_bytes);
    mkdir("/data/orbisdesk", 0777);
    mkdir("/data/orbisdesk/console-bare", 0777);
    unlink("/data/orbisdesk/console-bare/result.txt");
    PwK32Stats stats = {0};
    uint32_t base = 0, relocations = 0;
    int rc = reference ? run_exe("console32-bare.exe", "/data/orbisdesk/console-bare", &stats, &base, &relocations) : 1;
    uint8_t *produced = read_all("/data/orbisdesk/console-bare/result.txt", 4096, &produced_bytes);
    int matches = produced && reference && produced_bytes == reference_bytes && !memcmp(produced, reference, produced_bytes);
    int calls_ok = calls_match(&stats, expected, sizeof(expected) / sizeof(expected[0])) && !total(stats.crt_calls, PW_MSVCRT_EXPORTS);
    if (!rc && (!stats.exited || stats.exit_code || !matches || !calls_ok || stats.refused ||
                stats.leaked_handles || stats.threads != 1 || stats.thread_failures)) rc = 1;
    if (stats.exited) *exit_status = (int)stats.exit_code;
    free(reference); free(produced);
    PwPs4VmStats memory = {0};
    if (pw_vm_ps4_stats(&memory) || memory.reservations || memory.committed_bytes) rc = 1;
    snprintf(detail, capacity, "rc=%d link=%d exited=%u exit=%u base=0x%x highlow_applied=%u calls_ok=%d k32_calls=%u threads=%u "
             "thread_failures=%u refused=%u leaked=%u steps=%llu written=%llu result=%s live=%zu",
             rc, (int)stats.link_rc, stats.exited, stats.exit_code, base, relocations, calls_ok,
             total(stats.calls, PW_K32_EXPORTS), stats.threads,
             stats.thread_failures, stats.refused, stats.leaked_handles, (unsigned long long)stats.steps,
             (unsigned long long)stats.bytes_written, matches ? "matches-windows-reference" : produced ? "differs" : "missing",
             memory.reservations);
    return rc;
}

/* lifecycle-host.exe: LoadLibraryA from /data with DllMain, TLS callbacks and
 * thread notifications; the EXE checks the event order itself and returns 42,
 * the native Windows result. */
int probe_lifecycle_host(char *detail, size_t capacity, int *exit_status)
{
    static const Expected expected[] = {{"CloseHandle", 1}, {"CreateThread", 1}, {"FreeLibrary", 1},
        {"GetExitCodeThread", 1}, {"GetLastError", 1}, {"GetProcAddress", 3}, {"LoadLibraryA", 2},
        {"SetLastError", 1}, {"WaitForSingleObject", 1}};
    PwK32Stats stats = {0};
    uint32_t base = 0, relocations = 0;
    mkdir("/data/orbisdesk", 0777);
    int rc = run_exe("lifecycle-host.exe", "/data/orbisdesk", &stats, &base, &relocations);
    int calls_ok = calls_match(&stats, expected, sizeof(expected) / sizeof(expected[0])) && !total(stats.crt_calls, PW_MSVCRT_EXPORTS);
    /* lifecycle.dll: attach, thread attach/detach, detach (2 each); the
     * rejected DLL: attach plus its cleanup detach. */
    if (!rc && (!stats.returned || stats.exit_code != 42 || !calls_ok || stats.refused ||
                stats.leaked_handles || stats.threads != 1 || stats.thread_failures || stats.modules_loaded != 1 ||
                stats.modules_unloaded != 1 || stats.dll_init_failures != 1 || stats.notifications != 12)) rc = 1;
    if (stats.exited || stats.returned) *exit_status = (int)stats.exit_code;
    PwPs4VmStats memory = {0};
    if (pw_vm_ps4_stats(&memory) || memory.reservations || memory.committed_bytes) rc = 1;
    snprintf(detail, capacity, "rc=%d link=%d returned=%u terminated=%u exit=%u base=0x%x highlow_applied=%u calls_ok=%d "
             "threads=%u thread_failures=%u loaded=%u unloaded=%u init_failures=%u notifications=%u refused=%u leaked=%u "
             "steps=%llu live=%zu",
             rc, (int)stats.link_rc, stats.returned, stats.exited, stats.exit_code, base, relocations, calls_ok,
             stats.threads, stats.thread_failures, stats.modules_loaded, stats.modules_unloaded, stats.dll_init_failures,
             stats.notifications, stats.refused, stats.leaked_handles, (unsigned long long)stats.steps, memory.reservations);
    return rc;
}

/* console32.exe: the same program with the mingw CRT (msvcrt.dll, static TLS,
 * critical sections). Output and exit code must match native Windows. */
int probe_console32(char *detail, size_t capacity, int *exit_status)
{
    size_t reference_bytes = 0, produced_bytes = 0;
    uint8_t *reference = read_all("/data/console32-reference.txt", 4096, &reference_bytes);
    mkdir("/data/orbisdesk", 0777);
    mkdir("/data/orbisdesk/console32", 0777);
    unlink("/data/orbisdesk/console32/result.txt");
    PwK32Stats stats = {0};
    uint32_t base = 0, relocations = 0;
    int rc = reference ? run_exe("console32.exe", "/data/orbisdesk/console32", &stats, &base, &relocations) : 1;
    uint8_t *produced = read_all("/data/orbisdesk/console32/result.txt", 4096, &produced_bytes);
    int matches = produced && reference && produced_bytes == reference_bytes && !memcmp(produced, reference, produced_bytes);
    /* mingw: 3 initializers, 2 _onexit handlers, 2 heap blocks for its argv
     * copy that it never frees, and 2 EXE TLS callbacks per notification
     * (process attach, thread attach/detach, process detach). */
    if (!rc && (!stats.exited || stats.exit_code || !matches || stats.refused || stats.leaked_handles ||
                stats.threads != 1 || stats.thread_failures || stats.initializers != 3 || stats.exit_handlers != 2 ||
                stats.heap_live_blocks != 2 || stats.notifications != 8)) rc = 1;
    if (stats.exited || stats.returned) *exit_status = (int)stats.exit_code;
    free(reference); free(produced);
    PwPs4VmStats memory = {0};
    if (pw_vm_ps4_stats(&memory) || memory.reservations || memory.committed_bytes) rc = 1;
    snprintf(detail, capacity, "rc=%d link=%d exited=%u returned=%u exit=%u base=0x%x highlow_applied=%u k32_calls=%u crt_calls=%u "
             "initializers=%u exit_handlers=%u heap_allocations=%u heap_live=%u crt_output=%u notifications=%u threads=%u "
             "thread_failures=%u refused=%u leaked=%u steps=%llu result=%s live=%zu",
             rc, (int)stats.link_rc, stats.exited, stats.returned, stats.exit_code, base, relocations,
             total(stats.calls, PW_K32_EXPORTS), total(stats.crt_calls, PW_MSVCRT_EXPORTS), stats.initializers,
             stats.exit_handlers, stats.heap_allocations, stats.heap_live_blocks, stats.crt_output_bytes, stats.notifications,
             stats.threads, stats.thread_failures, stats.refused, stats.leaked_handles, (unsigned long long)stats.steps,
             matches ? "matches-windows-reference" : produced ? "differs" : "missing", memory.reservations);
    return rc;
}
