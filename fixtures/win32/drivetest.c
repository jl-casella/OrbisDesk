/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Phase 10: USB drives as a Windows program sees them, 64-bit (guest) and 32-bit.
 * Lines appended to C:\orbis\drive-result.txt, one block per run:
 *   drives   GetLogicalDrives, and for each letter its GetDriveType
 *   volume   GetVolumeInformation of the drive (argument 1, D: by default): label, serial,
 *            file system, maximum name length
 *   space    GetDiskFreeSpaceEx
 *   list     the first entries of the drive's root, with their sizes
 *   large    the largest file of the root: open, seek to its last 4 KiB and read them
 *   write    D:\orbisdesk-test\save.txt: create the folder, write, read back, compare, delete
 *            the file (the folder stays), so a save on the drive is tested end to end
 * Each step has ok= and the Win32 error; a step that cannot run says skipped=. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <string.h>

static FILE *out;

static void line(const char *format, ...)
{
    va_list args;
    va_start(args, format);
    vfprintf(out, format, args);
    va_end(args);
    fputc('\n', out);
    fflush(out);
}

static const char *type_name(UINT type)
{
    switch (type)
    {
    case DRIVE_UNKNOWN: return "unknown";
    case DRIVE_NO_ROOT_DIR: return "no_root";
    case DRIVE_REMOVABLE: return "removable";
    case DRIVE_FIXED: return "fixed";
    case DRIVE_REMOTE: return "remote";
    case DRIVE_CDROM: return "cdrom";
    case DRIVE_RAMDISK: return "ramdisk";
    }
    return "?";
}

int WINAPI WinMain(HINSTANCE instance, HINSTANCE previous, LPSTR command, int show)
{
    char root[4] = "D:\\", arguments[256], pattern[MAX_PATH], largest[MAX_PATH] = "";
    char label[MAX_PATH + 1], fs[MAX_PATH + 1], folder[MAX_PATH], file[MAX_PATH];
    DWORD mask, serial = 0, name_max = 0, fs_flags = 0, error;
    ULONGLONG largest_size = 0;
    ULARGE_INTEGER free_bytes, total_bytes, total_free;
    WIN32_FIND_DATAA data;
    SYSTEMTIME now;
    HANDLE find, handle;
    int count = 0;
    (void)instance; (void)previous; (void)show;

    /* a 64-bit guest may get explorer's command line (W174): arguments that start with '/'
     * are not ours */
    snprintf(arguments, sizeof(arguments), "%s", command ? command : "");
    for (char *token = strtok(arguments, " \t"); token; token = strtok(NULL, " \t"))
        if (token[0] != '/' && ((token[0] >= 'A' && token[0] <= 'Z') || (token[0] >= 'a' && token[0] <= 'z')))
        {
            root[0] = (char)(token[0] & ~0x20);
            break;
        }

    CreateDirectoryA("C:\\orbis", NULL);
    if (!(out = fopen("C:\\orbis\\drive-result.txt", "a"))) return 1;
    GetSystemTime(&now);
    line("run arch=%d drive=%c: utc=%04u-%02u-%02uT%02u:%02u:%02uZ", (int)sizeof(void *) * 8, root[0],
         now.wYear, now.wMonth, now.wDay, now.wHour, now.wMinute, now.wSecond);

    /* drives */
    mask = GetLogicalDrives();
    line("drives ok=%d error=%lu mask=%08lx", mask != 0, mask ? 0 : GetLastError(), mask);
    for (int letter = 0; letter < 26; letter++)
        if (mask & (1u << letter))
        {
            char each[4] = "A:\\";
            each[0] = (char)('A' + letter);
            line("  drive %c: type=%s", each[0], type_name(GetDriveTypeA(each)));
        }
    if (!(mask & (1u << (root[0] - 'A'))))
        line("  drive %c: not_in_mask=1 type=%s", root[0], type_name(GetDriveTypeA(root)));

    /* volume */
    label[0] = fs[0] = 0;
    if (GetVolumeInformationA(root, label, sizeof(label), &serial, &name_max, &fs_flags, fs, sizeof(fs)))
        line("volume ok=1 error=0 label=\"%s\" serial=%08lx fs=%s name_max=%lu flags=%08lx", label, serial, fs,
             name_max, fs_flags);
    else
        line("volume ok=0 error=%lu", GetLastError());

    /* space */
    if (GetDiskFreeSpaceExA(root, &free_bytes, &total_bytes, &total_free))
        line("space ok=1 error=0 total_mb=%llu free_mb=%llu", total_bytes.QuadPart >> 20, total_free.QuadPart >> 20);
    else
        line("space ok=0 error=%lu", GetLastError());

    /* list */
    snprintf(pattern, sizeof(pattern), "%s*", root);
    if ((find = FindFirstFileA(pattern, &data)) == INVALID_HANDLE_VALUE)
        line("list ok=0 error=%lu", GetLastError());
    else
    {
        do
        {
            ULONGLONG size = (ULONGLONG)data.nFileSizeHigh << 32 | data.nFileSizeLow;
            if (!strcmp(data.cFileName, ".") || !strcmp(data.cFileName, "..")) continue;
            if (count < 12)
                line("  entry %s%s size=%llu", data.cFileName,
                     data.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY ? "\\" : "", size);
            if (!(data.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) && size > largest_size)
            {
                largest_size = size;
                snprintf(largest, sizeof(largest), "%s%s", root, data.cFileName);
            }
            count++;
        } while (FindNextFileA(find, &data));
        error = GetLastError();
        FindClose(find);
        line("list ok=%d error=%lu entries=%d", error == ERROR_NO_MORE_FILES, error == ERROR_NO_MORE_FILES ? 0 : error,
             count);
    }

    /* large */
    if (!largest[0]) line("large ok=0 error=0 skipped=no-file");
    else if ((handle = CreateFileA(largest, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL)) == INVALID_HANDLE_VALUE)
        line("large ok=0 error=%lu stage=open file=%s", GetLastError(), largest);
    else
    {
        static char buffer[4096];
        LARGE_INTEGER position;
        DWORD read = 0;
        position.QuadPart = largest_size > sizeof(buffer) ? (LONGLONG)(largest_size - sizeof(buffer)) : 0;
        if (!SetFilePointerEx(handle, position, NULL, FILE_BEGIN))
            line("large ok=0 error=%lu stage=seek file=%s size=%llu", GetLastError(), largest, largest_size);
        else if (!ReadFile(handle, buffer, sizeof(buffer), &read, NULL))
            line("large ok=0 error=%lu stage=read file=%s size=%llu", GetLastError(), largest, largest_size);
        else
            line("large ok=%d error=0 file=%s size=%llu read=%lu", read == (DWORD)min(largest_size, sizeof(buffer)),
                 largest, largest_size, read);
        CloseHandle(handle);
    }

    /* write */
    snprintf(folder, sizeof(folder), "%sorbisdesk-test", root);
    snprintf(file, sizeof(file), "%s\\save.txt", folder);
    if (!CreateDirectoryA(folder, NULL) && GetLastError() != ERROR_ALREADY_EXISTS)
        line("write ok=0 error=%lu stage=mkdir folder=%s", GetLastError(), folder);
    else if ((handle = CreateFileA(file, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, 0, NULL)) == INVALID_HANDLE_VALUE)
        line("write ok=0 error=%lu stage=create file=%s", GetLastError(), file);
    else
    {
        char text[96], back[96] = "";
        DWORD written = 0, read = 0;
        int length = snprintf(text, sizeof(text), "orbisdesk drivetest%d %04u-%02u-%02u %02u:%02u:%02u\r\n",
                              (int)sizeof(void *) * 8, now.wYear, now.wMonth, now.wDay, now.wHour, now.wMinute, now.wSecond);
        BOOL wrote = WriteFile(handle, text, length, &written, NULL);
        error = wrote ? 0 : GetLastError();
        CloseHandle(handle);
        if (!wrote || written != (DWORD)length)
            line("write ok=0 error=%lu stage=write written=%lu", error, written);
        else if ((handle = CreateFileA(file, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL)) == INVALID_HANDLE_VALUE)
            line("write ok=0 error=%lu stage=reopen", GetLastError());
        else
        {
            ReadFile(handle, back, sizeof(back) - 1, &read, NULL);
            CloseHandle(handle);
            line("write ok=%d error=0 bytes=%lu same=%d", read == written && !memcmp(back, text, length), written,
                 read == written && !memcmp(back, text, length));
            if (!DeleteFileA(file)) line("  delete ok=0 error=%lu", GetLastError());
            else line("  delete ok=1 error=0");
        }
    }
    line("end");
    fclose(out);
    return 0;
}
