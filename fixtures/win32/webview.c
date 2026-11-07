/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Phase 9: the WebBrowser control (ieframe + mshtml + Wine Gecko) embedded in a program, the way
 * old programs embed IE. 64-bit (guest) and 32-bit (relaunched under WoW64).
 * Steps, each on its own line of C:\orbis\webview-result.txt with its HRESULT:
 *   ole       OleInitialize
 *   create    CoCreateInstance(CLSID_WebBrowser, IOleObject): the class registration
 *   activate  SetClientSite and DoVerb(OLEIVERB_INPLACEACTIVATE) in this window
 *   local     Navigate2 to C:\orbis\webtest\index.html, then messages until READYSTATE_COMPLETE
 *             (30 s at most); ready state and milliseconds
 *   title     document title (the page's is "orbis-webtest"; empty when Gecko did not load)
 *   es5       text the page's first script wrote into #es5 ("es5-ok" when jscript ran)
 *   es2020    the same for its second script (#es2020; jscript has no ES2020, so "not run" is expected)
 *   remote    the same navigation to argument 1 (http://example.com/ by default; "-" skips it):
 *             needs the network (phase 8) and is plain HTTP, since Wine's TLS (schannel) has no
 *             Unix side on the console
 * The file is appended to, one block per run. A step that cannot run because an earlier one
 * failed says so (skipped=...), never ok. The window stays open with the page until closed. */
#define COBJMACROS
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <ole2.h>
#include <exdisp.h>
#include <mshtml.h>
#include <shellapi.h>
#include <stdio.h>
#include <string.h>

static FILE *out;
static HWND window;

static void line(const char *format, ...)
{
    va_list args;
    va_start(args, format);
    vfprintf(out, format, args);
    va_end(args);
    fputc('\n', out);
    fflush(out);
}

/* ---- a minimal in-place container: client site, in-place site and frame of one window ---- */
static IOleClientSite client;
static IOleInPlaceSite inplace;
static IOleInPlaceFrame frame;

static HRESULT query(REFIID iid, void **object)
{
    if (IsEqualIID(iid, &IID_IUnknown) || IsEqualIID(iid, &IID_IOleClientSite)) *object = &client;
    else if (IsEqualIID(iid, &IID_IOleWindow) || IsEqualIID(iid, &IID_IOleInPlaceSite)) *object = &inplace;
    else if (IsEqualIID(iid, &IID_IOleInPlaceUIWindow) || IsEqualIID(iid, &IID_IOleInPlaceFrame)) *object = &frame;
    else { *object = NULL; return E_NOINTERFACE; }
    return S_OK;
}
static ULONG STDMETHODCALLTYPE add_ref(void *iface) { return 2; }   /* static objects */
static ULONG STDMETHODCALLTYPE release(void *iface) { return 1; }
static HRESULT STDMETHODCALLTYPE get_window(void *iface, HWND *hwnd) { *hwnd = window; return S_OK; }
static HRESULT STDMETHODCALLTYPE not_implemented(void) { return E_NOTIMPL; }
static HRESULT STDMETHODCALLTYPE accepted(void) { return S_OK; }

static HRESULT STDMETHODCALLTYPE client_query(IOleClientSite *iface, REFIID iid, void **object) { return query(iid, object); }
static HRESULT STDMETHODCALLTYPE client_container(IOleClientSite *iface, IOleContainer **container)
{ *container = NULL; return E_NOINTERFACE; }
static IOleClientSiteVtbl client_vtbl =
{
    client_query, (void *)add_ref, (void *)release,
    (void *)not_implemented,           /* SaveObject */
    (void *)not_implemented,           /* GetMoniker */
    client_container,
    (void *)accepted,                  /* ShowObject */
    (void *)accepted,                  /* OnShowWindow */
    (void *)not_implemented,           /* RequestNewObjectLayout */
};

static HRESULT STDMETHODCALLTYPE site_query(IOleInPlaceSite *iface, REFIID iid, void **object) { return query(iid, object); }
static HRESULT STDMETHODCALLTYPE site_context(IOleInPlaceSite *iface, IOleInPlaceFrame **frame_out, IOleInPlaceUIWindow **document,
                                              RECT *position, RECT *clip, OLEINPLACEFRAMEINFO *info)
{
    *frame_out = &frame;
    *document = NULL;
    GetClientRect(window, position);
    *clip = *position;
    info->fMDIApp = FALSE;
    info->hwndFrame = window;
    info->haccel = NULL;
    info->cAccelEntries = 0;
    return S_OK;
}
static IOleInPlaceSiteVtbl site_vtbl =
{
    site_query, (void *)add_ref, (void *)release,
    (void *)get_window,
    (void *)not_implemented,           /* ContextSensitiveHelp */
    (void *)accepted,                  /* CanInPlaceActivate */
    (void *)accepted,                  /* OnInPlaceActivate */
    (void *)accepted,                  /* OnUIActivate */
    site_context,
    (void *)not_implemented,           /* Scroll */
    (void *)accepted,                  /* OnUIDeactivate */
    (void *)accepted,                  /* OnInPlaceDeactivate */
    (void *)not_implemented,           /* DiscardUndoState */
    (void *)not_implemented,           /* DeactivateAndUndo */
    (void *)accepted,                  /* OnPosRectChange */
};

static HRESULT STDMETHODCALLTYPE frame_query(IOleInPlaceFrame *iface, REFIID iid, void **object) { return query(iid, object); }
static HRESULT STDMETHODCALLTYPE frame_accelerator(IOleInPlaceFrame *iface, MSG *msg, WORD id) { return S_FALSE; }
static IOleInPlaceFrameVtbl frame_vtbl =
{
    frame_query, (void *)add_ref, (void *)release,
    (void *)get_window,
    (void *)not_implemented,           /* ContextSensitiveHelp */
    (void *)not_implemented,           /* GetBorder */
    (void *)not_implemented,           /* RequestBorderSpace */
    (void *)not_implemented,           /* SetBorderSpace */
    (void *)accepted,                  /* SetActiveObject */
    (void *)not_implemented,           /* InsertMenus */
    (void *)accepted,                  /* SetMenu */
    (void *)not_implemented,           /* RemoveMenus */
    (void *)accepted,                  /* SetStatusText */
    (void *)accepted,                  /* EnableModeless */
    frame_accelerator,
};

/* ---- steps ---- */
static void utf8(BSTR text, char *buffer, int size)
{
    buffer[0] = 0;
    if (text) WideCharToMultiByte(CP_UTF8, 0, text, -1, buffer, size, NULL, NULL);
}

/* Navigate and pump messages until the document is complete; returns the HRESULT of Navigate2. */
static HRESULT navigate(IWebBrowser2 *browser, const WCHAR *url, const char *step)
{
    VARIANT target, empty;
    READYSTATE state = READYSTATE_UNINITIALIZED;
    DWORD start = GetTickCount(), elapsed = 0;
    HRESULT hr;
    MSG msg;

    VariantInit(&empty);
    V_VT(&target) = VT_BSTR;
    V_BSTR(&target) = SysAllocString(url);
    hr = IWebBrowser2_Navigate2(browser, &target, &empty, &empty, &empty, &empty);
    VariantClear(&target);
    if (FAILED(hr))
    {
        line("%s navigate=0x%08lx", step, (unsigned long)hr);
        return hr;
    }
    while (elapsed < 30000)
    {
        while (PeekMessageW(&msg, NULL, 0, 0, PM_REMOVE))
        {
            TranslateMessage(&msg);
            DispatchMessageW(&msg);
        }
        if (SUCCEEDED(IWebBrowser2_get_ReadyState(browser, &state)) && state == READYSTATE_COMPLETE) break;
        MsgWaitForMultipleObjects(0, NULL, FALSE, 50, QS_ALLINPUT);
        elapsed = GetTickCount() - start;
    }
    line("%s navigate=0x00000000 ready_state=%d complete=%s ms=%lu", step, (int)state,
         state == READYSTATE_COMPLETE ? "yes" : "no (30 s)", (unsigned long)(GetTickCount() - start));
    return state == READYSTATE_COMPLETE ? S_OK : E_PENDING;
}

static void element_text(IHTMLDocument3 *document, const WCHAR *id, const char *step)
{
    IHTMLElement *element = NULL;
    BSTR name = SysAllocString(id), text = NULL;
    char buffer[256];
    HRESULT hr = IHTMLDocument3_getElementById(document, name, &element);

    SysFreeString(name);
    if (FAILED(hr) || !element)
    {
        line("%s element=0x%08lx found=no", step, (unsigned long)hr);
        return;
    }
    hr = IHTMLElement_get_innerText(element, &text);
    utf8(text, buffer, sizeof(buffer));
    line("%s innerText=0x%08lx text=\"%s\"", step, (unsigned long)hr, buffer);
    SysFreeString(text);
    IHTMLElement_Release(element);
}

/* title, then the two script markers of the local page */
static void inspect(IWebBrowser2 *browser, BOOL markers)
{
    IDispatch *dispatch = NULL;
    IHTMLDocument2 *document = NULL;
    IHTMLDocument3 *document3 = NULL;
    BSTR title = NULL;
    char buffer[256];
    HRESULT hr = IWebBrowser2_get_Document(browser, &dispatch);

    if (FAILED(hr) || !dispatch)
    {
        line("title document=0x%08lx present=no", (unsigned long)hr);
        if (markers) line("es5 skipped=no document"), line("es2020 skipped=no document");
        return;
    }
    hr = IDispatch_QueryInterface(dispatch, &IID_IHTMLDocument2, (void **)&document);
    if (SUCCEEDED(hr))
    {
        hr = IHTMLDocument2_get_title(document, &title);
        utf8(title, buffer, sizeof(buffer));
        line("title get_title=0x%08lx text=\"%s\"", (unsigned long)hr, buffer);
        SysFreeString(title);
        IHTMLDocument2_Release(document);
    }
    else line("title IHTMLDocument2=0x%08lx", (unsigned long)hr);
    if (markers)
    {
        hr = IDispatch_QueryInterface(dispatch, &IID_IHTMLDocument3, (void **)&document3);
        if (SUCCEEDED(hr))
        {
            element_text(document3, L"es5", "es5");
            element_text(document3, L"es2020", "es2020");
            IHTMLDocument3_Release(document3);
        }
        else line("es5 IHTMLDocument3=0x%08lx", (unsigned long)hr), line("es2020 skipped=no IHTMLDocument3");
    }
    IDispatch_Release(dispatch);
}

static IOleObject *control;

static LRESULT CALLBACK window_proc(HWND hwnd, UINT message, WPARAM wparam, LPARAM lparam)
{
    switch (message)
    {
    case WM_SIZE:
        if (control)
        {
            IOleInPlaceObject *object;
            RECT rect;
            GetClientRect(hwnd, &rect);
            if (SUCCEEDED(IOleObject_QueryInterface(control, &IID_IOleInPlaceObject, (void **)&object)))
            {
                IOleInPlaceObject_SetObjectRects(object, &rect, &rect);
                IOleInPlaceObject_Release(object);
            }
        }
        return 0;
    case WM_DESTROY:
        PostQuitMessage(0);
        return 0;
    }
    return DefWindowProcW(hwnd, message, wparam, lparam);
}

int WINAPI WinMain(HINSTANCE instance, HINSTANCE previous, LPSTR command_line, int show)
{
    WNDCLASSW class = {0};
    IWebBrowser2 *browser = NULL;
    WCHAR remote[512] = L"http://example.com/";
    const char *bits = sizeof(void *) == 8 ? "64" : "32";
    SYSTEMTIME now;
    RECT rect;
    HRESULT hr;
    MSG msg;
    int argc;
    WCHAR **argv = CommandLineToArgvW(GetCommandLineW(), &argc);

    if (argv && argc > 1) lstrcpynW(remote, argv[1], ARRAYSIZE(remote));
    CreateDirectoryA("C:\\orbis", NULL);
    if (!(out = fopen("C:\\orbis\\webview-result.txt", "a"))) return 1;
    GetLocalTime(&now);
    line("== webview%s %04u-%02u-%02u %02u:%02u:%02u", bits, now.wYear, now.wMonth, now.wDay, now.wHour, now.wMinute, now.wSecond);

    client.lpVtbl = &client_vtbl;
    inplace.lpVtbl = &site_vtbl;
    frame.lpVtbl = &frame_vtbl;
    class.lpfnWndProc = window_proc;
    class.hInstance = instance;
    class.hCursor = LoadCursorW(NULL, (LPCWSTR)IDC_ARROW);
    class.hbrBackground = (HBRUSH)(COLOR_WINDOW + 1);
    class.lpszClassName = L"OrbisWebViewTest";
    RegisterClassW(&class);
    window = CreateWindowW(class.lpszClassName, sizeof(void *) == 8 ? L"WebView test (64-bit)" : L"WebView test (32-bit)",
                           WS_OVERLAPPEDWINDOW | WS_VISIBLE, CW_USEDEFAULT, CW_USEDEFAULT, 900, 600, NULL, NULL, instance, NULL);
    if (!window)
    {
        line("window error=%lu", GetLastError());
        fclose(out);
        return 1;
    }

    hr = OleInitialize(NULL);
    line("ole OleInitialize=0x%08lx", (unsigned long)hr);
    if (FAILED(hr)) goto done;
    hr = CoCreateInstance(&CLSID_WebBrowser, NULL, CLSCTX_INPROC_SERVER, &IID_IOleObject, (void **)&control);
    line("create CoCreateInstance=0x%08lx", (unsigned long)hr);
    if (FAILED(hr))
    {
        line("activate skipped=no control");
        line("local skipped=no control");
        goto done;
    }
    hr = IOleObject_SetClientSite(control, &client);
    if (SUCCEEDED(hr))
    {
        GetClientRect(window, &rect);
        hr = IOleObject_DoVerb(control, OLEIVERB_INPLACEACTIVATE, NULL, &client, 0, window, &rect);
    }
    line("activate SetClientSite+DoVerb=0x%08lx", (unsigned long)hr);
    if (SUCCEEDED(hr)) hr = IOleObject_QueryInterface(control, &IID_IWebBrowser2, (void **)&browser);
    if (FAILED(hr) || !browser)
    {
        line("local skipped=no IWebBrowser2 (0x%08lx)", (unsigned long)hr);
        goto done;
    }
    if (SUCCEEDED(navigate(browser, L"file:///C:/orbis/webtest/index.html", "local"))) inspect(browser, TRUE);
    else line("title skipped=local page not complete");
    if (lstrcmpW(remote, L"-"))
    {
        if (SUCCEEDED(navigate(browser, remote, "remote"))) inspect(browser, FALSE);
        else line("title skipped=remote page not complete");
        /* back to the local page for the person looking at the window */
        navigate(browser, L"file:///C:/orbis/webtest/index.html", "back");
    }
    else line("remote skipped=argument -");

done:
    line("done");
    fclose(out);
    while (GetMessageW(&msg, NULL, 0, 0) > 0)
    {
        TranslateMessage(&msg);
        DispatchMessageW(&msg);
    }
    if (browser) IWebBrowser2_Release(browser);
    if (control)
    {
        IOleObject_Close(control, OLECLOSE_NOSAVE);
        IOleObject_SetClientSite(control, NULL);
        IOleObject_Release(control);
    }
    OleUninitialize();
    LocalFree(argv);
    return 0;
}
