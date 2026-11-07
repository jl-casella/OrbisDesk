/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* A window that paints its client area one known colour, then, two seconds
 * after it was first painted, reads a pixel back, writes result.txt next to
 * the executable and closes itself: the result can be compared with native
 * Windows, and the presented frames must show the colour. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>

#define FILL RGB(20, 60, 140)
static unsigned paints;

static void write_result(HWND window)
{
    char path[MAX_PATH], text[128];
    DWORD length = GetModuleFileNameA(NULL, path, MAX_PATH), written;
    while (length && path[length - 1] != '\\') --length;
    lstrcpyA(path + length, "result.txt");
    HDC dc = GetDC(window);
    COLORREF pixel = GetPixel(dc, 10, 10);
    ReleaseDC(window, dc);
    RECT client;
    GetClientRect(window, &client);
    int n = snprintf(text, sizeof(text), "painted=%u;pixel=%06lx;client=%ldx%ld\r\n", paints ? 1u : 0u,
                     (unsigned long)pixel, client.right, client.bottom);
    HANDLE file = CreateFileA(path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file != INVALID_HANDLE_VALUE) {
        WriteFile(file, text, (DWORD)n, &written, NULL);
        CloseHandle(file);
    }
}

static LRESULT CALLBACK window_proc(HWND window, UINT msg, WPARAM w, LPARAM l)
{
    if (msg == WM_PAINT) {
        PAINTSTRUCT ps;
        HDC dc = BeginPaint(window, &ps);
        RECT rect;
        GetClientRect(window, &rect);
        HBRUSH brush = CreateSolidBrush(FILL);
        FillRect(dc, &rect, brush);
        DeleteObject(brush);
        EndPaint(window, &ps);
        if (!paints++) SetTimer(window, 1, 2000, NULL);
        return 0;
    }
    if (msg == WM_TIMER) {
        KillTimer(window, 1);
        write_result(window);
        DestroyWindow(window);
        return 0;
    }
    if (msg == WM_DESTROY) { PostQuitMessage(0); return 0; }
    return DefWindowProcA(window, msg, w, l);
}

int WINAPI WinMain(HINSTANCE instance, HINSTANCE previous, LPSTR command, int show)
{
    (void)previous; (void)command; (void)show;
    WNDCLASSA cls = {0};
    cls.lpfnWndProc = window_proc;
    cls.hInstance = instance;
    cls.hCursor = LoadCursorA(NULL, (LPCSTR)IDC_ARROW);
    cls.lpszClassName = "OrbisDeskGuiWindow";
    if (!RegisterClassA(&cls)) return 1;
    /* The client area, not the frame, has a fixed size: frame metrics differ by theme. */
    RECT frame = {0, 0, 464, 280};
    AdjustWindowRect(&frame, WS_OVERLAPPEDWINDOW, FALSE);
    HWND window = CreateWindowA(cls.lpszClassName, "orbisdesk GUI", WS_OVERLAPPEDWINDOW, 40, 40,
                               frame.right - frame.left, frame.bottom - frame.top, NULL, NULL, instance, NULL);
    if (!window) return 2;
    ShowWindow(window, SW_SHOWNORMAL);
    UpdateWindow(window);
    MSG msg;
    int rc;
    while ((rc = GetMessageA(&msg, NULL, 0, 0)) > 0) {
        TranslateMessage(&msg);
        DispatchMessageA(&msg);
    }
    return rc < 0 ? 3 : (int)msg.wParam;
}
