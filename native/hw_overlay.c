/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* W236: the control overlay. L3 and R3 pressed together open a panel over the output while the
 * program keeps running; until it closes, the pad drives the panel only (native/hw_pad.c shows
 * programs and its own emulation a neutral pad). Entries:
 *   SALIR         the program in front closes and the desktop comes back: a request that explorer's
 *                 kernelbase closer takes (tools/build-guest-hw.py; W239, no key since W238 died on
 *                 F24) and answers with the result, or return_to_desktop in a relaunched title
 *                 (native/wine_hardware.c)
 *   ESTADISTICAS  a corner readout with measured values only; "--" where there is no measure.
 *                 W2xx: laid out as MangoHud's HUD (legacy layout, its default colours), with the rows,
 *                 place and font_size of the prefix's MangoHud.conf
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
 *   LIMITE FPS    per program: off, 30, 60 or auto, saved in C:\orbis\overlay.ini ("fpslimit.<exe>=off", "60",
 *                 "auto"; 30 without a line, the default since 04.18); the sink holds that program's Vulkan presents
 *                 to the cap (platform/ps4/pw_wine_sink_ps4.c, pw_fps_limit.h, docs/FPS_LIMIT.md)
 *   GENERAR CUADROS  per program, on or off ("framegen.<exe>=on"; off without a line): at a cap of 30 the sink
 *                 shows a frame generated between each two of the game's (docs/FRAME_GENERATION.md, stage 5);
 *                 MangoHud's rectangle (pw_hw_overlay_hud_rect) is left out of the generation
 *   CONTROL       04.26: per program, a generic HID gamepad, Xbox 360, Xbox One or DualSense ("pad.<exe>=generic",
 *                 "x360", "xone" or "dualsense" in C:\orbis\overlay.ini; generic without a line, or Xbox 360 while
 *                 C:\orbis\padhid-xinput.txt exists). The type of the last program opened (with none, that default)
 *                 goes to C:\orbis\padtype.txt, which winebus (native/winebus_orbis.c: an unplug and a plug on a
 *                 change, W236), xinput and dinput (tools/build-xinput-hw.py, build-dinput-hw.py) read
 *   CONFIG        W240: the overlay's language, Spanish or English, saved in C:\orbis\overlay.ini
 *                 ("lang=es" or "lang=en"); every text it shows comes from the strings table below
 * 04.31: laid out as a quick access menu (docs/OVERLAY_MENU.md): a rail of section icons at the left (PERFORMANCE,
 * GRAPHICS, CONTROLS, SYSTEM, and EXIT at its foot) and the section's items at the right, changed in place (toggles,
 * sliders of choices, actions); the selected item's help and the buttons sit in a band at the bottom, as on the
 * native Steam client's pages (native/steam/steam_ui.c). The entries above, their keys in overlay.ini and their
 * effects are the same.
 * 04.36: the menu always opens on PERFORMANCE (it reopened at the last section, which was mostly EXIT). CONTROLS gains
 *   MAPEO DE TECLAS / KEY MAPPING: a screen with the DualShock 4 drawn and every button and stick direction listed, each
 *   given a keyboard key from an on-screen key picker, saved per program as the pad's key profile
 *   (C:\orbis\padmaps\<exe>.ini, native/hw_pad.c, W181/W213) and applied at once; DEFAULT takes the profile OrbisDesk
 *   ships for the program (C:\orbis\padmaps-default, tools/build-wine-hardware.py) or none (docs/OVERLAY_MENU.md).
 * The pad thread calls pw_hw_overlay_pad on each read; the sink calls pw_hw_overlay_draw on each
 * output frame before the flip (platform/ps4/pw_wine_sink_ps4.c). Drawn opaque: reading back the
 * output buffer, which the GPU writes, would be slow. The readout's background is a dither instead
 * (hud_background): part of the pixels take the background colour, the rest keep the picture. */
#include <dirent.h>
#include <errno.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <sys/types.h>
#include <sys/stat.h>
#include "pw_trace.h"  /* alpha 2: navigation and timing lines, traces only */
#include <time.h>
#include <unistd.h>
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
extern unsigned int pw_wine_vk_presents(void);  /* 04.26: native/wine_vk_runtime.c */
extern void pw_hw_pad_profile_reload(const char *exe);  /* 04.36: native/hw_pad.c */

#define TYPE_FILE "/data/wine-prefix/drive_c/orbis/padtype.txt"
#define CONFIG_FILE "/data/wine-prefix/drive_c/orbis/overlay.ini"
/* W213: while it exists, a program with no CONTROL choice gets Xbox 360 instead of the generic gamepad (04.26) */
#define XINPUT_SWITCH "/data/wine-prefix/drive_c/orbis/padhid-xinput.txt"
/* 04.31: the items, grouped in sections (section_items below); EXIT is the rail's last section, drawn at its foot */
enum {IT_FPS,IT_FRAMEGEN,IT_STATS,IT_RENDER,IT_STRETCH,IT_CONTROL,IT_KEYMAP,IT_MOUSE,IT_CURSOR,IT_KEYBOARD,IT_LANG,IT_EXIT,
      ITEMS};
enum {SEC_PERF,SEC_GRAPHICS,SEC_CONTROLS,SEC_SYSTEM,SEC_EXIT,SECTIONS};
enum {FOCUS_RAIL,FOCUS_ITEMS};
enum {VIEW_CLOSED,VIEW_PANEL,VIEW_KEYBOARD,VIEW_MAPPER};  /* 04.36: VIEW_MAPPER, KEY MAPPING's screen */
enum {TYPE_GENERIC,TYPE_X360,TYPE_XONE,TYPE_DUALSENSE,TYPES};  /* 04.26: generic first */
enum {VK_BACK=0x08,VK_TAB=0x09,VK_RETURN=0x0d,VK_SHIFT=0x10,VK_ESCAPE=0x1b,VK_SPACE=0x20,VK_END=0x23,VK_HOME=0x24,
      VK_LEFT=0x25,VK_RIGHT=0x27,VK_DELETE=0x2e,VK_F12=0x7b,VK_F24=0x87};
enum {REPEAT_FIRST_US=350000,REPEAT_US=110000,STICK_NAV=80,TOAST_US=3000000,STATS_US=1000000,HUD_CONF_US=5000000};
/* W238: MangoHud reads its key at a present, at most every 100 ms (keybinds.cpp): F12 is held longer.
 * 04.26 (run-0234: SeaMonkey's page did not change, nothing presented, and the key went unread): held at least that
 * long and until a Vulkan present after it, at most HUD_WAIT_US. MangoHud toggles again after 400 ms held, and the
 * first present after an idle stretch reads the key, so the key goes up at the first present past HUD_HOLD_US. */
enum {HUD_HOLD_US=250000,HUD_WAIT_US=3000000};
static const char *const type_names[TYPES]={NULL,"XBOX 360","XBOX ONE","DUALSENSE"};  /* generic: S_PAD_GENERIC */
static const char *const type_words[TYPES]={"generic","x360","xone","dualsense"};

/* W240: every text the overlay shows, in Spanish and in English, as UTF-8. W294: with the accents and the N with
 * tilde Spanish needs (text() draws them: a base letter and a mark, marked_glyphs below). */
enum {LANG_ES,LANG_EN,LANGS};
static const char *const lang_words[LANGS]={"es","en"};
static const char *const lang_names[LANGS]={"ESPAÑOL","ENGLISH"};
enum {S_ENTRY_EXIT,S_ENTRY_STATS,S_ENTRY_KEYBOARD,S_ENTRY_MOUSE,S_ENTRY_CONTROL,
      S_SEC_PERF,S_SEC_GRAPHICS,S_SEC_CONTROLS,S_SEC_SYSTEM,S_ITEM_LANG,S_ITEM_EXIT,S_ITEM_EXIT_ALONE,
      S_FOOT_RAIL,S_FOOT_CHOICE,S_FOOT_SAVE,S_FOOT_TOGGLE,S_FOOT_HUD,S_FOOT_OPEN,S_FOOT_EXIT,S_FOOT_BACK,
      S_RENDER_32_ONLY,S_T_RENDER_64,
      S_ENTRY_CURSOR,S_CURSOR_GAME,S_CURSOR_ALWAYS,S_CURSOR_HIDDEN,S_CURSOR_PROGRAM,S_HELP_CURSOR,S_T_CURSOR_NO_PROGRAM,
      S_ENTRY_STRETCH,S_HELP_STRETCH,
      S_ENTRY_RENDER,S_HELP_RENDER,S_RENDER_DXVK_VK,S_RENDER_DXVK_GL,S_RENDER_WINED3D_VK,S_RENDER_WINED3D_GL,
      S_T_RENDER_SAVED,S_T_RENDER_FAILED,S_T_RENDER_NO_ANSWER,S_T_RENDER_NO_PROGRAM,
      S_ENTRY_FPS,S_FPS_AUTO,S_HELP_FPS,S_T_FPS_NO_PROGRAM,S_ENTRY_FRAMEGEN,S_HELP_FRAMEGEN,S_T_FRAMEGEN_NO_PROGRAM,
      S_PAD_GENERIC,S_T_PAD_NO_PROGRAM,
      S_ON,S_OFF,
      S_HELP_EXIT,S_HELP_EXIT_ALONE,S_HELP_STATS,S_HELP_STATS_HUD,S_HELP_KEYBOARD,S_HELP_MOUSE,S_HELP_CONTROL,S_HELP_CONFIG,
      S_KB_TITLE,S_KB_CAPS,S_KB_LOWER,S_KB_HINT1,S_KB_HINT2,
      S_KEY_SHIFT,S_KEY_SPACE,S_KEY_BACK,S_KEY_ENTER,S_KEY_HOME,S_KEY_END,S_KEY_DELETE,
      S_STAT_FRAMES,S_STAT_INTERVAL,S_STAT_DIRECT,
      S_T_HUD_SENT,S_T_TYPE_NOT_SAVED,S_T_CONFIG_NOT_SAVED,S_T_CLOSED,S_T_REFUSED_DESKTOP,S_T_REFUSED_NONE,
      S_T_REFUSED_CONSOLE,S_T_KEPT,S_T_ASKED32,S_T_UNKNOWN,S_T_NOT_TAKEN,S_T_NO_RESULT,S_T_BACK_DESKTOP,
      S_T_BACK_FAILED,S_T_SEARCHING,
      /* 04.36: KEY MAPPING */
      S_ITEM_KEYMAP,S_HELP_KEYMAP,S_KM_HELP,S_KM_PICK_HELP,S_KM_FOOT,S_KM_FOOT_DIRTY,S_KM_PICK_TITLE,S_KM_PICK_FOOT,
      S_KM_MOUSE,S_KM_SYSTEM,S_KM_AUTO,S_KEY_UP,S_KEY_DOWN,S_KEY_LEFT,S_KEY_RIGHT,S_KEY_PGUP,S_KEY_PGDN,
      S_KEY_MOUSE_LEFT,S_KEY_MOUSE_RIGHT,S_KEY_MOUSE_MIDDLE,S_KEY_WHEEL_UP,S_KEY_WHEEL_DOWN,
      S_T_KM_SAVED,S_T_KM_NOT_SAVED,S_T_KM_NO_PROGRAM,S_T_KM_SHARE,S_T_KM_DEFAULT,S_T_KM_NO_DEFAULT,STRINGS};
static const char *const strings[LANGS][STRINGS]={
    [LANG_ES]={
        [S_ENTRY_EXIT]="SALIR",[S_ENTRY_STATS]="ESTADÍSTICAS",[S_ENTRY_KEYBOARD]="TECLADO",[S_ENTRY_MOUSE]="MOUSE",
        [S_ENTRY_CONTROL]="CONTROL",
        [S_SEC_PERF]="RENDIMIENTO",[S_SEC_GRAPHICS]="GRÁFICOS",[S_SEC_CONTROLS]="CONTROLES",[S_SEC_SYSTEM]="SISTEMA",
        [S_ITEM_LANG]="IDIOMA",[S_ITEM_EXIT]="CERRAR EL PROGRAMA",[S_ITEM_EXIT_ALONE]="VOLVER AL ESCRITORIO",
        [S_FOOT_RAIL]="X: ENTRAR     O: CERRAR",[S_FOOT_CHOICE]="< >: ELEGIR     O: VOLVER",
        [S_FOOT_SAVE]="< >: ELEGIR     X: GUARDAR     O: VOLVER",[S_FOOT_TOGGLE]="X: SÍ / NO     O: VOLVER",
        [S_FOOT_HUD]="X: MOSTRAR U OCULTAR     O: VOLVER",[S_FOOT_OPEN]="X: ABRIR     O: VOLVER",
        [S_FOOT_EXIT]="X: CERRARLO     O: VOLVER",[S_FOOT_BACK]="O: VOLVER",
        [S_RENDER_32_ONLY]="SOLO 32 BITS",[S_T_RENDER_64]="RENDERIZADO: SOLO PROGRAMAS DE 32 BITS",
        [S_ENTRY_CURSOR]="CURSOR",[S_CURSOR_GAME]="JUEGO",[S_CURSOR_ALWAYS]="SIEMPRE",[S_CURSOR_HIDDEN]="OCULTO",
        [S_CURSOR_PROGRAM]="PROGRAMA:",[S_T_CURSOR_NO_PROGRAM]="CURSOR: NINGÚN PROGRAMA ABIERTO",
        [S_ENTRY_STRETCH]="ESTIRAR",
        [S_ENTRY_RENDER]="RENDERIZADO",
        [S_HELP_RENDER]="D3D8/9 CON DXVK O CON EL WINED3D DE WINE, SOBRE VULKAN U OPENGL; DESPUÉS DIRECTDRAW Y D3D7. "
                        "SE GUARDA EN EL REGISTRO DE WINE Y VALE DESDE EL PRÓXIMO ARRANQUE. SOLO PROGRAMAS DE 32 BITS.",
        [S_RENDER_DXVK_VK]="DXVK + VULKAN",[S_RENDER_DXVK_GL]="DXVK + OPENGL",[S_RENDER_WINED3D_VK]="WINED3D + VULKAN",
        [S_RENDER_WINED3D_GL]="WINED3D + OPENGL",
        [S_T_RENDER_SAVED]="RENDERIZADO: AL PRÓXIMO ARRANQUE",[S_T_RENDER_FAILED]="RENDERIZADO: NO SE GUARDÓ",
        [S_T_RENDER_NO_ANSWER]="RENDERIZADO: SIN RESPUESTA",[S_T_RENDER_NO_PROGRAM]="RENDERIZADO: NINGÚN PROGRAMA",
        [S_ENTRY_FPS]="LÍMITE FPS",[S_FPS_AUTO]="AUTO",[S_T_FPS_NO_PROGRAM]="LÍMITE FPS: NINGÚN PROGRAMA ABIERTO",
        [S_HELP_FPS]="LOS CUADROS VULKAN DEL PROGRAMA SALEN PAREJOS A 30 O 60. AUTO: 60, O 30 SI BAJA DE 52. 30 HASTA QUE "
                     "SE ELIJA. CON EL LÍMITE DE MANGOHUD TAMBIÉN, GANA EL MÁS BAJO.",
        [S_ENTRY_FRAMEGEN]="GENERAR CUADROS",[S_T_FRAMEGEN_NO_PROGRAM]="GENERAR CUADROS: NINGÚN PROGRAMA",
        [S_PAD_GENERIC]="GENÉRICO",[S_T_PAD_NO_PROGRAM]="CONTROL: NINGÚN PROGRAMA ABIERTO",
        [S_HELP_FRAMEGEN]="CON LÍMITE FPS EN 30 MUESTRA 60: UN CUADRO INTERPOLADO ENTRE CADA DOS DEL JUEGO. SUMA UN CUADRO "
                          "DE RETRASO. SI LA GPU NO ALCANZA, SOLO LOS REALES. EXPERIMENTAL.",
        [S_HELP_STRETCH]="LA IMAGEN LLENA TODA LA PANTALLA, SIN FRANJAS NEGRAS, O MANTIENE SU PROPORCIÓN. NO CAMBIA CON EL "
                         "ESCRITORIO AL FRENTE.",
        [S_HELP_CURSOR]="JUEGO: LA FLECHA SE VE, SALVO EN PANTALLA COMPLETA SI EL JUEGO NO PONE CURSOR. SIEMPRE: SE VE "
                        "SIEMPRE. OCULTO: NO MIENTRAS EL PROGRAMA SIGA ABIERTO. EL MANDO LA MUEVE IGUAL.",
        [S_ON]="SÍ",[S_OFF]="NO",
        [S_HELP_EXIT]="CIERRA EL PROGRAMA DE LA VENTANA ACTIVA, COMO SI TERMINARA DE GOLPE, Y QUEDA EL ESCRITORIO. "
                      "NO PREGUNTA NI GUARDA: LO NO GUARDADO SE PIERDE.",
        [S_HELP_EXIT_ALONE]="CIERRA ESTE PROGRAMA, QUE CORRE SOLO, Y LA APP SE REINICIA EN EL ESCRITORIO. NO PREGUNTA NI GUARDA.",
        [S_HELP_STATS]="UNA LECTURA EN LA ESQUINA, COMO LA DE MANGOHUD: GPU, CPU, RAM, FPS Y TIEMPOS DE CUADRO DEL TÍTULO. "
                       "-- ES SIN MEDIDA. NO SE ENCIENDE SOBRE EL ESCRITORIO.",
        [S_HELP_STATS_HUD]="MANGOHUD SE MUESTRA U OCULTA CON SU TECLA, SHIFT+F12; EL PROGRAMA NO LA RECIBE. EL OVERLAY NO VE SI "
                           "QUEDÓ VISIBLE: MIRALO EN PANTALLA. LO QUE SE EDITA EN MANGOJUICE VALE PARA TODO HUD.",
        [S_HELP_KEYBOARD]="UN TECLADO EN PANTALLA PARA LA VENTANA CON EL FOCO. CUADRADO BORRA, TRIÁNGULO ESPACIO, L1 R1 "
                          "MUEVEN, L2 MAYÚSCULA, R2 SÍMBOLOS, OPTIONS ENTER, CÍRCULO CIERRA.",
        [S_HELP_MOUSE]="EL STICK Y EL TOUCHPAD COMO PUNTERO, CLIC Y RUEDA. APAGADO, SIGUEN LAS TECLAS Y LOS PERFILES DEL "
                       "MANDO. VALE HASTA CERRAR LA APP.",
        [S_HELP_CONTROL]="GENÉRICO: SIGUEN TECLAS Y PERFILES. XBOX 360 Y ONE: UN MANDO XBOX PARA XINPUT. DUALSENSE: UN "
                         "DUALSENSE CRUDO. EL ARRANQUE DEL PROGRAMA LO ESPERA; SI NO CAMBIA, REINICIÁ EL JUEGO.",
        [S_HELP_CONFIG]="EL IDIOMA DEL OVERLAY, GUARDADO EN C:\\ORBIS\\OVERLAY.INI. SE APLICA EN EL MOMENTO.",
        [S_KB_TITLE]="TECLADO",[S_KB_CAPS]="MAYÚS",[S_KB_LOWER]="minús",
        [S_KB_HINT1]="X TECLA  CUADRADO BORRA  TRIÁNGULO ESPACIO  L1 R1 CURSOR",
        [S_KB_HINT2]="L2 MAYÚSCULA  R2 SÍMBOLOS  OPTIONS ENTER  CÍRCULO CIERRA",
        [S_KEY_SHIFT]="MAYÚS",[S_KEY_SPACE]="ESPACIO",[S_KEY_BACK]="BORRAR",[S_KEY_ENTER]="ENTER",
        [S_KEY_HOME]="INICIO",[S_KEY_END]="FIN",[S_KEY_DELETE]="SUPR",
        [S_STAT_FRAMES]="CUADROS",[S_STAT_INTERVAL]="INTERVALO",[S_STAT_DIRECT]="DIRECTA",
        [S_T_HUD_SENT]="MANGOHUD: SHIFT+F12 ENVIADO",[S_T_TYPE_NOT_SAVED]="NO SE PUDO GUARDAR EL TIPO",
        [S_T_CONFIG_NOT_SAVED]="NO SE PUDO GUARDAR LA CONFIG",[S_T_CLOSED]="PROGRAMA CERRADO",
        [S_T_REFUSED_DESKTOP]="SALIENDO...",[S_T_REFUSED_NONE]="SALIR: NO HAY VENTANA ACTIVA",
        [S_T_REFUSED_CONSOLE]="SALIR: PROGRAMA DE CONSOLA, NO SE CIERRA",[S_T_KEPT]="NO SE PUDO CERRAR",
        [S_T_ASKED32]="SALIENDO...",[S_T_UNKNOWN]="SALIR: RESULTADO DESCONOCIDO",
        [S_T_NOT_TAKEN]="SALIR: SIN RESPUESTA",[S_T_NO_RESULT]="SALIR: SIN RESULTADO",
        [S_T_BACK_DESKTOP]="VOLVIENDO AL ESCRITORIO",[S_T_BACK_FAILED]="NO SE PUDO VOLVER AL ESCRITORIO",
        [S_T_SEARCHING]="SALIR: BUSCANDO EL PROGRAMA ACTIVO",
        [S_ITEM_KEYMAP]="MAPEO DE TECLAS",
        [S_HELP_KEYMAP]="UNA TECLA O UN CLIC DEL MOUSE PARA CADA BOTÓN Y DIRECCIÓN DE STICK DEL MANDO, POR PROGRAMA, PARA "
                        "JUEGOS QUE SOLO LEEN TECLADO Y MOUSE. SE GUARDA EN C:\\ORBIS\\PADMAPS.",
        [S_KM_HELP]="CON UNA TECLA ASIGNADA, LOS BOTONES VACÍOS NO HACEN NADA Y EL STICK IZQUIERDO MANDA LAS FLECHAS (AUTO). "
                    "UN PROGRAMA QUE LEE EL MANDO POR XINPUT RECIBE EL MANDO, NO LAS TECLAS.",
        [S_KM_PICK_HELP]="LA TECLA O EL BOTÓN DEL MOUSE QUEDA APRETADO MIENTRAS SE MANTIENE EL BOTÓN DEL MANDO; EL CLIC VA "
                         "DONDE ESTÁ LA FLECHA. LA RUEDA DA UN PASO POR PULSACIÓN. OPTIONS GUARDA.",
        [S_KM_FOOT]="X: ASIGNAR    CUADRADO: QUITAR    TRIÁNGULO: PREDETERMINADO    O: VOLVER",
        [S_KM_FOOT_DIRTY]="X: ASIGNAR    CUADRADO: QUITAR    TRIÁNGULO: PREDETERMINADO    OPTIONS: GUARDAR    O: CANCELAR",
        [S_KM_PICK_TITLE]="TECLA PARA",[S_KM_PICK_FOOT]="X: ASIGNAR    CUADRADO: SIN TECLA    O: CANCELAR",
        [S_KM_MOUSE]="PUNTERO",[S_KM_SYSTEM]="SISTEMA",[S_KM_AUTO]="AUTO",
        [S_KEY_UP]="ARRIBA",[S_KEY_DOWN]="ABAJO",[S_KEY_LEFT]="IZQUIERDA",[S_KEY_RIGHT]="DERECHA",[S_KEY_PGUP]="REPÁG",
        [S_KEY_PGDN]="AVPÁG",[S_KEY_MOUSE_LEFT]="CLIC IZQUIERDO",[S_KEY_MOUSE_RIGHT]="CLIC DERECHO",
        [S_KEY_MOUSE_MIDDLE]="CLIC CENTRAL",[S_KEY_WHEEL_UP]="RUEDA ARRIBA",[S_KEY_WHEEL_DOWN]="RUEDA ABAJO",
        [S_T_KM_SAVED]="MAPEO DE TECLAS GUARDADO",[S_T_KM_NOT_SAVED]="MAPEO DE TECLAS: NO SE GUARDÓ",
        [S_T_KM_NO_PROGRAM]="MAPEO: NINGÚN PROGRAMA ABIERTO",[S_T_KM_SHARE]="SHARE ES DEL SISTEMA",
        [S_T_KM_DEFAULT]="PREDETERMINADO: OPTIONS LO GUARDA",[S_T_KM_NO_DEFAULT]="SIN PERFIL PREDETERMINADO: VACÍO"},
    [LANG_EN]={
        [S_ENTRY_EXIT]="EXIT",[S_ENTRY_STATS]="STATISTICS",[S_ENTRY_KEYBOARD]="KEYBOARD",[S_ENTRY_MOUSE]="MOUSE",
        [S_ENTRY_CONTROL]="CONTROLLER",
        [S_SEC_PERF]="PERFORMANCE",[S_SEC_GRAPHICS]="GRAPHICS",[S_SEC_CONTROLS]="CONTROLS",[S_SEC_SYSTEM]="SYSTEM",
        [S_ITEM_LANG]="LANGUAGE",[S_ITEM_EXIT]="CLOSE THE PROGRAM",[S_ITEM_EXIT_ALONE]="BACK TO THE DESKTOP",
        [S_FOOT_RAIL]="X: OPEN     O: CLOSE",[S_FOOT_CHOICE]="< >: CHOOSE     O: BACK",
        [S_FOOT_SAVE]="< >: CHOOSE     X: SAVE     O: BACK",[S_FOOT_TOGGLE]="X: ON / OFF     O: BACK",
        [S_FOOT_HUD]="X: SHOW OR HIDE     O: BACK",[S_FOOT_OPEN]="X: OPEN     O: BACK",
        [S_FOOT_EXIT]="X: CLOSE IT     O: BACK",[S_FOOT_BACK]="O: BACK",
        [S_RENDER_32_ONLY]="32-BIT ONLY",[S_T_RENDER_64]="RENDERER: 32-BIT PROGRAMS ONLY",
        [S_ENTRY_CURSOR]="CURSOR",[S_CURSOR_GAME]="GAME",[S_CURSOR_ALWAYS]="ALWAYS",[S_CURSOR_HIDDEN]="HIDDEN",
        [S_CURSOR_PROGRAM]="PROGRAM:",[S_T_CURSOR_NO_PROGRAM]="CURSOR: NO PROGRAM OPEN",
        [S_ENTRY_STRETCH]="STRETCH",
        [S_ENTRY_RENDER]="RENDERER",
        [S_HELP_RENDER]="D3D8/9 THROUGH DXVK OR WINE'S WINED3D, ON VULKAN OR OPENGL; THEN DIRECTDRAW AND D3D7. SAVED IN "
                        "WINE'S REGISTRY, IT APPLIES FROM THE PROGRAM'S NEXT START. 32-BIT PROGRAMS ONLY.",
        [S_RENDER_DXVK_VK]="DXVK + VULKAN",[S_RENDER_DXVK_GL]="DXVK + OPENGL",[S_RENDER_WINED3D_VK]="WINED3D + VULKAN",
        [S_RENDER_WINED3D_GL]="WINED3D + OPENGL",
        [S_T_RENDER_SAVED]="RENDERER: AT THE NEXT START",[S_T_RENDER_FAILED]="RENDERER: NOT SAVED",
        [S_T_RENDER_NO_ANSWER]="RENDERER: NO ANSWER",[S_T_RENDER_NO_PROGRAM]="RENDERER: NO PROGRAM OPEN",
        [S_ENTRY_FPS]="FPS LIMIT",[S_FPS_AUTO]="AUTO",[S_T_FPS_NO_PROGRAM]="FPS LIMIT: NO PROGRAM OPEN",
        [S_HELP_FPS]="THE PROGRAM'S VULKAN FRAMES GO AT AN EVEN 30 OR 60. AUTO: 60, OR 30 BELOW 52. 30 UNTIL CHOSEN. "
                     "WITH MANGOHUD'S LIMIT TOO, THE LOWER WINS.",
        [S_ENTRY_FRAMEGEN]="FRAME GEN",[S_T_FRAMEGEN_NO_PROGRAM]="FRAME GEN: NO PROGRAM OPEN",
        [S_PAD_GENERIC]="GENERIC",[S_T_PAD_NO_PROGRAM]="CONTROLLER: NO PROGRAM OPEN",
        [S_HELP_FRAMEGEN]="WITH FPS LIMIT AT 30 IT SHOWS 60: AN INTERPOLATED FRAME BETWEEN EACH TWO OF THE GAME'S. IT ADDS "
                          "ONE FRAME OF DELAY. IF THE GPU CANNOT KEEP UP, REAL FRAMES ONLY. EXPERIMENTAL.",
        [S_HELP_STRETCH]="THE PICTURE FILLS THE WHOLE SCREEN, WITHOUT BLACK BARS, OR KEEPS ITS PROPORTIONS. IT DOES NOT "
                         "CHANGE WITH THE DESKTOP IN FRONT.",
        [S_HELP_CURSOR]="GAME: THE ARROW SHOWS, EXCEPT FULL SCREEN WHEN THE GAME SETS NO CURSOR. ALWAYS: IT ALWAYS SHOWS. "
                        "HIDDEN: NOT WHILE THE PROGRAM STAYS OPEN. THE PAD STILL MOVES IT.",
        [S_ON]="ON",[S_OFF]="OFF",
        [S_HELP_EXIT]="CLOSES THE PROGRAM OF THE ACTIVE WINDOW, AS IF IT ENDED AT ONCE, AND THE DESKTOP STAYS. "
                      "IT DOES NOT ASK OR SAVE: UNSAVED WORK IS LOST.",
        [S_HELP_EXIT_ALONE]="CLOSES THIS PROGRAM, WHICH RUNS ALONE, AND THE APP RESTARTS INTO THE DESKTOP. IT DOES NOT ASK OR SAVE.",
        [S_HELP_STATS]="A CORNER READOUT LAID OUT AS MANGOHUD'S: GPU, CPU, RAM, FPS AND FRAME TIMES OF THE TITLE. "
                       "-- MEANS NO MEASURE. IT DOES NOT TURN ON OVER THE DESKTOP.",
        [S_HELP_STATS_HUD]="MANGOHUD SHOWS OR HIDES WITH ITS KEY, SHIFT+F12; THE PROGRAM DOES NOT GET IT. THE OVERLAY CANNOT SEE "
                           "WHETHER IT SHOWS: CHECK THE SCREEN. MANGOJUICE EDITS APPLY TO EVERY HUD.",
        [S_HELP_KEYBOARD]="AN ON-SCREEN KEYBOARD FOR THE FOCUSED WINDOW. SQUARE DELETES, TRIANGLE SPACE, L1 R1 MOVE, "
                          "L2 SHIFT, R2 SYMBOLS, OPTIONS ENTER, CIRCLE CLOSES.",
        [S_HELP_MOUSE]="THE STICK AND THE TOUCHPAD AS POINTER, CLICKS AND WHEEL. WHEN OFF, THE PAD'S KEYS AND KEY "
                       "PROFILES STAY. IT LASTS UNTIL THE APP CLOSES.",
        [S_HELP_CONTROL]="GENERIC: PAD KEYS AND PROFILES STAY. XBOX 360 AND ONE: AN XBOX PAD FOR XINPUT. DUALSENSE: A RAW "
                         "DUALSENSE. THE PROGRAM'S START WAITS FOR IT; IF IT DOES NOT CHANGE, RESTART THE GAME.",
        [S_HELP_CONFIG]="THE OVERLAY'S LANGUAGE, SAVED IN C:\\ORBIS\\OVERLAY.INI. IT APPLIES AT ONCE.",
        [S_KB_TITLE]="KEYBOARD",[S_KB_CAPS]="CAPS",[S_KB_LOWER]="lower",
        [S_KB_HINT1]="X KEY  SQUARE DELETE  TRIANGLE SPACE  L1 R1 CURSOR",
        [S_KB_HINT2]="L2 SHIFT  R2 SYMBOLS  OPTIONS ENTER  CIRCLE CLOSE",
        [S_KEY_SHIFT]="SHIFT",[S_KEY_SPACE]="SPACE",[S_KEY_BACK]="BACKSPACE",[S_KEY_ENTER]="ENTER",
        [S_KEY_HOME]="HOME",[S_KEY_END]="END",[S_KEY_DELETE]="DEL",
        [S_STAT_FRAMES]="FRAMES",[S_STAT_INTERVAL]="INTERVAL",[S_STAT_DIRECT]="DIRECT",
        [S_T_HUD_SENT]="MANGOHUD: SHIFT+F12 SENT",[S_T_TYPE_NOT_SAVED]="COULD NOT SAVE THE TYPE",
        [S_T_CONFIG_NOT_SAVED]="COULD NOT SAVE THE SETTING",[S_T_CLOSED]="PROGRAM CLOSED",
        [S_T_REFUSED_DESKTOP]="EXITING...",[S_T_REFUSED_NONE]="EXIT: NO ACTIVE WINDOW",
        [S_T_REFUSED_CONSOLE]="EXIT: CONSOLE PROGRAM, NOT CLOSED",[S_T_KEPT]="COULD NOT CLOSE",
        [S_T_ASKED32]="EXITING...",[S_T_UNKNOWN]="EXIT: UNKNOWN RESULT",
        [S_T_NOT_TAKEN]="EXIT: NO ANSWER",[S_T_NO_RESULT]="EXIT: NO RESULT",
        [S_T_BACK_DESKTOP]="RETURNING TO THE DESKTOP",[S_T_BACK_FAILED]="COULD NOT RETURN TO THE DESKTOP",
        [S_T_SEARCHING]="EXIT: LOOKING FOR THE ACTIVE PROGRAM",
        [S_ITEM_KEYMAP]="KEY MAPPING",
        [S_HELP_KEYMAP]="A KEY OR A MOUSE CLICK FOR EACH BUTTON AND STICK DIRECTION OF THE PAD, PER PROGRAM, FOR GAMES "
                        "THAT READ ONLY THE KEYBOARD AND MOUSE. SAVED IN C:\\ORBIS\\PADMAPS.",
        [S_KM_HELP]="ONCE A KEY IS SET, EMPTY BUTTONS DO NOTHING AND THE LEFT STICK SENDS THE ARROWS (AUTO). A PROGRAM "
                    "THAT READS THE PAD THROUGH XINPUT GETS THE PAD, NOT THE KEYS.",
        [S_KM_PICK_HELP]="THE KEY OR MOUSE BUTTON STAYS DOWN WHILE THE PAD BUTTON IS HELD; A CLICK LANDS WHERE THE POINTER "
                         "IS. THE WHEEL TURNS ONE NOTCH PER PRESS. OPTIONS SAVES.",
        [S_KM_FOOT]="X: ASSIGN    SQUARE: CLEAR    TRIANGLE: DEFAULT    O: BACK",
        [S_KM_FOOT_DIRTY]="X: ASSIGN    SQUARE: CLEAR    TRIANGLE: DEFAULT    OPTIONS: SAVE    O: CANCEL",
        [S_KM_PICK_TITLE]="KEY FOR",[S_KM_PICK_FOOT]="X: ASSIGN    SQUARE: NO KEY    O: CANCEL",
        [S_KM_MOUSE]="POINTER",[S_KM_SYSTEM]="SYSTEM",[S_KM_AUTO]="AUTO",
        [S_KEY_UP]="UP",[S_KEY_DOWN]="DOWN",[S_KEY_LEFT]="LEFT",[S_KEY_RIGHT]="RIGHT",[S_KEY_PGUP]="PGUP",
        [S_KEY_PGDN]="PGDN",[S_KEY_MOUSE_LEFT]="MOUSE LEFT",[S_KEY_MOUSE_RIGHT]="MOUSE RIGHT",
        [S_KEY_MOUSE_MIDDLE]="MOUSE MIDDLE",[S_KEY_WHEEL_UP]="WHEEL UP",[S_KEY_WHEEL_DOWN]="WHEEL DOWN",
        [S_T_KM_SAVED]="KEY MAPPING SAVED",[S_T_KM_NOT_SAVED]="KEY MAPPING: NOT SAVED",
        [S_T_KM_NO_PROGRAM]="KEY MAPPING: NO PROGRAM OPEN",[S_T_KM_SHARE]="SHARE BELONGS TO THE SYSTEM",
        [S_T_KM_DEFAULT]="DEFAULT LOADED: OPTIONS SAVES IT",[S_T_KM_NO_DEFAULT]="NO DEFAULT PROFILE: ALL CLEARED"}};

/* 04.31: what each item is: its name, its help, and how it is changed (a choice of values, on/off, or an action) */
enum {KIND_CHOICE,KIND_TOGGLE,KIND_ACTION};
static const struct {int name,help,kind;} item_info[ITEMS]={
    [IT_FPS]={S_ENTRY_FPS,S_HELP_FPS,KIND_CHOICE},[IT_FRAMEGEN]={S_ENTRY_FRAMEGEN,S_HELP_FRAMEGEN,KIND_TOGGLE},
    [IT_STATS]={S_ENTRY_STATS,S_HELP_STATS,KIND_TOGGLE},[IT_RENDER]={S_ENTRY_RENDER,S_HELP_RENDER,KIND_CHOICE},
    [IT_STRETCH]={S_ENTRY_STRETCH,S_HELP_STRETCH,KIND_TOGGLE},[IT_CONTROL]={S_ENTRY_CONTROL,S_HELP_CONTROL,KIND_CHOICE},
    [IT_KEYMAP]={S_ITEM_KEYMAP,S_HELP_KEYMAP,KIND_ACTION},  /* 04.36 */
    [IT_MOUSE]={S_ENTRY_MOUSE,S_HELP_MOUSE,KIND_TOGGLE},[IT_CURSOR]={S_ENTRY_CURSOR,S_HELP_CURSOR,KIND_CHOICE},
    [IT_KEYBOARD]={S_ENTRY_KEYBOARD,S_HELP_KEYBOARD,KIND_ACTION},[IT_LANG]={S_ITEM_LANG,S_HELP_CONFIG,KIND_CHOICE},
    [IT_EXIT]={S_ITEM_EXIT,S_HELP_EXIT,KIND_ACTION}};
/* each section's items, -1 after the last; PERFORMANCE, GRAPHICS and CONTROLS hold per-program settings and show
 * the program they are saved for at their top */
enum {SECTION_ITEMS=5};
static const int section_items[SECTIONS][SECTION_ITEMS]={
    [SEC_PERF]={IT_FPS,IT_FRAMEGEN,IT_STATS,-1,-1},[SEC_GRAPHICS]={IT_RENDER,IT_STRETCH,-1,-1,-1},
    [SEC_CONTROLS]={IT_CONTROL,IT_KEYMAP,IT_MOUSE,IT_CURSOR,IT_KEYBOARD},[SEC_SYSTEM]={IT_LANG,-1,-1,-1,-1},
    [SEC_EXIT]={IT_EXIT,-1,-1,-1,-1}};
static const int section_names[SECTIONS]={S_SEC_PERF,S_SEC_GRAPHICS,S_SEC_CONTROLS,S_SEC_SYSTEM,S_ENTRY_EXIT};
static const int section_per_program[SECTIONS]={1,1,1,0,0};
static int section_count(int sec)
{
    int n=0;
    while(n<SECTION_ITEMS && section_items[sec][n]>=0) n++;
    return n;
}

static pthread_mutex_t lock=PTHREAD_MUTEX_INITIALIZER;
static pthread_once_t once=PTHREAD_ONCE_INIT;
/* 04.31: section and item are the rail's and the section's selection; focus says which of the two the pad moves */
static int view,section,item,focus,stats_on,mouse_on=1,pad_type,type_choice,title_alone;
static int kb_row,kb_col,kb_page,kb_shift;
static uint32_t held;       /* buttons down at the last read */
static int swallow;         /* after closing: the pad stays here until every button is up */
static uint32_t nav_held;   /* d-pad or stick directions held, for repeat */
static uint64_t nav_next_us;
static char toast[48];
static uint64_t toast_until_us,stats_next_us;
/* the readout's measures, sampled once a second: -1 (or 0 for FPS) where the source has none */
struct hud_values {int sampled,gpu_m,cpu_m,vk;long long ram_mib;unsigned fps_tenths,frame_us;};
static struct hud_values hud_now;
/* the intervals between output frames, measured in pw_hw_overlay_draw while the readout shows */
enum {FT_SAMPLES=200};  /* MangoHud's frametime graph keeps 200 */
static uint32_t ft_us[FT_SAMPLES];
static int ft_count,ft_head;
static uint64_t ft_last_us;
/* MangoHud.conf's rows, place and size, read when Estadisticas turns on */
enum {POS_TOP_LEFT,POS_TOP_RIGHT,POS_TOP_CENTER,POS_MIDDLE_LEFT,POS_MIDDLE_RIGHT,POS_BOTTOM_LEFT,POS_BOTTOM_RIGHT,
      POS_BOTTOM_CENTER,POSITIONS};
struct hud_conf {int loaded,gpu,cpu,vram,ram,fps,frametime,frame_timing,position,offset_x,offset_y,font_size,alpha_pct;};
static struct hud_conf hud_conf;
/* W238: kernelbase's closer says whether libMangoHud.dll is loaded; the sink whether Vulkan presents */
static int mangohud_loaded,vk_presenting;
/* W261: kernelbase's closer: the desktop, the taskbar or no window is in front (Salir's refusals) */
static int desktop_front;
static uint64_t hud_release_us;  /* Shift+F12 down until then */
static uint64_t hud_pressed_us;  /* 04.26: since then, and the present count then */
static unsigned hud_presents;
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
/* overlay.ini: cursor, stretch, fpslimit, framegen; 04.26: pad (a TYPE_, -1 without a line) */
static struct {char name[64];int mode,stretch,fps,fg,pad;} cursor_saved[CURSOR_SAVED];
static volatile int stretch_on;      /* W266: read by the sink without the lock */
static int cursor_saved_count;
static volatile int cursor_mode;     /* read by the sink without the lock */
static int cursor_choice;
static char cursor_program[64];      /* the program cursor_mode is for, "" for none */
/* LIMITE FPS for the last program opened: 0 off, 30, 60, -1 auto (pw_fps_limit.h's values). 04.18: 30 for a program
 * with no choice saved; with no program open (the desktop), off */
enum {FPS_CHOICES=4,FPS_DEFAULT=30};
static const int fps_values[FPS_CHOICES]={0,30,60,-1};
static const char *const fps_words[FPS_CHOICES]={"off","30","60","auto"};
static volatile int fps_limit;       /* read by the sink without the lock */
static int fps_choice;               /* an index into fps_values */
/* GENERAR CUADROS for the last program opened (docs/FRAME_GENERATION.md, stage 5) */
static volatile int framegen_on;     /* read by the sink without the lock */
/* changes whenever the last program opened does: the sink starts frame generation's decisions over */
static volatile unsigned program_serial;
static uint64_t hud_conf_next_us;    /* when GENERAR CUADROS looks at MangoHud.conf again */
static int fps_index(int value)
{
    for(int i=0;i<FPS_CHOICES;i++) if(fps_values[i]==value) return i;
    return 0;
}
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
/* 04.31: the world each program started in, 64 or 32, from kernelbase's guest launch through xinput's Unix library
 * (tools/build-xinput-hw.py: its 64-bit call table says 64, its WoW64 one 32), before pw_hw_overlay_program. RENDERER
 * sets only 32-bit programs' registry values; a program whose world is not known (an ELF without it) keeps it. */
enum {PROGRAM_BITS=16};
static struct {char name[64];int bits;} program_bits[PROGRAM_BITS];
static int program_bits_next;
void pw_wine_pad_program_bits(const char *exe,int bits);
void pw_wine_pad_program_bits(const char *exe,int bits)
{
    const char *base=exe;
    int i;
    for(const char *at=exe;at && *at;at++) if(*at=='\\' || *at=='/') base=at+1;
    if(!base || !base[0]) return;
    pthread_mutex_lock(&lock);
    for(i=0;i<PROGRAM_BITS && strcasecmp(program_bits[i].name,base);i++) ;
    if(i==PROGRAM_BITS) {
        i=program_bits_next;program_bits_next=(program_bits_next+1)%PROGRAM_BITS;
        snprintf(program_bits[i].name,sizeof(program_bits[i].name),"%s",base);
    }
    program_bits[i].bits=bits;
    pthread_mutex_unlock(&lock);
    if(pw_trace_on()) fprintf(stderr,"PWOVERLAY program %s bits=%d\n",base,bits);
}
/* lock held: 1 when RENDERER's program is a 64-bit one */
static int render_unavailable(void)
{
    if(!render_program[0]) return 0;
    for(int i=0;i<PROGRAM_BITS;i++) if(!strcasecmp(program_bits[i].name,render_program)) return program_bits[i].bits==64;
    return 0;
}
/* lock held (or init): a program's saved entry, added with mode game if add; -1 when there is none */
static int cursor_slot(const char *name,int add)
{
    for(int i=0;i<cursor_saved_count;i++) if(!strcasecmp(cursor_saved[i].name,name)) return i;
    if(!add || cursor_saved_count==CURSOR_SAVED) return -1;
    snprintf(cursor_saved[cursor_saved_count].name,sizeof(cursor_saved[0].name),"%s",name);
    cursor_saved[cursor_saved_count].mode=CURSOR_GAME;
    cursor_saved[cursor_saved_count].stretch=0;
    cursor_saved[cursor_saved_count].fps=FPS_DEFAULT;cursor_saved[cursor_saved_count].fg=0;
    cursor_saved[cursor_saved_count].pad=-1;
    return cursor_saved_count++;
}

static const char *str(int id)
{
    const char *s=strings[lang][id];
    return s?s:strings[LANG_ES][id]?strings[LANG_ES][id]:"?";
}
/* 04.26: CONTROL's types; the generic one's name is in the strings table */
static const char *type_name(int type)
{
    if(type<0 || type>=TYPES) return "--";
    return type==TYPE_GENERIC?str(S_PAD_GENERIC):type_names[type];
}
/* C:\orbis\overlay.ini: "key=value" lines: lang (es, en); W261: cursor.<exe> (game, always, hidden) */
static void read_config(void)
{
    char line[160];
    FILE *file=fopen(CONFIG_FILE,"r");
    lang=LANG_EN;  /* W303 (alpha-1): English until the user picks a language on the CONFIG page */
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
        if(!strncmp(line,"fpslimit.",9) && (eq=strrchr(line,'=')) && eq>line+9) {
            int value=-2;
            *eq=0;
            for(int i=0;i<FPS_CHOICES;i++) if(!strcmp(eq+1,fps_words[i])) value=fps_values[i];
            if(value==-2 || (slot=cursor_slot(line+9,1))<0) {
                fprintf(stderr,"PWOVERLAY config line ignored: %s=%s\n",line,eq+1);continue;
            }
            cursor_saved[slot].fps=value;
            continue;
        }
        if(!strncmp(line,"framegen.",9) && (eq=strrchr(line,'=')) && eq>line+9) {  /* stage 5 */
            *eq=0;
            if((strcmp(eq+1,"on") && strcmp(eq+1,"off")) || (slot=cursor_slot(line+9,1))<0) {
                fprintf(stderr,"PWOVERLAY config line ignored: %s=%s\n",line,eq+1);continue;
            }
            cursor_saved[slot].fg=!strcmp(eq+1,"on");
            continue;
        }
        if(!strncmp(line,"pad.",4) && (eq=strrchr(line,'=')) && eq>line+4) {  /* 04.26 */
            int type=-1;
            *eq=0;
            for(int i=0;i<TYPES;i++) if(!strcmp(eq+1,type_words[i])) type=i;
            if(type<0 || (slot=cursor_slot(line+4,1))<0) {
                fprintf(stderr,"PWOVERLAY config line ignored: %s=%s\n",line,eq+1);continue;
            }
            cursor_saved[slot].pad=type;
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
        /* 04.18: 30 is the default and writes no line; off does */
        if(ok && cursor_saved[i].fps!=FPS_DEFAULT)
            ok=fprintf(file,"fpslimit.%s=%s\n",cursor_saved[i].name,fps_words[fps_index(cursor_saved[i].fps)])>0;
        if(ok && cursor_saved[i].fg) ok=fprintf(file,"framegen.%s=on\n",cursor_saved[i].name)>0;
        if(ok && cursor_saved[i].pad>=0)  /* 04.26 */
            ok=fprintf(file,"pad.%s=%s\n",cursor_saved[i].name,type_words[cursor_saved[i].pad])>0;
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

/* pad_type: what padtype.txt holds, -1 for nothing this overlay writes (04.25's "x360" meant generic without
 * padhid-xinput.txt: it is written again at the start) */
static void read_type(void)
{
    char text[16]={0};
    FILE *file=fopen(TYPE_FILE,"r");
    if(file) {if(!fgets(text,sizeof(text),file)) text[0]=0;fclose(file);}
    text[strcspn(text,"\r\n")]=0;
    pad_type=-1;
    for(int i=0;i<TYPES;i++) if(!strcmp(text,type_words[i])) pad_type=i;
}
/* lock held (or init): padtype.txt says the type winebus, xinput and dinput follow */
static int write_type(int type,const char *program,const char *why)
{
    FILE *file=fopen(TYPE_FILE,"w");
    int ok=file && fprintf(file,"%s\n",type_words[type])>0;
    if(file && fclose(file)) ok=0;
    fprintf(stderr,"PWOVERLAY control type=%s program=%s saved=%d errno=%d why=%s\n",type_words[type],
            program[0]?program:"-",ok,ok?0:errno,why);
    if(ok) pad_type=type;
    return ok;
}
/* 04.26: a program with no CONTROL choice: generic, or Xbox 360 while padhid-xinput.txt exists (W213's switch) */
static int pad_default(void)
{
    struct stat st;
    return stat(XINPUT_SWITCH,&st)?TYPE_GENERIC:TYPE_X360;
}
/* lock held (or init): the last program opened's type into padtype.txt, when it differs; why: boot, start, exit */
static void pad_apply(const char *why)
{
    const char *name=program_count?programs[program_count-1]:"";
    int slot=name[0]?cursor_slot(name,0):-1;
    int type=slot>=0 && cursor_saved[slot].pad>=0?cursor_saved[slot].pad:pad_default();
    if(type!=pad_type) write_type(type,name,why);
}
static void init(void)
{
    read_type();
    read_config();
    pad_apply("boot");
    type_choice=pad_type;
    title_alone=pw_hw_overlay_exit_title(0);
    fprintf(stderr,"PWOVERLAY ready type=%s lang=%s title_alone=%d\n",pad_type>=0?type_words[pad_type]:"-",
            lang_words[lang],title_alone);
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
    if(pw_trace_on()) fprintf(stderr,"PWOVERLAY mangohud in_front=%d\n",loaded!=0);
}
/* W261: kernelbase's closer, when it changes (through native/hw_pad.c) */
void pw_hw_overlay_desktop(int in_front);
void pw_hw_overlay_desktop(int in_front)
{
    pthread_mutex_lock(&lock);
    desktop_front=in_front!=0;
    pthread_mutex_unlock(&lock);
    if(pw_trace_on()) fprintf(stderr,"PWOVERLAY desktop in_front=%d\n",in_front!=0);
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
    if(take && pw_trace_on()) fprintf(stderr,"PWOVERLAY exit taken by the closer\n");
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
    /* 04.18: a program with no choice saved runs at 30; the desktop (no program) is not limited */
    int fps=slot>=0?cursor_saved[slot].fps:name[0]?FPS_DEFAULT:0;
    int fg=slot>=0 && cursor_saved[slot].fg;  /* stage 5 */
    pad_apply(why);  /* 04.26: CONTROL follows the program */
    if(strcmp(name,cursor_program)) ++program_serial;
    if(fg!=framegen_on) {
        fprintf(stderr,"PWOVERLAY framegen=%s program=%s why=%s\n",fg?"on":"off",name[0]?name:"-",why);
        framegen_on=fg;
    }
    if(strcmp(name,render_program)) {  /* W287: GRAFICOS is read again for the new program */
        if(render_request==RENDER_SET) fprintf(stderr,"PWOVERLAY render set for %s dropped: the program changed\n",render_program);
        snprintf(render_program,sizeof(render_program),"%s",name);
        render_saved=-1;render_choice=0;render_taken=0;
        render_request=name[0]?RENDER_GET:RENDER_NONE;
    }
    if(fps!=fps_limit) {
        fprintf(stderr,"PWOVERLAY fpslimit=%s program=%s why=%s\n",fps_words[fps_index(fps)],name[0]?name:"-",why);
        fps_limit=fps;fps_choice=fps_index(fps);
    }
    if(mode==cursor_mode && stretch==stretch_on && !strcmp(name,cursor_program)) return 0;
    snprintf(cursor_program,sizeof(cursor_program),"%s",name);
    cursor_mode=mode;cursor_choice=mode;stretch_on=stretch;
    fprintf(stderr,"PWSINK cursor mode=%s stretch=%d program=%s saved=%d why=%s\n",cursor_words[mode],stretch,
            name[0]?name:"-",slot>=0,why);
    return 1;
}
/* W293: the "app starting" pointer, as Windows' IDC_APPSTARTING: from a program's start (pw_hw_overlay_program with
 * load 1: kernelbase's guest launch, 64- and 32-bit, or a relaunched title) until a top-level window is shown
 * (ps5drv.c through the sink, pw_hw_overlay_window_shown), that program ends, or BUSY_US pass. The sink draws a
 * turning ring by the arrow (pw_hw_busy_frame); the pad thread asks for a frame every BUSY_FRAME_US. */
enum {BUSY_US=20000000,BUSY_FRAME_US=100000,BUSY_FRAMES=8};
static volatile uint64_t busy_since_us;  /* 0 while no program starts; read by the sink without the lock */
static uint64_t busy_next_us;
static char busy_program[64];
/* lock held; 1 when it was busy */
static int busy_end(const char *why,const void *hwnd,const char *class_name)
{
    if(!busy_since_us) return 0;
    fprintf(stderr,"PWSINK busy end program=%s why=%s hwnd=%p class=%s ms=%llu\n",busy_program,why,hwnd,
            class_name?class_name:"-",(unsigned long long)((sceKernelGetProcessTime()-busy_since_us)/1000));
    busy_since_us=0;
    return 1;
}
/* lock held: a program started (load 1) or ended; 1 when the pointer changes */
static int busy_program_event(const char *name,int load)
{
    uint64_t now=sceKernelGetProcessTime();
    if(!load) return !strcasecmp(name,busy_program) && busy_end("exit",NULL,NULL);
    busy_end("replaced",NULL,NULL);
    snprintf(busy_program,sizeof(busy_program),"%s",name);
    busy_since_us=now?now:1;busy_next_us=now+BUSY_FRAME_US;
    fprintf(stderr,"PWSINK busy begin program=%s why=start\n",busy_program);
    return 1;
}
/* the sink, from ps5drv.c: a top-level window was shown for the first time (menus, tooltips, the desktop, the
 * taskbar and tool windows left out there) */
void pw_hw_overlay_window_shown(void *hwnd,const char *class_name);
void pw_hw_overlay_window_shown(void *hwnd,const char *class_name)
{
    int ended;
    pthread_mutex_lock(&lock);
    ended=busy_end("window",hwnd,class_name);
    pthread_mutex_unlock(&lock);
    if(ended) pw_hw_cursor_moved();
}
/* the sink, on each frame: the ring's frame (0 to BUSY_FRAMES-1) while a program starts, -1 otherwise */
int pw_hw_busy_frame(void);
int pw_hw_busy_frame(void)
{
    uint64_t since=busy_since_us,now=sceKernelGetProcessTime();
    if(!since || now-since>=BUSY_US) return -1;
    return (int)((now-since)/BUSY_FRAME_US%BUSY_FRAMES);
}
/* 04.30 (run-0255): a guest's start waits until winebus has the device of the type just applied (pad_apply,
 * why=start), so a program that lists its devices at once sees it: at most PAD_WAIT_US, then PAD_SETTLE_US for
 * winexinput's "&IG_" HID devices, which come after the bus device's start. Called by kernelbase's guest launch
 * (native/hw_pad.c pw_wine_pad_profile) before the program's entry point, without the lock. No wait when the device
 * is already the right one; weak: an ELF without winebus does not wait. */
/* 04.32 (run-0257): the type compared is the one pad_apply just wrote (want), passed to winebus, not padtype.txt read
 * back there; every start logs one line with winebus's state (bus 1 running, started 1, bus_kind its device's) */
extern int pw_winebus_pad_ready_kind(int want,int *state) __attribute__((weak));
extern void pw_winebus_pad_check_now(void) __attribute__((weak));
enum {PAD_WAIT_US=2000000,PAD_SETTLE_US=300000,PAD_POLL_US=10000};
static void pad_wait(const char *program,int want)
{
    static int unavailable_logged;
    uint64_t start,waited=0;
    int state=0,ready=0;
    if(!pw_winebus_pad_ready_kind || !pw_winebus_pad_check_now) {
        if(!unavailable_logged) fprintf(stderr,"PWOVERLAY control wait unavailable (no winebus in this ELF)\n");
        unavailable_logged=1;
        return;
    }
    if(want<0 || want>=TYPES) {fprintf(stderr,"PWOVERLAY control wait program=%s: no type written\n",program);return;}
    if(pw_winebus_pad_ready_kind(want,&state)) {
        if(pw_trace_on()) fprintf(stderr,"PWOVERLAY control wait program=%s type=%s ready=1 at_once=1 bus=%d started=%d bus_kind=%d\n",
                program,type_words[want],state&1,state>>1&1,state>>4);
        return;
    }
    pw_winebus_pad_check_now();
    start=sceKernelGetProcessTime();
    do {
        struct timespec pause={0,PAD_POLL_US*1000L};
        nanosleep(&pause,NULL);
        ready=pw_winebus_pad_ready_kind(want,&state);
        waited=sceKernelGetProcessTime()-start;
    } while(!ready && waited<PAD_WAIT_US);
    if(ready) {struct timespec settle={0,PAD_SETTLE_US*1000L};nanosleep(&settle,NULL);}
    if(!ready || pw_trace_on()) fprintf(stderr,"PWOVERLAY control wait program=%s type=%s ready=%d ms=%llu settle_ms=%d bus=%d started=%d bus_kind=%d\n",
            program,type_words[want],ready,(unsigned long long)(waited/1000),ready?PAD_SETTLE_US/1000:0,state&1,
            state>>1&1,state>>4);
}
void pw_hw_overlay_program(const char *exe,int load);
void pw_hw_overlay_program(const char *exe,int load)
{
    const char *base=exe;
    int changed,want;
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
    changed|=busy_program_event(base,load);  /* W293 */
    want=pad_type;  /* 04.32: the type pad_apply just wrote (or kept) for this program */
    pthread_mutex_unlock(&lock);
    if(changed) pw_hw_cursor_moved();
    if(load) pad_wait(base,want);  /* 04.30 */
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
/* the sink, on each Vulkan present: LIMITE FPS for the last program opened (0 off, 30, 60, -1 auto) */
int pw_hw_overlay_fps_limit(void);
int pw_hw_overlay_fps_limit(void) {return fps_limit;}
/* lock held: X on LIMITE FPS saves the choice for the last program opened and applies it at once */
static void fps_choose(void)
{
    const char *name=program_count?programs[program_count-1]:"";
    int slot,ok=0;
    if(!name[0]) {
        set_toast(str(S_T_FPS_NO_PROGRAM));
        fprintf(stderr,"PWOVERLAY fpslimit=%s not saved: no program open\n",fps_words[fps_choice]);
        fps_choice=fps_index(fps_limit);return;
    }
    if((slot=cursor_slot(name,1))>=0) {cursor_saved[slot].fps=fps_values[fps_choice];ok=write_config(lang);}
    fps_limit=fps_values[fps_choice];
    fprintf(stderr,"PWOVERLAY fpslimit=%s program=%s saved=%d errno=%d why=menu%s\n",fps_words[fps_choice],name,ok,
            ok?0:errno,slot<0?" (overlay.ini has 64 programs already)":"");
    if(!ok) set_toast(str(S_T_CONFIG_NOT_SAVED));
}
/* the sink, on each Vulkan present: GENERAR CUADROS for the last program opened (1 on), and a number that changes with
 * that program */
int pw_hw_overlay_framegen(void);
int pw_hw_overlay_framegen(void) {return framegen_on;}
unsigned pw_hw_overlay_program_serial(void);
unsigned pw_hw_overlay_program_serial(void) {return program_serial;}
/* lock held: X on GENERAR CUADROS turns it on or off for the last program opened, saves it and applies it at once */
static void framegen_toggle(void)
{
    const char *name=program_count?programs[program_count-1]:"";
    int slot,ok=0;
    if(!name[0]) {
        set_toast(str(S_T_FRAMEGEN_NO_PROGRAM));
        fprintf(stderr,"PWOVERLAY framegen not saved: no program open\n");return;
    }
    framegen_on=!framegen_on;
    if(framegen_on) hud_conf_next_us=0;   /* MangoHud's rectangle is read again soon */
    if((slot=cursor_slot(name,1))>=0) {cursor_saved[slot].fg=framegen_on;ok=write_config(lang);}
    fprintf(stderr,"PWOVERLAY framegen=%s program=%s saved=%d errno=%d why=menu fpslimit=%s%s\n",framegen_on?"on":"off",
            name,ok,ok?0:errno,fps_words[fps_index(fps_limit)],slot<0?" (overlay.ini has 64 programs already)":"");
    if(!ok) set_toast(str(S_T_CONFIG_NOT_SAVED));
}
/* 04.26, lock held: X on CONTROL saves the type for the last program opened and applies it at once: winebus replaces
 * the device within about a quarter of a second, xinput and dinput read it within a second */
static void pad_choose(void)
{
    const char *name=program_count?programs[program_count-1]:"";
    int slot,ok=0;
    if(type_choice<0 || type_choice>=TYPES) {type_choice=pad_type;return;}
    if(!name[0]) {
        set_toast(str(S_T_PAD_NO_PROGRAM));
        fprintf(stderr,"PWOVERLAY control type=%s not saved: no program open\n",type_words[type_choice]);
        type_choice=pad_type;return;
    }
    if((slot=cursor_slot(name,1))>=0) {cursor_saved[slot].pad=type_choice;ok=write_config(lang);}
    fprintf(stderr,"PWOVERLAY control pad.%s=%s saved=%d errno=%d why=menu%s\n",name,type_words[type_choice],ok,
            ok?0:errno,slot<0?" (overlay.ini has 64 programs already)":"");
    if(!ok) set_toast(str(S_T_CONFIG_NOT_SAVED));
    if(type_choice!=pad_type && !write_type(type_choice,name,"menu")) set_toast(str(S_T_TYPE_NOT_SAVED));
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
    if(pw_trace_on()) fprintf(stderr,"PWOVERLAY render set %s for %s requested\n",render_words[render_choice],render_program);
}
/* lock held: Estadisticas acts on MangoHud's HUD */
/* 04.26 (run-0234): the closer's report alone. It names a window in front that Vulkan presented to and keeps it while
 * it does not present; vk_presenting went 0 two seconds after a page stopped changing, and ESTADISTICAS then toggled
 * the overlay's own readout, not MangoHud */
static int hud_mode(void) {return mangohud_loaded;}

/* ---- the readout: each value is a measure, "--" when its source has none ---- */
/* MangoHud.conf as MangoHud reads it (overlay_params.cpp): its defaults first (fps, frametime,
 * frame_timing, cpu_stats, gpu_stats; font_size 24; background_alpha 0.5; top-left), then each line,
 * "key" or "key=value", turns on, off or sets; "full" turns every row on. Kept: the rows drawn here,
 * position, offset_x/y, font_size and background_alpha. legacy_layout=0's own order is not followed. */
#ifndef HUD_USERS  /* a host preview points it elsewhere */
#define HUD_USERS "/data/wine-prefix/drive_c/users"
#endif
static const char *const hud_positions[POSITIONS]={"top-left","top-right","top-center","middle-left","middle-right",
                                                    "bottom-left","bottom-right","bottom-center"};
/* %APPDATA% is under the prefix's user, whatever its name; with several users (a profile another prefix's
 * registry import added, 2026-11-13: C:\users\jose next to orbis), the MangoHud.conf saved last, which is the one
 * MangoJuice wrote. Its modification time, 0 when there is none. */
/* Hardware 2026-11-16 (run-0150 and run-0151, every time Estadisticas came on): "no MangoHud.conf,
 * MangoHud's defaults", with the file in place and MangoJuice writing it. The SDK's OrbisKernelStat
 * does not match the record the kernel returns (platform/ps4/pw_wine_platform.c PwOrbisStat, W230),
 * so st_mtime read the wrong bytes and came back 0 for every candidate; nothing beat newest=0 and no
 * path was chosen. pw_wine_stat converts that record into a struct stat, and the title links it. */
int pw_wine_stat(const char *,struct stat *);
/* what says the file changed: its time, or its size where the console reports no time */
static time_t hud_conf_stamp(const struct stat *st){return st->st_mtime?st->st_mtime:(time_t)st->st_size+1;}
static time_t hud_newest_conf(char *path,size_t size)
{
    char candidate[256];struct stat st;time_t newest=0;
    DIR *users=opendir(HUD_USERS);
    if(!users) return 0;
    struct dirent *e;
    while((e=readdir(users))) {
        if(e->d_name[0]=='.' || !strcasecmp(e->d_name,"Public")) continue;
        snprintf(candidate,sizeof(candidate),HUD_USERS "/%s/AppData/Roaming/MangoHud/MangoHud.conf",e->d_name);
        if(pw_wine_stat(candidate,&st)) continue;
        time_t stamp=hud_conf_stamp(&st);
        if(stamp>newest) {newest=stamp;snprintf(path,size,"%s",candidate);}
    }
    closedir(users);
    return newest;
}
static time_t hud_conf_mtime;  /* of the file hud_conf came from; the HUD reads it again when it changes */
static void hud_read_conf(struct hud_conf *c)
{
    char path[256]="",line[160];FILE *file=NULL;
    *c=(struct hud_conf){.loaded=1,.gpu=1,.cpu=1,.fps=1,.frametime=1,.frame_timing=1,.font_size=24,.alpha_pct=50};
    hud_conf_mtime=hud_newest_conf(path,sizeof(path));
    if(hud_conf_mtime) file=fopen(path,"r");
    if(!file) {if(pw_trace_on()) fprintf(stderr,"PWOVERLAY hud: no MangoHud.conf, MangoHud's defaults\n");return;}
    /* legacy_layout=0 (MangoJuice writes "legacy_layout=false"): MangoHud shows only the rows the file names
     * (overlay_params.cpp, sort_elements), not its defaults; each row's last value in the file, -1 unnamed */
    int legacy=1,named[7]={-1,-1,-1,-1,-1,-1,-1};
    int *const rows[7]={&c->gpu,&c->cpu,&c->vram,&c->ram,&c->fps,&c->frametime,&c->frame_timing};
    static const char *const row_keys[7]={"gpu_stats","cpu_stats","vram","ram","fps","frametime","frame_timing"};
    while(fgets(line,sizeof(line),file)) {
        char *key=line,*value,*end;
        if((end=strpbrk(key,"#\r\n"))) *end=0;
        while(*key==' ' || *key=='\t') key++;
        if((value=strchr(key,'='))) {*value++=0;while(*value==' ' || *value=='\t') value++;}
        for(end=key+strlen(key);end>key && (end[-1]==' ' || end[-1]=='\t');) *--end=0;
        if(!*key) continue;
        int on=!value || atoi(value)!=0;
        for(int i=0;i<7;i++) if(!strcmp(key,row_keys[i])) named[i]=on;
        if(!strcmp(key,"legacy_layout")) legacy=on;
        else if(!strcmp(key,"gpu_stats")) c->gpu=on;
        else if(!strcmp(key,"cpu_stats")) c->cpu=on;
        else if(!strcmp(key,"vram")) c->vram=on;
        else if(!strcmp(key,"ram")) c->ram=on;
        else if(!strcmp(key,"fps")) c->fps=on;
        else if(!strcmp(key,"frametime")) c->frametime=on;
        else if(!strcmp(key,"frame_timing")) c->frame_timing=on;
        else if(!strcmp(key,"full") && on) c->gpu=c->cpu=c->vram=c->ram=c->fps=c->frametime=c->frame_timing=1;
        else if(!strcmp(key,"position") && value) {
            for(int i=0;i<POSITIONS;i++) if(!strcmp(value,hud_positions[i])) c->position=i;
        } else if(!strcmp(key,"offset_x") && value) c->offset_x=atoi(value);
        else if(!strcmp(key,"offset_y") && value) c->offset_y=atoi(value);
        else if(!strcmp(key,"font_size") && value) {int n=atoi(value);if(n>=8 && n<=96) c->font_size=n;}
        else if(!strcmp(key,"background_alpha") && value) {
            double a=strtod(value,NULL);
            if(a>=0 && a<=1) c->alpha_pct=(int)(a*100+0.5);
        }
    }
    fclose(file);
    if(!legacy) for(int i=0;i<7;i++) *rows[i]=named[i]==1;
    if(pw_trace_on()) fprintf(stderr,"PWOVERLAY hud: %s legacy_layout=%d gpu=%d cpu=%d vram=%d ram=%d fps=%d frametime=%d frame_timing=%d position=%s"
            " font_size=%d alpha=%d%%\n",path,legacy,c->gpu,c->cpu,c->vram,c->ram,c->fps,c->frametime,c->frame_timing,
            hud_positions[c->position],c->font_size,c->alpha_pct);
}
static void sample_stats(void)
{
    unsigned vk_tenths=0,frames_tenths=0,avg_us=0,max_us=0;int vk_fresh=0,frames_fresh=0,load_conf;
    struct pw_ps4_telemetry telemetry;uint32_t returned=0;
    size_t direct_free=0;off_t found=0,total;
    struct hud_values v={.sampled=1,.gpu_m=-1,.cpu_m=-1,.ram_mib=-1};
    struct hud_conf conf;
    pthread_mutex_lock(&lock);load_conf=!hud_conf.loaded;pthread_mutex_unlock(&lock);
    if(!load_conf) {
        /* a save in MangoJuice shows without turning Estadisticas off and on (MangoHud's own watcher needs folder
         * notifications, which this wineserver lacks) */
        char path[256];
        if(hud_newest_conf(path,sizeof(path))!=hud_conf_mtime) load_conf=1;
    }
    if(load_conf) hud_read_conf(&conf);
    pw_hw_sink_stats(&vk_tenths,&vk_fresh,&frames_tenths,&avg_us,&max_us,&frames_fresh);
    memset(&telemetry,0,sizeof(telemetry));
    if(!pw_ps4_telemetry_query(&telemetry,sizeof(telemetry),&returned)) {
        if(telemetry.flags&PW_GPU_VALID) v.gpu_m=(int)telemetry.gpu_millipercent;
        if(telemetry.flags&PW_CPU_VALID) v.cpu_m=(int)telemetry.cpu_millipercent;
    }
    /* RAM: the title's direct memory less its largest free range (the SDK declares the call with its
     * outputs as plain values, platform/ps4/pw_wine_memory.c); with free memory in pieces that is an
     * upper bound of what is in use. VRAM has no measure of its own: the PS4's memory is one. */
    total=(off_t)sceKernelGetDirectMemorySize();
    if(total>0 && !((int32_t (*)(off_t,off_t,size_t,off_t *,size_t *))(uintptr_t)&sceKernelAvailableDirectMemorySize)(
           0,total,0,&found,&direct_free) && (off_t)direct_free<=total)
        v.ram_mib=(long long)((total-(off_t)direct_free)>>20);
    /* FPS: the Vulkan program's presents when it presents, otherwise the output's frames */
    if(vk_fresh && vk_tenths) {v.vk=1;v.fps_tenths=vk_tenths;v.frame_us=(unsigned)(10000000ull/vk_tenths);}
    else if(frames_fresh && frames_tenths) {v.fps_tenths=frames_tenths;v.frame_us=avg_us;}
    pthread_mutex_lock(&lock);
    hud_now=v;
    if(load_conf) hud_conf=conf;
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

/* ---- 04.36: KEY MAPPING, the pad's key profile of the last program opened (C:\orbis\padmaps\<exe>.ini) ----
 * native/hw_pad.c reads that file (pw_hw_pad_profile, W181): "source = key" lines, "#" or ";" comments, "stick = mouse"
 * keeping the left stick as the pointer, "rstick = mouse" the right one as mouse look (W248). This screen edits the
 * key lines of the sources listed below and keeps every other line as it is. A row's key is the name hw_pad.c's
 * profile_vk takes ("" for none); the key picker offers exactly those names. Share has no row in the profile: the
 * system keeps it (the SDK's pad state has no bit for it), and the screen says so. */
#ifndef PADMAP_DIR  /* a host preview points them elsewhere */
#define PADMAP_DIR "/data/wine-prefix/drive_c/orbis/padmaps"
#define PADMAP_DEFAULT_DIR "/data/wine-prefix/drive_c/orbis/padmaps-default"
#endif
enum {MAP_CROSS,MAP_CIRCLE,MAP_SQUARE,MAP_TRIANGLE,MAP_UP,MAP_DOWN,MAP_LEFT,MAP_RIGHT,MAP_L1,MAP_R1,MAP_L2,MAP_R2,MAP_L3,
      MAP_R3,MAP_LS_UP,MAP_LS_DOWN,MAP_LS_LEFT,MAP_LS_RIGHT,MAP_RS_UP,MAP_RS_DOWN,MAP_RS_LEFT,MAP_RS_RIGHT,MAP_OPTIONS,
      MAP_TOUCHPAD,MAP_SHARE,MAPS};
enum {MAP_KEY=16,MAP_BASE=4096};
/* hw_pad.c's profile_sources names (rstick_* since 04.36); group: the list's gaps */
static const struct {const char *source;int group;} map_sources[MAPS]={
    {"cross",0},{"circle",0},{"square",0},{"triangle",0},{"up",1},{"down",1},{"left",1},{"right",1},
    {"l1",2},{"r1",2},{"l2",2},{"r2",2},{"l3",2},{"r3",2},
    {"stick_up",3},{"stick_down",3},{"stick_left",3},{"stick_right",3},
    {"rstick_up",4},{"rstick_down",4},{"rstick_left",4},{"rstick_right",4},
    {"options",5},{"touchpad",5},{NULL,5}};
static const char *const map_labels[LANGS][MAPS]={
    [LANG_ES]={"CRUZ","CÍRCULO","CUADRADO","TRIÁNGULO","CRUCETA ARRIBA","CRUCETA ABAJO","CRUCETA IZQUIERDA",
               "CRUCETA DERECHA","L1","R1","L2","R2","L3 (CLIC STICK IZQ.)","R3 (CLIC STICK DER.)","STICK IZQ. ARRIBA",
               "STICK IZQ. ABAJO","STICK IZQ. IZQUIERDA","STICK IZQ. DERECHA","STICK DER. ARRIBA","STICK DER. ABAJO",
               "STICK DER. IZQUIERDA","STICK DER. DERECHA","OPTIONS","CLIC DEL TOUCHPAD","SHARE"},
    [LANG_EN]={"CROSS","CIRCLE","SQUARE","TRIANGLE","D-PAD UP","D-PAD DOWN","D-PAD LEFT","D-PAD RIGHT","L1","R1","L2",
               "R2","L3 (LEFT STICK CLICK)","R3 (RIGHT STICK CLICK)","LEFT STICK UP","LEFT STICK DOWN","LEFT STICK LEFT",
               "LEFT STICK RIGHT","RIGHT STICK UP","RIGHT STICK DOWN","RIGHT STICK LEFT","RIGHT STICK RIGHT","OPTIONS",
               "TOUCHPAD CLICK","SHARE"}};
/* the key picker, a keyboard of 13 columns: each key's profile name, its label (a string id, or text when -1) and
 * its width in columns; every row fills the 13. The last two rows are the mouse's buttons and wheel */
enum {PICK_COLS=13,PICK_ROWS=9,PICK_ROW_KEYS=14};
struct pick_key {const char *name,*text;int label,cols;};
static const struct pick_key pick_rows[PICK_ROWS][PICK_ROW_KEYS]={
    {{"escape","ESC",-1,1},{"f1","F1",-1,1},{"f2","F2",-1,1},{"f3","F3",-1,1},{"f4","F4",-1,1},{"f5","F5",-1,1},
     {"f6","F6",-1,1},{"f7","F7",-1,1},{"f8","F8",-1,1},{"f9","F9",-1,1},{"f10","F10",-1,1},{"f11","F11",-1,1},
     {"f12","F12",-1,1}},
    {{"1","1",-1,1},{"2","2",-1,1},{"3","3",-1,1},{"4","4",-1,1},{"5","5",-1,1},{"6","6",-1,1},{"7","7",-1,1},
     {"8","8",-1,1},{"9","9",-1,1},{"0","0",-1,1},{"backspace",NULL,S_KEY_BACK,3}},
    {{"tab","TAB",-1,1},{"q","Q",-1,1},{"w","W",-1,1},{"e","E",-1,1},{"r","R",-1,1},{"t","T",-1,1},{"y","Y",-1,1},
     {"u","U",-1,1},{"i","I",-1,1},{"o","O",-1,1},{"p","P",-1,1},{"delete",NULL,S_KEY_DELETE,2}},
    {{"ctrl","CTRL",-1,2},{"a","A",-1,1},{"s","S",-1,1},{"d","D",-1,1},{"f","F",-1,1},{"g","G",-1,1},{"h","H",-1,1},
     {"j","J",-1,1},{"k","K",-1,1},{"l","L",-1,1},{"enter",NULL,S_KEY_ENTER,2}},
    {{"shift",NULL,S_KEY_SHIFT,3},{"z","Z",-1,1},{"x","X",-1,1},{"c","C",-1,1},{"v","V",-1,1},{"b","B",-1,1},
     {"n","N",-1,1},{"m","M",-1,1},{"insert","INS",-1,1},{"home",NULL,S_KEY_HOME,2}},
    {{"alt","ALT",-1,2},{"space",NULL,S_KEY_SPACE,5},{"pageup",NULL,S_KEY_PGUP,2},{"pagedown",NULL,S_KEY_PGDN,2},
     {"end",NULL,S_KEY_END,2}},
    {{"up",NULL,S_KEY_UP,3},{"down",NULL,S_KEY_DOWN,3},{"left",NULL,S_KEY_LEFT,3},{"right",NULL,S_KEY_RIGHT,4}},
    /* the mouse: its buttons where the pointer is, and wheel notches (hw_pad.c profile_send) */
    {{"mouse_left",NULL,S_KEY_MOUSE_LEFT,5},{"mouse_right",NULL,S_KEY_MOUSE_RIGHT,4},{"mouse_middle",NULL,S_KEY_MOUSE_MIDDLE,4}},
    {{"wheel_up",NULL,S_KEY_WHEEL_UP,6},{"wheel_down",NULL,S_KEY_WHEEL_DOWN,7}}};
static int pick_count(int row)
{
    int n=0;
    while(n<PICK_ROW_KEYS && pick_rows[row][n].name) n++;
    return n;
}
static const struct pick_key *pick_find(const char *name,int *row,int *index)
{
    for(int r=0;r<PICK_ROWS;r++)
        for(int k=0;k<pick_count(r);k++)
            if(!strcasecmp(pick_rows[r][k].name,name)) {if(row) *row=r;if(index) *index=k;return &pick_rows[r][k];}
    return NULL;
}
/* a key's label: the picker's, or the name as the file has it (one hw_pad.c ignores keeps its line) */
static const char *pick_label(const char *name,char *buffer,size_t size)
{
    const struct pick_key *key=pick_find(name,NULL,NULL);
    if(key) return key->label>=0?str(key->label):key->text;
    snprintf(buffer,size,"%.15s?",name);  /* a name is at most 15 characters (MAP_KEY) */
    for(char *c=buffer;*c;c++) if(*c>='a' && *c<='z') *c=(char)(*c-'a'+'A');
    return buffer;
}
static char map_program[64];                         /* the program the screen edits, fixed while it is open */
static char map_key[MAPS][MAP_KEY],map_saved[MAPS][MAP_KEY];  /* the pending keys, and the file's */
static char map_base[MAP_BASE],map_base_saved[MAP_BASE];      /* the file's other lines, kept as they are */
static int map_row,map_picking,pick_row,pick_index,map_base_full;
/* lock held: one profile file into keys (lower case) and base (every line that is not a listed source's key line);
 * 0 when there is no file */
static int map_read(const char *path,char keys[MAPS][MAP_KEY],char *base,int *full)
{
    char line[256];
    size_t at=0;
    FILE *file=fopen(path,"r");
    memset(keys,0,sizeof(char[MAPS][MAP_KEY]));base[0]=0;*full=0;
    if(!file) return 0;
    while(fgets(line,sizeof(line),file)) {
        char source[32],key[32];
        int row=-1;
        line[strcspn(line,"\r\n")]=0;
        if(line[0]!='#' && line[0]!=';' && sscanf(line," %31[^= \t] = %31s",source,key)==2)
            for(int i=0;i<MAPS;i++) if(map_sources[i].source && !strcasecmp(source,map_sources[i].source)) row=i;
        if(row>=0 && strlen(key)<MAP_KEY) {
            if(keys[row][0]) fprintf(stderr,"PWOVERLAY keymap: %s named twice in %s, the last line kept\n",source,path);
            for(int c=0;key[c];c++) keys[row][c]=(char)(key[c]>='A' && key[c]<='Z'?key[c]-'A'+'a':key[c]);
            keys[row][strlen(key)]=0;
            continue;
        }
        size_t n=strlen(line);
        if(at+n+2>MAP_BASE) {*full=1;continue;}
        memcpy(base+at,line,n);at+=n;base[at++]='\n';base[at]=0;
    }
    fclose(file);
    return 1;
}
/* base's value for a source ("stick", "rstick"), lower case, "" when it has none */
static void map_base_value(const char *base,const char *name,char *value,size_t size)
{
    char line[256];
    value[0]=0;
    for(const char *at=base;*at;) {
        size_t n=strcspn(at,"\n");
        char source[32],key[32];
        snprintf(line,sizeof(line),"%.*s",(int)n,at);
        at+=n;if(*at) at++;
        if(line[0]=='#' || line[0]==';' || sscanf(line," %31[^= \t] = %31s",source,key)!=2 || strcasecmp(source,name)) continue;
        snprintf(value,size,"%s",key);
        for(char *c=value;*c;c++) if(*c>='A' && *c<='Z') *c=(char)(*c-'A'+'a');
    }
}
static int map_any(int first,int last)
{
    for(int i=first;i<=last;i++) if(map_key[i][0]) return 1;
    return 0;
}
/* lock held: what a row without a key does, as hw_pad.c would with the pending file: the left stick is the pointer with
 * "stick = mouse" (and no direction set), otherwise it sends the arrows once the profile has a key; the right stick is
 * mouse look with "rstick = mouse" (and no direction set) */
static int map_left_mouse(void)
{
    char value[16];
    map_base_value(map_base,"stick",value,sizeof(value));
    return !strcmp(value,"mouse") && !map_any(MAP_LS_UP,MAP_LS_RIGHT);
}
static int map_right_mouse(void)
{
    char value[16];
    map_base_value(map_base,"rstick",value,sizeof(value));
    return !strcmp(value,"mouse") && !map_any(MAP_RS_UP,MAP_RS_RIGHT);
}
static int map_auto_arrows(void)
{
    char value[16];
    map_base_value(map_base,"stick",value,sizeof(value));
    return !map_left_mouse() && (map_any(0,MAPS-1) || value[0]);
}
static int map_dirty(void)
{
    return memcmp(map_key,map_saved,sizeof(map_key)) || strcmp(map_base,map_base_saved);
}
/* lock held: the program's file into the pending and saved keys */
static void map_load(void)
{
    char path[256];
    int found;
    snprintf(path,sizeof(path),PADMAP_DIR "/%s.ini",map_program);
    found=map_read(path,map_saved,map_base_saved,&map_base_full);
    memcpy(map_key,map_saved,sizeof(map_key));memcpy(map_base,map_base_saved,sizeof(map_base));
    int keys=0;
    for(int i=0;i<MAPS;i++) keys+=map_key[i][0]!=0;
    if(pw_trace_on()) fprintf(stderr,"PWOVERLAY keymap program=%s file=%s keys=%d%s\n",map_program,found?"yes":"none",keys,
            map_base_full?" (other lines past 4 KiB not kept: saving refused)":"");
}
/* lock held: X on KEY MAPPING */
static void map_open(void)
{
    const char *name=program_count?programs[program_count-1]:"";
    if(!name[0]) {set_toast(str(S_T_KM_NO_PROGRAM));fprintf(stderr,"PWOVERLAY keymap: no program open\n");return;}
    snprintf(map_program,sizeof(map_program),"%s",name);
    map_load();
    view=VIEW_MAPPER;map_row=0;map_picking=0;
}
/* lock held: the pending mapping into the program's file, then hw_pad.c loads it again. Base's lines stay, except
 * "stick = mouse" once a left stick direction has a key and "rstick = mouse" once a right one has (the keys would
 * not go otherwise). A file left without a source line is removed: the pad works as without a profile. */
static int map_save(void)
{
    char path[256],text[MAP_BASE+MAPS*48+256],line[256],value[16];
    size_t at=0;
    int lines=0,ok;
    if(map_base_full) {fprintf(stderr,"PWOVERLAY keymap not saved: %s.ini has more than 4 KiB of other lines\n",map_program);return 0;}
    snprintf(path,sizeof(path),PADMAP_DIR "/%s.ini",map_program);
    text[0]=0;
    if(!map_base[0])
        at+=(size_t)snprintf(text+at,sizeof(text)-at,"; OrbisDesk pad profile for %s, written by the L3+R3 overlay's KEY MAPPING\n"
                             "; (native/hw_overlay.c); read by native/hw_pad.c. Lines are \"source = key\".\n",map_program);
    for(const char *p=map_base;*p;) {
        size_t n=strcspn(p,"\n");
        char source[32];
        snprintf(line,sizeof(line),"%.*s",(int)n,p);
        p+=n;if(*p) p++;
        if(line[0]!='#' && line[0]!=';' && sscanf(line," %31[^= \t] = %15s",source,value)==2) {
            for(char *c=value;*c;c++) if(*c>='A' && *c<='Z') *c=(char)(*c-'A'+'a');
            if(!strcasecmp(source,"stick") && !strcmp(value,"mouse") && map_any(MAP_LS_UP,MAP_LS_RIGHT)) continue;
            if(!strcasecmp(source,"rstick") && !strcmp(value,"mouse") && map_any(MAP_RS_UP,MAP_RS_RIGHT)) continue;
            lines++;
        }
        at+=(size_t)snprintf(text+at,sizeof(text)-at,"%s\n",line);
    }
    for(int i=0;i<MAPS;i++)
        if(map_key[i][0] && map_sources[i].source) {
            at+=(size_t)snprintf(text+at,sizeof(text)-at,"%s = %s\n",map_sources[i].source,map_key[i]);
            lines++;
        }
    if(!lines) ok=!unlink(path) || errno==ENOENT;
    else {
        FILE *file;
        mkdir(PADMAP_DIR,0777);
        file=fopen(path,"w");
        ok=file && fwrite(text,1,at,file)==at;
        if(file && fclose(file)) ok=0;
    }
    fprintf(stderr,"PWOVERLAY keymap saved program=%s lines=%d %s ok=%d errno=%d\n",map_program,lines,
            lines?"written":"removed",ok,ok?0:errno);
    if(!ok) return 0;
    map_load();
    pw_hw_pad_profile_reload(map_program);  /* the pad thread applies it at its next read */
    return 1;
}
/* lock held: TRIANGLE: the profile OrbisDesk ships for the program, or none; pending until OPTIONS */
static void map_default(void)
{
    char path[256];
    int full,found;
    snprintf(path,sizeof(path),PADMAP_DEFAULT_DIR "/%s.ini",map_program);
    found=map_read(path,map_key,map_base,&full);
    if(full) {map_base[0]=0;fprintf(stderr,"PWOVERLAY keymap: default %s too long, its other lines dropped\n",path);}
    set_toast(str(found?S_T_KM_DEFAULT:S_T_KM_NO_DEFAULT));
    fprintf(stderr,"PWOVERLAY keymap default program=%s file=%s\n",map_program,found?"yes":"none");
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
    if(view!=VIEW_CLOSED && pw_trace_on()) fprintf(stderr,"PWOVERLAY close\n");
    view=VIEW_CLOSED;swallow=1;kb_shift=0;map_picking=0;  /* 04.36: KEY MAPPING's pending keys are dropped */
}
/* 04.31, lock held: every choice back to the value in effect (a choice is only saved with X) */
static void reset_choices(void)
{
    type_choice=pad_type;lang_choice=lang;cursor_choice=cursor_mode;
    render_choice=render_saved>=0?render_saved:0;fps_choice=fps_index(fps_limit);
}
/* 04.31, lock held: a choice item's pending value, how many values it has and the value in effect (-1: none known);
 * NULL for an item that is not a choice */
static int *choice_of(int it,int *count,int *current)
{
    switch(it) {
    case IT_FPS: *count=FPS_CHOICES;*current=fps_index(fps_limit);return &fps_choice;
    case IT_RENDER: *count=RENDERS;*current=render_saved;return &render_choice;
    case IT_CONTROL: *count=TYPES;*current=pad_type;return &type_choice;
    case IT_CURSOR: *count=CURSOR_MODES;*current=cursor_mode;return &cursor_choice;
    case IT_LANG: *count=LANGS;*current=lang;return &lang_choice;
    }
    *count=0;*current=-1;
    return NULL;
}
/* lock held; returns 1 when EXIT's item was chosen (done by the caller without the lock).
 * 04.31: on the rail, up and down choose a section, X or right enters it, O closes the menu. In a section, up and
 * down choose an item; left and right move a choice's value (left on a toggle or an action goes back to the rail);
 * X saves the choice, turns the toggle or does the action; O goes back to the rail. Leaving an item or the section
 * puts its choice back to the value in effect. */
static int panel_input(uint32_t pressed,uint32_t nav)
{
    int it,count,current,*choice;
    if(focus==FOCUS_RAIL) {
        if(nav&NAV_UP) section=(section+SECTIONS-1)%SECTIONS;
        if(nav&NAV_DOWN) section=(section+1)%SECTIONS;
        if(pressed&ORBIS_PAD_BUTTON_CIRCLE) {close_overlay();return 0;}
        if((pressed&ORBIS_PAD_BUTTON_CROSS) || (nav&NAV_RIGHT)) {focus=FOCUS_ITEMS;item=0;reset_choices();}
        return 0;
    }
    if(item>=section_count(section)) item=0;
    it=section_items[section][item];
    choice=choice_of(it,&count,&current);
    if(it==IT_RENDER && render_unavailable()) choice=NULL;  /* a 64-bit program: nothing to choose */
    if(nav&(NAV_UP|NAV_DOWN)) {
        int n=section_count(section);
        item=(item+(nav&NAV_UP?n-1:1))%n;
        reset_choices();
        return 0;
    }
    if(pressed&ORBIS_PAD_BUTTON_CIRCLE) {focus=FOCUS_RAIL;reset_choices();return 0;}
    if(choice && (nav&NAV_LEFT)) {*choice=*choice<=0?0:*choice-1;return 0;}
    if(choice && (nav&NAV_RIGHT)) {*choice=*choice<0?0:*choice>=count-1?count-1:*choice+1;return 0;}
    if(nav&NAV_LEFT) {focus=FOCUS_RAIL;reset_choices();return 0;}
    if(!(pressed&ORBIS_PAD_BUTTON_CROSS)) return 0;
    switch(it) {
    case IT_EXIT: close_overlay();return 1;
    case IT_STATS:
        if(hud_mode()) {
            /* the overlay cannot read MangoHud's state: it says only that the key went */
            if(hud_release_us) break;
            pw_hw_pad_key(VK_SHIFT,1);pw_hw_pad_key(VK_F12,1);
            hud_pressed_us=sceKernelGetProcessTime();hud_presents=pw_wine_vk_presents();
            hud_release_us=hud_pressed_us+HUD_WAIT_US;  /* 04.26: or at the first present past HUD_HOLD_US */
            set_toast(str(S_T_HUD_SENT));
            if(pw_trace_on()) fprintf(stderr,"PWOVERLAY mangohud key sent: Shift+F12 down until a present (%u to %u ms)\n",
                    HUD_HOLD_US/1000,HUD_WAIT_US/1000);
            break;
        }
        /* W261: not turned on over the desktop (a game still loading): silently, only logged */
        if(!stats_on && desktop_front) {fprintf(stderr,"PWOVERLAY stats refused: desktop\n");break;}
        stats_on=!stats_on;stats_next_us=0;
        hud_conf.loaded=0;hud_now.sampled=0;ft_count=ft_head=0;ft_last_us=0;  /* MangoHud.conf read again */
        if(pw_trace_on()) fprintf(stderr,"PWOVERLAY stats=%d\n",stats_on);
        break;
    case IT_KEYBOARD: view=VIEW_KEYBOARD;kb_row=1;kb_col=0;kb_page=0;kb_shift=0;if(pw_trace_on()) fprintf(stderr,"PWOVERLAY keyboard\n");break;
    case IT_KEYMAP: map_open();break;  /* 04.36 */
    case IT_MOUSE: mouse_on=!mouse_on;pw_hw_pad_set_mouse(mouse_on);break;
    case IT_CURSOR: cursor_choose();break;
    case IT_STRETCH: stretch_toggle();break;
    case IT_RENDER:
        if(render_unavailable()) {
            set_toast(str(S_T_RENDER_64));
            fprintf(stderr,"PWOVERLAY render refused: %s is a 64-bit program\n",render_program);
            break;
        }
        render_choose();
        break;
    case IT_FPS: fps_choose();break;
    case IT_FRAMEGEN: framegen_toggle();break;
    case IT_CONTROL: pad_choose();break;
    case IT_LANG:
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
/* 04.36, lock held: KEY MAPPING. In the list, up and down choose a row; X opens the key picker on it, SQUARE clears
 * it, TRIANGLE takes the default profile, OPTIONS saves (only when something changed), O goes back to CONTROLS and
 * drops what was not saved. In the picker, the directions move over the keys, X gives the row that key, SQUARE leaves
 * it without one, O closes the picker. */
static int pick_column(int row,int index)
{
    int col=0;
    for(int k=0;k<index;k++) col+=pick_rows[row][k].cols;
    return col+(pick_rows[row][index].cols-1)/2;
}
static int pick_at_column(int row,int col)
{
    int start=0,n=pick_count(row);
    for(int k=0;k<n;k++) {
        if(col<start+pick_rows[row][k].cols) return k;
        start+=pick_rows[row][k].cols;
    }
    return n-1;
}
static void mapper_input(uint32_t pressed,uint32_t nav)
{
    if(map_picking) {
        if(nav&(NAV_UP|NAV_DOWN)) {
            int col=pick_column(pick_row,pick_index);
            pick_row=(pick_row+(nav&NAV_UP?PICK_ROWS-1:1))%PICK_ROWS;
            pick_index=pick_at_column(pick_row,col);
        }
        if(nav&NAV_LEFT) pick_index=(pick_index+pick_count(pick_row)-1)%pick_count(pick_row);
        if(nav&NAV_RIGHT) pick_index=(pick_index+1)%pick_count(pick_row);
        if(pressed&ORBIS_PAD_BUTTON_CROSS) {
            snprintf(map_key[map_row],MAP_KEY,"%s",pick_rows[pick_row][pick_index].name);
            map_picking=0;
        } else if(pressed&ORBIS_PAD_BUTTON_SQUARE) {map_key[map_row][0]=0;map_picking=0;}
        else if(pressed&ORBIS_PAD_BUTTON_CIRCLE) map_picking=0;
        return;
    }
    if(nav&NAV_UP) map_row=(map_row+MAPS-1)%MAPS;
    if(nav&NAV_DOWN) map_row=(map_row+1)%MAPS;
    if(pressed&ORBIS_PAD_BUTTON_CROSS) {
        if(map_row==MAP_SHARE) {set_toast(str(S_T_KM_SHARE));return;}
        map_picking=1;
        if(!map_key[map_row][0] || !pick_find(map_key[map_row],&pick_row,&pick_index)) {pick_row=3;pick_index=1;}  /* A */
    }
    if((pressed&ORBIS_PAD_BUTTON_SQUARE) && map_row!=MAP_SHARE) map_key[map_row][0]=0;
    if(pressed&ORBIS_PAD_BUTTON_TRIANGLE) map_default();
    if((pressed&ORBIS_PAD_BUTTON_OPTIONS) && map_dirty()) set_toast(str(map_save()?S_T_KM_SAVED:S_T_KM_NOT_SAVED));
    if(pressed&ORBIS_PAD_BUTTON_CIRCLE) {
        if(map_dirty()) fprintf(stderr,"PWOVERLAY keymap program=%s: changes dropped\n",map_program);
        view=VIEW_PANEL;
    }
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
    if(hud_release_us) {  /* 04.26: up at the first present past HUD_HOLD_US, or at HUD_WAIT_US without one */
        unsigned presents=pw_wine_vk_presents()-hud_presents;
        if(now>=hud_release_us || (presents && now-hud_pressed_us>=HUD_HOLD_US)) {
            pw_hw_pad_key(VK_F12,0);pw_hw_pad_key(VK_SHIFT,0);hud_release_us=0;
            if(pw_trace_on()) fprintf(stderr,"PWOVERLAY mangohud key up: %u ms, %u presents%s\n",(unsigned)((now-hud_pressed_us)/1000),
                    presents,presents?"":" (none: MangoHud did not read it)");
        }
    }
    if(exit_pending && now>=exit_deadline_us) {  /* W239: no closer took it, or it gave no result */
        fprintf(stderr,"PWOVERLAY exit %s\n",exit_pending==1?"not taken: no closer answered":"no result from the closer");
        set_toast(str(exit_pending==1?S_T_NOT_TAKEN:S_T_NO_RESULT));
        exit_pending=0;changed=1;
    }
    /* W293: the starting pointer's next frame, or its end after BUSY_US */
    if(busy_since_us && now-busy_since_us>=BUSY_US) changed|=busy_end("timeout",NULL,NULL);
    else if(busy_since_us && now>=busy_next_us) {busy_next_us=now+BUSY_FRAME_US;changed=1;}
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
            /* 04.36: on the rail, always at PERFORMANCE (04.31 kept the last section, mostly EXIT after closing a game) */
            view=VIEW_PANEL;focus=FOCUS_RAIL;section=SEC_PERF;item=0;reset_choices();
            if(pw_trace_on()) fprintf(stderr,"PWOVERLAY open\n");
        } else close_overlay();
        changed=1;
    } else if(view==VIEW_PANEL && (pressed || nav)) {exit_chosen=panel_input(pressed,nav);changed=1;}
    else if(view==VIEW_KEYBOARD && (pressed || nav)) {keyboard_input(pressed,nav);changed=1;}
    else if(view==VIEW_MAPPER && (pressed || nav)) {mapper_input(pressed,nav);changed=1;}  /* 04.36 */
    mine=view!=VIEW_CLOSED || swallow;
    if(swallow && view==VIEW_CLOSED && !buttons) swallow=0;
    if(toast_until_us && now>=toast_until_us) {toast_until_us=0;changed=1;}
    want_stats=stats_on && now>=stats_next_us;
    if(want_stats) stats_next_us=now+STATS_US;
    /* GENERAR CUADROS keeps MangoHud's rectangle out (pw_hw_overlay_hud_rect): MangoHud.conf is read, and read again
     * when MangoJuice saves it, every few seconds while MangoHud draws on a program that has it on */
    int want_conf=!want_stats && framegen_on && mangohud_loaded && now>=hud_conf_next_us,conf_loaded=hud_conf.loaded;
    if(want_conf) hud_conf_next_us=now+HUD_CONF_US;
    pthread_mutex_unlock(&lock);
    if(want_stats) {sample_stats();changed=1;}
    if(want_conf) {
        char path[256];
        if(!conf_loaded || hud_newest_conf(path,sizeof(path))!=hud_conf_mtime) {
            struct hud_conf conf;
            hud_read_conf(&conf);
            pthread_mutex_lock(&lock);hud_conf=conf;pthread_mutex_unlock(&lock);
        }
    }
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
static const struct {unsigned short c;unsigned char rows[7];} extra_glyphs[]={
    {0xa1,{4,0,4,4,4,4,4}},{0xbf,{4,0,4,8,16,17,14}},  /* W294: ¡ ¿ */
    {'!',{4,4,4,4,4,0,4}},{'"',{10,10,10,0,0,0,0}},{'#',{10,10,31,10,31,10,10}},{'$',{4,15,20,14,5,30,4}},
    {'&',{12,18,20,8,21,18,13}},{'\'',{12,4,8,0,0,0,0}},{'(',{2,4,8,8,8,4,2}},{')',{8,4,2,2,2,4,8}},
    {'*',{0,4,21,14,21,4,0}},{'+',{0,4,4,31,4,4,0}},{',',{0,0,0,0,12,4,8}},{';',{0,12,12,0,12,4,8}},
    {'<',{2,4,8,16,8,4,2}},{'=',{0,0,31,0,31,0,0}},{'>',{8,4,2,1,2,4,8}},{'?',{14,17,1,2,4,0,4}},
    {'@',{14,17,1,13,21,21,14}},{'[',{14,8,8,8,8,8,14}},{'\\',{16,8,8,4,2,2,1}},{']',{14,2,2,2,2,2,14}},
    {'^',{4,10,17,0,0,0,0}},{'_',{0,0,0,0,0,0,31}},{'`',{8,4,2,0,0,0,0}},{'{',{2,4,4,8,4,4,2}},
    {'|',{4,4,4,4,4,4,4}},{'}',{8,4,4,2,4,4,8}},{'~',{0,0,8,21,2,0,0}}};
/* W294: Latin-1 letters Spanish needs: the base letter's glyph and a mark of two rows, drawn above a capital (rows -2
 * and -1, so it keeps its height) and over a lowercase letter one row lower (rows -1 and 0, row 1 free; í loses its dot) */
enum {MARK_ACUTE,MARK_TILDE,MARK_DIAERESIS};
static const unsigned char marks[3][2]={{2,4},{13,22},{0,10}};
static const struct {unsigned short c;char base;unsigned char mark;} marked_glyphs[]={
    {0xc1,'A',MARK_ACUTE},{0xc9,'E',MARK_ACUTE},{0xcd,'I',MARK_ACUTE},{0xd3,'O',MARK_ACUTE},{0xda,'U',MARK_ACUTE},
    {0xd1,'N',MARK_TILDE},{0xdc,'U',MARK_DIAERESIS},
    {0xe1,'a',MARK_ACUTE},{0xe9,'e',MARK_ACUTE},{0xed,'i',MARK_ACUTE},{0xf3,'o',MARK_ACUTE},{0xfa,'u',MARK_ACUTE},
    {0xf1,'n',MARK_TILDE},{0xfc,'u',MARK_DIAERESIS}};
static const unsigned char *glyph(unsigned c)
{
    if(c>='A' && c<='Z') return hw_glyphs[c-'A'];
    if(c>='0' && c<='9') return hw_glyphs[26+c-'0'];
    if(c>='a' && c<='z') return lower_glyphs[c-'a'];
    switch(c) {case ':':return hw_glyphs[36];case '-':return hw_glyphs[37];case '.':return hw_glyphs[38];
               case '/':return hw_glyphs[39];case '%':return hw_glyphs[40];}
    for(unsigned i=0;i<sizeof(extra_glyphs)/sizeof(extra_glyphs[0]);i++) if(extra_glyphs[i].c==c) return extra_glyphs[i].rows;
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
/* W294: the next character of UTF-8 text: one byte (ASCII) or two (up to U+07FF, Latin-1 included); a longer or
 * broken sequence is one "?" */
static unsigned next_char(const char **t)
{
    const unsigned char *p=(const unsigned char *)*t;
    if(p[0]<0x80) {*t+=1;return p[0];}
    if((p[0]&0xe0)==0xc0 && (p[1]&0xc0)==0x80) {*t+=2;return (unsigned)(p[0]&0x1f)<<6|(p[1]&0x3f);}
    p++;
    while((*p&0xc0)==0x80) p++;
    *t=(const char *)p;
    return '?';
}
static int text_width(const char *t,int scale)
{
    int n=0;
    while(*t) {next_char(&t);n++;}
    return n?(n*6-1)*scale:0;
}
static void glyph_rows(const struct surface *s,int x,int y,const unsigned char *rows,int first,int count,uint32_t color,int scale)
{
    for(int r=0;r<count;r++)
        for(int col=0;col<5;col++) if(rows[r]&(1<<(4-col))) fill(s,x+col*scale,y+(first+r)*scale,scale,scale,color);
}
static void text(const struct surface *s,int x,int y,const char *t,uint32_t color,int scale)
{
    for(;*t;x+=6*scale) {
        unsigned c=next_char(&t);
        const unsigned char *g=glyph(c),*mark=NULL;
        int lower=0;
        for(unsigned i=0;i<sizeof(marked_glyphs)/sizeof(marked_glyphs[0]);i++)
            if(marked_glyphs[i].c==c) {
                g=glyph((unsigned char)marked_glyphs[i].base);mark=marks[marked_glyphs[i].mark];
                lower=marked_glyphs[i].base>='a';
            }
        if(!g) continue;
        if(lower) glyph_rows(s,x,y,g+2,2,5,color,scale);  /* the mark takes the top rows */
        else glyph_rows(s,x,y,g,0,7,color,scale);
        if(mark) glyph_rows(s,x,y,mark,lower?-1:-2,2,color,scale);  /* a lowercase one: rows -1 and 0, row 1 left free */
    }
}
/* words wrapped to columns characters (W294: characters, not bytes); returns the y below the last line */
static int wrapped(const struct surface *s,int x,int y,int columns,const char *t,uint32_t color,int scale,int bottom)
{
    char line[160];
    while(*t && y+7*scale<=bottom) {
        const char *at=t,*cut=NULL;
        int n=0;
        while(*at && n<columns) {if(*at==' ') cut=at;next_char(&at);n++;}
        if(*at && cut) at=cut;
        size_t bytes=(size_t)(at-t);
        if(bytes>=sizeof(line)) bytes=sizeof(line)-1;
        memcpy(line,t,bytes);line[bytes]=0;
        text(s,x,y,line,color,scale);
        t+=bytes;while(*t==' ') t++;
        y+=7*scale+5;
    }
    return y;
}
/* 04.31: the native Steam client's colours (native/steam/steam_ui.c): its page, band, highlight and accent */
enum {C_PANEL=0xff1b2838,C_RAIL=0xff171a21,C_EDGE=0xff66c0f4,C_ITEM=0xff22303d,C_SELECTED=0xff2a475e,C_TEXT=0xffffffff,
      C_DIM=0xff8f98a0,C_ON=0xff5be36a,C_OFF=0xffff6a6a,C_TRACK=0xff3d4c5c,C_KEY=0xff2a3f50,C_KEYSEL=0xff3d7ab0,
      C_BLACK=0xff000000};
/* 04.31: the rail's icons, 16x16, drawn at twice that */
static const char *const icons[SECTIONS][16]={
    [SEC_PERF]={  /* a lightning bolt */
        "..........####..",".........####...","........####....",".......####.....","......####......",
        ".....####.......","....##########..","...##########...","......####......",".....####.......",
        "....####........","...####.........","..###...........","..##............",".#..............",
        "................"},
    [SEC_GRAPHICS]={  /* a monitor */
        "................","################","#..............#","#..............#","#..............#",
        "#..............#","#..............#","#..............#","#..............#","#..............#",
        "################","......####......","......####......","...##########...","...##########...",
        "................"},
    [SEC_CONTROLS]={  /* a gamepad */
        "................","................","................","..####....####..",".##############.",
        "####.######.####","###...####.#.###","####.######.####","################","################",
        "######....######","#####......#####",".###........###.","................","................",
        "................"},
    [SEC_SYSTEM]={  /* a gear */
        "......####......","..##..####..##..",".####.####.####.","..############..","...####..####...",
        "####..........##","####..........##","..##..........##","..##..........##","####..........##",
        "####..........##","...####..####...","..############..",".####.####.####.","..##..####..##..",
        "......####......"},
    [SEC_EXIT]={  /* a power symbol */
        ".......##.......",".......##.......","...##..##..##...","..##...##...##..",".##....##....##.",
        ".#.....##.....#.","##.....##.....##","##............##","##............##","##............##",
        ".#............#.",".##..........##.","..##........##..","...##......##...",".....######.....",
        "................"}};
static void icon(const struct surface *s,int x,int y,const char *const rows[16],uint32_t color,int scale)
{
    for(int r=0;r<16;r++)
        for(int c=0;c<16;c++) if(rows[r][c]=='#') fill(s,x+c*scale,y+r*scale,scale,scale,color);
}
/* a rectangle with its corners cut: the toggles' and the knob's rounded look */
static void pill(const struct surface *s,int x,int y,int w,int h,uint32_t color)
{
    fill(s,x+2,y,w-4,h,color);fill(s,x+1,y+1,w-2,h-2,color);fill(s,x,y+2,w,h-4,color);
}
/* a toggle at the right of an item: the track in the accent colour and the knob right when on */
static void toggle(const struct surface *s,int right,int y,int on)
{
    enum {TW=44,TH=22,KNOB=16};
    int x=right-TW;
    pill(s,x,y,TW,TH,on?C_EDGE:C_TRACK);
    pill(s,on?x+TW-3-KNOB:x+3,y+3,KNOB,KNOB,on?C_TEXT:C_DIM);
}
/* a choice as a slider of steps (as the Steam Deck's): a track, a tick for each value in the middle of its cell, the
 * knob on the pending value and the track filled up to it; under each tick its name, in the accent colour for the
 * value in effect and in white for the pending one */
static void slider(const struct surface *s,int x,int w,int y,const char *const *names,int count,int pending,int current)
{
    int cell=w/count,knob_x=-1;
    if(pending>=0 && pending<count) knob_x=x+cell*pending+cell/2;
    fill(s,x,y-1,w,3,C_TRACK);
    if(knob_x>=0) fill(s,x,y-1,knob_x-x,3,C_EDGE);
    for(int i=0;i<count;i++) {
        int tx=x+cell*i+cell/2,tw=text_width(names[i],2);
        fill(s,tx-1,y-6,3,13,i<=pending?C_EDGE:C_TRACK);
        text(s,tx-tw/2,y+14,names[i],i==current?C_EDGE:i==pending?C_TEXT:C_DIM,2);
    }
    if(knob_x>=0) {pill(s,knob_x-8,y-8,16,16,C_TEXT);}
}
/* lock held: a choice item's names, short enough for a slider's cells */
static void choice_names(int it,const char **names)
{
    switch(it) {
    case IT_FPS: names[0]=str(S_OFF);names[1]=fps_words[1];names[2]=fps_words[2];names[3]=str(S_FPS_AUTO);break;
    case IT_RENDER: for(int r=0;r<RENDERS;r++) names[r]=render_short[r];break;
    case IT_CONTROL: names[0]=type_name(TYPE_GENERIC);names[1]="360";names[2]="ONE";names[3]=type_name(TYPE_DUALSENSE);break;
    case IT_CURSOR: for(int m=0;m<CURSOR_MODES;m++) names[m]=str(cursor_names[m]);break;
    case IT_LANG: for(int l=0;l<LANGS;l++) names[l]=lang_names[l];break;
    }
}
/* lock held: the pending choice's full name, at the right of its item's name */
static const char *choice_value(int it,int pending)
{
    const char *names[8]={0};
    if(pending<0) return "--";
    if(it==IT_RENDER) return str(render_names[pending]);
    if(it==IT_CONTROL) return type_name(pending);
    choice_names(it,names);
    return names[pending]?names[pending]:"--";
}
/* lock held: an item's help, and the buttons it answers (the band at the bottom) */
static const char *item_help(int it,int alone,int hud)
{
    if(it==IT_STATS && hud) return str(S_HELP_STATS_HUD);
    if(it==IT_EXIT && alone) return str(S_HELP_EXIT_ALONE);
    return str(item_info[it].help);
}
static const char *item_buttons(int it,int hud)
{
    int count,current,*choice=choice_of(it,&count,&current);
    if(it==IT_RENDER && render_unavailable()) return str(S_FOOT_BACK);
    if(choice) return str(*choice!=current?S_FOOT_SAVE:S_FOOT_CHOICE);
    if(it==IT_STATS && hud) return str(S_FOOT_HUD);
    if(it==IT_KEYBOARD || it==IT_KEYMAP) return str(S_FOOT_OPEN);
    if(it==IT_EXIT) return str(S_FOOT_EXIT);
    return str(S_FOOT_TOGGLE);
}
/* 04.31: flush with the output's top, right and bottom edges, an accent edge on the left. The rail of section icons
 * (EXIT at its foot), the section's title and, for per-program sections, the program its settings are saved for (the
 * last program opened that is still open, as before), then the items; at the bottom the band of the Steam client's
 * pages, under an accent rule: the selected item's help, and the buttons on its last line */
static void draw_panel(const struct surface *s,int alone,int hud)
{
    enum {W=540,RAIL=64,EDGE=2,CELL=56,FOOT_H=150,ROW_H=44,CHOICE_H=80,GAP=6,PAD=8};
    int x0=s->width-W,h=s->height,foot=h-FOOT_H,cx=x0+RAIL+PAD,cw=W-RAIL-2*PAD,y;
    int count=section_count(section),in_items=focus==FOCUS_ITEMS;
    fill(s,x0,0,EDGE,h,C_EDGE);fill(s,x0+EDGE,0,W-EDGE,h,C_PANEL);
    /* the rail */
    fill(s,x0+EDGE,0,RAIL-EDGE,foot,C_RAIL);
    for(int sec=0;sec<SECTIONS;sec++) {
        int cy=sec==SEC_EXIT?foot-CELL-8:8+sec*CELL,selected=sec==section;
        if(selected) {
            fill(s,x0+EDGE,cy,RAIL-EDGE,CELL,in_items?C_ITEM:C_SELECTED);
            fill(s,x0+EDGE,cy,4,CELL,C_EDGE);
        }
        icon(s,x0+(RAIL+EDGE)/2-16,cy+(CELL-32)/2,icons[sec],selected?C_TEXT:sec==SEC_EXIT?C_OFF:C_DIM,2);
    }
    /* the title and the program */
    text(s,cx+8,18,str(section_names[section]),C_TEXT,3);
    hw_text(s->pixels,(int)s->pitch,s->height,x0+W-16-text_width("ORBISDESK  L3+R3",2),22,"ORBISDESK",C_DIM,2);
    text(s,x0+W-16-text_width("L3+R3",2),22,"L3+R3",C_DIM,2);
    y=54;
    if(section_per_program[section]) {
        char line[96];
        const char *name=section==SEC_GRAPHICS && render_program[0]?render_program:program_count?programs[program_count-1]:"--";
        snprintf(line,sizeof(line),"%s %s",str(S_CURSOR_PROGRAM),name);
        text(s,cx+8,y+4,line,C_DIM,2);
        y+=30;
    }
    fill(s,cx,y,cw,1,C_ITEM);
    y+=GAP;
    /* the items */
    for(int i=0;i<count;i++) {
        int it=section_items[section][i],off=it==IT_RENDER && render_unavailable();  /* 04.31: a 64-bit program */
        int kind=item_info[it].kind,rh=kind==KIND_CHOICE && !off?CHOICE_H:ROW_H;
        int selected=in_items && i==item,right=cx+cw-12;
        const char *name=str(item_info[it].name);
        if(it==IT_EXIT && alone) name=str(S_ITEM_EXIT_ALONE);
        if(selected) fill(s,cx,y,cw,rh,C_SELECTED);
        text(s,cx+12,y+15,name,it==IT_EXIT?C_OFF:off?C_DIM:C_TEXT,2);
        if(off) text(s,right-text_width(str(S_RENDER_32_ONLY),2),y+15,str(S_RENDER_32_ONLY),C_DIM,2);
        else if(kind==KIND_CHOICE) {
            const char *names[8]={0};
            int n,current,*choice=choice_of(it,&n,&current),pending=*choice;
            const char *value=choice_value(it,pending>=0 && pending<n?pending:current);
            choice_names(it,names);
            text(s,right-text_width(value,2),y+15,value,pending!=current?C_EDGE:C_TEXT,2);
            slider(s,cx+16,cw-32,y+44,names,n,pending>=0 && pending<n?pending:current,current);
        } else if(kind==KIND_TOGGLE) {
            if(it==IT_STATS && hud) text(s,right-text_width("MANGOHUD",2),y+15,"MANGOHUD",C_ON,2);
            else toggle(s,right,y+11,it==IT_STATS?stats_on:it==IT_MOUSE?mouse_on:it==IT_STRETCH?stretch_on:framegen_on);
        } else text(s,right-text_width(">",2),y+15,">",selected?C_TEXT:C_DIM,2);
        y+=rh;
        fill(s,cx,y+GAP/2,cw,1,C_ITEM);
        y+=GAP;
    }
    /* the band: an accent rule, the help of the item selected (on the rail, of the section's first item), the buttons */
    fill(s,x0+EDGE,foot,W-EDGE,2,C_EDGE);
    fill(s,x0+EDGE,foot+2,W-EDGE,FOOT_H-2,C_RAIL);
    {
        int it=section_items[section][in_items && item<count?item:0];
        wrapped(s,x0+16,foot+14,(W-32)/12,item_help(it,alone,hud),C_DIM,2,h-40);
        text(s,x0+16,h-28,in_items?item_buttons(it,hud):str(S_FOOT_RAIL),C_TEXT,2);
    }
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
/* MangoHud's default colours (overlay_params.cpp) */
enum {HUD_BG=0xff020202,HUD_TEXT=0xffffffff,HUD_GPU=0xff2e9762,HUD_CPU=0xff2e97cb,HUD_VRAM=0xffad64c1,
      HUD_RAM=0xffc26693,HUD_ENGINE=0xffeb5b5b,HUD_FRAMETIME=0xff00ff00};
/* background_alpha without reading the output back: of each 2x2 block of pixels, alpha in quarters
 * take the background colour and the rest keep the picture; 0.5, MangoHud's default, is a checkerboard */
static void hud_background(const struct surface *s,int x,int y,int w,int h,int alpha_pct)
{
    static const int rank[4]={0,2,3,1};  /* (row&1)*2+(column&1): the diagonal first */
    int quarters=(alpha_pct*4+50)/100;
    if(quarters<=0) return;
    if(quarters>=4) {fill(s,x,y,w,h,HUD_BG);return;}
    for(int r=y<0?0:y;r<y+h && r<s->height;r++) {
        uint32_t *row=s->pixels+(size_t)r*s->pitch;
        for(int c=x<0?0:x;c<x+w && c<s->width;c++) if(rank[(r&1)*2+(c&1)]<quarters) row[c]=HUD_BG;
    }
}
/* text with a 1 px shadow in the background colour: the dither alone leaves bright pictures showing
 * through every other pixel, where blending would have darkened them */
static void hud_text(const struct surface *s,int x,int y,const char *t,uint32_t color,int scale)
{
    text(s,x+1,y+1,t,HUD_BG,scale);text(s,x,y,t,color,scale);
}
/* a value whose right edge, its unit included, is at right; the unit smaller and raised, as MangoHud's */
static void hud_value(const struct surface *s,int right,int y,const char *value,const char *unit,int scale,int small)
{
    int unit_w=value[0]=='-' || !unit?0:text_width(unit,small)+scale;
    hud_text(s,right-unit_w-text_width(value,scale),y,value,HUD_TEXT,scale);
    if(unit_w) hud_text(s,right-unit_w+scale,y,unit,HUD_TEXT,small);
}
static void hud_percent(char *out,size_t size,int millipercent)
{
    if(millipercent<0) snprintf(out,size,"--");
    else snprintf(out,size,"%d.%d",millipercent/1000,millipercent/100%10);
}
static void hud_line(const struct surface *s,int x0,int y0,int x1,int y1,uint32_t color)
{
    int dx=x1>x0?x1-x0:x0-x1,dy=y1>y0?y0-y1:y1-y0,sx=x0<x1?1:-1,sy=y0<y1?1:-1,e=dx+dy;
    for(;;) {
        fill(s,x0,y0,2,2,color);  /* MangoHud's line is 1.5 px */
        if(x0==x1 && y0==y1) break;
        int e2=2*e;
        if(e2>=dy) {e+=dy;x0+=sx;}
        if(e2<=dx) {e+=dx;y0+=sy;}
    }
}
/* lock held. MangoHud's legacy layout (hud_elements.cpp): a table of 3 columns, font_size*4.6 wide
 * each, one row per stat; its 24 px font is the 5x7 glyphs at 2x, the small font (0.55) at 1x.
 * Margin 10 px from the corner and 5 px of padding inside (overlay.cpp). */
enum {HUD_MARGIN=10,HUD_PADDING=5,HUD_GRAPH_H=50};
/* the readout's box, laid out as MangoHud's from MangoHud.conf, in a width x height picture; 0 with no rows */
static int hud_box(const struct hud_conf *c,int width,int height,int *x0,int *y0,int *pw,int *ph)
{
    int fs=c->font_size,small=(fs*55/100+6)/12;
    if(small<1) small=1;
    int w=fs*3*46/10,h=(c->gpu+c->cpu+c->vram+c->ram+c->fps)*fs+(c->frame_timing?fs/2+7*small+fs/4+HUD_GRAPH_H:0);
    if(!h) return 0;
    *pw=w+2*HUD_PADDING;*ph=h+2*HUD_PADDING;
    switch(c->position) {
    case POS_TOP_RIGHT: case POS_MIDDLE_RIGHT: case POS_BOTTOM_RIGHT: *x0=width-HUD_MARGIN-*pw;break;
    case POS_TOP_CENTER: case POS_BOTTOM_CENTER: *x0=(width-*pw)/2;break;
    default: *x0=HUD_MARGIN;
    }
    switch(c->position) {
    case POS_MIDDLE_LEFT: case POS_MIDDLE_RIGHT: *y0=(height-*ph)/2;break;
    case POS_BOTTOM_LEFT: case POS_BOTTOM_RIGHT: case POS_BOTTOM_CENTER: *y0=height-HUD_MARGIN-*ph;break;
    default: *y0=HUD_MARGIN;
    }
    *x0+=c->offset_x;*y0+=c->offset_y;
    return 1;
}
/* Frame generation (stage 5, the presenting thread): where MangoHud draws in the program's width x height image, while
 * MangoHud draws on the program in front: 1 and x0,y0,x1,y1 in rect, else 0. The generated frame takes that rectangle
 * unchanged from the real one. The box is this readout's imitation of MangoHud's layout (MangoHud.conf's rows,
 * place, offsets and font_size, as MangoJuice saves them for every HUD), widened by half and 16 pixels each way,
 * since MangoHud's own text widths and graph are not known here. The HUD's visibility (Shift+F12) is not known
 * either: the rectangle is kept out whether it shows or not. Before MangoHud.conf is read: MangoHud's defaults. */
int pw_hw_overlay_hud_rect(unsigned width,unsigned height,int *rect);
int pw_hw_overlay_hud_rect(unsigned width,unsigned height,int *rect)
{
    struct hud_conf c;
    int x0,y0,pw,ph,loaded;
    pthread_mutex_lock(&lock);
    loaded=mangohud_loaded;c=hud_conf;
    pthread_mutex_unlock(&lock);
    if(!loaded) return 0;
    if(!c.loaded) c=(struct hud_conf){.loaded=1,.gpu=1,.cpu=1,.fps=1,.frametime=1,.frame_timing=1,.font_size=24,.alpha_pct=50};
    if(!hud_box(&c,(int)width,(int)height,&x0,&y0,&pw,&ph)) return 0;
    int grow_w=pw/4+16,grow_h=ph/4+16;
    if(c.position==POS_TOP_RIGHT || c.position==POS_MIDDLE_RIGHT || c.position==POS_BOTTOM_RIGHT) x0-=2*grow_w;
    else if(c.position==POS_TOP_CENTER || c.position==POS_BOTTOM_CENTER) x0-=grow_w;
    rect[0]=x0-16;rect[1]=y0-grow_h;rect[2]=x0+pw+2*grow_w;rect[3]=y0+ph+grow_h;
    for(int i=0;i<4;i++) {
        int limit=i%2?(int)height:(int)width;
        if(rect[i]<0) rect[i]=0;
        if(rect[i]>limit) rect[i]=limit;
    }
    return rect[2]>rect[0] && rect[3]>rect[1];
}
static void draw_stats(const struct surface *s)
{
    enum {GRAPH_MAX_US=50000,PADDING=HUD_PADDING,GRAPH_H=HUD_GRAPH_H};
    const struct hud_conf *c=&hud_conf;const struct hud_values *v=&hud_now;
    int fs=c->font_size,scale=(fs+6)/12,small=(fs*55/100+6)/12,row=fs,ty,x,y,x0,y0,pw,ph;
    if(scale<1) scale=1;
    if(small<1) small=1;
    int width=fs*3*46/10,col=width/3,frametime=c->fps && c->frametime;
    char value[48],other[24];
    if(!hud_box(c,s->width,s->height,&x0,&y0,&pw,&ph)) return;
    hud_background(s,x0,y0,pw,ph,c->alpha_pct);
    x=x0+PADDING;y=y0+PADDING;ty=(row-7*scale)/2;
    if(c->gpu) {
        hud_text(s,x,y+ty,"GPU",HUD_GPU,scale);hud_percent(value,sizeof(value),v->gpu_m);
        hud_value(s,x+2*col,y+ty,value,"%",scale,small);y+=row;
    }
    if(c->cpu) {
        hud_text(s,x,y+ty,"CPU",HUD_CPU,scale);hud_percent(value,sizeof(value),v->cpu_m);
        hud_value(s,x+2*col,y+ty,value,"%",scale,small);y+=row;
    }
    if(c->vram) {hud_text(s,x,y+ty,"VRAM",HUD_VRAM,scale);hud_value(s,x+2*col,y+ty,"--",NULL,scale,small);y+=row;}
    if(c->ram) {
        hud_text(s,x,y+ty,"RAM",HUD_RAM,scale);
        if(v->ram_mib<0) snprintf(value,sizeof(value),"--");
        else snprintf(value,sizeof(value),"%lld.%lld",v->ram_mib/1024,v->ram_mib*10/1024%10);
        hud_value(s,x+2*col,y+ty,value,"GiB",scale,small);y+=row;
    }
    if(c->fps) {
        /* MangoHud names the program's API; here Vulkan's presents or the output's own frames */
        hud_text(s,x,y+ty,v->vk?"VULKAN":lang==LANG_EN?"OUTPUT":"SALIDA",HUD_ENGINE,scale);
        if(v->fps_tenths) snprintf(value,sizeof(value),"%u",(v->fps_tenths+5)/10);
        else snprintf(value,sizeof(value),"--");
        hud_value(s,x+2*col,y+ty,value,"FPS",scale,small);
        if(frametime) {
            if(v->frame_us) snprintf(value,sizeof(value),"%u.%u",v->frame_us/1000,v->frame_us/100%10);
            else snprintf(value,sizeof(value),"--");
            hud_value(s,x+3*col,y+ty,value,"ms",scale,small);
        }
        y+=row;
    }
    if(!c->frame_timing) return;
    /* the graph: the intervals between this output's frames, 0 to 50 ms, oldest at the left */
    uint32_t low=UINT32_MAX,high=0;
    for(int i=0;i<ft_count;i++) {
        uint32_t us=ft_us[(ft_head-ft_count+i+FT_SAMPLES)%FT_SAMPLES];
        if(us<low) low=us;
        if(us>high) high=us;
    }
    y+=fs/2;
    hud_text(s,x,y,"Frametime",HUD_ENGINE,small);
    if(ft_count) {
        snprintf(other,sizeof(other),"%u.%ums",high/1000,high/100%10);
        snprintf(value,sizeof(value),"min: %u.%ums, max: %s",low/1000,low/100%10,other);
    } else snprintf(value,sizeof(value),"min: --, max: --");
    hud_text(s,x+width-text_width(value,small),y,value,HUD_TEXT,small);
    y+=7*small+fs/4;
    for(int i=0,px=0,py=0;i<ft_count;i++) {
        uint32_t us=ft_us[(ft_head-ft_count+i+FT_SAMPLES)%FT_SAMPLES];
        if(us>GRAPH_MAX_US) us=GRAPH_MAX_US;
        int nx=x+(int)((long)i*(width-2)/(FT_SAMPLES-1)),ny=y+GRAPH_H-2-(int)((long)us*(GRAPH_H-2)/GRAPH_MAX_US);
        hud_line(s,i?px:nx,i?py:ny,nx,ny,HUD_FRAMETIME);
        px=nx;py=ny;
    }
}
/* ---- 04.36: KEY MAPPING's screen: the whole output. A DualShock 4 drawn at the left, with the row chosen in the list
 * at the right lit and joined to it by a line, as the button pictures of PC games' controller settings; the band of
 * the Steam client's pages at the bottom, as in the menu ---- */
enum {KM_BODY=0xff2a3a4a,KM_BODY_EDGE=0xff3d4c5c,KM_FREE=0xff4a5b6c,KM_SET=0xffc7d5e0,KM_SYSTEM=0xff34404d,
      KM_PAD_FREE=0xff2c3b49,KM_PAD_SET=0xff5d7183,KM_CROSS=0xff7ca9e0,KM_CIRCLE=0xffe8636b,KM_SQUARE=0xffd78fc8,
      KM_TRIANGLE=0xff3fcfa6};
static void disc(const struct surface *s,int cx,int cy,int r,uint32_t color)
{
    for(int dy=-r;dy<=r;dy++) {
        int w=r;
        while(w>0 && w*w+dy*dy>r*r) w--;
        fill(s,cx-w,cy+dy,2*w+1,1,color);
    }
}
static void rounded(const struct surface *s,int x,int y,int w,int h,int r,uint32_t color)
{
    if(2*r>w) r=w/2;
    if(2*r>h) r=h/2;
    fill(s,x+r,y,w-2*r,h,color);fill(s,x,y+r,w,h-2*r,color);
    disc(s,x+r,y+r,r,color);disc(s,x+w-1-r,y+r,r,color);disc(s,x+r,y+h-1-r,r,color);disc(s,x+w-1-r,y+h-1-r,r,color);
}
/* the face buttons' marks, about 14 pixels across */
static void face_mark(const struct surface *s,int x,int y,int row,uint32_t color,uint32_t inside)
{
    switch(row) {
    case MAP_CROSS: hud_line(s,x-6,y-6,x+5,y+5,color);hud_line(s,x-6,y+5,x+5,y-6,color);break;
    case MAP_CIRCLE: disc(s,x,y,7,color);disc(s,x,y,5,inside);break;
    case MAP_SQUARE: fill(s,x-6,y-6,13,13,color);fill(s,x-4,y-4,9,9,inside);break;
    case MAP_TRIANGLE: hud_line(s,x,y-7,x-7,y+5,color);hud_line(s,x,y-7,x+6,y+5,color);hud_line(s,x-7,y+5,x+6,y+5,color);break;
    }
}
/* a stick direction's mark: a wedge pointing out, its tip at x,y */
static void wedge(const struct surface *s,int x,int y,int dx,int dy,uint32_t color)
{
    for(int i=0;i<9;i++) {
        if(dx) fill(s,x-dx*i,y-i,1,2*i+1,color);
        else fill(s,x-i,y-dy*i,2*i+1,1,color);
    }
}
/* lock held: a row's colour on the picture: chosen, given a key, or free */
static uint32_t km_colour(int row)
{
    if(row==map_row) return C_EDGE;
    if(row==MAP_SHARE) return KM_SYSTEM;
    return map_key[row][0]?KM_SET:KM_FREE;
}
/* where each row's line ends, from the picture's centre */
static const short km_anchor[MAPS][2]={
    {160,-16},{192,-48},{128,-48},{160,-80},{-160,-78},{-160,-18},{-190,-48},{-130,-48},
    {-165,-133},{165,-133},{-165,-166},{165,-166},{-80,36},{80,36},
    {-80,-6},{-80,78},{-122,36},{-38,36},{80,-6},{80,78},{38,36},{122,36},
    {121,-99},{0,-74},{-121,-99}};
static void draw_pad_picture(const struct surface *s,int cx,int cy)
{
    /* the body: the middle and the two grips */
    for(int side=-1;side<=1;side+=2)
        for(int i=0;i<=75;i++) {
            int x=cx+side*(168+i*28/75),y=cy-10+i*2,r=58-i*14/75;
            disc(s,x,y,r+2,KM_BODY_EDGE);
        }
    rounded(s,cx-212,cy-124,424,156,38,KM_BODY_EDGE);
    for(int side=-1;side<=1;side+=2)
        for(int i=0;i<=75;i++) disc(s,cx+side*(168+i*28/75),cy-10+i*2,58-i*14/75,KM_BODY);
    rounded(s,cx-210,cy-122,420,152,36,KM_BODY);
    /* the shoulders: L2/R2 behind, L1/R1 in front */
    for(int side=-1;side<=1;side+=2) {
        int l2=side<0?MAP_L2:MAP_R2,l1=side<0?MAP_L1:MAP_R1,x2=side<0?cx-205:cx+125,x1=side<0?cx-215:cx+115;
        rounded(s,x2,cy-184,80,36,10,km_colour(l2));
        text(s,x2+(80-text_width(map_labels[LANG_EN][l2],2))/2,cy-177,map_labels[LANG_EN][l2],C_PANEL,2);
        rounded(s,x1,cy-144,100,22,8,km_colour(l1));
        text(s,x1+(100-text_width(map_labels[LANG_EN][l1],2))/2,cy-140,map_labels[LANG_EN][l1],C_PANEL,2);
    }
    /* the touchpad, share and options */
    rounded(s,cx-100,cy-120,200,92,10,KM_BODY_EDGE);
    rounded(s,cx-98,cy-118,196,88,9,map_row==MAP_TOUCHPAD?C_EDGE:map_key[MAP_TOUCHPAD][0]?KM_PAD_SET:KM_PAD_FREE);
    rounded(s,cx-128,cy-112,14,26,6,km_colour(MAP_SHARE));
    rounded(s,cx+114,cy-112,14,26,6,km_colour(MAP_OPTIONS));
    text(s,cx-121-text_width("SHARE",1)/2,cy-122,"SHARE",C_DIM,1);
    text(s,cx+121-text_width("OPTIONS",1)/2,cy-122,"OPTIONS",C_DIM,1);
    /* the d-pad */
    {
        int x=cx-160,y=cy-48;
        rounded(s,x-13,y-47,26,34,5,km_colour(MAP_UP));rounded(s,x-13,y+13,26,34,5,km_colour(MAP_DOWN));
        rounded(s,x-47,y-13,34,26,5,km_colour(MAP_LEFT));rounded(s,x+13,y-13,34,26,5,km_colour(MAP_RIGHT));
    }
    /* the face buttons, each with its mark */
    {
        static const int rows[4]={MAP_TRIANGLE,MAP_CIRCLE,MAP_CROSS,MAP_SQUARE};
        static const int at[4][2]={{0,-32},{32,0},{0,32},{-32,0}};
        for(int i=0;i<4;i++) {
            int x=cx+160+at[i][0],y=cy-48+at[i][1];
            uint32_t colour=km_colour(rows[i]);
            disc(s,x,y,17,colour);
            face_mark(s,x,y,rows[i],C_PANEL,colour);
        }
    }
    /* the sticks: the cap is L3/R3, the wedges the directions */
    for(int side=-1;side<=1;side+=2) {
        int x=cx+side*80,y=cy+36,first=side<0?MAP_LS_UP:MAP_RS_UP,click=side<0?MAP_L3:MAP_R3;
        disc(s,x,y,34,C_RAIL);
        disc(s,x,y,27,km_colour(click));
        disc(s,x,y,17,map_row==click?0xff4f9fd0:map_key[click][0]?0xffa9b8c5:0xff3f4f5f);
        wedge(s,x,y-42,0,-1,km_colour(first));wedge(s,x,y+42,0,1,km_colour(first+1));
        wedge(s,x-42,y,-1,0,km_colour(first+2));wedge(s,x+42,y,1,0,km_colour(first+3));
    }
    disc(s,cx,cy+36,10,KM_SYSTEM);  /* the PS button, the system's */
}
static void draw_mapper(const struct surface *s)
{
    enum {LIST_X=680,LIST_Y=72,ROW_H=21,GROUP_GAP=4,FOOT=624,PICK_X=LIST_X-14,PICK_Y=66,PICK_COL=42,PICK_KEY_H=34,PICK_ROW_H=40};
    char line[96],buffer[24];
    int cx=330,cy=332,right=s->width-40,row_y[MAPS],dirty=map_dirty();
    fill(s,0,0,s->width,s->height,C_PANEL);
    text(s,40,18,str(S_ITEM_KEYMAP),C_TEXT,3);
    snprintf(line,sizeof(line),"%s %s",str(S_CURSOR_PROGRAM),map_program);
    text(s,right-text_width(line,2),24,line,C_DIM,2);
    fill(s,40,56,s->width-80,1,C_ITEM);
    fill(s,LIST_X-20,64,1,FOOT-72,C_ITEM);
    draw_pad_picture(s,cx,cy);
    /* the list */
    for(int i=0,y=LIST_Y;i<MAPS;i++) {
        const char *value;
        uint32_t colour=C_DIM;
        if(i && map_sources[i].group!=map_sources[i-1].group) y+=GROUP_GAP;
        row_y[i]=y;
        if(i==map_row) {fill(s,LIST_X,y,right-LIST_X+12,ROW_H,map_picking?C_ITEM:C_SELECTED);fill(s,LIST_X,y,4,ROW_H,C_EDGE);}
        if(i<=MAP_TRIANGLE) {
            static const uint32_t marks[4]={KM_CROSS,KM_CIRCLE,KM_SQUARE,KM_TRIANGLE};
            face_mark(s,LIST_X+20,y+ROW_H/2,i,marks[i],i==map_row?(map_picking?C_ITEM:C_SELECTED):C_PANEL);
        }
        text(s,LIST_X+36,y+4,map_labels[lang][i],i==MAP_SHARE?C_DIM:C_TEXT,2);
        if(i==MAP_SHARE) value=str(S_KM_SYSTEM);
        else if(map_key[i][0]) {value=pick_label(map_key[i],buffer,sizeof(buffer));colour=strcmp(map_key[i],map_saved[i])?C_EDGE:C_TEXT;}
        else if(map_saved[i][0]) {value="--";colour=C_EDGE;}
        else if(i>=MAP_LS_UP && i<=MAP_LS_RIGHT && map_left_mouse()) value=str(S_KM_MOUSE);
        else if(i>=MAP_LS_UP && i<=MAP_LS_RIGHT && map_auto_arrows()) {
            static const int arrows[4]={S_KEY_UP,S_KEY_DOWN,S_KEY_LEFT,S_KEY_RIGHT};
            snprintf(line,sizeof(line),"%s: %s",str(S_KM_AUTO),str(arrows[i-MAP_LS_UP]));value=line;
        } else if(i>=MAP_RS_UP && i<=MAP_RS_RIGHT && map_right_mouse()) value=str(S_KM_MOUSE);
        else value="--";
        text(s,right-text_width(value,2),y+4,value,colour,2);
        y+=ROW_H;
    }
    /* the line from the chosen row to its place on the picture */
    {
        int y=row_y[map_row]+ROW_H/2,ax=cx+km_anchor[map_row][0],ay=cy+km_anchor[map_row][1];
        fill(s,LIST_X-34,y-1,34,2,C_EDGE);
        hud_line(s,LIST_X-34,y-1,ax,ay,C_EDGE);
        disc(s,ax,ay,4,C_EDGE);
    }
    /* the key picker, over the list */
    if(map_picking) {
        int w=s->width-16-PICK_X,h=FOOT-8-PICK_Y,left=PICK_X+(w-PICK_COLS*PICK_COL+4)/2;
        int top=PICK_Y+(h-PICK_ROWS*PICK_ROW_H)/2+14;
        box(s,PICK_X,PICK_Y,w,h,C_PANEL,C_EDGE);
        snprintf(line,sizeof(line),"%s %s",str(S_KM_PICK_TITLE),map_labels[lang][map_row]);
        text(s,left,PICK_Y+22,line,C_TEXT,2);
        if(map_key[map_row][0]) {
            const char *now=pick_label(map_key[map_row],buffer,sizeof(buffer));
            text(s,left+PICK_COLS*PICK_COL-4-text_width(now,2),PICK_Y+22,now,C_EDGE,2);
        }
        for(int r=0;r<PICK_ROWS;r++)
            for(int k=0,col=0;k<pick_count(r);col+=pick_rows[r][k].cols,k++) {
                const struct pick_key *key=&pick_rows[r][k];
                const char *label=key->label>=0?str(key->label):key->text;
                int kx=left+col*PICK_COL,ky=top+r*PICK_ROW_H,kw=key->cols*PICK_COL-4;
                int chosen=r==pick_row && k==pick_index,current=!strcasecmp(key->name,map_key[map_row]);
                if(current) fill(s,kx-2,ky-2,kw+4,PICK_KEY_H+4,C_EDGE);
                fill(s,kx,ky,kw,PICK_KEY_H,chosen?C_KEYSEL:C_KEY);
                text(s,kx+(kw-text_width(label,2))/2,ky+(PICK_KEY_H-14)/2,label,C_TEXT,2);
            }
    }
    /* the band */
    fill(s,0,FOOT,s->width,2,C_EDGE);
    fill(s,0,FOOT+2,s->width,s->height-FOOT-2,C_RAIL);
    wrapped(s,40,FOOT+12,(s->width-80)/12,str(map_picking?S_KM_PICK_HELP:S_KM_HELP),C_DIM,2,s->height-34);
    text(s,40,s->height-28,str(map_picking?S_KM_PICK_FOOT:dirty?S_KM_FOOT_DIRTY:S_KM_FOOT),C_TEXT,2);
}
/* the sink, on each output frame before the flip (its lock held) */
void pw_hw_overlay_draw(uint32_t *pixels,unsigned pitch,unsigned width,unsigned height);
void pw_hw_overlay_draw(uint32_t *pixels,unsigned pitch,unsigned width,unsigned height)
{
    struct surface s={pixels,pitch,(int)width,(int)height};
    char message[48];
    pthread_mutex_lock(&lock);
    int shown_view=view,stats=stats_on,toast_on=toast_until_us!=0;
    if(toast_on) snprintf(message,sizeof(message),"%s",toast);
    if(stats) {  /* the frametime graph's sample: this output frame's interval, under a second */
        uint64_t now=sceKernelGetProcessTime();
        if(ft_last_us && now-ft_last_us<1000000) {
            ft_us[ft_head]=(uint32_t)(now-ft_last_us);ft_head=(ft_head+1)%FT_SAMPLES;
            if(ft_count<FT_SAMPLES) ft_count++;
        }
        ft_last_us=now;
    }
    if(stats && hud_now.sampled && hud_conf.loaded) draw_stats(&s);
    if(shown_view==VIEW_PANEL) draw_panel(&s,title_alone,hud_mode());
    if(shown_view==VIEW_KEYBOARD) draw_keyboard(&s);
    if(shown_view==VIEW_MAPPER) draw_mapper(&s);  /* 04.36 */
    pthread_mutex_unlock(&lock);
    if(toast_on) {  /* W240: at the bottom, away from the readout's and MangoHud's corner */
        int w=text_width(message,3)+40,x=((int)width-w)/2,y=(int)height-24-46;
        fill(&s,x,y,w,46,C_EDGE);fill(&s,x+2,y+2,w-4,42,C_PANEL);
        text(&s,x+20,y+12,message,C_TEXT,3);
    }
}
