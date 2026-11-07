#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Pending change for tools/build-win32u-ps4.py (W179): a solid window frame for Luna and Noir.
Usage: flat-frame-w179.patch.py FILE adds the revision to FILE (build-win32u-ps4.py or a copy),
before its first revision of ps5drv.c. Also used by the compile check, through FRAME_OLD/FRAME_NEW."""
import pathlib,sys
FRAME_OLD='''    NtGdiSelectPen( hdc, get_sys_color_pen( COLOR_WINDOWFRAME ));

    if (has_static_outer_frame( ex_style ))
        draw_rect_edge( hdc, &rect, BDR_SUNKENOUTER, BF_RECT | BF_ADJUST, 1 );
    else if (has_big_frame( style, ex_style ))
        draw_rect_edge( hdc, &rect, EDGE_RAISED, BF_RECT | BF_ADJUST, 1 );

    draw_nc_frame( hdc, &rect, active, style, ex_style );
'''
FRAME_NEW='''    NtGdiSelectPen( hdc, get_sys_color_pen( COLOR_WINDOWFRAME ));

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
'''
if __name__=='__main__':
    path=pathlib.Path(sys.argv[1]);text=path.read_text()
    anchor="revise('dlls/win32u/ps5drv.c',"
    if text.count('OrbisDesk W179: a visual style')!=0:raise SystemExit('already applied')
    block=('# W179: a solid window frame in the border colour when a visual style sets one apart from the\n'
           '# button face (Luna, Noir; tools/build-msstyles-hw.py), as XP draws its windows.\n'
           "revise('dlls/win32u/defwnd.c','''"+FRAME_OLD+"''','''"+FRAME_NEW+"''',\n"
           "       'Solid frame in the border colour of a visual style (W179).')\n")
    at=text.index(anchor);path.write_text(text[:at]+block+text[at:]);print('applied to',path)
