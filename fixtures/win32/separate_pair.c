/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* PoP Phase D.3 / P019: a launcher and its game, both PE32 linked at 0x400000, like Prince of Persia's
 * launcher and POP.exe. Built twice (fixtures/win32, -DSEPARATE_GAME for the game).
 *
 * separate_launcher.exe runs on the desktop as an ordinary program (a guest of the title). It sets
 * HKCU\Software\Wine\AppDefaults\separate_game.exe\OrbisExecutionMode = "separate" (what winecfg's
 * "Separate processes" choice writes), starts separate_game.exe with CreateProcess, waits for it and records
 * its process id, image base and exit code.
 *
 * separate_game.exe, started that way, runs in the separate native process: both images then hold
 * 0x400000 at the same time, in two processes. It shows a window (static user32 imports: the desktop comes
 * from the separate process itself), counts clicks and keys, and exits with 44 after 60 s.
 * Results: Z:\orbisdesk\process-p014\separate-launcher.txt and separate-game.txt (Z: is /data). */
#include <windows.h>
#include <stdio.h>

#ifdef SEPARATE_GAME
static unsigned ticks, clicks, keys;
static LRESULT CALLBACK proc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp)
{
    switch (msg)
    {
    case WM_TIMER: if (++ticks >= 120) DestroyWindow(hwnd); else InvalidateRect(hwnd, NULL, FALSE); return 0;
    case WM_LBUTTONDOWN: case WM_RBUTTONDOWN: clicks++; InvalidateRect(hwnd, NULL, FALSE); return 0;
    case WM_KEYDOWN: keys++; InvalidateRect(hwnd, NULL, FALSE); return 0;
    case WM_PAINT:
    {
        PAINTSTRUCT ps; RECT rc; char line[96]; int n;
        HDC dc = BeginPaint(hwnd, &ps);
        GetClientRect(hwnd, &rc);
        FillRect(dc, &rc, (HBRUSH)GetStockObject(BLACK_BRUSH));
        SetBkMode(dc, TRANSPARENT); SetTextColor(dc, RGB(255, 210, 60));
        n = sprintf(line, "Juego PE32 en proceso separado (D.3)"); TextOutA(dc, 16, 16, line, n);
        n = sprintf(line, "base %p  pid %lu  segundos %u", (void *)GetModuleHandleA(NULL), GetCurrentProcessId(), ticks / 2);
        TextOutA(dc, 16, 48, line, n);
        n = sprintf(line, "clicks %u  teclas %u", clicks, keys); TextOutA(dc, 16, 80, line, n);
        EndPaint(hwnd, &ps);
        return 0;
    }
    case WM_DESTROY: PostQuitMessage(0); return 0;
    }
    return DefWindowProcA(hwnd, msg, wp, lp);
}

int main(int argc, char **argv)
{
    WNDCLASSA wc = {0}; MSG msg; HWND hwnd; FILE *f; char cwd[MAX_PATH] = "";
    GetCurrentDirectoryA(MAX_PATH, cwd);
    wc.lpfnWndProc = proc; wc.hInstance = GetModuleHandleA(NULL); wc.lpszClassName = "OrbisSeparateGame";
    wc.hCursor = LoadCursorA(NULL, (LPCSTR)IDC_ARROW);
    RegisterClassA(&wc);
    hwnd = CreateWindowExA(0, "OrbisSeparateGame", "Juego separado (D.3)", WS_OVERLAPPEDWINDOW | WS_VISIBLE,
                           420, 200, 440, 200, NULL, NULL, wc.hInstance, NULL);
    SetTimer(hwnd, 1, 500, NULL);
    while (GetMessageA(&msg, NULL, 0, 0) > 0) { TranslateMessage(&msg); DispatchMessageA(&msg); }
    f = fopen("Z:\\orbisdesk\\process-p014\\separate-game.txt", "w");
    if (f)
    {
        fprintf(f, "{\"build\":\"P019\",\"event\":\"game_done\",\"base\":\"%p\",\"pid\":%lu,\"argc\":%d,\"arg1\":\"%s\","
                   "\"cwd\":\"%s\",\"hwnd\":\"%p\",\"seconds\":%u,\"clicks\":%u,\"keys\":%u}\n",
                (void *)GetModuleHandleA(NULL), GetCurrentProcessId(), argc, argc > 1 ? argv[1] : "", cwd,
                (void *)hwnd, ticks / 2, clicks, keys);
        fclose(f);
    }
    return 44;
}
#else
int main(void)
{
    STARTUPINFOA si = {sizeof(si)}; PROCESS_INFORMATION pi = {0};
    char game[MAX_PATH], dir[MAX_PATH], cmd[MAX_PATH + 32], *slash;
    DWORD code = 0, wait = 0, error = 0; HKEY key; LONG reg; BOOL started; FILE *f;
    GetModuleFileNameA(NULL, game, MAX_PATH);
    strcpy(dir, game);
    if ((slash = strrchr(dir, '\\'))) *slash = 0;
    snprintf(game, MAX_PATH, "%s\\separate_game.exe", dir);
    reg = RegCreateKeyExA(HKEY_CURRENT_USER, "Software\\Wine\\AppDefaults\\separate_game.exe", 0, NULL, 0,
                          KEY_SET_VALUE, NULL, &key, NULL);
    if (!reg) { reg = RegSetValueExA(key, "OrbisExecutionMode", 0, REG_SZ, (const BYTE *)"separate", 9); RegCloseKey(key); }
    snprintf(cmd, sizeof(cmd), "\"%s\" desde-el-lanzador", game);
    started = CreateProcessA(game, cmd, NULL, NULL, FALSE, 0, NULL, dir, &si, &pi);
    if (!started) error = GetLastError();
    else
    {
        wait = WaitForSingleObject(pi.hProcess, 180000);
        GetExitCodeProcess(pi.hProcess, &code);
        CloseHandle(pi.hThread); CloseHandle(pi.hProcess);
    }
    f = fopen("Z:\\orbisdesk\\process-p014\\separate-launcher.txt", "w");
    if (f)
    {
        fprintf(f, "{\"build\":\"P019\",\"event\":\"launcher_done\",\"launcher_base\":\"%p\",\"launcher_pid\":%lu,\"registry\":%ld,"
                   "\"started\":%d,\"error\":%lu,\"game_pid\":%lu,\"wait\":%lu,\"exit_code\":%lu}\n",
                (void *)GetModuleHandleA(NULL), GetCurrentProcessId(), reg, started, error, pi.dwProcessId, wait, code);
        fclose(f);
    }
    return started && code == 44 ? 0 : 1;
}
#endif
