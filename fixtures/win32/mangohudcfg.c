/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* MangoHud Settings (C:\orbis\mangohudcfg.exe): the HUD options OrbisDesk honours, as a form.
 *
 * Two readers take %APPDATA%\MangoHud\MangoHud.conf: MangoHud's own layer (overlay_params.cpp:
 * "key" or "key=value" per line, the last one of a key wins, "full" first and then every other
 * key) and the title overlay's Estadisticas HUD (native/hw_overlay.c, hud_read_conf: the same
 * defaults, each line in order). The form edits only the keys the overlay also reads: the rows
 * fps, frametime, frame_timing, gpu_stats, cpu_stats, ram and vram, and position, offset_x,
 * offset_y, font_size and background_alpha. A save keeps every other line of the file as it was
 * (comments, other MangoHud options, "full"), drops the edited keys wherever they were, and writes
 * them once at the end, each with an explicit value; so both readers, whatever their order rules,
 * end with the same values.
 *
 * Built by tools/build-mangohudcfg-hw.py. MHC_CONF_ONLY leaves only the file logic, for the host
 * test (tests/test_mangohudcfg.py). An argument names another file instead of %APPDATA%'s. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* ---- the file: read as hw_overlay.c's hud_read_conf does, merged on save ---- */
enum {MHC_FPS,MHC_FRAMETIME,MHC_FRAME_TIMING,MHC_GPU,MHC_CPU,MHC_RAM,MHC_VRAM,MHC_ROWS};
static const char *const mhc_row_keys[MHC_ROWS]={"fps","frametime","frame_timing","gpu_stats","cpu_stats","ram","vram"};
enum {MHC_POSITIONS=8};
/* hw_overlay.c's order (hud_positions); MangoHud's parse_position takes the same eight names */
static const char *const mhc_positions[MHC_POSITIONS]={"top-left","top-right","top-center","middle-left","middle-right",
                                                        "bottom-left","bottom-right","bottom-center"};
static const char *const mhc_other_keys[]={"position","offset_x","offset_y","font_size","background_alpha"};
/* limits: font_size as hw_overlay.c takes it (8..96); MangoHud reads the offsets as unsigned */
enum {MHC_FONT_MIN=8,MHC_FONT_MAX=96,MHC_OFFSET_MAX=2000};
#define MHC_MARKER "# OrbisDesk: the HUD options below are written by MangoHud Settings (C:\\orbis\\mangohudcfg.exe)"

struct mhc_conf {int row[MHC_ROWS];int position,offset_x,offset_y,font_size,alpha_pct;};

/* MangoHud's defaults (overlay_params.cpp), which hw_overlay.c starts from too */
static void mhc_defaults(struct mhc_conf *c)
{
    memset(c,0,sizeof(*c));
    c->row[MHC_FPS]=c->row[MHC_FRAMETIME]=c->row[MHC_FRAME_TIMING]=c->row[MHC_GPU]=c->row[MHC_CPU]=1;
    c->font_size=24;c->alpha_pct=50;
}
/* one line as hud_read_conf splits it: '#' ends it, then "key" or "key=value", blanks trimmed.
 * line is changed in place; returns 0 for a line without a key. */
static int mhc_split(char *line,char **key,char **value)
{
    char *end;
    if((end=strpbrk(line,"#\r\n"))) *end=0;
    while(*line==' ' || *line=='\t') line++;
    *value=strchr(line,'=');
    if(*value) {*(*value)++=0;while(**value==' ' || **value=='\t') (*value)++;}
    for(end=line+strlen(line);end>line && (end[-1]==' ' || end[-1]=='\t');) *--end=0;
    *key=line;
    return *line!=0;
}
static int mhc_managed(const char *key)
{
    for(int i=0;i<MHC_ROWS;i++) if(!strcmp(key,mhc_row_keys[i])) return 1;
    for(size_t i=0;i<sizeof(mhc_other_keys)/sizeof(*mhc_other_keys);i++) if(!strcmp(key,mhc_other_keys[i])) return 1;
    return 0;
}
static int mhc_clamp(int v,int lo,int hi) {return v<lo?lo:v>hi?hi:v;}
/* the next line of text[0..len): its start and length without the '\n' */
static int mhc_next_line(const char *text,size_t len,size_t *at,const char **line,size_t *line_len)
{
    if(*at>=len) return 0;
    const char *nl=memchr(text+*at,'\n',len-*at);
    *line=text+*at;*line_len=nl?(size_t)(nl-*line):len-*at;
    *at+=*line_len+(nl?1:0);
    return 1;
}
static void mhc_read(const char *text,size_t len,struct mhc_conf *c)
{
    const char *line;size_t line_len,at=0;char copy[512];
    mhc_defaults(c);
    while(mhc_next_line(text,len,&at,&line,&line_len)) {
        char *key,*value;
        if(line_len>=sizeof(copy)) line_len=sizeof(copy)-1;  /* hw_overlay.c reads 159 bytes; no key is longer */
        memcpy(copy,line,line_len);copy[line_len]=0;
        if(!mhc_split(copy,&key,&value)) continue;
        int on=!value || atoi(value)!=0;
        int row=-1;
        for(int i=0;i<MHC_ROWS;i++) if(!strcmp(key,mhc_row_keys[i])) row=i;
        if(row>=0) c->row[row]=on;
        else if(!strcmp(key,"full") && on) {for(int i=0;i<MHC_ROWS;i++) c->row[i]=1;}
        else if(!strcmp(key,"position") && value) {
            for(int i=0;i<MHC_POSITIONS;i++) if(!strcmp(value,mhc_positions[i])) c->position=i;
        } else if(!strcmp(key,"offset_x") && value) c->offset_x=mhc_clamp(atoi(value),0,MHC_OFFSET_MAX);
        else if(!strcmp(key,"offset_y") && value) c->offset_y=mhc_clamp(atoi(value),0,MHC_OFFSET_MAX);
        else if(!strcmp(key,"font_size") && value) {int n=atoi(value);if(n>=MHC_FONT_MIN && n<=MHC_FONT_MAX) c->font_size=n;}
        else if(!strcmp(key,"background_alpha") && value) {
            double a=strtod(value,NULL);
            if(a>=0 && a<=1) c->alpha_pct=(int)(a*100+0.5);
        }
    }
}
/* text with the edited keys and the marker taken out, then the marker and every edited key once;
 * malloc'd, NULL when out of memory */
static char *mhc_merge(const char *text,size_t len,const struct mhc_conf *c,size_t *out_len)
{
    size_t size=len+1024,used=0,kept_end=0,at=0,line_len;const char *line;
    char *out=malloc(size),copy[512];
    if(!out) return NULL;
    while(mhc_next_line(text,len,&at,&line,&line_len)) {
        size_t n=line_len;
        if(n && line[n-1]=='\r') n--;
        if(n==strlen(MHC_MARKER) && !memcmp(line,MHC_MARKER,n)) continue;
        if(n<sizeof(copy)) {
            char *key,*value;
            memcpy(copy,line,n);copy[n]=0;
            if(mhc_split(copy,&key,&value) && mhc_managed(key)) continue;
        }
        memcpy(out+used,line,n);used+=n;out[used++]='\n';
        if(n) kept_end=used;  /* blank lines at the end are dropped */
    }
    used=kept_end;
    used+=snprintf(out+used,size-used,"%s\n",MHC_MARKER);
    for(int i=0;i<MHC_ROWS;i++) used+=snprintf(out+used,size-used,"%s=%d\n",mhc_row_keys[i],c->row[i]?1:0);
    used+=snprintf(out+used,size-used,"position=%s\noffset_x=%d\noffset_y=%d\nfont_size=%d\nbackground_alpha=%d.%02d\n",
                   mhc_positions[mhc_clamp(c->position,0,MHC_POSITIONS-1)],mhc_clamp(c->offset_x,0,MHC_OFFSET_MAX),
                   mhc_clamp(c->offset_y,0,MHC_OFFSET_MAX),mhc_clamp(c->font_size,MHC_FONT_MIN,MHC_FONT_MAX),
                   mhc_clamp(c->alpha_pct,0,100)/100,mhc_clamp(c->alpha_pct,0,100)%100);
    *out_len=used;
    return out;
}

#ifndef MHC_CONF_ONLY
/* ---- the window ---- */
#include <windows.h>
#include <commctrl.h>
#include <shlobj.h>

enum {ID_ROW=100,ID_POSITION=200,ID_FONT,ID_FONT_UD,ID_ALPHA,ID_ALPHA_UD,ID_OFFX,ID_OFFX_UD,ID_OFFY,ID_OFFY_UD,
      ID_DEFAULTS,ID_STATUS,ID_PATH};
enum {S_TITLE,S_SHOW,S_ROW0,S_LOOK=S_ROW0+MHC_ROWS,S_POSITION,S_FONT,S_ALPHA,S_OFFX,S_OFFY,S_POS0,
      S_SAVE=S_POS0+MHC_POSITIONS,S_DEFAULTS,S_CLOSE,S_LOADED,S_NO_FILE,S_SAVED,S_SAVE_FAILED,S_ASK_SAVE,
      S_DEFAULTS_SHOWN,S_RELOADED,S_COUNT};
static const WCHAR *const strings_en[S_COUNT]={
    [S_TITLE]=L"MangoHud Settings",[S_SHOW]=L"Show",
    [S_ROW0+MHC_FPS]=L"Frames per second (fps)",[S_ROW0+MHC_FRAMETIME]=L"Frame time in ms (frametime)",
    [S_ROW0+MHC_FRAME_TIMING]=L"Frame time graph (frame_timing)",[S_ROW0+MHC_GPU]=L"GPU load (gpu_stats)",
    [S_ROW0+MHC_CPU]=L"CPU load (cpu_stats)",[S_ROW0+MHC_RAM]=L"Memory in use (ram)",
    [S_ROW0+MHC_VRAM]=L"Video memory in use (vram)",
    [S_LOOK]=L"Place and look",[S_POSITION]=L"Position:",[S_FONT]=L"Font size:",
    [S_ALPHA]=L"Background opacity (%):",[S_OFFX]=L"Horizontal offset (px):",[S_OFFY]=L"Vertical offset (px):",
    [S_POS0]=L"Top left",[S_POS0+1]=L"Top right",[S_POS0+2]=L"Top centre",[S_POS0+3]=L"Middle left",
    [S_POS0+4]=L"Middle right",[S_POS0+5]=L"Bottom left",[S_POS0+6]=L"Bottom right",[S_POS0+7]=L"Bottom centre",
    [S_SAVE]=L"&Save",[S_DEFAULTS]=L"&Defaults",[S_CLOSE]=L"Close",
    [S_LOADED]=L"Other options in the file are kept when you save.",
    [S_NO_FILE]=L"No settings file yet: MangoHud's defaults are shown. Save creates it.",
    [S_SAVED]=L"Saved. MangoHud reads it when a program starts; the overlay's Statistics when it is turned on.",
    [S_SAVE_FAILED]=L"Could not save the file (error %lu).",
    [S_ASK_SAVE]=L"Save the changes to the HUD settings?",
    [S_DEFAULTS_SHOWN]=L"MangoHud's defaults are shown. Save to keep them.",
    [S_RELOADED]=L"The file changed and was read again.",
};
static const WCHAR *const strings_es[S_COUNT]={
    [S_TITLE]=L"Ajustes de MangoHud",[S_SHOW]=L"Mostrar",
    [S_ROW0+MHC_FPS]=L"Fotogramas por segundo (fps)",[S_ROW0+MHC_FRAMETIME]=L"Tiempo de fotograma en ms (frametime)",
    [S_ROW0+MHC_FRAME_TIMING]=L"Gr\x00e1" L"fica de tiempos (frame_timing)",[S_ROW0+MHC_GPU]=L"Carga de la GPU (gpu_stats)",
    [S_ROW0+MHC_CPU]=L"Carga de la CPU (cpu_stats)",[S_ROW0+MHC_RAM]=L"Memoria en uso (ram)",
    [S_ROW0+MHC_VRAM]=L"Memoria de v\x00ed" L"deo en uso (vram)",
    [S_LOOK]=L"Posici\x00f3n y aspecto",[S_POSITION]=L"Posici\x00f3n:",[S_FONT]=L"Tama\x00f1o de letra:",
    [S_ALPHA]=L"Opacidad del fondo (%):",[S_OFFX]=L"Desplazamiento horizontal (px):",
    [S_OFFY]=L"Desplazamiento vertical (px):",
    [S_POS0]=L"Arriba a la izquierda",[S_POS0+1]=L"Arriba a la derecha",[S_POS0+2]=L"Arriba al centro",
    [S_POS0+3]=L"En medio a la izquierda",[S_POS0+4]=L"En medio a la derecha",[S_POS0+5]=L"Abajo a la izquierda",
    [S_POS0+6]=L"Abajo a la derecha",[S_POS0+7]=L"Abajo al centro",
    [S_SAVE]=L"&Guardar",[S_DEFAULTS]=L"&Valores por defecto",[S_CLOSE]=L"Cerrar",
    [S_LOADED]=L"Al guardar se conservan las dem\x00e1s opciones del archivo.",
    [S_NO_FILE]=L"A\x00fan no hay archivo de ajustes: se muestran los valores por defecto de MangoHud. Guardar lo crea.",
    [S_SAVED]=L"Guardado. MangoHud lo lee al iniciarse un programa; las Estad\x00ed" L"sticas del overlay, al activarlas.",
    [S_SAVE_FAILED]=L"No se pudo guardar el archivo (error %lu).",
    [S_ASK_SAVE]=L"\x00bfGuardar los cambios en los ajustes del HUD?",
    [S_DEFAULTS_SHOWN]=L"Se muestran los valores por defecto de MangoHud. Guarde para conservarlos.",
    [S_RELOADED]=L"El archivo cambi\x00f3 y se ley\x00f3 de nuevo.",
};
static const WCHAR *const *strings=strings_en;

static WCHAR conf_path[MAX_PATH];
static HWND main_window;
static HFONT ui_font;
static int dirty,loading;
static FILETIME conf_time;

/* the whole file, malloc'd (NULL and *len 0 when it is absent); at most 1 MiB */
static char *read_file(size_t *len,FILETIME *written)
{
    HANDLE file=CreateFileW(conf_path,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE,NULL,OPEN_EXISTING,0,NULL);
    LARGE_INTEGER size;char *text=NULL;DWORD got=0;
    *len=0;memset(written,0,sizeof(*written));
    if(file==INVALID_HANDLE_VALUE) return NULL;
    if(GetFileSizeEx(file,&size) && size.QuadPart<=(1<<20) && (text=malloc((size_t)size.QuadPart+1))) {
        if(ReadFile(file,text,(DWORD)size.QuadPart,&got,NULL)) *len=got;
        GetFileTime(file,NULL,NULL,written);
    }
    CloseHandle(file);
    return text;
}
static void set_status(const WCHAR *text) {SetDlgItemTextW(main_window,ID_STATUS,text);}
static void conf_to_ui(const struct mhc_conf *c)
{
    loading=1;
    for(int i=0;i<MHC_ROWS;i++) CheckDlgButton(main_window,ID_ROW+i,c->row[i]?BST_CHECKED:BST_UNCHECKED);
    SendDlgItemMessageW(main_window,ID_POSITION,CB_SETCURSEL,c->position,0);
    SendDlgItemMessageW(main_window,ID_FONT_UD,UDM_SETPOS32,0,c->font_size);
    SendDlgItemMessageW(main_window,ID_ALPHA_UD,UDM_SETPOS32,0,c->alpha_pct);
    SendDlgItemMessageW(main_window,ID_OFFX_UD,UDM_SETPOS32,0,c->offset_x);
    SendDlgItemMessageW(main_window,ID_OFFY_UD,UDM_SETPOS32,0,c->offset_y);
    loading=0;
}
/* a number box: what was typed, held inside its limits (the up-down control does not check typing) */
static int number(int id,int lo,int hi,int fallback)
{
    BOOL ok;int v=(int)GetDlgItemInt(main_window,id,&ok,TRUE);
    return ok?mhc_clamp(v,lo,hi):fallback;
}
static void ui_to_conf(struct mhc_conf *c)
{
    struct mhc_conf d;mhc_defaults(&d);
    for(int i=0;i<MHC_ROWS;i++) c->row[i]=IsDlgButtonChecked(main_window,ID_ROW+i)==BST_CHECKED;
    LRESULT pos=SendDlgItemMessageW(main_window,ID_POSITION,CB_GETCURSEL,0,0);
    c->position=pos>=0 && pos<MHC_POSITIONS?(int)pos:0;
    c->font_size=number(ID_FONT,MHC_FONT_MIN,MHC_FONT_MAX,d.font_size);
    c->alpha_pct=number(ID_ALPHA,0,100,d.alpha_pct);
    c->offset_x=number(ID_OFFX,0,MHC_OFFSET_MAX,0);
    c->offset_y=number(ID_OFFY,0,MHC_OFFSET_MAX,0);
}
static void load(int reload)
{
    size_t len;struct mhc_conf c;
    char *text=read_file(&len,&conf_time);
    mhc_read(text?text:"",len,&c);
    conf_to_ui(&c);
    dirty=0;
    set_status(strings[!text?S_NO_FILE:reload?S_RELOADED:S_LOADED]);
    free(text);
}
/* the file as it is now merged with the form, through a temporary file renamed over it */
static int save(void)
{
    size_t len,out_len;struct mhc_conf c;FILETIME unused;WCHAR folder[MAX_PATH],temp[MAX_PATH+8],message[160];
    DWORD error=0,wrote=0;
    ui_to_conf(&c);
    char *text=read_file(&len,&unused),*out=mhc_merge(text?text:"",len,&c,&out_len);
    free(text);
    lstrcpynW(folder,conf_path,MAX_PATH);
    WCHAR *slash=wcsrchr(folder,L'\\');
    if(slash) {*slash=0;CreateDirectoryW(folder,NULL);}
    wsprintfW(temp,L"%s.new",conf_path);
    if(!out) error=ERROR_OUTOFMEMORY;
    else {
        HANDLE file=CreateFileW(temp,GENERIC_WRITE,0,NULL,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,NULL);
        if(file==INVALID_HANDLE_VALUE) error=GetLastError();
        else {
            if(!WriteFile(file,out,(DWORD)out_len,&wrote,NULL) || wrote!=out_len) error=GetLastError()?GetLastError():ERROR_WRITE_FAULT;
            CloseHandle(file);
            if(!error && !MoveFileExW(temp,conf_path,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH)) error=GetLastError();
            if(error) DeleteFileW(temp);
        }
    }
    free(out);
    if(error) {wsprintfW(message,strings[S_SAVE_FAILED],error);set_status(message);return 0;}
    char *again=read_file(&len,&conf_time);free(again);
    dirty=0;set_status(strings[S_SAVED]);
    return 1;
}

static HWND add(DWORD ex,const WCHAR *cls,const WCHAR *text,DWORD style,int x,int y,int w,int h,int id)
{
    HWND control=CreateWindowExW(ex,cls,text,WS_CHILD|WS_VISIBLE|style,x,y,w,h,main_window,(HMENU)(INT_PTR)id,
                                 GetModuleHandleW(NULL),NULL);
    SendMessageW(control,WM_SETFONT,(WPARAM)ui_font,FALSE);
    return control;
}
static void add_number(int y,int line,int label_w,const WCHAR *label,int id,int lo,int hi)
{
    add(0,L"STATIC",label,SS_LEFT|SS_CENTERIMAGE,24,y,label_w,line,-1);
    HWND edit=add(WS_EX_CLIENTEDGE,L"EDIT",L"",WS_TABSTOP|ES_NUMBER|ES_RIGHT,24+label_w+8,y,90,line,id);
    HWND updown=add(0,UPDOWN_CLASSW,NULL,UDS_SETBUDDYINT|UDS_ALIGNRIGHT|UDS_ARROWKEYS|UDS_NOTHOUSANDS,0,0,0,0,id+1);
    SendMessageW(updown,UDM_SETBUDDY,(WPARAM)edit,0);
    SendMessageW(updown,UDM_SETRANGE32,lo,hi);
}
/* the controls laid out from the font's height, so a larger theme font still fits */
static void create_controls(int *client_w,int *client_h)
{
    HDC dc=GetDC(main_window);TEXTMETRICW tm;
    HFONT old=SelectObject(dc,ui_font);GetTextMetricsW(dc,&tm);
    int label_w=0;SIZE size;
    for(int s=S_POSITION;s<=S_OFFY;s++) {
        GetTextExtentPoint32W(dc,strings[s],lstrlenW(strings[s]),&size);
        if(size.cx>label_w) label_w=size.cx;
    }
    SelectObject(dc,old);ReleaseDC(main_window,dc);
    int line=tm.tmHeight+8,gap=4,width=label_w+8+90+180+48;
    if(width<480) width=480;
    int y=10;
    add(0,L"BUTTON",strings[S_SHOW],BS_GROUPBOX,10,y,width-20,line*MHC_ROWS+gap*(MHC_ROWS-1)+line+8,-1);
    y+=line;
    for(int i=0;i<MHC_ROWS;i++,y+=line+gap)
        add(0,L"BUTTON",strings[S_ROW0+i],WS_TABSTOP|BS_AUTOCHECKBOX|(i?0:WS_GROUP),24,y,width-48,line,ID_ROW+i);
    y+=10;
    int look_top=y;
    y+=line;
    add(0,L"STATIC",strings[S_POSITION],SS_LEFT|SS_CENTERIMAGE,24,y,label_w,line,-1);
    HWND combo=add(0,L"COMBOBOX",L"",WS_TABSTOP|WS_VSCROLL|CBS_DROPDOWNLIST|WS_GROUP,24+label_w+8,y,240,line*10,ID_POSITION);
    for(int i=0;i<MHC_POSITIONS;i++) SendMessageW(combo,CB_ADDSTRING,0,(LPARAM)strings[S_POS0+i]);
    y+=line+gap;
    add_number(y,line,label_w,strings[S_FONT],ID_FONT,MHC_FONT_MIN,MHC_FONT_MAX);y+=line+gap;
    add_number(y,line,label_w,strings[S_ALPHA],ID_ALPHA,0,100);y+=line+gap;
    add_number(y,line,label_w,strings[S_OFFX],ID_OFFX,0,MHC_OFFSET_MAX);y+=line+gap;
    add_number(y,line,label_w,strings[S_OFFY],ID_OFFY,0,MHC_OFFSET_MAX);y+=line+gap;
    add(0,L"BUTTON",strings[S_LOOK],BS_GROUPBOX,10,look_top,width-20,y-look_top+4,-1);
    y+=14;
    add(0,L"STATIC",conf_path,SS_LEFT|SS_PATHELLIPSIS|SS_NOPREFIX,10,y,width-20,line,ID_PATH);y+=line;
    add(0,L"STATIC",L"",SS_LEFT|SS_NOPREFIX,10,y,width-20,line*2,ID_STATUS);y+=line*2+gap;
    int button_w=(width-20-16)/3;
    add(0,L"BUTTON",strings[S_SAVE],WS_TABSTOP|BS_DEFPUSHBUTTON|WS_GROUP,10,y,button_w,line+4,IDOK);
    add(0,L"BUTTON",strings[S_DEFAULTS],WS_TABSTOP,10+button_w+8,y,button_w,line+4,ID_DEFAULTS);
    add(0,L"BUTTON",strings[S_CLOSE],WS_TABSTOP,10+2*(button_w+8),y,button_w,line+4,IDCANCEL);
    *client_w=width;*client_h=y+line+4+10;
}
static int confirm_close(void)
{
    if(!dirty) return 1;
    int answer=MessageBoxW(main_window,strings[S_ASK_SAVE],strings[S_TITLE],MB_YESNOCANCEL|MB_ICONQUESTION);
    return answer==IDNO || (answer==IDYES && save());
}
static LRESULT CALLBACK window_proc(HWND window,UINT message,WPARAM wparam,LPARAM lparam)
{
    switch(message) {
    case WM_COMMAND: {
        int id=LOWORD(wparam),code=HIWORD(wparam);
        if(id==IDOK) {save();return 0;}
        if(id==IDCANCEL) {if(confirm_close()) DestroyWindow(window);return 0;}
        if(id==ID_DEFAULTS) {
            struct mhc_conf c;mhc_defaults(&c);conf_to_ui(&c);dirty=1;set_status(strings[S_DEFAULTS_SHOWN]);
            return 0;
        }
        if(!loading && ((id>=ID_ROW && id<ID_ROW+MHC_ROWS && code==BN_CLICKED) ||
                        (id==ID_POSITION && code==CBN_SELCHANGE) ||
                        ((id==ID_FONT || id==ID_ALPHA || id==ID_OFFX || id==ID_OFFY) && code==EN_CHANGE))) dirty=1;
        break;
    }
    case WM_ACTIVATE:
        /* edited elsewhere (Notepad) while this form had nothing unsaved: shown again */
        if(LOWORD(wparam)!=WA_INACTIVE && !dirty) {
            size_t len;FILETIME now;char *text=read_file(&len,&now);free(text);
            if(CompareFileTime(&now,&conf_time)) load(1);
        }
        break;
    case WM_CLOSE:
        if(confirm_close()) DestroyWindow(window);
        return 0;
    case WM_DESTROY:
        PostQuitMessage(0);
        return 0;
    }
    return DefWindowProcW(window,message,wparam,lparam);
}

int WINAPI wWinMain(HINSTANCE instance,HINSTANCE previous,PWSTR command_line,int show)
{
    (void)previous;
    INITCOMMONCONTROLSEX icc={sizeof(icc),ICC_STANDARD_CLASSES|ICC_UPDOWN_CLASS};
    InitCommonControlsEx(&icc);
    if(PRIMARYLANGID(GetUserDefaultUILanguage())==LANG_SPANISH) strings=strings_es;
    int argc=0;WCHAR **argv=CommandLineToArgvW(command_line,&argc);
    if(command_line && *command_line && argv && argc>0) lstrcpynW(conf_path,argv[0],MAX_PATH);
    else {
        /* %APPDATA%, MangoHud's own place for it; C:\users\orbis\AppData\Roaming on the console */
        if(SHGetFolderPathW(NULL,CSIDL_APPDATA,NULL,SHGFP_TYPE_CURRENT,conf_path)!=S_OK) {
            DWORD n=GetEnvironmentVariableW(L"APPDATA",conf_path,MAX_PATH);
            if(!n || n>=MAX_PATH) lstrcpyW(conf_path,L"C:\\users\\orbis\\AppData\\Roaming");
        }
        if(lstrlenW(conf_path)<MAX_PATH-32) lstrcatW(conf_path,L"\\MangoHud\\MangoHud.conf");
    }
    LocalFree(argv);
    NONCLIENTMETRICSW metrics;
    memset(&metrics,0,sizeof(metrics));metrics.cbSize=sizeof(metrics);
    ui_font=SystemParametersInfoW(SPI_GETNONCLIENTMETRICS,sizeof(metrics),&metrics,0)?
            CreateFontIndirectW(&metrics.lfMessageFont):(HFONT)GetStockObject(DEFAULT_GUI_FONT);
    /* the Start menu item's icon (tools/make-icons.py, C:\orbis\icons next to this program) */
    WCHAR icon_path[MAX_PATH];HICON icon=NULL;
    DWORD n=GetModuleFileNameW(NULL,icon_path,MAX_PATH);
    WCHAR *slash=n && n<MAX_PATH?wcsrchr(icon_path,L'\\'):NULL;
    if(slash && slash-icon_path<MAX_PATH-32) {
        lstrcpyW(slash,L"\\icons\\mangohud.ico");
        icon=LoadImageW(NULL,icon_path,IMAGE_ICON,0,0,LR_LOADFROMFILE|LR_DEFAULTSIZE);
    }
    WNDCLASSW cls={0};
    cls.lpfnWndProc=window_proc;cls.hInstance=instance;cls.lpszClassName=L"OrbisDeskMangoHudSettings";
    cls.hCursor=LoadCursorW(NULL,(LPCWSTR)IDC_ARROW);cls.hbrBackground=(HBRUSH)(COLOR_BTNFACE+1);
    cls.hIcon=icon?icon:LoadIconW(NULL,(LPCWSTR)IDI_APPLICATION);
    if(!RegisterClassW(&cls)) return 1;
    DWORD style=WS_OVERLAPPED|WS_CAPTION|WS_SYSMENU|WS_MINIMIZEBOX;
    main_window=CreateWindowExW(WS_EX_CONTROLPARENT,cls.lpszClassName,strings[S_TITLE],style,CW_USEDEFAULT,CW_USEDEFAULT,
                                100,100,NULL,NULL,instance,NULL);
    if(!main_window) return 1;
    int w,h;create_controls(&w,&h);
    RECT rect={0,0,w,h};AdjustWindowRectEx(&rect,style,FALSE,WS_EX_CONTROLPARENT);
    SetWindowPos(main_window,NULL,0,0,rect.right-rect.left,rect.bottom-rect.top,SWP_NOMOVE|SWP_NOZORDER);
    load(0);
    ShowWindow(main_window,show);
    UpdateWindow(main_window);
    SetFocus(GetDlgItem(main_window,ID_ROW));
    MSG msg;
    while(GetMessageW(&msg,NULL,0,0)>0) {
        if(IsDialogMessageW(main_window,&msg)) continue;
        TranslateMessage(&msg);DispatchMessageW(&msg);
    }
    if(ui_font && ui_font!=GetStockObject(DEFAULT_GUI_FONT)) DeleteObject(ui_font);
    return 0;
}
#endif
