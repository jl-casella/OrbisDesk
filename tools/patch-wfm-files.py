#!/usr/bin/env python3
"""W105: correct WFM enumeration and preserve real failure evidence (MIT upstream)."""
import pathlib,sys,shutil
root=pathlib.Path(sys.argv[1])
shutil.copy2(pathlib.Path(__file__).resolve().parent/'wfm-operations.h',root/'pwfm_operations.h')
def patch(name,old,new):
    p=root/name;t=p.read_text()
    if t.count(old)!=1:raise SystemExit('WFM context changed: '+name+': '+old[:80])
    p.write_text(t.replace(old,new,1))
patch('main.c','#include "main.h"','#include "main.h"\n#include "pw_shell_open.h"')
for name in ('file_actions.c','content_view.c'):
    patch(name,'#include "main.h"','#include "main.h"\n#include "pwfm_operations.h"')
patch('content_view.c','''            MoveFileW(oldFilename, newFilename);''','''            if (!MoveFileW(oldFilename, newFilename))
                pwfmOperationError(L"Rename",oldFilename,GetLastError());
            else OutputDebugStringW(L"PWFM rename_success");''')
patch('file_actions.c','''                SHFILEOPSTRUCT sfo = {0};
                sfo.hwnd = hwndDlg;
                sfo.wFunc = FO_DELETE;
                sfo.fFlags = FOF_SILENT | FOF_NOCONFIRMATION | FOF_NOERRORUI;
                sfo.pTo = NULL;
                sfo.pFrom = actionData->srcPaths[i];
                
                int res = SHFileOperation(&sfo);
                if (res != 0) break;''','''                if (!pwfmDeleteTree(actionData->srcPaths[i], &actionData->cancel)) {
                    pwfmOperationError(L"Delete",actionData->srcPaths[i],GetLastError());
                    break;
                }''')
patch('main.c','''        ShellExecute(hwndMain, L"open", path, NULL, parentPath, SW_SHOW);''',r'''        if (GetEnvironmentVariableW(L"WINE_PS4_GUESTS", NULL, 0)) {
            struct pw_shell_open_request request = {0};
            COPYDATASTRUCT data = {0};
            DWORD_PTR accepted = 0;
            wcscpy_s(request.path, MAX_PATH, path);
            wcscpy_s(request.directory, MAX_PATH, parentPath);
            data.dwData = PW_SHELL_OPEN_TAG; data.cbData = sizeof(request); data.lpData = &request;
            OutputDebugStringW(L"PWFM open_via_explorer");
            if (!SendMessageTimeoutW(GetDesktopWindow(), WM_COPYDATA, (WPARAM)hwndMain,
                                     (LPARAM)&data, SMTO_ABORTIFHUNG | SMTO_BLOCK, 5000, &accepted) || !accepted)
                MessageBoxW(hwndMain, L"El escritorio no pudo recibir la solicitud de apertura.", L"Abrir archivo", MB_OK | MB_ICONERROR);
        } else ShellExecute(hwndMain, L"open", path, NULL, parentPath, SW_SHOW);''')
patch('file_node.c','#include "main.h"','''#include "main.h"

static void logEnumeration(const wchar_t *kind, const wchar_t *path, DWORD error, unsigned count) {
    wchar_t message[512];
    swprintf_s(message, 512, L"PWFM %ls path=%ls error=%lu count=%u", kind, path, error, count);
    OutputDebugStringW(message);
}''')
patch('file_node.c','''        GetLogicalDriveStrings(MAX_PATH, drives);''','''        DWORD length = GetLogicalDriveStrings(MAX_PATH, drives);
        logEnumeration(L"drive_strings", L"Computer", length ? 0 : GetLastError(), length);
        if (!length || length >= MAX_PATH) return;''')
patch('file_node.c','''            if (!isPathExists(drive)) continue;''','''            DWORD attributes = GetFileAttributesW(drive);
            logEnumeration(L"drive_root", drive, attributes == INVALID_FILE_ATTRIBUTES ? GetLastError() : 0, attributes);
            if (attributes == INVALID_FILE_ATTRIBUTES || !(attributes & FILE_ATTRIBUTE_DIRECTORY)) continue;''')
patch('file_node.c','''        if (!isPathExists(path)) return;''','''        if (!isPathExists(path)) {
            logEnumeration(L"path_unavailable", path, GetLastError(), 0);
            return;
        }''')
patch('file_node.c','''        HANDLE handle = FindFirstFile(path, &wfd);
        ''','''        HANDLE handle = FindFirstFile(path, &wfd);
        if (handle == INVALID_HANDLE_VALUE) {
            logEnumeration(L"find_first_failed", path, GetLastError(), 0);
            return;
        }
        ''')
patch('file_node.c','''(onlyDirs && (wfd.dwFileAttributes & FILE_ATTRIBUTE_ARCHIVE))''','''(onlyDirs && !(wfd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY))''')
patch('file_node.c','''            if (((wfd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) || (wfd.dwFileAttributes & FILE_ATTRIBUTE_ARCHIVE)) &&
                !(wfd.dwFileAttributes & FILE_ATTRIBUTE_HIDDEN)) {''','''            if (!(wfd.dwFileAttributes & FILE_ATTRIBUTE_HIDDEN)) {''')
patch('file_node.c','''        FindClose(handle);
    }
    
    parent->children = firstChild;''','''        DWORD error = GetLastError();
        FindClose(handle);
        logEnumeration(L"find_end", path, error == ERROR_NO_MORE_FILES ? 0 : error, 0);
    }
    
    parent->children = firstChild;
    logEnumeration(L"children", parent->name, 0, getChildNodeCount(parent));''')
patch('content_view.c','''        if ((info.dwFileAttributes & FILE_ATTRIBUTE_ARCHIVE)) {''','''        if (info.dwFileAttributes != INVALID_FILE_ATTRIBUTES && !(info.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY)) {''')
# Phase 10 hot plug: WM_DEVICECHANGE from explorer's shell monitor (a USB drive came or went)
patch('main.c','''        case WM_DESTROY: {
            PostQuitMessage(0);
            return 0;
        }
        case WM_NOTIFY: {''','''        case WM_DESTROY: {
            PostQuitMessage(0);
            return 0;
        }
        case WM_DEVICECHANGE: {
            /* a USB drive came or went: leave a folder on a drive that is gone, read Computer again */
            if ((wParam == 0x8000 /* DBT_DEVICEARRIVAL */ || wParam == 0x8004 /* DBT_DEVICEREMOVECOMPLETE */) && currPathFileNode) {
                struct FileNode* drive = currPathFileNode;
                while (drive && drive->type != TYPE_DRIVE) drive = drive->parent;
                if (drive && drive->parent) {
                    wchar_t root[4] = {drive->name[0], L':', L'\\\\', 0};
                    if (GetFileAttributesW(root) == INVALID_FILE_ATTRIBUTES) navigateToFileNode(drive->parent);
                }
                else if (currPathFileNode->type == TYPE_COMPUTER) navigateRefresh();
            }
            return TRUE;
        }
        case WM_NOTIFY: {''')
