/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "winnls.h"
#include "pw_execution_mode.h"
#define IDC_ORBIS_EXECUTION 1290
#define IDC_ORBIS_EXECUTION_HELP 1291
static const WCHAR *orbis_execution_target;
static WCHAR *orbis_added[64];
static unsigned int orbis_added_count;
static int orbis_execution_selection;
static BOOL orbis_path_target(void)
{
    return orbis_execution_target && (wcschr(orbis_execution_target,'\\') || wcschr(orbis_execution_target,'/'));
}
static int orbis_execution_mode(void)
{
    WCHAR path[MAX_PATH],key[MAX_PATH+64],*value=NULL,*stored;
    int mode;
    if(!current_app)return PW_EXEC_AUTO;
    if(orbis_path_target() && pw_execution_key(orbis_execution_target,path,key))
    {
        stored=get_reg_key(HKEY_CURRENT_USER,key,L"ExecutablePath",NULL);
        if(stored && !wcsicmp(stored,path))value=get_reg_key(HKEY_CURRENT_USER,key,L"Mode",NULL);
        free(stored);
    }
    if(!value)value=get_reg_key(config_key,keypath(L""),L"OrbisExecutionMode",NULL);
    if(value){mode=pw_execution_parse(value);free(value);return mode;}
    value=get_reg_key(config_key,keypath(L""),L"OrbisRunsAlone",L"");
    mode=!pw_execution_retired_seed(current_app) && value && (value[0]=='Y' || value[0]=='y')?PW_EXEC_EXCLUSIVE:PW_EXEC_AUTO;
    free(value);return mode;
}
static void orbis_update_execution(HWND dialog)
{
    static const WCHAR *help[]={L"Uses desktop guests; asks before an exclusive restart.",
        L"Keeps desktop apps open; fails instead of restarting.",
        L"Runs in its own native process (needs the GoldHEN loader); no Direct3D yet.",
        L"Closes desktop apps and restarts OrbisDesk for this program."};
    orbis_execution_selection=orbis_execution_mode();
    EnableWindow(GetDlgItem(dialog,IDC_ORBIS_EXECUTION),current_app!=NULL);
    SendDlgItemMessageW(dialog,IDC_ORBIS_EXECUTION,CB_SETCURSEL,orbis_execution_selection,0);
    SetDlgItemTextW(dialog,IDC_ORBIS_EXECUTION_HELP,current_app?help[orbis_execution_selection]:L"Select an application. Added EXEs use their full path.");
}
static void orbis_on_execution_change(HWND dialog)
{
    int mode=(int)SendDlgItemMessageW(dialog,IDC_ORBIS_EXECUTION,CB_GETCURSEL,0,0);
    WCHAR path[MAX_PATH],key[MAX_PATH+64],*stored;
    if(!current_app || mode<0 || mode>3)return;
    if(orbis_path_target())
    {
        if(!pw_execution_key(orbis_execution_target,path,key))return;
        stored=get_reg_key(HKEY_CURRENT_USER,key,L"ExecutablePath",NULL);
        if(stored && wcsicmp(stored,path))
        {
            free(stored);MessageBoxW(dialog,L"This execution profile belongs to a different path. No setting was changed.",L"OrbisDesk",MB_OK|MB_ICONERROR);
            orbis_update_execution(dialog);return;
        }
        free(stored);set_reg_key(HKEY_CURRENT_USER,key,L"ExecutablePath",path);
        set_reg_key(HKEY_CURRENT_USER,key,L"Mode",pw_execution_names[mode]);
    }
    else
    {
        set_reg_key(config_key,keypath(L""),L"OrbisExecutionMode",pw_execution_names[mode]);
        set_reg_key(config_key,keypath(L""),L"OrbisRunsAlone",NULL);
    }
    orbis_update_execution(dialog);SendMessageW(GetParent(dialog),PSM_CHANGED,(WPARAM)dialog,0);
}
static void orbis_create_execution(HWND dialog)
{
    RECT list,rect,row={0,0,0,42},label={17,174,98,184},combo={100,171,245,247},help={17,190,245,212};
    HWND listview=GetDlgItem(dialog,IDC_APP_LISTVIEW),child,control;
    static const WCHAR *choices[]={L"Automatic (recommended)",L"Inside the desktop",L"Separate processes (GoldHEN loader)",L"Exclusive (restart desktop)"};unsigned i;
    if(!listview)return;
    MapDialogRect(dialog,&row);MapDialogRect(dialog,&label);MapDialogRect(dialog,&combo);MapDialogRect(dialog,&help);
    GetWindowRect(listview,&list);MapWindowPoints(NULL,dialog,(POINT *)&list,2);
    for(child=GetWindow(dialog,GW_CHILD);child;child=GetWindow(child,GW_HWNDNEXT))
    {
        if(child==listview)continue;
        GetWindowRect(child,&rect);MapWindowPoints(NULL,dialog,(POINT *)&rect,2);
        if(rect.top>=list.bottom)SetWindowPos(child,0,rect.left,rect.top-row.bottom,0,0,SWP_NOSIZE|SWP_NOZORDER|SWP_NOACTIVATE);
    }
    SetWindowPos(listview,0,0,0,list.right-list.left,list.bottom-list.top-row.bottom,SWP_NOMOVE|SWP_NOZORDER|SWP_NOACTIVATE);
    control=CreateWindowExW(0,L"Static",L"Execution &mode:",WS_CHILD|WS_VISIBLE,label.left,label.top,label.right-label.left,label.bottom-label.top,dialog,0,GetModuleHandleW(NULL),NULL);
    SendMessageW(control,WM_SETFONT,SendMessageW(dialog,WM_GETFONT,0,0),FALSE);
    control=CreateWindowExW(0,L"ComboBox",L"",WS_CHILD|WS_VISIBLE|WS_TABSTOP|WS_DISABLED|WS_VSCROLL|CBS_DROPDOWNLIST,
        combo.left,combo.top,combo.right-combo.left,combo.bottom-combo.top,dialog,(HMENU)(INT_PTR)IDC_ORBIS_EXECUTION,GetModuleHandleW(NULL),NULL);
    SendMessageW(control,WM_SETFONT,SendMessageW(dialog,WM_GETFONT,0,0),FALSE);
    for(i=0;i<4;i++)SendMessageW(control,CB_ADDSTRING,0,(LPARAM)choices[i]);
    control=CreateWindowExW(0,L"Static",L"",WS_CHILD|WS_VISIBLE,help.left,help.top,help.right-help.left,help.bottom-help.top,dialog,(HMENU)(INT_PTR)IDC_ORBIS_EXECUTION_HELP,GetModuleHandleW(NULL),NULL);
    SendMessageW(control,WM_SETFONT,SendMessageW(dialog,WM_GETFONT,0,0),FALSE);
}
static void orbis_load_profiles(HWND listview)
{
    HKEY root,key;DWORD i=0,size;WCHAR name[64],path[MAX_PATH],normalized[MAX_PATH],identity[MAX_PATH+64];
    if(RegOpenKeyW(HKEY_CURRENT_USER,L"Software\\OrbisDesk\\Execution",&root))return;
    for(;;i++)
    {
        size=ARRAY_SIZE(name);if(RegEnumKeyExW(root,i,name,&size,NULL,NULL,NULL,NULL))break;
        if(RegOpenKeyW(root,name,&key))continue;
        size=sizeof(path);
        if(!RegGetValueW(key,NULL,L"ExecutablePath",RRF_RT_REG_SZ,NULL,path,&size) && pw_execution_key(path,normalized,identity))
        {
            const WCHAR *leaf=wcsrchr(identity,'\\');
            if(leaf && !wcsicmp(leaf+1,name))add_listview_item(listview,path,wcsdup(path));
        }
        RegCloseKey(key);
    }
    RegCloseKey(root);
}
static void orbis_create_added_keys(void)
{
    HKEY root,key;unsigned i;
    if(!RegCreateKeyExW(config_key,L"AppDefaults",0,NULL,0,MAXIMUM_ALLOWED,NULL,&root,NULL))
    {
        for(i=0;i<orbis_added_count;i++)
            if(!RegCreateKeyExW(root,orbis_added[i],0,NULL,0,MAXIMUM_ALLOWED,NULL,&key,NULL))RegCloseKey(key);
        RegCloseKey(root);
    }
    for(i=0;i<orbis_added_count;i++)free(orbis_added[i]);
    orbis_added_count=0;
}
