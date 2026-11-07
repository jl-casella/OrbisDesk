/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Compile against the pinned Wine headers, never Windows SDK replacements. */
#include <stdarg.h>
#include "windef.h"
#include "winbase.h"
#include "winternl.h"
#define AT(type, member, offset) _Static_assert(__builtin_offsetof(type, member)==offset, #type "." #member)
AT(PEB32, ImageBaseAddress, 8);
AT(PEB32, LdrData, 0xc);
AT(PEB32, ProcessParameters, 0x10);
AT(TEB32, Peb, 0x30);
AT(RTL_USER_PROCESS_PARAMETERS32, CurrentDirectory, 0x24);
AT(RTL_USER_PROCESS_PARAMETERS32, ImagePathName, 0x38);
AT(RTL_USER_PROCESS_PARAMETERS32, CommandLine, 0x40);
AT(RTL_USER_PROCESS_PARAMETERS32, Environment, 0x48);
AT(PEB_LDR_DATA32, InLoadOrderModuleList, 0xc);
AT(PEB_LDR_DATA32, InMemoryOrderModuleList, 0x14);
AT(PEB_LDR_DATA32, InInitializationOrderModuleList, 0x1c);
AT(LDR_DATA_TABLE_ENTRY, DllBase, 0x18);
AT(LDR_DATA_TABLE_ENTRY, EntryPoint, 0x1c);
AT(LDR_DATA_TABLE_ENTRY, SizeOfImage, 0x20);
AT(LDR_DATA_TABLE_ENTRY, FullDllName, 0x24);
AT(LDR_DATA_TABLE_ENTRY, BaseDllName, 0x2c);
