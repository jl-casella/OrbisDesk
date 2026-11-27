# SPDX-License-Identifier: LGPL-2.1-or-later
"""Instrument the pinned NtReadFile body without changing its I/O contract."""
import re

def patch(text):
    start=text.index('NTSTATUS WINAPI NtReadFile(')
    end=text.index('\n/******************************************************************************',start)
    body=text[start:end]
    def change(old,new):
        nonlocal body
        if body.count(old)!=1:raise ValueError('NtReadFile context changed: '+old[:90])
        body=body.replace(old,new,1)
    change('    BOOL send_completion = FALSE, async_read, timeout_init_done = FALSE;',
           '    BOOL send_completion = FALSE, async_read, timeout_init_done = FALSE;\n'
           '    struct pw_readstamp pw_read = pw_readtrace_begin();')
    change('    if (!virtual_check_buffer_for_write( buffer, length ))',
           '    if (!status) pw_read.kind = type == FD_TYPE_FILE ? 1 : type == FD_TYPE_SOCKET ? 2 : 3;\n'
           '    pw_readtrace_stage( &pw_read, PW_READ_BUFFER );\n'
           '    if (!virtual_check_buffer_for_write( buffer, length ))')
    change('    if (status == STATUS_BAD_DEVICE_TYPE)\n',
           '    pw_readtrace_stage( &pw_read, PW_READ_IO );\n'
           '    if (status == STATUS_BAD_DEVICE_TYPE)\n')
    change('    async_read = !(options & (FILE_SYNCHRONOUS_IO_ALERT | FILE_SYNCHRONOUS_IO_NONALERT));',
           '    async_read = !(options & (FILE_SYNCHRONOUS_IO_ALERT | FILE_SYNCHRONOUS_IO_NONALERT));\n'
           '    pw_read.async_read = async_read;')
    change('            total = result;',
           '            total = result;\n'
           '            pw_read.actual = total; pw_read.known = 1;')
    change('            total += result;',
           '            total += result;\n'
           '            pw_read.actual = total; pw_read.known = 1;')
    change('err:\n    if (needs_close)',
           'err:\n    pw_readtrace_stage( &pw_read, PW_READ_COMPLETION );\n'
           '    if (needs_close)')
    change('        if (event) NtSetEvent( event, NULL );',
           '        pw_read.event = !!event; pw_read.apc = !!(apc && (!status || async_read));\n'
           '        if (event) NtSetEvent( event, NULL );')
    change('    if (send_completion && async_read)\n        add_completion( handle, cvalue, status, total, ret_status == STATUS_PENDING );',
           '    if (send_completion && async_read)\n    {\n'
           '        pw_read.completion = 1;\n'
           '        add_completion( handle, cvalue, status, total, ret_status == STATUS_PENDING );\n    }')
    # Evaluate each original return expression exactly once, including delegated reads.
    body,count=re.subn(r'\breturn ([^;\n]+);',r'return pw_readtrace_end( &pw_read, \1, length );',body)
    if count!=6:raise ValueError('NtReadFile return count changed: '+str(count))
    return '#include "pw_optrace.h"\n'+text[:start]+body+text[end:]
