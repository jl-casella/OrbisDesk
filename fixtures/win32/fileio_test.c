/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* W133: how a program reads a data file on the console, step by step. SuperMarioKart.exe
 * (Blitz3D) opened SMK\splash800x600.png twice and gave up without one read (W132). The file
 * named on the command line (default: the PNG SuperMarioKart.exe opens) is read four ways:
 * Win32 handle calls, the C runtime's fopen/fread, _open/_read, and a file mapping. Every
 * result goes to fileio-result.txt beside the executable. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <fcntl.h>
#include <io.h>
#include <errno.h>

static char text[4096];
static int n;
#define LOG(...) (n += snprintf(text + n, sizeof(text) - n, __VA_ARGS__))

int WINAPI WinMain(HINSTANCE instance, HINSTANCE previous, LPSTR command, int show)
{
    char path[MAX_PATH], out[MAX_PATH], target[MAX_PATH];
    DWORD length = GetModuleFileNameA(NULL, path, MAX_PATH), written, read = 0, type, high = 0, low;
    unsigned char buffer[16] = {0};
    HANDLE file;
    FILE *stream;
    int fd;
    (void)instance; (void)previous; (void)show;

    lstrcpyA(out, path);
    while (length && out[length - 1] != '\\') --length;
    out[length] = 0;
    /* default: the PNG SuperMarioKart.exe opens, spelled as it does (smk, not SMK) */
    lstrcpyA(target, command && command[0] ? command : "C:\\users\\orbis\\Documents\\SuperMarioKart\\smk\\splash800x600.png");
    if (target[0] == '"') { memmove(target, target + 1, strlen(target)); target[strcspn(target, "\"")] = 0; }
    GetCurrentDirectoryA(MAX_PATH, path);
    LOG("cwd=%s\r\nfile=%s\r\n", path, target);

    file = CreateFileA(target, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    LOG("CreateFile=%p error=%lu\r\n", (void *)file, file == INVALID_HANDLE_VALUE ? GetLastError() : 0);
    if (file != INVALID_HANDLE_VALUE)
    {
        SetLastError(0); type = GetFileType(file);
        LOG("GetFileType=%lu error=%lu\r\n", type, GetLastError());
        SetLastError(0); low = GetFileSize(file, &high);
        LOG("GetFileSize=%lu high=%lu error=%lu\r\n", low, high, GetLastError());
        BOOL ok = ReadFile(file, buffer, sizeof(buffer), &read, NULL);
        LOG("ReadFile=%d read=%lu error=%lu first=%02x%02x%02x%02x\r\n", ok, read, ok ? 0 : GetLastError(),
            buffer[0], buffer[1], buffer[2], buffer[3]);
        HANDLE mapping = CreateFileMappingA(file, NULL, PAGE_READONLY, 0, 0, NULL);
        LOG("CreateFileMapping=%p error=%lu\r\n", (void *)mapping, mapping ? 0 : GetLastError());
        if (mapping)
        {
            const unsigned char *view = MapViewOfFile(mapping, FILE_MAP_READ, 0, 0, 0);
            LOG("MapViewOfFile=%p error=%lu first=%02x%02x%02x%02x\r\n", (void *)view, view ? 0 : GetLastError(),
                view ? view[0] : 0, view ? view[1] : 0, view ? view[2] : 0, view ? view[3] : 0);
            if (view) UnmapViewOfFile(view);
            CloseHandle(mapping);
        }
        CloseHandle(file);
    }
    errno = 0; stream = fopen(target, "rb");
    LOG("fopen=%p errno=%d\r\n", (void *)stream, errno);
    if (stream)
    {
        size_t got = fread(buffer, 1, sizeof(buffer), stream);
        LOG("fread=%u first=%02x%02x%02x%02x\r\n", (unsigned)got, buffer[0], buffer[1], buffer[2], buffer[3]);
        fseek(stream, 0, SEEK_END);
        LOG("ftell_end=%ld\r\n", ftell(stream));
        fclose(stream);
    }
    errno = 0; fd = _open(target, _O_RDONLY | _O_BINARY);
    LOG("_open=%d errno=%d\r\n", fd, errno);
    if (fd >= 0)
    {
        int got = _read(fd, buffer, sizeof(buffer));
        LOG("_read=%d first=%02x%02x%02x%02x\r\n", got, buffer[0], buffer[1], buffer[2], buffer[3]);
        _close(fd);
    }
    lstrcatA(out, "fileio-result.txt");
    file = CreateFileA(out, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file != INVALID_HANDLE_VALUE) { WriteFile(file, text, (DWORD)n, &written, NULL); CloseHandle(file); }
    return 0;
}
