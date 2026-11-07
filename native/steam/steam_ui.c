/* SPDX-License-Identifier: GPL-3.0-or-later */
/* S3's screen and pad (steam_ui.h). The PS4 side opens its own 1920x1080 framebuffer with
 * sceVideoOut, as platform/ps4/pw_wine_sink_ps4.c's CPU path, letters it with native/hw_text.h and
 * reads the pad as native/hw_pad.c; QR codes come from Nayuki's qrcodegen (MIT). */
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
static pthread_t thread;
static volatile int running;

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
    /* one button: the first of the mask's order X, O, triangle */
    return buttons & -buttons;
}

#ifdef STEAM_HOST
/* The host: the page on stdout (the QR code as blocks), buttons from stdin. */
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
        printf("---- buttons: x o t ----\n");
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
        press(line[0] == 'x' ? STEAM_UI_CROSS : line[0] == 'o' ? STEAM_UI_CIRCLE : line[0] == 't' ? STEAM_UI_TRIANGLE : 0);
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
    pthread_t printing;
    note = log;
    running = 1;
    if (pthread_create(&thread, NULL, run, NULL) || pthread_create(&printing, NULL, printer, NULL)) return -1;
    pthread_detach(thread);
    pthread_detach(printing);
    return 0;
}
void steam_ui_close(void)
{
    running = 0;
}
#else
#include <orbis/Pad.h>
#include <orbis/Sysmodule.h>
#include <orbis/UserService.h>
#include <orbis/VideoOut.h>
#include <orbis/libkernel.h>

#include "../hw_text.h"

enum { WIDTH = 1920, HEIGHT = 1080, BUFFERS = 2, FORMAT_A8R8G8B8_SRGB = (int)0x80000000, TILING_LINEAR = 1,
       USER_MAIN = 255, FLIP_VSYNC = 1 };
enum { BACKGROUND = 0xff1b2838, FOREGROUND = 0xffffffff, TITLE = 0xff66c0f4, QR_LIGHT = 0xffffffff, QR_DARK = 0xff000000 };
static int video = -1, pad = -1;
static uint32_t *buffers[BUFFERS];

/* The page's text, word-wrapped to `columns`, from (x, y) down. */
static void draw_text(uint32_t *pixels, const char *text, int x, int y, int columns)
{
    char line[160];
    int first = 1;
    while (*text && y < HEIGHT - 60) {
        const char *end = strchr(text, '\n');
        size_t length = end ? (size_t)(end - text) : strlen(text);
        const int scale = first ? 6 : 4;
        const int width = columns * 4 / scale;
        while (1) {
            size_t take = length;
            if ((int)take > width) {
                take = (size_t)width;
                while (take > 0 && text[take] != ' ') --take;
                if (!take) take = (size_t)width;
            }
            memcpy(line, text, take);
            line[take] = 0;
            hw_text(pixels, WIDTH, HEIGHT, x, y, line, first ? TITLE : FOREGROUND, scale);
            y += 10 * scale;
            text += take;
            length -= take;
            while (length && *text == ' ') ++text, --length;
            if (!length) break;
        }
        if (first) y += 20;
        first = 0;
        text = end ? end + 1 : text + length;
        if (!end) break;
    }
}

static void draw(uint32_t *pixels)
{
    for (int i = 0; i < WIDTH * HEIGHT; ++i) pixels[i] = BACKGROUND;
    pthread_mutex_lock(&lock);
    int columns = 72;
    if (qr_size) {
        /* the code with a quiet zone of 4 modules, on white, at the right */
        const int modules = qr_size + 8, module = 720 / modules, side = module * modules;
        const int left = WIDTH - 120 - side, top = (HEIGHT - side) / 2;
        for (int y = 0; y < side; ++y)
            for (int x = 0; x < side; ++x) {
                const int mx = x / module - 4, my = y / module - 4;
                const int dark = mx >= 0 && my >= 0 && mx < qr_size && my < qr_size && qr_modules[my * qr_size + mx];
                pixels[(top + y) * WIDTH + left + x] = dark ? QR_DARK : QR_LIGHT;
            }
        columns = (left - 120 - 60) / 24;
    }
    draw_text(pixels, page_text, 120, 120, columns);
    pthread_mutex_unlock(&lock);
}

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
            press((down & ORBIS_PAD_BUTTON_CROSS ? STEAM_UI_CROSS : 0) | (down & ORBIS_PAD_BUTTON_CIRCLE ? STEAM_UI_CIRCLE : 0) |
                  (down & ORBIS_PAD_BUTTON_TRIANGLE ? STEAM_UI_TRIANGLE : 0));
        }
        pthread_mutex_lock(&lock);
        const unsigned current = version;
        pthread_mutex_unlock(&lock);
        if (current != drawn) {
            drawn = current;
            uint32_t *target = buffers[frame % BUFFERS];
            draw(target);
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
