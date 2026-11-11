/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "pw_execution_mode.h"
static enum pw_execution_mode ps4_execution_mode(const WCHAR *exe)
{
    WCHAR normalized[MAX_PATH],key[MAX_PATH+64],stored[MAX_PATH],value[32];DWORD bytes;
    const WCHAR *base=wcsrchr(exe,'\\'),*slash=wcsrchr(exe,'/');
    if(slash && (!base || slash>base))base=slash;
    base=base?base+1:exe;
    if(pw_execution_key(exe,normalized,key))
    {
        bytes=sizeof(stored);
        if(!RegGetValueW(HKEY_CURRENT_USER,key,L"ExecutablePath",RRF_RT_REG_SZ,NULL,stored,&bytes) && !wcsicmp(stored,normalized))
        {
            bytes=sizeof(value);
            if(!RegGetValueW(HKEY_CURRENT_USER,key,L"Mode",RRF_RT_REG_SZ,NULL,value,&bytes))return pw_execution_parse(value);
        }
    }
    if(wcslen(base)>MAX_PATH)return PW_EXEC_AUTO;
    swprintf(key,sizeof(key)/sizeof(*key),L"Software\\Wine\\AppDefaults\\%ls",base);
    bytes=sizeof(value);
    if(!RegGetValueW(HKEY_CURRENT_USER,key,L"OrbisExecutionMode",RRF_RT_REG_SZ,NULL,value,&bytes))return pw_execution_parse(value);
    /* Retire the old build-owned D3D11 test seed, even in preserved prefixes.
     * A new explicit execution-mode choice still takes precedence above. */
    if(pw_execution_retired_seed(base))return PW_EXEC_AUTO;
    bytes=sizeof(value);
    if(!RegGetValueW(HKEY_CURRENT_USER,key,L"OrbisRunsAlone",RRF_RT_REG_SZ,NULL,value,&bytes) &&
       (value[0]=='Y' || value[0]=='y'))return PW_EXEC_EXCLUSIVE;
    return PW_EXEC_AUTO;
}
static BOOL ps4_runs_alone(const WCHAR *exe)
{
    return ps4_execution_mode(exe)==PW_EXEC_EXCLUSIVE;
}
