/* SPDX-License-Identifier: LGPL-2.1-or-later */
static void ps4_guest_compiler_cleanup(void)
{
    static RTL_SRWLOCK gate=RTL_SRWLOCK_INIT;
    WCHAR *environment=NULL,*mark;
    DWORD needed;
    struct ps4_guest *owner=ps4_guest_current();
    ULONG_PTR loading=NtCurrentTeb()->UserReserved[2];
    /* A nested guest must not own temporary process-heap cleanup storage. */
    ps4_guest_set(NtCurrentTeb(),NULL);NtCurrentTeb()->UserReserved[2]=0;
    RtlAcquireSRWLockExclusive(&gate);
    environment=HeapAlloc(GetProcessHeap(),0,PW_COMPILER_ENV_BYTES*sizeof(WCHAR));
    if(!environment)goto done;
    needed=GetEnvironmentVariableW(L"DXVK_CONFIG",environment,PW_COMPILER_ENV_BYTES);
    if(!needed)goto done;
    if(needed>=PW_COMPILER_ENV_BYTES) {
        ERR("PWCOMPILER cleanup rejected: oversized configuration\n");goto done;
    }
    mark=wcsstr(environment,PW_COMPILER_WMARK);
    if(!mark)goto done; /* Explicit user options stay exactly as supplied. */
    *mark=0;
    BOOL ok=SetEnvironmentVariableW(L"DXVK_CONFIG",environment[0]?environment:NULL);
    ERR("PWCOMPILER cleanup generated=found removed=%u policy=dxvk-default restart_required=1\n",ok);
done:
    if(environment)HeapFree(GetProcessHeap(),0,environment);
    RtlReleaseSRWLockExclusive(&gate);
    ps4_guest_set(NtCurrentTeb(),owner);NtCurrentTeb()->UserReserved[2]=loading;
}
