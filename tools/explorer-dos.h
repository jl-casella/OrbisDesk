/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Only classify DOS executables: preserve PE, NE and LE/LX Windows loaders. */
static BOOL pw_is_dos_file(const WCHAR *path)
{
    BYTE header[64], signature[4];
    DWORD read, offset;
    LARGE_INTEGER size, seek;
    BOOL dos = FALSE;
    const WCHAR *ext = wcsrchr(path, '.');
    HANDLE file;
    if (!ext || (lstrcmpiW(ext, L".exe") && lstrcmpiW(ext, L".com"))) return FALSE;
    file = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                       NULL, OPEN_EXISTING, 0, NULL);
    if (file == INVALID_HANDLE_VALUE) return FALSE;
    if (!GetFileSizeEx(file, &size) || !ReadFile(file, header, sizeof(header), &read, NULL)) goto done;
    if (read < 2 || header[0] != 'M' || header[1] != 'Z')
    {
        dos = !lstrcmpiW(ext, L".com") && size.QuadPart > 0 && size.QuadPart <= 0xff00;
        goto done;
    }
    if (read < sizeof(header)) goto done;
    offset = (DWORD)header[60] | ((DWORD)header[61] << 8) | ((DWORD)header[62] << 16) | ((DWORD)header[63] << 24);
    if (offset >= sizeof(header) && (ULONGLONG)offset + 4 <= (ULONGLONG)size.QuadPart)
    {
        seek.QuadPart = offset;
        if (!SetFilePointerEx(file, seek, NULL, FILE_BEGIN) ||
            !ReadFile(file, signature, sizeof(signature), &read, NULL) || read != sizeof(signature)) goto done;
        if ((!memcmp(signature, "PE\0\0", 4)) || !memcmp(signature, "NE", 2) ||
            !memcmp(signature, "LE", 2) || !memcmp(signature, "LX", 2)) goto done;
    }
    dos = TRUE;
done:
    CloseHandle(file);
    return dos;
}
