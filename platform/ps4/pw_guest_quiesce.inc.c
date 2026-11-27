/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* The server can signal a thread handle before its pthread stops. Query the
 * native exit boundary before unloading ANY guest code, heaps or GPU objects. */
static BOOL ps4_guest_native_quiet(struct ps4_guest *guest,DWORD timeout)
{
    struct pw_thread_quiet state[ARRAY_SIZE(guest->threads)];
    HANDLE handles[ARRAY_SIZE(guest->threads)];
    UINT count,i,pending;
    DWORD begin=GetTickCount(),self=GetCurrentThreadId();
    memset(state,0,sizeof(state));
    RtlEnterCriticalSection(&guest->lock);
    count=guest->thread_count;memcpy(handles,guest->threads,count*sizeof(*handles));
    RtlLeaveCriticalSection(&guest->lock);
    do {
        pending=0;
        for(i=0;i<count;i++) {
            ULONG received=0;NTSTATUS status;
            if(GetThreadId(handles[i])==self)continue;
            state[i].magic=PW_THREAD_QUIET_MAGIC;state[i].active=2;
            status=NtQueryInformationThread(handles[i],ThreadTimes,&state[i],sizeof(state[i]),&received);
            if(status||received!=sizeof(state[i])||state[i].magic!=PW_THREAD_QUIET_MAGIC||state[i].active==2) {
                ERR("PWGUEST native_quiet unsupported module=%p thread=%04lx status=%#lx bytes=%lu; kept loaded\n",
                    guest->module,GetThreadId(handles[i]),status,received);
                return FALSE;
            }
            if(state[i].active)pending++;
        }
        if(!pending) {
            RtlEnterCriticalSection(&guest->lock);
            pending=guest->thread_count!=count;
            RtlLeaveCriticalSection(&guest->lock);
            if(pending)return FALSE;
            if(ps4_pw_traced()) ERR("PWGUEST native_quiet module=%p threads=%u elapsed_ms=%lu\n",guest->module,count,GetTickCount()-begin);
            return TRUE;
        }
        if(GetTickCount()-begin>=timeout)break;
        Sleep(10);
    }while(1);
    ERR("PWGUEST native_quiet timeout module=%p active=%u elapsed_ms=%lu; kept loaded\n",guest->module,pending,GetTickCount()-begin);
    return FALSE;
}
