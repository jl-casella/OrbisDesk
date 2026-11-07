/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef PW_PE32_H
#define PW_PE32_H
#include "prospero_win_vm.h"
#include "pw_x86_block.h"
enum { PW_PE32_MAX_SECTIONS = 32, PW_PE32_PAGE = 0x4000, PW_PE32_MAX_FILE = 0x400000,
       PW_PE32_MAX_PAGES = 0x2000000 / PW_PE32_PAGE, PW_PE32_MAX_IMPORTS = 64,
       PW_PE32_MAX_EXPORTS = 64, PW_PE32_MAX_MODULES = 8 };
typedef struct PwPe32Import {
    char module[64], name[128];
    uint32_t ordinal, by_ordinal, iat_rva, lookup_rva, name_rva, module_rva;
} PwPe32Import;
typedef struct PwPe32Export {
    char name[128];
    uint32_t ordinal, rva;
} PwPe32Export;
typedef struct PwPe32Section {
    uint32_t rva, bytes, mapped_bytes, raw_offset, raw_bytes, protection;
} PwPe32Section;
typedef struct PwPe32Info {
    uint32_t preferred, image_bytes, header_bytes, entry_rva, section_count;
    uint32_t reloc_rva, reloc_bytes, relocation_count;
    uint32_t section_alignment, header_mapped_bytes;
    uint32_t is_dll, import_rva, import_bytes, export_rva, export_bytes, iat_rva, iat_bytes;
    uint32_t import_count, export_count;
    uint32_t tls_rva, tls_bytes, tls_template_rva, tls_template_bytes, tls_zero_bytes, tls_index_rva;
    uint32_t tls_callback_count, tls_callbacks[16];
    PwPe32Section sections[PW_PE32_MAX_SECTIONS];
    PwPe32Import imports[PW_PE32_MAX_IMPORTS];
    PwPe32Export exports[PW_PE32_MAX_EXPORTS];
} PwPe32Info;
typedef struct PwPe32Image {
    PwVmBackend backend;
    PwVmRegion region;
    PwPe32Info info;
    uint32_t base, entry, relocations_applied, linked, init_state;
    void *lifecycle_owner;
    uint32_t page_count, shared_pages, widened_pages;
    uint8_t page_permissions[PW_PE32_MAX_PAGES], page_occupied[PW_PE32_MAX_PAGES];
} PwPe32Image;
/* Initial subset: i386 EXE/DLL, 4 or 16 KiB section alignment, eager imports
 * function exports, DLL entry points and bounded static TLS (EXE or DLL). Load config,
 * forwarded exports and bound/delay imports remain unsupported.
 * Output remains unchanged on parse/load failure. */
int pw_pe32_inspect(const void *file, size_t bytes, PwPe32Info *out);
int pw_pe32_load(const PwVmBackend *, const void *file, size_t bytes,
                 uint32_t address, PwPe32Image *out);
int pw_pe32_source(void *image, uint32_t pc, const uint8_t **source, size_t *bytes);
int pw_pe32_bind(const PwPe32Image *, PwX86State *);
int pw_pe32_unload(PwPe32Image *);
typedef struct PwPe32Module { const char *name; PwPe32Image *image; } PwPe32Module;
typedef struct PwPe32Modules { const PwPe32Module *modules; size_t count; } PwPe32Modules;
typedef struct PwPe32LinkReport {
    int code;
    char module[64], symbol[128];
    uint32_t ordinal, iat_rva, named, by_ordinal;
} PwPe32LinkReport;
/* No IAT changes on resolution failure. Providers must be import-free DLLs.
 * Modules stay mapped and unmodified for the CPU context's lifetime. */
int pw_pe32_link(PwPe32Image *, const PwPe32Module *, size_t, PwPe32LinkReport *);
int pw_pe32_modules_source(void *, uint32_t, const uint8_t **, size_t *);
#endif
