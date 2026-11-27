# SPDX-License-Identifier: LGPL-3.0-or-later
"""Context-checked startup insertion for a stock Wine process loader."""


def patch_root_loader(text):
    changes = (
        ('void loader_init( CONTEXT *context, void **entry )',
         '#include "pw_guest_steamstub.inc.c"\n\nvoid loader_init( CONTEXT *context, void **entry )'),
        ('    static int attach_done;\n    NTSTATUS status;',
         '    static int attach_done;\n    BOOL steamstub_first_start = FALSE;\n    NTSTATUS status;'),
        ('    if (!attach_done)  /* first time around */\n    {\n        attach_done = 1;',
         '    if (!attach_done)  /* first time around */\n    {\n        steamstub_first_start = TRUE;\n        attach_done = 1;'),
        ('    RtlLeaveCriticalSection( &loader_section );\n}\n\n\n/***********************************************************************\n *           RtlImageDirectoryEntryToData',
         '    RtlLeaveCriticalSection( &loader_section );\n'
         '    if (steamstub_first_start && !ps4_steamstub_start( NtCurrentTeb()->Peb->ImageBaseAddress ))\n'
         '        NtTerminateProcess( GetCurrentProcess(), STATUS_DLL_INIT_FAILED );\n'
         '}\n\n\n/***********************************************************************\n *           RtlImageDirectoryEntryToData'),
    )
    for old, new in changes:
        if text.count(old) != 1:
            raise ValueError('Wine loader startup context changed: ' + old[:70])
        text = text.replace(old, new)
    return text
