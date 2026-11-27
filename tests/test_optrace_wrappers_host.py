#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actual generated Unix wrappers preserve arguments, statuses and outputs."""
import pathlib,subprocess,tempfile
r=pathlib.Path(__file__).resolve().parents[1]
generated=(r/'build/wine-optrace/optrace.c').read_text();generated=generated[generated.index('extern NTSTATUS'):]
code=r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include "pw_optrace.h"
#define WINAPI
typedef int32_t NTSTATUS;typedef void *HANDLE;typedef unsigned char BOOLEAN;
typedef int BOOL,LONG;typedef void *HWND;typedef struct {unsigned message;} MSG;
typedef unsigned DWORD,ULONG,UINT;typedef int WAIT_TYPE;
typedef struct {long long QuadPart;} LARGE_INTEGER;
typedef struct {uintptr_t status,information;} IO_STATUS_BLOCK;
typedef void (*PIO_APC_ROUTINE)(void *,IO_STATUS_BLOCK *,unsigned);
static int begins,ends,real_calls;static IO_STATUS_BLOCK iosb;
static unsigned key=123;static LARGE_INTEGER offset={55},timeout={-5000};static char buffer[4];
static HANDLE h=(void *)11,event=(void *)12;
static void callback(void *a,IO_STATUS_BLOCK *b,unsigned c){(void)a;(void)b;(void)c;}
struct pw_opstamp pw_optrace_begin(void){begins++;return (struct pw_opstamp){99,1};}
void pw_optrace_end(struct pw_opstamp s,unsigned op,int32_t status,uint64_t n){assert(s.tsc==99&&s.active);assert(status==(int32_t)(0x100+op));assert(n==(op==PW_OP_READ?4:0));ends++;}
NTSTATUS __real_NtReadFile(HANDLE a,HANDLE b,PIO_APC_ROUTINE cb,void *ctx,IO_STATUS_BLOCK *io,void *buf,ULONG size,LARGE_INTEGER *pos,ULONG *k){
 assert(a==h&&b==event&&cb==callback&&ctx==(void *)13&&io==&iosb&&buf==buffer&&size==4&&pos==&offset&&k==&key);
 io->information=3;buffer[0]='x';real_calls++;return 0x100+PW_OP_READ;
}
NTSTATUS __real_NtWaitForSingleObject(HANDLE a,BOOLEAN b,const LARGE_INTEGER *t){assert(a==h&&b==1&&t==&timeout);real_calls++;return 0x100+PW_OP_WAIT_ONE;}
NTSTATUS __real_NtWaitForMultipleObjects(DWORD n,const HANDLE *a,WAIT_TYPE type,BOOLEAN b,const LARGE_INTEGER *t){assert(n==1&&a[0]==h&&type==1&&!b&&!t);real_calls++;return 0x100+PW_OP_WAIT_MANY;}
NTSTATUS __real_NtDelayExecution(BOOLEAN b,const LARGE_INTEGER *t){assert(b==1&&t==&timeout);real_calls++;return 0x100+PW_OP_DELAY;}
NTSTATUS __real_NtYieldExecution(void){real_calls++;return 0x100+PW_OP_YIELD;}
NTSTATUS __real_NtQueryPerformanceCounter(LARGE_INTEGER *a,LARGE_INTEGER *b){assert(a==&offset&&b==&timeout);a->QuadPart=456;b->QuadPart=789;real_calls++;return 0x100+PW_OP_QPC;}
NTSTATUS __real_NtWaitForAlertByThreadId(const void *a,const LARGE_INTEGER *t){assert(a==h&&t==&timeout);real_calls++;return 0x100+PW_OP_WAIT_ALERT;}
NTSTATUS __real_NtAlertThreadByThreadId(HANDLE a){assert(a==h);real_calls++;return 0x100+PW_OP_ALERT;}
NTSTATUS __real_NtSetEvent(HANDLE a,LONG *p){assert(a==h);*p=7;real_calls++;return 0x100+PW_OP_SET_EVENT;}
NTSTATUS __real_NtResetEvent(HANDLE a,LONG *p){assert(a==h);*p=8;real_calls++;return 0x100+PW_OP_RESET_EVENT;}
BOOL __real_NtUserPeekMessage(MSG *m,HWND w,UINT first,UINT last,UINT flags){assert(w==h&&first==2&&last==3&&flags==4);m->message=42;real_calls++;return 0x100+PW_OP_PEEK;}
DWORD __real_NtUserMsgWaitForMultipleObjectsEx(DWORD n,const HANDLE *a,DWORD t,DWORD mask,DWORD flags){assert(n==1&&a[0]==h&&t==5&&mask==6&&flags==7);real_calls++;return 0x100+PW_OP_MSG_WAIT;}
'''+generated+r'''
int main(void){
 assert(__wrap_NtReadFile(h,event,callback,(void *)13,&iosb,buffer,4,&offset,&key)==0x100+PW_OP_READ&&iosb.information==3&&buffer[0]=='x');
 assert(__wrap_NtWaitForSingleObject(h,1,&timeout)==0x100+PW_OP_WAIT_ONE);
 assert(__wrap_NtWaitForMultipleObjects(1,&h,1,0,NULL)==0x100+PW_OP_WAIT_MANY);
 assert(__wrap_NtDelayExecution(1,&timeout)==0x100+PW_OP_DELAY);
 assert(__wrap_NtYieldExecution()==0x100+PW_OP_YIELD);
 assert(__wrap_NtQueryPerformanceCounter(&offset,&timeout)==0x100+PW_OP_QPC&&offset.QuadPart==456&&timeout.QuadPart==789);
 LONG previous;MSG message;
 assert(__wrap_NtWaitForAlertByThreadId(h,&timeout)==0x100+PW_OP_WAIT_ALERT);
 assert(__wrap_NtAlertThreadByThreadId(h)==0x100+PW_OP_ALERT);
 assert(__wrap_NtSetEvent(h,&previous)==0x100+PW_OP_SET_EVENT&&previous==7);
 assert(__wrap_NtResetEvent(h,&previous)==0x100+PW_OP_RESET_EVENT&&previous==8);
 assert(__wrap_NtUserPeekMessage(&message,h,2,3,4)==0x100+PW_OP_PEEK&&message.message==42);
 assert(__wrap_NtUserMsgWaitForMultipleObjectsEx(1,&h,5,6,7)==0x100+PW_OP_MSG_WAIT);
 assert(begins==12&&ends==12&&real_calls==12);puts("PASS: twelve actual generated wrappers forward exact parameters and preserve results, IOSB, messages, event state and QPC outputs");
}
'''
with tempfile.TemporaryDirectory() as t:
 p=pathlib.Path(t);(p/'check.c').write_text(code)
 subprocess.run(['cc','-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-no-pie','-I'+str(r/'platform/ps4'),str(p/'check.c'),'-o',str(p/'check')],check=True)
 subprocess.run([str(p/'check')],check=True)
