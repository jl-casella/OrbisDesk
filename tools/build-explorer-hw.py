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
        if (stage != previous || count < 5 || !(count % 5))
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
 * stopped thread may hold). If a thread's context never comes, its "start" line is the last one. */
static void orbis_dump_threads( DWORD age )
{
    RTL_CRITICAL_SECTION *loader = NtCurrentTeb()->Peb->LoaderLock;
    THREADENTRY32 entry = {.dwSize = sizeof(entry)};
    DWORD pid = GetCurrentProcessId(), self = GetCurrentThreadId();
    unsigned int threads = 0;
    HANDLE snapshot;

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

            if (age < 8000) dumps = 0;
            else if ((dumps == 0) || (dumps == 1 && age >= 70000))
            {
                dumps++;
                orbis_dump_threads( age );
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
revise('systray.c','''                orbis_dump_threads( age );
            }
        }
        previous = stage;''','''                orbis_dump_threads( age );
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
                orbis_dump_threads( 0 );
            }
            if (!hung.hwnd) hung_since = hung_dumps = 0;
            else
            {
                if (!hung_since) hung_since = now | 1;
                if ((hung_dumps == 0 && now - hung_since >= 8000) || (hung_dumps == 1 && now - hung_since >= 70000))
                {
                    WCHAR class[64] = {0}, title[64] = {0};

                    GetClassNameW( hung.hwnd, class, ARRAY_SIZE(class) );
                    InternalGetWindowText( hung.hwnd, title, ARRAY_SIZE(title) );
                    ERR( "PWHUNG hwnd=%p tid=%04lx windows=%u class=%s title=%s age_ms=%lu\\n", hung.hwnd, hung.tid,
                         hung.count, debugstr_w( class ), debugstr_w( title ), now - hung_since );
                    hung_dumps++;
                    orbis_dump_threads( now - hung_since );
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
            if (launcher) ShellExecuteW( NULL, L"open", launcher->path, NULL, NULL, 0 );
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
