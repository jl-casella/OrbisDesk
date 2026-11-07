#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Pending change for tools/build-explorer-hw.py (not applied): the Start button glyph becomes
the app icon (tools/make-app-icon.py) drawn with GDI polygons. Usage: start-glyph-w169.patch.py FILE
rewrites FILE in place. Also imported by the preview script for the shared geometry."""
import pathlib,sys

# 256-unit design grid scaled to SM_CXSMICON: side strip, mullion, front face; the groove
# between the upper and lower panes is filled with the light-bar colour.
PANES=(  # colour, four corners
    ('#8fe0ff',((48,24),(80,16),(80,229),(48,240))),      # side column in the light-bar colour,
    ('#8fe0ff',((99,16),(216,42),(216,224),(99,229))),    # face column too: the groove shows it
    ('#3a9cf0',((48,24),(80,16),(80,91),(48,87))),        # side, upper
    ('#155cb8',((48,111),(80,115),(80,229),(48,240))),    # side, lower
    ('#4fb3ff',((99,16),(216,42),(216,109),(99,94))),     # face, upper
    ('#1f7fe6',((99,118),(216,133),(216,224),(99,229))),  # face, lower
)
OLD_HEAD='''        int size = GetSystemMetrics( SM_CXSMICON ), half = size / 2;
        int x = rect.left + 3, y = (rect.top + rect.bottom - size) / 2;
        HBRUSH pane = CreateSolidBrush( RGB( 0x1e, 0x90, 0xff ));
        RECT square, text = rect;

        SetRect( &square, x, y, x + half - 1, y + half - 1 );
        FillRect( dis->hDC, &square, pane );
        SetRect( &square, x + half, y, x + size, y + half - 1 );
        FillRect( dis->hDC, &square, pane );
        SetRect( &square, x, y + half, x + half - 1, y + size );
        FillRect( dis->hDC, &square, pane );
        SetRect( &square, x + half, y + half, x + size, y + size );
        FillRect( dis->hDC, &square, pane );
        DeleteObject( pane );
        text.left = x + size + 2;'''
def c_table():
    rgb=lambda h:'RGB( 0x%s, 0x%s, 0x%s )'%(h[1:3],h[3:5],h[5:7])
    points=',\n'.join('            {'+', '.join('{%d,%d}'%p for p in corners)+'}' for _,corners in PANES)
    colours=', '.join(rgb(h) for h,_ in PANES)
    return points,colours
def new_head():
    points,colours=c_table()
    return '''        /* the app icon (tools/make-app-icon.py): a four-pane window shaped like the console,
         * on a 256-unit grid; each column first in the light-bar colour, which shows in the
         * groove between its panes (W169) */
        static const POINT design[%d][4] =
        {
%s
        };
        static const COLORREF colours[%d] = { %s };
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
        text.left = x + size + 2;'''%(len(PANES),points,len(PANES),colours)
if __name__=='__main__':
    target=pathlib.Path(sys.argv[1]);text=target.read_text()
    if text.count(OLD_HEAD)!=1:raise SystemExit('Start glyph block not found once in '+str(target))
    text=text.replace(OLD_HEAD,new_head()).replace("'Start button glyph instead of the class icon.'",
        "'Start button glyph: the app icon (W169) instead of the class icon.'")
    target.write_text(text);print('applied to',target)
