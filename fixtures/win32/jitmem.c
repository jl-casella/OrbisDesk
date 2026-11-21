/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* SeaMonkey flexible memory (docs/SEAMONKEY_FLEXIBLE_MEMORY.md): memory the way SeaMonkey 2.53 (Gecko 60) uses it, 64-bit (a guest). SeaMonkey's heavy
 * pages ran the title's flexible memory dry (W224/W225); this program does the same allocations
 * without the browser. Steps, each on its own line of C:\orbis\jitmem-result.txt:
 *   memory   GlobalMemoryStatusEx before the steps (OrbisDesk reports direct + flexible memory)
 *   heap     mozjemalloc's chunks: VirtualAlloc of 1 MiB, MEM_RESERVE | MEM_COMMIT, read/write;
 *            everything after the first 16 KiB decommitted at once (arena_chunk_init with
 *            MALLOC_DECOMMIT); then runs of 16, 32 and 64 KiB committed again one by one, checked
 *            for zeros (Windows hands a page committed again out zeroed) and written. Chunks
 *            (argument 1, 384 by default: 384 MiB, about the flexible pool) stay allocated.
 *   purge    on every fourth chunk, two of the runs decommitted and committed again (mozjemalloc's
 *            purge), checked for zeros again
 *   views    256 VirtualAlloc of 80 KiB committed (the size W224 saw refused: "map_view anon mmap
 *            error ... size 0x14000"), each written
 *   jit      SpiderMonkey's executable memory: 1 GiB reserved PAGE_NOACCESS, then 64 KiB pieces
 *            (argument 2, 256 by default) committed read/write, filled with "mov eax, n; ret",
 *            changed to PAGE_EXECUTE_READ with VirtualProtect, FlushInstructionCache, and called
 *   release  every chunk, view and the reservation released with MEM_RELEASE
 * A step that fails stops at its first failure with the Win32 error and the count done so far; a
 * step after it that cannot run says skipped=..., never ok. The file is appended to, one block per
 * run. With the fix the flexible memory the steps use should come back in the log as "PWVM flexible
 * low" only near the end of the pool, and "PWVM decommit_host ... keeps direct memory". */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHUNK (1024 * 1024)
#define HEADER (16 * 1024)
#define VIEW_SIZE 0x14000
#define VIEWS 256
#define JIT_RESERVE (1024ull * 1024 * 1024)
#define JIT_PIECE (64 * 1024)

static FILE *out;

static void line(const char *format, ...)
{
    va_list args;
    va_start(args, format);
    vfprintf(out, format, args);
    va_end(args);
    fputc('\n', out);
    fflush(out);
}

static void memory(const char *when)
{
    MEMORYSTATUSEX status;
    status.dwLength = sizeof(status);
    if (!GlobalMemoryStatusEx(&status)) line("memory %s error=%lu", when, GetLastError());
    else line("memory %s total_phys=%llu avail_phys=%llu avail_virtual=%llu", when,
              (unsigned long long)status.ullTotalPhys, (unsigned long long)status.ullAvailPhys,
              (unsigned long long)status.ullAvailVirtual);
}

static int zeroed(const unsigned char *p, size_t size)
{
    size_t i;
    for (i = 0; i < size; i++) if (p[i]) return 0;
    return 1;
}

/* one run committed again, checked for zeros and written; 0 or the Win32 error (or -1: not zero) */
static long run_commit(unsigned char *p, size_t size, unsigned char fill)
{
    if (!VirtualAlloc(p, size, MEM_COMMIT, PAGE_READWRITE)) return (long)GetLastError();
    if (!zeroed(p, size)) return -1;
    memset(p, fill, size);
    return 0;
}

int main(int argc, char **argv)
{
    static const size_t runs[] = {16 * 1024, 32 * 1024, 64 * 1024};
    unsigned int chunk_count = argc > 1 ? (unsigned int)strtoul(argv[1], NULL, 0) : 384;
    unsigned int jit_count = argc > 2 ? (unsigned int)strtoul(argv[2], NULL, 0) : 256;
    unsigned char **chunks, *views[VIEWS], *jit = NULL;
    unsigned int made = 0, purged = 0, view_count = 0, pieces = 0, i;
    const char *stopped = NULL;
    long error = 0;

    out = fopen(argc > 3 ? argv[3] : "C:\\orbis\\jitmem-result.txt", "a");  /* argument 3: another file */
    if (!out) return 2;
    line("begin jitmem chunks=%u jit_pieces=%u", chunk_count, jit_count);
    memory("before");
    chunks = calloc(chunk_count ? chunk_count : 1, sizeof(*chunks));
    if (!chunks) { line("heap error=calloc"); fclose(out); return 2; }

    for (made = 0; made < chunk_count; made++)
    {
        unsigned char *c = VirtualAlloc(NULL, CHUNK, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
        size_t at = HEADER;
        unsigned int r;

        if (!c) { error = (long)GetLastError(); break; }
        chunks[made] = c;
        memset(c, 0xa5, HEADER);
        if (!VirtualFree(c + HEADER, CHUNK - HEADER, MEM_DECOMMIT)) { error = (long)GetLastError(); made++; break; }
        for (r = 0; at < CHUNK; r++)
        {
            size_t size = runs[r % 3];
            if (at + size > CHUNK) size = CHUNK - at;
            if ((error = run_commit(c + at, size, (unsigned char)(made + r + 1)))) break;
            at += size;
        }
        if (error) { made++; break; }
        if (made % 4 == 3)
        {
            /* the purge: two runs decommitted and committed again */
            if (!VirtualFree(c + HEADER, 32 * 1024, MEM_DECOMMIT) ||
                !VirtualFree(c + CHUNK / 2, 64 * 1024, MEM_DECOMMIT)) { error = (long)GetLastError(); made++; break; }
            if ((error = run_commit(c + HEADER, 32 * 1024, 0x5a)) ||
                (error = run_commit(c + CHUNK / 2, 64 * 1024, 0x5b))) { made++; stopped = "purge"; break; }
            purged++;
        }
    }
    if (error && !stopped) stopped = "heap";
    if (stopped && !strcmp(stopped, "heap"))
        line("heap failed error=%ld chunks=%u of %u%s", error, made, chunk_count, error == -1 ? " (not zeroed)" : "");
    else line("heap ok chunks=%u mib=%u", made, made);
    if (stopped && !strcmp(stopped, "purge"))
        line("purge failed error=%ld purged=%u%s", error, purged, error == -1 ? " (not zeroed)" : "");
    else if (stopped) line("purge skipped=heap purged=%u", purged);
    else line("purge ok purged=%u", purged);
    memory("after heap");

    if (stopped) line("views skipped=%s", stopped);
    else
    {
        for (view_count = 0; view_count < VIEWS; view_count++)
        {
            unsigned char *v = VirtualAlloc(NULL, VIEW_SIZE, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
            if (!v) { error = (long)GetLastError(); break; }
            views[view_count] = v;
            memset(v, 0x3c, VIEW_SIZE);
        }
        if (view_count < VIEWS) { line("views failed error=%ld views=%u of %u", error, view_count, VIEWS); stopped = "views"; }
        else line("views ok views=%u", view_count);
    }

    if (stopped) line("jit skipped=%s", stopped);
    else if (!(jit = VirtualAlloc(NULL, JIT_RESERVE, MEM_RESERVE, PAGE_NOACCESS)))
    {
        line("jit failed reserve error=%lu", GetLastError());
        stopped = "jit";
    }
    else
    {
        for (pieces = 0; pieces < jit_count && pieces < JIT_RESERVE / JIT_PIECE; pieces++)
        {
            unsigned char *p = jit + (size_t)pieces * JIT_PIECE;
            DWORD old;
            int (*code)(void);
            int got;

            if (!VirtualAlloc(p, JIT_PIECE, MEM_COMMIT, PAGE_READWRITE)) { error = (long)GetLastError(); break; }
            /* mov eax, imm32; ret, at the start and at the last bytes of the piece */
            p[0] = 0xb8; memcpy(p + 1, &pieces, 4); p[5] = 0xc3;
            p[JIT_PIECE - 6] = 0xb8; memcpy(p + JIT_PIECE - 5, &pieces, 4); p[JIT_PIECE - 1] = 0xc3;
            if (!VirtualProtect(p, JIT_PIECE, PAGE_EXECUTE_READ, &old)) { error = (long)GetLastError(); break; }
            FlushInstructionCache(GetCurrentProcess(), p, JIT_PIECE);
            code = (int (*)(void))p;
            got = code();
            code = (int (*)(void))(p + JIT_PIECE - 6);
            if (got != (int)pieces || code() != (int)pieces) { error = -2; break; }
            /* W^X: back to writable, as the JIT does to patch code */
            if (!VirtualProtect(p, JIT_PIECE, PAGE_READWRITE, &old)) { error = (long)GetLastError(); break; }
            p[0] = 0xc3;
            if (!VirtualProtect(p, JIT_PIECE, PAGE_EXECUTE_READ, &old)) { error = (long)GetLastError(); break; }
        }
        if (pieces < jit_count) { line("jit failed error=%ld pieces=%u of %u%s", error, pieces, jit_count,
                                      error == -2 ? " (wrong result)" : ""); stopped = "jit"; }
        else line("jit ok pieces=%u kib=%u", pieces, pieces * (JIT_PIECE / 1024));
    }
    memory("after jit");

    {
        unsigned int released = 0, failures = 0;
        for (i = 0; i < made; i++) if (chunks[i]) { if (VirtualFree(chunks[i], 0, MEM_RELEASE)) released++; else failures++; }
        for (i = 0; i < view_count; i++) { if (VirtualFree(views[i], 0, MEM_RELEASE)) released++; else failures++; }
        if (jit) { if (VirtualFree(jit, 0, MEM_RELEASE)) released++; else failures++; }
        if (failures) line("release failed failures=%u released=%u", failures, released);
        else line("release ok released=%u", released);
    }
    memory("after release");
    line("end jitmem %s", stopped ? stopped : "ok");
    fclose(out);
    free(chunks);
    return stopped ? 1 : 0;
}
