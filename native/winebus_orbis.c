/*
 * winebus: the console's pad as an XInput-compatible HID gamepad (OrbisDesk)
 *
 * This library is free software; you can redistribute it and/or
 * modify it under the terms of the GNU Lesser General Public
 * License as published by the Free Software Foundation; either
 * version 2.1 of the License, or (at your option) any later version.
 *
 * This library is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
 * Lesser General Public License for more details.
 */

/* Compiled by tools/build-hidstack-hw.py in place of bus_sdl.c, so winebus.sys's PE side runs
 * unchanged: its "SDL" bus thread calls these sdl_bus_* entry points. One device, laid out as
 * bus_sdl.c lays out a mapped game controller (hid_device_add_gamepad). By default (W213) it is a
 * generic HID gamepad (1209:5057); with C:\orbis\padhid-xinput.txt it is a wired Xbox 360
 * controller (045e:028e), so winebus adds WINEBUS\WINE_COMP_XINPUT and winexinput.sys makes the
 * "&IG_00" HID device that games (Unity, SDL) pair with XInput slot 0.
 * The state comes from native/hw_pad.c through pw_wine_pad_peek, which, unlike pw_wine_pad
 * (xinput), does not count as a game reading the pad: hw_pad.c's game mode stays with XInput.
 * W236: the controller type of the overlay (native/hw_overlay.c, C:\orbis\padtype.txt). With
 * padhid-xinput.txt, Xbox One makes it 045e:02ea. DualSense makes it a raw HID DualSense (054c:0ce6)
 * with that controller's USB reports, whatever padhid-xinput.txt says. A change while running
 * removes the device and adds the new one, as an unplug and a plug. */

#if 0
#pragma makedep unix
#endif

#include "config.h"

#include <errno.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "ntstatus.h"
#define WIN32_NO_STATUS
#include "windef.h"
#include "winbase.h"
#include "winternl.h"
#include "ddk/wdm.h"
#include "ddk/hidtypes.h"
#include "hidusage.h"

#include "wine/debug.h"
#include "wine/unixlib.h"
#include "unix_private.h"

WINE_DEFAULT_DEBUG_CHANNEL(hid);

/* native/hw_pad.c's struct PwXinputPad (XInput terms: y grows upwards) */
struct orbis_pad
{
    UINT32 packet;
    UINT16 buttons;
    BYTE left_trigger, right_trigger;
    INT16 thumb_lx, thumb_ly, thumb_rx, thumb_ry;
    BYTE connected;
};
extern int pw_wine_pad_available(void);
extern int pw_wine_pad_peek(struct orbis_pad *state);
extern void pw_wine_set_rumble(unsigned int left, unsigned int right);
/* W236: native/hw_pad.c, absent from ELFs without the launcher (weak: NULL there) */
extern int pw_wine_pad_dualsense(BYTE *report) __attribute__((weak));
extern void pw_wine_set_lightbar(unsigned int r, unsigned int g, unsigned int b) __attribute__((weak));

enum { POLL_NS = 8000000 };
/* W213: the pad is a generic HID gamepad by default (pid.codes 1209:5057); C:\orbis\padhid-xinput.txt
 * makes it the Xbox 360 controller of W198-W208 again */
#define XINPUT_SWITCH "/data/wine-prefix/drive_c/orbis/padhid-xinput.txt"
enum { GENERIC_VID = 0x1209, GENERIC_PID = 0x5057 };
/* W236 */
#define TYPE_FILE "/data/wine-prefix/drive_c/orbis/padtype.txt"
enum { KIND_GENERIC, KIND_X360, KIND_XONE, KIND_DUALSENSE };
static const char *const kind_names[] = {"generic-hid", "xinput", "xinput-xone", "dualsense"};
enum { KIND_CHECK_POLLS = 32 };  /* the type file is read about 4 times a second */
enum { DUALSENSE_REPORT = 64 };

static pthread_mutex_t orbis_cs = PTHREAD_MUTEX_INITIALIZER;
static struct list event_queue = LIST_INIT(event_queue);
static struct unix_device *pad_device, *started_device;
static int pad_kind;
static UINT32 last_packet;
static BOOL last_connected;
static BYTE sent_report[256];  /* the last report queued: only changes are sent */
static USHORT sent_len;
static BYTE dualsense_sequence;
static volatile LONG quit;

static void orbis_device_destroy(struct unix_device *iface)
{
}

static NTSTATUS orbis_device_start(struct unix_device *iface)
{
    pthread_mutex_lock(&orbis_cs);
    if (iface == pad_device) started_device = iface;
    pthread_mutex_unlock(&orbis_cs);
    fprintf(stderr, "PWHID pad device started%s\n", iface == pad_device ? "" : " (already replaced)");
    return STATUS_SUCCESS;
}

/* W236: no list_remove here: the device is on no list (its entry was never initialised, and a
 * stop, which comes only with a removal, would have read through NULL) */
static void orbis_device_stop(struct unix_device *iface)
{
    pthread_mutex_lock(&orbis_cs);
    if (started_device == iface) started_device = NULL;
    pthread_mutex_unlock(&orbis_cs);
    pw_wine_set_rumble(0, 0);
    fprintf(stderr, "PWHID pad device stopped\n");
}

/* rumble is the low-frequency (large, left) motor and buzz the high-frequency one, as in bus_sdl.c */
static NTSTATUS orbis_device_haptics_start(struct unix_device *iface, UINT duration_ms,
                                           USHORT rumble_intensity, USHORT buzz_intensity,
                                           USHORT left_intensity, USHORT right_intensity)
{
    TRACE("duration %u, rumble %u, buzz %u\n", duration_ms, rumble_intensity, buzz_intensity);
    pw_wine_set_rumble(rumble_intensity, buzz_intensity);
    return STATUS_SUCCESS;
}

static NTSTATUS orbis_device_haptics_stop(struct unix_device *iface)
{
    pw_wine_set_rumble(0, 0);
    return STATUS_SUCCESS;
}

static NTSTATUS orbis_device_physical_device_control(struct unix_device *iface, USAGE control)
{
    ERR("PWHID no force feedback: device control %#x\n", control);
    return STATUS_NOT_SUPPORTED;
}

static NTSTATUS orbis_device_physical_device_set_gain(struct unix_device *iface, BYTE percent)
{
    ERR("PWHID no force feedback: gain %u\n", percent);
    return STATUS_NOT_SUPPORTED;
}

static NTSTATUS orbis_device_physical_effect_control(struct unix_device *iface, BYTE index,
                                                     USAGE control, BYTE iterations)
{
    ERR("PWHID no force feedback: effect %u control %#x\n", index, control);
    return STATUS_NOT_SUPPORTED;
}

static NTSTATUS orbis_device_physical_effect_update(struct unix_device *iface, BYTE index,
                                                    struct effect_params *params)
{
    ERR("PWHID no force feedback: effect %u update\n", index);
    return STATUS_NOT_SUPPORTED;
}

static const struct hid_device_vtbl orbis_device_vtbl =
{
    orbis_device_destroy,
    orbis_device_start,
    orbis_device_stop,
    orbis_device_haptics_start,
    orbis_device_haptics_stop,
    orbis_device_physical_device_control,
    orbis_device_physical_device_set_gain,
    orbis_device_physical_effect_control,
    orbis_device_physical_effect_update,
};

/* W236: a DualSense over USB. The report descriptor declares the controller's own layout: input
 * report 1 (64 bytes: sticks, triggers, a counter, hat and 15 buttons, then 52 vendor bytes with
 * sensors, touchpad, timestamps and battery), output report 2 (rumble, light bar, LEDs, triggers)
 * and the feature reports programs ask for (5 calibration, 9 pairing, 0x20 firmware). */
static const BYTE dualsense_descriptor[] =
{
    0x05, 0x01, 0x09, 0x05, 0xa1, 0x01,             /* Generic Desktop, Game Pad, Collection (Application) */
    0x85, 0x01,                                     /* Report ID 1 */
    0x09, 0x30, 0x09, 0x31, 0x09, 0x32, 0x09, 0x35, /* X Y Z Rz: the sticks */
    0x09, 0x33, 0x09, 0x34,                         /* Rx Ry: the triggers */
    0x15, 0x00, 0x26, 0xff, 0x00, 0x75, 0x08, 0x95, 0x06, 0x81, 0x02,
    0x06, 0x00, 0xff, 0x09, 0x20, 0x95, 0x01, 0x81, 0x02,  /* the report counter */
    0x05, 0x01, 0x09, 0x39, 0x15, 0x00, 0x25, 0x07, 0x35, 0x00, 0x46, 0x3b, 0x01, 0x65, 0x14,
    0x75, 0x04, 0x95, 0x01, 0x81, 0x42, 0x65, 0x00,        /* hat switch, null state 8 */
    0x05, 0x09, 0x19, 0x01, 0x29, 0x0f, 0x15, 0x00, 0x25, 0x01, 0x75, 0x01, 0x95, 0x0f, 0x81, 0x02,  /* 15 buttons */
    0x06, 0x00, 0xff, 0x09, 0x21, 0x95, 0x0d, 0x81, 0x02,  /* 13 vendor bits */
    0x06, 0x00, 0xff, 0x09, 0x22, 0x15, 0x00, 0x26, 0xff, 0x00, 0x75, 0x08, 0x95, 0x34, 0x81, 0x02,  /* 52 bytes */
    0x85, 0x02, 0x09, 0x23, 0x95, 0x2f, 0x91, 0x02,        /* output report 2, 47 bytes */
    0x85, 0x05, 0x09, 0x33, 0x95, 0x28, 0xb1, 0x02,        /* feature 5, 40 bytes */
    0x85, 0x09, 0x09, 0x24, 0x95, 0x13, 0xb1, 0x02,        /* feature 9, 19 bytes */
    0x85, 0x20, 0x09, 0x26, 0x95, 0x3f, 0xb1, 0x02,        /* feature 0x20, 63 bytes */
    0xc0,
};

static NTSTATUS dualsense_get_report_descriptor(struct unix_device *iface, BYTE *buffer, UINT length, UINT *out_length)
{
    *out_length = sizeof(dualsense_descriptor);
    if (length < sizeof(dualsense_descriptor)) return STATUS_BUFFER_TOO_SMALL;
    memcpy(buffer, dualsense_descriptor, sizeof(dualsense_descriptor));
    return STATUS_SUCCESS;
}

/* output report 2 (USB): [1] flags 0, [2] flags 1, [3] right (small) motor, [4] left (large) motor,
 * [45..47] light bar. The PS4 pad has the motors and the light bar; adaptive triggers, the mute
 * and player LEDs and audio have nothing to reach and are reported once. */
static void dualsense_set_output_report(struct unix_device *iface, HID_XFER_PACKET *packet, IO_STATUS_BLOCK *io)
{
    static int unsupported_logged;
    const BYTE *data = packet->reportBuffer;

    if (packet->reportId != 0x02 || packet->reportBufferLen < 48)
    {
        ERR("PWHID dualsense output report %#x length %u not supported\n", packet->reportId, packet->reportBufferLen);
        io->Status = STATUS_NOT_SUPPORTED;
        io->Information = 0;
        return;
    }
    if (data[1] & 0x03) pw_wine_set_rumble(data[4] << 8, data[3] << 8);
    if ((data[2] & 0x04) && pw_wine_set_lightbar) pw_wine_set_lightbar(data[45], data[46], data[47]);
    if (((data[1] & ~0x03) || (data[2] & ~0x04)) && unsupported_logged < 4)
    {
        unsupported_logged++;
        ERR("PWHID dualsense output flags %02x %02x: only rumble and the light bar reach the PS4 pad\n", data[1], data[2]);
    }
    io->Status = STATUS_SUCCESS;
    io->Information = packet->reportBufferLen;
}

static void dualsense_get_feature_report(struct unix_device *iface, HID_XFER_PACKET *packet, IO_STATUS_BLOCK *io)
{
    ERR("PWHID dualsense feature report %#x not supported (no calibration, pairing or firmware data)\n", packet->reportId);
    io->Status = STATUS_NOT_SUPPORTED;
    io->Information = 0;
}

static void dualsense_set_feature_report(struct unix_device *iface, HID_XFER_PACKET *packet, IO_STATUS_BLOCK *io)
{
    ERR("PWHID dualsense set feature report %#x not supported\n", packet->reportId);
    io->Status = STATUS_NOT_SUPPORTED;
    io->Information = 0;
}

static const struct raw_device_vtbl dualsense_vtbl =
{
    orbis_device_destroy,
    orbis_device_start,
    orbis_device_stop,
    dualsense_get_report_descriptor,
    dualsense_set_output_report,
    dualsense_get_feature_report,
    dualsense_set_feature_report,
};

/* the input report; the counter and the timestamp (bytes 7 and 49-52) are filled when it is sent */
static void dualsense_report(BYTE *report)
{
    if (pw_wine_pad_dualsense(report)) return;
    memset(report, 0, DUALSENSE_REPORT);  /* no pad: neutral, as a disconnected pad reads */
    report[0] = 0x01;
    report[1] = report[2] = report[3] = report[4] = 0x80;
    report[8] = 0x08;
    report[33] = report[37] = 0x80;
}

/* XInput button bits to the gamepad report's buttons, in bus_sdl.c's controller order */
static const struct { UINT16 bit; BYTE index; } button_map[] =
{
    {0x1000, 0}, {0x2000, 1}, {0x4000, 2}, {0x8000, 3}, /* A B X Y */
    {0x0100, 4}, {0x0200, 5},                           /* LB RB */
    {0x0020, 6}, {0x0010, 7},                           /* Back Start */
    {0x0040, 8}, {0x0080, 9},                           /* LS RS */
};

static void set_report(struct unix_device *iface, const struct orbis_pad *pad)
{
    unsigned int i;
    LONG x = 0, y = 0;

    hid_device_set_abs_axis(iface, 0, pad->thumb_lx);
    hid_device_set_abs_axis(iface, 1, pad->thumb_ly);
    hid_device_set_abs_axis(iface, 2, pad->thumb_rx);
    hid_device_set_abs_axis(iface, 3, pad->thumb_ry);
    hid_device_set_abs_axis(iface, 4, pad->left_trigger * 32767 / 255);
    hid_device_set_abs_axis(iface, 5, pad->right_trigger * 32767 / 255);

    if (pad->buttons & 0x0001) y = -1;
    if (pad->buttons & 0x0002) y = +1;
    if (pad->buttons & 0x0004) x = -1;
    if (pad->buttons & 0x0008) x = +1;
    hid_device_set_hatswitch_x(iface, 0, x);
    hid_device_set_hatswitch_y(iface, 0, y);

    for (i = 0; i < ARRAY_SIZE(button_map); i++)
        hid_device_set_button(iface, button_map[i].index, !!(pad->buttons & button_map[i].bit));
}

static NTSTATUS build_report_descriptor(struct unix_device *iface)
{
    const USAGE_AND_PAGE device_usage = {.UsagePage = HID_USAGE_PAGE_GENERIC, .Usage = HID_USAGE_GENERIC_GAMEPAD};
    struct orbis_pad pad = {0};

    if (!hid_device_begin_report_descriptor(iface, &device_usage)) return STATUS_NO_MEMORY;
    if (!hid_device_add_gamepad(iface)) return STATUS_NO_MEMORY;
    if (!hid_device_add_haptics(iface)) return STATUS_NO_MEMORY;
    if (!hid_device_end_report_descriptor(iface)) return STATUS_NO_MEMORY;

    pw_wine_pad_peek(&pad);
    set_report(iface, &pad);
    return STATUS_SUCCESS;
}

/* W236: which device the pad is now: the overlay's type, and padhid-xinput.txt for the Xbox ones */
static int current_kind(void)
{
    char text[16] = {0};
    FILE *file;
    int dualsense = 0, xone = 0;

    if ((file = fopen(TYPE_FILE, "r")))
    {
        if (!fgets(text, sizeof(text), file)) text[0] = 0;
        fclose(file);
        dualsense = !strncmp(text, "dualsense", 9);
        xone = !strncmp(text, "xone", 4);
    }
    if (dualsense)
    {
        if (pw_wine_pad_dualsense) return KIND_DUALSENSE;
        fprintf(stderr, "PWHID dualsense unavailable in this ELF: the pad stays as before\n");
    }
    if (!(file = fopen(XINPUT_SWITCH, "r"))) return KIND_GENERIC;
    fclose(file);
    return xone ? KIND_XONE : KIND_X360;
}

/* a new device of that kind, queued as created; orbis_cs held */
static NTSTATUS add_device(int kind)
{
    struct device_desc desc =
    {
        .vid = 0x045e,
        .pid = 0x028e,
        .version = 0x0114,
        .input = -1,
        .uid = 0,
        .bus_type = BUS_TYPE_USB,
        .bus_id = -1,
        .is_gamepad = TRUE,
        .is_hidraw = FALSE,
    };
    struct unix_device *iface;
    NTSTATUS status;
    const char *product = "Controller (XBOX 360 For Windows)", *manufacturer = "OrbisDesk";

    /* W213: a generic HID gamepad (not an Xbox controller) unless C:\orbis\padhid-xinput.txt exists.
     * As an Xbox controller, winexinput's "&IG_" device makes Unity 2020's legacy input poll XInput
     * every frame; that turns hw_pad.c's game mode on (no pointer or key emulation) while Unity's
     * InputManager still ignored the pad (W208). As a generic gamepad Unity does not use XInput, so
     * the emulation and key profiles (C:\orbis\padmaps) keep working. XInput (xinput1_3, the pad as
     * controller 0) and DirectInput (joystick_pad.c) are the same in both modes. */
    if (kind == KIND_GENERIC)
    {
        desc.vid = GENERIC_VID;
        desc.pid = GENERIC_PID;
        desc.version = 0x0100;
        desc.is_gamepad = FALSE;
        product = "OrbisDesk Gamepad";
    }
    else if (kind == KIND_XONE)
    {
        desc.pid = 0x02ea;
        desc.version = 0x0408;
        product = "Controller (Xbox One For Windows)";
    }
    else if (kind == KIND_DUALSENSE)
    {
        /* raw: winebus takes it as hidraw (main.c is_hidraw_enabled prefers it for a DualSense);
         * not a gamepad for winexinput, which would pair it with XInput */
        desc.vid = 0x054c;
        desc.pid = 0x0ce6;
        desc.version = 0x0100;
        desc.is_gamepad = FALSE;
        desc.is_hidraw = TRUE;
        product = "Wireless Controller";
        manufacturer = "Sony Interactive Entertainment";
    }

    ntdll_umbstowcs(manufacturer, strlen(manufacturer) + 1, desc.manufacturer, ARRAY_SIZE(desc.manufacturer));
    ntdll_umbstowcs(product, strlen(product) + 1, desc.product, ARRAY_SIZE(desc.product));
    ntdll_umbstowcs("0000", sizeof("0000"), desc.serialnumber, ARRAY_SIZE(desc.serialnumber));

    if (kind == KIND_DUALSENSE)
    {
        if (!(iface = raw_device_create(&dualsense_vtbl, sizeof(struct unix_device)))) return STATUS_NO_MEMORY;
    }
    else
    {
        if (!(iface = hid_device_create(&orbis_device_vtbl, sizeof(struct unix_device)))) return STATUS_NO_MEMORY;
        if ((status = build_report_descriptor(iface)))
        {
            fprintf(stderr, "PWHID report descriptor failed status=%#x\n", (unsigned int)status);
            iface->vtbl->destroy(iface);
            free(iface);
            return status;
        }
    }

    pad_device = iface;
    pad_kind = kind;
    last_packet = 0;
    sent_len = 0;
    bus_event_queue_device_created(&event_queue, iface, &desc);
    fprintf(stderr, "PWHID pad bus init vid=%04x pid=%04x mode=%s\n", desc.vid, desc.pid, kind_names[kind]);
    return STATUS_SUCCESS;
}

NTSTATUS sdl_bus_init(void *args)
{
    NTSTATUS status;

    if (!pw_wine_pad_available())
    {
        fprintf(stderr, "PWHID no console pad in this ELF\n");
        return STATUS_NOT_SUPPORTED;
    }

    pthread_mutex_lock(&orbis_cs);
    status = add_device(current_kind());
    pthread_mutex_unlock(&orbis_cs);
    return status;
}

/* W236: the type changed: the old device goes (its stop and release come from the PE side; the
 * reference this bus took at its creation is kept, a few bytes per change), the new one comes */
static void replace_device(int kind)
{
    fprintf(stderr, "PWHID pad type change %s -> %s: removing the device\n", kind_names[pad_kind], kind_names[kind]);
    if (pad_device && !bus_event_queue_device_removed(&event_queue, pad_device))
        fprintf(stderr, "PWHID pad removal not queued\n");
    pad_device = NULL;
    started_device = NULL;
    if (add_device(kind)) fprintf(stderr, "PWHID pad type change: no new device\n");
}

NTSTATUS sdl_bus_wait(void *args)
{
    struct bus_event *result = args;
    struct timespec delay = {0, POLL_NS};
    struct orbis_pad pad;
    unsigned int polls = 0;

    /* cleanup previously returned event */
    bus_event_cleanup(result);

    while (!quit)
    {
        BOOL queued = FALSE;
        int kind = -1;

        if (!(++polls % KIND_CHECK_POLLS)) kind = current_kind();
        pthread_mutex_lock(&orbis_cs);
        if (bus_event_queue_pop(&event_queue, result))
        {
            pthread_mutex_unlock(&orbis_cs);
            return STATUS_PENDING;
        }
        if (kind >= 0 && kind != pad_kind) replace_device(kind);
        if (started_device && pad_device == started_device && pad_kind == KIND_DUALSENSE)
        {
            BYTE report[DUALSENSE_REPORT];
            struct timespec now;

            dualsense_report(report);
            if (!sent_len || memcmp(report, sent_report, DUALSENSE_REPORT))
            {
                /* the counter and timestamp are not compared: a report goes only when an input changed */
                memcpy(sent_report, report, DUALSENSE_REPORT);
                sent_len = DUALSENSE_REPORT;
                clock_gettime(CLOCK_MONOTONIC, &now);
                {
                    UINT32 stamp = (UINT32)((now.tv_sec * 1000000ull + now.tv_nsec / 1000) * 3);  /* 1/3 us units */
                    report[7] = dualsense_sequence++;
                    memcpy(report + 49, &stamp, sizeof(stamp));
                }
                queued = bus_event_queue_input_report(&event_queue, pad_device, report, DUALSENSE_REPORT);
            }
        }
        else if (started_device && pad_device == started_device)
        {
            memset(&pad, 0, sizeof(pad));
            pw_wine_pad_peek(&pad);
            if (pad.connected != last_connected)
            {
                last_connected = pad.connected;
                fprintf(stderr, "PWHID pad connected=%u\n", pad.connected);
            }
            /* a disconnected pad reads neutral, so the game sees released inputs */
            if (pad.packet != last_packet || !pad.connected)
            {
                struct hid_device_state *state = &pad_device->hid_device_state;
                last_packet = pad.packet;
                set_report(pad_device, &pad);
                if (state->report_len <= sizeof(sent_report) &&
                    (!sent_len || memcmp(state->report_buf, sent_report, state->report_len)))
                {
                    queued = bus_event_queue_input_report(&event_queue, pad_device, state->report_buf, state->report_len);
                    memcpy(sent_report, state->report_buf, state->report_len);
                    sent_len = state->report_len;
                }
            }
        }
        pthread_mutex_unlock(&orbis_cs);
        if (!queued) nanosleep(&delay, NULL);
    }

    TRACE("Orbis pad bus exiting\n");
    pthread_mutex_lock(&orbis_cs);
    bus_event_queue_destroy(&event_queue);
    pthread_mutex_unlock(&orbis_cs);
    return STATUS_SUCCESS;
}

NTSTATUS sdl_bus_stop(void *args)
{
    quit = 1;
    return STATUS_SUCCESS;
}
