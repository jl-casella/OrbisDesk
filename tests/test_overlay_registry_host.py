#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actual Explorer registry RPC parser with host Win32 boundary models; not Wine acceptance."""
from pathlib import Path
import subprocess,tempfile
r=Path(__file__).resolve().parents[1]
header=(r/'platform/ps4/pw_overlay_registry_guest.inc.c').read_text()
a=header.index('static void orbis_overlay_registry_poll(void)');b=header.index('static DWORD WINAPI orbis_overlay_registry_worker',a)
function=header[a:b]
builder=(r/'tools/build-explorer-hw.py').read_text()
assert 'orbis_overlay_registry_start();' in builder and 'registry_worker_source_sha256' in builder
assert 'startup=desktop' in header and 'Sleep(150)' in header
code=r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <wchar.h>
typedef wchar_t WCHAR;typedef long LSTATUS;
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define CP_UTF8 65001
#define MB_ERR_INVALID_CHARS 8
#define ERROR_INVALID_NAME 123
#define ERR(...) ((void)0)
static char input[160],output[200];static int writes,reads,value=3,write_status,read_status;
static int MultiByteToWideChar(unsigned cp,unsigned flags,const char *text,int length,WCHAR *out,int size){
 assert(cp==CP_UTF8 && flags==MB_ERR_INVALID_CHARS && length==-1);
 if(strlen(text)>=(size_t)size)return 0;
 for(size_t i=0;i<=strlen(text);i++){if((unsigned char)text[i]>127)return 0;out[i]=(unsigned char)text[i];}return strlen(text)+1;
}
static int orbis_native_call(const char *request,char *reply,size_t size){
 if(!strcmp(request,"<overlay-render-poll>")){snprintf(reply,size,"%s",input);return 1;}
 assert(!strncmp(request,"<overlay-render-result>",23));snprintf(output,sizeof(output),"%s",request+23);snprintf(reply,size,"-");return 1;
}
static int orbis_overlay_render_read(const WCHAR *exe,LSTATUS *status){assert(!wcscmp(exe,L"hl2.exe"));reads++;*status=read_status;return read_status?-1:value;}
static LSTATUS orbis_overlay_render_write(const WCHAR *exe,int choice){assert(!wcscmp(exe,L"hl2.exe"));writes++;if(!write_status)value=choice;return write_status;}
static int orbis_registry_traced(void){return 1;}
'''+function+r'''
int main(void){
 strcpy(input,"get hl2.exe");orbis_overlay_registry_poll();assert(!strcmp(output,"get 3 0 hl2.exe") && reads==1 && !writes);
 strcpy(input,"set 2 hl2.exe");orbis_overlay_registry_poll();assert(!strcmp(output,"set 2 0 hl2.exe") && reads==2 && writes==1);
 write_status=5;strcpy(input,"set 3 hl2.exe");orbis_overlay_registry_poll();assert(!strcmp(output,"set - 5 hl2.exe") && reads==2 && writes==2);
 read_status=5;strcpy(input,"get hl2.exe");orbis_overlay_registry_poll();assert(!strcmp(output,"get - 5 hl2.exe"));
 strcpy(input,"get path/hl2.exe");orbis_overlay_registry_poll();assert(!strcmp(output,"get - 123 path/hl2.exe"));
 strcpy(input,"-");strcpy(output,"untouched");orbis_overlay_registry_poll();assert(!strcmp(output,"untouched"));
 strcpy(input,"set 7 hl2.exe");orbis_overlay_registry_poll();assert(!strcmp(output,"untouched"));
 puts("PASS: desktop renderer RPC before any guest, get/set readback, errors, invalid names and idle; native taken gate is covered by overlay tests");
}
'''
with tempfile.TemporaryDirectory() as tmp:
    d=Path(tmp);(d/'check.c').write_text(code)
    subprocess.run(['cc','-std=gnu11','-O1','-g','-Wall','-Werror','-fsanitize=address,undefined','-no-pie',str(d/'check.c'),'-o',str(d/'check')],check=True)
    subprocess.run([str(d/'check')],check=True,timeout=10)
