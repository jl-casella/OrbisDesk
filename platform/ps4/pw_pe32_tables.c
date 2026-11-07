/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "pw_pe32_internal.h"
#include <string.h>

static uint16_t r16(const uint8_t *p) { return (uint16_t)(p[0] | p[1] << 8); }
static uint32_t r32(const uint8_t *p)
{
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}
static int text(const uint8_t *f, const PwPe32Info *info, uint32_t rva, char *out, unsigned capacity)
{
    for (unsigned i = 0; i < capacity; ++i) {
        if ((uint64_t)rva + i > UINT32_MAX) return PW_ERR_MALFORMED;
        const uint8_t *p = pw_pe32_file_rva(f, info, rva + i, 1);
        if (!p) return PW_ERR_MALFORMED;
        if (!*p) { out[i] = 0; return i ? PW_OK : PW_ERR_MALFORMED; }
        if (*p < 0x21 || *p > 0x7e) return PW_ERR_MALFORMED;
        out[i] = (char)*p;
    }
    return PW_ERR_LIMIT;
}
static int module_name(const char *name, char out[64])
{
    memset(out, 0, 64);
    unsigned n;
    for (n = 0; n < 64 && name[n]; ++n) {
        char c = name[n];
        if (c >= 'A' && c <= 'Z') c += 'a' - 'A';
        if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '_' || c == '-' || c == '.')) return PW_ERR_UNSUPPORTED;
        out[n] = c;
    }
    if (n == 64 || n < 5 || memcmp(out + n - 4, ".dll", 4)) return PW_ERR_UNSUPPORTED;
    out[n] = 0;
    return PW_OK;
}
static int writable(const PwPe32Info *info, uint32_t rva, uint32_t bytes)
{
    for (unsigned i = 0; i < info->section_count; ++i) {
        const PwPe32Section *s = &info->sections[i];
        if (rva >= s->rva && (uint64_t)rva + bytes <= (uint64_t)s->rva + s->bytes)
            return !!(s->protection & PW_PROT_WRITE);
    }
    return 0;
}
static int imports(const uint8_t *f, PwPe32Info *info)
{
    if (info->iat_bytes && (!pw_pe32_file_rva(f, info, info->iat_rva, info->iat_bytes) ||
                            !writable(info, info->iat_rva, info->iat_bytes))) return PW_ERR_MALFORMED;
    if (!info->import_bytes) return info->iat_bytes ? PW_ERR_MALFORMED : PW_OK;
    const uint8_t *directory = pw_pe32_file_rva(f, info, info->import_rva, info->import_bytes);
    if (!directory || info->import_bytes > 0x10000) return PW_ERR_MALFORMED;
    for (unsigned descriptor = 0; descriptor <= PW_PE32_MAX_MODULES; ++descriptor) {
        unsigned at = descriptor * 20;
        if ((uint64_t)at + 20 > info->import_bytes) return PW_ERR_MALFORMED;
        const uint8_t *d = directory + at;
        uint32_t lookup = r32(d), stamp = r32(d + 4), chain = r32(d + 8), name = r32(d + 12), iat = r32(d + 16);
        if (!(lookup | stamp | chain | name | iat)) return PW_OK;
        if (descriptor == PW_PE32_MAX_MODULES) return PW_ERR_LIMIT;
        if (!name || !iat || iat % 4 || lookup % 4) return PW_ERR_MALFORMED;
        if (stamp || chain) return PW_ERR_UNSUPPORTED;
        char raw_name[64], canonical[64];
        int rc = text(f, info, name, raw_name, sizeof(raw_name));
        if (!rc) rc = module_name(raw_name, canonical);
        if (rc) return rc;
        if (!lookup) lookup = iat;
        for (unsigned n = 0; n <= PW_PE32_MAX_IMPORTS; ++n) {
            uint64_t lookup_at = (uint64_t)lookup + n * 4, iat_at = (uint64_t)iat + n * 4;
            if (lookup_at > UINT32_MAX || iat_at > UINT32_MAX) return PW_ERR_MALFORMED;
            const uint8_t *l = pw_pe32_file_rva(f, info, (uint32_t)lookup_at, 4);
            const uint8_t *slot = pw_pe32_file_rva(f, info, (uint32_t)iat_at, 4);
            if (!l || !slot || !writable(info, (uint32_t)iat_at, 4)) return PW_ERR_MALFORMED;
            if (info->iat_bytes && (iat_at < info->iat_rva || iat_at + 4 > (uint64_t)info->iat_rva + info->iat_bytes)) return PW_ERR_MALFORMED;
            uint32_t value = r32(l);
            if (r32(slot) != value) return PW_ERR_UNSUPPORTED;
            if (!value) break;
            if (info->import_count == PW_PE32_MAX_IMPORTS) return PW_ERR_LIMIT;
            for (unsigned j = 0; j < info->import_count; ++j)
                if (info->imports[j].iat_rva == iat_at) return PW_ERR_MALFORMED;
            PwPe32Import *item = &info->imports[info->import_count++];
            memcpy(item->module, canonical, sizeof(canonical)); item->iat_rva = (uint32_t)iat_at;
            item->lookup_rva = (uint32_t)lookup_at;
            item->module_rva = name;
            if (value & 0x80000000u) {
                if (value & 0x7fff0000) return PW_ERR_MALFORMED;
                item->by_ordinal = 1; item->ordinal = value & 0xffff;
            } else {
                if (!pw_pe32_file_rva(f, info, value, 2) || value > UINT32_MAX - 2) return PW_ERR_MALFORMED;
                rc = text(f, info, value + 2, item->name, sizeof(item->name));
                item->name_rva = value + 2;
                if (rc) return rc;
            }
        }
    }
    return PW_ERR_LIMIT;
}
static int exports(const uint8_t *f, PwPe32Info *info)
{
    if (!info->export_bytes) return PW_OK;
    const uint8_t *d = pw_pe32_file_rva(f, info, info->export_rva, info->export_bytes);
    if (!d || info->export_bytes < 40 || r32(d)) return PW_ERR_MALFORMED;
    char dll[64], canonical[64];
    int rc = text(f, info, r32(d + 12), dll, sizeof(dll));
    if (!rc) rc = module_name(dll, canonical);
    if (rc) return rc;
    uint32_t base = r32(d + 16), functions = r32(d + 20), names = r32(d + 24);
    if (functions > PW_PE32_MAX_EXPORTS || names > functions) return PW_ERR_LIMIT;
    if ((uint64_t)base + functions > 0x10000) return PW_ERR_MALFORMED;
    const uint8_t *eat = pw_pe32_file_rva(f, info, r32(d + 28), functions * 4);
    const uint8_t *pointers = names ? pw_pe32_file_rva(f, info, r32(d + 32), names * 4) : NULL;
    const uint8_t *ordinals = names ? pw_pe32_file_rva(f, info, r32(d + 36), names * 2) : NULL;
    if ((functions && !eat) || (names && (!pointers || !ordinals))) return PW_ERR_MALFORMED;
    unsigned slots[PW_PE32_MAX_EXPORTS] = {0};
    for (unsigned i = 0; i < functions; ++i) {
        uint32_t rva = r32(eat + i * 4);
        if (!rva) continue;
        if (rva >= info->export_rva && (uint64_t)rva < (uint64_t)info->export_rva + info->export_bytes) return PW_ERR_UNSUPPORTED;
        int executable = 0;
        for (unsigned j = 0; j < info->section_count; ++j) {
            const PwPe32Section *s = &info->sections[j];
            if (rva >= s->rva && (uint64_t)rva < (uint64_t)s->rva + s->bytes && s->protection & PW_PROT_EXEC) executable = 1;
        }
        if (!executable) return PW_ERR_UNSUPPORTED;
        slots[i] = ++info->export_count;
        info->exports[slots[i] - 1].ordinal = base + i;
        info->exports[slots[i] - 1].rva = rva;
    }
    char previous[128] = {0};
    for (unsigned i = 0; i < names; ++i) {
        unsigned ordinal = r16(ordinals + i * 2);
        if (ordinal >= functions || !slots[ordinal]) return PW_ERR_MALFORMED;
        PwPe32Export *item = &info->exports[slots[ordinal] - 1];
        if (item->name[0]) return PW_ERR_UNSUPPORTED;
        rc = text(f, info, r32(pointers + i * 4), item->name, sizeof(item->name));
        if (rc) return rc;
        if (i && strcmp(previous, item->name) >= 0) return PW_ERR_MALFORMED;
        memcpy(previous, item->name, sizeof(previous));
    }
    return PW_OK;
}
int pw_pe32_parse_tables(const uint8_t *f, PwPe32Info *info)
{
    int rc = imports(f, info);
    if (!rc) rc = exports(f, info);
    if (rc || !info->tls_bytes) return rc;
    const uint8_t *tls = pw_pe32_file_rva(f, info, info->tls_rva, info->tls_bytes);
    if (!tls || info->tls_bytes != 24) return PW_ERR_MALFORMED;
    uint32_t start = r32(tls), end = r32(tls + 4), index = r32(tls + 8), callbacks = r32(tls + 12);
    uint32_t zero = r32(tls + 16), characteristics = r32(tls + 20);
    if (characteristics) return PW_ERR_UNSUPPORTED;
    if (end < start || end - start > 0x1000 || zero > 0x1000 - (end - start)) return PW_ERR_LIMIT;
    if (zero) return PW_ERR_UNSUPPORTED;
    if (start || end) {
        if (start < info->preferred || (uint64_t)end > (uint64_t)info->preferred + info->image_bytes) return PW_ERR_MALFORMED;
        info->tls_template_rva = start - info->preferred;
        info->tls_template_bytes = end - start;
        if (end != start && !pw_pe32_file_rva(f, info, info->tls_template_rva, end - start)) return PW_ERR_MALFORMED;
    }
    if (index < info->preferred || !writable(info, index - info->preferred, 4) || index % 4) return PW_ERR_MALFORMED;
    info->tls_index_rva = index - info->preferred;
    info->tls_zero_bytes = zero;
    if (callbacks) {
        if (callbacks < info->preferred || callbacks % 4) return PW_ERR_MALFORMED;
        for (unsigned i = 0; i <= 16; ++i) {
            uint64_t at = (uint64_t)(callbacks - info->preferred) + i * 4;
            if (at > UINT32_MAX) return PW_ERR_MALFORMED;
            const uint8_t *p = pw_pe32_file_rva(f, info, (uint32_t)at, 4);
            if (!p) return PW_ERR_MALFORMED;
            uint32_t target = r32(p);
            if (!target) return PW_OK;
            if (i == 16) return PW_ERR_LIMIT;
            if (target < info->preferred) return PW_ERR_MALFORMED;
            uint32_t rva = target - info->preferred;
            int executable = 0;
            for (unsigned j = 0; j < info->section_count; ++j) {
                const PwPe32Section *s = &info->sections[j];
                if (rva >= s->rva && (uint64_t)rva < (uint64_t)s->rva + s->bytes && (s->protection & PW_PROT_EXEC)) executable = 1;
            }
            if (!executable) return PW_ERR_MALFORMED;
            info->tls_callbacks[info->tls_callback_count++] = rva;
        }
    }
    return PW_OK;
}

int pw_pe32_link(PwPe32Image *image, const PwPe32Module *modules, size_t count, PwPe32LinkReport *report)
{
    if (!image || !image->region.handle || !report || (count && !modules)) return PW_ERR_PRECONDITION;
    memset(report, 0, sizeof(*report));
    if (count > PW_PE32_MAX_MODULES) return report->code = PW_ERR_LIMIT;
    if (image->linked && image->info.import_count) return report->code = PW_ERR_STATE;
    char names[PW_PE32_MAX_MODULES][64];
    for (size_t i = 0; i < count; ++i) {
        if (!modules[i].name || !modules[i].image || !modules[i].image->region.handle) return report->code = PW_ERR_PRECONDITION;
        int rc = module_name(modules[i].name, names[i]);
        if (rc) return report->code = rc;
        for (size_t j = 0; j < i; ++j) if (!strcmp(names[i], names[j])) return report->code = PW_ERR_MALFORMED;
    }
    uint32_t addresses[PW_PE32_MAX_IMPORTS];
    for (unsigned i = 0; i < image->info.import_count; ++i) {
        const PwPe32Import *item = &image->info.imports[i];
        memcpy(report->module, item->module, sizeof(report->module));
        memcpy(report->symbol, item->name, sizeof(report->symbol));
        report->ordinal = item->ordinal; report->iat_rva = item->iat_rva;
        const PwPe32Image *provider = NULL;
        for (size_t j = 0; j < count; ++j) if (!strcmp(item->module, names[j])) provider = modules[j].image;
        if (!provider) return report->code = PW_ERR_NOT_FOUND;
        if (!provider->info.is_dll || provider->info.import_count || !provider->linked) return report->code = PW_ERR_UNSUPPORTED;
        const PwPe32Export *symbol = NULL;
        for (unsigned j = 0; j < provider->info.export_count; ++j) {
            const PwPe32Export *candidate = &provider->info.exports[j];
            if (item->by_ordinal ? candidate->ordinal == item->ordinal : !strcmp(candidate->name, item->name)) symbol = candidate;
        }
        if (!symbol) return report->code = PW_ERR_NOT_FOUND;
        addresses[i] = provider->base + symbol->rva;
        if (item->by_ordinal) report->by_ordinal++; else report->named++;
    }
    for (unsigned i = 0; i < image->info.import_count; ++i)
        memcpy((uint8_t *)image->region.write_base + image->info.imports[i].iat_rva, &addresses[i], 4);
    image->linked = 1;
    report->module[0] = report->symbol[0] = 0; report->iat_rva = report->ordinal = 0;
    return PW_OK;
}

int pw_pe32_modules_source(void *opaque, uint32_t pc, const uint8_t **source, size_t *bytes)
{
    const PwPe32Modules *set = opaque;
    if (!set || !set->modules || set->count > PW_PE32_MAX_MODULES) return PW_ERR_PRECONDITION;
    for (size_t i = 0; i < set->count; ++i) {
        const PwPe32Image *image = set->modules[i].image;
        if (!image || !image->region.handle) return PW_ERR_STATE;
        if (pc >= image->base && (uint64_t)pc < (uint64_t)image->base + image->info.image_bytes)
            return pw_pe32_source(set->modules[i].image, pc, source, bytes);
    }
    return PW_ERR_NOT_FOUND;
}
