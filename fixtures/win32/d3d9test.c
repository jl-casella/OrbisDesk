/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* W124: the first Direct3D 9 program (DXVK over winevulkan and RADV). A window, a HAL
 * device, then about five seconds of frames: a clear whose colour cycles and one
 * vertex-coloured triangle. Each step's HRESULT, the adapter and the frame count go to
 * d3d9-result.txt next to the executable, so a failure says where it stopped. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <d3d9.h>
#include <stdio.h>

struct vertex { float x, y, z, rhw; DWORD colour; };

static LRESULT CALLBACK window_proc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp)
{
    if (msg == WM_CLOSE) { PostQuitMessage(0); return 0; }
    return DefWindowProcA(hwnd, msg, wp, lp);
}

int WINAPI WinMain(HINSTANCE instance, HINSTANCE previous, LPSTR command, int show)
{
    char path[MAX_PATH], text[1024];
    int n = 0;
    unsigned frames = 0;
    DWORD length = GetModuleFileNameA(NULL, path, MAX_PATH), written, start;
    WNDCLASSA cls = {0};
    HWND hwnd;
    IDirect3D9 *d3d;
    IDirect3DDevice9 *device = NULL;
    D3DPRESENT_PARAMETERS params = {0};
    D3DADAPTER_IDENTIFIER9 id = {0};
    HRESULT hr;
    (void)previous; (void)command;

    cls.lpfnWndProc = window_proc; cls.hInstance = instance; cls.lpszClassName = "OrbisDeskD3D9Test";
    cls.hCursor = LoadCursorA(NULL, (LPCSTR)IDC_ARROW);
    RegisterClassA(&cls);
    hwnd = CreateWindowA(cls.lpszClassName, sizeof(void *) == 8 ? "D3D9 test (64-bit)" : "D3D9 test (32-bit)",
                         WS_OVERLAPPEDWINDOW | WS_VISIBLE, 100, 100, 640, 480, NULL, NULL, instance, NULL);
    ShowWindow(hwnd, show);
    n += snprintf(text + n, sizeof(text) - n, "window=%p", (void *)hwnd);
    d3d = Direct3DCreate9(D3D_SDK_VERSION);
    n += snprintf(text + n, sizeof(text) - n, ";create9=%p", (void *)d3d);
    if (d3d)
    {
        hr = IDirect3D9_GetAdapterIdentifier(d3d, D3DADAPTER_DEFAULT, 0, &id);
        n += snprintf(text + n, sizeof(text) - n, ";adapter=%08lx:%s", (unsigned long)hr, id.Description);
        params.Windowed = TRUE;
        params.SwapEffect = D3DSWAPEFFECT_DISCARD;
        params.BackBufferFormat = D3DFMT_UNKNOWN;
        params.hDeviceWindow = hwnd;
        hr = IDirect3D9_CreateDevice(d3d, D3DADAPTER_DEFAULT, D3DDEVTYPE_HAL, hwnd,
                                     D3DCREATE_SOFTWARE_VERTEXPROCESSING, &params, &device);
        n += snprintf(text + n, sizeof(text) - n, ";device=%08lx", (unsigned long)hr);
    }
    if (device)
    {
        HRESULT clear = S_OK, draw = S_OK, present = S_OK;
        MSG msg;
        start = GetTickCount();
        while (GetTickCount() - start < 5000)
        {
            float t = (GetTickCount() - start) / 5000.0f;
            struct vertex triangle[3] = {
                {320.0f, 80.0f, 0.5f, 1.0f, 0xffff4040},
                {520.0f, 400.0f, 0.5f, 1.0f, 0xff40ff40},
                {120.0f, 400.0f, 0.5f, 1.0f, 0xff4040ff}};
            while (PeekMessageA(&msg, NULL, 0, 0, PM_REMOVE)) { TranslateMessage(&msg); DispatchMessageA(&msg); }
            if (FAILED(clear = IDirect3DDevice9_Clear(device, 0, NULL, D3DCLEAR_TARGET,
                                                      D3DCOLOR_XRGB((int)(40 + 120 * t), 30, (int)(160 - 120 * t)), 1.0f, 0))) break;
            IDirect3DDevice9_BeginScene(device);
            IDirect3DDevice9_SetFVF(device, D3DFVF_XYZRHW | D3DFVF_DIFFUSE);
            draw = IDirect3DDevice9_DrawPrimitiveUP(device, D3DPT_TRIANGLELIST, 1, triangle, sizeof(triangle[0]));
            IDirect3DDevice9_EndScene(device);
            if (FAILED(present = IDirect3DDevice9_Present(device, NULL, NULL, NULL, NULL))) break;
            frames++;
        }
        n += snprintf(text + n, sizeof(text) - n, ";clear=%08lx;draw=%08lx;present=%08lx;frames=%u;ms=%lu",
                      (unsigned long)clear, (unsigned long)draw, (unsigned long)present, frames,
                      (unsigned long)(GetTickCount() - start));
        IDirect3DDevice9_Release(device);
    }
    if (d3d) IDirect3D9_Release(d3d);
    n += snprintf(text + n, sizeof(text) - n, "\r\n");
    while (length && path[length - 1] != '\\') --length;
    lstrcpyA(path + length, "d3d9-result.txt");
    HANDLE file = CreateFileA(path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file != INVALID_HANDLE_VALUE)
    {
        WriteFile(file, text, (DWORD)n, &written, NULL);
        CloseHandle(file);
    }
    DestroyWindow(hwnd);
    return 0;
}
