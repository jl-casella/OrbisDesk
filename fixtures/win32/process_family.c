/* SPDX-License-Identifier: LGPL-2.1-or-later */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>

struct shared_state {
    DWORD magic, parent_pid, child_pid, parent_base, child_base;
    volatile LONG heartbeat, ready, observed;
};
static HANDLE log_file;

static unsigned append(char *out, unsigned at, const char *text)
{
    while (*text) out[at++] = *text++;
    return at;
}
static unsigned number(char *out, unsigned at, DWORD value)
{
    char digits[10]; unsigned count = 0;
    do { digits[count++] = (char)('0' + value % 10); value /= 10; } while (value);
    while (count) out[at++] = digits[--count];
    return at;
}
static void record(const char *event, DWORD error, DWORD detail)
{
    char out[320]; DWORD written; unsigned n = 0;
    n = append(out, n, "{\"event\":\""); n = append(out, n, event);
    n = append(out, n, "\",\"pid\":"); n = number(out, n, GetCurrentProcessId());
    n = append(out, n, ",\"image_base\":"); n = number(out, n, (DWORD)(ULONG_PTR)GetModuleHandleW(NULL));
    n = append(out, n, ",\"error\":"); n = number(out, n, error);
    n = append(out, n, ",\"detail\":"); n = number(out, n, detail);
    n = append(out, n, "}\r\n");
    if (log_file != INVALID_HANDLE_VALUE) {
        WriteFile(log_file, out, n, &written, NULL);
        FlushFileBuffers(log_file);
    }
}
static BOOL sibling(WCHAR *out, const WCHAR *name)
{
    DWORD length = GetModuleFileNameW(NULL, out, MAX_PATH);
    if (!length || length >= MAX_PATH) return FALSE;
    while (length && out[length - 1] != '\\' && out[length - 1] != '/') --length;
    while (*name && length < MAX_PATH - 1) out[length++] = *name++;
    out[length] = 0;
    return !*name;
}
static DWORD probe(void)
{
    WCHAR path[MAX_PATH]; HANDLE mapping; struct shared_state *state;
#ifdef FAMILY_CHILD
    WCHAR name[96]; HANDLE parent; LONG initial; DWORD start;
    if (!sibling(path, L"child.jsonl")) return 10;
    log_file = CreateFileW(path, GENERIC_WRITE, FILE_SHARE_READ, NULL, CREATE_ALWAYS, 0, NULL);
    record("child_entered", 0, 0);
    if (!GetEnvironmentVariableW(L"ORBISDESK_FAMILY_MAPPING", name, 96)) { record("missing_environment", GetLastError(), 0); return 11; }
    mapping = OpenFileMappingW(FILE_MAP_ALL_ACCESS, FALSE, name);
    if (!mapping) { record("mapping_open_failed", GetLastError(), 0); return 12; }
    state = MapViewOfFile(mapping, FILE_MAP_ALL_ACCESS, 0, 0, sizeof(*state));
    if (!state) { record("mapping_view_failed", GetLastError(), 0); CloseHandle(mapping); return 13; }
    state->child_pid = GetCurrentProcessId();
    state->child_base = (DWORD)(ULONG_PTR)GetModuleHandleW(NULL);
    record("mapping_opened", 0, state->parent_pid);
    if (state->magic != 0x504f5031 || state->parent_pid == state->child_pid) {
        record("process_identity_failed", 0, state->parent_pid); return 14;
    }
    parent = OpenProcess(SYNCHRONIZE, FALSE, state->parent_pid);
    if (!parent) { record("parent_open_failed", GetLastError(), state->parent_pid); return 15; }
    initial = state->heartbeat; start = GetTickCount();
    InterlockedExchange(&state->ready, 1);
    while (state->heartbeat <= initial && GetTickCount() - start < 5000) Sleep(10);
    if (state->heartbeat <= initial || WaitForSingleObject(parent, 0) != WAIT_TIMEOUT) {
        record("parent_not_progressing", 0, state->heartbeat); return 16;
    }
    InterlockedExchange(&state->observed, 1);
    record("child_verified", 0, state->parent_base);
    CloseHandle(parent); UnmapViewOfFile(state); CloseHandle(mapping);
    return 42;
#else
    WCHAR name[96] = L"Local\\OrbisDeskFamily-";
    WCHAR command[MAX_PATH * 2]; unsigned at = 22, i; DWORD pid, tick, exit_code = 0, started;
    STARTUPINFOW startup = {sizeof(startup)}; PROCESS_INFORMATION process = {0};
    if (!sibling(path, L"parent.jsonl")) return 20;
    log_file = CreateFileW(path, GENERIC_WRITE, FILE_SHARE_READ, NULL, CREATE_ALWAYS, 0, NULL);
    record("parent_entered", 0, 0);
    pid = GetCurrentProcessId(); tick = GetTickCount();
    /* A fresh object prevents stale state from being mistaken for a new child. */
    for (i = 0; name[i]; ++i) ;
    at = i;
    for (i = 0; i < 8; ++i) name[at++] = L"0123456789abcdef"[(pid >> (28 - 4 * i)) & 15];
    name[at++] = '-';
    for (i = 0; i < 8; ++i) name[at++] = L"0123456789abcdef"[(tick >> (28 - 4 * i)) & 15];
    name[at] = 0;
    SetLastError(0);
    mapping = CreateFileMappingW(INVALID_HANDLE_VALUE, NULL, PAGE_READWRITE, 0, sizeof(*state), name);
    if (!mapping || GetLastError() == ERROR_ALREADY_EXISTS) { record("mapping_create_failed", GetLastError(), 0); return 21; }
    state = MapViewOfFile(mapping, FILE_MAP_ALL_ACCESS, 0, 0, sizeof(*state));
    if (!state) { record("mapping_view_failed", GetLastError(), 0); CloseHandle(mapping); return 22; }
    state->magic = 0x504f5031; state->parent_pid = pid;
    state->parent_base = (DWORD)(ULONG_PTR)GetModuleHandleW(NULL);
    if (!SetEnvironmentVariableW(L"ORBISDESK_FAMILY_MAPPING", name)) { record("environment_failed", GetLastError(), 0); return 23; }
    if (!sibling(path, L"family-child.exe")) return 24;
    command[0] = '"';
    for (i = 0; path[i]; ++i) command[i + 1] = path[i];
    command[i + 1] = '"'; command[i + 2] = 0;
    record("create_child_attempt", 0, state->parent_base);
    if (!CreateProcessW(path, command, NULL, NULL, FALSE, CREATE_SUSPENDED, NULL, NULL, &startup, &process)) {
        record("create_child_failed", GetLastError(), 0); return 25;
    }
    record("create_child_returned", 0, process.dwProcessId);
    if (process.dwProcessId == pid) { record("process_identity_failed", 0, pid); return 26; }
    if (ResumeThread(process.hThread) == (DWORD)-1) { record("resume_failed", GetLastError(), 0); TerminateProcess(process.hProcess, 27); return 27; }
    started = GetTickCount();
    while (WaitForSingleObject(process.hProcess, 20) == WAIT_TIMEOUT && GetTickCount() - started < 10000)
        InterlockedIncrement(&state->heartbeat);
    if (WaitForSingleObject(process.hProcess, 0) != WAIT_OBJECT_0) {
        record("child_timeout", GetLastError(), 0); TerminateProcess(process.hProcess, 28); return 28;
    }
    if (!GetExitCodeProcess(process.hProcess, &exit_code) || exit_code != 42 || !state->observed ||
        state->child_pid != process.dwProcessId || state->child_base != 0x400000) {
        record("child_contract_failed", GetLastError(), exit_code); return 29;
    }
    record("family_verified", 0, state->child_pid);
    CloseHandle(process.hThread); CloseHandle(process.hProcess);
    UnmapViewOfFile(state); CloseHandle(mapping);
    return 0;
#endif
}
void entry(void)
{
    DWORD result;
    log_file = INVALID_HANDLE_VALUE;
    result = probe();
    record("exit", 0, result);
    if (log_file != INVALID_HANDLE_VALUE) CloseHandle(log_file);
    ExitProcess(result);
}
