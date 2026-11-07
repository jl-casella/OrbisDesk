/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* W127: DirectDraw 7 and Direct3D 7 as Blitz3D (SuperMarioKart.exe) use them, through Wine's
 * ddraw and wined3d's Vulkan renderer. A window, a windowed primary surface with a clipper,
 * an off-screen 3D render target, a HAL device, then about five seconds of frames: a Clear
 * whose colour cycles and one transformed, lit-free vertex-coloured triangle, blitted to the
 * primary. Each step's HRESULT and the frame count go to ddraw7-result.txt beside the exe. */
#define WIN32_LEAN_AND_MEAN
#define DIRECT3D_VERSION 0x0700
#include <windows.h>
#include <initguid.h>
#include <ddraw.h>
#include <d3d.h>
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
    IDirectDraw7 *ddraw = NULL;
    IDirectDrawSurface7 *primary = NULL, *target = NULL;
    IDirectDrawClipper *clipper = NULL;
    IDirect3D7 *d3d = NULL;
    IDirect3DDevice7 *device = NULL;
    DDSURFACEDESC2 desc;
    HRESULT hr;
    RECT client;
    (void)previous; (void)command;

    cls.lpfnWndProc = window_proc; cls.hInstance = instance; cls.lpszClassName = "OrbisDeskDDraw7Test";
    cls.hCursor = LoadCursorA(NULL, (LPCSTR)IDC_ARROW);
    RegisterClassA(&cls);
    hwnd = CreateWindowA(cls.lpszClassName, "DirectDraw 7 / D3D7 test", WS_OVERLAPPEDWINDOW | WS_VISIBLE,
                         100, 100, 640, 480, NULL, NULL, instance, NULL);
    ShowWindow(hwnd, show);
    UpdateWindow(hwnd);
    GetClientRect(hwnd, &client);

#define STEP(name, call) do { hr = (call); n += snprintf(text + n, sizeof(text) - n, "%s" name "=%08lx", n ? ";" : "", (unsigned long)hr); } while (0)
    STEP("create", DirectDrawCreateEx(NULL, (void **)&ddraw, &IID_IDirectDraw7, NULL));
    if (SUCCEEDED(hr)) STEP("coop", IDirectDraw7_SetCooperativeLevel(ddraw, hwnd, DDSCL_NORMAL));
    if (SUCCEEDED(hr))
    {
        memset(&desc, 0, sizeof(desc));
        desc.dwSize = sizeof(desc);
        desc.dwFlags = DDSD_CAPS;
        desc.ddsCaps.dwCaps = DDSCAPS_PRIMARYSURFACE;
        STEP("primary", IDirectDraw7_CreateSurface(ddraw, &desc, &primary, NULL));
    }
    if (SUCCEEDED(hr)) STEP("clipper", IDirectDraw7_CreateClipper(ddraw, 0, &clipper, NULL));
    if (SUCCEEDED(hr)) STEP("hwnd", IDirectDrawClipper_SetHWnd(clipper, 0, hwnd));
    if (SUCCEEDED(hr)) STEP("setclip", IDirectDrawSurface7_SetClipper(primary, clipper));
    if (SUCCEEDED(hr))
    {
        memset(&desc, 0, sizeof(desc));
        desc.dwSize = sizeof(desc);
        desc.dwFlags = DDSD_CAPS | DDSD_WIDTH | DDSD_HEIGHT;
        desc.dwWidth = client.right;
        desc.dwHeight = client.bottom;
        desc.ddsCaps.dwCaps = DDSCAPS_OFFSCREENPLAIN | DDSCAPS_3DDEVICE | DDSCAPS_VIDEOMEMORY;
        STEP("target", IDirectDraw7_CreateSurface(ddraw, &desc, &target, NULL));
    }
    if (SUCCEEDED(hr)) STEP("d3d7", IDirectDraw7_QueryInterface(ddraw, &IID_IDirect3D7, (void **)&d3d));
    if (SUCCEEDED(hr)) STEP("device", IDirect3D7_CreateDevice(d3d, &IID_IDirect3DHALDevice, target, &device));
    if (SUCCEEDED(hr))
    {
        HRESULT clear = S_OK, draw = S_OK, blit = S_OK;
        MSG msg;
        D3DVIEWPORT7 viewport = {0, 0, (DWORD)client.right, (DWORD)client.bottom, 0.0f, 1.0f};
        IDirect3DDevice7_SetViewport(device, &viewport);
        IDirect3DDevice7_SetRenderState(device, D3DRENDERSTATE_LIGHTING, FALSE);
        start = GetTickCount();
        while (GetTickCount() - start < 5000)
        {
            float t = (GetTickCount() - start) / 5000.0f;
            struct vertex triangle[3] = {
                {client.right / 2.0f, 40.0f, 0.5f, 1.0f, 0xffff4040},
                {client.right - 60.0f, client.bottom - 40.0f, 0.5f, 1.0f, 0xff40ff40},
                {60.0f, client.bottom - 40.0f, 0.5f, 1.0f, 0xff4040ff}};
            POINT origin = {0, 0};
            RECT on_screen;
            while (PeekMessageA(&msg, NULL, 0, 0, PM_REMOVE)) { TranslateMessage(&msg); DispatchMessageA(&msg); }
            if (FAILED(clear = IDirect3DDevice7_Clear(device, 0, NULL, D3DCLEAR_TARGET,
                    RGB_MAKE((int)(40 + 120 * t), 30, (int)(160 - 120 * t)), 1.0f, 0))) break;
            IDirect3DDevice7_BeginScene(device);
            draw = IDirect3DDevice7_DrawPrimitive(device, D3DPT_TRIANGLELIST, D3DFVF_XYZRHW | D3DFVF_DIFFUSE,
                                                  triangle, 3, 0);
            IDirect3DDevice7_EndScene(device);
            ClientToScreen(hwnd, &origin);
            SetRect(&on_screen, origin.x, origin.y, origin.x + client.right, origin.y + client.bottom);
            if (FAILED(blit = IDirectDrawSurface7_Blt(primary, &on_screen, target, NULL, DDBLT_WAIT, NULL))) break;
            frames++;
        }
        n += snprintf(text + n, sizeof(text) - n, ";clear=%08lx;draw=%08lx;blit=%08lx;frames=%u;ms=%lu",
                      (unsigned long)clear, (unsigned long)draw, (unsigned long)blit, frames,
                      (unsigned long)(GetTickCount() - start));
    }
    if (device) IDirect3DDevice7_Release(device);
    if (d3d) IDirect3D7_Release(d3d);
    if (target) IDirectDrawSurface7_Release(target);
    if (clipper) IDirectDrawClipper_Release(clipper);
    if (primary) IDirectDrawSurface7_Release(primary);
    if (ddraw) IDirectDraw7_Release(ddraw);
    n += snprintf(text + n, sizeof(text) - n, "\r\n");
    while (length && path[length - 1] != '\\') --length;
    lstrcpyA(path + length, "ddraw7-result.txt");
    HANDLE file = CreateFileA(path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file != INVALID_HANDLE_VALUE)
    {
        WriteFile(file, text, (DWORD)n, &written, NULL);
        CloseHandle(file);
    }
    DestroyWindow(hwnd);
    return 0;
}
