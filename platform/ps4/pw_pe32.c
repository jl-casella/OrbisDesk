/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "pw_pe32.h"
#include "pw_pe32_internal.h"
#include <string.h>

static uint16_t rd16(const uint8_t *p) { return (uint16_t)(p[0] | p[1] << 8); }
static uint32_t rd32(const uint8_t *p)
{
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}
static void wr32(uint8_t *p, uint32_t value)
{
    for (unsigned i = 0; i < 4; ++i) p[i] = (uint8_t)(value >> (8 * i));
}
static int range(uint64_t offset, uint64_t count, uint64_t limit)
{
    return offset <= limit && count <= limit - offset;
}
static const PwPe32Section *section_at(const PwPe32Info *info, uint32_t rva, uint32_t bytes)
{
    for (unsigned i = 0; i < info->section_count; ++i) {
        const PwPe32Section *s = &info->sections[i];
        if (rva >= s->rva && range((uint64_t)rva - s->rva, bytes, s->bytes)) return s;
    }
    return NULL;
}
const uint8_t *pw_pe32_file_rva(const uint8_t *file, const PwPe32Info *info, uint32_t rva, uint32_t bytes)
{
    const PwPe32Section *s = section_at(info, rva, bytes);
    if (!s || !range((uint64_t)rva - s->rva, bytes, s->raw_bytes)) return NULL;
    return file + s->raw_offset + (rva - s->rva);
}
static int relocation_targets(const uint8_t *file, PwPe32Info *info, uint32_t targets[4096])
{
    if (!info->reloc_bytes) return PW_OK;
    const uint8_t *table = pw_pe32_file_rva(file, info, info->reloc_rva, info->reloc_bytes);
    if (!table || info->reloc_bytes > 0x10000) return PW_ERR_MALFORMED;
    uint32_t cursor = 0, count = 0;
    while (cursor < info->reloc_bytes) {
        if (!range(cursor, 8, info->reloc_bytes)) return PW_ERR_MALFORMED;
        uint32_t page = rd32(table + cursor), block = rd32(table + cursor + 4);
        if (page % 0x1000 || block < 8 || block % 4 || !range(cursor, block, info->reloc_bytes)) return PW_ERR_MALFORMED;
        for (uint32_t at = 8; at < block; at += 2) {
            uint16_t item = rd16(table + cursor + at);
            unsigned type = item >> 12;
            if (!type) continue;
            if (type != 3) return PW_ERR_UNSUPPORTED;
            uint64_t target = (uint64_t)page + (item & 0xfff);
            if (target > UINT32_MAX || !section_at(info, (uint32_t)target, 4)) return PW_ERR_MALFORMED;
            if (target < (uint64_t)info->reloc_rva + info->reloc_bytes && target + 4 > info->reloc_rva) return PW_ERR_MALFORMED;
            if (count == 4096) return PW_ERR_LIMIT;
            for (unsigned i = 0; i < count; ++i)
                if (target < (uint64_t)targets[i] + 4 && target + 4 > targets[i]) return PW_ERR_MALFORMED;
            targets[count++] = (uint32_t)target;
        }
        cursor += block;
    }
    info->relocation_count = count;
    return PW_OK;
}

int pw_pe32_inspect(const void *input, size_t bytes, PwPe32Info *out)
{
    if (!input || !out) return PW_ERR_PRECONDITION;
    if (bytes > PW_PE32_MAX_FILE) return PW_ERR_LIMIT;
    const uint8_t *f = input;
    if (bytes < 64) return PW_ERR_TRUNCATED;
    if (f[0] != 'M' || f[1] != 'Z') return PW_ERR_NOT_PE;
    uint32_t pe = rd32(f + 0x3c);
    if (pe < 64 || !range(pe, 24, bytes)) return PW_ERR_TRUNCATED;
    if (memcmp(f + pe, "PE\0\0", 4)) return PW_ERR_NOT_PE;
    uint16_t count = rd16(f + pe + 6), opt_bytes = rd16(f + pe + 20), flags = rd16(f + pe + 22);
    if (rd16(f + pe + 4) != 0x14c || !(flags & 2)) return PW_ERR_UNSUPPORTED;
    if (!count || count > PW_PE32_MAX_SECTIONS) return PW_ERR_LIMIT;
    uint64_t opt_at = (uint64_t)pe + 24, table_at = opt_at + opt_bytes;
    if (opt_bytes < 96 || !range(opt_at, opt_bytes, bytes) || !range(table_at, count * 40u, bytes)) return PW_ERR_TRUNCATED;
    const uint8_t *o = f + opt_at;
    uint32_t section_align = rd32(o + 32);
    if (rd16(o) != 0x10b || (section_align != 0x1000 && section_align != PW_PE32_PAGE)) return PW_ERR_UNSUPPORTED;
    uint32_t file_align = rd32(o + 36), directories = rd32(o + 92);
    if (file_align < 512 || file_align > section_align || file_align & (file_align - 1)) return PW_ERR_MALFORMED;
    if (directories > 16 || !range(96, (uint64_t)directories * 8, opt_bytes)) return PW_ERR_MALFORMED;
    PwPe32Info info = {0};
    info.is_dll = !!(flags & 0x2000);
    info.section_alignment = section_align;
    info.preferred = rd32(o + 28); info.image_bytes = rd32(o + 56);
    info.header_bytes = rd32(o + 60); info.entry_rva = rd32(o + 16); info.section_count = count;
    if (!info.preferred || info.preferred % 0x10000 || !info.image_bytes || info.image_bytes > 0x2000000 ||
        info.image_bytes % section_align || (uint64_t)info.preferred + info.image_bytes > 0x100000000ull ||
        !info.header_bytes || info.header_bytes > section_align || info.header_bytes % file_align ||
        info.header_bytes < table_at + count * 40u || info.header_bytes > bytes) return PW_ERR_MALFORMED;
    info.header_mapped_bytes = (info.header_bytes + section_align - 1) & ~(section_align - 1);
    for (unsigned i = 0; i < count; ++i) {
        const uint8_t *h = f + table_at + i * 40;
        PwPe32Section *s = &info.sections[i];
        uint32_t virtual_bytes = rd32(h + 8), characteristics = rd32(h + 36);
        s->rva = rd32(h + 12); s->raw_bytes = rd32(h + 16); s->raw_offset = rd32(h + 20);
        s->bytes = virtual_bytes > s->raw_bytes ? virtual_bytes : s->raw_bytes;
        if (!s->bytes || s->bytes > info.image_bytes || s->rva < info.header_mapped_bytes || s->rva % section_align) return PW_ERR_MALFORMED;
        s->mapped_bytes = (s->bytes + section_align - 1) & ~(section_align - 1u);
        if (!range(s->rva, s->mapped_bytes, info.image_bytes)) return PW_ERR_MALFORMED;
        if (s->raw_bytes && (s->raw_offset < info.header_bytes || s->raw_offset % file_align ||
                            s->raw_bytes % file_align || !range(s->raw_offset, s->raw_bytes, bytes))) return PW_ERR_TRUNCATED;
        s->protection = (characteristics & 0x40000000 ? PW_PROT_READ : 0) |
                        (characteristics & 0x80000000 ? PW_PROT_READ | PW_PROT_WRITE : 0) |
                        (characteristics & 0x20000000 ? PW_PROT_READ | PW_PROT_EXEC : 0);
        if ((s->protection & (PW_PROT_WRITE | PW_PROT_EXEC)) == (PW_PROT_WRITE | PW_PROT_EXEC)) return PW_ERR_UNSUPPORTED;
        for (unsigned j = 0; j < i; ++j) {
            const PwPe32Section *p = &info.sections[j];
            if (s->rva < (uint64_t)p->rva + p->mapped_bytes && (uint64_t)s->rva + s->mapped_bytes > p->rva) return PW_ERR_MALFORMED;
            if (s->raw_bytes && p->raw_bytes && s->raw_offset < (uint64_t)p->raw_offset + p->raw_bytes &&
                (uint64_t)s->raw_offset + s->raw_bytes > p->raw_offset) return PW_ERR_MALFORMED;
        }
    }
    const PwPe32Section *entry = section_at(&info, info.entry_rva, 1);
    if ((!info.is_dll || info.entry_rva) && (!entry || !(entry->protection & PW_PROT_EXEC))) return PW_ERR_MALFORMED;
    for (unsigned i = 0; i < directories; ++i) {
        uint32_t rva = rd32(o + 96 + i * 8), length = rd32(o + 100 + i * 8);
        if (!rva && !length) continue;
        if (!rva || !length) return PW_ERR_MALFORMED;
        if (i == 5) { info.reloc_rva = rva; info.reloc_bytes = length; continue; }
        if (i == 0) { info.export_rva = rva; info.export_bytes = length; }
        else if (i == 1) { info.import_rva = rva; info.import_bytes = length; }
        else if (i == 12) { info.iat_rva = rva; info.iat_bytes = length; }
        else if (i == 9) { info.tls_rva = rva; info.tls_bytes = length; }
        else return PW_ERR_UNSUPPORTED;
    }
    if ((flags & 1) && info.reloc_bytes) return PW_ERR_MALFORMED;
    uint32_t targets[4096];
    int rc = relocation_targets(f, &info, targets);
    if (!rc) rc = pw_pe32_parse_tables(f, &info);
    if (rc) return rc;
    *out = info;
    return PW_OK;
}

static void plan_pages(PwPe32Image *image)
{
    uint8_t contributors[PW_PE32_MAX_PAGES] = {0}, readonly[PW_PE32_MAX_PAGES] = {0};
    image->page_count = (image->info.image_bytes + PW_PE32_PAGE - 1) / PW_PE32_PAGE;
    for (unsigned i = 0; i <= image->info.section_count; ++i) {
        uint32_t rva = i ? image->info.sections[i - 1].rva : 0;
        uint32_t span = i ? image->info.sections[i - 1].mapped_bytes : image->info.header_mapped_bytes;
        unsigned prot = i ? image->info.sections[i - 1].protection : PW_PROT_READ;
        unsigned first = rva / PW_PE32_PAGE, last = (rva + span - 1) / PW_PE32_PAGE;
        for (unsigned p = first; p <= last; ++p) {
            image->page_occupied[p] = 1;
            /* Original IA-32 bytes are read as data; only the separate JIT
             * cache is executed by the x86-64 host. */
            image->page_permissions[p] |= prot & (PW_PROT_READ | PW_PROT_WRITE);
            contributors[p]++;
            if (!(prot & PW_PROT_WRITE)) readonly[p] = 1;
        }
    }
    for (unsigned p = 0; p < image->page_count; ++p) {
        if (contributors[p] > 1) image->shared_pages++;
        if (readonly[p] && (image->page_permissions[p] & PW_PROT_WRITE)) image->widened_pages++;
    }
}

int pw_pe32_load(const PwVmBackend *vm, const void *file, size_t bytes, uint32_t address, PwPe32Image *out)
{
    if (!out || !pw_vm_backend_valid(vm) || vm->page_bytes != PW_PE32_PAGE ||
        !(vm->capabilities & PW_VM_CAP_EXACT_ADDRESS) || !vm->reserve_at ||
        vm->capabilities & PW_VM_CAP_ALIASED_EXEC) return PW_ERR_PRECONDITION;
    PwPe32Image image = {0};
    int rc = pw_pe32_inspect(file, bytes, &image.info);
    if (rc) return rc;
    image.backend = *vm; image.base = address ? address : image.info.preferred;
    if (image.base % 0x10000 || (uint64_t)image.base + image.info.image_bytes > 0x100000000ull) return PW_ERR_PRECONDITION;
    if (image.base != image.info.preferred && !image.info.relocation_count) return PW_ERR_UNSUPPORTED;
    plan_pages(&image);
    rc = vm->reserve_at(vm->context, image.base, image.page_count * PW_PE32_PAGE, PW_PE32_PAGE, &image.region);
    if (rc) return rc;
    uint8_t *mapped = image.region.write_base;
    for (unsigned p = 0; !rc && p < image.page_count; ++p) {
        if (!image.page_occupied[p]) continue;
        rc = vm->commit(vm->context, &image.region, p * PW_PE32_PAGE, PW_PE32_PAGE, 3);
        if (!rc) memset(mapped + p * PW_PE32_PAGE, 0, PW_PE32_PAGE);
    }
    if (!rc) memcpy(mapped, file, image.info.header_bytes);
    for (unsigned i = 0; !rc && i < image.info.section_count; ++i) {
        const PwPe32Section *s = &image.info.sections[i];
        if (s->raw_bytes) memcpy(mapped + s->rva, (const uint8_t *)file + s->raw_offset, s->raw_bytes);
    }
    if (!rc && image.base != image.info.preferred) {
        uint32_t targets[4096];
        rc = relocation_targets(file, &image.info, targets);
        for (unsigned i = 0; !rc && i < image.info.relocation_count; ++i) {
            uint8_t *p = mapped + targets[i];
            wr32(p, rd32(p) + (image.base - image.info.preferred));
            image.relocations_applied++;
        }
    }
    for (unsigned p = 0; !rc && p < image.page_count; ++p) {
        if (image.page_occupied[p])
            rc = vm->protect(vm->context, &image.region, p * PW_PE32_PAGE, PW_PE32_PAGE, image.page_permissions[p]);
    }
    if (rc) { vm->release(vm->context, &image.region); return rc; }
    image.entry = image.info.entry_rva ? image.base + image.info.entry_rva : 0;
    image.linked = !image.info.import_count;
    image.init_state = image.info.is_dll && (image.entry || image.info.tls_bytes) ? 0 : 2;
    *out = image;
    return PW_OK;
}

int pw_pe32_source(void *opaque, uint32_t pc, const uint8_t **source, size_t *bytes)
{
    const PwPe32Image *image = opaque;
    if (!image || !image->region.handle || !source || !bytes) return PW_ERR_PRECONDITION;
    if (!image->linked) return PW_ERR_STATE;
    if (image->init_state != 1 && image->init_state != 2) return PW_ERR_STATE;
    if (pc < image->base) return PW_ERR_NOT_FOUND;
    uint32_t rva = pc - image->base;
    const PwPe32Section *s = section_at(&image->info, rva, 1);
    if (!s || !(s->protection & PW_PROT_EXEC)) return PW_ERR_NOT_FOUND;
    *source = (const uint8_t *)image->region.exec_base + rva;
    *bytes = s->bytes - (rva - s->rva);
    return PW_OK;
}

int pw_pe32_bind(const PwPe32Image *image, PwX86State *state)
{
    if (!image || !image->region.handle || !state) return PW_ERR_PRECONDITION;
    if (!image->linked) return PW_ERR_STATE;
    if (state->memory_count > PW_X86_MEMORY_REGIONS - image->info.section_count - 1) return PW_ERR_LIMIT;
    state->memory[state->memory_count++] = (PwX86Memory){image->base, (uint64_t)image->base + image->info.header_mapped_bytes, PW_X86_READ};
    for (unsigned i = 0; i < image->info.section_count; ++i) {
        const PwPe32Section *s = &image->info.sections[i];
        state->memory[state->memory_count++] = (PwX86Memory){image->base + s->rva,
            (uint64_t)image->base + s->rva + s->mapped_bytes, s->protection};
    }
    if (!image->info.is_dll) state->eip = image->entry;
    return PW_OK;
}

int pw_pe32_unload(PwPe32Image *image)
{
    if (!image || !image->region.handle) return PW_ERR_PRECONDITION;
    if (image->lifecycle_owner) return PW_ERR_STATE;
    int rc = image->backend.release(image->backend.context, &image->region);
    if (!rc) memset(image, 0, sizeof(*image));
    return rc;
}
