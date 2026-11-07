/* SPDX-License-Identifier: LGPL-2.1-or-later */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>

static unsigned count;
static LRESULT CALLBACK window_proc(HWND window, UINT msg, WPARAM w, LPARAM l)
{
    if (msg == WM_KEYDOWN || msg == WM_LBUTTONDOWN) {
        ++count;
        InvalidateRect(window, NULL, FALSE);
        return 0;
    }
    if (msg == WM_PAINT) {
        PAINTSTRUCT ps;
        HDC dc = BeginPaint(window, &ps);
        RECT rect;
        GetClientRect(window, &rect);
        HBRUSH brush = CreateSolidBrush(count & 1 ? RGB(30, 160, 70) : RGB(20, 60, 140));
        FillRect(dc, &rect, brush);
        DeleteObject(brush);
        SetTextColor(dc, RGB(255, 255, 255));
        SetBkMode(dc, TRANSPARENT);
        const char text[] = "orbisdesk PE32 GDI - press a key to change colour";
        TextOutA(dc, 24, 24, text, sizeof(text) - 1);
        EndPaint(window, &ps);
        return 0;
    }
    if (msg == WM_DESTROY) { PostQuitMessage(0); return 0; }
    return DefWindowProcA(window, msg, w, l);
}

int WINAPI WinMain(HINSTANCE instance, HINSTANCE previous, LPSTR command, int show)
{
    (void)previous; (void)command;
    WNDCLASSA cls = {0};
    cls.lpfnWndProc = window_proc;
    cls.hInstance = instance;
    cls.lpszClassName = "OrbisDeskFixture";
    if (!RegisterClassA(&cls)) return 1;
    HWND window = CreateWindowA(cls.lpszClassName, "orbisdesk GDI", WS_OVERLAPPEDWINDOW,
                               0, 0, 640, 480, NULL, NULL, instance, NULL);
    if (!window) return 2;
    ShowWindow(window, show);
    MSG msg;
    int rc;
    while ((rc = GetMessageA(&msg, NULL, 0, 0)) > 0) {
        TranslateMessage(&msg);
        DispatchMessageA(&msg);
    }
    return rc < 0 ? 3 : (int)msg.wParam;
}
