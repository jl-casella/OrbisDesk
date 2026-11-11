/* SPDX-License-Identifier: LGPL-2.1-or-later */
#define _WIN32_WINNT 0x0600
#include <windows.h>
#include <stdio.h>
#include "pw_execution_policy.h"
static unsigned failures;
static void set(const WCHAR *key,const WCHAR *name,const WCHAR *value)
{
    HKEY handle;if(RegCreateKeyExW(HKEY_CURRENT_USER,key,0,NULL,0,KEY_ALL_ACCESS,NULL,&handle,NULL))ExitProcess(90);
    if(RegSetValueExW(handle,name,0,REG_SZ,(const BYTE *)value,(lstrlenW(value)+1)*sizeof(WCHAR)))ExitProcess(91);
    RegCloseKey(handle);
}
static void check(const char *name,const WCHAR *exe,int expected)
{
    int got=ps4_execution_mode(exe);
    printf("{\"case\":\"%s\",\"expected\":%d,\"actual\":%d,\"passed\":%s}\n",name,expected,got,got==expected?"true":"false");
    if(got!=expected)failures++;
    if(ps4_runs_alone(exe)!=(expected==PW_EXEC_EXCLUSIVE))failures++;
}
static void profile(const WCHAR *exe,const WCHAR *mode)
{
    WCHAR path[MAX_PATH],key[MAX_PATH+64];if(!pw_execution_key(exe,path,key))ExitProcess(92);
    set(key,L"ExecutablePath",path);set(key,L"Mode",mode);
}
int main(void)
{
    const WCHAR *a=L"C:\\OrbisDesk-test\\a\\game.exe",*b=L"C:\\OrbisDesk-test\\b\\game.exe";
    const WCHAR *legacy=L"Software\\Wine\\AppDefaults\\game.exe";
    WCHAR path[MAX_PATH],key[MAX_PATH+64];
    check("default_auto",a,PW_EXEC_AUTO);
    set(legacy,L"OrbisRunsAlone",L"Y");check("legacy_exclusive",a,PW_EXEC_EXCLUSIVE);
    profile(a,L"auto");check("path_auto_overrides_legacy",a,PW_EXEC_AUTO);check("other_path_keeps_legacy",b,PW_EXEC_EXCLUSIVE);
    profile(b,L"guest");check("same_basename_independent",b,PW_EXEC_GUEST);
    profile(a,L"exclusive");check("path_exclusive",a,PW_EXEC_EXCLUSIVE);
    check("normalized_case_slashes",L"c:/ORBISDESK-test/a/./game.exe",PW_EXEC_EXCLUSIVE);
    profile(a,L"separate");check("separate_is_distinct_policy",a,PW_EXEC_SEPARATE);
    pw_execution_key(a,path,key);set(key,L"ExecutablePath",b);check("wrong_path_identity_not_used",a,PW_EXEC_EXCLUSIVE);
    set(legacy,L"OrbisExecutionMode",L"guest");check("new_legacy_setting_precedes_old_checkbox",a,PW_EXEC_GUEST);
    profile(a,L"unknown");check("unknown_mode_safe_auto",a,PW_EXEC_AUTO);
    set(L"Software\\Wine\\AppDefaults\\d3d11test64.exe",L"OrbisRunsAlone",L"Y");
    check("retired_d3d_seed",L"C:\\orbis\\d3d11test64.exe",PW_EXEC_AUTO);
    set(L"Software\\Wine\\AppDefaults\\d3d11tests64.exe",L"OrbisRunsAlone",L"Y");
    check("retired_d3d_plural_alias",L"C:\\orbis\\d3d11tests64.exe",PW_EXEC_AUTO);
    profile(L"C:\\orbis\\d3d11test64.exe",L"exclusive");check("explicit_d3d_exclusive_still_works",L"C:\\orbis\\d3d11test64.exe",PW_EXEC_EXCLUSIVE);
    return failures?1:0;
}
