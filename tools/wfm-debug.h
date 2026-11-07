/* Preserve Windows error state and use the ANSI debug channel captured by Wine. */
#include <windows.h>
static inline void pwfmDebugStringW(const wchar_t *message) {
    DWORD error=GetLastError();char text[4096];
    if (WideCharToMultiByte(CP_UTF8,0,message,-1,text,sizeof(text),NULL,NULL)) OutputDebugStringA(text);
    SetLastError(error);
}
#define OutputDebugStringW pwfmDebugStringW
