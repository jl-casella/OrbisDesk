/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "pw_k32_internal.h"
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* msvcrt.dll subset for the mingw CRT start-up and exit paths. The heap is a
 * guest range with host-side block metadata; strings and buffers are read
 * through the thread's logical region table, and an inaccessible pointer is
 * a guest fault (PW_ERR_VM), as an access violation would be on Windows. */
enum { HEAP_BYTES = 0x100000, HEAP_BLOCKS = 4096, EXIT_HANDLERS = 32, SIGNALS = 32, TEXT = 256 };
/* Data page layout (guest offsets). */
enum { IOB = 0x000, IOB_BYTES = 32, INITENV = 0x060, FMODE = 0x064, COMMODE = 0x068, ACMDLN = 0x06c,
       ARGV = 0x070, ENVP = 0x078, CMDLINE = 0x080, PROGRAM = 0x0c0 };
enum { CRT_GETMAINARGS, CRT_INITENV, CRT_LCONV_INIT, CRT_P_ACMDLN, CRT_P_COMMODE, CRT_P_FMODE, CRT_SET_APP_TYPE,
       CRT_SETUSERMATHERR, CRT_AMSG_EXIT, CRT_CEXIT, CRT_INITTERM, CRT_IOB, CRT_ONEXIT, CRT_ABORT, CRT_CALLOC,
       CRT_EXIT, CRT_FPRINTF, CRT_FREE, CRT_FWRITE, CRT_MALLOC, CRT_MEMCPY, CRT_SIGNAL, CRT_STRLEN, CRT_STRNCMP,
       CRT_VFPRINTF, CRT_COUNT };
static const PwK32Export exports[CRT_COUNT] = {
    {"__getmainargs", 20, 1, 0, 0}, {"__initenv", 0, 1, 0, INITENV + 1}, {"__lconv_init", 0, 1, 0, 0},
    {"__p__acmdln", 0, 1, 0, 0}, {"__p__commode", 0, 1, 0, 0}, {"__p__fmode", 0, 1, 0, 0},
    {"__set_app_type", 4, 1, 0, 0}, {"__setusermatherr", 4, 1, 0, 0}, {"_amsg_exit", 4, 1, 0, 0},
    {"_cexit", 0, 1, 0, 0}, {"_initterm", 8, 1, 0, 0}, {"_iob", 0, 1, 0, IOB + 1}, {"_onexit", 4, 1, 0, 0},
    {"abort", 0, 1, 0, 0}, {"calloc", 8, 1, 0, 0}, {"exit", 4, 1, 0, 0}, {"fprintf", 8, 1, 1, 0},
    {"free", 4, 1, 0, 0}, {"fwrite", 16, 1, 0, 0}, {"malloc", 4, 1, 0, 0}, {"memcpy", 12, 1, 0, 0},
    {"signal", 8, 1, 0, 0}, {"strlen", 4, 1, 0, 0}, {"strncmp", 12, 1, 0, 0}, {"vfprintf", 12, 1, 0, 0}};
static uint32_t handler(void *, PwK32Call *);
const PwK32Module pw_msvcrt_ps4_module = {"msvcrt.dll", exports, CRT_COUNT, handler};
_Static_assert(CRT_COUNT == PW_MSVCRT_EXPORTS, "msvcrt export count");

typedef struct Block { uint32_t offset, bytes, used; } Block;
struct PwMsvcrt {
    PwK32Process *process;
    PwVmBackend vm;
    PwVmRegion heap;
    uint32_t heap_base, data;
    uint8_t *data_host;
    pthread_mutex_t mutex;
    Block blocks[HEAP_BLOCKS];
    unsigned block_count, live, allocations, peak, used_bytes;
    uint32_t exit_handlers[EXIT_HANDLERS], signals[SIGNALS], app_type, matherr;
    unsigned handler_count, initializers, handlers_run, output;
};

static void put32(PwMsvcrt *crt, uint32_t offset, uint32_t value) { memcpy(crt->data_host + offset, &value, 4); }
static uint32_t heap_alloc(PwMsvcrt *crt, uint32_t bytes)
{
    if (bytes > HEAP_BYTES) return 0;
    bytes = bytes ? (bytes + 15) & ~15u : 16;
    pthread_mutex_lock(&crt->mutex);
    uint32_t address = 0;
    for (unsigned i = 0; !address && i < crt->block_count; ++i) {
        Block *b = &crt->blocks[i];
        if (b->used || b->bytes < bytes) continue;
        if (b->bytes > bytes && crt->block_count < HEAP_BLOCKS) {
            memmove(b + 2, b + 1, (crt->block_count - i - 1) * sizeof(*b));
            b[1] = (Block){b->offset + bytes, b->bytes - bytes, 0};
            b->bytes = bytes;
            crt->block_count++;
        }
        b->used = 1;
        address = crt->heap_base + b->offset;
        bytes = b->bytes;
    }
    if (!address && crt->block_count < HEAP_BLOCKS) {
        uint32_t top = crt->block_count ? crt->blocks[crt->block_count - 1].offset + crt->blocks[crt->block_count - 1].bytes : 0;
        if (HEAP_BYTES - top >= bytes) {
            crt->blocks[crt->block_count++] = (Block){top, bytes, 1};
            address = crt->heap_base + top;
        }
    }
    if (address) {
        crt->live++; crt->allocations++; crt->used_bytes += bytes;
        if (crt->used_bytes > crt->peak) crt->peak = crt->used_bytes;
    }
    pthread_mutex_unlock(&crt->mutex);
    return address;
}
static int heap_free(PwMsvcrt *crt, uint32_t address)
{
    pthread_mutex_lock(&crt->mutex);
    int rc = -1;
    for (unsigned i = 0; i < crt->block_count; ++i) {
        Block *b = &crt->blocks[i];
        if (crt->heap_base + b->offset != address) continue;
        if (!b->used) break;
        b->used = 0; crt->live--; crt->used_bytes -= b->bytes; rc = 0;
        if (i + 1 < crt->block_count && !b[1].used) {
            b->bytes += b[1].bytes;
            memmove(b + 1, b + 2, (crt->block_count - i - 2) * sizeof(*b));
            crt->block_count--;
        }
        if (i && !b[-1].used) {
            b[-1].bytes += b->bytes;
            memmove(b, b + 1, (crt->block_count - i - 1) * sizeof(*b));
            crt->block_count--;
        }
        break;
    }
    pthread_mutex_unlock(&crt->mutex);
    return rc;
}
static int guest_strlen(const PwX86State *s, uint32_t address, uint32_t limit, uint32_t *length)
{
    for (uint32_t i = 0; i < limit; ++i) {
        if ((uint64_t)address + i > UINT32_MAX || !pw_k32_guest_span(s, address + i, 1, PW_X86_READ)) return PW_ERR_VM;
        if (!*(const char *)(uintptr_t)(address + i)) { *length = i; return PW_OK; }
    }
    return PW_ERR_LIMIT;
}
static int stream_of(PwMsvcrt *crt, uint32_t file)
{
    for (unsigned i = 1; i < 3; ++i) if (file == crt->data + IOB + i * IOB_BYTES) return (int)i;
    return -1;
}
static void emit(PwMsvcrt *crt, int stream, const char *text, size_t bytes)
{
    char escaped[2 * TEXT + 8];
    size_t out = 0;
    for (size_t i = 0; i < bytes && out + 7 < sizeof(escaped); ++i) {
        unsigned char ch = (unsigned char)text[i];
        if (ch == '"' || ch == '\\') { escaped[out++] = '\\'; escaped[out++] = (char)ch; }
        else if (ch < 0x20 || ch > 0x7e) out += (size_t)snprintf(escaped + out, sizeof(escaped) - out, "\\u%04x", ch);
        else escaped[out++] = (char)ch;
    }
    escaped[out] = 0;
    crt->output += (unsigned)bytes;
    pw_k32_trace(crt->process, "PWCRT {\"stream\":%d,\"text\":\"%s\"}", stream, escaped);
}
typedef struct Arguments { const PwGuestCall *frame; const PwX86State *state; uint32_t offset, list; } Arguments;
static int next_arg(Arguments *args, uint32_t *value)
{
    if (args->frame) {
        int rc = pw_guest_call_u32(args->frame, args->offset, value);
        args->offset += 4;
        return rc;
    }
    if (!pw_k32_guest_span(args->state, args->list, 4, PW_X86_READ)) return PW_ERR_VM;
    memcpy(value, (const void *)(uintptr_t)args->list, 4);
    args->list += 4;
    return PW_OK;
}
/* Format subset: %s %d %i %u %x %X %p %c %%, with no flags, width or length.
 * Anything else is refused, not approximated. */
static int format(const PwX86State *s, uint32_t pattern, Arguments *args, char *out, size_t capacity, size_t *length, const char **refusal)
{
    char spec[TEXT];
    int rc = pw_k32_guest_string(s, pattern, spec, sizeof(spec));
    if (rc) { *refusal = "format string unreadable or longer than 255 bytes"; return PW_ERR_UNSUPPORTED; }
    size_t n = 0;
    for (const char *f = spec; *f; ++f) {
        char piece[TEXT] = {0};
        if (*f != '%') piece[0] = *f;
        else {
            uint32_t value = 0;
            char kind = *++f;
            if (kind == '%') piece[0] = '%';
            else if (strchr("diuxXpcs", kind) && kind) {
                if (next_arg(args, &value)) return PW_ERR_VM;
                if (kind == 's') {
                    rc = value ? pw_k32_guest_string(s, value, piece, sizeof(piece)) : 0;
                    if (!value) snprintf(piece, sizeof(piece), "(null)");
                    if (rc) return PW_ERR_VM;
                } else if (kind == 'c') piece[0] = (char)value;
                else if (kind == 'd' || kind == 'i') snprintf(piece, sizeof(piece), "%d", (int)value);
                else if (kind == 'u') snprintf(piece, sizeof(piece), "%u", value);
                else if (kind == 'x') snprintf(piece, sizeof(piece), "%x", value);
                else if (kind == 'X') snprintf(piece, sizeof(piece), "%X", value);
                else snprintf(piece, sizeof(piece), "%08X", value);
            } else { *refusal = "printf conversion outside %s %d %i %u %x %X %p %c"; return PW_ERR_UNSUPPORTED; }
        }
        size_t add = strlen(piece);
        if (n + add >= capacity) { *refusal = "formatted text longer than 255 bytes"; return PW_ERR_UNSUPPORTED; }
        memcpy(out + n, piece, add); n += add;
    }
    out[n] = 0; *length = n;
    return PW_OK;
}
static int run_exit_handlers(PwMsvcrt *crt, PwK32Call *c)
{
    for (;;) {
        pthread_mutex_lock(&crt->mutex);
        uint32_t target = crt->handler_count ? crt->exit_handlers[--crt->handler_count] : 0;
        pthread_mutex_unlock(&crt->mutex);
        if (!target) return PW_OK;
        crt->handlers_run++;
        int rc = pw_k32_call_guest(c, target, NULL, 0, PW_GUEST_CDECL, NULL);
        if (rc) return rc;
    }
}
static uint32_t print(PwMsvcrt *crt, PwK32Call *c, uint32_t file, uint32_t pattern, Arguments *args)
{
    int stream = stream_of(crt, file);
    if (stream < 0) { c->refusal = "only stdout and stderr are writable"; return UINT32_MAX; }
    char text[TEXT];
    size_t length = 0;
    int rc = format(c->state, pattern, args, text, sizeof(text), &length, &c->refusal);
    if (rc == PW_ERR_VM) { c->rc = PW_ERR_VM; return 0; }
    if (rc) return UINT32_MAX;
    emit(crt, stream, text, length);
    return (uint32_t)length;
}
static uint32_t handler(void *state, PwK32Call *c)
{
    PwMsvcrt *crt = state;
    const PwX86State *s = c->state;
    const uint32_t *a = c->a;
    switch (c->index) {
    case CRT_GETMAINARGS:
        if (!pw_k32_guest_span(s, a[0], 4, PW_X86_WRITE) || !pw_k32_guest_span(s, a[1], 4, PW_X86_WRITE) ||
            !pw_k32_guest_span(s, a[2], 4, PW_X86_WRITE)) { c->rc = PW_ERR_VM; return 0; }
        {
            uint32_t values[3] = {1, crt->data + ARGV, crt->data + ENVP};
            for (unsigned i = 0; i < 3; ++i) memcpy((void *)(uintptr_t)a[i], &values[i], 4);
        }
        return 0;
    case CRT_LCONV_INIT: return 0;
    case CRT_P_ACMDLN: return crt->data + ACMDLN;
    case CRT_P_COMMODE: return crt->data + COMMODE;
    case CRT_P_FMODE: return crt->data + FMODE;
    case CRT_SET_APP_TYPE: crt->app_type = a[0]; c->bits = 0; return 0;
    case CRT_SETUSERMATHERR: crt->matherr = a[0]; c->bits = 0; return 0;
    case CRT_AMSG_EXIT:
        pw_k32_trace(crt->process, "PWCRT {\"runtime_error\":%u}", a[0]);
        c->exit = 1; c->exit_code = 255;
        return 0;
    case CRT_ABORT:
        pw_k32_trace(crt->process, "PWCRT {\"abort\":true}");
        c->exit = 1; c->exit_code = 3;
        return 0;
    case CRT_CEXIT: c->bits = 0; c->rc = run_exit_handlers(crt, c); return 0;
    case CRT_EXIT:
        c->rc = run_exit_handlers(crt, c);
        if (!c->rc) { c->exit = 1; c->exit_code = a[0]; }
        return 0;
    case CRT_INITTERM:
        c->bits = 0;
        if (a[0] > a[1] || (a[1] - a[0]) % 4 || (a[0] != a[1] && !pw_k32_guest_span(s, a[0], a[1] - a[0], PW_X86_READ))) {
            c->rc = PW_ERR_VM; return 0;
        }
        for (uint32_t at = a[0]; at < a[1]; at += 4) {
            uint32_t target;
            memcpy(&target, (const void *)(uintptr_t)at, 4);
            if (!target) continue;
            crt->initializers++;
            c->rc = pw_k32_call_guest(c, target, NULL, 0, PW_GUEST_CDECL, NULL);
            if (c->rc) return 0;
        }
        return 0;
    case CRT_ONEXIT:
        pthread_mutex_lock(&crt->mutex);
        if (crt->handler_count < EXIT_HANDLERS && a[0]) crt->exit_handlers[crt->handler_count++] = a[0];
        else c->refusal = "exit handler table full or null handler";
        pthread_mutex_unlock(&crt->mutex);
        return c->refusal ? 0 : a[0];
    case CRT_CALLOC: {
        uint64_t bytes = (uint64_t)a[0] * a[1];
        uint32_t address = bytes > HEAP_BYTES ? 0 : heap_alloc(crt, (uint32_t)bytes);
        if (address) memset((void *)(uintptr_t)address, 0, (size_t)bytes);
        return address;
    }
    case CRT_MALLOC: return heap_alloc(crt, a[0]);
    case CRT_FREE:
        c->bits = 0;
        if (a[0] && heap_free(crt, a[0])) c->refusal = "free of a pointer not returned by malloc";
        return 0;
    case CRT_MEMCPY:
        if (a[2] && (!pw_k32_guest_span(s, a[0], a[2], PW_X86_WRITE) || !pw_k32_guest_span(s, a[1], a[2], PW_X86_READ))) {
            c->rc = PW_ERR_VM; return 0;
        }
        memmove((void *)(uintptr_t)a[0], (const void *)(uintptr_t)a[1], a[2]);
        return a[0];
    case CRT_STRLEN: {
        uint32_t length = 0;
        int rc = guest_strlen(s, a[0], 0x100000, &length);
        if (rc == PW_ERR_VM) c->rc = rc;
        else if (rc) c->refusal = "string longer than 1 MiB";
        return length;
    }
    case CRT_STRNCMP:
        for (uint32_t i = 0; i < a[2]; ++i) {
            if (!pw_k32_guest_span(s, a[0] + i, 1, PW_X86_READ) || !pw_k32_guest_span(s, a[1] + i, 1, PW_X86_READ)) {
                c->rc = PW_ERR_VM; return 0;
            }
            unsigned char x = *(const unsigned char *)(uintptr_t)(a[0] + i), y = *(const unsigned char *)(uintptr_t)(a[1] + i);
            if (x != y) return x < y ? UINT32_MAX : 1;
            if (!x) break;
        }
        return 0;
    case CRT_SIGNAL: {
        if (a[0] >= SIGNALS) return UINT32_MAX; /* SIG_ERR */
        pthread_mutex_lock(&crt->mutex);
        uint32_t previous = crt->signals[a[0]];
        crt->signals[a[0]] = a[1];
        pthread_mutex_unlock(&crt->mutex);
        return previous;
    }
    case CRT_FWRITE: {
        int stream = stream_of(crt, a[3]);
        uint64_t bytes = (uint64_t)a[1] * a[2];
        if (stream < 0) { c->refusal = "only stdout and stderr are writable"; return 0; }
        if (bytes > 0x100000 || (bytes && !pw_k32_guest_span(s, a[0], (uint32_t)bytes, PW_X86_READ))) { c->rc = PW_ERR_VM; return 0; }
        for (uint64_t done = 0; done < bytes; done += TEXT)
            emit(crt, stream, (const char *)(uintptr_t)(a[0] + done), bytes - done > TEXT ? TEXT : (size_t)(bytes - done));
        return a[1] ? a[2] : 0;
    }
    case CRT_FPRINTF: {
        Arguments args = {c->frame, s, 8, 0};
        return print(crt, c, a[0], a[1], &args);
    }
    case CRT_VFPRINTF: {
        Arguments args = {NULL, s, 0, a[2]};
        return print(crt, c, a[0], a[1], &args);
    }
    }
    c->refusal = "unknown msvcrt slot";
    return 0;
}

int pw_msvcrt_ps4_create(PwMsvcrt **out, PwK32Process *process, const PwVmBackend *vm, uint32_t heap, uint32_t data, uint8_t *data_host)
{
    if (!out || !process || !vm || !data_host || heap % PW_PE32_PAGE) return PW_ERR_PRECONDITION;
    PwMsvcrt *crt = calloc(1, sizeof(*crt));
    if (!crt) return PW_ERR_LIMIT;
    crt->process = process; crt->vm = *vm; crt->heap_base = heap; crt->data = data; crt->data_host = data_host;
    if (pthread_mutex_init(&crt->mutex, NULL)) { free(crt); return PW_ERR_STATE; }
    int rc = vm->reserve_at(vm->context, heap, HEAP_BYTES, PW_PE32_PAGE, &crt->heap);
    if (!rc) rc = vm->commit(vm->context, &crt->heap, 0, HEAP_BYTES, PW_PROT_READ | PW_PROT_WRITE);
    if (!rc) rc = pw_k32_add_region(process, heap, HEAP_BYTES, PW_X86_READ | PW_X86_WRITE);
    if (rc) {
        if (crt->heap.handle) vm->release(vm->context, &crt->heap);
        pthread_mutex_destroy(&crt->mutex); free(crt);
        return rc;
    }
    /* _iob[i]._file = i; the rest of each FILE stays zero. */
    for (unsigned i = 0; i < 3; ++i) put32(crt, IOB + i * IOB_BYTES + 16, i);
    put32(crt, INITENV, data + ENVP);
    put32(crt, ACMDLN, data + CMDLINE);
    put32(crt, ARGV, data + PROGRAM);
    *out = crt;
    return PW_OK;
}
int pw_msvcrt_ps4_set_program(PwMsvcrt *crt, const char *name)
{
    if (!crt || !name || strlen(name) >= 64) return PW_ERR_PRECONDITION;
    memcpy(crt->data_host + CMDLINE, name, strlen(name) + 1);
    memcpy(crt->data_host + PROGRAM, name, strlen(name) + 1);
    return PW_OK;
}
void pw_msvcrt_ps4_stats(PwMsvcrt *crt, PwK32Stats *out)
{
    pthread_mutex_lock(&crt->mutex);
    out->heap_allocations = crt->allocations; out->heap_live_blocks = crt->live; out->heap_peak_bytes = crt->peak;
    out->initializers = crt->initializers; out->exit_handlers = crt->handlers_run; out->crt_output_bytes = crt->output;
    pthread_mutex_unlock(&crt->mutex);
}
int pw_msvcrt_ps4_destroy(PwMsvcrt *crt)
{
    if (!crt) return PW_ERR_PRECONDITION;
    int rc = crt->vm.release(crt->vm.context, &crt->heap);
    pthread_mutex_destroy(&crt->mutex);
    free(crt);
    return rc;
}
