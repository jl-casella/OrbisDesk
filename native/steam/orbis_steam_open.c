/* SPDX-License-Identifier: GPL-3.0-or-later */
/* C:\orbis\steam-open.exe: "Open Steam Client" in OrbisDesk's Start menu and on its Desktop. A 64-bit
 * guest that asks the title's native side to open the Steam client (native/steam/steam_client.cpp,
 * pw_hw_steam_open), through the same channel kernelbase's overlay closer uses (tools/build-guest-hw.py
 * ps4_overlay_call, W239): xinput1_3's Unix library, call 3 (unix_pad_profile), whose 260-byte name
 * native/hw_pad.c reads as a request ("<steam-open>") and answers in place ("opened", "busy",
 * "error ..."). The client then takes the screen and the pad until it exits; this program ends at once.
 *
 * "steam-open.exe --register <app>" (2026-11-25), run by the Steam client when it opens and right before Play:
 * the prefix's Steam registration points at OrbisDesk again. A game's own Steam emulator (a repack's
 * ColdClient-style launcher) writes itself there as Steam, and Steam-aware programs opened later went to it
 * (hardware: AC2's SteamStub opened GTA IV's repack launcher through steam://, then loaded its steamclient.dll).
 * OrbisDesk has no Windows Steam client: its client is native. So this program is Steam's executable and the
 * steam:// handler (a URL opens the client), and ActiveProcess says Steam is not running (no pid, no client
 * DLL) instead of naming someone else's. It also clears the Steam variables a game's emulator left in this
 * environment. What it found and did goes to Z:\orbisdesk\steam\registry-owner.txt for the client's log.
 *
 * Built by tools/build-steam-hosted.py with x86_64-w64-mingw32-gcc. */
#include <windows.h>
#include <winternl.h>

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>

/* Wine's MemoryWineLoadUnixLibByName (include/winternl.h), and the pad profile call's parameters
 * (tools/build-xinput-hw.py, struct xinput_profile_params) */
#define MEMORY_WINE_LOAD_UNIX_LIB_BY_NAME 1002
struct pad_profile_params {
    char exe[260];
    UINT32 load;
};
typedef NTSTATUS(WINAPI *unix_call_dispatcher)(UINT64 handle, unsigned int code, void *args);
NTSTATUS WINAPI NtQueryVirtualMemory(HANDLE process, LPCVOID address, ULONG klass, PVOID buffer, SIZE_T length,
                                     SIZE_T *result);

#define OWN_EXE L"C:\\orbis\\steam-open.exe"
#define OWN_DIR L"C:\\orbis\\steam"
#define RESULT_FILE L"Z:\\orbisdesk\\steam\\registry-owner.txt"

/* a string value, "" when absent */
static void read_string(HKEY root, const WCHAR *path, const WCHAR *name, WCHAR *out, DWORD chars)
{
    HKEY key;
    DWORD type = 0, size = (chars - 1) * sizeof(WCHAR);
    out[0] = 0;
    if (RegOpenKeyExW(root, path, 0, KEY_QUERY_VALUE | KEY_WOW64_64KEY, &key)) return;
    if (RegQueryValueExW(key, name, NULL, &type, (BYTE *)out, &size) || (type != REG_SZ && type != REG_EXPAND_SZ))
        out[0] = 0;
    else
        out[size / sizeof(WCHAR)] = 0;
    RegCloseKey(key);
}

static int set_string(HKEY root, const WCHAR *path, const WCHAR *name, const WCHAR *value)
{
    HKEY key;
    if (RegCreateKeyExW(root, path, 0, NULL, 0, KEY_SET_VALUE | KEY_WOW64_64KEY, NULL, &key, NULL)) return 0;
    const LONG rc = RegSetValueExW(key, name, 0, REG_SZ, (const BYTE *)value, (DWORD)((wcslen(value) + 1) * sizeof(WCHAR)));
    RegCloseKey(key);
    return rc == ERROR_SUCCESS;
}

static int set_dword(HKEY root, const WCHAR *path, const WCHAR *name, DWORD value)
{
    HKEY key;
    if (RegCreateKeyExW(root, path, 0, NULL, 0, KEY_SET_VALUE | KEY_WOW64_64KEY, NULL, &key, NULL)) return 0;
    const LONG rc = RegSetValueExW(key, name, 0, REG_DWORD, (const BYTE *)&value, sizeof(value));
    RegCloseKey(key);
    return rc == ERROR_SUCCESS;
}

static void delete_value(HKEY root, const WCHAR *path, const WCHAR *name)
{
    HKEY key;
    if (RegOpenKeyExW(root, path, 0, KEY_SET_VALUE | KEY_WOW64_64KEY, &key)) return;
    RegDeleteValueW(key, name);
    RegCloseKey(key);
}

/* "none", "orbisdesk" or "other": who a value named as Steam */
static const char *owner_of(const WCHAR *value)
{
    if (!value[0]) return "none";
    return wcsstr(value, L"orbis\\steam") ? "orbisdesk" : "other";
}

static int register_steam(const char *args)
{
    const unsigned long app = strtoul(args, NULL, 10);
    static const WCHAR steam_key[] = L"Software\\Valve\\Steam";
    static const WCHAR process_key[] = L"Software\\Valve\\Steam\\ActiveProcess";
    WCHAR exe[MAX_PATH], dll[MAX_PATH], dll64[MAX_PATH], url[MAX_PATH * 2];
    read_string(HKEY_CURRENT_USER, steam_key, L"SteamExe", exe, MAX_PATH);
    read_string(HKEY_CURRENT_USER, process_key, L"SteamClientDll", dll, MAX_PATH);
    read_string(HKEY_CURRENT_USER, process_key, L"SteamClientDll64", dll64, MAX_PATH);
    read_string(HKEY_CLASSES_ROOT, L"steam\\shell\\open\\command", NULL, url, MAX_PATH * 2);
    const char *exe_owner = owner_of(exe), *url_owner = owner_of(url);
    const char *dll_owner = dll[0] || dll64[0] ? "other" : "none";

    int ok = 1;
    /* Steam's own keys (HKCU), naming OrbisDesk's pieces */
    ok &= set_string(HKEY_CURRENT_USER, steam_key, L"SteamExe", OWN_EXE);
    ok &= set_string(HKEY_CURRENT_USER, steam_key, L"SteamPath", OWN_DIR);
    ok &= set_dword(HKEY_CURRENT_USER, steam_key, L"RunningAppID", (DWORD)app);
    /* no Windows Steam client runs here: no pid, no client DLL */
    ok &= set_dword(HKEY_CURRENT_USER, process_key, L"pid", 0);
    ok &= set_dword(HKEY_CURRENT_USER, process_key, L"ActiveUser", 0);
    delete_value(HKEY_CURRENT_USER, process_key, L"SteamClientDll");
    delete_value(HKEY_CURRENT_USER, process_key, L"SteamClientDll64");
    /* where Steam is installed, for 64- and 32-bit readers */
    ok &= set_string(HKEY_LOCAL_MACHINE, L"Software\\Valve\\Steam", L"InstallPath", OWN_DIR);
    ok &= set_string(HKEY_LOCAL_MACHINE, L"Software\\Wow6432Node\\Valve\\Steam", L"InstallPath", OWN_DIR);
    /* steam:// opens OrbisDesk's client; the user's own Classes would override the machine's, so both */
    static const WCHAR command[] = L"\"" OWN_EXE L"\" \"%1\"";
    for (int i = 0; i < 2; ++i) {
        const HKEY hive = i ? HKEY_CURRENT_USER : HKEY_LOCAL_MACHINE;
        ok &= set_string(hive, L"Software\\Classes\\steam", NULL, L"URL:Steam Protocol");
        ok &= set_string(hive, L"Software\\Classes\\steam", L"URL Protocol", L"");
        ok &= set_string(hive, L"Software\\Classes\\steam\\DefaultIcon", NULL, OWN_EXE);
        ok &= set_string(hive, L"Software\\Classes\\steam\\shell\\open\\command", NULL, command);
    }
    /* the variables a game's emulator set: shared by the programs this desktop starts, so they are cleared here */
    static const WCHAR *const variables[] = {L"SteamAppId", L"SteamGameId", L"SteamOverlayGameId", L"SteamUser",
                                             L"SteamClientLaunch", L"SteamEnv"};
    int cleared = 0;
    for (size_t i = 0; i < sizeof(variables) / sizeof(variables[0]); ++i) {
        WCHAR value[8];
        SetLastError(0);
        if (GetEnvironmentVariableW(variables[i], value, 8) || GetLastError() != ERROR_ENVVAR_NOT_FOUND) {
            SetEnvironmentVariableW(variables[i], NULL);
            ++cleared;
        }
    }

    /* Written to disk now (hardware 2026-11-26): a launcher in the separate process (Rockstar's, for GTA IV) runs
     * its own Wine, which reads the prefix's registry files when it starts; until this title's server saved them,
     * it still found another copy's emulator as Steam (ActiveProcess's SteamClientDll) and loaded it. On the
     * console flush_key writes the changed branches at once (tools/build-wine-delete-server.py, W190). */
    const LONG flushed_user = RegFlushKey(HKEY_CURRENT_USER), flushed_machine = RegFlushKey(HKEY_LOCAL_MACHINE);
    const int flushed = flushed_user == ERROR_SUCCESS && flushed_machine == ERROR_SUCCESS;

    /* for the client's log: owners and counts, never a path (it would name a game) */
    char line[256];
    const int n = snprintf(line, sizeof(line),
                           "owner=orbisdesk ok=%d app=%lu previous_exe=%s previous_client_dll=%s previous_url=%s "
                           "env_cleared=%d flushed=%d\n",
                           ok, app, exe_owner, dll_owner, url_owner, cleared, flushed);
    HANDLE file = CreateFileW(RESULT_FILE, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file != INVALID_HANDLE_VALUE) {
        DWORD wrote = 0;
        WriteFile(file, line, (DWORD)(n > 0 ? n : 0), &wrote, NULL);
        CloseHandle(file);
    }
    return ok ? 0 : 1;
}

/* "steam-open.exe --play <app>" (2026-11-26): a SteamStub game's Desktop and Start menu shortcut
 * (native/steam/steam_shortcut.cpp), and "steam-open.exe steam://run/<app>//<args>" or "steam://rungameid/<app>":
 * Steam's URL, which a game's launcher opens to have Steam start the game (hardware 2026-11-26: Rockstar's launcher
 * for GTA IV asks for steam://run/12210//-launchTitleInFolder "<folder>"). Both start what Play in the Steam client
 * would: the launch plan the client keeps for each installed game (native/steam/steam_bigpicture.inc.cpp,
 * RefreshLaunchPlan) names the program, its command line and folder, and whether gbe_fork's ColdClient loader takes
 * the game's ini; a URL's arguments go after the plan's. The registration goes to OrbisDesk first, as before Play.
 * The program is started here with CreateProcessW, the way Explorer starts a guest: not through Explorer's
 * title-launch request, whose single reply file a launcher in the separate process may be waiting on for this very
 * program. A plan that says the game can't start (SteamStub with full emulation off) is shown, and nothing starts.
 * What happened goes to Z:\orbisdesk\steam\url-run.txt and stderr, counts only: "PWSTEAM url run app=... args=...
 * plan=... launched=...". */
#define PLAN_DIR L"Z:\\orbisdesk\\steam\\launch\\"
#define COLDCLIENT_INI L"C:\\orbis\\steam\\coldclient\\ColdClientLoader.ini"
#define RUN_RESULT_FILE L"Z:\\orbisdesk\\steam\\url-run.txt"

static void show_utf8(const char *text, UINT icon)
{
    WCHAR wide[1024];
    if (!MultiByteToWideChar(CP_UTF8, 0, text, -1, wide, 1024)) lstrcpyW(wide, L"The game could not be started.");
    MessageBoxW(NULL, wide, L"OrbisDesk", MB_OK | icon);
}

/* the value of "key=" on its own line of the plan, "" when absent */
static void plan_value(const char *plan, const char *key, char *out, size_t size)
{
    const size_t length = strlen(key);
    out[0] = 0;
    for (const char *line = plan; line && *line; line = strchr(line, '\n') ? strchr(line, '\n') + 1 : NULL) {
        if (strncmp(line, key, length) || line[length] != '=') continue;
        const char *value = line + length + 1;
        size_t n = 0;
        while (value[n] && value[n] != '\n' && value[n] != '\r' && n + 1 < size) ++n;
        memcpy(out, value, n);
        out[n] = 0;
        return;
    }
}

static void report_run(const char *how, unsigned long app, int args, const char *plan, int launched, DWORD error)
{
    char line[192];
    const int n = snprintf(line, sizeof(line), "PWSTEAM url run via=%s app=%lu args=%d plan=%s launched=%d error=%lu\n", how,
                           app, args, plan, launched, error);
    if (n <= 0) return;
    DWORD wrote = 0;
    HANDLE err = GetStdHandle(STD_ERROR_HANDLE);
    if (err && err != INVALID_HANDLE_VALUE) WriteFile(err, line, (DWORD)n, &wrote, NULL);
    HANDLE file = CreateFileW(RUN_RESULT_FILE, GENERIC_WRITE, FILE_SHARE_READ, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file != INVALID_HANDLE_VALUE) {
        WriteFile(file, line, (DWORD)n, &wrote, NULL);
        CloseHandle(file);
    }
}

/* Starts the plan of `app` with `extra` (UTF-8) after its command line. 0 started; 1 not (shown); 3 no plan. */
static int start_plan(const char *how, unsigned long app, const char *extra)
{
    char app_text[16];
    snprintf(app_text, sizeof(app_text), " %lu", app);
    register_steam(app_text);
    WCHAR path[MAX_PATH];
    swprintf(path, MAX_PATH, PLAN_DIR L"%lu.plan", app);
    char plan[8192] = {0};
    HANDLE file = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    DWORD got = 0;
    if (file != INVALID_HANDLE_VALUE) {
        ReadFile(file, plan, sizeof(plan) - 1, &got, NULL);
        CloseHandle(file);
    }
    plan[got] = 0;
    const int args = extra && extra[0];
    if (!got) {
        report_run(how, app, args, "none", 0, 0);
        return 3;
    }
    char state[16], message[512], image[MAX_PATH * 3], command[3072], directory[MAX_PATH * 3], ini[8];
    plan_value(plan, "state", state, sizeof(state));
    plan_value(plan, "message", message, sizeof(message));
    plan_value(plan, "image", image, sizeof(image));
    plan_value(plan, "command", command, sizeof(command));
    plan_value(plan, "directory", directory, sizeof(directory));
    plan_value(plan, "ini", ini, sizeof(ini));
    if (strcmp(state, "ok") || !image[0]) {
        report_run(how, app, args, "blocked", 0, 0);
        show_utf8(message[0] ? message : "This game can't be started from here.", MB_ICONWARNING);
        return 1;
    }
    if (!strcmp(ini, "1")) {
        WCHAR from[MAX_PATH];
        swprintf(from, MAX_PATH, PLAN_DIR L"%lu.ini", app);
        if (!CopyFileW(from, COLDCLIENT_INI, FALSE)) {
            report_run(how, app, args, "ok", 0, GetLastError());
            show_utf8("Full emulation could not be set up for this game: its loader settings could not be written.",
                      MB_ICONERROR);
            return 1;
        }
    }
    char line[4096];
    snprintf(line, sizeof(line), "%s%s%s", command, args ? " " : "", args ? extra : "");
    static WCHAR wide_image[MAX_PATH * 2], wide_command[4096], wide_directory[MAX_PATH * 2];
    if (!MultiByteToWideChar(CP_UTF8, 0, image, -1, wide_image, MAX_PATH * 2) ||
        !MultiByteToWideChar(CP_UTF8, 0, line, -1, wide_command, 4096) ||
        !MultiByteToWideChar(CP_UTF8, 0, directory, -1, wide_directory, MAX_PATH * 2)) {
        report_run(how, app, args, "ok", 0, ERROR_INVALID_DATA);
        return 1;
    }
    STARTUPINFOW si;
    memset(&si, 0, sizeof(si));
    si.cb = sizeof(si);
    PROCESS_INFORMATION pi;
    memset(&pi, 0, sizeof(pi));
    const BOOL ok = CreateProcessW(wide_image, wide_command, NULL, NULL, FALSE, 0, NULL,
                                   wide_directory[0] ? wide_directory : NULL, &si, &pi);
    const DWORD error = ok ? 0 : GetLastError();
    report_run(how, app, args, "ok", ok, error);
    if (!ok) {
        char text[160];
        snprintf(text, sizeof(text), "Windows could not start the game: error %lu.", error);
        show_utf8(text, MB_ICONERROR);
        return 1;
    }
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return 0;
}

static int play_game(const char *args)
{
    const unsigned long app = strtoul(args, NULL, 10);
    if (!app) return 2;
    const int rc = start_plan("shortcut", app, "");
    if (rc == 3)
        show_utf8("This game's start is not prepared yet. Open the Steam client once, or choose Create shortcuts in its "
                  "Settings.", MB_ICONWARNING);
    return rc == 3 ? 1 : rc;
}

/* %XX decoded in place */
static void url_decode(char *text)
{
    char *out = text;
    for (const char *in = text; *in; ++in) {
        if (in[0] == '%' && isxdigit((unsigned char)in[1]) && isxdigit((unsigned char)in[2])) {
            const char hex[3] = {in[1], in[2], 0};
            *out++ = (char)strtoul(hex, NULL, 16);
            in += 2;
        } else {
            *out++ = *in;
        }
    }
    *out = 0;
}

/* steam://run/<app>[/<language>][//<args>] and steam://rungameid/<app>: the app and its arguments (UTF-8), true when
 * the command line holds one of them */
static int parse_run_url(const char *command, unsigned long *app, char *args, size_t size)
{
    const char *url = NULL;
    for (const char *at = command; *at; ++at)
        if (!_strnicmp(at, "steam://", 8)) { url = at + 8; break; }
    if (!url) return 0;
    char copy[4096];
    lstrcpynA(copy, url, sizeof(copy));
    /* the URL ends at its closing quote, or at the end */
    char *end = strchr(copy, '"');
    if (end) *end = 0;
    while (copy[0] && (copy[strlen(copy) - 1] == ' ' || copy[strlen(copy) - 1] == '\t')) copy[strlen(copy) - 1] = 0;
    const char *rest;
    if (!_strnicmp(copy, "run/", 4)) rest = copy + 4;
    else if (!_strnicmp(copy, "rungameid/", 10)) rest = copy + 10;
    else return 0;
    char *after = NULL;
    *app = strtoul(rest, &after, 10);
    if (!*app || *app >= 0x80000000ul) return 0;
    args[0] = 0;
    const char *slashes = after ? strstr(after, "//") : NULL;
    if (slashes) {
        lstrcpynA(args, slashes + 2, (int)size);
        url_decode(args);
    }
    return 1;
}

static int run_url(const char *command)
{
    unsigned long app = 0;
    char args[4096];
    if (!parse_run_url(command, &app, args, sizeof(args))) return -1;  /* another steam:// URL: the client opens */
    const int rc = start_plan("url", app, args);
    return rc == 3 ? -1 : rc;  /* no plan yet: the client opens, as for any other URL */
}

/* This program's own arguments (UTF-8), from GetCommandLineW without the program's name (hardware 2026-11-26,
 * 04.89 run-0229): WinMain's lpCmdLine comes from the C runtime's copy of the command line, and OrbisDesk's guests
 * share one process and its msvcrt, so it was another program's. "--register 0" from Explorer's desktop start read
 * as no argument and opened the Steam client at every desktop start; the client's --register before Play and the
 * shortcuts' --play were lost the same way. *how: "quoted", "bare" or "none" for the program's name. */
static void own_arguments(char *out, int size, const char **how)
{
    const WCHAR *line = GetCommandLineW();
    out[0] = 0;
    *how = "none";
    if (!line) return;
    while (*line == ' ' || *line == '\t') ++line;
    if (*line == '"') {
        const WCHAR *end = wcschr(line + 1, '"');
        line = end ? end + 1 : line + wcslen(line);
        *how = "quoted";
    } else if (*line && wcsncmp(line, L"--", 2) && wcsnicmp(line, L"steam://", 8)) {
        while (*line && *line != ' ' && *line != '\t') ++line;
        *how = "bare";
    }
    while (*line == ' ' || *line == '\t') ++line;
    if (!WideCharToMultiByte(CP_UTF8, 0, line, -1, out, size, NULL, NULL)) out[0] = 0;
}

/* the shape of this start, counts and kinds only: Z:\orbisdesk\steam\steam-open.txt and stderr */
static void report_start(const char *what, const char *how, size_t length, int runtime_matches)
{
    char line[160];
    const int n = snprintf(line, sizeof(line), "PWSTEAM open args=%s program_name=%s length=%u crt_cmdline_matches=%d\n",
                           what, how, (unsigned)length, runtime_matches);
    if (n <= 0) return;
    DWORD wrote = 0;
    /* stderr (the title's log) only with OrbisDesk's traces (PW_TRACE=0|1, unset counts as on); the file is its own */
    WCHAR trace[4];
    const BOOL traced = !(GetEnvironmentVariableW(L"PW_TRACE", trace, 4) == 1 && trace[0] == '0');
    HANDLE err = GetStdHandle(STD_ERROR_HANDLE);
    if (traced && err && err != INVALID_HANDLE_VALUE) WriteFile(err, line, (DWORD)n, &wrote, NULL);
    HANDLE file = CreateFileW(L"Z:\\orbisdesk\\steam\\steam-open.txt", GENERIC_WRITE, FILE_SHARE_READ, NULL, CREATE_ALWAYS,
                              FILE_ATTRIBUTE_NORMAL, NULL);
    if (file != INVALID_HANDLE_VALUE) {
        WriteFile(file, line, (DWORD)n, &wrote, NULL);
        CloseHandle(file);
    }
}

int WINAPI WinMain(HINSTANCE instance, HINSTANCE previous, LPSTR runtime_command, int show)
{
    (void)instance;
    (void)previous;
    (void)show;
    static char command[4096];
    const char *how;
    own_arguments(command, sizeof(command), &how);
    const int matches = runtime_command && !strcmp(runtime_command, command);
    const char *what = !strncmp(command, "--register", 10) ? "register"
                       : !strncmp(command, "--play", 6)    ? "play"
                       : _strnicmp(command, "steam://", 8) == 0 || strstr(command, "steam://") ? "url"
                       : command[0]                        ? "other"
                                                           : "none";
    report_start(what, how, strlen(command), matches);
    if (!strncmp(command, "--register", 10)) return register_steam(command + 10);
    if (!strncmp(command, "--play", 6)) return play_game(command + 6);
    if (command[0]) {
        const int rc = run_url(command);
        if (rc >= 0) return rc;
    }
    UNICODE_STRING name;
    RtlInitUnicodeString(&name, L"xinput1_3");
    UINT64 result[2] = {0};
    void **dispatcher = (void **)GetProcAddress(GetModuleHandleW(L"ntdll.dll"), "__wine_unix_call_dispatcher");
    const NTSTATUS status = NtQueryVirtualMemory(GetCurrentProcess(), &name, MEMORY_WINE_LOAD_UNIX_LIB_BY_NAME, result,
                                                 sizeof(result), NULL);
    if (status || !dispatcher || !*dispatcher) {
        MessageBoxW(NULL, L"OrbisDesk's native side could not be reached: the Steam client is not available here.",
                    L"Open Steam Client", MB_OK | MB_ICONERROR);
        return 1;
    }
    struct pad_profile_params params;
    memset(&params, 0, sizeof(params));
    strcpy(params.exe, "<steam-open>");
    if (((unix_call_dispatcher)*dispatcher)(result[1], 3, &params)) {
        MessageBoxW(NULL, L"The request to open the Steam client failed.", L"Open Steam Client", MB_OK | MB_ICONERROR);
        return 1;
    }
    params.exe[sizeof(params.exe) - 1] = 0;
    if (!strcmp(params.exe, "opened") || !strcmp(params.exe, "busy")) return 0;
    char text[300];
    lstrcpynA(text, "The Steam client did not open: ", sizeof(text));
    lstrcatA(text, params.exe);
    MessageBoxA(NULL, text, "Open Steam Client", MB_OK | MB_ICONERROR);
    return 1;
}
