#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Pending change for tools/build-explorer-hw.py (W179): the taskbar, Start and the window buttons
drawn from the visual style when it has XP's shell classes (Luna, Noir). Usage:
taskbar-theme-w179.patch.py FILE adds the revisions to FILE (build-explorer-hw.py or a copy),
before its "pinned build's own commands" section."""
import pathlib,sys
BLOCK=r"""# W179: the taskbar, Start and the window buttons from the visual style when it has XP's shell
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
        if (taskbar_theme)
        {
            RECT rect;

            GetClientRect( hwnd, &rect );
            pDrawThemeBackground( taskbar_theme, (HDC)wparam, TASKBAR_PART, 0, &rect, NULL );
            return 1;
        }
        break;

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
"""
if __name__=='__main__':
    path=pathlib.Path(sys.argv[1]);text=path.read_text()
    anchor="# The pinned build's own commands for the explorer objects and link, from make -n."
    if 'W179: the taskbar, Start and the window buttons' in text:raise SystemExit('already applied')
    at=text.index(anchor);path.write_text(text[:at]+BLOCK+'\n'+text[at:]);print('applied to',path)
