#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Build the hardware variant of Wine's explorer.exe (PE64): Start glyph, menu glyphs, clock.

W044. Only the hardware package uses this explorer; the Linux runner and its checks keep
the pinned explorer of out/wine-gui. The explorer sources are copied to an overlay and
revised there; each object is compiled with the exact command the pinned Wine build
uses (taken from `make -n`), only with the overlay source and a separate output.
"""
import hashlib,json,pathlib,shlex,shutil,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
SOURCE=ROOT/'.deps/wine/source';BUILD=ROOT/'.deps/wine/runtime/build'
overlay=ROOT/'.deps/wine/explorer-hw-overlay';work=ROOT/'build/explorer-hw';out=ROOT/'out/explorer-hw'
UNITS=('appbar','desktop','explorer','startmenu','systray')
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
commit=subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip()
if commit!=json.loads((ROOT/'sources.lock.json').read_text())['sources']['wine']['commit']:
    raise SystemExit('Wine source is not the pinned revision')
if overlay.exists():shutil.rmtree(overlay)
shutil.copytree(SOURCE/'programs/explorer',overlay)
for folder in (work,out):folder.mkdir(parents=True,exist_ok=True)
revisions=[]
def revise(path,old,new,why):
    target=overlay/path;text=target.read_text()
    if text.count(old)!=1:raise SystemExit('Unexpected context in '+path+': '+old[:60])
    target.write_text(text.replace(old,new));revisions.append({'path':path,'why':why})

# Start button: a four-pane window glyph drawn here, then the label.
revise('systray.c','''    else  /* start button */
        DrawCaptionTempW( 0, dis->hDC, &rect, 0, 0, start_label, flags | DC_INBUTTON | DC_ICON );
}''','''    else  /* start button */
    {
        /* the app icon (tools/make-app-icon.py): a four-pane window shaped like the console,
         * on a 256-unit grid; each column first in the light-bar colour, which shows in the
         * groove between its panes (W170) */
        static const POINT design[6][4] =
        {
            {{48,24}, {80,16}, {80,229}, {48,240}},
            {{99,16}, {216,42}, {216,224}, {99,229}},
            {{48,24}, {80,16}, {80,91}, {48,87}},
            {{48,111}, {80,115}, {80,229}, {48,240}},
            {{99,16}, {216,42}, {216,109}, {99,94}},
            {{99,118}, {216,133}, {216,224}, {99,229}}
        };
        static const COLORREF colours[6] = { RGB( 0x8f, 0xe0, 0xff ), RGB( 0x8f, 0xe0, 0xff ), RGB( 0x3a, 0x9c, 0xf0 ), RGB( 0x15, 0x5c, 0xb8 ), RGB( 0x4f, 0xb3, 0xff ), RGB( 0x1f, 0x7f, 0xe6 ) };
        int size = GetSystemMetrics( SM_CXSMICON ), i, j;
        int x = rect.left + 3, y = (rect.top + rect.bottom - size) / 2;
        HGDIOBJ old_pen = SelectObject( dis->hDC, GetStockObject( NULL_PEN ));
        HGDIOBJ old_brush = GetCurrentObject( dis->hDC, OBJ_BRUSH );
        RECT text = rect;

        for (i = 0; i < ARRAY_SIZE(design); i++)
        {
            POINT points[4];
            HBRUSH brush = CreateSolidBrush( colours[i] );

            for (j = 0; j < 4; j++)
            {
                points[j].x = x + design[i][j].x * size / 256;
                points[j].y = y + design[i][j].y * size / 256;
            }
            SelectObject( dis->hDC, brush );
            Polygon( dis->hDC, points, 4 );
            SelectObject( dis->hDC, old_brush );
            DeleteObject( brush );
        }
        SelectObject( dis->hDC, old_pen );
        text.left = x + size + 2;
        DrawCaptionTempW( 0, dis->hDC, &text, 0, 0, start_label, flags | DC_INBUTTON );
    }
}''','Start button glyph: the app icon (W170) instead of the class icon.')

# Clock at the right end of the taskbar; notification icons move left of it.
revise('systray.c','static int icon_cx, icon_cy, tray_width, tray_height;',
       'static int icon_cx, icon_cy, tray_width, tray_height;\nstatic int clock_width;\nstatic HWND clock_window;',
       'Clock state.')
revise('systray.c','        pos.x = tray_width - icon_cx * (icon->display + 1);',
       '        pos.x = tray_width - clock_width - icon_cx * (icon->display + 1);','Icons left of the clock.')
revise('systray.c','    int right = tray_width - nb_displayed * icon_cx;',
       '    int right = tray_width - clock_width - nb_displayed * icon_cx;','Buttons end before icons and clock.')
revise('systray.c','''static void do_show_systray(void)
{''','''#define CLOCK_TIMER 3

static void update_clock(void)
{
    WCHAR text[32];

    if (clock_window && GetTimeFormatW( LOCALE_USER_DEFAULT, TIME_NOSECONDS, NULL, NULL, text, ARRAY_SIZE(text) ))
        SetWindowTextW( clock_window, text );
}

static void show_clock( const LOGFONTW *logfont )
{
    static HFONT font;
    SIZE size;
    HDC hdc;

    if (!clock_window)
    {
        clock_window = CreateWindowExW( 0, L"Static", NULL, WS_CHILD | SS_CENTER | SS_CENTERIMAGE | SS_SUNKEN,
                                        0, 0, 0, 0, tray_window, 0, 0, NULL );
        if (!clock_window) return;
        font = CreateFontIndirectW( logfont );
        SendMessageW( clock_window, WM_SETFONT, (WPARAM)font, FALSE );
        SetTimer( tray_window, CLOCK_TIMER, 1000, NULL );
    }
    hdc = GetDC( clock_window );
    SelectObject( hdc, font );
    GetTextExtentPointW( hdc, L"00:00 PM", 8, &size );
    ReleaseDC( clock_window, hdc );
    clock_width = size.cx + 16;
    update_clock();
    SetWindowPos( clock_window, 0, tray_width - clock_width, 0, clock_width, tray_height,
                  SWP_NOZORDER | SWP_NOACTIVATE | SWP_SHOWWINDOW );
}

static void do_show_systray(void)
{''','Clock window, refreshed every second.')
revise('systray.c','''    start_button_width = size.cx;
    SetWindowPos( tray_window, 0, 0, GetSystemMetrics( SM_CYSCREEN ) - tray_height,
                  tray_width, tray_height, SWP_NOZORDER | SWP_NOACTIVATE | SWP_SHOWWINDOW );
    sync_taskbar_buttons();''','''    start_button_width = size.cx;
    SetWindowPos( tray_window, 0, 0, GetSystemMetrics( SM_CYSCREEN ) - tray_height,
                  tray_width, tray_height, SWP_NOZORDER | SWP_NOACTIVATE | SWP_SHOWWINDOW );
    show_clock( &ncm.lfMessageFont );
    sync_taskbar_buttons();''','Place the clock with the taskbar.')
revise('systray.c','''    case WM_MOVE:
        update_systray_balloon_position();
        break;''','''    case WM_MOVE:
        update_systray_balloon_position();
        break;

    case WM_TIMER:
        if (wparam == CLOCK_TIMER) update_clock();
        break;''','Clock tick.')

# W054: guest programs (tools/build-guest-hw.py) run in this process; their windows get
# taskbar buttons like another process's. A guest thread carries its guest in
# TEB.UserReserved.
revise('systray.c','''static void add_taskbar_button( HWND hwnd )
{
    struct taskbar_button *win;

    if (!enable_taskbar) return;

    /* ignore our own windows */
    if (hwnd)
    {
        DWORD process;
        if (!GetWindowThreadProcessId( hwnd, &process ) || process == GetCurrentProcessId()) return;
    }''','''static BOOL is_guest_thread( DWORD tid )
{
    THREAD_BASIC_INFORMATION info;
    HANDLE thread = OpenThread( THREAD_QUERY_LIMITED_INFORMATION, FALSE, tid );
    BOOL guest = FALSE;

    if (!thread) return FALSE;
    if (!NtQueryInformationThread( thread, ThreadBasicInformation, &info, sizeof(info), NULL ) && info.TebBaseAddress)
        guest = *(void **)((TEB *)info.TebBaseAddress)->UserReserved != NULL;
    CloseHandle( thread );
    return guest;
}

static void add_taskbar_button( HWND hwnd )
{
    struct taskbar_button *win;

    if (!enable_taskbar) return;

    /* ignore our own windows, but not a guest program's */
    if (hwnd)
    {
        DWORD process, tid = GetWindowThreadProcessId( hwnd, &process );
        if (!tid || (process == GetCurrentProcessId() && !is_guest_thread( tid ))) return;
    }''','Taskbar buttons for guest windows.')
revise('systray.c','#include <wine/debug.h>','#include <winternl.h>\n#include <wine/debug.h>','TEB and NtQueryInformationThread.')
# W057: Start menu icons. add_folder_contents hands add_shell_item a pidl relative to the
# folder being listed, but SHGetFileInfo(SHGFI_PIDL) takes an absolute one, so entries
# inside folders got no icon. The entry's parsing path from its folder gives the icon
# instead; if the system image list still has none, the shortcut's own icon location
# (IShellLink) or shell32's folder icon is extracted and drawn.
revise('startmenu.c','''    HIMAGELIST icon_himl;
    int icon_i;''','''    HIMAGELIST icon_himl;
    int icon_i;
    HICON icon;  /* when the system image list has none (W057) */''','Fallback icon.')
revise('startmenu.c','''    himl = (HIMAGELIST)SHGetFileInfoW((LPCWSTR)pidl, 0, &sfi, sizeof(sfi), SHGFI_PIDL|SHGFI_SYSICONINDEX|SHGFI_SMALLICON);
    if (himl)
    {
        item->icon_himl = himl;
        item->icon_i = sfi.iIcon;
    }''','''    {
        WCHAR path[MAX_PATH] = {0};
        STRRET where;

        if (parent->pidl && SUCCEEDED(IShellFolder_GetDisplayNameOf( parent->folder, pidl, SHGDN_FORPARSING, &where )))
            StrRetToBufW( &where, pidl, path, MAX_PATH );
        if (path[0])
            himl = (HIMAGELIST)SHGetFileInfoW( path, 0, &sfi, sizeof(sfi), SHGFI_SYSICONINDEX|SHGFI_SMALLICON );
        else
            himl = (HIMAGELIST)SHGetFileInfoW((LPCWSTR)pidl, 0, &sfi, sizeof(sfi), SHGFI_PIDL|SHGFI_SYSICONINDEX|SHGFI_SMALLICON);
        if (himl)
        {
            item->icon_himl = himl;
            item->icon_i = sfi.iIcon;
        }
        else item->icon = fallback_icon( path, item->folder != NULL );
    }''','Icons for entries inside folders.')
revise('startmenu.c','''static struct menu_item* add_shell_item(struct menu_item* parent, LPITEMIDLIST pidl)
{''','''/* a small icon for an entry the system image list has none for: a shortcut's icon
 * location, else its target, else the file; for a folder, shell32's folder icon */
static HICON fallback_icon( const WCHAR *path, BOOL folder )
{
    WCHAR source[MAX_PATH] = {0};
    int index = 0;
    HICON icon = NULL;

    if (folder)
    {
        ExtractIconExW( L"shell32.dll", -4 /* IDI_SHELL_FOLDER */, NULL, &icon, 1 );
        return icon;
    }
    if (!path[0]) return NULL;
    lstrcpynW( source, path, MAX_PATH );
    if (!lstrcmpiW( PathFindExtensionW( path ), L".lnk" ))
    {
        IShellLinkW *link;
        IPersistFile *file;

        source[0] = 0;
        if (SUCCEEDED(CoCreateInstance( &CLSID_ShellLink, NULL, CLSCTX_INPROC_SERVER, &IID_IShellLinkW, (void **)&link )))
        {
            if (SUCCEEDED(IShellLinkW_QueryInterface( link, &IID_IPersistFile, (void **)&file )))
            {
                if (SUCCEEDED(IPersistFile_Load( file, path, STGM_READ )) &&
                    (FAILED(IShellLinkW_GetIconLocation( link, source, MAX_PATH, &index )) || !source[0]))
                {
                    index = 0;
                    IShellLinkW_GetPath( link, source, MAX_PATH, NULL, 0 );
                }
                IPersistFile_Release( file );
            }
            IShellLinkW_Release( link );
        }
    }
    if (source[0]) ExtractIconExW( source, index, NULL, &icon, 1 );
    return icon;
}

static struct menu_item* add_shell_item(struct menu_item* parent, LPITEMIDLIST pidl)
{''','Fallback icon extraction.')
revise('startmenu.c','''        if (item->icon_himl) {
            mii.fMask |= MIIM_BITMAP;''','''        if (item->icon_himl || item->icon) {
            mii.fMask |= MIIM_BITMAP;''','Entries with a fallback icon get one drawn.')
# Run and Exit get drawn glyphs; they have no shell icon.
revise('startmenu.c','''    mii.fMask = MIIM_STRING|MIIM_ID;
    mii.dwTypeData = label;
    mii.wID = MENU_ID_RUN;''','''    mii.fMask = MIIM_STRING|MIIM_ID|MIIM_BITMAP;
    mii.dwTypeData = label;
    mii.hbmpItem = HBMMENU_CALLBACK;
    mii.wID = MENU_ID_RUN;''','Run item glyph.')
revise('startmenu.c','''    mii.fMask = MIIM_STRING|MIIM_ID;
    mii.dwTypeData = label;
    mii.wID = MENU_ID_EXIT;''','''    mii.fMask = MIIM_STRING|MIIM_ID|MIIM_BITMAP;
    mii.dwTypeData = label;
    mii.hbmpItem = HBMMENU_CALLBACK;
    mii.wID = MENU_ID_EXIT;''','Exit item glyph.')
# The Steam client inside the title: "Open Steam Client" right above "Exit desktop". It starts
# C:\\orbis\\steam-open.exe (native/steam/orbis_steam_open.c, tools/build-steam-hosted.py), the same
# request the Desktop link makes; the client then takes the screen and the pad until it exits.
revise('startmenu.c','#define MENU_ID_EXIT 2\n','#define MENU_ID_EXIT 2\n#define MENU_ID_STEAM 3\n','Steam item id.')
revise('startmenu.c','''    LoadStringW(NULL, IDS_EXIT_LABEL, label, ARRAY_SIZE(label));''','''    mii.fMask = MIIM_STRING|MIIM_ID|MIIM_BITMAP;
    mii.dwTypeData = (WCHAR *)L"Open Steam Client";
    mii.hbmpItem = HBMMENU_CALLBACK;
    mii.wID = MENU_ID_STEAM;
    InsertMenuItemW(root_menu.menuhandle, -1, TRUE, &mii);

    LoadStringW(NULL, IDS_EXIT_LABEL, label, ARRAY_SIZE(label));''','Steam item above Exit.')
revise('startmenu.c','''            else if (mii.wID == MENU_ID_EXIT)
                shut_down(hwnd);''','''            else if (mii.wID == MENU_ID_EXIT)
                shut_down(hwnd);
            else if (mii.wID == MENU_ID_STEAM)
                ShellExecuteW(NULL, L"open", L"C:\\\\orbis\\\\steam-open.exe", NULL, L"C:\\\\orbis", SW_SHOWNORMAL);''','Steam item command.')
revise('startmenu.c','LRESULT menu_wndproc(HWND hwnd, UINT msg, WPARAM wparam, LPARAM lparam)\n{','''/* Run: a window with a blue title bar. Exit: a power symbol. */
static void draw_menu_glyph( const DRAWITEMSTRUCT *dis )
{
    int size = GetSystemMetrics( SM_CXSMICON ), x = dis->rcItem.left - 2, y = dis->rcItem.top, middle = x + size / 2;
    HBRUSH brush;
    RECT r;

    if (dis->itemID == MENU_ID_RUN)
    {
        brush = CreateSolidBrush( RGB( 0xb0, 0xb0, 0xb0 ));  /* visible on a dark or light menu */
        SetRect( &r, x + 1, y + 2, x + size - 1, y + size - 2 );
        FillRect( dis->hDC, &r, brush );
        DeleteObject( brush );
        brush = CreateSolidBrush( RGB( 0x1e, 0x90, 0xff ));
        SetRect( &r, x + 2, y + 3, x + size - 2, y + 6 );
        FillRect( dis->hDC, &r, brush );
        DeleteObject( brush );
        SetRect( &r, x + 2, y + 6, x + size - 2, y + size - 3 );
        FillRect( dis->hDC, &r, GetStockObject( WHITE_BRUSH ));
    }
    else if (dis->itemID == MENU_ID_STEAM)
    {
        /* a blue disc with a white hub */
        HBRUSH old_brush;
        HPEN old_pen = SelectObject( dis->hDC, GetStockObject( NULL_PEN ));
        brush = CreateSolidBrush( RGB( 0x66, 0xc0, 0xf4 ));
        old_brush = SelectObject( dis->hDC, brush );
        Ellipse( dis->hDC, x + 1, y + 1, x + size - 1, y + size - 1 );
        SelectObject( dis->hDC, GetStockObject( WHITE_BRUSH ));
        Ellipse( dis->hDC, middle - 2, y + size / 2 - 2, middle + 3, y + size / 2 + 3 );
        SelectObject( dis->hDC, old_brush );
        SelectObject( dis->hDC, old_pen );
        DeleteObject( brush );
    }
    else if (dis->itemID == MENU_ID_EXIT)
    {
        HPEN pen = CreatePen( PS_SOLID, 2, RGB( 0xc0, 0x20, 0x20 )), old_pen = SelectObject( dis->hDC, pen );
        HBRUSH old_brush = SelectObject( dis->hDC, GetStockObject( NULL_BRUSH ));

        /* counter-clockwise from the left of the gap at the top round to its right */
        Arc( dis->hDC, x + 2, y + 3, x + size - 2, y + size - 1, middle - 3, y + 3, middle + 3, y + 3 );
        MoveToEx( dis->hDC, middle, y + 1, NULL );
        LineTo( dis->hDC, middle, y + size / 2 + 1 );
        SelectObject( dis->hDC, old_brush );
        SelectObject( dis->hDC, old_pen );
        DeleteObject( pen );
    }
}

LRESULT menu_wndproc(HWND hwnd, UINT msg, WPARAM wparam, LPARAM lparam)
{''','Glyph painter for Run and Exit.')
revise('startmenu.c','''            struct menu_item* item = (struct menu_item*)dis->itemData;

            ImageList_Draw(''','''            struct menu_item* item = (struct menu_item*)dis->itemData;

            if (!item)
            {
                draw_menu_glyph( dis );
                return TRUE;
            }
            if (!item->icon_himl)
            {
                if (item->icon) DrawIconEx( dis->hDC, dis->rcItem.left - 2, dis->rcItem.top, item->icon,
                                            GetSystemMetrics(SM_CXSMICON), GetSystemMetrics(SM_CYSMICON), 0, NULL, DI_NORMAL );
                return TRUE;
            }
            ImageList_Draw(''','Run and Exit have no menu_item; entries may have a fallback icon.')

# W097: distinguish a stopped shell thread from missing clicks after guest teardown.
# The observer belongs to explorer (created before any guest), never calls SendMessage,
# and records progress without trying to recover or conceal a blocked shell.
revise('systray.c','static int icon_cx, icon_cy, tray_width, tray_height;', '''static LONG volatile orbis_shell_stage, orbis_shell_tick;

void orbis_shell_mark( LONG stage )
{
    /* W151: no log per stage (several per window event); the observer reports the last one */
    InterlockedExchange( &orbis_shell_stage, stage );
}

static DWORD WINAPI orbis_shell_monitor( void *arg )
{
    DWORD tid = (DWORD)(ULONG_PTR)arg;
    unsigned int count = 0;
    LONG previous = -1;
    int shell_traced = -1;
    LARGE_INTEGER qpc_start = {0}, qpc_frequency = {0};

    QueryPerformanceCounter( &qpc_start );
    QueryPerformanceFrequency( &qpc_frequency );

    for (;;)
    {
        GUITHREADINFO info = {.cbSize = sizeof(info)};
        LONG stage;
        DWORD now;
        BOOL valid;
        LARGE_INTEGER qpc_now = {0};

        Sleep( 2000 );
        now = GetTickCount();
        stage = InterlockedCompareExchange( &orbis_shell_stage, 0, 0 );
        QueryPerformanceCounter( &qpc_now );
        valid = GetGUIThreadInfo( tid, &info );
        /* alpha-1: two lines every 10 s for the whole session, traces only (PW_TRACE, platform/ps4/pw_trace.h);
         * the hang reports below (PWHUNG, PWDUMP) stay */
        if (shell_traced < 0)
        {
            WCHAR level[4];
            shell_traced = !GetEnvironmentVariableW( L"PW_TRACE", level, ARRAY_SIZE(level) ) || level[0] != '0';
        }
        if (shell_traced && (stage != previous || count < 5 || !(count % 5)))
        {
            ERR( "PWSHELL clocks tick=%lu qpc_elapsed_ms=%I64d qpc_valid=%u\\n", now,
                 qpc_frequency.QuadPart ? (qpc_now.QuadPart - qpc_start.QuadPart) * 1000 / qpc_frequency.QuadPart : 0,
                 qpc_frequency.QuadPart != 0 );
            ERR( "PWSHELL monitor ui_tid=%04lx stage=%ld heartbeat_age_ms=%lu gui=%u flags=%lx active=%p focus=%p capture=%p menu=%p foreground=%p\\n",
                 tid, stage, now - (DWORD)InterlockedCompareExchange( &orbis_shell_tick, 0, 0 ),
                 valid, info.flags, info.hwndActive, info.hwndFocus, info.hwndCapture,
                 info.hwndMenuOwner, GetForegroundWindow() );
        }
        previous = stage;
        count++;
    }
}

static int icon_cx, icon_cy, tray_width, tray_height;''', 'Independent shell progress observer; no timeout/recovery simulation.')
# Wnnn (W192, W195: Pale Moon as a guest, then the desktop stopped and no thread logged anything):
# when the shell thread's heartbeat is 8 s old, and again at 70 s, each thread of the process
# once. Read only: a thread is suspended just for GetThreadContext; nothing is recovered.
revise('systray.c','''#include <wine/list.h>''','''#include <wine/list.h>
#include <winternl.h>
#include <tlhelp32.h>''','Thread dump on a stopped shell (toolhelp, NtQueryInformationThread).')
revise('systray.c','''static DWORD WINAPI orbis_shell_monitor( void *arg )
{''','''/* Wnnn (W199): the image an address is in, read from its own headers: no toolhelp (W198:
 * "modules unavailable error=5"; W199: the snapshot never returned) and no loader lock (W199: a
 * Pale Moon thread held it). The name is the image's export name, "-" when it has none. */
static const char *orbis_dump_image( ULONG_PTR address, ULONG_PTR *base )
{
    MEMORY_BASIC_INFORMATION info;
    const IMAGE_DOS_HEADER *dos;
    const IMAGE_NT_HEADERS64 *nt;
    const IMAGE_DATA_DIRECTORY *dir;
    ULONG_PTR start;

    if (!address || !VirtualQuery( (void *)address, &info, sizeof(info) ) || info.State != MEM_COMMIT ||
        !info.AllocationBase) return NULL;
    start = (ULONG_PTR)info.AllocationBase;
    if (!VirtualQuery( (void *)start, &info, sizeof(info) ) || info.State != MEM_COMMIT ||
        (info.Protect & (PAGE_NOACCESS | PAGE_GUARD)) || info.RegionSize < 0x1000) return NULL;
    dos = (const IMAGE_DOS_HEADER *)start;
    if (dos->e_magic != IMAGE_DOS_SIGNATURE || dos->e_lfanew <= 0 || dos->e_lfanew > 0x800) return NULL;
    nt = (const IMAGE_NT_HEADERS64 *)(start + dos->e_lfanew);
    if (nt->Signature != IMAGE_NT_SIGNATURE || nt->OptionalHeader.Magic != IMAGE_NT_OPTIONAL_HDR64_MAGIC ||
        address - start >= nt->OptionalHeader.SizeOfImage) return NULL;
    *base = start;
    dir = &nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_EXPORT];
    if (nt->OptionalHeader.NumberOfRvaAndSizes > IMAGE_DIRECTORY_ENTRY_EXPORT && dir->VirtualAddress &&
        dir->VirtualAddress < nt->OptionalHeader.SizeOfImage)
    {
        const IMAGE_EXPORT_DIRECTORY *exports = (const IMAGE_EXPORT_DIRECTORY *)(start + dir->VirtualAddress);

        if (exports->Name && exports->Name < nt->OptionalHeader.SizeOfImage) return (const char *)(start + exports->Name);
    }
    return "-";
}

static void orbis_dump_address( DWORD tid, const char *what, unsigned int index, ULONG_PTR address )
{
    ULONG_PTR base = 0;
    const char *name = orbis_dump_image( address, &base );

    if (name)
        ERR( "PWDUMP thread=%04lx %s %u %.40s+%Ix base=%Ix\\n", tid, what, index, name, address - base, base );
    else
        ERR( "PWDUMP thread=%04lx %s %u %Ix\\n", tid, what, index, address );
}

/* Wnnn: where a thread started and where it is now, on the Windows side. It is suspended only
 * for GetThreadContext; its stack is walked after it runs again, within the stack limits of its
 * TEB and through code of loaded modules only (unwind data; JIT code ends the walk). */
static void orbis_dump_thread( DWORD tid )
{
    HANDLE thread = OpenThread( THREAD_SUSPEND_RESUME | THREAD_GET_CONTEXT | THREAD_QUERY_INFORMATION, FALSE, tid );
    CONTEXT context = {.ContextFlags = CONTEXT_CONTROL | CONTEXT_INTEGER};
    THREAD_BASIC_INFORMATION basic;
    ULONG_PTR start = 0, stack_low = 0, stack_high = 0;
    void *teb = NULL;  /* W277 */
    DWORD suspend, error = 0;
    unsigned int frame;
    BOOL got;

    if (!thread)
    {
        ERR( "PWDUMP thread=%04lx open_error=%lu\\n", tid, GetLastError() );
        return;
    }
    NtQueryInformationThread( thread, ThreadQuerySetWin32StartAddress, &start, sizeof(start), NULL );
    if (!NtQueryInformationThread( thread, ThreadBasicInformation, &basic, sizeof(basic), NULL ) && basic.TebBaseAddress)
    {
        NT_TIB *tib = basic.TebBaseAddress;
        teb = basic.TebBaseAddress;
        stack_low = (ULONG_PTR)tib->StackLimit;
        stack_high = (ULONG_PTR)tib->StackBase;
    }
    orbis_dump_address( tid, "start", 0, start );
    suspend = SuspendThread( thread );
    got = suspend != (DWORD)-1 && GetThreadContext( thread, &context );
    if (!got) error = GetLastError();
    if (suspend != (DWORD)-1) ResumeThread( thread );
    CloseHandle( thread );
    if (!got)
    {
        ERR( "PWDUMP thread=%04lx context_error=%lu suspend=%ld\\n", tid, error, (LONG)suspend );
        return;
    }
    ERR( "PWDUMP thread=%04lx suspend=%lu rip=%Ix rsp=%Ix rax=%Ix rcx=%Ix rdx=%Ix r8=%Ix r9=%Ix stack=%Ix-%Ix\\n",
         tid, suspend, context.Rip, context.Rsp, context.Rax, context.Rcx, context.Rdx, context.R8, context.R9,
         stack_low, stack_high );
    for (frame = 0; frame < 20; frame++)
    {
        RUNTIME_FUNCTION *function;
        ULONG_PTR base, establisher;
        void *data;

        orbis_dump_address( tid, "frame", frame, context.Rip );
        if (context.Rsp < stack_low || context.Rsp + 8 > stack_high || !orbis_dump_image( context.Rip, &base )) break;
        if ((function = RtlLookupFunctionEntry( context.Rip, &base, NULL )))
            RtlVirtualUnwind( UNW_FLAG_NHANDLER, base, context.Rip, function, &context, &data, &establisher, NULL );
        else
        {
            context.Rip = *(ULONG_PTR *)context.Rsp;
            context.Rsp += 8;
        }
        if (!context.Rip) break;
    }
    /* W277 (W274: GTA San Andreas hung with its main thread and a d3d9 thread both in NtWaitForAlertByThreadId, and
     * the dump showed only their 64-bit side): a 32-bit thread's state at its last switch to 64-bit code, kept by
     * wow64 in TlsSlots[WOW64_TLS_CPURESERVED] (Flags, Machine, I386_CONTEXT), and its EBP chain. The addresses are
     * raw: the 32-bit modules are not in this loader's list (their bases are in the loaddll lines). */
    if (teb)
    {
        ULONG_PTR cpu = 0;
        USHORT machine = 0;
        ULONG regs[6] = {0}, ebp, link[2];
        SIZE_T done;

        if (!NtReadVirtualMemory( GetCurrentProcess(), (char *)teb + 0x1488, &cpu, sizeof(cpu), &done ) && cpu &&
            !NtReadVirtualMemory( GetCurrentProcess(), (char *)cpu + 2, &machine, sizeof(machine), &done ) &&
            machine == IMAGE_FILE_MACHINE_I386 &&
            !NtReadVirtualMemory( GetCurrentProcess(), (char *)cpu + 4 + 0xb4, regs, sizeof(regs), &done ))
        {
            /* I386_CONTEXT: Ebp 0xb4, Eip 0xb8, SegCs 0xbc, EFlags 0xc0, Esp 0xc4 */
            ERR( "PWDUMP thread=%04lx x86 eip=%lx esp=%lx ebp=%lx\\n", tid, regs[1], regs[4], regs[0] );
            for (frame = 0, ebp = regs[0]; frame < 24 && ebp; frame++, ebp = link[0])
            {
                if (NtReadVirtualMemory( GetCurrentProcess(), (void *)(ULONG_PTR)ebp, link, sizeof(link), &done ) ||
                    !link[1]) break;
                ERR( "PWDUMP thread=%04lx x86 frame %u ret=%lx ebp=%lx\\n", tid, frame, link[1], ebp );
                if (link[0] <= ebp) break;
            }
        }
    }
}

/* Wnnn: on the observer thread itself (a new thread would wait for the loader lock, which a
 * stopped thread may hold). If a thread's context never comes, its "start" line is the last one.
 * alpha-1 (W300: four dumps of 37 threads were 70% of a release run log, for a game that was loading, not
 * stopped): not full, one line with the thread count; full with traces (PW_TRACE) or on request. */
static void orbis_dump_threads( DWORD age, BOOL full )
{
    RTL_CRITICAL_SECTION *loader = NtCurrentTeb()->Peb->LoaderLock;
    THREADENTRY32 entry = {.dwSize = sizeof(entry)};
    DWORD pid = GetCurrentProcessId(), self = GetCurrentThreadId();
    unsigned int threads = 0;
    HANDLE snapshot;

    if (!full)
    {
        if ((snapshot = CreateToolhelp32Snapshot( TH32CS_SNAPTHREAD, 0 )) == INVALID_HANDLE_VALUE)
        {
            ERR( "PWDUMP skipped age_ms=%lu threads unavailable error=%lu\\n", age, GetLastError() );
            return;
        }
        if (Thread32First( snapshot, &entry )) do
            if (entry.th32OwnerProcessID == pid && entry.th32ThreadID != self) threads++;
        while (Thread32Next( snapshot, &entry ));
        CloseHandle( snapshot );
        ERR( "PWDUMP skipped age_ms=%lu threads=%u loader_owner=%04lx (full with traces or dumpnow.txt)\\n", age,
             threads, loader ? HandleToULong( loader->OwningThread ) : 0 );
        return;
    }
    ERR( "PWDUMP begin age_ms=%lu loader_owner=%04lx loader_count=%ld\\n", age,
         loader ? HandleToULong( loader->OwningThread ) : 0, loader ? loader->LockCount : 0 );
    /* W201: the thread list is the dump's first server call (PWSERVER in the server's watchdog) */
    ERR( "PWDUMP step=thread_list\\n" );
    if ((snapshot = CreateToolhelp32Snapshot( TH32CS_SNAPTHREAD, 0 )) == INVALID_HANDLE_VALUE)
    {
        ERR( "PWDUMP threads unavailable error=%lu\\n", GetLastError() );
        return;
    }
    if (Thread32First( snapshot, &entry )) do
    {
        if (entry.th32OwnerProcessID != pid || entry.th32ThreadID == self) continue;
        threads++;
        orbis_dump_thread( entry.th32ThreadID );
    } while (Thread32Next( snapshot, &entry ));
    CloseHandle( snapshot );
    ERR( "PWDUMP end threads=%u\\n", threads );
}

static DWORD WINAPI orbis_shell_monitor( void *arg )
{''','Thread dump helpers for a stopped shell.')
revise('systray.c','''    DWORD tid = (DWORD)(ULONG_PTR)arg;
    unsigned int count = 0;''','''    DWORD tid = (DWORD)(ULONG_PTR)arg;
    unsigned int count = 0, dumps = 0;''','Count the dumps of one stop.')
revise('systray.c','''        previous = stage;
        count++;''','''        {
            DWORD age = now - (DWORD)InterlockedCompareExchange( &orbis_shell_tick, 0, 0 );

            /* alpha-1: a tick stamped after `now` was read is a negative age, not a stop */
            if (age < 8000 || (LONG)age < 0) dumps = 0;
            else if ((dumps == 0) || (dumps == 1 && age >= 70000))
            {
                dumps++;
                orbis_dump_threads( age, shell_traced );
            }
        }
        previous = stage;
        count++;''','Dump the threads at 8 s and 70 s of a stopped shell.')
# W205 (W204: Pale Moon as a guest stopped after creating a second top-level window, while the
# shell went on): the same dump when a visible top-level window of another thread is hung (no
# message retrieved for 5 s, IsHungAppWindow) for 8 s, and again at 70 s. Read only.
revise('systray.c','''static DWORD WINAPI orbis_shell_monitor( void *arg )
{''','''/* W205: the first visible top-level window of another thread that Wine reports hung */
struct orbis_hung
{
    DWORD ui_tid, tid;
    HWND hwnd;
    unsigned int count;
};

static BOOL CALLBACK orbis_hung_proc( HWND hwnd, LPARAM lparam )
{
    struct orbis_hung *hung = (struct orbis_hung *)lparam;
    DWORD tid;

    if (!IsWindowVisible( hwnd ) || !IsHungAppWindow( hwnd )) return TRUE;
    if ((tid = GetWindowThreadProcessId( hwnd, NULL )) == hung->ui_tid) return TRUE;
    if (!hung->hwnd)
    {
        hung->hwnd = hwnd;
        hung->tid = tid;
    }
    hung->count++;
    return TRUE;
}

static DWORD WINAPI orbis_shell_monitor( void *arg )
{''','Find hung windows of other threads (W205).')
revise('systray.c','''    unsigned int count = 0, dumps = 0;''','''    unsigned int count = 0, dumps = 0, hung_dumps = 0;
    DWORD hung_since = 0;''','Count the dumps of one hung window (W205).')
revise('systray.c','''                orbis_dump_threads( age, shell_traced );
            }
        }
        previous = stage;''','''                orbis_dump_threads( age, shell_traced );
            }
        }
        {
            struct orbis_hung hung = {.ui_tid = tid};

            EnumWindows( orbis_hung_proc, (LPARAM)&hung );
            /* W217: a dump on demand (W216: SeaMonkey sat with no window, so no PWHUNG): the file is
             * created over FTP while a program sits there */
            if (GetFileAttributesW( L"C:\\\\orbis\\\\dumpnow.txt" ) != INVALID_FILE_ATTRIBUTES)
            {
                DeleteFileW( L"C:\\\\orbis\\\\dumpnow.txt" );
                ERR( "PWDUMP requested\\n" );
                orbis_dump_threads( 0, TRUE );
            }
            if (!hung.hwnd) hung_since = hung_dumps = 0;
            else
            {
                DWORD hung_age;

                if (!hung_since) hung_since = now | 1;
                /* alpha-1 (W300: age_ms=4294967295): `now | 1` is now + 1 for an even tick, so the first
                 * pass gave -1 and dumped at once; an age below zero is no age */
                hung_age = (LONG)(now - hung_since) > 0 ? now - hung_since : 0;
                if ((hung_dumps == 0 && hung_age >= 8000) || (hung_dumps == 1 && hung_age >= 70000))
                {
                    WCHAR class[64] = {0}, title[64] = {0};

                    GetClassNameW( hung.hwnd, class, ARRAY_SIZE(class) );
                    InternalGetWindowText( hung.hwnd, title, ARRAY_SIZE(title) );
                    ERR( "PWHUNG hwnd=%p tid=%04lx windows=%u class=%s title=%s age_ms=%lu\\n", hung.hwnd, hung.tid,
                         hung.count, debugstr_w( class ), debugstr_w( title ), hung_age );
                    hung_dumps++;
                    orbis_dump_threads( hung_age, shell_traced );
                }
            }
        }
        previous = stage;''','Dump the threads at 8 s and 70 s of a hung window (W205).')
revise('systray.c','''        if (wparam == CLOCK_TIMER) update_clock();''','''        if (wparam == CLOCK_TIMER)
        {
            InterlockedExchange( &orbis_shell_tick, GetTickCount() );
            update_clock();
        }''','Clock heartbeat on the actual shell thread.')
revise('systray.c','''    add_taskbar_button( 0 );

    if (enable_taskbar)''','''    add_taskbar_button( 0 );
    InterlockedExchange( &orbis_shell_tick, GetTickCount() );
    {
        HANDLE observer = CreateThread( NULL, 0, orbis_shell_monitor,
                                       (void *)(ULONG_PTR)GetCurrentThreadId(), 0, NULL );
        ERR( "PWSHELL observer=%p ui_tid=%04lx tray=%p\\n", observer, GetCurrentThreadId(), tray_window );
        if (observer) CloseHandle( observer );
    }

    if (enable_taskbar)''','Start observer before any guest can inherit thread ownership.')
revise('systray.c','''            click_taskbar_button( (HWND)lparam );''','''            click_taskbar_button( (HWND)lparam );
            orbis_shell_mark( 20 );''','Trace whether Start receives its button notification.')
revise('systray.c','''    list_remove( &win->entry );
    DestroyWindow( win->button );
    free( win );''','''    list_remove( &win->entry );
    orbis_shell_mark( 31 );
    DestroyWindow( win->button );
    orbis_shell_mark( 32 );
    free( win );''','Locate taskbar button destruction stalls.')
revise('systray.c','''    NtUserMessageCall( hwnd, WINE_SYSTRAY_CLEANUP_ICONS, 0, 0, NULL, NtUserSystemTrayCall, FALSE );''','''    orbis_shell_mark( 33 );
    NtUserMessageCall( hwnd, WINE_SYSTRAY_CLEANUP_ICONS, 0, 0, NULL, NtUserSystemTrayCall, FALSE );
    orbis_shell_mark( 34 );''','Trace tray cleanup after a guest window is destroyed.')
revise('systray.c','''void handle_parent_notify( HWND hwnd, WPARAM wp )
{
    switch''','''void handle_parent_notify( HWND hwnd, WPARAM wp )
{
    orbis_shell_mark( 30 );
    switch''','Trace guest window notifications.')
revise('systray.c','''    sync_taskbar_buttons();
}

/* this function creates the listener window */''','''    orbis_shell_mark( 35 );
    sync_taskbar_buttons();
    orbis_shell_mark( 36 );
}

/* this function creates the listener window */''','Trace taskbar synchronization after a window notification.')
revise('startmenu.c','''void do_startmenu(HWND hwnd)
{''','''extern void orbis_shell_mark( LONG stage );

void do_startmenu(HWND hwnd)
{''','Share shell progress markers.')
revise('startmenu.c','''    destroy_menus();

    TRACE( "creating start menu\\n" );''','''    orbis_shell_mark( 100 );
    destroy_menus();
    orbis_shell_mark( 101 );

    TRACE( "creating start menu\\n" );''','Locate previous-menu cleanup stalls.')
revise('startmenu.c','''        fill_menu(&user_startmenu);

        AppendMenuW''','''        orbis_shell_mark( 102 );
        fill_menu(&user_startmenu);
        orbis_shell_mark( 103 );

        AppendMenuW''','Trace Start enumeration and icon loading.')
revise('startmenu.c','''    if (SUCCEEDED(SHGetSpecialFolderLocation(NULL, CSIDL_CONTROLS, &pidl)))''','''    orbis_shell_mark( 104 );
    if (SUCCEEDED(SHGetSpecialFolderLocation(NULL, CSIDL_CONTROLS, &pidl)))''','Trace special-folder setup.')
revise('startmenu.c','''    if (!TrackPopupMenuEx(root_menu.menuhandle,''','''    orbis_shell_mark( 105 );
    if (!TrackPopupMenuEx(root_menu.menuhandle,''','Trace menu tracking entry.')
revise('startmenu.c','''        ERR( "couldn't display menu\\n" );
    }
}''','''        ERR( "couldn't display menu\\n" );
    }
    orbis_shell_mark( 106 );
}''','Trace menu tracking return.')

# W168: desktop shortcuts. explorer loads the .lnk files of the Desktop folders as launchers
# and paints them in the desktop window's WM_PAINT, but the desktop window has no surface in
# ps5drv (W045: only top-level windows are composed, over the driver's wallpaper layer), so
# nothing it paints reaches the screen; double-clicks there did reach it. The launchers move
# to their own top-level window at the bottom of the stack, the size of the icon grid from
# the top-left corner (screen and client coordinates are the same); it paints the wallpaper
# under them with PaintDesktop, never takes activation and stays at the bottom.
revise('desktop.c','''static DWORD CALLBACK watch_desktop_folders( LPVOID param )
{''','''static void place_desktop_icons( HWND panel );

static DWORD CALLBACK watch_desktop_folders( LPVOID param )
{''','Forward declaration for the folder watcher.')
revise('desktop.c','''        if (redraw) InvalidateRect( hwnd, NULL, TRUE );''','''        if (redraw) place_desktop_icons( hwnd );''',
       'A Desktop folder change resizes and repaints the launcher window.')
revise('desktop.c','''static void wait_named_mutex( const WCHAR *name )
{''','''/* the launcher grid: from the top-left corner, as many rows as the launchers need */
static void place_desktop_icons( HWND panel )
{
    unsigned int count = nb_launchers, rows, columns;

    if (!count || !launchers_per_row)
    {
        ShowWindow( panel, SW_HIDE );
        return;
    }
    rows = (count + launchers_per_row - 1) / launchers_per_row;
    columns = rows > 1 ? launchers_per_row : count;
    SetWindowPos( panel, HWND_BOTTOM, 0, 0, columns * launcher_size, rows * launcher_size,
                  SWP_NOACTIVATE | SWP_SHOWWINDOW );
    InvalidateRect( panel, NULL, TRUE );
}

static LRESULT WINAPI desktop_icons_wnd_proc( HWND hwnd, UINT message, WPARAM wp, LPARAM lp )
{
    switch (message)
    {
    case WM_MOUSEACTIVATE:
        return MA_NOACTIVATE;

    case WM_WINDOWPOSCHANGING:
        {
            WINDOWPOS *pos = (WINDOWPOS *)lp;
            if (!(pos->flags & SWP_NOZORDER)) pos->hwndInsertAfter = HWND_BOTTOM;
        }
        return 0;

    case WM_SETCURSOR:
        return (LRESULT)SetCursor( LoadCursorA( 0, (LPSTR)IDC_ARROW ) );

    case WM_ERASEBKGND:
        return TRUE;

    case WM_LBUTTONDBLCLK:
        {
            const struct launcher *launcher = launcher_from_point( (short)LOWORD(lp), (short)HIWORD(lp) );
            if (launcher) orbis_open_launcher( launcher->path );  /* W295 */
        }
        return 0;

    case WM_PAINT:
        {
            PAINTSTRUCT ps;
            BeginPaint( hwnd, &ps );
            PaintDesktop( ps.hdc );
            draw_launchers( ps.hdc, ps.rcPaint );
            EndPaint( hwnd, &ps );
        }
        return 0;
    }
    return DefWindowProcW( hwnd, message, wp, lp );
}

static HWND create_desktop_icons(void)
{
    WNDCLASSW class = {0};
    HWND panel;

    class.style = CS_DBLCLKS;
    class.lpfnWndProc = desktop_icons_wnd_proc;
    class.hCursor = LoadCursorW( 0, (LPCWSTR)IDC_ARROW );
    class.lpszClassName = L"OrbisDesktopIcons";
    if (!RegisterClassW( &class ) && GetLastError() != ERROR_CLASS_ALREADY_EXISTS)
    {
        ERR( "PWDESK class error=%lu\\n", GetLastError() );
        return 0;
    }
    panel = CreateWindowExW( WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE, class.lpszClassName, NULL, WS_POPUP,
                             0, 0, 0, 0, 0, 0, 0, NULL );
    if (!panel) ERR( "PWDESK window error=%lu\\n", GetLastError() );
    return panel;
}

static void wait_named_mutex( const WCHAR *name )
{''','Launcher window: wallpaper and icons, bottom of the stack, no activation.')
revise('desktop.c','''        if (!using_root && enable_launchers) initialize_launchers( hwnd );''','''        if (!using_root && enable_launchers)
        {
            HWND panel = create_desktop_icons();

            initialize_launchers( panel ? panel : hwnd );
            if (panel) place_desktop_icons( panel );
            ERR( "PWDESK launchers=%u panel=%p size=%d per_row=%d desktop=%s public=%s\\n", nb_launchers, panel,
                 launcher_size, launchers_per_row, debugstr_w(desktop_folder), debugstr_w(desktop_folder_public) );
        }''','Launchers in their own window; one log line with what was found.')

# W290 (user, W289: a Desktop shortcut renamed, deleted or added from WFM shows only after OrbisDesk
# restarts): watch_desktop_folders waits on ReadDirectoryChangesW, and the PS4 wineserver has no
# change backend (configured --without-inotify, no dnotify in the PS4 kernel, no kqueue path in
# server/change.c): the request stays pending forever. The native Steam client also writes Desktop
# links outside Wine. A thread compares a signature of the *.lnk files (name, size, last write)
# every 2 s; a change, or a notification where they work, asks the launcher window to reload the
# list on its own thread (upstream changed it from the watcher thread while the window painted).
# The icons get a right-click menu (circle, a two-finger press or tap, a mouse's right button):
# Open, Open file location (WFM), Rename, Delete (asks first; only the shortcut), Properties;
# on empty desktop: Refresh, Open Desktop folder.
revise('desktop.c','''static BOOL process_changes( const WCHAR *folder, char *buf )
{
    FILE_NOTIFY_INFORMATION *info = (FILE_NOTIFY_INFORMATION *)buf;
    BOOL ret = FALSE;

    for (;;)
    {
        switch (info->Action)
        {
        case FILE_ACTION_ADDED:
        case FILE_ACTION_RENAMED_NEW_NAME:
            if (add_launcher( folder, info->FileName, info->FileNameLength / sizeof(WCHAR) ))
                ret = TRUE;
            break;

        case FILE_ACTION_REMOVED:
        case FILE_ACTION_RENAMED_OLD_NAME:
            if (remove_launcher( folder, info->FileName, info->FileNameLength / sizeof(WCHAR) ))
                ret = TRUE;
            break;

        default:
            WARN( "unexpected action %lu\\n", info->Action );
            break;
        }
        if (!info->NextEntryOffset) break;
        info = (FILE_NOTIFY_INFORMATION *)((char *)info + info->NextEntryOffset);
    }
    return ret;
}
''','''/* W290: a notification only asks the launcher window to reload; the list is changed on its thread */
#define WM_ORBIS_DESKTOP_RESCAN (WM_APP + 0x51)
''','Notifications ask for a reload instead of changing the list from the watcher thread (W290).')
revise('desktop.c','''static BOOL remove_launcher( const WCHAR *folder, const WCHAR *filename, int len_filename )
{
    UINT i;
    WCHAR *path;
    BOOL ret = FALSE;

    if (!(path = append_path( folder, filename, len_filename ))) return FALSE;
    for (i = 0; i < nb_launchers; i++)
    {
        if (!wcsicmp( launchers[i]->path, path ))
        {
            free_launcher( launchers[i] );
            if (--nb_launchers)
                memmove( &launchers[i], &launchers[i + 1], sizeof(launchers[i]) * (nb_launchers - i) );
            ret = TRUE;
            break;
        }
    }
    free( path );
    return ret;
}
''','''/* W290: remove_launcher went with process_changes: a change reloads the whole list */
''','remove_launcher, used only by process_changes, removed (W290).')
# W295 (user, W294): a shortcut whose icon location and target give no icon (a DOS game, say) was left
# off the desktop, since add_launcher drops a launcher without an icon. It now gets shell32's generic
# window icon (resource 3, IDI_SHELL_WINDOW); its title stays the file name. The fallback is logged.
revise('desktop.c','''        ExtractIconExW( target_path, index, &icon, NULL, 1 );
    }
    return icon;''','''        ExtractIconExW( target_path, index, &icon, NULL, 1 );
    }
    if (!icon)
    {
        WCHAR shell32[MAX_PATH], message[2 * MAX_PATH];

        if (GetSystemDirectoryW( shell32, MAX_PATH ))
        {
            lstrcatW( shell32, L"\\\\shell32.dll" );
            ExtractIconExW( shell32, -3 /* IDI_SHELL_WINDOW */, &icon, NULL, 1 );
        }
        swprintf( message, ARRAY_SIZE(message), L"PWDESK launcher_default_icon icon=%p path=%s target=%s",
                  icon, icon_path, tmp_path );
        OutputDebugStringW( message );
    }
    return icon;''','A shortcut without an icon of its own gets the generic window icon instead of being left off (W295).')
# W295 (user, W295: desktop shortcuts to MARIO.EXE and CARMEN.EXE did not open; the same EXE opened
# from WFM did): a launcher went straight to ShellExecute, which hands a DOS executable to Wine
# (PWOPEN reject_title_replacement). A shortcut whose target is a DOS program now goes through the
# desktop's open request, the path WFM uses, which starts doshost.exe (patch-explorer-open.py).
revise('desktop.c','''static WCHAR *build_title( const WCHAR *filename, int len )''','''static void orbis_open_launcher( const WCHAR *path )
{
    IShellLinkW *link;
    WCHAR target[MAX_PATH] = {0}, expanded[MAX_PATH] = {0};
    struct pw_shell_open_request *request = NULL;

    if ((link = load_shelllink( path )))
    {
        IShellLinkW_GetPath( link, target, MAX_PATH, NULL, SLGP_RAWPATH );
        if (target[0] && ExpandEnvironmentStringsW( target, expanded, MAX_PATH ) && expanded[0] &&
            pw_is_dos_file( expanded ) &&
            (request = HeapAlloc( GetProcessHeap(), HEAP_ZERO_MEMORY, sizeof(*request) )))
        {
            lstrcpynW( request->path, expanded, MAX_PATH );
            IShellLinkW_GetWorkingDirectory( link, request->directory, MAX_PATH );
        }
        IShellLinkW_Release( link );
    }
    if (request)
    {
        if (PostMessageW( GetDesktopWindow(), PW_SHELL_OPEN_MESSAGE, 0, (LPARAM)request ))
        {
            ERR( "PWDOS launcher path=%s target=%s\\n", debugstr_w(path), debugstr_w(request->path) );
            return;
        }
        ERR( "PWDOS launcher post failed path=%s error=%lu\\n", debugstr_w(path), GetLastError() );
        HeapFree( GetProcessHeap(), 0, request );
    }
    ShellExecuteW( NULL, L"open", path, NULL, NULL, 0 );
}

static WCHAR *build_title( const WCHAR *filename, int len )''','Desktop shortcuts to DOS programs open through doshost, as from WFM (W295).')
revise('desktop.c','''            if (launcher) ShellExecuteW( NULL, L"open", launcher->path, NULL, NULL, 0 );''','''            if (launcher) orbis_open_launcher( launcher->path );  /* W295 */''','Desktop window double-click: the same launcher open (W295).')
revise('desktop.c','''            if (process_changes( desktop_folder, buf0 )) redraw = TRUE;''','''            redraw = TRUE;''','Notification on the user Desktop: reload (W290).')
revise('desktop.c','''            if (process_changes( desktop_folder_public, buf1 )) redraw = TRUE;''','''            redraw = TRUE;''','Notification on the public Desktop: reload (W290).')
revise('desktop.c','''        if (redraw) place_desktop_icons( hwnd );''','''        if (redraw) PostMessageW( hwnd, WM_ORBIS_DESKTOP_RESCAN, 0, 0 );''','The watcher posts the reload (W290).')
revise('desktop.c','''static LRESULT WINAPI desktop_icons_wnd_proc( HWND hwnd, UINT message, WPARAM wp, LPARAM lp )
{''','''/* W290: Desktop folder changes while OrbisDesk runs, and the right-click menu */
enum { ORBIS_RESCAN_NOTIFY, ORBIS_RESCAN_POLL, ORBIS_RESCAN_MENU };
enum { ORBIS_MENU_OPEN = 1, ORBIS_MENU_LOCATION, ORBIS_MENU_RENAME, ORBIS_MENU_DELETE, ORBIS_MENU_PROPERTIES,
       ORBIS_MENU_REFRESH = 10, ORBIS_MENU_DESKTOP_FOLDER };
static HWND orbis_desktop_panel;
static LONG orbis_desktop_signature;  /* folded: no 64-bit interlocked in this mingw */

/* name, size and last write of each *.lnk; order independent */
static ULONG64 orbis_folder_signature( const WCHAR *folder, ULONG64 seed, unsigned int *count )
{
    WCHAR glob[MAX_PATH];
    WIN32_FIND_DATAW data;
    ULONG64 sum = 0;
    HANDLE handle;

    if (!folder || swprintf( glob, ARRAY_SIZE(glob), L"%s\\\\*.lnk", folder ) < 0) return seed;
    if ((handle = FindFirstFileW( glob, &data )) == INVALID_HANDLE_VALUE) return seed;
    do
    {
        ULONG64 hash = 0xcbf29ce484222325ull ^ seed;
        const WCHAR *p;

        for (p = data.cFileName; *p; p++) hash = (hash ^ towlower( *p )) * 0x100000001b3ull;
        hash = (hash ^ data.ftLastWriteTime.dwLowDateTime) * 0x100000001b3ull;
        hash = (hash ^ data.ftLastWriteTime.dwHighDateTime) * 0x100000001b3ull;
        hash = (hash ^ data.nFileSizeLow) * 0x100000001b3ull;
        sum += hash;
        (*count)++;
    } while (FindNextFileW( handle, &data ));
    FindClose( handle );
    return sum + seed;
}

static LONG orbis_fold( ULONG64 value )
{
    return (LONG)(value ^ (value >> 32));
}

static ULONG64 orbis_desktop_files( unsigned int *count )
{
    *count = 0;
    return orbis_folder_signature( desktop_folder, 1, count ) ^ (orbis_folder_signature( desktop_folder_public, 2, count ) << 1);
}

/* the PS4 wineserver never completes ReadDirectoryChangesW (no inotify, no dnotify) and native
 * writers bypass it: compare the folders every 2 s */
static DWORD CALLBACK orbis_poll_desktop_folders( void *param )
{
    HWND panel = param;
    unsigned int count;

    ERR( "PWDESK poll every 2000 ms (no folder notifications on this wineserver)\\n" );
    for (;;)
    {
        ULONG64 now;

        Sleep( 2000 );
        now = orbis_desktop_files( &count );
        if (orbis_fold( now ) == InterlockedCompareExchange( &orbis_desktop_signature, 0, 0 )) continue;
        InterlockedExchange( &orbis_desktop_signature, orbis_fold( now ));
        ERR( "PWDESK poll change files=%u\\n", count );
        PostMessageW( panel, WM_ORBIS_DESKTOP_RESCAN, ORBIS_RESCAN_POLL, 0 );
    }
    return 0;
}

static void orbis_reload_launchers( HWND panel, WPARAM reason )
{
    static const char *reasons[] = { "notify", "poll", "menu" };
    unsigned int before = nb_launchers, count, i;
    HRESULT init;

    if (!launchers) return;
    init = CoInitialize( NULL );
    for (i = 0; i < nb_launchers; i++) free_launcher( launchers[i] );
    nb_launchers = 0;
    add_folder( desktop_folder );
    add_folder( desktop_folder_public );
    if (SUCCEEDED( init )) CoUninitialize();
    InterlockedExchange( &orbis_desktop_signature, orbis_fold( orbis_desktop_files( &count )));
    place_desktop_icons( panel );
    ERR( "PWDESK reload reason=%s launchers=%u->%u files=%u\\n", reason < ARRAY_SIZE(reasons) ? reasons[reason] : "?",
         before, nb_launchers, count );
}

/* Rename: a small dialog built in memory (no resource change); Enter / triangle accepts,
 * Escape / square cancels */
struct orbis_rename { WCHAR name[MAX_PATH]; };

static INT_PTR CALLBACK orbis_rename_proc( HWND dialog, UINT message, WPARAM wp, LPARAM lp )
{
    switch (message)
    {
    case WM_INITDIALOG:
        SetWindowLongPtrW( dialog, DWLP_USER, lp );
        SetDlgItemTextW( dialog, 100, ((struct orbis_rename *)lp)->name );
        SendDlgItemMessageW( dialog, 100, EM_SETSEL, 0, -1 );
        SetForegroundWindow( dialog );
        SetFocus( GetDlgItem( dialog, 100 ));
        return FALSE;
    case WM_COMMAND:
        if (LOWORD(wp) == IDOK)
        {
            struct orbis_rename *data = (struct orbis_rename *)GetWindowLongPtrW( dialog, DWLP_USER );
            GetDlgItemTextW( dialog, 100, data->name, ARRAY_SIZE(data->name) );
            EndDialog( dialog, IDOK );
            return TRUE;
        }
        if (LOWORD(wp) == IDCANCEL)
        {
            EndDialog( dialog, IDCANCEL );
            return TRUE;
        }
        break;
    }
    return FALSE;
}

static WORD *orbis_dialog_text( WORD *p, const WCHAR *text )
{
    while ((*p++ = *text++));
    return p;
}

static WORD *orbis_dialog_item( WORD *p, DWORD style, short x, short y, short cx, short cy, WORD id, WORD class,
                                const WCHAR *text )
{
    DLGITEMTEMPLATE *item = (DLGITEMTEMPLATE *)(((ULONG_PTR)p + 3) & ~(ULONG_PTR)3);

    item->style = style | WS_CHILD | WS_VISIBLE;
    item->dwExtendedStyle = 0;
    item->x = x; item->y = y; item->cx = cx; item->cy = cy;
    item->id = id;
    p = (WORD *)(item + 1);
    *p++ = 0xffff;
    *p++ = class;  /* 0x80 button, 0x81 edit, 0x82 static */
    p = orbis_dialog_text( p, text );
    *p++ = 0;
    return p;
}

static BOOL orbis_ask_name( struct orbis_rename *data )
{
    DWORD buffer[512] = {0};
    DLGTEMPLATE *dialog = (DLGTEMPLATE *)buffer;
    WORD *p;

    dialog->style = DS_MODALFRAME | DS_CENTER | DS_SETFONT | WS_POPUP | WS_CAPTION | WS_SYSMENU;
    dialog->dwExtendedStyle = WS_EX_TOPMOST;
    dialog->cdit = 4;
    dialog->cx = 220; dialog->cy = 62;
    p = (WORD *)(dialog + 1);
    *p++ = 0;  /* no menu */
    *p++ = 0;  /* standard class */
    p = orbis_dialog_text( p, L"Rename shortcut" );
    *p++ = 8;
    p = orbis_dialog_text( p, L"MS Shell Dlg" );
    p = orbis_dialog_item( p, SS_LEFT, 7, 7, 206, 9, 0xffff, 0x82, L"New name:" );
    p = orbis_dialog_item( p, ES_AUTOHSCROLL | WS_BORDER | WS_TABSTOP, 7, 18, 206, 13, 100, 0x81, L"" );
    p = orbis_dialog_item( p, BS_DEFPUSHBUTTON | WS_TABSTOP, 109, 40, 50, 14, IDOK, 0x80, L"OK" );
    orbis_dialog_item( p, BS_PUSHBUTTON | WS_TABSTOP, 163, 40, 50, 14, IDCANCEL, 0x80, L"Cancel" );
    return DialogBoxIndirectParamW( GetModuleHandleW( NULL ), dialog, NULL, orbis_rename_proc, (LPARAM)data ) == IDOK;
}

static void orbis_rename_launcher( HWND panel, const WCHAR *path, const WCHAR *title )
{
    struct orbis_rename data;
    const WCHAR *slash = wcsrchr( path, '\\\\' ), *dot = wcsrchr( path, '.' );
    WCHAR target[MAX_PATH], message[MAX_PATH + 64];
    WCHAR *start, *end;
    DWORD error = 0;

    if (!slash) return;
    if (!dot || dot < slash) dot = path + lstrlenW( path );
    lstrcpynW( data.name, title, ARRAY_SIZE(data.name) );
    if (!orbis_ask_name( &data )) return;
    for (start = data.name; *start == ' '; start++);
    for (end = start + lstrlenW( start ); end > start && (end[-1] == ' ' || end[-1] == '.'); end--);
    *end = 0;
    if (!*start || !wcscmp( start, title )) return;
    if (wcspbrk( start, L"\\\\/:*?\\"<>|" ))
    {
        MessageBoxW( NULL, L"A name cannot contain any of these characters:\\n\\\\ / : * ? \\" < > |",
                     L"Rename shortcut", MB_OK | MB_ICONWARNING | MB_TOPMOST );
        return;
    }
    if (swprintf( target, ARRAY_SIZE(target), L"%.*s\\\\%s%s", (int)(slash - path), path, start, dot ) < 0) return;
    if (!MoveFileW( path, target )) error = GetLastError();
    ERR( "PWDESK rename %s -> %s error=%lu\\n", debugstr_w(path), debugstr_w(target), error );
    if (error)
    {
        swprintf( message, ARRAY_SIZE(message), L"The shortcut could not be renamed (error %lu).", error );
        MessageBoxW( NULL, message, L"Rename shortcut", MB_OK | MB_ICONERROR | MB_TOPMOST );
    }
    PostMessageW( panel, WM_ORBIS_DESKTOP_RESCAN, ORBIS_RESCAN_MENU, 0 );
}

static void orbis_delete_launcher( HWND panel, const WCHAR *path, const WCHAR *title )
{
    WCHAR message[MAX_PATH + 128];
    DWORD error = 0;

    swprintf( message, ARRAY_SIZE(message), L"Delete the shortcut \\"%s\\"?\\n\\nOnly the shortcut is deleted; "
              L"the program it opens stays installed.", title );
    if (MessageBoxW( NULL, message, L"Delete shortcut", MB_YESNO | MB_ICONWARNING | MB_DEFBUTTON2 | MB_TOPMOST ) != IDYES)
        return;
    if (!DeleteFileW( path )) error = GetLastError();
    ERR( "PWDESK delete %s error=%lu\\n", debugstr_w(path), error );
    if (error)
    {
        swprintf( message, ARRAY_SIZE(message), L"The shortcut could not be deleted (error %lu).", error );
        MessageBoxW( NULL, message, L"Delete shortcut", MB_OK | MB_ICONERROR | MB_TOPMOST );
    }
    PostMessageW( panel, WM_ORBIS_DESKTOP_RESCAN, ORBIS_RESCAN_MENU, 0 );
}

static void orbis_launcher_properties( const WCHAR *path, const WCHAR *title )
{
    WCHAR target[MAX_PATH] = L"", arguments[MAX_PATH] = L"", folder[MAX_PATH] = L"", message[4 * MAX_PATH + 128];
    HRESULT init = CoInitialize( NULL );
    IShellLinkW *link = load_shelllink( path );

    if (link)
    {
        IShellLinkW_GetPath( link, target, ARRAY_SIZE(target), NULL, SLGP_RAWPATH );
        IShellLinkW_GetArguments( link, arguments, ARRAY_SIZE(arguments) );
        IShellLinkW_GetWorkingDirectory( link, folder, ARRAY_SIZE(folder) );
        IShellLinkW_Release( link );
        swprintf( message, ARRAY_SIZE(message), L"Name: %s\\nShortcut file: %s\\n\\nTarget: %s\\nArguments: %s\\nStart in: %s",
                  title, path, target[0] ? target : L"(none)", arguments[0] ? arguments : L"(none)",
                  folder[0] ? folder : L"(none)" );
    }
    else swprintf( message, ARRAY_SIZE(message), L"Name: %s\\nShortcut file: %s\\n\\nThe shortcut could not be read.",
                   title, path );
    if (SUCCEEDED( init )) CoUninitialize();
    MessageBoxW( NULL, message, L"Shortcut properties", MB_OK | MB_ICONINFORMATION | MB_TOPMOST );
}

/* WFM opens the folder given as its first argument */
static void orbis_open_folder( const WCHAR *folder, int length )
{
    WCHAR parameters[MAX_PATH + 2];

    if (swprintf( parameters, ARRAY_SIZE(parameters), L"\\"%.*s\\"", length, folder ) < 0) return;
    ShellExecuteW( NULL, L"open", L"wfm.exe", parameters, NULL, SW_SHOWNORMAL );
}

/* point in the launcher window's client coordinates; outside a launcher, the desktop items */
static void orbis_desktop_menu( HWND panel, int x, int y )
{
    const struct launcher *launcher = panel ? launcher_from_point( x, y ) : NULL;
    WCHAR *path = NULL, *title = NULL;
    HMENU menu = CreatePopupMenu();
    POINT screen = { x, y };
    UINT command;

    if (!menu || !panel) goto done;
    if (launcher)
    {
        if (!(path = wcsdup( launcher->path )) || !(title = wcsdup( launcher->title ))) goto done;
        AppendMenuW( menu, MF_STRING, ORBIS_MENU_OPEN, L"&Open" );
        AppendMenuW( menu, MF_STRING, ORBIS_MENU_LOCATION, L"Open file &location" );
        AppendMenuW( menu, MF_SEPARATOR, 0, NULL );
        AppendMenuW( menu, MF_STRING, ORBIS_MENU_RENAME, L"Rena&me" );
        AppendMenuW( menu, MF_STRING, ORBIS_MENU_DELETE, L"&Delete" );
        AppendMenuW( menu, MF_SEPARATOR, 0, NULL );
        AppendMenuW( menu, MF_STRING, ORBIS_MENU_PROPERTIES, L"P&roperties" );
        SetMenuDefaultItem( menu, ORBIS_MENU_OPEN, FALSE );
    }
    else
    {
        AppendMenuW( menu, MF_STRING, ORBIS_MENU_REFRESH, L"R&efresh" );
        if (desktop_folder) AppendMenuW( menu, MF_STRING, ORBIS_MENU_DESKTOP_FOLDER, L"Open &Desktop folder" );
    }
    ClientToScreen( panel, &screen );
    SetForegroundWindow( panel );
    command = TrackPopupMenuEx( menu, TPM_RETURNCMD | TPM_RIGHTBUTTON | TPM_LEFTALIGN | TPM_TOPALIGN,
                                screen.x, screen.y, panel, NULL );
    PostMessageW( panel, WM_NULL, 0, 0 );
    ERR( "PWDESK menu item=%s command=%u\\n", debugstr_w(path), command );
    switch (command)
    {
    case ORBIS_MENU_OPEN:
        ShellExecuteW( NULL, L"open", path, NULL, NULL, SW_SHOWNORMAL );
        break;
    case ORBIS_MENU_LOCATION:
        orbis_open_folder( path, wcsrchr( path, '\\\\' ) ? (int)(wcsrchr( path, '\\\\' ) - path) : lstrlenW( path ) );
        break;
    case ORBIS_MENU_RENAME:
        orbis_rename_launcher( panel, path, title );
        break;
    case ORBIS_MENU_DELETE:
        orbis_delete_launcher( panel, path, title );
        break;
    case ORBIS_MENU_PROPERTIES:
        orbis_launcher_properties( path, title );
        break;
    case ORBIS_MENU_REFRESH:
        PostMessageW( panel, WM_ORBIS_DESKTOP_RESCAN, ORBIS_RESCAN_MENU, 0 );
        break;
    case ORBIS_MENU_DESKTOP_FOLDER:
        orbis_open_folder( desktop_folder, lstrlenW( desktop_folder ) );
        break;
    }
done:
    if (menu) DestroyMenu( menu );
    free( path );
    free( title );
}

static LRESULT WINAPI desktop_icons_wnd_proc( HWND hwnd, UINT message, WPARAM wp, LPARAM lp )
{''','Desktop folder poll, reload on the launcher thread, right-click menu (W290).')
revise('desktop.c','''    case WM_LBUTTONDBLCLK:
        {
            const struct launcher *launcher''','''    case WM_ORBIS_DESKTOP_RESCAN:  /* W290 */
        orbis_reload_launchers( hwnd, wp );
        return 0;

    case WM_RBUTTONUP:  /* W290 */
        orbis_desktop_menu( hwnd, (short)LOWORD(lp), (short)HIWORD(lp) );
        return 0;

    case WM_LBUTTONDBLCLK:
        {
            const struct launcher *launcher''','Launcher window: reload and right-click menu (W290).')
revise('desktop.c','''    case WM_LBUTTONDBLCLK:
        if (!using_root)''','''    case WM_RBUTTONUP:  /* W290: empty desktop outside the launcher window; same coordinates */
        if (!using_root && orbis_desktop_panel)
        {
            POINT point = { (short)LOWORD(lp), (short)HIWORD(lp) };
            MapWindowPoints( hwnd, orbis_desktop_panel, &point, 1 );
            orbis_desktop_menu( orbis_desktop_panel, point.x, point.y );
        }
        return 0;

    case WM_LBUTTONDBLCLK:
        if (!using_root)''','Desktop window: right-click menu on empty desktop (W290).')
revise('desktop.c','''            if (panel) place_desktop_icons( panel );''','''            if (panel)
            {
                unsigned int files;
                HANDLE poll;

                place_desktop_icons( panel );
                orbis_desktop_panel = panel;  /* W290 */
                InterlockedExchange( &orbis_desktop_signature, orbis_fold( orbis_desktop_files( &files )));
                if ((poll = CreateThread( NULL, 0, orbis_poll_desktop_folders, panel, 0, NULL ))) CloseHandle( poll );
                else ERR( "PWDESK poll thread error=%lu\\n", GetLastError() );
            }''','Start the Desktop folder poll with the launcher window (W290).')

# W292 (user): the desktop launchers go in columns, top to bottom, and a new column starts at the
# right when the height above the taskbar is full; "File Manager" first, "Open Steam Client" second,
# the rest alphabetically (case-insensitive). The order is kept after every reload (2 s poll,
# rename, delete); a deleted one simply isn't there. One PWDESK order line per placement.
revise('desktop.c','''static RECT get_icon_rect( unsigned int index )
{
    RECT rect;
    unsigned int row = index / launchers_per_row;
    unsigned int col = index % launchers_per_row;''','''static unsigned int launchers_per_column = 1;  /* OrbisDesk W292: the grid fills columns */

static RECT get_icon_rect( unsigned int index )
{
    RECT rect;
    unsigned int row = index % launchers_per_column;
    unsigned int col = index / launchers_per_column;''','Icon rectangle: column-major grid (W292).')
revise('desktop.c','''static RECT get_title_rect( unsigned int index )
{
    RECT rect;
    unsigned int row = index / launchers_per_row;
    unsigned int col = index % launchers_per_row;''','''static RECT get_title_rect( unsigned int index )
{
    RECT rect;
    unsigned int row = index % launchers_per_column;
    unsigned int col = index / launchers_per_column;''','Title rectangle: column-major grid (W292).')
revise('desktop.c','''    index = x / launcher_size + (y / launcher_size) * launchers_per_row;''','''    if (x < 0 || y < 0 || (unsigned int)(y / launcher_size) >= launchers_per_column) return NULL;
    index = (x / launcher_size) * launchers_per_column + y / launcher_size;  /* W292: columns */''',
       'Hit test: column-major grid (W292).')
revise('desktop.c','''/* the launcher grid: from the top-left corner, as many rows as the launchers need */
static void place_desktop_icons( HWND panel )
{
    unsigned int count = nb_launchers, rows, columns;

    if (!count || !launchers_per_row)
    {
        ShowWindow( panel, SW_HIDE );
        return;
    }
    rows = (count + launchers_per_row - 1) / launchers_per_row;
    columns = rows > 1 ? launchers_per_row : count;
    SetWindowPos( panel, HWND_BOTTOM, 0, 0, columns * launcher_size, rows * launcher_size,
                  SWP_NOACTIVATE | SWP_SHOWWINDOW );
    InvalidateRect( panel, NULL, TRUE );
}''','''/* W292: "File Manager" first, "Open Steam Client" second, then alphabetical (case-insensitive) */
static int orbis_launcher_rank( const struct launcher *launcher )
{
    if (!wcsicmp( launcher->title, L"File Manager" )) return 0;
    if (!wcsicmp( launcher->title, L"Open Steam Client" )) return 1;
    return 2;
}

static int __cdecl orbis_launcher_compare( const void *a, const void *b )
{
    const struct launcher *first = *(struct launcher *const *)a, *second = *(struct launcher *const *)b;
    int order = orbis_launcher_rank( first ) - orbis_launcher_rank( second );

    if (!order) order = wcsicmp( first->title, second->title );
    if (!order) order = wcsicmp( first->path, second->path );
    return order;
}

static void orbis_sort_launchers( unsigned int columns )
{
    char line[800], title[200];
    unsigned int i, used = 0;

    if (nb_launchers > 1) qsort( launchers, nb_launchers, sizeof(launchers[0]), orbis_launcher_compare );
    line[0] = 0;
    for (i = 0; i < nb_launchers; i++)
    {
        if (!WideCharToMultiByte( CP_UTF8, 0, launchers[i]->title, -1, title, sizeof(title), NULL, NULL ))
            strcpy( title, "?" );
        if (used + strlen( title ) + 8 >= sizeof(line))
        {
            strcpy( line + used, " ..." );
            break;
        }
        used += sprintf( line + used, "%s%s", i ? " | " : "", title );
    }
    ERR( "PWDESK order count=%u columns=%u per_column=%u: %s\\n", nb_launchers, columns, launchers_per_column, line );
}

/* launchers per column: the height above the taskbar (Shell_TrayWnd is created before the
 * launchers), else the work area, else the screen */
static unsigned int orbis_desktop_rows(void)
{
    int height = GetSystemMetrics( SM_CYSCREEN );
    HWND tray = FindWindowW( L"Shell_TrayWnd", NULL );
    RECT rect;

    if (tray && IsWindowVisible( tray ) && GetWindowRect( tray, &rect ) && rect.top > 0 && rect.top < height)
        height = rect.top;
    else if (SystemParametersInfoW( SPI_GETWORKAREA, 0, &rect, 0 ) && rect.bottom > 0 && rect.bottom < height)
        height = rect.bottom;
    return launcher_size > 0 && height >= launcher_size ? height / launcher_size : 1;
}

/* the launcher grid (W292): from the top-left corner, filling columns top to bottom */
static void place_desktop_icons( HWND panel )
{
    unsigned int count = nb_launchers, rows, columns;

    if (!count || launcher_size <= 0)
    {
        ShowWindow( panel, SW_HIDE );
        ERR( "PWDESK order count=0\\n" );
        return;
    }
    launchers_per_column = orbis_desktop_rows();
    columns = (count + launchers_per_column - 1) / launchers_per_column;
    rows = columns > 1 ? launchers_per_column : count;
    orbis_sort_launchers( columns );
    SetWindowPos( panel, HWND_BOTTOM, 0, 0, columns * launcher_size, rows * launcher_size,
                  SWP_NOACTIVATE | SWP_SHOWWINDOW );
    InvalidateRect( panel, NULL, TRUE );
}''','Launcher window: columns sized to the height above the taskbar, fixed order, order log (W292).')

# W292 (user: change the desktop wallpaper, with a few more to choose from): the empty-desktop menu
# gets a Wallpaper submenu with the BMPs in C:\windows (tools/make-wallpaper-set.py draws three more).
# The choice goes through SPI_SETDESKWALLPAPER (registry, user32's bitmap, ps5drv's layer) and is
# mirrored to HKCU\Software\OrbisDesk\Desktop, which uploads keep; at start the mirror is restored
# when an upload put the build's default back.
revise('desktop.c','''/* point in the launcher window's client coordinates; outside a launcher, the desktop items */''','''/* W292: wallpapers */
#define ORBIS_MENU_WALLPAPER 100
#define ORBIS_MAX_WALLPAPERS 32
#define ORBIS_DEFAULT_WALLPAPER L"C:\\\\windows\\\\orbis-hills.bmp"
#define ORBIS_DESKTOP_KEY L"Software\\\\OrbisDesk\\\\Desktop"
static WCHAR orbis_wallpapers[ORBIS_MAX_WALLPAPERS][MAX_PATH];
static unsigned int orbis_wallpaper_count;

static int __cdecl orbis_wallpaper_compare( const void *a, const void *b )
{
    return wcsicmp( a, b );
}

/* "C:\\windows\\orbis-dusk.bmp" -> "Dusk" */
static void orbis_wallpaper_name( const WCHAR *path, WCHAR *name, unsigned int size )
{
    const WCHAR *start = wcsrchr( path, '\\\\' ), *dot;
    unsigned int length, i;

    start = start ? start + 1 : path;
    if (!wcsnicmp( start, L"orbis-", 6 ) && start[6]) start += 6;
    dot = wcsrchr( start, '.' );
    length = dot ? dot - start : lstrlenW( start );
    if (length >= size) length = size - 1;
    for (i = 0; i < length; i++) name[i] = start[i] == '-' || start[i] == '_' ? ' ' : start[i];
    name[length] = 0;
    if (length) name[0] = towupper( name[0] );
}

static HMENU orbis_wallpaper_menu(void)
{
    WCHAR folder[MAX_PATH], glob[MAX_PATH], current[MAX_PATH] = L"", name[64];
    WIN32_FIND_DATAW data;
    HANDLE handle;
    HMENU menu;
    unsigned int i;

    orbis_wallpaper_count = 0;
    if (!GetWindowsDirectoryW( folder, ARRAY_SIZE(folder) ) || !(menu = CreatePopupMenu())) return NULL;
    SystemParametersInfoW( SPI_GETDESKWALLPAPER, ARRAY_SIZE(current), current, 0 );
    if (swprintf( glob, ARRAY_SIZE(glob), L"%s\\\\*.bmp", folder ) > 0 &&
        (handle = FindFirstFileW( glob, &data )) != INVALID_HANDLE_VALUE)
    {
        do
        {
            if (data.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) continue;
            if (swprintf( orbis_wallpapers[orbis_wallpaper_count], MAX_PATH, L"%s\\\\%s", folder, data.cFileName ) > 0)
                orbis_wallpaper_count++;
        } while (orbis_wallpaper_count < ORBIS_MAX_WALLPAPERS && FindNextFileW( handle, &data ));
        FindClose( handle );
    }
    qsort( orbis_wallpapers, orbis_wallpaper_count, sizeof(orbis_wallpapers[0]), orbis_wallpaper_compare );
    for (i = 0; i < orbis_wallpaper_count; i++)
    {
        orbis_wallpaper_name( orbis_wallpapers[i], name, ARRAY_SIZE(name) );
        AppendMenuW( menu, MF_STRING | (wcsicmp( orbis_wallpapers[i], current ) ? 0 : MF_CHECKED),
                     ORBIS_MENU_WALLPAPER + i, name );
    }
    if (!orbis_wallpaper_count) AppendMenuW( menu, MF_STRING | MF_GRAYED, 0, L"(no wallpapers)" );
    ERR( "PWDESK wallpaper menu count=%u current=%s\\n", orbis_wallpaper_count, debugstr_w(current) );
    return menu;
}

/* the choice, where uploads keep it (tools/upload-hardware.py CONSOLE_OWNED) */
static void orbis_remember_wallpaper( const WCHAR *path )
{
    HKEY key;

    if (RegCreateKeyExW( HKEY_CURRENT_USER, ORBIS_DESKTOP_KEY, 0, NULL, 0, KEY_SET_VALUE, NULL, &key, NULL )) return;
    RegSetValueExW( key, L"Wallpaper", 0, REG_SZ, (const BYTE *)path, (lstrlenW( path ) + 1) * sizeof(WCHAR) );
    RegCloseKey( key );
}

static void orbis_set_wallpaper( HWND panel, const WCHAR *path )
{
    DWORD error = 0;

    if (!SystemParametersInfoW( SPI_SETDESKWALLPAPER, 0, (void *)path, SPIF_UPDATEINIFILE )) error = GetLastError();
    else orbis_remember_wallpaper( path );
    if (panel) InvalidateRect( panel, NULL, TRUE );
    ERR( "PWDESK wallpaper set %s error=%lu\\n", debugstr_w(path), error );
}

/* WM_SETTINGCHANGE: any program's SPI_SETDESKWALLPAPER; the icon window paints the wallpaper too */
static void orbis_wallpaper_changed(void)
{
    WCHAR current[MAX_PATH] = L"";

    SystemParametersInfoW( SPI_GETDESKWALLPAPER, ARRAY_SIZE(current), current, 0 );
    orbis_remember_wallpaper( current );
    if (orbis_desktop_panel) InvalidateRect( orbis_desktop_panel, NULL, TRUE );
    ERR( "PWDESK wallpaper changed %s\\n", debugstr_w(current) );
}

/* at start: an upload writes the build's default back into Control Panel; the mirror has the choice */
static void orbis_restore_wallpaper(void)
{
    WCHAR saved[MAX_PATH] = L"", current[MAX_PATH] = L"";
    DWORD size = sizeof(saved);
    BOOL restore;

    SystemParametersInfoW( SPI_GETDESKWALLPAPER, ARRAY_SIZE(current), current, 0 );
    if (RegGetValueW( HKEY_CURRENT_USER, ORBIS_DESKTOP_KEY, L"Wallpaper", RRF_RT_REG_SZ, NULL, saved, &size )) saved[0] = 0;
    restore = saved[0] && wcsicmp( saved, current ) && !wcsicmp( current, ORBIS_DEFAULT_WALLPAPER ) &&
              GetFileAttributesW( saved ) != INVALID_FILE_ATTRIBUTES;
    if (restore) SystemParametersInfoW( SPI_SETDESKWALLPAPER, 0, saved, SPIF_UPDATEINIFILE );
    else orbis_remember_wallpaper( current );
    ERR( "PWDESK wallpaper start current=%s saved=%s restored=%d\\n", debugstr_w(current), debugstr_w(saved), restore );
}

/* point in the launcher window's client coordinates; outside a launcher, the desktop items */''','Wallpaper list, choice, mirror and start restore (W292).')
revise('desktop.c','''        if (desktop_folder) AppendMenuW( menu, MF_STRING, ORBIS_MENU_DESKTOP_FOLDER, L"Open &Desktop folder" );''','''        if (desktop_folder) AppendMenuW( menu, MF_STRING, ORBIS_MENU_DESKTOP_FOLDER, L"Open &Desktop folder" );
        {
            HMENU wallpapers = orbis_wallpaper_menu();  /* W292 */
            if (wallpapers)
            {
                AppendMenuW( menu, MF_SEPARATOR, 0, NULL );
                AppendMenuW( menu, MF_POPUP, (UINT_PTR)wallpapers, L"&Wallpaper" );
            }
        }''','Empty-desktop menu: Wallpaper submenu (W292).')
revise('desktop.c','''    case ORBIS_MENU_DESKTOP_FOLDER:
        orbis_open_folder( desktop_folder, lstrlenW( desktop_folder ) );
        break;
    }''','''    case ORBIS_MENU_DESKTOP_FOLDER:
        orbis_open_folder( desktop_folder, lstrlenW( desktop_folder ) );
        break;
    default:  /* W292 */
        if (command >= ORBIS_MENU_WALLPAPER && command < ORBIS_MENU_WALLPAPER + orbis_wallpaper_count)
            orbis_set_wallpaper( panel, orbis_wallpapers[command - ORBIS_MENU_WALLPAPER] );
        break;
    }''','Wallpaper chosen from the menu (W292).')
revise('desktop.c','''        if (wp == SPI_SETDESKWALLPAPER)
            SystemParametersInfoW( SPI_SETDESKWALLPAPER, 0, NULL, FALSE );
        return 0;''','''        if (wp == SPI_SETDESKWALLPAPER)
        {
            SystemParametersInfoW( SPI_SETDESKWALLPAPER, 0, NULL, FALSE );
            if (!using_root) orbis_wallpaper_changed();  /* W292 */
        }
        return 0;''','A wallpaper change from another program: mirror it and repaint the icons (W292).')
revise('desktop.c','''        SystemParametersInfoW( SPI_SETDESKWALLPAPER, 0, NULL, FALSE );
        ClipCursor( NULL );''','''        if (!using_root) orbis_restore_wallpaper();  /* W292 */
        SystemParametersInfoW( SPI_SETDESKWALLPAPER, 0, NULL, FALSE );
        ClipCursor( NULL );''','The chosen wallpaper survives an upload (W292).')

# W292 (user): "Reset as Root" (in NORMAL) or "Reset as Sandbox" (in ROOT) in Start, always between
# "Open Steam Client" and "Exit desktop": the title relaunches straight into the other mode, without the
# NORMAL/ROOT screen (native/wine_hardware.c pw_hw_reset_mode, asked through native/hw_pad.c like
# steam-open.exe).
revise('startmenu.c','#define MENU_ID_STEAM 3\n','''#define MENU_ID_STEAM 3
#define MENU_ID_ROOT 4

/* W292: the title's native side (native/hw_pad.c pw_wine_pad_profile) through xinput1_3's Unix library,
 * call 3, as C:\\\\orbis\\\\steam-open.exe asks it; the 260-byte request is answered in place */
static BOOL orbis_native_call( const char *request, char *reply, size_t size )
{
    typedef LONG (WINAPI *query_fn)( HANDLE, LPCVOID, ULONG, PVOID, SIZE_T, SIZE_T * );
    typedef LONG (WINAPI *dispatch_fn)( UINT64, unsigned int, void * );
    struct { USHORT Length, MaximumLength; WCHAR *Buffer; } name = { 18, 20, (WCHAR *)L"xinput1_3" };
    struct { char exe[260]; UINT32 load; } params;
    HMODULE ntdll = GetModuleHandleW( L"ntdll.dll" );
    query_fn query = ntdll ? (query_fn)GetProcAddress( ntdll, "NtQueryVirtualMemory" ) : NULL;
    void **dispatcher = ntdll ? (void **)GetProcAddress( ntdll, "__wine_unix_call_dispatcher" ) : NULL;
    UINT64 library[2] = {0};

    if (!query || !dispatcher || !*dispatcher) return FALSE;
    if (query( GetCurrentProcess(), &name, 1002 /* MemoryWineLoadUnixLibByName */, library, sizeof(library), NULL ))
        return FALSE;
    ZeroMemory( &params, sizeof(params) );
    lstrcpynA( params.exe, request, sizeof(params.exe) );
    if (((dispatch_fn)*dispatcher)( library[1], 3, &params )) return FALSE;
    params.exe[sizeof(params.exe) - 1] = 0;
    lstrcpynA( reply, params.exe, size );
    return TRUE;
}

/* 1 when OrbisDesk started in ROOT, 0 in NORMAL (the sandbox), -1 when the native side does not say */
static int orbis_root_mode(void)
{
    static int mode = -2;
    char reply[64] = "";

    if (mode != -2) return mode;
    if (!orbis_native_call( "<root-mode>", reply, sizeof(reply) )) mode = -1;
    else if (!lstrcmpA( reply, "root" )) mode = 1;
    else if (!lstrcmpA( reply, "normal" )) mode = 0;
    else mode = -1;
    ERR( "PWROOT explorer mode=%d reply=%s\\n", mode, debugstr_a(reply) );
    return mode;
}

static void orbis_reset_mode( HWND hwnd )
{
    int to_root = !orbis_root_mode();
    const WCHAR *title = to_root ? L"Reset as Root" : L"Reset as Sandbox";
    char reply[260] = "";
    WCHAR text[400], detail[260];
    LONG user, machine;

    if (MessageBoxW( hwnd, to_root ?
                     L"OrbisDesk restarts now in ROOT mode (GoldHEN jailbreak, USB disks as D: to K:), "
                     L"without the NORMAL/ROOT screen.\\n\\nOpen programs close without saving. Continue?" :
                     L"OrbisDesk restarts now in NORMAL mode (the app sandbox, no USB disks), "
                     L"without the NORMAL/ROOT screen.\\n\\nOpen programs close without saving. Continue?",
                     title, MB_YESNO | MB_ICONWARNING | MB_DEFBUTTON2 | MB_TOPMOST ) != IDYES)
        return;
    user = RegFlushKey( HKEY_CURRENT_USER );
    machine = RegFlushKey( HKEY_LOCAL_MACHINE );
    ERR( "PWROOT explorer reset to=%s flush user=%ld machine=%ld\\n", to_root ? "root" : "normal", user, machine );
    if (!orbis_native_call( to_root ? "<reset-root>" : "<reset-sandbox>", reply, sizeof(reply) ))
        lstrcpynA( reply, "error: OrbisDesk's native side could not be reached", sizeof(reply) );
    ERR( "PWROOT explorer reset reply=%s\\n", debugstr_a(reply) );
    if (!MultiByteToWideChar( CP_UTF8, 0, reply, -1, detail, ARRAY_SIZE(detail) )) detail[0] = 0;
    lstrcpynW( text, to_root ? L"OrbisDesk could not restart in ROOT mode.\\n\\n" :
               L"OrbisDesk could not restart in NORMAL mode.\\n\\n", ARRAY_SIZE(text) );
    lstrcatW( text, detail );
    MessageBoxW( hwnd, text, title, MB_OK | MB_ICONERROR | MB_TOPMOST );
}
''','Reset item: native mode query and relaunch request (W292).')
revise('startmenu.c','''    mii.wID = MENU_ID_STEAM;
    InsertMenuItemW(root_menu.menuhandle, -1, TRUE, &mii);
''','''    mii.wID = MENU_ID_STEAM;
    InsertMenuItemW(root_menu.menuhandle, -1, TRUE, &mii);

    if (orbis_root_mode() >= 0)  /* W292: the other mode; not offered when the mode is unknown */
    {
        mii.fMask = MIIM_STRING|MIIM_ID|MIIM_BITMAP;
        mii.dwTypeData = (WCHAR *)(orbis_root_mode() ? L"Reset as Sandbox" : L"Reset as Root");
        mii.hbmpItem = HBMMENU_CALLBACK;
        mii.wID = MENU_ID_ROOT;
        InsertMenuItemW(root_menu.menuhandle, -1, TRUE, &mii);
    }
''','Reset as Root / Sandbox item between Steam and Exit (W292).')
revise('startmenu.c','''            else if (mii.wID == MENU_ID_STEAM)
                ShellExecuteW(NULL, L"open", L"C:\\\\orbis\\\\steam-open.exe", NULL, L"C:\\\\orbis", SW_SHOWNORMAL);''','''            else if (mii.wID == MENU_ID_STEAM)
                ShellExecuteW(NULL, L"open", L"C:\\\\orbis\\\\steam-open.exe", NULL, L"C:\\\\orbis", SW_SHOWNORMAL);
            else if (mii.wID == MENU_ID_ROOT)  /* W292 */
                orbis_reset_mode(hwnd);''','Reset item command (W292).')
revise('startmenu.c','''    else if (dis->itemID == MENU_ID_EXIT)
    {''','''    else if (dis->itemID == MENU_ID_ROOT && orbis_root_mode())
    {
        /* W292, Reset as Sandbox: a green shield with a white bar */
        POINT shield[5] = { { x + 2, y + 2 }, { x + size - 2, y + 2 }, { x + size - 2, y + size / 2 },
                            { middle, y + size - 1 }, { x + 2, y + size / 2 } };
        HBRUSH fill = CreateSolidBrush( RGB( 0x30, 0xb0, 0x50 )), old_brush = SelectObject( dis->hDC, fill );
        HPEN old_pen = SelectObject( dis->hDC, GetStockObject( NULL_PEN ));
        RECT bar;

        Polygon( dis->hDC, shield, 5 );
        SetRect( &bar, middle - 1, y + 4, middle + 1, y + size - 4 );
        FillRect( dis->hDC, &bar, GetStockObject( WHITE_BRUSH ));
        SelectObject( dis->hDC, old_brush );
        SelectObject( dis->hDC, old_pen );
        DeleteObject( fill );
    }
    else if (dis->itemID == MENU_ID_ROOT)
    {
        /* W292, Reset as Root: an amber restart arrow, an open ring with an arrowhead at its upper end */
        HPEN pen = CreatePen( PS_SOLID, 2, RGB( 0xf0, 0xa0, 0x20 )), old_pen = SelectObject( dis->hDC, pen );
        HBRUSH fill = CreateSolidBrush( RGB( 0xf0, 0xa0, 0x20 ));
        HBRUSH old_brush = SelectObject( dis->hDC, GetStockObject( NULL_BRUSH ));
        POINT head[3] = { { x + size - 3, y + 1 }, { x + size - 2, y + 7 }, { x + size - 8, y + 5 } };

        /* counter-clockwise from the upper right round to the right: a gap at the top right */
        Arc( dis->hDC, x + 2, y + 2, x + size - 2, y + size - 2, x + size - 3, y + 4, x + size - 1, y + size / 2 );
        SelectObject( dis->hDC, GetStockObject( NULL_PEN ));
        SelectObject( dis->hDC, fill );
        Polygon( dis->hDC, head, 3 );
        SelectObject( dis->hDC, old_brush );
        SelectObject( dis->hDC, old_pen );
        DeleteObject( fill );
        DeleteObject( pen );
    }
    else if (dis->itemID == MENU_ID_EXIT)
    {''','Reset as Root / Sandbox glyphs (W292).')

# W179: the taskbar, Start and the window buttons from the visual style when it has XP's shell
# classes (tools/build-msstyles-hw.py: Luna's blue taskbar and green Start, Noir's black and orange);
# Aero has none, and then, as with no style, the classic drawing stays. uxtheme is resolved at run
# time; a style chosen later reaches the tray window as WM_THEMECHANGED.
revise('systray.c','#include <commctrl.h>\n','#include <commctrl.h>\n#include <uxtheme.h>\n','HTHEME for the taskbar style.')
revise('systray.c','''static void paint_taskbar_button( const DRAWITEMSTRUCT *dis )
{''','''/* vssym32.h: TBP_BACKGROUNDBOTTOM, BP_PUSHBUTTON and TP_BUTTON (part 1), their states, TMT_* */
enum { TASKBAR_PART = 1, BUTTON_NORMAL = 1, BUTTON_PRESSED = 3, TOOLBAR_CHECKED = 5,
       PROPERTY_FILLCOLOR = 3802, PROPERTY_TEXTCOLOR = 3803 };
static HTHEME (WINAPI *pOpenThemeData)( HWND, LPCWSTR );
static HRESULT (WINAPI *pCloseThemeData)( HTHEME );
static HRESULT (WINAPI *pDrawThemeBackground)( HTHEME, HDC, int, int, const RECT *, const RECT * );
static HRESULT (WINAPI *pGetThemeColor)( HTHEME, int, int, int, COLORREF * );
static HRESULT (WINAPI *pSetWindowTheme)( HWND, LPCWSTR, LPCWSTR );
static HTHEME taskbar_theme;
static HBRUSH taskbar_brush;  /* behind the clock */
static COLORREF taskbar_fill, taskbar_text;

static void load_taskbar_theme(void)
{
    static HMODULE uxtheme;

    if (taskbar_theme) pCloseThemeData( taskbar_theme );
    taskbar_theme = 0;
    if (taskbar_brush) DeleteObject( taskbar_brush );
    taskbar_brush = 0;
    if (!uxtheme)
    {
        if (!(uxtheme = LoadLibraryW( L"uxtheme.dll" ))) return;
        pOpenThemeData = (void *)GetProcAddress( uxtheme, "OpenThemeData" );
        pCloseThemeData = (void *)GetProcAddress( uxtheme, "CloseThemeData" );
        pDrawThemeBackground = (void *)GetProcAddress( uxtheme, "DrawThemeBackground" );
        pGetThemeColor = (void *)GetProcAddress( uxtheme, "GetThemeColor" );
        pSetWindowTheme = (void *)GetProcAddress( uxtheme, "SetWindowTheme" );
    }
    if (!pOpenThemeData || !pCloseThemeData || !pDrawThemeBackground || !pGetThemeColor || !pSetWindowTheme) return;
    if (!(taskbar_theme = pOpenThemeData( tray_window, L"Taskbar" ))) return;
    if (FAILED(pGetThemeColor( taskbar_theme, TASKBAR_PART, 0, PROPERTY_FILLCOLOR, &taskbar_fill )))
        taskbar_fill = GetSysColor( COLOR_3DFACE );
    if (FAILED(pGetThemeColor( taskbar_theme, TASKBAR_PART, 0, PROPERTY_TEXTCOLOR, &taskbar_text )))
        taskbar_text = GetSysColor( COLOR_BTNTEXT );
    taskbar_brush = CreateSolidBrush( taskbar_fill );
}

/* a button's background from the style: Start as "Start::Button", a window as "TaskBand::Toolbar";
 * FALSE when the style has no taskbar, and the classic drawing follows */
static BOOL paint_themed_button( const DRAWITEMSTRUCT *dis, const struct taskbar_button *win, RECT *rect,
                                 COLORREF *text )
{
    BOOL pressed = (dis->itemState & ODS_SELECTED) != 0;
    int state;
    HTHEME theme;

    if (!taskbar_theme) return FALSE;
    if (!GetPropW( dis->hwndItem, L"OrbisTaskbarTheme" ))
    {
        /* once per button: SetWindowTheme sends the button WM_THEMECHANGED, which repaints it */
        SetPropW( dis->hwndItem, L"OrbisTaskbarTheme", (HANDLE)1 );
        pSetWindowTheme( dis->hwndItem, win->hwnd ? L"TaskBand" : L"Start", NULL );
    }
    if (!(theme = pOpenThemeData( dis->hwndItem, win->hwnd ? L"Toolbar" : L"Button" ))) return FALSE;
    state = pressed ? BUTTON_PRESSED : (win->hwnd && win->active) ? TOOLBAR_CHECKED : BUTTON_NORMAL;
    pDrawThemeBackground( theme, dis->hDC, 1, state, rect, NULL );
    if (FAILED(pGetThemeColor( theme, 1, state, PROPERTY_TEXTCOLOR, text ))) *text = taskbar_text;
    pCloseThemeData( theme );
    return TRUE;
}

/* a window's button on a styled taskbar: its small icon and title, without messages to its thread */
static void paint_themed_window_button( HDC hdc, const RECT *rect, const struct taskbar_button *win, COLORREF colour )
{
    int size = GetSystemMetrics( SM_CXSMICON );
    HICON icon = (HICON)GetClassLongPtrW( win->hwnd, GCLP_HICONSM );
    HGDIOBJ old_font = SelectObject( hdc, GetStockObject( DEFAULT_GUI_FONT ));
    WCHAR title[256];
    RECT text = *rect;

    if (!icon) icon = (HICON)GetClassLongPtrW( win->hwnd, GCLP_HICON );
    if (icon) DrawIconEx( hdc, text.left + 4, (text.top + text.bottom - size) / 2, icon, size, size, 0, NULL, DI_NORMAL );
    text.left += size + 8;
    text.right -= 4;
    InternalGetWindowText( win->hwnd, title, ARRAY_SIZE(title) );
    SetBkMode( hdc, TRANSPARENT );
    SetTextColor( hdc, colour );
    DrawTextW( hdc, title, -1, &text, DT_SINGLELINE | DT_VCENTER | DT_END_ELLIPSIS | DT_NOPREFIX );
    SelectObject( hdc, old_font );
}

/* Start's label on a styled taskbar: bold italic, as XP's */
static void paint_themed_start_label( HDC hdc, RECT *rect, const WCHAR *label, COLORREF colour )
{
    LOGFONTW font;
    HFONT bold;
    HGDIOBJ old_font;

    GetObjectW( GetStockObject( DEFAULT_GUI_FONT ), sizeof(font), &font );
    font.lfWeight = FW_BOLD;
    font.lfItalic = TRUE;
    font.lfHeight = font.lfHeight < 0 ? font.lfHeight - 2 : font.lfHeight + 2;
    bold = CreateFontIndirectW( &font );
    old_font = SelectObject( hdc, bold );
    SetBkMode( hdc, TRANSPARENT );
    SetTextColor( hdc, colour );
    DrawTextW( hdc, label, -1, rect, DT_SINGLELINE | DT_VCENTER | DT_NOPREFIX );
    SelectObject( hdc, old_font );
    DeleteObject( bold );
}

static void paint_taskbar_button( const DRAWITEMSTRUCT *dis )
{''','Taskbar style: loading and drawing.')
revise('systray.c','''    UINT flags = DC_TEXT;
    struct taskbar_button *win = find_taskbar_button( LongToHandle( dis->CtlID ));

    if (!win) return;
    GetClientRect( dis->hwndItem, &rect );
    DrawFrameControl( dis->hDC, &rect, DFC_BUTTON, DFCS_BUTTONPUSH | DFCS_ADJUSTRECT |
                      ((dis->itemState & ODS_SELECTED) ? DFCS_PUSHED : 0 ));
    if (win->hwnd)
    {
        flags |= win->active ? DC_ACTIVE : DC_INBUTTON;
        DrawCaptionTempW( win->hwnd, dis->hDC, &rect, 0, 0, NULL, flags );
    }''','''    UINT flags = DC_TEXT;
    struct taskbar_button *win = find_taskbar_button( LongToHandle( dis->CtlID ));
    COLORREF themed_text;
    BOOL themed;

    if (!win) return;
    GetClientRect( dis->hwndItem, &rect );
    themed = paint_themed_button( dis, win, &rect, &themed_text );
    if (!themed)
        DrawFrameControl( dis->hDC, &rect, DFC_BUTTON, DFCS_BUTTONPUSH | DFCS_ADJUSTRECT |
                          ((dis->itemState & ODS_SELECTED) ? DFCS_PUSHED : 0 ));
    if (win->hwnd && themed)
        paint_themed_window_button( dis->hDC, &rect, win, themed_text );
    else if (win->hwnd)
    {
        flags |= win->active ? DC_ACTIVE : DC_INBUTTON;
        DrawCaptionTempW( win->hwnd, dis->hDC, &rect, 0, 0, NULL, flags );
    }''','Styled or classic button background and content.')
revise('systray.c','''        DrawCaptionTempW( 0, dis->hDC, &text, 0, 0, start_label, flags | DC_INBUTTON );''',
       '''        if (themed) paint_themed_start_label( dis->hDC, &text, start_label, themed_text );
        else DrawCaptionTempW( 0, dis->hDC, &text, 0, 0, start_label, flags | DC_INBUTTON );''','Styled Start label.')
revise('systray.c','''    show_clock( &ncm.lfMessageFont );''','''    load_taskbar_theme();
    show_clock( &ncm.lfMessageFont );''','The style when the taskbar is shown.')
revise('systray.c','''    case WM_DRAWITEM:
''','''    case WM_ERASEBKGND:
        {
            RECT rect;
            HRESULT result = S_OK;
            static BOOL noted;
            HBRUSH brush = taskbar_brush ? taskbar_brush : GetSysColorBrush( COLOR_3DFACE );

            GetClientRect( hwnd, &rect );
            FillRect( (HDC)wparam, &rect, brush );
            if (taskbar_theme)
                result = pDrawThemeBackground( taskbar_theme, (HDC)wparam, TASKBAR_PART, 0, &rect, NULL );
            if (!noted)
            {
                ERR( "PWTASKBAR background base=1 themed=%u result=%#lx rect=%s\\n", !!taskbar_theme,
                     result, wine_dbgstr_rect( &rect ) );
                noted = TRUE;
            }
            return 1;
        }

    case WM_THEMECHANGED:
        load_taskbar_theme();
        RedrawWindow( hwnd, NULL, NULL, RDW_INVALIDATE | RDW_ERASE | RDW_ALLCHILDREN );
        break;

    case WM_CTLCOLORSTATIC:
        if (taskbar_theme && (HWND)lparam == clock_window)
        {
            SetBkColor( (HDC)wparam, taskbar_fill );
            SetTextColor( (HDC)wparam, taskbar_text );
            return (LRESULT)taskbar_brush;
        }
        break;

    case WM_DRAWITEM:
''','Styled taskbar background, style changes and the clock.')

# W182: the Control Panel submenu had no icons. Its items are applets, not files: their parsing
# name is the display name ("Wine Configuration"), so neither SHGetFileInfo nor W057's fallback (a
# file's icon) finds one. The folder's IExtractIconW knows the .cpl and its icon (a resource id,
# negative, as ExtractIconEx takes it; cpanelfolder.c); it is asked when the other ways give none.
revise('startmenu.c','''static HICON fallback_icon( const WCHAR *path, BOOL folder )
{''','''/* a small icon from the item's folder (IExtractIconW): the Control Panel's applets (W182) */
static HICON shell_item_icon( IShellFolder *folder, LPCITEMIDLIST pidl )
{
    IExtractIconW *extract;
    WCHAR location[MAX_PATH];
    HICON big_icon = NULL, small_icon = NULL;
    UINT flags = 0;
    int index = 0;

    if (FAILED(IShellFolder_GetUIObjectOf( folder, NULL, 1, &pidl, &IID_IExtractIconW, NULL, (void **)&extract )))
        return NULL;
    if (SUCCEEDED(IExtractIconW_GetIconLocation( extract, GIL_FORSHELL, location, MAX_PATH, &index, &flags )))
    {
        if (flags & GIL_NOTFILENAME)
            IExtractIconW_Extract( extract, location, index, &big_icon, &small_icon,
                                   MAKELONG( GetSystemMetrics( SM_CXICON ), GetSystemMetrics( SM_CXSMICON )));
        else
            ExtractIconExW( location, index, NULL, &small_icon, 1 );
    }
    IExtractIconW_Release( extract );
    if (big_icon) DestroyIcon( big_icon );
    return small_icon;
}

static HICON fallback_icon( const WCHAR *path, BOOL folder )
{''','Icons of items that are not files, from their folder.')
revise('startmenu.c','''        else item->icon = fallback_icon( path, item->folder != NULL );''','''        else
        {
            item->icon = fallback_icon( path, item->folder != NULL );
            if (!item->icon && parent->folder) item->icon = shell_item_icon( parent->folder, pidl );
        }''','Control Panel items: the icon from their folder when the file ways give none.')
# HID stack (tools/build-hidstack-hw.py): pwhidhost.dll runs ntoskrnl's IRP loop and loads winebus,
# so the pad is also an HID gamepad; its own thread logs each step (PWHID lines).
revise('desktop.c','''    desktopshellbrowserwindow_init();
    shellwindows_init();''','''    if (!LoadLibraryW( L"pwhidhost.dll" ))
        ERR( "PWHID pwhidhost.dll not loaded, error %lu\\n", GetLastError() );

    desktopshellbrowserwindow_init();
    shellwindows_init();''','HID stack: load pwhidhost.dll once the desktop is up.')

# Phase 10 hot plug: the shell monitor tells the programs when a drive letter comes or goes
# (the launcher's USB watcher changes the table; Wine's explorer has no mountmgr here).
revise('systray.c','''#include <shellapi.h>
''','''#include <shellapi.h>
#include <dbt.h>
#include <shlobj.h>
''','Device-change and shell notification headers (phase 10 hot plug).')
revise('systray.c','''            if (!hung.hwnd) hung_since = hung_dumps = 0;''','''            /* phase 10 hot plug: a USB drive letter came or went (the launcher refreshes the table
             * every 2 s in ROOT); the first round only records the letters */
            {
                static DWORD drives, cdroms;  /* DVD (J002): the CD-ROM letters, for their removal */
                static UINT waits[26];  /* W243: rounds an arriving root could not be opened */
                DWORD current = GetLogicalDrives(), changed = drives ? current ^ drives : 0;
                UINT i;

                if (!drives)  /* DVD (J002): a disc already in at the first round */
                    for (i = 2; i < 26; i++)
                    {
                        WCHAR letter[4] = {(WCHAR)('A' + i), ':', '\\\\', 0};

                        if ((current >> i) & 1 && GetDriveTypeW( letter ) == DRIVE_CDROM) cdroms |= 1u << i;
                    }
                for (i = 0; changed && i < 26; i++)
                {
                    DEV_BROADCAST_VOLUME volume = {sizeof(volume), DBT_DEVTYP_VOLUME};
                    WCHAR root[4] = {(WCHAR)('A' + i), ':', '\\\\', 0};
                    BOOL added = (current >> i) & 1;
                    DWORD_PTR result;
                    UINT type = DRIVE_UNKNOWN;
                    DWORD error = 0;

                    if (!((changed >> i) & 1)) continue;
                    volume.dbcv_unitmask = 1u << i;
                    /* DVD (J002): a disc came or went in a CD-ROM drive, as Windows tells it. W243: at the
                     * W241 reinsert GetDriveType did not give DRIVE_CDROM (flags=0): a root that cannot
                     * be opened yet is counted as absent and looked at again, 3 rounds at most, and the
                     * type is logged with the broadcast */
                    if (added)
                    {
                        type = GetDriveTypeW( root );
                        error = GetLastError();
                        if ((type == DRIVE_NO_ROOT_DIR || type == DRIVE_UNKNOWN) && waits[i] < 3)
                        {
                            waits[i]++;
                            ERR( "PWDRIVE arrival %c: not ready type=%u error=%lu wait=%u\\n", 'A' + i, type, error, waits[i] );
                            current &= ~(1u << i);
                            continue;
                        }
                        waits[i] = 0;
                        if (type == DRIVE_CDROM) cdroms |= 1u << i;
                    }
                    if ((cdroms >> i) & 1) volume.dbcv_flags = DBTF_MEDIA;
                    if (!added) cdroms &= ~(1u << i);
                    SendMessageTimeoutW( HWND_BROADCAST, WM_DEVICECHANGE, added ? DBT_DEVICEARRIVAL : DBT_DEVICEREMOVECOMPLETE,
                                         (LPARAM)&volume, SMTO_ABORTIFHUNG, 2000, &result );
                    SHChangeNotify( added ? SHCNE_DRIVEADD : SHCNE_DRIVEREMOVED, SHCNF_PATHW, root, NULL );
                    ERR( "PWDRIVE %s %c: broadcast flags=%#x type=%u error=%lu\\n", added ? "arrival" : "removal", 'A' + i,
                         volume.dbcv_flags, type, error );
                }
                drives = current;
            }
            if (!hung.hwnd) hung_since = hung_dumps = 0;''','Broadcast USB drive arrival and removal (phase 10 hot plug).')

# The pinned build's own commands for the explorer objects and link, from make -n.
subprocess.run(['python3',str(ROOT/'tools/patch-explorer-open.py'),str(overlay)],check=True)
revisions.append({'path':'desktop.c','why':'W106: copy WFM file-open requests and resolve them on Explorer desktop thread.'})
dry=subprocess.run(['make','-n']+[f'-W../../source/programs/explorer/{u}.c' for u in UNITS]+
                   ['programs/explorer/x86_64-windows/explorer.exe'],cwd=BUILD,capture_output=True,text=True,check=True).stdout
dry=dry.replace('\\\n',' ')
commands=[]
for line in dry.splitlines():
    if 'programs/explorer/' not in line:continue
    for u in UNITS:line=line.replace(f'../../source/programs/explorer/{u}.c',str(overlay/(u+'.c')))
    line=line.replace('programs/explorer/x86_64-windows/',str(work)+'/')
    commands.append(line)
if not any(str(overlay/'systray.c') in c for c in commands) or not any(str(work/'explorer.exe') in c for c in commands):
    raise SystemExit('make -n did not give the explorer commands:\n'+dry[-2000:])
for command in commands:
    run=subprocess.run(command,shell=True,cwd=BUILD,capture_output=True,text=True)
    if run.returncode:raise SystemExit(command[:300]+'\n'+run.stdout+run.stderr)
target=out/'explorer.exe';shutil.copyfile(work/'explorer.exe',target)
manifest={'schema_version':1,'wine_commit':commit,'explorer':{'path':'explorer.exe','sha256':sha(target)},
          'revisions':revisions,'commands':commands,
          'overlay_sha256':{p.name:sha(p) for p in sorted(overlay.glob('*.c'))},
          'open_protocol_sha256':sha(ROOT/'platform/ps4/pw_shell_open.h'),
          'dos_classifier_sha256':sha(ROOT/'tools/explorer-dos.h'),
          'open_patch_sha256':sha(ROOT/'tools/patch-explorer-open.py')}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'explorer':str(target.relative_to(ROOT)),'sha256':manifest['explorer']['sha256'],'revisions':len(revisions)}))
