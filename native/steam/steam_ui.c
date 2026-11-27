/* SPDX-License-Identifier: GPL-3.0-or-later */
/* The Steam client's screen and pad (steam_ui.h). Frames are drawn by the client's own thread into one of two
 * buffers (steam_draw.h) and published; the display side only copies the last published one. Text pages are
 * drawn by steam_bp.cpp's steam_bp_draw_page, with QR codes from Nayuki's qrcodegen (MIT). Three backends:
 *   - STEAM_HOST: the PC: frames on stdout as text (PNG files with STEAM_UI_SNAPSHOTS), buttons from stdin;
 *   - STEAM_UI_HOSTED: inside OrbisDesk's title (ORBW00002). The title owns VideoOut and the pad: its sink calls
 *     pw_hw_steam_draw() on every frame it shows and its pad thread pw_hw_steam_pad() on every read, as for the
 *     control overlay (native/hw_overlay.c); while the client is open (and not hidden behind a game it
 *     started) they show its frame over the desktop and take the pad;
 *   - otherwise: the standalone title ORBS00001, with a 1920x1080 framebuffer of its own (sceVideoOut, as
 *     platform/ps4/pw_wine_sink_ps4.c's CPU path) and its own scePadOpen (as native/hw_pad.c). */
#include "steam_ui.h"

#include <errno.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#include "qrcodegen.h"
#include "../../platform/ps4/pw_trace.h"  /* diagnostic lines only with traces */
#include "steam_draw.h"

#define PAGE_TEXT 4096

extern void steam_bp_draw_page(sd_canvas *canvas, const char *text, const unsigned char *qr, int qr_size);

static steam_ui_note note;
static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;  /* buttons, page */
static pthread_cond_t pressed_cond = PTHREAD_COND_INITIALIZER;
static char page_text[PAGE_TEXT];
static uint8_t qr_modules[177 * 177];  /* 1 = dark; the largest QR code is 177 modules wide */
static int qr_size;                    /* 0: no QR code on the page */
static unsigned pressed;
static int poked;
static volatile int running;
static volatile int hidden, show_request;

/* the frames: the client draws into the back one (render_lock held from begin to end), the display copies
 * the front one under frame_lock */
static pthread_mutex_t render_lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_mutex_t frame_lock = PTHREAD_MUTEX_INITIALIZER;
static uint32_t *frames[2];
static int frame_w, frame_h, front = -1, back;
static volatile int want_w, want_h;
static volatile unsigned frame_serial;

static void frame_published(const char *summary);
static void page_changed(void);

void steam_ui_begin(struct sd_canvas *canvas)
{
  pthread_mutex_lock(&render_lock);
  const int w = want_w, h = want_h;
  if (w != frame_w || h != frame_h || !frames[0]) {
    pthread_mutex_lock(&frame_lock);
    free(frames[0]);
    free(frames[1]);
    frames[0] = (uint32_t *)calloc((size_t)w * h, 4);
    frames[1] = (uint32_t *)calloc((size_t)w * h, 4);
    frame_w = w;
    frame_h = h;
    front = -1;
    pthread_mutex_unlock(&frame_lock);
  }
  back = front == 0 ? 1 : 0;
  sd_begin(canvas, frames[back], frame_w, frame_h, frame_w);
  if (!frames[back]) canvas->px = NULL;  /* out of memory: draws nothing */
}

void steam_ui_end(const char *summary)
{
  pthread_mutex_lock(&frame_lock);
  if (frames[back]) front = back;
  ++frame_serial;
  pthread_mutex_unlock(&frame_lock);
  pthread_mutex_unlock(&render_lock);
  frame_published(summary);
}

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
  pthread_mutex_unlock(&lock);
  memset(temp, 0, sizeof(temp));
  memset(code, 0, sizeof(code));
  sd_canvas canvas;
  steam_ui_begin(&canvas);
  pthread_mutex_lock(&lock);
  steam_bp_draw_page(&canvas, page_text, qr_size ? qr_modules : NULL, qr_size);
  pthread_mutex_unlock(&lock);
  steam_ui_end(NULL);
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

void steam_ui_poke(void)
{
  pthread_mutex_lock(&lock);
  poked = 1;
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
  /* one button: the first of the mask's order X, O, triangle, up, down... */
  return buttons & -buttons;
}

unsigned steam_ui_wait_for(unsigned mask, int timeout_ms)
{
  struct timespec until;
  clock_gettime(CLOCK_REALTIME, &until);
  until.tv_sec += timeout_ms / 1000;
  until.tv_nsec += (long)(timeout_ms % 1000) * 1000000L;
  if (until.tv_nsec >= 1000000000L) until.tv_sec += 1, until.tv_nsec -= 1000000000L;
  pthread_mutex_lock(&lock);
  int rc = 0;
  while (!(pressed & mask) && !poked && rc != ETIMEDOUT) rc = pthread_cond_timedwait(&pressed_cond, &lock, &until);
  unsigned buttons = pressed & mask;
  if (buttons) pressed = 0;
  poked = 0;
  pthread_mutex_unlock(&lock);
  return buttons & -buttons;
}

int steam_ui_hidden(void) { return hidden; }
void steam_ui_request_show(void)
{
  show_request = 1;
  steam_ui_poke();
}
int steam_ui_show_requested(void)
{
  if (!show_request) return 0;
  show_request = 0;
  return 1;
}

/* fonts: Wine's Tahoma from OrbisDesk's prefix, or (the host) STEAM_UI_FONTS */
static void load_fonts(void)
{
#ifdef STEAM_HOST
  const char *dir = getenv("STEAM_UI_FONTS");
  char regular[512], bold[512];
  snprintf(regular, sizeof(regular), "%s/tahoma.ttf", dir ? dir : "fonts");
  snprintf(bold, sizeof(bold), "%s/tahomabd.ttf", dir ? dir : "fonts");
  const int rc = sd_fonts_load(regular, bold);
#else
  errno = 0;
  const int rc = sd_fonts_load("/data/wine-prefix/drive_c/windows/Fonts/tahoma.ttf",
                               "/data/wine-prefix/drive_c/windows/Fonts/tahomabd.ttf");
#endif
  const int error = errno;
  if (note && (rc || pw_trace_on())) note("PWSTEAM ui fonts=%s errno=%d", rc == 0 ? "tahoma" : rc == 1 ? "tahoma_regular_only" : "bitmap", rc ? error : 0);
}

#if !defined(STEAM_HOST)
#include <orbis/Pad.h>
#include <orbis/libkernel.h>

/* The pad's newly pressed buttons as STEAM_UI_* bits: the d-pad and the left stick are directions, repeated
 * after 400 ms held, every 110 ms. `fresh`: what is down now counts as held, not pressed (the X that opened
 * the client). */
static unsigned held_bits;
static uint64_t repeat_at;
static int fresh = 1;
static unsigned bits_of(const OrbisPadData *data)
{
  const uint32_t down = data->buttons;
  unsigned bits = (down & ORBIS_PAD_BUTTON_CROSS ? STEAM_UI_CROSS : 0) | (down & ORBIS_PAD_BUTTON_CIRCLE ? STEAM_UI_CIRCLE : 0) |
                  (down & ORBIS_PAD_BUTTON_TRIANGLE ? STEAM_UI_TRIANGLE : 0) | (down & ORBIS_PAD_BUTTON_UP ? STEAM_UI_UP : 0) |
                  (down & ORBIS_PAD_BUTTON_DOWN ? STEAM_UI_DOWN : 0) | (down & ORBIS_PAD_BUTTON_LEFT ? STEAM_UI_LEFT : 0) |
                  (down & ORBIS_PAD_BUTTON_RIGHT ? STEAM_UI_RIGHT : 0) |
                  (down & (ORBIS_PAD_BUTTON_L1 | ORBIS_PAD_BUTTON_L2) ? STEAM_UI_L1 : 0) |
                  (down & (ORBIS_PAD_BUTTON_R1 | ORBIS_PAD_BUTTON_R2) ? STEAM_UI_R1 : 0) |
                  (down & ORBIS_PAD_BUTTON_SQUARE ? STEAM_UI_SQUARE : 0) |
                  (down & ORBIS_PAD_BUTTON_OPTIONS ? STEAM_UI_OPTIONS : 0);
  if (data->leftStick.y < 40) bits |= STEAM_UI_UP;
  if (data->leftStick.y > 215) bits |= STEAM_UI_DOWN;
  if (data->leftStick.x < 40) bits |= STEAM_UI_LEFT;
  if (data->leftStick.x > 215) bits |= STEAM_UI_RIGHT;
  return bits;
}
static void pad_input(const OrbisPadData *data)
{
  const unsigned bits = bits_of(data), directions = STEAM_UI_UP | STEAM_UI_DOWN | STEAM_UI_LEFT | STEAM_UI_RIGHT;
  const uint64_t now = sceKernelGetProcessTime();
  if (fresh) {
    fresh = 0;
    held_bits = bits;
    return;
  }
  unsigned down = bits & ~held_bits;
  if (down & directions) repeat_at = now + 400000;
  else if ((bits & directions) && now >= repeat_at) {
    down |= bits & directions;
    repeat_at = now + 110000;
  }
  held_bits = bits;
  press(down);
}
#endif

/* steam_ui.h: the client is past its start; set by its thread, read by the sink's */
static volatile int client_started;
void steam_ui_started(void) { client_started = 1; }

#ifdef STEAM_HOST
/* The host: each frame's text on stdout, buttons from stdin, PNG snapshots on request. */
static unsigned snapshots;
static void page_changed(void) {}
static void frame_published(const char *summary)
{
  pthread_mutex_lock(&lock);
  printf("---- screen ----\n%s\n", summary ? summary : page_text);
  for (int y = -2; y < qr_size + 2 && qr_size && !summary; ++y) {
    for (int x = -2; x < qr_size + 2; ++x) {
      const int dark = y >= 0 && x >= 0 && y < qr_size && x < qr_size && qr_modules[y * qr_size + x];
      fputs(dark ? "  " : "\xe2\x96\x88\xe2\x96\x88", stdout);
    }
    fputc('\n', stdout);
  }
  printf("---- buttons: x o t s u d < > l r p ----\n");
  fflush(stdout);
  pthread_mutex_unlock(&lock);
  const char *dir = getenv("STEAM_UI_SNAPSHOTS");
  if (dir && *dir) {
    char path[600];
    snprintf(path, sizeof(path), "%s/frame-%04u.png", dir, snapshots++);
    pthread_mutex_lock(&frame_lock);
    if (front >= 0) {
      sd_canvas c;
      sd_begin(&c, frames[front], frame_w, frame_h, frame_w);
      sd_write_png(&c, path);
    }
    pthread_mutex_unlock(&frame_lock);
  }
}
static void *run(void *unused)
{
  (void)unused;
  char line[64];
  while (running) {
    if (!fgets(line, sizeof(line), stdin)) {
      usleep(100000);
      continue;
    }
    const char c = line[0];
    press(c == 'x' ? STEAM_UI_CROSS : c == 'o' ? STEAM_UI_CIRCLE : c == 't' ? STEAM_UI_TRIANGLE : c == 'u' ? STEAM_UI_UP :
          c == 'd' ? STEAM_UI_DOWN : c == 'l' ? STEAM_UI_L1 : c == 'r' ? STEAM_UI_R1 : c == 's' ? STEAM_UI_SQUARE :
          c == 'p' ? STEAM_UI_OPTIONS : c == '<' || c == 'h' ? STEAM_UI_LEFT : c == '>' || c == 'k' ? STEAM_UI_RIGHT : 0);
  }
  return NULL;
}
int steam_ui_open(steam_ui_note log)
{
  pthread_t reader;
  note = log;
  const char *size = getenv("STEAM_UI_SIZE");
  want_w = 1280, want_h = 720;
  if (size && sscanf(size, "%dx%d", (int *)&want_w, (int *)&want_h) != 2) want_w = 1280, want_h = 720;
  load_fonts();
  running = 1;
  if (pthread_create(&reader, NULL, run, NULL)) return -1;
  pthread_detach(reader);
  return 0;
}
void steam_ui_hide(void) { hidden = 1; }
void steam_ui_unhide(void) { hidden = 0; }
void steam_ui_close(void) { running = 0; }
#elif defined(STEAM_UI_HOSTED)
/* OrbisDesk's sink shows a frame only when Wine presents or this is called (native/hw_overlay.c does the
 * same): each published frame is a new one. */
extern void pw_hw_cursor_moved(void);
/* native/wine_hardware.c: a Big Picture start (the client opens itself on the first frame) and its first
 * frame drawn (the start worked). Weak: an ELF without them only has the desktop. */
extern int pw_hw_bigpicture_boot(void) __attribute__((weak));
extern void pw_hw_bigpicture_ready(void) __attribute__((weak));
extern const char *pw_hw_steam_open(void);
static volatile int swallow;  /* after closing or hiding, the pad stays here until every button is up */
static void page_changed(void) {}
static void frame_published(const char *summary)
{
  (void)summary;
  if (running && !hidden) pw_hw_cursor_moved();
}

int steam_ui_open(steam_ui_note log)
{
  note = log;
  want_w = 1280, want_h = 720;  /* the sink's output (pw_wine_sink_ps4.c OUT_WIDTH x OUT_HEIGHT) */
  load_fonts();
  fresh = 1;  /* what is down now (the X that opened it) counts as held, not as a press */
  hidden = 0;
  running = 1;
  pw_hw_cursor_moved();
  note("PWSTEAM ui hosted open");
  return 0;
}

void steam_ui_hide(void)
{
  if (hidden) return;
  hidden = 1;
  swallow = 1;
  pw_hw_cursor_moved();  /* the game's frame again */
  if (pw_trace_on()) note("PWSTEAM ui hidden");
}

void steam_ui_unhide(void)
{
  if (!hidden) return;
  fresh = 1;
  hidden = 0;
  pw_hw_cursor_moved();
  if (pw_trace_on()) note("PWSTEAM ui shown");
}

void steam_ui_close(void)
{
  if (!running) return;
  running = 0;
  hidden = 0;
  swallow = 1;
  pw_hw_cursor_moved();  /* the desktop's frame again */
  note("PWSTEAM ui hosted close");
}

int pw_hw_steam_active(void) { return running && !hidden; }

/* The sink, for every frame it shows: the client's last frame over the whole screen while it is open. 1 when
 * it drew. In a Big Picture start the first frame opens the client. */
int pw_hw_steam_draw(uint32_t *pixels, unsigned pitch, unsigned width, unsigned height)
{
  static int autostarted, ready;
  if (!running) {
    if (!autostarted && pw_hw_bigpicture_boot && pw_hw_bigpicture_boot()) {
      autostarted = 1;
      pw_hw_steam_open();
    }
    return 0;
  }
  if (hidden) return 0;
  if ((int)width != want_w || (int)height != want_h) {
    want_w = (int)width;
    want_h = (int)height;
    steam_ui_poke();
  }
  pthread_mutex_lock(&frame_lock);
  if (front < 0) {
    for (unsigned y = 0; y < height; ++y)
      for (unsigned x = 0; x < width; ++x) pixels[(size_t)y * pitch + x] = 0xff0b0e12;
  } else if ((unsigned)frame_w == width && (unsigned)frame_h == height) {
    for (unsigned y = 0; y < height; ++y) memcpy(pixels + (size_t)y * pitch, frames[front] + (size_t)y * frame_w, (size_t)width * 4);
  } else {
    for (unsigned y = 0; y < height; ++y) {
      const uint32_t *row = frames[front] + (size_t)(y * (unsigned)frame_h / height) * frame_w;
      for (unsigned x = 0; x < width; ++x) pixels[(size_t)y * pitch + x] = row[x * (unsigned)frame_w / width];
    }
  }
  const int drew = front >= 0;
  pthread_mutex_unlock(&frame_lock);
  /* a Big Picture start worked once the client is past its start, not at its first frame */
  if (drew && client_started && !ready) {
    ready = 1;
    if (pw_hw_bigpicture_ready) pw_hw_bigpicture_ready();
  }
  return 1;
}

/* The pad thread, for every read: 1 while the client (or the release after it) has the pad, which the
 * desktop then reads neutral. */
int pw_hw_steam_pad(const OrbisPadData *data)
{
  if (!running || hidden) {
    if (!swallow) return 0;
    if (data->buttons) return 1;
    swallow = 0;
    return 1;
  }
  pad_input(data);
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
static void frame_published(const char *summary) { (void)summary; }

static void *run(void *unused)
{
  (void)unused;
  unsigned drawn = ~0u, frame = 0;
  while (running) {
    OrbisPadData data;
    memset(&data, 0, sizeof(data));
    if (pad >= 0 && !scePadReadState(pad, &data) && data.connected) pad_input(&data);
    if (frame_serial != drawn) {
      uint32_t *target = buffers[frame % BUFFERS];
      pthread_mutex_lock(&frame_lock);
      drawn = frame_serial;
      if (front >= 0 && frame_w == WIDTH && frame_h == HEIGHT) memcpy(target, frames[front], (size_t)WIDTH * HEIGHT * 4);
      pthread_mutex_unlock(&frame_lock);
      const int rc = sceVideoOutSubmitFlip(video, (int32_t)(frame % BUFFERS), FLIP_VSYNC, (int64_t)frame);
      static unsigned flip_failures;  /* every frame while flips fail: the first 16 */
      if (rc && flip_failures++ < 16) note("PWSTEAM ui flip rc=0x%08x", (unsigned)rc);
      ++frame;
    }
    sceKernelUsleep(16000);
  }
  return NULL;
}

int steam_ui_open(steam_ui_note log)
{
  note = log;
  want_w = WIDTH, want_h = HEIGHT;
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
  load_fonts();

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

/* the standalone title has nothing to hide behind */
void steam_ui_hide(void) { hidden = 1; }
void steam_ui_unhide(void) { hidden = 0; }

void steam_ui_close(void)
{
  if (!running) return;
  running = 0;
  pthread_join(thread, NULL);
}
#endif
