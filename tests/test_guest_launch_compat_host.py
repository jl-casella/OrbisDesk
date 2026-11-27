#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Execute actual canonical 04.59 functions against host boundary models, never a console acceptance claim."""
import ast, pathlib, subprocess, sys, tempfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from wine_fd_pressure import OLD, NEW, patch_server
source=(ROOT/'tools/build-guest-hw.py').read_text()
units={}
def revise(module,unit,old,new,why,source=None):
    key=(module,unit)
    if key not in units:units[key]=(ROOT/'.deps/wine/source'/(source or f'dlls/{module}/{unit}.c')).read_text()
    assert units[key].count(old)==1,(key,old[:70])
    units[key]=units[key].replace(old,new)
for node in ast.parse(source).body:
    if isinstance(node,ast.Expr) and isinstance(node.value,ast.Call):
        call=node.value
        if isinstance(call.func,ast.Name) and call.func.id=='revise' and len(call.args)>1:
            if all(isinstance(a,ast.Constant) for a in call.args) and [a.value for a in call.args[:2]]==['kernelbase','version']:
                revise(*[a.value for a in call.args])
            elif all(isinstance(a,ast.Constant) for a in call.args) and [a.value for a in call.args[:2]]==['kernelbase','process'] and 'A guest that terminates its own process ends alone.' in str(call.args[-1].value):
                revise(*[a.value for a in call.args])
start=source.index('# 04.59: guests must')
end=source.index("# (out/guest-hw-i386): the i386 ones",start)
exec(compile(source[start:end],'<canonical 04.59 transformations>','exec'),{'revise':revise})
def function(text,start):
    at=text.index(start);begin=text.index('{',at);depth=0
    for i in range(begin,len(text)):
        if text[i]=='{':depth+=1
        elif text[i]=='}':
            depth-=1
            if not depth:return text[at:i+1]
    raise AssertionError(start)
guest_header=ast.literal_eval(next(n.value for n in ast.parse(source).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='GUEST_H' for t in n.targets)))
loading=function(guest_header,'static inline struct ps4_guest *ps4_guest_or_loading')
cmd=units['ucrtbase','data']
narrow=function(cmd,'char* CDECL _get_narrow_winmain_command_line')
wide=function(cmd,'wchar_t* CDECL _get_wide_winmain_command_line')
dup=function(units['kernelbase','process'],'BOOL WINAPI DECLSPEC_HOTPATCH DuplicateHandle')
term=function(units['kernelbase','process'],'BOOL WINAPI DECLSPEC_HOTPATCH TerminateProcess')
pid=function(units['kernelbase','process'],'DWORD WINAPI DECLSPEC_HOTPATCH GetProcessId')
path=function(units['ntdll','loader'],'NTSTATUS WINAPI LdrGetDllPath')
ver=units['kernelbase','version']
cached_init=function(ver,'static BOOL CALLBACK ps4_init_guest_version')
version_helpers=ver[ver.index('static BOOL ps4_text_has'):ver.index('/**********************************************************************\n *  find_entry_by_id')]
# Context safety and idempotence are enforced on the same replacement compiled below.
assert patch_server(OLD)==NEW and patch_server(NEW)==NEW
try:patch_server('unexpected source')
except ValueError:pass
else:raise AssertionError('stale source accepted')
code=r"""
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#include <stdint.h>
#include <stdarg.h>
typedef wchar_t WCHAR;typedef const WCHAR *LPCWSTR,*PCWSTR;typedef WCHAR *PWSTR;
typedef void *HANDLE,*HMODULE;typedef unsigned DWORD,ULONG,UINT;typedef int BOOL,NTSTATUS;
typedef size_t SIZE_T;typedef uintptr_t ULONG_PTR;
#define WINAPI
#define CDECL
#define CALLBACK
#define DECLSPEC_HOTPATCH
#define TRUE 1
#define FALSE 0
#define MAX_PATH 260
#define NULL_HANDLE ((HANDLE)0)
#define ERR(...) ((void)0)
static int ps4_pw_traced(void){return 1;}
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define __ORBIS__ 1
#define FD_TYPE_FILE 1
#define FD_TYPE_DIR 2
static int cache_calls,cache_ok=1;
static int add_fd_to_cache(int h,int fd,int t,int a,int o){cache_calls++;return cache_ok;}
static int cache_decision(int fd,int type,int cacheable){
 struct {int cacheable,type,access,options;} v={cacheable,type,0,0},*reply=&v;
 int handle=1,close, *needs_close=&close;
""" + NEW + r"""
 return close;
}
static struct {uintptr_t UserReserved[3];struct {struct {struct {WCHAR *Buffer;} ImagePathName;} *ProcessParameters;} *Peb;} teb;
#define NtCurrentTeb() (&teb)
static char *lineA;static wchar_t *lineW;
static char *GetCommandLineA(void){return lineA;}
static WCHAR *GetCommandLineW(void){return lineW;}
"""
code+=r"""
typedef struct {DWORD dwMajorVersion,dwMinorVersion,dwBuildNumber,dwOSVersionInfoSize;} RTL_OSVERSIONINFOEXW;
typedef struct {int done;} INIT_ONCE;
struct ps4_guest{int id;INIT_ONCE version_once;RTL_OSVERSIONINFOEXW version_info;HANDLE ended;BOOL terminated;void (*exit_process)(struct ps4_guest *,DWORD);};
static struct ps4_guest parent_guest,child_guest,*ps4_guest_loading;
#define PS4_GUEST_LOADING 0x47345350
static struct ps4_guest *ps4_guest_current(void){return *(struct ps4_guest **)teb.UserReserved;}
""" + loading + '\n'
code+=narrow + '\n' + wide + r"""
#define OBJ_INHERIT 2
static HANDLE guest_handle=(HANDLE)42,other_event=(HANDLE)43;
static HANDLE got_src,got_dest,got_handle;static DWORD got_access,got_options,got_attrs;
static HANDLE GetCurrentProcess(void){return (HANDLE)(intptr_t)-1;}
static int ps4_guest_exit_code(HANDLE h,DWORD *code){assert(!code);return h==guest_handle;}
static int NtDuplicateObject(HANDLE sp,HANDLE h,HANDLE dp,HANDLE *out,DWORD ac,DWORD attrs,DWORD opts){
 got_src=sp;got_dest=dp;got_handle=h;got_access=ac;got_options=opts;got_attrs=attrs;
 if(sp==other_event||dp==other_event||h==(HANDLE)99)return -7;
 if(out)*out=(HANDLE)88;return 0;
}
static int set_ntstatus(int s){return !s;}
""" + dup + r"""
typedef struct {DWORD UniqueProcessId;} PROCESS_BASIC_INFORMATION;
#define ProcessBasicInformation 0
static DWORD GetCurrentProcessId(void){return 99;}
static int NtQueryInformationProcess(HANDLE process,int cls,PROCESS_BASIC_INFORMATION *p,size_t n,void *ret){
 if(process!=GetCurrentProcess())return -7;p->UniqueProcessId=99;return 0;
}
""" + pid + r"""
#define ERROR_INVALID_HANDLE 6
static int self_exits,last_error;
static void SetLastError(DWORD error){last_error=error;}
static int NtCompareObjects(HANDLE a,HANDLE b){return a==b?0:-7;}
static int NtTerminateProcess(HANDLE handle,UINT code){return handle==GetCurrentProcess()?0:-7;}
static void mock_self_exit(struct ps4_guest *g,DWORD code){self_exits++;}
""" + term + r"""
#define LOAD_WITH_ALTERED_SEARCH_PATH 1
#define LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR 2
#define LOAD_LIBRARY_SEARCH_APPLICATION_DIR 4
#define LOAD_LIBRARY_SEARCH_USER_DIRS 8
#define LOAD_LIBRARY_SEARCH_SYSTEM32 16
#define LOAD_LIBRARY_SEARCH_DEFAULT_DIRS 32
#define STATUS_INVALID_PARAMETER -3
static ULONG default_search_flags;static int dlldir_section,dll_safe_mode,locked,search_calls;
static struct {unsigned Length;WCHAR *Buffer;} dll_directory;
static WCHAR *guest_path,*selected;
static WCHAR *ps4_guest_dll_image(void){return guest_path?wcsdup(guest_path):NULL;}
static int get_dll_load_path_search_flags(PCWSTR m,DWORD f,WCHAR **p,const WCHAR *image){search_calls++;if(f&LOAD_LIBRARY_SEARCH_APPLICATION_DIR){free(selected);selected=wcsdup(image?image:teb.Peb->ProcessParameters->ImagePathName.Buffer);}return 3;}
static int get_dll_load_path(PCWSTR m,PCWSTR dir,ULONG safe,WCHAR **p){
 free(selected);selected=wcsdup(m);assert(locked);return 2;
}
static void RtlEnterCriticalSection(int *p){assert(!locked);locked=1;}
static void RtlLeaveCriticalSection(int *p){assert(locked);locked=0;}
static void *GetProcessHeap(void){return NULL;}
static void RtlFreeHeap(void *h,int flags,void *p){free(p);}
""" + path + r"""
struct version_info{DWORD major,minor,build;};
static struct {struct version_info info;} version_data[]={{{6,3,9600}},{{10,0,19045}}};
static struct version_info windows8_version_info={6,2,9200},windows8_1_version_info={6,3,9600};

typedef struct {unsigned a,b,c;} LDR_RESOURCE_INFO;
typedef struct {int x;} IMAGE_RESOURCE_DATA_ENTRY;
typedef struct {struct {unsigned MajorOperatingSystemVersion,MinorOperatingSystemVersion;} OptionalHeader;} IMAGE_NT_HEADERS;
static IMAGE_NT_HEADERS pe;
static const char *manifest;
static const WCHAR *requested_version;static WCHAR queried_key[512];static int registry_queries;
#define HKEY_CURRENT_USER ((HANDLE)1)
#define RRF_RT_REG_SZ 1
#define wcsicmp wcscasecmp
static unsigned GetModuleFileNameW(HMODULE m,WCHAR *out,unsigned size){wcscpy(out,m==(HMODULE)1?L"C:\\Games\\PlayGTAIV.exe":L"C:\\Games\\other.exe");return wcslen(out);}
static int test_swprintf(WCHAR *buf,size_t size,const WCHAR *fmt,const WCHAR *exe){return swprintf(buf,size,L"Software\\Wine\\AppDefaults\\%ls",exe);}
#define swprintf test_swprintf
static int RegGetValueW(HANDLE h,const WCHAR *key,const WCHAR *value,DWORD flags,void *type,WCHAR *out,DWORD *size){
 registry_queries++;wcscpy(queried_key,key);if(!requested_version)return 2;
 *size=(wcslen(requested_version)+1)*sizeof(WCHAR);wcscpy(out,requested_version);return 0;
}
static int LdrFindResource_U(HMODULE m,ULONG_PTR *i,int level,IMAGE_RESOURCE_DATA_ENTRY **entry){static IMAGE_RESOURCE_DATA_ENTRY resource;if(!manifest)return 1;*entry=&resource;return 0;}
static int LdrAccessResource(HMODULE m,IMAGE_RESOURCE_DATA_ENTRY *e,void **out,ULONG *size){*out=(void *)manifest;*size=strlen(manifest);return 0;}
static IMAGE_NT_HEADERS *RtlImageNtHeader(HMODULE m){return &pe;}
""" + version_helpers + r"""
static HMODULE current_module=(HMODULE)1;static int fail_version;
static HMODULE GetModuleHandleW(const WCHAR *name){return current_module;}
static int RtlGetVersion(RTL_OSVERSIONINFOEXW *v){if(fail_version)return 1;v->dwMajorVersion=10;v->dwMinorVersion=0;v->dwBuildNumber=19045;return 0;}
""" + cached_init + r"""
static int InitOnceExecuteOnce(INIT_ONCE *once,BOOL (*fn)(INIT_ONCE *,void *,void **),void *param,void **ctx){
 if(once->done)return 1;if(!fn(once,param,ctx))return 0;once->done=1;return 1;
}
#undef swprintf
int main(void){
 HANDLE out;
 // Actual received-fd policy: cache low fds, close high regular files/dirs, preserve all other types.
 assert(!cache_decision(511,FD_TYPE_FILE,1)&&cache_calls==1);
 assert(cache_decision(512,FD_TYPE_FILE,1)&&cache_calls==1);
 assert(cache_decision(700,FD_TYPE_DIR,1)&&cache_calls==1);
 assert(!cache_decision(700,3,1)&&cache_calls==2);
 assert(cache_decision(1,FD_TYPE_FILE,0)&&cache_calls==2);
 cache_ok=0;assert(cache_decision(1,FD_TYPE_FILE,1)&&cache_calls==3);
 teb.UserReserved[0]=(uintptr_t)&parent_guest;ps4_guest_loading=&child_guest;
 assert(ps4_guest_or_loading()==&parent_guest);
 teb.UserReserved[2]=PS4_GUEST_LOADING;assert(ps4_guest_or_loading()==&child_guest);
 teb.UserReserved[2]=0;assert(ps4_guest_or_loading()==&parent_guest);
 teb.UserReserved[0]=0;assert(!ps4_guest_or_loading());
 // Root cache stays root; parent/child/root and quoted no-argument guests remain independent.
 lineA="explorer.exe /desktop=shell";lineW=L"explorer.exe /desktop=shell";
 assert(!strcmp(_get_narrow_winmain_command_line(),"/desktop=shell"));
 assert(!wcscmp(_get_wide_winmain_command_line(),L"/desktop=shell"));
 teb.UserReserved[0]=1;
 lineA="\"C:\\Program Files\\vc_redist.exe\" /install";lineW=L"\"C:\\Program Files\\vc_redist.exe\" /install";
 assert(!strcmp(_get_narrow_winmain_command_line(),"/install"));
 assert(!wcscmp(_get_wide_winmain_command_line(),L"/install"));
 lineA="\"C:\\Temp\\vc_redist.exe\"	-burn.clean.room=\"C:\\Installer.exe\" -burn.filehandle.self=452";
 lineW=L"\"C:\\Temp\\vc_redist.exe\"	-burn.clean.room=\"C:\\Installer.exe\" -burn.filehandle.self=452";
 assert(!strncmp(_get_narrow_winmain_command_line(),"-burn.clean.room=",17));
 assert(!wcsncmp(_get_wide_winmain_command_line(),L"-burn.clean.room=",17));
 lineA="\"C:\\Games\\hl.exe\"";lineW=L"\"C:\\Games\\hl.exe\"";
 assert(!*_get_narrow_winmain_command_line()&&!*
 _get_wide_winmain_command_line());
 teb.UserReserved[0]=0;assert(!strcmp(_get_narrow_winmain_command_line(),"/desktop=shell"));
 assert(!wcscmp(_get_wide_winmain_command_line(),L"/desktop=shell"));
 // Registered guest process handles share the real host table; unrelated/invalid handles stay errors.
 assert(DuplicateHandle(guest_handle,(HANDLE)4,guest_handle,&out,0x123,1,5));
 assert(got_src==GetCurrentProcess()&&got_dest==GetCurrentProcess()&&got_handle==(HANDLE)4);
 assert(got_access==0x123&&got_options==5&&got_attrs==OBJ_INHERIT&&out==(HANDLE)88);
 assert(!DuplicateHandle(other_event,(HANDLE)4,GetCurrentProcess(),&out,0,0,0));
 assert(!DuplicateHandle(GetCurrentProcess(),(HANDLE)99,guest_handle,&out,0,0,0));
 assert(DuplicateHandle(GetCurrentProcess(),(HANDLE)4,NULL,NULL,0,0,1)&&!got_dest);
 assert(GetProcessId(guest_handle)==99&&GetProcessId(GetCurrentProcess())==99&&GetProcessId(other_event)==0);
 // A child end-event shares a PID but must never be mistaken for a request to terminate its parent.
 teb.UserReserved[0]=(uintptr_t)&parent_guest;parent_guest.ended=(HANDLE)45;parent_guest.exit_process=mock_self_exit;
 assert(!TerminateProcess(guest_handle,123)&&self_exits==0&&!parent_guest.terminated);
 assert(TerminateProcess(GetCurrentProcess(),123)&&self_exits==1&&parent_guest.terminated);
 TerminateProcess(parent_guest.ended,123);assert(self_exits==2);
 assert(!TerminateProcess(other_event,123)&&self_exits==2);
 assert(!TerminateProcess(NULL,123)&&last_error==ERROR_INVALID_HANDLE&&self_exits==2);
 teb.UserReserved[0]=0;
 // The application folder beats a global directory; explicit altered/search flags retain original behavior.
 typeof(*teb.Peb) peb;typeof(*peb.ProcessParameters) params;
 teb.Peb=&peb;peb.ProcessParameters=&params;params.ImagePathName.Buffer=L"C:\\windows\\orbis32host.exe";
 WCHAR *result=NULL,*unknown=(void *)1;
 guest_path=L"Z:\\orbisdesk\\steam-games\\70\\hl.exe";dll_directory.Buffer=L"E:\\L4D2\\bin";dll_directory.Length=12;
 assert(LdrGetDllPath(L"filesystem_stdio.dll",0,&result,&unknown)==2&&!unknown);
 assert(!wcscmp(selected,guest_path)&&!locked);
 assert(LdrGetDllPath(L"C:\\explicit\\module.dll",LOAD_WITH_ALTERED_SEARCH_PATH,&result,&unknown)==2);
 assert(!wcscmp(selected,L"C:\\explicit\\module.dll"));
 assert(LdrGetDllPath(L"module.dll",LOAD_LIBRARY_SEARCH_SYSTEM32,&result,&unknown)==3&&search_calls==1);
 assert(LdrGetDllPath(L"module.dll",LOAD_LIBRARY_SEARCH_APPLICATION_DIR,&result,&unknown)==3);assert(!wcscmp(selected,guest_path));
 guest_path=NULL;assert(LdrGetDllPath(L"module.dll",0,&result,&unknown)==2);
 assert(!wcscmp(selected,params.ImagePathName.Buffer));free(selected);
 // Each EXE sees its own configured version and its own manifest, retaining Windows version-lie rules.
 requested_version=L"win10";manifest="<supportedOS Id='{8E0F7A12-BFB3-4FE8-B9A5-48FD50A15A9A}'/>";
 RTL_OSVERSIONINFOEXW v={6,2,9200};ps4_guest_version((HMODULE)1,&v);
 assert(v.dwMajorVersion==10&&v.dwBuildNumber==19045);
 assert(!wcscmp(queried_key,L"Software\\Wine\\AppDefaults\\PlayGTAIV.exe"));
 requested_version=L"win7";v=(RTL_OSVERSIONINFOEXW){10,0,19045};ps4_guest_version((HMODULE)2,&v);
 assert(v.dwMajorVersion==6&&v.dwMinorVersion==1&&v.dwBuildNumber==7601);
 assert(!wcscmp(queried_key,L"Software\\Wine\\AppDefaults\\other.exe"));
 requested_version=NULL;manifest=NULL;v=(RTL_OSVERSIONINFOEXW){10,0,19045};ps4_guest_version((HMODULE)1,&v);
 assert(v.dwMajorVersion==6&&v.dwMinorVersion==2);
 pe.OptionalHeader.MajorOperatingSystemVersion=10;v=(RTL_OSVERSIONINFOEXW){10,0,19045};
 ps4_guest_version((HMODULE)1,&v);assert(v.dwMajorVersion==10);
 // Repeated queries do not hit the registry; another guest is independent; failed initialization retries.
 int before=registry_queries;
 struct ps4_guest cached={0},other={0},retry={0};
 requested_version=L"win10";manifest="<supportedOS Id='{8e0f7a12-bfb3-4fe8-b9a5-48fd50a15a9a}'/>";current_module=(HMODULE)1;
 assert(InitOnceExecuteOnce(&cached.version_once,ps4_init_guest_version,&cached,NULL));
 assert(cached.version_info.dwMajorVersion==10&&registry_queries==before+1);
 requested_version=L"win7";current_module=(HMODULE)2;
 assert(InitOnceExecuteOnce(&cached.version_once,ps4_init_guest_version,&cached,NULL));
 assert(cached.version_info.dwMajorVersion==10&&registry_queries==before+1);
 assert(InitOnceExecuteOnce(&other.version_once,ps4_init_guest_version,&other,NULL));
 assert(other.version_info.dwMinorVersion==1&&registry_queries==before+2);
 fail_version=1;assert(!InitOnceExecuteOnce(&retry.version_once,ps4_init_guest_version,&retry,NULL)&&!retry.version_once.done);
 fail_version=0;assert(InitOnceExecuteOnce(&retry.version_once,ps4_init_guest_version,&retry,NULL)&&retry.version_info.dwMinorVersion==1);
 puts("PASS: canonical FD pressure, guest/root WinMain isolation, real DuplicateHandle semantics, DLL application paths and per-EXE version/manifest.");
}
"""
with tempfile.TemporaryDirectory() as tmp:
    d=pathlib.Path(tmp);(d/'check.c').write_text(code)
    subprocess.run(['cc','-std=gnu11','-g','-O1','-fsanitize=address,undefined','-no-pie',str(d/'check.c'),'-o',str(d/'check')],check=True)
    subprocess.run([str(d/'check')],check=True)
