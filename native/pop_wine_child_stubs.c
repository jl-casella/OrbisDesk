/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* PoP Phase D.1b: the separate Wine process has no GPU of its own (the title owns RADV/GNM and the display).
 * The title's telemetry reads the GPU busy counters from Mesa; here there are none, so they stay zero and
 * telemetry reports its existing "warmup / no completed span" status, never a fabricated measurement. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/stat.h>
#include <pthread.h>
#ifndef POP_CHILD_GPU   /* with RADV linked (D.4), Mesa defines it */
void ac_ps4_get_gpu_app_busy(uint64_t *busy, uint64_t *span, uint64_t *lost);
void ac_ps4_get_gpu_app_busy(uint64_t *busy, uint64_t *span, uint64_t *lost)
{
    if (busy) *busy = 0;
    if (span) *span = 0;
    if (lost) *lost = 0;
}
#endif

/* ntdll's NtCreateUserProcess hook records the starter's directory and variables for the title's program
 * switch (native/wine_hardware.c) before asking for it. This process cannot switch the title; the switch
 * request itself is the platform's weak ENOSYS (platform/ps4/pw_wine_platform.c), so nothing is recorded. */
static char switch_dir[400];
void pw_hw_switch_context(const char *dir, const char *env);
void pw_hw_switch_context(const char *dir, const char *env)
{
    (void)env;
    snprintf(switch_dir, sizeof(switch_dir), "%s", dir ? dir : "");
}

/* PoP D.4: ntdll's NtCreateUserProcess hook asks for a program switch for every program this process starts.
 * Here that is a hand-over: the title's explorer starts the program as a guest of the title, where the GPU is
 * (a borrowed system process cannot map GPU memory: hardware 2026-11-12, kernel "gbase_map_2 invalid va").
 * A launcher run separately (both need the same fixed base) thus leaves the base to the game it starts. This
 * process then waits until the game ends, as a launcher waits on its game, and ends: what the launcher keeps
 * (Prince of Persia's PrinceSM shared memory, which POP.exe checks) lives as long as the game. The calling thread
 * stays in CreateProcess meanwhile; the launcher's other threads run. */
extern void pop_wine_child_log(const char *line);
#define TITLE_LAUNCH_DIR "/data/orbisdesk/process-p014/"

/* the reply's state for this token: 1 started, 2 ended, -1 failed (*value: pid or error), 0 none yet */
static int title_launch_reply(unsigned token, unsigned *value)
{
    char text[128], word[16];
    unsigned got_token = 0, got_value = 0;
    ssize_t got;
    int fd = open(TITLE_LAUNCH_DIR "title-launch-reply", O_RDONLY);
    if (fd < 0) return 0;
    got = read(fd, text, sizeof(text) - 1);
    close(fd);
    if (got <= 0) return 0;
    text[got] = 0;
    word[0] = 0;
    if (sscanf(text, "%u %15s %u", &got_token, word, &got_value) < 2 || got_token != token) return 0;
    *value = got_value;
    if (!strcmp(word, "started")) return 1;
    if (!strcmp(word, "ended")) return 2;
    if (!strcmp(word, "failed")) return -1;
    return 0;
}

/* hands the program to the title; the reply's state (see title_launch_reply), *token_out names its end event */
static int title_launch_start(const char *image, const char *command_line, unsigned *token_out, unsigned *value_out)
{
    char text[2048], line[900];
    static unsigned serial;
    unsigned token = (((unsigned)getpid() << 16) ^ (unsigned)time(NULL)) + serial++, value = 0;
    int n, fd, ok = 0, state = 0, waited;

    unlink(TITLE_LAUNCH_DIR "title-launch-reply");
    n = snprintf(text, sizeof(text), "%s\n%s\n%s\n%u\n", image, command_line ? command_line : image, switch_dir, token);
    fd = open(TITLE_LAUNCH_DIR "title-launch.tmp", O_WRONLY | O_CREAT | O_TRUNC, 0666);
    if (fd >= 0 && n > 0) { ok = write(fd, text, (size_t)n) == n; close(fd); chmod(TITLE_LAUNCH_DIR "title-launch.tmp", 0666); }
    ok = ok && !rename(TITLE_LAUNCH_DIR "title-launch.tmp", TITLE_LAUNCH_DIR "title-launch");
    snprintf(line, sizeof(line), "{\"build\":\"P021\",\"event\":\"title_launch\",\"image\":\"%.200s\",\"command\":\"%.400s\",\"token\":%u,\"ok\":%d}",
             image, command_line ? command_line : "(null)", token, ok);
    pop_wine_child_log(line);
    if (!ok) return -1;
    /* the title starts it within a few seconds (its watcher polls every 500 ms) */
    for (waited = 0; waited < 600 && !(state = title_launch_reply(token, &value)); waited++) usleep(100000);
    snprintf(line, sizeof(line), "{\"build\":\"P021\",\"event\":\"title_launch_reply\",\"token\":%u,\"state\":%d,\"value\":%u,\"ms\":%d}",
             token, state, value, waited * 100);
    pop_wine_child_log(line);
    *token_out = token;
    *value_out = value;
    return state;
}

/* the D.4 hand-over, kept for a title without the named end event: this thread waits for the game, then the
 * process ends (what the launcher keeps lives as long as the game) */
static void title_launch_wait_end(unsigned token) __attribute__((noreturn));
static void title_launch_wait_end(unsigned token)
{
    char line[200];
    unsigned value = 0;
    int state = 1;
    while (state == 1) { usleep(250000); state = title_launch_reply(token, &value); if (!state) state = 1; }
    snprintf(line, sizeof(line), "{\"build\":\"P021\",\"event\":\"title_launch_ended\",\"token\":%u,\"state\":%d}", token, state);
    pop_wine_child_log(line);
    exit(0);
}

int pw_hw_switch_program(const char *image, const char *command_line);
int pw_hw_switch_program(const char *image, const char *command_line)
{
    unsigned token = 0, value = 0;
    if (title_launch_start(image, command_line, &token, &value) <= 0) return -1;   /* CreateProcess fails as before */
    title_launch_wait_end(token);
}

/* PoP D.5 (D.4 on hardware 2026-11-13: Prince of Persia's launcher starts POP.exe from a thread, then sets an event
 * its main thread waits 25 s for, then waits on the process handle and reads the exit code; with CreateProcess held
 * until the game ended, the launcher said it could not start the game after 25 seconds). CreateProcess of a program
 * (not one of Wine's helpers) hands it to the title, as D.4 did, and returns: its process and thread handles are the
 * title's named end event for it (tools/patch-explorer-open.py), signaled when the game has ended, as a process
 * handle is (the title's own guests' process handles are their end events too, W267). NtQueryInformationProcess
 * answers the exit status for them: STILL_ACTIVE, then the status the title reported. Not forwarded: TerminateProcess
 * on that handle (it fails) and the process and thread ids (0). */
struct pop_ustr { unsigned short Length, MaximumLength; unsigned short *Buffer; };
struct pop_objattr { unsigned int Length; void *RootDirectory; struct pop_ustr *ObjectName; unsigned int Attributes;
                     void *SecurityDescriptor, *SecurityQualityOfService; };
struct pop_attr { uintptr_t Attribute; size_t Size; void *ValuePtr; size_t *ReturnLength; };
struct pop_attr_list { size_t TotalLength; struct pop_attr Attributes[1]; };
extern unsigned int NtOpenEvent(void **handle, unsigned int access, const struct pop_objattr *attr);
extern unsigned int NtWaitForSingleObject(void *handle, unsigned char alertable, const long long *timeout);
extern unsigned int NtCompareObjects(void *first, void *second);
extern unsigned int NtClose(void *handle);
extern unsigned int __real_NtCreateUserProcess(void **, void **, unsigned int, unsigned int, void *, void *, unsigned int,
                                               unsigned int, void *, void *, void *);
extern unsigned int __real_NtQueryInformationProcess(void *, int, void *, unsigned int, unsigned int *);

static struct { void *own; unsigned token, code; int ended; } handed[16];
static unsigned handed_next;
static pthread_mutex_t handed_lock = PTHREAD_MUTEX_INITIALIZER;

static void pop_ascii(char *out, size_t size, const struct pop_ustr *s, int nt_prefix)
{
    const unsigned short *p = s->Buffer;
    size_t length = p ? s->Length / 2 : 0, n;
    if (nt_prefix && length >= 4 && p[0] == '\\' && p[1] == '?' && p[2] == '?' && p[3] == '\\') { p += 4; length -= 4; }
    for (n = 0; n < length && n < size - 1; n++) out[n] = p[n] < 128 ? (char)p[n] : '?';
    out[n] = 0;
}

static int pop_helper(const char *image)
{
    static const char *const helpers[] = {"wineboot.exe", "services.exe", "rpcss.exe", "svchost.exe",
        "plugplay.exe", "winedevice.exe", "conhost.exe", "winemenubuilder.exe"};
    const char *base = strrchr(image, '\\');
    size_t k;
    base = base ? base + 1 : image;
    for (k = 0; k < sizeof(helpers) / sizeof(helpers[0]); k++)
    {
        const char *a = base, *b = helpers[k];
        while (*a && (*a | 0x20) == *b) { a++; b++; }
        if (!*a && !*b) return 1;
    }
    return 0;
}

static unsigned int pop_open_end(unsigned token, void **handle)
{
    char name[64];
    unsigned short wide[64];
    struct pop_ustr ustr;
    struct pop_objattr attr = {sizeof(attr), NULL, &ustr, 0, NULL, NULL};
    int n = snprintf(name, sizeof(name), "\\BaseNamedObjects\\PWTitleLaunch_%u", token), k;
    for (k = 0; k <= n; k++) wide[k] = (unsigned char)name[k];
    ustr.Length = (unsigned short)(n * 2);
    ustr.MaximumLength = (unsigned short)(n * 2 + 2);
    ustr.Buffer = wide;
    *handle = NULL;
    return NtOpenEvent(handle, 0x00100000 | 0x0001 /* SYNCHRONIZE | EVENT_QUERY_STATE */, &attr);
}

unsigned int __wrap_NtCreateUserProcess(void **process_ptr, void **thread_ptr, unsigned int process_access,
                                        unsigned int thread_access, void *process_attr, void *thread_attr,
                                        unsigned int process_flags, unsigned int thread_flags, void *params,
                                        void *info, void *ps_attr);
unsigned int __wrap_NtCreateUserProcess(void **process_ptr, void **thread_ptr, unsigned int process_access,
                                        unsigned int thread_access, void *process_attr, void *thread_attr,
                                        unsigned int process_flags, unsigned int thread_flags, void *params,
                                        void *info, void *ps_attr)
{
    /* RTL_USER_PROCESS_PARAMETERS (x86-64): CurrentDirectory.DosPath 0x38, ImagePathName 0x60, CommandLine 0x70 */
    const struct pop_ustr *path = params ? (const struct pop_ustr *)((char *)params + 0x60) : NULL;
    char image[260], command[1024], line[700];
    unsigned token = 0, value = 0, s1, s2, s3;
    void *process = NULL, *thread = NULL, *own = NULL;
    size_t n;
    int state;

    if (!path || !path->Buffer) goto real;
    pop_ascii(image, sizeof(image), path, 1);
    if (pop_helper(image)) goto real;
    pop_ascii(command, sizeof(command), (const struct pop_ustr *)((char *)params + 0x70), 0);
    pop_ascii(switch_dir, sizeof(switch_dir), (const struct pop_ustr *)((char *)params + 0x38), 0);
    for (n = strlen(switch_dir); n > 3 && switch_dir[n - 1] == '\\'; n--) switch_dir[n - 1] = 0;
    state = title_launch_start(image, command, &token, &value);
    if (state <= 0) return 0xC0000001;   /* STATUS_UNSUCCESSFUL: the title did not start it */
    s1 = pop_open_end(token, &process);
    s2 = pop_open_end(token, &thread);
    s3 = pop_open_end(token, &own);
    snprintf(line, sizeof(line), "{\"build\":\"P023\",\"event\":\"title_process\",\"image\":\"%.200s\",\"token\":%u,"
             "\"state\":%d,\"value\":%u,\"open\":[\"%x\",\"%x\",\"%x\"]}", image, token, state, value, s1, s2, s3);
    pop_wine_child_log(line);
    if (s1 || s2 || s3)
    {
        /* a title without the named end event: the D.4 hand-over */
        if (process) NtClose(process);
        if (thread) NtClose(thread);
        if (own) NtClose(own);
        title_launch_wait_end(token);
    }
    pthread_mutex_lock(&handed_lock);
    n = handed_next++ % (sizeof(handed) / sizeof(handed[0]));
    if (handed[n].own) NtClose(handed[n].own);
    handed[n].own = own;
    handed[n].token = token;
    handed[n].code = 0;
    handed[n].ended = 0;
    pthread_mutex_unlock(&handed_lock);
    if (ps_attr)
    {
        struct pop_attr_list *list = ps_attr;
        size_t count = (list->TotalLength - sizeof(size_t)) / sizeof(struct pop_attr), k;
        for (k = 0; k < count; k++)   /* PS_ATTRIBUTE_CLIENT_ID, PS_ATTRIBUTE_IMAGE_INFO: no process of its own */
            if ((list->Attributes[k].Attribute == 0x10003 || list->Attributes[k].Attribute == 6) &&
                list->Attributes[k].ValuePtr)
                memset(list->Attributes[k].ValuePtr, 0, list->Attributes[k].Size);
    }
    if (info) *(unsigned int *)((char *)info + sizeof(size_t)) = 0;   /* PS_CREATE_INFO.State: PsCreateInitialState */
    *process_ptr = process;
    *thread_ptr = thread;
    return 0;
real:
    return __real_NtCreateUserProcess(process_ptr, thread_ptr, process_access, thread_access, process_attr, thread_attr,
                                      process_flags, thread_flags, params, info, ps_attr);
}

unsigned int __wrap_NtQueryInformationProcess(void *handle, int info_class, void *info, unsigned int size, unsigned int *ret);
unsigned int __wrap_NtQueryInformationProcess(void *handle, int info_class, void *info, unsigned int size, unsigned int *ret)
{
    unsigned int status = __real_NtQueryInformationProcess(handle, info_class, info, size, ret), k, code = 0x103;
    char line[200];
    long long zero = 0;
    int found = -1, unknown = 0;

    /* an event handle: STATUS_ACCESS_DENIED (access is checked first) or STATUS_OBJECT_TYPE_MISMATCH */
    if ((status != 0xC0000022 && status != 0xC0000024) || info_class != 0 /* ProcessBasicInformation */ || !info || size < 48)
        return status;
    pthread_mutex_lock(&handed_lock);
    for (k = 0; k < sizeof(handed) / sizeof(handed[0]) && found < 0; k++)
        if (handed[k].own && !NtCompareObjects(handed[k].own, handle)) found = (int)k;
    if (found >= 0)
    {
        if (handed[found].ended) code = handed[found].code;
        else if (!NtWaitForSingleObject(handle, 0, &zero))
        {
            unsigned value = 0;
            /* the title wrote the exit status before signaling; a later hand-over may have replaced that reply */
            unknown = title_launch_reply(handed[found].token, &value) != 2;
            code = unknown ? 0 : value;
            handed[found].code = code;
            handed[found].ended = 1;
            snprintf(line, sizeof(line), "{\"build\":\"P023\",\"event\":\"title_process_ended\",\"token\":%u,\"code\":%u,"
                     "\"code_unknown\":%d}", handed[found].token, code, unknown);
            pop_wine_child_log(line);
        }
    }
    pthread_mutex_unlock(&handed_lock);
    if (found < 0) return status;
    memset(info, 0, 48);   /* PROCESS_BASIC_INFORMATION: ExitStatus first */
    *(unsigned int *)info = code;
    if (ret) *ret = 48;
    return 0;
}

/* PoP D.3: win32u asks for a separate process's window under a point, which only the title composites;
 * this process has none of those. */
unsigned long long pw_hw_separate_window(int x, int y);
unsigned long long pw_hw_separate_window(int x, int y)
{
    (void)x; (void)y;
    return 0;
}

/* 04.20 frame generation: native/telemetry.c reads the hardware sink's shown/real rate through a weak reference,
 * and create-fself refuses a PRX with an undefined one. This process has no hardware sink: nothing to report. */
int pw_hw_sink_fg_rate(unsigned *width, unsigned *height, unsigned *shown_tenths, unsigned *real_tenths,
                       unsigned *generated_tenths, uint64_t *sample_us);
int pw_hw_sink_fg_rate(unsigned *width, unsigned *height, unsigned *shown_tenths, unsigned *real_tenths,
                       unsigned *generated_tenths, uint64_t *sample_us)
{
    (void)width; (void)height; (void)shown_tenths; (void)real_tenths; (void)generated_tenths; (void)sample_us;
    return 0;
}

/* Mesa's pipeline trace (tools/vk-h0/patch-mesa-pipeline-trace.py) calls the sink's PWPERF counter through a weak
 * reference too; the child's sink keeps no such counter. */
void pw_vk_pipeline_note(unsigned kind, uint64_t ns, unsigned flags);
void pw_vk_pipeline_note(unsigned kind, uint64_t ns, unsigned flags)
{
    (void)kind; (void)ns; (void)flags;
}
