/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Called only inside the existing bounded first-chance exception trace.
 * Reads use NtReadVirtualMemory through ps4_guest_read: never dereference a
 * faulting instruction/stack directly or change the exception context. */
static void ps4_guest_fault_context( LONG n, const CONTEXT *context )
{
    static const char hex[] = "0123456789abcdef";
    BYTE bytes[16];
    char code[49];
    ULONG_PTR ip, sp;
    UINT i;
#ifdef __i386__
    DWORD stack[8];
    ip = context->Eip; sp = context->Esp;
    ERR( "PWFAULT n=%ld regs32 eax=%#lx ebx=%#lx ecx=%#lx edx=%#lx esi=%#lx edi=%#lx ebp=%#lx esp=%#lx eip=%#lx flags=%#lx\n",
         n, (unsigned long)context->Eax, (unsigned long)context->Ebx,
         (unsigned long)context->Ecx, (unsigned long)context->Edx,
         (unsigned long)context->Esi, (unsigned long)context->Edi,
         (unsigned long)context->Ebp, (unsigned long)context->Esp,
         (unsigned long)context->Eip, (unsigned long)context->EFlags );
#else
    ULONGLONG stack[8];
    ip = context->Rip; sp = context->Rsp;
    ERR( "PWFAULT n=%ld regs64 rax=%#llx rbx=%#llx rcx=%#llx rdx=%#llx rsi=%#llx rdi=%#llx rbp=%#llx rsp=%#llx rip=%#llx flags=%#lx\n",
         n, (unsigned long long)context->Rax, (unsigned long long)context->Rbx,
         (unsigned long long)context->Rcx, (unsigned long long)context->Rdx,
         (unsigned long long)context->Rsi, (unsigned long long)context->Rdi,
         (unsigned long long)context->Rbp, (unsigned long long)context->Rsp,
         (unsigned long long)context->Rip, (unsigned long)context->EFlags );
    ERR( "PWFAULT n=%ld regs64 r8=%#llx r9=%#llx r10=%#llx r11=%#llx r12=%#llx r13=%#llx r14=%#llx r15=%#llx\n",
         n, (unsigned long long)context->R8, (unsigned long long)context->R9,
         (unsigned long long)context->R10, (unsigned long long)context->R11,
         (unsigned long long)context->R12, (unsigned long long)context->R13,
         (unsigned long long)context->R14, (unsigned long long)context->R15 );
#endif
    if (ps4_guest_read( ip, bytes, sizeof(bytes) ))
    {
        for (i = 0; i < sizeof(bytes); i++)
        {
            code[i * 3] = hex[bytes[i] >> 4];
            code[i * 3 + 1] = hex[bytes[i] & 15];
            code[i * 3 + 2] = ' ';
        }
        code[sizeof(bytes) * 3 - 1] = 0;
        ERR( "PWFAULT n=%ld instruction_bytes=%s\n", n, code );
    }
    else ERR( "PWFAULT n=%ld instruction_bytes=unreadable\n", n );
    if (ps4_guest_read( sp, stack, sizeof(stack) ))
        for (i = 0; i < ARRAY_SIZE(stack); i++)
            ERR( "PWFAULT n=%ld stack_slot=%u value=%#llx\n", n, i, (unsigned long long)stack[i] );
    else ERR( "PWFAULT n=%ld stack=unreadable\n", n );
}
