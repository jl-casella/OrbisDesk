/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Phase 7: the first Direct3D 11 program (DXVK's d3d11 and dxgi over winevulkan and RADV).
 * A window, a hardware device with its swap chain, then about five seconds of frames: a
 * clear whose colour cycles. Each step's HRESULT, the feature level, the DXGI adapter, the
 * dxgi.dll that was loaded and the frame count go to d3d11-result.txt next to the
 * executable, so a failure says where it stopped. No shaders: the minimal case, as d3d9test. */
#define WIN32_LEAN_AND_MEAN
#define COBJMACROS
#include <windows.h>
#include <d3d11.h>
#include <dxgi.h>
#include <stdio.h>

static LRESULT CALLBACK window_proc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp)
{
    if (msg == WM_CLOSE) { PostQuitMessage(0); return 0; }
    return DefWindowProcA(hwnd, msg, wp, lp);
}

int WINAPI WinMain(HINSTANCE instance, HINSTANCE previous, LPSTR command, int show)
{
    char path[MAX_PATH], module[MAX_PATH] = "-", text[1536];
    int n = 0;
    unsigned frames = 0;
    DWORD length = GetModuleFileNameA(NULL, path, MAX_PATH), written, start;
    WNDCLASSA cls = {0};
    HWND hwnd;
    DXGI_SWAP_CHAIN_DESC desc = {0};
    IDXGISwapChain *chain = NULL;
    ID3D11Device *device = NULL;
    ID3D11DeviceContext *context = NULL;
    ID3D11Texture2D *back = NULL;
    ID3D11RenderTargetView *target = NULL;
    D3D_FEATURE_LEVEL level = 0;
    HMODULE dxgi;
    HRESULT hr;
    (void)previous; (void)command;

    cls.lpfnWndProc = window_proc; cls.hInstance = instance; cls.lpszClassName = "OrbisDeskD3D11Test";
    cls.hCursor = LoadCursorA(NULL, (LPCSTR)IDC_ARROW);
    RegisterClassA(&cls);
    hwnd = CreateWindowA(cls.lpszClassName, sizeof(void *) == 8 ? "D3D11 test (64-bit)" : "D3D11 test (32-bit)",
                         WS_OVERLAPPEDWINDOW | WS_VISIBLE, 100, 100, 640, 480, NULL, NULL, instance, NULL);
    ShowWindow(hwnd, show);
    n += snprintf(text + n, sizeof(text) - n, "window=%p", (void *)hwnd);
    desc.BufferCount = 2;
    desc.BufferDesc.Format = DXGI_FORMAT_R8G8B8A8_UNORM;
    desc.BufferUsage = DXGI_USAGE_RENDER_TARGET_OUTPUT;
    desc.OutputWindow = hwnd;
    desc.SampleDesc.Count = 1;
    desc.Windowed = TRUE;
    desc.SwapEffect = DXGI_SWAP_EFFECT_DISCARD;
    hr = D3D11CreateDeviceAndSwapChain(NULL, D3D_DRIVER_TYPE_HARDWARE, NULL, 0, NULL, 0, D3D11_SDK_VERSION,
                                       &desc, &chain, &device, &level, &context);
    n += snprintf(text + n, sizeof(text) - n, ";device=%08lx;level=%x", (unsigned long)hr, (unsigned)level);
    if ((dxgi = GetModuleHandleA("dxgi.dll"))) GetModuleFileNameA(dxgi, module, MAX_PATH);
    n += snprintf(text + n, sizeof(text) - n, ";dxgi=%s", module);
    if (device)
    {
        IDXGIDevice *dxgi_device;
        IDXGIAdapter *adapter;
        DXGI_ADAPTER_DESC info;
        char name[128] = "-";

        hr = ID3D11Device_QueryInterface(device, &IID_IDXGIDevice, (void **)&dxgi_device);
        if (SUCCEEDED(hr) && SUCCEEDED(hr = IDXGIDevice_GetAdapter(dxgi_device, &adapter)))
        {
            if (SUCCEEDED(hr = IDXGIAdapter_GetDesc(adapter, &info)))
                WideCharToMultiByte(CP_UTF8, 0, info.Description, -1, name, sizeof(name), NULL, NULL);
            IDXGIAdapter_Release(adapter);
        }
        if (dxgi_device) IDXGIDevice_Release(dxgi_device);
        n += snprintf(text + n, sizeof(text) - n, ";adapter=%08lx:%s", (unsigned long)hr, name);
        hr = IDXGISwapChain_GetBuffer(chain, 0, &IID_ID3D11Texture2D, (void **)&back);
        if (SUCCEEDED(hr)) hr = ID3D11Device_CreateRenderTargetView(device, (ID3D11Resource *)back, NULL, &target);
        n += snprintf(text + n, sizeof(text) - n, ";target=%08lx", (unsigned long)hr);
    }
    if (target)
    {
        HRESULT present = S_OK;
        MSG msg;
        start = GetTickCount();
        while (GetTickCount() - start < 5000)
        {
            float t = (GetTickCount() - start) / 5000.0f;
            const float colour[4] = {0.15f + 0.5f * t, 0.12f, 0.65f - 0.5f * t, 1.0f};
            while (PeekMessageA(&msg, NULL, 0, 0, PM_REMOVE)) { TranslateMessage(&msg); DispatchMessageA(&msg); }
            ID3D11DeviceContext_OMSetRenderTargets(context, 1, &target, NULL);
            ID3D11DeviceContext_ClearRenderTargetView(context, target, colour);
            if (FAILED(present = IDXGISwapChain_Present(chain, 1, 0))) break;
            frames++;
        }
        n += snprintf(text + n, sizeof(text) - n, ";present=%08lx;frames=%u;ms=%lu",
                      (unsigned long)present, frames, (unsigned long)(GetTickCount() - start));
    }
    if (target) ID3D11RenderTargetView_Release(target);
    if (back) ID3D11Texture2D_Release(back);
    if (context) ID3D11DeviceContext_Release(context);
    if (chain) IDXGISwapChain_Release(chain);
    if (device) ID3D11Device_Release(device);
    n += snprintf(text + n, sizeof(text) - n, "\r\n");
    while (length && path[length - 1] != '\\') --length;
    lstrcpyA(path + length, "d3d11-result.txt");
    HANDLE file = CreateFileA(path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file != INVALID_HANDLE_VALUE)
    {
        WriteFile(file, text, (DWORD)n, &written, NULL);
        CloseHandle(file);
    }
    DestroyWindow(hwnd);
    return 0;
}
