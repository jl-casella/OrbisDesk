/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "pw_k32_internal.h"
#include "pw_cpu_ps4.h"
#include "pw_pe32_lifecycle.h"
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <sched.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

enum { SLOT_RVA = 0x1000, SLOT_BYTES = 16, THUNK_LIMIT = PW_PE32_PAGE, STACK_BYTES = 0x10000, STACK_STRIDE = 0x20000,
       TEB_STRIDE = 0x40000, RETURN_TOKEN = 0x0badf00d, EXITED = PW_K32_EXITED, MODULES = PW_PE32_MAX_MODULES,
       RELOCATION_BASE = 0x34000000, RELOCATION_STRIDE = 0x01000000, MSVCRT_OFFSET = 0x10000,
       HEAP_BASE = 0x3c000000, REGIONS = 8, SECTIONS = 64 };
enum { K32_CLOSE, K32_CREATE_FILE, K32_CREATE_THREAD, K32_DELETE_CS, K32_ENTER_CS, K32_EXIT_PROCESS,
       K32_FREE_LIBRARY, K32_CURRENT_PROCESS, K32_PROCESS_ID, K32_EXIT_CODE, K32_GET_ERROR,
       K32_MODULE_HANDLE, K32_GET_PROC, K32_STARTUP_INFO, K32_INIT_CS, K32_LEAVE_CS, K32_LOAD_LIBRARY,
       K32_SET_ERROR, K32_EXCEPTION_FILTER, K32_SLEEP, K32_TERMINATE, K32_TLS_GET, K32_VIRTUAL_PROTECT,
       K32_VIRTUAL_QUERY, K32_WAIT, K32_WRITE_FILE };
/* Win32 values used by the handlers. */
enum { ERROR_FILE_NOT_FOUND = 2, ERROR_PATH_NOT_FOUND = 3, ERROR_TOO_MANY_OPEN_FILES = 4,
       ERROR_ACCESS_DENIED = 5, ERROR_INVALID_HANDLE = 6, ERROR_NOT_ENOUGH_MEMORY = 8,
       ERROR_BAD_FORMAT = 11, ERROR_BAD_LENGTH = 24, ERROR_GEN_FAILURE = 31, ERROR_NOT_SUPPORTED = 50,
       ERROR_FILE_EXISTS = 80, ERROR_INVALID_PARAMETER = 87, ERROR_INVALID_NAME = 123,
       ERROR_MOD_NOT_FOUND = 126, ERROR_PROC_NOT_FOUND = 127, ERROR_ALREADY_EXISTS = 183,
       ERROR_NOACCESS = 998, ERROR_DLL_INIT_FAILED = 1114, STILL_ACTIVE = 259, WAIT_TIMEOUT = 0x102,
       KEEP_ERROR = -1, CURRENT_PROCESS = 0xffffffffu };
static const PwK32Export kernel32_exports[PW_K32_EXPORTS] = {
    {"CloseHandle", 4, 0, 0, 0}, {"CreateFileA", 28, 0, 0, 0}, {"CreateThread", 24, 0, 0, 0},
    {"DeleteCriticalSection", 4, 0, 0, 0}, {"EnterCriticalSection", 4, 0, 0, 0}, {"ExitProcess", 4, 0, 0, 0},
    {"FreeLibrary", 4, 0, 0, 0}, {"GetCurrentProcess", 0, 0, 0, 0}, {"GetCurrentProcessId", 0, 0, 0, 0},
    {"GetExitCodeThread", 8, 0, 0, 0}, {"GetLastError", 0, 0, 0, 0}, {"GetModuleHandleA", 4, 0, 0, 0},
    {"GetProcAddress", 8, 0, 0, 0}, {"GetStartupInfoA", 4, 0, 0, 0}, {"InitializeCriticalSection", 4, 0, 0, 0},
    {"LeaveCriticalSection", 4, 0, 0, 0}, {"LoadLibraryA", 4, 0, 0, 0}, {"SetLastError", 4, 0, 0, 0},
    {"SetUnhandledExceptionFilter", 4, 0, 0, 0}, {"Sleep", 4, 0, 0, 0}, {"TerminateProcess", 8, 0, 0, 0},
    {"TlsGetValue", 4, 0, 0, 0}, {"VirtualProtect", 16, 0, 0, 0}, {"VirtualQuery", 12, 0, 0, 0},
    {"WaitForSingleObject", 8, 0, 0, 0}, {"WriteFile", 20, 0, 0, 0}};
static uint32_t kernel32_handler(void *, PwK32Call *);
static const PwK32Module kernel32_module = {"kernel32.dll", kernel32_exports, PW_K32_EXPORTS, kernel32_handler};

typedef struct Range { uint32_t base, bytes; unsigned permission; } Range;
struct PwK32Thread {
    PwK32Process *process;
    unsigned slot, used, handles, started, setup_done, finished, in_loader, generation, bound_count;
    int setup_rc, rc;
    uint32_t start, parameter, exit_code;
    uint64_t steps;
    pthread_t host;
    PwPs4Cpu *cpu;
    PwVmRegion stack;
    PwPe32Thread teb;
    Range bound[MODULES + REGIONS];
    PwX86Memory inherited[PW_X86_MEMORY_REGIONS];
    unsigned inherited_count;
};
typedef struct PwK32Thread Thread;
typedef struct Handle { unsigned kind; int fd; Thread *thread; } Handle;
enum { HANDLE_FREE, HANDLE_FILE, HANDLE_THREAD };
typedef struct CriticalSection { uint32_t address; unsigned used, owner, count; } CriticalSection;
/* Synthetic modules and the EXE are pinned; DLLs loaded from module_directory
 * are owned by the process and unmapped when their count drops to zero. */
enum { MODULE_FREE, MODULE_SYNTHETIC, MODULE_EXE, MODULE_DLL };
typedef struct Module {
    PwPe32Image *image;
    char name[64];
    unsigned kind, refs;
    const PwK32Module *synthetic;
    void *state;
} Module;
struct PwK32Process {
    PwVmBackend vm;
    char directory[192], module_directory[192];
    PwK32Trace sink;
    void *opaque;
    pthread_mutex_t mutex;
    pthread_cond_t changed;
    Module modules[MODULES];
    Range regions[REGIONS];
    unsigned region_count, ran, exiting, generation;
    PwPe32Lifecycle life;
    PwMsvcrt *crt;
    uint32_t stack, teb, exit_code, exception_filter;
    uint64_t max_steps;
    Thread threads[PW_K32_THREADS + 1];
    Handle handles[PW_K32_HANDLES];
    CriticalSection sections[SECTIONS];
    PwK32Stats stats;
};

const char *pw_k32_ps4_export_name(unsigned index)
{
    return index < PW_K32_EXPORTS ? kernel32_exports[index].name : NULL;
}
const char *pw_k32_ps4_crt_export_name(unsigned index)
{
    return index < pw_msvcrt_ps4_module.count ? pw_msvcrt_ps4_module.exports[index].name : NULL;
}
void pw_k32_trace(PwK32Process *p, const char *format, ...)
{
    if (!p->sink) return;
    char line[384];
    va_list list;
    va_start(list, format);
    vsnprintf(line, sizeof(line), format, list);
    va_end(list);
    p->sink(p->opaque, line);
}
#define trace pw_k32_trace
unsigned pw_k32_thread_slot(const PwK32Thread *t) { return t->slot; }
static int contains(uint32_t base, uint32_t bytes, uint64_t address)
{
    return address >= base && address - base < bytes;
}
/* Synthetic modules never change after create, so this needs no lock. */
static Module *thunk_module(PwK32Process *p, uint32_t pc)
{
    for (unsigned i = 0; i < MODULES; ++i) {
        Module *m = &p->modules[i];
        if (m->kind == MODULE_SYNTHETIC && contains(m->image->base, THUNK_LIMIT, pc)) return m;
    }
    return NULL;
}
static int source(void *opaque, uint32_t pc, const uint8_t **bytes, size_t *count)
{
    PwK32Process *p = opaque;
    /* Thunk slots are never translated: execution stops there for the host. */
    if (thunk_module(p, pc)) return PW_ERR_NOT_FOUND;
    int rc = PW_ERR_NOT_FOUND;
    pthread_mutex_lock(&p->mutex);
    for (unsigned i = 0; i < MODULES; ++i) {
        const Module *m = &p->modules[i];
        if ((m->kind == MODULE_EXE || m->kind == MODULE_DLL) && contains(m->image->base, m->image->info.image_bytes, pc)) {
            rc = pw_pe32_source(m->image, pc, bytes, count);
            break;
        }
    }
    pthread_mutex_unlock(&p->mutex);
    return rc;
}
/* Same coverage rule as the hostexec operand check: logical regions only. */
int pw_k32_guest_span(const PwX86State *s, uint32_t address, uint32_t bytes, unsigned permission)
{
    uint64_t cursor = address, end = cursor + bytes;
    if (!address || end > 0x100000000ull) return 0;
    while (cursor < end) {
        uint64_t covered = cursor;
        for (unsigned i = 0; i < s->memory_count; ++i) {
            const PwX86Memory *m = &s->memory[i];
            if (m->low <= cursor && m->high > cursor && (m->permissions & permission) == permission && m->high > covered)
                covered = m->high;
        }
        if (covered == cursor) return 0;
        cursor = covered;
    }
    return 1;
}
#define guest_span pw_k32_guest_span
int pw_k32_guest_string(const PwX86State *s, uint32_t address, char *out, unsigned capacity)
{
    for (unsigned i = 0; i < capacity; ++i) {
        if ((uint64_t)address + i > UINT32_MAX || !guest_span(s, address + i, 1, PW_X86_READ)) return ERROR_NOACCESS;
        out[i] = *(const char *)(uintptr_t)(address + i);
        if (!out[i]) return 0;
    }
    return ERROR_INVALID_NAME;
}
#define guest_string pw_k32_guest_string
static uint32_t *last_error(const PwX86State *s) { return (uint32_t *)(uintptr_t)(s->fs_base + 0x34); }
static int canonical(const char *name, char out[64], int add_dll)
{
    unsigned n = 0, dot = 0;
    for (; name[n]; ++n) {
        char c = name[n];
        if (n >= 59) return ERROR_INVALID_NAME;
        if (c >= 'A' && c <= 'Z') c += 'a' - 'A';
        if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '_' || c == '-' || c == '.')) return ERROR_INVALID_NAME;
        if (c == '.') dot = 1;
        out[n] = c;
    }
    if (!n || (n == 1 && out[0] == '.') || (n == 2 && out[0] == '.' && out[1] == '.')) return ERROR_INVALID_NAME;
    if (add_dll && !dot) memcpy(out + n, ".dll", 4), n += 4;
    out[n] = 0;
    return 0;
}
static Handle *handle_get(PwK32Process *p, uint32_t value)
{
    if (!value || value % 4 || value / 4 > PW_K32_HANDLES) return NULL;
    Handle *h = &p->handles[value / 4 - 1];
    return h->kind ? h : NULL;
}
static uint32_t handle_new(PwK32Process *p, unsigned kind, int fd, Thread *thread)
{
    for (unsigned i = 0; i < PW_K32_HANDLES; ++i) {
        if (p->handles[i].kind) continue;
        p->handles[i] = (Handle){kind, fd, thread};
        return (i + 1) * 4;
    }
    return 0;
}
static uint32_t win32_errno(int value)
{
    return value == ENOENT ? ERROR_FILE_NOT_FOUND : value == EEXIST ? ERROR_FILE_EXISTS :
           value == EACCES || value == EPERM ? ERROR_ACCESS_DENIED : value == EMFILE ? ERROR_TOO_MANY_OPEN_FILES :
           value == ENOTDIR ? ERROR_PATH_NOT_FOUND : ERROR_GEN_FAILURE;
}
/* Caller holds the mutex and the thread has published setup failure or finished:
 * it takes the mutex no more, so the join cannot deadlock. */
static void reap(Thread *t)
{
    pthread_join(t->host, NULL);
    t->process->stats.steps += t->steps;
    t->used = 0;
}
int pw_k32_add_region(PwK32Process *p, uint32_t base, uint32_t bytes, unsigned permission)
{
    pthread_mutex_lock(&p->mutex);
    int rc = p->region_count == REGIONS ? PW_ERR_LIMIT : PW_OK;
    if (!rc) { p->regions[p->region_count++] = (Range){base, bytes, permission}; p->generation++; }
    pthread_mutex_unlock(&p->mutex);
    return rc;
}
static int add_memory(PwX86State *s, uint32_t base, uint64_t high, unsigned permission)
{
    if (s->memory_count == PW_X86_MEMORY_REGIONS) return PW_ERR_LIMIT;
    s->memory[s->memory_count++] = (PwX86Memory){base, high, permission};
    return PW_OK;
}
/* Rebuild the module and process-region part of this thread's region table
 * after a change. Runs on the owning thread only, before it executes guest code. */
static int refresh(PwK32Process *p, Thread *t, PwX86State *s)
{
    pthread_mutex_lock(&p->mutex);
    unsigned kept = 0;
    for (unsigned i = 0; i < s->memory_count; ++i) {
        uint32_t low = (uint32_t)s->memory[i].low;
        int managed = 0;
        for (unsigned j = 0; j < t->bound_count; ++j) if (contains(t->bound[j].base, t->bound[j].bytes, low)) managed = 1;
        for (unsigned j = 0; j < MODULES; ++j)
            if (p->modules[j].kind && contains(p->modules[j].image->base, p->modules[j].image->info.image_bytes, low)) managed = 1;
        for (unsigned j = 0; j < p->region_count; ++j) if (contains(p->regions[j].base, p->regions[j].bytes, low)) managed = 1;
        if (!managed) s->memory[kept++] = s->memory[i];
    }
    s->memory_count = kept;
    t->bound_count = 0;
    int rc = PW_OK;
    for (unsigned j = 0; !rc && j < MODULES; ++j) {
        const Module *m = &p->modules[j];
        if (!m->kind) continue;
        const PwPe32Image *image = m->image;
        if (m->kind == MODULE_SYNTHETIC) {
            /* Only the data page; thunk slots stay outside the table. */
            if (image->info.section_count > 1) {
                const PwPe32Section *data = &image->info.sections[1];
                rc = add_memory(s, image->base + data->rva, (uint64_t)image->base + data->rva + data->mapped_bytes, data->protection);
            }
        } else {
            /* pw_pe32_bind without its EXE entry side effect. */
            rc = add_memory(s, image->base, (uint64_t)image->base + image->info.header_mapped_bytes, PW_X86_READ);
            for (unsigned i = 0; !rc && i < image->info.section_count; ++i) {
                const PwPe32Section *section = &image->info.sections[i];
                rc = add_memory(s, image->base + section->rva, (uint64_t)image->base + section->rva + section->mapped_bytes,
                                section->protection);
            }
        }
        t->bound[t->bound_count++] = (Range){image->base, image->info.image_bytes, 0};
    }
    for (unsigned j = 0; !rc && j < p->region_count; ++j) {
        rc = add_memory(s, p->regions[j].base, (uint64_t)p->regions[j].base + p->regions[j].bytes, p->regions[j].permission);
        t->bound[t->bound_count++] = p->regions[j];
    }
    t->generation = p->generation;
    pthread_mutex_unlock(&p->mutex);
    return rc;
}

static int execute(PwK32Process *p, Thread *t, uint32_t stop, int honor_exit);
static Thread *thread_of(PwK32Process *p, PwPs4Cpu *cpu)
{
    for (unsigned i = 0; i <= PW_K32_THREADS; ++i) if (p->threads[i].used && p->threads[i].cpu == cpu) return &p->threads[i];
    return NULL;
}
/* DLL and TLS notifications run under the lifecycle mutex; kernel32 calls
 * from there work, but loader re-entry is refused instead of deadlocking. */
static int runner(void *opaque, PwPs4Cpu *cpu, uint32_t stop)
{
    PwK32Process *p = opaque;
    Thread *t = thread_of(p, cpu);
    if (!t) return PW_ERR_STATE;
    unsigned outer = t->in_loader;
    t->in_loader = 1;
    int rc = execute(p, t, stop, 0);
    t->in_loader = outer;
    return rc;
}
int pw_k32_call_guest(PwK32Call *c, uint32_t target, const uint32_t *arguments, unsigned count,
                      PwGuestConvention convention, uint32_t *result)
{
    PwGuestCallback frame = {0};
    uint64_t value = 0;
    int rc = pw_guest_callback_enter(&frame, c->state, target, RETURN_TOKEN, arguments, count, convention);
    if (!rc) rc = execute(c->process, c->thread, RETURN_TOKEN, 1);
    if (!rc) rc = pw_guest_callback_leave(&frame, 32, &value);
    if (!rc && result) *result = (uint32_t)value;
    return rc;
}
static int setup(PwK32Process *p, Thread *t, uint32_t stack, uint32_t teb)
{
    int main_thread = !t->slot;
    int rc = p->vm.reserve_at(p->vm.context, stack, STACK_BYTES, PW_PE32_PAGE, &t->stack);
    if (!rc) rc = p->vm.commit(p->vm.context, &t->stack, 0, STACK_BYTES, PW_PROT_READ | PW_PROT_WRITE);
    if (!rc) rc = pw_cpu_ps4_create(&t->cpu, &p->vm, source, p);
    if (!rc) {
        PwX86State *s = pw_cpu_ps4_state(t->cpu);
        s->stack_low = stack; s->stack_high = stack + STACK_BYTES; s->gpr[4] = s->stack_high - 16;
        memcpy(s->memory, t->inherited, t->inherited_count * sizeof(s->memory[0]));
        s->memory_count = t->inherited_count;
        rc = add_memory(s, stack, (uint64_t)stack + STACK_BYTES, PW_X86_READ | PW_X86_WRITE);
        if (!rc) rc = refresh(p, t, s);
    }
    if (!rc) rc = pw_pe32_thread_create(&p->life, t->cpu, teb, main_thread, &t->teb);
    if (!rc) rc = main_thread ? pw_pe32_process_attach(&t->teb) : pw_pe32_thread_attach(&t->teb);
    return rc;
}
static int teardown(PwK32Process *p, Thread *t)
{
    int rc = 0;
    if (t->teb.region.handle) {
        if (t->teb.attached && (t->slot ? pw_pe32_thread_detach(&t->teb) : pw_pe32_process_detach(&t->teb))) rc = 1;
        if (pw_pe32_thread_destroy(&t->teb)) rc = 1;
    }
    if (t->cpu && pw_cpu_ps4_destroy(t->cpu)) rc = 1;
    t->cpu = NULL;
    if (t->stack.handle && p->vm.release(p->vm.context, &t->stack)) rc = 1;
    memset(&t->stack, 0, sizeof(t->stack));
    return rc;
}
static void *thread_main(void *opaque)
{
    Thread *t = opaque;
    PwK32Process *p = t->process;
    int rc = setup(p, t, p->stack + t->slot * STACK_STRIDE, p->teb + t->slot * TEB_STRIDE);
    if (rc) teardown(p, t);
    pthread_mutex_lock(&p->mutex);
    t->setup_rc = rc; t->setup_done = 1;
    pthread_cond_broadcast(&p->changed);
    pthread_mutex_unlock(&p->mutex);
    if (rc) return NULL;
    PwX86State *s = pw_cpu_ps4_state(t->cpu);
    PwGuestCallback frame = {0};
    uint64_t value = STILL_ACTIVE;
    rc = pw_guest_callback_enter(&frame, s, t->start, RETURN_TOKEN, &t->parameter, 1, PW_GUEST_STDCALL);
    if (!rc) rc = execute(p, t, RETURN_TOKEN, 1);
    if (!rc) rc = pw_guest_callback_leave(&frame, 32, &value);
    uint32_t eip = s->eip;
    if (teardown(p, t) && !rc) rc = PW_ERR_STATE;
    pthread_mutex_lock(&p->mutex);
    if (rc == EXITED) value = p->exit_code;
    else if (rc) {
        /* An unhandled fault ends the whole process, as on Windows. */
        p->stats.thread_failures++;
        if (!p->exiting) { p->exiting = 1; p->exit_code = 0xc0000005u; p->stats.run_rc = (unsigned)rc; }
        value = 0xc0000005u;
        trace(p, "PWK32 {\"thread\":%u,\"fault\":%d,\"eip\":\"0x%x\"}", t->slot, rc, eip);
    }
    t->rc = rc == EXITED ? 0 : rc; t->exit_code = (uint32_t)value; t->finished = 1;
    pthread_cond_broadcast(&p->changed);
    pthread_mutex_unlock(&p->mutex);
    return NULL;
}

static uint32_t create_file(PwK32Process *p, const PwX86State *s, const uint32_t *a, int *error, const char **refusal)
{
    char name[64], path[260];
    int rc = guest_string(s, a[0], name, sizeof(name));
    if (rc) { *error = rc; *refusal = "file name unreadable or longer than 63 bytes"; return UINT32_MAX; }
    int flat = strcmp(name, ".") && strcmp(name, "..");
    for (unsigned i = 0; name[i]; ++i) {
        char c = name[i];
        if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '.' || c == '_' || c == '-')) flat = 0;
    }
    if (!flat) { *error = ERROR_INVALID_NAME; *refusal = "only flat relative file names are mapped"; return UINT32_MAX; }
    uint32_t access = a[1], disposition = a[4], attributes = a[5];
    if (!access || access & ~0xc0000000u) { *error = ERROR_NOT_SUPPORTED; *refusal = "only GENERIC_READ/GENERIC_WRITE access"; return UINT32_MAX; }
    if (a[3] || a[6]) { *error = ERROR_NOT_SUPPORTED; *refusal = "security attributes and templates"; return UINT32_MAX; }
    if (attributes && attributes != 0x80) { *error = ERROR_NOT_SUPPORTED; *refusal = "only FILE_ATTRIBUTE_NORMAL"; return UINT32_MAX; }
    if (a[2] & ~7u || disposition < 1 || disposition > 5 || (disposition == 5 && !(access & 0x40000000u))) {
        *error = ERROR_INVALID_PARAMETER; return UINT32_MAX;
    }
    int flags = (access & 0x80000000u) && (access & 0x40000000u) ? O_RDWR : access & 0x40000000u ? O_WRONLY : O_RDONLY;
    static const int dispositions[] = {0, O_CREAT | O_EXCL, O_CREAT | O_TRUNC, 0, O_CREAT, O_TRUNC};
    flags |= dispositions[disposition];
    snprintf(path, sizeof(path), "%s/%s", p->directory, name);
    struct stat info;
    int existed = !stat(path, &info);
    int fd = open(path, flags, 0666);
    if (fd < 0) { *error = (int)win32_errno(errno); return UINT32_MAX; }
    pthread_mutex_lock(&p->mutex);
    uint32_t handle = handle_new(p, HANDLE_FILE, fd, NULL);
    pthread_mutex_unlock(&p->mutex);
    if (!handle) { close(fd); *error = ERROR_TOO_MANY_OPEN_FILES; *refusal = "handle table full"; return UINT32_MAX; }
    *error = existed && (disposition == 2 || disposition == 4) ? ERROR_ALREADY_EXISTS : 0;
    return handle;
}
static uint32_t write_file(PwK32Process *p, const PwX86State *s, const uint32_t *a, int *error, const char **refusal)
{
    if (a[4]) { *error = ERROR_NOT_SUPPORTED; *refusal = "overlapped I/O"; return 0; }
    if (!a[3]) { *error = ERROR_INVALID_PARAMETER; return 0; }
    if (!guest_span(s, a[3], 4, PW_X86_WRITE) || a[2] > 0x100000 || (a[2] && !guest_span(s, a[1], a[2], PW_X86_READ))) {
        *error = ERROR_NOACCESS; return 0;
    }
    uint32_t done = 0;
    memcpy((void *)(uintptr_t)a[3], &done, 4);
    pthread_mutex_lock(&p->mutex);
    Handle *h = handle_get(p, a[0]);
    int fd = h && h->kind == HANDLE_FILE ? h->fd : -1;
    while (fd >= 0 && done < a[2]) {
        ssize_t count = write(fd, (const uint8_t *)(uintptr_t)a[1] + done, a[2] - done);
        if (count <= 0) break;
        done += (uint32_t)count;
    }
    int failed = fd >= 0 && done < a[2] ? errno : 0;
    p->stats.bytes_written += done;
    pthread_mutex_unlock(&p->mutex);
    memcpy((void *)(uintptr_t)a[3], &done, 4);
    if (fd < 0) { *error = ERROR_INVALID_HANDLE; return 0; }
    if (failed) { *error = (int)win32_errno(failed); return 0; }
    return 1;
}
static uint32_t close_handle(PwK32Process *p, uint32_t value, int *error)
{
    pthread_mutex_lock(&p->mutex);
    Handle *h = handle_get(p, value);
    uint32_t result = 0;
    if (!h) *error = ERROR_INVALID_HANDLE;
    else if (h->kind == HANDLE_FILE) {
        result = !close(h->fd);
        if (!result) *error = (int)win32_errno(errno);
        h->kind = HANDLE_FREE;
    } else {
        Thread *t = h->thread;
        h->kind = HANDLE_FREE; t->handles--;
        if (t->finished && !t->handles) reap(t);
        result = 1;
    }
    pthread_mutex_unlock(&p->mutex);
    return result;
}
static uint32_t create_thread(PwK32Process *p, Thread *creator, const PwX86State *s, const uint32_t *a,
                              int *error, const char **refusal)
{
    if (a[0] || a[4]) { *error = ERROR_NOT_SUPPORTED; *refusal = "security attributes or creation flags"; return 0; }
    if (a[1] > STACK_BYTES) { *error = ERROR_NOT_ENOUGH_MEMORY; *refusal = "stack larger than 64 KiB"; return 0; }
    if (creator->in_loader) { *error = ERROR_NOT_SUPPORTED; *refusal = "CreateThread from a DLL notification"; return 0; }
    if (a[5] && !guest_span(s, a[5], 4, PW_X86_WRITE)) { *error = ERROR_NOACCESS; return 0; }
    pthread_mutex_lock(&p->mutex);
    Thread *t = NULL;
    for (unsigned i = 1; !t && i <= PW_K32_THREADS; ++i) if (!p->threads[i].used) t = &p->threads[i];
    uint32_t handle = t ? handle_new(p, HANDLE_THREAD, -1, t) : 0;
    if (!handle) {
        pthread_mutex_unlock(&p->mutex);
        *error = ERROR_NOT_ENOUGH_MEMORY; *refusal = "thread or handle table full"; return 0;
    }
    unsigned slot = (unsigned)(t - p->threads);
    memset(t, 0, sizeof(*t));
    t->process = p; t->slot = slot; t->used = 1; t->handles = 1;
    t->start = a[2]; t->parameter = a[3]; t->exit_code = STILL_ACTIVE;
    uint32_t own_teb = (uint32_t)(uintptr_t)creator->teb.region.write_base;
    for (unsigned i = 0; i < s->memory_count; ++i)
        if (s->memory[i].low != own_teb) t->inherited[t->inherited_count++] = s->memory[i];
    memcpy(t->bound, creator->bound, sizeof(t->bound)); t->bound_count = creator->bound_count;
    int rc = pthread_create(&t->host, NULL, thread_main, t);
    if (!rc) {
        t->started = 1;
        while (!t->setup_done) pthread_cond_wait(&p->changed, &p->mutex);
        rc = t->setup_rc;
        if (rc) reap(t);
    } else t->used = 0;
    if (rc) {
        p->handles[handle / 4 - 1].kind = HANDLE_FREE;
        pthread_mutex_unlock(&p->mutex);
        *error = ERROR_NOT_ENOUGH_MEMORY; *refusal = "host thread setup failed"; return 0;
    }
    p->stats.threads++;
    pthread_mutex_unlock(&p->mutex);
    uint32_t id = 0x100 + slot * 4;
    if (a[5]) memcpy((void *)(uintptr_t)a[5], &id, 4);
    return handle;
}
static uint32_t wait_thread(PwK32Process *p, const uint32_t *a, int *error, const char **refusal)
{
    pthread_mutex_lock(&p->mutex);
    Handle *h = handle_get(p, a[0]);
    uint32_t result = UINT32_MAX;
    if (!h) *error = ERROR_INVALID_HANDLE;
    else if (h->kind != HANDLE_THREAD) { *error = ERROR_NOT_SUPPORTED; *refusal = "only thread handles are waitable"; }
    else {
        Thread *t = h->thread;
        struct timespec deadline;
        clock_gettime(CLOCK_REALTIME, &deadline);
        deadline.tv_sec += a[1] / 1000;
        deadline.tv_nsec += (long)(a[1] % 1000) * 1000000;
        if (deadline.tv_nsec >= 1000000000) { deadline.tv_sec++; deadline.tv_nsec -= 1000000000; }
        int rc = 0;
        while (!t->finished && rc != ETIMEDOUT) {
            if (a[1] == UINT32_MAX) rc = pthread_cond_wait(&p->changed, &p->mutex);
            else rc = pthread_cond_timedwait(&p->changed, &p->mutex, &deadline);
            if (rc && rc != ETIMEDOUT) break;
        }
        if (t->finished) result = 0;
        else if (rc == ETIMEDOUT) result = WAIT_TIMEOUT;
        else *error = ERROR_GEN_FAILURE;
    }
    pthread_mutex_unlock(&p->mutex);
    return result;
}
static uint32_t exit_code_thread(PwK32Process *p, const PwX86State *s, const uint32_t *a, int *error)
{
    if (!guest_span(s, a[1], 4, PW_X86_WRITE)) { *error = ERROR_NOACCESS; return 0; }
    pthread_mutex_lock(&p->mutex);
    Handle *h = handle_get(p, a[0]);
    uint32_t code = h && h->kind == HANDLE_THREAD ? (h->thread->finished ? h->thread->exit_code : STILL_ACTIVE) : 0;
    int valid = h && h->kind == HANDLE_THREAD;
    pthread_mutex_unlock(&p->mutex);
    if (!valid) { *error = ERROR_INVALID_HANDLE; return 0; }
    memcpy((void *)(uintptr_t)a[1], &code, 4);
    return 1;
}
static int module_by_base(PwK32Process *p, uint32_t base)
{
    for (unsigned i = 0; i < MODULES; ++i) if (p->modules[i].kind && p->modules[i].image->base == base) return (int)i;
    return -1;
}
static int module_by_name(PwK32Process *p, const char *name)
{
    for (unsigned i = 0; i < MODULES; ++i) if (p->modules[i].kind && !strcmp(p->modules[i].name, name)) return (int)i;
    return -1;
}
/* Every loaded module except the EXE, for pw_pe32_link; mutex held. */
static size_t providers(PwK32Process *p, PwPe32Module *out)
{
    size_t count = 0;
    for (unsigned i = 0; i < MODULES; ++i)
        if (p->modules[i].kind == MODULE_SYNTHETIC || p->modules[i].kind == MODULE_DLL)
            out[count++] = (PwPe32Module){p->modules[i].name, p->modules[i].image};
    return count;
}
static uint8_t *read_module(const char *path, size_t *size, int *error)
{
    FILE *stream = fopen(path, "rb");
    if (!stream) { *error = errno == ENOENT ? ERROR_MOD_NOT_FOUND : (int)win32_errno(errno); return NULL; }
    long length = fseek(stream, 0, SEEK_END) ? -1 : ftell(stream);
    uint8_t *data = length > 0 && length <= PW_PE32_MAX_FILE && !fseek(stream, 0, SEEK_SET) ? malloc((size_t)length) : NULL;
    if (data && fread(data, 1, (size_t)length, stream) != (size_t)length) { free(data); data = NULL; }
    fclose(stream);
    if (!data) { *error = ERROR_BAD_FORMAT; return NULL; }
    *size = (size_t)length;
    return data;
}
/* Removes a DLL from the process list, then unmaps it. */
static void drop_module(PwK32Process *p, unsigned index)
{
    pthread_mutex_lock(&p->mutex);
    PwPe32Image *image = p->modules[index].image;
    memset(&p->modules[index], 0, sizeof(p->modules[index]));
    p->generation++;
    pthread_mutex_unlock(&p->mutex);
    pw_pe32_unload(image);
    free(image);
}
static uint32_t load_library(PwK32Process *p, Thread *t, const PwX86State *s, uint32_t address, int *error, const char **refusal)
{
    char name[64], wanted[64], path[260];
    int rc = guest_string(s, address, name, sizeof(name));
    if (!rc) rc = canonical(name, wanted, 1);
    if (rc) { *error = rc; return 0; }
    pthread_mutex_lock(&p->mutex);
    int found = module_by_name(p, wanted);
    if (found >= 0) {
        p->modules[found].refs++;
        pthread_mutex_unlock(&p->mutex);
        return p->modules[found].image->base;
    }
    unsigned index = 0;
    while (index < MODULES && p->modules[index].kind) ++index;
    pthread_mutex_unlock(&p->mutex);
    if (t->in_loader) { *error = ERROR_NOT_SUPPORTED; *refusal = "LoadLibraryA from a DLL notification"; return 0; }
    if (index == MODULES) { *error = ERROR_NOT_ENOUGH_MEMORY; *refusal = "module table full"; return 0; }
    size_t length = strlen(wanted);
    if (length < 5 || strcmp(wanted + length - 4, ".dll")) { *error = ERROR_MOD_NOT_FOUND; *refusal = "only .dll modules are loaded from disk"; return 0; }
    snprintf(path, sizeof(path), "%s/%s", p->module_directory, wanted);
    size_t bytes = 0;
    uint8_t *file = read_module(path, &bytes, error);
    if (!file) return 0;
    PwPe32Image *image = calloc(1, sizeof(*image));
    rc = image ? pw_pe32_load(&p->vm, file, bytes, 0, image) : PW_ERR_LIMIT;
    /* Preferred base taken: relocate into a small fixed pool when possible. */
    for (unsigned k = 0; rc == PW_ERR_VM && k < 4; ++k)
        rc = pw_pe32_load(&p->vm, file, bytes, RELOCATION_BASE + k * RELOCATION_STRIDE, image);
    free(file);
    if (rc) {
        free(image);
        *error = rc == PW_ERR_VM || rc == PW_ERR_LIMIT ? ERROR_NOT_ENOUGH_MEMORY : ERROR_BAD_FORMAT;
        trace(p, "PWK32 {\"thread\":%u,\"load\":\"%s\",\"rc\":%d}", t->slot, wanted, rc);
        if (rc == PW_ERR_UNSUPPORTED) *refusal = "PE feature outside the loader subset";
        return 0;
    }
    if (!image->info.is_dll) {
        pw_pe32_unload(image); free(image);
        *error = ERROR_BAD_FORMAT; return 0;
    }
    if (!image->linked) {
        PwPe32Module list[MODULES];
        pthread_mutex_lock(&p->mutex);
        size_t count = providers(p, list);
        pthread_mutex_unlock(&p->mutex);
        PwPe32LinkReport report;
        rc = pw_pe32_link(image, list, count, &report);
        if (rc) {
            trace(p, "PWK32 {\"thread\":%u,\"link\":%d,\"module\":\"%s\",\"symbol\":\"%s\"}", t->slot, rc, report.module, report.symbol);
            pw_pe32_unload(image); free(image);
            *error = rc == PW_ERR_NOT_FOUND ? ERROR_PROC_NOT_FOUND : ERROR_BAD_FORMAT;
            if (rc == PW_ERR_UNSUPPORTED) *refusal = "DLL imports from a module that itself imports";
            return 0;
        }
    }
    pthread_mutex_lock(&p->mutex);
    Module *m = &p->modules[index];
    memcpy(m->name, wanted, sizeof(wanted));
    m->image = image; m->kind = MODULE_DLL; m->refs = 1;
    p->generation++;
    pthread_mutex_unlock(&p->mutex);
    rc = pw_pe32_lifecycle_load(&p->life, image, &t->teb);
    if (rc) {
        trace(p, "PWK32 {\"thread\":%u,\"load\":\"%s\",\"attach\":%d}", t->slot, wanted, rc);
        drop_module(p, index);
        __atomic_fetch_add(&p->stats.dll_init_failures, 1, __ATOMIC_RELAXED);
        *error = ERROR_DLL_INIT_FAILED;
        return 0;
    }
    __atomic_fetch_add(&p->stats.modules_loaded, 1, __ATOMIC_RELAXED);
    return image->base;
}
static uint32_t get_proc(PwK32Process *p, const PwX86State *s, const uint32_t *a, int *error)
{
    pthread_mutex_lock(&p->mutex);
    int module = module_by_base(p, a[0]);
    const PwPe32Image *image = module < 0 ? NULL : p->modules[module].image;
    pthread_mutex_unlock(&p->mutex);
    if (!image) { *error = ERROR_MOD_NOT_FOUND; return 0; }
    char name[128] = {0};
    if (a[1] >= 0x10000) {
        int rc = guest_string(s, a[1], name, sizeof(name));
        if (rc) { *error = rc; return 0; }
    }
    for (unsigned i = 0; i < image->info.export_count; ++i) {
        const PwPe32Export *e = &image->info.exports[i];
        if (a[1] < 0x10000 ? e->ordinal == a[1] : !strcmp(e->name, name)) return image->base + e->rva;
    }
    *error = ERROR_PROC_NOT_FOUND;
    return 0;
}
static uint32_t free_library(PwK32Process *p, Thread *t, uint32_t base, int *error, const char **refusal)
{
    pthread_mutex_lock(&p->mutex);
    int module = module_by_base(p, base);
    unsigned last = module >= 0 && p->modules[module].kind == MODULE_DLL && p->modules[module].refs == 1;
    if (module >= 0 && !last && p->modules[module].refs > 1) p->modules[module].refs--;
    pthread_mutex_unlock(&p->mutex);
    if (module < 0) { *error = ERROR_MOD_NOT_FOUND; return 0; }
    /* Synthetic modules and the EXE are pinned for the process lifetime. */
    if (!last) return 1;
    if (t->in_loader) { *error = ERROR_NOT_SUPPORTED; *refusal = "FreeLibrary from a DLL notification"; return 0; }
    int rc = pw_pe32_lifecycle_unload(&p->life, p->modules[module].image, &t->teb);
    if (rc) trace(p, "PWK32 {\"thread\":%u,\"unload\":\"%s\",\"detach\":%d}", t->slot, p->modules[module].name, rc);
    drop_module(p, (unsigned)module);
    __atomic_fetch_add(&p->stats.modules_unloaded, 1, __ATOMIC_RELAXED);
    if (rc) { *error = ERROR_GEN_FAILURE; return 0; }
    return 1;
}
static CriticalSection *section_find(PwK32Process *p, uint32_t address)
{
    for (unsigned i = 0; i < SECTIONS; ++i) if (p->sections[i].used && p->sections[i].address == address) return &p->sections[i];
    return NULL;
}
/* The guest CRITICAL_SECTION bytes are left untouched; ownership is host-side.
 * Contended entry waits on the process condition. */
static uint32_t critical_section(PwK32Process *p, Thread *t, const PwX86State *s, PwK32Call *c)
{
    uint32_t address = c->a[0];
    c->bits = 0;
    if (!guest_span(s, address, 24, PW_X86_READ | PW_X86_WRITE)) { c->refusal = "critical section outside guest memory"; return 0; }
    pthread_mutex_lock(&p->mutex);
    CriticalSection *cs = section_find(p, address);
    unsigned me = t->slot + 1;
    if (c->index == K32_INIT_CS) {
        if (!cs) for (unsigned i = 0; !cs && i < SECTIONS; ++i) if (!p->sections[i].used) cs = &p->sections[i];
        if (cs) *cs = (CriticalSection){address, 1, 0, 0};
        else c->refusal = "critical section table full";
    } else if (!cs) c->refusal = "critical section not initialized";
    else if (c->index == K32_DELETE_CS) {
        if (cs->count) c->refusal = "critical section deleted while owned";
        cs->used = 0;
    } else if (c->index == K32_ENTER_CS) {
        while (cs->used && cs->count && cs->owner != me) pthread_cond_wait(&p->changed, &p->mutex);
        if (!cs->used) c->refusal = "critical section deleted while waiting";
        else { cs->owner = me; cs->count++; }
    } else {
        if (cs->owner != me || !cs->count) c->refusal = "critical section left by a non-owner";
        else if (!--cs->count) { cs->owner = 0; pthread_cond_broadcast(&p->changed); }
    }
    pthread_mutex_unlock(&p->mutex);
    return 0;
}
/* MEMORY_BASIC_INFORMATION from the logical region table. */
static uint32_t virtual_query(PwK32Process *p, const PwX86State *s, PwK32Call *c)
{
    uint32_t address = c->a[0], out = c->a[1];
    if (c->a[2] < 28) { c->error = ERROR_BAD_LENGTH; return 0; }
    if (!guest_span(s, out, 28, PW_X86_WRITE)) { c->error = ERROR_NOACCESS; return 0; }
    uint32_t info[7] = {address & ~0xfffu, 0, 1, 0x1000, 0x10000, 1, 0};
    for (unsigned i = 0; i < s->memory_count; ++i) {
        const PwX86Memory *m = &s->memory[i];
        if (m->low > address || m->high <= address) continue;
        unsigned perm = m->permissions;
        uint32_t protect = perm & PW_X86_EXEC ? (perm & PW_X86_WRITE ? 0x40 : 0x20) : perm & PW_X86_WRITE ? 4 : 2;
        int module = -1;
        pthread_mutex_lock(&p->mutex);
        for (unsigned j = 0; j < MODULES; ++j)
            if (p->modules[j].kind && contains(p->modules[j].image->base, p->modules[j].image->info.image_bytes, address)) module = (int)j;
        uint32_t allocation = module >= 0 ? p->modules[module].image->base : (uint32_t)m->low;
        pthread_mutex_unlock(&p->mutex);
        info[1] = allocation; info[2] = protect;
        info[3] = (uint32_t)(((m->high + 0xfff) & ~0xfffull) - info[0]);
        info[4] = 0x1000; info[5] = protect; info[6] = module >= 0 ? 0x1000000 : 0x20000;
        break;
    }
    memcpy((void *)(uintptr_t)out, info, sizeof(info));
    return 28;
}
static uint32_t kernel32_handler(void *state, PwK32Call *c)
{
    PwK32Process *p = state;
    Thread *t = c->thread;
    PwX86State *s = c->state;
    const uint32_t *a = c->a;
    switch (c->index) {
    case K32_CLOSE: return close_handle(p, a[0], &c->error);
    case K32_CREATE_FILE: return create_file(p, s, a, &c->error, &c->refusal);
    case K32_CREATE_THREAD: return create_thread(p, t, s, a, &c->error, &c->refusal);
    case K32_DELETE_CS: case K32_ENTER_CS: case K32_INIT_CS: case K32_LEAVE_CS: return critical_section(p, t, s, c);
    case K32_EXIT_PROCESS: c->exit = 1; c->exit_code = a[0]; return 0;
    case K32_FREE_LIBRARY: return free_library(p, t, a[0], &c->error, &c->refusal);
    case K32_CURRENT_PROCESS: return CURRENT_PROCESS;
    case K32_PROCESS_ID: return (uint32_t)getpid();
    case K32_EXIT_CODE: return exit_code_thread(p, s, a, &c->error);
    case K32_GET_ERROR: return *last_error(s);
    case K32_MODULE_HANDLE: {
        if (!a[0]) {
            for (unsigned i = 0; i < MODULES; ++i) if (p->modules[i].kind == MODULE_EXE) return p->modules[i].image->base;
            c->error = ERROR_MOD_NOT_FOUND; return 0;
        }
        char name[64], wanted[64];
        int rc = guest_string(s, a[0], name, sizeof(name));
        if (!rc) rc = canonical(name, wanted, 1);
        if (rc) { c->error = rc; return 0; }
        pthread_mutex_lock(&p->mutex);
        int found = module_by_name(p, wanted);
        uint32_t base = found >= 0 ? p->modules[found].image->base : 0;
        pthread_mutex_unlock(&p->mutex);
        if (!base) c->error = ERROR_MOD_NOT_FOUND;
        return base;
    }
    case K32_GET_PROC: return get_proc(p, s, a, &c->error);
    case K32_STARTUP_INFO: {
        c->bits = 0;
        if (!guest_span(s, a[0], 68, PW_X86_WRITE)) { c->refusal = "STARTUPINFOA outside guest memory"; return 0; }
        uint32_t info[17] = {68};
        memcpy((void *)(uintptr_t)a[0], info, sizeof(info));
        return 0;
    }
    case K32_LOAD_LIBRARY: return load_library(p, t, s, a[0], &c->error, &c->refusal);
    case K32_SET_ERROR: c->error = (int)a[0]; c->bits = 0; return 0;
    case K32_EXCEPTION_FILTER: {
        /* Recorded only: no SEH delivery exists that would call it. */
        pthread_mutex_lock(&p->mutex);
        uint32_t previous = p->exception_filter;
        p->exception_filter = a[0];
        pthread_mutex_unlock(&p->mutex);
        return previous;
    }
    case K32_SLEEP:
        c->bits = 0;
        if (!a[0]) sched_yield();
        for (uint32_t left = a[0]; left && left != UINT32_MAX;) {
            uint32_t chunk = left > 1000 ? 1000 : left;
            usleep(chunk * 1000);
            left -= chunk;
        }
        if (a[0] == UINT32_MAX) c->refusal = "infinite Sleep";
        return 0;
    case K32_TERMINATE:
        if (a[0] == CURRENT_PROCESS) { c->exit = 1; c->exit_code = a[1]; return 0; }
        c->error = ERROR_NOT_SUPPORTED; c->refusal = "only the current process can be terminated";
        return 0;
    case K32_TLS_GET:
        /* TlsSlots[64] at TEB+0xE10; TlsAlloc is not served, so all read zero. */
        if (a[0] >= 64) { c->error = ERROR_INVALID_PARAMETER; return 0; }
        c->error = 0;
        return *(uint32_t *)(uintptr_t)(s->fs_base + 0xe10 + a[0] * 4);
    case K32_VIRTUAL_PROTECT:
        c->error = ERROR_NOT_SUPPORTED; c->refusal = "VirtualProtect: protections are fixed at load";
        return 0;
    case K32_VIRTUAL_QUERY: return virtual_query(p, s, c);
    case K32_WAIT: return wait_thread(p, a, &c->error, &c->refusal);
    case K32_WRITE_FILE: return write_file(p, s, a, &c->error, &c->refusal);
    }
    c->refusal = "unknown kernel32 slot";
    return 0;
}
static int request_exit(PwK32Process *p, Thread *t, const char *call, uint32_t code)
{
    pthread_mutex_lock(&p->mutex);
    if (!p->exiting) { p->exiting = 1; p->exit_code = code; p->stats.exited = 1; }
    pthread_mutex_unlock(&p->mutex);
    trace(p, "PWK32 {\"thread\":%u,\"call\":\"%s\",\"code\":%u}", t->slot, call, code);
    return EXITED;
}

static int dispatch(PwK32Process *p, Thread *t, PwX86State *s, Module *m)
{
    const PwK32Module *def = m->synthetic;
    uint32_t offset = s->eip - m->image->base - SLOT_RVA;
    unsigned index = offset / SLOT_BYTES;
    if (s->eip < m->image->base + SLOT_RVA || offset % SLOT_BYTES || index >= def->count || def->exports[index].data) {
        trace(p, "PWK32 {\"thread\":%u,\"invalid_thunk\":\"0x%x\"}", t->slot, s->eip);
        return PW_ERR_NOT_FOUND;
    }
    const PwK32Export *e = &def->exports[index];
    PwGuestCall frame = {0};
    PwK32Call c = {p, t, s, &frame, index, {0}, KEEP_ERROR, NULL, 32, 0, 0, 0};
    int rc = pw_guest_call_begin(&frame, s, e->cdecl ? PW_GUEST_CDECL : PW_GUEST_STDCALL, e->bytes, e->variadic);
    for (unsigned i = 0; !rc && i < e->bytes / 4; ++i) rc = pw_guest_call_u32(&frame, i * 4, &c.a[i]);
    if (rc) return rc;
    if (def == &kernel32_module) __atomic_fetch_add(&p->stats.calls[index], 1, __ATOMIC_RELAXED);
    else if (index < PW_MSVCRT_EXPORTS) __atomic_fetch_add(&p->stats.crt_calls[index], 1, __ATOMIC_RELAXED);
    uint32_t result = def->handler(m->state, &c);
    if (c.refusal) __atomic_fetch_add(&p->stats.refused, 1, __ATOMIC_RELAXED);
    if (c.rc) return c.rc;
    if (c.exit) return request_exit(p, t, e->name, c.exit_code);
    if (c.error != KEEP_ERROR) *last_error(s) = (uint32_t)c.error;
    trace(p, "PWK32 {\"thread\":%u,\"call\":\"%s\",\"result\":\"0x%x\",\"error\":%d%s%s%s}", t->slot,
          e->name, result, c.error, c.refusal ? ",\"refused\":\"" : "", c.refusal ? c.refusal : "", c.refusal ? "\"" : "");
    return pw_guest_call_finish(&frame, c.bits, result);
}
static int execute(PwK32Process *p, Thread *t, uint32_t stop, int honor_exit)
{
    PwX86State *s = pw_cpu_ps4_state(t->cpu);
    uint64_t steps = 0;
    int rc = PW_OK;
    while (s->eip != stop) {
        if (honor_exit && __atomic_load_n(&p->exiting, __ATOMIC_ACQUIRE)) { rc = EXITED; break; }
        if (t->generation != __atomic_load_n(&p->generation, __ATOMIC_ACQUIRE) && (rc = refresh(p, t, s))) break;
        Module *m = thunk_module(p, s->eip);
        if (m) {
            rc = dispatch(p, t, s, m);
            if (rc) break;
            continue;
        }
        if (steps == p->max_steps) { rc = PW_ERR_LIMIT; break; }
        steps++;
        rc = pw_cpu_ps4_step(t->cpu);
        if (rc) break;
    }
    t->steps += steps;
    return rc;
}

/* Thunk page (RVA 0..0x4000, HLT slots from 0x1000) and an optional RW data page. */
static int synthetic_create(PwK32Process *p, const PwK32Module *def, uint32_t base, Module *out, uint8_t **data_host)
{
    unsigned data = 0;
    for (unsigned i = 0; i < def->count; ++i) if (def->exports[i].data) data = 1;
    if (def->count > (THUNK_LIMIT - SLOT_RVA) / SLOT_BYTES || def->count > PW_PE32_MAX_EXPORTS) return PW_ERR_LIMIT;
    PwPe32Image *image = calloc(1, sizeof(*image));
    if (!image) return PW_ERR_LIMIT;
    image->backend = p->vm;
    uint32_t bytes = (1 + data) * PW_PE32_PAGE;
    int rc = p->vm.reserve_at(p->vm.context, base, bytes, PW_PE32_PAGE, &image->region);
    if (!rc) rc = p->vm.commit(p->vm.context, &image->region, 0, bytes, PW_PROT_READ | PW_PROT_WRITE);
    if (!rc) {
        memset(image->region.write_base, 0xf4, PW_PE32_PAGE);
        if (data) memset((uint8_t *)image->region.write_base + PW_PE32_PAGE, 0, PW_PE32_PAGE);
        rc = p->vm.protect(p->vm.context, &image->region, 0, PW_PE32_PAGE, PW_PROT_READ);
    }
    if (rc) {
        if (image->region.handle) p->vm.release(p->vm.context, &image->region);
        free(image);
        return rc;
    }
    PwPe32Info *info = &image->info;
    info->preferred = base; info->image_bytes = bytes; info->is_dll = 1;
    info->section_alignment = 0x1000; info->header_mapped_bytes = 0x1000; info->section_count = 1 + data;
    info->sections[0] = (PwPe32Section){SLOT_RVA, THUNK_LIMIT - SLOT_RVA, THUNK_LIMIT - SLOT_RVA, 0, 0, PW_PROT_READ | PW_PROT_EXEC};
    if (data) info->sections[1] = (PwPe32Section){PW_PE32_PAGE, PW_PE32_PAGE, PW_PE32_PAGE, 0, 0, PW_PROT_READ | PW_PROT_WRITE};
    info->export_count = def->count;
    for (unsigned i = 0; i < def->count; ++i) {
        const PwK32Export *e = &def->exports[i];
        snprintf(info->exports[i].name, sizeof(info->exports[i].name), "%s", e->name);
        info->exports[i].ordinal = i + 1;
        info->exports[i].rva = e->data ? PW_PE32_PAGE + e->data - 1 : SLOT_RVA + i * SLOT_BYTES;
    }
    image->base = base; image->linked = 1; image->init_state = 2;
    image->page_count = 1 + data;
    for (unsigned i = 0; i <= data; ++i) {
        image->page_occupied[i] = 1;
        image->page_permissions[i] = i ? PW_PROT_READ | PW_PROT_WRITE : PW_PROT_READ;
    }
    *out = (Module){image, {0}, MODULE_SYNTHETIC, 1, def, NULL};
    snprintf(out->name, sizeof(out->name), "%s", def->name);
    if (data_host) *data_host = data ? (uint8_t *)image->region.write_base + PW_PE32_PAGE : NULL;
    return PW_OK;
}
static void synthetic_destroy(Module *m)
{
    if (m->kind != MODULE_SYNTHETIC) return;
    pw_pe32_unload(m->image);
    free(m->image);
    memset(m, 0, sizeof(*m));
}

int pw_k32_ps4_create(PwK32Process **out, const PwVmBackend *vm, uint32_t base, const char *directory,
                      const char *module_directory, PwK32Trace trace_line, void *opaque)
{
    if (!out || !pw_vm_backend_valid(vm) || vm->page_bytes != PW_PE32_PAGE || !vm->reserve_at || !directory ||
        !module_directory || base % 0x10000 || strlen(directory) >= sizeof(((PwK32Process *)0)->directory) ||
        strlen(module_directory) >= sizeof(((PwK32Process *)0)->module_directory)) return PW_ERR_PRECONDITION;
    PwK32Process *p = calloc(1, sizeof(*p));
    if (!p) return PW_ERR_LIMIT;
    p->vm = *vm; p->sink = trace_line; p->opaque = opaque; p->generation = 1;
    strcpy(p->directory, directory);
    strcpy(p->module_directory, module_directory);
    if (pthread_mutex_init(&p->mutex, NULL)) { free(p); return PW_ERR_STATE; }
    if (pthread_cond_init(&p->changed, NULL)) { pthread_mutex_destroy(&p->mutex); free(p); return PW_ERR_STATE; }
    uint8_t *crt_data = NULL;
    int rc = synthetic_create(p, &kernel32_module, base, &p->modules[0], NULL);
    if (!rc) p->modules[0].state = p;
    if (!rc) rc = synthetic_create(p, &pw_msvcrt_ps4_module, base + MSVCRT_OFFSET, &p->modules[2], &crt_data);
    if (!rc) rc = pw_msvcrt_ps4_create(&p->crt, p, vm, HEAP_BASE, base + MSVCRT_OFFSET + PW_PE32_PAGE, crt_data);
    if (!rc) p->modules[2].state = p->crt;
    if (rc) {
        if (p->crt) pw_msvcrt_ps4_destroy(p->crt);
        synthetic_destroy(&p->modules[2]);
        synthetic_destroy(&p->modules[0]);
        pthread_cond_destroy(&p->changed); pthread_mutex_destroy(&p->mutex); free(p);
        return rc;
    }
    *out = p;
    return PW_OK;
}
PwPe32Image *pw_k32_ps4_image(PwK32Process *p) { return p ? p->modules[0].image : NULL; }

int pw_k32_ps4_run(PwK32Process *p, PwPe32Image *exe, const char *exe_name,
                   uint32_t stack, uint32_t teb, uint64_t max_steps)
{
    if (!p || !exe || !exe->region.handle || exe->info.is_dll || !exe_name || !max_steps ||
        stack % 0x10000 || teb % 0x10000) return PW_ERR_PRECONDITION;
    if (p->ran) return PW_ERR_STATE;
    p->ran = 1; p->max_steps = max_steps; p->stack = stack; p->teb = teb;
    Module *exe_module = &p->modules[1];
    if (canonical(exe_name, exe_module->name, 0) || pw_msvcrt_ps4_set_program(p->crt, exe_name)) return PW_ERR_PRECONDITION;
    PwPe32Module list[MODULES];
    size_t count = providers(p, list);
    int rc = pw_pe32_link(exe, list, count, &p->stats.link);
    p->stats.link_rc = (unsigned)rc;
    if (rc) {
        trace(p, "PWK32 {\"link\":%d,\"module\":\"%s\",\"symbol\":\"%s\"}", rc, p->stats.link.module, p->stats.link.symbol);
        return rc;
    }
    pthread_mutex_lock(&p->mutex);
    exe_module->image = exe; exe_module->kind = MODULE_EXE; exe_module->refs = 1;
    p->generation++;
    pthread_mutex_unlock(&p->mutex);
    /* The EXE joins first, for its static TLS (index 0, as on Windows). */
    PwPe32Image *images[] = {exe, p->modules[0].image};
    rc = exe->info.tls_bytes ? pw_pe32_lifecycle_create(&p->life, &p->vm, images, 2)
                             : pw_pe32_lifecycle_create(&p->life, &p->vm, images + 1, 1);
    if (!rc) rc = pw_pe32_lifecycle_set_runner(&p->life, runner, p);
    if (rc) return rc;
    Thread *main_thread = &p->threads[0];
    main_thread->process = p; main_thread->used = 1;
    rc = setup(p, main_thread, stack, teb);
    uint64_t value = 0;
    if (!rc) {
        PwX86State *s = pw_cpu_ps4_state(main_thread->cpu);
        PwGuestCallback frame = {0};
        rc = pw_guest_callback_enter(&frame, s, exe->entry, RETURN_TOKEN, NULL, 0, PW_GUEST_CDECL);
        if (!rc) rc = execute(p, main_thread, RETURN_TOKEN, 1);
        if (!rc) {
            /* Returning from the entry point ends the process with EAX. */
            rc = pw_guest_callback_leave(&frame, 32, &value);
            pthread_mutex_lock(&p->mutex);
            if (!rc && !p->exiting) { p->exiting = 1; p->exit_code = (uint32_t)value; p->stats.returned = 1; }
            pthread_mutex_unlock(&p->mutex);
        }
        if (rc && rc != EXITED) trace(p, "PWK32 {\"thread\":0,\"fault\":%d,\"eip\":\"0x%x\"}", rc, s->eip);
        if (rc == EXITED) rc = PW_OK;
    } else trace(p, "PWK32 {\"thread\":0,\"setup\":%d}", rc);
    pthread_mutex_lock(&p->mutex);
    p->exiting = 1;
    for (unsigned i = 1; i <= PW_K32_THREADS; ++i) {
        Thread *t = &p->threads[i];
        while (t->used && !t->finished) pthread_cond_wait(&p->changed, &p->mutex);
        if (t->used) reap(t);
    }
    for (unsigned i = 0; i < PW_K32_HANDLES; ++i) {
        if (!p->handles[i].kind) continue;
        if (p->handles[i].kind == HANDLE_FILE) close(p->handles[i].fd);
        p->handles[i].kind = HANDLE_FREE;
        p->stats.leaked_handles++;
    }
    if (!p->stats.run_rc) p->stats.run_rc = (unsigned)rc;
    if (!rc && p->stats.thread_failures) rc = (int)p->stats.run_rc;
    p->stats.exit_code = p->exit_code;
    pthread_mutex_unlock(&p->mutex);
    /* Still-loaded DLLs get PROCESS_DETACH from the main thread teardown. */
    if (teardown(p, main_thread) && !rc) rc = PW_ERR_STATE;
    p->stats.steps += main_thread->steps;
    p->stats.notifications = p->life.events;
    main_thread->used = 0;
    if (pw_pe32_lifecycle_destroy(&p->life) && !rc) rc = PW_ERR_STATE;
    for (unsigned i = 0; i < MODULES; ++i) if (p->modules[i].kind == MODULE_DLL) drop_module(p, i);
    pthread_mutex_lock(&p->mutex);
    memset(exe_module, 0, sizeof(*exe_module));
    pthread_mutex_unlock(&p->mutex);
    return rc;
}
int pw_k32_ps4_stats(PwK32Process *p, PwK32Stats *out)
{
    if (!p || !out) return PW_ERR_PRECONDITION;
    pthread_mutex_lock(&p->mutex);
    *out = p->stats;
    pw_msvcrt_ps4_stats(p->crt, out);
    pthread_mutex_unlock(&p->mutex);
    return PW_OK;
}
int pw_k32_ps4_destroy(PwK32Process *p)
{
    if (!p) return PW_ERR_PRECONDITION;
    if (p->life.initialized) return PW_ERR_STATE;
    int rc = pw_msvcrt_ps4_destroy(p->crt);
    for (unsigned i = 0; i < MODULES; ++i) synthetic_destroy(&p->modules[i]);
    pthread_cond_destroy(&p->changed);
    pthread_mutex_destroy(&p->mutex);
    free(p);
    return rc;
}
