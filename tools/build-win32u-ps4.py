#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Compile Wine's win32u Unix side for Orbis with an in-process user driver.

The driver is prospero-win's PS5 user driver (patches 0400 and 0410), adapted: it is
enabled for __ORBIS__ and its presentation and input sink is linked into the boot ELF
instead of being found with dlsym. Each object uses its exact recipe from the Orbis
Wine Makefile; the patched sources live in their own overlay, with every hash recorded.
"""
import hashlib,json,pathlib,re,shlex,shutil,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
SOURCE=ROOT/'.deps/wine/source';UNIX=ROOT/'.deps/wine/ps4-unix'
overlay=ROOT/'.deps/wine/ps4-win32u-overlay';work=ROOT/'build/win32u-ps4'
PATCHES=['0400-win32u-ps5-user-driver.patch','0410-win32u-ps5-fontless-metrics-and-server-desktop.patch']
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
commit=subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip()
if commit!=json.loads((ROOT/'sources.lock.json').read_text())['sources']['wine']['commit']:
    raise SystemExit('Wine source is not the pinned revision')
if overlay.exists():shutil.rmtree(overlay)
shutil.copytree(SOURCE/'dlls/win32u',overlay/'dlls/win32u')
work.mkdir(parents=True,exist_ok=True)
manifest={'schema_version':1,'wine_commit':commit,'prospero_patches':[],'revisions':[],'objects':{}}
for filename in PATCHES:
    original=ROOT/'upstream/prospero-win/wine/patches'/filename
    adapted=original.read_text().replace('defined(__PROSPERO__) && !defined(WINE_PS5_USER_DRIVER)',
                                         '(defined(__PROSPERO__) || defined(__ORBIS__)) && !defined(WINE_PS5_USER_DRIVER)')
    target=work/filename;target.write_text(adapted)
    run=subprocess.run(['patch','--batch','--fuzz=0','-p1','-d',str(overlay),'-i',str(target)],capture_output=True,text=True)
    if run.returncode:raise SystemExit(run.stdout+run.stderr)
    manifest['prospero_patches'].append({'path':str(original.relative_to(ROOT)),'original_sha256':sha(original),
                                         'adapted_sha256':sha(target)})
def revise(path,old,new,why):
    target=overlay/path;text=target.read_text()
    if text.count(old)!=1:raise SystemExit('Unexpected context in '+path+': '+old[:60])
    target.write_text(text.replace(old,new))
    manifest['revisions'].append({'path':path,'why':why})
# The boot ELF is one static image: the sink is linked, not looked up.
# W179: a solid window frame in the border colour when a visual style sets one apart from the
# button face (Luna, Noir; tools/build-msstyles-hw.py), as XP draws its windows.
revise('dlls/win32u/defwnd.c','''    NtGdiSelectPen( hdc, get_sys_color_pen( COLOR_WINDOWFRAME ));

    if (has_static_outer_frame( ex_style ))
        draw_rect_edge( hdc, &rect, BDR_SUNKENOUTER, BF_RECT | BF_ADJUST, 1 );
    else if (has_big_frame( style, ex_style ))
        draw_rect_edge( hdc, &rect, EDGE_RAISED, BF_RECT | BF_ADJUST, 1 );

    draw_nc_frame( hdc, &rect, active, style, ex_style );
''','''    NtGdiSelectPen( hdc, get_sys_color_pen( COLOR_WINDOWFRAME ));

    /* OrbisDesk W179: a visual style whose border colour is not the button face (Luna's XP blue,
     * Noir's orange, tools/build-msstyles-hw.py) gets a solid frame in that colour, its 3D edges
     * included, as XP draws its windows; otherwise the classic frame */
    {
        int border = active ? COLOR_ACTIVEBORDER : COLOR_INACTIVEBORDER;

        if (has_big_frame( style, ex_style ) && !has_static_outer_frame( ex_style ) &&
            get_sys_color( border ) != get_sys_color( COLOR_3DFACE ))
        {
            int width = get_system_metrics( (style & WS_THICKFRAME) ? SM_CXFRAME : SM_CXDLGFRAME );
            int height = get_system_metrics( (style & WS_THICKFRAME) ? SM_CYFRAME : SM_CYDLGFRAME );

            NtGdiSelectBrush( hdc, get_sys_color_brush( border ));
            NtGdiPatBlt( hdc, rect.left, rect.top, rect.right - rect.left, height, PATCOPY );
            NtGdiPatBlt( hdc, rect.left, rect.top, width, rect.bottom - rect.top, PATCOPY );
            NtGdiPatBlt( hdc, rect.left, rect.bottom - 1, rect.right - rect.left, -height, PATCOPY );
            NtGdiPatBlt( hdc, rect.right - 1, rect.top, -width, rect.bottom - rect.top, PATCOPY );
            InflateRect( &rect, -width, -height );
        }
        else
        {
            if (has_static_outer_frame( ex_style ))
                draw_rect_edge( hdc, &rect, BDR_SUNKENOUTER, BF_RECT | BF_ADJUST, 1 );
            else if (has_big_frame( style, ex_style ))
                draw_rect_edge( hdc, &rect, EDGE_RAISED, BF_RECT | BF_ADJUST, 1 );

            draw_nc_frame( hdc, &rect, active, style, ex_style );
        }
    }
''',
       'Solid frame in the border colour of a visual style (W179).')
revise('dlls/win32u/ps5drv.c','''    present_frame = dlsym( RTLD_DEFAULT, "pw_wine_present" );
    next_input = dlsym( RTLD_DEFAULT, "pw_wine_next_input" );
    input_fd = dlsym( RTLD_DEFAULT, "pw_wine_input_fd" );''','''#ifdef __ORBIS__
    {
        extern int pw_wine_present( const void *bgra, unsigned int width, unsigned int height, unsigned int stride );
        extern int pw_wine_next_input( struct ps5_input *event );
        extern int pw_wine_input_fd( void );
        present_frame = pw_wine_present;
        next_input = pw_wine_next_input;
        input_fd = pw_wine_input_fd;
    }
#else
    present_frame = dlsym( RTLD_DEFAULT, "pw_wine_present" );
    next_input = dlsym( RTLD_DEFAULT, "pw_wine_next_input" );
    input_fd = dlsym( RTLD_DEFAULT, "pw_wine_input_fd" );
#endif''','The boot ELF links the sink statically; there is no dlsym of the title.')
# W033 on hardware: input was queued but ProcessEvents never ran; report each step of
# registering the wake descriptor with the server.
revise('dlls/win32u/ps5drv.c','''    if (wine_server_fd_to_handle( fd, GENERIC_READ | SYNCHRONIZE, 0, &handle )) return;
    SERVER_START_REQ( set_queue_fd )
    {
        req->handle = wine_server_obj_handle( handle );
        wine_server_call( req );
    }
    SERVER_END_REQ;''','''#ifdef __ORBIS__
    {
        NTSTATUS to_handle = wine_server_fd_to_handle( fd, GENERIC_READ | SYNCHRONIZE, 0, &handle ), queued;
        fprintf( stderr, "PWBOOT input_fd_register tid=%04x fd=%d to_handle=%08x\\n", (UINT)tid, fd, (UINT)to_handle );
        if (to_handle) return;
        SERVER_START_REQ( set_queue_fd )
        {
            req->handle = wine_server_obj_handle( handle );
            queued = wine_server_call( req );
        }
        SERVER_END_REQ;
        fprintf( stderr, "PWBOOT input_fd_set_queue tid=%04x status=%08x\\n", (UINT)tid, (UINT)queued );
    }
#else
    if (wine_server_fd_to_handle( fd, GENERIC_READ | SYNCHRONIZE, 0, &handle )) return;
    SERVER_START_REQ( set_queue_fd )
    {
        req->handle = wine_server_obj_handle( handle );
        wine_server_call( req );
    }
    SERVER_END_REQ;
#endif''','Hardware diagnosis: report the input wake descriptor registration.')
# W038: a wheel event (type 4, signed delta in y, WHEEL_DELTA units) for the right stick
# and USB mouse wheels of the hardware launcher.
revise('dlls/win32u/ps5drv.c','''        case 3:
            if (event.code < 3) send_mouse( hwnd, button_flags[event.code][event.down != 0], 0, 0 );
            break;
        }''','''        case 3:
            if (event.code < 3) send_mouse( hwnd, button_flags[event.code][event.down != 0], 0, 0 );
            break;
        case 4:
        {
            INPUT wheel = {.type = INPUT_MOUSE};
            wheel.mi.dwFlags = MOUSEEVENTF_WHEEL;
            wheel.mi.mouseData = (DWORD)event.y;
            NtUserSendHardwareInput( hwnd, 0, &wheel, 0 );
            break;
        }
        }''','Wheel input from the title (type 4).')
# W043: compose by z-order. The original driver copied each flush straight onto the
# screen and cleared a moved window's old rect to black: an older window flushing drew
# over newer ones, and what a moved window uncovered stayed black until something
# repainted it. Each window now keeps its last flushed content; the screen is rebuilt
# bottom to top from those copies, so moves, hides and restacks need no repaint.
revise('dlls/win32u/ps5drv.c','''    RECT visible;           /* screen coordinates */
    BOOL shown;
};''','''    RECT visible;           /* screen coordinates */
    BOOL shown;
    BOOL topmost;
    UINT32 *pixels;         /* last flushed content, visible-rect sized */
    INT pixels_width, pixels_height;
    /* W152: the last image a Vulkan swapchain of the window presented, drawn by the GPU over
     * its client area (screen coordinates); NULL when there is none */
    const UINT32 *vk_pixels;
    UINT vk_stride, vk_width, vk_height, vk_flags;
    RECT vk_rect;
    UINT64 vk_swapchain;
    RECT client;            /* W156: client area, screen coordinates like visible */
};''','Per-window content copy for the compositor.')
revise('dlls/win32u/ps5drv.c','''/* screen_lock held */
static void clear_screen_rect( const RECT *rect )
{
    RECT clip = {0, 0, screen_width, screen_height};
    INT y;

    if (!intersect_rect( &clip, &clip, rect )) return;
    for (y = clip.top; y < clip.bottom; y++)
        memset( screen + y * screen_width + clip.left, 0, (clip.right - clip.left) * 4 );
}''','''/* screen_lock held: rebuild a screen rect from the windows' content, bottom to top
 * (windows[0] is the bottom of the stack).
 * W075: each row is built in a scratch row and copied to the screen once. The sink's
 * presenter thread reads the screen while this runs (PW_SINK_ASYNC); when the wallpaper was
 * written first and the windows over it, a frame shown in between had the wallpaper where a
 * window is, which looked like the window turning transparent (W074, a Vulkan window
 * redrawn 130 times a second). A torn read now mixes only finished rows. */
static void compose_rect( const RECT *rect )
{
    static UINT32 *row;
    static UINT row_width;
    RECT clip = {0, 0, screen_width, screen_height}, content, parts[PS5_MAX_WINDOWS];
    UINT i, count = 0, order[PS5_MAX_WINDOWS];
    INT y, width;

    if (!intersect_rect( &clip, &clip, rect )) return;
    width = clip.right - clip.left;
    if (row_width < screen_width)
    {
        free( row );
        if (!(row = malloc( screen_width * sizeof(*row) ))) { row_width = 0; return; }
        row_width = screen_width;
    }
    for (i = 0; i < window_count; i++)
    {
        const struct ps5_window *window = &windows[i];

        if (!window->shown || !window->pixels) continue;
        SetRect( &content, window->visible.left, window->visible.top,
                 window->visible.left + window->pixels_width, window->visible.top + window->pixels_height );
        if (!intersect_rect( &parts[count], &clip, &content ) || !intersect_rect( &parts[count], &parts[count], &window->visible ))
            continue;
        order[count++] = i;
    }
    for (y = clip.top; y < clip.bottom; y++)
    {
        if (background) memcpy( row, background + y * screen_width + clip.left, width * 4 );
        else memset( row, 0, width * 4 );
        for (i = 0; i < count; i++)
        {
            const struct ps5_window *window = &windows[order[i]];
            const RECT *part = &parts[i];

            if (y < part->top || y >= part->bottom) continue;
            memcpy( row + (part->left - clip.left),
                    window->pixels + (y - window->visible.top) * window->pixels_width + (part->left - window->visible.left),
                    (part->right - part->left) * 4 );
        }
        memcpy( screen + y * screen_width + clip.left, row, width * 4 );
    }
}

/* screen_lock held: a resized window keeps what still fits until it repaints */
static void resize_pixels( struct ps5_window *window, INT width, INT height )
{
    UINT32 *pixels = calloc( (size_t)width * height, sizeof(*pixels) );
    INT y, keep_width = min( width, window->pixels_width ), keep_height = min( height, window->pixels_height );

    if (!pixels) return;
    for (y = 0; window->pixels && y < keep_height; y++)
        memcpy( pixels + y * width, window->pixels + y * window->pixels_width, keep_width * 4 );
    free( window->pixels );
    window->pixels = pixels;
    window->pixels_width = width;
    window->pixels_height = height;
}

/* screen_lock held: move windows[from] to stack position to, keeping topmost windows
 * above the others */
static void restack( UINT from, UINT to )
{
    struct ps5_window moved = windows[from];
    UINT first_topmost;

    memmove( &windows[from], &windows[from + 1], (window_count - from - 1) * sizeof(*windows) );
    window_count--;
    for (first_topmost = 0; first_topmost < window_count; first_topmost++)
        if (windows[first_topmost].topmost) break;
    if (moved.topmost) to = max( to, first_topmost );
    else to = min( to, first_topmost );
    to = min( to, window_count );
    memmove( &windows[to + 1], &windows[to], (window_count - to) * sizeof(*windows) );
    windows[to] = moved;
    window_count++;
}''','Compositor: rebuild screen rects by z-order from per-window content.')
# W045: the desktop window never gets a surface (get_win_ptr gives WND_DESKTOP), so what
# explorer paints there, the wallpaper included, never reaches the screen. The driver
# loads the wallpaper named by WINE_PS5_WALLPAPER (a host path to an uncompressed 24- or
# 32-bit BMP) itself and composes it under every window instead of black.
revise('dlls/win32u/ps5drv.c','#include <unistd.h>\n','#include <unistd.h>\n#include <fcntl.h>\n','open() for the wallpaper.')
revise('dlls/win32u/ps5drv.c','''static struct ps5_window windows[PS5_MAX_WINDOWS];''','''static struct ps5_window windows[PS5_MAX_WINDOWS];
static UINT32 *background;  /* screen-sized wallpaper, or NULL for black */''','Wallpaper layer.')
revise('dlls/win32u/ps5drv.c','''/***********************************************************************
 *           ps5_install_user_driver''','''/* Scale an uncompressed 24/32-bit BMP to the screen (nearest), or leave black. */
static void load_background( const char *path )
{
    BYTE *data = NULL;
    INT fd, width, height, bpp, x, y;
    UINT offset, stride;
    off_t size;

    if (!path || !*path) return;
    if ((fd = open( path, O_RDONLY )) == -1 || (size = lseek( fd, 0, SEEK_END )) < 54 ||
        lseek( fd, 0, SEEK_SET ) || !(data = malloc( size )) || read( fd, data, size ) != size)
    {
        ERR( "wallpaper %s: cannot read\\n", debugstr_a(path) );
        fprintf( stderr, "PWBOOT wallpaper_failed read path=%s\\n", path );
        if (fd != -1) close( fd );
        free( data );
        return;
    }
    close( fd );
    offset = *(const UINT *)(data + 10);
    width = *(const INT *)(data + 18);
    height = *(const INT *)(data + 22);
    bpp = *(const WORD *)(data + 28);
    stride = ((width * bpp / 8) + 3) & ~3;
    if (data[0] != 'B' || data[1] != 'M' || width <= 0 || !height || (bpp != 24 && bpp != 32) ||
        *(const UINT *)(data + 30) || offset + stride * (UINT)abs( height ) > (UINT)size ||
        !(background = malloc( (size_t)screen_width * screen_height * 4 )))
    {
        fprintf( stderr, "PWBOOT wallpaper_failed format path=%s\\n", path );
        free( data );
        return;
    }
    for (y = 0; y < (INT)screen_height; y++)
    {
        INT sy = y * abs( height ) / (INT)screen_height;
        const BYTE *row = data + offset + (size_t)(height > 0 ? abs( height ) - 1 - sy : sy) * stride;
        for (x = 0; x < (INT)screen_width; x++)
        {
            const BYTE *pixel = row + (size_t)(x * width / (INT)screen_width) * (bpp / 8);
            background[y * screen_width + x] = 0xff000000 | (pixel[2] << 16) | (pixel[1] << 8) | pixel[0];
        }
    }
    free( data );
    memcpy( screen, background, (size_t)screen_width * screen_height * 4 );
    fprintf( stderr, "PWBOOT wallpaper_loaded %dx%d bpp=%d\\n", width, abs( height ), bpp );
}

/***********************************************************************
 *           ps5_install_user_driver''','Load the wallpaper for the background layer.')
revise('dlls/win32u/ps5drv.c','''        ERR( "no memory for a %ux%u desktop\\n", screen_width, screen_height );
        return;
    }''','''        ERR( "no memory for a %ux%u desktop\\n", screen_width, screen_height );
        return;
    }
    load_background( getenv( "WINE_PS5_WALLPAPER" ));''','Wallpaper at driver install.')
revise('dlls/win32u/ps5drv.c','''    struct ps5_window *window;
    UINT stride = color_info->bmiHeader.biWidth * 4;
    RECT target, clip = {0, 0, screen_width, screen_height};
    INT y;

    pthread_mutex_lock( &screen_lock );
    if ((window = find_window( surface->hwnd )) && window->shown)
    {
        /* dirty is relative to the surface, whose origin is the visible rect's */
        target = *dirty;
        OffsetRect( &target, window->visible.left, window->visible.top );
        if (intersect_rect( &target, &target, &clip ) && intersect_rect( &target, &target, &window->visible ))
        {
            for (y = target.top; y < target.bottom; y++)
            {
                const BYTE *src = (const BYTE *)color_bits + (y - window->visible.top) * stride +
                                  (target.left - window->visible.left) * 4;
                memcpy( screen + y * screen_width + target.left, src, (target.right - target.left) * 4 );
            }
            present_screen();
        }
    }''','''    struct ps5_window *window;
    UINT stride = color_info->bmiHeader.biWidth * 4;
    RECT target, area;
    INT y, width, height;

    pthread_mutex_lock( &screen_lock );
    if ((window = find_window( surface->hwnd )) && window->shown)
    {
        width = window->visible.right - window->visible.left;
        height = window->visible.bottom - window->visible.top;
        if (width > 0 && height > 0 &&
            (!window->pixels || window->pixels_width != width || window->pixels_height != height))
            resize_pixels( window, width, height );
        /* dirty is relative to the surface; rect places the surface in the visible rect */
        target = *dirty;
        OffsetRect( &target, rect->left, rect->top );
        SetRect( &area, 0, 0, window->pixels_width, window->pixels_height );
        if (window->pixels && intersect_rect( &target, &target, &area ))
        {
            for (y = target.top; y < target.bottom; y++)
                memcpy( window->pixels + y * window->pixels_width + target.left,
                        (const BYTE *)color_bits + (y - rect->top) * stride + (target.left - rect->left) * 4,
                        (target.right - target.left) * 4 );
            OffsetRect( &target, window->visible.left, window->visible.top );
            compose_rect( &target );
            present_screen();
        }
    }''','Flush into the window copy, then recompose that screen rect.')
revise('dlls/win32u/ps5drv.c','''    struct ps5_window *window;
    BOOL shown = (NtUserGetWindowLongW( hwnd, GWL_STYLE ) & WS_VISIBLE) &&
                 NtUserGetAncestor( hwnd, GA_PARENT ) == get_desktop_window();
    BOOL repaint = FALSE;

    pthread_mutex_lock( &screen_lock );
    if (!(window = find_window( hwnd )) && shown && window_count < PS5_MAX_WINDOWS)
    {
        window = &windows[window_count++];
        window->hwnd = hwnd;
        window->shown = FALSE;
    }
    if (window)
    {
        if (window->shown && (!shown || !EqualRect( &window->visible, &new_rects->visible )))
        {
            clear_screen_rect( &window->visible );
            present_screen();
        }
        /* a window just shown may have painted before it had this surface */
        repaint = shown && !window->shown;
        window->visible = new_rects->visible;
        window->shown = shown;
    }
    pthread_mutex_unlock( &screen_lock );''','''    struct ps5_window *window;
    BOOL shown = (NtUserGetWindowLongW( hwnd, GWL_STYLE ) & WS_VISIBLE) &&
                 NtUserGetAncestor( hwnd, GA_PARENT ) == get_desktop_window();
    BOOL topmost = (NtUserGetWindowLongW( hwnd, GWL_EXSTYLE ) & WS_EX_TOPMOST) != 0;
    BOOL repaint = FALSE, restacked = FALSE;
    RECT old_visible;
    UINT i, index;

    pthread_mutex_lock( &screen_lock );
    if (!(window = find_window( hwnd )) && shown && window_count < PS5_MAX_WINDOWS)
    {
        /* a new window starts on top */
        window = &windows[window_count++];
        memset( window, 0, sizeof(*window) );
        window->hwnd = hwnd;
        window->topmost = topmost;
        restack( window_count - 1, window_count - 1 );
        window = find_window( hwnd );
    }
    if (window)
    {
        BOOL was_shown = window->shown, topmost_changed = window->topmost != topmost;

        index = window - windows;
        window->topmost = topmost;
        if (!(swp_flags & SWP_NOZORDER) || topmost_changed)
        {
            /* insert_after is the window just above this one, or HWND_TOP/HWND_BOTTOM */
            UINT to = window_count - 1;
            if (insert_after == HWND_BOTTOM) to = 0;
            else if (insert_after != HWND_TOP && insert_after != HWND_TOPMOST && insert_after != HWND_NOTOPMOST)
                for (i = 0; i < window_count; i++)
                    if (windows[i].hwnd == insert_after) { to = i > index ? i - 1 : i; break; }
            if (to != index) { restack( index, to ); restacked = TRUE; }
            window = find_window( hwnd );
        }
        old_visible = window->visible;
        /* a window just shown may have painted before it had this surface */
        repaint = shown && !was_shown;
        window->visible = new_rects->visible;
        window->shown = shown;
        if (was_shown && (!shown || !EqualRect( &old_visible, &window->visible ))) compose_rect( &old_visible );
        if (shown && (restacked || !was_shown || !EqualRect( &old_visible, &window->visible ))) compose_rect( &window->visible );
        if (was_shown || shown) present_screen();
    }
    pthread_mutex_unlock( &screen_lock );''','Restack and recompose instead of clearing to black.')
revise('dlls/win32u/ps5drv.c','''    if ((window = find_window( hwnd )))
    {
        if (window->shown)
        {
            clear_screen_rect( &window->visible );
            present_screen();
        }
        *window = windows[--window_count];
    }''','''    if ((window = find_window( hwnd )))
    {
        RECT old_visible = window->visible;
        BOOL was_shown = window->shown;
        UINT index = window - windows;

        free( window->pixels );
        memmove( &windows[index], &windows[index + 1], (window_count - index - 1) * sizeof(*windows) );
        window_count--;
        if (was_shown)
        {
            compose_rect( &old_visible );
            present_screen();
        }
    }''','Destroy keeps the stacking order and recomposes what was under the window.')
# W054/W055: mouse input went to the foreground window: given a visible window, the
# server delivers there whatever the pointer position. With a guest program in front
# (W053), clicks on the taskbar's Start button reached the guest. Without a window
# (W054) the server takes the desktop of the visible window station, which this title
# does not have, and drops the event. Mouse events carry the top-level window under the
# pointer, from the compositor's stack (the desktop window where there is none), as
# winex11 passes the X window under the pointer; win32u then finds the child. Keys keep
# the foreground window.
revise('dlls/win32u/ps5drv.c','''static BOOL ps5_ProcessEvents( DWORD mask )''','''/* the top-level window under a screen point, top of the stack first */
static HWND window_at( INT x, INT y )
{
    GUITHREADINFO info = {.cbSize = sizeof(info)};
    HWND hwnd = 0, foreground = NtUserGetForegroundWindow();
    DWORD tid = foreground ? get_window_thread( foreground, NULL ) : 0;
    UINT i;

    /* W060: a capture (window drag, open menu, pressed button) in the foreground thread
     * takes the pointer wherever it is: given a window, the server looks for a capture
     * only in that window's thread, so a drag lost its moves whenever the pointer got
     * ahead of the window (W057-W059: bursts with 1-5 s gaps) */
    if (tid && NtUserGetGUIThreadInfo( tid, &info ) && info.hwndCapture) return info.hwndCapture;

    pthread_mutex_lock( &screen_lock );
    for (i = window_count; i > 0 && !hwnd; i--)
    {
        const RECT *rect = &windows[i - 1].visible;
        if (windows[i - 1].shown && x >= rect->left && x < rect->right && y >= rect->top && y < rect->bottom)
            hwnd = windows[i - 1].hwnd;
    }
    pthread_mutex_unlock( &screen_lock );
    return hwnd ? hwnd : get_desktop_window();
}

static BOOL ps5_ProcessEvents( DWORD mask )''','Window under the pointer.')
revise('dlls/win32u/ps5drv.c','''            send_mouse( hwnd, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, cursor.x, cursor.y );''',
       '''            send_mouse( window_at( cursor.x, cursor.y ), MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, cursor.x, cursor.y );''',
       'Mouse moves go to the window under the pointer.')
revise('dlls/win32u/ps5drv.c','''            if (event.code < 3) send_mouse( hwnd, button_flags[event.code][event.down != 0], 0, 0 );''',
       '''            if (event.code < 3) send_mouse( window_at( cursor.x, cursor.y ), button_flags[event.code][event.down != 0], 0, 0 );''',
       'Mouse buttons go to the window under the pointer.')
revise('dlls/win32u/ps5drv.c','''            NtUserSendHardwareInput( hwnd, 0, &wheel, 0 );''',
       '''            NtUserSendHardwareInput( window_at( cursor.x, cursor.y ), 0, &wheel, 0 );''','The wheel goes to the window under the pointer.')
# W248: relative motion from the title (native/hw_pad.c: a key profile's right stick as mouse look). Raw
# input and DirectInput get its delta as it is; an absolute move gives "position - cursor", nothing at the
# edge of the screen.
revise('dlls/win32u/ps5drv.c','''            NtUserSendHardwareInput( window_at( cursor.x, cursor.y ), 0, &wheel, 0 );
            break;
        }
''','''            NtUserSendHardwareInput( window_at( cursor.x, cursor.y ), 0, &wheel, 0 );
            break;
        }
        case 5:  /* W248: relative motion, x and y the delta */
        {
            /* W249: not coalesced, as the absolute moves above: win32u's accum_mouse_motion keeps a plain move
             * until another input comes for the window, and W248's deltas never reached raw input */
            static UINT relative_logged;
            INPUT motion = {.type = INPUT_MOUSE};
            HWND target = window_at( cursor.x, cursor.y );
            NTSTATUS status;

            motion.mi.dx = event.x;
            motion.mi.dy = event.y;
            motion.mi.dwFlags = MOUSEEVENTF_MOVE | MOUSEEVENTF_MOVE_NOCOALESCE;
            status = NtUserSendHardwareInput( target, 0, &motion, 0 );
            if (relative_logged < 8)
            {
                relative_logged++;
                fprintf( stderr, "PWINPUT relative dx=%d dy=%d hwnd=%p status=%#x (raw input)\\n", (int)event.x,
                         (int)event.y, target, (UINT)status );
            }
            cursor.x = min( max( cursor.x + event.x, 0 ), (INT)screen_width - 1 );
            cursor.y = min( max( cursor.y + event.y, 0 ), (INT)screen_height - 1 );
            break;
        }
''','Relative motion from the title (type 5).')
# W056 diagnosis: a dragged window moves only when the button is released. Count the
# pointer moves Wine receives and the window moves the compositor sees.
revise('dlls/win32u/ps5drv.c','''            send_mouse( window_at( cursor.x, cursor.y ), MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, cursor.x, cursor.y );''',
       '''            send_mouse( window_at( cursor.x, cursor.y ), MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, cursor.x, cursor.y );
            {
                static UINT pointer_moves;
                if (++pointer_moves % 50 == 1)
                    fprintf( stderr, "PWBOOT pointer_move n=%u tid=%04x at=%d,%d\\n", pointer_moves,
                             (UINT)GetCurrentThreadId(), (int)cursor.x, (int)cursor.y );
            }''','Pointer move count.')
revise('dlls/win32u/ps5drv.c','''        if (shown && (restacked || !was_shown || !EqualRect( &old_visible, &window->visible ))) compose_rect( &window->visible );''',
       '''        if (shown && (restacked || !was_shown || !EqualRect( &old_visible, &window->visible ))) compose_rect( &window->visible );
        if (was_shown && shown && !EqualRect( &old_visible, &window->visible ))
        {
            /* W057: each of the first moves with its time, to see the drag rate */
            static UINT window_moves;
            if (++window_moves <= 120)
                fprintf( stderr, "PWBOOT window_move n=%u tid=%04x hwnd=%p to=%d,%d t_us=%llu\\n", window_moves,
                         (UINT)GetCurrentThreadId(), hwnd, (int)window->visible.left, (int)window->visible.top,
                         (unsigned long long)ps5_now_us() );
        }''','Window move count.')
# W063: a guest ended from another thread (TerminateThread: a console program when its
# console window closes, conhost when its last program exits) has its windows destroyed
# by the server, but no thread of its own runs the driver's DestroyWindow, so the
# compositor kept drawing them (W062: the console window stayed after "exit"). Input
# pulls check, at most every 200 ms, that each window still exists, and drop the others.
revise('dlls/win32u/ps5drv.c','''static BOOL ps5_ProcessEvents( DWORD mask )''','''static void purge_dead_windows(void)
{
    static unsigned long long last;
    unsigned long long now = ps5_now_us();
    RECT gone[PS5_MAX_WINDOWS];
    UINT i, count = 0;

    if (now - last < 200000) return;
    last = now;
    pthread_mutex_lock( &screen_lock );
    for (i = 0; i < window_count; i++)
    {
        if (is_window( windows[i].hwnd )) continue;
        fprintf( stderr, "PWBOOT window_gone hwnd=%p\\n", windows[i].hwnd );
        if (windows[i].shown) gone[count++] = windows[i].visible;
        free( windows[i].pixels );
        memmove( &windows[i], &windows[i + 1], (window_count - i - 1) * sizeof(*windows) );
        window_count--;
        i--;
    }
    for (i = 0; i < count; i++) compose_rect( &gone[i] );
    if (count) present_screen();
    pthread_mutex_unlock( &screen_lock );
}

static BOOL ps5_ProcessEvents( DWORD mask )''','Drop windows destroyed without a DestroyWindow call.')
revise('dlls/win32u/ps5drv.c','''    if (!next_input) return FALSE;
    if (!hwnd && (hwnd = last_shown_window()))''','''    if (!next_input) return FALSE;
    purge_dead_windows();
    if (!hwnd && (hwnd = last_shown_window()))''','Check for dead windows on input pulls.')
# W062 diagnosis: in W061 input reaches Wine every 17 ms, but a dragged window moves once
# a second. Time the move loop itself: every message it gets, and each SetWindowPos.
revise('dlls/win32u/defwnd.c','''        if (!NtUserGetMessage( &msg, 0, 0, 0 )) break;''','''        if (!NtUserGetMessage( &msg, 0, 0, 0 )) break;
#ifdef __ORBIS__
        {
            static UINT loop_messages;
            struct timespec ts;
            clock_gettime( CLOCK_MONOTONIC_RAW, &ts );
            if (++loop_messages <= 200)
                fprintf( stderr, "PWBOOT move_loop n=%u msg=%04x pt=%d,%d t_us=%llu\\n", loop_messages, msg.message,
                         (int)msg.pt.x, (int)msg.pt.y, (unsigned long long)ts.tv_sec * 1000000 + ts.tv_nsec / 1000 );
        }
#endif''','Move loop message trace.')
revise('dlls/win32u/defwnd.c','''                    NtUserSetWindowPos( hwnd, 0, rect.left, rect.top,
                                        rect.right - rect.left, rect.bottom - rect.top,
                                        hittest == HTCAPTION ? SWP_NOSIZE : 0 );''','''#ifdef __ORBIS__
                    struct timespec before, after;
                    static UINT moves;
                    clock_gettime( CLOCK_MONOTONIC_RAW, &before );
#endif
                    NtUserSetWindowPos( hwnd, 0, rect.left, rect.top,
                                        rect.right - rect.left, rect.bottom - rect.top,
                                        hittest == HTCAPTION ? SWP_NOSIZE : 0 );
#ifdef __ORBIS__
                    clock_gettime( CLOCK_MONOTONIC_RAW, &after );
                    if (++moves <= 100)
                        fprintf( stderr, "PWBOOT move_loop_setpos n=%u took_us=%lld\\n", moves,
                                 (long long)(after.tv_sec - before.tv_sec) * 1000000 + (after.tv_nsec - before.tv_nsec) / 1000 );
#endif''','SetWindowPos timing in the move loop.')
# (W061's input_pull log was removed in W151: it fell on the first Start menu opening.)
# W057 diagnosis: the drag moves the window about twice a second. Time each flush (copy
# into the window's content, compose, present) and report every 100.
revise('dlls/win32u/ps5drv.c','''/* screen_lock held: a resized window keeps what still fits until it repaints */''','''static unsigned long long ps5_now_us(void)
{
    struct timespec ts;
    clock_gettime( CLOCK_MONOTONIC_RAW, &ts );
    return ts.tv_sec * 1000000ull + ts.tv_nsec / 1000;
}

/* screen_lock held: a resized window keeps what still fits until it repaints */''','Monotonic microseconds.')
revise('dlls/win32u/ps5drv.c','''        if (window->pixels && intersect_rect( &target, &target, &area ))
        {''','''        if (window->pixels && intersect_rect( &target, &target, &area ))
        {
            static unsigned long long flush_us, flush_max, flush_pixels, flush_start;
            static UINT flushes;
            unsigned long long start = ps5_now_us(), spent;''','Flush timing start.')
revise('dlls/win32u/ps5drv.c','''            OffsetRect( &target, window->visible.left, window->visible.top );
            compose_rect( &target );
            present_screen();''','''            OffsetRect( &target, window->visible.left, window->visible.top );
            compose_rect( &target );
            present_screen();
            spent = ps5_now_us() - start;
            if (!flushes) flush_start = start;
            flushes++;
            flush_us += spent;
            if (spent > flush_max) flush_max = spent;
            flush_pixels += (unsigned long long)(target.right - target.left) * (target.bottom - target.top);
            if (!(flushes % 100))
            {
                fprintf( stderr, "PWBOOT flush_stats n=%u avg_us=%llu max_us=%llu avg_px=%llu over_ms=%llu\\n", flushes,
                         flush_us / 100, flush_max, flush_pixels / 100, (start - flush_start) / 1000 );
                flush_us = flush_max = flush_pixels = 0;
                flush_start = start;
            }''','Flush timing report.')
# W065: win32u accumulates mouse motion per thread (accum_mouse_motion) and sends it
# only when the target window changes or a button or wheel input arrives. In a drag
# the window under the pointer stays the same, so W064 showed every held move kept
# back and the move loop got the first WM_MOUSEMOVE only with the release. Pointer
# moves are sent at once, one per mouse sample.
revise('dlls/win32u/ps5drv.c','''            send_mouse( window_at( cursor.x, cursor.y ), MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, cursor.x, cursor.y );
            {
                static UINT pointer_moves;''','''            send_mouse( window_at( cursor.x, cursor.y ),
                        MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_MOVE_NOCOALESCE, cursor.x, cursor.y );
            {
                static UINT pointer_moves;''','Pointer moves are not accumulated.')
# W071 (H2): Mesa's RADV on GNM is linked into the same ELF (W070); win32u takes its
# entry points from there instead of dlopen("libvulkan.so.1"). The handle win32u keeps
# only says that Vulkan is present. pw_vk_get_instance_proc_addr (native/wine_vk_runtime.c)
# also answers vkGetDeviceProcAddr, which RADV's ICD lookup does not.
revise('dlls/win32u/vulkan.c','''#ifdef SONAME_LIBVULKAN
    vulkan_handle = dlopen( SONAME_LIBVULKAN, RTLD_NOW );
    if (!vulkan_handle) ERR( "Failed to load %s\\n", SONAME_LIBVULKAN );
#else
    ERR( "Wine was built without Vulkan support.\\n" );
#endif
    if (!vulkan_handle) return;

#define LOAD_FUNCPTR( f )                                                                          \\
    if (!(p_##f = dlsym( vulkan_handle, #f )))                                                     \\
    {                                                                                              \\
        ERR( "Failed to find " #f "\\n" );                                                          \\
        dlclose( vulkan_handle );                                                                  \\
        vulkan_handle = NULL;                                                                      \\
        return;                                                                                    \\
    }

    LOAD_FUNCPTR( vkGetDeviceProcAddr );
    LOAD_FUNCPTR( vkGetInstanceProcAddr );
#undef LOAD_FUNCPTR
''','''#ifdef __ORBIS__
    {
        /* set by the hardware launcher (native/wine_hardware.c); the Wine-only links
         * (tools/link-wine-boot.py) have no RADV and leave it NULL: no Vulkan */
        extern PFN_vkGetInstanceProcAddr pw_vk_instance_proc_addr;
        static char linked_radv;
        if (!pw_vk_instance_proc_addr)
        {
            ERR( "PWVK no RADV linked into this ELF\\n" );
            return;
        }
        p_vkGetInstanceProcAddr = pw_vk_instance_proc_addr;
        p_vkGetDeviceProcAddr = (PFN_vkGetDeviceProcAddr)pw_vk_instance_proc_addr( NULL, "vkGetDeviceProcAddr" );
        vulkan_handle = &linked_radv;
        ERR( "PWVK win32u uses the linked RADV: vkGetDeviceProcAddr %p\\n", p_vkGetDeviceProcAddr );
    }
#else
#ifdef SONAME_LIBVULKAN
    vulkan_handle = dlopen( SONAME_LIBVULKAN, RTLD_NOW );
    if (!vulkan_handle) ERR( "Failed to load %s\\n", SONAME_LIBVULKAN );
#else
    ERR( "Wine was built without Vulkan support.\\n" );
#endif
    if (!vulkan_handle) return;

#define LOAD_FUNCPTR( f )                                                                          \\
    if (!(p_##f = dlsym( vulkan_handle, #f )))                                                     \\
    {                                                                                              \\
        ERR( "Failed to find " #f "\\n" );                                                          \\
        dlclose( vulkan_handle );                                                                  \\
        vulkan_handle = NULL;                                                                      \\
        return;                                                                                    \\
    }

    LOAD_FUNCPTR( vkGetDeviceProcAddr );
    LOAD_FUNCPTR( vkGetInstanceProcAddr );
#undef LOAD_FUNCPTR
#endif
''','Vulkan comes from the RADV linked into the ELF.')
# W072 (H3): swapchains are Mesa's headless ones (the user driver has no VulkanInit, so
# win32u's null driver makes VK_EXT_headless_surface surfaces). On the PS4 Mesa leaves each
# presented image in a buffer the CPU reads (tools/vk-h0/patch-mesa-wsi.py) and records it
# (native/wine_vk_runtime.c); after the host present, the image is drawn into the
# swapchain's window with GDI, scaled to its client area, and the compositor shows it.
revise('dlls/win32u/vulkan.c','''static VkResult win32u_vkQueuePresentKHR( VkQueue client_queue, const VkPresentInfoKHR *client_present_info )
{''','''#ifdef __ORBIS__
/* platform/ps4/pw_wine_unixlibs.c; set when RADV is linked */
extern int (*pw_vk_last_frame)( const void *swapchain, const void **pixels, UINT *pitch, UINT *width,
                                UINT *height, int *format );
/* ps5drv.c (W152) */
extern BOOL ps5_vulkan_frame( HWND hwnd, UINT64 swapchain, const void *pixels, UINT pitch, UINT width, UINT height,
                              BOOL rgba, const RECT *client );
/* W242: platform/ps4/pw_wine_sink_ps4.c; the overlay counts MangoHud only for the window in front */
extern void pw_wine_vk_window_presented( unsigned long long hwnd );

static void pw_vk_show_frame( HWND hwnd, VkSwapchainKHR host_swapchain )
{
    static UINT shown;
    static LONGLONG draw_ticks, draw_count;  /* W074: time of the GDI copy */
    LARGE_INTEGER start, end, frequency;
    BITMAPINFO info = {{sizeof(BITMAPINFOHEADER)}};
    UINT pitch, width, height, i;
    const void *pixels;
    void *converted = NULL;
    int format, drawn = 0;
    RECT rect;
    HDC hdc;

    if (!pw_vk_last_frame || !pw_vk_last_frame( (const void *)(UINT_PTR)host_swapchain, &pixels, &pitch, &width,
                                                &height, &format ))
        return;
    pw_wine_vk_window_presented( (unsigned long long)(UINT_PTR)hwnd );  /* W242 */
    NtQueryPerformanceCounter( &start, &frequency );
    /* W152: while the GPU stacks the windows the image is a layer over the client area, read where
     * the WSI left it: no conversion, no GDI copy, no CPU composition */
    if (get_client_rect( hwnd, &rect, get_dpi_for_window( hwnd ) ))
    {
        RECT client = rect;
        map_window_points( hwnd, 0, (POINT *)&client, 2, get_dpi_for_window( hwnd ) );
        if (ps5_vulkan_frame( hwnd, (UINT64)(UINT_PTR)host_swapchain, pixels, pitch, width, height,
                              format == VK_FORMAT_R8G8B8A8_UNORM || format == VK_FORMAT_R8G8B8A8_SRGB, &client ))
        {
            NtQueryPerformanceCounter( &end, NULL );
            draw_ticks += end.QuadPart - start.QuadPart;
            draw_count++;
            if (++shown <= 5 || !(shown % 60))
            {
                ERR( "PWVK show_frame n=%u hwnd=%p %ux%u pitch=%u format=%d client=%s path=gpu_layer us=%lld\\n", shown, hwnd,
                     width, height, pitch, format, wine_dbgstr_rect( &client ),
                     frequency.QuadPart ? draw_ticks * 1000000 / frequency.QuadPart / draw_count : -1 );
                draw_ticks = draw_count = 0;
            }
            return;
        }
    }
    if (format == VK_FORMAT_R8G8B8A8_UNORM || format == VK_FORMAT_R8G8B8A8_SRGB)
    {
        /* GDI takes BGRA */
        const UINT *src = pixels;
        UINT *dst;
        if (!(converted = malloc( (size_t)pitch * height ))) return;
        dst = converted;
        for (i = 0; i < pitch / 4 * height; i++)
            dst[i] = (src[i] & 0xff00ff00) | ((src[i] & 0xff) << 16) | ((src[i] >> 16) & 0xff);
        pixels = converted;
    }
    info.bmiHeader.biWidth = pitch / 4;
    info.bmiHeader.biHeight = -(int)height;
    info.bmiHeader.biPlanes = 1;
    info.bmiHeader.biBitCount = 32;
    info.bmiHeader.biCompression = BI_RGB;
    if (get_client_rect( hwnd, &rect, get_dpi_for_window( hwnd ) ) &&
        (hdc = NtUserGetDCEx( hwnd, 0, DCX_CACHE | DCX_USESTYLE )))
    {
        drawn = NtGdiStretchDIBitsInternal( hdc, 0, 0, rect.right - rect.left, rect.bottom - rect.top, 0, 0, width, height,
                                            pixels, &info, DIB_RGB_COLORS, SRCCOPY, sizeof(info), pitch * height, NULL );
        NtUserReleaseDC( hwnd, hdc );
    }
    NtQueryPerformanceCounter( &end, NULL );
    draw_ticks += end.QuadPart - start.QuadPart;
    draw_count++;
    if (++shown <= 5 || !(shown % 60))
    {
        ERR( "PWVK show_frame n=%u hwnd=%p %ux%u pitch=%u format=%d client=%s drawn=%d gdi_us=%lld\\n", shown, hwnd,
             width, height, pitch, format, wine_dbgstr_rect( &rect ), drawn,
             frequency.QuadPart ? draw_ticks * 1000000 / frequency.QuadPart / draw_count : -1 );
        draw_ticks = draw_count = 0;
    }
    free( converted );
}
#endif

static VkResult win32u_vkQueuePresentKHR( VkQueue client_queue, const VkPresentInfoKHR *client_present_info )
{''','Show presented Vulkan images in their windows.')
revise('dlls/win32u/vulkan.c','''        RECT client_rect;

        client_surface_present( surface->client );
''','''        RECT client_rect;

#ifdef __ORBIS__
        if (swapchain_res >= VK_SUCCESS) pw_vk_show_frame( surface->hwnd, swapchains[i] );
#endif
        client_surface_present( surface->client );
''','Each present shows its image.')
# W152: a swapchain's last image may be a GPU layer (ps5drv.c ps5_vulkan_frame); it stops being one
# before the host swapchain, and with it the image's memory, goes away.
revise('dlls/win32u/vulkan.c','''    device->p_vkDestroySwapchainKHR( device->host.device, swapchain->obj.host.swapchain, NULL );''','''#ifdef __ORBIS__
    extern void ps5_vulkan_forget( HWND hwnd, UINT64 swapchain );  /* ps5drv.c */
    ps5_vulkan_forget( swapchain->surface->hwnd, (UINT64)(UINT_PTR)swapchain->obj.host.swapchain );
#endif
    device->p_vkDestroySwapchainKHR( device->host.device, swapchain->obj.host.swapchain, NULL );''',
       'The swapchain image stops being a GPU layer before it is freed.')
# W223: the present-scaling struct of a swapchain whose size differs from its window goes in front
# of the client's pNext chain instead of replacing it. DXVK's d3d8/d3d9 chain
# VkImageFormatListCreateInfo with VK_SWAPCHAIN_CREATE_MUTABLE_FORMAT_BIT_KHR; without the list RADV
# read address 0 in wsi_configure_image (W221, GTA Vice City's 640x480 swapchain).
revise('dlls/win32u/vulkan.c','''        create_info_host.pNext = &scaling;''','''        scaling.pNext = create_info_host.pNext;
        create_info_host.pNext = &scaling;''',
       'Present scaling extends the client pNext chain.')
# W154: while a window is dragged its program presents nothing new (the move loop runs in its
# thread), and in W153 its last Vulkan image stayed where it was presented while the frame moved
# and showed the window's white client. The image follows the client area (new_rects->client,
# screen coordinates like visible) on every move or resize, scaled until the next present.
revise('dlls/win32u/ps5drv.c','''        window->visible = new_rects->visible;
        window->shown = shown;
        if (was_shown && (!shown''','''        window->visible = new_rects->visible;
        window->shown = shown;
        window->client = new_rects->client;
        if (window->vk_pixels) window->vk_rect = fit_image( &window->client, window->vk_width, window->vk_height );
        if (was_shown && (!shown''','The Vulkan image moves with its window.')
# FreeType belongs to the same Orbis ELF; use real linked functions, not dlopen.
ft=json.loads((ROOT/'build/freetype-ps4/manifest.json').read_text())
if sha(ROOT/ft['library'])!=ft['sha256']:raise SystemExit('FreeType library changed')
manifest['freetype']=ft
# W118: win32u's own Vulkan instance is a 1.0 instance (only the KHR entry points of
# VK_KHR_get_physical_device_properties2 resolve). The WoW64-only placed-map branch called
# the core vkGetPhysicalDeviceProperties2 through the instance, a NULL pointer there: the
# first PE32 GUI program (W116/W117) jumped to address 0 right after Vulkan initialised.
revise('dlls/win32u/vulkan.c','''            instance->p_vkGetPhysicalDeviceProperties2( host_physical_device, &props );''',
       '''            instance->p_vkGetPhysicalDeviceProperties2KHR( host_physical_device, &props );''',
       'WoW64 placed-map query through the KHR entry point the 1.0 instance resolves.')
# W169: freeing a placed mapping (32-bit programs). RADV's placed map is a second, CPU-only mapping
# of the buffer's direct memory at Wine's reserved address (tools/vk-h0/patch-mesa-placed.py), and
# its unmap leaves that alias for Wine to release. Wine's MEM_RELEASE then maps its reservation
# over it again; if that does not replace the direct-memory alias, or the release of the direct
# memory left a hole there, Wine's view of the range is wrong. W167/W168: at the end of a
# SuperMarioKart race (when the game frees its resources) the 32-bit heap committed a large block
# there (heap_allocate_large) and faulted writing its header. The alias is unmapped here first, so
# Wine releases a range that holds nothing.
revise('dlls/win32u/vulkan.c','''    if (memory->vm_map)
    {
        SIZE_T alloc_size = 0;
        NtFreeVirtualMemory( GetCurrentProcess(), &memory->vm_map, &alloc_size, MEM_RELEASE );
    }''','''    if (memory->vm_map)
    {
        SIZE_T alloc_size = 0;
#ifdef __ORBIS__
        if (physical_device->map_placed_align)
        {
            extern int munmap( void *addr, size_t length );
            extern int *__error( void );  /* errno, which this file's includes do not declare */
            size_t length = (memory->size + 0x3fff) & ~(size_t)0x3fff;  /* the PS4's 16 KiB map unit */
            if (munmap( memory->vm_map, length ))
                ERR( "PWVK placed unmap of %p (%#zx bytes) failed, errno %d\\n", memory->vm_map, length, *__error() );
        }
#endif
        NtFreeVirtualMemory( GetCurrentProcess(), &memory->vm_map, &alloc_size, MEM_RELEASE );
    }''','Unmap the placed alias before Wine releases its reservation.')
# W125: RADV advertises VK_KHR_present_id/present_wait (and their 2 versions), but the headless
# WSI that the console's presentation uses (tools/vk-h0/patch-mesa-wsi.py) implements no wait:
# DXVK's presenter called vkWaitForPresentKHR and jumped to address 0 (W124, status 3 after its
# first frame). They are not offered to Windows programs; DXVK then paces without them.
revise('dlls/win32u/vulkan.c','''    extensions.has_VK_KHR_win32_keyed_mutex = extensions.has_VK_KHR_timeline_semaphore &&''',
       '''    extensions.has_VK_KHR_present_id = extensions.has_VK_KHR_present_id2 = 0;
    extensions.has_VK_KHR_present_wait = extensions.has_VK_KHR_present_wait2 = 0;
    extensions.has_VK_KHR_win32_keyed_mutex = extensions.has_VK_KHR_timeline_semaphore &&''',
       'Hide present id/wait: the headless WSI has no wait for present.')
# W189: Win32 sharing of Vulkan memory and semaphores. win32u implements an exported allocation
# through the driver's OPAQUE_FD export (vkGetMemoryFdKHR), and the console's RADV winsys has no
# dma-buf export (ac_ps4_drm.c ac_drm_bo_export returns -ENOSYS). Every shared allocation then
# failed as VK_ERROR_OUT_OF_HOST_MEMORY: W183, DXVK D3D11 in a 64-bit title, "DxvkMemoryAllocator:
# Memory allocation failed Size 4096" with empty heaps. 32-bit titles run wined3d, which does not
# use these. Without them, DXVK refuses shared resources with an error code instead of failing a
# plain allocation.
revise('dlls/win32u/vulkan.c','''    /* filter out unsupported client device extensions */''',
       '''#ifdef __ORBIS__
    extensions.has_VK_KHR_external_memory_win32 = 0;
    extensions.has_VK_KHR_external_semaphore_win32 = 0;
    extensions.has_VK_KHR_win32_keyed_mutex = 0;
#endif
    /* filter out unsupported client device extensions */''',
       'No Win32 memory/semaphore sharing: the PS4 winsys cannot export an fd.')
revise('dlls/win32u/freetype.c','#include "config.h"',
       '#include "config.h"\n#ifdef __ORBIS__\n#define HAVE_FT2BUILD_H 1\n#define SONAME_LIBFREETYPE "static-orbis-freetype"\n#endif',
       'Enable the real FreeType backend only in the Orbis overlay.')
revise('dlls/win32u/freetype.c','    ft_handle = dlopen(SONAME_LIBFREETYPE, RTLD_NOW);',
       '    ft_handle = &library;', 'Static library lifetime equals runtime lifetime.')
revise('dlls/win32u/freetype.c',
       '#define LOAD_FUNCPTR(f) if((p##f = dlsym(ft_handle, #f)) == NULL){WARN("Can\'t find symbol %s\\n", #f); goto sym_not_found;}',
       '#define LOAD_FUNCPTR(f) do { p##f = f; if (!p##f) goto sym_not_found; } while (0);',
       'Resolve every required function at link time; keep initialization failures real.')
revise('dlls/win32u/ps5drv.c','''            input.ki.wScan = NtUserMapVirtualKeyEx( event.code, MAPVK_VK_TO_VSC, NtUserGetKeyboardLayout( 0 ));
            input.ki.dwFlags = event.down ? 0 : KEYEVENTF_KEYUP;
''','''            input.ki.wScan = NtUserMapVirtualKeyEx( event.code, MAPVK_VK_TO_VSC, NtUserGetKeyboardLayout( 0 ));
            input.ki.dwFlags = event.down ? 0 : KEYEVENTF_KEYUP;
            switch (event.code)
            {
            case VK_LEFT: case VK_UP: case VK_RIGHT: case VK_DOWN: case VK_INSERT: case VK_DELETE:
            case VK_HOME: case VK_END: case VK_PRIOR: case VK_NEXT: case VK_RCONTROL: case VK_RMENU:
            case VK_DIVIDE: case VK_LWIN: case VK_RWIN: case VK_APPS:
                input.ki.dwFlags |= KEYEVENTF_EXTENDEDKEY;
                break;
            }
''','''Keys that a PC keyboard sends with an E0 prefix go as extended keys: DirectInput tells
DIK_RIGHT from DIK_NUMPAD6 by that flag. They are listed by virtual key because the layout
maps VK_RIGHT back to the numpad scan code 0x4d first, without E0, also with
MAPVK_VK_TO_VSC_EX (W141).''')
revise('dlls/win32u/ps5drv.c','''    if (!(screen = calloc( (size_t)screen_width * screen_height, sizeof(*screen) )))
''','''#ifdef __ORBIS__
    {
        extern void *pw_wine_screen_memory( unsigned int width, unsigned int height );
        screen = pw_wine_screen_memory( screen_width, screen_height );
    }
#endif
    if (!screen && !(screen = calloc( (size_t)screen_width * screen_height, sizeof(*screen) )))
''','''The desktop comes from the sink when it has GPU-readable memory for it (W142: the GPU
reads it to draw the output), else from calloc.''')
# W144 (phase 6, step 2): the GPU stacks the windows.
revise('dlls/win32u/ps5drv.c','''static UINT32 *background;  /* screen-sized wallpaper, or NULL for black */
''','''static UINT32 *background;  /* screen-sized wallpaper, or NULL for black */
/* W144: while the sink draws through the GPU, window contents and the wallpaper live in memory
 * the GPU reads and every present hands it the stack (bottom first); compose_rect and the
 * screen buffer are then left alone, and come back when the GPU path fails. The layout of
 * struct pw_wine_layer in platform/ps4/pw_wine_sink_ps4.c. */
struct ps5_layer
{
    const UINT32 *pixels;
    INT left, top, right, bottom;   /* screen coordinates */
    UINT stride;                    /* in pixels */
    UINT flags;                     /* W152: PS5_LAYER_IMAGE, PS5_LAYER_RGBA */
    UINT source_width, source_height;   /* scaled to the rect */
};
#define PS5_LAYER_IMAGE 1   /* a Vulkan image outside the pool, by address */
#define PS5_LAYER_RGBA 2    /* its words are R,G,B,A */
static BOOL gpu_layers;
static BOOL gpu_images;     /* W152: Vulkan frames are GPU layers */
extern int pw_wine_layers( void );
extern int pw_wine_layer_images( void );
extern void *pw_wine_layer_alloc( size_t bytes );
extern int pw_wine_layer_free( void *pixels );
extern int pw_wine_present_layers( const struct ps5_layer *layers, unsigned int count,
                                   unsigned int width, unsigned int height );
''','''Declarations for the GPU window stacking (W144).''')
revise('dlls/win32u/ps5drv.c','''    if (!intersect_rect( &clip, &clip, rect )) return;
    width = clip.right - clip.left;
''','''    if (gpu_layers) return;  /* the GPU stacks the windows at present (W144) */
    if (!intersect_rect( &clip, &clip, rect )) return;
    width = clip.right - clip.left;
''','''With the GPU stacking the windows the CPU screen is not composed (W144).''')
revise('dlls/win32u/ps5drv.c','''/* screen_lock held: a resized window keeps what still fits until it repaints */
static void resize_pixels( struct ps5_window *window, INT width, INT height )
{
    UINT32 *pixels = calloc( (size_t)width * height, sizeof(*pixels) );
''','''/* W145: a pixel no flush wrote yet. compose_rect only redraws flushed rects, so a part of a
 * window that never paints (W144: a 3-5 pixel margin around windows and menus) kept what was
 * under it; the GPU draws whole layers and showed those zeroed pixels as a black frame. Window
 * pixels start as this value and the shader (native/hw_sink_gpu/screen.frag) looks through it.
 * GDI writes 32-bit DIB pixels with alpha 0, so painted pixels do not take this value. */
#define PS5_UNPAINTED 0x01ff00ffu

/* screen_lock held: back to composing on the CPU, from a whole screen (W144) */
static void leave_layers( const char *why )
{
    RECT all = {0, 0, screen_width, screen_height};
    UINT i;
    size_t p, count;

    if (!gpu_layers) return;
    gpu_layers = gpu_images = FALSE;
    fprintf( stderr, "PWBOOT gpu_layers_off %s: CPU composition\\n", why );
    /* Vulkan frames go back to GDI from the next present (ps5_vulkan_frame) */
    for (i = 0; i < window_count; i++) windows[i].vk_pixels = NULL;
    for (i = 0; i < window_count; i++)
        for (p = 0, count = (size_t)windows[i].pixels_width * windows[i].pixels_height; windows[i].pixels && p < count; p++)
            if (windows[i].pixels[p] == PS5_UNPAINTED) windows[i].pixels[p] = 0;
    compose_rect( &all );
}

/* screen_lock held: pixels for a window or the wallpaper; GPU-readable and unpainted while the
 * GPU stacks the windows, else zeroed */
static UINT32 *alloc_pixels( size_t count )
{
    UINT32 *pixels;
    size_t i;

    if (gpu_layers)
    {
        if ((pixels = pw_wine_layer_alloc( count * sizeof(*pixels) )))
        {
            for (i = 0; i < count; i++) pixels[i] = PS5_UNPAINTED;
            return pixels;
        }
        leave_layers( "alloc" );
    }
    return calloc( count, sizeof(*pixels) );
}

static void free_pixels( UINT32 *pixels )
{
    if (pixels && !pw_wine_layer_free( pixels )) free( pixels );
}

/* screen_lock held: a resized window keeps what still fits until it repaints */
static void resize_pixels( struct ps5_window *window, INT width, INT height )
{
    UINT32 *pixels = alloc_pixels( (size_t)width * height );
''','''Window pixels come from the GPU pool while the GPU stacks the windows (W144).''')
revise('dlls/win32u/ps5drv.c','''    free( window->pixels );
    window->pixels = pixels;
''','''    free_pixels( window->pixels );
    window->pixels = pixels;
''','''Pool pixels go back to the pool (W144).''')
revise('dlls/win32u/ps5drv.c','''        free( window->pixels );
        memmove( &windows[index]''','''        free_pixels( window->pixels );
        memmove( &windows[index]''','''Pool pixels go back to the pool (W144).''')
revise('dlls/win32u/ps5drv.c','''        free( windows[i].pixels );''','''        free_pixels( windows[i].pixels );''',
       '''Pool pixels go back to the pool (W144).''')
revise('dlls/win32u/ps5drv.c','''/* screen_lock held */
static void present_screen(void)
{
''','''/* screen_lock held */
static void present_screen(void)
{
    if (gpu_layers)
    {
        /* the stack compose_rect draws: each window's content clipped to its visible rect */
        struct ps5_layer layers[2 * PS5_MAX_WINDOWS + 1];
        UINT i, count = 0, view_width = screen_width, view_height = screen_height;
        static int fit = -1;
        static UINT area_width, area_height;

        /* W155: a 32-bit title (WINE_PS5_FIT, native/wine_hardware.c) shows only the area its windows
         * cover, when it starts at the desktop's corner: SuperMarioKart's 800x600 window at 0,0 was
         * drawn 1:1 with a black column to its right, and now fills the screen (the sink keeps the
         * aspect). The pointer stays inside that area. */
        if (fit < 0) fit = getenv( "WINE_PS5_FIT" ) != NULL;
        if (fit)
        {
            RECT area = {0, 0, 0, 0};
            for (i = 0; i < window_count; i++)
                if (windows[i].shown) union_rect( &area, &area, &windows[i].visible );
            /* W156: not for small windows (W155: a 116x27 one at 0,0 filled the screen for a moment) */
            if (!area.left && !area.top && area.right >= 320 && area.bottom >= 200)
            {
                view_width = min( (UINT)area.right, screen_width );
                view_height = min( (UINT)area.bottom, screen_height );
            }
            if (view_width != area_width || view_height != area_height)
            {
                extern int pw_wine_pointer_area( unsigned int width, unsigned int height );  /* the sink */
                int bounded;
                area_width = view_width;
                area_height = view_height;
                bounded = pw_wine_pointer_area( view_width, view_height );
                fprintf( stderr, "PWBOOT fit_view %ux%u pointer=%d\\n", view_width, view_height, bounded );
            }
        }
        if (background)
            layers[count++] = (struct ps5_layer){background, 0, 0, screen_width, screen_height, screen_width,
                                                 0, screen_width, screen_height};
        for (i = 0; i < window_count; i++)
        {
            const struct ps5_window *window = &windows[i];
            INT right = min( window->visible.right, window->visible.left + window->pixels_width );
            INT bottom = min( window->visible.bottom, window->visible.top + window->pixels_height );

            if (!window->shown) continue;
            if (window->pixels)
                layers[count++] = (struct ps5_layer){window->pixels, window->visible.left, window->visible.top,
                    right, bottom, window->pixels_width, 0, right - window->visible.left, bottom - window->visible.top};
            /* W152: its Vulkan frame over the client area, right above the window */
            if (window->vk_pixels)
                layers[count++] = (struct ps5_layer){window->vk_pixels, window->vk_rect.left, window->vk_rect.top,
                    window->vk_rect.right, window->vk_rect.bottom, window->vk_stride, PS5_LAYER_IMAGE | window->vk_flags,
                    window->vk_width, window->vk_height};
        }
        /* the sink takes 65 layers (pw_wine_sink_ps4.c MAX_LAYERS) */
        if (count <= 65 && !pw_wine_present_layers( layers, count, view_width, view_height )) return;
        leave_layers( "present" );
    }
''','''Present the window stack to the GPU when it draws it (W144).''')
revise('dlls/win32u/ps5drv.c','''static BOOL ps5_surface_flush( struct window_surface *surface, const RECT *rect, const RECT *dirty,
''','''/* W152: a Vulkan swapchain of hwnd presented the image at pixels (left by Mesa's headless WSI
 * where the GPU reads it, vulkan.c pw_vk_show_frame); client is the window's client area in
 * screen coordinates. While the GPU stacks the windows the image becomes a layer over that area
 * and the frame is presented; FALSE when it is not taken, and vulkan.c draws it with GDI. */
/* W156: where a width x height image goes in a client area: as large as fits, keeping its
 * proportions, centred. A game that sets an emulated 800x600 mode has a client area covering
 * the screen and an 800x600 image (W155: drawn in the corner, as the program's coordinates
 * say); a window's own image fills its client area. */
static RECT fit_image( const RECT *client, UINT width, UINT height )
{
    RECT rect = *client;
    INT w = client->right - client->left, h = client->bottom - client->top;

    if (w <= 0 || h <= 0 || !width || !height) return rect;
    if ((LONGLONG)w * height > (LONGLONG)h * width)
    {
        INT fitted = (INT)((LONGLONG)h * width / height);
        rect.left += (w - fitted) / 2;
        rect.right = rect.left + fitted;
    }
    else
    {
        INT fitted = (INT)((LONGLONG)w * height / width);
        rect.top += (h - fitted) / 2;
        rect.bottom = rect.top + fitted;
    }
    return rect;
}

BOOL ps5_vulkan_frame( HWND hwnd, UINT64 swapchain, const void *pixels, UINT pitch, UINT width, UINT height,
                       BOOL rgba, const RECT *client )
{
    struct ps5_window *window;
    BOOL taken = FALSE, child = FALSE;

    if (!pixels || pitch % 4 || !width || !height) return FALSE;
    pthread_mutex_lock( &screen_lock );
    /* W229: the image of a child window (quartz's video window in its game window, W227) is a
     * layer of its top-level window, over the child's area */
    if (gpu_images && !(window = find_window( hwnd )) &&
        (window = find_window( NtUserGetAncestor( hwnd, GA_ROOT ) )))
        child = TRUE;
    if (gpu_images && window)
    {
        window->vk_pixels = pixels;
        window->vk_stride = pitch / 4;
        window->vk_width = width;
        window->vk_height = height;
        window->vk_flags = rgba ? PS5_LAYER_RGBA : 0;
        /* W156: the client area ps5drv knows is in screen coordinates; the one vulkan.c passes is in
         * the program's, which differ under an emulated display mode */
        window->vk_rect = fit_image( child || IsRectEmpty( &window->client ) ? client : &window->client, width, height );
        window->vk_swapchain = swapchain;
        present_screen();
        taken = gpu_images;   /* present_screen leaves the GPU path when the sink fails */
    }
    pthread_mutex_unlock( &screen_lock );
    return taken;
}

/* W152: the swapchain is about to be destroyed (and Mesa to free its images): its last image
 * stops being a layer before that */
void ps5_vulkan_forget( HWND hwnd, UINT64 swapchain )
{
    struct ps5_window *window;

    pthread_mutex_lock( &screen_lock );
    /* W229: a child's image is on its top-level window (ps5_vulkan_frame) */
    if (!(window = find_window( hwnd ))) window = find_window( NtUserGetAncestor( hwnd, GA_ROOT ) );
    if (window && window->vk_pixels && window->vk_swapchain == swapchain)
    {
        window->vk_pixels = NULL;
        present_screen();
    }
    pthread_mutex_unlock( &screen_lock );
}

/* screen_lock held. W146: the window's shape (its region, colour key or alpha, as Wine passes
 * it to every flush: 1 bit per surface pixel, set where the window shows) as transparency:
 * pixels outside it show the layer below, as on Windows. Only while the GPU stacks the
 * windows; compose_rect has always ignored the shape. */
static void apply_shape( struct ps5_window *window, const RECT *rect, const RECT *target,
                         const BITMAPINFO *shape_info, const void *shape_bits )
{
    INT width = shape_info->bmiHeader.biWidth, height = abs( shape_info->bmiHeader.biHeight ), x, y, sx, sy;
    UINT stride = height ? shape_info->bmiHeader.biSizeImage / height : 0;
    const BYTE *bits;

    for (y = target->top; y < target->bottom; y++)
    {
        if ((sy = y - rect->top) < 0 || sy >= height) continue;
        bits = (const BYTE *)shape_bits + (size_t)(shape_info->bmiHeader.biHeight > 0 ? height - 1 - sy : sy) * stride;
        for (x = target->left; x < target->right; x++)
        {
            if ((sx = x - rect->left) < 0 || sx >= width) continue;
            if (!(bits[sx / 8] & (0x80 >> (sx & 7)))) window->pixels[y * window->pixels_width + x] = PS5_UNPAINTED;
        }
    }
}

static BOOL ps5_surface_flush( struct window_surface *surface, const RECT *rect, const RECT *dirty,
''','''Window shapes become transparency on the GPU path (W146).''')
revise('dlls/win32u/ps5drv.c','''                        (target.right - target.left) * 4 );
            OffsetRect( &target, window->visible.left, window->visible.top );''','''                        (target.right - target.left) * 4 );
            if (shape_bits && gpu_layers) apply_shape( window, rect, &target, shape_info, shape_bits );
            OffsetRect( &target, window->visible.left, window->visible.top );''','''Shape applied per flush (W146).''')
revise('dlls/win32u/ps5drv.c','''        !(background = malloc( (size_t)screen_width * screen_height * 4 )))''',
       '''        !(background = alloc_pixels( (size_t)screen_width * screen_height )))''',
       '''The wallpaper is a GPU layer too (W144).''')
revise('dlls/win32u/ps5drv.c','''    load_background( getenv( "WINE_PS5_WALLPAPER" ));
''','''    gpu_layers = pw_wine_layers() != 0;
    gpu_images = gpu_layers && pw_wine_layer_images() != 0;
    fprintf( stderr, "PWBOOT gpu_layers=%d gpu_images=%d\\n", gpu_layers, gpu_images );
    load_background( getenv( "WINE_PS5_WALLPAPER" ));
''','''The GPU stacks the windows when the sink draws through it (W144).''')
# Wnnn (W192, W195: Pale Moon as a guest, then the desktop stopped): who holds win32u's USER lock
# or ps5drv's screen lock when another thread waits for it more than 5 s. The wait goes on as before.
revise('dlls/win32u/sysparams.c','''#include <pthread.h>
#include <assert.h>''','''#include <pthread.h>
#include <assert.h>
#include <errno.h>
#include <time.h>''','Lock wait reports (Wnnn).')
revise('dlls/win32u/sysparams.c','''void user_lock(void)
{
    pthread_mutex_lock( &user_mutex );''','''/* OrbisDesk Wnnn: a wait longer than 5 s is reported with the owner's thread id (0 when it
 * records none), and again when it ends; the wait itself has no time limit */
void pw_lock_wait( pthread_mutex_t *mutex, const char *name, const volatile unsigned int *owner )
{
    static int unsupported;
    struct timespec deadline;
    unsigned int waited = 0;
    int rc;

    if (!pthread_mutex_trylock( mutex )) return;
    if (unsupported)
    {
        pthread_mutex_lock( mutex );
        return;
    }
    clock_gettime( CLOCK_REALTIME, &deadline );
    for (;;)
    {
        deadline.tv_sec += 5;
        if ((rc = pthread_mutex_timedlock( mutex, &deadline )) != ETIMEDOUT) break;
        waited += 5;
        if (waited <= 20 || !(waited % 30))
            ERR( "PWLOCK wait lock=%s tid=%04x owner=%04x waited_s=%u\\n", name,
                 (unsigned int)GetCurrentThreadId(), *owner, waited );
    }
    if (rc)
    {
        unsupported = 1;
        ERR( "PWLOCK timedlock lock=%s rc=%d: lock waits are no longer reported\\n", name, rc );
        pthread_mutex_lock( mutex );
    }
    else if (waited)
        ERR( "PWLOCK got lock=%s tid=%04x after_s=%u\\n", name, (unsigned int)GetCurrentThreadId(), waited );
}

void user_lock(void)
{
    pw_lock_wait( &user_mutex, "user", &user_lock_thread );''','USER lock waits are reported (Wnnn).')
target=overlay/'dlls/win32u/ps5drv.c';text=target.read_text()
LOCK,UNLOCK='pthread_mutex_lock( &screen_lock );','pthread_mutex_unlock( &screen_lock );'
if not text.count(LOCK) or not text.count(UNLOCK):raise SystemExit('ps5drv.c: screen_lock calls not found')
target.write_text(text.replace(LOCK,'screen_lock_enter();').replace(UNLOCK,'screen_lock_leave();'))
manifest['revisions'].append({'path':'dlls/win32u/ps5drv.c','why':'Every screen_lock call records its owner (Wnnn).'})
revise('dlls/win32u/ps5drv.c','''static pthread_mutex_t screen_lock = PTHREAD_MUTEX_INITIALIZER;
''','''static pthread_mutex_t screen_lock = PTHREAD_MUTEX_INITIALIZER;
/* OrbisDesk Wnnn: the screen lock records its owner; a wait longer than 5 s is reported
 * (pw_lock_wait, sysparams.c) */
static volatile unsigned int screen_lock_thread;
extern void pw_lock_wait( pthread_mutex_t *mutex, const char *name, const volatile unsigned int *owner );

static void screen_lock_enter(void)
{
    pw_lock_wait( &screen_lock, "ps5_screen", &screen_lock_thread );
    screen_lock_thread = GetCurrentThreadId();
}

static void screen_lock_leave(void)
{
    screen_lock_thread = 0;
    pthread_mutex_unlock( &screen_lock );
}
''','Screen lock owner (Wnnn).')
# W248 (W246 run-0003.log:100920, VLC playing a DVD: the desktop froze). Thread 0184 (VLC's Direct3D 9
# output, DXVK, its swapchain destroyed through MangoHud: "PWHUD destroy_swapchain downstream begin" at
# 100091 with no end) held ps5_screen in ps5_vulkan_forget and waited for the user lock in
# NtUserGetAncestor (VLC's video is a child window, so find_window( hwnd ) found nothing); thread 013c
# held the user lock and waited for ps5_screen ("PWLOCK wait lock=user tid=0184 owner=013c" and
# "lock=ps5_screen tid=013c owner=0184" every 5 s). Win32u calls the driver without the user lock, but
# a caller may hold it (it is recursive); ps5drv itself took it under screen_lock in three places:
# NtUserGetAncestor in ps5_vulkan_frame and ps5_vulkan_forget, is_window in purge_dead_windows. Now the
# root window is looked up before screen_lock, and is_window is asked outside it: screen_lock is never
# held while the user lock is taken, so the order is always user, then screen.
revise('dlls/win32u/ps5drv.c','''    BOOL taken = FALSE, child = FALSE;

    if (!pixels || pitch % 4 || !width || !height) return FALSE;
    screen_lock_enter();
    /* W229: the image of a child window (quartz's video window in its game window, W227) is a
     * layer of its top-level window, over the child's area */
    if (gpu_images && !(window = find_window( hwnd )) &&
        (window = find_window( NtUserGetAncestor( hwnd, GA_ROOT ) )))
        child = TRUE;''','''    BOOL taken = FALSE, child = FALSE;
    HWND root;

    if (!pixels || pitch % 4 || !width || !height) return FALSE;
    screen_lock_enter();
    /* W229: the image of a child window (quartz's video window in its game window, W227) is a
     * layer of its top-level window, over the child's area. W248: NtUserGetAncestor takes the
     * user lock, so screen_lock is left around it and the window looked for again */
    if (gpu_images && !(window = find_window( hwnd )))
    {
        screen_lock_leave();
        root = NtUserGetAncestor( hwnd, GA_ROOT );
        screen_lock_enter();
        if (gpu_images && !(window = find_window( hwnd )) && root && (window = find_window( root )))
            child = TRUE;
    }''','The root window is looked up outside screen_lock (W248).')
revise('dlls/win32u/ps5drv.c','''    struct ps5_window *window;

    screen_lock_enter();
    /* W229: a child's image is on its top-level window (ps5_vulkan_frame) */
    if (!(window = find_window( hwnd ))) window = find_window( NtUserGetAncestor( hwnd, GA_ROOT ) );''','''    struct ps5_window *window;
    HWND root;

    screen_lock_enter();
    /* W229: a child's image is on its top-level window (ps5_vulkan_frame). W248: NtUserGetAncestor
     * takes the user lock, so screen_lock is left around it and the window looked for again */
    if (!(window = find_window( hwnd )))
    {
        screen_lock_leave();
        root = NtUserGetAncestor( hwnd, GA_ROOT );
        screen_lock_enter();
        if (!(window = find_window( hwnd )) && root) window = find_window( root );
    }''','The root window is looked up outside screen_lock (W248).')
revise('dlls/win32u/ps5drv.c','''    RECT gone[PS5_MAX_WINDOWS];
    UINT i, count = 0;

    if (now - last < 200000) return;
    last = now;
    screen_lock_enter();
    for (i = 0; i < window_count; i++)
    {
        if (is_window( windows[i].hwnd )) continue;''','''    RECT gone[PS5_MAX_WINDOWS];
    HWND listed[PS5_MAX_WINDOWS], dead[PS5_MAX_WINDOWS];
    UINT i, j, count = 0, listed_count, dead_count = 0;

    if (now - last < 200000) return;
    last = now;
    /* W248: is_window takes the user lock: the windows are asked about outside screen_lock */
    screen_lock_enter();
    listed_count = window_count;
    for (i = 0; i < listed_count; i++) listed[i] = windows[i].hwnd;
    screen_lock_leave();
    for (i = 0; i < listed_count; i++) if (!is_window( listed[i] )) dead[dead_count++] = listed[i];
    if (!dead_count) return;
    screen_lock_enter();
    for (i = 0; i < window_count; i++)
    {
        for (j = 0; j < dead_count; j++) if (windows[i].hwnd == dead[j]) break;
        if (j == dead_count) continue;''','is_window is asked outside screen_lock (W248).')
# W236 (pe32-en-explorer-plan.md, W235: explorer's 32-bit guests): what each world needs in one process.
# The 32-bit user32 of explorer's 32-bit world set win32u's builtin window procs to its own; a 64-bit
# thread then called one (W235 run-0003.log: explorer's MessageBox got WM_NCCREATE at a 32-bit address).
# Each world keeps its procs, and a thread gets its own world's.
revise('dlls/win32u/class.c','''static UINT winproc_used = NTUSER_NB_PROCS;
''','''static UINT winproc_used = NTUSER_NB_PROCS;

/* W236: the builtin procs of the 32-bit user32 in a 64-bit process with a 32-bit world (explorer's PE32
 * guests); its WoW64 threads get these, the others the 64-bit ones in winproc_array */
static WINDOWPROC builtin_procs32[NTUSER_NB_PROCS];
static HINSTANCE user32_module32;
static BOOL have_procs64;
BOOL have_procs32;  /* W240: also imm.c */

static inline WINDOWPROC *pw_builtin_for_thread( WINDOWPROC *proc )
{
    if (have_procs32 && proc >= winproc_array && proc < winproc_array + NTUSER_NB_PROCS && NtCurrentTeb()->WowTebOffset)
        return &builtin_procs32[proc - winproc_array];
    return proc;
}
''','Builtin window procs per world (W236).')
revise('dlls/win32u/class.c','''    WINDOWPROC *ptr = get_winproc_ptr( proc );

    if (!ptr || ptr == WINPROC_PROC16) return proc;
''','''    WINDOWPROC *ptr = get_winproc_ptr( proc );

    if (!ptr || ptr == WINPROC_PROC16) return proc;
    ptr = pw_builtin_for_thread( ptr );  /* W236 */
    /* W239: a 32-bit thread cannot reach a proc above 4 GiB (a class of explorer's 64-bit side): it gets
     * the handle, and CallWindowProc goes through dispatch_win_proc_params */
    if (NtCurrentTeb()->WowTebOffset && (((ULONG_PTR)ptr->procA | (ULONG_PTR)ptr->procW) >> 32)) return proc;
''','Builtin window procs per world (W236).')
revise('dlls/win32u/class.c','''        params->procA = proc->procA;
        params->procW = proc->procW;
''','''        proc = pw_builtin_for_thread( proc );  /* W236 */
        params->procA = proc->procA;
        params->procW = proc->procW;
''','Builtin window procs per world (W236).')
revise('dlls/win32u/class.c','''    return (DLGPROC)(ansi ? proc->procA : proc->procW);''','''    proc = pw_builtin_for_thread( proc );  /* W236 */
    return (DLGPROC)(ansi ? proc->procA : proc->procW);''','Builtin window procs per world (W236).')
revise('dlls/win32u/class.c','''    UINT i;

    for (i = 0; i < NTUSER_NB_PROCS; i++)
    {
        winproc_array[i].procA = client_procsA[i][0];''','''    UINT i;

    /* W236: the 32-bit user32 of a 64-bit process's 32-bit world keeps its own builtin procs */
    if (have_procs64 && NtCurrentTeb()->WowTebOffset)
    {
        for (i = 0; i < NTUSER_NB_PROCS; i++)
        {
            builtin_procs32[i].procA = client_procsA[i][0];
            builtin_procs32[i].procW = client_procsW[i][0];
        }
        user32_module32 = user_module;
        have_procs32 = TRUE;
        ERR( "PWWOW win32u: the 32-bit user32 %p keeps its own builtin window procs\\n", user_module );
        return STATUS_SUCCESS;
    }
    if (!NtCurrentTeb()->WowTebOffset) have_procs64 = TRUE;
    for (i = 0; i < NTUSER_NB_PROCS; i++)
    {
        winproc_array[i].procA = client_procsA[i][0];''','Builtin window procs per world (W236).')
revise('dlls/win32u/class.c','''        (!fnid && wc->hInstance == user32_module))  /* we can't register a class for user32 */''',
'''        (!fnid && (wc->hInstance == user32_module ||  /* we can't register a class for user32 */
                   (user32_module32 && wc->hInstance == user32_module32))))  /* W236: either one */''',
'Builtin window procs per world (W236).')
revise('dlls/win32u/class.c','''            wc->hInstance     = (instance == user32_module) ? 0 : instance;''',
'''            wc->hInstance     = (instance == user32_module || (user32_module32 && instance == user32_module32)) ? 0 : instance;''',
'Builtin window procs per world (W236).')
# The 32-bit gdi32 reads the GDI handle table and DC attributes through 32-bit pointers (get_gdi_shared:
# TEB32->GdiBatchCount -> PEB64), and the world's threads use what win32u allocates for them: W235's
# gui-window32 faulted in gdi32 on a truncated pointer to explorer's table (read of 0x2070F86).
revise('dlls/win32u/win32u_private.h','''extern ULONG_PTR zero_bits;
''','''extern ULONG_PTR zero_bits;
/* W236: in a 64-bit process with a 32-bit world (explorer's PE32 guests) a WoW64 thread gets memory its
 * 32-bit code can address, as in a WoW64 process; explorer's own threads keep theirs */
static inline ULONG_PTR pw_thread_zero_bits(void)
{
    if (!zero_bits && NtCurrentTeb()->WowTebOffset) return 0xffffffff;
    return zero_bits;
}
/* and what both worlds read (the GDI handle table, DC attributes) is below 4 GiB */
static inline ULONG_PTR pw_shared_zero_bits(void)
{
    return zero_bits ? zero_bits : 0xffffffff;
}
#define zero_bits pw_thread_zero_bits()
''','zero_bits per thread; shared GDI memory below 4 GiB (W236).')
revise('dlls/win32u/syscall.c','''ULONG_PTR zero_bits = 0;''','''#undef zero_bits  /* W236: the variable itself (win32u_private.h) */
ULONG_PTR zero_bits = 0;''','zero_bits per thread; shared GDI memory below 4 GiB (W236).')
revise('dlls/win32u/gdiobj.c','''    if (NtAllocateVirtualMemory( GetCurrentProcess(), (void **)&gdi_shared, zero_bits,''',
'''    if (NtAllocateVirtualMemory( GetCurrentProcess(), (void **)&gdi_shared, pw_shared_zero_bits(),  /* W236 */''',
'zero_bits per thread; shared GDI memory below 4 GiB (W236).')
revise('dlls/win32u/dc.c','''        if (!NtAllocateVirtualMemory( GetCurrentProcess(), (void **)&bucket->entries, zero_bits,''',
'''        if (!NtAllocateVirtualMemory( GetCurrentProcess(), (void **)&bucket->entries, pw_shared_zero_bits(),  /* W236 */''',
'zero_bits per thread; shared GDI memory below 4 GiB (W236).')
# W239 (W238: gui-window32, d3d9test32 and ddraw7test32 executed at FE9ED9E0, 64-bit imm32's
# ime_ui_window_proc cut to 32 bits): the "Wine IME" class 64-bit imm32 registers globally, and any other
# class explorer's 64-bit side registers, reached a 32-bit thread. Such a proc is never called there.
revise('dlls/win32u/message.c','''    if (thread_info->msg_call_depth > MAX_WINPROC_RECURSION) return 0;
    thread_info->msg_call_depth++;
    status = KeUserModeCallback( NtUserCallWinProc, params, size, &ret_ptr, &ret_len );''','''    if (thread_info->msg_call_depth > MAX_WINPROC_RECURSION) return 0;
    /* W239: a 32-bit thread of explorer's 32-bit world cannot run a 64-bit proc (a class of the 64-bit
     * side, W238: 64-bit imm32's "Wine IME" UI window); the window gets the default behaviour */
    if (NtCurrentTeb()->WowTebOffset && (((ULONG_PTR)params->procA | (ULONG_PTR)params->procW) >> 32))
    {
        static DWORD logged_thread;
        DWORD tid = HandleToULong( NtCurrentTeb()->ClientId.UniqueThread );

        if (logged_thread != tid)
        {
            logged_thread = tid;
            ERR( "PWWOW win32u: 32-bit thread %04x window %p msg %#x: proc %p/%p is 64-bit; default_window_proc instead\\n",
                 (int)tid, params->hwnd, params->msg, params->procA, params->procW );
        }
        if (client_ret)
        {
            *client_ret = NULL;
            *client_ret_size = 0;
        }
        return default_window_proc( params->hwnd, params->msg, params->wparam, params->lparam, params->ansi );
    }
    thread_info->msg_call_depth++;
    status = KeUserModeCallback( NtUserCallWinProc, params, size, &ret_ptr, &ret_len );''',
'A 32-bit thread never calls a 64-bit window proc (W239).')
# W240 (W239: WM_IME_SETCONTEXT still reached 64-bit imm32's ime_ui_window_proc on a 32-bit thread): a 32-bit
# thread of explorer's 32-bit world has no default IME window, so its imm32 never makes an IME UI window.
revise('dlls/win32u/imm.c','''BOOL register_imm_window( HWND hwnd )
{
    struct imm_thread_data *thread_data;

    TRACE( "(%p)\\n", hwnd );

    if (disable_ime || !needs_ime_window( hwnd ))
        return FALSE;''','''BOOL register_imm_window( HWND hwnd )
{
    extern BOOL have_procs32;  /* class.c, W236 */
    struct imm_thread_data *thread_data;

    TRACE( "(%p)\\n", hwnd );

    if (disable_ime || !needs_ime_window( hwnd ))
        return FALSE;
    /* W240: the "Wine IME" class is 64-bit imm32's in explorer's process; a 32-bit thread there gets no
     * IME window (explorer has no IME composition) */
    if (have_procs32 && NtCurrentTeb()->WowTebOffset)
        return FALSE;''','No IME window for a 32-bit thread of explorer (W240).')
# W248 (W246: Vice City skipped its intro movies, which it does when its window is deactivated during
# startup): every foreground change, the first 400.
revise('dlls/win32u/input.c','''    TRACE( "hwnd %p, mouse %u, internal %u -> ret %u, previous %p\\n", hwnd, mouse, internal, ret, previous );
''','''    TRACE( "hwnd %p, mouse %u, internal %u -> ret %u, previous %p\\n", hwnd, mouse, internal, ret, previous );
    {
        static LONG logged;  /* W248 */

        if (ret && previous != hwnd && InterlockedIncrement( &logged ) <= 400)
            ERR( "PWFOCUS foreground %p (thread %04x) -> %p (thread %04x) by %04x mouse=%u\\n", previous,
                 (int)get_window_thread( previous, NULL ), hwnd, (int)new_thread_id,
                 (int)HandleToULong( NtCurrentTeb()->ClientId.UniqueThread ), mouse );
    }
''','Foreground changes are logged (W248).')
revise('dlls/win32u/window.c','''BOOL WINAPI NtUserShowWindow( HWND hwnd, INT cmd )
{
    HWND full_handle;

    if (is_broadcast(hwnd))
    {
        RtlSetLastWin32Error( ERROR_INVALID_PARAMETER );
        return FALSE;
    }
    if ((full_handle = is_current_thread_window( hwnd )))
        return show_window( full_handle, cmd );
''','''/* W248 (the user: Vice City's window stayed behind the desktop until a pad press, which also skipped its
 * movies): the first top-level window a 32-bit thread of explorer's 32-bit world shows becomes the foreground,
 * as a starting process's window does on Windows */
static void pw_world_first_window( HWND hwnd, INT cmd )
{
    extern BOOL have_procs32;  /* class.c, W236 */
    static DWORD done[64];
    static unsigned int done_count;
    DWORD tid = HandleToULong( NtCurrentTeb()->ClientId.UniqueThread );
    HWND previous;
    unsigned int i;
    BOOL set;

    if (!have_procs32 || !NtCurrentTeb()->WowTebOffset) return;
    if (cmd == SW_HIDE || cmd == SW_MINIMIZE || cmd == SW_SHOWMINIMIZED || cmd == SW_SHOWMINNOACTIVE ||
        cmd == SW_SHOWNA || cmd == SW_SHOWNOACTIVATE || cmd == SW_FORCEMINIMIZE) return;
    if ((get_window_long( hwnd, GWL_STYLE ) & (WS_CHILD | WS_VISIBLE)) != WS_VISIBLE) return;
    if (NtUserGetAncestor( hwnd, GA_PARENT ) != get_desktop_window()) return;
    for (i = 0; i < done_count; i++) if (done[i] == tid) return;
    if (done_count < ARRAY_SIZE(done)) done[done_count++] = tid;
    previous = NtUserGetForegroundWindow();
    set = previous == hwnd || set_foreground_window( hwnd, FALSE, FALSE );
    ERR( "PWWOW guest32 first window %p of thread %04x: foreground %p -> %p set=%u tick=%u\\n", hwnd, (int)tid,
         previous, NtUserGetForegroundWindow(), set, (unsigned int)NtGetTickCount() );
}

BOOL WINAPI NtUserShowWindow( HWND hwnd, INT cmd )
{
    HWND full_handle;

    if (is_broadcast(hwnd))
    {
        RtlSetLastWin32Error( ERROR_INVALID_PARAMETER );
        return FALSE;
    }
    if ((full_handle = is_current_thread_window( hwnd )))
    {
        BOOL ret = show_window( full_handle, cmd );
        pw_world_first_window( full_handle, cmd );  /* W248 */
        return ret;
    }
''','The first window of a 32-bit guest comes to the front (W248).')
# W248 (W246: SuperMarioKart in explorer's 32-bit world set an 800x600 mode and was drawn 1:1 in the corner,
# over the desktop): a window covering the display mode a game set is shown full screen, scaled by the sink.
revise('dlls/win32u/ps5drv.c','''static POINT cursor;
''','''static POINT cursor;
static RECT monitor_rect;   /* W248: the primary monitor, the display mode a game set (WindowPosChanged) */
''','The monitor rect for full screen windows (W248).')
revise('dlls/win32u/ps5drv.c','''    RECT old_visible;
    UINT i, index;

    screen_lock_enter();
    if (!(window = find_window( hwnd )) && shown''','''    RECT old_visible;
    UINT i, index;
    /* W248: the mode a game set (win32u applies it: this driver offers one mode). Taken here, outside the
     * screen lock; the taskbar's move after a mode change brings it */
    RECT monitor = get_primary_monitor_rect( (struct ratio){0} );

    screen_lock_enter();
    monitor_rect = monitor;
    if (!(window = find_window( hwnd )) && shown''','Keep the monitor rect (W248).')
revise('dlls/win32u/ps5drv.c','''        static UINT area_width, area_height;
''','''        static UINT area_width, area_height;
        INT full = -1;  /* W248: the window shown full screen */
''','The full screen window (W248).')
revise('dlls/win32u/ps5drv.c','''        if (background)
            layers[count++] = (struct ps5_layer){background, 0, 0, screen_width, screen_height, screen_width,
                                                 0, screen_width, screen_height};
        for (i = 0; i < window_count; i++)
        {''','''        /* W248: the highest shown window covering the monitor (at 0,0), with only topmost windows above it
         * (the taskbar), is shown full screen: the monitor's area alone, which the sink scales to the output
         * keeping the aspect, black around; only that window, no wallpaper or taskbar, as Windows hides the
         * taskbar for it. The pointer stays inside. A relaunched title keeps W155. */
        if (!fit && monitor_rect.right > 0 && monitor_rect.bottom > 0 && !monitor_rect.left && !monitor_rect.top)
            for (i = window_count; i-- > 0;)
            {
                const struct ps5_window *window = &windows[i];

                if (!window->shown) continue;
                if (window->visible.left <= 0 && window->visible.top <= 0 && window->visible.right >= monitor_rect.right &&
                    window->visible.bottom >= monitor_rect.bottom)
                {
                    full = i;
                    break;
                }
                if (!window->topmost) break;
            }
        if (full >= 0)
        {
            view_width = min( (UINT)monitor_rect.right, screen_width );
            view_height = min( (UINT)monitor_rect.bottom, screen_height );
        }
        if (!fit)
        {
            static HWND shown_full;
            static UINT shown_width, shown_height;
            HWND now = full >= 0 ? windows[full].hwnd : NULL;

            if (now != shown_full || (now && (view_width != shown_width || view_height != shown_height)))
            {
                extern int pw_wine_pointer_area( unsigned int width, unsigned int height );  /* the sink */
                int bounded = pw_wine_pointer_area( view_width, view_height );

                if (now) fprintf( stderr, "PWSINK fullscreen on hwnd=%p %ux%u of %ux%u pointer=%d\\n", now, view_width,
                                  view_height, screen_width, screen_height, bounded );
                else fprintf( stderr, "PWSINK fullscreen off hwnd=%p pointer=%d\\n", shown_full, bounded );
                shown_full = now;
                shown_width = view_width;
                shown_height = view_height;
            }
        }
        if (background && full < 0)
            layers[count++] = (struct ps5_layer){background, 0, 0, screen_width, screen_height, screen_width,
                                                 0, screen_width, screen_height};
        for (i = full >= 0 ? (UINT)full : 0; i < (full >= 0 ? (UINT)full + 1 : window_count); i++)
        {''','Show a window covering the monitor full screen (W248).')
# W248: every display mode change, with its thread (the guests share explorer's process; kernelbase's PWGUEST
# lines name their threads and it restores the mode when the guest ends).
revise('dlls/win32u/sysparams.c','''    if (is_virtual_desktop() || emulate_modeset) ret = DISP_CHANGE_SUCCESSFUL;
    else ret = user_driver->pChangeDisplaySettings( displays, primary_name, hwnd, flags, lparam );
''','''    if (is_virtual_desktop() || emulate_modeset) ret = DISP_CHANGE_SUCCESSFUL;
    else ret = user_driver->pChangeDisplaySettings( displays, primary_name, hwnd, flags, lparam );
    ERR( "PWSINK mode set %ux%u flags=%#x tid=%04x result=%d\\n", (UINT)displays->dmPelsWidth,
         (UINT)displays->dmPelsHeight, (UINT)flags, (UINT)GetCurrentThreadId(), (int)ret );  /* W248 */
''','Log display mode changes (W248).')
# W251 (W249: SuperMarioKart's 64 MiB placed map found no flexible memory next to explorer): the placed range is
# a reservation until RADV maps its alias there; then it is read/write.
revise('dlls/win32u/vulkan.c','''        if (NtAllocateVirtualMemory( GetCurrentProcess(), &placed_info.pPlacedAddress, zero_bits,
                                     &alloc_size, MEM_COMMIT, PAGE_READWRITE ))''','''#ifdef __ORBIS__
        /* W251: committed without access, a reservation on Orbis: RADV's alias replaces it (W169) */
        if (NtAllocateVirtualMemory( GetCurrentProcess(), &placed_info.pPlacedAddress, zero_bits,
                                     &alloc_size, MEM_COMMIT, PAGE_NOACCESS ))
#else
        if (NtAllocateVirtualMemory( GetCurrentProcess(), &placed_info.pPlacedAddress, zero_bits,
                                     &alloc_size, MEM_COMMIT, PAGE_READWRITE ))
#endif''','A placed Vulkan map takes no memory for its placeholder (W251).')
revise('dlls/win32u/vulkan.c','''        memory->vm_map = placed_info.pPlacedAddress;
''','''        memory->vm_map = placed_info.pPlacedAddress;
#ifdef __ORBIS__
        {
            /* W251: Wine's view of the range, now RADV's direct-memory alias, is read/write */
            void *addr = placed_info.pPlacedAddress;
            SIZE_T size = memory->size;
            ULONG old;
            NTSTATUS status = NtProtectVirtualMemory( GetCurrentProcess(), &addr, &size, PAGE_READWRITE, &old );

            if (status) ERR( "PWVK placed map %p protection status %#x\\n", placed_info.pPlacedAddress, (int)status );
        }
#endif
''','A placed Vulkan map takes no memory for its placeholder (W251).')
# W254 (W252: Vice City vanished during its device re-creation after the movies, the i386 MangoHud off): the Vulkan
# lifecycle calls of the threads of explorer's 32-bit world log a begin and an end.
revise('dlls/win32u/vulkan.c','''static struct vulkan_funcs vulkan_funcs =
{''','''/* W254: begin/end lines for the threads of explorer's 32-bit world (have_procs32, class.c W236) */
static inline BOOL pw32_traced(void)
{
    extern BOOL have_procs32;
    return have_procs32 && NtCurrentTeb()->WowTebOffset;
}

static VkResult pw32_vkCreateInstance( const VkInstanceCreateInfo *info, const VkAllocationCallbacks *allocator,
                                       VkInstance *instance )
{
    BOOL traced = pw32_traced();
    VkResult res;

    if (traced) ERR( "PWVK32 begin vkCreateInstance\\n" );
    res = win32u_vkCreateInstance( info, allocator, instance );
    if (traced) ERR( "PWVK32 end vkCreateInstance res=%d\\n", res );
    return res;
}

static void pw32_vkDestroyInstance( VkInstance instance, const VkAllocationCallbacks *allocator )
{
    BOOL traced = pw32_traced();

    if (traced) ERR( "PWVK32 begin vkDestroyInstance %p\\n", instance );
    win32u_vkDestroyInstance( instance, allocator );
    if (traced) ERR( "PWVK32 end vkDestroyInstance\\n" );
}

static VkResult pw32_vkCreateDevice( VkPhysicalDevice physical_device, const VkDeviceCreateInfo *info,
                                     const VkAllocationCallbacks *allocator, VkDevice *device )
{
    BOOL traced = pw32_traced();
    VkResult res;

    if (traced) ERR( "PWVK32 begin vkCreateDevice queues=%u extensions=%u\\n", info->queueCreateInfoCount,
                     info->enabledExtensionCount );
    res = win32u_vkCreateDevice( physical_device, info, allocator, device );
    if (traced) ERR( "PWVK32 end vkCreateDevice res=%d device=%p\\n", res, res ? NULL : *device );
    return res;
}

static void pw32_vkDestroyDevice( VkDevice device, const VkAllocationCallbacks *allocator )
{
    BOOL traced = pw32_traced();

    if (traced) ERR( "PWVK32 begin vkDestroyDevice %p\\n", device );
    win32u_vkDestroyDevice( device, allocator );
    if (traced) ERR( "PWVK32 end vkDestroyDevice\\n" );
}

static VkResult pw32_vkCreateWin32SurfaceKHR( VkInstance instance, const VkWin32SurfaceCreateInfoKHR *info,
                                              const VkAllocationCallbacks *allocator, VkSurfaceKHR *surface )
{
    BOOL traced = pw32_traced();
    VkResult res;

    if (traced) ERR( "PWVK32 begin vkCreateWin32SurfaceKHR hwnd=%p\\n", info->hwnd );
    res = win32u_vkCreateWin32SurfaceKHR( instance, info, allocator, surface );
    if (traced) ERR( "PWVK32 end vkCreateWin32SurfaceKHR res=%d\\n", res );
    return res;
}

static void pw32_vkDestroySurfaceKHR( VkInstance instance, VkSurfaceKHR surface, const VkAllocationCallbacks *allocator )
{
    BOOL traced = pw32_traced();

    if (traced) ERR( "PWVK32 begin vkDestroySurfaceKHR\\n" );
    win32u_vkDestroySurfaceKHR( instance, surface, allocator );
    if (traced) ERR( "PWVK32 end vkDestroySurfaceKHR\\n" );
}

static VkResult pw32_vkCreateSwapchainKHR( VkDevice device, const VkSwapchainCreateInfoKHR *info,
                                           const VkAllocationCallbacks *allocator, VkSwapchainKHR *swapchain )
{
    BOOL traced = pw32_traced();
    VkResult res;

    if (traced) ERR( "PWVK32 begin vkCreateSwapchainKHR %ux%u images=%u old=%s\\n", info->imageExtent.width,
                     info->imageExtent.height, info->minImageCount, info->oldSwapchain ? "yes" : "no" );
    res = win32u_vkCreateSwapchainKHR( device, info, allocator, swapchain );
    if (traced) ERR( "PWVK32 end vkCreateSwapchainKHR res=%d\\n", res );
    return res;
}

static void pw32_vkDestroySwapchainKHR( VkDevice device, VkSwapchainKHR swapchain, const VkAllocationCallbacks *allocator )
{
    BOOL traced = pw32_traced();

    if (traced) ERR( "PWVK32 begin vkDestroySwapchainKHR\\n" );
    win32u_vkDestroySwapchainKHR( device, swapchain, allocator );
    if (traced) ERR( "PWVK32 end vkDestroySwapchainKHR\\n" );
}

static VkResult pw32_vkAllocateMemory( VkDevice device, const VkMemoryAllocateInfo *info,
                                       const VkAllocationCallbacks *allocator, VkDeviceMemory *memory )
{
    BOOL traced = pw32_traced() && info->allocationSize >= 0x1000000;
    VkResult res;

    if (traced) ERR( "PWVK32 begin vkAllocateMemory %#llx type=%u\\n", (unsigned long long)info->allocationSize,
                     info->memoryTypeIndex );
    res = win32u_vkAllocateMemory( device, info, allocator, memory );
    if (traced || (res && pw32_traced()))
        ERR( "PWVK32 end vkAllocateMemory %#llx res=%d\\n", (unsigned long long)info->allocationSize, res );
    return res;
}

static struct vulkan_funcs vulkan_funcs =
{''','Vulkan lifecycle calls of 32-bit programs are traced (W254).')
revise('dlls/win32u/vulkan.c','''    .p_vkAllocateMemory = win32u_vkAllocateMemory,''','''    .p_vkAllocateMemory = pw32_vkAllocateMemory,  /* W254 */''',
       'Vulkan lifecycle calls of 32-bit programs are traced (W254).')
revise('dlls/win32u/vulkan.c','''    .p_vkCreateDevice = win32u_vkCreateDevice,''','''    .p_vkCreateDevice = pw32_vkCreateDevice,  /* W254 */''',
       'Vulkan lifecycle calls of 32-bit programs are traced (W254).')
revise('dlls/win32u/vulkan.c','''    .p_vkCreateInstance = win32u_vkCreateInstance,''','''    .p_vkCreateInstance = pw32_vkCreateInstance,  /* W254 */''',
       'Vulkan lifecycle calls of 32-bit programs are traced (W254).')
revise('dlls/win32u/vulkan.c','''    .p_vkCreateSwapchainKHR = win32u_vkCreateSwapchainKHR,''','''    .p_vkCreateSwapchainKHR = pw32_vkCreateSwapchainKHR,  /* W254 */''',
       'Vulkan lifecycle calls of 32-bit programs are traced (W254).')
revise('dlls/win32u/vulkan.c','''    .p_vkCreateWin32SurfaceKHR = win32u_vkCreateWin32SurfaceKHR,''','''    .p_vkCreateWin32SurfaceKHR = pw32_vkCreateWin32SurfaceKHR,  /* W254 */''',
       'Vulkan lifecycle calls of 32-bit programs are traced (W254).')
revise('dlls/win32u/vulkan.c','''    .p_vkDestroyDevice = win32u_vkDestroyDevice,''','''    .p_vkDestroyDevice = pw32_vkDestroyDevice,  /* W254 */''',
       'Vulkan lifecycle calls of 32-bit programs are traced (W254).')
revise('dlls/win32u/vulkan.c','''    .p_vkDestroyInstance = win32u_vkDestroyInstance,''','''    .p_vkDestroyInstance = pw32_vkDestroyInstance,  /* W254 */''',
       'Vulkan lifecycle calls of 32-bit programs are traced (W254).')
revise('dlls/win32u/vulkan.c','''    .p_vkDestroySurfaceKHR = win32u_vkDestroySurfaceKHR,''','''    .p_vkDestroySurfaceKHR = pw32_vkDestroySurfaceKHR,  /* W254 */''',
       'Vulkan lifecycle calls of 32-bit programs are traced (W254).')
revise('dlls/win32u/vulkan.c','''    .p_vkDestroySwapchainKHR = win32u_vkDestroySwapchainKHR,''','''    .p_vkDestroySwapchainKHR = pw32_vkDestroySwapchainKHR,  /* W254 */''',
       'Vulkan lifecycle calls of 32-bit programs are traced (W254).')
# W266 (W264: Call of Duty's "zink: could not create swapchain" after a surface for hwnd 0): the surface capabilities
# of explorer's 32-bit world, on a failure (a surface whose hwnd is no window gets VK_ERROR_SURFACE_LOST_KHR at once)
# and when the extents change.
revise('dlls/win32u/vulkan.c','''static struct vulkan_funcs vulkan_funcs =
{''','''/* W266: a 32-bit program's surface capabilities, on a failure and when the extents change */
static void pw32_trace_surface_caps( VkSurfaceKHR client_surface, VkResult res, const VkSurfaceCapabilitiesKHR *caps )
{
    static UINT last[6];
    struct surface *surface = client_surface ? surface_from_handle( client_surface ) : NULL;
    HWND hwnd = surface ? surface->hwnd : 0;
    UINT now[6];

    if (res)
    {
        ERR( "PWVK32 surface caps hwnd=%p window=%d res=%d\\n", hwnd, hwnd && NtUserIsWindow( hwnd ) ? 1 : 0, res );
        return;
    }
    now[0] = caps->currentExtent.width;
    now[1] = caps->currentExtent.height;
    now[2] = caps->minImageExtent.width;
    now[3] = caps->minImageExtent.height;
    now[4] = caps->maxImageExtent.width;
    now[5] = caps->maxImageExtent.height;
    if (!memcmp( last, now, sizeof(now) )) return;
    memcpy( last, now, sizeof(now) );
    ERR( "PWVK32 surface caps hwnd=%p window=%d current=%ux%u min=%ux%u max=%ux%u images=%u-%u\\n", hwnd,
         hwnd && NtUserIsWindow( hwnd ) ? 1 : 0, now[0], now[1], now[2], now[3], now[4], now[5],
         caps->minImageCount, caps->maxImageCount );
}

static VkResult pw32_vkGetPhysicalDeviceSurfaceCapabilitiesKHR( VkPhysicalDevice physical_device, VkSurfaceKHR surface,
                                                                VkSurfaceCapabilitiesKHR *capabilities )
{
    VkResult res = win32u_vkGetPhysicalDeviceSurfaceCapabilitiesKHR( physical_device, surface, capabilities );

    if (pw32_traced()) pw32_trace_surface_caps( surface, res, capabilities );
    return res;
}

static VkResult pw32_vkGetPhysicalDeviceSurfaceCapabilities2KHR( VkPhysicalDevice physical_device,
                                                                 const VkPhysicalDeviceSurfaceInfo2KHR *surface_info,
                                                                 VkSurfaceCapabilities2KHR *capabilities )
{
    VkResult res = win32u_vkGetPhysicalDeviceSurfaceCapabilities2KHR( physical_device, surface_info, capabilities );

    if (pw32_traced()) pw32_trace_surface_caps( surface_info->surface, res, &capabilities->surfaceCapabilities );
    return res;
}

static struct vulkan_funcs vulkan_funcs =
{''','The surface capabilities of 32-bit programs are traced (W266).')
revise('dlls/win32u/vulkan.c','''    .p_vkGetPhysicalDeviceSurfaceCapabilitiesKHR = win32u_vkGetPhysicalDeviceSurfaceCapabilitiesKHR,''',
       '''    .p_vkGetPhysicalDeviceSurfaceCapabilitiesKHR = pw32_vkGetPhysicalDeviceSurfaceCapabilitiesKHR,  /* W266 */''',
       'The surface capabilities of 32-bit programs are traced (W266).')
revise('dlls/win32u/vulkan.c','''    .p_vkGetPhysicalDeviceSurfaceCapabilities2KHR = win32u_vkGetPhysicalDeviceSurfaceCapabilities2KHR,''',
       '''    .p_vkGetPhysicalDeviceSurfaceCapabilities2KHR = pw32_vkGetPhysicalDeviceSurfaceCapabilities2KHR,  /* W266 */''',
       'The surface capabilities of 32-bit programs are traced (W266).')
# W255 (W253: Vice City ended silently as its movie's video threads ended): a swapchain's image stays a GPU layer of a
# window whose lookup failed (VMR7's video child destroyed before its swapchain); every window still showing it
# drops it before Mesa frees the image, which the sink's GPU would otherwise read.
revise('dlls/win32u/ps5drv.c','''    if (window && window->vk_pixels && window->vk_swapchain == swapchain)
    {
        window->vk_pixels = NULL;
        present_screen();
    }
    screen_lock_leave();
}''','''    {
        UINT i, cleared = 0;

        if (window && window->vk_pixels && window->vk_swapchain == swapchain)
        {
            window->vk_pixels = NULL;
            cleared++;
        }
        else  /* W255: the window is gone or shows another swapchain: any window still showing this one */
        {
            for (i = 0; i < window_count; i++)
                if (windows[i].vk_pixels && windows[i].vk_swapchain == swapchain)
                {
                    windows[i].vk_pixels = NULL;
                    cleared++;
                }
        }
        fprintf( stderr, "PWVK forget swapchain=%#llx hwnd=%p window=%p cleared=%u\\n", (unsigned long long)swapchain,
                 hwnd, window ? window->hwnd : NULL, cleared );
        if (cleared) present_screen();
    }
    screen_lock_leave();
}''','A destroyed swapchain leaves no GPU layer behind (W255).')
# W256 (Vice City showed the desktop's arrow over the game): in a full-screen window (W248) the sink draws the
# pointer only while the window under it is that window's and its cursor is the program's own (created, from a
# file, or from its modules); user32's cursors and no cursor (ShowCursor(FALSE)) hide it. ps5drv had no SetCursor.
revise('dlls/win32u/cursoricon.c','''BOOL process_wine_setcursor( HWND hwnd, HWND window, HCURSOR handle )
{''','''/* OrbisDesk W256 (ps5drv.c ps5_SetCursor): 1 when the cursor is the program's own (created by it or loaded from
 * a file: no module; or from one of its modules), 0 for user32's (LoadCursor(NULL, ...), the classes' arrow),
 * -1 for none */
int pw_cursor_kind( HCURSOR handle )
{
    static const WCHAR user32W[] = {'u','s','e','r','3','2','.','d','l','l'};
    struct cursoricon_object *obj;
    UINT length, n = ARRAY_SIZE(user32W);
    int kind = 1;

    if (!handle || !(obj = get_icon_ptr( handle ))) return -1;
    length = obj->module.Length / sizeof(WCHAR);
    if (length >= n && !wcsnicmp( obj->module.Buffer + length - n, user32W, n ) &&
        (length == n || obj->module.Buffer[length - n - 1] == '\\\\'))
        kind = 0;
    release_user_handle_ptr( obj );
    return kind;
}

BOOL process_wine_setcursor( HWND hwnd, HWND window, HCURSOR handle )
{''',"The driver can tell the program's cursors from user32's (W256).")
revise('dlls/win32u/ps5drv.c','''/* screen_lock held */
static void present_screen(void)
''','''/* W256: in a full-screen window the sink draws the pointer only with a cursor over it (W261: any; W256 wanted the
 * program's own) */
extern int pw_cursor_kind( HCURSOR handle );        /* cursoricon.c: 1 the program's, 0 user32's, -1 none */
extern void pw_wine_pointer_hidden( int hidden );   /* the sink */
static pthread_mutex_t pointer_lock = PTHREAD_MUTEX_INITIALIZER;  /* after screen_lock, before the sink's */
static HWND pointer_full, pointer_window;
static HCURSOR pointer_cursor;
static int pointer_kind = -1, pointer_hidden = -1;

/* pointer_lock held */
static void update_pointer(void)
{
    /* W261 (Portal's menus set user32's arrow): only no cursor hides it; the overlay's cursor mode can show or
     * hide it anyway (pw_wine_sink_ps4.c pointer_off) */
    int hidden = pointer_full && pointer_kind < 0;

    if (hidden == pointer_hidden) return;
    pointer_hidden = hidden;
    pw_wine_pointer_hidden( hidden );
    fprintf( stderr, "PWSINK cursor hidden=%d full=%p window=%p cursor=%p kind=%d\\n", hidden, pointer_full,
             pointer_window, pointer_cursor, pointer_kind );
}

/* screen_lock held: the window shown full screen, or NULL */
static void set_pointer_full( HWND hwnd )
{
    pthread_mutex_lock( &pointer_lock );
    pointer_full = hwnd;
    update_pointer();
    pthread_mutex_unlock( &pointer_lock );
}

/* screen_lock held */
static void present_screen(void)
''','The pointer state of a full-screen window (W256).')
revise('dlls/win32u/ps5drv.c','''                shown_full = now;
''','''                shown_full = now;
                set_pointer_full( now );  /* W256 */
''','A full-screen window changes the pointer rule (W256).')
revise('dlls/win32u/ps5drv.c','''static BOOL ps5_SetCursorPos( INT x, INT y )
''','''/* W256: the cursor of the window under the pointer (WM_WINE_SETCURSOR, on that window's thread); NULL while
 * its display count is below 0. The user lock is taken here, before pointer_lock, never under it. */
static void ps5_SetCursor( HWND hwnd, HCURSOR cursor )
{
    int kind = pw_cursor_kind( cursor );
    HWND top = hwnd ? NtUserGetAncestor( hwnd, GA_ROOT ) : NULL;

    pthread_mutex_lock( &pointer_lock );
    pointer_window = top;
    pointer_cursor = cursor;
    pointer_kind = kind;
    update_pointer();
    pthread_mutex_unlock( &pointer_lock );
}

static BOOL ps5_SetCursorPos( INT x, INT y )
''','ps5drv has SetCursor (W256).')
revise('dlls/win32u/ps5drv.c','''    .pSetCursorPos = ps5_SetCursorPos,
''','''    .pSetCursorPos = ps5_SetCursorPos,
    .pSetCursor = ps5_SetCursor,  /* W256 */
''','ps5drv has SetCursor (W256).')
# W256 (W255: the screen froze after Salir on Vice City; the terminated guest never destroyed its swapchain): the
# forget that window destruction does is logged with its reason, and the next stacks handed to the sink are listed.
revise('dlls/win32u/ps5drv.c','''static RECT monitor_rect;   /* W248: the primary monitor, the display mode a game set (WindowPosChanged) */
''','''static RECT monitor_rect;   /* W248: the primary monitor, the display mode a game set (WindowPosChanged) */
static UINT pw_stack_log;   /* W256: stacks to list after a window with a Vulkan image went */
''','The stacks after a window with a Vulkan image went are listed (W256).')
revise('dlls/win32u/ps5drv.c','''        /* the sink takes 65 layers (pw_wine_sink_ps4.c MAX_LAYERS) */
        if (count <= 65 && !pw_wine_present_layers( layers, count, view_width, view_height )) return;''','''        if (pw_stack_log)  /* W256: flags 0x1 is a Vulkan image read by address */
        {
            pw_stack_log--;
            for (i = 0; i < count; i++)
                fprintf( stderr, "PWSINK stack %u/%u pixels=%p rect=(%d,%d)-(%d,%d) flags=%#x source=%ux%u\\n", i, count,
                         layers[i].pixels, layers[i].left, layers[i].top, layers[i].right, layers[i].bottom,
                         layers[i].flags, layers[i].source_width, layers[i].source_height );
        }
        /* the sink takes 65 layers (pw_wine_sink_ps4.c MAX_LAYERS) */
        if (count <= 65 && !pw_wine_present_layers( layers, count, view_width, view_height )) return;''',
       'The stacks after a window with a Vulkan image went are listed (W256).')
revise('dlls/win32u/ps5drv.c','''        fprintf( stderr, "PWBOOT window_gone hwnd=%p\\n", windows[i].hwnd );
''','''        fprintf( stderr, "PWBOOT window_gone hwnd=%p\\n", windows[i].hwnd );
        if (windows[i].vk_pixels)  /* W256: its Vulkan image goes with the window */
        {
            fprintf( stderr, "PWVK forget swapchain=%#llx hwnd=%p reason=window_gone\\n",
                     (unsigned long long)windows[i].vk_swapchain, windows[i].hwnd );
            pw_stack_log = 3;
        }
''','A dead window takes its Vulkan image along, logged (W256).')
revise('dlls/win32u/ps5drv.c','''        UINT index = window - windows;

        free_pixels( window->pixels );''','''        UINT index = window - windows;

        if (window->vk_pixels)  /* W256: its Vulkan image goes with the window */
        {
            fprintf( stderr, "PWVK forget swapchain=%#llx hwnd=%p reason=destroy_window\\n",
                     (unsigned long long)window->vk_swapchain, hwnd );
            pw_stack_log = 3;
        }
        free_pixels( window->pixels );''','A destroyed window takes its Vulkan image along, logged (W256).')
# W265 (W263: Age of Empires II offered nothing above 800x600): display modes up to 1920x1080 above the 1280x720
# desktop, from a fixed list; ps5drv shows the full-screen window of a larger mode whole (GPU layers) and the
# pointer reaches it.
revise('dlls/win32u/sysparams.c','''    static SIZE default_sizes[] =
    {
        /* 4:3 */
        { 640,  480},
        { 800,  600},
        {1024,  768},
        {1152,  864},
        {1280,  960},
        {1600, 1200},
        /* 16:9 */
        { 960,  540},
        {1280,  720},
        {1600,  900},
        {1920, 1080},
        {2560, 1440},
        {2880, 1620},
        {3200, 1800},
        /* 16:10 */
        {1440,  900},
        {1680, 1050},
        {1920, 1200},
        {2560, 1600},
        /* 3:2 */
        {1440,  960},
        {1920, 1280},
        /* 21:9 ultra-wide */
        {2560, 1080},
        /* 12:5 */
        {1920,  800},
        {3840, 1600},
        /* 5:4 */
        {1280, 1024},
        /* 5:3 */
        {1280,  768},
    };''','''    /* OrbisDesk W265: the sizes a game may choose; ps5drv shows the one set full screen, scaled (W248) */
    static SIZE default_sizes[] =
    {
        { 640,  480}, { 800,  600}, {1024,  768}, {1152,  864}, {1280,  720},
        {1280,  960}, {1280, 1024}, {1366,  768}, {1600,  900}, {1920, 1080},
    };''','The display mode sizes offered (W265).')
revise('dlls/win32u/sysparams.c','''static DEVMODEW *get_virtual_modes( const DEVMODEW *initial, const DEVMODEW *maximum,
                                    const DEVMODEW *host_modes, UINT host_modes_count, UINT32 *modes_count )
{
    UINT depths[] = {8, 16, initial->dmBitsPerPel}, freqs[] = {60, -1}, sizes_count, i, j, f, count = 0;''','''static DEVMODEW *get_virtual_modes( const DEVMODEW *initial, const DEVMODEW *physical_maximum,
                                    const DEVMODEW *host_modes, UINT host_modes_count, UINT32 *modes_count )
{
    /* OrbisDesk W265: modes up to 1920x1080 above a smaller desktop (1280x720); the physical mode stays the
     * desktop's, ps5drv shows a full-screen window of the mode set scaled to the output (W248) */
    DEVMODEW pw_maximum = *physical_maximum;
    const DEVMODEW *maximum = &pw_maximum;
    UINT depths[] = {8, 16, initial->dmBitsPerPel}, freqs[] = {60, -1}, sizes_count, i, j, f, count = 0;''',
       'Display modes above the desktop size (W265).')
revise('dlls/win32u/sysparams.c','''    vertical = initial->dmPelsHeight > initial->dmPelsWidth;
''','''    vertical = initial->dmPelsHeight > initial->dmPelsWidth;
    if (!vertical)
    {
        pw_maximum.dmPelsWidth = max( pw_maximum.dmPelsWidth, 1920 );
        pw_maximum.dmPelsHeight = max( pw_maximum.dmPelsHeight, 1080 );
    }
''','Display modes above the desktop size (W265).')
revise('dlls/win32u/ps5drv.c','''            view_width = min( (UINT)monitor_rect.right, screen_width );
            view_height = min( (UINT)monitor_rect.bottom, screen_height );''','''            /* W265: a mode larger than the desktop too: the windows' layers are in its coordinates */
            view_width = min( (UINT)monitor_rect.right, 3840 );
            view_height = min( (UINT)monitor_rect.bottom, 2160 );''','A full screen mode larger than the desktop is shown whole (W265).')
revise('dlls/win32u/ps5drv.c','''static RECT monitor_rect;   /* W248: the primary monitor, the display mode a game set (WindowPosChanged) */
''','''static RECT monitor_rect;   /* W248: the primary monitor, the display mode a game set (WindowPosChanged) */
/* W265: the pointer's bounds: the desktop, or a larger display mode a game set */
static UINT input_width(void) { return max( screen_width, (UINT)max( monitor_rect.right, 0 ) ); }
static UINT input_height(void) { return max( screen_height, (UINT)max( monitor_rect.bottom, 0 ) ); }
''','The pointer reaches a mode larger than the desktop (W265).')
revise('dlls/win32u/ps5drv.c','''            cursor.x = min( max( event.x, 0 ), (INT)screen_width - 1 );
            cursor.y = min( max( event.y, 0 ), (INT)screen_height - 1 );''','''            cursor.x = min( max( event.x, 0 ), (INT)input_width() - 1 );  /* W265 */
            cursor.y = min( max( event.y, 0 ), (INT)input_height() - 1 );''','The pointer reaches a mode larger than the desktop (W265).')
revise('dlls/win32u/ps5drv.c','''            cursor.x = min( max( cursor.x + event.x, 0 ), (INT)screen_width - 1 );
            cursor.y = min( max( cursor.y + event.y, 0 ), (INT)screen_height - 1 );''','''            cursor.x = min( max( cursor.x + event.x, 0 ), (INT)input_width() - 1 );  /* W265 */
            cursor.y = min( max( cursor.y + event.y, 0 ), (INT)input_height() - 1 );''','The pointer reaches a mode larger than the desktop (W265).')
# W269 (W267: Call of Duty ended with status 3 with nothing on screen): the window texts that 32-bit threads set
# (static controls, dialogs, message boxes, titles). Read only.
revise('dlls/win32u/defwnd.c','''    TRACE( "%p, %s\\n", hwnd, debugstr_w(str) );
''','''    TRACE( "%p, %s\\n", hwnd, debugstr_w(str) );
#ifdef __ORBIS__
    if (str && NtCurrentTeb()->WowTebOffset)  /* W269: a 32-bit thread's window text */
    {
        static LONG pw_texts;

        if (InterlockedIncrement( &pw_texts ) <= 300) ERR( "PWTEXT hwnd=%p text=%s\\n", hwnd, debugstr_w(str) );
    }
#endif
''','The window texts 32-bit threads set are traced (W269).')
# W272 (W270: NFS U2 and Quake 3 move only while input arrives; the server wakes on time): a 32-bit thread's
# message wait, acquire or present that takes over 100 ms, and what ended the wait. Traces only.
revise('dlls/win32u/message.c','''/* wait for message or signaled handle */
static DWORD wait_message(''','''#ifdef __ORBIS__
/* W272 (W270: NFS U2 and Quake 3 move only while input arrives): a 32-bit thread's message wait over 100 ms,
 * the timeout it asked for ("late": under 100 ms asked, over 100 ms past it) and what ended it: its queue, one of
 * its handles, the timeout or an APC. At most 150 lines a thread, 3000 in all. */
static LONG pw_msgwait_lines, pw_msgwait_tids[128], pw_msgwait_counts[128];

static void pw_msgwait_note( DWORD count, DWORD timeout, DWORD wake_mask, DWORD changed_mask, DWORD flags,
                             DWORD ret, LONGLONG took )
{
    LONG tid = GetCurrentThreadId();
    LONGLONG ms = took / 10000;
    const char *woke = ret == WAIT_TIMEOUT ? "timeout" : ret == count - 1 ? "queue" : ret < count - 1 ? "handle" :
                       ret == STATUS_USER_APC ? "apc" : "other";
    unsigned int i;

    if (InterlockedIncrement( &pw_msgwait_lines ) > 3000) return;
    for (i = 0; i < ARRAY_SIZE(pw_msgwait_tids); i++)
    {
        LONG owner = InterlockedCompareExchange( &pw_msgwait_tids[i], tid, 0 );

        if (owner && owner != tid) continue;
        if (InterlockedIncrement( &pw_msgwait_counts[i] ) > 150) return;
        ERR( "PWWAIT msg thread=%04x took_ms=%d asked_ms=%d%s woke=%s ret=%#x handles=%d wake_mask=%#x "
             "changed_mask=%#x flags=%#x\\n", (int)tid, (int)ms, timeout == INFINITE ? -1 : (int)timeout,
             timeout < 100 && ms > timeout + 100 ? " late" : "", woke, (int)ret, (int)count - 1, (int)wake_mask,
             (int)changed_mask, (int)flags );
        return;
    }
}
#endif

/* wait for message or signaled handle */
static DWORD wait_message(''','A 32-bit thread message wait over 100 ms is traced (W272).')
revise('dlls/win32u/message.c','''    LARGE_INTEGER time, now, *abs;
    void *ret_ptr;
    ULONG ret_len;
    HANDLE event;
    DWORD ret;
''','''    LARGE_INTEGER time, now, *abs;
    void *ret_ptr;
    ULONG ret_len;
    HANDLE event;
    DWORD ret;
#ifdef __ORBIS__
    LARGE_INTEGER pw_start, pw_end;  /* W272 */
#endif
''','The message wait is timed (W272).')
revise('dlls/win32u/message.c','''    do ret = NtWaitForMultipleObjects( count, handles, type, !!(flags & MWMO_ALERTABLE), abs );
    while (ret == count - 1 && !process_driver_events( QS_ALLINPUT, wake_mask, changed_mask ));
''','''#ifdef __ORBIS__
    NtQueryPerformanceCounter( &pw_start, NULL );  /* W272 */
#endif
    do ret = NtWaitForMultipleObjects( count, handles, type, !!(flags & MWMO_ALERTABLE), abs );
    while (ret == count - 1 && !process_driver_events( QS_ALLINPUT, wake_mask, changed_mask ));
#ifdef __ORBIS__
    if (NtCurrentTeb()->WowTebOffset)
    {
        NtQueryPerformanceCounter( &pw_end, NULL );
        if (pw_end.QuadPart - pw_start.QuadPart > 1000000)
            pw_msgwait_note( count, timeout, wake_mask, changed_mask, flags, ret, pw_end.QuadPart - pw_start.QuadPart );
    }
#endif
''','The message wait is timed (W272).')
# W273 (W272: Quake 3's dinput polls with MsgWaitForMultipleObjectsEx(0, NULL, 0, QS_ALLINPUT, 0) every frame; idle,
# each call took ~966 ms and ended on the queue: the loop waited again while the server signaled the queue and
# process_driver_events found nothing for the mask). A zero timeout waits once: when the queue wakes it with
# nothing for the mask, the result is WAIT_TIMEOUT, as the next wait (deadline passed) would return. The first
# wait and the loop count of a slow call are traced, to find the stale signal.
revise('dlls/win32u/message.c','''    do ret = NtWaitForMultipleObjects( count, handles, type, !!(flags & MWMO_ALERTABLE), abs );
    while (ret == count - 1 && !process_driver_events( QS_ALLINPUT, wake_mask, changed_mask ));
#ifdef __ORBIS__
    if (NtCurrentTeb()->WowTebOffset)''','''#ifdef __ORBIS__
    {
        LARGE_INTEGER pw_first = {{0}};
        unsigned int pw_loops = 0;

        for (;;)
        {
            ret = NtWaitForMultipleObjects( count, handles, type, !!(flags & MWMO_ALERTABLE), abs );
            if (!pw_loops++) NtQueryPerformanceCounter( &pw_first, NULL );
            if (ret != count - 1 || process_driver_events( QS_ALLINPUT, wake_mask, changed_mask )) break;
            if (!timeout)
            {
                ret = WAIT_TIMEOUT;
                break;
            }
        }
        if (NtCurrentTeb()->WowTebOffset && pw_loops > 1)
        {
            static LONG lines;
            NtQueryPerformanceCounter( &pw_end, NULL );
            if (pw_end.QuadPart - pw_start.QuadPart > 1000000 && InterlockedIncrement( &lines ) <= 300)
                ERR( "PWWAIT msgloop thread=%04x asked_ms=%d loops=%u first_ms=%d took_ms=%d ret=%#x\\n",
                     (int)GetCurrentThreadId(), timeout == INFINITE ? -1 : (int)timeout, pw_loops,
                     (int)((pw_first.QuadPart - pw_start.QuadPart) / 10000),
                     (int)((pw_end.QuadPart - pw_start.QuadPart) / 10000), (int)ret );
        }
    }
#else
    do ret = NtWaitForMultipleObjects( count, handles, type, !!(flags & MWMO_ALERTABLE), abs );
    while (ret == count - 1 && !process_driver_events( QS_ALLINPUT, wake_mask, changed_mask ));
#endif
#ifdef __ORBIS__
    if (NtCurrentTeb()->WowTebOffset)''','A zero-timeout message wait waits once (W273).')
revise('dlls/win32u/vulkan.c','''static struct vulkan_funcs vulkan_funcs =
{''','''/* W272 (W270: NFS U2 and Quake 3 move only while input arrives): a 32-bit thread's acquire or present that
 * takes over 100 ms (a stall in the swapchain rather than in a wait), the first 600 */
static void pw32_vk_slow( const char *what, const LARGE_INTEGER *start, VkResult res, uint64_t timeout )
{
    static LONG lines;
    LARGE_INTEGER end;
    LONGLONG ms;

    NtQueryPerformanceCounter( &end, NULL );
    ms = (end.QuadPart - start->QuadPart) / 10000;
    if (ms < 100 || InterlockedIncrement( &lines ) > 600) return;
    ERR( "PWWAIT vk thread=%04x %s took_ms=%d timeout_ms=%d res=%d\\n", (int)GetCurrentThreadId(), what, (int)ms,
         timeout == UINT64_MAX ? -1 : (int)min( timeout / 1000000, 0x7fffffff ), res );
}

static VkResult pw32_vkAcquireNextImageKHR( VkDevice client_device, VkSwapchainKHR client_swapchain, uint64_t timeout,
                                            VkSemaphore client_semaphore, VkFence client_fence, uint32_t *image_index )
{
    LARGE_INTEGER start;
    VkResult res;

    if (!NtCurrentTeb()->WowTebOffset)
        return win32u_vkAcquireNextImageKHR( client_device, client_swapchain, timeout, client_semaphore, client_fence,
                                             image_index );
    NtQueryPerformanceCounter( &start, NULL );
    res = win32u_vkAcquireNextImageKHR( client_device, client_swapchain, timeout, client_semaphore, client_fence,
                                        image_index );
    pw32_vk_slow( "vkAcquireNextImageKHR", &start, res, timeout );
    return res;
}

static VkResult pw32_vkAcquireNextImage2KHR( VkDevice client_device, const VkAcquireNextImageInfoKHR *acquire_info,
                                             uint32_t *image_index )
{
    LARGE_INTEGER start;
    VkResult res;

    if (!NtCurrentTeb()->WowTebOffset) return win32u_vkAcquireNextImage2KHR( client_device, acquire_info, image_index );
    NtQueryPerformanceCounter( &start, NULL );
    res = win32u_vkAcquireNextImage2KHR( client_device, acquire_info, image_index );
    pw32_vk_slow( "vkAcquireNextImage2KHR", &start, res, acquire_info->timeout );
    return res;
}

static VkResult pw32_vkQueuePresentKHR( VkQueue client_queue, const VkPresentInfoKHR *client_present_info )
{
    LARGE_INTEGER start;
    VkResult res;

    if (!NtCurrentTeb()->WowTebOffset) return win32u_vkQueuePresentKHR( client_queue, client_present_info );
    NtQueryPerformanceCounter( &start, NULL );
    res = win32u_vkQueuePresentKHR( client_queue, client_present_info );
    pw32_vk_slow( "vkQueuePresentKHR", &start, res, UINT64_MAX );
    return res;
}

static struct vulkan_funcs vulkan_funcs =
{''','A 32-bit thread acquire or present over 100 ms is traced (W272).')
revise('dlls/win32u/vulkan.c','''    .p_vkAcquireNextImage2KHR = win32u_vkAcquireNextImage2KHR,
    .p_vkAcquireNextImageKHR = win32u_vkAcquireNextImageKHR,''','''    .p_vkAcquireNextImage2KHR = pw32_vkAcquireNextImage2KHR,  /* W272 */
    .p_vkAcquireNextImageKHR = pw32_vkAcquireNextImageKHR,  /* W272 */''','Acquire goes through the W272 timer.')
revise('dlls/win32u/vulkan.c','''    .p_vkQueuePresentKHR = win32u_vkQueuePresentKHR,''','''    .p_vkQueuePresentKHR = pw32_vkQueuePresentKHR,  /* W272 */''',
       'Present goes through the W272 timer.')
target=overlay/'dlls/win32u/freetype.c'
target.write_text(target.read_text().replace('dlclose(ft_handle);','/* Static FreeType: no dynamic library handle to close. */'))
makefile=(UNIX/'Makefile').read_text().splitlines()
def recipe(target):
    index=next((i for i,line in enumerate(makefile) if line.startswith(target+': ') and i+1<len(makefile)
                and makefile[i+1].startswith('\t$(CC)')),None)
    if index is None:return None
    parts=[];index+=1
    while True:
        line=makefile[index];parts.append(line.rstrip().removesuffix('\\'))
        if not line.rstrip().endswith('\\'):break
        index+=1
    return ' '.join(parts).replace('$(CC)',str(UNIX/'orbis-cc')).replace('$(CFLAGS)','-g -O2')
units=sorted({re.match(r'^(dlls/win32u/[a-z0-9_/]+)\.o: ',line).group(1) for line in makefile
              if re.match(r'^dlls/win32u/[a-z0-9_/]+\.o: ',line)})
units.append('dlls/win32u/ps5drv')
template=recipe('dlls/win32u/bitblt.o')
results=[]
for unit in units:
    command=recipe(unit+'.o')
    if command is None:command=template.replace('dlls/win32u/bitblt','dlls/win32u/ps5drv')
    output=work/(unit.removeprefix('dlls/win32u/').replace('/','_')+'.o')
    command=shlex.split(command.replace('$@',str(output)))
    original=str(SOURCE/(unit+'.c'))
    command=[str(overlay/(unit+'.c')) if arg==original or arg.endswith('/'+unit+'.c') else arg for arg in command]
    command+=['-D__ORBIS__','-I'+str(ROOT/'platform/ps4'),'-I'+str(overlay/'dlls/win32u'),'-ffunction-sections',
              '-fdata-sections','-include',str(ROOT/'platform/ps4/pw_wine_posix.h'),
              # IDL-generated headers are platform independent; config.h still comes from the Orbis tree.
              '-idirafter',str(ROOT/'.deps/wine/runtime/build/include')]
    command[1:1]=['-I'+str(ROOT/'build/freetype-ps4/include'),
                  '-I'+str(ROOT/'.deps/shadPS4-fork/externals/freetype/include')]
    log=work/(output.stem+'.log')
    with log.open('w') as handle:
        run=subprocess.run(command,cwd=UNIX,stdout=handle,stderr=subprocess.STDOUT)
    results.append({'unit':unit,'exit_code':run.returncode})
    if not run.returncode:manifest['objects'][str(output.relative_to(ROOT))]=sha(output)
manifest['results']=results
manifest['sources']={str(path.relative_to(ROOT)):sha(path) for path in sorted((overlay/'dlls/win32u').rglob('*.[ch]'))}
(work/'report.json').write_text(json.dumps(manifest,indent=2)+'\n')
failed=[item['unit'] for item in results if item['exit_code']]
print(json.dumps({'units':len(results),'failed':failed}))
if failed:raise SystemExit(1)
