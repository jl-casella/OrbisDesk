/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* File locks the way SQLite takes them on Windows (docs/SEAMONKEY_FILE_LOCKS.md), 32- or 64-bit.
 * SeaMonkey on the console reported NS_ERROR_STORAGE_BUSY: SQLite returns SQLITE_BUSY whenever
 * LockFileEx fails, whatever the error. This program takes SQLite's locks on a file next to it
 * (lockprobe.db, and lockprobe.db-shm for the WAL locks) through two handles, as two connections
 * to one database do, and writes one line per step to lockprobe-result.txt next to it (appended,
 * one block per run) and to stdout:
 *   <step> ok|fail error=<Win32 error> expect=ok|<error> match|MISMATCH
 * 33 is ERROR_LOCK_VIOLATION, the conflict Windows reports between the two handles; 158 is
 * ERROR_NOT_LOCKED. The last line counts the mismatches. On Windows every line says match. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#define PENDING_BYTE  0x40000000u  /* SQLite's lock bytes (os_win.c) */
#define RESERVED_BYTE (PENDING_BYTE + 1)
#define SHARED_FIRST  (PENDING_BYTE + 2)
#define SHARED_SIZE   510
#define SHM_BASE      120          /* WIN_SHM_BASE: the -shm file's lock bytes */

static FILE *out;
static int mismatches;

static void say(const char *format, ...)
{
    va_list args;
    va_start(args, format); vprintf(format, args); va_end(args);
    if (out) { va_start(args, format); vfprintf(out, format, args); va_end(args); fflush(out); }
}

static void check(const char *step, BOOL ok, DWORD expect)
{
    DWORD error = ok ? 0 : GetLastError();
    int match = expect ? (!ok && error == expect) : ok;
    char want[16];
    if (expect) snprintf(want, sizeof(want), "%lu", expect); else strcpy(want, "ok");
    if (!match) mismatches++;
    if (ok) say("%-24s ok expect=%s %s\n", step, want, match ? "match" : "MISMATCH");
    else say("%-24s fail error=%lu expect=%s %s\n", step, error, want, match ? "match" : "MISMATCH");
}

static BOOL lock(HANDLE file, BOOL exclusive, DWORD offset, DWORD length)
{
    OVERLAPPED at; memset(&at, 0, sizeof(at)); at.Offset = offset;
    return LockFileEx(file, LOCKFILE_FAIL_IMMEDIATELY | (exclusive ? LOCKFILE_EXCLUSIVE_LOCK : 0), 0, length, 0, &at);
}

static BOOL unlock(HANDLE file, DWORD offset, DWORD length)
{
    OVERLAPPED at; memset(&at, 0, sizeof(at)); at.Offset = offset;
    return UnlockFileEx(file, 0, length, 0, &at);
}

static HANDLE open_shared(const char *path, DWORD disposition)
{
    return CreateFileA(path, GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE, NULL, disposition,
                       FILE_ATTRIBUTE_NORMAL, NULL);
}

int main(void)
{
    char dir[MAX_PATH], path[MAX_PATH], shm[MAX_PATH], result[MAX_PATH], *slash;
    char block[4096];
    DWORD written;
    SYSTEMTIME now;
    HANDLE a, b, s1, s2;

    GetModuleFileNameA(NULL, dir, sizeof(dir));
    if ((slash = strrchr(dir, '\\'))) *slash = 0;
    snprintf(path, sizeof(path), "%s\\lockprobe.db", dir);
    snprintf(shm, sizeof(shm), "%s\\lockprobe.db-shm", dir);
    snprintf(result, sizeof(result), "%s\\lockprobe-result.txt", dir);
    out = fopen(result, "a");
    GetLocalTime(&now);
    say("lockprobe %d-bit %04u-%02u-%02u %02u:%02u:%02u file=%s\n", (int)(sizeof(void *) * 8), now.wYear, now.wMonth,
        now.wDay, now.wHour, now.wMinute, now.wSecond, path);

    a = open_shared(path, CREATE_ALWAYS);
    if (a == INVALID_HANDLE_VALUE) { say("open_a fail error=%lu\n", GetLastError()); return 1; }
    memset(block, 0, sizeof(block));
    if (!WriteFile(a, block, sizeof(block), &written, NULL)) say("write fail error=%lu\n", GetLastError());
    b = open_shared(path, OPEN_EXISTING);
    if (b == INVALID_HANDLE_VALUE) { say("open_b fail error=%lu\n", GetLastError()); return 1; }

    /* the old API, low offset */
    check("lockfile_a_0", LockFile(a, 0, 0, 1, 0), 0);
    check("lockfile_b_0", LockFile(b, 0, 0, 1, 0), ERROR_LOCK_VIOLATION);
    check("unlockfile_a_0", UnlockFile(a, 0, 0, 1, 0), 0);

    /* connection a: SHARED (pending byte, then the shared range), then RESERVED */
    check("a_pending", lock(a, TRUE, PENDING_BYTE, 1), 0);
    check("a_shared", lock(a, FALSE, SHARED_FIRST, SHARED_SIZE), 0);
    check("a_unlock_pending", unlock(a, PENDING_BYTE, 1), 0);
    check("a_reserved", lock(a, TRUE, RESERVED_BYTE, 1), 0);
    /* connection b: SHARED next to a's, RESERVED refused */
    check("b_pending", lock(b, TRUE, PENDING_BYTE, 1), 0);
    check("b_shared", lock(b, FALSE, SHARED_FIRST, SHARED_SIZE), 0);
    check("b_unlock_pending", unlock(b, PENDING_BYTE, 1), 0);
    check("b_reserved_busy", lock(b, TRUE, RESERVED_BYTE, 1), ERROR_LOCK_VIOLATION);
    /* a wants EXCLUSIVE while b reads: refused; after b's unlock it gets it */
    check("a_pending_2", lock(a, TRUE, PENDING_BYTE, 1), 0);
    check("a_unlock_shared", unlock(a, SHARED_FIRST, SHARED_SIZE), 0);
    check("a_exclusive_busy", lock(a, TRUE, SHARED_FIRST, SHARED_SIZE), ERROR_LOCK_VIOLATION);
    check("b_unlock_shared", unlock(b, SHARED_FIRST, SHARED_SIZE), 0);
    check("a_exclusive", lock(a, TRUE, SHARED_FIRST, SHARED_SIZE), 0);
    check("a_unlock_exclusive", unlock(a, SHARED_FIRST, SHARED_SIZE), 0);
    check("a_unlock_pending_2", unlock(a, PENDING_BYTE, 1), 0);
    check("a_unlock_reserved", unlock(a, RESERVED_BYTE, 1), 0);
    check("a_unlock_twice", unlock(a, RESERVED_BYTE, 1), ERROR_NOT_LOCKED);

    /* WAL: the -shm file's lock bytes (winShmSystemLock) */
    s1 = open_shared(shm, CREATE_ALWAYS);
    s2 = open_shared(shm, OPEN_EXISTING);
    if (s1 == INVALID_HANDLE_VALUE || s2 == INVALID_HANDLE_VALUE) say("open_shm fail error=%lu\n", GetLastError());
    else
    {
        WriteFile(s1, block, sizeof(block), &written, NULL);
        check("shm_dms_shared_a", lock(s1, FALSE, SHM_BASE + 8, 1), 0);
        check("shm_dms_shared_b", lock(s2, FALSE, SHM_BASE + 8, 1), 0);
        check("shm_write_a", lock(s1, TRUE, SHM_BASE, 1), 0);
        check("shm_write_b_busy", lock(s2, TRUE, SHM_BASE, 1), ERROR_LOCK_VIOLATION);
        check("shm_unlock_write_a", unlock(s1, SHM_BASE, 1), 0);
        check("shm_write_b", lock(s2, TRUE, SHM_BASE, 1), 0);
        check("shm_unlock_write_b", unlock(s2, SHM_BASE, 1), 0);
        CloseHandle(s2);
        CloseHandle(s1);
    }
    /* a lock dies with its handle */
    check("b_lock_end", lock(b, TRUE, 0, 1), 0);
    CloseHandle(b);
    check("a_after_close_b", lock(a, TRUE, 0, 1), 0);
    CloseHandle(a);
    DeleteFileA(shm);
    DeleteFileA(path);
    say("lockprobe done mismatches=%d\n", mismatches);
    if (out) fclose(out);
    return mismatches ? 2 : 0;
}
