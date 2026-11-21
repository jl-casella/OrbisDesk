#!/usr/bin/env python3
"""W106: marshal file opening to Explorer's desktop thread, without retaining caller data."""
from pathlib import Path
import sys,shutil
root=Path(sys.argv[1]);project=Path(__file__).resolve().parents[1]
shutil.copy2(project/'platform/ps4/pw_shell_open.h',root/'pw_shell_open.h')
shutil.copy2(project/'tools/explorer-dos.h',root/'explorer-dos.h')
p=root/'desktop.c';t=p.read_text();t=t.replace('#include "resource.h"','#include "resource.h"\n#include "pw_shell_open.h"',1)
t=t.replace('#include "pw_shell_open.h"','#include "pw_shell_open.h"\n#include "explorer-dos.h"',1)
t=t.replace('#include "explorer-dos.h"','#include "explorer-dos.h"\n'+r'''
/* PoP D.4: programs a separate Windows process starts run here, as guests. It writes PW_TITLE_LAUNCH_FILE and
 * waits; this thread reads and removes it and posts the request to the desktop window, which answers in
 * PW_TITLE_LAUNCH_REPLY_FILE (platform/ps4/pw_shell_open.h). */
static void pw_title_launch_reply(DWORD token, const char *what, DWORD value)
{
    char text[64];
    DWORD done = 0;
    int n = snprintf(text, sizeof(text), "%lu %s %lu\n", token, what, value);
    HANDLE file = CreateFileW(PW_TITLE_LAUNCH_REPLY_FILE, GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_DELETE, NULL,
                              CREATE_ALWAYS, 0, NULL);
    if (file == INVALID_HANDLE_VALUE) return;
    WriteFile(file, text, n, &done, NULL);
    CloseHandle(file);
}

struct pw_title_launch_wait { HANDLE handles[2]; HANDLE done; DWORD token; };

/* the guest has ended when its end event (a 64-bit guest's process handle) or its main thread is signaled; a
 * 32-bit guest's process handle is this process (kernelbase ps4_world_launch), so its thread tells. The reply
 * carries its exit status: a 64-bit guest's process handle answers it (W267), a 32-bit guest's main thread does.
 * PoP D.5: then the named end event, the separate process's handle for this program, is signaled. */
static DWORD WINAPI pw_title_launch_waiter(void *arg)
{
    struct pw_title_launch_wait *wait = arg;
    DWORD count = wait->handles[1] ? 2 : 1, code = 0;
    WaitForMultipleObjects(count, wait->handles, FALSE, INFINITE);
    if (!GetExitCodeProcess(wait->handles[0], &code) || code == STILL_ACTIVE)
        if (!wait->handles[1] || !GetExitCodeThread(wait->handles[1], &code) || code == STILL_ACTIVE) code = 0;
    pw_title_launch_reply(wait->token, "ended", code);
    if (wait->done) { SetEvent(wait->done); CloseHandle(wait->done); }
    CloseHandle(wait->handles[0]);
    if (wait->handles[1]) CloseHandle(wait->handles[1]);
    HeapFree(GetProcessHeap(), 0, wait);
    return 0;
}

static DWORD WINAPI pw_title_launch_watch(void *arg)
{
    HWND desktop = arg;
    for (;;)
    {
        char text[4096], *line[4] = {0}, *p;
        DWORD got = 0;
        int k;
        HANDLE file;
        Sleep(500);
        file = CreateFileW(PW_TITLE_LAUNCH_FILE, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_DELETE, NULL, OPEN_EXISTING, 0, NULL);
        if (file == INVALID_HANDLE_VALUE) continue;
        ReadFile(file, text, sizeof(text) - 1, &got, NULL);
        CloseHandle(file);
        DeleteFileW(PW_TITLE_LAUNCH_FILE);
        text[got] = 0;
        for (p = text, k = 0; k < 4 && p && *p; k++) { line[k] = p; p = strchr(p, '\n'); if (p) *p++ = 0; }
        if (line[0] && line[0][0])
        {
            struct pw_shell_launch_request *launch = HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, sizeof(*launch));
            if (!launch) continue;
            MultiByteToWideChar(CP_UTF8, 0, line[0], -1, launch->image, MAX_PATH - 1);
            MultiByteToWideChar(CP_UTF8, 0, line[1] ? line[1] : line[0], -1, launch->command, 1023);
            if (line[2]) MultiByteToWideChar(CP_UTF8, 0, line[2], -1, launch->directory, MAX_PATH - 1);
            if (line[3]) launch->token = strtoul(line[3], NULL, 10);
            if (!PostMessageW(desktop, PW_SHELL_LAUNCH_MESSAGE, 0, (LPARAM)launch))
            {
                pw_title_launch_reply(launch->token, "failed", GetLastError());
                HeapFree(GetProcessHeap(), 0, launch);
            }
        }
    }
    return 0;
}
''',1)
anchor='''    switch(message)
    {
    case WM_SYSCOMMAND:'''
replacement=r'''    {
        /* PoP D.4: the watcher for programs a separate process hands to this title, started once */
        static LONG title_launch_started;
        if (!InterlockedExchange(&title_launch_started, 1))
        {
            HANDLE thread = CreateThread(NULL, 0, pw_title_launch_watch, hwnd, 0, NULL);
            if (thread) CloseHandle(thread);
        }
    }
    switch(message)
    {
    case PW_SHELL_LAUNCH_MESSAGE:
        {
            struct pw_shell_launch_request *launch = (void *)lp;
            STARTUPINFOW si = {sizeof(si)};
            PROCESS_INFORMATION pi = {0};
            BOOL ok;
            DWORD error;
            /* Hardware 2026-11-16 (run-0174): Warcraft III's war3.exe, handed over by its launcher in the separate
             * process, came with no directory and started in explorer's, so it found none of its .mpq files and
             * said "Warcraft III was unable to initialize". With none, the program's own folder, where a launcher
             * started from the desktop runs. */
            if (!launch->directory[0])
            {
                WCHAR *slash = wcsrchr(launch->image, '\\');
                if (slash && slash - launch->image < MAX_PATH - 1)
                {
                    memcpy(launch->directory, launch->image, (slash - launch->image) * sizeof(WCHAR));
                    launch->directory[slash - launch->image] = 0;
                    if (slash - launch->image == 2) lstrcatW(launch->directory, L"\\");   /* "E:" is not a root */
                }
            }
            ok = CreateProcessW(launch->image, launch->command, NULL, NULL, FALSE, 0, NULL,
                                launch->directory[0] ? launch->directory : NULL, &si, &pi);
            error = ok ? 0 : GetLastError();
            ERR("PWLAUNCH image=%s command=%s dir=%s ok=%d error=%lu pid=%04lx\n", debugstr_w(launch->image),
                debugstr_w(launch->command), debugstr_w(launch->directory), ok, error, pi.dwProcessId);
            if (ok)
            {
                struct pw_title_launch_wait *wait = HeapAlloc(GetProcessHeap(), 0, sizeof(*wait));
                HANDLE thread = NULL, done;
                WCHAR done_name[64];
                /* PoP D.5: the separate process's CreateProcess returns this event as the program's process handle
                 * (native/pop_wine_child_stubs.c); it is created before the reply that lets that process open it */
                wsprintfW(done_name, L"Global\\PWTitleLaunch_%lu", launch->token);
                done = CreateEventW(NULL, TRUE, FALSE, done_name);
                pw_title_launch_reply(launch->token, "started", pi.dwProcessId);
                if (wait)
                {
                    wait->handles[0] = pi.hProcess;
                    wait->handles[1] = pi.hThread;
                    wait->done = done;
                    wait->token = launch->token;
                    thread = CreateThread(NULL, 0, pw_title_launch_waiter, wait, 0, NULL);
                }
                if (thread) CloseHandle(thread);
                else
                {
                    /* nothing to wait with: the separate process ends now, as before */
                    pw_title_launch_reply(launch->token, "ended", 0);
                    if (done) { SetEvent(done); CloseHandle(done); }
                    CloseHandle(pi.hThread);
                    CloseHandle(pi.hProcess);
                    HeapFree(GetProcessHeap(), 0, wait);
                }
            }
            else pw_title_launch_reply(launch->token, "failed", error);
            HeapFree(GetProcessHeap(), 0, launch);
            return 0;
        }
    case WM_COPYDATA:
        {
            const COPYDATASTRUCT *data = (const COPYDATASTRUCT *)lp;
            const struct pw_shell_open_request *request;
            struct pw_shell_open_request *copy;
            DWORD pid = 0;
            if (!data || data->dwData != PW_SHELL_OPEN_TAG) break;
            if (!GetEnvironmentVariableW(L"WINE_PS4_GUESTS", NULL, 0)) return FALSE;
            GetWindowThreadProcessId((HWND)wp, &pid);
            if (pid != GetCurrentProcessId() || data->cbData != sizeof(*request) || !data->lpData) return FALSE;
            request = data->lpData;
            if (!request->path[0] || request->path[MAX_PATH - 1] ||
                request->directory[MAX_PATH - 1]) return FALSE;
            copy = HeapAlloc(GetProcessHeap(), 0, sizeof(*copy));
            if (!copy) return FALSE;
            memcpy(copy, request, sizeof(*copy));
            if (!PostMessageW(hwnd, PW_SHELL_OPEN_MESSAGE, 0, (LPARAM)copy))
            { HeapFree(GetProcessHeap(), 0, copy); return FALSE; }
            ERR("PWOPEN queued path=%s tid=%04lx\n", debugstr_w(copy->path), GetCurrentThreadId());
            return TRUE;
        }
    case PW_SHELL_OPEN_MESSAGE:
        {
            struct pw_shell_open_request *request = (void *)lp;
            SHELLEXECUTEINFOW info = {sizeof(info)};
            BOOL opened;
            DWORD error;
            WCHAR parameters[MAX_PATH + 3];
            /* Only our WM_COPYDATA handler posts this message in this title.
             * Do not retain pointers into the WFM guest or create its workers. */
            info.fMask = SEE_MASK_NOASYNC | SEE_MASK_FLAG_NO_UI;
            info.hwnd = hwnd; info.lpVerb = L"open";
            info.lpFile = request->path; info.lpDirectory = request->directory;
            info.nShow = SW_SHOWNORMAL;
            if (pw_is_dos_file(request->path))
            {
                HWND existing = FindWindowW(L"OrbisDesk.DOSHost", NULL);
                if (existing)
                {
                    SetForegroundWindow(existing);
                    MessageBoxW(hwnd, L"Cerrá el juego DOS abierto antes de iniciar otro.", L"DOS", MB_OK);
                    HeapFree(GetProcessHeap(), 0, request);
                    return 0;
                }
                swprintf(parameters, ARRAY_SIZE(parameters), L"\"%s\"", request->path);
                info.lpFile = L"C:\\windows\\system32\\doshost.exe";
                info.lpParameters = parameters;
                ERR("PWDOS dispatch path=%s tid=%04lx\n", debugstr_w(request->path), GetCurrentThreadId());
            }
            SetLastError(0);
            opened = ShellExecuteExW(&info); error = GetLastError();
            ERR("PWOPEN result path=%s opened=%u error=%lu tid=%04lx\n",
                debugstr_w(request->path), opened, error, GetCurrentThreadId());
            if (!opened) MessageBoxW(hwnd, L"No se pudo abrir el archivo. Puede faltar una aplicación compatible o una asociación.",
                                     L"Abrir archivo", MB_OK | MB_ICONERROR);
            HeapFree(GetProcessHeap(), 0, request);
            return 0;
        }
    case WM_SYSCOMMAND:'''
assert t.count(anchor)==1
p.write_text(t.replace(anchor,replacement,1))
