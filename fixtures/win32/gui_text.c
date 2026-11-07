/* SPDX-License-Identifier: LGPL-2.1-or-later */
#define UNICODE
#define _UNICODE
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>

static HDC surface;
static HBITMAP bitmap;
static HFONT font;
static unsigned black_pixels;
static unsigned window_ink;
static int passed;
static WCHAR family[64];
static SIZE extent;
static TEXTMETRICW metric;
static unsigned paints;
static WCHAR progress_path[MAX_PATH];
static void progress(const char *text)
{
    HANDLE file=CreateFileW(progress_path,FILE_APPEND_DATA,FILE_SHARE_READ,NULL,OPEN_ALWAYS,0,NULL);
    if (file!=INVALID_HANDLE_VALUE) { DWORD written;WriteFile(file,text,lstrlenA(text),&written,NULL);CloseHandle(file); }
}
static const WCHAR message[] = L"Wine PS4: texto 0123456789 \x00e1\x00e9\x00f1";

static LRESULT CALLBACK proc(HWND window, UINT msg, WPARAM w, LPARAM l)
{
    if (msg == WM_PAINT) {
        progress("paint\r\n");++paints;
        PAINTSTRUCT ps;
        HDC dc = BeginPaint(window, &ps);
        RECT rect={0,0,480,160};
        FillRect(dc,&rect,(HBRUSH)GetStockObject(WHITE_BRUSH));
        HGDIOBJ previous=SelectObject(dc,font);
        SetTextColor(dc,RGB(0,0,0));SetBkColor(dc,RGB(255,255,255));
        if (!TextOutW(dc,16,40,message,(int)(sizeof(message)/sizeof(WCHAR))-1)) passed=0;
        SelectObject(dc,previous);
        EndPaint(window, &ps);
        return 0;
    }
    if (msg == WM_TIMER) {
        progress("timer\r\n");
        HDC dc=GetDC(window);
        /* Glyph overhang may extend beyond the advance returned by GetTextExtent.
         * Read the same complete client rectangle used for the reference DIB. */
        for (int y=0;y<160;y++)
            for (int x=0;x<480;x++) if (GetPixel(dc,x,y)==RGB(0,0,0)) ++window_ink;
        ReleaseDC(window,dc);
        passed=passed && window_ink==black_pixels;
        passed=passed && paints>0;
        char path[MAX_PATH], result[512];
        DWORD n = GetModuleFileNameA(NULL, path, MAX_PATH), written;
        while (n && path[n-1] != '\\') --n;
        lstrcpyA(path+n, "text-result.txt");
        int length = snprintf(result, sizeof(result),
            "passed=%d;family_tahoma=%d;painted=%d;width=%ld;height=%ld;metric_height=%ld;ink=%u;window_ink=%u\r\n",
            passed, !lstrcmpiW(family,L"Tahoma"), paints>0, extent.cx, extent.cy, metric.tmHeight, black_pixels,window_ink);
        HANDLE file = CreateFileA(path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, 0, NULL);
        if (file == INVALID_HANDLE_VALUE || !WriteFile(file,result,length,&written,NULL) || written!=(DWORD)length)
            passed=0;
        if (file != INVALID_HANDLE_VALUE) CloseHandle(file);
        KillTimer(window,1);
        DestroyWindow(window);
        return 0;
    }
    if (msg == WM_DESTROY) { PostQuitMessage(passed ? 0 : 5); return 0; }
    return DefWindowProcW(window,msg,w,l);
}

int WINAPI WinMain(HINSTANCE instance,HINSTANCE previous,LPSTR command,int show)
{
    (void)previous; (void)command; (void)show;
    WCHAR font_path[MAX_PATH];
    DWORD path_len=GetModuleFileNameW(NULL,font_path,MAX_PATH);
    while (path_len && font_path[path_len-1]!='\\') --path_len;
    lstrcpyW(progress_path,font_path);lstrcpyW(progress_path+path_len,L"text-progress.txt");
    progress("start\r\n");
    lstrcpyW(font_path+path_len,L"tahoma.ttf");
    HANDLE font_file=CreateFileW(font_path,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,0,NULL);
    if (font_file==INVALID_HANDLE_VALUE) return 6;
    DWORD font_size=GetFileSize(font_file,NULL),font_read=0,font_count=0;
    void *font_bytes=HeapAlloc(GetProcessHeap(),0,font_size);
    if (!font_bytes || !ReadFile(font_file,font_bytes,font_size,&font_read,NULL) || font_read!=font_size) return 7;
    CloseHandle(font_file);
    HANDLE private_font=AddFontMemResourceEx(font_bytes,font_size,NULL,&font_count);
    if (!private_font || !font_count) return 8;
    progress("font_loaded\r\n");
    WORD indices[sizeof(message)/sizeof(WCHAR)];
    void *pixels;
    BITMAPINFO info = {0};
    info.bmiHeader.biSize=sizeof(BITMAPINFOHEADER);
    info.bmiHeader.biWidth=480;info.bmiHeader.biHeight=-160;
    info.bmiHeader.biPlanes=1;info.bmiHeader.biBitCount=32;info.bmiHeader.biCompression=BI_RGB;
    surface=CreateCompatibleDC(NULL);
    bitmap=CreateDIBSection(surface,&info,DIB_RGB_COLORS,&pixels,NULL,0);
    if (!surface || !bitmap) return 1;
    HGDIOBJ old_bitmap=SelectObject(surface,bitmap);
    font=CreateFontW(-20,0,0,0,FW_NORMAL,FALSE,FALSE,FALSE,DEFAULT_CHARSET,
        OUT_TT_ONLY_PRECIS,CLIP_DEFAULT_PRECIS,NONANTIALIASED_QUALITY,DEFAULT_PITCH,L"Tahoma");
    HGDIOBJ old_font=SelectObject(surface,font);
    RECT rect={0,0,480,160};FillRect(surface,&rect,(HBRUSH)GetStockObject(WHITE_BRUSH));
    SetTextColor(surface,RGB(0,0,0));SetBkColor(surface,RGB(255,255,255));
    int count=(int)(sizeof(message)/sizeof(WCHAR))-1;
    passed=font && GetTextFaceW(surface,64,family) && !lstrcmpiW(family,L"Tahoma") &&
        GetTextMetricsW(surface,&metric) && metric.tmHeight>0 &&
        GetTextExtentPoint32W(surface,message,count,&extent) && extent.cx>0 && extent.cy>0 &&
        GetGlyphIndicesW(surface,message,count,indices,GGI_MARK_NONEXISTING_GLYPHS)!=GDI_ERROR;
    for (int i=0;i<count;i++) if (indices[i]==0xffff) passed=0;
    passed=passed && TextOutW(surface,16,40,message,count);
    GdiFlush();
    for (int i=0;i<480*160;i++) if ((((DWORD*)pixels)[i]&0xffffff)==0) ++black_pixels;
    passed=passed && black_pixels>50 && black_pixels<10000;
    progress("text_rendered\r\n");
    /* A missing or malformed resource must fail through Wine's real font backend. */
    passed=passed && !AddFontResourceExW(L"C:\\orbis\\missing-font.ttf",FR_PRIVATE,NULL);
    WCHAR bad_path[MAX_PATH];
    lstrcpyW(bad_path,font_path);lstrcpyW(bad_path+path_len,L"bad-font.ttf");
    HANDLE bad=CreateFileW(bad_path,GENERIC_WRITE,0,NULL,CREATE_ALWAYS,0,NULL);
    if (bad!=INVALID_HANDLE_VALUE) {
        DWORD written;WriteFile(bad,"not a font",10,&written,NULL);CloseHandle(bad);
        passed=passed && !AddFontResourceExW(bad_path,FR_PRIVATE,NULL);
    } else passed=0;
    progress("negative_cases\r\n");
    WNDCLASSW cls={0};cls.lpfnWndProc=proc;cls.hInstance=instance;cls.lpszClassName=L"OrbisText";
    if (!RegisterClassW(&cls)) return 2;
    RECT frame={0,0,480,160};AdjustWindowRect(&frame,WS_OVERLAPPEDWINDOW,FALSE);
    HWND window=CreateWindowW(cls.lpszClassName,L"Wine PS4 - texto",WS_OVERLAPPEDWINDOW,40,40,
        frame.right-frame.left,frame.bottom-frame.top,NULL,NULL,instance,NULL);
    if (!window) return 3;
    ShowWindow(window,SW_SHOWNORMAL);
    ShowWindow(window,SW_SHOW);
    InvalidateRect(window,NULL,TRUE);UpdateWindow(window);
    if (!SetTimer(window,1,2000,NULL)) return 9;
    progress("window_shown\r\n");
    MSG msg;int rc;
    while ((rc=GetMessageW(&msg,NULL,0,0))>0) { TranslateMessage(&msg);DispatchMessageW(&msg); }
    SelectObject(surface,old_font);SelectObject(surface,old_bitmap);
    DeleteObject(font);DeleteObject(bitmap);DeleteDC(surface);
    RemoveFontMemResourceEx(private_font);HeapFree(GetProcessHeap(),0,font_bytes);
    return rc<0 ? 4 : (int)msg.wParam;
}
