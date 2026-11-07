/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "pw_pe32.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int inspect(const uint8_t *file, size_t bytes)
{
    PwPe32Info info, before;
    memset(&info, 0x5a, sizeof(info)); before = info;
    int rc = pw_pe32_inspect(file, bytes, &info);
    if (rc) assert(!memcmp(&info, &before, sizeof(info)));
    else {
        assert(info.section_count && info.section_count <= PW_PE32_MAX_SECTIONS);
        assert(info.header_bytes <= bytes);
        for (unsigned i = 0; i < info.section_count; ++i) {
            const PwPe32Section *s = &info.sections[i];
            assert((uint64_t)s->rva + s->mapped_bytes <= info.image_bytes);
            assert(!s->raw_bytes || (uint64_t)s->raw_offset + s->raw_bytes <= bytes);
        }
    }
    return rc;
}

int main(int argc, char **argv)
{
    assert(argc == 2);
    FILE *stream = fopen(argv[1], "rb"); assert(stream);
    assert(!fseek(stream, 0, SEEK_END));
    long length = ftell(stream); assert(length > 0 && length <= PW_PE32_MAX_FILE);
    rewind(stream);
    uint8_t *file = malloc((size_t)length); assert(file);
    assert(fread(file, 1, (size_t)length, stream) == (size_t)length);
    assert(!fclose(stream));
    PwPe32Info info;
    assert(!pw_pe32_inspect(file, (size_t)length, &info));
    assert(info.relocation_count);
    if (strstr(argv[1], "imports32")) assert(info.import_count == 2 && !info.is_dll);
    else if (strstr(argv[1], "testmath")) assert(info.is_dll && info.export_count == 2 && !info.import_count);
    else if (strstr(argv[1], "nested")) assert(info.is_dll && info.import_count == 1);
    else if (strstr(argv[1], "lifecycle")) assert(info.is_dll && info.tls_callback_count == 1 && info.tls_template_bytes == 24 && info.tls_zero_bytes == 0);
    else assert(info.relocation_count == 5 && info.preferred == 0x30000000 && !info.import_count);
    unsigned zero_fill_rejections = 0;
    if (info.tls_bytes) {
        for (unsigned i = 0; i < info.section_count; ++i) {
            const PwPe32Section *s = &info.sections[i];
            if (info.tls_rva < s->rva || info.tls_rva - s->rva >= s->raw_bytes) continue;
            uint8_t *field = file + s->raw_offset + info.tls_rva - s->rva + 16;
            uint32_t saved, unsupported = 8;
            memcpy(&saved, field, 4); memcpy(field, &unsupported, 4);
            assert(inspect(file, (size_t)length) == PW_ERR_UNSUPPORTED);
            memcpy(field, &saved, 4);
            zero_fill_rejections++;
        }
        assert(zero_fill_rejections == 1);
    }
    size_t required = info.header_bytes;
    for (unsigned i = 0; i < info.section_count; ++i) {
        size_t end = (size_t)info.sections[i].raw_offset + info.sections[i].raw_bytes;
        if (end > required) required = end;
    }
    for (size_t n = 0; n < (size_t)length; ++n) {
        int rc = inspect(file, n);
        if (n < required) assert(rc);
    }
    unsigned mutations = 0;
    for (size_t at = 0; at < info.header_bytes; ++at) {
        for (unsigned bit = 0; bit < 8; ++bit) {
            file[at] ^= (uint8_t)(1u << bit);
            inspect(file, (size_t)length);
            file[at] ^= (uint8_t)(1u << bit);
            mutations++;
        }
    }
    for (unsigned i = 0; i < info.section_count; ++i) {
        const PwPe32Section *s = &info.sections[i];
        uint32_t rvas[] = {info.reloc_rva, info.import_rva, info.export_rva, info.tls_rva};
        uint32_t sizes[] = {info.reloc_bytes, info.import_bytes, info.export_bytes, info.tls_bytes};
        for (unsigned directory = 0; directory < 4; ++directory) {
        if (!sizes[directory] || rvas[directory] < s->rva || rvas[directory] - s->rva >= s->raw_bytes) continue;
        size_t raw = s->raw_offset + rvas[directory] - s->rva;
        for (unsigned at = 0; at < sizes[directory]; ++at) {
            uint8_t saved = file[raw + at];
            file[raw + at] = 0xff;
            inspect(file, (size_t)length);
            file[raw + at] = saved;
            mutations++;
        }
        }
    }
    free(file);
    printf("{\"status\":\"passed\",\"environment\":\"WSL host parser, not PS4\","
           "\"truncations\":%ld,\"mutations\":%u,\"zero_fill_rejections\":%u}\n", length, mutations, zero_fill_rejections);
    return 0;
}
