/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* B0 of the plan for 32-bit programs as guests of explorer (pe32-en-explorer-plan.md, section 7):
 * run as a 64-bit guest of explorer, it measures what that plan needs and changes nothing that
 * stays. Every line goes to wow64probe-result.txt beside the executable (appended, one block per
 * run):
 * - lowmap: the address space below 4 GiB as Wine shows it (VirtualQuery: Wine's own reserved
 *   areas are free here), the totals, the largest free range and every image or region of 1 MiB or
 *   more that is not free. The 32-bit world needs a large free range below 4 GiB.
 * - signals: whether this process has W136's raw signal entry (PW_NATIVE_SIGNALS, set for explorer
 *   by C:\orbis\wow64probe.txt).
 * - cpu: wow64native.dll loaded here and BTCpuProcessInit called on a thread of its own. That
 *   function writes the CPU flags through TlsSlots[WOW64_TLS_WOW64INFO], which wow64.dll fills in a
 *   WoW64 process and nobody here: the thread gives it a WOW64INFO of its own for the call and puts
 *   the slot back. No 32-bit code runs. Without raw signals the backend refuses
 *   (STATUS_NOT_SUPPORTED), which is the expected answer then. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>

#define WOW64_TLS_WOW64INFO 10          /* include/winternl.h */
#define TEB_TLS_SLOTS 0x1480            /* TEB64.TlsSlots */
#define LIMIT_4G 0x100000000ull
#define MAX_LISTED 200

typedef LONG (WINAPI *cpu_init_proc)(void);
static FILE *out;

static const char *state_name(DWORD state)
{
    return state == MEM_COMMIT ? "commit" : state == MEM_RESERVE ? "reserve" : "free";
}

static const char *type_name(DWORD type)
{
    return type == MEM_IMAGE ? "image" : type == MEM_MAPPED ? "mapped" : type == MEM_PRIVATE ? "private" : "-";
}

static void lowmap(void)
{
    MEMORY_BASIC_INFORMATION info;
    ULONG_PTR at = 0x10000, largest_at = 0;
    ULONGLONG free_bytes = 0, reserved = 0, committed = 0, largest = 0;
    unsigned int listed = 0, skipped = 0;

    while (at < LIMIT_4G && VirtualQuery((void *)at, &info, sizeof(info)))
    {
        ULONG_PTR base = (ULONG_PTR)info.BaseAddress;
        ULONGLONG size = info.RegionSize;

        if (base + size > LIMIT_4G) size = LIMIT_4G - base;
        if (info.State == MEM_FREE)
        {
            free_bytes += size;
            if (size > largest) { largest = size; largest_at = base; }
        }
        else
        {
            if (info.State == MEM_RESERVE) reserved += size;
            else committed += size;
            if (size >= 0x100000 || info.Type == MEM_IMAGE)
            {
                if (listed < MAX_LISTED)
                {
                    char name[MAX_PATH] = "";
                    if (info.Type == MEM_IMAGE)
                        GetModuleFileNameA((HMODULE)info.AllocationBase, name, sizeof(name));
                    fprintf(out, "region base=%#llx size=%#llx state=%s type=%s alloc=%#llx %s\n",
                            (ULONGLONG)base, size, state_name(info.State), type_name(info.Type),
                            (ULONGLONG)(ULONG_PTR)info.AllocationBase, name);
                    listed++;
                }
                else skipped++;
            }
        }
        if (base + info.RegionSize <= at) break;
        at = base + info.RegionSize;
    }
    fprintf(out, "lowmap free=%#llx reserved=%#llx committed=%#llx largest_free=%#llx at=%#llx listed=%u not_listed=%u\n",
            free_bytes, reserved, committed, largest, (ULONGLONG)largest_at, listed, skipped);
}

static DWORD WINAPI cpu_thread(void *unused)
{
    void **slots = (void **)((BYTE *)NtCurrentTeb() + TEB_TLS_SLOTS);
    ULONG info[16] = {0};               /* WOW64INFO: NativeSystemPageSize, CpuFlags, ... */
    cpu_init_proc init;
    HMODULE module;
    void *saved;
    LONG status;

    if (!(module = LoadLibraryW(L"wow64native.dll")))
    {
        fprintf(out, "cpu load_failed error=%lu\n", GetLastError());
        return 1;
    }
    fprintf(out, "cpu module=%p below_4g=%d\n", (void *)module, (ULONG_PTR)module < LIMIT_4G);
    if (!(init = (cpu_init_proc)(void *)GetProcAddress(module, "BTCpuProcessInit")))
    {
        fprintf(out, "cpu no_BTCpuProcessInit error=%lu\n", GetLastError());
        return 1;
    }
    saved = slots[WOW64_TLS_WOW64INFO];
    slots[WOW64_TLS_WOW64INFO] = info;
    status = init();
    slots[WOW64_TLS_WOW64INFO] = saved;
    fprintf(out, "cpu BTCpuProcessInit status=%#lx cpu_flags=%#lx slot_was=%p\n", (unsigned long)status, info[1], saved);
    return 0;
}

int WINAPI WinMain(HINSTANCE instance, HINSTANCE previous, LPSTR command, int show)
{
    char path[MAX_PATH], *slash, signals[16] = "";
    SYSTEMTIME now;
    HANDLE thread;

    GetModuleFileNameA(NULL, path, sizeof(path));
    if ((slash = strrchr(path, '\\'))) strcpy(slash + 1, "wow64probe-result.txt");
    if (!(out = fopen(path, "a"))) return 1;
    GetLocalTime(&now);
    fprintf(out, "run %04u-%02u-%02u %02u:%02u:%02u pid=%lu\n", now.wYear, now.wMonth, now.wDay,
            now.wHour, now.wMinute, now.wSecond, GetCurrentProcessId());
    GetEnvironmentVariableA("PW_NATIVE_SIGNALS", signals, sizeof(signals));
    fprintf(out, "signals PW_NATIVE_SIGNALS=%s\n", signals[0] ? signals : "(unset)");
    fflush(out);
    lowmap();
    fflush(out);
    if ((thread = CreateThread(NULL, 0, cpu_thread, NULL, 0, NULL)))
    {
        WaitForSingleObject(thread, INFINITE);
        CloseHandle(thread);
    }
    else fprintf(out, "cpu thread_failed error=%lu\n", GetLastError());
    fprintf(out, "end\n");
    fclose(out);
    return 0;
}
