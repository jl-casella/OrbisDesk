/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Shared PE-side execution profile identity. Include after Win32/NLS declarations. */
#ifndef PW_EXECUTION_MODE_H
#define PW_EXECUTION_MODE_H
#include <wchar.h>
enum pw_execution_mode { PW_EXEC_AUTO, PW_EXEC_GUEST, PW_EXEC_SEPARATE, PW_EXEC_EXCLUSIVE };
static const WCHAR *pw_execution_names[] = {L"auto",L"guest",L"separate",L"exclusive"};
static BOOL pw_execution_key(const WCHAR *exe,WCHAR *normalized,WCHAR *key)
{
    WCHAR full[MAX_PATH];DWORD length;unsigned i;ULONGLONG hash=0xcbf29ce484222325ULL;
    if(!exe || !(length=GetFullPathNameW(exe,MAX_PATH,full,NULL)) || length>=MAX_PATH)return FALSE;
    for(i=0;i<length;i++)if(full[i]=='/')full[i]='\\';
    if(!LCMapStringEx(LOCALE_NAME_INVARIANT,LCMAP_LOWERCASE,full,-1,normalized,MAX_PATH,NULL,NULL,0))return FALSE;
    for(i=0;normalized[i];i++){hash^=normalized[i];hash*=0x100000001b3ULL;}
    swprintf(key,MAX_PATH+64,L"Software\\OrbisDesk\\Execution\\%016llx",hash);
    return TRUE;
}
static enum pw_execution_mode pw_execution_parse(const WCHAR *value)
{
    unsigned i;for(i=0;value && i<4;i++)if(!wcsicmp(value,pw_execution_names[i]))return (enum pw_execution_mode)i;
    return PW_EXEC_AUTO;
}
static BOOL pw_execution_retired_seed(const WCHAR *name)
{
    return !wcsicmp(name,L"d3d11test64.exe") || !wcsicmp(name,L"d3d11tests64.exe");
}
#endif
