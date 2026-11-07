/* OrbisDesk W108; real Win32 operations, no success placeholders. */
static void pwfmOperationError(const wchar_t *operation, const wchar_t *path, DWORD error) {
    wchar_t message[640];
    swprintf_s(message,640,L"PWFM operation=%ls path=%ls error=%lu",operation,path,error);
    OutputDebugStringW(message);
    swprintf_s(message,640,L"%ls\n%ls\nError: %lu",operation,path,error);
    MessageBoxW(NULL,message,L"File Manager",MB_OK | MB_ICONERROR);
}

struct pwfmDeleteChild { struct pwfmDeleteChild *next; wchar_t path[MAX_PATH]; };
static BOOL pwfmDeleteTree(const wchar_t *input, volatile bool *cancel) {
    wchar_t path[MAX_PATH],pattern[MAX_PATH];
    DWORD length=GetFullPathNameW(input,MAX_PATH,path,NULL),attributes,error=0;
    if (!length || length>=MAX_PATH) { SetLastError(length?ERROR_FILENAME_EXCED_RANGE:GetLastError());return FALSE; }
    if (length<=3 && path[1]==L':') {SetLastError(ERROR_ACCESS_DENIED);return FALSE;}
    if (cancel && *cancel) {SetLastError(ERROR_CANCELLED);return FALSE;}
    attributes=GetFileAttributesW(path);
    if (attributes==INVALID_FILE_ATTRIBUTES) return FALSE;
    if (!(attributes & FILE_ATTRIBUTE_DIRECTORY)) {
        BOOL ok=DeleteFileW(path);DWORD status=ok?0:GetLastError();wchar_t log[640];
        swprintf_s(log,640,L"PWFM delete_file path=%ls error=%lu",path,status);OutputDebugStringW(log);
        SetLastError(status);return ok;
    }
    if (attributes & FILE_ATTRIBUTE_REPARSE_POINT) return RemoveDirectoryW(path);
    if (length+3>MAX_PATH) {SetLastError(ERROR_FILENAME_EXCED_RANGE);return FALSE;}
    swprintf_s(pattern,MAX_PATH,L"%ls\\*",path);
    WIN32_FIND_DATAW data;
    HANDLE find=FindFirstFileW(pattern,&data);
    struct pwfmDeleteChild *head=NULL,**tail=&head;
    if (find==INVALID_HANDLE_VALUE) {
        error=GetLastError();
        if (error!=ERROR_FILE_NOT_FOUND && error!=ERROR_NO_MORE_FILES) return FALSE;
        error=0;
    } else {
        do {
            if (cancel && *cancel) {error=ERROR_CANCELLED;break;}
            if (!wcscmp(data.cFileName,L".") || !wcscmp(data.cFileName,L"..")) continue;
            if (length+wcslen(data.cFileName)+2>MAX_PATH) {error=ERROR_FILENAME_EXCED_RANGE;break;}
            struct pwfmDeleteChild *child=calloc(1,sizeof(*child));
            if (!child) {error=ERROR_NOT_ENOUGH_MEMORY;break;}
            swprintf_s(child->path,MAX_PATH,L"%ls\\%ls",path,data.cFileName);
            wchar_t entryLog[640];swprintf_s(entryLog,640,L"PWFM delete_child path=%ls attributes=%08lx",child->path,data.dwFileAttributes);OutputDebugStringW(entryLog);
            *tail=child;tail=&child->next;
        } while (FindNextFileW(find,&data));
        if (!error) {error=GetLastError();if (error==ERROR_NO_MORE_FILES) error=0;}
        FindClose(find);
    }
    /* No find handle survives across recursion or removal. Do not follow links.
     * Keep the first real error; a partial deletion is never reported as success. */
    while (head) {
        struct pwfmDeleteChild *child=head;head=child->next;
        if (!error && !pwfmDeleteTree(child->path,cancel)) error=GetLastError();
        free(child);
    }
    if (!error) {
        for (unsigned attempt=0;;attempt++) {
            if (cancel && *cancel) {error=ERROR_CANCELLED;break;}
            if (RemoveDirectoryW(path)) break;
            error=GetLastError();
            if (error!=ERROR_DIR_NOT_EMPTY || attempt==10) break;
            wchar_t retry[640];swprintf_s(retry,640,L"PWFM remove_retry path=%ls attempt=%u error=%lu",path,attempt+1,error);OutputDebugStringW(retry);
            /* DeleteFile/RemoveDirectory may mark delete-on-close. Retry only
             * the final rmdir; do not delete newly-created concurrent contents. */
            Sleep(50);error=0;
        }
    }
    wchar_t log[640];swprintf_s(log,640,L"PWFM remove_tree path=%ls error=%lu",path,error);OutputDebugStringW(log);
    SetLastError(error);return error==0;
}
