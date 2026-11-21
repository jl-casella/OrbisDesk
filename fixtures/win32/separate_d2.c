/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* PoP Phase D.2 / P018: a Windows GUI program in the separate Wine process, its window on the title's desktop.
 *
 * A process started outside the title has no desktop in its startup information, so win32u would open the
 * default desktop ("Default"), not the title's explorer desktop ("shell"). Wine's own per-application setting
 * picks it: HKCU\Software\Wine\AppDefaults\separate_d2.exe\Explorer, Desktop = "shell". It is read when the
 * process first attaches to a desktop, so this program sets it first and loads user32/gdi32 only afterwards
 * (no static imports of them). D.3 has to give every separately started program its desktop generically.
 *
 * The window (480x300 at 400,180, a normal captioned window) repaints a counter twice a second and counts
 * clicks and keys. After 120 s it writes Z:\orbisdesk\process-p014\separate-d2.txt and exits with code 43. */
#include <windows.h>
#include <stdio.h>

typedef ATOM (WINAPI *RegisterClassW_t)(const WNDCLASSW *);
typedef HWND (WINAPI *CreateWindowExW_t)(DWORD, LPCWSTR, LPCWSTR, DWORD, int, int, int, int, HWND, HMENU, HINSTANCE, LPVOID);
typedef BOOL (WINAPI *ShowWindow_t)(HWND, int);
typedef BOOL (WINAPI *UpdateWindow_t)(HWND);
typedef BOOL (WINAPI *GetMessageW_t)(MSG *, HWND, UINT, UINT);
typedef BOOL (WINAPI *TranslateMessage_t)(const MSG *);
typedef LRESULT (WINAPI *DispatchMessageW_t)(const MSG *);
typedef LRESULT (WINAPI *DefWindowProcW_t)(HWND, UINT, WPARAM, LPARAM);
typedef HDC (WINAPI *BeginPaint_t)(HWND, PAINTSTRUCT *);
typedef BOOL (WINAPI *EndPaint_t)(HWND, const PAINTSTRUCT *);
typedef int (WINAPI *FillRect_t)(HDC, const RECT *, HBRUSH);
typedef BOOL (WINAPI *GetClientRect_t)(HWND, RECT *);
typedef UINT_PTR (WINAPI *SetTimer_t)(HWND, UINT_PTR, UINT, TIMERPROC);
typedef BOOL (WINAPI *InvalidateRect_t)(HWND, const RECT *, BOOL);
typedef void (WINAPI *PostQuitMessage_t)(int);
typedef BOOL (WINAPI *DestroyWindow_t)(HWND);
typedef HDESK (WINAPI *GetThreadDesktop_t)(DWORD);
typedef BOOL (WINAPI *GetUserObjectInformationW_t)(HANDLE, int, void *, DWORD, DWORD *);
typedef HBRUSH (WINAPI *CreateSolidBrush_t)(COLORREF);
typedef BOOL (WINAPI *TextOutW_t)(HDC, int, int, LPCWSTR, int);
typedef int (WINAPI *SetBkMode_t)(HDC, int);
typedef COLORREF (WINAPI *SetTextColor_t)(HDC, COLORREF);

static struct {
    RegisterClassW_t RegisterClassW; CreateWindowExW_t CreateWindowExW; ShowWindow_t ShowWindow; UpdateWindow_t UpdateWindow;
    GetMessageW_t GetMessageW; TranslateMessage_t TranslateMessage; DispatchMessageW_t DispatchMessageW;
    DefWindowProcW_t DefWindowProcW; BeginPaint_t BeginPaint; EndPaint_t EndPaint; FillRect_t FillRect;
    GetClientRect_t GetClientRect; SetTimer_t SetTimer; InvalidateRect_t InvalidateRect; PostQuitMessage_t PostQuitMessage;
    DestroyWindow_t DestroyWindow; GetThreadDesktop_t GetThreadDesktop; GetUserObjectInformationW_t GetUserObjectInformationW;
    CreateSolidBrush_t CreateSolidBrush; TextOutW_t TextOutW; SetBkMode_t SetBkMode; SetTextColor_t SetTextColor;
} u;
static unsigned ticks, clicks, keys, paints;
static HBRUSH background;

static LRESULT CALLBACK proc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp)
{
    switch (msg)
    {
    case WM_TIMER:
        if (++ticks >= 240) u.DestroyWindow(hwnd);   /* 240 x 500 ms */
        else u.InvalidateRect(hwnd, NULL, FALSE);
        return 0;
    case WM_LBUTTONDOWN: case WM_RBUTTONDOWN: clicks++; u.InvalidateRect(hwnd, NULL, FALSE); return 0;
    case WM_KEYDOWN: keys++; u.InvalidateRect(hwnd, NULL, FALSE); return 0;
    case WM_PAINT:
    {
        PAINTSTRUCT ps; RECT rc; WCHAR line[96];
        HDC dc = u.BeginPaint(hwnd, &ps);
        u.GetClientRect(hwnd, &rc);
        u.FillRect(dc, &rc, background);
        u.SetBkMode(dc, TRANSPARENT); u.SetTextColor(dc, RGB(255, 255, 255));
        int n = swprintf(line, 96, L"OrbisDesk: proceso separado (D.2)"); u.TextOutW(dc, 16, 16, line, n);
        n = swprintf(line, 96, L"pid %lu   segundos %u", GetCurrentProcessId(), ticks / 2); u.TextOutW(dc, 16, 48, line, n);
        n = swprintf(line, 96, L"clicks %u   teclas %u", clicks, keys); u.TextOutW(dc, 16, 80, line, n);
        n = swprintf(line, 96, L"ventana de un .exe en otro proceso nativo"); u.TextOutW(dc, 16, 112, line, n);
        u.EndPaint(hwnd, &ps); paints++;
        return 0;
    }
    case WM_DESTROY: u.PostQuitMessage(0); return 0;
    }
    return u.DefWindowProcW(hwnd, msg, wp, lp);
}

int main(void)
{
    FILE *f;
    HKEY key; LONG reg = RegCreateKeyExW(HKEY_CURRENT_USER, L"Software\\Wine\\AppDefaults\\separate_d2.exe\\Explorer",
                                         0, NULL, 0, KEY_SET_VALUE, NULL, &key, NULL);
    if (!reg) { reg = RegSetValueExW(key, L"Desktop", 0, REG_SZ, (const BYTE *)L"shell", sizeof(L"shell")); RegCloseKey(key); }

    HMODULE user = LoadLibraryW(L"user32.dll"), gdi = LoadLibraryW(L"gdi32.dll");
    if (!user || !gdi) return 4;
#define U(name) u.name = (name##_t)GetProcAddress(user, #name)
#define G(name) u.name = (name##_t)GetProcAddress(gdi, #name)
    U(RegisterClassW); U(CreateWindowExW); U(ShowWindow); U(UpdateWindow); U(GetMessageW); U(TranslateMessage);
    U(DispatchMessageW); U(DefWindowProcW); U(BeginPaint); U(EndPaint); U(FillRect); U(GetClientRect); U(SetTimer);
    U(InvalidateRect); U(PostQuitMessage); U(DestroyWindow); U(GetThreadDesktop); U(GetUserObjectInformationW);
    G(CreateSolidBrush); G(TextOutW); G(SetBkMode); G(SetTextColor);

    background = u.CreateSolidBrush(RGB(30, 90, 160));
    WNDCLASSW wc = {0}; wc.lpfnWndProc = proc; wc.hInstance = GetModuleHandleW(NULL); wc.lpszClassName = L"OrbisSeparateD2";
    ATOM atom = u.RegisterClassW(&wc);
    HWND hwnd = u.CreateWindowExW(0, L"OrbisSeparateD2", L"Proceso separado (D.2)", WS_OVERLAPPEDWINDOW,
                                  400, 180, 480, 300, NULL, NULL, wc.hInstance, NULL);
    WCHAR desk[64] = L"?"; DWORD got = 0;
    u.GetUserObjectInformationW(u.GetThreadDesktop(GetCurrentThreadId()), UOI_NAME, desk, sizeof(desk), &got);
    if (hwnd) { u.ShowWindow(hwnd, SW_SHOW); u.UpdateWindow(hwnd); u.SetTimer(hwnd, 1, 500, NULL); }

    MSG msg;
    while (hwnd && u.GetMessageW(&msg, NULL, 0, 0) > 0) { u.TranslateMessage(&msg); u.DispatchMessageW(&msg); }

    f = fopen("Z:\\orbisdesk\\process-p014\\separate-d2.txt", "w");
    if (f)
    {
        fprintf(f, "{\"build\":\"P018\",\"event\":\"gui_done\",\"pid\":%lu,\"registry\":%ld,\"atom\":%u,\"hwnd\":\"%p\","
                   "\"desktop\":\"%ls\",\"seconds\":%u,\"clicks\":%u,\"keys\":%u,\"paints\":%u}\n",
                GetCurrentProcessId(), reg, atom, (void *)hwnd, desk, ticks / 2, clicks, keys, paints);
        fclose(f);
    }
    return hwnd ? 43 : 5;
}
