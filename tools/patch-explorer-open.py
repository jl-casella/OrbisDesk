#!/usr/bin/env python3
"""W106: marshal file opening to Explorer's desktop thread, without retaining caller data."""
from pathlib import Path
import sys,shutil
root=Path(sys.argv[1]);project=Path(__file__).resolve().parents[1]
shutil.copy2(project/'platform/ps4/pw_shell_open.h',root/'pw_shell_open.h')
shutil.copy2(project/'tools/explorer-dos.h',root/'explorer-dos.h')
p=root/'desktop.c';t=p.read_text();t=t.replace('#include "resource.h"','#include "resource.h"\n#include "pw_shell_open.h"',1)
t=t.replace('#include "pw_shell_open.h"','#include "pw_shell_open.h"\n#include "explorer-dos.h"',1)
anchor='''    switch(message)
    {
    case WM_SYSCOMMAND:'''
replacement=r'''    switch(message)
    {
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
