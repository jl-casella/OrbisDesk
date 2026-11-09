/* SPDX-License-Identifier: GPL-3.0-or-later */
/* The Steam client's screen and pad (steam_ui.h): pages of text and QR codes (Nayuki's qrcodegen, MIT)
 * lettered with native/hw_text.h's glyphs. Three backends:
 *   - STEAM_HOST: the PC, the page on stdout and the buttons from stdin;
 *   - STEAM_UI_HOSTED: inside OrbisDesk's title (ORBW00002). The title owns VideoOut and the pad: its
 *     sink calls pw_hw_steam_draw() on every frame it shows and its pad thread pw_hw_steam_pad() on
 *     every read, as for the control overlay (native/hw_overlay.c); while the client is open they
 *     draw over the desktop and take the pad;
 *   - otherwise: the standalone title ORBS00001, with a 1920x1080 framebuffer of its own (sceVideoOut,
 *     as platform/ps4/pw_wine_sink_ps4.c's CPU path) and its own scePadOpen (as native/hw_pad.c). */
#include "steam_ui.h"

#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "qrcodegen.h"

#define PAGE_TEXT 4096

static steam_ui_note note;
static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t pressed_cond = PTHREAD_COND_INITIALIZER;
static char page_text[PAGE_TEXT];
static uint8_t qr_modules[177 * 177];  /* 1 = dark; the largest QR code is 177 modules wide */
static int qr_size;                    /* 0: no QR code on the page */
static unsigned pressed;
static unsigned version;               /* bumped by each page */
static volatile int running;

static void page_changed(void);

int steam_ui_show(const char *text, const char *qr)
{
    uint8_t temp[qrcodegen_BUFFER_LEN_MAX], code[qrcodegen_BUFFER_LEN_MAX];
    int size = 0;
    if (qr) {
        if (!qrcodegen_encodeText(qr, temp, code, qrcodegen_Ecc_MEDIUM, qrcodegen_VERSION_MIN, qrcodegen_VERSION_MAX,
                                  qrcodegen_Mask_AUTO, 1))
            return -1;
        size = qrcodegen_getSize(code);
    }
    pthread_mutex_lock(&lock);
    snprintf(page_text, sizeof(page_text), "%s", text);
    for (int y = 0; y < size; ++y)
        for (int x = 0; x < size; ++x) qr_modules[y * size + x] = qrcodegen_getModule(code, x, y);
    qr_size = size;
    pressed = 0;
    ++version;
    pthread_mutex_unlock(&lock);
    memset(temp, 0, sizeof(temp));
    memset(code, 0, sizeof(code));
    page_changed();
    return 0;
}

static void press(unsigned buttons)
{
    if (!buttons) return;
    pthread_mutex_lock(&lock);
    pressed |= buttons;
    pthread_cond_broadcast(&pressed_cond);
    pthread_mutex_unlock(&lock);
}

unsigned steam_ui_take(void)
{
    pthread_mutex_lock(&lock);
    const unsigned buttons = pressed;
    pressed = 0;
    pthread_mutex_unlock(&lock);
    return buttons;
}

unsigned steam_ui_wait(unsigned mask)
{
    pthread_mutex_lock(&lock);
    while (!(pressed & mask)) pthread_cond_wait(&pressed_cond, &lock);
    unsigned buttons = pressed & mask;
    pressed = 0;
    pthread_mutex_unlock(&lock);
    /* one button: the first of the mask's order X, O, triangle, up, down */
    return buttons & -buttons;
}

#ifdef STEAM_HOST
/* The host: the page on stdout (the QR code as blocks), buttons from stdin. */
static void page_changed(void) {}
static unsigned shown = ~0u;
static void print_page(void)
{
    pthread_mutex_lock(&lock);
    if (shown != version) {
        shown = version;
        printf("---- screen ----\n%s\n", page_text);
        for (int y = -2; y < qr_size + 2 && qr_size; ++y) {
            for (int x = -2; x < qr_size + 2; ++x) {
                const int dark = y >= 0 && x >= 0 && y < qr_size && x < qr_size && qr_modules[y * qr_size + x];
                fputs(dark ? "  " : "\xe2\x96\x88\xe2\x96\x88", stdout);
            }
            fputc('\n', stdout);
        }
        printf("---- buttons: x o t u d ----\n");
        fflush(stdout);
    }
    pthread_mutex_unlock(&lock);
}
static void *run(void *unused)
{
    (void)unused;
    char line[64];
    while (running) {
        print_page();
        if (!fgets(line, sizeof(line), stdin)) {
            usleep(100000);
            continue;
        }
        press(line[0] == 'x' ? STEAM_UI_CROSS : line[0] == 'o' ? STEAM_UI_CIRCLE : line[0] == 't' ? STEAM_UI_TRIANGLE :
              line[0] == 'u' ? STEAM_UI_UP : line[0] == 'd' ? STEAM_UI_DOWN : line[0] == 'l' ? STEAM_UI_L1 :
              line[0] == 'r' ? STEAM_UI_R1 : line[0] == 's' ? STEAM_UI_SQUARE : line[0] == 'p' ? STEAM_UI_OPTIONS : 0);
    }
    return NULL;
}
static void *printer(void *unused)
{
    (void)unused;
    while (running) {
        print_page();
        usleep(100000);
    }
    return NULL;
}
int steam_ui_open(steam_ui_note log)
{
    pthread_t reader, printing;
    note = log;
    running = 1;
    if (pthread_create(&reader, NULL, run, NULL) || pthread_create(&printing, NULL, printer, NULL)) return -1;
    pthread_detach(reader);
    pthread_detach(printing);
    return 0;
}
void steam_ui_close(void)
{
    running = 0;
}
#else
#include <orbis/Pad.h>
#include <orbis/libkernel.h>

#include "../hw_text.h"

enum { BACKGROUND = 0xff1b2838, FOREGROUND = 0xffffffff, TITLE = 0xff66c0f4, HIGHLIGHT = 0xff2a475e,
       WARN = 0xffffb347, BAND = 0xff171a21, RULE = 0xff66c0f4,
       QR_LIGHT = 0xffffffff, QR_DARK = 0xff000000 };

/* Accented capitals for the languages' own names (ESPAÑOL, FRANÇAIS, ČEŠTINA): hw_text.h's letter with
 * a mark of two rows above it (in the line's spacing: a line is 10 rows, a letter 7) or, for the
 * cedilla, below it. Rows are 5 bits wide, as hw_glyphs'. */
enum { MARK_NONE, MARK_ACUTE, MARK_GRAVE, MARK_CIRCUMFLEX, MARK_TILDE, MARK_DIAERESIS, MARK_CARON, MARK_BREVE,
       MARK_CEDILLA };
static const unsigned char mark_rows[][2] = {
    {0, 0}, {2, 4}, {8, 4}, {4, 10}, {13, 22}, {10, 0}, {10, 4}, {17, 14}, {4, 12},  /* Ü's dots apart from its arms */
};

/* One character of UTF-8 text: the ASCII letter to draw and its mark, *s past it. Lower case is drawn
 * as upper case, as hw_text does. Latin-1's letters with marks, and the few Latin Extended-A ones
 * Steam's language names use (Ă, Č, Š); anything else is skipped whole. */
static unsigned char next_char(const char **s, int *mark)
{
    const unsigned char *p = (const unsigned char *)*s;
    *mark = MARK_NONE;
    if (p[0] < 0x80) {
        ++*s;
        return p[0];
    }
    unsigned code = 0;
    int length = p[0] >= 0xf0 ? 4 : p[0] >= 0xe0 ? 3 : p[0] >= 0xc0 ? 2 : 1;
    for (int i = 1; i < length; ++i)
        if ((p[i] & 0xc0) != 0x80) length = i;  /* a broken sequence (a wrap cut it): skip its bytes */
    if (length == 2) code = ((unsigned)(p[0] & 0x1f) << 6) | (p[1] & 0x3f);
    *s += length;
    if (code >= 0xe0 && code <= 0xfe && code != 0xf7) code -= 0x20;  /* Latin-1 lower to upper */
    static const struct { unsigned short code; unsigned char letter, mark; } letters[] = {
        {0xc0, 'A', MARK_GRAVE}, {0xc1, 'A', MARK_ACUTE}, {0xc2, 'A', MARK_CIRCUMFLEX}, {0xc3, 'A', MARK_TILDE},
        {0xc4, 'A', MARK_DIAERESIS}, {0xc7, 'C', MARK_CEDILLA}, {0xc8, 'E', MARK_GRAVE}, {0xc9, 'E', MARK_ACUTE},
        {0xca, 'E', MARK_CIRCUMFLEX}, {0xcb, 'E', MARK_DIAERESIS}, {0xcc, 'I', MARK_GRAVE}, {0xcd, 'I', MARK_ACUTE},
        {0xce, 'I', MARK_CIRCUMFLEX}, {0xcf, 'I', MARK_DIAERESIS}, {0xd1, 'N', MARK_TILDE}, {0xd2, 'O', MARK_GRAVE},
        {0xd3, 'O', MARK_ACUTE}, {0xd4, 'O', MARK_CIRCUMFLEX}, {0xd5, 'O', MARK_TILDE}, {0xd6, 'O', MARK_DIAERESIS},
        {0xd9, 'U', MARK_GRAVE}, {0xda, 'U', MARK_ACUTE}, {0xdb, 'U', MARK_CIRCUMFLEX}, {0xdc, 'U', MARK_DIAERESIS},
        {0xdd, 'Y', MARK_ACUTE}, {0x102, 'A', MARK_BREVE}, {0x103, 'A', MARK_BREVE}, {0x10c, 'C', MARK_CARON},
        {0x10d, 'C', MARK_CARON}, {0x160, 'S', MARK_CARON}, {0x161, 'S', MARK_CARON},
    };
    for (size_t i = 0; i < sizeof(letters) / sizeof(letters[0]); ++i)
        if (letters[i].code == code) {
            *mark = letters[i].mark;
            return letters[i].letter;
        }
    return 0;
}

static void draw_rows(uint32_t *pixels, int pitch, int width, int height, int x, int y, const unsigned char *rows,
                      int count, uint32_t color, int scale)
{
    for (int yy = 0; yy < count; yy++)
        for (int xx = 0; xx < 5; xx++)
            if (rows[yy] & (1 << (4 - xx)))
                for (int dy = 0; dy < scale; dy++)
                    for (int dx = 0; dx < scale; dx++) {
                        const int px = x + xx * scale + dx, py = y + yy * scale + dy;
                        if (px >= 0 && px < width && py >= 0 && py < height) pixels[py * pitch + px] = color;
                    }
}

/* hw_text.h's glyphs into a buffer with a pitch (in pixels): the hosted target's rows may be wider
 * than the screen (the GPU sink's row pitch). The text is UTF-8 (next_char); STEAM_UI_ACCENT switches
 * between `color` and the accent and takes no room. */
static void draw_string(uint32_t *pixels, int pitch, int width, int height, int x, int y, const char *s, uint32_t color,
                        int scale)
{
    const uint32_t plain = color;
    while (*s) {
        int mark;
        unsigned char c = next_char(&s, &mark);
        if (c == (unsigned char)STEAM_UI_ACCENT) {
            color = color == plain ? TITLE : plain;
            continue;
        }
        if (!c) continue;  /* a character the font can't show takes no room */
        int g = -1;
        if (c >= 'a' && c <= 'z') c -= 32;
        if (c >= 'A' && c <= 'Z') g = c - 'A';
        else if (c >= '0' && c <= '9') g = 26 + c - '0';
        else if (c == ':') g = 36;
        else if (c == '-') g = 37;
        else if (c == '.') g = 38;
        else if (c == '/') g = 39;
        else if (c == '%') g = 40;
        if (g >= 0) {
            draw_rows(pixels, pitch, width, height, x, y, hw_glyphs[g], 7, color, scale);
            if (mark == MARK_CEDILLA)
                draw_rows(pixels, pitch, width, height, x, y + 7 * scale, mark_rows[mark], 2, color, scale);
            else if (mark != MARK_NONE)
                draw_rows(pixels, pitch, width, height, x, y - 2 * scale, mark_rows[mark], 2, color, scale);
        }
        x += 6 * scale;  /* a space, or a sign the font lacks, keeps its room as before */
    }
}

/* The page's text, word-wrapped to `columns` body characters, from (x, y) down to y_end (a line that
 * wouldn't fit whole isn't drawn). With `title` the first line is the title. pixels NULL only
 * measures. Returns the y below the last line. */
static int draw_text(uint32_t *pixels, int pitch, int screen_w, int screen_h, const char *text, size_t text_length,
                     int x, int y, int y_end, int columns, int title_scale, int body_scale, int title)
{
    char line[256];
    int first = title;
    const char *stop = text + text_length;
    while (text < stop) {
        const char *end = memchr(text, '\n', (size_t)(stop - text));
        size_t length = end ? (size_t)(end - text) : (size_t)(stop - text);
        const int scale = first ? title_scale : body_scale;
        int width = columns * body_scale / scale;
        if (width > (int)sizeof(line) - 1) width = (int)sizeof(line) - 1;
        uint32_t color = first ? TITLE : FOREGROUND;
        int bar = 0;
        if (!first && length && *text == STEAM_UI_MARK) {
            bar = 1;  /* the selected entry of a list: a bar behind its first line */
            ++text;
            --length;
        }
        if (!first && length && *text == STEAM_UI_WARN) {
            color = WARN;
            ++text;
            --length;
        }
        while (1) {
            if (y + 10 * scale > y_end) return y;
            if (pixels && bar)
                for (int yy = y - 2 * scale; yy < y + 8 * scale && yy < screen_h; ++yy)  /* marks above included */
                    for (int xx = x - 2 * scale; xx < x + columns * 6 * body_scale && xx < screen_w; ++xx)
                        if (yy >= 0 && xx >= 0) pixels[yy * pitch + xx] = HIGHLIGHT;
            bar = 0;
            size_t take = length;
            if ((int)take > width) {
                take = (size_t)width;
                while (take > 0 && text[take] != ' ') --take;
                if (!take) take = (size_t)width;
            }
            memcpy(line, text, take);
            line[take] = 0;
            if (pixels) draw_string(pixels, pitch, screen_w, screen_h, x, y, line, color, scale);
            y += 10 * scale;
            text += take;
            length -= take;
            while (length && *text == ' ') ++text, --length;
            if (!length) break;
        }
        if (first) y += 3 * body_scale;
        first = 0;
        if (!end) break;
        text = end + 1;
    }
    return y;
}

/* The page at any size: 1920x1080 for the standalone title, the desktop's 1280x720 when hosted. The
 * footer (STEAM_UI_FOOTER and what follows) sits in a band at the bottom; the body above it is cut
 * where the band starts, so a shorter or longer list never moves the footer. */
static void render(uint32_t *pixels, int pitch, int width, int height)
{
    (void)hw_text;  /* hw_text.h's own drawer assumes pitch == width; draw_string replaces it */
    for (int y = 0; y < height; ++y)
        for (int x = 0; x < width; ++x) pixels[y * pitch + x] = BACKGROUND;
    const int title_scale = height >= 1000 ? 6 : 4, body_scale = height >= 1000 ? 4 : 3, margin = width / 16;
    pthread_mutex_lock(&lock);
    int columns = (width - 2 * margin) / (6 * body_scale);
    if (qr_size) {
        /* the code with a quiet zone of 4 modules, on white, at the right */
        const int modules = qr_size + 8, module = (height * 2 / 3) / modules, side = module * modules;
        const int left = width - margin - side, top = (height - side) / 2;
        for (int y = 0; y < side; ++y)
            for (int x = 0; x < side; ++x) {
                const int mx = x / module - 4, my = y / module - 4;
                const int dark = mx >= 0 && my >= 0 && mx < qr_size && my < qr_size && qr_modules[my * qr_size + mx];
                pixels[(top + y) * pitch + left + x] = dark ? QR_DARK : QR_LIGHT;
            }
        columns = (left - 2 * margin) / (6 * body_scale);
    }
    const size_t length = strlen(page_text);
    const char *footer = page_text[0] == STEAM_UI_FOOTER ? page_text : strstr(page_text, "\n\x02");
    if (footer && *footer == '\n') ++footer;
    const size_t body_length = footer ? (size_t)(footer - page_text) : length;
    int body_end = height - 10 * body_scale;
    if (footer) {
        ++footer;  /* past the footer byte */
        const size_t footer_length = length - (size_t)(footer - page_text);
        const int footer_columns = (width - 2 * margin) / (6 * body_scale);
        const int footer_height = draw_text(NULL, pitch, width, height, footer, footer_length, margin, 0, height,
                                            footer_columns, title_scale, body_scale, 0);
        /* the band keeps the height of FOOTER_LINES lines on every page, so it starts at the same place on
         * all of them; a longer footer (a narrow screen) makes it taller */
        enum { FOOTER_LINES = 4 };
        const int lines_height = footer_height > FOOTER_LINES * 10 * body_scale ? footer_height : FOOTER_LINES * 10 * body_scale;
        const int pad = 4 * body_scale, top = height - height / 18 - lines_height - pad;
        for (int y = top; y < height; ++y)
            for (int x = 0; x < width; ++x) pixels[y * pitch + x] = y < top + (body_scale + 1) / 2 ? RULE : BAND;
        draw_text(pixels, pitch, width, height, footer, footer_length, margin, top + pad, height, footer_columns,
                  title_scale, body_scale, 0);
        body_end = top - 2 * body_scale;
    }
    draw_text(pixels, pitch, width, height, page_text, body_length, margin, height / 9, body_end, columns, title_scale,
              body_scale, 1);
    pthread_mutex_unlock(&lock);
}

/* The pad's newly pressed buttons as STEAM_UI_* bits. */
static unsigned buttons_of(uint32_t down)
{
    return (down & ORBIS_PAD_BUTTON_CROSS ? STEAM_UI_CROSS : 0) | (down & ORBIS_PAD_BUTTON_CIRCLE ? STEAM_UI_CIRCLE : 0) |
           (down & ORBIS_PAD_BUTTON_TRIANGLE ? STEAM_UI_TRIANGLE : 0) | (down & ORBIS_PAD_BUTTON_UP ? STEAM_UI_UP : 0) |
           (down & ORBIS_PAD_BUTTON_DOWN ? STEAM_UI_DOWN : 0) |
           (down & (ORBIS_PAD_BUTTON_L1 | ORBIS_PAD_BUTTON_L2) ? STEAM_UI_L1 : 0) |
           (down & (ORBIS_PAD_BUTTON_R1 | ORBIS_PAD_BUTTON_R2) ? STEAM_UI_R1 : 0) |
           (down & ORBIS_PAD_BUTTON_SQUARE ? STEAM_UI_SQUARE : 0) |
           (down & ORBIS_PAD_BUTTON_OPTIONS ? STEAM_UI_OPTIONS : 0);
}

#ifdef STEAM_UI_HOSTED
/* OrbisDesk's sink shows a frame only when Wine presents or this is called (native/hw_overlay.c does
 * the same): each page is a new frame. */
extern void pw_hw_cursor_moved(void);
static volatile int swallow;  /* after closing, the pad stays here until every button is up */
static uint32_t held;
static void page_changed(void)
{
    if (running) pw_hw_cursor_moved();
}

int steam_ui_open(steam_ui_note log)
{
    note = log;
    held = ~0u;  /* what is down now (the X that opened it) counts as held, not as a press */
    running = 1;
    pw_hw_cursor_moved();
    note("PWSTEAM ui hosted open");
    return 0;
}

void steam_ui_close(void)
{
    if (!running) return;
    running = 0;
    swallow = 1;
    pw_hw_cursor_moved();  /* the desktop's frame again */
    note("PWSTEAM ui hosted close");
}

int pw_hw_steam_active(void) { return running; }

/* The sink, for every frame it shows: the Steam page over the whole screen while the client is open.
 * 1 when it drew. */
int pw_hw_steam_draw(uint32_t *pixels, unsigned pitch, unsigned width, unsigned height)
{
    if (!running) return 0;
    render(pixels, (int)pitch, (int)width, (int)height);
    return 1;
}

/* The pad thread, for every read: 1 while the client (or the release after it) has the pad, which the
 * desktop then reads neutral. */
int pw_hw_steam_pad(const OrbisPadData *data)
{
    if (!running) {
        if (!swallow) return 0;
        if (data->buttons) return 1;
        swallow = 0;
        return 1;
    }
    const uint32_t now = data->buttons;
    const uint32_t down = held == ~0u ? 0 : now & ~held;
    held = now;
    press(buttons_of(down));
    return 1;
}
#else
#include <orbis/Sysmodule.h>
#include <orbis/UserService.h>
#include <orbis/VideoOut.h>

enum { WIDTH = 1920, HEIGHT = 1080, BUFFERS = 2, FORMAT_A8R8G8B8_SRGB = (int)0x80000000, TILING_LINEAR = 1,
       USER_MAIN = 255, FLIP_VSYNC = 1 };
static int video = -1, pad = -1;
static uint32_t *buffers[BUFFERS];
static pthread_t thread;
static void page_changed(void) {}

static void *run(void *unused)
{
    (void)unused;
    unsigned drawn = ~0u, frame = 0;
    uint32_t held = 0;
    while (running) {
        OrbisPadData data;
        memset(&data, 0, sizeof(data));
        if (pad >= 0 && !scePadReadState(pad, &data) && data.connected) {
            const uint32_t now = data.buttons, down = now & ~held;
            held = now;
            press(buttons_of(down));
        }
        pthread_mutex_lock(&lock);
        const unsigned current = version;
        pthread_mutex_unlock(&lock);
        if (current != drawn) {
            drawn = current;
            uint32_t *target = buffers[frame % BUFFERS];
            render(target, WIDTH, WIDTH, HEIGHT);
            const int rc = sceVideoOutSubmitFlip(video, (int32_t)(frame % BUFFERS), FLIP_VSYNC, (int64_t)frame);
            if (rc) note("PWSTEAM ui flip rc=0x%08x", (unsigned)rc);
            ++frame;
        }
        sceKernelUsleep(16000);
    }
    return NULL;
}

int steam_ui_open(steam_ui_note log)
{
    note = log;
    const int user_module = sceSysmoduleLoadModuleInternal(ORBIS_SYSMODULE_INTERNAL_USER_SERVICE);
    const int video_module = sceSysmoduleLoadModuleInternal(ORBIS_SYSMODULE_INTERNAL_VIDEO_OUT);
    const int pad_module = sceSysmoduleLoadModuleInternal(ORBIS_SYSMODULE_INTERNAL_PAD);
    int user = -1;
    const int service = sceUserServiceInitialize(NULL);
    const int user_rc = sceUserServiceGetInitialUser(&user);
    const int pad_init = scePadInit();
    pad = scePadOpen(user, 0, 0, NULL);
    note("PWSTEAM ui modules user=0x%08x video=0x%08x pad=0x%08x service=0x%08x user_rc=0x%08x pad_init=0x%08x pad=0x%08x",
         (unsigned)user_module, (unsigned)video_module, (unsigned)pad_module, (unsigned)service, (unsigned)user_rc,
         (unsigned)pad_init, (unsigned)pad);
    if (pad < 0) return -1;

    const size_t bytes = (size_t)WIDTH * HEIGHT * 4, aligned = (bytes + 0x1fffff) & ~(size_t)0x1fffff;
    off_t physical = 0;
    void *memory = NULL;
    video = sceVideoOutOpen(USER_MAIN, 0, 0, NULL);
    if (video < 0) {
        note("PWSTEAM ui video open rc=0x%08x", (unsigned)video);
        return -1;
    }
    int rc = sceKernelAllocateDirectMemory(0, sceKernelGetDirectMemorySize(), aligned * BUFFERS, 0x200000, 3, &physical);
    if (!rc) rc = sceKernelMapDirectMemory(&memory, aligned * BUFFERS, 0x33, 0, physical, 0x200000);
    if (rc) {
        note("PWSTEAM ui memory rc=0x%08x", (unsigned)rc);
        return -1;
    }
    OrbisVideoOutBufferAttribute attribute;
    memset(&attribute, 0, sizeof(attribute));
    sceVideoOutSetBufferAttribute(&attribute, FORMAT_A8R8G8B8_SRGB, TILING_LINEAR, 0, WIDTH, HEIGHT, WIDTH);
    void *addresses[BUFFERS];
    for (int i = 0; i < BUFFERS; ++i) addresses[i] = buffers[i] = (uint32_t *)((char *)memory + aligned * i);
    rc = sceVideoOutRegisterBuffers(video, 0, addresses, BUFFERS, &attribute);
    if (rc) {
        note("PWSTEAM ui register rc=0x%08x", (unsigned)rc);
        return -1;
    }
    running = 1;
    rc = pthread_create(&thread, NULL, run, NULL);
    note("PWSTEAM ui ready %dx%d thread=%d", WIDTH, HEIGHT, rc);
    return rc ? -1 : 0;
}

void steam_ui_close(void)
{
    if (!running) return;
    running = 0;
    pthread_join(thread, NULL);
}
#endif
#endif
