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
static unsigned ticks, clicks, keys, frames;
/* PoP D.4b: in the title (no PW_SEPARATE_PROCESS) the game draws with OpenGL, which a separate process cannot
 * (no GPU memory there); opengl32 is loaded only then, so the D.3 run in the separate process never touches it. */
static HDC gl_dc;
static HGLRC gl_rc;
static char gl_renderer[128];
static void (WINAPI *p_glClearColor)(float, float, float, float);
static void (WINAPI *p_glClear)(unsigned);
static void gl_start(HWND hwnd)
{
    HGLRC (WINAPI *p_wglCreateContext)(HDC);
    BOOL (WINAPI *p_wglMakeCurrent)(HDC, HGLRC);
    const unsigned char *(WINAPI *p_glGetString)(unsigned);
    PIXELFORMATDESCRIPTOR pfd = {sizeof(pfd), 1, PFD_DRAW_TO_WINDOW | PFD_SUPPORT_OPENGL | PFD_DOUBLEBUFFER, PFD_TYPE_RGBA, 32};
    HMODULE gl;
    int format;
    char title[192];
    if (GetEnvironmentVariableA("PW_SEPARATE_PROCESS", NULL, 0)) return;
    if (!(gl = LoadLibraryA("opengl32.dll"))) { snprintf(gl_renderer, sizeof(gl_renderer), "no opengl32 (%lu)", GetLastError()); return; }
    p_wglCreateContext = (void *)GetProcAddress(gl, "wglCreateContext");
    p_wglMakeCurrent = (void *)GetProcAddress(gl, "wglMakeCurrent");
    p_glGetString = (void *)GetProcAddress(gl, "glGetString");
    p_glClearColor = (void *)GetProcAddress(gl, "glClearColor");
    p_glClear = (void *)GetProcAddress(gl, "glClear");
    if (!p_wglCreateContext || !p_wglMakeCurrent || !p_glGetString || !p_glClearColor || !p_glClear) return;
    gl_dc = GetDC(hwnd);
    format = ChoosePixelFormat(gl_dc, &pfd);
    if (!format || !SetPixelFormat(gl_dc, format, &pfd)) { snprintf(gl_renderer, sizeof(gl_renderer), "pixel format %d error %lu", format, GetLastError()); return; }
    if (!(gl_rc = p_wglCreateContext(gl_dc)) || !p_wglMakeCurrent(gl_dc, gl_rc))
    {
        snprintf(gl_renderer, sizeof(gl_renderer), "context error %lu", GetLastError());
        gl_rc = NULL;
        return;
    }
    snprintf(gl_renderer, sizeof(gl_renderer), "%s", (const char *)p_glGetString(0x1F01 /* GL_RENDERER */));
    snprintf(title, sizeof(title), "Juego en el titulo (GL): %s", gl_renderer);
    SetWindowTextA(hwnd, title);
}
static LRESULT CALLBACK proc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp)
{
    switch (msg)
    {
    case WM_TIMER: if (++ticks >= 120) DestroyWindow(hwnd); else InvalidateRect(hwnd, NULL, FALSE); return 0;
    case WM_LBUTTONDOWN: case WM_RBUTTONDOWN: clicks++; InvalidateRect(hwnd, NULL, FALSE); return 0;
    case WM_KEYDOWN: keys++; InvalidateRect(hwnd, NULL, FALSE); return 0;
    case WM_PAINT:
        if (gl_rc)
        {
            /* the color steps every second; each click and key shifts it */
            unsigned step = ticks / 2 + clicks + keys;
            ValidateRect(hwnd, NULL);
            p_glClearColor((step % 3) == 0 ? 0.9f : 0.1f, (step % 3) == 1 ? 0.8f : 0.1f, (step % 3) == 2 ? 0.9f : 0.2f, 1.0f);
            p_glClear(0x4000 /* GL_COLOR_BUFFER_BIT */);
            SwapBuffers(gl_dc);
            frames++;
            return 0;
        }
        else
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
    wc.style = CS_OWNDC;
    wc.lpfnWndProc = proc; wc.hInstance = GetModuleHandleA(NULL); wc.lpszClassName = "OrbisSeparateGame";
    wc.hCursor = LoadCursorA(NULL, (LPCSTR)IDC_ARROW);
    RegisterClassA(&wc);
    hwnd = CreateWindowExA(0, "OrbisSeparateGame", "Juego separado (D.3)", WS_OVERLAPPEDWINDOW | WS_VISIBLE,
                           420, 200, 440, 200, NULL, NULL, wc.hInstance, NULL);
    gl_start(hwnd);
    SetTimer(hwnd, 1, 500, NULL);
    while (GetMessageA(&msg, NULL, 0, 0) > 0) { TranslateMessage(&msg); DispatchMessageA(&msg); }
    f = fopen("Z:\\orbisdesk\\process-p014\\separate-game.txt", "w");
    if (f)
    {
        fprintf(f, "{\"build\":\"P019\",\"event\":\"game_done\",\"base\":\"%p\",\"pid\":%lu,\"argc\":%d,\"arg1\":\"%s\","
                   "\"cwd\":\"%s\",\"hwnd\":\"%p\",\"seconds\":%u,\"clicks\":%u,\"keys\":%u,\"gl\":%d,\"frames\":%u,\"renderer\":\"%s\"}\n",
                (void *)GetModuleHandleA(NULL), GetCurrentProcessId(), argc, argc > 1 ? argv[1] : "", cwd,
                (void *)hwnd, ticks / 2, clicks, keys, gl_rc != NULL, frames, gl_renderer);
        fclose(f);
    }
    return 44;
}
#elif defined(SEPARATE_INVERSE)
/* PoP D.4: the launcher runs separately and the game in the title, where the GPU is (a separate process cannot
 * map GPU memory). Opened from the desktop it runs in the title first: it sets itself to "separate" and the game
 * to "guest", starts itself again (now in the separate process) and ends, leaving 0x400000 free in the title.
 * The separate copy (PW_SEPARATE_PROCESS is set there) starts separate_game.exe, which the separate process
 * hands to the title: the game then runs in the title at 0x400000 (drawing with OpenGL there), and the
 * separate copy waits in CreateProcess until the game ends, as a launcher waits on its game (D.4b).
 * Result: Z:\orbisdesk\process-p014\separate-inverse.txt, and the game's separate-game.txt. */
int main(void)
{
    STARTUPINFOA si = {sizeof(si)}; PROCESS_INFORMATION pi = {0};
    char self[MAX_PATH], dir[MAX_PATH], game[MAX_PATH], cmd[MAX_PATH + 40], *slash;
    BOOL separate = GetEnvironmentVariableA("PW_SEPARATE_PROCESS", NULL, 0) != 0, started;
    DWORD error = 0; HKEY key; FILE *f;
    GetModuleFileNameA(NULL, self, MAX_PATH);
    strcpy(dir, self);
    if ((slash = strrchr(dir, '\\'))) *slash = 0;
    snprintf(game, MAX_PATH, "%s\\separate_game.exe", dir);
    if (!separate)
    {
        if (!RegCreateKeyExA(HKEY_CURRENT_USER, "Software\\Wine\\AppDefaults\\separate_inverse.exe", 0, NULL, 0, KEY_SET_VALUE, NULL, &key, NULL))
        { RegSetValueExA(key, "OrbisExecutionMode", 0, REG_SZ, (const BYTE *)"separate", 9); RegCloseKey(key); }
        if (!RegCreateKeyExA(HKEY_CURRENT_USER, "Software\\Wine\\AppDefaults\\separate_game.exe", 0, NULL, 0, KEY_SET_VALUE, NULL, &key, NULL))
        { RegSetValueExA(key, "OrbisExecutionMode", 0, REG_SZ, (const BYTE *)"guest", 6); RegCloseKey(key); }
        snprintf(cmd, sizeof(cmd), "\"%s\"", self);
        started = CreateProcessA(self, cmd, NULL, NULL, FALSE, 0, NULL, dir, &si, &pi);
        if (!started) error = GetLastError();
        else { CloseHandle(pi.hThread); CloseHandle(pi.hProcess); }
        f = fopen("Z:\\orbisdesk\\process-p014\\separate-inverse.txt", "w");
        if (f)
        {
            fprintf(f, "{\"build\":\"P021\",\"event\":\"inverse_title\",\"base\":\"%p\",\"pid\":%lu,\"started_separate\":%d,\"error\":%lu,\"separate_pid\":%lu}\n",
                    (void *)GetModuleHandleA(NULL), GetCurrentProcessId(), started, error, pi.dwProcessId);
            fclose(f);
        }
        return 0;   /* ends at once: the game needs this base in the title */
    }
    Sleep(5000);   /* let the title copy end first */
    snprintf(cmd, sizeof(cmd), "\"%s\" desde-el-lanzador-separado", game);
    started = CreateProcessA(game, cmd, NULL, NULL, FALSE, 0, NULL, dir, &si, &pi);
    /* the hand-over ends this process; reaching here means it did not happen */
    error = GetLastError();
    f = fopen("Z:\\orbisdesk\\process-p014\\separate-inverse.txt", "a");
    if (f)
    {
        fprintf(f, "{\"build\":\"P021\",\"event\":\"inverse_separate_returned\",\"base\":\"%p\",\"pid\":%lu,\"started\":%d,\"error\":%lu}\n",
                (void *)GetModuleHandleA(NULL), GetCurrentProcessId(), started, error);
        fclose(f);
    }
    return 1;
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
