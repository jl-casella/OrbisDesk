/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "pw_pe32_internal.h"
#include "pw_cpu_ps4.h"
#include "pw_vm_ps4.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static uint8_t *read_file(const char *path, size_t *bytes)
{
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;
    int rc = fseek(f, 0, SEEK_END);
    long size = ftell(f);
    if (size <= 0 || size > PW_PE32_MAX_FILE) rc = 1;
    if (!rc) rc = fseek(f, 0, SEEK_SET);
    uint8_t *data = !rc ? malloc((size_t)size) : NULL;
    if (!data) rc = 1;
    if (!rc && fread(data, 1, (size_t)size, f) != (size_t)size) rc = 1;
    if (fclose(f)) rc = 1;
    if (rc) { free(data); return NULL; }
    *bytes = (size_t)size;
    return data;
}
static uint32_t rd(const void *p) { uint32_t v; memcpy(&v, p, 4); return v; }
static void wr(void *p, uint32_t v) { memcpy(p, &v, 4); }

static int invalid_tables(uint8_t *exe, size_t exe_bytes, uint8_t *dll, size_t dll_bytes, unsigned *checks)
{
    PwPe32Info info;
    int rc = pw_pe32_inspect(exe, exe_bytes, &info);
    if (rc || info.import_count != 2) return 1;
    uint8_t *descriptor = (uint8_t *)pw_pe32_file_rva(exe, &info, info.import_rva, 20);
    uint32_t saved = rd(descriptor + 16);
    wr(descriptor + 16, 0xfffffffcu);
    rc = pw_pe32_inspect(exe, exe_bytes, &info);
    wr(descriptor + 16, saved);
    if (rc != PW_ERR_MALFORMED) return 1;
    (*checks)++;
    if (pw_pe32_inspect(dll, dll_bytes, &info)) return 1;
    uint8_t *exports = (uint8_t *)pw_pe32_file_rva(dll, &info, info.export_rva, 40);
    uint8_t *eat = (uint8_t *)pw_pe32_file_rva(dll, &info, rd(exports + 28), 4);
    uint8_t *ord = (uint8_t *)pw_pe32_file_rva(dll, &info, rd(exports + 36), 2);
    uint32_t eat_saved = rd(eat);
    wr(eat, info.export_rva);
    rc = pw_pe32_inspect(dll, dll_bytes, &info);
    wr(eat, eat_saved);
    if (rc != PW_ERR_UNSUPPORTED) return 1;
    (*checks)++;
    uint16_t ordinal; memcpy(&ordinal, ord, 2);
    memset(ord, 0xff, 2);
    rc = pw_pe32_inspect(dll, dll_bytes, &info);
    memcpy(ord, &ordinal, 2);
    if (rc != PW_ERR_MALFORMED) return 1;
    (*checks)++;
    uint32_t pointer_saved = rd(exports + 32);
    wr(exports + 32, 0xfffffffcu);
    rc = pw_pe32_inspect(dll, dll_bytes, &info);
    wr(exports + 32, pointer_saved);
    if (rc != PW_ERR_MALFORMED) return 1;
    (*checks)++;
    uint32_t pe = rd(dll + 0x3c), entry = rd(dll + pe + 24 + 16);
    wr(dll + pe + 24 + 16, info.image_bytes + 0x1000);
    rc = pw_pe32_inspect(dll, dll_bytes, &info);
    wr(dll + pe + 24 + 16, entry);
    if (rc != PW_ERR_MALFORMED) return 1;
    (*checks)++;
    return 0;
}
typedef struct Trace {
    PwPe32Modules set;
    uint32_t dll_base;
    unsigned exports_seen;
} Trace;
static int source_view(void *opaque, uint32_t pc, const uint8_t **source, size_t *bytes)
{
    Trace *trace = opaque;
    const PwPe32Image *dll = trace->set.modules[1].image;
    for (unsigned i = 0; i < dll->info.export_count; ++i) {
        const PwPe32Export *e = &dll->info.exports[i];
        if (pc == trace->dll_base + e->rva) trace->exports_seen |= e->ordinal == 7 ? 1u : e->ordinal == 11 ? 2u : 0u;
    }
    return pw_pe32_modules_source(&trace->set, pc, source, bytes);
}

int probe_dll(int kind, char *detail, size_t capacity, int *exit_status)
{
    size_t exe_bytes = 0, dll_bytes = 0;
    uint8_t *exe = read_file("/data/imports32.exe", &exe_bytes);
    uint8_t *dll = read_file(kind == 6 ? "/data/nested.dll" : "/data/testmath.dll", &dll_bytes);
    int rc = exe && dll ? 0 : 1;
    PwVmBackend vm;
    PwPe32Image images[2] = {0};
    PwVmRegion stack = {0};
    PwPs4Cpu *cpu = NULL;
    PwPe32LinkReport report = {0};
    unsigned checks = 0, returned = 0, seen = 0, fixups = 0;
    if (!rc) rc = pw_vm_ps4_backend(&vm);
    if (!rc && kind == 5) rc = invalid_tables(exe, exe_bytes, dll, dll_bytes, &checks);
    if (!rc && kind != 5) {
        PwPe32Info info;
        rc = pw_pe32_inspect(exe, exe_bytes, &info);
        for (unsigned i = 0; !rc && i < info.import_count; ++i) {
            const PwPe32Import *item = &info.imports[i];
            if (kind == 3 && !item->by_ordinal) {
                uint8_t *name = (uint8_t *)pw_pe32_file_rva(exe, &info, item->name_rva, 1);
                *name = 'X';
            }
            if (kind == 4 && item->by_ordinal) {
                wr((void *)pw_pe32_file_rva(exe, &info, item->lookup_rva, 4), 0x80000008);
                wr((void *)pw_pe32_file_rva(exe, &info, item->iat_rva, 4), 0x80000008);
            }
        }
        if (!rc && kind == 6) {
            uint8_t *name = (uint8_t *)pw_pe32_file_rva(exe, &info, info.imports[0].module_rva, 13);
            if (!name) rc = 1; else { memset(name, 0, 13); memcpy(name, "nested.dll", 11); }
        }
        if (!rc) rc = pw_pe32_load(&vm, exe, exe_bytes, kind == 1 ? 0x34000000 : 0, &images[0]);
        if (!rc) rc = pw_pe32_load(&vm, dll, dll_bytes, kind == 1 ? 0x36000000 : 0, &images[1]);
        if (!rc && (images[0].info.import_count != 2 || !images[1].info.is_dll)) rc = 1;
        uint32_t before[PW_PE32_MAX_IMPORTS] = {0};
        for (unsigned i = 0; !rc && i < images[0].info.import_count; ++i)
            before[i] = rd((const uint8_t *)images[0].region.write_base + images[0].info.imports[i].iat_rva);
        PwPe32Module modules[] = {{"imports32.exe", &images[0]}, {kind == 6 ? "nested.dll" : "TESTMATH.DLL", &images[1]}};
        if (!rc) {
            const uint8_t *source; size_t bytes;
            if (pw_pe32_source(&images[0], images[0].entry, &source, &bytes) != PW_ERR_STATE) rc = 1;
        }
        if (!rc) {
            int result = pw_pe32_link(&images[0], kind == 2 ? NULL : modules + 1, kind == 2 ? 0 : 1, &report);
            int expected = kind == 2 || kind == 3 || kind == 4 ? PW_ERR_NOT_FOUND : kind == 6 ? PW_ERR_UNSUPPORTED : PW_OK;
            if (result != expected || report.code != expected) rc = 1;
            if (expected) {
                for (unsigned i = 0; i < images[0].info.import_count; ++i)
                    if (rd((const uint8_t *)images[0].region.write_base + images[0].info.imports[i].iat_rva) != before[i]) rc = 1;
                if (images[0].linked || !report.module[0]) rc = 1;
                if (kind == 3 && strcmp(report.symbol, "Xcale")) rc = 1;
                if (kind == 4 && report.ordinal != 8) rc = 1;
                if (!rc) checks++;
            } else if (report.named != 1 || report.by_ordinal != 1) rc = 1;
        }
        if (!rc && kind < 2) {
            for (unsigned i = 0; i < images[0].info.import_count; ++i) {
                const PwPe32Import *import = &images[0].info.imports[i];
                uint32_t expected = 0;
                for (unsigned j = 0; j < images[1].info.export_count; ++j) {
                    const PwPe32Export *symbol = &images[1].info.exports[j];
                    if (import->by_ordinal ? symbol->ordinal == import->ordinal : !strcmp(symbol->name, import->name)) expected = images[1].base + symbol->rva;
                }
                if (!expected || rd((const uint8_t *)images[0].region.write_base + import->iat_rva) != expected) rc = 1;
            }
            fixups = images[0].relocations_applied + images[1].relocations_applied;
            if (kind == 1 && !fixups) rc = 1;
            if (!rc) rc = vm.reserve_at(NULL, 0x38000000, PW_PE32_PAGE, PW_PE32_PAGE, &stack);
            if (!rc) rc = vm.commit(NULL, &stack, 0, stack.bytes, 3);
            Trace trace = {{modules, 2}, images[1].base, 0};
            if (!rc) rc = pw_cpu_ps4_create(&cpu, &vm, source_view, &trace);
            if (!rc) {
                PwX86State *state = pw_cpu_ps4_state(cpu);
                state->stack_low = 0x38000000; state->stack_high = 0x38004000;
                state->gpr[4] = state->stack_high - 4;
                *(uint32_t *)(uintptr_t)state->gpr[4] = 0x0badf00d;
                state->memory[state->memory_count++] = (PwX86Memory){state->stack_low, state->stack_high, 3};
                state->gpr[3] = 0x11223344; state->gpr[5] = 0x55667788;
                state->gpr[6] = 0x12345678; state->gpr[7] = 0x87654321;
                rc = pw_pe32_bind(&images[1], state);
                if (!rc) rc = pw_pe32_bind(&images[0], state);
                if (!rc) rc = pw_cpu_ps4_run(cpu, 0x0badf00d, 64);
                returned = state->gpr[0]; seen = trace.exports_seen;
                if (!rc && (returned != 42 || seen != 3 || state->gpr[4] != state->stack_high ||
                            state->gpr[3] != 0x11223344 || state->gpr[5] != 0x55667788 ||
                            state->gpr[6] != 0x12345678 || state->gpr[7] != 0x87654321)) rc = 1;
                if (!rc) *exit_status = (int)returned;
            }
            if (cpu && pw_cpu_ps4_destroy(cpu)) rc = 1;
            cpu = NULL;
        }
    }
    if (cpu && pw_cpu_ps4_destroy(cpu)) rc = 1;
    if (stack.handle && vm.release(NULL, &stack)) rc = 1;
    for (unsigned i = 0; i < 2; ++i) if (images[i].region.handle && pw_pe32_unload(&images[i])) rc = 1;
    free(exe); free(dll);
    PwPs4VmStats memory = {0};
    if (pw_vm_ps4_stats(&memory) || memory.reservations || memory.committed_bytes) rc = 1;
    snprintf(detail, capacity, "kind=%d rc=%d return=%u named=%u ordinal=%u seen=%u fixups=%u checks=%u error=%d module=%s symbol=%s ordinal_error=%u live=%zu",
             kind, rc, returned, report.named, report.by_ordinal, seen, fixups, checks, report.code,
             report.module, report.symbol, report.ordinal, memory.reservations);
    return rc;
}
