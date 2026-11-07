/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* W236: the control overlay. L3 and R3 pressed together open a panel over the output while the
 * program keeps running; until it closes, the pad drives the panel only (native/hw_pad.c shows
 * programs and its own emulation a neutral pad). Entries:
 *   SALIR         the program in front closes and the desktop comes back: a request that explorer's
 *                 kernelbase closer takes (tools/build-guest-hw.py; W239, no key since W238 died on
 *                 F24) and answers with the result, or return_to_desktop in a relaunched title
 *                 (native/wine_hardware.c)
 *   ESTADISTICAS  a corner readout with measured values only; "--" where there is no measure.
 *                 W238: MangoHud's own HUD instead, when its layer is loaded and a Vulkan program
 *                 presents: Shift+F12, a hotkey of kernelbase's closer, which MangoHud reads as F12
 *   TECLADO       an on-screen keyboard; its keys go to the focused window as key events
 *   MOUSE         the pad as pointer on or off (native/hw_pad.c), for this run only
 *   CURSOR        W261: whether the sink draws the pointer, per program: game (ps5drv's rule), always or
 *                 hidden, saved in C:\orbis\overlay.ini ("cursor.<exe>=..."; game without a line)
 *   ESTIRAR       W266: the picture fills the whole output, no black bars, per program ("stretch.<exe>=on";
 *                 off without a line); not changed with the desktop in front
 *   GRAFICOS      W287: per 32-bit program, from its next start: D3D8/9 through DXVK or Wine's wined3d, and
 *                 wined3d's renderer Vulkan or OpenGL; kernelbase's closer keeps them in the registry
 *                 (HKCU\Software\Wine\AppDefaults\<exe>, tools/build-guest-hw.py)
 *   CONTROL       Xbox 360, Xbox One or DualSense, saved in C:\orbis\padtype.txt, which xinput,
 *                 dinput (tools/build-xinput-hw.py, build-dinput-hw.py) and winebus
 *                 (native/winebus_orbis.c) read
 *   CONFIG        W240: the overlay's language, Spanish or English, saved in C:\orbis\overlay.ini
 *                 ("lang=es" or "lang=en"); every text it shows comes from the strings table below
 * The pad thread calls pw_hw_overlay_pad on each read; the sink calls pw_hw_overlay_draw on each
 * output frame before the flip (platform/ps4/pw_wine_sink_ps4.c). Drawn opaque: reading back the
 * output buffer, which the GPU writes, would be slow. */
#include <errno.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <strings.h>
#include <sys/types.h>
#include <orbis/libkernel.h>
#include <orbis/Pad.h>
#include "hw_text.h"
#include "pw_telemetry.h"

extern void pw_hw_pad_key(uint32_t vk,int down);     /* native/hw_pad.c */
extern void pw_hw_pad_set_mouse(int on);
extern void pw_hw_cursor_moved(void);                /* the sink shows the last frame again */
extern int pw_hw_overlay_exit_title(int ask);        /* native/wine_hardware.c */
extern void pw_hw_sink_stats(unsigned *vk_tenths,int *vk_fresh,unsigned *frames_tenths,unsigned *avg_us,
                             unsigned *max_us,int *frames_fresh);
extern uint32_t pw_ps4_telemetry_query(void *info,uint32_t bytes,uint32_t *returned);  /* native/telemetry.c */

#define TYPE_FILE "/data/wine-prefix/drive_c/orbis/padtype.txt"
#define CONFIG_FILE "/data/wine-prefix/drive_c/orbis/overlay.ini"
enum {ENTRY_EXIT,ENTRY_STATS,ENTRY_KEYBOARD,ENTRY_MOUSE,ENTRY_CURSOR,ENTRY_STRETCH,ENTRY_RENDER,ENTRY_CONTROL,ENTRY_CONFIG,
      ENTRIES};
enum {VIEW_CLOSED,VIEW_PANEL,VIEW_KEYBOARD};
enum {TYPE_X360,TYPE_XONE,TYPE_DUALSENSE,TYPES};
enum {VK_BACK=0x08,VK_TAB=0x09,VK_RETURN=0x0d,VK_SHIFT=0x10,VK_ESCAPE=0x1b,VK_SPACE=0x20,VK_END=0x23,VK_HOME=0x24,
      VK_LEFT=0x25,VK_RIGHT=0x27,VK_DELETE=0x2e,VK_F12=0x7b,VK_F24=0x87};
enum {REPEAT_FIRST_US=350000,REPEAT_US=110000,STICK_NAV=80,TOAST_US=3000000,STATS_US=1000000};
/* W238: MangoHud reads its key at a present, at most every 100 ms (keybinds.cpp): F12 is held longer */
enum {HUD_HOLD_US=250000};
static const char *const type_names[TYPES]={"XBOX 360","XBOX ONE","DUALSENSE"};
static const char *const type_words[TYPES]={"x360","xone","dualsense"};

/* W240: every text the overlay shows, in Spanish and in English. The glyphs have no accents or N
 * with tilde (hw_text.h and the tables below), so the Spanish is written without them. */
enum {LANG_ES,LANG_EN,LANGS};
static const char *const lang_words[LANGS]={"es","en"};
static const char *const lang_names[LANGS]={"ESPANOL","ENGLISH"};
enum {S_ENTRY_EXIT,S_ENTRY_STATS,S_ENTRY_KEYBOARD,S_ENTRY_MOUSE,S_ENTRY_CONTROL,S_ENTRY_CONFIG,
      S_ENTRY_CURSOR,S_CURSOR_GAME,S_CURSOR_ALWAYS,S_CURSOR_HIDDEN,S_CURSOR_PROGRAM,S_HELP_CURSOR,S_T_CURSOR_NO_PROGRAM,
      S_ENTRY_STRETCH,S_HELP_STRETCH,
      S_ENTRY_RENDER,S_HELP_RENDER,S_RENDER_DXVK_VK,S_RENDER_DXVK_GL,S_RENDER_WINED3D_VK,S_RENDER_WINED3D_GL,
      S_T_RENDER_SAVED,S_T_RENDER_FAILED,S_T_RENDER_NO_ANSWER,S_T_RENDER_NO_PROGRAM,
      S_ON,S_OFF,S_OWN_ON,S_OWN_OFF,S_SAVED,S_FOOTER,
      S_HELP_EXIT,S_HELP_EXIT_ALONE,S_HELP_STATS,S_HELP_STATS_HUD,S_HELP_KEYBOARD,S_HELP_MOUSE,S_HELP_CONTROL,S_HELP_CONFIG,
      S_KB_TITLE,S_KB_CAPS,S_KB_LOWER,S_KB_HINT1,S_KB_HINT2,
      S_KEY_SHIFT,S_KEY_SPACE,S_KEY_BACK,S_KEY_ENTER,S_KEY_HOME,S_KEY_END,S_KEY_DELETE,
      S_STAT_FRAMES,S_STAT_INTERVAL,S_STAT_DIRECT,
      S_T_HUD_SENT,S_T_TYPE_NOT_SAVED,S_T_CONFIG_NOT_SAVED,S_T_CLOSED,S_T_REFUSED_DESKTOP,S_T_REFUSED_NONE,
      S_T_REFUSED_CONSOLE,S_T_KEPT,S_T_ASKED32,S_T_UNKNOWN,S_T_NOT_TAKEN,S_T_NO_RESULT,S_T_BACK_DESKTOP,
      S_T_BACK_FAILED,S_T_SEARCHING,STRINGS};
static const char *const strings[LANGS][STRINGS]={
    [LANG_ES]={
        [S_ENTRY_EXIT]="SALIR",[S_ENTRY_STATS]="ESTADISTICAS",[S_ENTRY_KEYBOARD]="TECLADO",[S_ENTRY_MOUSE]="MOUSE",
        [S_ENTRY_CONTROL]="CONTROL",[S_ENTRY_CONFIG]="CONFIG",
        [S_ENTRY_CURSOR]="CURSOR",[S_CURSOR_GAME]="JUEGO",[S_CURSOR_ALWAYS]="SIEMPRE",[S_CURSOR_HIDDEN]="OCULTO",
        [S_CURSOR_PROGRAM]="PROGRAMA:",[S_T_CURSOR_NO_PROGRAM]="CURSOR: NINGUN PROGRAMA ABIERTO",
        [S_ENTRY_STRETCH]="ESTIRAR",
        [S_ENTRY_RENDER]="GRAFICOS",
        [S_HELP_RENDER]="IZQUIERDA Y DERECHA ELIGEN, X GUARDA PARA EL ULTIMO PROGRAMA ABIERTO EN EL REGISTRO DE WINE. "
                        "VALE DESDE SU PROXIMO ARRANQUE. PRIMERO D3D8/9, DESPUES DIRECTDRAW Y D3D7. SOLO PROGRAMAS DE 32 BITS.",
        [S_RENDER_DXVK_VK]="DXVK + VULKAN",[S_RENDER_DXVK_GL]="DXVK + OPENGL",[S_RENDER_WINED3D_VK]="WINED3D + VULKAN",
        [S_RENDER_WINED3D_GL]="WINED3D + OPENGL",
        [S_T_RENDER_SAVED]="GRAFICOS: AL PROXIMO ARRANQUE",[S_T_RENDER_FAILED]="GRAFICOS: NO SE GUARDO (VER LOG)",
        [S_T_RENDER_NO_ANSWER]="GRAFICOS: SIN RESPUESTA (VER LOG)",[S_T_RENDER_NO_PROGRAM]="GRAFICOS: NINGUN PROGRAMA ABIERTO",
        [S_HELP_STRETCH]="X: ESTIRA LA IMAGEN A TODA LA PANTALLA, SIN FRANJAS NEGRAS, O VUELVE A MANTENER SU PROPORCION. "
                         "SE GUARDA PARA EL ULTIMO PROGRAMA ABIERTO EN C:\\ORBIS\\OVERLAY.INI. NO CAMBIA CON EL ESCRITORIO "
                         "AL FRENTE.",
        [S_HELP_CURSOR]="IZQUIERDA Y DERECHA ELIGEN, X GUARDA PARA EL ULTIMO PROGRAMA ABIERTO EN C:\\ORBIS\\OVERLAY.INI. "
                        "JUEGO: LA FLECHA SE VE, SALVO EN PANTALLA COMPLETA SI EL JUEGO NO PONE CURSOR. SIEMPRE: SE VE "
                        "SIEMPRE. OCULTO: NO SE VE MIENTRAS ESE PROGRAMA SIGA ABIERTO. EL MANDO LA MUEVE IGUAL.",
        [S_ON]="SI",[S_OFF]="NO",[S_OWN_ON]="PROPIA: SI",[S_OWN_OFF]="PROPIA: NO",[S_SAVED]="GUARDADO",[S_FOOTER]="X ELEGIR   O CERRAR",
        [S_HELP_EXIT]="X: CIERRA EL PROGRAMA DE LA VENTANA ACTIVA, COMO SI TERMINARA DE GOLPE, Y QUEDA EL ESCRITORIO. "
                      "NO PREGUNTA NI GUARDA: LO NO GUARDADO SE PIERDE.",
        [S_HELP_EXIT_ALONE]="X: CIERRA ESTE PROGRAMA, QUE CORRE SOLO, Y LA APP SE REINICIA EN EL ESCRITORIO. NO PREGUNTA NI GUARDA.",
        [S_HELP_STATS]="X: MUESTRA U OCULTA LA LECTURA EN LA ESQUINA. FPS VK: PRESENTACIONES VULKAN POR SEGUNDO. CUADROS: "
                       "LOS QUE WINE ENTREGA A LA PANTALLA, CON SU INTERVALO MEDIO Y MAXIMO. CPU Y GPU: USO MEDIDO DEL TITULO. "
                       "MEM: FLEXIBLE LIBRE Y MAYOR BLOQUE LIBRE DE MEMORIA DIRECTA. -- ES SIN MEDIDA.",
        [S_HELP_STATS_HUD]="X: MUESTRA U OCULTA MANGOHUD CON SU TECLA (SHIFT+F12; EL PROGRAMA NO LA RECIBE). EL OVERLAY NO PUEDE "
                           "LEER SI QUEDO VISIBLE: MIRALO EN PANTALLA. SIN UN PROGRAMA VULKAN EN PANTALLA, X PRENDE LA LECTURA PROPIA.",
        [S_HELP_KEYBOARD]="X: ABRE EL TECLADO. ESCRIBE EN LA VENTANA CON EL FOCO. CUADRADO BORRA, TRIANGULO ESPACIO, L1 Y R1 "
                          "MUEVEN EL CURSOR, L2 MAYUSCULA, R2 SIMBOLOS, OPTIONS ENTER, CIRCULO CIERRA.",
        [S_HELP_MOUSE]="X: ENCIENDE O APAGA EL MANDO COMO MOUSE. APAGADO, EL STICK Y EL TOUCHPAD NO MUEVEN EL PUNTERO NI HACEN "
                       "CLIC NI RUEDA. LAS TECLAS DEL MANDO Y LOS PERFILES SIGUEN. VALE HASTA CERRAR LA APP.",
        [S_HELP_CONTROL]="IZQUIERDA Y DERECHA ELIGEN, X GUARDA. MUCHOS JUEGOS ELIGEN EL MANDO AL ARRANCAR: SI NO CAMBIA, "
                         "REINICIA EL JUEGO. 360 Y ONE CAMBIAN EL ID QUE VEN XINPUT Y DIRECTINPUT. DUALSENSE AGREGA UN MANDO HID "
                         "PARA JUEGOS QUE BUSCAN MANDOS NUEVOS (SDL, STEAM); XINPUT SIGUE COMO 360: PUEDE HABER DOS MANDOS.",
        [S_HELP_CONFIG]="IZQUIERDA Y DERECHA ELIGEN EL IDIOMA DEL OVERLAY, X LO GUARDA EN C:\\ORBIS\\OVERLAY.INI. SE APLICA "
                        "EN EL MOMENTO.",
        [S_KB_TITLE]="TECLADO",[S_KB_CAPS]="MAYUS",[S_KB_LOWER]="minus",
        [S_KB_HINT1]="X TECLA  CUADRADO BORRA  TRIANGULO ESPACIO  L1 R1 CURSOR",
        [S_KB_HINT2]="L2 MAYUSCULA  R2 SIMBOLOS  OPTIONS ENTER  CIRCULO CIERRA",
        [S_KEY_SHIFT]="MAYUS",[S_KEY_SPACE]="ESPACIO",[S_KEY_BACK]="BORRAR",[S_KEY_ENTER]="ENTER",
        [S_KEY_HOME]="INICIO",[S_KEY_END]="FIN",[S_KEY_DELETE]="SUPR",
        [S_STAT_FRAMES]="CUADROS",[S_STAT_INTERVAL]="INTERVALO",[S_STAT_DIRECT]="DIRECTA",
        [S_T_HUD_SENT]="MANGOHUD: SHIFT+F12 ENVIADO",[S_T_TYPE_NOT_SAVED]="NO SE PUDO GUARDAR EL TIPO",
        [S_T_CONFIG_NOT_SAVED]="NO SE PUDO GUARDAR LA CONFIG",[S_T_CLOSED]="PROGRAMA CERRADO",
        [S_T_REFUSED_DESKTOP]="SALIR: EL ESCRITORIO NO SE CIERRA",[S_T_REFUSED_NONE]="SALIR: NO HAY VENTANA ACTIVA",
        [S_T_REFUSED_CONSOLE]="SALIR: PROGRAMA DE CONSOLA, NO SE CIERRA",[S_T_KEPT]="NO SE PUDO CERRAR: VER LOG",
        [S_T_ASKED32]="SALIR: PEDIDO AL MUNDO DE 32 BITS",[S_T_UNKNOWN]="SALIR: RESULTADO DESCONOCIDO",
        [S_T_NOT_TAKEN]="SALIR: SIN RESPUESTA (VER LOG)",[S_T_NO_RESULT]="SALIR: SIN RESULTADO (VER LOG)",
        [S_T_BACK_DESKTOP]="VOLVIENDO AL ESCRITORIO",[S_T_BACK_FAILED]="NO SE PUDO VOLVER AL ESCRITORIO",
        [S_T_SEARCHING]="SALIR: BUSCANDO EL PROGRAMA ACTIVO"},
    [LANG_EN]={
        [S_ENTRY_EXIT]="EXIT",[S_ENTRY_STATS]="STATISTICS",[S_ENTRY_KEYBOARD]="KEYBOARD",[S_ENTRY_MOUSE]="MOUSE",
        [S_ENTRY_CONTROL]="CONTROLLER",[S_ENTRY_CONFIG]="CONFIG",
        [S_ENTRY_CURSOR]="CURSOR",[S_CURSOR_GAME]="GAME",[S_CURSOR_ALWAYS]="ALWAYS",[S_CURSOR_HIDDEN]="HIDDEN",
        [S_CURSOR_PROGRAM]="PROGRAM:",[S_T_CURSOR_NO_PROGRAM]="CURSOR: NO PROGRAM OPEN",
        [S_ENTRY_STRETCH]="STRETCH",
        [S_ENTRY_RENDER]="GRAPHICS",
        [S_HELP_RENDER]="LEFT AND RIGHT CHOOSE, X SAVES IT FOR THE LAST PROGRAM OPENED IN WINE'S REGISTRY. IT APPLIES "
                        "FROM ITS NEXT START. FIRST D3D8/9, THEN DIRECTDRAW AND D3D7. 32-BIT PROGRAMS ONLY.",
        [S_RENDER_DXVK_VK]="DXVK + VULKAN",[S_RENDER_DXVK_GL]="DXVK + OPENGL",[S_RENDER_WINED3D_VK]="WINED3D + VULKAN",
        [S_RENDER_WINED3D_GL]="WINED3D + OPENGL",
        [S_T_RENDER_SAVED]="GRAPHICS: AT THE NEXT START",[S_T_RENDER_FAILED]="GRAPHICS: NOT SAVED (SEE LOG)",
        [S_T_RENDER_NO_ANSWER]="GRAPHICS: NO ANSWER (SEE LOG)",[S_T_RENDER_NO_PROGRAM]="GRAPHICS: NO PROGRAM OPEN",
        [S_HELP_STRETCH]="X: STRETCHES THE PICTURE TO THE WHOLE SCREEN, WITHOUT BLACK BARS, OR KEEPS ITS PROPORTIONS AGAIN. "
                         "SAVED FOR THE LAST PROGRAM OPENED IN C:\\ORBIS\\OVERLAY.INI. IT DOES NOT CHANGE WITH THE DESKTOP "
                         "IN FRONT.",
        [S_HELP_CURSOR]="LEFT AND RIGHT CHOOSE, X SAVES IT FOR THE LAST PROGRAM OPENED IN C:\\ORBIS\\OVERLAY.INI. GAME: "
                        "THE ARROW SHOWS, EXCEPT FULL SCREEN WHEN THE GAME SETS NO CURSOR. ALWAYS: IT ALWAYS SHOWS. "
                        "HIDDEN: IT DOES NOT SHOW WHILE THAT PROGRAM STAYS OPEN. THE PAD STILL MOVES IT.",
        [S_ON]="ON",[S_OFF]="OFF",[S_OWN_ON]="OWN: ON",[S_OWN_OFF]="OWN: OFF",[S_SAVED]="SAVED",[S_FOOTER]="X SELECT   O CLOSE",
        [S_HELP_EXIT]="X: CLOSES THE PROGRAM OF THE ACTIVE WINDOW, AS IF IT ENDED AT ONCE, AND THE DESKTOP STAYS. "
                      "IT DOES NOT ASK OR SAVE: UNSAVED WORK IS LOST.",
        [S_HELP_EXIT_ALONE]="X: CLOSES THIS PROGRAM, WHICH RUNS ALONE, AND THE APP RESTARTS INTO THE DESKTOP. IT DOES NOT ASK OR SAVE.",
        [S_HELP_STATS]="X: SHOWS OR HIDES THE CORNER READOUT. FPS VK: VULKAN PRESENTS PER SECOND. FRAMES: THOSE WINE HANDS "
                       "TO THE SCREEN, WITH THEIR MEAN AND LONGEST INTERVAL. CPU AND GPU: MEASURED USE OF THE TITLE. MEM: FREE "
                       "FLEXIBLE MEMORY AND LARGEST FREE BLOCK OF DIRECT MEMORY. -- MEANS NO MEASURE.",
        [S_HELP_STATS_HUD]="X: SHOWS OR HIDES MANGOHUD WITH ITS KEY (SHIFT+F12; THE PROGRAM DOES NOT GET IT). THE OVERLAY CANNOT "
                           "READ WHETHER IT IS VISIBLE: CHECK THE SCREEN. WITHOUT A VULKAN PROGRAM ON SCREEN, X TOGGLES THE "
                           "OWN READOUT.",
        [S_HELP_KEYBOARD]="X: OPENS THE KEYBOARD. IT TYPES INTO THE FOCUSED WINDOW. SQUARE DELETES, TRIANGLE SPACE, L1 AND R1 "
                          "MOVE THE CURSOR, L2 SHIFT, R2 SYMBOLS, OPTIONS ENTER, CIRCLE CLOSES.",
        [S_HELP_MOUSE]="X: TURNS THE PAD AS MOUSE ON OR OFF. WHEN OFF, THE STICK AND THE TOUCHPAD DO NOT MOVE THE POINTER, "
                       "CLICK OR SCROLL. THE PAD'S KEYS AND KEY PROFILES STAY. IT LASTS UNTIL THE APP CLOSES.",
        [S_HELP_CONTROL]="LEFT AND RIGHT CHOOSE, X SAVES. MANY GAMES PICK THE CONTROLLER ONLY WHEN THEY START: IF IT DOES NOT "
                         "CHANGE, RESTART THE GAME. 360 AND ONE CHANGE THE ID XINPUT AND DIRECTINPUT SEE. DUALSENSE ADDS AN HID "
                         "CONTROLLER FOR GAMES THAT LOOK FOR NEW ONES (SDL, STEAM); XINPUT STAYS A 360: TWO MAY SHOW.",
        [S_HELP_CONFIG]="LEFT AND RIGHT CHOOSE THE OVERLAY'S LANGUAGE, X SAVES IT IN C:\\ORBIS\\OVERLAY.INI. IT APPLIES AT ONCE.",
        [S_KB_TITLE]="KEYBOARD",[S_KB_CAPS]="CAPS",[S_KB_LOWER]="lower",
        [S_KB_HINT1]="X KEY  SQUARE DELETE  TRIANGLE SPACE  L1 R1 CURSOR",
        [S_KB_HINT2]="L2 SHIFT  R2 SYMBOLS  OPTIONS ENTER  CIRCLE CLOSE",
        [S_KEY_SHIFT]="SHIFT",[S_KEY_SPACE]="SPACE",[S_KEY_BACK]="BACKSPACE",[S_KEY_ENTER]="ENTER",
        [S_KEY_HOME]="HOME",[S_KEY_END]="END",[S_KEY_DELETE]="DEL",
        [S_STAT_FRAMES]="FRAMES",[S_STAT_INTERVAL]="INTERVAL",[S_STAT_DIRECT]="DIRECT",
        [S_T_HUD_SENT]="MANGOHUD: SHIFT+F12 SENT",[S_T_TYPE_NOT_SAVED]="COULD NOT SAVE THE TYPE",
        [S_T_CONFIG_NOT_SAVED]="COULD NOT SAVE THE SETTING",[S_T_CLOSED]="PROGRAM CLOSED",
        [S_T_REFUSED_DESKTOP]="EXIT: THE DESKTOP IS NOT CLOSED",[S_T_REFUSED_NONE]="EXIT: NO ACTIVE WINDOW",
        [S_T_REFUSED_CONSOLE]="EXIT: CONSOLE PROGRAM, NOT CLOSED",[S_T_KEPT]="COULD NOT CLOSE: SEE LOG",
        [S_T_ASKED32]="EXIT: ASKED THE 32-BIT WORLD",[S_T_UNKNOWN]="EXIT: UNKNOWN RESULT",
        [S_T_NOT_TAKEN]="EXIT: NO ANSWER (SEE LOG)",[S_T_NO_RESULT]="EXIT: NO RESULT (SEE LOG)",
        [S_T_BACK_DESKTOP]="BACK TO THE DESKTOP",[S_T_BACK_FAILED]="COULD NOT RETURN TO THE DESKTOP",
        [S_T_SEARCHING]="EXIT: LOOKING FOR THE ACTIVE PROGRAM"}};

static pthread_mutex_t lock=PTHREAD_MUTEX_INITIALIZER;
static pthread_once_t once=PTHREAD_ONCE_INIT;
static int view,entry,stats_on,mouse_on=1,pad_type,type_choice,title_alone;
static int kb_row,kb_col,kb_page,kb_shift;
static uint32_t held;       /* buttons down at the last read */
static int swallow;         /* after closing: the pad stays here until every button is up */
static uint32_t nav_held;   /* d-pad or stick directions held, for repeat */
static uint64_t nav_next_us;
static char toast[48];
static uint64_t toast_until_us,stats_next_us;
static char stats_lines[5][44];
/* W238: kernelbase's closer says whether libMangoHud.dll is loaded; the sink whether Vulkan presents */
static int mangohud_loaded,vk_presenting;
/* W261: kernelbase's closer: the desktop, the taskbar or no window is in front (Salir's refusals) */
static int desktop_front;
static uint64_t hud_release_us;  /* Shift+F12 down until then */
/* W239: Salir's request: 1 waiting for the closer, 2 taken, waiting for its result */
enum {EXIT_TAKE_US=2500000,EXIT_RESULT_US=10000000};
static int exit_pending;
static uint64_t exit_deadline_us;
/* W240: the language in use and the one chosen on the CONFIG page */
static int lang,lang_choice;
/* W261: the pointer's mode (the sink, pw_hw_cursor_mode) for the last program opened that is still open */
enum {CURSOR_GAME,CURSOR_ALWAYS,CURSOR_HIDDEN,CURSOR_MODES};
enum {PROGRAMS=8,CURSOR_SAVED=64};
static const char *const cursor_words[CURSOR_MODES]={"game","always","hidden"};
static const int cursor_names[CURSOR_MODES]={S_CURSOR_GAME,S_CURSOR_ALWAYS,S_CURSOR_HIDDEN};
static char programs[PROGRAMS][64];  /* the most recent last */
static int program_count;
static struct {char name[64];int mode,stretch;} cursor_saved[CURSOR_SAVED];  /* overlay.ini's cursor and stretch lines */
static volatile int stretch_on;      /* W266: read by the sink without the lock */
static int cursor_saved_count;
static volatile int cursor_mode;     /* read by the sink without the lock */
static int cursor_choice;
static char cursor_program[64];      /* the program cursor_mode is for, "" for none */
/* W287: GRAFICOS for the last program opened: the choice kernelbase's closer read back from the registry (-1 not
 * known yet, or a value this menu does not set), and one request at a time for the closer (pw_hw_overlay_render_poll):
 * get when the program changes, set on X */
enum {RENDERS=4,RENDER_ANSWER_US=3000000};
enum {RENDER_NONE,RENDER_GET,RENDER_SET};
static const int render_names[RENDERS]={S_RENDER_DXVK_VK,S_RENDER_DXVK_GL,S_RENDER_WINED3D_VK,S_RENDER_WINED3D_GL};
static const char *const render_words[RENDERS]={"dxvk-vulkan","dxvk-gl","wined3d-vulkan","wined3d-gl"};
static const char *const render_short[RENDERS]={"DXVK VK","DXVK GL","WD3D VK","WD3D GL"};
static char render_program[64];
static int render_saved=-1,render_choice,render_request,render_request_choice,render_taken;
static uint64_t render_deadline_us;
/* lock held (or init): a program's saved entry, added with mode game if add; -1 when there is none */
static int cursor_slot(const char *name,int add)
{
    for(int i=0;i<cursor_saved_count;i++) if(!strcasecmp(cursor_saved[i].name,name)) return i;
    if(!add || cursor_saved_count==CURSOR_SAVED) return -1;
    snprintf(cursor_saved[cursor_saved_count].name,sizeof(cursor_saved[0].name),"%s",name);
    cursor_saved[cursor_saved_count].mode=CURSOR_GAME;
    cursor_saved[cursor_saved_count].stretch=0;
    return cursor_saved_count++;
}

static const char *str(int id)
{
    const char *s=strings[lang][id];
    return s?s:strings[LANG_ES][id]?strings[LANG_ES][id]:"?";
}
/* C:\orbis\overlay.ini: "key=value" lines: lang (es, en); W261: cursor.<exe> (game, always, hidden) */
static void read_config(void)
{
    char line[160];
    FILE *file=fopen(CONFIG_FILE,"r");
    lang=LANG_ES;
    while(file && fgets(line,sizeof(line),file)) {
        char *eq;int mode=-1,slot;
        line[strcspn(line,"\r\n")]=0;
        for(int i=0;i<LANGS;i++)
            if(!strncmp(line,"lang=",5) && !strncmp(line+5,lang_words[i],strlen(lang_words[i]))) lang=i;
        if(!strncmp(line,"stretch.",8) && (eq=strrchr(line,'=')) && eq>line+8) {  /* W266 */
            *eq=0;
            if((strcmp(eq+1,"on") && strcmp(eq+1,"off")) || (slot=cursor_slot(line+8,1))<0) {
                fprintf(stderr,"PWOVERLAY config line ignored: %s=%s\n",line,eq+1);continue;
            }
            cursor_saved[slot].stretch=!strcmp(eq+1,"on");
            continue;
        }
        if(strncmp(line,"cursor.",7) || !(eq=strrchr(line,'=')) || eq==line+7) continue;
        *eq=0;
        for(int m=0;m<CURSOR_MODES;m++) if(!strcmp(eq+1,cursor_words[m])) mode=m;
        if(mode<0 || (slot=cursor_slot(line+7,1))<0) {fprintf(stderr,"PWOVERLAY config line ignored: %s=%s\n",line,eq+1);continue;}
        cursor_saved[slot].mode=mode;
    }
    if(file) fclose(file);
    lang_choice=lang;
    for(int l=0;l<LANGS;l++) for(int i=0;i<STRINGS;i++)
        if(!strings[l][i]) fprintf(stderr,"PWOVERLAY string %d missing in %s\n",i,lang_words[l]);
}
/* lock held: the language and the cursor modes (W261) */
static int write_config(int new_lang)
{
    FILE *file=fopen(CONFIG_FILE,"w");
    int ok=file && fprintf(file,"lang=%s\n",lang_words[new_lang])>0;
    for(int i=0;ok && i<cursor_saved_count;i++) {
        ok=fprintf(file,"cursor.%s=%s\n",cursor_saved[i].name,cursor_words[cursor_saved[i].mode])>0;
        if(ok && cursor_saved[i].stretch) ok=fprintf(file,"stretch.%s=on\n",cursor_saved[i].name)>0;  /* W266 */
    }
    if(file && fclose(file)) ok=0;
    return ok;
}
/* lock held */
static int save_config(int new_lang)
{
    int ok=write_config(new_lang);
    fprintf(stderr,"PWOVERLAY config lang=%s saved=%d errno=%d\n",lang_words[new_lang],ok,ok?0:errno);
    if(ok) lang=new_lang;
    return ok;
}

static void read_type(void)
{
    char text[16]={0};
    FILE *file=fopen(TYPE_FILE,"r");
    if(file) {if(!fgets(text,sizeof(text),file)) text[0]=0;fclose(file);}
    pad_type=TYPE_X360;
    for(int i=0;i<TYPES;i++) if(!strncmp(text,type_words[i],strlen(type_words[i]))) pad_type=i;
    type_choice=pad_type;
}
static void init(void)
{
    read_type();
    read_config();
    title_alone=pw_hw_overlay_exit_title(0);
    fprintf(stderr,"PWOVERLAY ready type=%s lang=%s title_alone=%d\n",type_words[pad_type],lang_words[lang],title_alone);
}
/* lock held */
static int save_type(int type)
{
    FILE *file=fopen(TYPE_FILE,"w");
    int ok=file && fprintf(file,"%s\n",type_words[type])>0;
    if(file && fclose(file)) ok=0;
    fprintf(stderr,"PWOVERLAY control type=%s saved=%d errno=%d\n",type_words[type],ok,ok?0:errno);
    if(ok) pad_type=type;
    return ok;
}
static void set_toast(const char *text)
{
    snprintf(toast,sizeof(toast),"%s",text);
    toast_until_us=sceKernelGetProcessTime()+TOAST_US;
}

/* W238: kernelbase's closer, once a second when it changes (through native/hw_pad.c). W242: 1 only when
 * MangoHud draws on the program in front (a 64-bit guest whose window Vulkan presents to) */
void pw_hw_overlay_mangohud(int loaded);
void pw_hw_overlay_mangohud(int loaded)
{
    pthread_mutex_lock(&lock);
    mangohud_loaded=loaded!=0;
    pthread_mutex_unlock(&lock);
    fprintf(stderr,"PWOVERLAY mangohud in_front=%d\n",loaded!=0);
}
/* W261: kernelbase's closer, when it changes (through native/hw_pad.c) */
void pw_hw_overlay_desktop(int in_front);
void pw_hw_overlay_desktop(int in_front)
{
    pthread_mutex_lock(&lock);
    desktop_front=in_front!=0;
    pthread_mutex_unlock(&lock);
    fprintf(stderr,"PWOVERLAY desktop in_front=%d\n",in_front!=0);
}
/* W239: kernelbase's closer, every 150 ms (through native/hw_pad.c): 1 when Salir was chosen */
int pw_hw_overlay_exit_poll(void);
int pw_hw_overlay_exit_poll(void)
{
    int take;
    pthread_mutex_lock(&lock);
    take=exit_pending==1;
    if(take) {exit_pending=2;exit_deadline_us=sceKernelGetProcessTime()+EXIT_RESULT_US;}
    pthread_mutex_unlock(&lock);
    if(take) fprintf(stderr,"PWOVERLAY exit taken by the closer\n");
    return take;
}
/* W239: what the closer did; the toast says it */
void pw_hw_overlay_exit_result(const char *result);
void pw_hw_overlay_exit_result(const char *result)
{
    static const struct {const char *result;int toast;} toasts[]={
        {"closed",S_T_CLOSED},{"refused-desktop",S_T_REFUSED_DESKTOP},{"refused-none",S_T_REFUSED_NONE},
        {"refused-console",S_T_REFUSED_CONSOLE},{"kept",S_T_KEPT},{"asked32",S_T_ASKED32}};
    int toast_text=S_T_UNKNOWN;
    for(unsigned i=0;i<sizeof(toasts)/sizeof(toasts[0]);i++) if(!strcmp(result,toasts[i].result)) toast_text=toasts[i].toast;
    fprintf(stderr,"PWOVERLAY exit result %s\n",result);
    pthread_mutex_lock(&lock);
    exit_pending=0;set_toast(str(toast_text));
    pthread_mutex_unlock(&lock);
    pw_hw_cursor_moved();
}
/* W261: the program the cursor mode is for: kernelbase's guest launch (load 1) and exit (load 0) through
 * native/hw_pad.c pw_wine_pad_profile, and a relaunched title (native/wine_hardware.c) */
/* lock held; why: start, exit */
static int cursor_apply(const char *why)
{
    const char *name=program_count?programs[program_count-1]:"";
    int slot=name[0]?cursor_slot(name,0):-1,mode=slot>=0?cursor_saved[slot].mode:CURSOR_GAME;
    int stretch=slot>=0 && cursor_saved[slot].stretch;  /* W266 */
    if(strcmp(name,render_program)) {  /* W287: GRAFICOS is read again for the new program */
        if(render_request==RENDER_SET) fprintf(stderr,"PWOVERLAY render set for %s dropped: the program changed\n",render_program);
        snprintf(render_program,sizeof(render_program),"%s",name);
        render_saved=-1;render_choice=0;render_taken=0;
        render_request=name[0]?RENDER_GET:RENDER_NONE;
    }
    if(mode==cursor_mode && stretch==stretch_on && !strcmp(name,cursor_program)) return 0;
    snprintf(cursor_program,sizeof(cursor_program),"%s",name);
    cursor_mode=mode;cursor_choice=mode;stretch_on=stretch;
    fprintf(stderr,"PWSINK cursor mode=%s stretch=%d program=%s saved=%d why=%s\n",cursor_words[mode],stretch,
            name[0]?name:"-",slot>=0,why);
    return 1;
}
void pw_hw_overlay_program(const char *exe,int load);
void pw_hw_overlay_program(const char *exe,int load)
{
    const char *base=exe;
    int changed;
    for(const char *at=exe;at && *at;at++) if(*at=='\\' || *at=='/') base=at+1;
    if(!base || !base[0]) return;
    pthread_once(&once,init);
    pthread_mutex_lock(&lock);
    for(int i=0;i<program_count;i++)
        if(!strncasecmp(programs[i],base,sizeof(programs[0])-1)) {
            memmove(programs+i,programs+i+1,(size_t)(program_count-i-1)*sizeof(programs[0]));program_count--;break;
        }
    if(load) {
        if(program_count==PROGRAMS) {memmove(programs,programs+1,(PROGRAMS-1)*sizeof(programs[0]));program_count--;}
        snprintf(programs[program_count++],sizeof(programs[0]),"%s",base);
    }
    changed=cursor_apply(load?"start":"exit");
    pthread_mutex_unlock(&lock);
    if(changed) pw_hw_cursor_moved();
}
/* the sink, whenever it would draw the pointer: 0 game (ps5drv's rule), 1 always, 2 hidden */
int pw_hw_cursor_mode(void);
int pw_hw_cursor_mode(void) {return cursor_mode;}
/* lock held: X on CURSOR saves the chosen mode for the last program opened and applies it */
static void cursor_choose(void)
{
    const char *name=program_count?programs[program_count-1]:"";
    int slot,ok=0;
    if(!name[0]) {
        set_toast(str(S_T_CURSOR_NO_PROGRAM));
        fprintf(stderr,"PWSINK cursor mode=%s not saved: no program open\n",cursor_words[cursor_choice]);
        cursor_choice=cursor_mode;return;
    }
    if((slot=cursor_slot(name,1))>=0) {cursor_saved[slot].mode=cursor_choice;ok=write_config(lang);}
    cursor_mode=cursor_choice;
    fprintf(stderr,"PWSINK cursor mode=%s program=%s saved=%d errno=%d why=menu%s\n",cursor_words[cursor_mode],name,ok,
            ok?0:errno,slot<0?" (overlay.ini has 64 programs already)":"");
    if(!ok) set_toast(str(S_T_CONFIG_NOT_SAVED));
}
/* W266: the sink, on each frame: 1 when the picture fills the whole output */
int pw_hw_overlay_stretch(void);
int pw_hw_overlay_stretch(void) {return stretch_on;}
/* lock held: X on ESTIRAR turns it on or off for the last program opened and saves it; with the desktop in front
 * (desktop_front, as Estadisticas) or no program it does nothing, only logged */
static void stretch_toggle(void)
{
    const char *name=program_count?programs[program_count-1]:"";
    int slot,ok=0;
    if(desktop_front || !name[0]) {fprintf(stderr,"PWOVERLAY stretch refused: %s\n",desktop_front?"desktop":"no program");return;}
    stretch_on=!stretch_on;
    if((slot=cursor_slot(name,1))>=0) {cursor_saved[slot].stretch=stretch_on;ok=write_config(lang);}
    fprintf(stderr,"PWSINK stretch=%d program=%s saved=%d errno=%d why=menu%s\n",stretch_on,name,ok,ok?0:errno,
            slot<0?" (overlay.ini has 64 programs already)":"");
    if(!ok) set_toast(str(S_T_CONFIG_NOT_SAVED));
}
/* W287: kernelbase's closer, every 150 ms (through native/hw_pad.c): GRAFICOS's request, "-" for none:
 * "get <exe>" or "set <choice> <exe>" */
void pw_hw_overlay_render_poll(char *reply,size_t size);
void pw_hw_overlay_render_poll(char *reply,size_t size)
{
    pthread_once(&once,init);
    pthread_mutex_lock(&lock);
    if(render_request==RENDER_NONE || render_taken) snprintf(reply,size,"-");
    else {
        if(render_request==RENDER_GET) snprintf(reply,size,"get %s",render_program);
        else snprintf(reply,size,"set %d %s",render_request_choice,render_program);
        render_taken=1;render_deadline_us=sceKernelGetProcessTime()+RENDER_ANSWER_US;
    }
    pthread_mutex_unlock(&lock);
}
/* W287: what the closer read, or wrote and read back: "get|set <choice, - for another value> <status> <exe>" */
void pw_hw_overlay_render_result(const char *result);
void pw_hw_overlay_render_result(const char *result)
{
    char what[4],choice_text[4],exe[64];
    long status;
    int choice=-1,toast_text=-1;
    if(sscanf(result,"%3s %3s %ld %63[^\n]",what,choice_text,&status,exe)!=4) {
        fprintf(stderr,"PWOVERLAY render result unreadable: %s\n",result);return;
    }
    if(choice_text[0]>='0' && choice_text[0]<'0'+RENDERS && !choice_text[1]) choice=choice_text[0]-'0';
    pthread_mutex_lock(&lock);
    if(!render_taken || strcasecmp(exe,render_program)) {
        fprintf(stderr,"PWOVERLAY render %s for %s ignored: not the request waiting (%s)\n",what,exe,
                render_program[0]?render_program:"-");
        pthread_mutex_unlock(&lock);return;
    }
    if(!strcmp(what,"set")) toast_text=!status && choice==render_request_choice?S_T_RENDER_SAVED:S_T_RENDER_FAILED;
    if(!status) render_saved=choice;
    render_choice=render_saved>=0?render_saved:0;
    render_request=RENDER_NONE;render_taken=0;
    if(toast_text>=0) set_toast(str(toast_text));
    fprintf(stderr,"PWOVERLAY render %s program=%s choice=%s status=%ld\n",what,exe,choice>=0?render_words[choice]:"other",status);
    pthread_mutex_unlock(&lock);
    pw_hw_cursor_moved();
}
/* lock held: X on GRAFICOS asks the closer to write the chosen value for the last program opened */
static void render_choose(void)
{
    if(!render_program[0]) {
        set_toast(str(S_T_RENDER_NO_PROGRAM));fprintf(stderr,"PWOVERLAY render not saved: no program open\n");return;
    }
    if(render_request==RENDER_SET) {fprintf(stderr,"PWOVERLAY render: a set is waiting already\n");return;}
    if(render_choice==render_saved) return;
    render_request=RENDER_SET;render_request_choice=render_choice;render_taken=0;
    render_deadline_us=sceKernelGetProcessTime()+RENDER_ANSWER_US;
    fprintf(stderr,"PWOVERLAY render set %s for %s requested\n",render_words[render_choice],render_program);
}
/* lock held: Estadisticas acts on MangoHud's HUD */
static int hud_mode(void) {return mangohud_loaded && vk_presenting;}

/* ---- the readout: each value is a measure, "--" when its source has none ---- */
static void sample_stats(void)
{
    unsigned vk_tenths=0,frames_tenths=0,avg_us=0,max_us=0;int vk_fresh=0,frames_fresh=0;
    struct pw_ps4_telemetry telemetry;uint32_t returned=0;
    size_t flexible=0,direct_free=0;off_t found=0;
    char lines[5][44],cpu[16],gpu[16],flex[16],direct[16];
    pw_hw_sink_stats(&vk_tenths,&vk_fresh,&frames_tenths,&avg_us,&max_us,&frames_fresh);
    memset(&telemetry,0,sizeof(telemetry));
    int telemetry_ok=!pw_ps4_telemetry_query(&telemetry,sizeof(telemetry),&returned);
    /* the SDK declares these two with their outputs as plain values (platform/ps4/pw_wine_memory.c) */
    int flex_rc=((int32_t (*)(size_t *))(uintptr_t)&sceKernelAvailableFlexibleMemorySize)(&flexible);
    int direct_rc=((int32_t (*)(off_t,off_t,size_t,off_t *,size_t *))(uintptr_t)&sceKernelAvailableDirectMemorySize)(
        0,(off_t)sceKernelGetDirectMemorySize(),0,&found,&direct_free);
    if(vk_fresh) snprintf(lines[0],sizeof(lines[0]),"FPS VK %u.%u",vk_tenths/10,vk_tenths%10);
    else snprintf(lines[0],sizeof(lines[0]),"FPS VK --");
    if(frames_fresh) {
        snprintf(lines[1],sizeof(lines[1]),"%s %u.%u/S",str(S_STAT_FRAMES),frames_tenths/10,frames_tenths%10);
        snprintf(lines[2],sizeof(lines[2]),"%s %u.%u MS MAX %u.%u",str(S_STAT_INTERVAL),avg_us/1000,avg_us/100%10,
                 max_us/1000,max_us/100%10);
    } else {
        snprintf(lines[1],sizeof(lines[1]),"%s --",str(S_STAT_FRAMES));
        snprintf(lines[2],sizeof(lines[2]),"%s --",str(S_STAT_INTERVAL));
    }
    if(telemetry_ok && (telemetry.flags&PW_CPU_VALID))
        snprintf(cpu,sizeof(cpu),"%u.%u%%",telemetry.cpu_millipercent/1000,telemetry.cpu_millipercent/100%10);
    else snprintf(cpu,sizeof(cpu),"--");
    if(telemetry_ok && (telemetry.flags&PW_GPU_VALID))
        snprintf(gpu,sizeof(gpu),"%u.%u%%",telemetry.gpu_millipercent/1000,telemetry.gpu_millipercent/100%10);
    else snprintf(gpu,sizeof(gpu),"--");
    snprintf(lines[3],sizeof(lines[3]),"CPU %s GPU %s",cpu,gpu);
    if(!flex_rc) snprintf(flex,sizeof(flex),"%zu MB",flexible>>20); else snprintf(flex,sizeof(flex),"--");
    if(!direct_rc) snprintf(direct,sizeof(direct),"%zu MB",direct_free>>20); else snprintf(direct,sizeof(direct),"--");
    snprintf(lines[4],sizeof(lines[4]),"MEM FLEX %s %s %s",flex,str(S_STAT_DIRECT),direct);
    pthread_mutex_lock(&lock);
    memcpy(stats_lines,lines,sizeof(stats_lines));
    pthread_mutex_unlock(&lock);
}

/* ---- on-screen keyboard: a US layout, as the USB keyboard's (hw_pad.c hid_to_vk) ---- */
struct key {char label[12];uint8_t vk,shift;};
static const char *const char_rows[2][3]={{"qwertyuiop","asdfghjkl@","zxcvbnm,.-"},
                                          {"-+=/\\:;'\"?","[]{}<>,.~|","!#$%&*()_^"}};
static const char *const digit_row="1234567890";
static int char_key(char c,struct key *key)
{
    static const struct {char c;uint8_t vk,shift;} punctuation[]={
        {'!','1',1},{'@','2',1},{'#','3',1},{'$','4',1},{'%','5',1},{'^','6',1},{'&','7',1},{'*','8',1},
        {'(','9',1},{')','0',1},{'-',0xbd,0},{'_',0xbd,1},{'=',0xbb,0},{'+',0xbb,1},{'[',0xdb,0},{'{',0xdb,1},
        {']',0xdd,0},{'}',0xdd,1},{'\\',0xdc,0},{'|',0xdc,1},{';',0xba,0},{':',0xba,1},{'\'',0xde,0},
        {'"',0xde,1},{',',0xbc,0},{'<',0xbc,1},{'.',0xbe,0},{'>',0xbe,1},{'/',0xbf,0},{'?',0xbf,1},
        {'`',0xc0,0},{'~',0xc0,1}};
    key->label[0]=c;key->label[1]=0;
    if(c>='a' && c<='z') {key->vk=(uint8_t)(c-'a'+'A');key->shift=(uint8_t)kb_shift;if(kb_shift) key->label[0]=(char)(c-'a'+'A');return 1;}
    if(c>='0' && c<='9') {key->vk=(uint8_t)c;key->shift=0;return 1;}
    for(unsigned i=0;i<sizeof(punctuation)/sizeof(punctuation[0]);i++)
        if(punctuation[i].c==c) {key->vk=punctuation[i].vk;key->shift=punctuation[i].shift;return 1;}
    return 0;
}
/* rows 0-3 have ten keys; row 3 of the symbols and row 4 have five wide ones (two columns each) */
static int row_wide(int row) {return row==4 || (row==3 && kb_page==1);}
static void key_at(int row,int col,struct key *key)
{
    static const struct {int label;uint8_t vk;} specials[5]={{-1,VK_TAB},{-1,VK_ESCAPE},{S_KEY_HOME,VK_HOME},
                                                              {S_KEY_END,VK_END},{S_KEY_DELETE,VK_DELETE}};
    memset(key,0,sizeof(*key));
    if(row==4) {
        static const int labels[5]={S_KEY_SHIFT,-1,S_KEY_SPACE,S_KEY_BACK,S_KEY_ENTER};
        snprintf(key->label,sizeof(key->label),"%s",col/2==1?(kb_page?"ABC":"123"):str(labels[col/2]));
        static const uint8_t vks[5]={0,0,VK_SPACE,VK_BACK,VK_RETURN};
        key->vk=vks[col/2];
        return;
    }
    if(row==3 && kb_page==1) {
        int i=col/2;
        snprintf(key->label,sizeof(key->label),"%s",specials[i].label<0?(i?"ESC":"TAB"):str(specials[i].label));
        key->vk=specials[i].vk;
        return;
    }
    char c=kb_page?char_rows[1][row][col]:row==0?digit_row[col]:char_rows[0][row-1][col];
    char_key(c,key);
}
static void type_vk(uint32_t vk,int shift)
{
    if(shift) pw_hw_pad_key(VK_SHIFT,1);
    pw_hw_pad_key(vk,1);pw_hw_pad_key(vk,0);
    if(shift) pw_hw_pad_key(VK_SHIFT,0);
}
/* lock held */
static void press_key(void)
{
    struct key key;
    key_at(kb_row,kb_col,&key);
    if(kb_row==4 && kb_col/2==0) {kb_shift=!kb_shift;return;}
    if(kb_row==4 && kb_col/2==1) {kb_page=!kb_page;if(row_wide(kb_row)) kb_col&=~1;return;}
    if(!key.vk) return;
    type_vk(key.vk,key.shift);
    if(key.shift && kb_row<4 && key.label[0]>='A' && key.label[0]<='Z') kb_shift=0;  /* one letter, as on a phone */
}

/* ---- input ---- */
enum {NAV_UP=1,NAV_DOWN=2,NAV_LEFT=4,NAV_RIGHT=8};
static uint32_t directions(const OrbisPadData *data)
{
    uint32_t b=data->buttons,dirs=0;
    int dx=(int)data->leftStick.x-128,dy=(int)data->leftStick.y-128;
    if((b&ORBIS_PAD_BUTTON_UP) || dy<-STICK_NAV) dirs|=NAV_UP;
    if((b&ORBIS_PAD_BUTTON_DOWN) || dy>STICK_NAV) dirs|=NAV_DOWN;
    if((b&ORBIS_PAD_BUTTON_LEFT) || dx<-STICK_NAV) dirs|=NAV_LEFT;
    if((b&ORBIS_PAD_BUTTON_RIGHT) || dx>STICK_NAV) dirs|=NAV_RIGHT;
    return dirs;
}
/* lock held */
static void close_overlay(void)
{
    if(view!=VIEW_CLOSED) fprintf(stderr,"PWOVERLAY close\n");
    view=VIEW_CLOSED;swallow=1;kb_shift=0;
}
/* lock held; returns 1 when Salir was chosen (done by the caller without the lock) */
static int panel_input(uint32_t pressed,uint32_t nav)
{
    if(nav&NAV_UP) entry=(entry+ENTRIES-1)%ENTRIES;
    if(nav&NAV_DOWN) entry=(entry+1)%ENTRIES;
    if(entry==ENTRY_CONTROL && (nav&NAV_LEFT)) type_choice=(type_choice+TYPES-1)%TYPES;
    if(entry==ENTRY_CONTROL && (nav&NAV_RIGHT)) type_choice=(type_choice+1)%TYPES;
    if(entry!=ENTRY_CONTROL && (nav&(NAV_UP|NAV_DOWN))) type_choice=pad_type;
    if(entry==ENTRY_CONFIG && (nav&NAV_LEFT)) lang_choice=(lang_choice+LANGS-1)%LANGS;
    if(entry==ENTRY_CONFIG && (nav&NAV_RIGHT)) lang_choice=(lang_choice+1)%LANGS;
    if(entry!=ENTRY_CONFIG && (nav&(NAV_UP|NAV_DOWN))) lang_choice=lang;
    if(entry==ENTRY_CURSOR && (nav&NAV_LEFT)) cursor_choice=(cursor_choice+CURSOR_MODES-1)%CURSOR_MODES;
    if(entry==ENTRY_CURSOR && (nav&NAV_RIGHT)) cursor_choice=(cursor_choice+1)%CURSOR_MODES;
    if(entry!=ENTRY_CURSOR && (nav&(NAV_UP|NAV_DOWN))) cursor_choice=cursor_mode;
    if(entry==ENTRY_RENDER && (nav&NAV_LEFT)) render_choice=(render_choice+RENDERS-1)%RENDERS;
    if(entry==ENTRY_RENDER && (nav&NAV_RIGHT)) render_choice=(render_choice+1)%RENDERS;
    if(entry!=ENTRY_RENDER && (nav&(NAV_UP|NAV_DOWN))) render_choice=render_saved>=0?render_saved:0;
    if(pressed&ORBIS_PAD_BUTTON_CIRCLE) {close_overlay();return 0;}
    if(!(pressed&ORBIS_PAD_BUTTON_CROSS)) return 0;
    switch(entry) {
    case ENTRY_EXIT: close_overlay();return 1;
    case ENTRY_STATS:
        if(hud_mode()) {
            /* the overlay cannot read MangoHud's state: it says only that the key went */
            if(hud_release_us) break;
            pw_hw_pad_key(VK_SHIFT,1);pw_hw_pad_key(VK_F12,1);
            hud_release_us=sceKernelGetProcessTime()+HUD_HOLD_US;
            set_toast(str(S_T_HUD_SENT));
            fprintf(stderr,"PWOVERLAY mangohud key sent: Shift+F12 held %u ms\n",HUD_HOLD_US/1000);
            break;
        }
        /* W261: not turned on over the desktop (a game still loading): silently, only logged */
        if(!stats_on && desktop_front) {fprintf(stderr,"PWOVERLAY stats refused: desktop\n");break;}
        stats_on=!stats_on;stats_next_us=0;
        fprintf(stderr,"PWOVERLAY stats=%d\n",stats_on);
        break;
    case ENTRY_KEYBOARD: view=VIEW_KEYBOARD;kb_row=1;kb_col=0;kb_page=0;kb_shift=0;fprintf(stderr,"PWOVERLAY keyboard\n");break;
    case ENTRY_MOUSE: mouse_on=!mouse_on;pw_hw_pad_set_mouse(mouse_on);break;
    case ENTRY_CURSOR: cursor_choose();break;
    case ENTRY_STRETCH: stretch_toggle();break;
    case ENTRY_RENDER: render_choose();break;
    case ENTRY_CONTROL:
        if(type_choice==pad_type) break;
        if(!save_type(type_choice)) {set_toast(str(S_T_TYPE_NOT_SAVED));type_choice=pad_type;}
        break;
    case ENTRY_CONFIG:
        if(lang_choice==lang) break;
        if(!save_config(lang_choice)) {set_toast(str(S_T_CONFIG_NOT_SAVED));lang_choice=lang;}
        break;
    }
    return 0;
}
/* lock held */
static void keyboard_input(uint32_t pressed,uint32_t nav)
{
    if(nav&NAV_UP) kb_row=(kb_row+4)%5;
    if(nav&NAV_DOWN) kb_row=(kb_row+1)%5;
    if(nav&(NAV_UP|NAV_DOWN) && row_wide(kb_row)) kb_col&=~1;
    if(row_wide(kb_row)) {
        if(nav&NAV_LEFT) kb_col=(kb_col+8)%10;
        if(nav&NAV_RIGHT) kb_col=(kb_col+2)%10;
    } else {
        if(nav&NAV_LEFT) kb_col=(kb_col+9)%10;
        if(nav&NAV_RIGHT) kb_col=(kb_col+1)%10;
    }
    if(pressed&ORBIS_PAD_BUTTON_CROSS) press_key();
    if(pressed&ORBIS_PAD_BUTTON_SQUARE) type_vk(VK_BACK,0);
    if(pressed&ORBIS_PAD_BUTTON_TRIANGLE) type_vk(VK_SPACE,0);
    if(pressed&ORBIS_PAD_BUTTON_L1) type_vk(VK_LEFT,0);
    if(pressed&ORBIS_PAD_BUTTON_R1) type_vk(VK_RIGHT,0);
    if(pressed&ORBIS_PAD_BUTTON_L2) kb_shift=!kb_shift;
    if(pressed&ORBIS_PAD_BUTTON_R2) {kb_page=!kb_page;if(row_wide(kb_row)) kb_col&=~1;}
    if(pressed&ORBIS_PAD_BUTTON_OPTIONS) type_vk(VK_RETURN,0);
    if(pressed&ORBIS_PAD_BUTTON_CIRCLE) close_overlay();
}
/* the pad thread, on each read: 1 while the overlay has the pad */
int pw_hw_overlay_pad(const OrbisPadData *data);
int pw_hw_overlay_pad(const OrbisPadData *data)
{
    pthread_once(&once,init);
    uint32_t buttons=data->connected?data->buttons:0,pressed=buttons&~held;
    uint32_t dirs=data->connected?directions(data):0,nav=0;
    uint64_t now=sceKernelGetProcessTime();
    int changed=0,exit_chosen=0,mine,want_stats,presenting=-1;
    held=buttons;
    if(view!=VIEW_CLOSED) {  /* W238: before the lock (the sink takes its lock, then this one) */
        unsigned vk_tenths,frames_tenths,avg_us,max_us;int frames_fresh;
        pw_hw_sink_stats(&vk_tenths,&presenting,&frames_tenths,&avg_us,&max_us,&frames_fresh);
    }
    pthread_mutex_lock(&lock);
    if(presenting>=0 && presenting!=vk_presenting) {vk_presenting=presenting;changed=1;}
    if(hud_release_us && now>=hud_release_us) {pw_hw_pad_key(VK_F12,0);pw_hw_pad_key(VK_SHIFT,0);hud_release_us=0;}
    if(exit_pending && now>=exit_deadline_us) {  /* W239: no closer took it, or it gave no result */
        fprintf(stderr,"PWOVERLAY exit %s\n",exit_pending==1?"not taken: no closer answered":"no result from the closer");
        set_toast(str(exit_pending==1?S_T_NOT_TAKEN:S_T_NO_RESULT));
        exit_pending=0;changed=1;
    }
    /* W287: a set waits at most RENDER_ANSWER_US, a get once taken; a get no closer took waits */
    if(render_request && (render_taken || render_request==RENDER_SET) && now>=render_deadline_us) {
        fprintf(stderr,"PWOVERLAY render %s for %s: %s\n",render_request==RENDER_SET?"set":"get",render_program,
                render_taken?"no answer from the closer":"not taken: no closer answered");
        if(render_request==RENDER_SET) set_toast(str(S_T_RENDER_NO_ANSWER));
        render_request=RENDER_NONE;render_taken=0;changed=1;
    }
    /* a direction acts when pressed, then repeats while held */
    if(dirs&~nav_held) {nav=dirs&~nav_held;nav_next_us=now+REPEAT_FIRST_US;}
    else if(dirs && now>=nav_next_us) {nav=dirs;nav_next_us=now+REPEAT_US;}
    nav_held=dirs;
    if((buttons&ORBIS_PAD_BUTTON_L3) && (buttons&ORBIS_PAD_BUTTON_R3) && (pressed&(ORBIS_PAD_BUTTON_L3|ORBIS_PAD_BUTTON_R3))) {
        if(view==VIEW_CLOSED) {
            view=VIEW_PANEL;type_choice=pad_type;lang_choice=lang;cursor_choice=cursor_mode;
            render_choice=render_saved>=0?render_saved:0;
            fprintf(stderr,"PWOVERLAY open\n");
        } else close_overlay();
        changed=1;
    } else if(view==VIEW_PANEL && (pressed || nav)) {exit_chosen=panel_input(pressed,nav);changed=1;}
    else if(view==VIEW_KEYBOARD && (pressed || nav)) {keyboard_input(pressed,nav);changed=1;}
    mine=view!=VIEW_CLOSED || swallow;
    if(swallow && view==VIEW_CLOSED && !buttons) swallow=0;
    if(toast_until_us && now>=toast_until_us) {toast_until_us=0;changed=1;}
    want_stats=stats_on && now>=stats_next_us;
    if(want_stats) stats_next_us=now+STATS_US;
    pthread_mutex_unlock(&lock);
    if(want_stats) {sample_stats();changed=1;}
    if(exit_chosen) {
        if(title_alone) {
            pthread_mutex_lock(&lock);set_toast(str(S_T_BACK_DESKTOP));pthread_mutex_unlock(&lock);
            pw_hw_cursor_moved();
            fprintf(stderr,"PWOVERLAY exit title\n");
            pw_hw_overlay_exit_title(1);  /* returns only if the system did not close the title */
            pthread_mutex_lock(&lock);set_toast(str(S_T_BACK_FAILED));pthread_mutex_unlock(&lock);
        } else {
            /* W239: kernelbase's closer takes it (pw_hw_overlay_exit_poll) and answers with the result */
            pthread_mutex_lock(&lock);
            exit_pending=1;exit_deadline_us=now+EXIT_TAKE_US;set_toast(str(S_T_SEARCHING));
            pthread_mutex_unlock(&lock);
            fprintf(stderr,"PWOVERLAY exit requested\n");
        }
        changed=1;
    }
    if(changed) pw_hw_cursor_moved();
    return mine;
}

/* ---- drawing ---- */
static const unsigned char lower_glyphs[26][7]={
    {0,0,14,1,15,17,15},{16,16,22,25,17,17,30},{0,0,14,16,16,17,14},{1,1,13,19,17,17,15},{0,0,14,17,31,16,14},
    {6,9,8,28,8,8,8},{0,15,17,17,15,1,14},{16,16,22,25,17,17,17},{4,0,12,4,4,4,14},{2,0,6,2,2,18,12},
    {16,16,18,20,24,20,18},{12,4,4,4,4,4,14},{0,0,26,21,21,17,17},{0,0,22,25,17,17,17},{0,0,14,17,17,17,14},
    {0,0,30,17,30,16,16},{0,0,13,19,15,1,1},{0,0,22,25,16,16,16},{0,0,14,16,14,1,30},{8,8,28,8,8,9,6},
    {0,0,17,17,17,19,13},{0,0,17,17,17,10,4},{0,0,17,17,21,21,10},{0,0,17,10,4,10,17},{0,0,17,17,15,1,14},
    {0,0,31,2,4,8,31}};
static const struct {char c;unsigned char rows[7];} extra_glyphs[]={
    {'!',{4,4,4,4,4,0,4}},{'"',{10,10,10,0,0,0,0}},{'#',{10,10,31,10,31,10,10}},{'$',{4,15,20,14,5,30,4}},
    {'&',{12,18,20,8,21,18,13}},{'\'',{12,4,8,0,0,0,0}},{'(',{2,4,8,8,8,4,2}},{')',{8,4,2,2,2,4,8}},
    {'*',{0,4,21,14,21,4,0}},{'+',{0,4,4,31,4,4,0}},{',',{0,0,0,0,12,4,8}},{';',{0,12,12,0,12,4,8}},
    {'<',{2,4,8,16,8,4,2}},{'=',{0,0,31,0,31,0,0}},{'>',{8,4,2,1,2,4,8}},{'?',{14,17,1,2,4,0,4}},
    {'@',{14,17,1,13,21,21,14}},{'[',{14,8,8,8,8,8,14}},{'\\',{16,8,8,4,2,2,1}},{']',{14,2,2,2,2,2,14}},
    {'^',{4,10,17,0,0,0,0}},{'_',{0,0,0,0,0,0,31}},{'`',{8,4,2,0,0,0,0}},{'{',{2,4,4,8,4,4,2}},
    {'|',{4,4,4,4,4,4,4}},{'}',{8,4,4,2,4,4,8}},{'~',{0,0,8,21,2,0,0}}};
static const unsigned char *glyph(unsigned char c)
{
    if(c>='A' && c<='Z') return hw_glyphs[c-'A'];
    if(c>='0' && c<='9') return hw_glyphs[26+c-'0'];
    if(c>='a' && c<='z') return lower_glyphs[c-'a'];
    switch(c) {case ':':return hw_glyphs[36];case '-':return hw_glyphs[37];case '.':return hw_glyphs[38];
               case '/':return hw_glyphs[39];case '%':return hw_glyphs[40];}
    for(unsigned i=0;i<sizeof(extra_glyphs)/sizeof(extra_glyphs[0]);i++) if(extra_glyphs[i].c==(char)c) return extra_glyphs[i].rows;
    return NULL;
}
struct surface {uint32_t *pixels;unsigned pitch;int width,height;};
static void fill(const struct surface *s,int x,int y,int w,int h,uint32_t color)
{
    for(int r=y<0?0:y;r<y+h && r<s->height;r++)
        for(int c=x<0?0:x;c<x+w && c<s->width;c++) s->pixels[(size_t)r*s->pitch+c]=color;
}
static void box(const struct surface *s,int x,int y,int w,int h,uint32_t color,uint32_t edge)
{
    fill(s,x,y,w,h,edge);fill(s,x+2,y+2,w-4,h-4,color);
}
static int text_width(const char *t,int scale) {return t[0]?((int)strlen(t)*6-1)*scale:0;}
static void text(const struct surface *s,int x,int y,const char *t,uint32_t color,int scale)
{
    for(;*t;t++,x+=6*scale) {
        const unsigned char *g=glyph((unsigned char)*t);
        if(!g) continue;
        for(int r=0;r<7;r++) for(int c=0;c<5;c++) if(g[r]&(1<<(4-c))) fill(s,x+c*scale,y+r*scale,scale,scale,color);
    }
}
/* words wrapped to columns characters; returns the y below the last line */
static int wrapped(const struct surface *s,int x,int y,int columns,const char *t,uint32_t color,int scale,int bottom)
{
    char line[64];
    while(*t && y+7*scale<=bottom) {
        int n=0,cut=0;
        while(t[n] && n<columns) {if(t[n]==' ') cut=n;n++;}
        if(t[n] && cut) n=cut;
        if(n>=(int)sizeof(line)) n=sizeof(line)-1;
        memcpy(line,t,(size_t)n);line[n]=0;
        text(s,x,y,line,color,scale);
        t+=n;while(*t==' ') t++;
        y+=7*scale+5;
    }
    return y;
}
enum {C_PANEL=0xff1b1e24,C_EDGE=0xff3a7bd5,C_ITEM=0xff262a33,C_SELECTED=0xff2a5fb0,C_TEXT=0xffffffff,C_DIM=0xff9aa3b0,
      C_ON=0xff5be36a,C_OFF=0xffff6a6a,C_KEY=0xff2e333d,C_KEYSEL=0xff3a7bd5,C_BLACK=0xff000000};
static const char *entry_help(int which,int alone,int hud)
{
    static const int help[ENTRIES]={S_HELP_EXIT,S_HELP_STATS,S_HELP_KEYBOARD,S_HELP_MOUSE,S_HELP_CURSOR,S_HELP_STRETCH,
                                    S_HELP_RENDER,S_HELP_CONTROL,S_HELP_CONFIG};
    if(which==ENTRY_STATS && hud) return str(S_HELP_STATS_HUD);
    if(which==ENTRY_EXIT && alone) return str(S_HELP_EXIT_ALONE);
    return str(help[which]);
}
/* an option list (CONTROL, CONFIG): the chosen one marked, the saved one labelled; returns the y below */
static int draw_options(const struct surface *s,int x0,int w,int y,const char *const *names,int count,int choice,int saved)
{
    for(int i=0;i<count;i++,y+=30) {
        char label[24];
        snprintf(label,sizeof(label),"%s %s",i==choice?">":" ",names[i]);
        if(i==choice) fill(s,x0+12,y-6,w-24,26,C_ITEM);
        text(s,x0+24,y,label,i==choice?C_TEXT:C_DIM,2);
        if(i==saved) text(s,x0+w-24-text_width(str(S_SAVED),2),y,str(S_SAVED),C_ON,2);
    }
    return y+6;
}
/* W240: flush with the output's top, right and bottom edges; an edge only on the left */
static void draw_panel(const struct surface *s,int which,int stats,int mouse,int type,int choice,int alone,int hud)
{
    static const int names[ENTRIES]={S_ENTRY_EXIT,S_ENTRY_STATS,S_ENTRY_KEYBOARD,S_ENTRY_MOUSE,S_ENTRY_CURSOR,S_ENTRY_STRETCH,
                                     S_ENTRY_RENDER,S_ENTRY_CONTROL,S_ENTRY_CONFIG};
    /* W266: 36 (was 40) so eight entries took what seven did; W287: 32 for nine, with GRAFICOS's options and help */
    enum {W=460,ITEM_H=32,ITEM_GAP=6,EDGE=2};
    int x0=s->width-W,y0=0,h=s->height,y;
    fill(s,x0,y0,EDGE,h,C_EDGE);fill(s,x0+EDGE,y0,W-EDGE,h,C_PANEL);
    hw_text(s->pixels,(int)s->pitch,s->height,x0+16,y0+14,"ORBISDESK",C_DIM,2);
    text(s,x0+W-16-text_width("L3+R3",2),y0+14,"L3+R3",C_DIM,2);
    y=y0+44;
    for(int i=0;i<ENTRIES;i++,y+=ITEM_H+ITEM_GAP) {
        char state[16]="";uint32_t state_color=C_DIM;
        fill(s,x0+12,y,W-24,ITEM_H,i==which?C_SELECTED:C_ITEM);
        text(s,x0+24,y+(ITEM_H-21)/2,str(names[i]),C_TEXT,3);
        if(i==ENTRY_STATS && hud) {snprintf(state,sizeof(state),"MANGOHUD");state_color=C_ON;}
        else if(i==ENTRY_STATS) {snprintf(state,sizeof(state),"%s",str(stats?S_OWN_ON:S_OWN_OFF));state_color=stats?C_ON:C_DIM;}
        if(i==ENTRY_MOUSE) {snprintf(state,sizeof(state),"%s",str(mouse?S_ON:S_OFF));state_color=mouse?C_ON:C_OFF;}
        if(i==ENTRY_CURSOR) {
            snprintf(state,sizeof(state),"%s",str(cursor_names[cursor_mode]));state_color=cursor_mode==CURSOR_HIDDEN?C_OFF:C_DIM;
        }
        if(i==ENTRY_STRETCH) {snprintf(state,sizeof(state),"%s",str(stretch_on?S_ON:S_OFF));state_color=stretch_on?C_ON:C_DIM;}
        if(i==ENTRY_RENDER) snprintf(state,sizeof(state),"%s",render_saved>=0?render_short[render_saved]:"--");
        if(i==ENTRY_CONTROL) snprintf(state,sizeof(state),"%s",type_names[type]);
        if(i==ENTRY_CONFIG) snprintf(state,sizeof(state),"%s",lang_names[lang]);
        text(s,x0+W-24-text_width(state,2),y+(ITEM_H-14)/2,state,i==which?C_TEXT:state_color,2);
    }
    y+=6;
    if(which==ENTRY_CONTROL) y=draw_options(s,x0,W,y,type_names,TYPES,choice,type);
    if(which==ENTRY_CONFIG) y=draw_options(s,x0,W,y,lang_names,LANGS,lang_choice,lang);
    if(which==ENTRY_CURSOR) {  /* W261: the program it is saved for, then the modes */
        const char *modes[CURSOR_MODES];char line[80];
        int slot=program_count?cursor_slot(programs[program_count-1],0):-1;
        for(int m=0;m<CURSOR_MODES;m++) modes[m]=str(cursor_names[m]);
        snprintf(line,sizeof(line),"%s %s",str(S_CURSOR_PROGRAM),program_count?programs[program_count-1]:"--");
        text(s,x0+24,y,line,C_DIM,2);
        y=draw_options(s,x0,W,y+30,modes,CURSOR_MODES,cursor_choice,slot>=0?cursor_saved[slot].mode:-1);
    }
    if(which==ENTRY_RENDER) {  /* W287: the program, then the choices; the closer's reading marked */
        const char *renders[RENDERS];char line[80];
        for(int r=0;r<RENDERS;r++) renders[r]=str(render_names[r]);
        snprintf(line,sizeof(line),"%s %s",str(S_CURSOR_PROGRAM),render_program[0]?render_program:"--");
        text(s,x0+24,y,line,C_DIM,2);
        y=draw_options(s,x0,W,y+30,renders,RENDERS,render_choice,render_saved);
    }
    wrapped(s,x0+20,y,(W-40)/12,entry_help(which,alone,hud),C_DIM,2,y0+h-44);
    text(s,x0+20,y0+h-32,str(S_FOOTER),C_DIM,2);
}
/* lock held: key_at reads the page and shift */
static void draw_keyboard(const struct surface *s)
{
    enum {KEY_W=92,KEY_H=44,GAP=6,TOP_PAD=40,BOTTOM_PAD=60};
    int total_w=10*KEY_W+9*GAP,x0=(s->width-total_w)/2,area_h=TOP_PAD+5*KEY_H+4*GAP+BOTTOM_PAD,y0=s->height-area_h-10;
    int row=kb_row,col=kb_col;
    box(s,x0-20,y0,total_w+40,area_h,C_PANEL,C_EDGE);
    text(s,x0,y0+14,str(S_KB_TITLE),C_DIM,2);
    text(s,x0+total_w-text_width(str(kb_shift?S_KB_CAPS:S_KB_LOWER),2),y0+14,str(kb_shift?S_KB_CAPS:S_KB_LOWER),
         kb_shift?C_ON:C_DIM,2);
    for(int r=0;r<5;r++) {
        int wide=row_wide(r),keys=wide?5:10;
        for(int k=0;k<keys;k++) {
            struct key key;int c=wide?k*2:k;
            int kx=x0+c*(KEY_W+GAP),ky=y0+TOP_PAD+r*(KEY_H+GAP),kw=wide?2*KEY_W+GAP:KEY_W;
            int selected=r==row && (wide?col/2==k:col==k);
            key_at(r,c,&key);
            fill(s,kx,ky,kw,KEY_H,selected?C_KEYSEL:C_KEY);
            int scale=strlen(key.label)>1?2:3;
            text(s,kx+(kw-text_width(key.label,scale))/2,ky+(KEY_H-7*scale)/2,key.label,C_TEXT,scale);
        }
    }
    int hy=y0+TOP_PAD+5*KEY_H+4*GAP+10;
    text(s,x0,hy,str(S_KB_HINT1),C_DIM,2);
    text(s,x0,hy+22,str(S_KB_HINT2),C_DIM,2);
}
/* W240: where MangoHud puts its HUD with this prefix's MangoHud.conf (position=top-left, no offsets):
 * a 10 px margin from the corner and 5 px of padding inside (overlay.cpp, margin and WindowPadding) */
static void draw_stats(const struct surface *s,char lines[5][44])
{
    enum {MARGIN=10,PADDING=5,LINE=22,GLYPH=14};
    int widest=0;
    for(int i=0;i<5;i++) if(text_width(lines[i],2)>widest) widest=text_width(lines[i],2);
    fill(s,MARGIN,MARGIN,widest+2*PADDING,4*LINE+GLYPH+2*PADDING,C_BLACK);
    for(int i=0;i<5;i++) text(s,MARGIN+PADDING,MARGIN+PADDING+i*LINE,lines[i],0xffffff00u,2);
}
/* the sink, on each output frame before the flip (its lock held) */
void pw_hw_overlay_draw(uint32_t *pixels,unsigned pitch,unsigned width,unsigned height);
void pw_hw_overlay_draw(uint32_t *pixels,unsigned pitch,unsigned width,unsigned height)
{
    struct surface s={pixels,pitch,(int)width,(int)height};
    char lines[5][44],message[48];
    pthread_mutex_lock(&lock);
    int shown_view=view,stats=stats_on,toast_on=toast_until_us!=0;
    if(stats) memcpy(lines,stats_lines,sizeof(lines));
    if(toast_on) snprintf(message,sizeof(message),"%s",toast);
    if(stats && lines[0][0]) draw_stats(&s,lines);
    if(shown_view==VIEW_PANEL) draw_panel(&s,entry,stats_on,mouse_on,pad_type,type_choice,title_alone,hud_mode());
    if(shown_view==VIEW_KEYBOARD) draw_keyboard(&s);
    pthread_mutex_unlock(&lock);
    if(toast_on) {  /* W240: at the bottom, away from the readout's and MangoHud's corner */
        int w=text_width(message,3)+40,x=((int)width-w)/2,y=(int)height-24-46;
        fill(&s,x,y,w,46,C_EDGE);fill(&s,x+2,y+2,w-4,42,C_PANEL);
        text(&s,x+20,y+12,message,C_TEXT,3);
    }
}
