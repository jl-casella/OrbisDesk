/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Explorer's independent registry worker. The existing kernelbase closer may
 * also poll: native render_taken admits exactly one consumer per request. */
static int orbis_overlay_render_read(const WCHAR *exe,LSTATUS *status)
{
    WCHAR key[160],value[32];DWORD size=sizeof(value);int choice=0;
    swprintf(key,ARRAY_SIZE(key),L"Software\\Wine\\AppDefaults\\%s\\Direct3D",exe);
    *status=RegGetValueW(HKEY_CURRENT_USER,key,L"renderer",RRF_RT_REG_SZ,NULL,value,&size);
    if(*status && *status!=ERROR_FILE_NOT_FOUND) return -1;
    if(!*status && !wcsicmp(value,L"gl")) choice|=1;
    else if(!*status && wcsicmp(value,L"vulkan")) choice=-1;
    swprintf(key,ARRAY_SIZE(key),L"Software\\Wine\\AppDefaults\\%s\\DllOverrides",exe);size=sizeof(value);
    *status=RegGetValueW(HKEY_CURRENT_USER,key,L"d3d9",RRF_RT_REG_SZ,NULL,value,&size);
    if(*status==ERROR_FILE_NOT_FOUND) *status=0;
    else if(*status) return -1;
    else if(value[0]=='b' || value[0]=='B') {if(choice>=0) choice|=2;}
    else if(value[0]!='n' && value[0]!='N') choice=-1;
    return choice;
}
static LSTATUS orbis_overlay_render_write(const WCHAR *exe,int choice)
{
    static const WCHAR *const dlls[]={L"d3d8",L"d3d9"};
    WCHAR key[160];LSTATUS status;
    swprintf(key,ARRAY_SIZE(key),L"Software\\Wine\\AppDefaults\\%s\\Direct3D",exe);
    if(choice&1) status=RegSetKeyValueW(HKEY_CURRENT_USER,key,L"renderer",REG_SZ,L"gl",sizeof(L"gl"));
    else if((status=RegDeleteKeyValueW(HKEY_CURRENT_USER,key,L"renderer"))==ERROR_FILE_NOT_FOUND) status=0;
    if(status) return status;
    swprintf(key,ARRAY_SIZE(key),L"Software\\Wine\\AppDefaults\\%s\\DllOverrides",exe);
    for(unsigned i=0;i<ARRAY_SIZE(dlls) && !status;i++) {
        if(choice&2) status=RegSetKeyValueW(HKEY_CURRENT_USER,key,dlls[i],REG_SZ,L"builtin",sizeof(L"builtin"));
        else if((status=RegDeleteKeyValueW(HKEY_CURRENT_USER,key,dlls[i]))==ERROR_FILE_NOT_FOUND) status=0;
    }
    return status;
}
/* OrbisDesk's trace switch (PW_TRACE=0|1, platform/ps4/pw_trace.h); unset counts as on. Read once. */
static BOOL orbis_registry_traced(void)
{
    static LONG traced=-1;
    if(traced<0) {
        WCHAR value[4];
        traced=!(GetEnvironmentVariableW(L"PW_TRACE",value,ARRAY_SIZE(value))==1 && value[0]=='0');
    }
    return traced;
}
static void orbis_overlay_registry_poll(void)
{
    char request[160],result[200],ignore[8];const char *name=NULL;
    WCHAR exe[64];LSTATUS status=0;int choice=-1,set=0;
    if(!orbis_native_call("<overlay-render-poll>",request,sizeof(request))) return;
    if(!strncmp(request,"get ",4)) name=request+4;
    else if(!strncmp(request,"set ",4) && request[4]>='0' && request[4]<='3' && request[5]==' ') {
        name=request+6;set=1;choice=request[4]-'0';
    }
    if(!name) return;
    if(!MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,name,-1,exe,ARRAY_SIZE(exe)) || !exe[0] || wcspbrk(exe,L"\\/")) {
        status=ERROR_INVALID_NAME;choice=-1;
    } else if(!set || !(status=orbis_overlay_render_write(exe,choice))) choice=orbis_overlay_render_read(exe,&status);
    else choice=-1;
    if(set || status || orbis_registry_traced())
        ERR("PWOVERLAY registry worker %s exe=%s choice=%d status=%ld\n",set?"set":"get",debugstr_a(name),choice,status);
    snprintf(result,sizeof(result),"<overlay-render-result>%s %c %ld %s",set?"set":"get",choice<0?'-':'0'+choice,status,name);
    orbis_native_call(result,ignore,sizeof(ignore));
}
static DWORD WINAPI orbis_overlay_registry_worker(void *unused)
{
    (void)unused;
    if(orbis_registry_traced()) ERR("PWOVERLAY registry worker ready startup=desktop poll_ms=150\n");
    for(;;) {orbis_overlay_registry_poll();Sleep(150);}
    return 0;
}
void orbis_overlay_registry_start(void);
void orbis_overlay_registry_start(void)
{
    static LONG started;HANDLE thread;
    if(InterlockedCompareExchange(&started,1,0)) return;
    thread=CreateThread(NULL,0,orbis_overlay_registry_worker,NULL,0,NULL);
    if(thread) CloseHandle(thread);
    else {InterlockedExchange(&started,0);ERR("PWOVERLAY registry worker start failed error=%lu\n",GetLastError());}
}
