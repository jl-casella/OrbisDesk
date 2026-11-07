#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Pending change for tools/build-win32u-ps4.py (W182, diagnosis of the winecfg Apply freeze): two
markers in win32u, no change of behaviour. Usage: paint-broadcast-diag-w182.patch.py FILE adds the
revisions to FILE (build-win32u-ps4.py or a copy) before its first revision of ps5drv.c. The
compile check uses the REVISIONS list directly."""
import pathlib,sys
REVISIONS=[
('dlls/win32u/dce.c','''static void update_now( HWND hwnd, UINT rdw_flags )
{
    HWND child = 0;
''','''static void update_now( HWND hwnd, UINT rdw_flags )
{
    HWND child = 0;
    unsigned int loops = 0;  /* OrbisDesk W182 (diagnosis) */
    static LONG loop_logged;
''','update_now: an iteration count.'),
('dlls/win32u/dce.c','''        send_message( child, WM_PAINT, 0, 0 );
        if (rdw_flags & RDW_NOCHILDREN) break;''','''        send_message( child, WM_PAINT, 0, 0 );
        /* OrbisDesk W182 (diagnosis): a window that keeps needing WM_PAINT keeps this loop going;
         * W180's winecfg froze applying a theme, whose SetSysColors repaints with RDW_UPDATENOW */
        if (++loops == 256 && !InterlockedExchange( &loop_logged, 1 ))
            ERR( "PWPAINT update_now_loop hwnd=%p child=%p tid=%04x flags=%#x\\\\n", hwnd, child,
                 (int)get_window_thread( child, NULL ), flags );
        if (rdw_flags & RDW_NOCHILDREN) break;''','update_now: one line when a window keeps it looping.'),
('dlls/win32u/message.c','''static BOOL broadcast_message( struct send_message_info *info, DWORD_PTR *res_ptr )
{''','''/* OrbisDesk W182 (diagnosis): a window that used a broadcast's whole timeout, once per window */
static void broadcast_timeout_log( HWND hwnd, UINT msg, DWORD elapsed, UINT timeout )
{
    static HWND logged[32];
    static unsigned int count;
    unsigned int i;

    if (!timeout || elapsed < timeout) return;
    for (i = 0; i < count; i++) if (logged[i] == hwnd) return;
    if (count >= ARRAY_SIZE(logged)) return;
    logged[count++] = hwnd;
    ERR( "PWBCAST timeout msg=%04x hwnd=%p tid=%04x elapsed_ms=%u\\\\n", msg, hwnd,
         (int)get_window_thread( hwnd, NULL ), (int)elapsed );
}

static BOOL broadcast_message( struct send_message_info *info, DWORD_PTR *res_ptr )
{''','Broadcast: the timeout logger.'),
('dlls/win32u/message.c','''            case MSG_UNICODE:
            case MSG_OTHER_PROCESS:
                send_message_timeout( list[i], info->msg, info->wparam, info->lparam,
                                      info->flags, info->timeout, FALSE );
                break;
            case MSG_ASCII:
                send_message_timeout( list[i], info->msg, info->wparam, info->lparam,
                                      info->flags, info->timeout, TRUE );
                break;''','''            case MSG_UNICODE:
            case MSG_OTHER_PROCESS:
            case MSG_ASCII:
            {
                DWORD start = NtGetTickCount();
                send_message_timeout( list[i], info->msg, info->wparam, info->lparam,
                                      info->flags, info->timeout, info->type == MSG_ASCII );
                broadcast_timeout_log( list[i], info->msg, NtGetTickCount() - start, info->timeout );
                break;
            }''','Broadcast: time the send to each window.'),
]
if __name__=='__main__':
    path=pathlib.Path(sys.argv[1]);text=path.read_text()
    if 'PWPAINT update_now_loop' in text:raise SystemExit('already applied')
    block='# W182 (diagnosis): winecfg froze applying a theme (W180); which window keeps update_now looping\n# or uses a broadcast\'s whole timeout. Markers only.\n'
    for target,old,new,why in REVISIONS:
        block+="revise('%s','''%s''','''%s''',\n       '%s')\n"%(target,old,new,why)
    anchor="revise('dlls/win32u/ps5drv.c',"
    at=text.index(anchor);path.write_text(text[:at]+block+text[at:]);print('applied to',path)
