/* SPDX-License-Identifier: GPL-2.0-or-later
 * Minimal libretro host for DOSBox Pure in an OrbisDesk PE64 guest.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shellapi.h>
#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdarg.h>
#include <stdlib.h>
#include <string.h>
#include "libretro.h"
#include "pw_dos_audio.h"

static HWND window;
static BOOL running=TRUE,loaded,initialized,ready_audio;
static HMODULE core;
static uint32_t *pixels;
static unsigned width,height;
static uint64_t frames,audio_frames;
static LONG keys[RETROK_LAST];
static struct retro_keyboard_callback keyboard;
static enum retro_pixel_format pixel_format=RETRO_PIXEL_FORMAT_XRGB8888;
static char system_dir[MAX_PATH],save_dir[MAX_PATH];
static struct pw_dos_audio_packet audio;
static LONG (WINAPI *query)(ULONG,void*,ULONG,ULONG*);
static void (*core_init)(void),(*core_deinit)(void),(*core_run)(void),(*core_unload)(void);
static bool (*core_load)(const struct retro_game_info*);
static void (*core_av)(struct retro_system_av_info*);
static void (*core_port)(unsigned,unsigned);
static struct retro_core_options_update_display_callback display_callback;
static struct {char key[128],value[256];} variables[192];
static unsigned variable_count;

static void log_message(const char *format,...) {
    char line[1800];va_list args;va_start(args,format);vsnprintf(line,sizeof(line),format,args);va_end(args);
    OutputDebugStringA(line);
}
static void RETRO_CALLCONV core_log(enum retro_log_level level,const char *format,...) {
    char line[1500];va_list args;va_start(args,format);vsnprintf(line,sizeof(line),format,args);va_end(args);
    log_message("PWDOS core level=%u %s",(unsigned)level,line);
}
static const char *override(const char *key) {
    if(!strcmp(key,"dosbox_pure_cpu_core"))return "normal";
    if(!strcmp(key,"dosbox_pure_cycles"))return "4720";
    if(!strcmp(key,"dosbox_pure_voodoo_perf"))return "0";
    if(!strcmp(key,"dosbox_pure_midi"))return "disabled";
    if(!strcmp(key,"dosbox_pure_menu_time"))return "0";
    if(!strcmp(key,"dosbox_pure_savestate"))return "off";
    return NULL;
}
static void remember(const char *key,const char *value) {
    if(!key||!value)return;
    for(unsigned i=0;i<variable_count;i++)if(!strcmp(variables[i].key,key))return;
    if(variable_count>=192)return;
    snprintf(variables[variable_count].key,128,"%s",key);
    snprintf(variables[variable_count++].value,256,"%s",value);
}
static bool RETRO_CALLCONV environment(unsigned command,void *data) {
    switch(command) {
    case RETRO_ENVIRONMENT_GET_CORE_OPTIONS_VERSION:*(unsigned*)data=2;return true;
    case RETRO_ENVIRONMENT_SET_CORE_OPTIONS_V2: {
        const struct retro_core_options_v2 *options=data;
        for(const struct retro_core_option_v2_definition *d=options->definitions;d&&d->key;d++)remember(d->key,d->default_value?d->default_value:d->values[0].value);
        return true;
    }
    case RETRO_ENVIRONMENT_SET_CORE_OPTIONS: {
        const struct retro_core_option_definition *d=data;
        for(;d&&d->key;d++)remember(d->key,d->default_value?d->default_value:d->values[0].value);
        return true;
    }
    case RETRO_ENVIRONMENT_GET_VARIABLE: {
        struct retro_variable *v=data;v->value=override(v->key);
        if(v->value)return true;
        for(unsigned i=0;i<variable_count;i++)if(!strcmp(v->key,variables[i].key)){v->value=variables[i].value;return true;}
        return false;
    }
    case RETRO_ENVIRONMENT_GET_VARIABLE_UPDATE:*(bool*)data=false;return true;
    case RETRO_ENVIRONMENT_SET_CORE_OPTIONS_UPDATE_DISPLAY_CALLBACK:display_callback=*(struct retro_core_options_update_display_callback*)data;return true;
    case RETRO_ENVIRONMENT_SET_CORE_OPTIONS_DISPLAY:return true;
    case RETRO_ENVIRONMENT_SET_PIXEL_FORMAT:
        pixel_format=*(enum retro_pixel_format*)data;
        return pixel_format==RETRO_PIXEL_FORMAT_XRGB8888;
    case RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY:*(const char**)data=system_dir;return true;
    case RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY:*(const char**)data=save_dir;return true;
    case RETRO_ENVIRONMENT_GET_LOG_INTERFACE:((struct retro_log_callback*)data)->log=core_log;return true;
    case RETRO_ENVIRONMENT_SET_KEYBOARD_CALLBACK:keyboard=*(struct retro_keyboard_callback*)data;return true;
    case RETRO_ENVIRONMENT_GET_CAN_DUPE:*(bool*)data=true;return true;
    case RETRO_ENVIRONMENT_GET_INPUT_BITMASKS:return true;
    case RETRO_ENVIRONMENT_GET_INPUT_DEVICE_CAPABILITIES:
        *(uint64_t*)data=(UINT64_C(1)<<RETRO_DEVICE_KEYBOARD)|(UINT64_C(1)<<RETRO_DEVICE_JOYPAD);return true;
    case RETRO_ENVIRONMENT_GET_LANGUAGE:*(unsigned*)data=RETRO_LANGUAGE_ENGLISH;return true;
    case RETRO_ENVIRONMENT_GET_AUDIO_VIDEO_ENABLE:*(int*)data=1|(ready_audio?2:0);return true;
    case RETRO_ENVIRONMENT_GET_TARGET_REFRESH_RATE:*(float*)data=60.0f;return true;
    case RETRO_ENVIRONMENT_GET_INPUT_MAX_USERS:*(unsigned*)data=1;return true;
    case RETRO_ENVIRONMENT_SET_SUPPORT_NO_GAME:
    case RETRO_ENVIRONMENT_SET_INPUT_DESCRIPTORS:
    case RETRO_ENVIRONMENT_SET_CONTROLLER_INFO:
    case RETRO_ENVIRONMENT_SET_SUPPORT_ACHIEVEMENTS:
    case RETRO_ENVIRONMENT_SET_GEOMETRY:return true;
    case RETRO_ENVIRONMENT_SET_MESSAGE: {
        const struct retro_message *m=data;log_message("PWDOS message %s",m->msg?m->msg:"");return true;
    }
    case RETRO_ENVIRONMENT_SHUTDOWN:running=FALSE;log_message("PWDOS core_shutdown");return true;
    default:return false;
    }
}
static void RETRO_CALLCONV video(const void *data,unsigned w,unsigned h,size_t pitch) {
    if(!data||data==RETRO_HW_FRAME_BUFFER_VALID)return;
    if(!w||!h||w>2048||h>2048||pitch<(size_t)w*4){log_message("PWDOS invalid_video w=%u h=%u pitch=%llu",w,h,(unsigned long long)pitch);running=FALSE;return;}
    if(w!=width||h!=height) {
        uint32_t *next=malloc((size_t)w*h*4);
        if(!next){running=FALSE;return;}
        free(pixels);pixels=next;width=w;height=h;
        log_message("PWDOS video_mode %ux%u",w,h);
    }
    for(unsigned y=0;y<h;y++)memcpy(pixels+(size_t)y*w,(const char*)data+(size_t)y*pitch,w*4);
    frames++;
    if(frames==1||frames%300==0) {
        uint32_t hash=2166136261u;
        for(size_t i=0;i<(size_t)w*h;i++)hash=(hash^pixels[i])*16777619u;
        log_message("PWDOS video_frame n=%llu size=%ux%u hash=%08x",(unsigned long long)frames,w,h,hash);
    }
    InvalidateRect(window,NULL,FALSE);
}
static bool audio_call(unsigned action,const int16_t *samples,size_t count) {
    if(!query)return false;
    audio.action=action;audio.frames=(uint32_t)count;audio.pcm=(uintptr_t)samples;ULONG returned=0;
    LONG status=query(PW_DOS_AUDIO_CLASS,&audio,sizeof(audio),&returned);
    if(status||returned!=sizeof(audio)||audio.status) {
        log_message("PWDOS audio_fail action=%u nt=%08lx native=%08x",action,(unsigned long)status,(unsigned)audio.status);return false;
    }
    return true;
}
static size_t RETRO_CALLCONV audio_batch(const int16_t *data,size_t count) {
    if(ready_audio && count) {
        for(size_t at=0;at<count;) {
            size_t n=count-at>8192?8192:count-at;
            if(!audio_call(PW_DOS_AUDIO_SUBMIT,data+at*2,n)) {
                audio_call(PW_DOS_AUDIO_CLOSE,NULL,0);ready_audio=FALSE;
                SetWindowTextW(window,L"DOS - OrbisDesk (sin audio)");break;
            }
            audio_frames+=n;at+=n;
        }
    }
    return count;
}
static void RETRO_CALLCONV audio_sample(int16_t left,int16_t right){int16_t pair[2]={left,right};audio_batch(pair,1);}
static void key_event(unsigned key,BOOL down,uint32_t character) {
    if(key>=RETROK_LAST)return;
    LONG before=InterlockedExchange(&keys[key],down?1:0);
    if(keyboard.callback && (before!=(down?1:0)||character))keyboard.callback(!!down,key,character,0);
}
static unsigned translate_key(WPARAM key) {
    if(key>='A'&&key<='Z')return (unsigned)key+('a'-'A');
    if(key>='0'&&key<='9')return (unsigned)key;
    if(key>=VK_F1&&key<=VK_F12)return RETROK_F1+(unsigned)(key-VK_F1);
    switch(key) {
    case VK_RETURN:return RETROK_RETURN;case VK_ESCAPE:return RETROK_ESCAPE;case VK_SPACE:return RETROK_SPACE;
    case VK_BACK:return RETROK_BACKSPACE;case VK_TAB:return RETROK_TAB;
    case VK_UP:return RETROK_UP;case VK_DOWN:return RETROK_DOWN;case VK_LEFT:return RETROK_LEFT;case VK_RIGHT:return RETROK_RIGHT;
    case VK_SHIFT:return RETROK_LSHIFT;case VK_CONTROL:return RETROK_LCTRL;case VK_MENU:return RETROK_LALT;
    case VK_HOME:return RETROK_HOME;case VK_END:return RETROK_END;case VK_DELETE:return RETROK_DELETE;case VK_INSERT:return RETROK_INSERT;
    case VK_PRIOR:return RETROK_PAGEUP;case VK_NEXT:return RETROK_PAGEDOWN;
    default:return RETROK_UNKNOWN;
    }
}
static void RETRO_CALLCONV input_poll(void){}
static int16_t RETRO_CALLCONV input_state(unsigned port,unsigned device,unsigned index,unsigned id) {
    (void)index;
    if(port)return 0;
    if(device==RETRO_DEVICE_KEYBOARD && id<RETROK_LAST)return (int16_t)InterlockedCompareExchange(&keys[id],0,0);
    if(device==RETRO_DEVICE_JOYPAD) {
        static const unsigned map[16]={RETROK_LCTRL,RETROK_SPACE,RETROK_ESCAPE,RETROK_RETURN,RETROK_UP,RETROK_DOWN,RETROK_LEFT,RETROK_RIGHT,
                                       RETROK_SPACE,RETROK_LSHIFT,RETROK_LCTRL,RETROK_LALT,RETROK_F1,RETROK_F2,0,0};
        unsigned bits=0;for(unsigned i=0;i<16;i++)if(map[i]&&InterlockedCompareExchange(&keys[map[i]],0,0))bits|=1u<<i;
        return id==RETRO_DEVICE_ID_JOYPAD_MASK?(int16_t)bits:(id<16?!!(bits&(1u<<id)):0);
    }
    return 0;
}
static LRESULT CALLBACK wndproc(HWND hwnd,UINT msg,WPARAM wp,LPARAM lp) {
    switch(msg) {
    case WM_CLOSE:running=FALSE;return 0;
    case WM_ERASEBKGND:return 1;
    case WM_KEYDOWN:case WM_SYSKEYDOWN:case WM_KEYUP:case WM_SYSKEYUP: {
        unsigned key=translate_key(wp);if(key)key_event(key,msg==WM_KEYDOWN||msg==WM_SYSKEYDOWN,0);return 0;
    }
    case WM_CHAR:if(keyboard.callback)keyboard.callback(true,RETROK_UNKNOWN,(uint32_t)wp,0);return 0;
    case WM_LBUTTONDOWN:case WM_LBUTTONUP:key_event(RETROK_SPACE,msg==WM_LBUTTONDOWN,0);return 0;
    case WM_RBUTTONDOWN:case WM_RBUTTONUP:key_event(RETROK_LCTRL,msg==WM_RBUTTONDOWN,0);return 0;
    case WM_KILLFOCUS:for(unsigned i=0;i<RETROK_LAST;i++)if(keys[i])key_event(i,FALSE,0);return 0;
    case WM_PAINT: {
        PAINTSTRUCT paint;HDC dc=BeginPaint(hwnd,&paint);RECT rect;GetClientRect(hwnd,&rect);
        FillRect(dc,&rect,(HBRUSH)GetStockObject(BLACK_BRUSH));
        if(pixels && width && height) {
            BITMAPINFO info={0};info.bmiHeader.biSize=sizeof(BITMAPINFOHEADER);info.bmiHeader.biWidth=width;
            info.bmiHeader.biHeight=-(LONG)height;info.bmiHeader.biPlanes=1;info.bmiHeader.biBitCount=32;info.bmiHeader.biCompression=BI_RGB;
            int w=rect.right,h=(int)((int64_t)w*3/4);if(h>rect.bottom){h=rect.bottom;w=h*4/3;}
            StretchDIBits(dc,(rect.right-w)/2,(rect.bottom-h)/2,w,h,0,0,width,height,pixels,&info,DIB_RGB_COLORS,SRCCOPY);
        }
        EndPaint(hwnd,&paint);return 0;
    }
    }
    return DefWindowProcW(hwnd,msg,wp,lp);
}
#define LOAD(name,type) type name=(type)GetProcAddress(core,#name);if(!name){log_message("PWDOS missing_export %s",#name);goto cleanup;}
int WINAPI wWinMain(HINSTANCE instance,HINSTANCE previous,LPWSTR command,int show) {
    (void)previous;(void)command;(void)show;
    HANDLE singleton=CreateMutexW(NULL,TRUE,L"OrbisDesk.DOSHost.Singleton");
    if(!singleton||GetLastError()==ERROR_ALREADY_EXISTS){if(singleton)CloseHandle(singleton);MessageBoxW(NULL,L"Ya hay un juego DOS abierto.",L"DOS",MB_OK);return 2;}
    running=TRUE;loaded=initialized=ready_audio=FALSE;window=NULL;
    width=height=0;frames=audio_frames=0;variable_count=0;
    memset(keys,0,sizeof(keys));memset(&keyboard,0,sizeof(keyboard));
    memset(&audio,0,sizeof(audio));
    int result=1,argc=0;LPWSTR *argv=CommandLineToArgvW(GetCommandLineW(),&argc);
    wchar_t module[MAX_PATH],dll[MAX_PATH],save[MAX_PATH];char content[MAX_PATH*3];
    if(!argv||argc!=2){MessageBoxW(NULL,L"Abrí un juego DOS desde File Manager.",L"DOS",MB_OK);goto cleanup;}
    if(!WideCharToMultiByte(CP_UTF8,0,argv[1],-1,content,sizeof(content),NULL,NULL))goto cleanup;
    log_message("PWDOS entered content=%s cpu=normal cycles=4720",content);
    GetModuleFileNameW(instance,module,MAX_PATH);wchar_t *slash=wcsrchr(module,L'\\');if(!slash)goto cleanup;slash[1]=0;
    swprintf(dll,MAX_PATH,L"%lsdosbox_pure_libretro.dll",module);
    WideCharToMultiByte(CP_UTF8,0,module,-1,system_dir,sizeof(system_dir),NULL,NULL);
    wcscpy(save,L"C:\\users\\orbis\\AppData\\Local\\OrbisDesk");
    if(GetFileAttributesW(save)==INVALID_FILE_ATTRIBUTES) {
        const wchar_t *legacy=L"C:\\users\\orbis\\AppData\\Local\\OrbisWin";
        if(GetFileAttributesW(legacy)!=INVALID_FILE_ATTRIBUTES && !MoveFileW(legacy,save)) {
            log_message("PWDOS save_migration_failed error=%lu",GetLastError());
            MessageBoxW(NULL,L"No se pudieron migrar los guardados DOS. Los originales se conservaron.",L"OrbisDesk",MB_OK|MB_ICONERROR);
            goto cleanup;
        }
    }
    CreateDirectoryW(save,NULL);
    wcscat(save,L"\\DOS");CreateDirectoryW(save,NULL);
    WideCharToMultiByte(CP_UTF8,0,save,-1,save_dir,sizeof(save_dir),NULL,NULL);
    core=LoadLibraryW(dll);if(!core){log_message("PWDOS load_core_failed error=%lu",GetLastError());MessageBoxW(NULL,L"No se pudo cargar el motor DOS.",L"DOS",MB_OK|MB_ICONERROR);goto cleanup;}
    core_init=(void(*)(void))GetProcAddress(core,"retro_init");core_deinit=(void(*)(void))GetProcAddress(core,"retro_deinit");
    core_run=(void(*)(void))GetProcAddress(core,"retro_run");core_unload=(void(*)(void))GetProcAddress(core,"retro_unload_game");
    core_load=(bool(*)(const struct retro_game_info*))GetProcAddress(core,"retro_load_game");
    core_av=(void(*)(struct retro_system_av_info*))GetProcAddress(core,"retro_get_system_av_info");
    core_port=(void(*)(unsigned,unsigned))GetProcAddress(core,"retro_set_controller_port_device");
    if(!core_init||!core_deinit||!core_run||!core_unload||!core_load||!core_av||!core_port)goto cleanup;
    {
        typedef void (*SetEnv)(retro_environment_t);typedef void (*SetVideo)(retro_video_refresh_t);
        typedef void (*SetAudio)(retro_audio_sample_t);typedef void (*SetBatch)(retro_audio_sample_batch_t);
        typedef void (*SetPoll)(retro_input_poll_t);typedef void (*SetState)(retro_input_state_t);
        LOAD(retro_set_environment,SetEnv);LOAD(retro_set_video_refresh,SetVideo);LOAD(retro_set_audio_sample,SetAudio);
        LOAD(retro_set_audio_sample_batch,SetBatch);LOAD(retro_set_input_poll,SetPoll);LOAD(retro_set_input_state,SetState);
        retro_set_environment(environment);retro_set_video_refresh(video);retro_set_audio_sample(audio_sample);
        retro_set_audio_sample_batch(audio_batch);retro_set_input_poll(input_poll);retro_set_input_state(input_state);
    }
    WNDCLASSW cls={0};cls.lpfnWndProc=wndproc;cls.hInstance=instance;cls.lpszClassName=L"OrbisDesk.DOSHost";
    cls.hCursor=LoadCursorW(NULL,IDC_ARROW);RegisterClassW(&cls);
    window=CreateWindowW(cls.lpszClassName,L"DOS - OrbisDesk",WS_OVERLAPPEDWINDOW|WS_VISIBLE,CW_USEDEFAULT,CW_USEDEFAULT,820,650,NULL,NULL,instance,NULL);
    if(!window)goto cleanup;
    query=(void*)GetProcAddress(GetModuleHandleW(L"ntdll.dll"),"NtQuerySystemInformation");
    audio.size=sizeof(audio);audio.version=1;audio.sample_rate=44100;
    ready_audio=audio_call(PW_DOS_AUDIO_OPEN,NULL,0);
    if(!ready_audio)SetWindowTextW(window,L"DOS - OrbisDesk (sin audio)");
    log_message("PWDOS init_begin audio=%u",ready_audio);core_init();initialized=TRUE;core_port(0,RETRO_DEVICE_KEYBOARD);
    struct retro_game_info game={content,NULL,0,NULL};
    log_message("PWDOS load_begin");loaded=core_load(&game);log_message("PWDOS load_end ok=%u",loaded);
    if(!loaded){MessageBoxW(window,L"El motor DOS no pudo abrir el juego.",L"DOS",MB_OK|MB_ICONERROR);goto cleanup;}
    struct retro_system_av_info av={0};core_av(&av);
    if(ready_audio && audio.sample_rate!=(unsigned)av.timing.sample_rate) {
        audio_call(PW_DOS_AUDIO_CLOSE,NULL,0);audio.sample_rate=(unsigned)av.timing.sample_rate;ready_audio=audio_call(PW_DOS_AUDIO_OPEN,NULL,0);
    }
    log_message("PWDOS running fps=%.3f sample_rate=%.0f",av.timing.fps,av.timing.sample_rate);
    LARGE_INTEGER frequency,start;QueryPerformanceFrequency(&frequency);QueryPerformanceCounter(&start);
    double next=(double)start.QuadPart;double step=(double)frequency.QuadPart/(av.timing.fps>10?av.timing.fps:60);
    while(running) {
        MSG msg;while(PeekMessageW(&msg,NULL,0,0,PM_REMOVE)){if(msg.message==WM_QUIT)running=FALSE;TranslateMessage(&msg);DispatchMessageW(&msg);}
        if(!running)break;
        core_run();UpdateWindow(window);next+=step;
        LARGE_INTEGER now;QueryPerformanceCounter(&now);
        if(next-now.QuadPart>frequency.QuadPart/500)Sleep((DWORD)((next-now.QuadPart)*1000.0/frequency.QuadPart));
        if(now.QuadPart-next>frequency.QuadPart/4)next=(double)now.QuadPart;
    }
    result=0;
cleanup:
    log_message("PWDOS shutdown_begin loaded=%u initialized=%u frames=%llu audio_frames=%llu",loaded,initialized,(unsigned long long)frames,(unsigned long long)audio_frames);
    if(loaded)core_unload();
    if(initialized)core_deinit();
    keyboard.callback=NULL;
    if(ready_audio)audio_call(PW_DOS_AUDIO_CLOSE,NULL,0);
    ready_audio=FALSE;
    if(window)DestroyWindow(window);
    free(pixels);pixels=NULL;
    /* W114: unload the core after deinit (it joins its workers). Reusing the loaded
     * module crashed the second game of a session with a NULL frame-buffer write
     * (W112/W113, CARMEN.EXE after smb.exe); a fresh load starts from clean globals. */
    if(core){BOOL freed=FreeLibrary(core);log_message("PWDOS core_unloaded freed=%u error=%lu",freed,freed?0:GetLastError());core=NULL;}
    if(argv)LocalFree(argv);
    ReleaseMutex(singleton);CloseHandle(singleton);
    log_message("PWDOS shutdown_end rc=%d",result);return result;
}
